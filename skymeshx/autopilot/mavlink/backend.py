"""
MAVLink backend — connects to ArduPilot or PX4 via MAVLink protocol.

Supports:
    Serial:   /dev/ttyUSB0, COM3
    UDP:      udp:127.0.0.1:14550
    TCP:      tcp:127.0.0.1:5760
    SITL:     tcp:127.0.0.1:5760 (ArduPilot SITL default)

Auto-detects autopilot type from HEARTBEAT.autopilot field.
"""
import math
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from skymeshx.autopilot.base import AutopilotBackend, TelemetrySnapshot
from skymeshx.exceptions import DependencyError

try:
    from pymavlink import mavutil
    _MAV_OK = True
except ImportError:
    _MAV_OK = False

_COPTER_MODES = {
    0:"STABILIZE",1:"ACRO",2:"ALT_HOLD",3:"AUTO",4:"GUIDED",
    5:"LOITER",6:"RTL",7:"CIRCLE",9:"LAND",16:"POSHOLD",
    17:"BRAKE",18:"THROW",21:"SMART_RTL",
}
_PX4_MODES = {1:"MANUAL",2:"ALTCTL",3:"POSCTL",4:"AUTO",6:"OFFBOARD",7:"STABILIZED"}


class MAVLinkBackend(AutopilotBackend):
    """
    pymavlink-based backend. Works with ArduPilot and PX4.
    Stream rates are configured conservatively for Pi 1 compatibility.
    """

    def __init__(self, stream_rates: Optional[Dict[int, int]] = None):
        self._conn   = None
        self._tel    = TelemetrySnapshot()
        self._lock   = threading.Lock()
        self._cbs:   Dict[str, List[Callable]] = {}
        self._rx_thread: Optional[threading.Thread] = None
        self._running    = False
        self._autopilot  = "unknown"
        # stream_id → rate_hz
        self._stream_rates = stream_rates or {6: 4, 10: 4, 11: 2, 2: 1}

    # ── Connection ─────────────────────────────────────────────────────────

    def connect(self, connection_string: str, baud: int = 57600, **kwargs) -> bool:
        if not _MAV_OK:
            raise DependencyError("pymavlink", "pip install pymavlink")
        try:
            self._conn = mavutil.mavlink_connection(
                connection_string, baud=baud,
                source_system=255, autoreconnect=True,
            )
            hb = self._conn.wait_heartbeat(timeout=15)
            if hb is None:
                return False
            self._detect_autopilot(hb)
            self._request_streams()
            self._running = True
            self._rx_thread = threading.Thread(
                target=self._rx_loop, daemon=True, name="mav-rx"
            )
            self._rx_thread.start()
            return True
        except Exception as e:
            print(f"[mavlink] connect error: {e}")
            return False

    def disconnect(self):
        self._running = False
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def is_connected(self) -> bool:
        if not self._conn:
            return False
        return (time.time() - self._tel.timestamp) < 5.0

    @property
    def telemetry(self) -> TelemetrySnapshot:
        return self._tel

    @property
    def autopilot_type(self) -> str:
        return self._autopilot

    # ── Commands ────────────────────────────────────────────────────────────

    def arm(self, force: bool = False) -> bool:
        self._cmd_long(400, 1.0, 21196.0 if force else 0.0)
        return True

    def disarm(self, force: bool = False) -> bool:
        self._cmd_long(400, 0.0, 21196.0 if force else 0.0)
        return True

    def takeoff(self, altitude: float) -> bool:
        # PX4 uses TAKEOFF sub-mode; ArduPilot uses GUIDED before MAV_CMD_NAV_TAKEOFF.
        if self._autopilot == "px4":
            self._cmd_long(176, 1, 4, 2)  # DO_SET_MODE: main=AUTO(4), sub=TAKEOFF(2)
        else:
            self.set_mode("GUIDED")
        time.sleep(0.2)
        self._cmd_long(22, 0,0,0,0,0,0, altitude)
        return True

    def land(self) -> bool:
        self._cmd_long(21)
        return True

    def rtl(self) -> bool:
        self._cmd_long(20)
        return True

    def goto(self, lat: float, lon: float, alt: float) -> bool:
        if not self._conn:
            return False
        self._conn.mav.set_position_target_global_int_send(
            0,
            self._conn.target_system,
            self._conn.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            0b0000111111111000,
            int(lat * 1e7), int(lon * 1e7), alt,
            0,0,0, 0,0,0, 0,0,
        )
        return True

    def set_mode(self, mode: str) -> bool:
        # Try ArduPilot mode map first, then PX4 if not found.
        mode_map = {v: k for k, v in _COPTER_MODES.items()}
        num = mode_map.get(mode.upper())
        if num is not None:
            self._cmd_long(176, 1, num)
            return True
        # PX4 mode map
        px4_map = {v: k for k, v in _PX4_MODES.items()}
        px4_num = px4_map.get(mode.upper())
        if px4_num is not None:
            self._cmd_long(176, 1, px4_num)
            return True
        return False

    def send_command(self, cmd_id: int, *params) -> bool:
        p = list(params) + [0] * (7 - len(params))
        self._cmd_long(cmd_id, *p[:7])
        return True

    def set_live_param(self, name: str, value: float) -> bool:
        """Send PARAM_SET to the vehicle via MAVLink.

        Args:
            name:  Parameter name (max 16 chars, ArduPilot convention).
            value: New value as float.

        Returns:
            True if the message was sent (no ACK waiting), False if not connected.
        """
        if not self._conn:
            return False
        pname = name.encode("utf-8")[:16].ljust(16, b"\x00")
        self._conn.mav.param_set_send(
            self._conn.target_system,
            self._conn.target_component,
            pname,
            float(value),
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
        )
        return True

    def fetch_all_params(self, timeout: float = 10.0) -> Dict[str, float]:
        """Request all parameters via PARAM_REQUEST_LIST and collect PARAM_VALUE replies.

        Runs synchronously (blocks the calling thread).  Intended to be called
        from a worker thread, not the Qt main thread.

        Args:
            timeout: Maximum seconds to wait for the full parameter list.

        Returns:
            Dict mapping param name → value.  Empty dict on error/timeout.
        """
        if not self._conn or not _MAV_OK:
            return {}
        params: Dict[str, float] = {}
        expected_count = None
        self._conn.mav.param_request_list_send(
            self._conn.target_system,
            self._conn.target_component,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            msg = self._conn.recv_match(
                type="PARAM_VALUE", blocking=True, timeout=min(remaining, 1.0)
            )
            if msg is None:
                break
            pname = msg.param_id.rstrip("\x00")
            params[pname] = float(msg.param_value)
            if expected_count is None:
                expected_count = msg.param_count
            if expected_count and len(params) >= expected_count:
                break
        return params

    def on_message(self, msg_type: str, cb: Callable):
        self._cbs.setdefault(msg_type, []).append(cb)

    def request_stream(self, stream_id: int, rate_hz: float):
        if self._conn:
            self._conn.mav.request_data_stream_send(
                self._conn.target_system,
                self._conn.target_component,
                stream_id, int(rate_hz), 1,
            )

    # ── Internal ────────────────────────────────────────────────────────────

    def _detect_autopilot(self, hb):
        ap = getattr(hb, "autopilot", 0)
        self._autopilot = "ardupilot" if ap == 3 else "px4" if ap == 12 else "unknown"

    def _request_streams(self):
        for sid, rate in self._stream_rates.items():
            self.request_stream(sid, rate)

    def _rx_loop(self):
        while self._running:
            if not self._conn:
                time.sleep(0.5)
                continue
            try:
                msg = self._conn.recv_match(blocking=True, timeout=2.0)
            except Exception:
                time.sleep(0.2)
                continue
            if msg:
                self._parse(msg)

    def _parse(self, msg):
        t   = msg.get_type()
        tel = self._tel
        if t == "HEARTBEAT":
            with self._lock:
                tel.armed       = bool(msg.base_mode & 0x80)
                tel.flight_mode = self._decode_mode(msg)
                tel.timestamp   = time.time()
        elif t == "GLOBAL_POSITION_INT":
            with self._lock:
                tel.lat     = msg.lat / 1e7
                tel.lon     = msg.lon / 1e7
                tel.alt     = msg.alt / 1000.0
                tel.alt_rel = msg.relative_alt / 1000.0
                tel.vx      = msg.vx / 100.0
                tel.vy      = msg.vy / 100.0
                tel.vz      = msg.vz / 100.0
                tel.groundspeed = math.hypot(tel.vx, tel.vy)
        elif t == "ATTITUDE":
            with self._lock:
                tel.roll  = round(math.degrees(msg.roll), 2)
                tel.pitch = round(math.degrees(msg.pitch), 2)
                tel.yaw   = round(math.degrees(msg.yaw) % 360, 2)
        elif t == "VFR_HUD":
            with self._lock:
                tel.groundspeed = msg.groundspeed
                tel.alt         = msg.alt
        elif t in ("SYS_STATUS", "BATTERY_STATUS"):
            with self._lock:
                if hasattr(msg, "battery_remaining") and msg.battery_remaining >= 0:
                    tel.battery_pct = float(msg.battery_remaining)
                if hasattr(msg, "voltage_battery") and msg.voltage_battery > 0:
                    tel.battery_v = msg.voltage_battery / 1000.0
        elif t == "GPS_RAW_INT":
            with self._lock:
                tel.gps_fix    = msg.fix_type
                tel.satellites = msg.satellites_visible
        # Fire callbacks
        for cb in self._cbs.get(t, []):
            try:
                cb(msg)
            except Exception as e:
                print(f"[mavlink] cb error: {e}")
        for cb in self._cbs.get("*", []):
            try:
                cb(msg)
            except Exception:
                pass

    def _cmd_long(self, cmd, p1=0,p2=0,p3=0,p4=0,p5=0,p6=0,p7=0):
        if self._conn:
            self._conn.mav.command_long_send(
                self._conn.target_system,
                self._conn.target_component,
                cmd, 0,
                float(p1), float(p2), float(p3),
                float(p4), float(p5), float(p6), float(p7),
            )

    def _decode_mode(self, hb) -> str:
        if self._autopilot == "ardupilot":
            return _COPTER_MODES.get(hb.custom_mode, f"MODE_{hb.custom_mode}")
        elif self._autopilot == "px4":
            return _PX4_MODES.get((hb.custom_mode >> 16) & 0xFF, f"PX4_{hb.custom_mode}")
        return f"MODE_{hb.custom_mode}"
