# SkyMeshX GCS — User Interface Guide

> Version 0.4.0 · All tabs, controls, and parameters explained in English.

---

## Table of Contents

1. [Main Toolbar (Instrument Bar)](#1-main-toolbar-instrument-bar)
2. [Map View](#2-map-view)
3. [Dashboard Tab](#3-dashboard-tab)
4. [Swarm Tab](#4-swarm-tab)
5. [Mission Planning Tab](#5-mission-planning-tab)
6. [Safety / APF Tab](#6-safety--apf-tab)
7. [Gimbal / Camera Tab](#7-gimbal--camera-tab)
8. [ROS2 / uXRCE Tab](#8-ros2--uxrce-tab)
9. [Scenario / Experiment Tab](#9-scenario--experiment-tab)
10. [Flight Log Tab](#10-flight-log-tab)
11. [System Log Tab](#11-system-log-tab)
12. [Help Tab](#12-help-tab)

---

## 1. Main Toolbar (Instrument Bar)

The toolbar at the top of the screen provides quick-access controls for the currently **selected drone**.

| Button / Field | Description |
|---|---|
| **Drone selector** (dropdown) | Choose which drone the toolbar controls apply to. Changes here are reflected across all tabs. |
| **CONNECT / DISCONNECT** | Opens a connection to the drone using the configured connection string (e.g. `tcp:127.0.0.1:5762`). Disconnect closes the MAVLink link cleanly. |
| **ARM** | Arms the drone motors. The drone must be on the ground in `IDLE` state. A confirmation is required if the safety FSM rejects the request. |
| **DISARM** | Disarms the motors. Only allowed when the drone is on the ground (`IDLE` or after landing). |
| **TAKEOFF** | Commands the drone to take off to the configured altitude. The drone must be `ARMED` first. |
| **LAND** | Commands the drone to land at its current position. |
| **RTL** (Return to Launch) | Commands the drone to fly back to its home / launch position and land automatically. |
| **HOLD / LOITER** | Commands the drone to stop at its current position and hold. |
| **Flight Mode** display | Shows the current autopilot flight mode reported by the drone (e.g. `GUIDED`, `AUTO`, `LOITER`). |
| **FSM State** badge | Shows the GCS internal state machine state (e.g. `FLYING`, `MISSION`, `DISCONNECTED`). This is separate from the autopilot mode. |
| **Battery %** | Live battery percentage. Turns orange below 30 %, red below 15 %. |
| **GPS Fix** | GPS fix type: `No Fix` → `2D` → `3D` → `3D+DGPS`. Green = good, orange = degraded. |
| **Altitude (m)** | Current altitude above the takeoff point (relative altitude), in metres. |

---

## 2. Map View

The interactive map is the central view. It shows drone positions, waypoints, field boundaries, and (optionally) a live camera PIP overlay.

### Map Controls

| Control | Description |
|---|---|
| **Click on map** | Places a waypoint at that location (when in waypoint drawing mode). |
| **Right-click drag** | Pans the map. |
| **Scroll wheel** | Zooms in / out. |
| **Drone marker** | Each connected drone is shown as a coloured marker with its ID label. Click a marker to select that drone. |
| **Waypoint markers** | Numbered WP markers (WP 1, WP 2, …). Drag to reposition. |
| **Field boundary** (green polygon) | Drawn when using Mission Planning → Draw on Map. Defines the area for coverage / seeding / solar missions. |

### Map Toolbar Buttons

| Button | Description |
|---|---|
| **MISSION** toggle | Activates / deactivates mission mode. When active, clicking the map adds waypoints to the current mission. |
| **BOUNDARY** | Activates field boundary drawing mode. Each click adds a boundary vertex. Press FINISH (or the button again) to close the polygon. |
| **CLEAR WP** | Removes all waypoints from the map. |
| **Camera PIP** (picture-in-picture) | A small live video overlay appears on the map when a video stream is active and configured. Disappears automatically when there is no active stream (R-10: no blank rectangle is ever shown). |
| **Zoom +/−** | Map zoom buttons. |
| **Centre on drone** | Centres the map on the selected drone's position. |

---

## 3. Dashboard Tab

Live telemetry readout for the selected drone.

### Drone Selector

Dropdown at the top. Automatically selects the first connected drone. Changing the selection here changes the selected drone globally across all panels.

### Status Badges

| Badge | Description |
|---|---|
| **FSM State** (coloured pill) | Internal GCS state machine. Full labels: `IDLE (Connected, ready)`, `ARMED (Ready for takeoff)`, `FLYING (In the air)`, `MISSION (Autopilot active)`, `RTL (Returning)`, `EMERGENCY (Emergency!)`. Blinking = transition in progress. |
| **Drone Type** | `Generic UAV (Standard)` — standard MAVLink drone with FSM + Mission support. `Observation UAV (Gimbal/Camera)` — drone with gimbal, downward/forward camera, and ROS2 bridge support. |
| **Swarm Role** | Only visible when the drone is part of a swarm: `Leader`, `Follower`, or `Coordinator`. |

### FSM Control Guide

A compact reminder of the correct command sequence:
1. Press **ARM** → State becomes `ARMED`
2. Press **TAKEOFF** → State becomes `TAKEOFF` → `FLYING`
3. Issue **GOTO** / **Waypoints** (Swarm tab)
4. Press **RTL** or **LAND** → drone returns / lands

The highlighted line below the guide shows a context-sensitive hint for the current state.

### FSM History

A timestamped list of the last state transitions (e.g. `IDLE → ARMED → TAKEOFF → FLYING`). Newest entry at the bottom. Updated every second.

### KPI Grid (6 tiles)

| Tile | Key | Unit | Description |
|---|---|---|---|
| **ALTITUDE** | `alt_rel` | m | Height above takeoff point |
| **SPEED** | `groundspeed` | m/s | Horizontal ground speed |
| **HEADING** | `yaw` | ° | Compass heading (0 = North) |
| **CLIMB** | `climb` | m/s | Vertical speed (positive = climbing) |
| **SATELLITES** | `satellites` | sat | Number of GPS satellites in view |
| **THROTTLE** | `throttle` | % | Motor throttle output |

### Battery Bar

Shows battery percentage and voltage. Colour: green > 50 %, orange 20–50 %, red < 20 %.

### GPS Strip

Shows GPS fix type, satellite count, and current latitude / longitude coordinates (6 decimal places).

---

## 4. Swarm Tab

Multi-drone management: connect, control, and configure a fleet of drones.

### Left Column — Drone Selection & System Info

#### Drone Selection

- **Drone selector** (dropdown): Selects the active drone. Changing here updates the global selection across all tabs.
- **Generic / Obs. type buttons**: Sets the drone type.
  - **Generic**: Standard flight with FSM and mission support.
  - **Obs.** (Observation): Unlocks the Gimbal and ROS2 bridge features for this drone.

#### Connected Drones List

Each row shows one drone:

| Element | Description |
|---|---|
| **Checkbox** (left edge) | Tick to include this drone as a **Mission Target**. Ticked drones are used when sending multi-drone waypoint commands or uploading missions in Multi-Drone mode. |
| **Drone ID + checkmark** | Name of the drone. ✓ = currently selected drone. |
| **Status line** | Shows `OFFLINE` if disconnected, arm state, flight mode, and current altitude. |
| **⟳ Conn / ⏏ Disc button** | Reconnect or disconnect this individual drone. |
| **✕ button** | Remove this drone from the swarm entirely. |

The header row shows how many drones are currently selected as mission targets. **CLEAR** deselects all.

#### System Info Panel

Displays technical details for the selected drone:

| Field | Description |
|---|---|
| **Autopilot** | Autopilot type (e.g. `ArduCopter`, `PX4`) |
| **Vehicle** | Vehicle type (e.g. `Multirotor`, `VTOL`) |
| **Firmware** | Firmware version string |
| **Board** | Flight controller board ID |
| **System** | MAVLink system status code |
| **Flight Mode** | Raw autopilot mode string |
| **FSM State** | GCS state machine state |
| **Drone Type** | `generic` or `observation` |
| **Connection String** | The MAVLink connection address (e.g. `tcp:127.0.0.1:5762`) |
| **Vendor ID / Product ID** | USB hardware identifiers (filled after AUTOPILOT_VERSION response) |

### Right Column — Swarm Commands & Waypoints

#### Swarm Commands

These buttons send commands to **all connected drones** simultaneously:

| Button | Description |
|---|---|
| **ARM ALL** | Arms motors on all drones. |
| **DISARM ALL** | Disarms all drones. |
| **Takeoff Alt (m)** | Input field: altitude in metres for the next TAKEOFF ALL command. Default: 10 m. |
| **TAKEOFF ALL** | Commands all drones to take off to the configured altitude. |
| **LAND ALL** | Commands all drones to land at their current positions. |
| **RTL ALL** | Commands all drones to return to their launch points and land. |
| **FLIGHT MODE (ALL)** | Buttons for each mode: `STABILIZE`, `ALT_HOLD`, `LOITER`, `AUTO`, `GUIDED`, `POSCTL`, `OFFBOARD`, `HOLD`. Clicking a mode sets it on all drones. |

#### Waypoint / GOTO

| Control | Description |
|---|---|
| **Single Drone / Multi-Drone** toggle | Choose whether the GOTO command targets only the selected drone or all checked Mission Targets. |
| **Target indicator** | Shows the current target (drone name or "N drones selected"). |
| **Lat / Lon** fields | Target GPS coordinates (decimal degrees, e.g. `48.137154`, `11.576124`). |
| **Alt (m)** field | Target altitude in metres above takeoff point. |
| **Distance preview** | Automatically calculated straight-line distance from the drone's current position to the entered coordinates. |
| **SEND GOTO** | Sends the GOTO command to the target drone(s). The drone must be in `GUIDED` mode. |
| **Add WP** | Adds the entered coordinates as a waypoint to the mission waypoint list. |

#### Waypoint List

Shows all waypoints added to the current mission. Each row:

| Column | Description |
|---|---|
| **#** | Waypoint sequence number. |
| **Lat / Lon** | GPS coordinates of the waypoint. |
| **Alt** | Target altitude at this waypoint. |
| **✕** | Remove this waypoint from the list. |

**UPLOAD MISSION** sends the full waypoint list to the selected drone(s). **CLEAR ALL** removes all waypoints.

#### Formation

Configure swarm formation offsets for follower drones:

| Field | Description |
|---|---|
| **North offset (m)** | Distance ahead (+) or behind (−) the leader, in metres. |
| **East offset (m)** | Distance to the right (+) or left (−) of the leader, in metres. |
| **Alt offset (m)** | Altitude difference above (+) or below (−) the leader. |
| **SET OFFSET** | Sends the configured offset to the selected follower drone. |

---

## 5. Mission Planning Tab

Plan autonomous missions for field coverage, precision seeding, or solar panel inspection.

### Mission Type

Select the mission type at the top:

| Type | Description |
|---|---|
| **▦ Coverage** | Systematic grid / lawnmower coverage of a field boundary. Used for mapping or general inspection. |
| **◉ Seeding** | Precision seeding mission with seed dispenser control. Opens the Seeding Wizard (full parameter set). |
| **☀ Solar** | Solar panel inspection mission. Opens the Solar Wizard with panel array configuration. |

> ℹ Switching mission type while drawing mode is active first requires pressing **ESC** to cancel the current mode.

---

### Field Coverage Mode

#### Coverage Pattern

| Pattern | Description |
|---|---|
| **Parallel Lines** | Classic lawnmower — horizontal parallel flight lines. |
| **Spiral** | Inward spiral from the field boundary to the centre. |
| **Grid** | Bi-directional crosshatch pattern (flies horizontal + vertical lines). |
| **Zigzag** | Alternating diagonal lines. |

#### Parameters

| Parameter | Range | Description |
|---|---|---|
| **Altitude (m)** | 10–100 m | Flight altitude above ground. Lower = higher image resolution but slower coverage. |
| **Line Spacing (m)** | 5–50 m | Distance between adjacent flight lines. Smaller = more overlap and better coverage. |
| **Overlap (%)** | 0–50 % | Image overlap between adjacent passes. 20–30 % is standard for photogrammetry. |
| **Flight Speed (m/s)** | 2–15 m/s | Horizontal flight speed during the mission. Faster = less battery time, reduced image quality. |

Hint labels below each slider give a plain-English quality description (e.g. *"Tight (high coverage)"*, *"High (fast coverage)"*).

#### Multi-Drone Strategy

| Strategy | Description |
|---|---|
| **Single Drone** | One drone covers the entire field boundary. |
| **Offset Pattern** | Waypoints are distributed in a round-robin pattern across drones (D1: lines 1, 4, 7 … D2: lines 2, 5, 8 …). |
| **Field Splitting** | The field boundary is divided into equal vertical zones; each drone covers one zone. |
| **Sequential + APF** | All drones fly the same path with a configurable time delay between each. APF collision avoidance is active. |
| **Formation Flight** | The leader drone flies the coverage pattern; follower drones maintain a fixed offset formation behind it. |

- **Formation Offset (m)** *(Formation Flight only)*: Lateral separation between drones in formation. Range: 3–20 m.
- **Start Delay (s)** *(Sequential + APF only)*: Time gap between drone start times. Range: 5–60 s.

#### Field Boundary

| Button | Description |
|---|---|
| **DRAW ON MAP** | Activates boundary drawing mode. Click on the map to place boundary vertices. Minimum 3 points required. |
| **FINISH** | Closes the boundary polygon (visible while drawing mode is active). |
| **CLEAR** | Removes all boundary points and the current coverage plan. |

#### Mission Preview

Shown after a valid boundary is drawn and the coverage plan is generated:

| Value | Description |
|---|---|
| **Waypoints** | Total number of waypoints in the generated mission. |
| **Distance** | Total flight distance in kilometres. |
| **Est. Time** | Estimated flight duration in minutes (based on configured speed). |

---

## 6. Safety / APF Tab

Configures the Artificial Potential Field (APF) collision avoidance system.

| Control | Description |
|---|---|
| **Enable APF** | Turns the safety filter on or off. When on, all GOTO commands pass through the APF before being sent to the drone. |
| **Influence radius (m)** | Distance at which an obstacle starts repelling the drone's path. Larger = earlier avoidance. |
| **Max force** | Maximum deflection force the APF applies. Higher = more aggressive avoidance turns. |
| **Update rate (Hz)** | How often the APF recalculates positions. Default: 20 Hz. |
| **Add obstacle** | Manually register a static obstacle at a GPS position. |
| **Drone exclusion zone** | Each drone in the swarm automatically acts as an obstacle for all other drones. |

---

## 7. Gimbal / Camera Tab

Controls the camera gimbal and displays the live downward/forward video stream for `Observation UAV` drones.

> ⚠ Gimbal and live video features are only available when the selected drone type is set to **Observation UAV**. A warning banner is shown for Generic drones.

### Drone Selector

Dropdown at the top. Selects which drone's gimbal and camera is controlled. Changes here also update the global drone selection.

### Video Stream Display

A 16:9 live video window. States:

| Status | Display | Description |
|---|---|---|
| `unconfigured` | 📹 "No Active Stream" | No video source has been configured for this drone. Configure one in **ROS2 → Video** tab. |
| `waiting` | ⏳ "Waiting for stream…" | Stream URL is set; the system is probing for an incoming UDP stream. |
| `receiving` | **LIVE** badge + video | Frames are being received and decoded. The **LIVE** badge blinks in the top-left corner. |
| `stalled` | ⚠ "Stream stalled" | Stream was active but frames stopped arriving. |
| `error` | ✕ "Stream error" | An error occurred while opening or decoding the stream. Check the URL and drone connection. |

> R-10 policy: No blank black rectangle is ever shown before a stream is confirmed `receiving`. The placeholder is always displayed instead.

The bottom overlay (visible when `receiving`) shows the stream URL and frame size.

### Stream Controls

| Button | Description |
|---|---|
| **Start Stream** | Activates the video decoder for the selected drone. The target switches to `gimbal`, which means the Map PIP will pause while this view is live. |
| **End Stream** | Stops the decoder and releases the video source. The display returns to the placeholder. |
| **Snapshot** | Saves the current frame as a PNG file to the `snapshots/` directory. |

### Gimbal Control

| Control | Description |
|---|---|
| **Pitch slider** | Tilts the gimbal up (0°) or down (−90°). 0 = horizontal, −90 = straight down. |
| **Yaw slider** | Rotates the gimbal left (−180°) or right (+180°). 0 = facing forward. |
| **CENTRE** button | Returns the gimbal to pitch 0°, yaw 0° (straight forward). |
| **NADIR** button | Points the gimbal straight down (pitch −90°, yaw 0°). Used for orthophoto / inspection. |
| **TRACK** toggle | Enables autonomous target tracking (requires a target region to be set). |

---

## 8. ROS2 / uXRCE Tab

Manages the ROS2 bridge, SITL launcher, topic health browser, bag recorder, and video stream configuration.

The tab is divided into **5 sub-tabs** at the top: **Connection**, **Topics**, **Bag**, **Video**, **Debug**.

### ROS2 Status Indicator

A coloured dot (top-right of the tab bar) shows the overall ROS2 status:

| Colour | Status | Description |
|---|---|---|
| 🟢 Green (blinking) | `ROS2 + px4_msgs OK` | rclpy and px4_msgs are installed. Ready to bridge. |
| 🟡 Yellow | `ROS2 OK — px4_msgs missing` | rclpy works but px4_msgs is not built. Build it with `colcon build`. |
| 🔴 Red | `rclpy not installed` | ROS2 is not installed. Install ROS2 Humble first. |

---

### Connection Sub-tab

#### PX4 Bridge

| Control | Description |
|---|---|
| **Drone selector** | Choose which drone to connect the ROS2 bridge to. |
| **NS (Namespace)** field | ROS2 namespace for this drone (e.g. `uav_1`, `px4_1`). Leave blank to use the default `/fmu/*` topics. The resolved topic prefix is shown below the field. |
| **Connect / Disconnect** button | Starts or stops the ROS2–MAVLink bridge for the selected drone. The button colour reflects the current state (green = start, red = stop). Requires `ROS2 + px4_msgs OK`. |

#### PX4 SITL

Launches a simulated PX4 drone (Software-in-the-Loop) directly from the GCS.

| Control | Description |
|---|---|
| **PX4 directory** | Full path to your local `PX4-Autopilot` clone (e.g. `/home/user/PX4-Autopilot`). |
| **Model** | Drone model to simulate. See table below. |
| **World** | Gazebo world environment. See table below. |
| **NS** | Namespace for this SITL instance (e.g. `uav_1`). |
| **Camera / Gimbal** checkboxes | Enable camera and/or gimbal plugins (only visible for compatible models). |
| **START SITL / STOP SITL** | Launches or kills the Gazebo + PX4 SITL process. A status badge shows `RUNNING` with the PID and uptime while active. |
| **START ALL / STOP ALL** | For multi-vehicle: launches or kills all configured SITL instances at once. |

##### Supported Models

| Model | Description |
|---|---|
| `gz_x500` | Standard X500 quadcopter — no camera |
| `gz_x500_gimbal` | X500 with 3-axis gimbal + downward camera → UDP stream port 5600 |
| `gz_x500_mono_cam` | X500 with forward mono camera → UDP stream port 5600 |
| `gz_x500_lidar_down` | X500 with downward-facing LiDAR rangefinder |
| `gz_standard_vtol` | Standard VTOL (fixed-wing + multirotor) |
| `gz_rc_cessna` | Fixed-wing Cessna |
| `iris` | Classic ArduCopter Iris model |
| `sih_quadx` | SIH (Simulation-in-Hardware) — no Gazebo, headless only |

##### World Profiles

| World | Description |
|---|---|
| `empty_default` | Flat empty world — fastest, good for logic/mission testing |
| `aruco_precision_landing` | ArUco marker pad — requires `gz_x500_mono_cam` |
| `baylands_water` | Visual bay/water environment |
| `ridge_terrain` | Hilly terrain — best with `gz_x500_lidar_down` |
| `walls_collision` | Walled obstacle course — good for APF testing |
| `windy_disturbance` | Wind disturbance active — tests robustness |
| `moving_platform` | Moving landing platform (PX4 v1.16+). Set `PX4_GZ_MODEL_POSE=0,0,2.2`. |
| `rover_grid` | Flat grid world for rover/ground vehicle testing |

> ⚠ Compatibility warnings appear automatically when an incompatible model/world combination is selected.

---

### Topics Sub-tab

Browse live ROS2 topics for the connected drone.

| Control | Description |
|---|---|
| **Discover** button | Queries `ros2 topic list` for the active namespace. Populates the topic list. |
| **Filter** field | Filter displayed topics by substring (e.g. `/fmu/out`). |
| **Topic list** | Each row shows the topic name, current **Hz** rate, last message age, and seen/unseen status. |
| **Click topic** | Expands the latest message as compact JSON in a detail panel below. |
| **Watch List** | Pin important topics to keep them at the top of the list. |

Topic health is automatically exported to `ros2_topic_health.json` in the active trace bundle when a Trace session is running.

---

### Bag Sub-tab

Record ROS2 bag files during a simulation.

| Control | Description |
|---|---|
| **Preset** dropdown | Choose a recording preset (topic selection). See table below. |
| **Scenario name** field | Label for this recording (used in the output filename). |
| **START RECORDING** | Starts `ros2 bag record` with the selected topics. A red blinking indicator appears while recording. |
| **STOP RECORDING** | Stops the recording and reports the output file path and size. |
| **Duration / Size** | Live display of recording duration and estimated file size. |
| **Open in Flight Log** | Loads the finished bag file directly into the **Flight Log** tab for playback. |

##### Recording Presets

| Preset | Topics included |
|---|---|
| `minimal_mission` | vehicle_status, global_pos, local_pos, odometry, attitude, control_mode, mission_result, failsafe_flags |
| `full_px4_out` | All topics under `/<ns>/fmu/out/*` |
| `camera_gimbal` | gimbal_device_attitude_status, gimbal_device_set_attitude, camera/image_raw |
| `swarm_multi_vehicle` | vehicle_status, odometry, trajectory_setpoint for all active namespaces |

---

### Video Sub-tab

Configure the live video stream source for each drone.

| Control | Description |
|---|---|
| **Drone** dropdown | Select which drone to configure. |
| **Host** field | IP address or hostname of the video source (default: `127.0.0.1` for local SITL). |
| **Port** field | UDP port for the incoming H.264 stream (default: `5600` for PX4 Gazebo). |
| **PX4 Quick Buttons** | Five coloured quick-set buttons: **px4_1** (5600), **px4_2** (5601), **px4_3** (5602), **px4_4** (5603), **px4_5** (5604). Click to fill the Port field automatically. |
| **Probe Stream** | Tests whether a UDP stream is reachable on the configured host:port without starting the decoder. Updates the status badge. |
| **Status badge** | `waiting` (probing), `receiving` (frames arriving), `stalled` (stream interrupted), `error` (cannot open). |

> The live video is rendered in the **Gimbal / Camera** tab (for the gimbal view) and as a PIP overlay on the **Map** (for aerial overview). Only one renderer is active at a time.

---

### Debug Sub-tab

Trace bundle management and diagnostic information.

#### Trace Session

A trace bundle records all GCS events (UI actions, mission events, topic health, video status) to a timestamped folder under `trace_runs/`.

| Control | Description |
|---|---|
| **Scenario name** field | A short label identifying this session (e.g. `gz_x500_seeding_test`). |
| **START TRACE** | Creates a new trace session folder (`trace_runs/<timestamp>_<scenario>/`) and begins recording all events. |
| **STOP + EXPORT** | Stops the session and writes the final `manifest.json` and `ros2_topic_health.json`. |
| **Session status** | Shows `ACTIVE` with the elapsed time and folder path, or `INACTIVE`. |
| **OPEN FOLDER** | Opens the trace bundle folder in the system file manager. |
| **EXPORT MARKDOWN** | Runs `tools/analyze_trace.py` to generate a human-readable `summary.md` inside the bundle folder. |

#### MAVLink / Topic Diagnostics

Shows real-time latency and message rates for the active MAVLink connection and subscribed ROS2 topics.

---

## 9. Scenario / Experiment Tab

Run pre-configured mission scenarios and experiments.

| Control | Description |
|---|---|
| **Scenario selector** | Choose a scenario from the list (e.g. Seeding Test, Solar Inspection, Multi-UAV Formation). |
| **Parameters panel** | Scenario-specific parameters (field size, UAV count, altitude, etc.). |
| **PREVIEW** | Generates the mission on the map without uploading it. |
| **RUN** | Uploads the mission to the selected drones and starts execution. |
| **ABORT** | Sends RTL to all drones involved in the scenario. |
| **Log** | Shows scenario-specific log messages. |

---

## 10. Flight Log Tab

Visualise and replay post-flight CSV log files or ROS2 bag files.

### Open Buttons

| Button | Description |
|---|---|
| **OPEN CSV** | Opens a file picker to load a CSV flight log. Required columns: `timestamp`, `alt_rel`, `groundspeed`, `battery_pct`, `vz`. |
| **OPEN BAG** | Opens a file picker to load a ROS2 `.mcap` or `.db3` bag file for playback. |
| **Filename display** | Shows the name of the currently loaded file, or `-- no log loaded --`. |

### Flight Log Summary

After loading a CSV, a text summary is shown:

| Field | Description |
|---|---|
| **Rows** | Number of data rows parsed from the CSV. |
| **Duration** | Total flight time (MM:SS). |
| **Max alt** | Maximum altitude reached during the flight (metres). |
| **Max speed** | Maximum ground speed recorded (m/s). |
| **Battery delta** | Battery percentage consumed during the flight (%). |

### ROS2 Bag Playback Controls

| Control | Description |
|---|---|
| **State / Progress display** | Shows current playback state (`STOPPED`, `PLAYING`, `PAUSED`) and current time / total duration. |
| **PLAY** | Starts bag playback using `ros2 bag play`. Requires ROS2 to be installed. |
| **STOP** | Stops playback. Progress resets to 0. |
| **−** / **+** speed buttons | Decrease / increase playback speed by 0.5×. Range: 0.1× to 10.0×. |
| **Speed indicator** | Shows the current playback rate (e.g. `Speed: 1.0×`). |

> ℹ ROS2 bag playback requires a working ROS2 installation and publishes topics to the ROS2 network in real time. Other ROS2 subscribers (e.g. rviz2) will receive the replayed data.

---

## 11. System Log Tab

Real-time message log showing all GCS events.

### Sub-tabs

| Tab | Description |
|---|---|
| **System Log** | All log messages from all drones and GCS components. Each message is tagged with `[DroneID]`, a timestamp, and colour-coded by severity. |
| **Trace** | Messages specifically tagged as trace events (used by the Trace Bundle system). |

### Log Controls

| Control | Description |
|---|---|
| **Level filter** | Filter by severity: `ALL`, `INFO`, `WARN`, `ERROR`. |
| **Drone filter** | Show messages from one drone only, or all. |
| **Search** field | Filter messages by text content. |
| **SAVE** | Exports the current log to a `.txt` file. |
| **CLEAR** | Clears the displayed log (does not affect the auto-saved syslog file). |

> Log messages are auto-saved to `syslogs/skymeshx-<date>.log` in the background, even when the Log tab has never been opened.

---

## 12. Help Tab

Displays this user guide and a feature reference inside the GCS application.

---

## Appendix — FSM State Machine

The GCS maintains an internal Finite State Machine (FSM) for each drone independently of the autopilot flight mode.

```
DISCONNECTED
    │ connect()
    ▼
  IDLE  ←──────────────────────────────────┐
    │ arm()                                 │
    ▼                                       │
 ARMING                                    │
    │ (success)                             │
    ▼                                       │
 ARMED                                     │
    │ takeoff()                             │
    ▼                                       │
 TAKEOFF                                   │
    │ (airborne)                            │
    ▼                                       │
 FLYING ──→ MISSION (uploadMission)        │
    │      ──→ RTL                          │
    │ land()                                │
    ▼                                       │
 LANDING                                   │
    │ (on ground)                           │
    └───────────────────────────────────────┘

Any state → EMERGENCY (emergency trigger)
```

Invalid transitions are rejected and logged. The `rejected_count` counter increments for monitoring.

---

## Appendix — Connection Strings

| Format | Example | Use case |
|---|---|---|
| `tcp:<host>:<port>` | `tcp:127.0.0.1:5762` | Raw ArduCopter SITL (default) |
| `tcp:<host>:<port>` | `tcp:127.0.0.1:5760` | MAVProxy-aggregated SITL |
| `udp:<host>:<port>` | `udp:127.0.0.1:14550` | MAVLink over UDP (GCS standard port) |
| `serial:<port>:<baud>` | `serial:/dev/ttyUSB0:57600` | Physical serial/USB connection |

> Default port if none is specified: `tcp:127.0.0.1:5762`

---

## 13. SITL-Tab

Der SITL-Tab steuert den gesamten ArduPilot-SITL-Lebenszyklus.

### Sub-Tabs

#### Setup & Build
Verwaltet das ArduPilot-Repository und Build.
- **Repository-Pfad**: Pfad zum ArduPilot-Verzeichnis.
- **Board** + **Fahrzeug**: Ziel für `./waf configure && ./waf <vehicle>`.
- **▶ Build** / **Clean** / **Distclean**: öffnen jeweils ein Terminal.

#### Sim starten
Konfiguriert und startet eine einzelne SITL-Instanz.
- **Fahrzeug**: ArduCopter, ArduPlane, ArduRover, ArduSub, ArduHeli, …
- **Rahmentyp**: alle Frames des gewählten Fahrzeugs.
- **Standort**: Simulationsstandort aus über 100 verfügbaren Orten.
- **Geschwindigkeit**: 1×–10× Speedup.
- **GCS-Verbindung**: TCP (Port 5760) oder UDP.
- **Peripheriegeräte**: aktivierbare Geräte mit automatischen Parameterüberschreibungen.
- **▶ Simulation starten** / **■ Stoppen**.

#### Swarm
Gleich wie „Sim starten", aber für mehrere Instanzen gleichzeitig (2–20 Drohnen).

#### Parameter
Live-Parameterverwaltung für laufende SITL-Instanz.
- Tabelle bekannter `SIM_*`-Parameter mit Wert und Einheit.
- Klick auf einen Wert → Inline-Editing → per MAVProxy One-Shot gesetzt.

#### Gazebo

| Element | Beschreibung |
|---|---|
| **LIDAR (gz.transport)** | Topic-Eingabe, „Auf Karte zeigen"-Toggle, „▶ OpenCV Fenster"-Button |
| **OPTICAL FLOW** | Gleich wie LiDAR |
| **Stop Viewers** | Beendet alle laufenden Viewer-Prozesse |
| **Karten-Overlay-Buttons** | Zeigen Live-Frames direkt als PIP auf der Karte an |
| **GStreamer-Streaming** | UDP-Port, Stream in GCS anzeigen oder GSt-Terminal öffnen |

#### Debug

| Element | Beschreibung |
|---|---|
| **MAVProxy starten** | Adresse, `--map`, `--console` |
| **Joystick laden** | MAVProxy mit Joystick-Modul |
| **PREARM FIXES** | Quick-Fix-Karten (Frame Class, Accel, Compass, Arming Checks, Takeoff) |

---

## 14. Sensor Bridge (Gimbal-Tab)

Am Ende des **Gimbal-Tabs** befindet sich der Bereich **SENSOR BRIDGE — GAZEBO → ARDUPILOT**.

### Wozu?

Die Bridge sendet Optical Flow und LiDAR-Hindernisdaten per MAVLink an ArduPilot. ArduPilot kann damit:
- **Optical Flow**: Position ohne GPS halten (`FLOW_TYPE=5`, `EK3_SRC1_VELXY=5`).
- **LiDAR**: Hindernisse erkennen und ausweichen (`PRX1_TYPE=2`, `AVOID_ENABLE=7`).

### Verwendung

1. Gazebo-Simulation starten (SITL-Tab → Gazebo).
2. **Gimbal-Tab** öffnen → Bereich **SENSOR BRIDGE**.
3. MAVLink-Adresse, Kamera- und LiDAR-Topic eingeben.
4. **⚙ Parameter setzen** klicken → ArduPilot startet neu.
5. **▶ Bridge starten** klicken → Status-LED wird grün.

| Kontrolle | Beschreibung |
|---|---|
| **MAVLink** | Verbindungsstring (Standard: `udpin:0.0.0.0:14550`) |
| **Kamera-Topic** | Gazebo-Topic für Optical Flow (Standard: `/flow_camera/image`) |
| **LiDAR-Topic** | Gazebo-Topic für LiDAR (Standard: `/lidar/scan`) |
| **⚙ Parameter setzen** | Setzt alle 8 Bridge-Parameter per MAVProxy One-Shot |
| **▶ Bridge starten** | Startet `gazebo_mavlink_sensor_bridge.py` direkt |
| **■ Stoppen** | Beendet die Bridge (SIGTERM) |
| **Status-LED** | Grün = aktiv, Rot = Fehler, Grau = gestoppt |

### Live-Overlays auf der Karte

Wenn ein Sensor-Overlay aktiviert ist (SITL-Tab → Gazebo → „Auf Karte zeigen"), erscheint auf der Karte:
- **LiDAR-Polarplot** (links unten): Obstacles als Punkte, Abstands-Gitterlinien.
- **Optical-Flow-Bild** (links unten, rechts vom LiDAR): Kamerabild mit Flow-Vektorpfeilen.

Klick auf den Overlay oder Toggle-Button schließt ihn wieder.

---

*SkyMeshX GCS v0.4.0 · docs/ui/ui-user-guide.md*
