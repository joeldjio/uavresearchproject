# Release Notes — Version 0.4.0

**Release Date:** Juli 2026
**Branch:** `feat/sitl-panel-and-context` + `feat/gz-mavlink-sensor-bridge` → `main`
**Schwerpunkt:** ArduPilot SITL-Panel, Gazebo-Sensor-Overlays, Sensor-Bridge, UI-Übersetzungen

---

## Übersicht

Version 0.4.0 liefert eine vollständig integrierte ArduPilot-SITL-Umgebung im GCS sowie eine direkte Gazebo→ArduPilot MAVLink-Sensor-Bridge. Der gesamte SITL-Lebenszyklus — Build, Konfiguration, Start, Stopp, Parameter, Gazebo-Sensor-Integration — ist jetzt aus einem einzigen Panel heraus steuerbar. Zusätzlich werden Live-LiDAR- und Optical-Flow-Frames als Map-Overlays direkt in der Kartenansicht angezeigt.

---

## Neue Features

### SITL-Panel (`tools/ui/qml/panels/SITLPanel.qml`)

Vollständig überarbeitetes SITL-Panel mit 6 Sub-Tabs:

| Tab | Inhalt |
|---|---|
| **Setup & Build** | Repository-Pfad, Board-/Fahrzeugauswahl, `./waf configure` + `./waf <vehicle>` Build-Buttons |
| **Sim starten** | Fahrzeug, Rahmentyp, Standort, Geschwindigkeit, TCP/UDP-Verbindungsmodus, Peripheriegeräte, Starten/Stoppen |
| **Swarm** | Drohnen-Anzahl, Standort, Peripheriegeräte, Swarm-Start |
| **Parameter** | Bekannte `SIM_*`-Parameter mit Beschreibung und Live-Editing via MAVProxy One-Shot |
| **Gazebo** | LiDAR-Viewer, Optical-Flow-Viewer, Sensor-Stream-Monitor, GStreamer-Routing, Karten-Overlay-Toggles |
| **Debug** | MAVProxy starten, Joystick laden, PreArm Quick-Fix-Karten |

Weitere Verbesserungen:
- Auto-Connect nach SITL-Start (konfigurierbar).
- Peripheriegeräte-Katalog (GPS, LiDAR, Optical-Flow, Rangefinder, Kamera, Beacon) mit Parameter-Overlays.
- Alle UI-Texte auf Deutsch übersetzt (Vehicle→Fahrzeug, Frame→Rahmentyp, Location→Standort usw.).

---

### Gazebo-Sensor-Overlays auf der Karte (`tools/ui/qml/MapView.qml`)

Live-Sensordaten direkt als PIP-Overlays auf der Karte:

| Overlay | Größe | Quelle |
|---|---|---|
| **LiDAR** | 320 × 320 px | `gz.transport13` → `/lidar/scan` → OpenCV Polarplot → JPEG |
| **Optical Flow** | 320 × 240 px | `gz.transport13` → `/flow_camera/image` → OpenCV Farneback → JPEG |
| **Kamera** | 360 × 202 px | Video-Stream-Context (unverändert) |

- Toggle-Buttons direkt auf der Karte (linke untere Ecke).
- Zwei separate `gz.transport`-Nodes (`_gz_node_lidar`, `_gz_node_flow`) — kein Callback-Mixing.
- Anti-Flicker: `_poll_gz_data()` emittiert nur bei tatsächlicher Frame-Änderung (Base64-Vergleich).
- Overlay schließen: Klick auf den PIP-Frame oder Toggle-Button.

---

### Gazebo-Viewer als direkte Subprozesse (`tools/ui/context/sitl_context.py`)

**Problem vorher:** `launchLidarViewer` / `launchFlowViewer` öffneten gnome-terminal → bash → python3. `stopViewers()` sandte SIGTERM an den Terminal-Wrapper, nicht an den Python-Prozess → Fenster blieb offen.

**Fix:** Viewer werden jetzt direkt als `subprocess.Popen(["python3", script, ...])` gestartet.

