"""
PX4 Gazebo SITL automation.

Automatically starts:
- Micro XRCE-DDS Agent
- PX4 SITL instances with Gazebo
- Waits for connections
"""

from __future__ import annotations

import re
import shlex
import subprocess
import time
import os
import signal
import sys
import threading
from typing import Optional, List, Callable

from skymeshx.exceptions import ConfigurationError, InvalidParameterError, SimulationError
import logging

logger = logging.getLogger(__name__)


class PX4GazeboCluster:
    """
    Automatic setup for PX4 SITL + Gazebo + uXRCE-DDS.
    
    Starts:
        1. Micro XRCE-DDS Agent (Port 8888)
        2. PX4 SITL instances with Gazebo
        3. Waits for uXRCE-DDS connections
    
    Example:
        >>> cluster = PX4GazeboCluster(
        ...     num_drones=1,
        ...     px4_dir="/home/iruz/PX4-Autopilot",
        ...     model="x500",
        ...     ros2_setups=[
        ...         "/opt/ros/humble/setup.bash",
        ...         "/home/iruz/ws_sensor_combined/install/setup.bash"
        ...     ]
        ... )
        >>> cluster.start()
        >>> # SITL is ready, connect bridges
        >>> bridge = PX4ROS2Bridge(namespace="uav_1")
        >>> bridge.start()
        >>> # ...
        >>> cluster.stop()
        
    Or use as context manager:
        >>> with PX4GazeboCluster(num_drones=1) as cluster:
        ...     # SITL is ready
        ...     pass
    """
    
    def __init__(
        self,
        num_drones: int = 1,
        px4_dir: str = "~/PX4-Autopilot",
        model: str = "x500",
        world: str = "default",
        xrce_port: int = 8888,
        ros2_setups: Optional[List[str]] = None,
        namespace_prefix: str = "uav",
        log_callback: Optional[Callable[[str, str], None]] = None,
    ):
        """
        Initialize PX4 Gazebo cluster.
        
        Args:
            num_drones: Number of drones to spawn (1-10)
            px4_dir: Path to PX4-Autopilot directory
            model: PX4 model (x500, iris, etc.)
            world: Gazebo world name
            xrce_port: uXRCE-DDS Agent port
            ros2_setups: List of ROS2 setup.bash files to source
            namespace_prefix: Prefix for drone namespaces (e.g., "uav" → "uav_1", "uav_2")
            log_callback: Optional callback for log messages: callback(source, message)
                         source can be "xrce_agent", "px4_sitl_0", etc.
        """
        if num_drones < 1 or num_drones > 10:
            raise InvalidParameterError("num_drones", num_drones, "valid range: 1–10")

        # Validate model/world/namespace_prefix to prevent shell injection.
        # These values end up in a shell command string (shell=True is required
        # for `source setup.bash && make` chaining on Linux).
        _SAFE_IDENT = re.compile(r"^[a-zA-Z0-9_\-]+$")
        if not _SAFE_IDENT.match(model):
            raise InvalidParameterError("model", model, "only [a-zA-Z0-9_-] allowed")
        if not _SAFE_IDENT.match(world):
            raise InvalidParameterError("world", world, "only [a-zA-Z0-9_-] allowed")
        if not _SAFE_IDENT.match(namespace_prefix):
            raise InvalidParameterError("namespace_prefix", namespace_prefix, "only [a-zA-Z0-9_-] allowed")

        self.num_drones = num_drones
        self.px4_dir = os.path.expanduser(px4_dir)
        self.model = model
        self.world = world
        self.xrce_port = xrce_port
        self.ros2_setups = ros2_setups or []
        self.namespace_prefix = namespace_prefix
        self.log_callback = log_callback
        self._processes = []
        self._running = False
        self._log_threads = []
        
        # Validate PX4 directory
        if not os.path.isdir(self.px4_dir):
            raise ConfigurationError(f"PX4 directory not found: {self.px4_dir}")
    
    def start(self) -> bool:
        """
        Start XRCE-DDS Agent + PX4 SITL instances.
        
        Returns:
            True if all processes started successfully
        """
        if self._running:
            logger.warning("Cluster already running")
            return False
        
        try:
            # 1. Start XRCE-DDS Agent
            logger.info(f"Starting Micro XRCE-DDS Agent on port {self.xrce_port}...")
            
            # Check if agent is already running
            if self._is_port_in_use(self.xrce_port):
                logger.warning(f"Port {self.xrce_port} already in use, assuming XRCE-DDS Agent is running")
            else:
                agent_proc = subprocess.Popen(
                    ["MicroXRCEAgent", "udp4", "-p", str(self.xrce_port)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                )
                self._processes.append(("xrce_agent", agent_proc))
                
                # Start log streaming threads if callback provided
                if self.log_callback:
                    stdout_thread = threading.Thread(
                        target=self._stream_output,
                        args=(agent_proc, "xrce_agent", "stdout"),
                        daemon=True
                    )
                    stderr_thread = threading.Thread(
                        target=self._stream_output,
                        args=(agent_proc, "xrce_agent", "stderr"),
                        daemon=True
                    )
                    stdout_thread.start()
                    stderr_thread.start()
                    self._log_threads.extend([stdout_thread, stderr_thread])
                
                time.sleep(2)
                
                # Check if agent started
                if agent_proc.poll() is not None:
                    logger.error("XRCE-DDS Agent failed to start")
                    return False
                
                logger.info("✓ XRCE-DDS Agent running")
            
            # 2. Start PX4 SITL instances
            for i in range(self.num_drones):
                instance_id = i
                namespace = f"{self.namespace_prefix}_{i+1}"
                
                logger.info(f"Starting PX4 SITL instance {instance_id} (namespace: {namespace})...")
                
                # Prepare environment
                env = os.environ.copy()
                env["PX4_SIM_MODEL"] = self.model
                env["PX4_GZ_WORLD"] = self.world
                env["PX4_UXRCE_DDS_NS"] = namespace
                
                # Build command with ROS2 sourcing
                existing_setups = [setup for setup in self.ros2_setups if setup and os.path.isfile(setup)]
                if existing_setups and sys.platform != "win32":
                    # Linux/Mac: source ROS2 setups in the same shell.
                    # shell=True is required because `source` is a shell built-in.
                    # Setup file paths are quoted with shlex to prevent injection.
                    source_cmds = " && ".join(
                        [f"source {shlex.quote(s)}" for s in existing_setups]
                    )
                    # model is already validated to [a-zA-Z0-9_-] in __init__
                    cmd = (
                        f"{source_cmds} && "
                        f"cd {shlex.quote(self.px4_dir)} && "
                        f"make px4_sitl gz_{self.model}"
                    )

                    sitl_proc = subprocess.Popen(
                        cmd,
                        shell=True,
                        executable="/bin/bash",
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                else:
                    # Windows or no ROS2 setups: just run make directly
                    sitl_proc = subprocess.Popen(
                        ["make", "px4_sitl", f"gz_{self.model}"],
                        cwd=self.px4_dir,
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                    )
                
                self._processes.append((f"px4_sitl_{namespace}", sitl_proc))
                
                # Start log streaming threads if callback provided
                if self.log_callback:
                    stdout_thread = threading.Thread(
                        target=self._stream_output,
                        args=(sitl_proc, f"px4_sitl_{namespace}", "stdout"),
                        daemon=True
                    )
                    stderr_thread = threading.Thread(
                        target=self._stream_output,
                        args=(sitl_proc, f"px4_sitl_{namespace}", "stderr"),
                        daemon=True
                    )
                    stdout_thread.start()
                    stderr_thread.start()
                    self._log_threads.extend([stdout_thread, stderr_thread])
                
                # Wait for SITL to initialize
                wait_time = 10 if i == 0 else 5  # First drone takes longer (Gazebo startup)
                logger.info(f"  Waiting {wait_time}s for {namespace} to initialize...")
                time.sleep(wait_time)
                
                # Check if SITL started
                if sitl_proc.poll() is not None:
                    logger.error(f"PX4 SITL {namespace} failed to start")
                    self.stop()
                    return False
                
                logger.info(f"✓ {namespace} running")
            
            logger.info(f"All {self.num_drones} drones started successfully")
            logger.info("Waiting for uXRCE-DDS connections...")
            time.sleep(3)
            
            self._running = True
            return True
            
        except FileNotFoundError as e:
            logger.error(f"Command not found: {e}")
            logger.error("Make sure MicroXRCEAgent is installed: pip install micro-xrce-dds-agent")
            self.stop()
            return False
        except Exception as e:
            logger.error(f"Failed to start cluster: {e}")
            self.stop()
            return False
    
    def _stream_output(self, proc: subprocess.Popen, source: str, stream_name: str):
        """
        Stream process output to log callback in a background thread.
        
        Args:
            proc: Process to stream from
            source: Source identifier (e.g., "xrce_agent", "px4_sitl_0")
            stream_name: "stdout" or "stderr"
        """
        stream = proc.stdout if stream_name == "stdout" else proc.stderr
        if stream is None:
            return
        
        try:
            for line in iter(stream.readline, b''):
                if not line:
                    break
                
                text = line.decode('utf-8', errors='replace').rstrip()
                if text and self.log_callback:
                    self.log_callback(source, text)
                    
        except Exception as e:
            if self.log_callback:
                self.log_callback(source, f"[Log stream error: {e}]")
    
    def stop(self):
        """Stop all processes gracefully."""
        if not self._processes:
            return
        
        logger.info("Stopping PX4 Gazebo cluster...")
        
        for name, proc in reversed(self._processes):
            try:
                logger.info(f"  Stopping {name}...")
                
                if sys.platform == "win32":
                    # Windows: send CTRL_BREAK_EVENT
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    # Linux/Mac: send SIGTERM
                    proc.terminate()
                
                # Wait for graceful shutdown
                try:
                    proc.wait(timeout=5)
                    logger.info(f"  ✓ {name} stopped")
                except subprocess.TimeoutExpired:
                    logger.warning(f"  {name} did not stop gracefully, killing...")
                    proc.kill()
                    proc.wait()
                    
            except Exception as e:
                logger.error(f"  Error stopping {name}: {e}")
        
        self._processes.clear()
        self._running = False
        logger.info("Cluster stopped")
    
    def is_running(self) -> bool:
        """Check if cluster is running."""
        return self._running and all(proc.poll() is None for _, proc in self._processes)
    
    def get_namespaces(self) -> List[str]:
        """Get list of drone namespaces."""
        return [f"{self.namespace_prefix}_{i+1}" for i in range(self.num_drones)]
    
    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is already in use."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return False
            except OSError:
                return True
    
    def __enter__(self):
        """Context manager entry."""
        if not self.start():
            raise SimulationError("Failed to start PX4 Gazebo cluster")
        return self
    
    def __exit__(self, *args):
        """Context manager exit."""
        self.stop()
    
    def __del__(self):
        """Cleanup on deletion."""
        if hasattr(self, '_processes'):
            self.stop()

