"""
ROS2 Thermal Camera Subscriber.

Subscribes to ROS2 thermal camera topics (Image) and converts
thermal images to temperature maps for hotspot detection in solar panels.

Typical Topics:
    - /thermal/image_raw          (FLIR thermal camera)
    - /thermal/temperature        (Calibrated temperature)
    - /thermal_camera/image       (Generic thermal camera)

Frame Convention:
    Input: ROS2 sensor_msgs/Image (16-bit thermal data)
    Output: NumPy array with temperature in Celsius
    
    Thermal cameras typically output 16-bit raw values that need
    calibration to convert to actual temperature readings.

Usage:
    from skymeshx.sensors.thermal_camera import ThermalCameraSubscriber
    
    # Create thermal camera subscriber
    def on_thermal_image(image, metadata):
        # Process temperature map
        hotspots = np.where(image > 80.0)  # Find panels > 80°C
        print(f"Found {len(hotspots[0])} hotspots")
    
    camera = ThermalCameraSubscriber(
        topic="/thermal/image_raw",
        callback=on_thermal_image
    )
    
    camera.start()
    # ... camera runs in background thread ...
    camera.stop()
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional

try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_OK = False

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    from cv_bridge import CvBridge
    _ROS2_OK = True
except ImportError:
    rclpy = None  # type: ignore
    Node = object  # type: ignore
    Image = None  # type: ignore
    CvBridge = None  # type: ignore
    _ROS2_OK = False

from skymeshx.ros.context import acquire_ros, release_ros
from skymeshx.exceptions import DependencyError


class ThermalCameraSubscriber:
    """
    Subscribe to ROS2 thermal camera topics.
    
    Converts thermal Image messages to temperature arrays in Celsius.
    Runs in background thread with configurable callback.
    
    Thread Safety:
        - start() and stop() are thread-safe
        - Callback is invoked from ROS2 executor thread
        - Multiple subscribers can run concurrently
    
    Parameters:
        topic           : ROS2 topic name (e.g., "/thermal/image_raw")
        callback        : Function called with (image, metadata) on each frame
        calibration_a   : Linear calibration coefficient (temp = a * raw + b)
        calibration_b   : Linear calibration offset
        min_temp        : Minimum valid temperature (°C)
        max_temp        : Maximum valid temperature (°C)
    """
    
    def __init__(
        self,
        topic: str = "/thermal/image_raw",
        callback: Optional[Callable[[np.ndarray, Dict], None]] = None,
        calibration_a: float = 0.01,
        calibration_b: float = -273.15,
        min_temp: float = -40.0,
        max_temp: float = 150.0
    ):
        if not _ROS2_OK:
            raise DependencyError("rclpy", "pip install rclpy cv_bridge")
        if not _NUMPY_OK:
            raise DependencyError("numpy", "pip install numpy")
        
        self.topic = topic
        self.callback = callback
        self.calibration_a = calibration_a
        self.calibration_b = calibration_b
        self.min_temp = min_temp
        self.max_temp = max_temp
        
        self._node: Optional[Node] = None
        self._subscription = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._bridge = CvBridge()
        
        # Statistics
        self._frame_count = 0
        self._last_frame_time = 0.0
        self._fps = 0.0
    
    def start(self) -> bool:
        """
        Start subscribing to thermal camera topic.
        
        Returns:
            True if started successfully, False otherwise
        """
        with self._lock:
            if self._running:
                return True
            
            # Acquire ROS2 context
            if not acquire_ros():
                return False
            
            try:
                # Create ROS2 node
                self._node = rclpy.create_node(
                    f'thermal_camera_subscriber_{id(self)}'
                )
                
                # Create subscription
                self._subscription = self._node.create_subscription(
                    Image,
                    self.topic,
                    self._on_image,
                    10  # QoS depth
                )
                
                # Start spinning thread
                self._running = True
                self._thread = threading.Thread(
                    target=self._spin,
                    daemon=True,
                    name=f"ThermalCamera-{self.topic}"
                )
                self._thread.start()
                
                return True
                
            except Exception as e:
                print(f"Failed to start thermal camera subscriber: {e}")
                release_ros()
                return False
    
    def stop(self) -> None:
        """Stop subscribing and cleanup resources."""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
        
        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        # Cleanup ROS2 resources
        if self._node:
            try:
                self._node.destroy_node()
            except Exception:
                pass
            self._node = None
        
        release_ros()
    
    def _spin(self) -> None:
        """Background thread that spins the ROS2 executor."""
        while self._running:
            try:
                rclpy.spin_once(self._node, timeout_sec=0.1)
            except Exception as e:
                if self._running:
                    print(f"Error in thermal camera spin: {e}")
                break
    
    def _on_image(self, msg: Image) -> None:
        """
        Process incoming thermal image message.
        
        Args:
            msg: ROS2 Image message with thermal data
        """
        try:
            # Convert ROS Image to numpy array
            if msg.encoding == "16UC1":
                # 16-bit unsigned integer (typical for thermal cameras)
                thermal_raw = self._bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
            elif msg.encoding == "mono16":
                thermal_raw = self._bridge.imgmsg_to_cv2(msg, desired_encoding="mono16")
            else:
                print(f"Unsupported thermal image encoding: {msg.encoding}")
                return
            
            # Apply calibration to convert raw values to temperature (Celsius)
            temp_celsius = self._calibrate_temperature(thermal_raw)
            
            # Clip to valid temperature range
            temp_celsius = np.clip(temp_celsius, self.min_temp, self.max_temp)
            
            # Create metadata
            metadata = {
                'timestamp': msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                'frame_id': msg.header.frame_id,
                'encoding': msg.encoding,
                'width': msg.width,
                'height': msg.height,
                'min_temp': float(np.min(temp_celsius)),
                'max_temp': float(np.max(temp_celsius)),
                'mean_temp': float(np.mean(temp_celsius)),
                'fps': self._fps
            }
            
            # Update statistics
            self._update_stats()
            
            # Invoke callback
            if self.callback:
                self.callback(temp_celsius, metadata)
                
        except Exception as e:
            print(f"Error processing thermal image: {e}")
    
    def _calibrate_temperature(self, raw: np.ndarray) -> np.ndarray:
        """
        Convert raw thermal values to temperature in Celsius.
        
        Uses linear calibration: temp = a * raw + b
        
        Args:
            raw: Raw thermal values (16-bit unsigned)
        
        Returns:
            Temperature array in Celsius
        """
        # Convert to float for calibration
        raw_float = raw.astype(np.float32)
        
        # Apply linear calibration
        temp_celsius = self.calibration_a * raw_float + self.calibration_b
        
        return temp_celsius
    
    def _update_stats(self) -> None:
        """Update frame rate statistics."""
        self._frame_count += 1
        current_time = time.time()
        
        if self._last_frame_time > 0:
            dt = current_time - self._last_frame_time
            if dt > 0:
                # Exponential moving average for FPS
                alpha = 0.1
                instant_fps = 1.0 / dt
                self._fps = alpha * instant_fps + (1 - alpha) * self._fps
        
        self._last_frame_time = current_time
    
    def get_stats(self) -> Dict:
        """
        Get subscriber statistics.
        
        Returns:
            Dictionary with frame_count and fps
        """
        return {
            'frame_count': self._frame_count,
            'fps': self._fps,
            'running': self._running
        }
    
    def is_running(self) -> bool:
        """Check if subscriber is running."""
        return self._running


class ThermalHotspotDetector:
    """
    Detect hotspots in thermal images for solar panel inspection.
    
    Identifies areas with abnormally high temperatures that may
    indicate faulty or damaged solar panels.
    """
    
    def __init__(
        self,
        threshold_temp: float = 80.0,
        min_hotspot_size: int = 10
    ):
        """
        Initialize hotspot detector.
        
        Args:
            threshold_temp: Temperature threshold for hotspot detection (°C)
            min_hotspot_size: Minimum number of pixels for valid hotspot
        """
        if not _NUMPY_OK:
            raise DependencyError("numpy", "pip install numpy")
        
        self.threshold_temp = threshold_temp
        self.min_hotspot_size = min_hotspot_size
    
    def detect_hotspots(
        self,
        temp_image: np.ndarray
    ) -> list[Dict]:
        """
        Detect hotspots in temperature image.
        
        Args:
            temp_image: Temperature array in Celsius
        
        Returns:
            List of hotspot dictionaries with location and statistics
        """
        # Find pixels above threshold
        hotspot_mask = temp_image > self.threshold_temp
        
        # Label connected components
        try:
            from scipy import ndimage
            labeled, num_features = ndimage.label(hotspot_mask)
        except ImportError:
            # Fallback: treat all hotspot pixels as one region
            if np.any(hotspot_mask):
                num_features = 1
                labeled = hotspot_mask.astype(int)
            else:
                return []
        
        hotspots = []
        
        for i in range(1, num_features + 1):
            # Get pixels for this hotspot
            hotspot_pixels = labeled == i
            pixel_count = np.sum(hotspot_pixels)
            
            # Filter by minimum size
            if pixel_count < self.min_hotspot_size:
                continue
            
            # Calculate hotspot statistics
            hotspot_temps = temp_image[hotspot_pixels]
            y_coords, x_coords = np.where(hotspot_pixels)
            
            hotspot = {
                'id': i,
                'pixel_count': int(pixel_count),
                'center_x': float(np.mean(x_coords)),
                'center_y': float(np.mean(y_coords)),
                'min_temp': float(np.min(hotspot_temps)),
                'max_temp': float(np.max(hotspot_temps)),
                'mean_temp': float(np.mean(hotspot_temps)),
                'std_temp': float(np.std(hotspot_temps))
            }
            
            hotspots.append(hotspot)
        
        return hotspots
