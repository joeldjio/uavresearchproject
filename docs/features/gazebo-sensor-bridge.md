# Gazebo → ArduPilot MAVLink Sensor-Bridge

> Datei: `tools/ui/gz_bridge/gazebo_mavlink_sensor_bridge.py`
> Zugehöriger GCS-Bereich: Gimbal-Tab → Sensor Bridge

---

## Überblick

Die Sensor-Bridge verbindet Gazebo-Sensor-Topics direkt mit ArduPilot über MAVLink — ohne ROS2. Sie berechnet Optical Flow aus dem Kamerabild (Farneback-Algorithmus) und wandelt LiDAR-Scans in Hindernisdaten um, die ArduPilot für Positionshaltung ohne GPS und für Hinderniserkennung verwenden kann.

Gleiches Script — SITL und echte Hardware.

---

## Architektur

```text
Gazebo Simulation / Echte Sensoren
      │
      │  gz.transport13 Topics
      ├─────────────────────────────────────────────────────────────
      │                                                             │
      ▼                                                             ▼
/flow_camera/image                                          /lidar/scan
(gz.msgs.Image)                                         (gz.msgs.LaserScan)
      │                                                             │
      ▼                                                             ▼
OpenCV Farneback                                     Sektor-Mapping (72 Bins)
Optical Flow                                         Gazebo CCW → MAVLink FRD CW
      │                                                             │
      ├───────────────────────────────┬───────────────────────────-┤
      │                               │                             │
      ▼                               ▼                             ▼
OPTICAL_FLOW_RAD               DISTANCE_SENSOR               OBSTACLE_DISTANCE
(FLOW_TYPE=5)                  (RNGFND1_TYPE=10)             (PRX1_TYPE=2)
                               (RNGFND1_ORIENT=25)           72 Sektoren × 5°
      │                               │                             │
      └───────────────────────────────┴─────────────────────────────┘
                                      │
                                      ▼
                              ArduPilot MAVLink
                          (SITL: udp:14550 / Hardware: serial / tcp)
```

---

## Voraussetzungen

### Software
```bash
pip install opencv-python pymavlink
pip install gz-transport13 gz-msgs10   # Gazebo Harmonic
```

### ArduPilot-Parameter (einmalig setzen)

Diese Parameter müssen vor dem ersten Start in ArduPilot gesetzt werden. Am einfachsten über den GCS-Button **⚙ Parameter setzen** im Gimbal-Tab:

```
param set FLOW_TYPE       5      # MAVLink Optical Flow
param set RNGFND1_TYPE   10      # MAVLink Rangefinder
param set RNGFND1_MIN_CM  5
param set RNGFND1_MAX_CM 3000
param set RNGFND1_ORIENT 25      # Nach unten (PITCH_270)
param set PRX1_TYPE       2      # MAVLink Proximity
param set AVOID_ENABLE    7      # Hinderniserkennung an
param set AVOID_MARGIN    2      # Sicherheitsabstand 2 m
reboot
```

---

## Verwendung

### Über den GCS (empfohlen)

1. Gazebo-Simulation starten (SITL-Tab → Gazebo).
2. **Gimbal-Tab** öffnen → Bereich **SENSOR BRIDGE**.
3. MAVLink-Adresse eintragen (Standard: `udpin:0.0.0.0:14550`).
4. **⚙ Parameter setzen** klicken → ArduPilot neu starten.
5. **▶ Bridge starten** klicken.
6. Status-LED wird grün: `Bridge aktiv — sendet OPTICAL_FLOW_RAD + OBSTACLE_DISTANCE`.

### Kommandozeile (SITL)

```bash
# Standard-SITL
python3 tools/ui/gz_bridge/gazebo_mavlink_sensor_bridge.py --no-display

# Mit expliziten Topics
python3 tools/ui/gz_bridge/gazebo_mavlink_sensor_bridge.py \
    --mavlink udpin:0.0.0.0:14550 \
    --camera-topic /flow_camera/image \
    --lidar-topic /lidar/scan \
    --no-display
```

### Kommandozeile (echte Hardware)

```bash
# USB-Serial (z. B. Pixhawk 4)
python3 tools/ui/gz_bridge/gazebo_mavlink_sensor_bridge.py \
    --mavlink /dev/ttyACM0:115200 \
    --no-display

# Netzwerk
python3 tools/ui/gz_bridge/gazebo_mavlink_sensor_bridge.py \
    --mavlink tcp:192.168.1.10:5760 \
    --no-display
```

### Mit OpenCV-Fenstern (Diagnose)

```bash
# Ohne --no-display → öffnet zwei Fenster
python3 tools/ui/gz_bridge/gazebo_mavlink_sensor_bridge.py
# Beenden mit Q oder ESC im Fenster
```

---

## MAVLink-Nachrichten

### OPTICAL_FLOW_RAD

Wird bei jedem Kamerabild gesendet (typisch 10–30 Hz).

| Feld | Wert | Beschreibung |
|---|---|---|
| `time_usec` | Systemzeit µs | Zeitstempel |
| `sensor_id` | 0 | Sensor-ID |
| `integration_time_us` | `dt * 1e6` | Integrationszeit |
| `integrated_x` | Berechnet | Flow in Sensor-X (rad) |
| `integrated_y` | Berechnet | Flow in Sensor-Y (rad) |
| `integrated_xgyro/ygyro/zgyro` | `gyro * dt` | Gyroskop-Integration |
| `quality` | 0–255 | Textur × Endlichkeit × Vektorgröße |
| `distance` | `relative_alt_m` | Abstand zum Boden |

