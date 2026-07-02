"""
MAVLinkConnection — core MAVLink connection layer.

Supports:
  - ArduPilot (Copter, Plane, Rover)
  - PX4
  - Serial, TCP, UDP connections

Usage:
    conn = MAVLinkConnection("tcp:127.0.0.1:5760")
    conn.connect()
    print(conn.telemetry.lat, conn.telemetry.lon)
    conn.disconnect()
"""

import math
import re
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from skymeshx.core.telemetry import TelemetryState

try:
    from pymavlink import mavextra, mavutil

    _MAVLINK_OK = True
except ImportError:
    _MAVLINK_OK = False


# ArduPilot custom mode map
_ARDUPILOT_MODES = {
    0: "STABILIZE",
    1: "ACRO",
    2: "ALT_HOLD",
    3: "AUTO",
    4: "GUIDED",
    5: "LOITER",
    6: "RTL",
    7: "CIRCLE",
    9: "LAND",
    11: "DRIFT",
    13: "SPORT",
    14: "FLIP",
    15: "AUTOTUNE",
    16: "POSHOLD",
    17: "BRAKE",
    18: "THROW",
    19: "AVOID_ADSB",
    20: "GUIDED_NOGPS",
    21: "SMART_RTL",
    22: "FLOWHOLD",
    23: "FOLLOW",
    24: "ZIGZAG",
}

# PX4 main mode map
_PX4_MAIN_MODES = {
    1: "MANUAL",
    2: "ALTCTL",
    3: "POSCTL",
    4: "AUTO",
    5: "ACRO",
    6: "OFFBOARD",
    7: "STABILIZED",
    8: "RATTITUDE",
}

_PX4_SUB_MODES_AUTO = {
    1: "READY",
    2: "TAKEOFF",
    3: "LOITER",
    4: "MISSION",
    5: "RTL",
    6: "LAND",
    8: "FOLLOW_TARGET",
}

# MAV_CMD identifiers we care about (subset). Used for nicer ACK log lines.
_MAV_CMD_NAMES = {
    16: "NAV_WAYPOINT",
    20: "NAV_RETURN_TO_LAUNCH",
    21: "NAV_LAND",
    22: "NAV_TAKEOFF",
    176: "DO_SET_MODE",
    178: "DO_CHANGE_SPEED",
    400: "COMPONENT_ARM_DISARM",
}

# MAV_RESULT values — see mavlink/common.xml.
_MAV_RESULT_NAMES = {
    0: "ACCEPTED",
    1: "TEMPORARILY_REJECTED",
    2: "DENIED",
    3: "UNSUPPORTED",
    4: "FAILED",
    5: "IN_PROGRESS",
    6: "CANCELLED",
}

_MAV_TYPE_NAMES = {
    0: "GENERIC",
    1: "FIXED_WING",
    2: "QUADROTOR",
    3: "COAXIAL",
    4: "HELICOPTER",
    5: "ANTENNA_TRACKER",
    6: "GCS",
    7: "AIRSHIP",
    8: "FREE_BALLOON",
    9: "ROCKET",
    10: "GROUND_ROVER",
    11: "SURFACE_BOAT",
    12: "SUBMARINE",
    13: "HEXAROTOR",
    14: "OCTOROTOR",
    15: "TRICOPTER",
    16: "FLAPPING_WING",
    17: "KITE",
    18: "ONBOARD_CONTROLLER",
    19: "VTOL_DUOROTOR",
    20: "VTOL_QUADROTOR",
    21: "VTOL_TILTROTOR",
    26: "GIMBAL",
    27: "ADSB",
    28: "PARAFOIL",
    29: "DODECAROTOR",
    30: "CAMERA",
    31: "CHARGING_STATION",
    32: "FLARM",
    33: "SERVO",
    34: "ODID",
    35: "DECAROTOR",
    36: "BATTERY",
    37: "PARACHUTE",
    38: "LOG",
    39: "OSD",
    40: "IMU",
    41: "GPS",
    42: "WINCH",
}


