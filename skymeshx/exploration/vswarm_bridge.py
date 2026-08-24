"""
VSwarmBridge — connects SkyMeshX to the EPFL LIS vswarm ROS package.

Reference: https://github.com/lis-epfl/vswarm
Paper: Schilling et al., IEEE RA-L 2021
       "Vision-based Drone Flocking in Outdoor Environments"

vswarm is a decentralized, communication-free swarm controller:
  - Detects neighboring drones via CNN on omnidirectional camera images
  - Estimates relative positions from camera + known drone size
  - Multi-target tracking (RFS filter)
  - Reynolds-inspired flocking (no inter-drone communication needed)

Architecture:
    SkyMeshX        vswarm ROS nodes
    /camera/image  ───▶  object_detector  ───▶  relative_localizer
                                                       │
                                                  multi_target_tracker
                                                       │
    MAVLink goto   ◀──── velocity target  ◀────  flocking_controller

Topics published to vswarm:
    /{ns}/image            sensor_msgs/Image        (from drone camera)
    /{ns}/camera_info      sensor_msgs/CameraInfo   (calibration)
    /{ns}/odometry         nav_msgs/Odometry        (MAVLink telemetry)

Topics received from vswarm:
    /{ns}/cmd_vel          geometry_msgs/Twist      (flocking velocity cmd)
    /{ns}/detections       vision_msgs/Detection2DArray (optional, debug)

Services:
    /{ns}/takeoff          std_srvs/SetBool
    /{ns}/offboard         std_srvs/SetBool         (start flocking)

Usage:
    from skymeshx import Drone
    from skymeshx.exploration import VSwarmBridge

    drone = Drone("tcp:127.0.0.1:5760")
    drone.connect()

    bridge = VSwarmBridge(drone, camera_topic="/camera/image_raw")
    bridge.start()
    drone.arm()
    drone.takeoff(altitude=2.5)
    bridge.start_flocking()
    # drone now follows Reynolds flocking law autonomously
"""
import math
import threading
import time
from typing import Callable, Optional

try:
    import rclpy
    from rclpy.node import Node
    from nav_msgs.msg import Odometry
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import Image, CameraInfo
    from std_srvs.srv import SetBool
    _ROS2_OK = True
except ImportError:
    _ROS2_OK = False

from skymeshx.ros.context import acquire_ros, release_ros
from skymeshx.exceptions import DependencyError, ROS2InitError, ROS2NotAvailableError


def _euler_to_quat(roll, pitch, yaw):
    r, p, y = math.radians(roll), math.radians(pitch), math.radians(yaw)
    cr, sr = math.cos(r/2), math.sin(r/2)
    cp, sp = math.cos(p/2), math.sin(p/2)
    cy, sy = math.cos(y/2), math.sin(y/2)
    return (
        sr*cp*cy - cr*sp*sy,
        cr*sp*cy + sr*cp*sy,
        cr*cp*sy - sr*sp*cy,
        cr*cp*cy + sr*sp*sy,
    )


