"""
PX4 Mission Upload via uXRCE-DDS.

Provides mission upload functionality for PX4 via ROS2 topics.
Uses the native PX4 mission protocol over uXRCE-DDS.

Reference:
    https://docs.px4.io/main/en/ros2/user_guide.html
    https://mavlink.io/en/services/mission.html
"""

from __future__ import annotations

import threading
import time
import logging
from typing import Optional, List, Dict, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum

# Import shared validation logic
try:
    from skymeshx.control.mission_validation import validate_waypoints
    _VALIDATION_OK = True
except ImportError:
    _VALIDATION_OK = False

from skymeshx.exceptions import DependencyError, MissionUploadError, ROS2NotAvailableError

try:
    import rclpy
    from rclpy.node import Node
    _ROS2_OK = True
except ImportError:
    _ROS2_OK = False

try:
    from px4_msgs.msg import VehicleMissionItem, VehicleMissionItemCount
    # Note: VehicleMissionAck might not exist in all px4_msgs versions
    # We'll handle this gracefully
    try:
        from px4_msgs.msg import VehicleMissionAck
        _MISSION_ACK_OK = True
    except ImportError:
        _MISSION_ACK_OK = False
    
    # Mission status monitoring
    try:
        from px4_msgs.msg import MissionResult
        _MISSION_RESULT_OK = True
    except ImportError:
        _MISSION_RESULT_OK = False
    
    _PX4_MSGS_OK = True
except ImportError:
    _PX4_MSGS_OK = False

logger = logging.getLogger(__name__)


