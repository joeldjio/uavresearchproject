# SkyMeshX

**Python SDK + QML Ground Control Station for ArduPilot/PX4 drones — MAVLink, swarms, SITL, Gazebo sensor bridge, mission planning, and safety filters.**

[![Tests](https://github.com/joeldjio/skymeshx/workflows/Tests/badge.svg)](https://github.com/joeldjio/skymeshx/actions)
[![Coverage](https://codecov.io/gh/joeldjio/skymeshx/branch/main/graph/badge.svg)](https://codecov.io/gh/joeldjio/skymeshx)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![UI: PySide6/QML](https://img.shields.io/badge/UI-PySide6%20%2F%20QML-green.svg)](https://doc.qt.io/qtforpython/)

SkyMeshX combines a Python SDK, a PySide6/QML ground control station, MAVLink control, PX4-native ROS2/uXRCE-DDS integration, mission planning, safety filters, simulation support, and research data tooling.

> Safety note: SkyMeshX can command real vehicles. Test new workflows in SITL first, then with propellers removed, and only then in controlled flight conditions.

## Highlights

- **Ground control station**: PySide6/QML UI with dashboard, map, swarm, mission, safety, gimbal/camera, ROS2, SITL, flight log, and help panels.
- **Core drone SDK**: `Drone` and `Swarm` APIs for MAVLink endpoints over TCP, UDP, serial, and COM ports.
- **Mission planning**: manual waypoint missions, field coverage, seeding missions with servo/dispenser commands, and solar inspection with camera/gimbal trigger metadata.
- **Explicit mission execution**: upload and start are separate actions; upload clears/adds/uploads the mission, while `Start Mission` explicitly arms/takes off/starts.
- **Swarm coordination**: multi-drone management, formations, leader/follower workflows, distributed allocation, and APF-aware movement.
- **Safety systems**: APF collision avoidance, collision prediction, battery monitoring, geofence support, and mission validation.
- **ArduPilot SITL panel**: full SITL lifecycle from the GCS — build, configure, launch, stop, parameter management, peripheral devices, swarm spin-up, MAVProxy quick-fixes, and Gazebo sensor integration.
- **Gazebo sensor overlays**: in-process `gz.transport13` subscriptions render live LiDAR (polar plot) and Optical Flow frames directly onto the map as PIP overlays — no extra windows.
- **Gazebo → MAVLink sensor bridge**: `gazebo_mavlink_sensor_bridge.py` forwards `OPTICAL_FLOW_RAD`, `DISTANCE_SENSOR`, and `OBSTACLE_DISTANCE` to ArduPilot from Gazebo sensors; works for SITL and real hardware.
- **PX4 + ROS2**: uXRCE-DDS bridge, PX4 topic discovery/health, mission upload/monitoring, frame conversions, bag recording, SITL launch controls, and Gazebo world/model profiles.
- **Camera and gimbal workflows**: camera context, observation UAV model hooks, thermal settings, video stream status, and optional live frames through the UI.
- **Traceability**: trace bundles, mission/WP tracking, ROS2 topic health exports, flight logs, JSONL/CSV telemetry logs, and ROS2 bag workflows.
- **Hardware-free tests**: the default test suite mocks MAVLink, ROS2, SITL, and hardware dependencies.

## Quick Start

### 1. Install from source

```bash
git clone https://github.com/joeldjio/skymeshx.git
cd skymeshx

python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux/macOS
# source .venv/bin/activate

pip install -e .
pip install -r requirements.txt
```

For test dependencies:

```bash
pip install -e ".[test]"
```

ROS2 support is optional and must be installed through your ROS2 distribution, for example ROS2 Humble plus `px4_msgs`.

### 2. Launch the GCS

```bash
python -m tools.ui
```

Useful variants:

```bash
python -m tools.ui --debug
python tools/ui/startup_profiler.py
```

### 3. Connect to ArduPilot SITL

SkyMeshX defaults to the raw ArduCopter SITL endpoint:

```text
tcp:127.0.0.1:5762
```

`tcp:127.0.0.1:5760` is commonly the MAVProxy-aggregated SITL port, not the raw default.

```bash
sim_vehicle.py -v ArduCopter
python -m tools.ui
```

Then connect in the UI with `tcp:127.0.0.1:5762`.

### 4. Connect to PX4 SITL + ROS2

PX4-native workflows use uXRCE-DDS and ROS2 topics, not MAVLink-over-ROS.

```bash
source /opt/ros/humble/setup.bash
source /path/to/px4_msgs_ws/install/setup.bash

MicroXRCEAgent udp4 -p 8888

cd /path/to/PX4-Autopilot
PX4_UXRCE_DDS_NS=uav_1 make px4_sitl gz_x500
```

Then launch the UI, open the ROS2 panel, set namespace `uav_1`, and start the PX4 bridge.

See [docs/setup/px4-sitl.md](docs/setup/px4-sitl.md) for the full workflow.

## Command Line

```bash
skymeshx connect
skymeshx status --port tcp:127.0.0.1:5762
DRONE_PORT=udp:127.0.0.1:14550 skymeshx arm
```

Connection resolution order:

```text
--port flag > DRONE_PORT environment variable > tcp:127.0.0.1:5762
```

## Python API Examples

### Single drone

```python
from skymeshx import Drone

drone = Drone("tcp:127.0.0.1:5762")
drone.connect()
drone.arm()
drone.takeoff(10.0)
drone.goto(47.397742, 8.545594, 15.0)
drone.land()
drone.disconnect()
```

### Swarm

```python
from skymeshx import Swarm

swarm = Swarm()
swarm.add("D1", "tcp:127.0.0.1:5762")
swarm.add("D2", "tcp:127.0.0.1:5763")
swarm.add("D3", "tcp:127.0.0.1:5764")

swarm.connect_all()
swarm.arm_all()
swarm.takeoff_all(altitude=10.0)
swarm.formation("v", spacing=5.0, leader="D1", use_apf=True)
swarm.land_all()
swarm.disconnect_all()
```

### Field coverage

```python
from skymeshx.control.field_coverage import (
    CoverageConfig,
    CoveragePattern,
    FieldBoundary,
    FieldCoveragePlanner,
)

boundary = FieldBoundary(
    corners=[
        (47.397742, 8.545594),
        (47.397742, 8.546594),
        (47.398742, 8.546594),
        (47.398742, 8.545594),
    ]
)

planner = FieldCoveragePlanner()
planner.set_home_position(47.397742, 8.545594)

config = CoverageConfig(
    pattern=CoveragePattern.PARALLEL_LINES,
    altitude=20.0,
    line_spacing=10.0,
    speed=5.0,
)

waypoints = planner.generate_coverage_waypoints(boundary, config)
```

### Solar inspection preview

```python
from skymeshx.control.solar_inspection import (
    InspectionConfig,
    PanelRow,
    SolarParkInspectionPlanner,
)

rows = [
    PanelRow(start=(48.1370, 11.5750), end=(48.1380, 11.5750), width=2.0),
]

planner = SolarParkInspectionPlanner()
config = InspectionConfig(
    altitude=30.0,
    speed=3.0,
    gimbal_pitch=-90.0,
    trigger_distance=8.0,
)

preview = planner.generate_solar_mission_with_preview(rows, config)
print(preview.to_dict()["totalImages"])
```

## Architecture

SkyMeshX is organized as layered software. UI code never talks directly to
MAVLink, ROS2, or simulator processes; it goes through Qt context objects that
translate QML calls into Python services. Mission planners stay hardware-free
and produce waypoint/preview data first. Upload and execution are separate
backend actions so a generated mission can be inspected before any vehicle is
armed or started.

```text
QML Ground Control Station
        |
        v
Qt context layer (tools/ui/context)
        |
        |  validates UI input, emits Qt signals, runs blocking work off-thread
        |
        v
Mission planning and domain services
        |
        |  field coverage, seeding, solar inspection, safety, capability checks
        |
        v
Core SDK and state management
        |
        |  Drone, Swarm, telemetry cache, FSM, trace logger, mission engine
        |
        v
Transport and simulator integrations
        |
        |  MAVLink, PX4 ROS2/uXRCE-DDS, SITL, Gazebo, bag/trace tooling
        |
        v
ArduPilot, PX4, SITL, Gazebo, or hardware
```

Feature-critical mission paths:

| Workflow | UI entry | Python boundary | Planner/service | Output |
| --- | --- | --- | --- | --- |
| Field coverage | `MissionPanel.qml` | `MissionContext` | `FieldCoveragePlanner` | Coverage waypoints and map overlay |
| Seeding | `SeedingPanel.qml` | `generateSeedingPreview()` / `uploadSeedingMission()` | `SeedingMissionPlanner` | Coverage rows, seed drop points, servo commands, warnings |
| Solar inspection | `SolarInspectionPanel.qml` | `generateSolarPreview()` / `uploadSolarMission()` | `SolarParkInspectionPlanner` | Panel rows, camera trigger points, footprint polygons, gimbal/camera commands |
| PX4 ROS2 | `ROS2Panel.qml` | `ROS2Context` | `PX4ROSBridge`, SITL launcher, bag recorder | Topic health, bridge state, traces, bags |
| Camera/gimbal | `GimbalPanel.qml`, map PIP | `CameraContext`, `GimbalContext` | Observation UAV model and stream status | Stream control, snapshots, gimbal/camera commands |

The seeding and solar planners are intentionally usable without the UI. Their
preview methods return QML-compatible dictionaries, while their waypoint lists
can be passed to the mission upload path. The upload path only clears, adds,
validates, and uploads mission items. The explicit `Start Mission` command is
responsible for arming, takeoff, and mission start.

Key directories:

| Path | Purpose |
| --- | --- |
| [skymeshx/core](skymeshx/core) | MAVLink connection, telemetry state, FSM, trace logger |
| [skymeshx/sdk](skymeshx/sdk) | High-level `Drone` and `Swarm` APIs |
| [skymeshx/control](skymeshx/control) | Mission engine, coverage, seeding, solar inspection |
| [skymeshx/safety](skymeshx/safety) | APF, collision prediction, battery and perception safety |
| [skymeshx/ros](skymeshx/ros) | PX4 ROS2 bridge, mission upload, formations, bag recorder |
| [skymeshx/simulation](skymeshx/simulation) | SITL, PX4 Gazebo, replay helpers |
| [tools/ui](tools/ui) | PySide6/QML ground control station |
| [tests](tests) | Hardware-free unit and integration tests |
| [docs](docs) | API, setup, feature, UI, security, and testing documentation |

## Important Conventions

- **Default MAVLink endpoint**: `tcp:127.0.0.1:5762`.
- **Mission upload is blocking at the protocol layer**: `MissionEngine.upload()` is run off the UI thread.
- **Upload is not execute**: mission upload and mission start are intentionally separate for safety.
- **PX4 ROS2 topics**: PX4 to ROS2 uses `/fmu/out/*`; ROS2 to PX4 uses `/fmu/in/*`.
- **Frame conventions**: PX4 and MAVLink use NED/FRD; ROS2 uses ENU/FLU. Convert at boundaries.
- **ROS2 context management**: use `acquire_ros()` / `release_ros()` instead of calling `rclpy.init()` directly.
- **Optional dependencies stay lazy**: core imports should not require UI, ROS2, SITL, or hardware packages.
- **Tests are hardware-free by default**: use mocks and fixtures from [tests/conftest.py](tests/conftest.py).

## Ground Control Station

The GCS is launched with:

```bash
python -m tools.ui
```

Main UI areas:

- **Dashboard**: selected drone status, telemetry, and quick actions.
- **Map**: Leaflet-based map, drone markers, paths, boundaries, mission overlays, seeding drops, solar rows, optional video PIP, and live LiDAR/Flow sensor overlays.
- **Mission**: manual waypoints, coverage missions, seeding wizard, solar inspection wizard, upload/start/pause/abort controls.
- **Swarm**: drone selection, formation controls, multi-vehicle state, and coordination helpers.
- **Safety**: APF, collision, battery, and safety feedback.
- **Gimbal/Camera**: camera controls, gimbal commands, stream start/stop, thermal settings, sensor bridge (Gazebo→MAVLink), and observation UAV hooks.
- **SITL**: full ArduPilot SITL lifecycle — build, configure vehicle/frame/location, launch sim, stop, Swarm spin-up, MAVProxy quick-fixes, parameter management, Gazebo integration with LiDAR/Flow overlays and sensor bridge.
- **ROS2**: PX4 bridge, SITL launcher, topic browser, bag recorder, video stream controls, debug/trace tooling.
- **Flight Log**: CSV and ROS2 bag playback workflows.

See [docs/ui/ui-user-guide.md](docs/ui/ui-user-guide.md).

## ArduPilot SITL, Gazebo, and Sensor Bridge

SkyMeshX includes a complete ArduPilot SITL workflow integrated into the GCS:

- **SITL panel** (Tab "SITL") with sub-tabs: Setup & Build, Sim starten, Swarm, Parameter, Gazebo, Debug.
- Vehicle/frame/location/speedup dropdowns; TCP and UDP GCS connection modes.
- Peripheral device catalogue (GPS, LiDAR, optical flow, rangefinder, camera, beacon).
- Auto-connect after SITL starts (configurable).
- MAVProxy quick-fix cards (PreArm fixes, arming checks, guided/takeoff sequences).
- Parameter tab: known `SIM_*` parameters with live editing via MAVProxy one-shot.
- **Gazebo tab**: LiDAR viewer, Optical Flow viewer, sensor stream monitor, GStreamer stream routing.
- **Live overlays on the map**: in-process `gz.transport13` subscriptions push LiDAR (polar plot, 300×300) and Optical Flow (320×240) frames directly onto the map as PIP images — toggle per sensor, no extra windows.
- **Gazebo → MAVLink sensor bridge** (`tools/ui/gz_bridge/gazebo_mavlink_sensor_bridge.py`): sends `OPTICAL_FLOW_RAD`, `DISTANCE_SENSOR`, and `OBSTACLE_DISTANCE` to ArduPilot; headless, SIGTERM-safe, works for SITL and real hardware.
- One-click parameter apply (`FLOW_TYPE=5`, `RNGFND1_TYPE=10`, `RNGFND1_ORIENT=25`, `PRX1_TYPE=2`, `AVOID_ENABLE=7`, `AVOID_MARGIN=2`) from the Sensor Bridge section.
- Bridge status LED (green/red, 1.5 s polling) and EKF Non-GPS hint block.

## PX4, ROS2, and Video

SkyMeshX includes active support for Linux-based PX4 simulation workflows:

- PX4 SITL launcher with model, namespace, world profile, SIH mode, and multi-vehicle support.
- ROS2 setup source fields for bridge and SITL sessions.
- PX4 topic discovery, topic health, and selected topic subscription.
- ROS2 bag recording presets and playback tooling.
- Optional live video frames from UDP/RTSP/MJPEG sources through `VideoStreamContext`.
- Default PX4 Gazebo video ports: `5600`, `5601`, `5602`, ...
- Trace bundle export under [trace_runs](trace_runs) for later analysis.

Useful docs:

- [PX4 SITL startup](docs/setup/px4-sitl.md)
- [PX4 mission upload via uXRCE-DDS](docs/setup/px4-mission-upload.md)
- [PX4 mission monitoring](docs/setup/px4-mission-monitoring.md)
- [Frame conventions](docs/setup/frame-conventions.md)
- [SITL camera stream test checklist](docs/testing/sitl-camera-stream.md)
- [SITL bag workflow](docs/testing/sitl-bag-workflow.md)
- [Gazebo Sensor Bridge](docs/features/gazebo-sensor-bridge.md)

## Testing

```bash
pytest tests/
pytest tests/ -k "not slow"
pytest tests/test_solar_inspection.py -v
pytest tests/test_ros2_sitl_launcher.py -v
```

SITL smoke tests are opt-in:

```bash
SITL_AVAILABLE=1 pytest tests/test_sitl_smoke.py -v
```

The default suite is designed to run without real MAVLink, ROS2, PX4, Gazebo, cameras, or drones.

## Documentation Map

| Start here | Document |
| --- | --- |
| Complete feature overview | [docs/features/complete-feature-description.md](docs/features/complete-feature-description.md) |
| API architecture | [docs/api/overview.md](docs/api/overview.md) |
| Full API reference | [docs/api/reference.md](docs/api/reference.md) |
| UI user guide | [docs/ui/ui-user-guide.md](docs/ui/ui-user-guide.md) |
| Installation | [docs/setup/installation.md](docs/setup/installation.md) |
| PX4 SITL | [docs/setup/px4-sitl.md](docs/setup/px4-sitl.md) |
| **Gazebo Sensor Bridge** | [docs/features/gazebo-sensor-bridge.md](docs/features/gazebo-sensor-bridge.md) |
| **Release Notes v0.4.0** | [docs/release/notes-v0.4.0.md](docs/release/notes-v0.4.0.md) |
| Field coverage | [docs/features/field-coverage-planning.md](docs/features/field-coverage-planning.md) |
| Seeding missions | [docs/features/seeding-mission-planner.md](docs/features/seeding-mission-planner.md) |
| Seeding SITL checklist | [docs/testing/sitl-seeding-mission.md](docs/testing/sitl-seeding-mission.md) |
| Solar inspection | [docs/features/solar-inspection.md](docs/features/solar-inspection.md) |
| Solar SITL checklist | [docs/testing/sitl-solar-mission.md](docs/testing/sitl-solar-mission.md) |
| Battery monitoring | [docs/features/battery-monitoring.md](docs/features/battery-monitoring.md) |
| Collision prediction | [docs/features/collision-prediction.md](docs/features/collision-prediction.md) |
| CI and test strategy | [docs/testing/ci-cd-guide.md](docs/testing/ci-cd-guide.md) |
| Release checklist | [docs/release/checklist.md](docs/release/checklist.md) |

## Licensing

The core project is licensed under MIT. The graphical GCS uses PySide6/Qt for Python under LGPL v3 through dynamic linking.

See:

- [LICENSE](LICENSE)
- [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt)
- [NOTICE.txt](NOTICE.txt)

## Project Status

SkyMeshX is alpha-stage research software. The core APIs, hardware-free tests, safety primitives, seeding/solar planners, and the SITL/Gazebo sensor bridge are usable. ArduPilot SITL with live sensor overlays (LiDAR, Optical Flow) and the Gazebo→MAVLink bridge are production-ready for simulation; hardware sensor bridge testing is ongoing.

Repository: <https://github.com/joeldjio/skymeshx>