class VSwarmBridge:
    """
    Bridges SkyMeshX ↔ vswarm flocking controller.

    Velocity commands from vswarm are converted to MAVLink position
    targets (drone.goto) at a configurable integration rate.

    Parameters
    ----------
    drone           : Drone instance
    camera_topic    : ROS2 topic providing sensor_msgs/Image
    camera_info_topic: ROS2 topic providing sensor_msgs/CameraInfo
    ns              : vswarm node namespace (default: /vswarm)
    publish_hz      : Odometry publish rate
    cmd_vel_gain    : Scale factor for velocity → position step (m/s * dt)
    on_cmd_vel      : Optional callback(vx, vy, vz) for every velocity command
    """

    def __init__(
        self,
        drone,
        camera_topic:      str   = "/camera/image_raw",
        camera_info_topic: str   = "/camera/camera_info",
        ns:                str   = "/vswarm",
        publish_hz:        float = 10.0,
        cmd_vel_gain:      float = 1.0,
        on_cmd_vel:        Optional[Callable] = None,
    ):
        if not _ROS2_OK:
            raise DependencyError(
                "rclpy",
                "install ROS2 Humble: https://docs.ros.org/en/humble/Installation.html",
            )
        self._drone          = drone
        self._camera_topic   = camera_topic
        self._caminfo_topic  = camera_info_topic
        self._ns             = ns
        self._hz             = publish_hz
        self._gain           = cmd_vel_gain
        self._on_cmd_vel     = on_cmd_vel
        self._node: Optional[Node] = None
        self._thread: Optional[threading.Thread] = None
        self._running        = False
        self._flocking       = False
        # Latest velocity command from vswarm
        self._cmd_vx         = 0.0
        self._cmd_vy         = 0.0
        self._cmd_vz         = 0.0
        self._cmd_yaw_rate   = 0.0
        # Velocity integration thread
        self._vel_thread: Optional[threading.Thread] = None
        self._vel_dt         = 0.25    # seconds between position updates

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        if not _ROS2_OK:
            raise ROS2NotAvailableError("ROS2 not available")
        if not acquire_ros():
            raise ROS2InitError("rclpy.init() failed")
        self._running = True
        self._thread  = threading.Thread(
            target=self._spin, daemon=True, name="vswarm-bridge"
        )
        self._thread.start()
        time.sleep(0.5)

    def stop(self):
        if not self._running:
            return
        self._running  = False
        self._flocking = False
        try:
            if self._node is not None:
                self._node.destroy_node()
        except Exception as e:
            print(f"[vswarm-bridge] destroy_node error: {e}")
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        release_ros()

    # ── Flocking control ──────────────────────────────────────────────────

    def start_flocking(self):
        """Call vswarm offboard service to enable flocking."""
        if self._node:
            self._node.call_offboard(True)
        self._flocking = True
        # Start velocity → goto integration loop
        self._vel_thread = threading.Thread(
            target=self._vel_integration_loop, daemon=True, name="vswarm-vel"
        )
        self._vel_thread.start()

    def stop_flocking(self):
        self._flocking = False
        if self._node:
            self._node.call_offboard(False)
        self._cmd_vx = self._cmd_vy = self._cmd_vz = 0.0

    @property
    def flocking(self) -> bool:
        return self._flocking

    @property
    def current_cmd_vel(self) -> tuple:
        """Returns latest (vx, vy, vz, yaw_rate) from vswarm."""
        return (self._cmd_vx, self._cmd_vy, self._cmd_vz, self._cmd_yaw_rate)

    # ── Velocity → position integration ──────────────────────────────────

    def _vel_integration_loop(self):
        """
        Converts vswarm cmd_vel (velocity) to MAVLink goto commands.

        vswarm outputs body-frame velocity; we integrate to get
        a position target in NED and send drone.goto().
        """
        dt = self._vel_dt
        while self._flocking and self._running:
            t = self._drone.telemetry
            if abs(self._cmd_vx) > 0.05 or abs(self._cmd_vy) > 0.05 or abs(self._cmd_vz) > 0.05:
                # Rotate body-frame → NED using current yaw
                yaw_rad = math.radians(t.yaw)
                # Body x=forward, y=left, z=up → NED north, east, down
                v_north =  self._cmd_vx * math.cos(yaw_rad) - self._cmd_vy * math.sin(yaw_rad)
                v_east  =  self._cmd_vx * math.sin(yaw_rad) + self._cmd_vy * math.cos(yaw_rad)
                v_up    =  self._cmd_vz

                # Integrate: new position = current + velocity * dt * gain
                dlat = (v_north * dt * self._gain) / 111320.0
                dlon = (v_east  * dt * self._gain) / (
                    111320.0 * math.cos(math.radians(t.lat)) + 1e-9
                )
                dalt = v_up * dt * self._gain

                target_lat = t.lat     + dlat
                target_lon = t.lon     + dlon
                target_alt = t.alt_rel + dalt

                self._drone._conn.goto(target_lat, target_lon, target_alt)
            time.sleep(dt)

    # ── Internal ──────────────────────────────────────────────────────────

    def _on_cmd_vel_received(self, vx, vy, vz, yaw_rate):
        self._cmd_vx      = vx
        self._cmd_vy      = vy
        self._cmd_vz      = vz
        self._cmd_yaw_rate = yaw_rate
        if self._on_cmd_vel:
            self._on_cmd_vel(vx, vy, vz, yaw_rate)

    def _spin(self):
        # rclpy.init() handled by acquire_ros() in start().
        self._node = _VSwarmNode(
            ns              = self._ns,
            drone           = self._drone,
            hz              = self._hz,
            camera_topic    = self._camera_topic,
            caminfo_topic   = self._caminfo_topic,
            on_cmd_vel      = self._on_cmd_vel_received,
        )
        try:
            while self._running and rclpy.ok():
                rclpy.spin_once(self._node, timeout_sec=0.1)
        except Exception as e:
            print(f"[vswarm-bridge] ROS spin error: {e}")
        # Node teardown handled by stop().


