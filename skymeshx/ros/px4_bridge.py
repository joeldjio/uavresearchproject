"""
PX4ROS2Bridge — proper PX4 ↔ ROS2 integration via uXRCE-DDS.

PX4 v1.14+ uses uXRCE-DDS (NOT FastRTPS, NOT MAVLink-over-ROS).
Topics live under /fmu/out/* (PX4 → ROS2) and /fmu/in/* (ROS2 → PX4).

Reference:
    https://docs.px4.io/main/en/ros2/user_guide.html
    https://docs.px4.io/main/en/middleware/uxrce_dds

Frame Convention
----------------
PX4 and ROS2 use different coordinate systems:

PX4 Native Frames:
- Position: NED (North-East-Down)
- Body: FRD (Forward-Right-Down)

ROS2 Standard Frames:
- Position: ENU (East-North-Up)
- Body: FLU (Forward-Left-Up)

Conversions (implemented in ned_to_enu(), enu_to_ned(), frd_to_flu()):
- NED→ENU: [x,y,z]_enu = [y, x, -z]_ned
- ENU→NED: [x,y,z]_ned = [y, x, -z]_enu
- FRD→FLU: [x,y,z]_flu = [x, -y, -z]_frd

This bridge automatically handles all frame conversions between PX4 and ROS2.

Prerequisites:
    1. PX4 v1.14+ firmware on FC
    2. Micro XRCE-DDS Agent running on companion computer:
         pip3 install --user uxrce_dds_agent    (Python version)
         # or C++ version: https://micro.ros.org/docs/overview/xrce_dds
    3. On FC (via MAVLink shell):
         uxrce_dds_client start -t udp -h <companion_ip> -p 8888
         # or for multi-vehicle:
         uxrce_dds_client start -t udp -h <ip> -p 8888 -n uav_1
    4. px4_msgs installed in ROS2 workspace:
         cd ~/ros2_ws/src && git clone https://github.com/PX4/px4_msgs
         cd ~/ros2_ws && colcon build --packages-select px4_msgs
         source install/setup.bash

Usage (two modes):

    Mode 1 — Read from PX4 via uXRCE-DDS (no MAVLink needed):
        bridge = PX4ROS2Bridge(namespace="uav_1")
        bridge.start()
        # Access telemetry: bridge.telemetry

    Mode 2 — Bridge PX4 uXRCE-DDS ↔ SkyMeshX Drone object:
        bridge = PX4ROS2Bridge(drone=drone, namespace="uav_1")
        bridge.start()
        bridge.arm()
        bridge.takeoff(altitude=10.0)
"""
import math
import threading
import time
from typing import Callable, Optional, List, Dict
from enum import Enum

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
    _ROS2_OK = True
except ImportError:
    _ROS2_OK = False


# ── Connection Status ──────────────────────────────────────────────────────

