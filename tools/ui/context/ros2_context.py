"""
ROS2Context — QML bridge for PX4ROS2Bridge (uXRCE-DDS).

Exposed to QML as context property 'ros2'.

Features:
  - Toggle ROS2 bridge on/off per drone (not parallel to MAVLink)
  - Configure uXRCE-DDS namespace
  - Stream native PX4 uORB topics (VehicleOdometry, VehicleStatus, BatteryStatus)
  - Offboard-mode via TrajectorySetpoint (position/velocity)
  - ROS2 node status display

QML Signals:
  - bridgeStatusChanged(droneId, active)
  - telemetryReceived(droneId, snapshot)
  - ros2LogMessage(level, text)
  - nodeStatusChanged(status)        -- "ok" | "no_ros2" | "no_px4_msgs" | "error"

QML Slots:
  - startBridge(droneId, namespace)
  - stopBridge(droneId)
  - setOffboardPosition(droneId, north, east, down, yaw)
  - setOffboardVelocity(droneId, vn, ve, vd, yawRate)
  - stopOffboard(droneId)
  - armBridge(droneId)
  - disarmBridge(droneId)
  - takeoffBridge(droneId, altitude)
  - landBridge(droneId)
  - rtlBridge(droneId)
  - activateOffboardMode(droneId)
  - getBridgeTopics(droneId)         -> list of active topic names
"""
import threading
import importlib.util
import math
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal, Slot, QTimer