if _ROS2_OK:
    class _VSwarmNode(Node):
        def __init__(self, ns, drone, hz, camera_topic, caminfo_topic, on_cmd_vel):
            super().__init__("skymeshx_vswarm_bridge")
            self._drone      = drone
            self._on_cmd_vel = on_cmd_vel

            # Publish odometry to vswarm
            self._pub_odom = self.create_publisher(
                Odometry, f"{ns}/odometry", 10
            )

            # Subscribe to vswarm velocity commands
            self.create_subscription(
                Twist, f"{ns}/cmd_vel", self._cb_cmd_vel, 10
            )

            # Forward camera image + info to vswarm
            self.create_subscription(
                Image,      camera_topic,  self._cb_image,    10
            )
            self.create_subscription(
                CameraInfo, caminfo_topic, self._cb_caminfo,  10
            )
            self._pub_image   = self.create_publisher(Image,      f"{ns}/image",       10)
            self._pub_caminfo = self.create_publisher(CameraInfo, f"{ns}/camera_info", 10)

            # Service clients
            self._svc_takeoff  = self.create_client(SetBool, f"{ns}/takeoff")
            self._svc_offboard = self.create_client(SetBool, f"{ns}/offboard")

            self.create_timer(1.0 / hz, self._publish_odom)

        def _publish_odom(self):
            t   = self._drone.telemetry
            now = self.get_clock().now().to_msg()
            odom = Odometry()
            odom.header.stamp    = now
            odom.header.frame_id = "world"
            odom.child_frame_id  = "base_link"
            odom.pose.pose.position.x = t.lat
            odom.pose.pose.position.y = t.lon
            odom.pose.pose.position.z = t.alt_rel
            qx, qy, qz, qw = _euler_to_quat(t.roll, t.pitch, t.yaw)
            odom.pose.pose.orientation.x = qx
            odom.pose.pose.orientation.y = qy
            odom.pose.pose.orientation.z = qz
            odom.pose.pose.orientation.w = qw
            odom.twist.twist.linear.x = t.vx
            odom.twist.twist.linear.y = t.vy
            odom.twist.twist.linear.z = t.vz
            self._pub_odom.publish(odom)

        def _cb_cmd_vel(self, msg: Twist):
            self._on_cmd_vel(
                msg.linear.x, msg.linear.y, msg.linear.z,
                msg.angular.z
            )

        def _cb_image(self, msg: Image):
            self._pub_image.publish(msg)

        def _cb_caminfo(self, msg: CameraInfo):
            self._pub_caminfo.publish(msg)

        def call_takeoff(self, enable: bool):
            req = SetBool.Request()
            req.data = enable
            if self._svc_takeoff.wait_for_service(timeout_sec=2.0):
                self._svc_takeoff.call_async(req)

        def call_offboard(self, enable: bool):
            req = SetBool.Request()
            req.data = enable
            if self._svc_offboard.wait_for_service(timeout_sec=2.0):
                self._svc_offboard.call_async(req)
