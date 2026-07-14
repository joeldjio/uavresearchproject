"""
Field Coverage Planning for Agricultural UAV Operations.

Generates waypoint patterns for efficient field coverage with configurable
overlap, altitude, and pattern types (parallel lines, spiral, etc.).

Frame Convention
----------------
All positions use GPS coordinates (latitude, longitude) for field boundaries.
Generated waypoints include altitude in meters above ground (positive UP).
Internal calculations use local NED meters for distance computations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Optional


class CoveragePattern(Enum):
    """Coverage pattern types."""
    PARALLEL_LINES = 0  # Parallel lines with alternating direction
    SPIRAL = 1          # Spiral from outside to inside
    GRID = 2            # Grid pattern (both directions)
    ZIGZAG = 3          # Zigzag pattern (no turns at ends)


class MultiDroneStrategy(Enum):
    """Multi-drone coverage distribution strategies."""
    SINGLE_DRONE = 0      # Single drone covers entire field (default)
    OFFSET_PATTERN = 1    # Distribute lines among drones (D1: lines 1,4,7... D2: lines 2,5,8...)
    FIELD_SPLITTING = 2   # Divide field into zones based on drone count
    SEQUENTIAL_APF = 3    # Time-delayed start with APF collision avoidance
    FORMATION_FLIGHT = 4  # Leader flies pattern, followers maintain formation


@dataclass
class FieldBoundary:
    """Field boundary definition in GPS coordinates."""
    corners: List[Tuple[float, float]]  # [(lat, lon), ...]
    
    def __post_init__(self):
        """Validate boundary has at least 3 corners."""
        if len(self.corners) < 3:
            raise ValueError("Field boundary must have at least 3 corners")


@dataclass
class CoverageConfig:
    """Configuration for field coverage planning."""
    pattern: CoveragePattern = CoveragePattern.PARALLEL_LINES
    altitude: float = 20.0  # meters AGL
    overlap: float = 0.2    # 20% overlap between passes
    line_spacing: float = 10.0  # meters between parallel lines
    speed: float = 5.0      # m/s
    heading: float = 0.0    # degrees (0=North, 90=East) for parallel lines
    
    def __post_init__(self):
        """Validate configuration parameters."""
        if self.altitude <= 0:
            raise ValueError("Altitude must be positive")
        if not 0 <= self.overlap < 1:
            raise ValueError("Overlap must be between 0 and 1")
        if self.line_spacing <= 0:
            raise ValueError("Line spacing must be positive")
        if self.speed <= 0:
            raise ValueError("Speed must be positive")


class FieldCoveragePlanner:
    """
    Generate waypoint patterns for field coverage.
    
    Supports multiple coverage patterns optimized for agricultural operations
    like crop monitoring, spraying, or mapping.
    """
    
    def __init__(self):
        """Initialize field coverage planner."""
        self._home_position: Optional[Tuple[float, float]] = None
    
    def set_home_position(self, lat: float, lon: float) -> None:
        """
        Set home position for local coordinate conversions.
        
        Args:
            lat: Home latitude (degrees)
            lon: Home longitude (degrees)
        """
        self._home_position = (lat, lon)
    
    def generate_coverage_waypoints(
        self,
        boundary: FieldBoundary,
        config: CoverageConfig,
        add_rtl: bool = True
    ) -> List[Tuple[float, float, float]]:
        """
        Generate waypoints for field coverage.
        
        Args:
            boundary: Field boundary definition
            config: Coverage configuration
            add_rtl: If True, adds RTL (Return to Launch) as final waypoint
            
        Returns:
            List of waypoints as (lat, lon, alt) tuples
            
        Raises:
            ValueError: If home position not set or invalid configuration
        """
        if self._home_position is None:
            raise ValueError("Home position must be set before generating waypoints")
        
        # Convert boundary to local NED coordinates
        local_corners = [
            self._gps_to_local(lat, lon)
            for lat, lon in boundary.corners
        ]
        
        # Generate pattern in local coordinates
        if config.pattern == CoveragePattern.PARALLEL_LINES:
            local_waypoints = self._generate_parallel_lines(local_corners, config)
        elif config.pattern == CoveragePattern.SPIRAL:
            local_waypoints = self._generate_spiral(local_corners, config)
        elif config.pattern == CoveragePattern.GRID:
            local_waypoints = self._generate_grid(local_corners, config)
        elif config.pattern == CoveragePattern.ZIGZAG:
            local_waypoints = self._generate_zigzag(local_corners, config)
        else:
            raise ValueError(f"Unsupported pattern: {config.pattern}")
        
        # Convert back to GPS coordinates with altitude
        gps_waypoints = [
            (*self._local_to_gps(n, e), config.altitude)
            for n, e in local_waypoints
        ]
        
        # Add RTL waypoint at the end (return to home position)
        if add_rtl and self._home_position:
            home_lat, home_lon = self._home_position
            gps_waypoints.append((home_lat, home_lon, config.altitude))
        
        return gps_waypoints
    
    def _rotate_corners(
        self,
        corners: List[Tuple[float, float]],
        angle_deg: float,
    ) -> List[Tuple[float, float]]:
        """Rotate NED corners by *angle_deg* degrees (counter-clockwise)."""
        a = math.radians(angle_deg)
        cos_a, sin_a = math.cos(a), math.sin(a)
        return [(n * cos_a - e * sin_a, n * sin_a + e * cos_a) for n, e in corners]

    def _generate_parallel_lines(
        self,
        corners: List[Tuple[float, float]],
        config: CoverageConfig,
        *,
        _heading_override: Optional[float] = None,
    ) -> List[Tuple[float, float]]:
        """
        Generate parallel line pattern.

        Lines run along the *heading* axis (default 0 = North–South strips).
        The field polygon is rotated so that scanlines are always east–west
        in the rotated frame, then rotated back.

        Args:
            corners: Field corners in local NED (north, east)
            config: Coverage configuration
            _heading_override: Internal — use this heading instead of config.heading

        Returns:
            List of waypoints in local NED coordinates
        """
        heading = _heading_override if _heading_override is not None else config.heading

        # Rotate corners so that the scan direction aligns with east axis.
        # heading=0  → lines run N–S  → rotate by 0° (scan east)
        # heading=90 → lines run E–W  → rotate by -90° (scan east in rotated frame)
        rot_corners = self._rotate_corners(corners, -heading)

        # Calculate bounding box in rotated frame.
        north_vals = [n for n, e in rot_corners]
        east_vals  = [e for n, e in rot_corners]
        min_n, max_n = min(north_vals), max(north_vals)
        min_e, max_e = min(east_vals),  max(east_vals)

        field_width = max_e - min_e
        num_lines = int(field_width / config.line_spacing) + 1

        rot_waypoints: List[Tuple[float, float]] = []
        for i in range(num_lines):
            offset = min_e + i * config.line_spacing
            if offset > max_e:
                offset = max_e

            line_e = offset
            segments = self._polygon_segments_at_east(rot_corners, line_e)
            if not segments and abs(offset - max_e) < 1e-6 and max_e > min_e:
                line_e = max_e - 1e-6
                segments = self._polygon_segments_at_east(rot_corners, line_e)

            # Fall back to bbox only for degenerate polygons.
            if not segments:
                segments = [(min_n, max_n)]

            for start_n, end_n in segments:
                # Alternate direction for efficient lawnmower traversal.
                if i % 2 != 0:
                    start_n, end_n = end_n, start_n

                rot_waypoints.append((start_n, line_e))
                rot_waypoints.append((end_n, line_e))

        # Rotate waypoints back to the original NED frame.
        return self._rotate_corners(rot_waypoints, heading)

    def _polygon_segments_at_east(
        self,
        corners: List[Tuple[float, float]],
        east: float,
    ) -> List[Tuple[float, float]]:
        """Return north-coordinate intervals where a north/east scanline is inside the polygon."""
        if len(corners) < 3:
            return []

        intersections: List[float] = []
        count = len(corners)
        for idx in range(count):
            n1, e1 = corners[idx]
            n2, e2 = corners[(idx + 1) % count]

            if abs(e2 - e1) < 1e-12:
                continue
            if (e1 <= east < e2) or (e2 <= east < e1):
                t = (east - e1) / (e2 - e1)
                intersections.append(n1 + t * (n2 - n1))

        intersections.sort()
        unique: List[float] = []
        for value in intersections:
            if not unique or abs(value - unique[-1]) > 1e-6:
                unique.append(value)

        segments: List[Tuple[float, float]] = []
        # Step by 2 — if odd count (non-convex edge case), the last unpaired
        # entry is intentionally skipped rather than accessing unique[idx+1].
        for idx in range(0, len(unique) - 1, 2):
            start_n = unique[idx]
            end_n = unique[idx + 1]
            if abs(end_n - start_n) > 0.1:
                segments.append((start_n, end_n))
        return segments
    
    def _polygon_segments_at_north(
        self,
        corners: List[Tuple[float, float]],
        north: float,
    ) -> List[Tuple[float, float]]:
        """Return east-coordinate intervals where a horizontal scanline is inside the polygon."""
        if len(corners) < 3:
            return []

        intersections: List[float] = []
        count = len(corners)
        for idx in range(count):
            n1, e1 = corners[idx]
            n2, e2 = corners[(idx + 1) % count]

            if abs(n2 - n1) < 1e-12:
                continue
            if (n1 <= north < n2) or (n2 <= north < n1):
                t = (north - n1) / (n2 - n1)
                intersections.append(e1 + t * (e2 - e1))

        intersections.sort()
        unique: List[float] = []
        for value in intersections:
            if not unique or abs(value - unique[-1]) > 1e-6:
                unique.append(value)

        segments: List[Tuple[float, float]] = []
        for idx in range(0, len(unique) - 1, 2):
            start_e = unique[idx]
            end_e   = unique[idx + 1]
            if abs(end_e - start_e) > 0.1:
                segments.append((start_e, end_e))
        return segments

    def _generate_spiral(
        self,
        corners: List[Tuple[float, float]],
        config: CoverageConfig
    ) -> List[Tuple[float, float]]:
        """
        Generate inward spiral using contracted parallel-line passes.

        Each inward layer is produced by shrinking the boundary polygon
        by one ``line_spacing`` step and running a single parallel-line
        sweep.  This keeps the spiral clipped to the actual polygon shape
        rather than just its bounding box.

        Args:
            corners: Field corners in local NED
            config: Coverage configuration

        Returns:
            List of waypoints in local NED coordinates
        """
        import copy

        spacing = config.line_spacing
        waypoints: List[Tuple[float, float]] = []

        # Build successive inset layers.
        # A simple inset: move each edge inward by *spacing*.
        # We approximate this by shrinking the polygon toward its centroid.
        current = list(corners)
        layer = 0

        while True:
            # Generate one lawnmower pass over the current polygon layer.
            layer_wps = self._generate_parallel_lines(current, config)
            if not layer_wps:
                break
            waypoints.extend(layer_wps)

            # Shrink polygon inward toward centroid by one spacing step.
            cx = sum(n for n, e in current) / len(current)
            cy = sum(e for n, e in current) / len(current)
            shrunken = []
            for n, e in current:
                dn = cx - n
                de = cy - e
                dist = math.hypot(dn, de)
                if dist < 1e-6:
                    break  # polygon collapsed
                scale = max(0.0, dist - spacing) / dist
                shrunken.append((cx + (n - cx) * scale, cy + (e - cy) * scale))

            if len(shrunken) < 3:
                break

            # Check whether the shrunken polygon has meaningful area left.
            north_vals = [n for n, e in shrunken]
            east_vals  = [e for n, e in shrunken]
            if (max(north_vals) - min(north_vals) < spacing or
                    max(east_vals) - min(east_vals) < spacing):
                break

            current = shrunken
            layer += 1
            # Safety cap: never more layers than twice the max-dim / spacing.
            north_vals_orig = [n for n, e in corners]
            east_vals_orig  = [e for n, e in corners]
            max_dim = max(
                max(north_vals_orig) - min(north_vals_orig),
                max(east_vals_orig)  - min(east_vals_orig),
            )
            if layer > int(max_dim / spacing) + 2:
                break

        return waypoints
    
    def _generate_grid(
        self,
        corners: List[Tuple[float, float]],
        config: CoverageConfig
    ) -> List[Tuple[float, float]]:
        """
        Generate grid pattern (two perpendicular lawnmower passes).

        The first pass uses ``config.heading``; the second pass is rotated
        by 90° so that it sweeps the orthogonal direction.  Both passes are
        polygon-clipped via ``_generate_parallel_lines``.

        Args:
            corners: Field corners in local NED
            config: Coverage configuration

        Returns:
            List of waypoints in local NED coordinates
        """
        # First pass — along config.heading.
        horizontal = self._generate_parallel_lines(corners, config)

        # Second pass — perpendicular (heading + 90°).
        vertical = self._generate_parallel_lines(
            corners, config, _heading_override=config.heading + 90.0
        )

        return horizontal + vertical
    
    def _generate_zigzag(
        self,
        corners: List[Tuple[float, float]],
        config: CoverageConfig
    ) -> List[Tuple[float, float]]:
        """
        Generate zigzag pattern.

        Identical to parallel lines — the lawnmower already alternates
        direction per strip, producing a continuous zigzag path with no
        wasted turn-back segments.

        Args:
            corners: Field corners in local NED
            config: Coverage configuration

        Returns:
            List of waypoints in local NED coordinates
        """
        return self._generate_parallel_lines(corners, config)
    
    def _gps_to_local(self, lat: float, lon: float) -> Tuple[float, float]:
        """
        Convert GPS coordinates to local NED relative to home.
        
        Args:
            lat: Latitude (degrees)
            lon: Longitude (degrees)
            
        Returns:
            (north, east) in meters
        """
        if self._home_position is None:
            raise ValueError("Home position not set")
        
        home_lat, home_lon = self._home_position
        
        # Simple flat-earth approximation (good for small areas)
        R = 6371000  # Earth radius in meters
        
        dlat = math.radians(lat - home_lat)
        dlon = math.radians(lon - home_lon)
        
        north = dlat * R
        east = dlon * R * math.cos(math.radians(home_lat))
        
        return (north, east)
    
    def _local_to_gps(self, north: float, east: float) -> Tuple[float, float]:
        """
        Convert local NED coordinates to GPS.
        
        Args:
            north: North offset in meters
            east: East offset in meters
            
        Returns:
            (lat, lon) in degrees
        """
        if self._home_position is None:
            raise ValueError("Home position not set")
        
        home_lat, home_lon = self._home_position
        
        # Simple flat-earth approximation
        R = 6371000  # Earth radius in meters
        
        dlat = north / R
        dlon = east / (R * math.cos(math.radians(home_lat)))
        
        lat = home_lat + math.degrees(dlat)
        lon = home_lon + math.degrees(dlon)
        
        return (lat, lon)
    
    def estimate_coverage_time(
        self,
        waypoints: List[Tuple[float, float, float]],
        speed: float
    ) -> float:
        """
        Estimate time to complete coverage mission.
        
        Args:
            waypoints: List of (lat, lon, alt) waypoints
            speed: Flight speed in m/s
            
        Returns:
            Estimated time in seconds
        """
        if len(waypoints) < 2:
            return 0.0
        
        total_distance = 0.0
        for i in range(len(waypoints) - 1):
            lat1, lon1, _ = waypoints[i]
            lat2, lon2, _ = waypoints[i + 1]
            
            # Haversine distance
            R = 6371000  # Earth radius in meters
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            
            a = (math.sin(dlat / 2) ** 2 +
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                 math.sin(dlon / 2) ** 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance = R * c
            
            total_distance += distance
        
        return total_distance / speed
    
    def distribute_waypoints_for_swarm(
        self,
        waypoints: List[Tuple[float, float, float]],
        num_drones: int,
        strategy: MultiDroneStrategy,
        formation_offset: float = 5.0,
        sequential_delay: float = 10.0
    ) -> dict[str, List[Tuple[float, float, float]]]:
        """
        Distribute waypoints among multiple drones based on strategy.
        
        Args:
            waypoints: Full coverage waypoints (lat, lon, alt)
            num_drones: Number of drones in swarm
            strategy: Distribution strategy to use
            formation_offset: Meters between drones in formation (for FORMATION_FLIGHT)
            sequential_delay: Seconds between drone starts (for SEQUENTIAL_APF)
            
        Returns:
            Dictionary mapping drone_id to waypoint list
            
        Example:
            >>> planner = FieldCoveragePlanner()
            >>> waypoints = [(lat1, lon1, alt), (lat2, lon2, alt), ...]
            >>> distributed = planner.distribute_waypoints_for_swarm(
            ...     waypoints, num_drones=3, strategy=MultiDroneStrategy.OFFSET_PATTERN
            ... )
            >>> # distributed = {"D1": [...], "D2": [...], "D3": [...]}
        """
        if num_drones <= 0:
            raise ValueError("Number of drones must be positive")
        
        if num_drones == 1 or strategy == MultiDroneStrategy.SINGLE_DRONE:
            # Single drone gets all waypoints
            return {"D1": waypoints}
        
        if strategy == MultiDroneStrategy.OFFSET_PATTERN:
            return self._distribute_offset_pattern(waypoints, num_drones)
        
        elif strategy == MultiDroneStrategy.FIELD_SPLITTING:
            # Field splitting requires boundary - not applicable to pre-generated waypoints
            # Return offset pattern as fallback
            return self._distribute_offset_pattern(waypoints, num_drones)
        
        elif strategy == MultiDroneStrategy.SEQUENTIAL_APF:
            return self._distribute_sequential(waypoints, num_drones, sequential_delay)
        
        elif strategy == MultiDroneStrategy.FORMATION_FLIGHT:
            return self._distribute_formation(waypoints, num_drones, formation_offset)
        
        else:
            raise ValueError(f"Unsupported strategy: {strategy}")
    
    def _distribute_offset_pattern(
        self,
        waypoints: List[Tuple[float, float, float]],
        num_drones: int
    ) -> dict[str, List[Tuple[float, float, float]]]:
        """
        Distribute waypoints using offset pattern (interleaved lines).
        
        Drone 1 gets waypoints 0, num_drones, 2*num_drones, ...
        Drone 2 gets waypoints 1, num_drones+1, 2*num_drones+1, ...
        etc.
        
        Args:
            waypoints: Full coverage waypoints
            num_drones: Number of drones
            
        Returns:
            Dictionary mapping drone_id to waypoint list
        """
        result = {f"D{i+1}": [] for i in range(num_drones)}
        
        for idx, wp in enumerate(waypoints):
            drone_idx = idx % num_drones
            drone_id = f"D{drone_idx + 1}"
            result[drone_id].append(wp)
        
        return result
    
    def _distribute_sequential(
        self,
        waypoints: List[Tuple[float, float, float]],
        num_drones: int,
        delay_seconds: float
    ) -> dict[str, List[Tuple[float, float, float]]]:
        """
        Distribute waypoints with time delays (for APF collision avoidance).
        
        All drones get same waypoints but with staggered start times.
        This relies on APF (Artificial Potential Field) for collision avoidance.
        
        Args:
            waypoints: Full coverage waypoints
            num_drones: Number of drones
            delay_seconds: Delay between drone starts
            
        Returns:
            Dictionary mapping drone_id to waypoint list
            
        Note:
            Actual time delay must be implemented in mission upload logic.
            This method just assigns same waypoints to all drones.
        """
        result = {}
        for i in range(num_drones):
            drone_id = f"D{i+1}"
            # All drones get same waypoints
            # Time delay handled by mission upload with (i * delay_seconds) offset
            result[drone_id] = waypoints.copy()
        
        return result
    
    def _distribute_formation(
        self,
        waypoints: List[Tuple[float, float, float]],
        num_drones: int,
        offset_meters: float
    ) -> dict[str, List[Tuple[float, float, float]]]:
        """
        Distribute waypoints for formation flight.
        
        Leader (D1) gets original waypoints.
        Followers get offset waypoints maintaining formation.
        
        Args:
            waypoints: Full coverage waypoints
            num_drones: Number of drones
            offset_meters: Distance between drones in formation
            
        Returns:
            Dictionary mapping drone_id to waypoint list
        """
        if self._home_position is None:
            raise ValueError("Home position must be set for formation flight")
        
        result = {}
        
        # Leader gets original waypoints
        result["D1"] = waypoints.copy()
        
        # Followers get offset waypoints
        for i in range(1, num_drones):
            drone_id = f"D{i+1}"
            offset_waypoints = []
            
            for lat, lon, alt in waypoints:
                # Convert to local NED
                n, e = self._gps_to_local(lat, lon)
                
                # Apply offset (followers fly to the right of leader)
                # Offset in East direction for simple line formation
                e_offset = e + (i * offset_meters)
                
                # Convert back to GPS
                lat_offset, lon_offset = self._local_to_gps(n, e_offset)
                offset_waypoints.append((lat_offset, lon_offset, alt))
            
            result[drone_id] = offset_waypoints
        
        return result
    
    def split_field_into_zones(
        self,
        boundary: FieldBoundary,
        num_zones: int,
        config: CoverageConfig
    ) -> dict[str, List[Tuple[float, float, float]]]:
        """
        Split field into zones and generate coverage for each zone.
        
        Divides field into vertical strips (one per drone) and generates
        coverage pattern for each strip.
        
        Args:
            boundary: Field boundary definition
            num_zones: Number of zones (should equal number of drones)
            config: Coverage configuration
            
        Returns:
            Dictionary mapping drone_id to waypoint list for that zone
            
        Example:
            >>> planner = FieldCoveragePlanner()
            >>> planner.set_home_position(47.397742, 8.545594)
            >>> boundary = FieldBoundary([...])
            >>> zones = planner.split_field_into_zones(boundary, num_zones=3, config)
            >>> # zones = {"D1": [waypoints for zone 1], "D2": [...], "D3": [...]}
        """
        if self._home_position is None:
            raise ValueError("Home position must be set before splitting field")
        
        if num_zones <= 0:
            raise ValueError("Number of zones must be positive")
        
        if num_zones == 1:
            # Single zone = full field
            waypoints = self.generate_coverage_waypoints(boundary, config, add_rtl=True)
            return {"D1": waypoints}
        
        # Convert boundary to local NED
        local_corners = [
            self._gps_to_local(lat, lon)
            for lat, lon in boundary.corners
        ]
        
        # Calculate bounding box
        north_vals = [n for n, e in local_corners]
        east_vals = [e for n, e in local_corners]
        min_north, max_north = min(north_vals), max(north_vals)
        min_east, max_east = min(east_vals), max(east_vals)
        
        # Split field into vertical zones (divide East dimension)
        zone_width = (max_east - min_east) / num_zones
        
        result = {}
        for i in range(num_zones):
            drone_id = f"D{i+1}"
            
            # Define zone boundaries
            zone_min_east = min_east + (i * zone_width)
            zone_max_east = min_east + ((i + 1) * zone_width)
            
            # Create sub-boundary for this zone (rectangle)
            zone_corners_local = [
                (min_north, zone_min_east),
                (max_north, zone_min_east),
                (max_north, zone_max_east),
                (min_north, zone_max_east)
            ]
            
            # Convert back to GPS
            zone_corners_gps = [
                self._local_to_gps(n, e)
                for n, e in zone_corners_local
            ]
            
            # Create sub-boundary and generate coverage
            zone_boundary = FieldBoundary(zone_corners_gps)
            zone_waypoints = self.generate_coverage_waypoints(
                zone_boundary, config, add_rtl=False  # No RTL for field splitting to avoid collisions
            )
            
            # Add zone-specific RTL point (center of zone at end)
            zone_center_north = (min_north + max_north) / 2
            zone_center_east = (zone_min_east + zone_max_east) / 2
            rtl_lat, rtl_lon = self._local_to_gps(zone_center_north, zone_center_east)
            zone_waypoints.append((rtl_lat, rtl_lon, config.altitude))
            
            result[drone_id] = zone_waypoints
        
        return result