- `_gz_build_env()`: sourcet das Gazebo-Setup-Bash-Script in einem Child-Prozess und gibt das env-Dict zurück (colcon-Pfade korrekt).
- `stopViewers()`: `terminate()` + `wait(2)` + `kill()`, setzt `_gz_lidar_active`/`_gz_flow_active` zurück.
- `stopAll()`: ebenfalls gz-Overlay-State zurücksetzen.

---

### Gazebo → ArduPilot MAVLink Sensor-Bridge (`tools/ui/gz_viewers/gazebo_mavlink_sensor_bridge.py`)

Neue Bridge-Datei für SITL **und echte Hardware**:

#### Eingänge
| Gazebo-Topic | Typ |
|---|---|
| `/flow_camera/image` | `gz.msgs.Image` |
| `/lidar/scan` | `gz.msgs.LaserScan` |

#### Ausgaben (MAVLink)
| Nachricht | ArduPilot-Parameter |
|---|---|
| `OPTICAL_FLOW_RAD` | `FLOW_TYPE=5` |
| `DISTANCE_SENSOR` (nach unten) | `RNGFND1_TYPE=10`, `RNGFND1_ORIENT=25` |
| `OBSTACLE_DISTANCE` (72 Sektoren) | `PRX1_TYPE=2`, `AVOID_ENABLE=7` |

#### Merkmale
- Farneback Optical Flow mit Qualitätswert (Textur × Endlichkeit × Vektorgröße).
- LiDAR-Koordinaten-Umrechnung: Gazebo CCW → MAVLink FRD CW.
- Rate-Limiting für `OBSTACLE_DISTANCE` (~10 Hz).
- Bodenabstand aus `GLOBAL_POSITION_INT.relative_alt` (SITL-Modus); bei echter Hardware durch echten Downward-Rangefinder ersetzen.
- `--no-display` Headless-Modus.
- SIGTERM-sauber über `signal.signal()`.
- Hardware: `--mavlink /dev/ttyACM0:115200` oder `tcp:192.168.1.10:5760`.

#### Verwendung
```bash
# SITL (Standard)
python3 tools/ui/gz_viewers/gazebo_mavlink_sensor_bridge.py --no-display

# Echte Hardware
python3 tools/ui/gz_viewers/gazebo_mavlink_sensor_bridge.py \
    --mavlink /dev/ttyACM0:115200 \
    --camera-topic /flow_camera/image \
    --lidar-topic /lidar/scan \
    --no-display
```

---

### Sensor-Bridge UI im Gimbal-Tab (`tools/ui/qml/panels/GimbalPanel.qml`)

Neuer Bereich **„SENSOR BRIDGE — GAZEBO → ARDUPILOT"** am Ende des Gimbal-Panels:

- Verbindungsfelder: MAVLink-Adresse, Kamera-Topic, LiDAR-Topic.
- Parameter-Liste (aus `getBridgeParamList()`): alle 8 ArduPilot-Parameter angezeigt.
- Master-Feld für Parameter-Apply.
- Status-LED: grün (aktiv) / rot (Fehler) / grau (gestoppt), 1,5 s Polling.
- **Buttons:**
  - `⚙ Parameter setzen` → `applyBridgeParams()` (MAVProxy One-Shot, kein Terminal-Fenster)
  - `▶ Bridge starten` → `launchSensorBridge()` (direkter Subprozess)
  - `■ Stoppen` → `stopSensorBridge()`
- EKF Non-GPS Hinweis-Block (`EK3_SRC1_POSXY=0`, `EK3_SRC1_VELXY=5`).

---

### Neue `SITLContext`-Slots

| Slot | Signatur | Beschreibung |
|---|---|---|
| `launchSensorBridge` | `(config_json: str)` | Startet Bridge als direkter Subprozess |
| `stopSensorBridge` | `()` | SIGTERM + wait + SIGKILL |
| `getBridgeStatus` | `() → str` | `"stopped"\|"running"\|"error"` |
| `getBridgeParamList` | `() → QVariantList` | Liste `[{name, value}]` |
| `applyBridgeParams` | `(master: str)` | Alle 8 Parameter per MAVProxy One-Shot |

---

### Viewer-Skripte (`tools/ui/gz_viewers/`)

