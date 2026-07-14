# API Reference - Quick Guide

Complete API reference for the SkyMeshX Platform.

## High-Level SDK

### Drone Class

```python
from skymeshx import Drone

drone = Drone(connection_string, drone_id="drone", log_dir="logs", auto_log=True)
```

**Connection:**
- `connect(timeout=15.0) -> bool`
- `disconnect()`
- `connected -> bool`

**Commands:**
- `arm(timeout=10.0, force=False) -> bool`
- `disarm(timeout=5.0, force=False) -> bool`
- `set_mode(mode, timeout=5.0) -> bool`
- `takeoff(altitude=10.0, timeout=30.0) -> bool`
- `land(timeout=60.0) -> bool`
- `rtl()`
- `goto(lat, lon, alt, timeout=60.0) -> bool`
- `set_speed(speed_ms)`
- `wait(seconds)`
- `wait_for_landing(timeout=300.0) -> bool`

**Properties:**
- `telemetry -> TelemetryState`
- `lat, lon, altitude, heading, armed, mode, battery, groundspeed, position`

**Mission:**
- `mission -> MissionEngine`
- `run_mission(waypoints, wait=True, timeout=600.0) -> bool`

**Data:**
- `store -> TelemetryStore`
- `get_history(last_n=100) -> list`
- `export_csv() -> str`

**Events:**
- `on(event, callback)` - Register event handler
- `off(event, callback)` - Unregister event handler

### Swarm Class

```python
from skymeshx import Swarm

swarm = Swarm(log_dir="logs", auto_log=True)
```

**Management:**
- `add(drone_id, connection_string) -> Drone`
- `remove(drone_id)`
- `get(drone_id) -> Drone`
- `drones -> List[Drone]`
- `count -> int`

**Connection:**
- `connect_all(timeout=15.0) -> Dict[str, bool]`
- `disconnect_all()`

**Commands:**
- `arm_all(force=False)`
- `disarm_all(force=False)`
- `takeoff_all(altitude=10.0)`
- `land_all()`
- `rtl_all()`
- `set_mode_all(mode)`
- `set_speed_all(speed_ms)`

**Formation:**
- `formation(shape, spacing=5.0, leader=None)` - Shapes: "line", "v", "grid", "circle", "wedge"
- `start_follow(shape="line", spacing=5.0, leader=None, update_hz=2.0)`
- `stop_follow()`

**Data:**
- `telemetry_all() -> Dict[str, dict]`

**Events:**
- `on(event, callback)`

## Core Layer

### MAVLinkConnection

```python
from skymeshx.core.connection import MAVLinkConnection

conn = MAVLinkConnection(connection_string, source_system=255, auto_reconnect=True)
```

**Methods:** Same as Drone class commands, plus:
- `send_raw(msg_type, **kwargs)` - Send raw MAVLink message
- `validate_connection_string(s) -> str` - Validate connection string

**Events:**
- "connected", "disconnected", "telemetry", "message", "statustext", "armed", "mode", "command_ack"

### StateMachine

```python
from skymeshx.core.fsm import StateMachine, DroneState

fsm = StateMachine(drone_id="drone")
```

**States:**
- IDLE, ARMING, ARMED, TAKEOFF, FLYING, MISSION, RTL, LANDING, EMERGENCY, ERROR

**Methods:**
- `transition(new_state, force=False) -> bool`
- `reset()` - Force to IDLE
- `emergency()` - Force to EMERGENCY
- `on_transition(callback)`
- `on_rejection(callback)`
- `history(last_n=20) -> List[dict]`

**Properties:**
- `state, previous, is_airborne, is_safe, can_arm, can_takeoff, can_mission, rejected_count`

### TelemetryState

```python
from skymeshx.core.telemetry import TelemetryState

tel = TelemetryState()
```

**Fields:**
- GPS: lat, lon, alt, alt_rel, gps_fix, satellites
- Attitude: roll, pitch, yaw
- Velocity: vx, vy, vz, airspeed, groundspeed, climb
- Battery: battery_v, battery_pct, current_a
- Status: armed, flight_mode, autopilot, vehicle_type, system_status

**Methods:**
- `update(**kwargs)` - Thread-safe update
- `snapshot() -> dict` - Get all fields

**Properties:**
- `is_stale -> bool` - No heartbeat for >5s
- `has_gps -> bool` - GPS fix >= 3

