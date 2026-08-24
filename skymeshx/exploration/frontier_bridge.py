"""
FrontierExplorationBridge — connects SkyMeshX to the larics
uav_frontier_exploration_3d ROS package.

Reference: https://github.com/larics/uav_frontier_exploration_3d
Paper: Batinovic et al., IEEE RA-L 2021

Topics published to the explorer:
    /exploration/odometry      nav_msgs/Odometry
    /exploration/cloud_in      sensor_msgs/PointCloud2  (passthrough, see below)
    /exploration/carrot_pose   geometry_msgs/PoseStamped

Topics received from the explorer:
    /exploration/point_reached std_msgs/Bool
    /exploration/octomap_volume std_msgs/Float64MultiArray

Services called:
    /exploration/toggle        std_srvs/SetBool   (start/stop)
    /exploration/save_octomap  std_srvs/Empty     (save map)

Frame Convention
----------------
All positions use local NED (North-East-Down) coordinates:
- x: North (meters)
- y: East (meters)
- z: Altitude above ground (meters, positive UP)

Note: Odometry messages are converted to ROS2 ENU frame for the explorer.
Frontier points received from the explorer are converted back to NED.

Usage:
    from skymeshx import Drone
    from skymeshx.exploration import FrontierExplorationBridge

    drone = Drone("tcp:127.0.0.1:5760")
    drone.connect()

    bridge = FrontierExplorationBridge(drone)
    bridge.start()
    bridge.exploration_start()
    # drone now flies autonomously to frontier points
    bridge.wait_until_done()
    bridge.stop()
"""

import math
import struct
import threading
import time
from typing import Callable, Optional

try:
    import rclpy
    from geometry_msgs.msg import Point, PoseStamped, Quaternion, Twist, Vector3
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from sensor_msgs.msg import PointCloud2, PointField
    from std_msgs.msg import Bool, Float64MultiArray, Header
    from std_srvs.srv import Empty as EmptySrv
    from std_srvs.srv import SetBool

    _ROS2_OK = True
except ImportError:
    _ROS2_OK = False

from skymeshx.ros.context import acquire_ros, release_ros
from skymeshx.exceptions import DependencyError, ROS2InitError, ROS2NotAvailableError


def _euler_to_quat(roll: float, pitch: float, yaw: float) -> tuple:
    """Roll/pitch/yaw (deg) → quaternion (x,y,z,w)."""
    r = math.radians(roll)
    p = math.radians(pitch)
    y = math.radians(yaw)
    cr, sr = math.cos(r / 2), math.sin(r / 2)
    cp, sp = math.cos(p / 2), math.sin(p / 2)
    cy, sy = math.cos(y / 2), math.sin(y / 2)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


