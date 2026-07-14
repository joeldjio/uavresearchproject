"""
SkyMeshX UI Backend Bridge.

Wraps SkyMeshX SDK objects and emits Qt signals so the UI stays
decoupled from the research backend.

Architecture
------------
DroneBackend  — one instance per physical/simulated drone.
               Polls telemetry at 10 Hz and emits Qt signals.
SwarmBackend  — owns all DroneBackends, aggregates snapshots at 5 Hz,
               and exposes bulk swarm commands.
"""

import threading
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

# ── SkyMeshX SDK — TRULY lazy ────────────────────────────────────
# These imports were previously eager. They pull in MAVLink, asyncio
# event loops and a lot of model code (~300-800ms). We now defer them
# until the first DroneBackend.connect() call.
_DroneSDK = None  # type: ignore
_GenericUAV = None  # type: ignore
_ObservationUAV = None  # type: ignore
_DroneState = None  # type: ignore
_sdk_loaded = False


def _ensure_sdk_loaded() -> None:
    """Import skymeshx SDK on first use. Cached after first call."""
    global _DroneSDK, _GenericUAV, _ObservationUAV, _DroneState, _sdk_loaded
    if _sdk_loaded:
        return
    _sdk_loaded = True
    try:
        from skymeshx.sdk.drone import Drone as _D

        _DroneSDK = _D
    except ImportError:
        pass
    try:
        from skymeshx.core.fsm import DroneState as _S
        from skymeshx.models.generic_uav import GenericUAVModel as _G
        from skymeshx.models.observation_uav import ObservationUAVModel as _O

        _GenericUAV = _G
        _ObservationUAV = _O
        _DroneState = _S
    except ImportError:
        pass


# Drone types
DRONE_TYPE_GENERIC = "generic"
DRONE_TYPE_OBSERVATION = "observation"


def _run_async(fn: Callable, *args, **kwargs) -> None:
    """Fire-and-forget: run *fn* in a daemon thread."""
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


