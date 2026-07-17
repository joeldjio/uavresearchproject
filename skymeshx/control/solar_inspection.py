"""
Solar Park Inspection Planning for UAV Operations.

Generates waypoint patterns for efficient solar panel inspection with configurable
altitude, gimbal angles, and image overlap. Supports thermal camera integration
for hotspot detection.

Frame Convention
----------------
All positions use GPS coordinates (latitude, longitude) for panel locations.
Generated waypoints include altitude in meters above ground (positive UP).
Internal calculations use local NED meters for distance computations.

MAVLink Commands
----------------
- MAV_CMD_NAV_WAYPOINT (16): Navigate to waypoint
- MAV_CMD_DO_MOUNT_CONTROL (205): Control gimbal orientation
- MAV_CMD_DO_DIGICAM_CONTROL (203): Trigger camera capture
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple, Optional

try:
    from pymavlink.dialects.v20.ardupilotmega import MAV_CMD_NAV_WAYPOINT as _MAV_CMD_NAV_WAYPOINT
except Exception:
    _MAV_CMD_NAV_WAYPOINT = 16  # MAV_CMD_NAV_WAYPOINT fallback

from skymeshx.control.mission import Waypoint


@dataclass
class PanelRow:
    """Solar panel row definition in GPS coordinates."""
    start: Tuple[float, float]  # (lat, lon) start of row
    end: Tuple[float, float]    # (lat, lon) end of row
    width: float = 2.0          # meters, panel row width
    
    def __post_init__(self):
        """Validate panel row coordinates."""
        if self.start == self.end:
            raise ValueError("Panel row start and end must be different")
        if self.width <= 0:
            raise ValueError("Panel row width must be positive")


@dataclass
class InspectionConfig:
    """Configuration for solar park inspection."""
    altitude: float = 15.0          # meters AGL above panels
    gimbal_pitch: float = -90.0     # degrees (-90 = straight down)
    gimbal_roll: float = 0.0        # degrees
    gimbal_yaw: float = 0.0         # degrees (relative to heading)
    overlap: float = 0.3            # image overlap ratio (0.0-1.0)
    speed: float = 3.0              # m/s (slower for better image quality)
    camera_fov_horizontal: float = 60.0  # degrees
    camera_fov_vertical: float = 45.0    # degrees
    trigger_distance: float = 5.0   # meters between camera triggers
    
    def __post_init__(self):
        """Validate configuration parameters."""
        if self.altitude <= 0:
            raise ValueError("Altitude must be positive")
        if not 0 <= self.overlap < 1:
            raise ValueError("Overlap must be between 0 and 1")
        if self.speed <= 0:
            raise ValueError("Speed must be positive")
        if not -90 <= self.gimbal_pitch <= 90:
            raise ValueError("Gimbal pitch must be between -90 and 90 degrees")
        if self.trigger_distance <= 0:
            raise ValueError("Trigger distance must be positive")


@dataclass
class CameraTriggerPoint:
    """Camera trigger point with footprint metadata for mission preview."""
    lat: float
    lon: float
    alt: float
    gimbal_angle: float
    footprint: List[dict]
    expected_image_id: str


@dataclass
class SolarMissionPreview:
    """Complete solar inspection preview data for UI and validation."""
    waypoints: List[Waypoint]
    waypoint_list: List[dict]
    trigger_points: List[CameraTriggerPoint]
    flight_path: List[dict]
    estimated_duration: float
    estimated_battery_usage: float
    total_images: int
    storage_required: float
    coverage_area: float
    warnings: List[str]

    def to_dict(self) -> dict:
        return {
            "waypoints": self.waypoint_list,
            "triggerPoints": [
                {
                    "lat": point.lat,
                    "lon": point.lon,
                    "alt": point.alt,
                    "gimbalAngle": point.gimbal_angle,
                    "footprint": point.footprint,
                    "expectedImageId": point.expected_image_id,
                }
                for point in self.trigger_points
            ],
            "flightPath": self.flight_path,
            "estimatedDuration": self.estimated_duration,
            "estimatedBatteryUsage": self.estimated_battery_usage,
            "totalImages": self.total_images,
            "storageRequired": self.storage_required,
            "coverageArea": self.coverage_area,
            "warnings": list(self.warnings),
        }


class SolarParkInspectionPlanner:
    """
    Generate waypoint patterns for solar park inspection.
    
    Supports systematic inspection of solar panel rows with automatic
    camera triggering and gimbal control for optimal image capture.
    
    Usage:
        planner = SolarParkInspectionPlanner()
        rows = [
            PanelRow(start=(48.137, 11.575), end=(48.138, 11.575)),
            PanelRow(start=(48.137, 11.576), end=(48.138, 11.576))
        ]
        config = InspectionConfig(altitude=15.0, overlap=0.3)
        waypoints = planner.plan_inspection(rows, config)
    """
    
    def __init__(self):
        """Initialize solar park inspection planner."""
        self._home_position: Optional[Tuple[float, float]] = None
    
    def set_home_position(self, lat: float, lon: float) -> None:
        """
        Set home position for local coordinate conversions.
        
        Args:
            lat: Home latitude (degrees)
            lon: Home longitude (degrees)
        """
        self._home_position = (lat, lon)
    
    def plan_inspection(
        self,
        panel_rows: List[PanelRow],
        config: InspectionConfig,
        add_rtl: bool = True
    ) -> List[Waypoint]:
        """
        Generate waypoints for solar panel inspection.
        
        Creates a systematic flight pattern over panel rows with camera
        triggers at regular intervals and gimbal control for optimal viewing.
        
        Args:
            panel_rows: List of panel row definitions
            config: Inspection configuration
            add_rtl: Add RTL (Return to Launch) waypoint at end
        
        Returns:
            List of waypoints with camera trigger and gimbal commands
        
        Raises:
            ValueError: If panel_rows is empty or config is invalid
        """
        if not panel_rows:
            raise ValueError("At least one panel row required")
        
        waypoints = []
        
        # Process each panel row
        for row_idx, row in enumerate(panel_rows):
            # Generate waypoints along the row
            row_waypoints = self._interpolate_row(row, config)
            
            # Add waypoints with camera triggers
            for wp_idx, (lat, lon) in enumerate(row_waypoints):
                # Navigation waypoint
                nav_wp = Waypoint(
                    lat=lat,
                    lon=lon,
                    alt=config.altitude,
                    speed=config.speed,
                    cmd=16,  # MAV_CMD_NAV_WAYPOINT
                    radius=2.0
                )
                waypoints.append(nav_wp)
                
                # Gimbal control command (only at first waypoint of each row)
                if wp_idx == 0:
                    gimbal_wp = Waypoint(
                        lat=lat,
                        lon=lon,
                        alt=config.altitude,
                        cmd=205,  # MAV_CMD_DO_MOUNT_CONTROL
                        param1=config.gimbal_pitch,  # Pitch angle
                        param2=config.gimbal_roll,   # Roll angle
                        param3=config.gimbal_yaw,    # Yaw angle
                        param7=2.0  # MAV_MOUNT_MODE_MAVLINK_TARGETING
                    )
                    waypoints.append(gimbal_wp)
                
                # Camera trigger command
                trigger_wp = Waypoint(
                    lat=lat,
                    lon=lon,
                    alt=config.altitude,
                    cmd=203,  # MAV_CMD_DO_DIGICAM_CONTROL
                    param5=1.0  # Trigger camera
                )
                waypoints.append(trigger_wp)
        
        # Add RTL waypoint if requested.
        # lat/lon/alt must be 0 per MAVLink spec for NAV_RETURN_TO_LAUNCH —
        # this avoids a 0.00 m distance-validation error against the last NAV WP.
        if add_rtl and waypoints:
            rtl_wp = Waypoint(
                lat=0.0,
                lon=0.0,
                alt=0.0,
                cmd=20  # MAV_CMD_NAV_RETURN_TO_LAUNCH
            )
            waypoints.append(rtl_wp)
        
        return waypoints

    def generate_solar_mission_with_preview(
        self,
        panel_rows: List[PanelRow],
        config: InspectionConfig,
        add_rtl: bool = True,
        thermal_enabled: bool = False,
    ) -> SolarMissionPreview:
        """
        Generate inspection waypoints plus UI-ready preview metadata.

        The preview is hardware-free and does not upload or execute a mission.
        """
        waypoints = self.plan_inspection(panel_rows, config, add_rtl=add_rtl)
        nav_waypoints = [wp for wp in waypoints if wp.cmd == _MAV_CMD_NAV_WAYPOINT]
        trigger_points = self._build_trigger_points(panel_rows, config)
        mission_time = self.estimate_mission_time(panel_rows, config)
        coverage_area = self.calculate_coverage_area(panel_rows, config)
        warnings = self.validate_solar_mission(
            panel_rows,
            config,
            thermal_enabled=thermal_enabled,
        )["warnings"]
        distance = self._total_row_distance(panel_rows)
        battery_required = self._estimate_battery_usage(mission_time, distance)

        return SolarMissionPreview(
            waypoints=waypoints,
            waypoint_list=[
                {"lat": wp.lat, "lon": wp.lon, "alt": wp.alt, "cmd": wp.cmd}
                for wp in waypoints
            ],
            trigger_points=trigger_points,
            flight_path=[
                {"lat": wp.lat, "lon": wp.lon, "alt": wp.alt}
                for wp in nav_waypoints
            ],
            estimated_duration=mission_time,
            estimated_battery_usage=battery_required,
            total_images=len(trigger_points),
            storage_required=self._estimate_storage_mb(len(trigger_points), thermal_enabled),
            coverage_area=coverage_area,
            warnings=warnings,
        )

    def validate_solar_mission(
        self,
        panel_rows: List[PanelRow],
        config: InspectionConfig,
        thermal_enabled: bool = False,
        battery_available_percent: float = 100.0,
    ) -> dict:
        """Validate solar mission parameters and return actionable warnings."""
        warnings: List[str] = []
        errors: List[str] = []

        if not panel_rows:
            errors.append("At least one panel row required")
            return {"valid": False, "warnings": warnings, "errors": errors}

        footprint_width, footprint_height = self._camera_footprint_m(config)
        if footprint_width <= 0 or footprint_height <= 0:
            errors.append("Camera footprint is invalid")
            return {"valid": False, "warnings": warnings, "errors": errors}

        if config.trigger_distance > footprint_height * max(0.1, 1.0 - config.overlap):
            warnings.append(
                "Trigger distance may leave image gaps for the configured vertical FOV and overlap"
            )

        max_row_width = max(row.width for row in panel_rows)
        if footprint_width < max_row_width:
            warnings.append(
                "Camera footprint is narrower than at least one panel row"
            )

        if config.altitude < 5.0:
            warnings.append("Low altitude - verify obstacle clearance above panels")
        elif config.altitude > 120.0:
            warnings.append("High altitude - image detail may be insufficient")

        gsd_cm = self._estimate_gsd_cm(config)
        if gsd_cm > 5.0:
            warnings.append("Ground sample distance is coarse for detailed defect inspection")

        mission_time = self.estimate_mission_time(panel_rows, config)
        distance = self._total_row_distance(panel_rows)
        battery_required = self._estimate_battery_usage(mission_time, distance)
        if battery_required > battery_available_percent:
            warnings.append("Estimated battery requirement exceeds available battery")
        elif battery_required > 80.0:
            warnings.append("Mission may require high battery usage - consider splitting rows")

        if not thermal_enabled:
            warnings.append("Thermal camera disabled - hotspot detection will be limited")

        return {
            "valid": not errors,
            "warnings": warnings,
            "errors": errors,
            "estimatedBatteryUsage": battery_required,
            "gsdCm": gsd_cm,
            "footprintWidthM": footprint_width,
            "footprintHeightM": footprint_height,
        }
    
    def _interpolate_row(
        self,
        row: PanelRow,
        config: InspectionConfig
    ) -> List[Tuple[float, float]]:
        """
        Generate waypoints along a panel row.
        
        Calculates waypoint positions based on trigger distance and overlap
        to ensure complete coverage of the panel row.
        
        Args:
            row: Panel row definition
            config: Inspection configuration
        
        Returns:
            List of (lat, lon) waypoint coordinates
        """
        # Calculate row length in meters
        row_length = self._haversine_distance(
            row.start[0], row.start[1],
            row.end[0], row.end[1]
        )
        
        # Calculate number of waypoints based on trigger distance
        num_waypoints = max(2, int(row_length / config.trigger_distance) + 1)
        
        # Generate waypoints along the row
        waypoints = []
        for i in range(num_waypoints):
            # Linear interpolation between start and end
            t = i / (num_waypoints - 1) if num_waypoints > 1 else 0
            lat = row.start[0] + t * (row.end[0] - row.start[0])
            lon = row.start[1] + t * (row.end[1] - row.start[1])
            waypoints.append((lat, lon))
        
        return waypoints

    def _build_trigger_points(
        self,
        panel_rows: List[PanelRow],
        config: InspectionConfig,
    ) -> List[CameraTriggerPoint]:
        points: List[CameraTriggerPoint] = []
        for row_idx, row in enumerate(panel_rows, start=1):
            for point_idx, (lat, lon) in enumerate(self._interpolate_row(row, config), start=1):
                points.append(
                    CameraTriggerPoint(
                        lat=lat,
                        lon=lon,
                        alt=config.altitude,
                        gimbal_angle=config.gimbal_pitch,
                        footprint=self._footprint_polygon(lat, lon, config),
                        expected_image_id=f"solar-r{row_idx:02d}-{point_idx:03d}",
                    )
                )
        return points

    def _footprint_polygon(
        self,
        lat: float,
        lon: float,
        config: InspectionConfig,
    ) -> List[dict]:
        width_m, height_m = self._camera_footprint_m(config)
        half_w = width_m / 2.0
        half_h = height_m / 2.0
        corners_ne = [
            (-half_h, -half_w),
            (-half_h, half_w),
            (half_h, half_w),
            (half_h, -half_w),
        ]
        return [
            self._offset_coord(lat, lon, north_m, east_m)
            for north_m, east_m in corners_ne
        ]

    def _camera_footprint_m(self, config: InspectionConfig) -> Tuple[float, float]:
        width = 2.0 * config.altitude * math.tan(
            math.radians(config.camera_fov_horizontal / 2.0)
        )
        height = 2.0 * config.altitude * math.tan(
            math.radians(config.camera_fov_vertical / 2.0)
        )
        return width, height

    def _offset_coord(self, lat: float, lon: float, north_m: float, east_m: float) -> dict:
        dlat = north_m / 111_320.0
        dlon = east_m / (
            111_320.0 * max(0.1, math.cos(math.radians(lat)))
        )
        return {"lat": lat + dlat, "lon": lon + dlon}

    def _estimate_gsd_cm(self, config: InspectionConfig) -> float:
        footprint_width, _ = self._camera_footprint_m(config)
        assumed_image_width_px = 1920.0
        return (footprint_width * 100.0) / assumed_image_width_px

    def _total_row_distance(self, panel_rows: List[PanelRow]) -> float:
        return sum(
            self._haversine_distance(
                row.start[0],
                row.start[1],
                row.end[0],
                row.end[1],
            )
            for row in panel_rows
        )

    def _estimate_battery_usage(self, mission_time_s: float, distance_m: float) -> float:
        # Conservative first-order estimate for preview warnings only.
        time_component = mission_time_s / 60.0 * 3.0
        distance_component = distance_m / 1000.0 * 8.0
        return min(100.0, max(5.0, time_component + distance_component + 10.0))

    def _estimate_storage_mb(self, image_count: int, thermal_enabled: bool) -> float:
        rgb_mb = image_count * 5.0
        thermal_mb = image_count * 2.5 if thermal_enabled else 0.0
        return rgb_mb + thermal_mb
    
    def _haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculate distance between two GPS coordinates using Haversine formula.
        
        Args:
            lat1, lon1: First coordinate (degrees)
            lat2, lon2: Second coordinate (degrees)
        
        Returns:
            Distance in meters
        """
        R = 6371000  # Earth radius in meters
        
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        # Haversine formula
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def calculate_coverage_area(
        self,
        panel_rows: List[PanelRow],
        config: InspectionConfig
    ) -> float:
        """
        Calculate total area covered by inspection mission.
        
        Args:
            panel_rows: List of panel row definitions
            config: Inspection configuration
        
        Returns:
            Total coverage area in square meters
        """
        total_area = 0.0
        
        for row in panel_rows:
            row_length = self._haversine_distance(
                row.start[0], row.start[1],
                row.end[0], row.end[1]
            )
            # Calculate effective coverage width based on camera FOV and altitude
            coverage_width = 2 * config.altitude * math.tan(
                math.radians(config.camera_fov_horizontal / 2)
            )
            total_area += row_length * coverage_width
        
        return total_area
    
    def estimate_mission_time(
        self,
        panel_rows: List[PanelRow],
        config: InspectionConfig
    ) -> float:
        """
        Estimate total mission time in seconds.
        
        Args:
            panel_rows: List of panel row definitions
            config: Inspection configuration
        
        Returns:
            Estimated mission time in seconds
        """
        total_distance = 0.0
        
        for row in panel_rows:
            row_length = self._haversine_distance(
                row.start[0], row.start[1],
                row.end[0], row.end[1]
            )
            total_distance += row_length
        
        # Add transition time between rows (assume 10 seconds per transition)
        transition_time = (len(panel_rows) - 1) * 10.0 if len(panel_rows) > 1 else 0.0
        
        # Calculate flight time
        flight_time = total_distance / config.speed
        
        return flight_time + transition_time