class FrontierExplorationBridge:
    """
    Bridges SkyMeshX ↔ larics frontier explorer.

    - Converts MAVLink telemetry → ROS2 Odometry / PoseStamped
    - Receives next-frontier goals → sends drone.goto()
    - Optional: republishes external PointCloud2 from a depth camera topic
    """

    def __init__(
        self,
        drone,
        ns: str = "/exploration",
        publish_hz: float = 10.0,
        point_cloud_topic: Optional[str] = None,  # external topic to forward
        on_goal_reached: Optional[Callable] = None,
        on_volume_update: Optional[Callable] = None,
    ):
        if not _ROS2_OK:
            raise DependencyError(
                "rclpy",
                "install ROS2 Humble: https://docs.ros.org/en/humble/Installation.html",
            )
        self._drone = drone
        self._ns = ns
        self._hz = publish_hz
        self._pc_topic = point_cloud_topic
        self._on_goal_reached = on_goal_reached
        self._on_volume_update = on_volume_update
        self._node: Optional[Node] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._exploring = False
        self._done_event = threading.Event()
        self._explored_volume: dict = {}
        self._current_goal: Optional[tuple] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self):
        """Start the ROS2 node and bridge."""
        if self._running:
            return
        if not _ROS2_OK:
            raise ROS2NotAvailableError("ROS2 not available")
        if not acquire_ros():
            raise ROS2InitError("rclpy.init() failed")
        self._running = True
        self._thread = threading.Thread(
            target=self._spin, daemon=True, name="frontier-bridge"
        )
        self._thread.start()
        time.sleep(0.5)  # let node initialize

    def stop(self):
        if not self._running:
            return
        self._running = False
        self.exploration_stop()
        try:
            if self._node is not None:
                self._node.destroy_node()
        except Exception as e:
            print(f"[frontier-bridge] destroy_node error: {e}")
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        release_ros()

    # ── Exploration control ───────────────────────────────────────────────

    def exploration_start(self):
        """Call /exploration/toggle service to start the explorer."""
        if self._node:
            self._node.call_toggle(True)
            self._exploring = True
            self._done_event.clear()

    def exploration_stop(self):
        if self._node:
            self._node.call_toggle(False)
        self._exploring = False

    def save_octomap(self, filename: str = "map", file_path: str = "/tmp"):
        if self._node:
            self._node.call_save_octomap(filename, file_path)

    def wait_until_done(self, timeout: float = 3600.0) -> bool:
        """Block until explorer reports no more frontiers."""
        return self._done_event.wait(timeout=timeout)

    @property
    def explored_volume(self) -> dict:
        return dict(self._explored_volume)

    @property
    def exploring(self) -> bool:
        return self._exploring

    # ── Internal ──────────────────────────────────────────────────────────

    def _spin(self):
        # rclpy.init() handled by acquire_ros() in start().
        self._node = _FrontierNode(
            ns=self._ns,
            drone=self._drone,
            hz=self._hz,
            pc_topic=self._pc_topic,
            on_point_reached=self._on_point_reached,
            on_volume=self._on_volume,
        )
        try:
            while self._running and rclpy.ok():
                rclpy.spin_once(self._node, timeout_sec=0.1)
        except Exception as e:
            print(f"[frontier-bridge] ROS spin error: {e}")
        # Node teardown handled by stop().

    def _on_point_reached(self, reached: bool):
        if reached and self._exploring:
            if self._on_goal_reached:
                self._on_goal_reached()

    def _on_volume(self, occupied, free, total, unmapped):
        self._explored_volume = {
            "occupied": occupied,
            "free": free,
            "total": total,
            "unmapped": unmapped,
            "explored_pct": round((1 - unmapped / max(total, 1)) * 100, 1),
        }
        if self._on_volume_update:
            self._on_volume_update(self._explored_volume)
        # Exploration done when unmapped volume is very small
        if total > 0 and unmapped / total < 0.02:
            self._done_event.set()