class DroneBackend(QObject):
    """
    Wraps a single Drone SDK instance and forwards telemetry as Qt signals.

    All SDK callbacks are re-emitted through signal/slot which safely
    crosses the thread boundary back to the main (UI) thread.
    """

    telemetry_updated = Signal(dict)  # full TelemetryState snapshot
    state_changed = Signal(str)  # flight_mode string
    connected_changed = Signal(bool)
    log_message = Signal(str, str)  # (level, text)
    fsm_state_changed = Signal(str, str)  # (drone_id, fsm_state_name)
    _start_poll = Signal()  # internal: start timer from main thread

    _POLL_INTERVAL_MS = 100  # 10 Hz telemetry polling

    def __init__(
        self,
        drone_id: str,
        connection_string: str,
        drone_type: str = DRONE_TYPE_GENERIC,
        baud: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.drone_id: str = drone_id
        self.connection_string: str = connection_string
        self.drone_type: str = drone_type
        self.baud: Optional[int] = baud
        self._drone: Optional[_DroneSDK] = None
        self._fsm_state: str = "DISCONNECTED"
        # Swarm role state
        self.swarm_role: str = "none"
        self.leader_id: str = ""
        self.formation_offset: tuple = (0.0, 0.0, 0.0)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)
        self._start_poll.connect(self._poll_timer.start)
        self._last_snap: Optional[dict] = None

    @property
    def fsm_state(self) -> str:
        return self._fsm_state

    # ── Connection ────────────────────────────────────────────────────────

    def _safe_emit(self, signal, *args) -> bool:
        """Emit a Qt signal but tolerate the QObject having been deleted
        (happens when a connect-thread outlives its DroneBackend during
        shutdown / drone removal)."""
        try:
            signal.emit(*args)
            return True
        except RuntimeError:
            # "wrapped C/C++ object of type DroneBackend has been deleted"
            return False

    def connect(self) -> None:
        """Connect to the drone (blocking — run in a background thread)."""
        _ensure_sdk_loaded()
        # Tear down any previous drone object so its TCP socket is released
        # before we try to open a new connection to the same address.
        if self._drone is not None:
            try:
                self._drone.disconnect()
            except Exception:
                pass
            self._drone = None
        try:
            # Prefer typed models (FSM-aware) if available
            if (
                self.drone_type == DRONE_TYPE_OBSERVATION
                and _ObservationUAV is not None
            ):
                self._drone = _ObservationUAV(
                    self.drone_id, self.connection_string, log_dir="logs", baud=self.baud
                )
            elif _GenericUAV is not None:
                self._drone = _GenericUAV(
                    self.drone_id, self.connection_string, log_dir="logs", baud=self.baud
                )
            elif _DroneSDK is not None:
                self._drone = _DroneSDK(
                    self.connection_string, drone_id=self.drone_id, log_dir="logs", baud=self.baud
                )
            else:
                self._safe_emit(
                    self.log_message, "ERROR", "skymeshx SDK not installed."
                )
                self._safe_emit(self.connected_changed, False)
                return

            self._drone.on("statustext", self._on_statustext)
            try:
                self._drone.on("command_ack", self._on_command_ack)
            except Exception:
                # Older SDK builds may not expose the event \u2014 not fatal.
                pass

            # Wire FSM if available (GenericUAVModel/ObservationUAVModel)
            if hasattr(self._drone, "fsm"):
                self._drone.fsm.on_transition(self._on_fsm_transition)
                if hasattr(self._drone.fsm, "on_rejection"):
                    self._drone.fsm.on_rejection(self._on_fsm_rejection)
                self._fsm_state = self._drone.fsm.state.name

            ok = self._drone.connect(timeout=10.0)
            if not self._safe_emit(self.connected_changed, ok):
                # Backend was already torn down — abort silently.
                return
            if ok:
                self._fsm_state = "IDLE"
                self._safe_emit(self.fsm_state_changed, self.drone_id, "IDLE")
                self._safe_emit(
                    self.log_message,
                    "INFO",
                    f"[{self.drone_id}] Connected ({self.drone_type})",
                )
                self._safe_emit(self._start_poll)
            else:
                self._fsm_state = "DISCONNECTED"
                self._safe_emit(
                    self.log_message, "ERROR", f"[{self.drone_id}] Connection timed out"
                )
        except Exception as exc:
            self._safe_emit(self.log_message, "ERROR", f"[{self.drone_id}] {exc}")
            self._safe_emit(self.connected_changed, False)

    def disconnect(self) -> None:
        self._poll_timer.stop()
        if self._drone:
            self._drone.disconnect()
            self._drone = None
        self.connected_changed.emit(False)

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def drone(self) -> Optional[_DroneSDK]:
        return self._drone

    @property
    def is_connected(self) -> bool:
        return self._drone is not None and self._drone.connected

    # ── Flight commands (all fire-and-forget) ─────────────────────────────

    def arm(self, force: bool = False) -> None:
        if self._drone:
            self.log_message.emit("INFO", f"[{self.drone_id}] ▶ ARM (force={force})")
            _run_async(self._drone.arm, force=force)

    def disarm(self, force: bool = False) -> None:
        if self._drone:
            self.log_message.emit("INFO", f"[{self.drone_id}] ■ DISARM (force={force})")
            _run_async(self._drone.disarm, force=force)

    def takeoff(self, altitude: float) -> None:
        if self._drone:
            self.log_message.emit("INFO", f"[{self.drone_id}] ⬆ TAKEOFF to {altitude}m")
            _run_async(self._drone.takeoff, altitude)

    def land(self) -> None:
        if self._drone:
            self.log_message.emit("INFO", f"[{self.drone_id}] ⬇ LAND initiated")
            _run_async(self._drone.land)

    def rtl(self) -> None:
        if self._drone:
            self.log_message.emit(
                "INFO", f"[{self.drone_id}] 🏠 RTL (Return to Launch)"
            )
            _run_async(self._drone.rtl)

    def set_mode(self, mode: str) -> None:
        if self._drone:
            self.log_message.emit("INFO", f"[{self.drone_id}] MODE change to '{mode}'")
            _run_async(self._drone.set_mode, mode)

    def goto(self, lat: float, lon: float, alt: float) -> None:
        if self._drone:
            self.log_message.emit(
                "INFO",
                f"[{self.drone_id}] 🎯 GOTO lat={lat:.6f} lon={lon:.6f} alt={alt}m",
            )
            _run_async(self._drone.goto, lat, lon, alt)

    def change_altitude(self, alt: float) -> None:
        if self._drone:
            self.log_message.emit("INFO", f"[{self.drone_id}] ↕ CHANGE ALT to {alt}m")
            _run_async(self._drone.goto, self._drone.lat, self._drone.lon, alt)

    # ── Gimbal control (ObservationUAVModel only) ─────────────────────────

    def gimbal_point(self, pitch: float, roll: float = 0.0, yaw: float = 0.0) -> None:
        if self._drone and hasattr(self._drone, "gimbal_point"):
            self.log_message.emit(
                "INFO",
                f"[{self.drone_id}] 📷 GIMBAL pitch={pitch} roll={roll} yaw={yaw}",
            )
            _run_async(self._drone.gimbal_point, pitch, roll, yaw)

    def gimbal_home(self) -> None:
        if self._drone and hasattr(self._drone, "gimbal_home"):
            _run_async(self._drone.gimbal_home)

    def get_gimbal_state(self) -> dict:
        if self._drone and hasattr(self._drone, "gimbal_state"):
            return self._drone.gimbal_state
        return {"pitch": 0.0, "roll": 0.0, "yaw": 0.0}

    # ── Camera control (ObservationUAVModel only) ─────────────────────────

    def camera_start_stream(self, source: str) -> bool:
        if not self._drone:
            return False
        if hasattr(self._drone, "start_camera_stream"):
            return bool(self._drone.start_camera_stream(source))
        if hasattr(self._drone, "start_stream"):
            self._drone.start_stream()
            return True
        return False

    def camera_stop_stream(self) -> bool:
        if not self._drone:
            return False
        if hasattr(self._drone, "stop_camera_stream"):
            return bool(self._drone.stop_camera_stream())
        if hasattr(self._drone, "stop_stream"):
            self._drone.stop_stream()
            return True
        return False

    def camera_snapshot(self):
        if not self._drone:
            return False
        if hasattr(self._drone, "capture_snapshot"):
            return self._drone.capture_snapshot()
        return False

    def camera_start_recording(self, path: str) -> bool:
        if not self._drone or not hasattr(self._drone, "start_recording"):
            return False
        result = self._drone.start_recording(path)
        return True if result is None else bool(result)

    def camera_stop_recording(self) -> bool:
        if not self._drone or not hasattr(self._drone, "stop_recording"):
            return False
        result = self._drone.stop_recording()
        return True if result is None else bool(result)

    def get_camera_status(self) -> dict:
        if self._drone and hasattr(self._drone, "get_camera_status"):
            status = self._drone.get_camera_status()
        else:
            status = {
                "streamActive": False,
                "recordingActive": False,
                "backendAvailable": self._drone is not None,
            }
        # Always include droneType so detect_capabilities() can read it
        # from this dict without needing a second get_telemetry_snapshot() call.
        status.setdefault("droneType", self.drone_type)
        return status

    def set_swarm_role(self, role: str, leader_id: str = "") -> None:
        self.swarm_role = role
        self.leader_id = leader_id
        if self._drone and hasattr(self._drone, "set_role"):
            self._drone.set_role(role, leader_id if leader_id else None)
        self.log_message.emit(
            "INFO", f"[{self.drone_id}] ROLE={role} leader={leader_id or '—'}"
        )

    def set_formation_offset(self, north: float, east: float, alt: float) -> None:
        self.formation_offset = (north, east, alt)
        if self._drone and hasattr(self._drone, "set_formation_offset"):
            self._drone.set_formation_offset(north, east, alt)

    def get_fsm_history(self) -> list:
        if self._drone and hasattr(self._drone, "fsm"):
            return self._drone.fsm.history(last_n=30)
        return []

    # ── Data access ───────────────────────────────────────────────────────

    def get_telemetry_snapshot(self) -> Optional[dict]:
        if not self._drone:
            return None
        snap = self._drone.telemetry.snapshot()
        snap["connectionString"] = self.connection_string
        snap["connected"] = self.is_connected
        snap["droneType"] = self.drone_type
        snap["fsmState"] = self._fsm_state
        snap["swarmRole"] = self.swarm_role
        snap["leaderId"] = self.leader_id
        return snap

    # ── Internal ──────────────────────────────────────────────────────────

    def _on_fsm_transition(self, old, new) -> None:
        """Called by FSM on background thread — safe-emit via signal."""
        name = new.name if hasattr(new, "name") else str(new)
        self._fsm_state = name
        self._safe_emit(self.fsm_state_changed, self.drone_id, name)
        lvl = "WARN" if name == "EMERGENCY" else "INFO"
        self._safe_emit(
            self.log_message,
            lvl,
            f"[{self.drone_id}] FSM: {old.name if hasattr(old, 'name') else old} → {name}",
        )

    def _poll(self) -> None:
        if not (self._drone and self._drone.connected):
            return
        snap = self._drone.telemetry.snapshot()
        # Only emit telemetry_updated if the snapshot actually changed.
        # Always emit state_changed (cheap string comparison in QML).
        if snap != self._last_snap:
            self._last_snap = snap
            self._safe_emit(self.telemetry_updated, snap)
        self._safe_emit(self.state_changed, snap.get("flight_mode", "UNKNOWN"))

    def _on_statustext(self, text: str, severity: int) -> None:
        level = "WARN" if severity > 3 else "INFO"
        self._safe_emit(self.log_message, level, f"[{self.drone_id}] {text}")

    def _on_command_ack(
        self, cmd_name: str, result_code: int, result_name: str, success: bool
    ) -> None:
        """Surface MAVLink COMMAND_ACK results in the UI log.

        ACCEPTED is logged at INFO (debug-grade), everything else is WARN/ERROR
        so the operator notices DENIED / FAILED commands instead of silent drops.
        """
        if success:
            # Don't spam the log with every accepted ack \u2014 most users only
            # care about failures. Uncomment if you need verbose tracing.
            return
        # IN_PROGRESS (5) is informational; everything else is a real problem.
        if result_code == 5:
            level = "INFO"
        elif result_code in (2, 3, 4):  # DENIED / UNSUPPORTED / FAILED
            level = "ERROR"
        else:
            level = "WARN"
        self._safe_emit(
            self.log_message,
            level,
            f"[{self.drone_id}] NACK {cmd_name} \u2192 {result_name}",
        )

    def _on_fsm_rejection(self, current_state, requested_state) -> None:
        """Log invalid FSM transitions so they don't fail silently."""
        cur = getattr(current_state, "name", str(current_state))
        req = getattr(requested_state, "name", str(requested_state))
        self._safe_emit(
            self.log_message,
            "WARN",
            f"[{self.drone_id}] FSM rejected {cur} \u2192 {req}",
        )


