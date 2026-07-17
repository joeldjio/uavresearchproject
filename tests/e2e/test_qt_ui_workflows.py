"""
E2E Tests - Qt UI Workflows
----------------------------
End-to-end tests for PySide6/QML UI workflows.
Uses pytest-qt for Qt application testing.
"""
import pytest

# Guard: skip collection entirely if Qt libs are unavailable (headless CI
# without libegl1 / libGL, or PySide6 not installed).
PySide6 = pytest.importorskip("PySide6", reason="PySide6 required for E2E Qt tests")
from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402


@pytest.mark.e2e
@pytest.mark.ui
def test_ui_startup_and_window_creation(qapp):
    """E2E: UI application starts and main window is created"""
    from tools.ui.legacy.main_window import MainWindow
    
    # Create main window
    window = MainWindow()
    window.show()
    
    # Verify window is visible
    assert window.isVisible()
    assert window.windowTitle() == "skymeshx gcs"
    
    # Verify minimum size
    assert window.width() >= 1200
    assert window.height() >= 800
    
    # Close window
    window.close()


@pytest.mark.e2e
@pytest.mark.ui
def test_navigation_between_panels(qapp, wired_locator):
    """E2E: Navigate between different panels"""
    from tools.ui.legacy.main_window import MainWindow
    
    window = MainWindow()
    window.show()
    
    # Get QML engine
    engine = window.engine
    root = engine.rootObjects()[0]
    
    # Verify initial panel (should be Map or Dashboard)
    current_panel = root.property("currentPanel")
    assert current_panel is not None
    
    # Simulate panel navigation
    panels = ["map", "dashboard", "swarm", "safety", "ros2", "experiment", "log"]
    for panel in panels:
        root.setProperty("currentPanel", panel)
        QTest.qWait(100)  # Wait for transition
        assert root.property("currentPanel") == panel
    
    window.close()


@pytest.mark.e2e
@pytest.mark.ui
def test_drone_connection_workflow(qapp, wired_locator, fake_conn):
    """E2E: Connect drone via UI"""
    from tools.ui.legacy.main_window import MainWindow
    
    # Setup fake connection
    swarm_ctx = wired_locator.get("swarm")
    swarm_ctx.add_drone("UAV_1", fake_conn)
    
    window = MainWindow()
    window.show()
    
    # Simulate connection
    fake_conn.connected = True
    swarm_ctx.on_drone_connected("UAV_1")
    
    # Verify connection state
    assert swarm_ctx.is_connected("UAV_1")
    assert len(swarm_ctx.get_drone_ids()) == 1
    
    window.close()


@pytest.mark.e2e
@pytest.mark.ui
def test_arm_disarm_workflow(qapp, wired_locator, fake_conn):
    """E2E: ARM and DISARM drone via UI"""
    from tools.ui.legacy.main_window import MainWindow
    
    swarm_ctx = wired_locator.get("swarm")
    swarm_ctx.add_drone("UAV_1", fake_conn)
    fake_conn.connected = True
    
    window = MainWindow()
    window.show()
    
    # ARM drone
    fake_conn.arm()
    QTest.qWait(100)
    
    # Verify armed state
    telemetry = swarm_ctx.get_telemetry("UAV_1")
    assert telemetry["armed"] is True
    
    # DISARM drone
    fake_conn.disarm()
    QTest.qWait(100)
    
    # Verify disarmed state
    telemetry = swarm_ctx.get_telemetry("UAV_1")
    assert telemetry["armed"] is False
    
    window.close()


@pytest.mark.e2e
@pytest.mark.ui
def test_apf_toggle_workflow(qapp, wired_locator):
    """E2E: Toggle APF safety filter via UI"""
    from tools.ui.legacy.main_window import MainWindow
    
    safety_ctx = wired_locator.get("safety")
    
    window = MainWindow()
    window.show()
    
    # Initially disabled
    assert safety_ctx.apf_enabled is False
    
    # Enable APF
    safety_ctx.toggle_apf()
    QTest.qWait(100)
    assert safety_ctx.apf_enabled is True
    
    # Disable APF
    safety_ctx.toggle_apf()
    QTest.qWait(100)
    assert safety_ctx.apf_enabled is False
    
    window.close()


