"""
SITLContext — QML bridge for ArduPilot SITL lifecycle management.

Exposed to QML as context property 'sitl'.

Architecture:
  - All build/sim/gazebo commands open an external terminal window.
  - SITL stdout is piped into the in-panel console (sitlLogLine signal).
  - All lifecycle events are logged into the active TraceLogger session
    (trace_runs/<session>/ui_events.jsonl) as source="sitl".
  - Per-session sim_config.json is written when a trace session is active.

External terminal fallback chain (first found is used):
  gnome-terminal → xterm → konsole → xfce4-terminal → lxterminal → tilix

Signals (QML):
  sitlStatusChanged(str)       "stopped"|"starting"|"running"|"error"
  buildStatusChanged(str)      "idle"|"building"|"done"|"error"
  sitlLogLine(str)             one raw output line (panel console only)
  sitlInstancesChanged()       running instance list changed
  repoValidChanged(bool)       repo path validation result changed
  gazeboStatusChanged(str)     "stopped"|"running"|"error"
  logMessage(str, str)         (level, text) → global swarm log

Slots (QML):
  setRepoPath(path)            save + validate repo path
  getRepoPath() → str
  isRepoValid() → bool
  runBuild(board, vehicle)     open terminal: ./waf configure + ./waf <vehicle>
  runClean()                   open terminal: ./waf clean
  runDistclean()               open terminal: ./waf distclean
  launchSimVehicle(json)       open terminal: sim_vehicle.py
  launchSwarm(json)            open terminal: sim_vehicle.py (swarm)
  stopAll()                    SIGTERM all tracked terminal procs
  isRunning() → bool
  sitlStatus() → str
  runningInstances() → list
  launchGazebo(json)           open terminal: gz sim
  stopGazebo()
  isGazeboAvailable() → bool
  detectGazeboWorlds() → list
  isGstAvailable() → bool
  detectStreamingTopics() → list
  enableStreaming(topic)       gz topic -t … -p "data: 1"
  launchGstPreview(host, port) open terminal: gst-launch-1.0 …
  launchLidarViewer(topic)     open detached OpenCV LiDAR polar-plot window
  launchFlowViewer(topic)      open detached OpenCV flow-camera window
  launchSensorBridge(json)     start gz→MAVLink bridge as direct subprocess
  stopSensorBridge()           SIGTERM the running bridge process
  getBridgeStatus() → str      "stopped"|"running"|"error"
  applyBridgeParams(master)    send ArduPilot params via mavproxy one-shot
  launchMavproxy(json)         open terminal: mavproxy.py
  launchMavproxyWithJoystick() open terminal with joystick module
  launchMavproxyGraph(field)   open terminal with graph module
  isJoystickAvailable() → bool
  detectBinary(vehicle) → str  legacy compat
  availableVehicles() → list
  loadConfig() → str           JSON from ~/.config/skymeshx/sitl.json
  saveConfig(json)             persist to ~/.config/skymeshx/sitl.json
  getRecentTraceLogs(n) → list last n sitl events from active trace session
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QMetaObject, QObject, QTimer, Q_ARG, Qt, Signal, Slot


# ── Status constants ──────────────────────────────────────────────────────────
_S_STOPPED  = "stopped"
_S_STARTING = "starting"
_S_RUNNING  = "running"
_S_ERROR    = "error"
_B_IDLE     = "idle"
_B_BUILDING = "building"
_B_DONE     = "done"
_B_ERROR    = "error"

# Known vehicles: binary name → human label
_VEHICLES: Dict[str, str] = {
    "ArduCopter": "Copter (Multirotor)",
    "ArduPlane":  "Plane (Fixed-wing)",
    "ArduRover":  "Rover / Ground Vehicle",
    "ArduSub":    "Sub (Underwater)",
    "ArduHeli":   "Helicopter",
}

# Known parameters (subset for quick access in the Parameter tab)
# category drives the colour badge in Tab 4; keep categories consistent.
_SIM_PARAMS: Dict[str, dict] = {
    # ── Simulation ──────────────────────────────────────────────────────────
    "SIM_WIND_SPD":    {"default": 0,    "unit": "m/s",   "desc": "Wind speed",               "category": "SIM"},
    "SIM_WIND_DIR":    {"default": 0,    "unit": "deg",   "desc": "Wind direction (0=North)",  "category": "SIM"},
    "SIM_WIND_TURB":   {"default": 0,    "unit": "",      "desc": "Turbulence amplitude",      "category": "SIM"},
    "SIM_GPS_DELAY":   {"default": 1,    "unit": "ticks", "desc": "GPS delay",                 "category": "SIM"},
    "SIM_GPS_NOISE":   {"default": 0,    "unit": "m",     "desc": "GPS noise (sigma)",         "category": "SIM"},
    "SIM_GPS_GLITCH_X":{"default": 0,    "unit": "m",     "desc": "GPS glitch East",           "category": "SIM"},
    "SIM_GPS_GLITCH_Y":{"default": 0,    "unit": "m",     "desc": "GPS glitch North",          "category": "SIM"},
    "SIM_BARO_RND":    {"default": 0,    "unit": "Pa",    "desc": "Barometer noise",           "category": "SIM"},
    "SIM_BARO_COUNT":  {"default": 1,    "unit": "",      "desc": "Number of barometers",      "category": "SIM"},
    "SIM_DRIFT_SPEED": {"default": 0,    "unit": "m/s",   "desc": "Gyro drift speed",          "category": "SIM"},
    "SIM_RATE_HZ":     {"default": 1200, "unit": "Hz",    "desc": "Simulation rate",           "category": "SIM"},
    "SIM_SONAR_SCALE": {"default": 1,    "unit": "",      "desc": "Rangefinder scale",         "category": "SIM"},
    "SIM_ACCEL_RND":   {"default": 0,    "unit": "m/s/s", "desc": "Accelerometer noise",       "category": "SIM"},
    "SIM_GYRO_RND":    {"default": 0,    "unit": "deg/s", "desc": "Gyro noise",                "category": "SIM"},
    "SIM_SPEEDUP":     {"default": 1,    "unit": "×",     "desc": "Simulation speedup",        "category": "SIM"},
    # ── Frame (critical for PreArm: Motors check) ───────────────────────────
    # FRAME_CLASS: 1=Quad, 2=Hexa, 3=Octa, 4=OctaQuad, 7=Tri, 13=Heli
    "FRAME_CLASS":     {"default": 1,    "unit": "",      "desc": "Frame class  (1=Quad, 2=Hexa, 3=Octa, 7=Tri)", "category": "FRAME"},
    # FRAME_TYPE: 0=Plus, 1=X, 2=V, 3=H, 12=BetaFlightX
    "FRAME_TYPE":      {"default": 1,    "unit": "",      "desc": "Frame type   (0=Plus, 1=X, 2=V, 3=H)",         "category": "FRAME"},
    # ── Compass ─────────────────────────────────────────────────────────────
    "COMPASS_ENABLE":  {"default": 1,    "unit": "",      "desc": "Enable compass",            "category": "COMPASS"},
    "COMPASS_EXTERNAL":{"default": 0,    "unit": "",      "desc": "External compass",          "category": "COMPASS"},
    # ── Rangefinder ─────────────────────────────────────────────────────────
    "RNGFND1_TYPE":    {"default": 0,    "unit": "",      "desc": "Rangefinder type (10=sim)", "category": "RNGFND"},
    "RNGFND1_MAX_CM":  {"default": 4000, "unit": "cm",    "desc": "Rangefinder max range",     "category": "RNGFND"},
    "RNGFND1_MIN_CM":  {"default": 0,    "unit": "cm",    "desc": "Rangefinder min range",     "category": "RNGFND"},
    # ── Barometer ───────────────────────────────────────────────────────────
    "BARO_FIELD_ELV":  {"default": 0,    "unit": "m",     "desc": "Baro field elevation",      "category": "BARO"},
    # ── Camera / Mount ──────────────────────────────────────────────────────
    "CAM_TRIGG_TYPE":  {"default": 0,    "unit": "",      "desc": "Camera trigger type",       "category": "CAM"},
    "MNT_TYPE":        {"default": 0,    "unit": "",      "desc": "Mount type (1=servo)",      "category": "MNT"},
    "MNT_DEFLT_MODE":  {"default": 0,    "unit": "",      "desc": "Mount default mode",        "category": "MNT"},
}

# ── PreArm fix scripts — sequences sent as MAVProxy script files ──────────────
# Each entry: {"id", "label", "desc", "commands": [str]}
# Triggered from Debug tab → opens MAVProxy with --script=<tempfile>
_PREARM_FIXES: List[dict] = [
    {
        "id":       "frame_class_type",
        "label":    "PreArm: Motors — Frame Class/Type",
        "desc":     "PreArm: Motors: Check frame class and type\n"
                    "→ setzt FRAME_CLASS=1 (Quad) + FRAME_TYPE=1 (X) und rebootet",
        "commands": [
            "param set FRAME_CLASS 1",
            "param set FRAME_TYPE 1",
            "reboot",
        ],
    },
    {
        "id":       "accel_cal",
        "label":    "PreArm: Accel — Not Calibrated",
        "desc":     "PreArm: Accels not calibrated\n→ erzwingt IMU-Kalibrierung (SITL)",
        "commands": [
            "param set INS_ACCEL_ERROR_THRESHOLD 3",
            "accelcalsimple",
        ],
    },
    {
        "id":       "compass_not_healthy",
        "label":    "PreArm: Compass — Not Healthy",
        "desc":     "PreArm: Compass not healthy\n→ deaktiviert Compass (SITL ohne Magnetometer)",
        "commands": [
            "param set ARMING_CHECK 0",
        ],
    },
    {
        "id":       "arming_check_off",
        "label":    "Arming Checks deaktivieren",
        "desc":     "Alle Arming-Checks ausschalten (nur für SITL-Tests)\n→ ARMING_CHECK=0",
        "commands": [
            "param set ARMING_CHECK 0",
        ],
    },
    {
        "id":       "arming_check_on",
        "label":    "Arming Checks zurücksetzen",
        "desc":     "Arming-Checks wieder einschalten\n→ ARMING_CHECK=1",
        "commands": [
            "param set ARMING_CHECK 1",
        ],
    },
    {
        "id":       "guided_takeoff",
        "label":    "GUIDED → Arm → Takeoff 10m",
        "desc":     "Schnell-Sequenz: Mode GUIDED, arm throttle, takeoff 10",
        "commands": [
            "mode guided",
            "arm throttle",
            "takeoff 10",
        ],
    },
]

# Peripheral device catalogue (what can be toggled in Tab 3)
_PERIPHERAL_CATALOGUE: List[dict] = [
    # --- Sensors ---
    {"id": "gps2",     "label": "2nd GPS",         "category": "sensor",
     "hint": "SIM_GPS2_ENABLE=1",
     "params": {"SIM_GPS2_ENABLE": 1}},
    {"id": "lidar",    "label": "Lidar / Rangefinder", "category": "sensor",
     "hint": "SIM_SONAR_SCALE + RNGFND1_TYPE=10",
     "params": {"RNGFND1_TYPE": 10, "RNGFND1_MAX_CM": 4000, "SIM_SONAR_SCALE": 1}},
    {"id": "baro2",    "label": "2nd Barometer",    "category": "sensor",
     "hint": "SIM_BARO_COUNT=2",
     "params": {"SIM_BARO_COUNT": 2}},
    {"id": "compass2", "label": "2nd Compass (ext)", "category": "sensor",
     "hint": "COMPASS_EXTERNAL=1 — restart required",
     "params": {"COMPASS_EXTERNAL": 1}},
    # --- Environment ---
    {"id": "wind",     "label": "Wind",             "category": "environment",
     "hint": "SIM_WIND_SPD + SIM_WIND_DIR + SIM_WIND_TURB",
     "params": {"SIM_WIND_SPD": 5, "SIM_WIND_DIR": 180, "SIM_WIND_TURB": 0}},
    # --- Camera / Display ---
    {"id": "osd",      "label": "OSD (on-screen display)", "category": "display",
     "hint": "--osd flag (restart required)",
     "params": {}},
    {"id": "gimbal",   "label": "Gimbal (2-axis)",  "category": "camera",
     "hint": "MNT_TYPE=1 + SIM_RATE_HZ=200",
     "params": {"MNT_TYPE": 1, "SIM_RATE_HZ": 200}},
    {"id": "camera",   "label": "Camera Trigger",   "category": "camera",
     "hint": "CAM_TRIGG_TYPE=1",
     "params": {"CAM_TRIGG_TYPE": 1}},
]

# SITL binary search paths (in priority order)
_SITL_SEARCH: List[Path] = [
    Path.home() / "ardupilot" / "build" / "sitl" / "bin",
    Path.home() / "ardupilot" / "Tools" / "autotest",
    Path("/usr/local/bin"),
    Path("/opt/ardupilot/bin"),
]

# External terminal candidates: (name, argv_template)
# {title} and {script} are filled in at call time.
_TERMINAL_CANDIDATES: List[Tuple[str, List[str]]] = [
    ("gnome-terminal", ["gnome-terminal", "--title={title}", "--", "bash", "-c", "{script}"]),
    ("xterm",          ["xterm", "-T", "{title}", "-e", "bash", "-c", "{script}"]),
    ("konsole",        ["konsole", "--title", "{title}", "-e", "bash", "-c", "{script}"]),
    ("xfce4-terminal", ["xfce4-terminal", "--title={title}", "-e", "bash -c '{script}'"]),
    ("lxterminal",     ["lxterminal", "--title={title}", "-e", "bash -c '{script}'"]),
    ("tilix",          ["tilix", "-t", "{title}", "-e", "bash -c '{script}'"]),
]

# Config + trace file paths
_CONFIG_PATH = Path.home() / ".config" / "skymeshx" / "sitl.json"


def _find_sim_vehicle(repo_path: str) -> str:
    """Return path to sim_vehicle.py or '' if not found."""
    candidates = [
        Path(repo_path) / "Tools" / "autotest" / "sim_vehicle.py",
        Path.home() / "ardupilot" / "Tools" / "autotest" / "sim_vehicle.py",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    found = shutil.which("sim_vehicle.py")
    return found or ""


def _find_binary(vehicle: str, repo_path: str = "") -> str:
    """Return the SITL binary path for `vehicle`, or ''."""
    search = list(_SITL_SEARCH)
    if repo_path:
        search.insert(0, Path(repo_path) / "build" / "sitl" / "bin")
    for base in search:
        candidate = base / vehicle
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which(vehicle) or ""


def _validate_repo(path: str) -> bool:
    """Return True if path looks like a valid ArduPilot checkout."""
    p = Path(path)
    return (
        (p / "Tools" / "autotest" / "sim_vehicle.py").exists()
        and (p / "wscript").exists()
    )


def _default_config() -> dict:
    return {
        "repo_path": str(Path.home() / "ardupilot"),
        "build": {"board": "sitl", "vehicle": "copter"},
        "sim": {
            "vehicle": "ArduCopter",
            "frame": "",
            "location": "CMAC",
            "speedup": 1,
            "protocol": "tcp",
            "tcp_port": 5760,
            "udp_host": "127.0.0.1",
            "udp_port": 14550,
            "use_map": False,
            "use_console": False,
            "no_mavproxy": False,
            "wipe": False,
            "extra_args": "",
        },
        "swarm": {
            "count": 5,
            "vehicle": "ArduCopter",
            "auto_sysid": True,
            "mcast": True,
            "location": "CMAC",
            "offset_mode": "line",
            "offset_heading": 90,
            "offset_spacing": 10,
            "swarm_file": "",
        },
        "gazebo": {
            "world": "iris_runway.sdf",
            "verbosity": 4,
            "use_json_model": True,
            "vehicle": "ArduCopter",
            "frame": "gazebo-iris",
            "stream_host": "127.0.0.1",
            "stream_port": 5600,
            # Working directory for `gz sim`; the worlds/ path is relative to this.
            # Must contain ardupilot_gazebo/worlds/ (or worlds/ directly).
            "gz_ws_path": str(Path.home() / "gz_ws" / "src"),
        },
    }


def _gz_env_prefix() -> str:
    """Return bash lines that source the Gazebo environment if not already active.

    When the viewer is launched from a GUI terminal (gnome-terminal etc.) it
    inherits the desktop environment, which usually does NOT have gz.transport
    on PYTHONPATH or LD_LIBRARY_PATH.  We probe the most common setup files in
    priority order and source the first one that exists.

    Returns a multi-line bash string (may be empty if nothing is found).
    """
    # Candidate setup files in priority order
    candidates: List[Path] = [
        # Colcon workspace install (most common for gz_ws)
        Path.home() / "gz_ws" / "install" / "setup.bash",
        # ROS2 workspace that also installs gz
        Path.home() / "ros2_ws" / "install" / "setup.bash",
        # System-wide Gazebo Harmonic
        Path("/opt/gz/harmonic/setup.bash"),
        Path("/usr/share/gazebo/setup.bash"),
        Path("/usr/share/gz/gz-transport13/setup.bash"),
    ]
    # Also honour any setup file already on GZ_SETUP_FILE env override
    env_override = os.environ.get("GZ_SETUP_FILE", "")
    if env_override:
        candidates.insert(0, Path(env_override))

    lines: List[str] = []
    for p in candidates:
        if p.exists():
            lines.append(f'source {shlex.quote(str(p))}\n')
            break  # one is enough

    # Propagate GZ_* env vars from the parent process if set
    for var in ("GZ_PARTITION", "GZ_IP", "GZ_RELAY", "GZ_VERSION",
                "PYTHONPATH", "LD_LIBRARY_PATH"):
        val = os.environ.get(var)
        if val:
            lines.append(f'export {var}={shlex.quote(val)}\n')

    return "".join(lines)


def _gz_build_env() -> dict:
    """Build an environment dict for directly launching viewer sub-processes.

    Inherits the current process environment and overlays GZ_* variables and
    any sourced setup file's PYTHONPATH / LD_LIBRARY_PATH so that
    gz.transport13 is importable without a shell wrapper.
    """
    env = os.environ.copy()

    # Source the first Gazebo setup file we find via a child bash and capture
    # the resulting env — this is the only reliable way to pick up colcon paths.
    candidates: List[Path] = [
        Path.home() / "gz_ws" / "install" / "setup.bash",
        Path.home() / "ros2_ws" / "install" / "setup.bash",
        Path("/opt/gz/harmonic/setup.bash"),
        Path("/usr/share/gazebo/setup.bash"),
        Path("/usr/share/gz/gz-transport13/setup.bash"),
    ]
    env_override = os.environ.get("GZ_SETUP_FILE", "")
    if env_override:
        candidates.insert(0, Path(env_override))

    for p in candidates:
        if p.exists():
            try:
                result = subprocess.run(
                    ["bash", "-c", f'source {shlex.quote(str(p))} && env'],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.splitlines():
                    if "=" in line:
                        k, _, v = line.partition("=")
                        env[k] = v
            except Exception:
                pass
            break

    return env


class _PeripheralDevice:
    """One enabled peripheral device with its active parameter overrides."""

    def __init__(self, device_id: str, config: dict) -> None:
        self.device_id = device_id
        self.config    = config   # {"enabled": bool, "params": {name: value}}


class _TrackedProc:
    """One tracked external process (terminal or background)."""

    def __init__(self, label: str, proc: subprocess.Popen):
        self.label   = label
        self.proc    = proc
        self.started = time.time()


class SITLContext(QObject):
    """QObject bridge for ArduPilot SITL lifecycle."""

    # ── Signals ───────────────────────────────────────────────────────────────
    sitlStatusChanged        = Signal(str)
    buildStatusChanged       = Signal(str)
    sitlLogLine              = Signal(str)
    sitlInstancesChanged     = Signal()
    repoValidChanged         = Signal(bool)
    gazeboStatusChanged      = Signal(str)
    logMessage               = Signal(str, str)   # (level, text) → swarm log
    peripheralDevicesChanged = Signal()
    paramChanged             = Signal(str, str)   # (name, value)
    # Fired after terminal opens — payload: list of {id, connection_string}
    # Listeners (service_locator.wire) use this to auto-connect drones.
    autoConnectReady         = Signal("QVariantList")
    # Fired when user toggles a sensor overlay (lidar/flow) from the SITL panel.
    # QML MapView listens to this to show/hide the matching overlay.
    sensorOverlayToggled     = Signal(str, bool)  # (sensor_type, visible)
    # gz.transport live frames — base64-encoded JPEG, emitted at ~5 Hz.
    # QML uses: Image { source: "data:image/jpeg;base64," + payload }
    lidarFrameReady          = Signal(str)
    flowFrameReady           = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._lock          = threading.Lock()
        self._sim_status    = _S_STOPPED
        self._build_status  = _B_IDLE
        self._gazebo_status = _S_STOPPED
        self._repo_valid    = False
        self._procs:  List[_TrackedProc] = []   # all tracked terminal procs
        self._viewer_procs: List[_TrackedProc] = []  # detached viewer windows

        # Per-instance tracking for the "running instances" list
        # Each entry: {"index": i, "vehicle": str, "port": int, "started": float}
        self._instances: List[dict] = []

        # Peripheral devices: device_id → {"enabled": bool, "params": {…}}
        self._peripheral_devices: Dict[str, dict] = {}

        # Pending parameter overrides (applied on next MAVProxy start)
        self._pending_params: Dict[str, str] = {}

        # gz.transport in-process subscription state
        # Two separate Nodes to prevent callback mixing between topics
        self._gz_node_lidar:    Any = None
        self._gz_node_flow:     Any = None
        self._gz_lidar_active:  bool = False
        self._gz_flow_active:   bool = False
        # Latest rendered JPEG-Base64 frames (written by bg thread, read by QTimer)
        self._gz_lidar_data:    Optional[str] = None   # base64 string or None
        self._gz_flow_data:     Optional[dict] = None  # {"_prev_gray": …, "_b64": str|None}
        self._gz_lock           = threading.Lock()
        # Track last emitted b64 to skip unchanged frames (reduces flicker)
        self._gz_lidar_last:    str = ""
        # Sensor bridge subprocess
        self._bridge_proc: Optional[subprocess.Popen] = None
        self._bridge_status: str = "stopped"   # "stopped"|"running"|"error"
        self._gz_flow_last:     str = ""

        # Load persisted config
        self._cfg = _default_config()
        self._load_config_from_disk()

        # Watchdog: poll tracked procs every 3 s
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(3000)
        self._watchdog.timeout.connect(self._poll_procs)
        self._watchdog.start()

        # gz overlay poller: emit lidarFrameReady / flowFrameReady at ~8 Hz
        self._gz_poller = QTimer(self)
        self._gz_poller.setInterval(125)
        self._gz_poller.timeout.connect(self._poll_gz_data)
        self._gz_poller.start()

    # ─────────────────────────────────────────────────────────────────────────
    # Repo management
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(str)
    def setRepoPath(self, path: str) -> None:
        path = path.strip()
        self._cfg["repo_path"] = path
        valid = _validate_repo(path)
        self._repo_valid = valid
        self.repoValidChanged.emit(valid)
        self._save_config_to_disk()
        self._trace("repo_set", {"path": path, "valid": valid})
        self._log("INFO", f"[SITL] Repo path set: {path} ({'valid' if valid else 'NOT valid'})")

    @Slot(result=str)
    def getRepoPath(self) -> str:
        return self._cfg.get("repo_path", "")

    @Slot(result=bool)
    def isRepoValid(self) -> bool:
        return _validate_repo(self._cfg.get("repo_path", ""))

    @Slot(result=str)
    def detectSimVehicle(self) -> str:
        return _find_sim_vehicle(self._cfg.get("repo_path", ""))

    # ─────────────────────────────────────────────────────────────────────────
    # Build
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(str, str)
    def runBuild(self, board: str, vehicle: str) -> None:
        """Open a terminal window running ./waf configure + ./waf <vehicle>."""
        repo = self._cfg.get("repo_path", "")
        if not repo:
            self._log("ERROR", "[SITL] Repo path not set — cannot build")
            return

        board   = board.strip()   or "sitl"
        vehicle = vehicle.strip() or "copter"

        script = (
            f'set -e\n'
            f'cd {shlex.quote(repo)}\n'
            f'echo "=== ./waf configure --board {board} ==="\n'
            f'./waf configure --board {shlex.quote(board)}\n'
            f'echo "=== ./waf {vehicle} ==="\n'
            f'./waf {shlex.quote(vehicle)}\n'
            f'echo ""\n'
            f'echo "━━━ BUILD DONE — press ENTER to close ━━━"\n'
            f'read\n'
        )
        cmd = f"./waf configure --board {board} && ./waf {vehicle}"
        self._trace("build_start", {"board": board, "vehicle": vehicle, "cmd": cmd, "repo": repo})
        self._log("INFO", f"[SITL] Build started: {cmd}")
        self._set_build_status(_B_BUILDING)

        proc = self._open_terminal(script, title=f"ArduPilot Build — {vehicle}")
        if proc:
            self._cfg.setdefault("build", {}).update({"board": board, "vehicle": vehicle})
            self._save_config_to_disk()
        else:
            self._set_build_status(_B_ERROR)

    @Slot()
    def runClean(self) -> None:
        repo = self._cfg.get("repo_path", "")
        if not repo:
            self._log("ERROR", "[SITL] Repo path not set")
            return
        script = (
            f'cd {shlex.quote(repo)}\n'
            f'./waf clean\n'
            f'echo "━━━ CLEAN DONE ━━━" ; read\n'
        )
        self._trace("build_clean", {"repo": repo})
        self._log("INFO", "[SITL] Running ./waf clean")
        self._open_terminal(script, title="ArduPilot Clean")

    @Slot()
    def runDistclean(self) -> None:
        repo = self._cfg.get("repo_path", "")
        if not repo:
            self._log("ERROR", "[SITL] Repo path not set")
            return
        script = (
            f'cd {shlex.quote(repo)}\n'
            f'./waf distclean\n'
            f'echo "━━━ DISTCLEAN DONE ━━━" ; read\n'
        )
        self._trace("build_distclean", {"repo": repo})
        self._log("INFO", "[SITL] Running ./waf distclean")
        self._open_terminal(script, title="ArduPilot Distclean")

    @Slot(result=str)
    def buildStatus(self) -> str:
        return self._build_status

    # ─────────────────────────────────────────────────────────────────────────
    # Sim Vehicle launch
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(str)
    def launchSimVehicle(self, config_json: str) -> None:
        """
        Build a sim_vehicle.py command from config_json and open it in a
        terminal. Config keys (all optional, defaults from saved config):
          vehicle, frame, location, speedup, protocol, tcp_port,
          udp_host, udp_port, use_map, use_console, no_mavproxy,
          wipe, extra_args
        """
        try:
            cfg = json.loads(config_json)
        except Exception as exc:
            self._log("ERROR", f"[SITL] Invalid config JSON: {exc}")
            return

        sim_vehicle = _find_sim_vehicle(self._cfg.get("repo_path", ""))
        if not sim_vehicle:
            self._log("ERROR",
                "[SITL] sim_vehicle.py not found. "
                "Set the repo path in the Setup tab first.")
            self._set_sim_status(_S_ERROR)
            return

        vehicle     = cfg.get("vehicle",     "ArduCopter")
        frame       = cfg.get("frame",       "").strip()
        location    = cfg.get("location",    "CMAC").strip()
        speedup     = int(cfg.get("speedup", 1))
        protocol    = cfg.get("protocol",    "tcp")
        tcp_port    = int(cfg.get("tcp_port", 5760))
        udp_host    = cfg.get("udp_host",    "127.0.0.1")
        udp_port    = int(cfg.get("udp_port", 14550))
        use_map     = bool(cfg.get("use_map",     False))
        use_console = bool(cfg.get("use_console", False))
        no_mavproxy = bool(cfg.get("no_mavproxy", False))
        wipe        = bool(cfg.get("wipe",         False))
        extra_args  = cfg.get("extra_args", "").strip()

        cmd_parts = [f"python3 {shlex.quote(sim_vehicle)}", f"-v {shlex.quote(vehicle)}"]
        if frame:
            cmd_parts.append(f"-f {shlex.quote(frame)}")
        if location:
            cmd_parts.append(f"--location {shlex.quote(location)}")
        if speedup != 1:
            cmd_parts.append(f"--speedup {speedup}")
        if use_map and not no_mavproxy:
            cmd_parts.append("--map")
        if use_console and not no_mavproxy:
            cmd_parts.append("--console")
        if no_mavproxy:
            cmd_parts.append("--no-mavproxy")
        if wipe:
            cmd_parts.append("--wipe-eeprom")

        # GCS connection
        # sim_vehicle.py -A passes its value as a single string to MAVProxy/ardupilot.
        # The value must be a single shell token — use single-quotes inside the script
        # so bash passes it as one argument (double-quotes get stripped by bash -c).
        if protocol == "udp":
            cmd_parts.append(f"-A '--serial0=udpclient:{udp_host}:{udp_port}'")
        elif no_mavproxy:
            # listening TCP — GCS connects to port
            cmd_parts.append(f"-A '--serial0=tcp:{tcp_port}'")

        if extra_args:
            cmd_parts.append(extra_args)

        full_cmd = " ".join(cmd_parts)
        script = (
            f'cd {shlex.quote(self._cfg.get("repo_path", str(Path.home() / "ardupilot")))}\n'
            f'echo "=== ArduPilot SITL ==="\n'
            f'echo "{full_cmd}"\n'
            f'echo ""\n'
            f'{full_cmd}\n'
            f'echo "--- SITL exited ---" ; read\n'
        )

        self._trace("sim_start", {
            "vehicle": vehicle, "frame": frame, "location": location,
            "protocol": protocol, "port": tcp_port if protocol == "tcp" else udp_port,
            "no_mavproxy": no_mavproxy, "cmd": full_cmd,
        })
        self._log("INFO", f"[SITL] Launching: {full_cmd}")

        proc = self._open_terminal(script, title=f"SITL — {vehicle}")
        if proc:
            with self._lock:
                self._instances = [{"index": 0, "vehicle": vehicle,
                                    "port": tcp_port, "started": time.time()}]
            self._set_sim_status(_S_RUNNING)
            self.sitlInstancesChanged.emit()

            # Auto-connect: build endpoint based on chosen protocol.
            # Serial 0 = tcp_port (5760)  → MAVProxy/GCS telemetry
            # Serial 1 = tcp_port + 2     → direct GCS connection (5762)
            # We connect to Serial 1 so GCS doesn't conflict with MAVProxy.
            if protocol == "udp":
                endpoint = f"udpin:0.0.0.0:{udp_port}"
            else:
                # Use Serial 1 port (base + 2) for direct GCS connection
                endpoint = f"tcp:127.0.0.1:{tcp_port + 2}"
            self._schedule_auto_connect([
                {"id": "sitl_1", "connection_string": endpoint}
            ])

            # Save last sim config
            self._cfg["sim"].update(cfg)
            self._save_config_to_disk()
        else:
            self._set_sim_status(_S_ERROR)

    # ─────────────────────────────────────────────────────────────────────────
    # Swarm launch
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(str)
    def launchSwarm(self, config_json: str) -> None:
        """
        Launch multi-vehicle SITL. Config keys:
          vehicle, count, auto_sysid, mcast, location,
          offset_mode ("line"|"file"), offset_heading, offset_spacing,
          swarm_file, use_map, use_console, extra_args
        """
        try:
            cfg = json.loads(config_json)
        except Exception as exc:
            self._log("ERROR", f"[SITL] Invalid swarm config: {exc}")
            return

        sim_vehicle = _find_sim_vehicle(self._cfg.get("repo_path", ""))
        if not sim_vehicle:
            self._log("ERROR", "[SITL] sim_vehicle.py not found.")
            self._set_sim_status(_S_ERROR)
            return

        vehicle     = cfg.get("vehicle",        "ArduCopter")
        count       = int(cfg.get("count",       5))
        auto_sysid  = bool(cfg.get("auto_sysid", True))
        mcast       = bool(cfg.get("mcast",      True))
        location    = cfg.get("location",        "CMAC")
        offset_mode = cfg.get("offset_mode",     "line")
        heading     = int(cfg.get("offset_heading", 90))
        spacing     = int(cfg.get("offset_spacing", 10))
        swarm_file  = cfg.get("swarm_file",      "")
        use_map     = bool(cfg.get("use_map",     False))
        use_console = bool(cfg.get("use_console", False))
        extra_args  = cfg.get("extra_args",      "").strip()

        cmd_parts = [
            f"python3 {shlex.quote(sim_vehicle)}",
            f"-v {shlex.quote(vehicle)}",
            f"--count {count}",
            f"--location {shlex.quote(location)}",
        ]
        if auto_sysid:
            cmd_parts.append("--auto-sysid")
        if mcast:
            cmd_parts.append("--mcast")
        if use_map:
            cmd_parts.append("--map")
        if use_console:
            cmd_parts.append("--console")
        if offset_mode == "line":
            cmd_parts.append(f"--auto-offset-line {heading},{spacing}")
        elif offset_mode == "file" and swarm_file:
            cmd_parts.append(f"--swarm {shlex.quote(swarm_file)}")
        if extra_args:
            cmd_parts.append(extra_args)

        full_cmd = " \\\n  ".join(cmd_parts)
        script = (
            f'cd {shlex.quote(self._cfg.get("repo_path", str(Path.home() / "ardupilot")))}\n'
            f'echo "=== ArduPilot SITL Swarm ({count}× {vehicle}) ==="\n'
            f'{" ".join(cmd_parts)}\n'
            f'echo "--- Swarm exited ---" ; read\n'
        )

        self._trace("swarm_start", {
            "vehicle": vehicle, "count": count, "location": location,
            "auto_sysid": auto_sysid, "mcast": mcast,
            "offset_mode": offset_mode, "cmd": " ".join(cmd_parts),
        })
        self._log("INFO", f"[SITL] Swarm ({count}× {vehicle}): {' '.join(cmd_parts[:4])}…")

        proc = self._open_terminal(script, title=f"SITL Swarm — {count}× {vehicle}")
        if proc:
            with self._lock:
                self._instances = [
                    {"index": i, "vehicle": vehicle,
                     "port": 5760 + i * 10, "started": time.time()}
                    for i in range(count)
                ]
            self._set_sim_status(_S_RUNNING)
            self.sitlInstancesChanged.emit()
            self._cfg["swarm"].update(cfg)
            self._save_config_to_disk()

            # Auto-connect all swarm instances via Serial 1.
            # ArduPilot SITL serial port layout (per instance, step=10):
            #   Serial 0: 5760 + i*10  (MAVProxy)
            #   Serial 1: 5762 + i*10  (direct GCS — used here)
            #   Serial 2: 5763 + i*10
            connections = [
                {"id": f"sitl_{i + 1}",
                 "connection_string": f"tcp:127.0.0.1:{5762 + i * 10}"}
                for i in range(count)
            ]
            self._schedule_auto_connect(connections)
        else:
            self._set_sim_status(_S_ERROR)

    # ─────────────────────────────────────────────────────────────────────────
    # Stop
    # ─────────────────────────────────────────────────────────────────────────

    @Slot()
    def stopAll(self) -> None:
        with self._lock:
            procs = list(self._procs) + list(self._viewer_procs)
        for tp in procs:
            try:
                tp.proc.terminate()
                try:
                    tp.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    tp.proc.kill()
            except Exception:
                pass
        with self._lock:
            self._procs.clear()
            self._viewer_procs.clear()
            self._instances.clear()
        # Reset overlay state
        self._gz_lidar_active = False
        self._gz_flow_active  = False
        with self._gz_lock:
            self._gz_lidar_data = None
            self._gz_flow_data  = None
            self._gz_lidar_last = ""
            self._gz_flow_last  = ""
        self._set_sim_status(_S_STOPPED)
        self.sitlInstancesChanged.emit()
        self._trace("sim_stop", {"reason": "user_stop_all"})
        self._log("INFO", "[SITL] All processes stopped.")

    @Slot()
    def stopViewers(self) -> None:
        """Close all detached sensor-viewer processes (LiDAR / Flow OpenCV windows)."""
        with self._lock:
            procs = list(self._viewer_procs)
        for tp in procs:
            try:
                tp.proc.terminate()
                try:
                    tp.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    tp.proc.kill()
            except Exception:
                pass
        with self._lock:
            self._viewer_procs.clear()
        # Also deactivate in-process overlays and clear caches so map overlay
        # goes back to "no data" state when viewers are stopped externally.
        self._gz_lidar_active = False
        self._gz_flow_active  = False
        with self._gz_lock:
            self._gz_lidar_data = None
            self._gz_flow_data  = None
            self._gz_lidar_last = ""
            self._gz_flow_last  = ""
        self._log("INFO", "[SITL] Viewer windows closed.")

    @Slot(str, bool)
    def setSensorOverlay(self, sensor_type: str, visible: bool) -> None:
        """Toggle a sensor overlay on the map (lidar or flow).

        Emits sensorOverlayToggled(sensor_type, visible) which MapView.qml
        handles to show/hide the matching overlay panel.
        Also starts/stops the in-process gz.transport subscription so the
        overlay gets live data without needing MAVLink OBSTACLE_DISTANCE.
        """
        self.sensorOverlayToggled.emit(sensor_type, visible)
        self._log("INFO", f"[SITL] Sensor overlay '{sensor_type}' → {'on' if visible else 'off'}")
        if visible:
            self._gz_subscribe(sensor_type)
        else:
            self._gz_unsubscribe(sensor_type)

    # ─────────────────────────────────────────────────────────────────────────
    # gz.transport in-process subscriptions for map overlays
    # ─────────────────────────────────────────────────────────────────────────

    def _gz_make_node(self) -> Any:
        """Create a fresh gz.transport Node. Returns None if unavailable."""
        try:
            from gz.transport13 import Node as GzNode  # noqa: PLC0415
            return GzNode()
        except Exception as exc:
            self._log("WARN", f"[SITL] gz.transport13 not available: {exc}")
            return None

    def _gz_subscribe(self, sensor_type: str) -> None:
        if sensor_type == "lidar" and not self._gz_lidar_active:
            if self._gz_node_lidar is None:
                self._gz_node_lidar = self._gz_make_node()
            if self._gz_node_lidar is None:
                return
            try:
                from gz.msgs10.laserscan_pb2 import LaserScan  # noqa: PLC0415
                topic = "/lidar/scan"
                ok = self._gz_node_lidar.subscribe(LaserScan, topic, self._gz_lidar_cb)
                if ok:
                    self._gz_lidar_active = True
                    self._log("INFO", f"[SITL] gz subscribed: {topic}")
                else:
                    self._log("WARN", f"[SITL] gz subscribe failed: {topic}")
            except Exception as exc:
                self._log("WARN", f"[SITL] gz lidar subscribe error: {exc}")

        elif sensor_type == "flow" and not self._gz_flow_active:
            if self._gz_node_flow is None:
                self._gz_node_flow = self._gz_make_node()
            if self._gz_node_flow is None:
                return
            try:
                from gz.msgs10.image_pb2 import Image  # noqa: PLC0415
                topic = "/flow_camera/image"
                ok = self._gz_node_flow.subscribe(Image, topic, self._gz_flow_cb)
                if ok:
                    self._gz_flow_active = True
                    self._log("INFO", f"[SITL] gz subscribed: {topic}")
                else:
                    self._log("WARN", f"[SITL] gz subscribe failed: {topic}")
            except Exception as exc:
                self._log("WARN", f"[SITL] gz flow subscribe error: {exc}")

    def _gz_unsubscribe(self, sensor_type: str) -> None:
        # gz.transport13 Node has no unsubscribe — just clear the active flag
        # and drop cached data so the overlay goes back to "no data" state.
        if sensor_type == "lidar":
            self._gz_lidar_active = False
            with self._gz_lock:
                self._gz_lidar_data = None
        elif sensor_type == "flow":
            self._gz_flow_active = False
            with self._gz_lock:
                self._gz_flow_data = None

    def _gz_lidar_cb(self, msg: Any) -> None:
        """gz.transport callback — renders the LiDAR frame with OpenCV (identical
        to lidar_viewer.py) and stores the JPEG-Base64 string."""
        try:
            import base64  # noqa: PLC0415
            import math as _math  # noqa: PLC0415
            import cv2          # noqa: PLC0415
            import numpy as np  # noqa: PLC0415

            ranges = np.asarray(msg.ranges, dtype=np.float32)
            if ranges.size == 0:
                return

            angle_min  = float(msg.angle_min)
            angle_max  = float(msg.angle_max)
            angle_step = float(msg.angle_step)
            if abs(angle_step) > 1e-12:
                angles = angle_min + np.arange(ranges.size, dtype=np.float32) * angle_step
            else:
                angles = np.linspace(angle_min, angle_max, ranges.size, dtype=np.float32)

            range_min    = float(msg.range_min)
            range_max    = float(msg.range_max)
            display_range = range_max
            valid = np.isfinite(ranges) & (ranges >= range_min) & (ranges <= range_max)
            shown_angles = angles[valid]
            shown_ranges = ranges[valid]

            # ── Render exactly like lidar_viewer.py ──────────────────────────
            W = 300; cx = W // 2; cy = W // 2
            radius = int(W * 0.44)
            canvas = np.zeros((W, W, 3), dtype=np.uint8)

            # Grid
            for frac in (0.25, 0.5, 0.75, 1.0):
                r = int(radius * frac)
                cv2.circle(canvas, (cx, cy), r, (70, 70, 70), 1)
                label = f"{display_range * frac:.0f}m"
                cv2.putText(canvas, label, (cx + 4, cy - r + 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, (130, 130, 130), 1)
            cv2.line(canvas, (cx - radius, cy), (cx + radius, cy), (70, 70, 70), 1)
            cv2.line(canvas, (cx, cy - radius), (cx, cy + radius), (70, 70, 70), 1)

            # Drone marker + forward arrow
            cv2.circle(canvas, (cx, cy), 5, (0, 255, 255), -1)
            cv2.arrowedLine(canvas, (cx, cy), (cx + 25, cy), (0, 255, 255), 1, tipLength=0.3)

            # LiDAR points
            if shown_ranges.size > 0:
                scale = radius / display_range
                x  = shown_ranges * np.cos(shown_angles)
                y  = shown_ranges * np.sin(shown_angles)
                px = (cx + x * scale).astype(np.int32)
                py = (cy - y * scale).astype(np.int32)
                for xi, yi in zip(px, py):
                    if 0 <= xi < W and 0 <= yi < W:
                        cv2.circle(canvas, (int(xi), int(yi)), 2, (0, 255, 0), -1)

                ni     = int(np.argmin(shown_ranges))
                status = (f"{shown_ranges.size}pts "
                          f"min={shown_ranges[ni]:.1f}m")
                cv2.putText(canvas, status, (4, 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
            else:
                cv2.putText(canvas, "Warte auf LiDAR...", (10, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            ok, buf = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                return
            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            with self._gz_lock:
                self._gz_lidar_data = b64
        except Exception:
            pass

    def _gz_flow_cb(self, msg: Any) -> None:
        """gz.transport callback — renders the flow frame with OpenCV (identical
        to flow_viewer.py) and stores the JPEG-Base64 string."""
        try:
            import base64  # noqa: PLC0415
            import cv2      # noqa: PLC0415
            import numpy as np  # noqa: PLC0415

            width  = int(msg.width)
            height = int(msg.height)
            if width <= 0 or height <= 0 or not msg.data:
                return

            raw = np.frombuffer(msg.data, dtype=np.uint8)
            rgb_size  = width * height * 3
            rgba_size = width * height * 4
            gray_size = width * height

            if raw.size >= rgba_size:
                rgba  = raw[:rgba_size].reshape((height, width, 4))
                frame = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
            elif raw.size >= rgb_size:
                rgb   = raw[:rgb_size].reshape((height, width, 3))
                frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            elif raw.size >= gray_size:
                gray_img = raw[:gray_size].reshape((height, width))
                frame = cv2.cvtColor(gray_img, cv2.COLOR_GRAY2BGR)
            else:
                return

            gray_cur = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            with self._gz_lock:
                prev      = self._gz_flow_data
                prev_gray = prev.get("_prev_gray") if isinstance(prev, dict) else None

            if prev_gray is None or prev_gray.shape != gray_cur.shape:
                # First frame — store gray, emit the raw camera image
                with self._gz_lock:
                    self._gz_flow_data = {"_prev_gray": gray_cur, "_b64": None}
                return

            # ── Render exactly like flow_viewer.py ───────────────────────────
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, gray_cur, None,
                pyr_scale=0.5, levels=3, winsize=21,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
            )

            # draw_flow_vectors — step=20, scale=4
            display = frame.copy()
            step = 20; fscale = 4.0
            h, w = frame.shape[:2]
            for fy in range(step // 2, h, step):
                for fx in range(step // 2, w, step):
                    dx, dy = flow[fy, fx]
                    ex = int(round(fx + dx * fscale))
                    ey = int(round(fy + dy * fscale))
                    cv2.arrowedLine(display, (fx, fy), (ex, ey),
                                    (0, 255, 0), 1, tipLength=0.3)

            flow_x = float(np.median(flow[..., 0]))
            flow_y = float(np.median(flow[..., 1]))
            median_mag = float(np.median(np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)))

            cv2.putText(display, f"Flow x={flow_x:+.2f} y={flow_y:+.2f} px/frame",
                        (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1)
            cv2.putText(display, f"mag={median_mag:.3f}",
                        (4, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1)

            ok, buf = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                return
            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            with self._gz_lock:
                self._gz_flow_data = {"_prev_gray": gray_cur, "_b64": b64}
        except Exception:
            pass

    @Slot()
    def _poll_gz_data(self) -> None:
        """QTimer slot (main thread) — emit only when frame changed (no flicker)."""
        with self._gz_lock:
            lidar = self._gz_lidar_data
            flow  = self._gz_flow_data

        if lidar and self._gz_lidar_active and isinstance(lidar, str):
            if lidar != self._gz_lidar_last:
                self._gz_lidar_last = lidar
                self.lidarFrameReady.emit(lidar)

        if flow and self._gz_flow_active and isinstance(flow, dict):
            b64 = flow.get("_b64")
            if b64 and b64 != self._gz_flow_last:
                self._gz_flow_last = b64
                self.flowFrameReady.emit(b64)

    # ─────────────────────────────────────────────────────────────────────────
    # Status / instance list
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(result=str)
    def sitlStatus(self) -> str:
        return self._sim_status

    @Slot(result=bool)
    def isRunning(self) -> bool:
        return self._sim_status == _S_RUNNING

    @Slot(result="QVariantList")
    def runningInstances(self) -> List[dict]:
        with self._lock:
            now = time.time()
            return [
                {**inst, "uptime": int(now - inst["started"])}
                for inst in self._instances
            ]

    # ─────────────────────────────────────────────────────────────────────────
    # Gazebo
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(result=bool)
    def isGazeboAvailable(self) -> bool:
        return shutil.which("gz") is not None

    @Slot(result="QVariantList")
    def detectGazeboWorlds(self) -> List[str]:
        """Scan known paths for .sdf world files, return sorted list."""
        worlds: List[str] = []
        # Collect candidate directories in priority order
        search_dirs: List[Path] = [
            # User's ardupilot_gazebo plugin repo (source tree)
            Path.home() / "ardupilot_gazebo" / "worlds",
            # Typical gz_ws workspace layout (seen in user testing)
            Path.home() / "gz_ws" / "src" / "ardupilot_gazebo" / "worlds",
            # CMake install prefix inside build dir
            Path.home() / "gz_ws" / "src" / "ardupilot_gazebo" / "build" / "worlds",
            # Standard Gazebo system share dirs
            Path("/usr/share/gz/worlds"),
            Path("/usr/share/gazebo/worlds"),
            Path("/usr/share/gazebo-11/worlds"),
            # GZ_SIM_RESOURCE_PATH entries
            *[
                Path(p) / "worlds"
                for p in os.environ.get("GZ_SIM_RESOURCE_PATH", "").split(":")
                if p
            ],
        ]
        seen: set = set()
        for d in search_dirs:
            if d.exists():
                for sdf in sorted(d.glob("*.sdf")):
                    if str(sdf) not in seen:
                        seen.add(str(sdf))
                        worlds.append(str(sdf))
        return worlds

    @Slot(str)
    def setGzWsPath(self, path: str) -> None:
        """Persist the Gazebo workspace path (used as cwd for gz sim)."""
        path = path.strip()
        self._cfg.setdefault("gazebo", {})["gz_ws_path"] = path
        self._save_config_to_disk()
        self._log("INFO", f"[SITL] Gazebo ws path: {path}")

    @Slot(result=str)
    def getGzWsPath(self) -> str:
        return self._cfg.get("gazebo", {}).get(
            "gz_ws_path", str(Path.home() / "gz_ws" / "src")
        )

    @Slot(str)
    def launchGazebo(self, config_json: str) -> None:
        """Open terminal with: cd <gz_ws_path> && gz sim -v{verbosity} -r {world}

        The gz sim command is run from the gz_ws_path so that relative .sdf paths
        (worlds/iris_runway.sdf) are resolved correctly when gz_ws_path contains
        ardupilot_gazebo/worlds/.
        """
        try:
            cfg = json.loads(config_json)
        except Exception as exc:
            self._log("ERROR", f"[SITL] Invalid Gazebo config: {exc}")
            return

        world     = cfg.get("world",      "iris_runway.sdf")
        verbosity = int(cfg.get("verbosity", 4))
        gz_ws     = cfg.get("gz_ws_path",
                             self._cfg.get("gazebo", {}).get(
                                 "gz_ws_path", str(Path.home() / "gz_ws" / "src")
                             ))

        script = (
            f'echo "=== Gazebo Harmonic ==="\n'
            f'echo "cwd: {gz_ws}"\n'
            f'cd {shlex.quote(gz_ws)}\n'
            f'gz sim -v{verbosity} -r {shlex.quote(world)}\n'
            f'echo "--- Gazebo exited ---" ; read\n'
        )
        self._trace("gazebo_start", {"world": world, "verbosity": verbosity, "cwd": gz_ws})
        self._log("INFO", f"[SITL] Gazebo (cwd={gz_ws}): gz sim -v{verbosity} -r {world}")

        proc = self._open_terminal(script, title=f"Gazebo — {Path(world).name}")
        if proc:
            self._gazebo_status = _S_RUNNING
            self.gazeboStatusChanged.emit(_S_RUNNING)
            self._cfg.setdefault("gazebo", {}).update(cfg)
            self._save_config_to_disk()
        else:
            self._gazebo_status = _S_ERROR
            self.gazeboStatusChanged.emit(_S_ERROR)

    @Slot()
    def stopGazebo(self) -> None:
        self._gazebo_status = _S_STOPPED
        self.gazeboStatusChanged.emit(_S_STOPPED)
        self._trace("gazebo_stop", {})

    @Slot()
    def runGzTopicList(self) -> None:
        """Open a terminal running: gz topic -l | grep -i streaming
        Lets the user see available streaming topics before enabling them.
        """
        script = (
            'echo "=== gz topic -l | grep -i streaming ==="\n'
            'gz topic -l | grep -i "streaming" || echo "(no streaming topics found)"\n'
            'echo ""\n'
            'echo "=== All topics (for reference): ==="\n'
            'gz topic -l\n'
            'echo ""\n'
            'echo "Press ENTER to close"\n'
            'read\n'
        )
        self._open_terminal(script, title="Gazebo Topics")

    @Slot(result=bool)
    def isGstAvailable(self) -> bool:
        return shutil.which("gst-launch-1.0") is not None

    @Slot(result="QVariantList")
    def detectStreamingTopics(self) -> List[str]:
        """Run: gz topic -l | grep -i streaming (3s timeout)"""
        gz = shutil.which("gz")
        if not gz:
            return []
        try:
            result = subprocess.run(
                [gz, "topic", "-l"],
                capture_output=True, text=True, timeout=3
            )
            lines = result.stdout.splitlines()
            return [l for l in lines if "streaming" in l.lower()]
        except Exception:
            return []

    @Slot(str)
    def enableStreaming(self, topic: str) -> None:
        gz = shutil.which("gz")
        if not gz or not topic:
            return
        cmd = [gz, "topic", "-t", topic, "-m", "gz.msgs.Boolean", "-p", "data: 1"]
        try:
            subprocess.Popen(cmd)
            self._trace("stream_enable", {"topic": topic})
            self._log("INFO", f"[SITL] Streaming enabled: {topic}")
        except Exception as exc:
            self._log("ERROR", f"[SITL] Failed to enable streaming: {exc}")

    @Slot(result="QVariantList")
    def detectGazeboSensorTopics(self) -> List[str]:
        """Scan gz topic -l for lidar/flow related topics. Times out after 3 s."""
        gz = shutil.which("gz")
        if not gz:
            return []
        try:
            result = subprocess.run(
                [gz, "topic", "-l"],
                capture_output=True, text=True, timeout=3,
            )
            lines = result.stdout.splitlines()
            keywords = ("lidar", "scan", "flow", "range", "optical", "distance")
            found = [ln for ln in lines if any(kw in ln.lower() for kw in keywords)]
        except Exception:
            found = []
        return found

    @Slot(str, result=str)
    def getSdfSnippet(self, sensor_type: str) -> str:
        """Return a ready-to-paste SDF XML snippet for sensor_type (lidar or flow_camera)."""
        if sensor_type == "lidar":
            return (
                '<!-- ═══ 360° LiDAR (GPU) ═════════════════════════════════════════ -->\n'
                '<link name="lidar_link">\n'
                '  <pose>0 0 0.12 0 0 0</pose>\n'
                '  <inertial><mass>0.01</mass>\n'
                '    <inertia><ixx>0.00001</ixx><iyy>0.00001</iyy><izz>0.00001</izz></inertia>\n'
                '  </inertial>\n'
                '  <sensor name="lidar" type="gpu_lidar">\n'
                '    <pose>0 0 0 0 0 0</pose>\n'
                '    <topic>/lidar/scan</topic>\n'
                '    <update_rate>20</update_rate>\n'
                '    <always_on>true</always_on>\n'
                '    <visualize>true</visualize>\n'
                '    <lidar>\n'
                '      <scan>\n'
                '        <horizontal>\n'
                '          <samples>720</samples>\n'
                '          <resolution>1</resolution>\n'
                '          <min_angle>-3.14159265</min_angle>\n'
                '          <max_angle>3.14159265</max_angle>\n'
                '        </horizontal>\n'
                '        <vertical>\n'
                '          <samples>1</samples><resolution>1</resolution>\n'
                '          <min_angle>0</min_angle><max_angle>0</max_angle>\n'
                '        </vertical>\n'
                '      </scan>\n'
                '      <range><min>0.15</min><max>20.0</max><resolution>0.01</resolution></range>\n'
                '      <noise><type>gaussian</type><mean>0</mean><stddev>0.01</stddev></noise>\n'
                '    </lidar>\n'
                '  </sensor>\n'
                '</link>\n'
                '<joint name="lidar_joint" type="fixed">\n'
                '  <parent>base_link</parent>\n'
                '  <child>lidar_link</child>\n'
                '</joint>\n'
                '<!-- ════════════════════════════════════════════════════════════════ -->'
            )
        if sensor_type == "flow_camera":
            return (
                '<!-- ═══ Optical-Flow downward camera ════════════════════════════════ -->\n'
                '<link name="flow_camera_link">\n'
                '  <pose>0 0 -0.05 0 1.570796 0</pose>\n'
                '  <inertial><mass>0.01</mass>\n'
                '    <inertia><ixx>0.00001</ixx><iyy>0.00001</iyy><izz>0.00001</izz></inertia>\n'
                '  </inertial>\n'
                '  <sensor name="flow_camera" type="camera">\n'
                '    <topic>/flow_camera/image</topic>\n'
                '    <update_rate>30</update_rate>\n'
                '    <always_on>true</always_on>\n'
                '    <visualize>false</visualize>\n'
                '    <camera>\n'
                '      <horizontal_fov>1.047</horizontal_fov>\n'
                '      <image><width>320</width><height>240</height><format>R8G8B8</format></image>\n'
                '      <clip><near>0.05</near><far>30</far></clip>\n'
                '    </camera>\n'
                '  </sensor>\n'
                '</link>\n'
                '<joint name="flow_camera_joint" type="fixed">\n'
                '  <parent>base_link</parent>\n'
                '  <child>flow_camera_link</child>\n'
                '</joint>\n'
                '<!-- ════════════════════════════════════════════════════════════════ -->'
            )
        return f"<!-- Unknown sensor_type: {sensor_type!r} -->"

    @Slot(str)
    def launchGazeboSensorStream(self, config_json: str) -> None:
        """
        Open a terminal showing a human-readable summary of a Gazebo sensor topic.

        LiDAR: filters the 720-line ranges/intensities flood to one compact line per frame:
            Frame     1 | beams=720 | hits=  3 | min=1.23m max=18.50m

        flow_camera: shows only frame count + image size (raw image bytes are not printed).
        """
        try:
            cfg = json.loads(config_json)
        except Exception as exc:
            self._log("ERROR", f"[SITL] launchGazeboSensorStream bad JSON: {exc}")
            return

        sensor_type = cfg.get("sensor_type", "lidar")
        default_topic = "/lidar/scan" if sensor_type == "lidar" else "/flow_camera/image"
        topic = cfg.get("topic", default_topic).strip() or default_topic

        gz = shutil.which("gz")
        if not gz:
            self._log("WARN", "[SITL] gz CLI not found — cannot open sensor stream")
            return

        label = {"lidar": "LiDAR (gz topic)", "flow_camera": "Optical Flow (gz topic)"}.get(
            sensor_type, sensor_type
        )

        if sensor_type == "lidar":
            # gz topic -e separates messages with a blank line OR '---'.
            # Intensities lines are skipped; a new frame starts whenever a
            # non-ranges line arrives after ranges have been collected.
            python_filter = (
                "import sys, re\n"
                "frame=0; ranges=[]\n"
                "def flush_frame(ranges):\n"
                "    global frame\n"
                "    if not ranges: return\n"
                "    frame+=1\n"
                "    finite=[r for r in ranges if r!=float('inf') and r<9999]\n"
                "    mn=min(finite) if finite else float('nan')\n"
                "    mx=max(finite) if finite else 0\n"
                "    print(f'Frame {frame:5d} | beams={len(ranges):3d} | hits={len(finite):3d} | min={mn:.2f}m max={mx:.2f}m', flush=True)\n"
                "for line in sys.stdin:\n"
                "    line=line.rstrip()\n"
                "    m=re.match(r'\\s*ranges:\\s*([\\d.eE+\\-inf]+)', line)\n"
                "    if m:\n"
                "        try: ranges.append(float(m.group(1)))\n"
                "        except: ranges.append(float('inf'))\n"
                "        continue\n"
                "    if re.match(r'\\s*intensities:', line): continue\n"
                "    # blank line or '---' or any header line = frame boundary\n"
                "    if line == '' or line.startswith('---') or line.startswith('header') or line.startswith('stamp') or line.startswith('seq'):\n"
                "        flush_frame(ranges); ranges=[]\n"
            )
            hint = "(Zusammenfassung pro Frame — ranges/intensities werden gefiltert)"
        else:
            # gz topic -e for camera Image: skip 'data:' byte lines (they are
            # raw pixel values and produce the character-flood the user sees).
            # Frame boundary = blank line or '---'.
            python_filter = (
                "import sys, re\n"
                "frame=0; width=0; height=0; step=0\n"
                "for line in sys.stdin:\n"
                "    line=line.rstrip()\n"
                "    if re.match(r'\\s*data:', line): continue\n"
                "    m=re.match(r'\\s*width:\\s*(\\d+)', line)\n"
                "    if m: width=int(m.group(1)); continue\n"
                "    m=re.match(r'\\s*height:\\s*(\\d+)', line)\n"
                "    if m: height=int(m.group(1)); continue\n"
                "    m=re.match(r'\\s*step:\\s*(\\d+)', line)\n"
                "    if m: step=int(m.group(1)); continue\n"
                "    if (line == '' or line.startswith('---')) and width:\n"
                "        frame+=1\n"
                "        bpp=int(step/width) if width else 0\n"
                "        print(f'Frame {frame:5d} | {width}x{height} px  {bpp}bpp', flush=True)\n"
                "        width=0; height=0; step=0\n"
            )
            hint = "(Nur Frame-Zaehler und Bildgroesse — rohe Bilddaten werden gefiltert)"

        script = (
            f'echo "══════════════════════════════════════════"\n'
            f'echo "  {label}"\n'
            f'echo "  Topic: {topic}"\n'
            f'echo "  {hint}"\n'
            f'echo "══════════════════════════════════════════"\n'
            f'echo "Warte auf erste Nachricht... (Ctrl-C zum Beenden)"\n'
            f'echo ""\n'
            f'gz topic -e -t {shlex.quote(topic)} | python3 -c {shlex.quote(python_filter)}\n'
            f'echo "--- Stream beendet ---"\n'
            f'read\n'
        )
        self._trace("gz_sensor_stream", {"sensor_type": sensor_type, "topic": topic})
        self._log("INFO", f"[SITL] Gazebo sensor stream: {topic}")
        self._open_terminal(script, title=f"{label} — {topic}")

    @Slot()
    def launchGazeboSensorMonitorAll(self) -> None:
        """Open a terminal showing both LiDAR and optical-flow topics with filtered output."""
        gz = shutil.which("gz")
        if not gz:
            self._log("WARN", "[SITL] gz CLI not found")
            return

        lidar_filter = (
            "import sys, re\n"
            "frame=0; ranges=[]\n"
            "def flush_frame(ranges):\n"
            "    global frame\n"
            "    if not ranges: return\n"
            "    frame+=1\n"
            "    finite=[r for r in ranges if r!=float('inf') and r<9999]\n"
            "    mn=min(finite) if finite else float('nan')\n"
            "    mx=max(finite) if finite else 0\n"
            "    print(f'[LIDAR] Frame {frame:5d} | beams={len(ranges):3d} | hits={len(finite):3d} | min={mn:.2f}m max={mx:.2f}m', flush=True)\n"
            "for line in sys.stdin:\n"
            "    line=line.rstrip()\n"
            "    m=re.match(r'\\s*ranges:\\s*([\\d.eE+\\-inf]+)', line)\n"
            "    if m:\n"
            "        try: ranges.append(float(m.group(1)))\n"
            "        except: ranges.append(float('inf'))\n"
            "        continue\n"
            "    if re.match(r'\\s*intensities:', line): continue\n"
            "    if line == '' or line.startswith('---') or line.startswith('header') or line.startswith('stamp') or line.startswith('seq'):\n"
            "        flush_frame(ranges); ranges=[]\n"
        )
        flow_filter = (
            "import sys, re\n"
            "frame=0; width=0; height=0; step=0\n"
            "for line in sys.stdin:\n"
            "    line=line.rstrip()\n"
            "    if re.match(r'\\s*data:', line): continue\n"
            "    m=re.match(r'\\s*width:\\s*(\\d+)', line)\n"
            "    if m: width=int(m.group(1)); continue\n"
            "    m=re.match(r'\\s*height:\\s*(\\d+)', line)\n"
            "    if m: height=int(m.group(1)); continue\n"
            "    m=re.match(r'\\s*step:\\s*(\\d+)', line)\n"
            "    if m: step=int(m.group(1)); continue\n"
            "    if (line == '' or line.startswith('---')) and width:\n"
            "        frame+=1\n"
            "        bpp=int(step/width) if width else 0\n"
            "        print(f'[FLOW]  Frame {frame:5d} | {width}x{height} px  {bpp}bpp', flush=True)\n"
            "        width=0; height=0; step=0\n"
        )

        import tempfile  # noqa: PLC0415
        lidar_tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_lidar.py", delete=False, encoding="utf-8"
        )
        lidar_tmp.write(lidar_filter)
        lidar_tmp.close()
        flow_tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_flow.py", delete=False, encoding="utf-8"
        )
        flow_tmp.write(flow_filter)
        flow_tmp.close()

        script = (
            'echo "═══════════════════════════════════════════════════════"\n'
            'echo "  Gazebo Sensor Monitor — LiDAR + Optical Flow"\n'
            'echo "  (kompakte Ausgabe, keine rohen Bytes)"\n'
            'echo "═══════════════════════════════════════════════════════"\n'
            'echo ""\n'
            'echo "Verfuegbare Topics:"\n'
            'gz topic -l | grep -E "(lidar|scan|flow|range|optical|distance)" || echo "(keine sensor topics gefunden)"\n'
            'echo ""\n'
            f'gz topic -e -t /lidar/scan | python3 {shlex.quote(lidar_tmp.name)} &\n'
            'GZ_LIDAR_PID=$!\n'
            f'gz topic -e -t /flow_camera/image | python3 {shlex.quote(flow_tmp.name)} &\n'
            'GZ_FLOW_PID=$!\n'
            'echo "Beide Streams laufen — druecke ENTER zum Beenden"\n'
            'read\n'
            'kill $GZ_LIDAR_PID $GZ_FLOW_PID 2>/dev/null\n'
            f'rm -f {shlex.quote(lidar_tmp.name)} {shlex.quote(flow_tmp.name)}\n'
            'echo "--- Monitor beendet ---"\n'
            'read\n'
        )
        self._trace("gz_sensor_monitor_all", {})
        self._log("INFO", "[SITL] Gazebo sensor monitor (all) opened")
        self._open_terminal(script, title="Gazebo Sensor Monitor — LiDAR + Flow")

    @Slot(str)
    def launchLidarViewer(self, topic: str = "/lidar/scan") -> None:
        """Launch the OpenCV LiDAR polar-plot viewer as a direct subprocess.

        The Python process is tracked directly so stopViewers() / stopAll() can
        send SIGTERM straight to it — no terminal wrapper means the window
        closes reliably.  Close manually with Q or ESC inside the window.
        Requires: pip install opencv-python gz-transport13 gz-msgs10
        """
        script = Path(__file__).parent.parent / "gz_bridge" / "lidar_viewer.py"
        topic = (topic or "/lidar/scan").strip()
        if not script.exists():
            self._log("ERROR", f"[SITL] lidar_viewer.py not found: {script}")
            return
        try:
            env = _gz_build_env()
            proc = subprocess.Popen(
                ["python3", str(script), "--topic", topic],
                env=env,
                start_new_session=True,   # detach from our process group
            )
            with self._lock:
                self._viewer_procs.append(_TrackedProc(f"lidar:{topic}", proc))
            self._trace("lidar_viewer_launch", {"topic": topic, "pid": proc.pid})
            self._log("INFO", f"[SITL] LiDAR viewer launched (PID {proc.pid}, topic={topic})")
        except Exception as exc:
            self._log("ERROR", f"[SITL] launchLidarViewer failed: {exc}")

    @Slot(str)
    def launchFlowViewer(self, topic: str = "/flow_camera/image") -> None:
        """Launch the OpenCV flow-camera viewer as a direct subprocess.

        The Python process is tracked directly so stopViewers() / stopAll() can
        send SIGTERM straight to it — no terminal wrapper means the window
        closes reliably.  Close manually with Q or ESC inside the window.
        Requires: pip install opencv-python gz-transport13 gz-msgs10
        """
        script = Path(__file__).parent.parent / "gz_bridge" / "flow_viewer.py"
        topic = (topic or "/flow_camera/image").strip()
        if not script.exists():
            self._log("ERROR", f"[SITL] flow_viewer.py not found: {script}")
            return
        try:
            env = _gz_build_env()
            proc = subprocess.Popen(
                ["python3", str(script), "--topic", topic],
                env=env,
                start_new_session=True,   # detach from our process group
            )
            with self._lock:
                self._viewer_procs.append(_TrackedProc(f"flow:{topic}", proc))
            self._trace("flow_viewer_launch", {"topic": topic, "pid": proc.pid})
            self._log("INFO", f"[SITL] Flow viewer launched (PID {proc.pid}, topic={topic})")
        except Exception as exc:
            self._log("ERROR", f"[SITL] launchFlowViewer failed: {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Gazebo → MAVLink Sensor Bridge
    # ─────────────────────────────────────────────────────────────────────────

    # ArduPilot-Parameter die die Bridge benötigt.
    # Automatisch per applyBridgeParams() gesetzt, identisch für SITL + Hardware.
    _BRIDGE_PARAMS: Dict[str, str] = {
        "FLOW_TYPE":       "5",    # MAVLink Optical Flow (OPTICAL_FLOW_RAD)
        "RNGFND1_TYPE":   "10",    # MAVLink Rangefinder (DISTANCE_SENSOR)
        "RNGFND1_MIN_CM":  "5",
        "RNGFND1_MAX_CM": "3000",
        "RNGFND1_ORIENT": "25",    # nach unten (PITCH_270)
        "PRX1_TYPE":       "2",    # MAVLink Proximity (OBSTACLE_DISTANCE)
        "AVOID_ENABLE":    "7",    # Hinderniserkennung aktivieren
        "AVOID_MARGIN":    "2",    # Sicherheitsabstand in Metern
    }

    @Slot(result=str)
    def getBridgeStatus(self) -> str:
        """Aktueller Status der Sensor-Bridge: 'stopped'|'running'|'error'."""
        # Prozess noch am Leben?
        if self._bridge_proc is not None:
            if self._bridge_proc.poll() is None:
                self._bridge_status = "running"
            else:
                rc = self._bridge_proc.returncode
                self._bridge_status = "error" if rc != 0 else "stopped"
                self._bridge_proc = None
        return self._bridge_status

    @Slot(result="QVariantList")
    def getBridgeParamList(self) -> List[dict]:
        """Liste der Bridge-Parameter für die UI-Anzeige."""
        return [{"name": k, "value": v} for k, v in self._BRIDGE_PARAMS.items()]

    @Slot(str)
    def launchSensorBridge(self, config_json: str = "{}") -> None:
        """Starte die Gazebo→MAVLink Sensor-Bridge als direkten Subprozess.

        config_json (optional): {"mavlink": "udpin:0.0.0.0:14550",
                                 "camera_topic": "/flow_camera/image",
                                 "lidar_topic":  "/lidar/scan"}

        Die Bridge läuft headless (--no-display) und kann per stopSensorBridge()
        oder stopAll() beendet werden.
        """
        # Bereits laufende Bridge stoppen
        if self._bridge_proc is not None and self._bridge_proc.poll() is None:
            self._log("WARN", "[SITL] Bridge läuft bereits — wird neu gestartet")
            self.stopSensorBridge()

        script = Path(__file__).parent.parent / "gz_bridge" / "gazebo_mavlink_sensor_bridge.py"
        if not script.exists():
            self._log("ERROR", f"[SITL] gazebo_mavlink_sensor_bridge.py nicht gefunden: {script}")
            self._bridge_status = "error"
            return

        try:
            cfg = json.loads(config_json) if config_json.strip() else {}
        except Exception:
            cfg = {}

        mavlink      = cfg.get("mavlink",       "udpin:0.0.0.0:14550").strip()
        camera_topic = cfg.get("camera_topic",  "/flow_camera/image").strip()
        lidar_topic  = cfg.get("lidar_topic",   "/lidar/scan").strip()

        cmd = [
            "python3", str(script),
            "--mavlink",       mavlink,
            "--camera-topic",  camera_topic,
            "--lidar-topic",   lidar_topic,
            "--no-display",
        ]

        try:
            env  = _gz_build_env()
            proc = subprocess.Popen(cmd, env=env, start_new_session=True)
            self._bridge_proc   = proc
            self._bridge_status = "running"
            with self._lock:
                self._viewer_procs.append(_TrackedProc("sensor_bridge", proc))
            self._trace("bridge_launch", {
                "pid": proc.pid, "mavlink": mavlink,
                "camera": camera_topic, "lidar": lidar_topic,
            })
            self._log("INFO",
                f"[SITL] Sensor-Bridge gestartet (PID {proc.pid}, MAVLink={mavlink})")
        except Exception as exc:
            self._bridge_status = "error"
            self._log("ERROR", f"[SITL] launchSensorBridge fehlgeschlagen: {exc}")

    @Slot()
    def stopSensorBridge(self) -> None:
        """Beende die laufende Sensor-Bridge (SIGTERM → SIGKILL nach 2 s)."""
        proc = self._bridge_proc
        if proc is None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass
        self._bridge_proc   = None
        self._bridge_status = "stopped"
        # Aus _viewer_procs entfernen
        with self._lock:
            self._viewer_procs = [
                tp for tp in self._viewer_procs if tp.label != "sensor_bridge"
            ]
        self._log("INFO", "[SITL] Sensor-Bridge gestoppt.")

    @Slot(str)
    def applyBridgeParams(self, master: str = "tcp:127.0.0.1:5760") -> None:
        """Sende alle benötigten ArduPilot-Parameter für die Bridge per MAVProxy.

        Entspricht:
            param set FLOW_TYPE 5
            param set RNGFND1_TYPE 10  …
            reboot

        Funktioniert für SITL und echte Hardware — nur master-Adresse anpassen.
        """
        master = (master or "tcp:127.0.0.1:5760").strip()
        params = dict(self._BRIDGE_PARAMS)

        # Über _apply_params_now (no-terminal, detached mavproxy one-shot)
        self._apply_params_now(params)
        self._trace("bridge_params_applied", {"master": master, "params": params})
        self._log("INFO",
            f"[SITL] Bridge-Parameter gesendet an {master}: "
            + ", ".join(f"{k}={v}" for k, v in params.items()))

    @Slot(str, int)
    def launchGstPreview(self, host: str, port: int) -> None:
        """
        Open a terminal running gst-launch-1.0 for H.264 RTP preview.

        Note: udpsrc is a listener — it ignores the host parameter and binds to
        0.0.0.0:{port}. The `host` argument is kept for API compat only.

        Uses the verbose GStreamer caps notation (with explicit type annotations)
        which is more robust across GStreamer versions and matches what Gazebo
        Harmonic actually sends (confirmed working format).
        """
        # Verbose caps format — matches real Gazebo H.264 RTP output
        caps = (
            "application/x-rtp,"
            "media=(string)video,"
            "clock-rate=(int)90000,"
            "encoding-name=(string)H264"
        )
        gst_cmd = (
            f"gst-launch-1.0 -v "
            f"udpsrc port={port} "
            f"caps='{caps}' "
            f"! rtph264depay ! avdec_h264 ! videoconvert ! autovideosink sync=false"
        )
        script = f'{gst_cmd}\necho "--- GStreamer exited ---"\nread\n'
        self._trace("gst_preview", {"port": port, "caps": caps})
        self._log("INFO", f"[SITL] GStreamer preview: udp://0.0.0.0:{port}")
        self._open_terminal(script, title=f"GStreamer Preview :{port}")

    # ─────────────────────────────────────────────────────────────────────────
    # MAVProxy
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(str)
    def launchMavproxy(self, config_json: str) -> None:
        """
        Config keys: master (default tcp:127.0.0.1:5760),
        use_map, use_console, extra_args, script_commands (list of str)
        """
        try:
            cfg = json.loads(config_json)
        except Exception:
            cfg = {}

        master      = cfg.get("master",      "tcp:127.0.0.1:5760")
        use_map     = bool(cfg.get("use_map",     False))
        use_console = bool(cfg.get("use_console", False))
        extra_args  = cfg.get("extra_args",   "").strip()
        commands    = cfg.get("script_commands", [])

        script_path = self._write_mavproxy_script(commands) if commands else None

        cmd_parts = [f"mavproxy.py --master={master}"]
        if use_map:
            cmd_parts.append("--map")
        if use_console:
            cmd_parts.append("--console")
        if script_path:
            cmd_parts.append(f"--script={shlex.quote(str(script_path))}")
        if extra_args:
            cmd_parts.append(extra_args)

        full_cmd = " ".join(cmd_parts)
        script = f'{full_cmd}\necho "--- MAVProxy exited ---" ; read\n'
        self._trace("mavproxy_start", {"master": master, "cmd": full_cmd})
        self._log("INFO", f"[SITL] MAVProxy: {full_cmd}")
        self._open_terminal(script, title=f"MAVProxy — {master}")

    @Slot()
    def launchMavproxyWithJoystick(self) -> None:
        self.launchMavproxy(json.dumps({
            "master": "tcp:127.0.0.1:5760",
            "use_map": False,
            "use_console": False,
            "script_commands": ["module load joystick"],
        }))

    @Slot(str)
    def launchMavproxyGraph(self, field: str) -> None:
        field = field.strip() or "VFR_HUD.alt"
        self.launchMavproxy(json.dumps({
            "master": "tcp:127.0.0.1:5760",
            "use_console": False,
            "script_commands": [f"graph {field}"],
        }))

    @Slot(result=bool)
    def isJoystickAvailable(self) -> bool:
        return Path("/dev/input/js0").exists()

    @Slot(result="QVariantList")
    def getPreArmFixes(self) -> List[dict]:
        """Return the PreArm fix script catalogue for the Debug tab."""
        return list(_PREARM_FIXES)

    @Slot(str, str)
    def launchMavproxyFix(self, fix_id: str, master: str) -> None:
        """
        Run a PreArm fix sequence via MAVProxy script file.

        Looks up the fix by id in _PREARM_FIXES, writes commands to a temp
        .scr file, then opens MAVProxy with --script pointing to that file.
        The --console flag is included so the operator can see command output.
        """
        fix = next((f for f in _PREARM_FIXES if f["id"] == fix_id), None)
        if not fix:
            self._log("WARN", f"[SITL] Unknown PreArm fix id: {fix_id}")
            return

        commands = fix["commands"]
        master   = (master or "tcp:127.0.0.1:5760").strip()

        self._trace("prearm_fix", {"fix_id": fix_id, "commands": commands, "master": master})
        self._log("INFO", f"[SITL] PreArm fix '{fix['label']}': {', '.join(commands)}")
        self.launchMavproxy(json.dumps({
            "master":          master,
            "use_map":         False,
            "use_console":     True,
            "script_commands": commands,
        }))

    # ─────────────────────────────────────────────────────────────────────────
    # Peripheral devices (Tab 3)
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(result="QVariantList")
    def getPeripheralCatalogue(self) -> List[dict]:
        """Return the full peripheral device catalogue with enabled state."""
        result = []
        for item in _PERIPHERAL_CATALOGUE:
            enabled_cfg = self._peripheral_devices.get(item["id"], {})
            result.append({
                **item,
                "enabled": enabled_cfg.get("enabled", False),
                "activeParams": enabled_cfg.get("params", item["params"]),
            })
        return result

    @Slot(str, str)
    def setPeripheralDevice(self, device_id: str, config_json: str) -> None:
        """Enable a peripheral device and apply its parameters immediately.

        Parameters are stored for next launch (pending_params) AND, if SITL
        is currently running, sent right now via a silent mavproxy one-shot.
        """
        try:
            cfg = json.loads(config_json)
        except Exception as exc:
            self._log("ERROR", f"[SITL] setPeripheralDevice bad JSON: {exc}")
            return
        self._peripheral_devices[device_id] = cfg
        params = cfg.get("params", {})
        for name, value in params.items():
            self._pending_params[name] = str(value)
        self._save_config_to_disk()
        self._trace("peripheral_set", {"device": device_id, "config": cfg})
        self._log("INFO", f"[SITL] Peripheral '{device_id}' enabled")
        # Apply immediately if SITL is running
        if params and self._sim_status == _S_RUNNING:
            self._apply_params_now(params)
        self.peripheralDevicesChanged.emit()

    @Slot(str)
    def removePeripheralDevice(self, device_id: str) -> None:
        """Disable a peripheral device."""
        if device_id in self._peripheral_devices:
            # Remove its params from pending_params
            old_params = self._peripheral_devices[device_id].get("params", {})
            for name in old_params:
                self._pending_params.pop(name, None)
            del self._peripheral_devices[device_id]
            self._save_config_to_disk()
            self._trace("peripheral_remove", {"device": device_id})
            self._log("INFO", f"[SITL] Peripheral '{device_id}' disabled")
            self.peripheralDevicesChanged.emit()

    @Slot(result=str)
    def getPeripheralDevices(self) -> str:
        """Return JSON of currently enabled devices."""
        return json.dumps(self._peripheral_devices)

    def _apply_params_now(self, params: dict) -> None:
        """Silently send 'param set NAME VALUE' for each entry via a mavproxy one-shot.

        Runs detached — no terminal window is opened.  Best-effort: if mavproxy
        is not on PATH this is a no-op.
        """
        mavproxy = shutil.which("mavproxy.py") or shutil.which("mavproxy")
        if not mavproxy:
            self._log("WARN", "[SITL] mavproxy not found — params queued for next start")
            return
        cmds = "  ".join(f"param set {n} {v};" for n, v in params.items())
        cmd = [mavproxy, "--master=tcp:127.0.0.1:5760",
               "--cmd", cmds + "  reboot;  exit"]
        try:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._log("INFO", f"[SITL] Params applied now: {list(params.keys())}")
        except Exception as exc:
            self._log("WARN", f"[SITL] Immediate param apply failed: {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Parameters (Tab 4)
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(result=str)
    def getKnownParams(self) -> str:
        """Return JSON list of known SIM_* parameters with metadata."""
        result = []
        for name, meta in _SIM_PARAMS.items():
            pending_val = self._pending_params.get(name)
            result.append({
                "name":     name,
                "default":  meta["default"],
                "unit":     meta["unit"],
                "desc":     meta["desc"],
                "category": meta["category"],
                "pending":  pending_val,  # None if not overridden
            })
        return json.dumps(result)

    @Slot(str, str)
    def setParam(self, name: str, value: str) -> None:
        """
        Store a parameter override. Applied on next MAVProxy/sim_vehicle start.
        Emits paramChanged(name, value).
        """
        name  = name.strip()
        value = value.strip()
        if not name:
            return
        self._pending_params[name] = value
        self._save_config_to_disk()
        self._trace("param_set", {"name": name, "value": value})
        self._log("INFO", f"[SITL] Param pending: {name} = {value}")
        self.paramChanged.emit(name, value)

    @Slot(str)
    def clearParam(self, name: str) -> None:
        """Remove a pending parameter override."""
        if name in self._pending_params:
            del self._pending_params[name]
            self._save_config_to_disk()
            self.paramChanged.emit(name, "")

    @Slot(result=str)
    def getPendingParams(self) -> str:
        """Return JSON dict of all pending parameter overrides."""
        return json.dumps(self._pending_params)

    # ─────────────────────────────────────────────────────────────────────────
    # Legacy / compat helpers
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(str, result=str)
    def detectBinary(self, vehicle: str) -> str:
        return _find_binary(vehicle, self._cfg.get("repo_path", ""))

    @Slot(result="QVariantList")
    def availableVehicles(self) -> List[str]:
        return list(_VEHICLES.keys())

    @Slot(result="QVariantList")
    def vehicleLabels(self) -> List[str]:
        return list(_VEHICLES.values())

    # ─────────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(result=str)
    def loadConfig(self) -> str:
        return json.dumps(self._cfg)

    @Slot(str)
    def saveConfig(self, config_json: str) -> None:
        try:
            cfg = json.loads(config_json)
            self._cfg.update(cfg)
            self._save_config_to_disk()
        except Exception as exc:
            self._log("WARN", f"[SITL] saveConfig failed: {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Trace / debug
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(int, result="QVariantList")
    def getRecentTraceLogs(self, max_lines: int = 50) -> List[dict]:
        """Return last N sitl-source events from the active trace session."""
        from skymeshx.core.trace_logger import TraceLogger, _iter_jsonl  # noqa
        logger = TraceLogger.get()
        if not logger.session_active or not logger.session_path:
            return []
        ui_path = Path(logger.session_path) / "ui_events.jsonl"
        rows = _iter_jsonl(ui_path)
        sitl_rows = [r for r in rows if r.get("source") == "sitl"]
        return sitl_rows[-max_lines:]

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _schedule_auto_connect(self, connections: List[dict], delay_ms: int = 8000) -> None:
        """
        Fire autoConnectReady after `delay_ms` ms so SITL has time to boot.

        Default is 8 s — ArduPilot SITL needs a few seconds to initialise its
        TCP listeners before the GCS can open a connection.  After the delay
        DroneBackend.connect() still has its own 10 s heartbeat timeout, so the
        total window before a final failure is ~18 s.

        connections: list of {"id": str, "connection_string": str}
        The signal payload is passed through to service_locator.wire() which
        calls swarm.addDrone(id, connection_string) for each entry.
        """
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(delay_ms)
        timer.timeout.connect(lambda: self.autoConnectReady.emit(connections))
        timer.start()
        self._log("INFO",
            f"[SITL] Auto-connect in {delay_ms / 1000:.0f}s: "
            + ", ".join(f"{c['id']}@{c['connection_string']}" for c in connections))

    def _open_terminal(self, script: str, title: str = "SITL") -> Optional[subprocess.Popen]:
        """
        Open an external terminal running `script`.
        Tries terminal candidates in order; returns the Popen if successful.
        """
        # Write script to a temp file to avoid quoting issues
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, prefix="skymeshx_sitl_"
        ) as f:
            f.write("#!/bin/bash\n")
            f.write(script)
            script_path = f.name
        os.chmod(script_path, 0o755)

        for name, template in _TERMINAL_CANDIDATES:
            if not shutil.which(name):
                continue
            try:
                # Build argv with {title} and {script} substituted
                argv = [
                    part.format(title=title, script=script_path)
                    for part in template
                ]
                proc = subprocess.Popen(argv)
                self._emit_console(f"[SITL] Terminal '{name}' opened (PID {proc.pid})")
                self._trace("terminal_open", {
                    "terminal": name, "title": title, "pid": proc.pid
                })
                with self._lock:
                    self._procs.append(_TrackedProc(title, proc))
                return proc
            except Exception as exc:
                self._emit_console(f"[SITL] Terminal '{name}' failed: {exc}")

        self._log("ERROR",
            "[SITL] No terminal emulator found. "
            "Install gnome-terminal, xterm, or konsole.")
        return None

    def _write_mavproxy_script(self, commands: List[str]) -> Path:
        """Write a MAVProxy .scr file with the given commands."""
        path = Path(tempfile.gettempdir()) / "skymeshx_mavproxy.scr"
        path.write_text("\n".join(commands) + "\n", encoding="utf-8")
        return path

    def _set_sim_status(self, status: str) -> None:
        if self._sim_status != status:
            self._sim_status = status
            self.sitlStatusChanged.emit(status)

    def _set_build_status(self, status: str) -> None:
        if self._build_status != status:
            self._build_status = status
            self.buildStatusChanged.emit(status)

    def _log(self, level: str, text: str) -> None:
        """Emit to global swarm log AND panel console."""
        self.logMessage.emit(level, text)
        self._emit_console(text)

    def _emit_console(self, text: str) -> None:
        """Emit a line to the panel console (thread-safe)."""
        QMetaObject.invokeMethod(
            self, "_do_emit_console",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, text),
        )

    @Slot(str)
    def _do_emit_console(self, text: str) -> None:
        self.sitlLogLine.emit(text)

    def _trace(self, event_type: str, data: dict) -> None:
        """Write event to active TraceLogger session as source='sitl'."""
        try:
            from skymeshx.core.trace_logger import TraceLogger
            TraceLogger.get().log_ui_event(f"sitl/{event_type}", {**data, "source": "sitl"})
        except Exception:
            pass  # Tracing must never block

    def _load_config_from_disk(self) -> None:
        try:
            if _CONFIG_PATH.exists():
                saved = json.loads(_CONFIG_PATH.read_text("utf-8"))
                # Deep-merge: overwrite only keys that exist in saved
                for section, value in saved.items():
                    if isinstance(value, dict) and isinstance(self._cfg.get(section), dict):
                        self._cfg[section].update(value)
                    else:
                        self._cfg[section] = value
                # Restore peripheral devices and pending params
                if "peripheral_devices" in saved:
                    self._peripheral_devices = saved["peripheral_devices"]
                if "pending_params" in saved:
                    self._pending_params = saved["pending_params"]
        except Exception:
            pass

    def _save_config_to_disk(self) -> None:
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                **self._cfg,
                "peripheral_devices": self._peripheral_devices,
                "pending_params":     self._pending_params,
            }
            _CONFIG_PATH.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            self._log("WARN", f"[SITL] Config save failed: {exc}")

    @Slot()
    def _poll_procs(self) -> None:
        """Remove dead terminal processes from tracking list."""
        with self._lock:
            before = len(self._procs)
            self._procs = [tp for tp in self._procs if tp.proc.poll() is None]
            after = len(self._procs)
            # Also clean up closed viewer windows
            self._viewer_procs = [tp for tp in self._viewer_procs if tp.proc.poll() is None]
        if before != after:
            # If all sim terminals are gone, update status
            if after == 0 and self._sim_status == _S_RUNNING:
                with self._lock:
                    self._instances.clear()
                self._set_sim_status(_S_STOPPED)
                self.sitlInstancesChanged.emit()
                self._trace("sim_exit", {"reason": "terminal_closed"})
                self._log("INFO", "[SITL] All terminal processes exited.")

    def shutdown(self) -> None:
        """Called on app quit — terminate all tracked child processes."""
        self.stopAll()