class SwarmBackend(QObject):
    """
    Owns all DroneBackend instances and aggregates their telemetry.

    Signals
    -------
    drone_added(drone_id)           — a new backend was registered
    drone_removed(drone_id)         — a backend was removed
    swarm_telemetry_updated(dict)   — {drone_id: snapshot} at ~5 Hz
    log_message(level, text)        — forwarded from every DroneBackend
    """

    drone_added = Signal(str)
    drone_removed = Signal(str)
    swarm_telemetry_updated = Signal(dict)
    log_message = Signal(str, str)
    fsm_state_changed = Signal(str, str)  # (drone_id, fsm_state_name)

    _AGG_INTERVAL_MS = 200  # 5 Hz aggregation

    def __init__(self, parent=None):
        super().__init__(parent)
        self._backends: Dict[str, DroneBackend] = {}
        self._camera_context = None
        self._agg_timer = QTimer(self)
        self._agg_timer.setInterval(self._AGG_INTERVAL_MS)
        self._agg_timer.timeout.connect(self._aggregate)
        # Cached last aggregate result; lets us skip emit when nothing
        # changed (esp. when all drones disconnected — pure stubs).
        self._last_aggregate: Dict[str, dict] = {}
        # Timer is started lazily in add_drone() and stopped in remove_drone()
        # when no drones remain — saves ~5 wakeups/sec on idle.

    def _ensure_timer_state(self) -> None:
        """Start aggregation timer only when drones exist."""
        if self._backends and not self._agg_timer.isActive():
            self._agg_timer.start()
        elif not self._backends and self._agg_timer.isActive():
            self._agg_timer.stop()

    def set_camera_context(self, camera_context) -> None:
        self._camera_context = camera_context

    def get_camera_context(self):
        return self._camera_context

    # ── Fleet management ──────────────────────────────────────────────────

    def add_drone(
        self,
        drone_id: str,
        connection_string: str,
        drone_type: str = DRONE_TYPE_GENERIC,
        baud: Optional[int] = None,
    ) -> DroneBackend:
        backend = DroneBackend(
            drone_id, connection_string, drone_type=drone_type, baud=baud, parent=self
        )
        backend.log_message.connect(self.log_message)
        backend.fsm_state_changed.connect(self.fsm_state_changed)
        self._backends[drone_id] = backend
        self._ensure_timer_state()
        self.drone_added.emit(drone_id)
        return backend

    def set_drone_role(self, drone_id: str, role: str, leader_id: str = "") -> None:
        b = self._backends.get(drone_id)
        if b:
            b.set_swarm_role(role, leader_id)

    def set_drone_formation_offset(
        self, drone_id: str, north: float, east: float, alt: float
    ) -> None:
        b = self._backends.get(drone_id)
        if b:
            b.set_formation_offset(north, east, alt)

    def gimbal_point(
        self, drone_id: str, pitch: float, roll: float = 0.0, yaw: float = 0.0
    ) -> None:
        b = self._backends.get(drone_id)
        if b:
            b.gimbal_point(pitch, roll, yaw)

    def gimbal_home(self, drone_id: str) -> None:
        b = self._backends.get(drone_id)
        if b:
            b.gimbal_home()

    def get_gimbal_state(self, drone_id: str) -> dict:
        b = self._backends.get(drone_id)
        return b.get_gimbal_state() if b else {}

    def camera_start_stream(self, drone_id: str, source: str) -> bool:
        b = self._backends.get(drone_id)
        return b.camera_start_stream(source) if b else False

    def camera_stop_stream(self, drone_id: str) -> bool:
        b = self._backends.get(drone_id)
        return b.camera_stop_stream() if b else False

    def camera_snapshot(self, drone_id: str):
        b = self._backends.get(drone_id)
        return b.camera_snapshot() if b else False

    def camera_start_recording(self, drone_id: str, path: str) -> bool:
        b = self._backends.get(drone_id)
        return b.camera_start_recording(path) if b else False

    def camera_stop_recording(self, drone_id: str) -> bool:
        b = self._backends.get(drone_id)
        return b.camera_stop_recording() if b else False

    def get_camera_status(self, drone_id: str) -> dict:
        b = self._backends.get(drone_id)
        return b.get_camera_status() if b else {}
    
    def get_fsm_history(self, drone_id: str) -> list:
        b = self._backends.get(drone_id)
        return b.get_fsm_history() if b else []

    def change_altitude(self, drone_id: str, alt: float) -> None:
        b = self._backends.get(drone_id)
        if b:
            b.change_altitude(alt)

    def remove_drone(self, drone_id: str) -> None:
        backend = self._backends.pop(drone_id, None)
        if backend:
            backend.disconnect()
            backend.deleteLater()
        self._ensure_timer_state()
        self.drone_removed.emit(drone_id)

    def get_backend(self, drone_id: str) -> Optional[DroneBackend]:
        return self._backends.get(drone_id)

    def all_backends(self) -> Dict[str, DroneBackend]:
        return dict(self._backends)

    # ── Bulk connection ───────────────────────────────────────────────────

    def connect_all(self) -> None:
        for backend in self._backends.values():
            _run_async(backend.connect)

    def disconnect_all(self) -> None:
        for backend in self._backends.values():
            backend.disconnect()

    # ── Bulk flight commands ──────────────────────────────────────────────

    def arm_all(self, force: bool = False) -> None:
        count = len(self._backends)
        self.log_message.emit(
            "INFO", f"[SWARM] ▶ ARM ALL ({count} drones, force={force})"
        )
        for b in self._backends.values():
            b.arm(force=force)

    def disarm_all(self, force: bool = False) -> None:
        count = len(self._backends)
        self.log_message.emit(
            "INFO", f"[SWARM] ■ DISARM ALL ({count} drones, force={force})"
        )
        for b in self._backends.values():
            b.disarm(force=force)

    def takeoff_all(self, altitude: float) -> None:
        count = len(self._backends)
        self.log_message.emit(
            "INFO", f"[SWARM] ⬆ TAKEOFF ALL ({count} drones to {altitude}m)"
        )
        for b in self._backends.values():
            b.takeoff(altitude)

    def land_all(self) -> None:
        count = len(self._backends)
        self.log_message.emit("INFO", f"[SWARM] ⬇ LAND ALL ({count} drones)")
        for b in self._backends.values():
            b.land()

    def rtl_all(self) -> None:
        count = len(self._backends)
        self.log_message.emit("INFO", f"[SWARM] 🏠 RTL ALL ({count} drones)")
        for b in self._backends.values():
            b.rtl()

    # ── Internal ──────────────────────────────────────────────────────────

    def _aggregate(self) -> None:
        result: Dict[str, dict] = {}
        for did, b in self._backends.items():
            snap = b.get_telemetry_snapshot()
            if snap is not None:
                result[did] = snap
            else:
                # Drone added but never connected or disconnected — keep it visible
                result[did] = {
                    "connected": False,
                    "flight_mode": "OFFLINE",
                    "armed": False,
                    "battery_pct": -1.0,
                    "alt_rel": 0.0,
                    "groundspeed": 0.0,
                    "lat": 0.0,
                    "lon": 0.0,
                    "yaw": 0.0,
                }
        if not result:
            return
        # Skip emit if nothing changed since last tick — common case
        # when all drones are disconnected and snapshots are pure stubs.
        if result == self._last_aggregate:
            return
        self._last_aggregate = result
        self.swarm_telemetry_updated.emit(result)
