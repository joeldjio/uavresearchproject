"""
MissionEngine — upload/run/monitor MAVLink missions.

Waypoint format follows MAVLink MISSION_ITEM_INT.

Usage:
    mission = MissionEngine(connection)
    mission.add(Waypoint(lat=48.137, lon=11.575, alt=20))
    mission.add(Waypoint(lat=48.138, lon=11.576, alt=20))
    mission.upload()
    mission.start()
    mission.wait_done()
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from skymeshx.core.connection import MAVLinkConnection
from skymeshx.control.mission_validation import validate_waypoints, calculate_distance


@dataclass
class Waypoint:
    lat: float
    lon: float
    alt: float = 10.0
    speed: Optional[float] = None  # m/s, None = keep current
    hold: float = 0.0  # seconds to loiter
    cmd: int = 16  # MAV_CMD_NAV_WAYPOINT
    radius: float = 2.0  # acceptance radius m
    # MAVLink command parameters (for special commands like gimbal, camera)
    param1: float = 0.0
    param2: float = 0.0
    param3: float = 0.0
    param4: float = 0.0
    param5: float = 0.0
    param6: float = 0.0
    param7: float = 0.0


class MissionEngine:
    """
    Mission upload and execution engine.
    
    Args:
        connection: MAVLink connection to the autopilot
        handshake_timeout: Seconds to wait for MISSION_REQUEST(0) (default: 0.25)
        item_timeout: Seconds to wait for each MISSION_REQUEST (default: 3.0)
        ack_timeout: Seconds to wait for final MISSION_ACK (default: 5.0)
    
    Thread Safety
    -------------
    Mission building (add/clear) is thread-safe with lock protection.
    upload() spawns a background thread and is safe to call from any thread.
    Progress/completion callbacks are invoked from the upload thread.
    """

    def __init__(
        self,
        connection: MAVLinkConnection,
        handshake_timeout: float = 0.25,
        item_timeout: float = 3.0,
        ack_timeout: float = 5.0
    ):
        self._conn = connection
        self._waypoints: List[Waypoint] = []
        self._current = -1
        self._running = False
        self._done_event = threading.Event()
        self._abort_event = threading.Event()
        self._last_seq = -1
        self._on_waypoint: Optional[Callable] = None
        self._on_done: Optional[Callable] = None
        # Upload-time state (initialised in upload())
        self._req_events: dict = {}
        self._ack_event = threading.Event()
        self._ack_result: int = -1
        # Async upload state
        self._upload_thread: Optional[threading.Thread] = None
        self._upload_progress_callback: Optional[Callable[[int, int], None]] = None
        self._upload_complete_callback: Optional[Callable[[bool], None]] = None
        # Configurable timeouts
        self._handshake_timeout = handshake_timeout
        self._item_timeout = item_timeout
        self._ack_timeout = ack_timeout
        # TS-03 FIX: Lock to protect mission building operations
        self._build_lock = threading.Lock()

        if connection:
            connection.on("message", self._on_message)

    # ── Build mission ─────────────────────────────────────────────────────

    def clear(self):
        """Clear all waypoints. Thread-safe."""
        with self._build_lock:
            self._waypoints.clear()

    def add(self, wp: Waypoint):
        """Add a waypoint to the mission. Thread-safe."""
        with self._build_lock:
            self._waypoints.append(wp)

    def from_list(self, points: List[dict]):
        """Load waypoints from list. Thread-safe."""
        with self._build_lock:
            self._waypoints = [
                Waypoint(lat=p["lat"], lon=p["lon"], alt=p.get("alt", 10.0)) for p in points
            ]

    # ── Pre-flight validation ─────────────────────────────────────────────
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate mission before upload. Thread-safe.
        
        Checks:
        - Minimum waypoint count (at least 1)
        - Valid coordinates (lat: -90 to 90, lon: -180 to 180)
        - Reasonable altitudes (0 to 500m)
        - Waypoint spacing (warn if < 1m apart)
        - Connection status
        
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        # Check connection
        if not self._conn or not self._conn._mav:
            errors.append("No MAVLink connection")
            return False, errors
        
        # Create snapshot of waypoints under lock
        with self._build_lock:
            waypoints_dict = [
                {"lat": wp.lat, "lon": wp.lon, "alt": wp.alt, "cmd": wp.cmd}
                for wp in self._waypoints
            ]
        
        # Use shared validation logic (outside lock)
        is_valid, validation_errors = validate_waypoints(waypoints_dict)
        errors.extend(validation_errors)
        
        return len(errors) == 0, errors

    # ── Upload & control ──────────────────────────────────────────────────

    def upload(self, validate_first: bool = True) -> bool:
        """Upload all queued waypoints to the autopilot.

        .. warning::
            This is **blocking** for ~50ms per waypoint (push-all path) or
            until the autopilot completes the handshake (request-based path).
            Always call from a worker thread, never from the UI / Qt main
            thread.

        Uses a **hybrid protocol**:

        1. Sends ``MISSION_COUNT`` and waits up to
           :attr:`_HANDSHAKE_TIMEOUT` seconds for a ``MISSION_REQUEST(0)``
           from the autopilot.
        2. If the request arrives → full request/response handshake
           (correct MAVLink behaviour).
        3. Otherwise → legacy push-all with 50 ms inter-item pacing
           (ArduPilot-compatible fallback).

        Abort via :meth:`abort` is honoured at every step.
        
        Args:
            validate_first: Run pre-flight validation before upload (default: True)
        
        Returns:
            False if validation fails or upload fails, True on success
        """
        # Pre-flight validation
        if validate_first:
            is_valid, errors = self.validate()
            if not is_valid:
                print(f"[Mission] Pre-flight validation failed:")
                for error in errors:
                    print(f"  - {error}")
                return False
        
        mav = self._conn._mav
        
        # Create snapshot of waypoints under lock for upload
        with self._build_lock:
            if not mav or not self._waypoints:
                return False
            waypoints_snapshot = list(self._waypoints)
        
        # Allow upload() to be called again after a previous abort().
        self._abort_event.clear()

        n = len(waypoints_snapshot) + 1  # +1 for home
        self._req_events = {i: threading.Event() for i in range(n)}
        self._ack_event = threading.Event()
        self._ack_result = -1
        self._conn.on("message", self._on_upload_msg)

        try:
            return self._do_upload(mav, n, waypoints_snapshot)
        finally:
            try:
                self._conn.off("message", self._on_upload_msg)
            except AttributeError:
                pass
            self._req_events = {}
            self._ack_event.clear()

    def upload_async(
        self,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_complete: Optional[Callable[[bool], None]] = None
    ) -> bool:
        """
        Upload waypoints asynchronously in a background thread.
        
        This is the non-blocking version of upload() that should be used
        from UI threads to prevent freezing.
        
        Args:
            on_progress: Callback(current, total) called after each waypoint upload
            on_complete: Callback(success) called when upload finishes
        
        Returns:
            True if upload thread started successfully, False if already uploading
        
        Example:
            def progress(current, total):
                print(f"Uploading {current}/{total}")
            
            def complete(success):
                print(f"Upload {'succeeded' if success else 'failed'}")
            
            mission.upload_async(on_progress=progress, on_complete=complete)
        """
        # Check if already uploading
        if self._upload_thread is not None and self._upload_thread.is_alive():
            return False
        
        self._upload_progress_callback = on_progress
        self._upload_complete_callback = on_complete
        
        # Start upload in background thread
        self._upload_thread = threading.Thread(
            target=self._upload_worker,
            daemon=True,
            name="mission-upload"
        )
        self._upload_thread.start()
        return True
    
    def _upload_worker(self):
        """Worker thread for async upload."""
        try:
            # Call the blocking upload() method
            success = self.upload()
            
            # Notify completion
            if self._upload_complete_callback:
                try:
                    self._upload_complete_callback(success)
                except Exception as e:
                    print(f"[mission] upload complete callback error: {e}")
        except Exception as e:
            print(f"[mission] upload worker error: {e}")
            if self._upload_complete_callback:
                try:
                    self._upload_complete_callback(False)
                except Exception:
                    pass
        finally:
            self._upload_progress_callback = None
            self._upload_complete_callback = None
    
    def is_uploading(self) -> bool:
        """Check if an async upload is in progress."""
        return self._upload_thread is not None and self._upload_thread.is_alive()

    def _do_upload(self, mav, n: int, waypoints_snapshot: List[Waypoint]) -> bool:
        """Send MISSION_COUNT and choose handshake vs. push-all path."""
        # Store snapshot for use in _send_item
        self._upload_waypoints = waypoints_snapshot
        
        try:
            mav.mav.mission_count_send(mav.target_system, mav.target_component, n, 0)
        except Exception as e:
            print(f"[mission] mission_count_send failed: {e}")
            return False

        # Wait for MISSION_REQUEST(0), checking abort every 10 ms.
        deadline = time.time() + self._handshake_timeout
        while time.time() < deadline:
            if self._abort_event.is_set():
                return False
            if self._req_events[0].is_set():
                break
            time.sleep(0.01)
        use_handshake = self._req_events[0].is_set()

        if use_handshake:
            return self._upload_handshake(mav, n)
        else:
            return self._upload_push_all(mav, n)

    def _upload_handshake(self, mav, n: int) -> bool:
        """Request-based handshake: send each item only after MISSION_REQUEST."""
        for seq in range(n):
            # seq 0 was already signalled (it triggered this path).
            if seq > 0:
                if self._abort_event.is_set():
                    return False
                if not self._req_events[seq].wait(timeout=self._item_timeout):
                    print(f"[mission] timeout waiting for MISSION_REQUEST({seq})")
                    return False
            if not self._send_item(mav, seq):
                return False
            # Report progress after each waypoint
            if self._upload_progress_callback:
                try:
                    self._upload_progress_callback(seq + 1, n)
                except Exception as e:
                    print(f"[mission] progress callback error: {e}")
        # Wait for final MISSION_ACK.
        if not self._ack_event.wait(timeout=self._ack_timeout):
            print("[mission] timeout waiting for MISSION_ACK")
            return False
        return self._ack_result == 0  # MAV_MISSION_ACCEPTED

    def _upload_push_all(self, mav, n: int) -> bool:
        """Legacy push-all with 50 ms cancel-aware pacing (ArduPilot fallback)."""
        if self._abort_event.is_set():
            return False
        if not self._send_item(mav, 0):
            return False
        # Report progress for first item
        if self._upload_progress_callback:
            try:
                self._upload_progress_callback(1, n)
            except Exception as e:
                print(f"[mission] progress callback error: {e}")
        
        for seq in range(1, n):
            if self._abort_event.wait(0.05):
                return False
            if not self._send_item(mav, seq):
                return False
            # Report progress after each waypoint
            if self._upload_progress_callback:
                try:
                    self._upload_progress_callback(seq + 1, n)
                except Exception as e:
                    print(f"[mission] progress callback error: {e}")
        return True

    def _send_item(self, mav, seq: int) -> bool:
        """Send a single MISSION_ITEM_INT for *seq*. Uses snapshot from upload."""
        t = self._conn.telemetry
        try:
            if seq == 0:  # home
                mav.mav.mission_item_int_send(
                    mav.target_system,
                    mav.target_component,
                    0,
                    0,
                    16,
                    1,
                    1,
                    0,
                    0,
                    0,
                    0,
                    int(t.home_lat * 1e7) or int(t.lat * 1e7),
                    int(t.home_lon * 1e7) or int(t.lon * 1e7),
                    t.home_alt or t.alt,
                    0,
                )
            else:
                # Use snapshot instead of self._waypoints
                wp = self._upload_waypoints[seq - 1]
                # MAV_FRAME_GLOBAL_RELATIVE_ALT (6): alt is metres above home.
                # This is required for PX4 (frame 3 = GLOBAL absolute MSL is rejected).
                # ArduPilot also accepts frame 6 for relative-alt missions.
                mav.mav.mission_item_int_send(
                    mav.target_system,
                    mav.target_component,
                    seq,
                    6,  # MAV_FRAME_GLOBAL_RELATIVE_ALT
                    wp.cmd,
                    0,
                    1,
                    wp.hold,
                    wp.radius,
                    0,
                    0,
                    int(wp.lat * 1e7),
                    int(wp.lon * 1e7),
                    wp.alt,
                    0,
                )
        except Exception as e:
            print(f"[mission] send item {seq} failed: {e}")
            return False
        return True

    def _on_upload_msg(self, msg) -> None:
        """Listener registered for the duration of upload() only."""
        t = msg.get_type()
        if t in ("MISSION_REQUEST", "MISSION_REQUEST_INT"):
            seq = getattr(msg, "seq", None)
            if seq is not None and seq in self._req_events:
                self._req_events[seq].set()
        elif t == "MISSION_ACK":
            self._ack_result = getattr(msg, "type", -1)
            self._ack_event.set()

    def start(self) -> bool:
        if not self._conn.set_mode("AUTO"):
            return False
        self._running = True
        self._done_event.clear()
        self._current = 0
        self._last_seq = -1
        return True

    def pause(self) -> bool:
        return self._conn.set_mode("LOITER")

    def resume(self) -> bool:
        return self._conn.set_mode("AUTO")

    def abort(self) -> bool:
        self._running = False
        # Interrupt any in-flight upload() loop and unblock wait_done().
        self._abort_event.set()
        self._done_event.set()
        return self._conn.rtl()

    def wait_done(self, timeout: float = 600.0) -> bool:
        return self._done_event.wait(timeout=timeout)

    # ── Callbacks ─────────────────────────────────────────────────────────

    def on_waypoint_reached(self, cb: Callable):
        self._on_waypoint = cb

    def on_mission_done(self, cb: Callable):
        self._on_done = cb

    # ── Internal ──────────────────────────────────────────────────────────

    def _on_message(self, msg):
        t = msg.get_type()
        if t == "MISSION_CURRENT":
            self._current = msg.seq
            if self._on_waypoint:
                self._on_waypoint(msg.seq)
        elif t == "MISSION_ITEM_REACHED":
            self._last_seq = msg.seq
            if self._on_waypoint:
                self._on_waypoint(msg.seq)
            # Last waypoint reached -> mission done
            if self._running and msg.seq >= len(self._waypoints):
                self._mark_done()
        elif t == "MISSION_ACK" and msg.type == 0:
            # Successful upload-ack ignored; only completion-ack matters here.
            pass
        elif t == "HEARTBEAT":
            # Mode left AUTO while a mission is running -> mark done so
            # wait_done() can return instead of hanging forever.
            mode = (self._conn.telemetry.flight_mode or "").upper()
            if self._running and mode not in ("AUTO", "GUIDED") and self._current > 0:
                self._mark_done()

    def _mark_done(self):
        if self._done_event.is_set():
            return
        self._running = False
        self._done_event.set()
        if self._on_done:
            try:
                self._on_done()
            except Exception:
                pass