class UploadStatus(Enum):
    """Mission upload status."""
    IDLE = "idle"
    SENDING_COUNT = "sending_count"
    SENDING_ITEMS = "sending_items"
    WAITING_ACK = "waiting_ack"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PX4MissionUploader:
    """
    Mission upload via uXRCE-DDS for PX4.
    
    Uploads waypoint missions to PX4 using ROS2 topics:
        - /fmu/in/vehicle_mission_item_count
        - /fmu/in/vehicle_mission_item
        - /fmu/out/vehicle_mission_ack (if available)
    
    Example:
        >>> uploader = PX4MissionUploader(node, namespace="uav_1")
        >>> waypoints = [
        ...     {"lat": 47.397742, "lon": 8.545594, "alt": 10.0},
        ...     {"lat": 47.397842, "lon": 8.545694, "alt": 15.0},
        ... ]
        >>> success = uploader.upload(waypoints)
    """
    
    def __init__(self, node: Node, namespace: str = ""):
        """
        Initialize mission uploader.
        
        Args:
            node: ROS2 node instance
            namespace: PX4 namespace (e.g., "uav_1")
        """
        if not _ROS2_OK:
            raise ROS2NotAvailableError("rclpy not available")
        if not _PX4_MSGS_OK:
            raise DependencyError("px4_msgs", "colcon build --packages-select px4_msgs")
        
        self._node = node
        self._ns = f"/{namespace}" if namespace else ""
        
        # Publishers
        self._pub_count = node.create_publisher(
            VehicleMissionItemCount,
            f"{self._ns}/fmu/in/vehicle_mission_item_count",
            10
        )
        self._pub_item = node.create_publisher(
            VehicleMissionItem,
            f"{self._ns}/fmu/in/vehicle_mission_item",
            10
        )
        
        # Subscriber for ACK (if available)
        self._sub_ack = None
        if _MISSION_ACK_OK:
            self._sub_ack = node.create_subscription(
                VehicleMissionAck,
                f"{self._ns}/fmu/out/vehicle_mission_ack",
                self._on_ack,
                10
            )
        
        # Subscriber for mission result/status (if available)
        self._sub_result = None
        if _MISSION_RESULT_OK:
            self._sub_result = node.create_subscription(
                MissionResult,
                f"{self._ns}/fmu/out/mission_result",
                self._on_mission_result,
                10
            )
        
        self._ack_received = threading.Event()
        self._ack_result = None
        
        # Mission status tracking
        self._mission_status = {
            "active": False,
            "current_seq": 0,
            "total_count": 0,
            "reached": False,
            "finished": False,
            "failure": False,
            "item_do_jump_changed": False,
            "item_changed_index": 0,
            "mode_auto": False,
            "mode_offboard": False,
        }
        self._status_callbacks: List[Callable] = []
        self._uploaded_waypoints: List[Dict] = []
        
        # Async upload state
        self._upload_status = UploadStatus.IDLE
        self._upload_progress = 0.0  # 0.0 to 1.0
        self._upload_future: Optional[Future] = None
        self._upload_cancelled = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mission_upload")
        self._progress_callbacks: List[Callable[[UploadStatus, float, str], None]] = []
        
        logger.info(f"PX4MissionUploader initialized (namespace: {namespace or '/'})")
    
    def validate(self, waypoints: List[Dict]) -> Tuple[bool, List[str]]:
        """
        Validate mission waypoints before upload.
        
        Checks:
        - Minimum waypoint count (at least 1)
        - Valid coordinates (lat: -90 to 90, lon: -180 to 180)
        - Reasonable altitudes (0 to 500m)
        - Waypoint spacing (warn if < 1m apart)
        
        Args:
            waypoints: List of waypoint dicts with keys: lat, lon, alt
        
        Returns:
            (is_valid, list_of_errors)
        """
        if not _VALIDATION_OK:
            # Fallback: basic validation if shared module not available
            errors = []
            if len(waypoints) == 0:
                errors.append("Mission has no waypoints")
            return len(errors) == 0, errors
        
        return validate_waypoints(waypoints)
    
    def upload(self, waypoints: List[Dict], timeout: float = 10.0, validate_first: bool = True) -> bool:
        """
        Upload waypoints to PX4.
        
        Args:
            waypoints: List of waypoint dicts with keys: lat, lon, alt
                      Example: [{"lat": 47.397, "lon": 8.545, "alt": 10.0}, ...]
            timeout: Timeout in seconds for ACK (if available)
        
        Returns:
            True if upload successful (or if ACK not available)
        
        Args:
            validate_first: Run pre-flight validation before upload (default: True)
        """
        # Pre-flight validation
        if validate_first:
            is_valid, errors = self.validate(waypoints)
            if not is_valid:
                logger.error("Pre-flight validation failed:")
                for error in errors:
                    logger.error(f"  - {error}")
                return False
        
        if not waypoints:
            logger.warning("No waypoints to upload")
            return False
        
        # Store waypoints for later retrieval
        self._uploaded_waypoints = waypoints.copy()
        
        # Update mission status
        self._mission_status["total_count"] = len(waypoints)
        self._mission_status["current_seq"] = 0
        
        logger.info(f"Uploading {len(waypoints)} waypoints...")
        
        # Reset ACK state
        self._ack_received.clear()
        self._ack_result = None
        
        # 1. Send mission count
        count_msg = VehicleMissionItemCount()
        count_msg.timestamp = int(time.time() * 1e6)
        count_msg.count = len(waypoints)
        self._pub_count.publish(count_msg)
        logger.debug(f"Sent mission count: {len(waypoints)}")
        
        # Small delay to ensure count is received
        time.sleep(0.1)
        
        # 2. Send mission items
        for i, wp in enumerate(waypoints):
            item = VehicleMissionItem()
            item.timestamp = int(time.time() * 1e6)
            item.sequence = i
            item.frame = 3  # MAV_FRAME_GLOBAL_RELATIVE_ALT
            item.command = 16  # MAV_CMD_NAV_WAYPOINT
            item.latitude = wp["lat"]
            item.longitude = wp["lon"]
            item.altitude = wp["alt"]
            item.autocontinue = True
            
            # Optional parameters
            item.param1 = wp.get("hold_time", 0.0)  # Hold time in seconds
            item.param2 = wp.get("accept_radius", 1.0)  # Acceptance radius in meters
            item.param3 = wp.get("pass_radius", 0.0)  # Pass radius
            item.param4 = wp.get("yaw", float('nan'))  # Yaw angle
            
            self._pub_item.publish(item)
            logger.debug(f"Sent waypoint {i+1}/{len(waypoints)}: "
                        f"lat={wp['lat']:.6f}, lon={wp['lon']:.6f}, alt={wp['alt']:.1f}")
            
            # Small delay between items
            time.sleep(0.05)
        
        logger.info(f"All {len(waypoints)} waypoints sent")
        
        # 3. Wait for ACK (if available)
        if _MISSION_ACK_OK and self._sub_ack:
            logger.debug(f"Waiting for ACK (timeout: {timeout}s)...")
            ack_received = self._ack_received.wait(timeout=timeout)
            
            if not ack_received:
                logger.warning("No ACK received within timeout")
                return False
            
            if self._ack_result == 0:  # MAV_MISSION_ACCEPTED
                logger.info("✓ Mission upload confirmed by PX4")
                return True
            else:
                logger.error(f"Mission upload rejected by PX4 (result: {self._ack_result})")
                return False
        else:
            # No ACK available, assume success
            logger.info("✓ Mission uploaded (no ACK confirmation available)")
            return True
    
    def upload_async(
        self, 
        waypoints: List[Dict], 
        timeout: float = 10.0,
        progress_callback: Optional[Callable[[UploadStatus, float, str], None]] = None
    ) -> Future:
        """
        Upload waypoints asynchronously (non-blocking).
        
        Args:
            waypoints: List of waypoint dicts with keys: lat, lon, alt
            timeout: Timeout in seconds for ACK
            progress_callback: Optional callback(status, progress, message)
                              Called with progress updates
        
        Returns:
            Future object that resolves to bool (success/failure)
            
        Example:
            >>> def on_progress(status, progress, msg):
            ...     print(f"{status.value}: {progress*100:.0f}% - {msg}")
            >>> future = uploader.upload_async(waypoints, progress_callback=on_progress)
            >>> # Do other work...
            >>> success = future.result()  # Wait for completion
        """
        if self._upload_status != UploadStatus.IDLE:
            raise MissionUploadError(f"Upload already in progress (status: {self._upload_status.value})")
        
        # Reset state
        self._upload_cancelled.clear()
        self._upload_progress = 0.0
        
        # Register callback if provided
        if progress_callback:
            self._progress_callbacks.append(progress_callback)
        
        # Submit upload task to executor
        self._upload_future = self._executor.submit(
            self._upload_worker,
            waypoints,
            timeout
        )
        
        return self._upload_future
    
    def cancel_upload(self):
        """Cancel ongoing async upload."""
        if self._upload_status not in (UploadStatus.IDLE, UploadStatus.SUCCESS, UploadStatus.FAILED):
            logger.info("Cancelling upload...")
            self._upload_cancelled.set()
            self._update_progress(UploadStatus.CANCELLED, 0.0, "Upload cancelled by user")
    
    def get_upload_status(self) -> Dict:
        """
        Get current upload status.
        
        Returns:
            Dict with keys: status, progress, message
        """
        return {
            "status": self._upload_status.value,
            "progress": self._upload_progress,
            "is_uploading": self._upload_status not in (
                UploadStatus.IDLE, 
                UploadStatus.SUCCESS, 
                UploadStatus.FAILED,
                UploadStatus.CANCELLED
            )
        }
    
    def add_progress_callback(self, callback: Callable[[UploadStatus, float, str], None]):
        """Add a progress callback."""
        if callback not in self._progress_callbacks:
            self._progress_callbacks.append(callback)
    
    def remove_progress_callback(self, callback: Callable[[UploadStatus, float, str], None]):
        """Remove a progress callback."""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    def _update_progress(self, status: UploadStatus, progress: float, message: str = ""):
        """Update progress and notify callbacks."""
        self._upload_status = status
        self._upload_progress = progress
        
        # Notify all callbacks
        for callback in self._progress_callbacks:
            try:
                callback(status, progress, message)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")
    
    def _upload_worker(self, waypoints: List[Dict], timeout: float) -> bool:
        """Worker function for async upload (runs in thread)."""
        try:
            if not waypoints:
                self._update_progress(UploadStatus.FAILED, 0.0, "No waypoints to upload")
                return False
            
            # Store waypoints
            self._uploaded_waypoints = waypoints.copy()
            self._mission_status["total_count"] = len(waypoints)
            self._mission_status["current_seq"] = 0
            
            logger.info(f"[Async] Uploading {len(waypoints)} waypoints...")
            
            # Reset ACK state
            self._ack_received.clear()
            self._ack_result = None
            
            # Phase 1: Send mission count (10% progress)
            self._update_progress(UploadStatus.SENDING_COUNT, 0.1, f"Sending mission count: {len(waypoints)}")
            
            if self._upload_cancelled.is_set():
                return False
            
            count_msg = VehicleMissionItemCount()
            count_msg.timestamp = int(time.time() * 1e6)
            count_msg.count = len(waypoints)
            self._pub_count.publish(count_msg)
            logger.debug(f"[Async] Sent mission count: {len(waypoints)}")
            
            time.sleep(0.1)
            
            # Phase 2: Send mission items (10% to 80% progress)
            self._update_progress(UploadStatus.SENDING_ITEMS, 0.1, "Sending waypoints...")
            
            for i, wp in enumerate(waypoints):
                if self._upload_cancelled.is_set():
                    return False
                
                item = VehicleMissionItem()
                item.timestamp = int(time.time() * 1e6)
                item.sequence = i
                item.frame = 3  # MAV_FRAME_GLOBAL_RELATIVE_ALT
                item.command = 16  # MAV_CMD_NAV_WAYPOINT
                item.latitude = wp["lat"]
                item.longitude = wp["lon"]
                item.altitude = wp["alt"]
                item.autocontinue = True
                
                # Optional parameters
                item.param1 = wp.get("hold_time", 0.0)
                item.param2 = wp.get("accept_radius", 1.0)
                item.param3 = wp.get("pass_radius", 0.0)
                item.param4 = wp.get("yaw", float('nan'))
                
                self._pub_item.publish(item)
                
                # Update progress (10% to 80%)
                progress = 0.1 + (0.7 * (i + 1) / len(waypoints))
                self._update_progress(
                    UploadStatus.SENDING_ITEMS, 
                    progress, 
                    f"Sent waypoint {i+1}/{len(waypoints)}"
                )
                
                logger.debug(f"[Async] Sent waypoint {i+1}/{len(waypoints)}: "
                            f"lat={wp['lat']:.6f}, lon={wp['lon']:.6f}, alt={wp['alt']:.1f}")
                
                time.sleep(0.05)
            
            logger.info(f"[Async] All {len(waypoints)} waypoints sent")
            
            # Phase 3: Wait for ACK (80% to 100% progress)
            if _MISSION_ACK_OK and self._sub_ack:
                self._update_progress(UploadStatus.WAITING_ACK, 0.8, f"Waiting for ACK (timeout: {timeout}s)...")
                logger.debug(f"[Async] Waiting for ACK (timeout: {timeout}s)...")
                
                ack_received = self._ack_received.wait(timeout=timeout)
                
                if self._upload_cancelled.is_set():
                    return False
                
                if not ack_received:
                    self._update_progress(UploadStatus.FAILED, 0.8, "No ACK received within timeout")
                    logger.warning("[Async] No ACK received within timeout")
                    return False
                
                if self._ack_result == 0:  # MAV_MISSION_ACCEPTED
                    self._update_progress(UploadStatus.SUCCESS, 1.0, "Mission upload confirmed by PX4")
                    logger.info("[Async] ✓ Mission upload confirmed by PX4")
                    return True
                else:
                    self._update_progress(UploadStatus.FAILED, 0.8, f"Mission rejected by PX4 (result: {self._ack_result})")
                    logger.error(f"[Async] Mission upload rejected by PX4 (result: {self._ack_result})")
                    return False
            else:
                # No ACK available, assume success
                self._update_progress(UploadStatus.SUCCESS, 1.0, "Mission uploaded (no ACK confirmation)")
                logger.info("[Async] ✓ Mission uploaded (no ACK confirmation available)")
                return True
                
        except Exception as e:
            self._update_progress(UploadStatus.FAILED, self._upload_progress, f"Upload error: {e}")
            logger.error(f"[Async] Upload error: {e}", exc_info=True)
            return False
    
    def clear(self) -> bool:
        """
        Clear mission on PX4.
        
        Returns:
            True if successful
        """
        logger.info("Clearing mission...")
        
        # Send count = 0 to clear mission
        count_msg = VehicleMissionItemCount()
        count_msg.timestamp = int(time.time() * 1e6)
        count_msg.count = 0
        self._pub_count.publish(count_msg)
        
        logger.info("✓ Mission clear command sent")
        return True
    
    def _on_ack(self, msg):
        """Handle mission ACK from PX4."""
        self._ack_result = msg.result
        self._ack_received.set()
        
        result_names = {
            0: "ACCEPTED",
            1: "ERROR",
            2: "UNSUPPORTED_FRAME",
            3: "UNSUPPORTED",
            4: "NO_SPACE",
            5: "INVALID",
            6: "INVALID_PARAM1",
            7: "INVALID_PARAM2",
            8: "INVALID_PARAM3",
            9: "INVALID_PARAM4",
            10: "INVALID_PARAM5_X",
            11: "INVALID_PARAM6_Y",
            12: "INVALID_PARAM7",
            13: "INVALID_SEQUENCE",
            14: "DENIED",
        }
        
        result_name = result_names.get(msg.result, f"UNKNOWN({msg.result})")
        logger.debug(f"Received mission ACK: {result_name}")
    
    def _on_mission_result(self, msg):
        """Handle mission result/status from PX4."""
        # Update mission status
        self._mission_status.update({
            "active": msg.mission_id > 0,
            "current_seq": msg.seq_current,
            "total_count": msg.seq_total,
            "reached": msg.seq_reached == msg.seq_current,
            "finished": msg.finished,
            "failure": msg.failure,
            "item_do_jump_changed": msg.item_do_jump_changed,
            "item_changed_index": msg.item_changed_index,
            "mode_auto": msg.mode_auto,
            "mode_offboard": msg.mode_offboard,
        })
        
        # Fire callbacks
        for cb in self._status_callbacks:
            try:
                cb(self._mission_status.copy())
            except Exception as e:
                logger.error(f"Mission status callback error: {e}")
        
        logger.debug(f"Mission status: seq {msg.seq_current}/{msg.seq_total}, "
                    f"finished={msg.finished}, failure={msg.failure}")
    
    def on_status_change(self, callback: Callable):
        """
        Register callback for mission status changes.
        
        Args:
            callback: Function that receives mission status dict
        """
        self._status_callbacks.append(callback)
    
    def get_status(self) -> Dict:
        """
        Get current mission status.
        
        Returns:
            Dict with mission status information
        """
        return self._mission_status.copy()
    
    def get_waypoints(self) -> List[Dict]:
        """
        Get uploaded waypoints.
        
        Returns:
            List of waypoint dicts
        """
        return self._uploaded_waypoints.copy()