## Control Layer

### MissionEngine

```python
from skymeshx.control.mission import MissionEngine, Waypoint

mission = MissionEngine(connection)
```

**Building:**
- `clear()`
- `add(wp: Waypoint)`
- `from_list(points: List[dict])`

**Execution:**
- `upload() -> bool` - **BLOCKING**, use worker thread
- `start() -> bool`
- `pause() -> bool`
- `resume() -> bool`
- `abort() -> bool`
- `wait_done(timeout=600.0) -> bool`

**Callbacks:**
- `on_waypoint_reached(callback)`
- `on_mission_done(callback)`

### Waypoint

```python
from skymeshx.control.mission import Waypoint

wp = Waypoint(lat, lon, alt=10.0, speed=None, hold=0.0, cmd=16, radius=2.0)
```

## Safety Layer

### APFSafetyFilter

```python
from skymeshx.safety.apf import APFSafetyFilter, Pose3D

apf = APFSafetyFilter(
    min_separation=2.0,
    max_speed=3.0,
    geofence_radius=50.0,
    geofence_alt=(1.0, 30.0),
    repulsion_gain=2.0,
    attraction_gain=1.0,
    obstacle_radius=4.0,
    dt=0.05
)
```

**Methods:**
- `filter(positions: Dict[str, Pose3D], desired: Dict[str, Pose3D]) -> Dict[str, Pose3D]`
- `check_separation(positions) -> List[Tuple[str, str, float]]`
- `add_obstacle(x, y, z=0.0)`
- `clear_obstacles()`

### Pose3D

```python
from skymeshx.safety.apf import Pose3D

pos = Pose3D(x=0.0, y=0.0, z=0.0)  # x=North, y=East, z=altitude (positive up)
```

**Methods:**
- `dist(other) -> float` - 3D distance
- `dist_2d(other) -> float` - 2D distance
- `norm() -> float` - Magnitude
- `normalized() -> Pose3D` - Unit vector
- `clamp(max_norm) -> Pose3D` - Limit magnitude

**Operators:**
- `pos1 + pos2` - Addition
- `pos * scalar` - Multiplication

### Geofence

```python
from skymeshx.safety.apf import Geofence

fence = Geofence(origin_x=0.0, origin_y=0.0, radius=50.0, alt_min=1.0, alt_max=30.0)
```

**Methods:**
- `contains(p: Pose3D) -> bool`
- `clip(p: Pose3D) -> Pose3D`

### APFFilterLoop

```python
from skymeshx.safety.apf import APFFilterLoop

loop = APFFilterLoop(apf, get_positions, get_desired, on_safe, hz=20.0, on_violation=None)
```

**Methods:**
- `start()` - Start background thread
- `stop()` - Stop background thread

## ROS2 Integration

### PX4Bridge

```python
from skymeshx.ros.context import acquire_ros, release_ros
from skymeshx.ros.px4_bridge import PX4Bridge

acquire_ros()
try:
    bridge = PX4Bridge(namespace="/px4_1")
    bridge.arm()
    bridge.takeoff(10.0)
finally:
    release_ros()
```

**Methods:**
- `arm() -> bool`
- `disarm() -> bool`
- `takeoff(altitude) -> bool`
- `land() -> bool`
- `goto_local(x, y, z) -> bool` - Local NED
- `goto_global(lat, lon, alt) -> bool` - GPS

**Frame Conversions:**
- `ned_to_enu(x, y, z) -> (x, y, z)` - NED to ENU
- `enu_to_ned(x, y, z) -> (x, y, z)` - ENU to NED
- `frd_to_flu(x, y, z) -> (x, y, z)` - FRD to FLU

### BagRecorder

```python
from skymeshx.ros.bag_recorder import BagRecorder

recorder = BagRecorder(output_dir="bags")
```

**Methods:**
- `start_recording(topics: List[str], bag_name: str)`
- `stop_recording()`
- `is_recording() -> bool`

## Formations

### formation_offsets

```python
from skymeshx.sdk.formations import formation_offsets, SHAPES

offsets = formation_offsets(shape, count, spacing)
# Returns: List[(north_m, east_m)]
```

**Shapes:**
- "line" - Followers trail behind
- "v" - 60° V formation
- "grid" - Square grid
- "circle" - Ring around leader
- "wedge" - Tight V formation

## Data Collection

### TelemetryLogger

