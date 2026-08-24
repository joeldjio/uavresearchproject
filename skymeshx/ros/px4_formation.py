"""
PX4 Multi-Vehicle Formation Controller via uXRCE-DDS.

Coordinates multiple PX4 drones in formation using Offboard mode and
TrajectorySetpoint messages. Uses canonical formation geometry from
skymeshx.sdk.formations.

Key Features:
- Leader-follower formation control
- Automatic NED↔ENU frame conversion
- Offboard mode management per vehicle
- Real-time position updates at 20Hz
- Thread-safe operation

Frame Convention:
- Input: NED (North-East-Down) with positive z_up (altitude above ground)
- PX4: NED (North-East-Down) with negative z_down
- Conversion handled automatically

Usage:
    controller = PX4FormationController(
        leader_ns="uav_1",
        follower_namespaces=["uav_2", "uav_3"],
        shape="v",
        spacing=5.0
    )
    controller.start()
    controller.set_leader_position(north=10, east=5, altitude=15)
    # Followers automatically maintain formation
    controller.stop()
"""
from __future__ import annotations

import math
import threading
import time
from typing import Dict, List, Optional, Tuple

from skymeshx.sdk.formations import formation_offsets, SHAPES
from skymeshx.exceptions import DependencyError, ROS2NotAvailableError

# Optional ROS2 imports
_ROS2_OK = False
_PX4_MSGS_OK = False
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
    _ROS2_OK = True
    try:
        from px4_msgs.msg import (
            OffboardControlMode,
            TrajectorySetpoint,
            VehicleCommand,
            VehicleStatus,
            VehicleLocalPosition
        )
        _PX4_MSGS_OK = True
    except ImportError:
        pass
except ImportError:
    pass


def ned_to_enu(north: float, east: float, down: float) -> Tuple[float, float, float]:
    """Convert NED (North-East-Down) to ENU (East-North-Up)."""
    return (east, north, -down)


def enu_to_ned(east: float, north: float, up: float) -> Tuple[float, float, float]:
    """Convert ENU (East-North-Up) to NED (North-East-Down)."""
    return (north, east, -up)