if _ROS2_OK:

    class _FrontierNode(Node):
        def __init__(self, ns, drone, hz, pc_topic, on_point_reached, on_volume):
            super().__init__("skymeshx_frontier_bridge")
            self._drone = drone
            self._hz = hz
            self._on_point_reached = on_point_reached
            self._on_volume = on_volume

            # Reference GPS origin for local NED conversion.
            # Set once on the first valid GPS reading (non-zero lat/lon).
            self._ref_lat: Optional[float] = None
            self._ref_lon: Optional[float] = None

            # Publishers → Explorer
            self._pub_odom = self.create_publisher(Odometry, f"{ns}/odometry", 10)
            self._pub_carrot = self.create_publisher(
                PoseStamped, f"{ns}/carrot_pose", 10
            )

            # Subscribers ← Explorer
            self.create_subscription(
                Bool, f"{ns}/point_reached", self._cb_point_reached, 10
            )
            self.create_subscription(
                Float64MultiArray, f"{ns}/octomap_volume", self._cb_volume, 10
            )

            # Service clients
            self._svc_toggle = self.create_client(SetBool, f"{ns}/toggle")
            self._svc_save = self.create_client(EmptySrv, f"{ns}/save_octomap")

            # Optional: forward external point cloud topic
            if pc_topic:
                self.create_subscription(PointCloud2, pc_topic, self._cb_cloud, 10)
                self._pub_cloud = self.create_publisher(
                    PointCloud2, f"{ns}/cloud_in", 10
                )
            else:
                self._pub_cloud = None

            # Publish timer
            self.create_timer(1.0 / self._hz, self._publish_telemetry)

        # ── Coordinate helpers ────────────────────────────────────────────

        def _set_ref_if_needed(self, lat: float, lon: float) -> bool:
            """Latch reference origin on first valid GPS fix. Returns True once set."""
            if self._ref_lat is None and lat != 0.0 and lon != 0.0:
                self._ref_lat = lat
                self._ref_lon = lon
                self.get_logger().info(
                    f"[frontier-bridge] NED origin set: lat={lat:.6f} lon={lon:.6f}"
                )
            return self._ref_lat is not None

        def _gps_to_ned(self, lat: float, lon: float) -> tuple:
            """Convert GPS (degrees) to local NED metres relative to the reference origin.

            Returns (north_m, east_m). Caller must ensure _set_ref_if_needed() has
            returned True before calling this.
            """
            north = (lat - self._ref_lat) * 111_320.0
            east = (
                (lon - self._ref_lon)
                * 111_320.0
                * math.cos(math.radians(self._ref_lat))
            )
            return north, east

        # ── Telemetry publisher ───────────────────────────────────────────

        def _publish_telemetry(self):
            t = self._drone.telemetry
            now = self.get_clock().now().to_msg()

            # Wait until we have a valid GPS fix before publishing.
            if not self._set_ref_if_needed(t.lat, t.lon):
                return

            north, east = self._gps_to_ned(t.lat, t.lon)
            qx, qy, qz, qw = _euler_to_quat(t.roll, t.pitch, t.yaw)

            # Odometry — position in local NED metres, velocity in m/s NED
            odom = Odometry()
            odom.header.stamp = now
            odom.header.frame_id = "world"
            odom.child_frame_id = "base_link"
            odom.pose.pose.position.x = north
            odom.pose.pose.position.y = east
            odom.pose.pose.position.z = t.alt_rel
            odom.pose.pose.orientation.x = qx
            odom.pose.pose.orientation.y = qy
            odom.pose.pose.orientation.z = qz
            odom.pose.pose.orientation.w = qw
            odom.twist.twist.linear.x = t.vx
            odom.twist.twist.linear.y = t.vy
            odom.twist.twist.linear.z = t.vz
            self._pub_odom.publish(odom)

            # Carrot pose — current drone pose in local NED (used by the
            # carrot-following algorithm inside the explorer node).
            carrot = PoseStamped()
            carrot.header.stamp = now
            carrot.header.frame_id = "world"
            carrot.pose.position.x = north
            carrot.pose.position.y = east
            carrot.pose.position.z = t.alt_rel
            carrot.pose.orientation.x = qx
            carrot.pose.orientation.y = qy
            carrot.pose.orientation.z = qz
            carrot.pose.orientation.w = qw
            self._pub_carrot.publish(carrot)

        def _cb_point_reached(self, msg: Bool):
            self._on_point_reached(msg.data)

        def _cb_volume(self, msg: Float64MultiArray):
            if len(msg.data) >= 4:
                self._on_volume(*msg.data[:4])

        def _cb_cloud(self, msg: PointCloud2):
            if self._pub_cloud:
                self._pub_cloud.publish(msg)

        def call_toggle(self, enable: bool):
            req = SetBool.Request()
            req.data = enable
            if self._svc_toggle.wait_for_service(timeout_sec=2.0):
                self._svc_toggle.call_async(req)
            else:
                self.get_logger().warn("exploration/toggle service not available")

        def call_save_octomap(self, filename: str, file_path: str):
            req = EmptySrv.Request()
            if self._svc_save.wait_for_service(timeout_sec=2.0):
                self._svc_save.call_async(req)
            else:
                self.get_logger().warn("exploration/save_octomap service not available")
