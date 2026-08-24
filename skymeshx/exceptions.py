"""
Custom exception types for SkyMeshX platform.

Provides explicit exception hierarchy for better error handling and recovery.
All exceptions inherit from SkyMeshXError base class.

Exception Hierarchy
-------------------
SkyMeshXError (base)
├── ConnectionError
│   ├── HeartbeatTimeoutError
│   └── InvalidConnectionStringError
├── CommandError
│   ├── CommandRejectedError
│   └── CommandTimeoutError
├── MissionError
│   ├── MissionUploadError
│   ├── MissionAbortedError
│   └── InvalidWaypointError
├── StateTransitionError
├── ConfigurationError
│   └── InvalidParameterError
├── ROS2Error
│   ├── ROS2NotAvailableError
│   ├── ROS2InitError
│   └── TopicTimeoutError
├── SafetyViolationError
│   ├── GeofenceBreachError
│   ├── CollisionRiskError
│   └── BatteryLowError
├── DependencyError
├── TimeoutError
├── DataError
│   ├── LogFileError
│   └── InvalidDataFormatError
├── SimulationError
├── ScriptAbortedError
├── LLMResponseError
└── SessionError

Usage:
    from skymeshx.exceptions import ConnectionError, TimeoutError
    
    try:
        drone.connect()
    except ConnectionError as e:
        logger.error(f"Connection failed: {e}")
        # Retry logic here
    except TimeoutError as e:
        logger.warning(f"Operation timed out: {e}")
        # Timeout handling here
"""

# Base exception class
class SkyMeshXError(Exception):
    """Base exception for all SkyMeshX errors."""
    pass


# Connection-related errors
class ConnectionError(SkyMeshXError):
    """Raised when connection to drone fails or is lost."""
    pass


class HeartbeatTimeoutError(ConnectionError):
    """Raised when no heartbeat received within timeout period."""
    pass


class InvalidConnectionStringError(ConnectionError):
    """Raised when connection string format is invalid."""
    pass


# Command execution errors
class CommandError(SkyMeshXError):
    """Base class for command execution errors."""
    pass


class CommandRejectedError(CommandError):
    """Raised when autopilot rejects a command (MAV_RESULT != ACCEPTED)."""
    def __init__(self, command: str, result: int, message: str = ""):
        self.command = command
        self.result = result
        super().__init__(f"Command {command} rejected (result={result}): {message}")


class CommandTimeoutError(CommandError):
    """Raised when command acknowledgment not received within timeout."""
    def __init__(self, command: str, timeout: float):
        self.command = command
        self.timeout = timeout
        super().__init__(f"Command {command} timed out after {timeout}s")


# Mission-related errors
class MissionError(SkyMeshXError):
    """Base class for mission-related errors."""
    pass


class MissionUploadError(MissionError):
    """Raised when mission upload fails."""
    pass


class MissionAbortedError(MissionError):
    """Raised when mission upload is aborted by user."""
    pass


class InvalidWaypointError(MissionError):
    """Raised when waypoint data is invalid."""
    pass


# State machine errors
class StateTransitionError(SkyMeshXError):
    """Raised when FSM state transition is invalid."""
    def __init__(self, from_state: str, to_state: str, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition {from_state} → {to_state}: {reason}"
        )


# Configuration errors
class ConfigurationError(SkyMeshXError):
    """Raised when configuration is invalid."""
    pass


class InvalidParameterError(ConfigurationError):
    """Raised when parameter value is out of valid range."""
    def __init__(self, param: str, value, valid_range: str = ""):
        self.param = param
        self.value = value
        super().__init__(
            f"Invalid parameter {param}={value}. {valid_range}"
        )


# ROS2-related errors
class ROS2Error(SkyMeshXError):
    """Base class for ROS2-related errors."""
    pass


class ROS2NotAvailableError(ROS2Error):
    """Raised when ROS2 is not installed or not available."""
    pass


class ROS2InitError(ROS2Error):
    """Raised when rclpy.init() fails."""
    pass


class TopicTimeoutError(ROS2Error):
    """Raised when no messages received on topic within timeout."""
    def __init__(self, topic: str, timeout: float):
        self.topic = topic
        self.timeout = timeout
        super().__init__(f"No messages on {topic} for {timeout}s")


# Safety-related errors
class SafetyViolationError(SkyMeshXError):
    """Raised when safety constraint is violated."""
    pass


class GeofenceBreachError(SafetyViolationError):
    """Raised when drone breaches geofence boundary."""
    def __init__(self, drone_id: str, position: tuple, limit: str):
        self.drone_id = drone_id
        self.position = position
        self.limit = limit
        super().__init__(
            f"Drone {drone_id} breached geofence at {position}: {limit}"
        )


class CollisionRiskError(SafetyViolationError):
    """Raised when collision risk detected between drones."""
    def __init__(self, drone1: str, drone2: str, distance: float, min_distance: float):
        self.drone1 = drone1
        self.drone2 = drone2
        self.distance = distance
        self.min_distance = min_distance
        super().__init__(
            f"Collision risk: {drone1} ↔ {drone2} distance={distance:.1f}m "
            f"(min={min_distance:.1f}m)"
        )


class BatteryLowError(SafetyViolationError):
    """Raised when battery level is critically low."""
    def __init__(self, drone_id: str, battery_pct: float, threshold: float):
        self.drone_id = drone_id
        self.battery_pct = battery_pct
        self.threshold = threshold
        super().__init__(
            f"Drone {drone_id} battery critically low: {battery_pct:.1f}% "
            f"(threshold={threshold:.1f}%)"
        )


# Dependency errors
class DependencyError(SkyMeshXError):
    """Raised when required dependency is missing."""
    def __init__(self, package: str, install_cmd: str = ""):
        self.package = package
        self.install_cmd = install_cmd
        msg = f"Required package '{package}' not found."
        if install_cmd:
            msg += f" Install with: {install_cmd}"
        super().__init__(msg)


# Timeout errors (generic)
class TimeoutError(SkyMeshXError):
    """Raised when operation times out."""
    def __init__(self, operation: str, timeout: float):
        self.operation = operation
        self.timeout = timeout
        super().__init__(f"{operation} timed out after {timeout}s")


# File/Data errors
class DataError(SkyMeshXError):
    """Base class for data-related errors."""
    pass


class LogFileError(DataError):
    """Raised when log file cannot be read or written."""
    pass


class InvalidDataFormatError(DataError):
    """Raised when data format is invalid or corrupted."""
    pass


# Simulation errors
class SimulationError(SkyMeshXError):
    """Raised when SITL/Gazebo simulation fails to start or crashes."""
    pass


# Script execution errors
class ScriptAbortedError(SkyMeshXError):
    """Raised when a user script is stopped before completion."""
    pass


# LLM / AI errors
class LLMResponseError(SkyMeshXError):
    """Raised when LLM response cannot be parsed or is invalid."""
    def __init__(self, message: str, raw_response: str = ""):
        self.raw_response = raw_response
        super().__init__(message)


# Session / lifecycle errors
class SessionError(SkyMeshXError):
    """Raised when a trace/recording session is in an invalid state."""
    pass
