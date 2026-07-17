"""
MissionContext — exposes Field Coverage Planning to QML.

Registered as context property 'mission' in the QML engine.
"""

from __future__ import annotations

import math
import threading
from typing import Any, List, Tuple, Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, Property, Signal, Slot

from skymeshx.control.field_coverage import (
    FieldCoveragePlanner,
    FieldBoundary,
    CoverageConfig,
    CoveragePattern,
    MultiDroneStrategy,
)
from skymeshx.control.mission import MissionEngine, Waypoint
from skymeshx.control.seeding_planner import (
    DispenserCalibration,
    SeedingMissionPlanner,
    SeedingConfig,
)

if TYPE_CHECKING:
    from tools.ui.context.swarm_context import SwarmContext


class MissionContext(QObject):
    """QML-callable wrapper for field coverage planning."""

    # Signals
    logMessage = Signal(str, str, arguments=["level", "text"])
    fieldBoundaryChanged = Signal()
    coverageGenerated = Signal()
    coverageCleared = Signal()
    drawingModeChanged = Signal(bool, arguments=["active"])
    missionLockChanged = Signal(bool, arguments=["locked"])
    solarPanelRowsChanged = Signal()
    solarStatsChanged = Signal()
    solarRowDrawingModeChanged = Signal(bool, arguments=["active"])
    missionWaypointModeChanged = Signal(bool, arguments=["active"])
    missionWaypointsChanged = Signal()
    seedingPreviewChanged = Signal()
    solarPreviewChanged = Signal()
    missionUploadStarted = Signal(str, arguments=["mode"])
    missionUploadFinished = Signal(bool, str, arguments=["success", "message"])

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        
        # Field Coverage Planner
        self._planner = FieldCoveragePlanner()
        self._home_set = False
        self._home_lat = 0.0
        self._home_lon = 0.0
        
        # Seeding Mission Planner
        self._seeding_planner = SeedingMissionPlanner()
        
        # Mission mode: 0 = coverage, 1 = seeding, 2 = solar inspection
        self._mission_mode = 0
        self._seeding_mode_enabled = False  # Kept for backward compatibility
        
        # Field boundary
        self._boundary_points: List[Tuple[float, float]] = []
        self._drawing_mode = False
        self._exclusion_zone_drawing = False
        self._current_exclusion_zone: List[Tuple[float, float]] = []
        self._exclusion_zones: List[List[Tuple[float, float]]] = []
        
        # Coverage configuration
        self._coverage_pattern = CoveragePattern.PARALLEL_LINES.value
        self._coverage_altitude = 20.0
        self._coverage_line_spacing = 10.0
        self._coverage_overlap = 0.2
        self._coverage_speed = 5.0
        
        # Multi-drone strategy
        self._multi_drone_strategy = MultiDroneStrategy.SINGLE_DRONE.value
        self._formation_offset = 5.0  # meters between drones in formation
        self._sequential_delay = 10.0  # seconds between drone starts
        
        # Generated waypoints
        self._coverage_waypoints: List[Tuple[float, float, float]] = []
        self._coverage_distance = 0.0
        self._coverage_time = 0.0
        self._preview_active = False
        
        # Seeding mission configuration
        self._seed_spacing = 2.0  # meters between seed drops
        self._seed_row_spacing = 5.0  # meters between rows
        self._seed_altitude = 10.0  # seeding altitude
        self._seed_drop_duration = 0.5  # seconds dispenser stays open
        self._servo_channel = 9  # servo channel for dispenser
        self._servo_open_pwm = 1900  # PWM value to open dispenser
        self._servo_close_pwm = 1100  # PWM value to close dispenser
        
        # Generated seeding waypoints
        self._seeding_waypoints: List[Waypoint] = []
        self._seeding_distance = 0.0
        self._seeding_time = 0.0
        self._seeding_drop_count = 0
        self._seeding_preview_active = False
        self._last_seeding_preview: dict = {}
        self._last_solar_preview: dict = {}
        self._uploaded_missions: dict[str, dict[str, int]] = {}
        
        # Solar inspection configuration
        self._solar_panel_rows: List[dict] = []  # List of {start_lat, start_lon, end_lat, end_lon, length}
        self._solar_altitude = 15.0
        
        # Mission mode waypoint adding (similar to boundary drawing)
        self._mission_waypoint_mode = False
        self._mission_waypoints: List[Tuple[float, float, float]] = []  # (lat, lon, alt)
        self._mission_waypoint_altitude = 20.0
        self._solar_gimbal_pitch = -90.0
        self._solar_trigger_distance = 5.0
        self._solar_overlap = 0.3
        self._solar_coverage_area = 0.0
        self._solar_mission_time = 0.0
        self._solar_waypoint_count = 0
        self._solar_photo_count = 0
        self._solar_waypoints: List[Waypoint] = []
        self._adding_solar_row = False  # True when waiting for user to click two points on map
        self._solar_row_start_lat = 0.0
        self._solar_row_start_lon = 0.0
        
        # Mission lock state
        self._mission_locked = False
        self._poll_in_progress = False  # Gate to prevent concurrent polls

        # Explicit mission target drone IDs set by QML before upload/start.
        # Empty list = fall back to all connected drones (legacy behaviour).
        self._target_drone_ids: List[str] = []

        # Swarm context reference (injected via wire())
        self._swarm_context: Optional["SwarmContext"] = None
        
        # Poll mission status every 500ms to update lock state
        from PySide6.QtCore import QTimer
        self._lock_poll_timer = QTimer(self)
        self._lock_poll_timer.timeout.connect(self._update_mission_lock)
        self._lock_poll_timer.start(500)  # 500ms polling interval
        
        # Boundary drawing timeout (5 minutes)
        self._drawing_timeout_timer = QTimer(self)
        self._drawing_timeout_timer.timeout.connect(self._on_drawing_timeout)
        self._drawing_timeout_timer.setSingleShot(True)

    # ── Properties ────────────────────────────────────────────────────────

    @Property(bool, notify=drawingModeChanged)
    def drawingMode(self):
        return self._drawing_mode

    @Property(int, notify=fieldBoundaryChanged)
    def fieldBoundaryPoints(self):
        return len(self._boundary_points)

    @Property(int, notify=fieldBoundaryChanged)
    def coveragePattern(self):
        return self._coverage_pattern

    @coveragePattern.setter
    def coveragePattern(self, value):
        self._coverage_pattern = value
        self.fieldBoundaryChanged.emit()

    @Property(float, notify=fieldBoundaryChanged)
    def coverageAltitude(self):
        return self._coverage_altitude

    @coverageAltitude.setter
    def coverageAltitude(self, value):
        self._coverage_altitude = value
        self.fieldBoundaryChanged.emit()

    @Property(float, notify=fieldBoundaryChanged)
    def coverageLineSpacing(self):
        return self._coverage_line_spacing

    @coverageLineSpacing.setter
    def coverageLineSpacing(self, value):
        self._coverage_line_spacing = value
        self.fieldBoundaryChanged.emit()

    @Property(float, notify=fieldBoundaryChanged)
    def coverageOverlap(self):
        return self._coverage_overlap

    @coverageOverlap.setter
    def coverageOverlap(self, value):
        self._coverage_overlap = value
        self.fieldBoundaryChanged.emit()

    @Property(float, notify=fieldBoundaryChanged)
    def coverageSpeed(self):
        return self._coverage_speed

    @coverageSpeed.setter
    def coverageSpeed(self, value):
        self._coverage_speed = value
        self.fieldBoundaryChanged.emit()

    @Property(int, notify=coverageGenerated)
    def coverageWaypointCount(self):
        return len(self._coverage_waypoints)

    @Property(float, notify=coverageGenerated)
    def coverageDistance(self):
        return self._coverage_distance

    @Property(float, notify=coverageGenerated)
    def coverageTime(self):
        return self._coverage_time

    @Property(bool, notify=coverageGenerated)
    def fieldCoverageActive(self):
        return len(self._coverage_waypoints) > 0

    @Property(int, notify=fieldBoundaryChanged)
    def multiDroneStrategy(self):
        return self._multi_drone_strategy

    @multiDroneStrategy.setter
    def multiDroneStrategy(self, value):
        self._multi_drone_strategy = value
        self.fieldBoundaryChanged.emit()

    @Property(float, notify=fieldBoundaryChanged)
    def formationOffset(self):
        return self._formation_offset

    @formationOffset.setter
    def formationOffset(self, value):
        self._formation_offset = value
        self.fieldBoundaryChanged.emit()

    @Property(float, notify=fieldBoundaryChanged)
    def sequentialDelay(self):
        return self._sequential_delay

    @sequentialDelay.setter
    def sequentialDelay(self, value):
        self._sequential_delay = value
        self.fieldBoundaryChanged.emit()

    @Property(bool, notify=missionLockChanged)
    def missionLocked(self):
        """True if any drone is currently executing a mission (prevents editing)."""
        return self._mission_locked
    
    @Property(bool, notify=missionWaypointModeChanged)
    def missionWaypointMode(self):
        """True when in mission waypoint adding mode."""
        return self._mission_waypoint_mode
    
    @Property(int, notify=missionWaypointsChanged)
    def missionWaypointCount(self):
        """Number of mission waypoints added."""
        return len(self._mission_waypoints)
    
    @Property(float, notify=missionWaypointsChanged)
    def missionWaypointAltitude(self):
        """Altitude for mission waypoints."""
        return self._mission_waypoint_altitude
    
    @missionWaypointAltitude.setter
    def missionWaypointAltitude(self, value):
        self._mission_waypoint_altitude = value
        self.missionWaypointsChanged.emit()

    # ── Methods ───────────────────────────────────────────────────────────
    
    def _update_mission_lock(self):
        """
        Poll swarm context to check if any drone is in mission mode.
        
        Thread-safe with gating to prevent concurrent polls.
        Uses SwarmContext._mission_active dict as primary source of truth.
        
        Timer is automatically stopped when no drones are connected to reduce
        idle CPU usage from 15-20% to <5%.
        """
        # Gate timer when no drones connected (Improvement 6: Polling Overhead Reduction)
        if self._swarm_context:
            try:
                backends = self._swarm_context.backend.all_backends()
                has_drones = len(backends) > 0
                
                if has_drones and not self._lock_poll_timer.isActive():
                    self._lock_poll_timer.start()
                elif not has_drones and self._lock_poll_timer.isActive():
                    self._lock_poll_timer.stop()
                    # Clear lock state when no drones
                    if self._mission_locked:
                        self._mission_locked = False
                        self.missionLockChanged.emit(False)
                    return
            except Exception:
                pass  # Ignore errors in timer gating
        
        # Gate: Skip if previous poll still running
        if self._poll_in_progress:
            return
        
        if not self._swarm_context:
            return
        
        try:
            self._poll_in_progress = True
            mission_active = False
            
            # Primary check: SwarmContext._mission_active dict (set by MissionContext)
            # This is the authoritative source for mission-controlled drones
            if hasattr(self._swarm_context, '_mission_active'):
                with self._swarm_context._state_lock:
                    # Check if any drone has an active mission (Event not set)
                    for drone_id, event in self._swarm_context._mission_active.items():
                        if not event.is_set():  # Event cleared = mission active
                            mission_active = True
                            break
            
            # Fallback check: Poll backend FSM states (for missions started externally)
            if not mission_active:
                try:
                    backends = self._swarm_context.backend.all_backends()
                    
                    for drone_id, backend in backends.items():
                        if not backend.is_connected:
                            continue
                        
                        # Check FSM state (non-blocking)
                        if hasattr(backend, 'fsm_state'):
                            try:
                                fsm_state = str(backend.fsm_state).upper()
                                if fsm_state == 'MISSION':
                                    mission_active = True
                                    break
                            except Exception:
                                pass  # Ignore errors from individual backends
                        
                        # Check telemetry flight mode (with timeout protection)
                        if hasattr(backend, 'get_telemetry_snapshot'):
                            try:
                                snap = backend.get_telemetry_snapshot()
                                if snap:
                                    flight_mode = str(snap.get('flight_mode', '')).upper()
                                    if flight_mode in ('AUTO', 'MISSION'):
                                        mission_active = True
                                        break
                            except Exception:
                                pass  # Ignore errors from individual backends
                
                except Exception:
                    pass  # Ignore errors from backend iteration
            
            # Update lock state if changed (emit signal outside lock)
            if mission_active != self._mission_locked:
                self._mission_locked = mission_active
                self.missionLockChanged.emit(mission_active)
                if mission_active:
                    self.logMessage.emit("INFO", "[MISSION] 🔒 Mission lock activated")
                else:
                    self.logMessage.emit("INFO", "[MISSION] 🔓 Mission lock released")
        
        finally:
            self._poll_in_progress = False

    @Slot(float, float)
    def setHomePosition(self, lat: float, lon: float):
        with self._lock:
            self._planner.set_home_position(lat, lon)
            self._seeding_planner.set_home_position(lat, lon)
            self._home_set = True
            self._home_lat = lat
            self._home_lon = lon
            self.logMessage.emit("INFO", f"[MISSION] Home: {lat:.6f}, {lon:.6f}")

    def _commit_current_exclusion_zone_locked(self) -> bool:
        """Commit the active exclusion zone if enough points were drawn."""
        if not self._current_exclusion_zone:
            return False

        point_count = len(self._current_exclusion_zone)
        if point_count >= 3:
            self._exclusion_zones.append(list(self._current_exclusion_zone))
            self.logMessage.emit("INFO", f"[MISSION] Exclusion zone: {point_count} points")
        else:
            self.logMessage.emit("WARNING", "[MISSION] Need >=3 exclusion points")

        self._current_exclusion_zone.clear()
        return True

    @Slot()
    def startDrawingBoundary(self):
        exclusion_changed = False
        with self._lock:
            exclusion_changed = self._commit_current_exclusion_zone_locked()
            self._drawing_mode = True
            self._exclusion_zone_drawing = False
            self.logMessage.emit("INFO", f"[MISSION] Drawing mode set to: {self._drawing_mode}")
            self.drawingModeChanged.emit(True)
            self.logMessage.emit("INFO", "[MISSION] Click map to define boundary (5min timeout)")
            # Start 5-minute timeout
            self._drawing_timeout_timer.start(300000)  # 300000ms = 5 minutes
        if exclusion_changed:
            self.fieldBoundaryChanged.emit()

    def _on_drawing_timeout(self):
        """Auto-cancel boundary drawing after 5 minutes — stops drawing mode but keeps collected points."""
        with self._lock:
            if self._drawing_mode:
                self._drawing_mode = False
                # Do NOT clear _boundary_points — keep what the user already drew
                self._drawing_timeout_timer.stop()
                self.drawingModeChanged.emit(False)
                self.fieldBoundaryChanged.emit()
                self.logMessage.emit("WARN", "[MISSION] ⏱ Boundary drawing timed out (5min) — points kept")

    @Slot()
    def cancelDrawingBoundary(self):
        """Cancel boundary drawing and clear points."""
        try:
            with self._lock:
                self._drawing_mode = False
                self._exclusion_zone_drawing = False
                self._boundary_points.clear()
                self._current_exclusion_zone.clear()
                self._drawing_timeout_timer.stop()
            self.drawingModeChanged.emit(False)
            self.fieldBoundaryChanged.emit()
            self.logMessage.emit("INFO", "[MISSION] ❌ Boundary drawing cancelled")
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] cancelDrawingBoundary error: {e}")

    @Slot(float, float)
    def addBoundaryPoint(self, lat: float, lon: float):
        """Add a boundary point during drawing mode."""
        try:
            added_exclusion_point = False
            with self._lock:
                if self._exclusion_zone_drawing:
                    self._current_exclusion_zone.append((lat, lon))
                    point_count = len(self._current_exclusion_zone)
                    self.logMessage.emit("INFO", f"[MISSION] Exclusion point {point_count} added")
                    added_exclusion_point = True
                else:
                    self._boundary_points.append((lat, lon))
                    # Set home position from first boundary point
                    if len(self._boundary_points) == 1 and not self._home_set:
                        self._planner.set_home_position(lat, lon)
                        self._seeding_planner.set_home_position(lat, lon)
                        self._home_set = True
                        self._home_lat = lat
                        self._home_lon = lon
            # Emit signal AFTER releasing lock to prevent deadlock
            self.fieldBoundaryChanged.emit()
            if added_exclusion_point:
                return

            self.logMessage.emit("INFO", f"[MISSION] Point {len(self._boundary_points)} added")
            if len(self._boundary_points) == 1:
                self.logMessage.emit("INFO", f"[MISSION] Home set to first boundary point")
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] Failed to add point: {e}")

    @Slot()
    def finishDrawingBoundary(self):
        exclusion_committed = False
        boundary_count = 0
        with self._lock:
            self._drawing_mode = False
            self._drawing_timeout_timer.stop()  # Stop timeout timer
            if self._exclusion_zone_drawing:
                self._exclusion_zone_drawing = False
                self._commit_current_exclusion_zone_locked()
                exclusion_committed = True
            else:
                boundary_count = len(self._boundary_points)
        # Emit signals outside the lock to prevent deadlock.
        self.drawingModeChanged.emit(False)
        if exclusion_committed:
            self.fieldBoundaryChanged.emit()
            return
        if boundary_count >= 3:
            self.logMessage.emit("INFO", f"[MISSION] ✅ Boundary: {boundary_count} points")
        else:
            self.logMessage.emit("WARNING", "[MISSION] Need ≥3 points")
    
    @Slot(int, float, float)
    def updateBoundaryPoint(self, index: int, lat: float, lon: float):
        """Update a boundary point position when dragged on map."""
        try:
            with self._lock:
                if 0 <= index < len(self._boundary_points):
                    self._boundary_points[index] = (lat, lon)
                    # Emit signal AFTER releasing lock
            self.fieldBoundaryChanged.emit()
            self.logMessage.emit("INFO", f"[MISSION] Boundary point {index + 1} updated")
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] Failed to update boundary point: {e}")

    @Slot()
    def clearFieldBoundary(self):
        with self._lock:
            self._boundary_points.clear()
            self._current_exclusion_zone.clear()
            self._exclusion_zones.clear()
            self._exclusion_zone_drawing = False
            self._coverage_waypoints.clear()
            self._coverage_distance = 0.0
            self._coverage_time = 0.0
        # Emit signals AFTER releasing lock
        self.fieldBoundaryChanged.emit()
        self.coverageCleared.emit()
        self.logMessage.emit("INFO", "[MISSION] Boundary cleared")
    
    # ── Mission Waypoint Mode Methods ────────────────────────────────────
    
    @Slot()
    def clearBoundary(self):
        """QML alias for clearing the drawn field boundary."""
        self.clearFieldBoundary()

    @Slot()
    def startDrawingExclusionZone(self):
        """Activate map drawing for a seeding exclusion zone."""
        exclusion_changed = False
        with self._lock:
            exclusion_changed = self._commit_current_exclusion_zone_locked()
            self._drawing_mode = True
            self._exclusion_zone_drawing = True
            self.drawingModeChanged.emit(True)
            self.logMessage.emit("INFO", "[MISSION] Click map to define exclusion zone")
            self._drawing_timeout_timer.start(300000)
        if exclusion_changed:
            self.fieldBoundaryChanged.emit()

    @Slot()
    def startMissionWaypointMode(self):
        """Start mission waypoint adding mode."""
        with self._lock:
            self._mission_waypoint_mode = True
            # Also activate drawing mode so map accepts clicks
            self._drawing_mode = True
        # Emit signals outside the lock to prevent deadlock if a connected
        # QML slot re-enters any locked MissionContext method.
        self.missionWaypointModeChanged.emit(True)
        self.drawingModeChanged.emit(True)
        self.logMessage.emit("INFO", "[MISSION] Click map to add waypoints")
    
    @Slot()
    def finishMissionWaypointMode(self):
        """Finish mission waypoint adding mode."""
        with self._lock:
            self._mission_waypoint_mode = False
            # Also deactivate drawing mode
            self._drawing_mode = False
            wp_count = len(self._mission_waypoints)
        # Emit signals outside the lock to prevent deadlock.
        self.missionWaypointModeChanged.emit(False)
        self.drawingModeChanged.emit(False)
        if wp_count > 0:
            self.logMessage.emit("INFO", f"[MISSION] ✅ Added {wp_count} waypoints")
        else:
            self.logMessage.emit("WARNING", "[MISSION] No waypoints added")
    
    @Slot()
    def cancelMissionWaypointMode(self):
        """Cancel mission waypoint adding mode and clear waypoints."""
        try:
            with self._lock:
                self._mission_waypoint_mode = False
                self._drawing_mode = False
                self._mission_waypoints.clear()
            self.missionWaypointModeChanged.emit(False)
            self.drawingModeChanged.emit(False)
            self.missionWaypointsChanged.emit()
            self.logMessage.emit("INFO", "[MISSION] ❌ Waypoint mode cancelled")
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] cancelMissionWaypointMode error: {e}")
    
    @Slot(float, float)
    def addMissionWaypoint(self, lat: float, lon: float):
        """Add a mission waypoint during waypoint mode."""
        try:
            with self._lock:
                self._mission_waypoints.append((lat, lon, self._mission_waypoint_altitude))
                # Set home position from first waypoint
                if len(self._mission_waypoints) == 1 and not self._home_set:
                    self._planner.set_home_position(lat, lon)
                    self._seeding_planner.set_home_position(lat, lon)
                    self._home_set = True
                    self._home_lat = lat
                    self._home_lon = lon
            # Emit signal AFTER releasing lock
            self.missionWaypointsChanged.emit()
            self.logMessage.emit("INFO", f"[MISSION] Waypoint {len(self._mission_waypoints)} added: {lat:.6f}, {lon:.6f}")
            if len(self._mission_waypoints) == 1:
                self.logMessage.emit("INFO", "[MISSION] Home set to first waypoint")
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] Failed to add waypoint: {e}")
    
    @Slot()
    def clearMissionWaypoints(self):
        """Clear all mission waypoints."""
        with self._lock:
            self._mission_waypoints.clear()
        self.missionWaypointsChanged.emit()
        self.logMessage.emit("INFO", "[MISSION] Waypoints cleared")
    
    @Slot(result="QVariantList")
    def getMissionWaypoints(self):
        """Get mission waypoints for map display."""
        with self._lock:
            return [{"lat": lat, "lon": lon, "alt": alt} for lat, lon, alt in self._mission_waypoints]

    @Slot()
    def generateMission(self):
        """Unified generate method - calls coverage, seeding, or solar based on mode."""
        if self._mission_mode == 1:
            self.generateSeedingMission()
        elif self._mission_mode == 2:
            self.generateSolarInspection()
        else:
            self.generateFieldCoverage()
    
    @Slot()
    def generateFieldCoverage(self):
        try:
            with self._lock:
                if not self._home_set:
                    self.logMessage.emit("ERROR", "[MISSION] Home not set")
                    return
                if len(self._boundary_points) < 3:
                    self.logMessage.emit("ERROR", "[MISSION] Need ≥3 points")
                    return
                
                boundary = FieldBoundary(corners=self._boundary_points)
                config = CoverageConfig(
                    pattern=CoveragePattern(self._coverage_pattern),
                    altitude=self._coverage_altitude,
                    line_spacing=self._coverage_line_spacing,
                    overlap=self._coverage_overlap,
                    speed=self._coverage_speed,
                )
                
                self._coverage_waypoints = self._planner.generate_coverage_waypoints(boundary, config)
                self._coverage_distance = self._calculate_distance()
                self._coverage_time = self._planner.estimate_coverage_time(
                    self._coverage_waypoints, self._coverage_speed
                )
            
            # Emit signals AFTER releasing lock to prevent deadlock
            self.coverageGenerated.emit()
            self.logMessage.emit(
                "INFO",
                f"[MISSION] {len(self._coverage_waypoints)} WP, "
                f"{self._coverage_distance/1000:.2f} km, {self._coverage_time/60:.1f} min"
            )
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] Failed: {e}")

    def set_swarm_context(self, swarm_context: "SwarmContext") -> None:
        """Inject SwarmContext reference for mission upload."""
        self._swarm_context = swarm_context

    def _mission_mode_name(self, mode: Optional[int] = None) -> str:
        mode_value = self._mission_mode if mode is None else mode
        if mode_value == 1:
            return "seeding"
        if mode_value == 2:
            return "solar"
        return "coverage"

    def _clear_uploaded_missions(self) -> None:
        with self._lock:
            self._uploaded_missions.clear()

    def _mark_mission_uploaded(self, drone_id: str, mode: int, waypoint_count: int) -> None:
        with self._lock:
            self._uploaded_missions[drone_id] = {
                "mode": int(mode),
                "waypoint_count": int(waypoint_count),
            }

    def _uploaded_mission_for(self, drone_id: str) -> dict[str, int] | None:
        with self._lock:
            uploaded = self._uploaded_missions.get(drone_id)
            return dict(uploaded) if uploaded else None

    @Slot()
    @Slot(str)
    def setTargetDroneIds(self, ids_json: str) -> None:
        """
        Set the list of drone IDs that upload/start/stop will act on.
        Pass JSON array of strings, e.g. '["drone1","drone2"]'.
        Pass '[]' or '' to reset to all-connected-drones fallback.
        """
        import json
        try:
            ids = json.loads(ids_json) if ids_json.strip() else []
            self._target_drone_ids = [str(i) for i in ids if i]
        except Exception:
            self._target_drone_ids = []

    def _get_target_drones(self) -> List[Tuple[str, Any]]:
        """
        Return list of (drone_id, backend) to act on.

        Priority:
          1. _target_drone_ids if non-empty — filter connected backends to that set
          2. All connected backends (legacy fall-back)
        """
        if not self._swarm_context:
            return []
        backends = self._swarm_context.backend.all_backends()
        connected = {
            did: b for did, b in backends.items() if b.is_connected
        }
        if self._target_drone_ids:
            return [
                (did, connected[did])
                for did in self._target_drone_ids
                if did in connected
            ]
        return list(connected.items())

    @Slot()
    def uploadMission(self):
        """Unified upload method - calls coverage, seeding, or solar based on mode."""
        if self._mission_mode == 1:
            self.uploadSeedingMission()
        elif self._mission_mode == 2:
            self.uploadSolarMission()
        else:
            self.uploadCoverageMission()

    @Slot()
    def startMission(self):
        """Explicitly start an uploaded mission by switching connected drones to AUTO."""
        threading.Thread(
            target=self._mission_control_worker,
            args=("start",),
            daemon=True
        ).start()

    @Slot()
    def pauseMission(self):
        """Pause an active mission by switching connected drones to LOITER."""
        threading.Thread(
            target=self._mission_control_worker,
            args=("pause",),
            daemon=True
        ).start()

    @Slot()
    def abortMission(self):
        """Abort active mission and command RTL on connected drones."""
        threading.Thread(
            target=self._mission_control_worker,
            args=("abort",),
            daemon=True
        ).start()

    def _auto_start_drone(self, drone_id: str, backend: Any, mission_mode: int) -> bool:
        """
        Arm → Takeoff → AUTO for one drone immediately after a successful upload.

        Drone state branching:
          - Already airborne (alt >= 2 m)  → set AUTO only
          - Armed but on ground             → takeoff then AUTO
          - Disarmed on ground              → GUIDED (ArduPilot only) → arm → takeoff → AUTO

        Returns True if AUTO mode was successfully set.
        """
        import time

        drone = getattr(backend, "_drone", None)
        if not drone:
            self.logMessage.emit("WARN", f"[{drone_id}] No drone object — cannot auto-start")
            return False

        is_px4 = getattr(drone._conn.telemetry, "autopilot", "") == "px4"

        if drone.altitude >= 2.0:
            # Already airborne — switch to AUTO directly
            self.logMessage.emit("INFO", f"[{drone_id}] 🛫 Already airborne — starting mission (AUTO)...")
        else:
            # On the ground — need to arm and take off first
            if not drone.armed:
                # 1. GUIDED mode (ArduPilot only — PX4 rejects DO_SET_MODE while disarmed)
                if not is_px4:
                    self.logMessage.emit("INFO", f"[{drone_id}] 🔧 Switching to GUIDED...")
                    if not drone.set_mode("GUIDED", timeout=5.0):
                        self.logMessage.emit("WARN", f"[{drone_id}] ⚠ GUIDED mode failed, trying anyway...")

                # 2. ARM
                self.logMessage.emit("INFO", f"[{drone_id}] 🔧 Arming...")
                if not drone.arm(timeout=10.0):
                    self.logMessage.emit("ERROR", f"[{drone_id}] ❌ Arm failed — mission not started")
                    return False
                self.logMessage.emit("INFO", f"[{drone_id}] ✅ Armed")
            else:
                self.logMessage.emit("INFO", f"[{drone_id}] Already armed — proceeding to takeoff")

            # 3. TAKEOFF
            if mission_mode == 1:
                takeoff_alt = self._seed_altitude
            elif mission_mode == 2:
                takeoff_alt = self._solar_altitude
            else:
                takeoff_alt = self._coverage_altitude
            self.logMessage.emit("INFO", f"[{drone_id}] 🚁 Taking off to {takeoff_alt}m...")
            if not drone.takeoff(altitude=takeoff_alt, timeout=30.0):
                self.logMessage.emit("WARN", f"[{drone_id}] ⚠ Takeoff timed out — attempting AUTO anyway...")
            else:
                self.logMessage.emit("INFO", f"[{drone_id}] ✅ Airborne")
                time.sleep(1.0)  # brief settle

        # 4. SET AUTO
        self.logMessage.emit("INFO", f"[{drone_id}] 🎯 Starting mission (AUTO)...")
        ok = drone.set_mode("AUTO", timeout=5.0)
        if ok:
            self.logMessage.emit("INFO", f"[{drone_id}] ✅ Mission started!")
            if self._swarm_context is not None:
                with self._swarm_context._state_lock:
                    if drone_id not in self._swarm_context._mission_active:
                        self._swarm_context._mission_active[drone_id] = threading.Event()
                    self._swarm_context._mission_active[drone_id].clear()
        else:
            self.logMessage.emit("WARN", f"[{drone_id}] ⚠ Could not set AUTO mode")
        return ok

    def _mission_control_worker(self, action: str) -> None:
        import time
        try:
            connected = self._get_target_drones()
            if not connected:
                self.logMessage.emit("ERROR", "[MISSION] No target drones — select a drone first")
                return

            success_count = 0
            for drone_id, backend in connected:
                try:
                    if action == "start":
                        drone = getattr(backend, "_drone", None)
                        if not drone:
                            self.logMessage.emit("WARN", f"[{drone_id}] No drone object")
                            continue

                        uploaded = self._uploaded_mission_for(drone_id)
                        if not uploaded:
                            self.logMessage.emit(
                                "ERROR",
                                f"[{drone_id}] No uploaded mission. Press Upload Mission before Start Mission."
                            )
                            continue
                        if uploaded.get("mode") != self._mission_mode:
                            uploaded_mode = self._mission_mode_name(uploaded.get("mode"))
                            current_mode = self._mission_mode_name()
                            self.logMessage.emit(
                                "ERROR",
                                f"[{drone_id}] Uploaded mission is {uploaded_mode}, current mode is {current_mode}. Upload again before start."
                            )
                            continue
                        if uploaded.get("waypoint_count", 0) <= 0:
                            self.logMessage.emit(
                                "ERROR",
                                f"[{drone_id}] Uploaded mission has no waypoints. Upload a valid mission before start."
                            )
                            continue

                        # ARM → TAKEOFF → AUTO.MISSION
                        # ArduPilot: requires GUIDED mode before arming.
                        # PX4: accepts arm from any mode; GUIDED switch must be skipped
                        #      (PX4 ignores/rejects DO_SET_MODE GUIDED while disarmed).
                        is_px4 = getattr(drone._conn.telemetry, "autopilot", "") == "px4"

                        if drone.altitude < 2.0:
                            # 1. Switch to GUIDED — ArduPilot only
                            if not is_px4:
                                self.logMessage.emit("INFO", f"[{drone_id}] 🔧 Switching to GUIDED...")
                                if not drone.set_mode("GUIDED", timeout=5.0):
                                    self.logMessage.emit("WARN", f"[{drone_id}] ⚠ GUIDED mode failed, trying anyway...")

                            # 2. ARM
                            if not drone.armed:
                                self.logMessage.emit("INFO", f"[{drone_id}] 🔧 Arming...")
                                if not drone.arm(timeout=10.0):
                                    self.logMessage.emit("ERROR", f"[{drone_id}] ❌ Arm failed")
                                    continue
                                self.logMessage.emit("INFO", f"[{drone_id}] ✅ Armed")

                            # 3. TAKEOFF
                            if self._mission_mode == 1:
                                takeoff_alt = self._seed_altitude
                            elif self._mission_mode == 2:
                                takeoff_alt = self._solar_altitude
                            else:
                                takeoff_alt = self._coverage_altitude
                            self.logMessage.emit("INFO", f"[{drone_id}] 🚁 Taking off to {takeoff_alt}m...")
                            if not drone.takeoff(altitude=takeoff_alt, timeout=30.0):
                                self.logMessage.emit("WARN", f"[{drone_id}] ⚠ Takeoff timeout, continuing...")
                            else:
                                self.logMessage.emit("INFO", f"[{drone_id}] ✅ Airborne")
                                time.sleep(1.0)  # brief settle after takeoff

                        # 4. SET AUTO to start the uploaded mission
                        self.logMessage.emit("INFO", f"[{drone_id}] 🎯 Starting mission (AUTO)...")
                        ok = drone.set_mode("AUTO", timeout=5.0)
                        if ok:
                            success_count += 1
                            self.logMessage.emit("INFO", f"[{drone_id}] ✅ Mission started!")
                            # Mark mission active in SwarmContext
                            if self._swarm_context is not None:
                                with self._swarm_context._state_lock:
                                    if drone_id not in self._swarm_context._mission_active:
                                        self._swarm_context._mission_active[drone_id] = threading.Event()
                                    self._swarm_context._mission_active[drone_id].clear()
                        else:
                            self.logMessage.emit("WARN", f"[{drone_id}] ⚠ Could not set AUTO mode")

                    elif action == "pause":
                        drone = getattr(backend, "_drone", None)
                        ok = bool(drone and drone.set_mode("LOITER", timeout=5.0))
                        if ok:
                            success_count += 1
                        else:
                            self.logMessage.emit("WARN", f"[{drone_id}] Pause failed")

                    elif action == "abort":
                        backend.rtl()
                        success_count += 1
                        # Clear mission-active flag
                        if self._swarm_context is not None:
                            with self._swarm_context._state_lock:
                                self._swarm_context._mission_active.pop(drone_id, None)

                    else:
                        self.logMessage.emit("WARN", f"[{drone_id}] Unknown action: {action}")

                except Exception as e:
                    self.logMessage.emit("ERROR", f"[{drone_id}] Mission {action} error: {e}")

            self.logMessage.emit(
                "INFO",
                f"[MISSION] {action} command sent to {success_count}/{len(connected)} drone(s)"
            )
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] {action} worker error: {e}")
    
    @Slot()
    def uploadCoverageMission(self):
        """Upload coverage mission to selected drones (via AppState.missionTargets)."""
        with self._lock:
            if not self._coverage_waypoints:
                self.logMessage.emit("ERROR", "[MISSION] No waypoints to upload")
                self.missionUploadFinished.emit(False, "No waypoints to upload")
                return
            
            if not self._swarm_context:
                self.logMessage.emit("ERROR", "[MISSION] SwarmContext not available")
                self.missionUploadFinished.emit(False, "SwarmContext not available")
                return
            
            # Get selected drone IDs from AppState (QML singleton)
            # We'll call a method on swarm_context to get the list
            waypoints = list(self._coverage_waypoints)

        self._clear_uploaded_missions()
        self.missionUploadStarted.emit("coverage")
        
        # Run upload in background thread to avoid blocking UI
        threading.Thread(
            target=self._upload_mission_worker,
            args=(waypoints,),
            daemon=True
        ).start()
    
    def _upload_mission_worker(self, waypoints: List[Tuple[float, float, float]]) -> None:
        """Background worker for mission upload (runs in daemon thread)."""
        try:
            target_drones = self._get_target_drones()
            if not target_drones:
                self.logMessage.emit("ERROR", "[MISSION] No target drones found — select a drone first")
                return
            
            num_drones = len(target_drones)
            strategy = MultiDroneStrategy(self._multi_drone_strategy)
            
            # Distribute waypoints based on strategy
            if strategy == MultiDroneStrategy.FIELD_SPLITTING and len(self._boundary_points) >= 3:
                # Use field splitting (requires boundary)
                try:
                    boundary = FieldBoundary(self._boundary_points)
                    config = CoverageConfig(
                        pattern=CoveragePattern(self._coverage_pattern),
                        altitude=self._coverage_altitude,
                        line_spacing=self._coverage_line_spacing,
                        overlap=self._coverage_overlap,
                        speed=self._coverage_speed
                    )
                    distributed_waypoints = self._planner.split_field_into_zones(
                        boundary, num_drones, config
                    )
                    self.logMessage.emit(
                        "INFO",
                        f"[MISSION] Field split into {num_drones} zones"
                    )
                except Exception as e:
                    self.logMessage.emit("ERROR", f"[MISSION] Field splitting failed: {e}")
                    return
            else:
                # Use waypoint distribution strategies
                distributed_waypoints = self._planner.distribute_waypoints_for_swarm(
                    waypoints,
                    num_drones,
                    strategy,
                    formation_offset=self._formation_offset,
                    sequential_delay=self._sequential_delay
                )
            
            self.logMessage.emit(
                "INFO",
                f"[MISSION] Strategy: {strategy.name}, uploading to {num_drones} drone(s)..."
            )
            
            # Create mapping from actual drone_id to D1, D2, D3... format
            drone_id_mapping = {}
            for idx, (drone_id, _) in enumerate(target_drones):
                drone_id_mapping[drone_id] = f"D{idx + 1}"
            
            # Upload to each drone with its specific waypoints
            success_count = 0
            for drone_id, backend in target_drones:
                # Get waypoints for this drone using mapped ID
                mapped_id = drone_id_mapping[drone_id]
                drone_waypoints = distributed_waypoints.get(mapped_id, [])
                if not drone_waypoints:
                    self.logMessage.emit(
                        "WARN",
                        f"[{drone_id}] No waypoints assigned, skipping"
                    )
                    continue
                try:
                    # Get the drone's MAVLink connection
                    # backend._drone is GenericUAVModel (inherits from Drone)
                    # Drone has _conn attribute (MAVLinkConnection)
                    if not backend._drone or not hasattr(backend._drone, '_conn'):
                        self.logMessage.emit(
                            "WARN",
                            f"[{drone_id}] No connection available, skipping"
                        )
                        continue
                    
                    conn = backend._drone._conn
                    if not conn or not conn.connected:
                        self.logMessage.emit(
                            "WARN",
                            f"[{drone_id}] Connection not active, skipping"
                        )
                        continue
                    
                    # Create mission engine
                    mission = MissionEngine(conn)
                    mission.clear()
                    
                    # Add waypoints for this specific drone
                    for lat, lon, alt in drone_waypoints:
                        mission.add(Waypoint(
                            lat=lat,
                            lon=lon,
                            alt=alt,
                            speed=self._coverage_speed
                        ))
                    
                    # Upload (blocking call, but we're in a worker thread)
                    if not mission.upload():
                        self.logMessage.emit(
                            "ERROR",
                            f"[{drone_id}] ❌ Mission upload failed"
                        )
                        continue
                    
                    self.logMessage.emit(
                        "INFO",
                        f"[{drone_id}] ✅ Mission uploaded ({len(drone_waypoints)} waypoints)"
                    )
                    
                    self._mark_mission_uploaded(drone_id, 0, len(drone_waypoints))
                    # Auto-start: arm/takeoff/AUTO based on current drone state
                    started = self._auto_start_drone(drone_id, backend, 0)
                    if started:
                        success_count += 1
                    else:
                        success_count += 1  # Upload succeeded; start failure is non-fatal
                
                except Exception as e:
                    self.logMessage.emit(
                        "ERROR",
                        f"[{drone_id}] Upload error: {e}"
                    )
            
            if success_count > 0:
                self.logMessage.emit(
                    "INFO",
                    f"[MISSION] ✅ Upload complete: {success_count}/{len(target_drones)} drone(s) — mission auto-started."
                )
            else:
                self.logMessage.emit(
                    "ERROR",
                    "[MISSION] ❌ All uploads failed"
                )
        
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] Upload worker error: {e}")

    @Slot()
    def togglePreview(self):
        """Unified preview toggle - calls coverage or seeding based on mode."""
        if self._seeding_mode_enabled:
            self.toggleSeedingPreview()
        else:
            self.toggleCoveragePreview()
    
    @Slot()
    def toggleCoveragePreview(self):
        """Toggle coverage preview visibility on map."""
        with self._lock:
            self._preview_active = not self._preview_active
        
        # Emit signal outside lock
        if self._preview_active:
            self.coverageGenerated.emit()  # Show coverage
            self.logMessage.emit("INFO", "[MISSION] Preview enabled - coverage visible")
        else:
            self.coverageCleared.emit()  # Hide coverage
            self.logMessage.emit("INFO", "[MISSION] Preview disabled - coverage hidden")

    @Slot(result="QVariantList")
    def getCoverageWaypoints(self):
        """Return coverage waypoints as list of dicts for QML/JavaScript."""
        try:
            with self._lock:
                snapshot = list(self._coverage_waypoints)
            return [{"lat": float(lat), "lon": float(lon), "alt": float(alt)}
                    for lat, lon, alt in snapshot]
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] getCoverageWaypoints failed: {e}")
            return []

    @Slot(result="QVariantList")
    def getBoundaryPoints(self):
        """Return boundary points as list of dicts for QML/JavaScript."""
        try:
            with self._lock:
                snapshot = list(self._boundary_points)
            return [{"lat": float(lat), "lon": float(lon)} for lat, lon in snapshot]
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] getBoundaryPoints failed: {e}")
            return []

    @Slot(result="QVariantList")
    def getExclusionZones(self):
        """Return completed and in-progress exclusion zones for QML/JavaScript."""
        try:
            with self._lock:
                snap_zones = [list(z) for z in self._exclusion_zones]
                snap_current = list(self._current_exclusion_zone)
            zones = [
                [{"lat": float(lat), "lon": float(lon)} for lat, lon in zone]
                for zone in snap_zones
            ]
            if snap_current:
                zones.append([
                    {"lat": float(lat), "lon": float(lon)}
                    for lat, lon in snap_current
                ])
            return zones
        except Exception as e:
            self.logMessage.emit("ERROR", f"[MISSION] getExclusionZones failed: {e}")
            return []

    # ── Mission Mode Properties ───────────────────────────────────────────
    
    @Property(int, notify=fieldBoundaryChanged)
    def missionMode(self):
        """Mission mode: 0=Coverage, 1=Seeding, 2=Solar Inspection."""
        return self._mission_mode
    
    @missionMode.setter
    def missionMode(self, value):
        if self._mission_mode != value:
            self._mission_mode = value
            # Update legacy seedingModeEnabled for backward compatibility
            self._seeding_mode_enabled = (value == 1)
            self.fieldBoundaryChanged.emit()
            if value == 0:
                self.logMessage.emit("INFO", "[MISSION] 📐 Coverage mode enabled")
            elif value == 1:
                self.logMessage.emit("INFO", "[MISSION] 🌱 Seeding mode enabled")
            elif value == 2:
                self.logMessage.emit("INFO", "[MISSION] ☀ Solar Inspection mode enabled")
    
    @Property(bool, notify=fieldBoundaryChanged)
    def seedingModeEnabled(self):
        """Legacy property for backward compatibility. Use missionMode instead."""
        return self._seeding_mode_enabled
    
    @seedingModeEnabled.setter
    def seedingModeEnabled(self, value):
        # Map to missionMode: False=0 (Coverage), True=1 (Seeding)
        self.missionMode = 1 if value else 0
    
    # ── Seeding Mission Properties ────────────────────────────────────────
    
    @Property(float, notify=fieldBoundaryChanged)
    def seedSpacing(self):
        return self._seed_spacing
    
    @seedSpacing.setter
    def seedSpacing(self, value):
        self._seed_spacing = value
        self.fieldBoundaryChanged.emit()
    
    @Property(float, notify=fieldBoundaryChanged)
    def seedRowSpacing(self):
        return self._seed_row_spacing
    
    @seedRowSpacing.setter
    def seedRowSpacing(self, value):
        self._seed_row_spacing = value
        self.fieldBoundaryChanged.emit()
    
    @Property(float, notify=fieldBoundaryChanged)
    def seedAltitude(self):
        return self._seed_altitude
    
    @seedAltitude.setter
    def seedAltitude(self, value):
        self._seed_altitude = value
        self.fieldBoundaryChanged.emit()
    
    @Property(float, notify=fieldBoundaryChanged)
    def seedDropDuration(self):
        return self._seed_drop_duration
    
    @seedDropDuration.setter
    def seedDropDuration(self, value):
        self._seed_drop_duration = value
        self.fieldBoundaryChanged.emit()
    
    @Property(int, notify=fieldBoundaryChanged)
    def servoChannel(self):
        return self._servo_channel
    
    @servoChannel.setter
    def servoChannel(self, value):
        self._servo_channel = value
        self.fieldBoundaryChanged.emit()
    
    @Property(int, notify=fieldBoundaryChanged)
    def servoOpenPWM(self):
        return self._servo_open_pwm
    
    @servoOpenPWM.setter
    def servoOpenPWM(self, value):
        self._servo_open_pwm = value
        self.fieldBoundaryChanged.emit()
    
    @Property(int, notify=fieldBoundaryChanged)
    def servoClosePWM(self):
        return self._servo_close_pwm
    
    @servoClosePWM.setter
    def servoClosePWM(self, value):
        self._servo_close_pwm = value
        self.fieldBoundaryChanged.emit()
    
    @Property(int, notify=coverageGenerated)
    def seedingWaypointCount(self):
        return len(self._seeding_waypoints)
    
    @Property(int, notify=coverageGenerated)
    def seedingDropCount(self):
        return self._seeding_drop_count
    
    @Property(float, notify=coverageGenerated)
    def seedingDistance(self):
        return self._seeding_distance
    
    @Property(float, notify=coverageGenerated)
    def seedingTime(self):
        return self._seeding_time
    
    @Property(bool, notify=coverageGenerated)
    def seedingMissionActive(self):
        return len(self._seeding_waypoints) > 0
    
    # ── Seeding Mission Methods ───────────────────────────────────────────
    
    def _mission_param(self, params: dict, keys: List[str], default: Any) -> Any:
        for key in keys:
            if key in params and params[key] is not None:
                return params[key]
        return default

    def _mission_float_param(self, params: dict, keys: List[str], default: float) -> float:
        return float(self._mission_param(params, keys, default))

    def _mission_int_param(self, params: dict, keys: List[str], default: int) -> int:
        return int(self._mission_param(params, keys, default))

    def _mission_bool_param(self, params: dict, keys: List[str], default: bool) -> bool:
        value = self._mission_param(params, keys, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _boundary_point_from_mapping(self, point: dict) -> Tuple[float, float]:
        return float(point["lat"]), float(point["lon"])

    def _seeding_boundary_from_params(self, params: dict) -> FieldBoundary:
        if "boundary" in params:
            raw_points = params["boundary"]
        elif "fieldBoundary" in params:
            raw_points = params["fieldBoundary"]
        elif "boundaryPoints" in params:
            raw_points = params["boundaryPoints"]
        elif "points" in params:
            raw_points = params["points"]
        else:
            raw_points = [{"lat": lat, "lon": lon} for lat, lon in self._boundary_points]

        corners = [self._boundary_point_from_mapping(dict(point)) for point in raw_points]
        return FieldBoundary(corners=corners)

    def _seeding_calibration_from_params(self, params: dict) -> DispenserCalibration:
        tank_capacity_kg = self._mission_float_param(
            params, ["tankCapacityKg", "tank_capacity_kg"], 1.0
        )
        if "tankCapacityG" in params or "tank_capacity_g" in params:
            tank_capacity_kg = self._mission_float_param(
                params, ["tankCapacityG", "tank_capacity_g"], 1000.0
            ) / 1000.0

        return DispenserCalibration(
            seed_capacity=self._mission_int_param(
                params, ["seedCapacity", "seed_capacity"], 500
            ),
            seed_weight_g=self._mission_float_param(
                params, ["seedWeightG", "seed_weight_g", "seedWeight"], 0.05
            ),
            tank_capacity_kg=tank_capacity_kg,
            seeds_per_drop=self._mission_int_param(
                params, ["seedsPerDrop", "seeds_per_drop"], 1
            ),
            max_drop_rate=self._mission_float_param(
                params, ["maxDropRate", "max_drop_rate", "dispenseRate"], 2.0
            ),
        )

    @Slot("QVariantMap", result="QVariantMap")
    def generateSeedingPreview(self, params: dict):
        """Generate seeding mission preview data for QML without upload or execution."""
        try:
            params = dict(params or {})
            with self._lock:
                boundary = self._seeding_boundary_from_params(params)
                home_lat = self._home_lat if self._home_set else boundary.corners[0][0]
                home_lon = self._home_lon if self._home_set else boundary.corners[0][1]
                config = SeedingConfig(
                    seed_spacing=self._mission_float_param(
                        params, ["seedSpacing", "seed_spacing"], self._seed_spacing
                    ),
                    row_spacing=self._mission_float_param(
                        params, ["rowSpacing", "row_spacing"], self._seed_row_spacing
                    ),
                    altitude=self._mission_float_param(
                        params, ["altitude"], self._seed_altitude
                    ),
                    speed=self._mission_float_param(params, ["speed"], self._coverage_speed),
                    servo_channel=self._mission_int_param(
                        params, ["servoChannel", "servo_channel"], self._servo_channel
                    ),
                    servo_open_pwm=self._mission_int_param(
                        params, ["servoOpenPWM", "servo_open_pwm"], self._servo_open_pwm
                    ),
                    servo_close_pwm=self._mission_int_param(
                        params, ["servoClosePWM", "servo_close_pwm"], self._servo_close_pwm
                    ),
                    drop_duration=self._mission_float_param(
                        params, ["dropDuration", "drop_duration"], self._seed_drop_duration
                    ),
                )
                calibration = self._seeding_calibration_from_params(params)

            planner = SeedingMissionPlanner()
            planner.set_home_position(home_lat, home_lon)
            stored_exclusion_zones = [
                {
                    "points": [{"lat": lat, "lon": lon} for lat, lon in zone],
                    "name": f"exclusion-{idx + 1}",
                }
                for idx, zone in enumerate(self._exclusion_zones)
            ]
            if len(self._current_exclusion_zone) >= 3:
                stored_exclusion_zones.append(
                    {
                        "points": [
                            {"lat": lat, "lon": lon}
                            for lat, lon in self._current_exclusion_zone
                        ],
                        "name": f"exclusion-{len(stored_exclusion_zones) + 1}",
                    }
                )
            exclusion_zones = list(
                self._mission_param(
                    params,
                    ["exclusionZones", "exclusion_zones"],
                    stored_exclusion_zones,
                )
            )
            add_rtl = self._mission_bool_param(params, ["addRtl", "add_rtl"], True)
            battery_available = self._mission_float_param(
                params, ["batteryAvailablePercent", "battery_available_percent"], 100.0
            )

            preview = planner.generate_seeding_mission_with_preview(
                boundary,
                config,
                calibration=calibration,
                exclusion_zones=exclusion_zones,
                add_rtl=add_rtl,
            )
            validation = planner.validate_seeding_mission(
                boundary,
                config,
                calibration=calibration,
                exclusion_zones=exclusion_zones,
                battery_available_percent=battery_available,
            )

            result = preview.to_dict()
            result["valid"] = bool(validation["valid"])
            result["errors"] = list(validation["errors"])
            result["warnings"] = list(dict.fromkeys(result["warnings"] + validation["warnings"]))
            result["validation"] = validation
            with self._lock:
                self._last_seeding_preview = result
                self._seeding_waypoints = list(preview.waypoints) if result["valid"] else []
                # Only clear the uploaded missions cache when the preview
                # succeeds — preserve a valid upload if regeneration fails.
                if result["valid"]:
                    self._uploaded_missions.clear()
            self.seedingPreviewChanged.emit()
            return result
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SEEDING] Preview generation failed: {e}")
            return {
                "valid": False,
                "errors": [str(e)],
                "warnings": [],
                "waypoints": [],
                "flightPath": [],
                "flightRows": [],
                "dropPoints": [],
                "exclusionZones": [],
                "estimatedSeedUsage": 0,
                "estimatedSeedWeightKg": 0.0,
                "estimatedDuration": 0.0,
                "estimatedBatteryUsage": 0.0,
                "estimatedDistance": 0.0,
                "fieldArea": 0.0,
                "validation": {"valid": False, "errors": [str(e)], "warnings": []},
            }

    @Slot(result="QVariantMap")
    def getSeedingPreview(self):
        """Return the last computed seeding preview for main.qml to push to the map."""
        return dict(self._last_seeding_preview)

    @Slot()
    def generateSeedingMission(self):
        """Generate seeding mission with servo commands for seed drops."""
        try:
            with self._lock:
                if not self._home_set:
                    self.logMessage.emit("ERROR", "[SEEDING] Home not set")
                    return
                if len(self._boundary_points) < 3:
                    self.logMessage.emit("ERROR", "[SEEDING] Need ≥3 boundary points")
                    return
                
                # Create boundary and config
                boundary = FieldBoundary(corners=self._boundary_points)
                
                # Generate seeding mission
                self._seeding_waypoints = self._seeding_planner.plan_seeding_mission(
                    boundary=boundary,
                    seed_spacing=self._seed_spacing,
                    row_spacing=self._seed_row_spacing,
                    altitude=self._seed_altitude,
                    servo_channel=self._servo_channel,
                    servo_open_pwm=self._servo_open_pwm,
                    servo_close_pwm=self._servo_close_pwm,
                    drop_duration=self._seed_drop_duration,
                    add_rtl=True
                )
                
                # Calculate statistics
                seeding_config = SeedingConfig(
                    seed_spacing=self._seed_spacing,
                    row_spacing=self._seed_row_spacing,
                    altitude=self._seed_altitude,
                    servo_channel=self._servo_channel,
                    servo_open_pwm=self._servo_open_pwm,
                    servo_close_pwm=self._servo_close_pwm,
                    drop_duration=self._seed_drop_duration,
                    speed=self._coverage_speed
                )
                
                stats = self._seeding_planner.estimate_mission_stats(
                    boundary=boundary,
                    config=seeding_config
                )
                
                self._seeding_distance = stats["total_distance"]
                self._seeding_time = stats["estimated_time"]
                self._seeding_drop_count = stats["seed_count"]
            
            # Emit signals AFTER releasing lock
            self.coverageGenerated.emit()
            self.logMessage.emit(
                "INFO",
                f"[SEEDING] {len(self._seeding_waypoints)} WP, "
                f"{self._seeding_drop_count} seeds, "
                f"{self._seeding_distance/1000:.2f} km, "
                f"{self._seeding_time/60:.1f} min"
            )
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SEEDING] Generation failed: {e}")
    
    @Slot()
    def uploadSeedingMission(self):
        """Upload seeding mission to selected drones."""
        with self._lock:
            if not self._seeding_waypoints:
                self.logMessage.emit("ERROR", "[SEEDING] No waypoints to upload")
                self.missionUploadFinished.emit(False, "No seeding waypoints to upload")
                return
            
            if not self._swarm_context:
                self.logMessage.emit("ERROR", "[SEEDING] SwarmContext not available")
                self.missionUploadFinished.emit(False, "SwarmContext not available")
                return
            
            waypoints = list(self._seeding_waypoints)

        self._clear_uploaded_missions()
        self.missionUploadStarted.emit("seeding")
        
        # Run upload in background thread
        threading.Thread(
            target=self._upload_seeding_mission_worker,
            args=(waypoints,),
            daemon=True
        ).start()
    
    def _upload_seeding_mission_worker(self, waypoints: List[Waypoint]) -> None:
        """Background worker for seeding mission upload."""
        try:
            target_drones = self._get_target_drones()
            if not target_drones:
                self.logMessage.emit("ERROR", "[SEEDING] No target drones — select a drone first")
                return
            
            self.logMessage.emit(
                "INFO",
                f"[SEEDING] Uploading to {len(target_drones)} drone(s)..."
            )
            
            success_count = 0
            for drone_id, backend in target_drones:
                try:
                    if not backend._drone or not hasattr(backend._drone, '_conn'):
                        self.logMessage.emit(
                            "WARN",
                            f"[{drone_id}] No connection, skipping"
                        )
                        continue
                    
                    conn = backend._drone._conn
                    if not conn or not conn.connected:
                        self.logMessage.emit(
                            "WARN",
                            f"[{drone_id}] Connection not active, skipping"
                        )
                        continue
                    
                    # Create mission engine and upload
                    mission = MissionEngine(conn)
                    mission.clear()
                    
                    for wp in waypoints:
                        mission.add(wp)
                    
                    # Validate before upload
                    is_valid, errors = mission.validate()
                    if not is_valid:
                        self.logMessage.emit(
                            "ERROR",
                            f"[{drone_id}] ❌ Validation failed:"
                        )
                        for error in errors[:5]:  # Show first 5 errors
                            self.logMessage.emit("ERROR", f"  - {error}")
                        if len(errors) > 5:
                            self.logMessage.emit("ERROR", f"  ... and {len(errors)-5} more errors")
                        continue
                    
                    if not mission.upload(validate_first=False):  # Already validated
                        self.logMessage.emit(
                            "ERROR",
                            f"[{drone_id}] ❌ Upload failed (protocol error)"
                        )
                        continue
                    
                    self.logMessage.emit(
                        "INFO",
                        f"[{drone_id}] ✅ Seeding mission uploaded ({len(waypoints)} WP)"
                    )
                    
                    self._mark_mission_uploaded(drone_id, 1, len(waypoints))
                    # Auto-start: arm/takeoff/AUTO based on current drone state
                    self._auto_start_drone(drone_id, backend, 1)
                    success_count += 1
                
                except Exception as e:
                    self.logMessage.emit("ERROR", f"[{drone_id}] Upload error: {e}")
            
            if success_count > 0:
                self.logMessage.emit(
                    "INFO",
                    f"[SEEDING] ✅ Upload complete: {success_count}/{len(target_drones)} drone(s) — mission auto-started."
                )
            else:
                self.logMessage.emit("ERROR", "[SEEDING] ❌ All uploads failed")
        
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SEEDING] Worker error: {e}")
    
    @Slot()
    def toggleSeedingPreview(self):
        """Toggle seeding mission preview on map."""
        with self._lock:
            self._seeding_preview_active = not self._seeding_preview_active
        
        if self._seeding_preview_active:
            self.coverageGenerated.emit()
            self.logMessage.emit("INFO", "[SEEDING] Preview enabled")
        else:
            self.coverageCleared.emit()
            self.logMessage.emit("INFO", "[SEEDING] Preview disabled")
    
    @Slot(result="QVariantList")
    def getSeedingWaypoints(self):
        """Return seeding waypoints for QML/JavaScript map display.
        
        Returns NAV waypoints with 'isSeedPoint' flag for visualization.
        """
        try:
            with self._lock:
                waypoints = []
                for wp in self._seeding_waypoints:
                    if wp.cmd == 16:  # MAV_CMD_NAV_WAYPOINT only
                        waypoints.append({
                            "lat": float(wp.lat),
                            "lon": float(wp.lon),
                            "alt": float(wp.alt),
                            "isSeedPoint": wp.hold > 0.0  # Seed points have hold time
                        })
                return waypoints
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SEEDING] getSeedingWaypoints failed: {e}")
            return []

    # ── Solar Inspection Properties ────────────────────────────────────────
    
    @Property(bool, notify=solarStatsChanged)
    def solarInspectionActive(self):
        return self._mission_mode == 2 and len(self._solar_panel_rows) > 0
    
    @Property(int, notify=solarPanelRowsChanged)
    def solarPanelRowCount(self):
        return len(self._solar_panel_rows)
    
    @Property("QVariantList", notify=solarPanelRowsChanged)
    def solarPanelRows(self):
        """Return list of solar panel rows for QML/Map display."""
        # Convert to format expected by MapView JavaScript
        rows = []
        for row in self._solar_panel_rows:
            rows.append({
                "start": {"lat": row["start_lat"], "lon": row["start_lon"]},
                "end": {"lat": row["end_lat"], "lon": row["end_lon"]},
                "length": row["length"],
                "panelCount": 0  # TODO: Calculate based on panel size
            })
        return rows
    
    @Property(float, notify=solarStatsChanged)
    def solarAltitude(self):
        return self._solar_altitude
    
    @solarAltitude.setter
    def solarAltitude(self, value):
        if self._solar_altitude != value:
            self._solar_altitude = value
            self.solarStatsChanged.emit()
    
    @Property(float, notify=solarStatsChanged)
    def solarGimbalPitch(self):
        return self._solar_gimbal_pitch
    
    @solarGimbalPitch.setter
    def solarGimbalPitch(self, value):
        if self._solar_gimbal_pitch != value:
            self._solar_gimbal_pitch = value
            self.solarStatsChanged.emit()
    
    @Property(float, notify=solarStatsChanged)
    def solarTriggerDistance(self):
        return self._solar_trigger_distance
    
    @solarTriggerDistance.setter
    def solarTriggerDistance(self, value):
        if self._solar_trigger_distance != value:
            self._solar_trigger_distance = value
            self.solarStatsChanged.emit()
    
    @Property(float, notify=solarStatsChanged)
    def solarOverlap(self):
        return self._solar_overlap
    
    @solarOverlap.setter
    def solarOverlap(self, value):
        if self._solar_overlap != value:
            self._solar_overlap = value
            self.solarStatsChanged.emit()
    
    @Property(float, notify=solarStatsChanged)
    def solarCoverageArea(self):
        return self._solar_coverage_area
    
    @Property(float, notify=solarStatsChanged)
    def solarMissionTime(self):
        return self._solar_mission_time
    
    @Property(int, notify=solarStatsChanged)
    def solarWaypointCount(self):
        return self._solar_waypoint_count
    
    @Property(int, notify=solarStatsChanged)
    def solarPhotoCount(self):
        return self._solar_photo_count
    
    # ── Solar Inspection Methods ───────────────────────────────────────────
    
    @Slot()
    def startDrawingSolarRows(self):
        """QML alias for starting solar row drawing."""
        self.startAddingSolarRow()

    @Slot()
    def clearSolarRows(self):
        """QML alias for clearing drawn solar rows."""
        self.clearSolarPanelRows()

    @Slot()
    def startAddingSolarRow(self):
        """Start interactive solar row addition on map."""
        with self._lock:
            self._commit_current_exclusion_zone_locked()
            self._adding_solar_row = True
            self._solar_row_start_lat = 0.0
            self._solar_row_start_lon = 0.0
            self._drawing_mode = False
            self._exclusion_zone_drawing = False
            self._mission_waypoint_mode = False
            self._drawing_timeout_timer.stop()
        self.drawingModeChanged.emit(False)
        self.missionWaypointModeChanged.emit(False)
        self.fieldBoundaryChanged.emit()
        self.solarRowDrawingModeChanged.emit(True)
        self.logMessage.emit("INFO", "[SOLAR] Click two points on map to define panel row")
    
    @Slot(float, float)
    def addSolarRowPoint(self, lat: float, lon: float):
        """Handle a click point for solar row drawing."""
        try:
            if self._solar_row_start_lat == 0.0 and self._solar_row_start_lon == 0.0:
                # First click - store start point
                self._solar_row_start_lat = lat
                self._solar_row_start_lon = lon
                self.logMessage.emit("INFO", "[SOLAR] Start point set, click end point")
            else:
                # Second click - complete the row
                self.addSolarRow(self._solar_row_start_lat, self._solar_row_start_lon, lat, lon)
                # Reset for next row but keep drawing mode active
                self._solar_row_start_lat = 0.0
                self._solar_row_start_lon = 0.0
                self.logMessage.emit("INFO", "[SOLAR] Row added. Click to add another row, or press ESC to finish")
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SOLAR] addSolarRowPoint failed: {e}")
    
    @Slot()
    def cancelSolarRowDrawing(self):
        """Cancel solar row drawing mode. Lock-free for UI responsiveness."""
        try:
            # No lock needed - these are simple assignments that Qt handles atomically
            self._adding_solar_row = False
            self._solar_row_start_lat = 0.0
            self._solar_row_start_lon = 0.0
            self.solarRowDrawingModeChanged.emit(False)
            self.logMessage.emit("INFO", "[SOLAR] ❌ Solar row drawing cancelled")
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SOLAR] cancelSolarRowDrawing error: {e}")
    
    @Property(bool, notify=solarRowDrawingModeChanged)
    def addingSolarRow(self):
        """Return whether solar row drawing mode is active."""
        return self._adding_solar_row
    
    @Slot(float, float, float, float)
    def addSolarRow(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float):
        """Add a solar panel row defined by start and end coordinates."""
        try:
            # Calculate row length
            R = 6371000  # Earth radius in meters
            dlat = math.radians(end_lat - start_lat)
            dlon = math.radians(end_lon - start_lon)
            a = (math.sin(dlat / 2) ** 2 +
                 math.cos(math.radians(start_lat)) * math.cos(math.radians(end_lat)) *
                 math.sin(dlon / 2) ** 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            length = R * c
            
            row = {
                "start_lat": start_lat,
                "start_lon": start_lon,
                "end_lat": end_lat,
                "end_lon": end_lon,
                "length": length
            }
            
            with self._lock:
                self._solar_panel_rows.append(row)
                self._adding_solar_row = False
            
            self.solarPanelRowsChanged.emit()
            self.logMessage.emit("INFO", f"[SOLAR] Added row {len(self._solar_panel_rows)} ({length:.1f}m)")
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SOLAR] Failed to add row: {e}")
    
    @Slot()
    def clearSolarPanelRows(self):
        """Clear all solar panel rows and map visualization."""
        try:
            with self._lock:
                self._solar_panel_rows.clear()
                self._solar_waypoints.clear()
                self._solar_coverage_area = 0.0
                self._solar_mission_time = 0.0
                self._solar_waypoint_count = 0
                self._solar_photo_count = 0
            
            # Emit signals to update UI and map
            self.solarPanelRowsChanged.emit()
            self.solarStatsChanged.emit()
            self.logMessage.emit("INFO", "[SOLAR] Cleared all panel rows")
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SOLAR] clearSolarPanelRows failed: {e}")
    
    @Slot(int)
    def removeSolarRow(self, index: int):
        """Remove a solar panel row by index."""
        try:
            with self._lock:
                if 0 <= index < len(self._solar_panel_rows):
                    self._solar_panel_rows.pop(index)
                    self.solarPanelRowsChanged.emit()
                    self.logMessage.emit("INFO", f"[SOLAR] Removed row {index + 1}")
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SOLAR] Failed to remove row: {e}")

    def _solar_param(self, params: dict, keys: List[str], default: Any) -> Any:
        """Read a QML params value by accepting camelCase and snake_case names."""
        for key in keys:
            if key in params and params[key] is not None:
                return params[key]
        return default

    def _solar_float_param(self, params: dict, keys: List[str], default: float) -> float:
        return float(self._solar_param(params, keys, default))

    def _solar_bool_param(self, params: dict, keys: List[str], default: bool) -> bool:
        value = self._solar_param(params, keys, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _solar_point_from_params(self, row: dict, prefix: str) -> Tuple[float, float]:
        nested = row.get(prefix)
        if isinstance(nested, dict):
            return float(nested["lat"]), float(nested["lon"])
        return float(row[f"{prefix}_lat"]), float(row[f"{prefix}_lon"])

    def _solar_preview_rows_from_params(self, params: dict):
        from skymeshx.control.solar_inspection import PanelRow

        if "rows" in params:
            raw_rows = params["rows"]
        elif "panelRows" in params:
            raw_rows = params["panelRows"]
        else:
            raw_rows = list(self._solar_panel_rows)

        rows = []
        for raw_row in raw_rows:
            row = dict(raw_row)
            start = self._solar_point_from_params(row, "start")
            end = self._solar_point_from_params(row, "end")
            width = float(row.get("width", 2.0))
            rows.append(PanelRow(start=start, end=end, width=width))
        return rows

    @Slot("QVariantMap", result="QVariantMap")
    def generateSolarPreview(self, params: dict):
        """Generate solar mission preview data for QML without upload or execution."""
        try:
            from skymeshx.control.solar_inspection import (
                SolarParkInspectionPlanner,
                InspectionConfig,
            )

            params = dict(params or {})
            with self._lock:
                rows = self._solar_preview_rows_from_params(params)
                altitude = self._solar_float_param(params, ["altitude"], self._solar_altitude)
                gimbal_pitch = self._solar_float_param(
                    params, ["gimbalPitch", "gimbal_pitch", "gimbalAngle", "cameraAngle"], self._solar_gimbal_pitch
                )
                speed = self._solar_float_param(params, ["speed"], 3.0)
                trigger_distance = self._solar_float_param(
                    params, ["triggerDistance", "trigger_distance"], self._solar_trigger_distance
                )
                trigger_time = self._solar_float_param(
                    params, ["triggerTime", "trigger_time"], 0.0
                )
                if trigger_distance <= 0 and trigger_time > 0:
                    trigger_distance = speed * trigger_time
                overlap = self._solar_float_param(
                    params,
                    ["overlap", "forwardOverlap", "forward_overlap", "sideOverlap", "side_overlap"],
                    self._solar_overlap,
                )
                if overlap > 1.0:
                    overlap = overlap / 100.0

            config = InspectionConfig(
                altitude=altitude,
                gimbal_pitch=gimbal_pitch,
                trigger_distance=trigger_distance,
                overlap=overlap,
                speed=speed,
                camera_fov_horizontal=self._solar_float_param(
                    params, ["cameraHFov", "cameraHFOV", "camera_hfov", "cameraFovHorizontal", "camera_fov_horizontal"], 60.0
                ),
                camera_fov_vertical=self._solar_float_param(
                    params, ["cameraVFov", "cameraVFOV", "camera_vfov", "cameraFovVertical", "camera_fov_vertical"], 45.0
                ),
            )
            thermal_enabled = self._solar_bool_param(
                params, ["thermalEnabled", "thermal_enabled"], False
            )
            add_rtl = self._solar_bool_param(params, ["addRtl", "addRTL", "add_rtl"], True)
            battery_available = self._solar_float_param(
                params, ["batteryAvailablePercent", "battery_available_percent"], 100.0
            )

            planner = SolarParkInspectionPlanner()
            preview = planner.generate_solar_mission_with_preview(
                rows,
                config,
                add_rtl=add_rtl,
                thermal_enabled=thermal_enabled,
            )
            validation = planner.validate_solar_mission(
                rows,
                config,
                thermal_enabled=thermal_enabled,
                battery_available_percent=battery_available,
            )

            result = preview.to_dict()
            result["valid"] = bool(validation["valid"])
            result["errors"] = list(validation["errors"])
            result["warnings"] = list(dict.fromkeys(result["warnings"] + validation["warnings"]))
            result["validation"] = validation
            with self._lock:
                self._last_solar_preview = result
                self._solar_waypoints = list(preview.waypoints) if result["valid"] else []
                # Only clear the uploaded missions cache when the preview succeeds.
                if result["valid"]:
                    self._uploaded_missions.clear()
            self.solarPreviewChanged.emit()
            return result
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SOLAR] Preview generation failed: {e}")
            return {
                "valid": False,
                "errors": [str(e)],
                "warnings": [],
                "waypoints": [],
                "triggerPoints": [],
                "flightPath": [],
                "estimatedDuration": 0.0,
                "estimatedBatteryUsage": 0.0,
                "totalImages": 0,
                "storageRequired": 0.0,
                "coverageArea": 0.0,
                "validation": {"valid": False, "errors": [str(e)], "warnings": []},
            }
    
    @Slot(result="QVariantMap")
    def getSolarPreview(self):
        """Return the last computed solar preview for main.qml to push to the map."""
        return dict(self._last_solar_preview)

    @Slot()
    def generateSolarInspection(self):
        """Generate solar inspection mission waypoints."""
        try:
            from skymeshx.control.solar_inspection import (
                SolarParkInspectionPlanner,
                PanelRow,
                InspectionConfig
            )
            
            with self._lock:
                if len(self._solar_panel_rows) == 0:
                    self.logMessage.emit("ERROR", "[SOLAR] No panel rows defined")
                    return
                
                planner = SolarParkInspectionPlanner()
                
                # Convert UI rows to PanelRow objects
                rows = [
                    PanelRow(
                        start=(row['start_lat'], row['start_lon']),
                        end=(row['end_lat'], row['end_lon'])
                    )
                    for row in self._solar_panel_rows
                ]
                
                # Create config
                config = InspectionConfig(
                    altitude=self._solar_altitude,
                    gimbal_pitch=self._solar_gimbal_pitch,
                    trigger_distance=self._solar_trigger_distance,
                    overlap=self._solar_overlap
                )
                
                # Generate waypoints
                self._solar_waypoints = planner.plan_inspection(rows, config, add_rtl=True)
                
                # Update stats
                self._solar_waypoint_count = len(self._solar_waypoints)
                self._solar_photo_count = sum(1 for wp in self._solar_waypoints if wp.cmd == 203)
                self._solar_coverage_area = planner.calculate_coverage_area(rows, config)
                self._solar_mission_time = planner.estimate_mission_time(rows, config)
            
            # Emit signals AFTER releasing lock
            self.solarStatsChanged.emit()
            self.coverageGenerated.emit()
            self.logMessage.emit(
                "INFO",
                f"[SOLAR] {self._solar_waypoint_count} WP, "
                f"{self._solar_photo_count} photos, "
                f"{self._solar_coverage_area:.1f} m², "
                f"{self._solar_mission_time/60:.1f} min"
            )
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SOLAR] Generation failed: {e}")
            import traceback
            traceback.print_exc()
    
    @Slot(result="QVariantList")
    def getSolarWaypoints(self):
        """Return solar inspection waypoints for QML/JavaScript map display."""
        try:
            with self._lock:
                waypoints = []
                for wp in self._solar_waypoints:
                    if wp.cmd == 16:  # MAV_CMD_NAV_WAYPOINT only
                        waypoints.append({
                            "lat": float(wp.lat),
                            "lon": float(wp.lon),
                            "alt": float(wp.alt),
                            "isPhotoPoint": False
                        })
                    elif wp.cmd == 203:  # MAV_CMD_DO_DIGICAM_CONTROL (photo trigger)
                        # Photo triggers use previous waypoint's position
                        if waypoints:
                            waypoints[-1]["isPhotoPoint"] = True
                return waypoints
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SOLAR] getSolarWaypoints failed: {e}")
            return []
    
    @Slot()
    def uploadSolarMission(self):
        """Upload solar inspection mission to selected drones."""
        with self._lock:
            if not self._solar_waypoints:
                self.logMessage.emit("ERROR", "[SOLAR] No waypoints to upload")
                self.missionUploadFinished.emit(False, "No solar waypoints to upload")
                return
            
            if not self._swarm_context:
                self.logMessage.emit("ERROR", "[SOLAR] SwarmContext not available")
                self.missionUploadFinished.emit(False, "SwarmContext not available")
                return
            
            waypoints = list(self._solar_waypoints)

        self._clear_uploaded_missions()
        self.missionUploadStarted.emit("solar")
        
        # Run upload in background thread
        threading.Thread(
            target=self._upload_solar_mission_worker,
            args=(waypoints,),
            daemon=True
        ).start()
    
    def _upload_solar_mission_worker(self, waypoints: List[Waypoint]) -> None:
        """Background worker for solar mission upload."""
        try:
            target_drones = self._get_target_drones()
            if not target_drones:
                self.logMessage.emit("ERROR", "[SOLAR] No target drones — select a drone first")
                return
            
            self.logMessage.emit(
                "INFO",
                f"[SOLAR] Uploading to {len(target_drones)} drone(s)..."
            )
            
            success_count = 0
            for drone_id, backend in target_drones:
                try:
                    if not backend._drone or not hasattr(backend._drone, '_conn'):
                        self.logMessage.emit(
                            "WARN",
                            f"[{drone_id}] No connection, skipping"
                        )
                        continue
                    
                    conn = backend._drone._conn
                    if not conn or not conn.connected:
                        self.logMessage.emit(
                            "WARN",
                            f"[{drone_id}] Connection not active, skipping"
                        )
                        continue
                    
                    # Create mission engine and upload
                    mission = MissionEngine(conn)
                    mission.clear()
                    
                    for wp in waypoints:
                        mission.add(wp)
                    
                    # Validate before upload
                    is_valid, errors = mission.validate()
                    if not is_valid:
                        self.logMessage.emit(
                            "ERROR",
                            f"[{drone_id}] ❌ Validation failed:"
                        )
                        for error in errors[:5]:
                            self.logMessage.emit("ERROR", f"  - {error}")
                        if len(errors) > 5:
                            self.logMessage.emit("ERROR", f"  ... and {len(errors)-5} more errors")
                        continue
                    
                    if not mission.upload(validate_first=False):
                        self.logMessage.emit(
                            "ERROR",
                            f"[{drone_id}] ❌ Upload failed (protocol error)"
                        )
                        continue
                    
                    self.logMessage.emit(
                        "INFO",
                        f"[{drone_id}] ✅ {len(waypoints)} waypoints uploaded"
                    )
                    
                    self._mark_mission_uploaded(drone_id, 2, len(waypoints))
                    # Auto-start: arm/takeoff/AUTO based on current drone state
                    self._auto_start_drone(drone_id, backend, 2)
                    success_count += 1
                
                except Exception as e:
                    self.logMessage.emit("ERROR", f"[{drone_id}] Upload error: {e}")
            
            if success_count > 0:
                self.logMessage.emit(
                    "INFO",
                    f"[SOLAR] ✅ Upload complete: {success_count}/{len(target_drones)} drone(s) — mission auto-started."
                )
            else:
                self.logMessage.emit("ERROR", "[SOLAR] ❌ All uploads failed")
        
        except Exception as e:
            self.logMessage.emit("ERROR", f"[SOLAR] Worker error: {e}")

    def _calculate_distance(self) -> float:
        if len(self._coverage_waypoints) < 2:
            return 0.0
        
        total = 0.0
        for i in range(len(self._coverage_waypoints) - 1):
            lat1, lon1, _ = self._coverage_waypoints[i]
            lat2, lon2, _ = self._coverage_waypoints[i + 1]
            
            R = 6371000
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            
            a = (math.sin(dlat / 2) ** 2 +
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                 math.sin(dlon / 2) ** 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            total += R * c
        
        return total

# Made with Bob