class PX4FormationController:
    """
    Multi-vehicle formation controller for PX4 via uXRCE-DDS.
    
    Manages a leader and multiple followers in formation. Leader position
    is set manually, followers maintain formation offsets automatically.
    """
    
    def __init__(
        self,
        leader_ns: str,
        follower_namespaces: List[str],
        shape: str = "v",
        spacing: float = 5.0,
        update_rate_hz: float = 20.0
    ):
        """
        Initialize formation controller.
        
        Args:
            leader_ns: Leader vehicle namespace (e.g., "uav_1")
            follower_namespaces: List of follower namespaces (e.g., ["uav_2", "uav_3"])
            shape: Formation shape from formations.SHAPES
            spacing: Distance between vehicles in meters
            update_rate_hz: Position update rate (default 20Hz)
        """
        if not _ROS2_OK:
            raise ROS2NotAvailableError("rclpy not available — install ROS2 Humble+")
        if not _PX4_MSGS_OK:
            raise DependencyError("px4_msgs", "colcon build --packages-select px4_msgs")
        
        self.leader_ns = leader_ns
        self.follower_namespaces = follower_namespaces
        self.shape = shape
        self.spacing = spacing
        self.update_rate_hz = update_rate_hz
        
        # Formation offsets (NED, relative to leader)
        self.offsets = formation_offsets(shape, len(follower_namespaces), spacing)
        
        # Leader position (NED with positive z_up)
        self._leader_pos = {"north": 0.0, "east": 0.0, "altitude": 0.0}
        self._leader_yaw = 0.0  # radians
        self._lock = threading.Lock()
        
        # ROS2 nodes (one per vehicle)
        self._nodes: Dict[str, Node] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Publishers per vehicle
        self._offboard_pubs: Dict[str, any] = {}
        self._traj_pubs: Dict[str, any] = {}
        self._cmd_pubs: Dict[str, any] = {}
        
        # Subscribers per vehicle (for status monitoring)
        self._status_subs: Dict[str, any] = {}
        self._vehicle_status: Dict[str, int] = {}  # namespace -> arming_state
        
        # Offboard mode counters (need 10+ setpoints before arming)
        self._offboard_counters: Dict[str, int] = {}
    
    def start(self) -> bool:
        """Start formation controller. Returns True if successful."""
        if self._running:
            return True
        
        if not rclpy.ok():
            rclpy.init()
        
        # Create nodes for all vehicles
        all_namespaces = [self.leader_ns] + self.follower_namespaces
        for ns in all_namespaces:
            node = Node(f"formation_ctrl_{ns}")
            self._nodes[ns] = node
            self._offboard_counters[ns] = 0
            self._vehicle_status[ns] = 0  # Unknown
            
            # QoS profile for PX4 (best effort, keep last)
            qos = QoSProfile(
                reliability=QoSReliabilityPolicy.BEST_EFFORT,
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=1
            )
            
            # Publishers
            self._offboard_pubs[ns] = node.create_publisher(
                OffboardControlMode,
                f"/{ns}/fmu/in/offboard_control_mode",
                qos
            )
            self._traj_pubs[ns] = node.create_publisher(
                TrajectorySetpoint,
                f"/{ns}/fmu/in/trajectory_setpoint",
                qos
            )
            self._cmd_pubs[ns] = node.create_publisher(
                VehicleCommand,
                f"/{ns}/fmu/in/vehicle_command",
                qos
            )
            
            # Subscriber for vehicle status
            self._status_subs[ns] = node.create_subscription(
                VehicleStatus,
                f"/{ns}/fmu/out/vehicle_status",
                lambda msg, ns=ns: self._on_vehicle_status(ns, msg),
                qos
            )
        
        # Start update thread
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        
        return True
    
    def stop(self):
        """Stop formation controller and cleanup."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        
        # Destroy nodes
        for node in self._nodes.values():
            node.destroy_node()
        self._nodes.clear()
    
    def set_leader_position(
        self,
        north: float,
        east: float,
        altitude: float,
        yaw: float = 0.0
    ):
        """
        Set leader position. Followers will maintain formation offsets.
        
        Args:
            north: North position in meters (NED)
            east: East position in meters (NED)
            altitude: Altitude above ground in meters (positive up)
            yaw: Heading in radians (0 = North, π/2 = East)
        """
        with self._lock:
            self._leader_pos = {
                "north": float(north),
                "east": float(east),
                "altitude": float(altitude)
            }
            self._leader_yaw = float(yaw)
    
    def get_leader_position(self) -> Dict[str, float]:
        """Get current leader position (NED with positive altitude)."""
        with self._lock:
            return self._leader_pos.copy()
    
    def get_follower_positions(self) -> Dict[str, Dict[str, float]]:
        """Get current follower positions (NED with positive altitude)."""
        with self._lock:
            leader = self._leader_pos
            positions = {}
            
            for i, ns in enumerate(self.follower_namespaces):
                if i < len(self.offsets):
                    n_off, e_off = self.offsets[i]
                    positions[ns] = {
                        "north": leader["north"] + n_off,
                        "east": leader["east"] + e_off,
                        "altitude": leader["altitude"]
                    }
            
            return positions
    
    def arm_all(self):
        """Arm all vehicles (leader + followers)."""
        all_namespaces = [self.leader_ns] + self.follower_namespaces
        for ns in all_namespaces:
            self._send_vehicle_command(ns, VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0)
    
    def disarm_all(self):
        """Disarm all vehicles."""
        all_namespaces = [self.leader_ns] + self.follower_namespaces
        for ns in all_namespaces:
            self._send_vehicle_command(ns, VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 0.0)
    
    def enable_offboard_all(self):
        """Enable offboard mode for all vehicles."""
        all_namespaces = [self.leader_ns] + self.follower_namespaces
        for ns in all_namespaces:
            self._send_vehicle_command(ns, VehicleCommand.VEHICLE_CMD_DO_SET_MODE, 1.0, 6.0)
    
    def _update_loop(self):
        """Main update loop - runs at update_rate_hz."""
        rate = 1.0 / self.update_rate_hz
        
        while self._running:
            start = time.time()
            
            # Spin all nodes
            for node in self._nodes.values():
                rclpy.spin_once(node, timeout_sec=0.0)
            
            # Publish offboard control mode for all vehicles
            all_namespaces = [self.leader_ns] + self.follower_namespaces
            for ns in all_namespaces:
                self._publish_offboard_control_mode(ns)
                self._offboard_counters[ns] += 1
            
            # Publish trajectory setpoints
            with self._lock:
                leader = self._leader_pos
                yaw = self._leader_yaw
            
            # Leader setpoint
            self._publish_trajectory_setpoint(
                self.leader_ns,
                leader["north"],
                leader["east"],
                leader["altitude"],
                yaw
            )
            
            # Follower setpoints (with formation offsets)
            for i, ns in enumerate(self.follower_namespaces):
                if i < len(self.offsets):
                    n_off, e_off = self.offsets[i]
                    self._publish_trajectory_setpoint(
                        ns,
                        leader["north"] + n_off,
                        leader["east"] + e_off,
                        leader["altitude"],
                        yaw
                    )
            
            # Sleep to maintain rate
            elapsed = time.time() - start
            sleep_time = max(0.0, rate - elapsed)
            time.sleep(sleep_time)
    
    def _publish_offboard_control_mode(self, namespace: str):
        """Publish offboard control mode message."""
        if namespace not in self._offboard_pubs:
            return
        
        msg = OffboardControlMode()
        msg.timestamp = int(time.time() * 1e6)
        msg.position = True
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        
        self._offboard_pubs[namespace].publish(msg)
    
    def _publish_trajectory_setpoint(
        self,
        namespace: str,
        north: float,
        east: float,
        altitude: float,
        yaw: float
    ):
        """
        Publish trajectory setpoint in NED frame.
        
        Args:
            namespace: Vehicle namespace
            north: North position (meters)
            east: East position (meters)
            altitude: Altitude above ground (meters, positive up)
            yaw: Heading (radians, 0=North)
        """
        if namespace not in self._traj_pubs:
            return
        
        msg = TrajectorySetpoint()
        msg.timestamp = int(time.time() * 1e6)
        
        # Convert to PX4 NED (with negative z_down)
        msg.position[0] = float(north)
        msg.position[1] = float(east)
        msg.position[2] = float(-altitude)  # PX4 uses negative down
        
        msg.yaw = float(yaw)
        
        # NaN for unused fields
        msg.velocity[0] = float('nan')
        msg.velocity[1] = float('nan')
        msg.velocity[2] = float('nan')
        msg.acceleration[0] = float('nan')
        msg.acceleration[1] = float('nan')
        msg.acceleration[2] = float('nan')
        msg.jerk[0] = float('nan')
        msg.jerk[1] = float('nan')
        msg.jerk[2] = float('nan')
        msg.yawspeed = float('nan')
        
        self._traj_pubs[namespace].publish(msg)
    
    def _send_vehicle_command(
        self,
        namespace: str,
        command: int,
        param1: float = 0.0,
        param2: float = 0.0
    ):
        """Send vehicle command (ARM, OFFBOARD, etc.)."""
        if namespace not in self._cmd_pubs:
            return
        
        msg = VehicleCommand()
        msg.timestamp = int(time.time() * 1e6)
        msg.command = command
        msg.param1 = param1
        msg.param2 = param2
        msg.target_system = 1
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        
        self._cmd_pubs[namespace].publish(msg)
    
    def _on_vehicle_status(self, namespace: str, msg):
        """Callback for vehicle status updates."""
        self._vehicle_status[namespace] = msg.arming_state
    
    def get_vehicle_status(self, namespace: str) -> int:
        """Get vehicle arming state (0=unknown, 1=disarmed, 2=armed)."""
        return self._vehicle_status.get(namespace, 0)
    
    def is_offboard_ready(self, namespace: str) -> bool:
        """Check if vehicle has received enough setpoints for offboard mode."""
        return self._offboard_counters.get(namespace, 0) >= 10


__all__ = ["PX4FormationController", "ned_to_enu", "enu_to_ned"]

