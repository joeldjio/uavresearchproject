"""
Drone — the main public API class.

This is what researchers import and use in their scripts.

Usage:
    from skymeshx import Drone

    drone = Drone("tcp:127.0.0.1:5760")
    drone.connect()
    drone.arm()
    drone.takeoff(10)

    @drone.on("altitude")
    def on_alt(v):
        if v > 15:
            drone.set_speed(3.0)

    drone.wait_for_landing()
    drone.disconnect()
"""

import threading
import time
from typing import Callable, Optional

from skymeshx.control.mission import MissionEngine, Waypoint
from skymeshx.core.connection import MAVLinkConnection
from skymeshx.core.telemetry import TelemetryState
from skymeshx.data.logger import TelemetryLogger
from skymeshx.data.store import TelemetryStore


class Drone:
    """
    High-level drone API.

    All blocking methods (arm, takeoff, goto, …) accept a timeout parameter
    and raise TimeoutError if the operation does not complete in time.
    """

    def __init__(
        self,
        connection_string,  # str or Connection object for testing
        drone_id: str = "drone",
        log_dir: str = "logs",
        auto_log: bool = True,
        baud: Optional[int] = None,
    ):
        self.id = drone_id
        # Accept either a connection string or a connection object (for testing)
        if isinstance(connection_string, str):
            self._conn = MAVLinkConnection(connection_string, baud=baud)
        else:
            self._conn = connection_string  # Assume it's a connection object
        self._logger = TelemetryLogger(log_dir) if auto_log else None
        self._store = TelemetryStore()
        self._mission = MissionEngine(self._conn)
        self._event_cbs: dict = {}
        self._stop = threading.Event()

        # Wire core events → high-level events
        self._conn.on("telemetry", self._on_telemetry)
        self._conn.on("armed", self._on_armed)
        self._conn.on("mode", self._on_mode)
        self._conn.on("statustext", lambda t, s: self._emit("statustext", t, s))
        self._conn.on("connected", lambda: self._emit("connected"))
        self._conn.on("disconnected", lambda: self._emit("disconnected"))
        self._conn.on(
            "command_ack",
            lambda name, code, res, ok: self._emit("command_ack", name, code, res, ok),
        )

    # ── Connection ────────────────────────────────────────────────────────

    def connect(self, timeout: float = 15.0) -> bool:
        ok = self._conn.connect(timeout=timeout)
        if ok and self._logger:
            self._logger.start(drone_id=self.id)
        return ok

    def disconnect(self):
        if self._logger:
            self._logger.stop()
        self._conn.disconnect()

    @property
    def connected(self) -> bool:
        return self._conn.connected

    # ── Telemetry (direct attribute access) ───────────────────────────────

    @property
    def telemetry(self) -> TelemetryState:
        return self._conn.telemetry

    @property
    def lat(self) -> float:
        return self._conn.telemetry.lat

    @property
    def lon(self) -> float:
        return self._conn.telemetry.lon

    @property
    def altitude(self) -> float:
        return self._conn.telemetry.alt_rel

    @property
    def heading(self) -> float:
        return self._conn.telemetry.yaw

    @property
    def armed(self) -> bool:
        return self._conn.telemetry.armed

    @property
    def mode(self) -> str:
        return self._conn.telemetry.flight_mode

    @property
    def battery(self) -> float:
        return self._conn.telemetry.battery_pct

    @property
    def groundspeed(self) -> float:
        return self._conn.telemetry.groundspeed

    @property
    def position(self) -> tuple:
        t = self._conn.telemetry
        return (t.lat, t.lon, t.alt_rel)

    # ── Commands ──────────────────────────────────────────────────────────

    def arm(self, timeout: float = 10.0, force: bool = False) -> bool:
        """Arm the drone. Returns immediately if already armed."""
        if self._conn.telemetry.armed:
            return True
        if self._logger:
            self._logger.log_event("arm_command", {"force": force})
        self._conn.arm(force=force)
        return self._wait_for(lambda: self._conn.telemetry.armed, timeout)

    def disarm(self, timeout: float = 5.0, force: bool = False) -> bool:
        """Disarm the drone. Returns immediately if already disarmed."""
        if not self._conn.telemetry.armed:
            return True
        if self._logger:
            self._logger.log_event("disarm_command", {"force": force})
        self._conn.disarm(force=force)
        return self._wait_for(lambda: not self._conn.telemetry.armed, timeout)

    def set_mode(self, mode: str, timeout: float = 5.0) -> bool:
        """Set flight mode. Returns immediately if already in target mode."""
        if self._conn.telemetry.flight_mode.upper() == mode.upper():
            return True
        self._conn.set_mode(mode)
        return self._wait_for(
            lambda: self._conn.telemetry.flight_mode.upper() == mode.upper(),
            timeout,
        )

    def takeoff(self, altitude: float = 10.0, timeout: float = 30.0) -> bool:
        """Takeoff to altitude with timeout.
        
        Args:
            altitude: Target altitude in meters AGL
            timeout: Maximum time to wait for takeoff completion (seconds)
            
        Returns:
            True if takeoff succeeded within timeout, False otherwise
        """
        import time
        start_time = time.time()
        
        if self._logger:
            self._logger.log_event("takeoff_command", {"altitude": altitude})
        
        # Arm with portion of timeout
        if not self.armed:
            arm_timeout = min(timeout * 0.3, 10.0)  # 30% of timeout or 10s max
            if not self.arm(timeout=arm_timeout):
                return False
        
        # Check remaining time
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            return False
        
        # Set mode with portion of remaining timeout.
        # ArduPilot: GUIDED is required before MAV_CMD_NAV_TAKEOFF.
        # PX4: MAV_CMD_NAV_TAKEOFF (22) is accepted in most modes — skip the mode
        # switch for PX4 (setting AUTO.TAKEOFF via DO_SET_MODE before arming is
        # rejected with TEMPORARILY_REJECTED while disarmed).
        ap = self._conn.telemetry.autopilot
        if ap != "px4":
            mode_timeout = min((timeout - elapsed) * 0.2, 5.0)
            self.set_mode("GUIDED", timeout=mode_timeout)  # best-effort for ArduPilot

        # Send takeoff command
        self._conn.takeoff(altitude)
        
        # Wait for altitude with remaining timeout
        elapsed = time.time() - start_time
        remaining = max(timeout - elapsed, 0.1)  # At least 0.1s
        return self._wait_for(
            lambda: self._conn.telemetry.alt_rel >= altitude * 0.85,
            remaining,
        )

    def land(self, timeout: float = 60.0) -> bool:
        """Land the drone. Returns immediately if already disarmed."""
        if not self._conn.telemetry.armed:
            return True
        if self._logger:
            self._logger.log_event("land_command", {})
        self._conn.land()
        return self._wait_for(
            lambda: not self._conn.telemetry.armed,
            timeout,
        )

    def rtl(self):
        """Return to launch and log the command."""
        if self._logger:
            self._logger.log_event("rtl_command", {})
        self._conn.rtl()

    def goto(
        self,
        lat: float,
        lon: float,
        alt: float,
        timeout: float = 60.0,
        acceptance_radius: float = 2.0,
        check_altitude: bool = True,
        check_velocity: bool = True
    ) -> bool:
        """
        Navigate to GPS coordinates with configurable arrival criteria.
        
        Args:
            lat: Target latitude (degrees)
            lon: Target longitude (degrees)
            alt: Target altitude (meters AGL)
            timeout: Maximum time to wait (seconds)
            acceptance_radius: Horizontal distance threshold (meters, default: 2.0)
            check_altitude: If True, also verify altitude within 1.0m (default: True)
            check_velocity: If True, verify groundspeed < 0.5 m/s (default: True)
            
        Returns:
            True if drone arrived at target within timeout, False otherwise
            
        Note:
            The drone is considered "arrived" when:
            - Horizontal distance < acceptance_radius
            - (Optional) Altitude error < 1.0m
            - (Optional) Groundspeed < 0.5 m/s (drone has stopped)
        """
        if self._logger:
            self._logger.log_event("goto_command", {
                "lat": lat, "lon": lon, "alt": alt,
                "acceptance_radius": acceptance_radius
            })
        
        start_time = time.time()
        
        # PX4: use SET_POSITION_TARGET_GLOBAL_INT in OFFBOARD mode for single-point
        # navigation only when already in OFFBOARD — otherwise use the MAVLink mission
        # upload path (MissionEngine) which is the correct PX4 interface for
        # waypoint missions.  For the sequential-goto fallback used here we stay in
        # whatever mode PX4 is currently in and send the position target; PX4 will
        # accept it in OFFBOARD if the GCS is already sending a stream, or it can
        # be in GUIDED (ArduPilot compat alias) on newer builds.
        # ArduPilot: switch to GUIDED before sending SET_POSITION_TARGET.
        ap = self._conn.telemetry.autopilot
        if ap != "px4":
            current_mode = self._conn.telemetry.flight_mode.upper()
            if current_mode != "GUIDED":
                mode_timeout = min(timeout * 0.2, 5.0)
                if not self.set_mode("GUIDED", timeout=mode_timeout):
                    return False
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False

        # Send goto command
        self._conn.goto(lat, lon, alt)
        
        # Define arrival condition
        def _arrived():
            # Check horizontal distance
            if self._distance_to(lat, lon) > acceptance_radius:
                return False
            
            # Check altitude if requested
            if check_altitude:
                alt_error = abs(self._conn.telemetry.alt_rel - alt)
                if alt_error > 1.0:
                    return False
            
            # Check velocity if requested (drone has stopped)
            if check_velocity:
                if self._conn.telemetry.groundspeed > 0.5:
                    return False
            
            return True
        
        # Use remaining time to wait for arrival
        elapsed = time.time() - start_time
        remaining = max(timeout - elapsed, 0.1)
        
        return self._wait_for(_arrived, remaining)

    def set_speed(self, speed_ms: float):
        self._conn.set_speed(speed_ms)

    def wait(self, seconds: float):
        time.sleep(seconds)

    def wait_for_landing(self, timeout: float = 300.0) -> bool:
        return self._wait_for(lambda: not self._conn.telemetry.armed, timeout)

    # ── Mission ───────────────────────────────────────────────────────────

    @property
    def mission(self) -> MissionEngine:
        return self._mission

    def run_mission(
        self, waypoints: list, wait: bool = True, timeout: float = 600.0
    ) -> bool:
        self._mission.clear()
        for wp in waypoints:
            if isinstance(wp, dict):
                self._mission.add(Waypoint(**wp))
            else:
                self._mission.add(wp)
        self._mission.upload()
        self._mission.start()
        if wait:
            return self._mission.wait_done(timeout=timeout)
        return True

    # ── Data access ───────────────────────────────────────────────────────

    @property
    def store(self) -> TelemetryStore:
        return self._store

    def get_history(self, last_n: int = 100) -> list:
        return self._store.get(self.id, last_n=last_n)

    def export_csv(self) -> str:
        return self._store.export_csv(self.id)

    # ── Events ────────────────────────────────────────────────────────────

    def on(self, event: str, callback: Optional[Callable] = None):
        """Register event callback. Can be used as decorator."""
        if callback is None:

            def decorator(fn):
                self._event_cbs.setdefault(event, []).append(fn)
                return fn

            return decorator
        self._event_cbs.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callable):
        if event in self._event_cbs:
            self._event_cbs[event] = [
                c for c in self._event_cbs[event] if c is not callback
            ]

    # ── Internal ──────────────────────────────────────────────────────────

    def _emit(self, event: str, *args):
        for cb in self._event_cbs.get(event, []):
            try:
                cb(*args)
            except Exception as e:
                print(f"[drone] event error ({event}): {e}")

    def _on_telemetry(self, tel: TelemetryState):
        snap = tel.snapshot()
        self._store.push(self.id, snap)
        if self._logger:
            self._logger.log(snap)
        self._emit("telemetry", tel)
    
    def _on_armed(self, armed: bool):
        """Handle armed state change and log event."""
        if self._logger:
            self._logger.log_event("armed" if armed else "disarmed", {"armed": armed})
        self._emit("armed", armed)
    
    def _on_mode(self, mode: str):
        """Handle mode change and log event."""
        if self._logger:
            self._logger.log_event("mode_change", {"mode": mode})
        self._emit("mode", mode)

    def _wait_for(self, condition: Callable, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if condition():
                return True
            time.sleep(0.1)
        return False

    def _distance_to(self, lat: float, lon: float) -> float:
        import math

        t = self._conn.telemetry
        dlat = math.radians(lat - t.lat)
        dlon = math.radians(lon - t.lon)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(t.lat))
            * math.cos(math.radians(lat))
            * math.sin(dlon / 2) ** 2
        )
        return 6371000 * 2 * math.asin(math.sqrt(a))
