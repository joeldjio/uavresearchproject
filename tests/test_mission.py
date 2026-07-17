"""Tests for :mod:`skymeshx.control.mission`.

These regression-test the lifecycle fixes:
* ``_done_event`` is now set on last-waypoint, mode-change, and abort.
* ``upload()`` honours ``abort()`` mid-flight via the cancel-aware Event.wait.
"""
from __future__ import annotations

import threading
import time

import pytest

from skymeshx.control.mission import MissionEngine, Waypoint


@pytest.fixture
def engine(fake_conn):
    eng = MissionEngine(fake_conn)
    eng.from_list([
        {"lat": 47.1, "lon": 8.1, "alt": 10.0},
        {"lat": 47.2, "lon": 8.2, "alt": 10.0},
        {"lat": 47.3, "lon": 8.3, "alt": 10.0},
    ])
    return eng


class TestLifecycle:
    def test_start_sets_mode_and_clears_done_event(self, engine, fake_conn):
        assert engine.start() is True
        assert "AUTO" in fake_conn.mode_set
        assert not engine._done_event.is_set()

    def test_wait_done_blocks_until_event_set(self, engine):
        engine.start()
        # wait_done with tiny timeout should hit the timeout (return False).
        assert engine.wait_done(timeout=0.05) is False
        engine._mark_done()
        assert engine.wait_done(timeout=0.05) is True


class TestCompletionDetection:
    """Regression: previously _done_event was never set; wait_done() hung."""

    def test_last_waypoint_reached_marks_done(self, engine, make_msg):
        engine.start()
        # Simulate seq advancing.
        for seq in range(1, len(engine._waypoints) + 1):
            engine._conn.emit_message(make_msg("MISSION_ITEM_REACHED", seq=seq))
        assert engine._done_event.is_set()
        assert engine.wait_done(timeout=0.1) is True

    def test_intermediate_waypoint_does_not_mark_done(self, engine, make_msg):
        engine.start()
        engine._conn.emit_message(make_msg("MISSION_ITEM_REACHED", seq=1))
        assert not engine._done_event.is_set()

    def test_mode_change_away_from_auto_marks_done(self, engine, fake_conn, make_msg):
        engine.start()
        # Advance to a non-zero waypoint so the HEARTBEAT branch fires.
        engine._conn.emit_message(make_msg("MISSION_CURRENT", seq=1))
        # Operator switches to LOITER -> mission should finalize.
        fake_conn.telemetry.flight_mode = "LOITER"
        engine._conn.emit_message(make_msg("HEARTBEAT"))
        assert engine._done_event.is_set()

    def test_heartbeat_in_auto_does_not_mark_done(self, engine, fake_conn, make_msg):
        engine.start()
        engine._conn.emit_message(make_msg("MISSION_CURRENT", seq=1))
        fake_conn.telemetry.flight_mode = "AUTO"
        engine._conn.emit_message(make_msg("HEARTBEAT"))
        assert not engine._done_event.is_set()

    def test_on_done_callback_fires_exactly_once(self, engine, make_msg):
        calls = []
        engine.on_mission_done(lambda: calls.append(True))
        engine.start()
        engine._conn.emit_message(make_msg("MISSION_ITEM_REACHED", seq=99))
        engine._conn.emit_message(make_msg("MISSION_ITEM_REACHED", seq=99))
        assert calls == [True]   # idempotent

    def test_on_done_exception_is_swallowed(self, engine, make_msg):
        engine.on_mission_done(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        engine.start()
        # Should not raise even though the callback explodes.
        engine._conn.emit_message(make_msg("MISSION_ITEM_REACHED", seq=99))
        assert engine._done_event.is_set()


class TestAbort:
    def test_abort_sets_done_event_and_calls_rtl(self, engine, fake_conn):
        engine.start()
        assert engine.abort() is True
        assert engine._done_event.is_set()
        assert fake_conn.rtl_calls == 1

    def test_abort_sets_abort_event_for_upload(self, engine):
        engine.start()
        assert not engine._abort_event.is_set()
        engine.abort()
        assert engine._abort_event.is_set()


class TestUpload:
    def test_upload_sends_count_and_all_items(self, engine, fake_conn):
        ok = engine.upload()
        assert ok is True
        sends = fake_conn._mav.mav
        # 1 count + 1 home + 3 waypoints = 1 + 4 = 5 calls total
        assert sends.mission_count_send.call_count == 1
        assert sends.mission_item_int_send.call_count == 1 + 3

    def test_upload_returns_false_on_empty(self, fake_conn):
        eng = MissionEngine(fake_conn)
        eng.from_list([])
        assert eng.upload() is False

    def test_upload_is_interrupted_by_abort_mid_flight(self, fake_conn):
        """Regression: abort() must break out of the pacing loop."""
        eng = MissionEngine(fake_conn)
        # 200 waypoints * 0.05s = 10s if not abortable; abort cuts to ~0.
        eng.from_list([{"lat": 47.0, "lon": 8.0, "alt": 10.0}] * 200)

        def aborter():
            time.sleep(0.05)
            eng.abort()

        t = threading.Thread(target=aborter, daemon=True)
        t0 = time.monotonic()
        t.start()
        ok = eng.upload()
        elapsed = time.monotonic() - t0
        t.join(timeout=1.0)

        assert ok is False                # abort interrupted
        assert elapsed < 1.5              # nowhere near the 10s worst case

    def test_upload_continues_after_failed_send(self, fake_conn):
        """If a single item raises, upload returns False without partial state."""
        eng = MissionEngine(fake_conn)
        eng.from_list([
            {"lat": 47.0000, "lon": 8.0000, "alt": 10.0},
            {"lat": 47.0010, "lon": 8.0010, "alt": 10.0},
            {"lat": 47.0020, "lon": 8.0020, "alt": 10.0},
        ])
        # Make the second item_int_send raise.
        original = fake_conn._mav.mav.mission_item_int_send
        call_count = {"n": 0}

        def flaky(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 2:        # second call = first waypoint
                raise RuntimeError("simulated send failure")
            return original(*a, **kw)

        fake_conn._mav.mav.mission_item_int_send = flaky
        assert eng.upload() is False
        # We attempted at least 2 calls (home + 1 wp that failed).
        assert call_count["n"] >= 2


class TestRTLAfterCompletion:
    def test_running_flag_reset_after_done(self, engine, make_msg):
        engine.start()
        assert engine._running is True
        engine._conn.emit_message(make_msg("MISSION_ITEM_REACHED", seq=99))
        assert engine._running is False
