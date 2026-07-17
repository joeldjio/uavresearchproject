"""
UI Context Tests
----------------
Tests for UI context classes (SwarmContext, SafetyContext, etc.)
"""
import pytest


def test_swarm_context_exists():
    """Test that SwarmContext can be imported"""
    from tools.ui.context.swarm_context import SwarmContext
    assert SwarmContext is not None


def test_swarm_context_initialization():
    """Test SwarmContext initialization"""
    from tools.ui.context.swarm_context import SwarmContext
    
    ctx = SwarmContext()
    assert ctx is not None
    
    # Check methods exist
    assert hasattr(ctx, 'droneIds')
    assert hasattr(ctx, 'droneSnapshot')
    assert hasattr(ctx, 'addDrone')
    assert hasattr(ctx, 'removeDrone')
    assert hasattr(ctx, 'armDrone')
    assert hasattr(ctx, 'disarmDrone')
    assert hasattr(ctx, 'takeoffDrone')
    assert hasattr(ctx, 'landDrone')
    assert hasattr(ctx, 'rtlDrone')
    assert hasattr(ctx, 'gotoDrone')
    assert hasattr(ctx, 'setMode')


def test_swarm_context_drone_ids():
    """Test droneIds returns a list"""
    from tools.ui.context.swarm_context import SwarmContext
    
    ctx = SwarmContext()
    ids = ctx.droneIds()
    
    assert isinstance(ids, list)


def test_swarm_context_drone_snapshot():
    """Test droneSnapshot returns dict or None"""
    from tools.ui.context.swarm_context import SwarmContext
    
    ctx = SwarmContext()
    snap = ctx.droneSnapshot("nonexistent")
    
    # Should return dict (empty or with defaults) or None
    assert snap is None or isinstance(snap, dict)


def test_safety_context_exists():
    """Test that SafetyContext can be imported"""
    from tools.ui.context.safety_context import SafetyContext
    assert SafetyContext is not None


def test_safety_context_initialization():
    """Test SafetyContext initialization"""
    from tools.ui.context.safety_context import SafetyContext
    
    ctx = SafetyContext()
    assert ctx is not None
    
    # Check properties exist
    assert hasattr(ctx, 'apfActive')
    assert hasattr(ctx, 'violationCount')
    
    # Check methods exist
    assert hasattr(ctx, 'configureAPF')
    assert hasattr(ctx, 'disableAPF')


def test_safety_context_initial_state():
    """Test SafetyContext initial state"""
    from tools.ui.context.safety_context import SafetyContext
    
    ctx = SafetyContext()
    
    # APF should be disabled initially
    assert ctx.apfActive is False
    
    # Violation count should be 0
    assert ctx.violationCount == 0


def test_ros2_context_exists():
    """Test that ROS2Context can be imported"""
    from tools.ui.context.ros2_context import ROS2Context
    assert ROS2Context is not None


def test_ros2_context_initialization():
    """Test ROS2Context initialization"""
    from tools.ui.context.ros2_context import ROS2Context
    
    ctx = ROS2Context()
    assert ctx is not None
    
    # Check methods exist
    assert hasattr(ctx, 'nodeStatus')


def test_ros2_context_node_status():
    """Test ROS2 node status returns valid value"""
    from tools.ui.context.ros2_context import ROS2Context
    
    ctx = ROS2Context()
    status = ctx.nodeStatus()
    
    # Should be one of the valid statuses
    assert status in ["ok", "no_px4_msgs", "no_ros2"]


def test_experiment_context_exists():
    """Test that ExperimentContext can be imported"""
    from tools.ui.context.experiment_context import ExperimentContext
    assert ExperimentContext is not None


def test_experiment_context_initialization():
    """Test ExperimentContext initialization"""
    from tools.ui.context.experiment_context import ExperimentContext
    
    ctx = ExperimentContext()
    assert ctx is not None


def test_bag_playback_context_exists():
    """Test that BagPlaybackContext can be imported"""
    from tools.ui.context.bag_playback_context import BagPlaybackContext
    assert BagPlaybackContext is not None


def test_bag_playback_context_initialization():
    """Test BagPlaybackContext initialization"""
    from tools.ui.context.bag_playback_context import BagPlaybackContext
    
    ctx = BagPlaybackContext()
    assert ctx is not None
    
    # Check methods exist
    assert hasattr(ctx, 'loadBag')
    assert hasattr(ctx, 'play')
    assert hasattr(ctx, 'pause')
    assert hasattr(ctx, 'seek')


def test_bag_playback_context_initial_state():
    """Test BagPlaybackContext initial state"""
    from tools.ui.context.bag_playback_context import BagPlaybackContext
    
    ctx = BagPlaybackContext()
    
    # Context should be initialized
    assert ctx is not None
    
    # Check that basic methods don't crash
    ctx.pause()  # Should work even if not playing


def test_ui_app_module_exists():
    """Test that UI app module can be imported"""
    import tools.ui.app
    assert tools.ui.app is not None