@pytest.mark.e2e
@pytest.mark.ui
def test_formation_selection_workflow(qapp, wired_locator, fake_conn):
    """E2E: Select formation via UI"""
    from tools.ui.legacy.main_window import MainWindow
    
    swarm_ctx = wired_locator.get("swarm")
    swarm_ctx.add_drone("UAV_1", fake_conn)
    swarm_ctx.add_drone("UAV_2", fake_conn)
    
    window = MainWindow()
    window.show()
    
    # Set formation
    formations = ["line", "v", "circle", "grid"]
    for formation in formations:
        swarm_ctx.set_formation(formation, spacing=5.0)
        QTest.qWait(100)
        assert swarm_ctx.current_formation == formation
    
    window.close()


@pytest.mark.e2e
@pytest.mark.ui
def test_ros2_bag_recording_workflow(qapp, wired_locator):
    """E2E: Start/stop ROS2 bag recording via UI"""
    from tools.ui.legacy.main_window import MainWindow
    
    ros2_ctx = wired_locator.get("ros2")
    
    window = MainWindow()
    window.show()
    
    # Initially not recording
    assert ros2_ctx.is_recording is False
    
    # Start recording
    ros2_ctx.start_recording("test_bag")
    QTest.qWait(100)
    assert ros2_ctx.is_recording is True
    
    # Stop recording
    ros2_ctx.stop_recording()
    QTest.qWait(100)
    assert ros2_ctx.is_recording is False
    
    window.close()


@pytest.mark.e2e
@pytest.mark.ui
def test_experiment_execution_workflow(qapp, wired_locator):
    """E2E: Execute experiment script via UI"""
    from tools.ui.legacy.main_window import MainWindow
    
    exp_ctx = wired_locator.get("experiment")
    
    window = MainWindow()
    window.show()
    
    # Set script
    script = "print('Hello from E2E test')"
    exp_ctx.set_script(script)
    
    # Execute script
    exp_ctx.execute_script()
    QTest.qWait(500)
    
    # Verify execution (check logs or status)
    assert exp_ctx.last_execution_status == "success"
    
    window.close()


@pytest.mark.e2e
@pytest.mark.ui
def test_telemetry_update_workflow(qapp, wired_locator, fake_conn, snap_factory):
    """E2E: Telemetry updates propagate through UI"""
    from tools.ui.legacy.main_window import MainWindow
    
    swarm_ctx = wired_locator.get("swarm")
    swarm_ctx.add_drone("UAV_1", fake_conn)
    fake_conn.connected = True
    
    window = MainWindow()
    window.show()
    
    # Send telemetry updates
    for alt in [5.0, 10.0, 15.0, 20.0]:
        snap = snap_factory(alt_rel=alt, armed=True)
        fake_conn.emit_message("GLOBAL_POSITION_INT", snap)
        QTest.qWait(50)
        
        # Verify telemetry updated
        telemetry = swarm_ctx.get_telemetry("UAV_1")
        assert abs(telemetry["alt_rel"] - alt) < 0.1
    
    window.close()


@pytest.mark.e2e
@pytest.mark.ui
@pytest.mark.slow
def test_performance_ui_responsiveness(qapp, wired_locator, fake_conn, snap_factory):
    """E2E: UI remains responsive under high telemetry load"""
    from tools.ui.legacy.main_window import MainWindow
    import time
    
    swarm_ctx = wired_locator.get("swarm")
    
    # Add multiple drones
    for i in range(5):
        swarm_ctx.add_drone(f"UAV_{i}", fake_conn)
    
    window = MainWindow()
    window.show()
    
    start_time = time.time()
    
    # Send 100 telemetry updates per drone
    for _ in range(100):
        for i in range(5):
            snap = snap_factory(alt_rel=10.0 + i)
            fake_conn.emit_message("GLOBAL_POSITION_INT", snap)
        QTest.qWait(10)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Should complete in reasonable time (<5s for 500 updates)
    assert duration < 5.0, f"UI too slow: {duration:.2f}s for 500 updates"
    
    # UI should still be responsive
    assert window.isVisible()
    
    window.close()