**Kamera-Ausrichtung (konfigurierbar):**

Für eine nach unten gerichtete Kamera:
```python
FLOW_SWAP_XY = True    # Y-Bild → Sensor-X, X-Bild → Sensor-Y
FLOW_X_SIGN  = -1.0
FLOW_Y_SIGN  =  1.0
```

Wenn Flow-Richtung falsch → `FLOW_X_SIGN`/`FLOW_Y_SIGN` umkehren oder `FLOW_SWAP_XY` ändern.

### DISTANCE_SENSOR

Wird zusammen mit `OPTICAL_FLOW_RAD` gesendet.

| Feld | Wert |
|---|---|
| `min_distance_cm` | 5 |
| `max_distance_cm` | 3000 |
| `current_distance_cm` | `relative_alt_m * 100` (SITL) |
| `type` | `MAV_DISTANCE_SENSOR_LASER` |
| `orientation` | `MAV_SENSOR_ROTATION_PITCH_270` (nach unten) |

> **Hardware-Hinweis:** In der SITL-Version wird der Bodenabstand aus `GLOBAL_POSITION_INT.relative_alt` entnommen — keine echte Distanzmessung. Für Hardware einen echten Downward-Rangefinder anschließen und die `DISTANCE_SENSOR`-Logik durch echte Messwerte ersetzen.

### OBSTACLE_DISTANCE

Wird bei jedem LiDAR-Scan gesendet, mit Rate-Limiting (~10 Hz).

| Feld | Wert |
|---|---|
| `distances` | 72 × uint16 (cm), leer = `max_cm + 1` |
| `increment` | 5° |
| `min_distance_cm` | Aus `msg.range_min` |
| `max_distance_cm` | Aus `msg.range_max` |
| `angle_offset` | -180° (BODY_FRD, Startwinkel) |
| `frame` | `MAV_FRAME_BODY_FRD` |

**Koordinaten-Umrechnung:**
- Gazebo: positive Winkel **gegen** den Uhrzeigersinn (+X vorwärts).
- MAVLink FRD: Sektoren **im** Uhrzeigersinn.
- Umrechnung: `clockwise_deg = -degrees(gazebo_angle_rad)`.

---

## Optical-Flow-Qualitätswert

Der Qualitätswert 0–255 wird aus drei Faktoren berechnet:

```python
textur   = laplacian_variance(gray) / 250.0        # Bildtextur
endlich  = anteil_endlicher_flow_vektoren           # Robustheit
klein    = anteil_flow < 20 px/frame                # Ausreißer
quality  = 255 × clamp(textur) × endlich × klein
```

Niedrige Qualität (<50): homogene Oberfläche, Überbelichtung, oder sehr schnelle Bewegung.

---

## EKF-Integration — Optical Flow ohne GPS

Nach erfolgreichem Test mit GPS kann Flow als Positionsquelle konfiguriert werden:

```
param set EK3_SRC1_POSXY 0    # Keine absolute horizontale Positionsquelle
param set EK3_SRC1_VELXY 5    # Flow als horizontale Geschwindigkeitsquelle
reboot
```

**Reihenfolge für sicheres Aktivieren:**
1. GPS aktiv lassen.
2. Bridge starten, in MAVProxy prüfen: `watch OPTICAL_FLOW_RAD`.
3. Flow-Richtung prüfen: vorwärts fliegen → `integrated_y` positiv (bei Standard-Setup).
4. Falls falsch: `FLOW_X_SIGN`/`FLOW_Y_SIGN`/`FLOW_SWAP_XY` im Bridge-Script anpassen.
5. Nach Bestätigung: `EK3_SRC1_VELXY=5` setzen, neu starten.

---

## Empfang in MAVProxy prüfen

```bash
mavproxy.py --master=tcp:127.0.0.1:5760

# Optical Flow
watch OPTICAL_FLOW_RAD

# Rangefinder
watch DISTANCE_SENSOR

# Hindernisdaten
watch OBSTACLE_DISTANCE

# Proximity-Anzeige auf der Karte
module load proximity
```

---

## Standalone Viewer (ohne Bridge)

Für isolierten Test einzelner Sensoren:

```bash
# LiDAR Polarplot
python3 tools/ui/gz_bridge/lidar_viewer.py --topic /lidar/scan

# Optical Flow Kamerabild
python3 tools/ui/gz_bridge/flow_viewer.py --topic /flow_camera/image
```

Beenden jeweils mit **Q** oder **ESC** im Fenster.

Über den GCS: **SITL-Tab → Gazebo → ▶ OpenCV Fenster**.

---

## Bekannte Einschränkungen

| Einschränkung | Beschreibung |
|---|---|
| DISTANCE_SENSOR Bodenabstand | Nur in SITL aus `relative_alt` — kein echter Downward-Sensor |
| gz.transport Plattform | Nur Linux mit Gazebo Harmonic (`gz-transport13`) |
| Callback-Threading | gz.transport-Callbacks laufen in einem Background-Thread — kein direkter GUI-Zugriff erlaubt |
| EKF-Inertialnavigation | Flow allein ohne GPS ist für Tests geeignet; für Produktion muss die Kamera-Ausrichtung exakt kalibriert sein |

---

## Verwandte Dokumente

- [ArduPilot SITL starten](../setup/px4-sitl.md)
- [API-Referenz: SITLContext-Slots](../api/reference.md#sitlcontext)
- [Release Notes v0.4.0](../release/notes-v0.4.0.md)