class MAVLinkConnection:
    """
    Thread-safe MAVLink connection.

    Events (register with .on(event, callback)):
        "connected"    — fired once connection is established
        "disconnected" — fired on disconnect
        "telemetry"    — fired on every telemetry update (TelemetryState)
        "message"      — fired on every raw MAVLink message
        "statustext"   — fired on STATUSTEXT (text, severity)
        "armed"        — fired when armed state changes (bool)
        "mode"         — fired when flight mode changes (str)
    
    Thread Safety
    -------------
    All public methods are thread-safe and can be called from any thread.
    Internal state (telemetry, connection status) is protected by locks.
    Event callbacks are dispatched from the receive thread - keep handlers fast.
    Command methods (goto, set_mode, arm, etc.) use a command lock to serialize access.
    """

    STREAM_RATES = {
        1: 4,  # RAW_SENSORS
        2: 4,  # EXTENDED_STATUS (battery, etc.)
        3: 2,  # RC_CHANNELS
        6: 4,  # POSITION (GPS)
        10: 10,  # EXTRA1 (attitude)
        11: 4,  # EXTRA2 (VFR_HUD)
        12: 2,  # EXTRA3 (AHRS, wind)
    }

    def __init__(
        self,
        connection_string: str,
        source_system: int = 255,
        auto_reconnect: bool = True,
        baud: Optional[int] = None,
    ):
        if not _MAVLINK_OK:
            raise ImportError("pymavlink not installed: pip install pymavlink")
        self.connection_string = connection_string
        self.source_system = source_system
        self._baud = baud
        self.telemetry = TelemetryState()
        self._mav = None
        self._thread = None
        self._stop = threading.Event()
        self._connected = False
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        # Tracks recently-issued commands so incoming COMMAND_ACK messages
        # can be correlated back to their cmd_id and reported with a name.
        # Bounded to last 32 entries (MAVLink doesn't carry a sequence id
        # on COMMAND_ACK so we just remember the most recent send per cmd).
        self._pending_cmds: Dict[int, float] = {}
        self._cmd_lock = threading.Lock()
        # Last NACK — useful for the UI to surface in a status bar.
        self.last_nack: Optional[Tuple[str, str]] = None  # (cmd_name, result_name)
        self._auto_reconnect = auto_reconnect

    # ── Public API ───────────────────────────────────────────────────────────

    @staticmethod
    def validate_connection_string(s: str) -> str:
        """Validate a MAVLink connection string.

        Returns the (possibly stripped) string on success, raises
        ``ValueError`` with a descriptive message on failure.

        Accepted formats:
          tcp:HOST:PORT    e.g. tcp:127.0.0.1:5760
          udp:HOST:PORT    e.g. udp:127.0.0.1:14550
          udpin:HOST:PORT  e.g. udpin:0.0.0.0:14550
          /dev/ttyUSBx     Linux serial device (optionally :BAUD)
          serial:/dev/…    pymavlink serial prefix form
          COMx             Windows serial port (optionally :BAUD)
        """
        if not s or not s.strip():
            raise ValueError("Connection string must not be empty")
        s = s.strip()
        # tcp/udp/udpin/udpout:HOST:PORT
        m = re.match(r"^(tcp|udp|udpin|udpout):([^:]+):(\d+)$", s, re.IGNORECASE)
        if m:
            port = int(m.group(3))
            if not (1 <= port <= 65535):
                raise ValueError(f"Port {port} is out of range (1-65535)")
            return s
        # Linux serial: /dev/tty* (bare or with :BAUD suffix)
        if re.match(r"^/dev/", s):
            return s
        # pymavlink serial: prefix form
        if re.match(r"^serial:/dev/", s):
            return s
        # Windows COM port: COMx or COMx:BAUD
        if re.match(r"^COM\d+(?::\d+)?$", s, re.IGNORECASE):
            return s
        raise ValueError(
            f"Unrecognized connection string {s!r}. "
            "Expected tcp:HOST:PORT, udp:HOST:PORT, udpin:HOST:PORT, "
            "/dev/ttyUSBx[:BAUD], serial:/dev/..., or COMx[:BAUD]"
        )

    def connect(self, timeout: float = 15.0) -> bool:
        if self._connected:
            return True
        try:
            self.validate_connection_string(self.connection_string)
        except ValueError as e:
            self._emit("statustext", str(e), 3)
            return False
        self._stop.clear()
        try:
            # For Windows COM ports, pymavlink needs baud as separate parameter
            if self._baud is not None:
                self._mav = mavutil.mavlink_connection(
                    self.connection_string,
                    baud=self._baud,
                    source_system=self.source_system,
                    autoreconnect=True,
                )
            else:
                self._mav = mavutil.mavlink_connection(
                    self.connection_string,
                    source_system=self.source_system,
                    autoreconnect=True,
                )
            hb = self._mav.wait_heartbeat(timeout=timeout)
            if hb is None:
                return False
        except Exception as e:
            self._emit("statustext", f"Connection error: {e}", 3)
            return False

        self._detect_autopilot(hb)
        self._connected = True
        self._request_streams()
        self._request_autopilot_version()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="mav-rx")
        self._thread.start()
        self._emit("connected")
        return True

    def disconnect(self):
        self._stop.set()
        self._connected = False
        if self._mav:
            try:
                self._mav.close()
            except Exception:
                pass
            self._mav = None
        self._emit("disconnected")

    @property
    def connected(self) -> bool:
        return self._connected

    def on(self, event: str, callback: Callable):
        self._listeners.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callable):
        if event in self._listeners:
            self._listeners[event] = [
                c for c in self._listeners[event] if c is not callback
            ]

    # ── Commands ─────────────────────────────────────────────────────────────

    def arm(self, force: bool = False) -> bool:
        param2 = 21196.0 if force else 0.0
        return self._command_long(400, 1.0, param2)

    def disarm(self, force: bool = False) -> bool:
        param2 = 21196.0 if force else 0.0
        return self._command_long(400, 0.0, param2)

    def set_mode(self, mode: str) -> bool:
        mode = mode.upper()
        if self.telemetry.autopilot == "px4":
            return self._set_mode_px4(mode)
        return self._set_mode_ardupilot(mode)

    def takeoff(self, altitude: float = 10.0) -> bool:
        return self._command_long(22, 0, 0, 0, 0, 0, 0, altitude)

    def land(self) -> bool:
        return self._command_long(21)

    def rtl(self) -> bool:
        return self._command_long(20)

    def goto(self, lat: float, lon: float, alt: float) -> bool:
        """Fly to GPS coordinate using SET_POSITION_TARGET_GLOBAL_INT.

        Works with both ArduPilot (GUIDED mode) and PX4 (OFFBOARD mode).
        Frame: MAV_FRAME_GLOBAL_RELATIVE_ALT (6) — alt is metres above home.
        type_mask 0x0FF8: use only position, ignore velocity/accel/yaw.
        """
        if not self._mav:
            return False
        try:
            # MAV_FRAME_GLOBAL_RELATIVE_ALT = 6
            # type_mask bits: 0=use, 1=ignore
            #   bits 0-2  → position (clear → use)
            #   bits 3-5  → velocity (set → ignore)
            #   bits 6-8  → acceleration (set → ignore)
            #   bit  10   → yaw (set → ignore)
            #   bit  11   → yaw_rate (set → ignore)
            #   0b_1111_1111_1000 = 0x0FF8
            self._mav.mav.set_position_target_global_int_send(
                0,  # time_boot_ms (unused)
                self._mav.target_system,
                self._mav.target_component,
                6,  # MAV_FRAME_GLOBAL_RELATIVE_ALT
                0x0FF8,  # type_mask: position only
                int(lat * 1e7),  # lat_int  (deg × 1e7)
                int(lon * 1e7),  # lon_int  (deg × 1e7)
                float(alt),  # alt (m above home)
                0.0,
                0.0,
                0.0,  # vx, vy, vz  (ignored)
                0.0,
                0.0,
                0.0,  # afx, afy, afz (ignored)
                0.0,
                0.0,  # yaw, yaw_rate (ignored)
            )
        except Exception as e:
            self._emit("statustext", f"goto error: {e}", 3)
            return False
        return True

    def set_speed(self, speed_ms: float) -> bool:
        return self._command_long(178, 1, speed_ms, -1, 0)

    # Whitelist of allowed MAVLink message types for send_raw()
    # This prevents command injection attacks via arbitrary message types
    ALLOWED_RAW_MESSAGES = {
        # Position/velocity commands
        "set_position_target_local_ned",
        "set_position_target_global_int",
        "set_attitude_target",
        # Mission commands
        "mission_item",
        "mission_item_int",
        "mission_count",
        "mission_request",
        "mission_ack",
        "mission_clear_all",
        # Parameter commands
        "param_set",
        "param_request_read",
        "param_request_list",
        # Other safe commands
        "command_long",
        "command_int",
        "manual_control",
        "rc_channels_override",
        "set_mode",
        "heartbeat",
    }

    def send_raw(self, msg_type: str, **kwargs):
        """
        Send a raw MAVLink message.
        
        Security
        --------
        Only whitelisted message types are allowed to prevent command injection.
        If you need to send a message type not in the whitelist, add it to
        ALLOWED_RAW_MESSAGES after security review.
        
        Raises
        ------
        ValueError
            If msg_type is not in the whitelist
        """
        if msg_type not in self.ALLOWED_RAW_MESSAGES:
            raise ValueError(
                f"Message type '{msg_type}' not in whitelist. "
                f"Allowed types: {sorted(self.ALLOWED_RAW_MESSAGES)}"
            )
        if self._mav:
            getattr(self._mav.mav, f"{msg_type}_send")(**kwargs)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _emit(self, event: str, *args):
        # TS-01 FIX: Create snapshot of callbacks under lock to prevent
        # iterator invalidation if on()/off() is called during iteration
        with self._lock:
            callbacks = list(self._listeners.get(event, []))
        # Call callbacks outside lock to avoid deadlock if callback calls back into connection
        for cb in callbacks:
            try:
                cb(*args)
            except Exception as e:
                print(f"[core] listener error ({event}): {e}")

    def _command_long(self, cmd, p1=0, p2=0, p3=0, p4=0, p5=0, p6=0, p7=0) -> bool:
        if not self._mav:
            return False
        try:
            self._mav.mav.command_long_send(
                self._mav.target_system,
                self._mav.target_component,
                cmd,
                0,
                p1,
                p2,
                p3,
                p4,
                p5,
                p6,
                p7,
            )
        except Exception as e:
            self._emit("statustext", f"command_long send error (cmd {cmd}): {e}", 3)
            return False
        with self._cmd_lock:
            self._pending_cmds[int(cmd)] = time.time()
            # TS-04 FIX: Efficient cleanup - only when dict grows large
            # Avoids O(n) iteration on every command and prevents dict modification during iteration
            if len(self._pending_cmds) > 100:
                cutoff = time.time() - 10.0
                self._pending_cmds = {
                    k: t for k, t in self._pending_cmds.items() if t >= cutoff
                }
        return True

    def _detect_autopilot(self, heartbeat):
        ap = heartbeat.autopilot
        if ap == 3:
            self.telemetry.update(autopilot="ardupilot")
        elif ap == 12:
            self.telemetry.update(autopilot="px4")
        else:
            self.telemetry.update(autopilot="unknown")
        vehicle_type = _MAV_TYPE_NAMES.get(
            getattr(heartbeat, "type", -1), f"TYPE_{getattr(heartbeat, 'type', -1)}"
        )
        self.telemetry.update(vehicle_type=vehicle_type)

    def _request_streams(self):
        if not self._mav:
            return
        for sid, rate in self.STREAM_RATES.items():
            self._mav.mav.request_data_stream_send(
                self._mav.target_system,
                self._mav.target_component,
                sid,
                rate,
                1,
            )

    def _request_autopilot_version(self):
        if not self._mav:
            return
        try:
            self._mav.mav.command_long_send(
                self._mav.target_system,
                self._mav.target_component,
                512,
                0,
                148,
                0,
                0,
                0,
                0,
                0,
                0,
            )
        except Exception as e:
            self._emit("statustext", f"autopilot version request error: {e}", 4)

    def _set_mode_ardupilot(self, mode: str) -> bool:
        mode_map = {v: k for k, v in _ARDUPILOT_MODES.items()}
        num = mode_map.get(mode)
        if num is None:
            return False
        return self._command_long(176, 1, num)

    def _set_mode_px4(self, mode: str) -> bool:
        base_mode = 1
        for num, name in _PX4_MAIN_MODES.items():
            if name == mode:
                return self._command_long(176, base_mode, num)
        return False

    def _loop(self):
        """Outer receive loop with optional exponential-backoff reconnect."""
        while not self._stop.is_set():
            try:
                self._recv_loop()
            except Exception:
                pass
            if self._stop.is_set() or not self._auto_reconnect:
                break
            # Connection lost — notify and attempt reconnect.
            self._connected = False
            self._emit("disconnected")
            self._reconnect_loop()

    def _recv_loop(self):
        """Inner loop: receive and dispatch MAVLink messages."""
        while not self._stop.is_set() and self._mav:
            msg = self._mav.recv_match(blocking=True, timeout=1.0)
            if msg is None:
                continue
            self._parse(msg)

    def _reconnect_loop(self):
        """Try to re-establish the connection with exponential backoff.

        Blocks until either a successful reconnect or ``_stop`` is set.
        Backoff sequence: 1s, 2s, 4s, 8s, 16s, capped at 30s.
        """
        backoff = 1.0
        attempt = 0
        while not self._stop.is_set():
            attempt += 1
            print(f"[mav] Reconnect attempt {attempt}, waiting {backoff:.0f}s...")
            self._stop.wait(backoff)
            if self._stop.is_set():
                return
            try:
                self._mav = mavutil.mavlink_connection(
                    self.connection_string,
                    source_system=self.source_system,
                    autoreconnect=True,
                )
                hb = self._mav.wait_heartbeat(timeout=10.0)
                if hb is None:
                    raise ConnectionError("No heartbeat received")
            except Exception as e:
                print(f"[mav] Reconnect failed: {e}")
                backoff = min(backoff * 2, 30.0)
                continue
            # Reconnect successful.
            self._detect_autopilot(hb)
            self._connected = True
            self._request_streams()
            self._request_autopilot_version()
            print(f"[mav] Reconnected after {attempt} attempt(s)")
            self._emit("connected")
            return

    def _parse(self, msg):
        t = msg.get_type()
        tel = self.telemetry
        self._emit("message", msg)

        if t == "HEARTBEAT":
            armed = bool(msg.base_mode & 0x80)
            if armed != tel.armed:
                tel.update(armed=armed)
                self._emit("armed", armed)
            mode = self._decode_mode(msg)
            if mode != tel.flight_mode:
                tel.update(flight_mode=mode)
                self._emit("mode", mode)
            vehicle_type = _MAV_TYPE_NAMES.get(
                getattr(msg, "type", -1), f"TYPE_{getattr(msg, 'type', -1)}"
            )
            tel.update(
                last_heartbeat=time.time(),
                system_status=msg.system_status,
                vehicle_type=vehicle_type,
            )

        elif t == "GLOBAL_POSITION_INT":
            tel.update(
                lat=msg.lat / 1e7,
                lon=msg.lon / 1e7,
                alt=msg.alt / 1000.0,
                alt_rel=msg.relative_alt / 1000.0,
                vx=msg.vx / 100.0,
                vy=msg.vy / 100.0,
                vz=msg.vz / 100.0,
                last_gps=time.time(),
            )
            self._emit("telemetry", tel)

        elif t == "GPS_RAW_INT":
            tel.update(gps_fix=msg.fix_type, satellites=msg.satellites_visible)

        elif t == "ATTITUDE":
            tel.update(
                roll=math.degrees(msg.roll),
                pitch=math.degrees(msg.pitch),
                yaw=math.degrees(msg.yaw) % 360,
                last_attitude=time.time(),
            )
            self._emit("telemetry", tel)

        elif t == "VFR_HUD":
            tel.update(
                airspeed=msg.airspeed,
                groundspeed=msg.groundspeed,
                alt=msg.alt,
                climb=msg.climb,
                throttle=msg.throttle,
            )

        elif t == "BATTERY_STATUS":
            if msg.voltages and msg.voltages[0] != 65535:
                tel.update(battery_v=msg.voltages[0] / 1000.0)
            bpct = (
                float(msg.battery_remaining)
                if msg.battery_remaining > 0
                else (-1.0 if msg.battery_remaining < 0 else tel.battery_pct)
            )
            tel.update(
                current_a=msg.current_battery / 100.0
                if msg.current_battery >= 0
                else 0.0,
                battery_pct=bpct,
            )

        elif t == "SYS_STATUS":
            # Only update from SYS_STATUS if > 0 (SITL often sends 0 when not simulating battery)
            if msg.battery_remaining > 0:
                tel.update(battery_pct=float(msg.battery_remaining))
            if msg.voltage_battery > 0:
                tel.update(battery_v=msg.voltage_battery / 1000.0)

        elif t == "RAW_IMU":
            tel.update(
                accel_x=msg.xacc / 1000.0,
                accel_y=msg.yacc / 1000.0,
                accel_z=msg.zacc / 1000.0,
                gyro_x=msg.xgyro / 1000.0,
                gyro_y=msg.ygyro / 1000.0,
                gyro_z=msg.zgyro / 1000.0,
            )

        elif t == "HOME_POSITION":
            tel.update(
                home_lat=msg.latitude / 1e7,
                home_lon=msg.longitude / 1e7,
                home_alt=msg.altitude / 1000.0,
            )

        elif t == "STATUSTEXT":
            self._emit("statustext", msg.text, msg.severity)

        elif t == "COMMAND_ACK":
            cmd_id = int(getattr(msg, "command", -1))
            result = int(getattr(msg, "result", -1))
            cmd_name = _MAV_CMD_NAMES.get(cmd_id, f"CMD_{cmd_id}")
            res_name = _MAV_RESULT_NAMES.get(result, f"RESULT_{result}")
            success = result == 0
            with self._cmd_lock:
                self._pending_cmds.pop(cmd_id, None)
            if not success:
                self.last_nack = (cmd_name, res_name)
                # IN_PROGRESS is informational, not an error.
                if result != 5:
                    self._emit(
                        "statustext",
                        f"NACK {cmd_name} → {res_name}",
                        4,  # MAV_SEVERITY_WARNING
                    )
            self._emit("command_ack", cmd_name, result, res_name, success)

        elif t == "AUTOPILOT_VERSION":

            def _version_u32(value):
                try:
                    value = int(value)
                except Exception:
                    return ""
                major = (value >> 24) & 0xFF
                minor = (value >> 16) & 0xFF
                patch = (value >> 8) & 0xFF
                fw_type = value & 0xFF
                return f"{major}.{minor}.{patch} ({fw_type})"

            def _bytes_hex(value):
                if value is None:
                    return ""
                try:
                    return bytes(value).hex()
                except Exception:
                    return ""

            tel.update(
                firmware_version=_version_u32(getattr(msg, "flight_sw_version", 0)),
                board_version=str(getattr(msg, "board_version", "")),
                vendor_id=int(getattr(msg, "vendor_id", 0) or 0),
                product_id=int(getattr(msg, "product_id", 0) or 0),
                flight_custom_version=_bytes_hex(
                    getattr(msg, "flight_custom_version", None)
                ),
                middleware_custom_version=_bytes_hex(
                    getattr(msg, "middleware_custom_version", None)
                ),
                os_custom_version=_bytes_hex(getattr(msg, "os_custom_version", None)),
            )

    def _decode_mode(self, hb) -> str:
        ap = self.telemetry.autopilot
        if ap == "ardupilot":
            return _ARDUPILOT_MODES.get(hb.custom_mode, f"MODE_{hb.custom_mode}")
        elif ap == "px4":
            main = (hb.custom_mode >> 16) & 0xFF
            sub = (hb.custom_mode >> 24) & 0xFF
            name = _PX4_MAIN_MODES.get(main, f"MAIN_{main}")
            if main == 4:
                name = _PX4_SUB_MODES_AUTO.get(sub, name)
            return name
        return f"MODE_{hb.custom_mode}"
