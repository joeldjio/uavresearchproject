"""
ROS2 Bag Recorder for PX4 data recording and playback.

This module provides a wrapper around ros2 bag CLI for recording and playing back
ROS2 topics from PX4 drones. It runs recording/playback in background processes.
"""

import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

try:
    import rclpy
    _ROS2_OK = True
except ImportError:
    _ROS2_OK = False

from skymeshx.exceptions import ROS2NotAvailableError


@dataclass
class BagInfo:
    """Information about a recorded bag file."""
    path: str
    size_mb: float
    duration_sec: float
    message_count: int
    topics: List[str]
    start_time: str


class ROS2BagRecorder:
    """
    ROS2 Bag recorder for PX4 topics.
    
    Runs `ros2 bag record` in a background process and provides status monitoring.
    """
    
    def __init__(self, output_dir: str = "./bags"):
        """
        Initialize bag recorder.
        
        Args:
            output_dir: Directory to store bag files (default: ./bags)
        """
        if not _ROS2_OK:
            raise ROS2NotAvailableError("rclpy not available — cannot use ROS2 bag recorder")
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self._process: Optional[subprocess.Popen] = None
        self._recording = False
        self._current_bag_path: Optional[Path] = None
        self._start_time: Optional[float] = None
        self._message_count = 0
        
        # Monitoring thread
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
    
    def start_recording(
        self,
        topics: List[str],
        bag_name: Optional[str] = None,
        compression: str = "zstd"
    ) -> bool:
        """
        Start recording specified topics.
        
        Args:
            topics: List of topic names to record (e.g., ["/fmu/out/vehicle_odometry"])
            bag_name: Optional custom bag name (default: timestamp-based)
            compression: Compression mode: "zstd", "lz4", or "none" (default: zstd)
        
        Returns:
            True if recording started successfully
        """
        if self._recording:
            print("[BagRecorder] Already recording")
            return False
        
        if not topics:
            print("[BagRecorder] No topics specified")
            return False
        
        # Generate bag name
        if bag_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bag_name = f"px4_bag_{timestamp}"
        
        self._current_bag_path = self.output_dir / bag_name
        
        # Build command
        cmd = [
            "ros2", "bag", "record",
            "-o", str(self._current_bag_path),
            "-s", compression
        ]
        cmd.extend(topics)
        
        try:
            # Start recording process
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self._recording = True
            self._start_time = time.time()
            self._message_count = 0
            
            # Start monitoring thread
            self._stop_monitor.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_recording,
                daemon=True
            )
            self._monitor_thread.start()
            
            print(f"[BagRecorder] Started recording to {self._current_bag_path}")
            return True
            
        except Exception as e:
            print(f"[BagRecorder] Failed to start recording: {e}")
            self._recording = False
            return False
    
    def stop_recording(self) -> bool:
        """
        Stop current recording.
        
        Returns:
            True if recording stopped successfully
        """
        if not self._recording:
            print("[BagRecorder] Not recording")
            return False
        
        try:
            # Stop monitoring
            self._stop_monitor.set()
            if self._monitor_thread:
                self._monitor_thread.join(timeout=2.0)
            
            # Terminate recording process
            if self._process:
                self._process.terminate()
                self._process.wait(timeout=5.0)
            
            self._recording = False
            duration = time.time() - self._start_time if self._start_time else 0
            
            print(f"[BagRecorder] Stopped recording after {duration:.1f}s")
            print(f"[BagRecorder] Bag saved to {self._current_bag_path}")
            
            return True
            
        except Exception as e:
            print(f"[BagRecorder] Error stopping recording: {e}")
            return False
        finally:
            self._process = None
            self._recording = False
    
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._recording
    
    def get_recording_status(self) -> dict:
        """
        Get current recording status.
        
        Returns:
            Dict with keys: recording, duration_sec, bag_path, size_mb
        """
        if not self._recording:
            return {
                "recording": False,
                "duration_sec": 0.0,
                "bag_path": "",
                "size_mb": 0.0
            }
        
        duration = time.time() - self._start_time if self._start_time else 0.0
        size_mb = self._get_bag_size_mb() if self._current_bag_path else 0.0
        
        return {
            "recording": True,
            "duration_sec": duration,
            "bag_path": str(self._current_bag_path),
            "size_mb": size_mb
        }
    
    def list_bags(self) -> List[BagInfo]:
        """
        List all bag files in output directory.
        
        Returns:
            List of BagInfo objects
        """
        bags = []
        
        for bag_dir in self.output_dir.iterdir():
            if bag_dir.is_dir():
                info = self._get_bag_info(bag_dir)
                if info:
                    bags.append(info)
        
        # Sort by start time (newest first)
        bags.sort(key=lambda x: x.start_time, reverse=True)
        return bags
    
    def play_bag(self, bag_path: str, rate: float = 1.0) -> bool:
        """
        Play back a recorded bag file.
        
        Args:
            bag_path: Path to bag directory
            rate: Playback rate multiplier (default: 1.0 = real-time)
        
        Returns:
            True if playback started successfully
        """
        bag_path = Path(bag_path)
        if not bag_path.exists():
            print(f"[BagRecorder] Bag not found: {bag_path}")
            return False
        
        cmd = [
            "ros2", "bag", "play",
            str(bag_path),
            "-r", str(rate)
        ]
        
        try:
            # Start playback in background
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print(f"[BagRecorder] Started playback of {bag_path} at {rate}x speed")
            return True
            
        except Exception as e:
            print(f"[BagRecorder] Failed to start playback: {e}")
            return False
    
    def _monitor_recording(self):
        """Monitor recording process (runs in background thread)."""
        while not self._stop_monitor.is_set():
            if self._process and self._process.poll() is not None:
                # Process terminated unexpectedly
                print("[BagRecorder] Recording process terminated unexpectedly")
                self._recording = False
                break
            
            time.sleep(1.0)
    
    def _get_bag_size_mb(self) -> float:
        """Get current bag size in MB."""
        if not self._current_bag_path or not self._current_bag_path.exists():
            return 0.0
        
        total_size = 0
        for file in self._current_bag_path.rglob("*"):
            if file.is_file():
                total_size += file.stat().st_size
        
        return total_size / (1024 * 1024)
    
    def _get_bag_info(self, bag_path: Path) -> Optional[BagInfo]:
        """Get information about a bag file using ros2 bag info."""
        try:
            result = subprocess.run(
                ["ros2", "bag", "info", str(bag_path)],
                capture_output=True,
                text=True,
                timeout=5.0
            )
            
            if result.returncode != 0:
                return None
            
            # Parse output
            output = result.stdout
            duration = 0.0
            message_count = 0
            topics = []
            start_time = ""
            
            for line in output.split("\n"):
                line = line.strip()
                if "Duration:" in line:
                    # Extract duration in seconds (format: "Duration: 45.2s" or "Duration: 45.2")
                    parts = line.split(":")
                    if len(parts) >= 2:
                        duration_str = parts[1].strip().rstrip('s').split()[0]
                        try:
                            duration = float(duration_str)
                        except ValueError:
                            pass
                
                elif "Start:" in line:
                    parts = line.split(":", 1)
                    if len(parts) >= 2:
                        start_time = parts[1].strip()
                
                elif "Messages:" in line or "Message count:" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        try:
                            message_count = int(parts[1].strip())
                        except ValueError:
                            pass
                
                elif "Topic:" in line or line.startswith("/"):
                    # Extract topic name
                    if "Topic:" in line:
                        topic = line.split("Topic:")[1].strip().split()[0]
                    else:
                        topic = line.split()[0]
                    if topic.startswith("/"):
                        topics.append(topic)
            
            # Get size
            size_mb = 0.0
            for file in bag_path.rglob("*"):
                if file.is_file():
                    size_mb += file.stat().st_size / (1024 * 1024)
            
            return BagInfo(
                path=str(bag_path),
                size_mb=size_mb,
                duration_sec=duration,
                message_count=message_count,
                topics=list(set(topics)),  # Remove duplicates
                start_time=start_time
            )
            
        except Exception as e:
            print(f"[BagRecorder] Error getting bag info for {bag_path}: {e}")
            return None
    
    def __del__(self):
        """Cleanup on deletion."""
        if self._recording:
            self.stop_recording()

