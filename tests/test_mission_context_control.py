"""Hardware-free tests for MissionContext explicit mission controls."""

from __future__ import annotations

import threading
from types import SimpleNamespace

from tools.ui.context.mission_context import MissionContext


class FakeDrone:
    def __init__(self, *, armed=False, altitude=0.0, autopilot="ardupilot"):
        self.armed = armed
        self.altitude = altitude
        self.calls = []
        # _conn.telemetry.autopilot is read by the start/auto-start logic
        self._conn = SimpleNamespace(
            telemetry=SimpleNamespace(autopilot=autopilot)
        )

    def arm(self, timeout=0.0):
        self.calls.append(("arm", timeout))
        self.armed = True
        return True

    def takeoff(self, altitude, timeout=0.0):
        self.calls.append(("takeoff", altitude, timeout))
        self.altitude = altitude
        return True

    def set_mode(self, mode, timeout=0.0):
        self.calls.append(("set_mode", mode, timeout))
        return True


class FakeBackend:
    is_connected = True

    def __init__(self, drone):
        self._drone = drone
        self.rtl_calls = 0

    def rtl(self):
        self.rtl_calls += 1
        return True


class FakeBackendRegistry:
    def __init__(self, backends):
        self._backends = dict(backends)

    def all_backends(self):
        return dict(self._backends)


class FakeSwarmContext:
    def __init__(self, backends):
        self.backend = FakeBackendRegistry(backends)
        self._state_lock = threading.Lock()
        self._mission_active = {}


def test_start_mission_worker_guided_arm_takeoff_auto_and_marks_active(monkeypatch, qapp):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    drone = FakeDrone(armed=False, altitude=0.0)
    ctx = MissionContext()
    ctx.set_swarm_context(FakeSwarmContext({"D1": FakeBackend(drone)}))
    ctx._mark_mission_uploaded("D1", 0, 3)

    ctx._mission_control_worker("start")

    # Sequence must be: GUIDED → arm → takeoff → AUTO
    assert drone.calls == [
        ("set_mode", "GUIDED", 5.0),
        ("arm", 10.0),
        ("takeoff", ctx._coverage_altitude, 30.0),
        ("set_mode", "AUTO", 5.0),
    ]
    assert "D1" in ctx._swarm_context._mission_active
    assert ctx._swarm_context._mission_active["D1"].is_set() is False


def test_start_mission_worker_uses_seeding_takeoff_altitude(monkeypatch, qapp):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    drone = FakeDrone(armed=True, altitude=0.0)
    ctx = MissionContext()
    ctx._mission_mode = 1
    ctx._seed_altitude = 7.5
    ctx.set_swarm_context(FakeSwarmContext({"D1": FakeBackend(drone)}))
    ctx._mark_mission_uploaded("D1", 1, 3)

    ctx._mission_control_worker("start")

    assert ("takeoff", 7.5, 30.0) in drone.calls
    assert drone.calls[-1] == ("set_mode", "AUTO", 5.0)


def test_start_mission_worker_uses_solar_takeoff_altitude(monkeypatch, qapp):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    drone = FakeDrone(armed=True, altitude=0.0)
    ctx = MissionContext()
    ctx._mission_mode = 2
    ctx._solar_altitude = 18.0
    ctx.set_swarm_context(FakeSwarmContext({"D1": FakeBackend(drone)}))
    ctx._mark_mission_uploaded("D1", 2, 3)

    ctx._mission_control_worker("start")

    assert ("takeoff", 18.0, 30.0) in drone.calls
    assert drone.calls[-1] == ("set_mode", "AUTO", 5.0)


def test_start_mission_worker_blocks_without_uploaded_mission(qapp):
    drone = FakeDrone(armed=True, altitude=10.0)
    ctx = MissionContext()
    ctx.set_swarm_context(FakeSwarmContext({"D1": FakeBackend(drone)}))

    ctx._mission_control_worker("start")

    assert drone.calls == []
    assert "D1" not in ctx._swarm_context._mission_active


def test_pause_mission_worker_sets_loiter(qapp):
    drone = FakeDrone(armed=True, altitude=10.0)
    ctx = MissionContext()
    ctx.set_swarm_context(FakeSwarmContext({"D1": FakeBackend(drone)}))

    ctx._mission_control_worker("pause")

    assert drone.calls == [("set_mode", "LOITER", 5.0)]


def test_abort_mission_worker_sends_rtl_and_clears_active(qapp):
    drone = FakeDrone(armed=True, altitude=10.0)
    backend = FakeBackend(drone)
    ctx = MissionContext()
    ctx.set_swarm_context(FakeSwarmContext({"D1": backend}))
    ctx._swarm_context._mission_active["D1"] = threading.Event()
    ctx._swarm_context._mission_active["D1"].clear()

    ctx._mission_control_worker("abort")

    assert backend.rtl_calls == 1
    assert "D1" not in ctx._swarm_context._mission_active


def test_boundary_timeout_keeps_drawn_points(qapp):
    ctx = MissionContext()
    ctx.startDrawingBoundary()
    ctx.addBoundaryPoint(48.137, 11.575)
    ctx.addBoundaryPoint(48.1375, 11.575)
    ctx.addBoundaryPoint(48.1375, 11.5755)

    ctx._on_drawing_timeout()

    assert ctx.drawingMode is False
    assert ctx.fieldBoundaryPoints == 3
    assert ctx.getBoundaryPoints() == [
        {"lat": 48.137, "lon": 11.575},
        {"lat": 48.1375, "lon": 11.575},
        {"lat": 48.1375, "lon": 11.5755},
    ]