class ConnectionStatus(Enum):
    """ROS2 bridge connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"

from skymeshx.ros.context import acquire_ros, release_ros
from skymeshx.ros.px4_mission import PX4MissionUploader
from skymeshx.exceptions import DependencyError, ROS2NotAvailableError, TopicTimeoutError

try:
    from px4_msgs.msg import (
        VehicleOdometry,
        VehicleStatus,
        BatteryStatus,
        SensorGps,
        VehicleAttitude,
        VehicleLocalPosition,
        VehicleGlobalPosition,
        VehicleCommand,
        OffboardControlMode,
        TrajectorySetpoint,
    )
    _PX4_MSGS_OK = True
except ImportError:
    _PX4_MSGS_OK = False


# ── Frame conversion utilities ─────────────────────────────────────────────────

def ned_to_enu(north: float, east: float, down: float) -> tuple:
    """
    Convert NED (North-East-Down) to ENU (East-North-Up).
    
    Args:
        north: North coordinate in meters (NED frame)
        east: East coordinate in meters (NED frame)
        down: Down coordinate in meters (NED frame, positive = below origin)
    
    Returns:
        Tuple of (east, north, up) in ENU frame
    
    Example:
        >>> ned_to_enu(10.0, 20.0, 30.0)  # 10m North, 20m East, 30m Down
        (20.0, 10.0, -30.0)  # 20m East, 10m North, 30m Up
    """
    return (east, north, -down)

def enu_to_ned(east: float, north: float, up: float) -> tuple:
    """
    Convert ENU (East-North-Up) to NED (North-East-Down).
    
    Args:
        east: East coordinate in meters (ENU frame)
        north: North coordinate in meters (ENU frame)
        up: Up coordinate in meters (ENU frame, positive = above origin)
    
    Returns:
        Tuple of (north, east, down) in NED frame
    
    Example:
        >>> enu_to_ned(20.0, 10.0, -30.0)  # 20m East, 10m North, 30m Up
        (10.0, 20.0, 30.0)  # 10m North, 20m East, 30m Down
    """
    return (north, east, -up)

def frd_to_flu(forward: float, right: float, down: float) -> tuple:
    """
    Convert FRD (Forward-Right-Down) to FLU (Forward-Left-Up) body frame.
    
    This is a pi rotation around the X-axis (forward axis).
    
    Args:
        forward: Forward coordinate in meters (FRD frame)
        right: Right coordinate in meters (FRD frame)
        down: Down coordinate in meters (FRD frame)
    
    Returns:
        Tuple of (forward, left, up) in FLU frame
    
    Example:
        >>> frd_to_flu(1.0, 2.0, 3.0)  # 1m Forward, 2m Right, 3m Down
        (1.0, -2.0, -3.0)  # 1m Forward, 2m Left, 3m Up
    """
    return (forward, -right, -down)

def quat_ned_to_enu(w: float, x: float, y: float, z: float) -> tuple:
    """Rotate quaternion from NED/FRD to ENU/FLU frame."""
    # Apply -pi/2 around Z then pi around X
    # Simplified: swap and negate specific components
    return (w, y, x, -z)


# ── PX4 vehicle command IDs ────────────────────────────────────────────────────

class VehicleCommandId:
    ARM_DISARM      = 400
    TAKEOFF         = 22
    LAND            = 21
    RTL             = 20
    SET_MODE        = 176


class PX4ROS2Bridge:
    """
    Bridges SkyMeshX ↔ PX4 via uXRCE-DDS (the correct PX4 v1.14 way).

    Can operate in two modes:
    1. Standalone: reads PX4 uORB topics, fills internal telemetry dict
    2. Paired: syncs PX4 telemetry to a SkyMeshX Drone object + sends commands

    Parameters
    ----------
    drone       : Optional Drone instance to sync telemetry to
    namespace   : PX4 uXRCE-DDS namespace (e.g. "uav_1" → /uav_1/fmu/*)
                  Leave empty for single-vehicle default (/fmu/*)
    publish_hz  : Control setpoint publish rate (must be >2Hz for offboard mode)
    """

    def __init__(
        self,
        drone=None,
        namespace:   str   = "",
        publish_hz:  float = 10.0,
        auto_reconnect: bool = True,
        max_reconnect_delay: float = 30.0,
    ):
        if not _ROS2_OK:
            raise DependencyError("rclpy", "pip install rclpy  # or install ROS2 Humble+")
        if not _PX4_MSGS_OK:
            raise DependencyError(
                "px4_msgs",
                "cd ~/ros2_ws/src && git clone https://github.com/PX4/px4_msgs"
                " && cd ~/ros2_ws && colcon build --packages-select px4_msgs"
                " && source install/setup.bash",
            )
        self._drone     = drone
        self._ns_prefix = f"/{namespace}" if namespace else ""
        self._hz        = publish_hz
        self._node: Optional[Node] = None
        self._thread: Optional[threading.Thread] = None
        self._running   = False
        
        # Reconnect logic
        self._auto_reconnect = auto_reconnect
        self._max_reconnect_delay = max_reconnect_delay
        self._max_reconnect_attempts = 5  # Maximum number of reconnect attempts
        self._reconnect_delay = 1.0  # Start with 1 second
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._last_message_time = 0.0
        self._connection_timeout = 5.0  # Consider disconnected if no messages for 5s
        self._reconnect_attempts = 0

        # Internal telemetry (filled from uXRCE-DDS topics)
        self.telemetry: dict = {
            "armed":        False,
            "flight_mode":  0,
            "lat":          0.0,
            "lon":          0.0,
            "alt":          0.0,
            "alt_rel":      0.0,
            "vx":           0.0,
            "vy":           0.0,
            "vz":           0.0,
            "roll":         0.0,
            "pitch":        0.0,
            "yaw":          0.0,
            "battery_pct":  -1.0,
            "battery_v":    0.0,
            "gps_fix":      0,
            "satellites":   0,
            # Frame conversion debug (NED = PX4 native, ENU = ROS2 standard)
            "ned_north":    0.0,
            "ned_east":     0.0,
            "ned_down":     0.0,
            "enu_east":     0.0,
            "enu_north":    0.0,
            "enu_up":       0.0,
        }
        self._offboard_active  = False
        self._setpoint: Optional[dict] = None
        self._callbacks: dict = {}
        self._mission_uploader: Optional[PX4MissionUploader] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        if not acquire_ros():
            self._set_status(ConnectionStatus.FAILED)
            print("[px4-bridge] rclpy not available \u2014 cannot start")
            return
        self._reconnect_attempts = 0
        self._reconnect_delay = 1.0
        self._running = True
        self._thread  = threading.Thread(
            target=self._spin, daemon=True, name="px4-ros2-bridge"
        )
        self._thread.start()
        time.sleep(0.5)
        print(f"[px4-bridge] Started. Namespace: '{self._ns_prefix or '/'}'")
        print(f"[px4-bridge] Listening on {self._ns_prefix}/fmu/out/*")

    def stop(self):
        """Stop the bridge and cleanup resources."""
        if not self._running:
            return
        self._running = False
        self._set_status(ConnectionStatus.DISCONNECTED)
        # Wake spin() so the thread can exit cleanly.
        try:
            if self._node is not None:
                self._node.destroy_node()
        except Exception as e:
            print(f"[px4-bridge] destroy_node error: {e}")
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        release_ros()
    
    @property
    def connection_status(self) -> ConnectionStatus:
        """
        Current connection status.
        
        Returns:
            ConnectionStatus enum value (DISCONNECTED, CONNECTING, CONNECTED,
            RECONNECTING, or FAILED)
        
        Example:
            if bridge.connection_status == ConnectionStatus.CONNECTED:
                bridge.arm()
        """
        return self._connection_status
    
    def get_connection_status(self) -> ConnectionStatus:
        """Get current connection status (deprecated: use connection_status property)."""
        return self._connection_status
    
    def is_connected(self) -> bool:
        """Check if bridge is connected and receiving data."""
        return self._connection_status == ConnectionStatus.CONNECTED
    
    def get_reconnect_info(self) -> dict:
        """
        Get reconnection information.
        
        Returns:
            Dict with reconnect status:
            - status: Current ConnectionStatus
            - attempts: Number of reconnect attempts
            - next_delay: Next reconnect delay in seconds
            - last_message_age: Seconds since last message
        """
        return {
            "status": self._connection_status.value,
            "attempts": self._reconnect_attempts,
            "next_delay": self._reconnect_delay,
            "last_message_age": time.time() - self._last_message_time if self._last_message_time > 0 else -1,
        }

    # ── Vehicle commands (PX4 VehicleCommand) ─────────────────────────────

    def arm(self):
        self._send_vehicle_command(VehicleCommandId.ARM_DISARM, param1=1.0)

    def disarm(self):
        self._send_vehicle_command(VehicleCommandId.ARM_DISARM, param1=0.0)

    def takeoff(self, altitude: float = 10.0):
        self._send_vehicle_command(VehicleCommandId.TAKEOFF, param7=altitude)

    def land(self):
        self._send_vehicle_command(VehicleCommandId.LAND)

    def rtl(self):
        self._send_vehicle_command(VehicleCommandId.RTL)

    def set_offboard_mode(self):
        """Switch to OFFBOARD mode (required before sending setpoints)."""
        self._send_vehicle_command(
            VehicleCommandId.SET_MODE,
            param1=1.0,    # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
            param2=6.0,    # PX4 OFFBOARD mode
        )

    # ── Offboard setpoints ─────────────────────────────────────────────────

    def set_position_setpoint_ned(
        self, north: float, east: float, down: float, yaw: float = 0.0
    ):
        """
        Set position setpoint in NED frame (PX4 native).
        Call this at >2Hz while in OFFBOARD mode or PX4 will disengage.
        """
        self._offboard_active = True
        self._setpoint = {
            "type": "position",
            "x": north, "y": east, "z": down, "yaw": yaw,
        }

    def set_position_setpoint_enu(
        self, east: float, north: float, up: float, yaw: float = 0.0
    ):
        """Set position setpoint in ENU frame (auto-converts to NED)."""
        n, e, d = enu_to_ned(east, north, up)
        self.set_position_setpoint_ned(n, e, d, yaw)

    def set_velocity_setpoint_ned(
        self, vn: float, ve: float, vd: float, yaw_rate: float = 0.0
    ):
        """Set velocity setpoint in NED frame."""
        self._offboard_active = True
        self._setpoint = {
            "type": "velocity",
            "vx": vn, "vy": ve, "vz": vd, "yawspeed": yaw_rate,
        }

    def stop_offboard(self):
        self._offboard_active = False
        self._setpoint = None

    # ── Mission Management ────────────────────────────────────────────────

    def upload_mission(self, waypoints: List[Dict], timeout: float = 10.0) -> bool:
        """
        Upload waypoint mission to PX4.
        
        Args:
            waypoints: List of waypoint dicts with keys: lat, lon, alt
                      Example: [{"lat": 47.397, "lon": 8.545, "alt": 10.0}, ...]
            timeout: Timeout in seconds for ACK
        
        Returns:
            True if upload successful
        """
        if not self._mission_uploader:
            print("[px4-bridge] Mission uploader not available")
            return False
        return self._mission_uploader.upload(waypoints, timeout=timeout)

    def clear_mission(self) -> bool:
        """
        Clear mission on PX4.
        
        Returns:
            True if successful
        """
        if not self._mission_uploader:
            print("[px4-bridge] Mission uploader not available")
            return False
        return self._mission_uploader.clear()

    def start_mission(self):
        """Start mission execution (switch to AUTO.MISSION mode)."""
        # PX4 mode 4 = AUTO.MISSION
        self._send_vehicle_command(
            VehicleCommandId.SET_MODE,
            param1=1.0,  # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
            param2=4.0,  # PX4 AUTO.MISSION mode
        )

    def pause_mission(self):
        """Pause mission execution (switch to AUTO.LOITER mode)."""
        # PX4 mode 3 = AUTO.LOITER
        self._send_vehicle_command(
            VehicleCommandId.SET_MODE,
            param1=1.0,  # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
            param2=3.0,  # PX4 AUTO.LOITER mode
        )
    
    def get_mission_status(self) -> dict:
        """
        Get current mission status.
        
        Returns:
            Dict with mission status information:
            - active: Mission is active
            - current_seq: Current waypoint index
            - total_count: Total waypoint count
            - reached: Current waypoint reached
            - finished: Mission finished
            - failure: Mission failed
        """
        if not self._mission_uploader:
            return {
                "active": False,
                "current_seq": 0,
                "total_count": 0,
                "reached": False,
                "finished": False,
                "failure": False,
            }
        return self._mission_uploader.get_status()
    
    def get_mission_waypoints(self) -> list:
        """
        Get uploaded mission waypoints.
        
        Returns:
            List of waypoint dicts
        """
        if not self._mission_uploader:
            return []
        return self._mission_uploader.get_waypoints()
    
    def on_mission_status(self, callback: Callable):
        """
        Register callback for mission status changes.
        
        Args:
            callback: Function that receives mission status dict
        """
        if self._mission_uploader:
            self._mission_uploader.on_status_change(callback)

    # ── Events ────────────────────────────────────────────────────────────

    def on(self, event: str, cb: Callable):
        """
        Register callback.
        
        Events:
        - 'telemetry': Telemetry data updated
        - 'armed': Armed state changed
        - 'mode': Flight mode changed
        - 'connection_status': Connection status changed (receives ConnectionStatus)
        """
        self._callbacks.setdefault(event, []).append(cb)

    # ── Internal ──────────────────────────────────────────────────────────

    def _spin(self):
        """Main spin loop with reconnect logic."""
        while self._running:
            try:
                self._set_status(ConnectionStatus.CONNECTING)
                
                # Create node
                self._node = _PX4Node(
                    ns_prefix       = self._ns_prefix,
                    hz              = self._hz,
                    on_telemetry    = self._on_telemetry,
                    get_setpoint    = lambda: self._setpoint,
                    offboard_active = lambda: self._offboard_active,
                )
                
                # Initialize mission uploader after node is created
                try:
                    self._mission_uploader = PX4MissionUploader(
                        self._node,
                        namespace=self._ns_prefix.lstrip("/") if self._ns_prefix else ""
                    )
                except Exception as e:
                    print(f"[px4-bridge] Mission uploader init failed: {e}")
                    self._mission_uploader = None
                
                self._set_status(ConnectionStatus.CONNECTED)
                self._reconnect_attempts = 0
                self._reconnect_delay = 1.0
                print(f"[px4-bridge] Connected successfully")
                
                # Main spin loop with health monitoring
                while self._running and rclpy.ok():
                    rclpy.spin_once(self._node, timeout_sec=0.1)
                    
                    # Check connection health
                    if self._last_message_time > 0:
                        age = time.time() - self._last_message_time
                        if age > self._connection_timeout:
                            print(f"[px4-bridge] No messages for {age:.1f}s - connection lost")
                            raise TopicTimeoutError(f"/{self._ns_prefix}", self._connection_timeout)
                
                # Clean exit
                break
                
            except Exception as e:
                print(f"[px4-bridge] Connection error: {e}")
                
                # Cleanup node
                try:
                    if self._node is not None:
                        self._node.destroy_node()
                        self._node = None
                except Exception as cleanup_err:
                    print(f"[px4-bridge] Cleanup error: {cleanup_err}")
                
                # Handle reconnect
                if not self._running:
                    break
                
                if not self._auto_reconnect:
                    print("[px4-bridge] Auto-reconnect disabled - stopping")
                    self._set_status(ConnectionStatus.FAILED)
                    break
                
                self._reconnect_attempts += 1
                
                # Check if max attempts reached
                if self._reconnect_attempts > self._max_reconnect_attempts:
                    print(f"[px4-bridge] Max reconnect attempts ({self._max_reconnect_attempts}) reached - giving up")
                    self._set_status(ConnectionStatus.FAILED)
                    break
                
                self._set_status(ConnectionStatus.RECONNECTING)
                
                print(f"[px4-bridge] Reconnecting in {self._reconnect_delay:.1f}s (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})...")
                
                # Wait with early exit check
                wait_start = time.time()
                while self._running and (time.time() - wait_start) < self._reconnect_delay:
                    time.sleep(0.1)
                
                if not self._running:
                    break
                
                # Exponential backoff
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
        
        # Final cleanup
        self._set_status(ConnectionStatus.DISCONNECTED)

    def _send_vehicle_command(self, cmd: int, **params):
        if self._node:
            self._node.send_vehicle_command(cmd, **params)
        else:
            print(f"[px4-bridge] Node not ready — command {cmd} dropped")

    def _on_telemetry(self, data: dict):
        """Handle telemetry update and track connection health."""
        self._last_message_time = time.time()
        
        self.telemetry.update(data)
        # Sync to SkyMeshX Drone if paired
        if self._drone:
            t = self._drone._conn.telemetry
            t.lat         = data.get("lat",         t.lat)
            t.lon         = data.get("lon",         t.lon)
            t.alt         = data.get("alt",         t.alt)
            t.alt_rel     = data.get("alt_rel",     t.alt_rel)
            t.roll        = data.get("roll",        t.roll)
            t.pitch       = data.get("pitch",       t.pitch)
            t.yaw         = data.get("yaw",         t.yaw)
            t.battery_pct = data.get("battery_pct", t.battery_pct)
            t.battery_v   = data.get("battery_v",   t.battery_v)
            t.armed       = data.get("armed",       t.armed)
        # Fire callbacks
        for cb in self._callbacks.get("telemetry", []):
            try:
                cb(data)
            except Exception as e:
                print(f"[px4-bridge] callback error: {e}")
    
    def _set_status(self, status: ConnectionStatus):
        """Update connection status and fire callbacks."""
        if self._connection_status != status:
            self._connection_status = status
            print(f"[px4-bridge] Status: {status.value}")
            
            # Fire status callbacks
            for cb in self._callbacks.get("connection_status", []):
                try:
                    cb(status)
                except Exception as e:
                    print(f"[px4-bridge] status callback error: {e}")


if _ROS2_OK and _PX4_MSGS_OK:
    class _PX4Node(Node):
        def __init__(self, ns_prefix, hz, on_telemetry, get_setpoint, offboard_active):
            super().__init__("skymeshx_px4_bridge")
            self._ns          = ns_prefix
            self._on_tel      = on_telemetry
            self._get_sp      = get_setpoint
            self._is_offboard = offboard_active

            # PX4 requires sensor_data QoS for subscriptions
            qos = QoSProfile(
                reliability=QoSReliabilityPolicy.BEST_EFFORT,
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=5,
            )

            # ── Subscribers (PX4 → ROS2) ──────────────────────────────────
            self.create_subscription(
                VehicleGlobalPosition,
                f"{ns_prefix}/fmu/out/vehicle_global_position",
                self._cb_global_pos, qos,
            )
            self.create_subscription(
                VehicleLocalPosition,
                f"{ns_prefix}/fmu/out/vehicle_local_position",
                self._cb_local_pos, qos,
            )
            self.create_subscription(
                VehicleAttitude,
                f"{ns_prefix}/fmu/out/vehicle_attitude",
                self._cb_attitude, qos,
            )
            self.create_subscription(
                VehicleStatus,
                f"{ns_prefix}/fmu/out/vehicle_status",
                self._cb_status, qos,
            )
            self.create_subscription(
                BatteryStatus,
                f"{ns_prefix}/fmu/out/battery_status",
                self._cb_battery, qos,
            )
            self.create_subscription(
                SensorGps,
                f"{ns_prefix}/fmu/out/vehicle_gps_position",
                self._cb_gps, qos,
            )

            # ── Publishers (ROS2 → PX4) ───────────────────────────────────
            self._pub_cmd = self.create_publisher(
                VehicleCommand,
                f"{ns_prefix}/fmu/in/vehicle_command", 10,
            )
            self._pub_offboard = self.create_publisher(
                OffboardControlMode,
                f"{ns_prefix}/fmu/in/offboard_control_mode", 10,
            )
            self._pub_traj = self.create_publisher(
                TrajectorySetpoint,
                f"{ns_prefix}/fmu/in/trajectory_setpoint", 10,
            )

            # Publish setpoints at configured rate
            self.create_timer(1.0 / hz, self._publish_setpoints)

            self._arm_state   = False
            self._flight_mode = 0
            # Captured on first VehicleGlobalPosition message; used to derive
            # alt_rel for displays. VehicleLocalPosition already gives a
            # proper relative-to-launch altitude (handled in _cb_local_pos).
            self._home_alt: float | None = None

        # ── Subscribers ───────────────────────────────────────────────────

        def _cb_global_pos(self, msg: VehicleGlobalPosition):
            # Capture home altitude on the first valid sample so subsequent
            # alt_rel values are meaningful (PX4 doesn't ship a home msg here).
            if self._home_alt is None and msg.alt is not None:
                self._home_alt = float(msg.alt)
            alt_rel = (
                float(msg.alt) - self._home_alt
                if self._home_alt is not None
                else 0.0
            )
            self._on_tel({
                "lat":      msg.lat,
                "lon":      msg.lon,
                "alt":      msg.alt,
                "alt_rel":  alt_rel,
                "home_alt": self._home_alt or 0.0,
            })

        def _cb_local_pos(self, msg: VehicleLocalPosition):
            # PX4 local pos is NED — convert to ENU for display
            # Store both NED (PX4 native) and ENU (ROS2 standard) for frame visualization
            ned_n, ned_e, ned_d = msg.x, msg.y, msg.z
            enu_e, enu_n, enu_u = ned_to_enu(ned_n, ned_e, ned_d)
            ve, vn, vu = ned_to_enu(msg.vx, msg.vy, msg.vz)
            self._on_tel({
                "alt_rel": enu_u,
                "vx": vn, "vy": ve, "vz": vu,
                # Frame conversion debug
                "ned_north": ned_n,
                "ned_east": ned_e,
                "ned_down": ned_d,
                "enu_east": enu_e,
                "enu_north": enu_n,
                "enu_up": enu_u,
            })

        def _cb_attitude(self, msg: VehicleAttitude):
            # PX4 quaternion is FRD/NED, convert to ENU roll/pitch/yaw
            q = msg.q
            # q = [w, x, y, z] in PX4
            w, x, y, z = q[0], q[1], q[2], q[3]
            # Convert FRD→FLU: rotate pi around X
            x_flu, y_flu, z_flu = frd_to_flu(x, y, z)
            # Euler from quaternion (FLU)
            roll  = math.degrees(math.atan2(2*(w*x_flu + y_flu*z_flu), 1 - 2*(x_flu**2 + y_flu**2)))
            pitch = math.degrees(math.asin(max(-1, min(1, 2*(w*y_flu - z_flu*x_flu)))))
            yaw   = math.degrees(math.atan2(2*(w*z_flu + x_flu*y_flu), 1 - 2*(y_flu**2 + z_flu**2))) % 360
            self._on_tel({"roll": roll, "pitch": pitch, "yaw": yaw})

        def _cb_status(self, msg: VehicleStatus):
            armed = msg.arming_state == 2   # ARMING_STATE_ARMED
            self._arm_state   = armed
            self._flight_mode = msg.nav_state
            self._on_tel({"armed": armed, "flight_mode": msg.nav_state})

        def _cb_battery(self, msg: BatteryStatus):
            self._on_tel({
                "battery_pct": msg.remaining * 100.0,
                "battery_v":   msg.voltage_v,
            })

        def _cb_gps(self, msg: SensorGps):
            self._on_tel({
                "gps_fix":    msg.fix_type,
                "satellites": msg.satellites_used,
            })

        # ── Publishers ────────────────────────────────────────────────────

        def _publish_setpoints(self):
            sp = self._get_sp()
            if not self._is_offboard() or sp is None:
                return
            now = self.get_clock().now().to_msg()

            # Offboard control mode (must be sent to keep PX4 in offboard)
            ocm = OffboardControlMode()
            ocm.timestamp  = self.get_clock().now().nanoseconds // 1000
            ocm.position   = sp["type"] == "position"
            ocm.velocity   = sp["type"] == "velocity"
            ocm.acceleration = False
            ocm.attitude   = False
            ocm.body_rate  = False
            self._pub_offboard.publish(ocm)

            # Trajectory setpoint (NED frame — PX4 native)
            ts = TrajectorySetpoint()
            ts.timestamp = ocm.timestamp
            if sp["type"] == "position":
                ts.position    = [sp["x"], sp["y"], sp["z"]]
                ts.yaw         = sp.get("yaw", float("nan"))
                ts.velocity    = [float("nan")] * 3
                ts.acceleration = [float("nan")] * 3
            elif sp["type"] == "velocity":
                ts.velocity    = [sp["vx"], sp["vy"], sp["vz"]]
                ts.yawspeed    = sp.get("yawspeed", float("nan"))
                ts.position    = [float("nan")] * 3
            self._pub_traj.publish(ts)

        def send_vehicle_command(self, command: int, **params):
            cmd = VehicleCommand()
            cmd.timestamp         = self.get_clock().now().nanoseconds // 1000
            cmd.command           = command
            cmd.param1            = float(params.get("param1", 0.0))
            cmd.param2            = float(params.get("param2", 0.0))
            cmd.param3            = float(params.get("param3", 0.0))
            cmd.param4            = float(params.get("param4", 0.0))
            cmd.param5            = float(params.get("param5", 0.0))
            cmd.param6            = float(params.get("param6", 0.0))
            cmd.param7            = float(params.get("param7", 0.0))
            cmd.target_system     = 1
            cmd.target_component  = 1
            cmd.source_system     = 255
            cmd.source_component  = 0
            cmd.from_external     = True
            self._pub_cmd.publish(cmd)
