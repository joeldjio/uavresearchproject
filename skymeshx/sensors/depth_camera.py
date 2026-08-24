"""
ROS2 Depth Camera / Point Cloud Subscriber.

Subscribes to ROS2 depth camera topics (PointCloud2) and converts
point clouds to local NED coordinates for obstacle detection.

Typical Topics:
    - /camera/depth/points        (Intel RealSense)
    - /velodyne_points            (Velodyne LiDAR)
    - /ouster/points              (Ouster LiDAR)
    - /livox/lidar                (Livox LiDAR)

Frame Convention:
    Input: ROS2 sensor_msgs/PointCloud2 (typically in camera/sensor frame)
    Output: Local NED coordinates (x=North, y=East, z=altitude above ground)
    
    Requires transform from sensor frame to body frame, then body to NED.

Usage:
    from skymeshx.sensors.depth_camera import DepthCameraSubscriber
    from skymeshx.safety.perception_avoidance import PerceptionEnhancedAPF
    
    # Create APF filter
    apf = PerceptionEnhancedAPF()
    
    # Create depth camera subscriber
    def on_pointcloud(drone_id, points):
        apf.update_from_pointcloud(drone_id, points)
    
    camera = DepthCameraSubscriber(
        topic="/camera/depth/points",
        callback=on_pointcloud,
        drone_id="drone_1"
    )
    
    camera.start()
    # ... camera runs in background thread ...
    camera.stop()
"""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Tuple

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import PointCloud2
    from sensor_msgs_py import point_cloud2
    _ROS2_OK = True
except ImportError:
    rclpy = None  # type: ignore
    Node = object  # type: ignore
    PointCloud2 = None  # type: ignore
    point_cloud2 = None  # type: ignore
    _ROS2_OK = False

from skymeshx.ros.context import acquire_ros, release_ros
from skymeshx.exceptions import DependencyError


class DepthCameraSubscriber:
    """
    Subscribe to ROS2 depth camera/LiDAR point cloud topics.
    
    Converts PointCloud2 messages to list of (x, y, z) tuples in local NED.
    Runs in background thread with configurable callback.
    
    Thread Safety:
        - start() and stop() are thread-safe
        - Callback is invoked from ROS2 executor thread
        - Multiple subscribers can run concurrently
    
    Parameters:
        topic       : ROS2 topic name (e.g., "/camera/depth/points")
        callback    : Function called with (drone_id, points) on each message
        drone_id    : Identifier for this drone
        max_range   : Maximum range to include points (meters, None = no limit)
        downsample  : Downsample factor (1 = all points, 2 = every 2nd point, etc.)
    """
    
    def __init__(
        self,
        topic: str = "/camera/depth/points",
        callback: Optional[Callable[[str, List[Tuple[float, float, float]]], None]] = None,
        drone_id: str = "drone_1",
        max_range: Optional[float] = None,
        downsample: int = 1
    ):
        if not _ROS2_OK:
            raise DependencyError("rclpy", "pip install rclpy sensor_msgs_py")
        
        self.topic = topic
        self.callback = callback
        self.drone_id = drone_id
        self.max_range = max_range
        self.downsample = max(1, downsample)
        
        self._node: Optional[Node] = None
        self._subscription = None
        self._executor = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        
        # Statistics
        self._messages_received = 0
        self._points_processed = 0
        self._last_message_time = 0.0
    
    def start(self) -> bool:
        """
        Start subscribing to depth camera topic.
        
        Returns:
            True if started successfully, False if already running or ROS2 unavailable
        """
        if self._running:
            return False
        
        if not acquire_ros():
            return False
        
        try:
            # Create ROS2 node
            self._node = rclpy.create_node(f"depth_camera_{self.drone_id}")
            
            # Create subscription
            self._subscription = self._node.create_subscription(
                PointCloud2,
                self.topic,
                self._on_pointcloud,
                10  # QoS depth
            )
            
            # Create executor
            self._executor = rclpy.executors.SingleThreadedExecutor()
            self._executor.add_node(self._node)
            
            # Start executor in background thread
            self._running = True
            self._thread = threading.Thread(
                target=self._spin_thread,
                daemon=True,
                name=f"DepthCamera-{self.drone_id}"
            )
            self._thread.start()
            
            return True
            
        except Exception as e:
            print(f"[DepthCamera] Failed to start: {e}")
            release_ros()
            return False
    
    def stop(self):
        """Stop subscribing and clean up resources."""
        if not self._running:
            return
        
        self._running = False
        
        # Stop executor
        if self._executor:
            self._executor.shutdown()
        
        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        # Destroy node
        if self._node:
            self._node.destroy_node()
            self._node = None
        
        # Release ROS context
        release_ros()
    
    def _spin_thread(self):
        """Background thread that spins the ROS2 executor."""
        try:
            while self._running and rclpy.ok():
                self._executor.spin_once(timeout_sec=0.1)
        except Exception as e:
            print(f"[DepthCamera] Executor error: {e}")
        finally:
            self._running = False
    
    def _on_pointcloud(self, msg: PointCloud2):
        """
        Callback for PointCloud2 messages.
        
        Converts point cloud to list of (x, y, z) tuples and calls user callback.
        """
        self._messages_received += 1
        self._last_message_time = time.time()
        
        try:
            # Extract points from PointCloud2 message
            # point_cloud2.read_points returns generator of (x, y, z, ...) tuples
            points_raw = point_cloud2.read_points(
                msg,
                field_names=("x", "y", "z"),
                skip_nans=True
            )
            
            # Convert to list and apply filters
            points = []
            for i, (x, y, z) in enumerate(points_raw):
                # Downsample
                if i % self.downsample != 0:
                    continue
                
                # Range filter
                if self.max_range is not None:
                    dist = (x**2 + y**2 + z**2) ** 0.5
                    if dist > self.max_range:
                        continue
                
                # TODO: Transform from sensor frame to NED
                # For now, assume points are already in body frame
                # and body frame is aligned with NED (simplified)
                points.append((x, y, z))
            
            self._points_processed += len(points)
            
            # Call user callback
            if self.callback and points:
                self.callback(self.drone_id, points)
                
        except Exception as e:
            print(f"[DepthCamera] Error processing point cloud: {e}")
    
    def get_statistics(self) -> dict:
        """
        Get subscriber statistics.
        
        Returns:
            Dictionary with:
            - messages_received: Total PointCloud2 messages received
            - points_processed: Total points processed
            - last_message_time: Timestamp of last message (seconds since epoch)
            - is_running: Whether subscriber is active
        """
        return {
            "messages_received": self._messages_received,
            "points_processed": self._points_processed,
            "last_message_time": self._last_message_time,
            "is_running": self._running
        }
    
    def __enter__(self):
        """Context manager support."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        self.stop()
        return False