# ── Detect ROS2 availability WITHOUT importing rclpy ──────────────────
# Importing rclpy is expensive (1-3s on cold start). We only check if
# it CAN be imported via importlib.util.find_spec, then defer the real
# import to first bridge start.
def _has_import_spec(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


_ROS2_AVAILABLE   = _has_import_spec("rclpy")
_BRIDGE_AVAILABLE = _has_import_spec("skymeshx.ros.px4_bridge")
_PX4Bridge: Optional[type] = None  # populated on first start_bridge


_PX4_REQUIRED_TOPICS = [
    "vehicle_status",
    "vehicle_global_position",
    "vehicle_local_position",
    "vehicle_odometry",
    "vehicle_attitude",
    "vehicle_control_mode",
    "battery_status",
    "failsafe_flags",
    "mission_result",
]


_LAUNCH_PROFILES = [
    {
        "id": "gz_x500",
        "label": "PX4 x500",
        "model": "gz_x500",
        "worldProfile": "empty_default",
        "world": "default",
        "cameraEnabled": False,
        "gimbalEnabled": False,
    },
    {
        "id": "gz_x500_mono_cam",
        "label": "PX4 x500 Mono Camera",
        "model": "gz_x500_mono_cam",
        "worldProfile": "aruco_precision_landing",
        "world": "aruco",
        "cameraEnabled": True,
        "gimbalEnabled": False,
    },
    {
        "id": "gz_x500_gimbal",
        "label": "PX4 x500 Gimbal",
        "model": "gz_x500_gimbal",
        "worldProfile": "empty_default",
        "world": "default",
        "cameraEnabled": True,
        "gimbalEnabled": True,
    },
    {
        "id": "gz_x500_lidar_down",
        "label": "PX4 x500 Lidar Down",
        "model": "gz_x500_lidar_down",
        "worldProfile": "ridge_terrain",
        "world": "ridge",
        "cameraEnabled": False,
        "gimbalEnabled": False,
    },
    {
        "id": "gz_standard_vtol",
        "label": "PX4 Standard VTOL",
        "model": "gz_standard_vtol",
        "worldProfile": "moving_platform",
        "world": "moving_platform",
        "cameraEnabled": False,
        "gimbalEnabled": False,
    },
    {
        "id": "gz_plane",
        "label": "PX4 Plane",
        "model": "gz_plane",
        "worldProfile": "empty_default",
        "world": "default",
        "cameraEnabled": False,
        "gimbalEnabled": False,
    },
    {
        "id": "sih_quadx",
        "label": "PX4 SIH Quadcopter",
        "model": "sih_quadx",
        "worldProfile": "sih_headless",
        "world": "",
        "cameraEnabled": False,
        "gimbalEnabled": False,
    },
]


_WORLD_PROFILES = {
    "empty_default": {"world": "default", "model": "gz_x500"},
    "aruco_precision_landing": {"world": "aruco", "model": "gz_x500_mono_cam"},
    "baylands_water": {"world": "bayland", "model": "gz_x500"},
    "ridge_terrain": {"world": "ridge", "model": "gz_x500_lidar_down"},
    "walls_collision": {"world": "walls", "model": "gz_x500"},
    "windy_disturbance": {"world": "windy", "model": "gz_x500"},
    "moving_platform": {"world": "moving_platform", "model": "gz_standard_vtol"},
    "rover_grid": {"world": "rover", "model": "gz_rover"},
}


_BAG_PRESETS = {
    "minimal_mission": [
        "vehicle_status",
        "vehicle_global_position",
        "vehicle_local_position",
        "vehicle_odometry",
        "vehicle_attitude",
        "vehicle_control_mode",
        "mission_result",
        "failsafe_flags",
    ],
    "full_px4_out": ["*"],
    "camera_gimbal": [
        "gimbal_device_attitude_status",
        "gimbal_device_set_attitude",
        "camera/image_raw",
    ],
    "swarm_multi_vehicle": [
        "vehicle_status",
        "vehicle_odometry",
        "trajectory_setpoint",
    ],
}


class _TerminalProcessCluster:
    """Small process handle used when SITL is launched in a visible terminal."""

    def __init__(self, proc: subprocess.Popen):
        self._proc = proc
        self._processes = [("sitl_terminal", proc)]

    def is_running(self) -> bool:
        return self._proc.poll() is None

    def stop(self) -> None:
        if self._proc.poll() is not None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()


def _refresh_ros2_availability() -> None:
    """Refresh import probes after ROS2 setup files changed the environment."""
    global _ROS2_AVAILABLE, _BRIDGE_AVAILABLE
    importlib.invalidate_caches()
    _ROS2_AVAILABLE = _has_import_spec("rclpy")
    _BRIDGE_AVAILABLE = _has_import_spec("skymeshx.ros.px4_bridge")


def _ensure_bridge_loaded() -> bool:
    """Import PX4ROS2Bridge on first use. Returns True if available."""
    global _PX4Bridge
    if _PX4Bridge is not None:
        return True
    _refresh_ros2_availability()
    if not (_ROS2_AVAILABLE and _BRIDGE_AVAILABLE):
        return False
    try:
        from skymeshx.ros.px4_bridge import PX4ROS2Bridge as _B
        _PX4Bridge = _B
        return True
    except ImportError:
        return False


class ROS2Context(QObject):
    """QML-callable wrapper around PX4ROS2Bridge."""

    # ── Signals ───────────────────────────────────────────────────────────
    bridgeStatusChanged = Signal(str, bool,   arguments=["droneId", "active"])
    telemetryReceived   = Signal(str, "QVariant", arguments=["droneId", "snapshot"])
    ros2LogMessage      = Signal(str, str,    arguments=["level", "text"])
    nodeStatusChanged   = Signal(str,          arguments=["status"])
    missionStatusChanged = Signal(str, "QVariant", arguments=["droneId", "status"])
    connectionStatusChanged = Signal(str, str, arguments=["droneId", "status"])
    sitlStatusChanged = Signal("QVariant", arguments=["status"])
    topicMessage = Signal(str, str, float, arguments=["topic", "jsonData", "timestamp"])
    bagRecordStarted = Signal(str, arguments=["path"])
    bagRecordStopped = Signal(str, float, arguments=["path", "sizeMb"])
    bagRecordError = Signal(str, arguments=["message"])
    
    # Command-sent signals — emitted immediately after command dispatch
    # (NOT after vehicle ACK; use bridge telemetry state for that).
    armCommandSent = Signal(str, arguments=["droneId"])
    disarmCommandSent = Signal(str, arguments=["droneId"])
    takeoffCommandSent = Signal(str, float, arguments=["droneId", "altitude"])
    landCommandSent = Signal(str, arguments=["droneId"])
    rtlCommandSent = Signal(str, arguments=["droneId"])

    # Aliases kept for backward compatibility — will be removed in v0.5
    armConfirmed = armCommandSent
    disarmConfirmed = disarmCommandSent
    takeoffConfirmed = takeoffCommandSent
    landConfirmed = landCommandSent
    rtlConfirmed = rtlCommandSent

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridges: Dict[str, object] = {}
        self._namespaces: Dict[str, str] = {}
        self._active_drone_ids: set = set()
        self._bridge_terminal_logs: Dict[str, Path] = {}

        # Poll timer — forward bridge telemetry to QML at 5 Hz.
        # Started lazily on first bridge start, stopped when last bridge stops.
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._poll)

        # SITL cluster management
        self._sitl_cluster = None
        # Terminal window: spawn SITL/Bridge in a visible gnome-terminal (Linux only)
        self._use_terminal: bool = True
        self._sitl_config = {
            'px4_dir': '/home/iruz/PX4-Autopilot',
            'model': 'x500',
            'namespace': 'uav_1',
            'ros2_setups': [
                '/opt/ros/humble/setup.bash',
                '/home/iruz/ws_sensor_combined/install/setup.bash'
            ]
        }
        self._sitl_profiles: list[dict] = []
        self._sitl_started_at: float = 0.0
        self._sitl_status: dict = self._default_sitl_status()

        # Topic discovery/health state. This is intentionally lightweight so
        # the normal test suite stays hardware-free.
        self._discovered_topics: dict[str, list[str]] = {}
        self._topic_health: dict[str, dict] = {}
        self._topic_subscriptions: dict[str, str] = {}
        self._bag_recorder = None
        self._mission_waypoints: dict[str, list[dict]] = {}
        self._last_wp_trace: dict[str, tuple[int, float]] = {}

        # Emit initial node status
        self._emit_node_status()

    def _gate_poll_timer(self) -> None:
        if self._active_drone_ids and not self._poll_timer.isActive():
            self._poll_timer.start()
        elif not self._active_drone_ids and self._poll_timer.isActive():
            self._poll_timer.stop()

    def _run_async(self, target) -> None:
        threading.Thread(target=target, daemon=True).start()

    def _ros2_setup_sources(self) -> list[str]:
        return self._clean_ros2_setup_sources(self._sitl_config.get("ros2_setups", []))

    def _clean_ros2_setup_sources(self, sources: Any) -> list[str]:
        if isinstance(sources, str):
            raw_items = sources.replace(";", "\n").splitlines()
        elif isinstance(sources, (list, tuple)):
            raw_items = sources
        else:
            raw_items = []

        cleaned: list[str] = []
        for item in raw_items:
            path = str(item or "").strip()
            if not path:
                continue
            if path.startswith("source "):
                path = path[len("source "):].strip()
            elif path.startswith(". "):
                path = path[2:].strip()
            path = path.strip("\"'")
            if path and path not in cleaned:
                cleaned.append(path)
        return cleaned

    def _source_command_lines(self, sources: Any) -> list[str]:
        return [f"source {shlex.quote(path)}" for path in self._clean_ros2_setup_sources(sources)]

    def _apply_ros2_setup_environment(self, sources: Any, purpose: str) -> bool:
        if sys.platform == "win32":
            return False

        configured = self._clean_ros2_setup_sources(sources)
        if not configured:
            return False

        existing = [
            os.path.expanduser(path)
            for path in configured
            if os.path.isfile(os.path.expanduser(path))
        ]
        if not existing:
            self.ros2LogMessage.emit("WARN", f"[ROS2] No existing setup.bash paths for {purpose}")
            return False

        source_cmds = " && ".join(f"source {shlex.quote(path)}" for path in existing)
        cmd = f"{{ {source_cmds}; }} >/dev/null 2>&1 && env -0"
        try:
            result = subprocess.run(
                ["/bin/bash", "-lc", cmd],
                check=False,
                capture_output=True,
                timeout=15,
            )
        except Exception as exc:
            self.ros2LogMessage.emit("WARN", f"[ROS2] Could not source setup files for {purpose}: {exc}")
            return False

        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            self.ros2LogMessage.emit("WARN", f"[ROS2] setup.bash source failed for {purpose}: {err}")
            return False

        for entry in result.stdout.split(b"\0"):
            if not entry or b"=" not in entry:
                continue
            key, value = entry.split(b"=", 1)
            os.environ[key.decode("utf-8", errors="replace")] = value.decode("utf-8", errors="replace")
        _refresh_ros2_availability()
        self.ros2LogMessage.emit("INFO", f"[ROS2] Sourced {len(existing)} setup file(s) for {purpose}")
        return True

    def _terminal_launcher(self) -> tuple[str, list[str]] | None:
        if not self._use_terminal:
            return None
        if sys.platform == "win32":
            wsl_path = shutil.which("wsl.exe")
            if not wsl_path:
                return None
            wt_path = shutil.which("wt.exe")
            if wt_path:
                return (
                    "Windows Terminal (WSL)",
                    [wt_path, "new-tab", "--title", "{title}", wsl_path, "bash", "{script_wsl}"],
                )
            cmd_path = shutil.which("cmd.exe")
            if cmd_path:
                return (
                    "cmd (WSL)",
                    [cmd_path, "/c", "start", "{title}", wsl_path, "bash", "{script_wsl}"],
                )
            return None
        candidates = [
            ("gnome-terminal", ["gnome-terminal", "--title", "{title}", "--", "bash", "{script}"]),
            ("konsole", ["konsole", "--hold", "-p", "tabtitle={title}", "-e", "bash", "{script}"]),
            ("xfce4-terminal", ["xfce4-terminal", "--title", "{title}", "--hold", "--command", "bash {script_q}"]),
            ("xterm", ["xterm", "-T", "{title}", "-hold", "-e", "bash", "{script}"]),
        ]
        for binary, template in candidates:
            path = shutil.which(binary)
            if path:
                resolved = [path if part == binary else part for part in template]
                return binary, resolved
        return None

    def _wsl_path(self, path: Path) -> str:
        resolved = str(path.resolve())
        drive, tail = os.path.splitdrive(resolved)
        if drive:
            letter = drive[0].lower()
            tail = tail.replace("\\", "/")
            return f"/mnt/{letter}{tail}"
        return resolved.replace("\\", "/")

    def _launch_visible_terminal(self, title: str, script_lines: list[str]) -> subprocess.Popen | None:
        launcher = self._terminal_launcher()
        if not launcher:
            self.ros2LogMessage.emit("WARN", f"[ROS2] No visible terminal launcher found for '{title}'")
            return None

        terminal_name, template = launcher
        script_dir = Path(tempfile.gettempdir()) / "skymeshx_terminals"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"{title.lower().replace(' ', '_').replace('/', '_')}_{int(time.time())}.sh"
        script = "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -u",
                f"echo '[SkyMeshX] {title}'",
                *script_lines,
                "status=$?",
                "echo",
                "echo \"[SkyMeshX] Session exited with status ${status}\"",
                "exec bash",
            ]
        )
        script_path.write_text(script + "\n", encoding="utf-8")
        script_path.chmod(0o755)

        replacements = {
            "{title}": title,
            "{script}": str(script_path),
            "{script_q}": shlex.quote(str(script_path)),
            "{script_wsl}": self._wsl_path(script_path),
        }
        cmd = [
            replacements[part]
            if part in replacements
            else part.format(
                title=title,
                script=str(script_path),
                script_q=shlex.quote(str(script_path)),
                script_wsl=self._wsl_path(script_path),
            )
            for part in template
        ]
        try:
            proc = subprocess.Popen(cmd)
            self.ros2LogMessage.emit("INFO", f"[ROS2] Opened {terminal_name}: {title}")
            return proc
        except Exception as exc:
            self.ros2LogMessage.emit("WARN", f"[ROS2] Could not open terminal '{terminal_name}': {exc}")
            return None

    def _launch_bridge_terminal(self, drone_id: str, namespace: str) -> None:
        sources = self._ros2_setup_sources()
        log_dir = Path(tempfile.gettempdir()) / "skymeshx_terminals"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"bridge_{drone_id}.log"
        log_path.write_text(f"[SkyMeshX] PX4 bridge terminal log for {drone_id}\n", encoding="utf-8")
        self._bridge_terminal_logs[drone_id] = log_path
        lines = [
            *self._source_command_lines(sources),
            f"cd {shlex.quote(str(Path.cwd()))}",
            f"echo '[SkyMeshX] PX4 bridge diagnostics for {drone_id} namespace {namespace or '/'}'",
            "echo '[SkyMeshX] Bridge runs inside the UI process; this shell uses the same ROS2 setup sources.'",
            "echo '[SkyMeshX] ROS_DOMAIN_ID='${ROS_DOMAIN_ID:-unset}",
            "ros2 topic list 2>/dev/null | grep -E '(/fmu/|/px4_|/uav_)' || true",
            f"echo '[SkyMeshX] Tailing bridge log: {log_path}'",
            f"tail -n +1 -F {shlex.quote(str(log_path))}",
        ]
        self._launch_visible_terminal(f"SkyMeshX PX4 Bridge {drone_id}", lines)

    def _write_bridge_terminal_log(self, drone_id: str, message: str) -> None:
        log_path = self._bridge_terminal_logs.get(drone_id)
        if not log_path:
            return
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{time.strftime('%H:%M:%S')}  {message}\n")
        except Exception:
            pass

    def _start_sitl_in_terminal(self, first: dict) -> bool:
        cluster_model = first.get("clusterModel") or self._normalize_model_for_cluster(first.get("model", "gz_x500"))
        namespace = str(first.get("namespace") or self._sitl_config.get("namespace", "px4_1")).strip("/") or "px4_1"
        px4_dir = str(first.get("px4Dir") or self._sitl_config.get("px4_dir", ""))
        xrce_port = int(first.get("xrcePort", 8888))
        world = str(first.get("world", "default"))
        world_env = dict(first.get("worldEnv") or {})

        lines = [
            *self._source_command_lines(first.get("ros2Setups", self._ros2_setup_sources())),
            f"cd {shlex.quote(os.path.expanduser(px4_dir))}",
            f"export PX4_SIM_MODEL={shlex.quote(str(cluster_model))}",
            f"export PX4_GZ_WORLD={shlex.quote(world)}",
            f"export PX4_UXRCE_DDS_NS={shlex.quote(namespace)}",
        ]
        for key, value in sorted(world_env.items()):
            lines.append(f"export {key}={shlex.quote(str(value))}")
        lines.extend(
            [
                f"echo '[SkyMeshX] Starting MicroXRCEAgent udp4 -p {xrce_port}'",
                f"MicroXRCEAgent udp4 -p {xrce_port} &",
                "XRCE_PID=$!",
                "PX4_PID=",
                "trap 'test -n \"${PX4_PID}\" && kill ${PX4_PID} 2>/dev/null || true; kill ${XRCE_PID} 2>/dev/null || true' EXIT INT TERM",
                "sleep 1",
                f"echo '[SkyMeshX] Starting PX4 SITL: make px4_sitl {shlex.quote('gz_' + str(cluster_model))}'",
                f"make px4_sitl {shlex.quote('gz_' + str(cluster_model))} &",
                "PX4_PID=$!",
                "wait ${PX4_PID}",
            ]
        )
        proc = self._launch_visible_terminal("SkyMeshX PX4 SITL", lines)
        if proc is None:
            return False
        self._sitl_cluster = _TerminalProcessCluster(proc)
        self._sitl_started_at = time.monotonic()
        self._sitl_status.update(
            {
                "running": True,
                "status": "running",
                "gazebo_running": not bool(first.get("sih", False)),
                "pid": self._extract_cluster_pid(),
                "uptime_s": 0.0,
            }
        )
        self.ros2LogMessage.emit("INFO", "[SITL] Visible terminal session started")
        self._trace_event("sitl_launch", {"status": "running", "terminal": True, "profiles": self._sitl_profiles})
        self._emit_sitl_status()
        return True

    def _trace_event(self, event_type: str, data: dict) -> None:
        try:
            from skymeshx.core.trace_logger import TraceLogger

            TraceLogger.get().log_ui_event(event_type, data)
        except Exception:
            pass

    def _trace_mission_event(self, event_type: str, data: dict) -> None:
        try:
            from skymeshx.core.trace_logger import TraceLogger

            TraceLogger.get().log_mission_event(event_type, data)
        except Exception:
            pass

    def _trace_wp_tracking(self, drone_id: str, status: dict) -> None:
        waypoints = self._mission_waypoints.get(drone_id) or self.getMissionWaypoints(drone_id)
        if not waypoints:
            return

        seq = int(status.get("current_seq", status.get("seq_current", 0)) or 0)
        wp_index = max(0, min(seq, len(waypoints) - 1))
        now = time.monotonic()
        last_seq, last_at = self._last_wp_trace.get(drone_id, (-1, -9999.0))
        if last_seq == wp_index and now - last_at < 1.0:
            return

        bridge = self._bridges.get(drone_id)
        telemetry = dict(getattr(bridge, "telemetry", {}) or {}) if bridge is not None else {}
        drone_lat = float(telemetry.get("lat", status.get("lat", 0.0)) or 0.0)
        drone_lon = float(telemetry.get("lon", status.get("lon", 0.0)) or 0.0)
        target = waypoints[wp_index]
        target_lat = float(target.get("lat", 0.0) or 0.0)
        target_lon = float(target.get("lon", 0.0) or 0.0)
        acceptance_radius = target.get("accept_radius", target.get("acceptance_radius", None))
        distance_m = self._distance_m(drone_lat, drone_lon, target_lat, target_lon)

        try:
            from skymeshx.core.trace_logger import TraceLogger

            TraceLogger.get().log_wp_tracking(
                drone_id,
                wp_index,
                drone_lat,
                drone_lon,
                target_lat,
                target_lon,
                distance_m,
                "global_relative_alt",
                float(acceptance_radius) if acceptance_radius is not None else None,
            )
            self._last_wp_trace[drone_id] = (wp_index, now)
        except Exception:
            pass

    def _distance_m(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_m = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lam = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2.0) ** 2
        return 2.0 * radius_m * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))

    def _trace_topic_health(self, topic: str, health: dict) -> None:
        try:
            from skymeshx.core.trace_logger import TraceLogger

            TraceLogger.get().log_ros2_health(
                topic,
                float(health.get("estimatedHz", 0.0)),
                float(health.get("lastMessageAgeSec", 0.0)),
                str(health.get("qos", "")),
            )
        except Exception:
            pass

    def _default_sitl_status(self) -> dict:
        return {
            "running": False,
            "model": "",
            "world": "",
            "namespace": "",
            "pid": 0,
            "uptime_s": 0.0,
            "gazebo_running": False,
            "vehicle_count": 0,
            "vehicles": [],
            "status": "stopped",
        }

    def _emit_sitl_status(self) -> None:
        self.sitlStatusChanged.emit(self.getSitlStatus())

    def _normalized_namespace(self, namespace_or_drone: str) -> str:
        raw = str(namespace_or_drone or "").strip()
        ns = self._namespaces.get(raw, raw)
        return ns.strip("/")

    def _topic_prefix(self, namespace_or_drone: str) -> str:
        ns = self._normalized_namespace(namespace_or_drone)
        return f"/{ns}/fmu" if ns else "/fmu"

    def _px4_topic(self, namespace_or_drone: str, direction: str, name: str) -> str:
        if name.startswith("/"):
            return name
        prefix = self._topic_prefix(namespace_or_drone)
        return f"{prefix}/{direction}/{name}"

    def _default_topics_for_namespace(self, namespace_or_drone: str) -> list[str]:
        return [self._px4_topic(namespace_or_drone, "out", topic) for topic in _PX4_REQUIRED_TOPICS]

    def _normalize_model_for_cluster(self, model: str) -> str:
        normalized = str(model or "gz_x500").strip()
        return normalized[3:] if normalized.startswith("gz_") else normalized

    def _namespace_prefix(self, namespace: str) -> str:
        ns = str(namespace or "px4_1").strip().strip("/")
        if "_" in ns:
            return ns.rsplit("_", 1)[0]
        digits = len(ns) - len(ns.rstrip("0123456789"))
        return ns[:-digits] if digits else ns

    def _normalize_sitl_profile(self, profile: Any = None, index: int = 0, base_port: int = 5762) -> dict:
        data = dict(profile) if isinstance(profile, dict) else {}
        model = str(data.get("model") or self._sitl_config.get("model") or "gz_x500")
        if model == "x500":
            model = "gz_x500"
        world_profile = str(data.get("worldProfile") or data.get("world_profile") or "empty_default")
        world_defaults = _WORLD_PROFILES.get(world_profile, {})
        world = str(data.get("world") or world_defaults.get("world") or "default")
        namespace = str(data.get("namespace") or self._sitl_config.get("namespace") or f"px4_{index + 1}")
        namespace = namespace.strip("/") or f"px4_{index + 1}"
        if index > 0 and namespace.endswith("_1"):
            namespace = f"{self._namespace_prefix(namespace)}_{index + 1}"

        video_port = int(data.get("videoPort", data.get("video_port", 5600 + index)))
        mavlink_port = int(data.get("mavlinkPort", data.get("mavlink_port", base_port + index)))
        xrce_port = int(data.get("xrcePort", data.get("xrce_port", 8888 + index)))
        model_pose = str(data.get("modelPose") or data.get("pose") or "0,0,0,0,0,0")
        world_env = dict(data.get("worldEnv") or data.get("world_env") or {})
        if world:
            world_env.setdefault("PX4_GZ_WORLD", world)
        if model_pose:
            world_env.setdefault("PX4_GZ_MODEL_POSE", model_pose)
        if "ros2Setups" in data:
            ros2_setups = data.get("ros2Setups")
        elif "ros2_setups" in data:
            ros2_setups = data.get("ros2_setups")
        else:
            ros2_setups = self._sitl_config.get("ros2_setups", [])

        normalized = {
            "autopilot": "px4",
            "controlPath": "ros2_uxrce",
            "model": model,
            "clusterModel": self._normalize_model_for_cluster(model),
            "worldProfile": world_profile,
            "world": world,
            "namespace": namespace,
            "mavlinkPort": mavlink_port,
            "mavlinkEndpoint": f"tcp:127.0.0.1:{mavlink_port}",
            "xrcePort": xrce_port,
            "videoPort": video_port,
            "modelPose": model_pose,
            "worldEnv": world_env,
            "cameraEnabled": bool(data.get("cameraEnabled", data.get("camera_enabled", "camera" in model))),
            "gimbalEnabled": bool(data.get("gimbalEnabled", data.get("gimbal_enabled", "gimbal" in model))),
            "px4Dir": str(data.get("px4Dir") or data.get("px4_dir") or self._sitl_config.get("px4_dir", "")),
            "ros2Setups": self._clean_ros2_setup_sources(ros2_setups),
        }
        return normalized

    def _build_multi_profiles(self, count_or_profiles: Any, base_port: int = 5762) -> list[dict]:
        if isinstance(count_or_profiles, list):
            return [
                self._normalize_sitl_profile(profile, index=i, base_port=base_port)
                for i, profile in enumerate(count_or_profiles)
            ]
        count = int(count_or_profiles or 1)
        count = max(1, min(count, 5))
        base = self._normalize_sitl_profile({}, index=0, base_port=base_port)
        prefix = "px4" if base.get("namespace") in {"", "uav_1"} else self._namespace_prefix(base["namespace"])
        return [
            self._normalize_sitl_profile(
                {
                    **base,
                    "namespace": f"{prefix}_{i + 1}",
                    "videoPort": 5600 + i,
                    "mavlinkPort": base_port + i,
                    "xrcePort": 8888 + i,
                },
                index=i,
                base_port=base_port,
            )
            for i in range(count)
        ]

    def _extract_cluster_pid(self) -> int:
        cluster = self._sitl_cluster
        processes = getattr(cluster, "_processes", []) if cluster is not None else []
        for _, proc in processes:
            pid = int(getattr(proc, "pid", 0) or 0)
            if pid:
                return pid
        return int(getattr(cluster, "pid", 0) or 0) if cluster is not None else 0

    # ── Status ────────────────────────────────────────────────────────────

    def _emit_node_status(self):
        _refresh_ros2_availability()
        if not _ROS2_AVAILABLE:
            self.nodeStatusChanged.emit("no_ros2")
        elif not _BRIDGE_AVAILABLE:
            self.nodeStatusChanged.emit("no_px4_msgs")
        else:
            self.nodeStatusChanged.emit("ok")

    @Slot(result=str)
    def nodeStatus(self) -> str:
        _refresh_ros2_availability()
        if not _ROS2_AVAILABLE:
            # On Linux with ROS2, rclpy is only importable after setup.bash is
            # sourced. Try sourcing once per poll cycle so the status dot turns
            # green automatically when the user has configured setup files.
            sources = self._ros2_setup_sources()
            if sources:
                self._apply_ros2_setup_environment(sources, "status_check")
                _refresh_ros2_availability()
            if not _ROS2_AVAILABLE:
                return "no_ros2"
        if not _BRIDGE_AVAILABLE:
            return "no_px4_msgs"
        return "ok"

    @Slot(str, result=bool)
    def isBridgeActive(self, drone_id: str) -> bool:
        return drone_id in self._active_drone_ids

    @Slot(result="QVariant")
    @Slot(str, result=str)
    def getConnectionStatus(self, drone_id: str) -> str:
        """Get connection status for a drone."""
        bridge = self._bridges.get(drone_id)
        if not bridge:
            return "disconnected"
        try:
            status = bridge.get_connection_status()
            return status.value if hasattr(status, 'value') else str(status)
        except Exception:
            return "unknown"
    
    @Slot(str, result="QVariant")
    def getReconnectInfo(self, drone_id: str) -> dict:
        """Get reconnect information for a drone."""
        bridge = self._bridges.get(drone_id)
        if not bridge:
            return {}
        try:
            return bridge.get_reconnect_info()
        except Exception:
            return {}
    def activeBridges(self) -> list:
        return list(self._active_drone_ids)

    # ── Bridge lifecycle ──────────────────────────────────────────────────

    @Slot(str, str)
    def startBridge(self, drone_id: str, namespace: str) -> None:
        """Start uXRCE-DDS bridge for a drone. Stops MAVLink if it was active."""
        sources = self._ros2_setup_sources()
        self._apply_ros2_setup_environment(sources, "bridge")
        _refresh_ros2_availability()

        if drone_id in self._active_drone_ids:
            self.ros2LogMessage.emit("WARN", f"[ROS2] Bridge for {drone_id} already running")
            return

        ns = namespace.strip()
        self._namespaces[drone_id] = ns
        self._launch_bridge_terminal(drone_id, ns)
        self._write_bridge_terminal_log(drone_id, f"Starting bridge namespace='{ns or '/'}'")

        if not _ROS2_AVAILABLE:
            self.ros2LogMessage.emit("ERROR", "[ROS2] rclpy not found — install ROS2 Humble+")
            return
        if not _BRIDGE_AVAILABLE:
            self.ros2LogMessage.emit("ERROR", "[ROS2] px4_msgs not found — build px4_msgs in your ROS2 workspace")
            return
        if not _ensure_bridge_loaded():
            self.ros2LogMessage.emit("ERROR", "[ROS2] PX4 bridge module unavailable")
            self._write_bridge_terminal_log(drone_id, "ERROR PX4 bridge module unavailable")
            return

        def _start():
            try:
                bridge = _PX4Bridge(namespace=ns, publish_hz=10.0, auto_reconnect=True)
                bridge.on("telemetry", lambda data: self._on_bridge_telemetry(drone_id, data))
                bridge.on("connection_status", lambda status: self._on_connection_status(drone_id, status))
                bridge.start()
                self._bridges[drone_id] = bridge
                self._active_drone_ids.add(drone_id)
                self._gate_poll_timer()
                self.bridgeStatusChanged.emit(drone_id, True)
                self.ros2LogMessage.emit("INFO", f"[ROS2] Bridge started for {drone_id} ns='{ns or '/'}'")
                self.ros2LogMessage.emit("INFO", f"[ROS2] Listening on {ns or ''}/fmu/out/*")
                domain = os.environ.get("ROS_DOMAIN_ID", "0 (default)")
                self.ros2LogMessage.emit("INFO",
                    f"[ROS2] ROS_DOMAIN_ID={domain} -- PX4 must use the same domain")
                self.ros2LogMessage.emit("INFO",
                    "[ROS2] MicroXRCEAgent udp4 -p 8888 must be running in a separate terminal")
                self._write_bridge_terminal_log(drone_id, "Bridge started")
                self._write_bridge_terminal_log(drone_id, f"Listening on {ns or ''}/fmu/out/*")
            except Exception as e:
                self.ros2LogMessage.emit("ERROR", f"[ROS2] Bridge start failed: {e}")
                self._write_bridge_terminal_log(drone_id, f"ERROR Bridge start failed: {e}")

        threading.Thread(target=_start, daemon=True).start()

    @Slot(str)
    def stopBridge(self, drone_id: str) -> None:
        bridge = self._bridges.pop(drone_id, None)
        self._active_drone_ids.discard(drone_id)
        self._gate_poll_timer()
        if bridge:
            try:
                bridge.stop()
            except Exception:
                pass
        self.bridgeStatusChanged.emit(drone_id, False)
        self.ros2LogMessage.emit("INFO", f"[ROS2] Bridge stopped for {drone_id}")
        self._write_bridge_terminal_log(drone_id, "Bridge stopped")

    # ── Offboard control ──────────────────────────────────────────────────

    @Slot(str)
    def activateOffboardMode(self, drone_id: str) -> None:
        b = self._bridges.get(drone_id)
        if b:
            b.set_offboard_mode()
            self.ros2LogMessage.emit("INFO", f"[ROS2] {drone_id} → OFFBOARD mode activated")
        else:
            self.ros2LogMessage.emit("WARN", f"[ROS2] No bridge for {drone_id}")

    @Slot(str, float, float, float, float)
    def setOffboardPosition(self, drone_id: str, north: float, east: float,
                            down: float, yaw: float) -> None:
        b = self._bridges.get(drone_id)
        if b:
            b.set_position_setpoint_ned(north, east, down, yaw)
            self.ros2LogMessage.emit("INFO",
                f"[ROS2] {drone_id} POSITION N={north:.1f} E={east:.1f} D={down:.1f} yaw={yaw:.1f}")

    @Slot(str, float, float, float, float)
    def setOffboardVelocity(self, drone_id: str, vn: float, ve: float,
                            vd: float, yaw_rate: float) -> None:
        b = self._bridges.get(drone_id)
        if b:
            b.set_velocity_setpoint_ned(vn, ve, vd, yaw_rate)
            self.ros2LogMessage.emit("INFO",
                f"[ROS2] {drone_id} VELOCITY vN={vn:.1f} vE={ve:.1f} vD={vd:.1f}")

    @Slot(str)
    def stopOffboard(self, drone_id: str) -> None:
        b = self._bridges.get(drone_id)
        if b:
            b.stop_offboard()
            self.ros2LogMessage.emit("INFO", f"[ROS2] {drone_id} offboard setpoints stopped")

    # ── Vehicle commands via bridge ───────────────────────────────────────

    @Slot(str)
    def armBridge(self, drone_id: str) -> None:
        b = self._bridges.get(drone_id)
        if b:
            b.arm()
            self.ros2LogMessage.emit("INFO", f"[ROS2] {drone_id} ARM sent via uXRCE-DDS")
            self.armCommandSent.emit(drone_id)

    @Slot(str)
    def disarmBridge(self, drone_id: str) -> None:
        b = self._bridges.get(drone_id)
        if b:
            b.disarm()
            self.ros2LogMessage.emit("INFO", f"[ROS2] {drone_id} DISARM sent via uXRCE-DDS")
            self.disarmCommandSent.emit(drone_id)

    @Slot(str, float)
    def takeoffBridge(self, drone_id: str, altitude: float) -> None:
        b = self._bridges.get(drone_id)
        if b:
            b.takeoff(altitude)
            self.ros2LogMessage.emit("INFO", f"[ROS2] {drone_id} TAKEOFF {altitude}m via uXRCE-DDS")
            self.takeoffCommandSent.emit(drone_id, altitude)

    @Slot(str)
    def landBridge(self, drone_id: str) -> None:
        b = self._bridges.get(drone_id)
        if b:
            b.land()
            self.ros2LogMessage.emit("INFO", f"[ROS2] {drone_id} LAND via uXRCE-DDS")
            self.landCommandSent.emit(drone_id)

    @Slot(str)
    def rtlBridge(self, drone_id: str) -> None:
        b = self._bridges.get(drone_id)
        if b:
            b.rtl()
            self.ros2LogMessage.emit("INFO", f"[ROS2] {drone_id} RTL via uXRCE-DDS")
            self._trace_mission_event("mission_abort", {"droneId": drone_id, "action": "rtl", "status": "sent"})
            self.rtlCommandSent.emit(drone_id)

    # ── Topic snapshot ────────────────────────────────────────────────────

    @Slot(str, result="QVariant")
    def bridgeSnapshot(self, drone_id: str) -> dict:
        b = self._bridges.get(drone_id)
        return dict(b.telemetry) if b else {}

    @Slot(str, result="QVariant")
    def getBridgeTopics(self, drone_id: str) -> list:
        ns = self._normalized_namespace(drone_id)
        prefix = f"/{ns}/fmu" if ns else "/fmu"
        return [
            f"{prefix}/out/vehicle_global_position",
            f"{prefix}/out/vehicle_local_position",
            f"{prefix}/out/vehicle_attitude",
            f"{prefix}/out/vehicle_status",
            f"{prefix}/out/battery_status",
            f"{prefix}/out/vehicle_gps_position",
            f"{prefix}/in/vehicle_command",
            f"{prefix}/in/offboard_control_mode",
            f"{prefix}/in/trajectory_setpoint",
        ]

    @Slot(str, result="QVariantList")
    def discoverTopics(self, namespace: str) -> list:
        """Discover ROS2 topics for a namespace, falling back to PX4 defaults."""
        ns = self._normalized_namespace(namespace)
        bridge = self._bridges.get(namespace) or self._bridges.get(ns)
        topics: list[str] = []

        try:
            node = getattr(bridge, "_node", None) if bridge is not None else None
            if node is not None and hasattr(node, "get_topic_names_and_types"):
                topics = [name for name, _types in node.get_topic_names_and_types()]
        except Exception as exc:
            self.ros2LogMessage.emit("WARN", f"[ROS2] Topic discovery via node failed: {exc}")

        if not topics:
            topics = self._default_topics_for_namespace(ns)
            topics.extend(
                [
                    self._px4_topic(ns, "in", "vehicle_command"),
                    self._px4_topic(ns, "in", "offboard_control_mode"),
                    self._px4_topic(ns, "in", "trajectory_setpoint"),
                ]
            )

        if ns:
            prefix = f"/{ns}/"
            topics = [topic for topic in topics if topic.startswith(prefix) or topic.startswith("/fmu/")]

        unique_topics = sorted(dict.fromkeys(topics))
        self._discovered_topics[ns or "/"] = unique_topics
        self._trace_event("topic_discovery", {"namespace": ns, "count": len(unique_topics)})
        return unique_topics

    @Slot(str, result="QVariantMap")
    def getTopicHealth(self, namespace: str) -> dict:
        """Return topic health for a namespace."""
        ns = self._normalized_namespace(namespace)
        topics = self._discovered_topics.get(ns or "/") or self.discoverTopics(ns)
        result = {}
        for topic in topics:
            result[topic] = dict(
                self._topic_health.get(
                    topic,
                    {
                        "seen": False,
                        "messageCount": 0,
                        "lastMessageAgeSec": -1.0,
                        "estimatedHz": 0.0,
                        "qos": "",
                    },
                )
            )
        return result

    @Slot(str, str, result=bool)
    def subscribeToTopic(self, topic: str, drone_id: str) -> bool:
        """Register a topic watch. Real bridge subscriptions are optional."""
        topic = str(topic or "").strip()
        drone_id = str(drone_id or "").strip()
        if not topic:
            self.ros2LogMessage.emit("WARN", "[ROS2] Empty topic subscription ignored")
            return False

        self._topic_subscriptions[topic] = drone_id
        self._topic_health.setdefault(
            topic,
            {
                "seen": False,
                "messageCount": 0,
                "lastMessageAgeSec": -1.0,
                "estimatedHz": 0.0,
                "qos": "",
            },
        )
        self.ros2LogMessage.emit("INFO", f"[ROS2] Watching topic {topic} for {drone_id or 'namespace'}")
        self._trace_event("topic_subscribe", {"topic": topic, "droneId": drone_id})
        return True

    def _record_topic_message(self, topic: str, json_data: str = "{}", qos: str = "") -> None:
        """Update topic health and emit a compact message event."""
        now = time.monotonic()
        previous = self._topic_health.get(topic, {})
        last_seen = float(previous.get("_lastSeenMonotonic", 0.0) or 0.0)
        count = int(previous.get("messageCount", 0)) + 1
        hz = 0.0 if last_seen <= 0 else 1.0 / max(0.001, now - last_seen)
        health = {
            "seen": True,
            "messageCount": count,
            "lastMessageAgeSec": 0.0,
            "estimatedHz": hz,
            "qos": qos,
            "_lastSeenMonotonic": now,
        }
        self._topic_health[topic] = health
        public_health = {k: v for k, v in health.items() if not k.startswith("_")}
        self._trace_topic_health(topic, public_health)
        self.topicMessage.emit(topic, json_data, time.time())

    # ── Internal ──────────────────────────────────────────────────────────

    def _on_bridge_telemetry(self, drone_id: str, data: dict) -> None:
        self.telemetryReceived.emit(drone_id, data)
        ns = self._namespaces.get(drone_id, drone_id)
        topic = self._px4_topic(ns, "out", "vehicle_odometry")
        self._record_topic_message(topic, "{}", "sensor_data")
    
    def _on_connection_status(self, drone_id: str, status) -> None:
        """Handle connection status changes from bridge."""
        status_str = status.value if hasattr(status, 'value') else str(status)
        self.connectionStatusChanged.emit(drone_id, status_str)
        self._write_bridge_terminal_log(drone_id, f"Connection status: {status_str}")
        
        # Log status changes to LogPanel via ros2LogMessage
        if status_str == "connected":
            self.ros2LogMessage.emit("INFO", f"[ROS2] {drone_id} connected")
        elif status_str == "reconnecting":
            self.ros2LogMessage.emit("WARN", f"[ROS2] {drone_id} reconnecting...")
        elif status_str == "failed":
            self.ros2LogMessage.emit("ERROR", f"[ROS2] {drone_id} connection failed")
        elif status_str == "disconnected":
            self.ros2LogMessage.emit("INFO", f"[ROS2] {drone_id} disconnected")

    def _poll(self) -> None:
        for did, bridge in list(self._bridges.items()):
            snap = dict(bridge.telemetry)
            if snap:
                self.telemetryReceived.emit(did, snap)

    # ── PX4 SITL Control ──────────────────────────────────────────────────

    @Slot(result=bool)
    def isSitlRunning(self) -> bool:
        """Check if SITL cluster is running."""
        return self._sitl_cluster is not None and self._sitl_cluster.is_running()

    @Slot(result=str)
    def getSitlPx4Dir(self) -> str:
        """Get current PX4 directory."""
        return self._sitl_config.get('px4_dir', '')

    @Slot(str)
    def setSitlPx4Dir(self, path: str) -> None:
        """Set PX4 directory."""
        self._sitl_config['px4_dir'] = path

    @Slot(result=str)
    def getSitlModel(self) -> str:
        """Get current SITL model."""
        return self._sitl_config.get('model', 'x500')

    @Slot(str)
    def setSitlModel(self, model: str) -> None:
        """Set SITL model."""
        self._sitl_config['model'] = model

    @Slot(result=str)
    def getSitlNamespace(self) -> str:
        """Get current SITL namespace."""
        return self._sitl_config.get('namespace', 'uav_1')

    @Slot(str)
    def setSitlNamespace(self, namespace: str) -> None:
        """Set SITL namespace."""
        self._sitl_config['namespace'] = namespace

    @Slot(result="QVariant")
    def getSitlRos2Setups(self) -> list:
        """Get ROS2 setup files."""
        return self._ros2_setup_sources()

    @Slot(result="QVariant")
    def getRos2SetupSources(self) -> list:
        """Get shared ROS2 setup files for Bridge and SITL."""
        return self._ros2_setup_sources()

    @Slot(result=str)
    def getRos2SetupSourcesText(self) -> str:
        """Get shared ROS2 setup files as newline-separated text."""
        return "\n".join(self._ros2_setup_sources())

    @Slot(str)
    def setRos2SetupSourcesText(self, text: str) -> None:
        """Set shared ROS2 setup files from newline-separated text."""
        self._sitl_config["ros2_setups"] = self._clean_ros2_setup_sources(text)

    @Slot("QVariant")
    def setRos2SetupSources(self, sources: Any) -> None:
        """Set shared ROS2 setup files from QML list/string data."""
        self._sitl_config["ros2_setups"] = self._clean_ros2_setup_sources(sources)

    @Slot(result=bool)
    def getUseVisibleTerminal(self) -> bool:
        """Return whether Bridge/SITL starts should open a visible Linux terminal."""
        return bool(self._use_terminal)

    @Slot(bool)
    def setUseVisibleTerminal(self, enabled: bool) -> None:
        """Enable/disable visible terminal launch for Bridge/SITL starts."""
        self._use_terminal = bool(enabled)

    @Slot(result=str)
    def getRos2EnvInfo(self) -> str:
        """Return current ROS_DOMAIN_ID and ROS_LOCALHOST_ONLY for display in the UI."""
        domain = os.environ.get("ROS_DOMAIN_ID", "0 (default)")
        localhost = os.environ.get("ROS_LOCALHOST_ONLY", "0")
        return f"ROS_DOMAIN_ID={domain}  ROS_LOCALHOST_ONLY={localhost}"

    @Slot(str, str, result=bool)
    def launchCommandInTerminal(self, title: str, command: str) -> bool:
        """
        Open a visible terminal emulator and run *command* in it.

        Internally delegates to _launch_visible_terminal which tries
        gnome-terminal / konsole / xfce4-terminal / xterm in order.
        Returns True if a terminal process was spawned, False otherwise
        (e.g., on Windows or when no emulator is found in PATH).
        """
        proc = self._launch_visible_terminal(title, [command])
        if proc is None:
            return False
        self.ros2LogMessage.emit("INFO", f"[ROS2] Terminal opened: {title}")
        return True

    @Slot(str, str, str, result=str)
    def buildSitlCommand(self, px4_dir: str, namespace: str, make_target: str) -> str:
        """
        Build the three-line PX4 SITL startup command string.
        Useful for QML TextEdit live-preview fields.
        """
        import shlex as _shlex
        ns = namespace.strip() or "uav_1"
        mt = make_target.strip() or "gz_x500"
        px4 = os.path.expanduser(px4_dir.strip()) if px4_dir.strip() else "~/PX4-Autopilot"
        return (
            f"cd {_shlex.quote(px4)}\n"
            f"export PX4_UXRCE_DDS_NS={_shlex.quote(ns)}\n"
            f"make px4_sitl {_shlex.quote(mt)}"
        )

    @Slot(str)
    def addSitlRos2Setup(self, path: str) -> None:
        """Add ROS2 setup file."""
        cleaned = self._clean_ros2_setup_sources([path])
        if cleaned and cleaned[0] not in self._sitl_config['ros2_setups']:
            self._sitl_config['ros2_setups'].append(cleaned[0])

    @Slot(str)
    def removeSitlRos2Setup(self, path: str) -> None:
        """Remove ROS2 setup file."""
        cleaned = self._clean_ros2_setup_sources([path])
        if cleaned and cleaned[0] in self._sitl_config['ros2_setups']:
            self._sitl_config['ros2_setups'].remove(cleaned[0])

    @Slot(result="QVariant")
    def listLaunchProfiles(self) -> list:
        """Return predefined PX4/Gazebo/SIH launch profiles."""
        return [dict(profile) for profile in _LAUNCH_PROFILES]

    @Slot(str, str, result="QVariant")
    def getWorldProfileWarnings(self, model: str, world_profile: str) -> list:
        """Return compatibility warnings for a PX4 model/world profile pair."""
        model_name = str(model or "")
        profile = str(world_profile or "empty_default")
        warnings: list[str] = []

        if profile == "ridge_terrain" and "lidar" not in model_name:
            warnings.append("ridge_terrain works best with gz_x500_lidar_down")
        if profile == "aruco_precision_landing" and "mono_cam" not in model_name:
            warnings.append("aruco_precision_landing needs gz_x500_mono_cam")
        if profile == "moving_platform":
            warnings.append("moving_platform requires PX4_GZ_MODEL_POSE=0,0,2.2")
        return warnings

    @Slot(result="QVariantMap")
    def getSitlStatus(self) -> dict:
        """Return current SITL status for QML."""
        status = dict(self._sitl_status)
        if status.get("running") and self._sitl_started_at:
            status["uptime_s"] = max(0.0, time.monotonic() - self._sitl_started_at)
        if self._sitl_cluster is not None:
            try:
                status["running"] = bool(self._sitl_cluster.is_running())
                status["gazebo_running"] = status["running"] and not status.get("sih", False)
            except Exception:
                pass
            status["pid"] = self._extract_cluster_pid()
        return status

    @Slot(result=bool)
    @Slot("QVariant", result=bool)
    def startSitl(self, profile: Any = None) -> bool:
        """Start PX4 SITL + Gazebo + XRCE-DDS Agent."""
        return self._start_sitl_profiles([self._normalize_sitl_profile(profile)])

    @Slot(result=bool)
    @Slot("QVariant", result=bool)
    def startSihSitl(self, profile: Any = None) -> bool:
        """Start PX4 SIH mode profile (headless, no Gazebo)."""
        normalized = self._normalize_sitl_profile(profile or {"model": "sih_quadx", "world": ""})
        normalized["model"] = "sih_quadx"
        normalized["clusterModel"] = "sih_quadx"
        normalized["world"] = ""
        normalized["sih"] = True
        return self._start_sitl_profiles([normalized])

    @Slot(int, int, result=bool)
    @Slot("QVariant", result=bool)
    def startMultiSitl(self, count_or_profiles: Any = 1, base_port: int = 5762) -> bool:
        """Start N PX4 SITL vehicles or a list of explicit vehicle profiles."""
        profiles = self._build_multi_profiles(count_or_profiles, base_port)
        return self._start_sitl_profiles(profiles)

    def _start_sitl_profiles(self, profiles: list[dict]) -> bool:
        if self._sitl_cluster is not None:
            try:
                if self._sitl_cluster.is_running():
                    self.ros2LogMessage.emit("WARN", "[SITL] Already running")
                    return False
            except Exception:
                pass

        if not profiles:
            self.ros2LogMessage.emit("ERROR", "[SITL] No launch profiles provided")
            return False

        self._sitl_profiles = [dict(profile) for profile in profiles]
        first = self._sitl_profiles[0]
        self._sitl_config.update(
            {
                "px4_dir": first.get("px4Dir", self._sitl_config.get("px4_dir", "")),
                "model": first.get("model", self._sitl_config.get("model", "gz_x500")),
                "namespace": first.get("namespace", self._sitl_config.get("namespace", "px4_1")),
                "ros2_setups": first.get("ros2Setups", self._sitl_config.get("ros2_setups", [])),
            }
        )
        self._sitl_status = {
            "running": False,
            "status": "starting",
            "model": first.get("model", ""),
            "world": first.get("world", ""),
            "namespace": first.get("namespace", ""),
            "pid": 0,
            "uptime_s": 0.0,
            "gazebo_running": False,
            "vehicle_count": len(self._sitl_profiles),
            "vehicles": [dict(profile) for profile in self._sitl_profiles],
            "sih": bool(first.get("sih", False)),
        }
        self._emit_sitl_status()
        self._trace_event("sitl_launch", {"status": "starting", "profiles": self._sitl_profiles})

        if len(self._sitl_profiles) == 1 and sys.platform != "win32" and self._terminal_launcher():
            if self._start_sitl_in_terminal(first):
                return True
            self.ros2LogMessage.emit("WARN", "[SITL] Visible terminal failed, falling back to background launcher")

        def _start():
            try:
                from skymeshx.simulation import PX4GazeboCluster

                cluster_model = first.get("clusterModel") or self._normalize_model_for_cluster(first.get("model", "gz_x500"))
                namespace_prefix = self._namespace_prefix(first.get("namespace", "px4_1"))
                self.ros2LogMessage.emit(
                    "INFO",
                    f"[SITL] Starting {len(self._sitl_profiles)} PX4 profile(s): "
                    f"model={first.get('model')} world={first.get('world')} ns={namespace_prefix}_N",
                )

                def log_callback(source: str, message: str):
                    self.ros2LogMessage.emit("INFO", f"[{source}] {message}")

                cluster = PX4GazeboCluster(
                    num_drones=len(self._sitl_profiles),
                    px4_dir=first.get("px4Dir", self._sitl_config["px4_dir"]),
                    model=cluster_model,
                    world=first.get("world", "default"),
                    xrce_port=int(first.get("xrcePort", 8888)),
                    ros2_setups=first.get("ros2Setups", self._sitl_config["ros2_setups"]),
                    namespace_prefix=namespace_prefix,
                    log_callback=log_callback,
                )

                if cluster.start():
                    self._sitl_cluster = cluster
                    self._sitl_started_at = time.monotonic()
                    self._sitl_status.update(
                        {
                            "running": True,
                            "status": "running",
                            "gazebo_running": not bool(first.get("sih", False)),
                            "pid": self._extract_cluster_pid(),
                            "uptime_s": 0.0,
                        }
                    )
                    self.ros2LogMessage.emit("INFO", "[SITL] ✓ Cluster started successfully")
                    self._trace_event("sitl_launch", {"status": "running", "profiles": self._sitl_profiles})
                else:
                    self._sitl_status.update({"running": False, "status": "failed", "gazebo_running": False})
                    self.ros2LogMessage.emit("ERROR", "[SITL] Failed to start cluster")
                    self._trace_event("sitl_launch", {"status": "failed", "profiles": self._sitl_profiles})
            except FileNotFoundError as exc:
                self._sitl_status.update({"running": False, "status": "failed", "gazebo_running": False})
                self.ros2LogMessage.emit("ERROR", f"[SITL] PX4 directory not found: {exc}")
                self._trace_event("sitl_launch", {"status": "failed", "error": str(exc)})
            except ImportError as exc:
                self._sitl_status.update({"running": False, "status": "failed", "gazebo_running": False})
                self.ros2LogMessage.emit("ERROR",
                    f"[SITL] PX4GazeboCluster not available ({exc}). "
                    "Use the Command Launcher in the Connection tab to start PX4 manually.")
                self._trace_event("sitl_launch", {"status": "failed", "error": str(exc)})
            except Exception as exc:
                self._sitl_status.update({"running": False, "status": "failed", "gazebo_running": False})
                self.ros2LogMessage.emit("ERROR", f"[SITL] Start failed: {exc}")
                self._trace_event("sitl_launch", {"status": "failed", "error": str(exc)})
            finally:
                self._emit_sitl_status()

        self._run_async(_start)
        return True

    @Slot(result=bool)
    @Slot(str, result=bool)
    def stopSitl(self, namespace: str = "") -> bool:
        """Stop PX4 SITL cluster. Namespace is accepted for future per-vehicle stop."""
        # Atomically grab and clear the cluster reference so that concurrent
        # calls cannot both pass the None guard and double-stop the same object.
        cluster = self._sitl_cluster
        if cluster is None:
            self.ros2LogMessage.emit("WARN", "[SITL] Not running")
            return False
        self._sitl_cluster = None

        def _stop():
            try:
                self.ros2LogMessage.emit("INFO", "[SITL] Stopping cluster...")
                cluster.stop()
                self._trace_event("sitl_launch", {"status": "stopped", "namespace": namespace})
                self.ros2LogMessage.emit("INFO", "[SITL] ✓ Cluster stopped")
            except Exception as exc:
                self.ros2LogMessage.emit("ERROR", f"[SITL] Stop failed: {exc}")
                self._trace_event("sitl_launch", {"status": "stop_failed", "error": str(exc)})
            finally:
                self._sitl_started_at = 0.0
                self._sitl_status.update(
                    {"running": False, "status": "stopped", "gazebo_running": False, "pid": 0, "uptime_s": 0.0}
                )
                self._emit_sitl_status()

        self._run_async(_stop)
        return True

    @Slot(result=bool)
    def stopAllSitl(self) -> bool:
        """Stop all SITL vehicles."""
        return self.stopSitl("")
    
    # ── Mission Management ────────────────────────────────────────────────
    
    @Slot(str, "QVariant", result=bool)
    def uploadMission(self, drone_id: str, waypoints: list) -> bool:
        """
        Upload waypoint mission to PX4.
        
        Args:
            drone_id: Drone identifier
            waypoints: List of waypoint dicts with keys: lat, lon, alt
        
        Returns:
            True if upload successful
        """
        b = self._bridges.get(drone_id)
        if not b:
            self.ros2LogMessage.emit("WARN", f"[MISSION] No bridge for {drone_id}")
            self._trace_mission_event("mission_upload", {"droneId": drone_id, "status": "rejected", "reason": "no_bridge"})
            return False
        
        try:
            # Convert QML list to Python list of dicts
            wp_list = []
            for wp in waypoints:
                wp_dict = {
                    "lat": float(wp.get("lat", 0)),
                    "lon": float(wp.get("lon", 0)),
                    "alt": float(wp.get("alt", 0)),
                }
                # Optional parameters
                if "hold_time" in wp:
                    wp_dict["hold_time"] = float(wp["hold_time"])
                if "accept_radius" in wp:
                    wp_dict["accept_radius"] = float(wp["accept_radius"])
                if "yaw" in wp:
                    wp_dict["yaw"] = float(wp["yaw"])
                wp_list.append(wp_dict)
            
            self.ros2LogMessage.emit("INFO", f"[MISSION] Uploading {len(wp_list)} waypoints to {drone_id}...")
            self._trace_mission_event(
                "mission_upload",
                {"droneId": drone_id, "status": "started", "waypointCount": len(wp_list), "controlPath": "ros2_uxrce"},
            )
            success = b.upload_mission(wp_list, timeout=10.0)
            
            if success:
                self._mission_waypoints[drone_id] = [dict(wp) for wp in wp_list]
                self._last_wp_trace.pop(drone_id, None)
                self.ros2LogMessage.emit("INFO", f"[MISSION] ✓ Mission uploaded to {drone_id}")
                self._trace_mission_event(
                    "mission_upload",
                    {"droneId": drone_id, "status": "finished", "success": True, "waypointCount": len(wp_list)},
                )
                # Register status callback
                b.on_mission_status(lambda status: self._on_mission_status(drone_id, status))
            else:
                self.ros2LogMessage.emit("ERROR", f"[MISSION] Upload failed for {drone_id}")
                self._trace_mission_event(
                    "mission_upload",
                    {"droneId": drone_id, "status": "finished", "success": False, "waypointCount": len(wp_list)},
                )
            
            return success
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[MISSION] Upload error: {e}")
            self._trace_mission_event("mission_upload", {"droneId": drone_id, "status": "error", "error": str(e)})
            return False
    
    @Slot(str, result=bool)
    def clearMission(self, drone_id: str) -> bool:
        """Clear mission on PX4."""
        b = self._bridges.get(drone_id)
        if not b:
            self.ros2LogMessage.emit("WARN", f"[MISSION] No bridge for {drone_id}")
            self._trace_mission_event("mission_abort", {"droneId": drone_id, "action": "clear", "status": "rejected", "reason": "no_bridge"})
            return False
        
        try:
            success = b.clear_mission()
            if success:
                self._mission_waypoints.pop(drone_id, None)
                self._last_wp_trace.pop(drone_id, None)
                self.ros2LogMessage.emit("INFO", f"[MISSION] ✓ Mission cleared on {drone_id}")
            self._trace_mission_event("mission_abort", {"droneId": drone_id, "action": "clear", "status": "sent", "success": bool(success)})
            return success
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[MISSION] Clear error: {e}")
            self._trace_mission_event("mission_abort", {"droneId": drone_id, "action": "clear", "status": "error", "error": str(e)})
            return False
    
    @Slot(str)
    def startMission(self, drone_id: str) -> None:
        """Start mission execution (switch to AUTO.MISSION mode)."""
        b = self._bridges.get(drone_id)
        if not b:
            self.ros2LogMessage.emit("WARN", f"[MISSION] No bridge for {drone_id}")
            self._trace_mission_event("mission_start", {"droneId": drone_id, "status": "rejected", "reason": "no_bridge"})
            return
        
        try:
            b.start_mission()
            self._trace_mission_event("mission_start", {"droneId": drone_id, "status": "sent"})
            self.ros2LogMessage.emit("INFO", f"[MISSION] ✓ Mission started on {drone_id}")
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[MISSION] Start error: {e}")
            self._trace_mission_event("mission_start", {"droneId": drone_id, "status": "error", "error": str(e)})
    
    @Slot(str)
    def pauseMission(self, drone_id: str) -> None:
        """Pause mission execution (switch to AUTO.LOITER mode)."""
        b = self._bridges.get(drone_id)
        if not b:
            self.ros2LogMessage.emit("WARN", f"[MISSION] No bridge for {drone_id}")
            self._trace_mission_event("mission_pause", {"droneId": drone_id, "status": "rejected", "reason": "no_bridge"})
            return
        
        try:
            b.pause_mission()
            self._trace_mission_event("mission_pause", {"droneId": drone_id, "status": "sent"})
            self.ros2LogMessage.emit("INFO", f"[MISSION] ✓ Mission paused on {drone_id}")
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[MISSION] Pause error: {e}")
            self._trace_mission_event("mission_pause", {"droneId": drone_id, "status": "error", "error": str(e)})

    @Slot(str)
    def abortMission(self, drone_id: str) -> None:
        """Abort mission execution by switching PX4 out of AUTO.MISSION."""
        b = self._bridges.get(drone_id)
        if not b:
            self.ros2LogMessage.emit("WARN", f"[MISSION] No bridge for {drone_id}")
            self._trace_mission_event("mission_abort", {"droneId": drone_id, "action": "pause", "status": "rejected", "reason": "no_bridge"})
            return

        try:
            b.pause_mission()
            self.ros2LogMessage.emit("WARN", f"[MISSION] Mission abort sent to {drone_id}")
            self._trace_mission_event("mission_abort", {"droneId": drone_id, "action": "pause", "status": "sent"})
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[MISSION] Abort error: {e}")
            self._trace_mission_event("mission_abort", {"droneId": drone_id, "action": "pause", "status": "error", "error": str(e)})
    
    @Slot(str, result="QVariant")
    def getMissionStatus(self, drone_id: str) -> dict:
        """Get current mission status."""
        b = self._bridges.get(drone_id)
        if not b:
            return {
                "active": False,
                "current_seq": 0,
                "total_count": 0,
                "reached": False,
                "finished": False,
                "failure": False,
            }
        
        try:
            return b.get_mission_status()
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[MISSION] Status error: {e}")
            return {}
    
    @Slot(str, result="QVariant")
    def getMissionWaypoints(self, drone_id: str) -> list:
        """Get uploaded mission waypoints."""
        b = self._bridges.get(drone_id)
        if not b:
            return []
        
        try:
            return b.get_mission_waypoints()
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[MISSION] Waypoints error: {e}")
            return []
    
    def _on_mission_status(self, drone_id: str, status: dict) -> None:
        """Handle mission status updates from bridge."""
        self.missionStatusChanged.emit(drone_id, status)
        self._trace_mission_event("mission_status", {"droneId": drone_id, **dict(status)})
        self._trace_wp_tracking(drone_id, status)
        
        # Log significant events
        if status.get("finished"):
            self.ros2LogMessage.emit("INFO", f"[MISSION] ✓ Mission completed on {drone_id}")
        elif status.get("failure"):
            self.ros2LogMessage.emit("WARNING", f"[MISSION] ✗ Mission failed on {drone_id}")
    # ── Formation Control ──────────────────────────────────────────────────
    
    def __init_formation_controller(self):
        """Initialize formation controller (lazy loading)."""
        if hasattr(self, '_formation_controller'):
            return self._formation_controller is not None
        
        try:
            from skymeshx.ros.px4_formation import PX4FormationController
            self._formation_controller = None
            self._FormationController = PX4FormationController
            return True
        except ImportError:
            self._formation_controller = None
            self._FormationController = None
            return False
    
    @Slot(result=bool)
    def isFormationActive(self) -> bool:
        """Check if formation controller is running."""
        return hasattr(self, '_formation_controller') and self._formation_controller is not None
    
    @Slot(str, "QVariant", str, float)
    def startFormation(self, leader_id: str, follower_ids: list, shape: str, spacing: float) -> None:
        """
        Start formation control.
        
        Args:
            leader_id: Leader drone ID (e.g., "uav_1")
            follower_ids: List of follower drone IDs (e.g., ["uav_2", "uav_3"])
            shape: Formation shape (line, v, grid, circle, wedge)
            spacing: Distance between vehicles in meters
        """
        if not self.__init_formation_controller():
            self.ros2LogMessage.emit("ERROR", "[FORMATION] PX4FormationController not available")
            return
        
        if self.isFormationActive():
            self.ros2LogMessage.emit("WARN", "[FORMATION] Already running")
            return
        
        def _start():
            try:
                # Get namespaces from active bridges
                leader_ns = self._namespaces.get(leader_id, leader_id)
                follower_ns = [self._namespaces.get(fid, fid) for fid in follower_ids]
                
                self.ros2LogMessage.emit("INFO", f"[FORMATION] Starting controller...")
                self.ros2LogMessage.emit("INFO", f"[FORMATION] Leader: {leader_ns}")
                self.ros2LogMessage.emit("INFO", f"[FORMATION] Followers: {', '.join(follower_ns)}")
                self.ros2LogMessage.emit("INFO", f"[FORMATION] Shape: {shape}, Spacing: {spacing}m")
                
                controller = self._FormationController(
                    leader_ns=leader_ns,
                    follower_namespaces=follower_ns,
                    shape=shape,
                    spacing=spacing,
                    update_rate_hz=20.0
                )
                
                if controller.start():
                    self._formation_controller = controller
                    self.ros2LogMessage.emit("INFO", "[FORMATION] ✓ Controller started")
                else:
                    self.ros2LogMessage.emit("ERROR", "[FORMATION] Failed to start controller")
                    
            except Exception as e:
                self.ros2LogMessage.emit("ERROR", f"[FORMATION] Start failed: {e}")
        
        threading.Thread(target=_start, daemon=True).start()
    
    @Slot()
    def stopFormation(self) -> None:
        """Stop formation controller."""
        if not self.isFormationActive():
            self.ros2LogMessage.emit("WARN", "[FORMATION] Not running")
            return
        
        def _stop():
            try:
                self.ros2LogMessage.emit("INFO", "[FORMATION] Stopping controller...")
                self._formation_controller.stop()
                self._formation_controller = None
                self.ros2LogMessage.emit("INFO", "[FORMATION] ✓ Controller stopped")
            except Exception as e:
                self.ros2LogMessage.emit("ERROR", f"[FORMATION] Stop failed: {e}")
        
        threading.Thread(target=_stop, daemon=True).start()
    
    @Slot(float, float, float, float)
    def setFormationLeaderPosition(self, north: float, east: float, altitude: float, yaw: float) -> None:
        """
        Set leader position. Followers maintain formation offsets.
        
        Args:
            north: North position in meters (NED)
            east: East position in meters (NED)
            altitude: Altitude above ground in meters (positive up)
            yaw: Heading in radians (0 = North)
        """
        if not self.isFormationActive():
            self.ros2LogMessage.emit("WARN", "[FORMATION] Controller not running")
            return
        
        try:
            self._formation_controller.set_leader_position(north, east, altitude, yaw)
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[FORMATION] Set position failed: {e}")
    
    @Slot(result="QVariant")
    def getFormationLeaderPosition(self) -> dict:
        """Get current leader position."""
        if not self.isFormationActive():
            return {"north": 0.0, "east": 0.0, "altitude": 0.0}
        
        try:
            return self._formation_controller.get_leader_position()
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[FORMATION] Get position failed: {e}")
            return {"north": 0.0, "east": 0.0, "altitude": 0.0}
    
    @Slot(result="QVariant")
    def getFormationFollowerPositions(self) -> dict:
        """Get current follower positions."""
        if not self.isFormationActive():
            return {}
        
        try:
            return self._formation_controller.get_follower_positions()
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[FORMATION] Get follower positions failed: {e}")
            return {}
    
    @Slot()
    def armFormation(self) -> None:
        """Arm all vehicles in formation."""
        if not self.isFormationActive():
            self.ros2LogMessage.emit("WARN", "[FORMATION] Controller not running")
            return
        
        try:
            self._formation_controller.arm_all()
            self.ros2LogMessage.emit("INFO", "[FORMATION] ✓ All vehicles armed")
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[FORMATION] Arm failed: {e}")
    
    @Slot()
    def disarmFormation(self) -> None:
        """Disarm all vehicles in formation."""
        if not self.isFormationActive():
            self.ros2LogMessage.emit("WARN", "[FORMATION] Controller not running")
            return
        
        try:
            self._formation_controller.disarm_all()
            self.ros2LogMessage.emit("INFO", "[FORMATION] ✓ All vehicles disarmed")
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[FORMATION] Disarm failed: {e}")
    
    @Slot()
    def enableOffboardFormation(self) -> None:
        """Enable offboard mode for all vehicles in formation."""
        if not self.isFormationActive():
            self.ros2LogMessage.emit("WARN", "[FORMATION] Controller not running")
            return
        
        try:
            self._formation_controller.enable_offboard_all()
            self.ros2LogMessage.emit("INFO", "[FORMATION] ✓ Offboard mode enabled for all vehicles")
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[FORMATION] Enable offboard failed: {e}")
    # ═══════════════════════════════════════════════════════════════════════
    # BAG RECORDING
    # ═══════════════════════════════════════════════════════════════════════

    def _default_bag_namespace(self) -> str:
        if self._namespaces:
            return next(iter(self._namespaces.values())).strip("/")
        if self._sitl_profiles:
            return str(self._sitl_profiles[0].get("namespace", "px4_1")).strip("/")
        return "px4_1"

    def _resolve_bag_topics(self, topics: list | None, preset: str = "", namespace: str = "") -> list[str]:
        explicit = [str(topic).strip() for topic in (topics or []) if str(topic).strip()]
        if explicit:
            return explicit

        ns = (namespace or self._default_bag_namespace()).strip("/")
        preset_name = preset or "minimal_mission"
        names = _BAG_PRESETS.get(preset_name, _BAG_PRESETS["minimal_mission"])
        resolved: list[str] = []
        for name in names:
            if name == "*":
                resolved.append(self._px4_topic(ns, "out", "*"))
            elif name.startswith("/"):
                resolved.append(name)
            elif "/" in name and not name.startswith("vehicle_") and not name.startswith("battery_"):
                resolved.append(f"/{ns}/{name}" if ns else f"/{name}")
            else:
                resolved.append(self._px4_topic(ns, "out", name))
        return resolved

    def _ensure_bag_recorder(self, output_dir: str = "") -> bool:
        if self._bag_recorder is not None:
            return True
        try:
            from skymeshx.ros.bag_recorder import ROS2BagRecorder

            bags_dir = Path(output_dir) if output_dir else Path.cwd() / "bags"
            self._bag_recorder = ROS2BagRecorder(output_dir=str(bags_dir))
            self.ros2LogMessage.emit("INFO", f"[BAG] Recorder initialized (output: {bags_dir})")
            return True
        except Exception as exc:
            message = f"[BAG] Failed to initialize recorder: {exc}"
            self.ros2LogMessage.emit("ERROR", message)
            self.bagRecordError.emit(message)
            return False

    @Slot("QVariant", str, str, result=bool)
    def startBagRecord(self, topics: list, output_dir: str = "", preset: str = "minimal_mission") -> bool:
        """Start a bag recording using explicit topics or a named preset."""
        topic_list = self._resolve_bag_topics(list(topics) if topics else [], preset)
        if not topic_list:
            self.ros2LogMessage.emit("WARN", "[BAG] No topics selected")
            return False

        if not self._ensure_bag_recorder(output_dir):
            return False

        try:
            bag_name = f"{preset}_{time.strftime('%Y%m%d_%H%M%S')}" if preset else None
            success = self._bag_recorder.start_recording(
                topics=topic_list,
                bag_name=bag_name,
                compression="zstd",
            )
            if success:
                status = self._bag_recorder.get_recording_status()
                path = str(status.get("bag_path", ""))
                self.bagRecordStarted.emit(path)
                self.ros2LogMessage.emit("INFO", f"[BAG] ✓ Recording started ({len(topic_list)} topics)")
                self._trace_event(
                    "bag_record",
                    {"status": "started", "path": path, "preset": preset, "topics": topic_list},
                )
            else:
                self.bagRecordError.emit("Failed to start recording")
                self.ros2LogMessage.emit("ERROR", "[BAG] Failed to start recording")
            return bool(success)
        except Exception as exc:
            message = f"[BAG] Start recording error: {exc}"
            self.ros2LogMessage.emit("ERROR", message)
            self.bagRecordError.emit(message)
            return False

    @Slot(result=str)
    def stopBagRecord(self) -> str:
        """Stop current bag recording and return the bag path."""
        if self._bag_recorder is None:
            self.ros2LogMessage.emit("WARN", "[BAG] Recorder not initialized")
            return ""

        before = self._bag_recorder.get_recording_status()
        path = str(before.get("bag_path", ""))
        try:
            success = self._bag_recorder.stop_recording()
            after = self._bag_recorder.get_recording_status()
            size_mb = float(before.get("size_mb", after.get("size_mb", 0.0)) or 0.0)
            if success:
                self.bagRecordStopped.emit(path, size_mb)
                self.ros2LogMessage.emit("INFO", "[BAG] ✓ Recording stopped")
                self._trace_event("bag_record", {"status": "stopped", "path": path, "sizeMb": size_mb})
                return path
            self.ros2LogMessage.emit("WARN", "[BAG] Not recording")
            return ""
        except Exception as exc:
            message = f"[BAG] Stop recording error: {exc}"
            self.ros2LogMessage.emit("ERROR", message)
            self.bagRecordError.emit(message)
            return ""

    @Slot(result="QVariantMap")
    def getBagStatus(self) -> dict:
        """Return bag recording status."""
        return self.getBagRecordingStatus()
    
    @Slot("QVariant", str, str, result=bool)
    def startBagRecording(self, topics: list, bag_name: str = "", compression: str = "zstd") -> bool:
        """
        Start recording ROS2 bag.
        
        Args:
            topics: List of topic names to record (e.g., ["/fmu/out/vehicle_odometry"])
            bag_name: Optional custom bag name (default: timestamp-based)
            compression: Compression mode: "zstd", "lz4", or "none" (default: zstd)
        
        Returns:
            True if recording started successfully
        """
        topic_list = [str(topic).strip() for topic in (topics or []) if str(topic).strip()]
        if not topic_list:
            self.ros2LogMessage.emit("WARN", "[BAG] No topics selected")
            return False

        if not self._ensure_bag_recorder(""):
            return False

        try:
            success = self._bag_recorder.start_recording(
                topics=topic_list,
                bag_name=bag_name if bag_name else None,
                compression=compression
            )
            
            if success:
                status = self._bag_recorder.get_recording_status()
                path = str(status.get("bag_path", ""))
                self.bagRecordStarted.emit(path)
                self.ros2LogMessage.emit("INFO", f"[BAG] ✓ Recording started ({len(topic_list)} topics)")
                self._trace_event(
                    "bag_record",
                    {"status": "started", "path": path, "preset": "", "topics": topic_list},
                )
            else:
                self.ros2LogMessage.emit("ERROR", "[BAG] Failed to start recording")
                self.bagRecordError.emit("Failed to start recording")
            
            return success
            
        except Exception as e:
            message = f"[BAG] Start recording error: {e}"
            self.ros2LogMessage.emit("ERROR", message)
            self.bagRecordError.emit(message)
            return False
    
    @Slot(result=bool)
    def stopBagRecording(self) -> bool:
        """
        Stop current bag recording.
        
        Returns:
            True if recording stopped successfully
        """
        return bool(self.stopBagRecord())
    
    @Slot(result=bool)
    def isBagRecording(self) -> bool:
        """Check if currently recording."""
        if not hasattr(self, '_bag_recorder') or self._bag_recorder is None:
            return False
        
        try:
            return self._bag_recorder.is_recording()
        except Exception:
            return False
    
    @Slot(result="QVariantMap")
    def getBagRecordingStatus(self) -> dict:
        """
        Get current recording status.
        
        Returns:
            Dict with keys: recording, duration_sec, bag_path, size_mb
        """
        if not hasattr(self, '_bag_recorder') or self._bag_recorder is None:
            return {
                "recording": False,
                "duration_sec": 0.0,
                "bag_path": "",
                "size_mb": 0.0
            }
        
        try:
            return self._bag_recorder.get_recording_status()
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[BAG] Status error: {e}")
            return {
                "recording": False,
                "duration_sec": 0.0,
                "bag_path": "",
                "size_mb": 0.0
            }
    
    @Slot(result="QVariantList")
    def listBags(self) -> list:
        """
        List all recorded bags.
        
        Returns:
            List of dicts with keys: path, size_mb, duration_sec, message_count, topics, start_time
        """
        if not hasattr(self, '_bag_recorder') or self._bag_recorder is None:
            try:
                from skymeshx.ros.bag_recorder import ROS2BagRecorder
                self._bag_recorder = ROS2BagRecorder(output_dir="./bags")
            except Exception as e:
                self.ros2LogMessage.emit("ERROR", f"[BAG] Failed to initialize recorder: {e}")
                return []
        
        try:
            bags = self._bag_recorder.list_bags()
            
            # Convert BagInfo objects to dicts for QML
            return [
                {
                    "path": bag.path,
                    "size_mb": bag.size_mb,
                    "duration_sec": bag.duration_sec,
                    "message_count": bag.message_count,
                    "topics": bag.topics,
                    "start_time": bag.start_time
                }
                for bag in bags
            ]
            
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[BAG] List bags error: {e}")
            return []
    
    @Slot(str, float, result=bool)
    def playBag(self, bag_path: str, rate: float = 1.0) -> bool:
        """
        Play back a recorded bag.
        
        Args:
            bag_path: Path to bag directory
            rate: Playback rate multiplier (default: 1.0 = real-time)
        
        Returns:
            True if playback started successfully
        """
        if not hasattr(self, '_bag_recorder') or self._bag_recorder is None:
            try:
                from skymeshx.ros.bag_recorder import ROS2BagRecorder
                self._bag_recorder = ROS2BagRecorder(output_dir="./bags")
            except Exception as e:
                self.ros2LogMessage.emit("ERROR", f"[BAG] Failed to initialize recorder: {e}")
                return False
        
        try:
            success = self._bag_recorder.play_bag(bag_path, rate)
            
            if success:
                self.ros2LogMessage.emit("INFO", f"[BAG] ✓ Playing {bag_path} at {rate}x speed")
            else:
                self.ros2LogMessage.emit("ERROR", f"[BAG] Failed to play {bag_path}")
            
            return success
            
        except Exception as e:
            self.ros2LogMessage.emit("ERROR", f"[BAG] Playback error: {e}")
            return False
    
    
    # ── Frame Conversion Debug ─────────────────────────────────────────────
    
    @Slot(str, result="QVariant")
    def getFrameData(self, drone_id: str) -> dict:
        """
        Get NED and ENU frame data for visualization.
        
        Returns dict with:
            ned_north, ned_east, ned_down (PX4 native frame)
            enu_east, enu_north, enu_up (ROS2 standard frame)
        """
        b = self._bridges.get(drone_id)
        if not b:
            return {
                "ned_north": 0.0, "ned_east": 0.0, "ned_down": 0.0,
                "enu_east": 0.0, "enu_north": 0.0, "enu_up": 0.0,
            }
        
        tel = b.telemetry
        return {
            "ned_north": tel.get("ned_north", 0.0),
            "ned_east": tel.get("ned_east", 0.0),
            "ned_down": tel.get("ned_down", 0.0),
            "enu_east": tel.get("enu_east", 0.0),
            "enu_north": tel.get("enu_north", 0.0),
            "enu_up": tel.get("enu_up", 0.0),
        }