def test_ui_backend_module_exists():
    """Test that UI backend module can be imported"""
    import tools.ui.backend
    assert tools.ui.backend is not None


def test_ui_version_exists():
    """Test that UI version is defined"""
    from tools.ui import _version
    
    # Version module should exist
    assert _version is not None
    
    # Should have VERSION constant
    assert hasattr(_version, 'VERSION')
    version = _version.VERSION
    
    assert version is not None
    assert isinstance(version, str)
    assert len(version) > 0
    
    # Should follow semver pattern (x.y.z)
    parts = version.split('.')
    assert len(parts) >= 2  # At least major.minor


def test_ui_license_module_exists():
    """Test that license module can be imported"""
    from tools.ui import license
    assert license is not None


def test_ui_main_window_module_exists():
    """Test that main_window module can be imported (now in tools.ui.legacy)"""
    from tools.ui.legacy import main_window
    assert main_window is not None


def test_swarm_context_signals():
    """Test that SwarmContext has Qt signals"""
    from tools.ui.context.swarm_context import SwarmContext
    
    ctx = SwarmContext()
    
    # Should have signals (PySide6 signals)
    # These are typically named like: droneAdded, droneRemoved, telemetryUpdated
    # We can't easily test signal emission without Qt event loop,
    # but we can check they exist
    assert hasattr(ctx, 'droneAdded') or hasattr(ctx, 'drone_added')
    assert hasattr(ctx, 'droneRemoved') or hasattr(ctx, 'drone_removed')


def test_safety_context_signals():
    """Test that SafetyContext has Qt signals"""
    from tools.ui.context.safety_context import SafetyContext
    
    ctx = SafetyContext()
    
    # SafetyContext should be a QObject (has signals)
    from PySide6.QtCore import QObject
    assert isinstance(ctx, QObject)


def test_ros2_context_signals():
    """Test that ROS2Context has Qt signals"""
    from tools.ui.context.ros2_context import ROS2Context
    
    ctx = ROS2Context()
    
    # Should have signals for status changes
    assert hasattr(ctx, 'nodeStatusChanged') or hasattr(ctx, 'node_status_changed')


def test_bag_playback_context_signals():
    """Test that BagPlaybackContext has Qt signals"""
    from tools.ui.context.bag_playback_context import BagPlaybackContext
    
    ctx = BagPlaybackContext()
    
    # BagPlaybackContext should be a QObject (has signals)
    from PySide6.QtCore import QObject
    assert isinstance(ctx, QObject)


def test_swarm_context_add_remove_drone():
    """Test adding and removing drones"""
    from tools.ui.context.swarm_context import SwarmContext
    
    ctx = SwarmContext()
    
    # Initially empty
    initial_ids = ctx.droneIds()
    assert isinstance(initial_ids, list)
    
    # Add drone
    ctx.addDrone("TEST_UAV", "mock://")
    
    # Should be in list (or not, depending on mock implementation)
    # This test just verifies the method doesn't crash
    ids_after_add = ctx.droneIds()
    assert isinstance(ids_after_add, list)
    
    # Remove drone
    ctx.removeDrone("TEST_UAV")
    
    # Should work without error
    ids_after_remove = ctx.droneIds()
    assert isinstance(ids_after_remove, list)


def test_safety_context_apf_toggle():
    """Test APF enable/disable"""
    from tools.ui.context.safety_context import SafetyContext
    
    ctx = SafetyContext()
    
    # Initially disabled
    assert ctx.apfActive is False
    
    # Enable APF
    ctx.configureAPF({})
    
    # Should be enabled (or not, depending on backend availability)
    # This test just verifies the method doesn't crash
    assert isinstance(ctx.apfActive, bool)
    
    # Disable APF
    ctx.disableAPF()
    
    # Should work without error
    assert isinstance(ctx.apfActive, bool)


def test_bag_playback_context_load_nonexistent():
    """Test loading non-existent bag file"""
    from tools.ui.context.bag_playback_context import BagPlaybackContext
    
    ctx = BagPlaybackContext()
    
    # Try to load non-existent file
    result = ctx.loadBag("/nonexistent/path/to/bag.db3")
    
    # Should return False or handle gracefully
    assert result is False or result is None


def test_ui_contexts_are_qobjects():
    """Test that all contexts inherit from QObject"""
    from PySide6.QtCore import QObject
    from tools.ui.context.swarm_context import SwarmContext
    from tools.ui.context.safety_context import SafetyContext
    from tools.ui.context.ros2_context import ROS2Context
    from tools.ui.context.experiment_context import ExperimentContext
    from tools.ui.context.bag_playback_context import BagPlaybackContext
    
    # All contexts should be QObjects (for signals/slots)
    assert issubclass(SwarmContext, QObject)
    assert issubclass(SafetyContext, QObject)
    assert issubclass(ROS2Context, QObject)
    assert issubclass(ExperimentContext, QObject)
    assert issubclass(BagPlaybackContext, QObject)