| Datei | Beschreibung |
|---|---|
| `lidar_viewer.py` | Standalone OpenCV LiDAR Polarplot (Q/ESC zum Schließen) |
| `flow_viewer.py` | Standalone OpenCV Optical-Flow-Kamerabild mit Vektorpfeilen |
| `gazebo_mavlink_sensor_bridge.py` | **Neu** — Gazebo→ArduPilot MAVLink-Bridge |

---

### `.gitignore`
`mav.parm`, `*.tlog`, `*.tlog.raw` dauerhaft ausgeschlossen.

---

## UI-Übersetzungen (Deutsch)

### `SITLPanel.qml`
| Vorher | Nachher |
|---|---|
| Vehicle | Fahrzeug |
| Frame | Rahmentyp |
| Location | Standort |
| Speedup | Geschwindigkeit |
| GCS Host | GCS-Host |
| Start Simulation | Simulation starten |
| Stop | Stoppen |
| Stream URL | Stream-URL |

### `GimbalPanel.qml`
| Vorher | Nachher |
|---|---|
| CAMERA CONTROLS | KAMERA STEUERUNG |
| CAMERA SETTINGS | KAMERA EINSTELLUNGEN |
| THERMAL SETTINGS | WÄRME EINSTELLUNGEN |
| CAMERA STATUS | KAMERA STATUS |
| Source | Quelle |
| Profile | Profil |
| Resolution | Auflösung |
| Frame Age | Frame-Alter |
| Dropped Frames | Verlorene Frames |
| No errors | Kein Fehler |

---

## Bugfixes

| Problem | Fix |
|---|---|
| Flow-Viewer-Fenster ließ sich nicht schließen | Viewer jetzt direkte Subprozesse statt Terminal-Wrapper |
| LiDAR-Overlay zeigte nichts | Anti-Flicker-Fix in `_poll_gz_data()` — nur bei Frame-Änderung emittieren |
| Overlay blieb nach `stopViewers()` sichtbar | `_gz_lidar_active`/`_gz_flow_active` + `_last`-Caches werden jetzt zurückgesetzt |
| OpenCV-Fenstername mit Sonderzeichen brachte X11 zum Absturz | Fenstername bereinigt (kein Em-Dash, kein Schrägstrich) |
| gz.transport Callback-Mixing zwischen LiDAR und Flow | Zwei separate Nodes (`_gz_node_lidar`, `_gz_node_flow`) |

---

## Geänderte Dateien

| Datei | Art |
|---|---|
| `tools/ui/context/sitl_context.py` | Geändert |
| `tools/ui/qml/MapView.qml` | Geändert |
| `tools/ui/qml/panels/SITLPanel.qml` | Geändert |
| `tools/ui/qml/panels/GimbalPanel.qml` | Geändert |
| `tools/ui/qml/main.qml` | Geändert |
| `tools/ui/qml/components/CompassInstrument.qml` | Geändert |
| `tools/ui/qml/components/InstrBar.qml` | Geändert |
| `tools/ui/backend.py` | Geändert |
| `tools/ui/context/mission_context.py` | Geändert |
| `tools/ui/gz_viewers/lidar_viewer.py` | **Neu** |
| `tools/ui/gz_viewers/flow_viewer.py` | **Neu** |
| `tools/ui/gz_viewers/gazebo_mavlink_sensor_bridge.py` | **Neu** |
| `skymeshx/control/field_coverage.py` | Geändert |
| `skymeshx/core/connection.py` | Geändert |
| `.gitignore` | Geändert |

---

## Upgrade-Hinweise

1. `gz.transport13` und `gz.msgs10` installieren (für Gazebo-Features):
   ```bash
   pip install gz-transport13 gz-msgs10
   ```
2. `opencv-python` installieren (für Viewer und Bridge):
   ```bash
   pip install opencv-python
   ```
3. Vor der Bridge: ArduPilot-Parameter setzen (einmalig) via **⚙ Parameter setzen** im Gimbal-Tab → Reboot → Bridge starten.

---

## Links

- **GitHub:** https://github.com/joeldjio/skymeshx
- **Dokumentation:** [docs/](../README.md)
- **Gazebo Sensor Bridge:** [docs/features/gazebo-sensor-bridge.md](../features/gazebo-sensor-bridge.md)
- **Vorherige Version:** [v0.3.3](notes-v0.3.3.md)