```python
from skymeshx.data.logger import TelemetryLogger

logger = TelemetryLogger(log_dir="logs")
logger.start(drone_id="D1")
logger.log(telemetry_dict)
logger.stop()
```

### TelemetryStore

```python
from skymeshx.data.store import TelemetryStore

store = TelemetryStore()
store.push(drone_id, telemetry_dict)
history = store.get(drone_id, last_n=100)
csv = store.export_csv(drone_id)
```

## Simulation

### SITLInstance

```python
from skymeshx.simulation.sitl import SITLInstance

sitl = SITLInstance(
    vehicle="copter",
    home=(48.137, 11.575, 0, 0),
    instance=0,
    speedup=1
)
sitl.start()
connection_string = sitl.connection_string  # "tcp:127.0.0.1:5762"
sitl.stop()
```

### PX4Gazebo

```python
from skymeshx.simulation.px4_gazebo import PX4Gazebo

sim = PX4Gazebo(
    model="iris",
    world="empty",
    instance=0,
    headless=False
)
sim.start()
# ... use ROS2 bridge ...
sim.stop()
```

## Lazy Imports

```python
from skymeshx import get_backend, get_sitl, get_coordinator, get_swarm_commander

# Get autopilot backend
backend = get_backend("mavlink")  # or "ardupilot", "px4"

# Get SITL instance
sitl = get_sitl(vehicle="copter", instance=0)

# Get coordinator model
coordinator = get_coordinator()

# Get LLM swarm commander
commander = get_swarm_commander()
```

## Constants

### Default Ports

```python
# ArduPilot SITL
5762  # Raw SITL (default)
5760  # MAVProxy-aggregated

# PX4 SITL
14540  # MAVLink (instance 0)
14541  # MAVLink (instance 1)

# Standard GCS
14550  # UDP
```

### MAVLink Modes

**ArduPilot:**
- STABILIZE, ACRO, ALT_HOLD, AUTO, GUIDED, LOITER, RTL, CIRCLE, LAND

**PX4:**
- MANUAL, ALTCTL, POSCTL, AUTO, ACRO, OFFBOARD, STABILIZED

## Error Handling

All methods return `bool` for success/failure. No exceptions for normal operation failures.

**Connection failures:**
```python
if not drone.connect():
    print("Connection failed")
```

**Command failures:**
```python
if not drone.arm():
    print("Arm failed")
```

**Mission failures:**
```python
if not mission.upload():
    print("Upload failed")
    if conn.last_nack:
        cmd, result = conn.last_nack
        print(f"Last NACK: {cmd} → {result}")
```

## Thread Safety

**Thread-safe:**
- All `TelemetryState` operations
- All `StateMachine` operations
- All `MAVLinkConnection` operations
- Swarm `*_all()` methods

**NOT thread-safe:**
- `MissionEngine.upload()` - use worker thread
- Multiple simultaneous `formation()` calls

## See Also

- [API Overview](overview.md) - Architecture and concepts
- [Core API](core.md) - Low-level connection and state
- [Control API](control.md) - Mission planning
- [Safety API](safety.md) - Collision avoidance
- [Swarm Coordination](../features/swarm-coordination.md) - Multi-drone features

---

## SITLContext

QML-Bridge für den ArduPilot-SITL-Lebenszyklus. Registriert als `sitl` Context-Property.

```python
# Nur intern — wird in tools/ui/app.py registriert:
# engine.rootContext().setContextProperty("sitl", sitl_context)
```

### SITL Lebenszyklus

| Slot | Rückgabe | Beschreibung |
|---|---|---|
| `launchSimVehicle(json)` | — | Startet SITL-Terminal (`sim_vehicle.py`) |
| `launchSwarm(json)` | — | Startet mehrere SITL-Instanzen |
| `stopAll()` | — | SIGTERM alle Prozesse + Overlays zurücksetzen |
| `stopViewers()` | — | SIGTERM alle Viewer-Prozesse |
| `isRunning()` | `bool` | True wenn SITL läuft |
| `sitlStatus()` | `str` | `"stopped"\|"starting"\|"running"\|"error"` |
| `runningInstances()` | `QVariantList` | `[{index, vehicle, port, started}]` |

### Build

| Slot | Parameter | Beschreibung |
|---|---|---|
| `runBuild(board, vehicle)` | `str, str` | `./waf configure && ./waf <vehicle>` |
| `runClean()` | — | `./waf clean` |
| `runDistclean()` | — | `./waf distclean` |

