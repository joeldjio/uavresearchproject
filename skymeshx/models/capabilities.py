"""Hardware capability model and mission-mode requirement checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class DroneCapabilities:
    """Hardware capabilities known or declared for one drone."""

    has_camera: bool = False
    has_thermal_camera: bool = False
    has_gimbal: bool = False
    has_dispenser: bool = False
    has_gps: bool = True
    has_mission_upload: bool = True
    has_live_stream: bool = False
    has_recording: bool = False
    camera_resolution: Optional[Tuple[int, int]] = None
    camera_fov: Optional[Tuple[float, float]] = None
    gimbal_axes: List[str] = field(default_factory=list)
    dispenser_type: Optional[str] = None
    manual_overrides: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hasCamera": self.has_camera,
            "hasThermalCamera": self.has_thermal_camera,
            "hasGimbal": self.has_gimbal,
            "hasDispenser": self.has_dispenser,
            "hasGps": self.has_gps,
            "hasMissionUpload": self.has_mission_upload,
            "hasLiveStream": self.has_live_stream,
            "hasRecording": self.has_recording,
            "cameraResolution": _format_resolution(self.camera_resolution),
            "cameraFov": list(self.camera_fov) if self.camera_fov else None,
            "gimbalAxes": list(self.gimbal_axes),
            "dispenserType": self.dispenser_type,
        }


MODE_REQUIREMENTS = {
    "solar": {
        "required": {
            "has_camera": "Camera required for solar inspection",
            "has_gimbal": "Gimbal required for panel-facing inspection",
            "has_mission_upload": "Mission upload support required",
            "has_gps": "GPS required for geotagged inspection",
        },
        "recommended": {
            "has_thermal_camera": "Thermal camera not detected - thermal inspection will be limited",
            "has_recording": "Recording not detected - only snapshots may be available",
        },
    },
    "solar_inspection": "solar",
    "seeding": {
        "required": {
            "has_dispenser": "Seed dispenser required for seeding mode",
            "has_mission_upload": "Mission upload support required",
            "has_gps": "GPS required for field seeding",
        },
        "recommended": {
            "has_camera": "Camera not detected - visual documentation will be limited",
        },
    },
    "mapping": {
        "required": {
            "has_camera": "Camera required for mapping mode",
            "has_mission_upload": "Mission upload support required",
            "has_gps": "GPS required for mapping",
        },
        "recommended": {
            "has_gimbal": "Gimbal not detected - camera footprint control will be limited",
        },
    },
}


def check_mode_requirements(mode: str, capabilities: DroneCapabilities) -> Dict[str, Any]:
    """
    Check required and recommended hardware for a mission mode.

    Returns a QML-friendly dict:
    {"satisfied": bool, "missing": list[str], "warnings": list[str]}
    """
    requirements = _resolve_mode(mode)
    missing = []
    for attr, message in requirements["required"].items():
        try:
            if not bool(getattr(capabilities, attr)):
                missing.append(message)
        except AttributeError:
            missing.append(message)
    warnings = []
    for attr, message in requirements["recommended"].items():
        try:
            if not bool(getattr(capabilities, attr)):
                warnings.append(message)
        except AttributeError:
            warnings.append(message)
    return {
        "satisfied": not missing,
        "missing": missing,
        "warnings": warnings,
        "mode": _canonical_mode(mode),
    }


def detect_capabilities(source: Any = None, overrides: Optional[Dict[str, Any]] = None) -> DroneCapabilities:
    """
    Build capabilities from a backend/drone/status object plus manual overrides.

    The detector is intentionally conservative and duck-typed so tests and UI
    mock objects can use dicts or lightweight fakes without importing MAVLink.
    """
    data = _status_dict(source)
    drone_type = str(
        data.get("droneType") or data.get("drone_type") or data.get("type") or ""
    ).lower()
    is_observation = drone_type == "observation"

    caps = DroneCapabilities(
        has_camera=bool(data.get("hasCamera", data.get("camera_available", is_observation))),
        has_thermal_camera=bool(data.get("hasThermalCamera", data.get("thermal_camera_available", False))),
        has_gimbal=bool(data.get("hasGimbal", data.get("gimbal_available", is_observation))),
        has_dispenser=bool(data.get("hasDispenser", data.get("dispenser_available", False))),
        has_gps=bool(data.get("hasGps", data.get("gps_available", True))),
        has_mission_upload=bool(data.get("hasMissionUpload", data.get("mission_upload_available", True))),
        has_live_stream=bool(data.get("hasLiveStream", data.get("live_stream_available", is_observation))),
        has_recording=bool(data.get("hasRecording", data.get("recording_available", is_observation))),
        camera_resolution=_parse_resolution(data.get("cameraResolution") or data.get("max_resolution")),
        camera_fov=_parse_fov(data.get("cameraFov") or data.get("camera_fov")),
        gimbal_axes=list(data.get("gimbalAxes") or data.get("gimbal_axes") or (["pitch", "yaw"] if is_observation else [])),
        dispenser_type=data.get("dispenserType") or data.get("dispenser_type"),
    )
    if overrides:
        apply_manual_overrides(caps, overrides)
    return caps


def apply_manual_overrides(capabilities: DroneCapabilities, overrides: Dict[str, Any]) -> DroneCapabilities:
    """Apply manual capability overrides in-place and return capabilities."""
    for key, value in overrides.items():
        # Only convert keys that actually contain upper-case camelCase letters.
        # Already-snake_case keys (e.g. "has_dispenser") must not be passed
        # through _camel_to_snake, which would double the underscores.
        if any(c.isupper() for c in key):
            attr = _camel_to_snake(key)
        else:
            attr = key
        if hasattr(capabilities, attr):
            setattr(capabilities, attr, value)
            capabilities.manual_overrides[attr] = value
    return capabilities


def _resolve_mode(mode: str) -> Dict[str, Dict[str, str]]:
    key = _canonical_mode(mode)
    requirements = MODE_REQUIREMENTS.get(key)
    if isinstance(requirements, str):
        requirements = MODE_REQUIREMENTS[requirements]
    if requirements is None:
        raise ValueError(f"Unsupported mission mode: {mode}")
    return requirements


def _canonical_mode(mode: str) -> str:
    key = str(mode or "").strip().lower().replace("-", "_").replace(" ", "_")
    return "solar" if key in {"solar", "solar_inspection"} else key


def _status_dict(source: Any) -> Dict[str, Any]:
    if source is None:
        return {}
    if isinstance(source, dict):
        return dict(source)
    if hasattr(source, "get_camera_status"):
        status = source.get_camera_status()
        if isinstance(status, dict):
            return status
    if hasattr(source, "get_telemetry_snapshot"):
        snap = source.get_telemetry_snapshot()
        if isinstance(snap, dict):
            return snap
    if hasattr(source, "status"):
        status = source.status()
        if isinstance(status, dict):
            return status
    # Last-resort: read only the known safe attribute names instead of
    # iterating dir(), which can invoke property getters with side effects.
    _SAFE_KEYS = ("has_camera", "has_gimbal", "has_thermal", "has_dispenser",
                  "has_gps", "droneType", "type", "drone_type")
    result: Dict[str, Any] = {}
    for key in _SAFE_KEYS:
        if hasattr(source, key):
            try:
                result[key] = getattr(source, key)
            except Exception:
                pass
    return result


def _parse_resolution(value: Any) -> Optional[Tuple[int, int]]:
    if value is None:
        return None
    if isinstance(value, str) and "x" in value.lower():
        left, right = value.lower().split("x", 1)
        try:
            return int(left), int(right)
        except ValueError:
            return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
    return None


def _parse_fov(value: Any) -> Optional[Tuple[float, float]]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    return None


def _format_resolution(value: Optional[Tuple[int, int]]) -> Optional[str]:
    if value is None:
        return None
    return f"{value[0]}x{value[1]}"


def _camel_to_snake(value: str) -> str:
    out = []
    for char in str(value):
        if char.isupper() and out:
            out.append("_")
        out.append(char.lower())
    return "".join(out)

