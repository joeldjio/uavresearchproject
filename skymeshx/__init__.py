"""
SkyMeshX — ROS2-based SkyMeshX Middleware Platform.

Core API:
    from skymeshx import Drone, Swarm
    from skymeshx.autopilot import get_backend
    from skymeshx.models import GenericUAVModel, CoordinatorUAVModel
    from skymeshx.simulation import SITLInstance, SITLCluster, TelemetryReplay
    from skymeshx.experiment import Scenario, ScenarioRunner, MetricsCollector
    from skymeshx.safety import APFSafetyFilter, Pose3D
    from skymeshx.llm import SwarmCommander

Autopilot backends:
    mavlink   → ArduPilot + PX4 via MAVLink (pymavlink)
    ardupilot → ArduPilot-specific extensions
    px4       → PX4 native via uXRCE-DDS (ROS2)
"""
from skymeshx.sdk.drone import Drone
from skymeshx.sdk.swarm_api import Swarm

# Export common exceptions for convenience
from skymeshx.exceptions import (
    SkyMeshXError,
    ConnectionError,
    HeartbeatTimeoutError,
    InvalidConnectionStringError,
    CommandError,
    CommandRejectedError,
    CommandTimeoutError,
    MissionError,
    MissionUploadError,
    StateTransitionError,
    ConfigurationError,
    InvalidParameterError,
    ROS2Error,
    ROS2NotAvailableError,
    SafetyViolationError,
    GeofenceBreachError,
    CollisionRiskError,
    BatteryLowError,
    DependencyError,
    TimeoutError,
    SimulationError,
    ScriptAbortedError,
    LLMResponseError,
    SessionError,
)

__version__ = "0.2.0"
__all__ = [
    "Drone",
    "Swarm",
    # Exceptions
    "SkyMeshXError",
    "ConnectionError",
    "HeartbeatTimeoutError",
    "InvalidConnectionStringError",
    "CommandError",
    "CommandRejectedError",
    "CommandTimeoutError",
    "MissionError",
    "MissionUploadError",
    "StateTransitionError",
    "ConfigurationError",
    "InvalidParameterError",
    "ROS2Error",
    "ROS2NotAvailableError",
    "SafetyViolationError",
    "GeofenceBreachError",
    "CollisionRiskError",
    "BatteryLowError",
    "DependencyError",
    "TimeoutError",
    "SimulationError",
    "ScriptAbortedError",
    "LLMResponseError",
    "SessionError",
]

# Lazy imports — avoids hard dependencies at import time
def get_backend(autopilot: str = "mavlink"):
    from skymeshx.autopilot import get_backend as _get
    return _get(autopilot)

def get_sitl(**kwargs):
    from skymeshx.simulation import SITLInstance
    return SITLInstance(**kwargs)

def get_coordinator(**kwargs):
    from skymeshx.models import CoordinatorUAVModel
    return CoordinatorUAVModel(**kwargs)

def get_swarm_commander(**kwargs):
    from skymeshx.llm import SwarmCommander
    return SwarmCommander(**kwargs)