### Gazebo-Viewer

| Slot | Parameter | Beschreibung |
|---|---|---|
| `launchLidarViewer(topic)` | `str` | Startet `lidar_viewer.py` direkt |
| `launchFlowViewer(topic)` | `str` | Startet `flow_viewer.py` direkt |
| `setSensorOverlay(type, visible)` | `str, bool` | `"lidar"\|"flow"` Karten-Overlay |
| `getBridgeStatus()` | `str` | `"stopped"\|"running"\|"error"` |
| `getBridgeParamList()` | `QVariantList` | `[{name, value}]` |
| `launchSensorBridge(config_json)` | `str` | Startet Gazebo→MAVLink Bridge |
| `stopSensorBridge()` | — | SIGTERM Bridge |
| `applyBridgeParams(master)` | `str` | Alle Bridge-Parameter per MAVProxy One-Shot |

**Bridge-Config-JSON:**
```json
{
  "mavlink":      "udpin:0.0.0.0:14550",
  "camera_topic": "/flow_camera/image",
  "lidar_topic":  "/lidar/scan"
}
```

### Parameter

| Slot | Parameter | Beschreibung |
|---|---|---|
| `setParam(name, value)` | `str, str` | Einzelnen Parameter setzen |
| `getKnownParams()` | `str` | JSON-Liste aller SIM_*-Parameter |
| `getPreArmFixes()` | `QVariantList` | Liste der Fix-Karten |
| `launchMavproxyFix(fix_id, master)` | `str, str` | Fix per MAVProxy ausführen |
| `applyBridgeParams(master)` | `str` | Bridge-Parameter setzen (8 Params) |

### Signale

| Signal | Payload | Beschreibung |
|---|---|---|
| `sitlStatusChanged` | `str` | Status geändert |
| `sitlLogLine` | `str` | Log-Zeile für das Konsolen-Panel |
| `sitlInstancesChanged` | — | Instanzliste geändert |
| `gazeboStatusChanged` | `str` | Gazebo-Status |
| `sensorOverlayToggled` | `str, bool` | Overlay-Sichtbarkeit geändert |
| `lidarFrameReady` | `str` | Base64-JPEG für LiDAR-Overlay |
| `flowFrameReady` | `str` | Base64-JPEG für Flow-Overlay |

### _BRIDGE_PARAMS (Klassenattribut)

```python
SITLContext._BRIDGE_PARAMS = {
    "FLOW_TYPE":       "5",    # MAVLink Optical Flow
    "RNGFND1_TYPE":   "10",    # MAVLink Rangefinder
    "RNGFND1_MIN_CM":  "5",
    "RNGFND1_MAX_CM": "3000",
    "RNGFND1_ORIENT": "25",    # nach unten (PITCH_270)
    "PRX1_TYPE":       "2",    # MAVLink Proximity
    "AVOID_ENABLE":    "7",
    "AVOID_MARGIN":    "2",
}
```

---

## GazeboMavlinkSensorBridge

Standalone-Skript `tools/ui/gz_viewers/gazebo_mavlink_sensor_bridge.py`.

```bash
python3 gazebo_mavlink_sensor_bridge.py [--mavlink CONN] [--camera-topic TOPIC] \
    [--lidar-topic TOPIC] [--no-display]
```

| Argument | Standard | Beschreibung |
|---|---|---|
| `--mavlink` | `udpin:0.0.0.0:14550` | MAVLink-Verbindung (UDP, TCP, Serial) |
| `--camera-topic` | `/flow_camera/image` | Gazebo Kamera-Topic |
| `--lidar-topic` | `/lidar/scan` | Gazebo LiDAR-Topic |
| `--no-display` | false | Headless — keine OpenCV-Fenster |

**MAVLink-Ausgaben:**

| Nachricht | Frequenz | ArduPilot-Param |
|---|---|---|
| `OPTICAL_FLOW_RAD` | Kameratakt | `FLOW_TYPE=5` |
| `DISTANCE_SENSOR` | Kameratakt | `RNGFND1_TYPE=10` |
| `OBSTACLE_DISTANCE` | ~10 Hz | `PRX1_TYPE=2` |

Vollständige Dokumentation: [docs/features/gazebo-sensor-bridge.md](../features/gazebo-sensor-bridge.md)

