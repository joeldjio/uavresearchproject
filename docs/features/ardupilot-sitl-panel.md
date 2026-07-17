# ArduPilot SITL-Panel

> GCS-Tab: **SITL** · Kontext: `tools/ui/context/sitl_context.py`

---

## Übersicht

Das SITL-Panel steuert den gesamten ArduPilot-SITL-Lebenszyklus direkt aus dem GCS. Es besteht aus 6 Sub-Tabs und ermöglicht Build, Konfiguration, Start, Stopp, Parameterverwaltung, Swarm-Betrieb, Gazebo-Sensor-Integration und MAVProxy-Debugging ohne ein einziges Terminal manuell öffnen zu müssen.

---

## Sub-Tabs

### 1. Setup & Build

Verwaltet das ArduPilot-Repository und den Build-Prozess.

| Feld / Button | Beschreibung |
|---|---|
| **Repository-Pfad** | Pfad zum ArduPilot-Verzeichnis (z. B. `~/ardupilot`) |
| **Board** | Zielhardware für den Build (z. B. `sitl`, `CubeBlack`) |
| **Fahrzeug** | ArduCopter, ArduPlane, ArduRover, ArduSub, ArduHeli ... |
| **▶ Build** | Öffnet Terminal: `./waf configure && ./waf <vehicle>` |
| **Clean** | `./waf clean` |
| **Distclean** | `./waf distclean` |

### 2. Sim starten

Konfiguriert und startet eine einzelne SITL-Instanz.

| Feld | Beschreibung |
|---|---|
| **Fahrzeug** | Dropdown (ArduCopter, ArduPlane, ...) |
| **Rahmentyp** | Frame-Liste für das gewählte Fahrzeug (X, quad, hexa, ...) |
| **Standort** | Simulationsstandort (CMAC, Ballarat, GrandCanyon, ...) |
| **Geschwindigkeit** | Sim-Speedup-Faktor (1×, 2×, 5×, 10×) |
| **TCP / UDP** | GCS-Verbindungsmodus und Port |
| **Extra Argumente** | Freitextfeld für beliebige `sim_vehicle.py`-Argumente |
| **Peripheriegeräte** | Katalog aktivierbarer Geräte mit Parameter-Overlays |

**Buttons:**
- `▶ Simulation starten` — öffnet Terminal mit `sim_vehicle.py`
- `■ Stoppen` — SIGTERM an alle SITL-Prozesse
- Laufende Instanzen werden als Liste mit Port und Verbindungsstring angezeigt

**Peripheriegeräte-Katalog:**

| Kategorie | Beispiele |
|---|---|
| Sensor | GPS2, LiDAR/Rangefinder, Optical Flow, Barometer, Compass |
| Umgebung | Wind, Turbulenz, Magnetische Interferenz |
| Kamera | Flow-Kamera, Gimbal-Kamera |
| Display | OSD, Anzeige-Erweiterungen |

### 3. Swarm

Identisch zu Tab 2, aber für mehrere Instanzen gleichzeitig.

| Feld | Beschreibung |
|---|---|
| **Anzahl Drohnen** | 2–20 SITL-Instanzen |
| **Standort** | Gemeinsamer Startstandort |
| **Peripheriegeräte** | Für alle Instanzen gleich |

Auto-Connect: nach dem Start verbindet der GCS automatisch alle Drohnen wenn konfiguriert.

### 4. Parameter

Live-Parameterverwaltung für laufende SITL-Instanz.

- Tabelle bekannter `SIM_*`-Parameter mit Beschreibung, Standardwert und Einheit.
- Inline-Editing: Wert anklicken → neuen Wert eingeben → per MAVProxy One-Shot gesetzt.
- Keine Terminal-Öffnung: Parameter werden via detachiertem `mavproxy.py --cmd "param set ..."` gesetzt.

### 5. Gazebo

Integration mit Gazebo Harmonic Simulation.

| Bereich | Beschreibung |
|---|---|
| **Verfügbare Welten** | Liste erkannter `.sdf`-Welten |
| **Gazebo starten** | Öffnet Terminal: `gz sim <world.sdf>` |
| **SENSOREN (LIDAR / OPTICAL FLOW)** | Topic-Eingabe, Karten-Overlay-Toggle, OpenCV-Fenster-Button |
| **Streaming** | GStreamer-Routing, UDP-Port, Stream in GCS anzeigen |

**Karten-Overlay-Toggles:**
- `◉ Auf Karte (aktiv)` / `◎ Auf Karte zeigen` — startet `gz.transport13`-Subscription in-process, rendert Frames per OpenCV und sendet als JPEG-Base64 an QML.
- **▶ OpenCV Fenster** — öffnet separaten Viewer-Prozess (Q/ESC zum Schließen).

**Stop Viewers:** Beendet alle laufenden Viewer-Prozesse per SIGTERM.

### 6. Debug

Werkzeuge für Diagnose und Quick-Fixes.

| Bereich | Beschreibung |
|---|---|
| **MAVProxy starten** | Master-Feld, --map/--console Checkboxen |
| **Joystick laden** | MAVProxy mit Joystick-Modul |
| **PREARM FIXES** | Vorgefertigte Fix-Karten für häufige PreArm-Fehler |

**PreArm Quick-Fix-Karten:**

| Fix | Befehle |
|---|---|
| Motors: Frame Class/Type | `param set FRAME_CLASS 1; param set FRAME_TYPE 1; reboot` |
| Accel nicht kalibriert | `param set INS_ACCEL_ERROR_THRESHOLD 3; accelcalsimple` |
| Compass nicht gesund | `param set ARMING_CHECK 0` |
| Arming Checks deaktivieren | `param set ARMING_CHECK 0` |
| Arming Checks zurücksetzen | `param set ARMING_CHECK 1` |
| GUIDED → Arm → Takeoff 10m | `mode guided; arm throttle; takeoff 10` |

---

## Live-Overlays auf der Karte

Wenn ein Sensor-Overlay aktiviert ist, erscheint ein PIP-Bild direkt auf der Karte:

| Overlay | Position | Größe | Aktivierung |
|---|---|---|---|
| LiDAR Polarplot | Links unten | 320×320 px | Toggle-Button „◉ LiDAR" auf der Karte |
| Optical Flow | Links unten (rechts vom LiDAR) | 320×240 px | Toggle-Button „◉ Flow" auf der Karte |
| Kamera-PIP | Links unten | 360×202 px | VideoStreamContext |

Die Toggle-Buttons werden auch vom SITL-Panel (Gazebo-Tab) gesteuert — Klick auf „Auf Karte zeigen" synchronisiert den Karten-Toggle.

---

## SITLContext API-Übersicht

Alle Slots sind als `@Slot()` dekoriert und von QML aus aufrufbar.

### Lebenszyklusverwaltung

| Slot | Parameter | Beschreibung |
|---|---|---|
| `launchSimVehicle(json)` | Config-JSON | Startet SITL-Terminal |
| `launchSwarm(json)` | Config-JSON | Startet Swarm-SITL |
| `stopAll()` | — | SIGTERM alle Prozesse, gz-Overlays zurücksetzen |
| `isRunning()` | — | `bool` |
| `sitlStatus()` | — | `"stopped"\|"starting"\|"running"\|"error"` |
| `runningInstances()` | — | `QVariantList` |

### Gazebo-Viewer

| Slot | Parameter | Beschreibung |
|---|---|---|
| `launchLidarViewer(topic)` | Topic-String | Startet `lidar_viewer.py` direkt |
| `launchFlowViewer(topic)` | Topic-String | Startet `flow_viewer.py` direkt |
| `stopViewers()` | — | SIGTERM alle Viewer, Overlays deaktivieren |
| `setSensorOverlay(type, visible)` | `"lidar"\|"flow"`, bool | Karten-Overlay ein/ausschalten |

### Sensor-Bridge

| Slot | Parameter | Beschreibung |
|---|---|---|
| `launchSensorBridge(config_json)` | JSON mit mavlink/topics | Startet Bridge direkt |
| `stopSensorBridge()` | — | SIGTERM Bridge |
| `getBridgeStatus()` | — | `"stopped"\|"running"\|"error"` |
| `getBridgeParamList()` | — | `[{name, value}]` |
| `applyBridgeParams(master)` | MAVLink-Adresse | Parameter per MAVProxy One-Shot |

### Parameter

| Slot | Parameter | Beschreibung |
|---|---|---|
| `setParam(name, value)` | Name, Wert | Einzelnen Parameter setzen |
| `getKnownParams()` | — | JSON-Liste aller SIM_*-Parameter |
| `getPreArmFixes()` | — | Liste der Fix-Karten |
| `launchMavproxyFix(fix_id, master)` | Fix-ID, Adresse | Fix per MAVProxy ausführen |

---

## Verwandte Dokumente

- [Gazebo Sensor Bridge](gazebo-sensor-bridge.md)
- [Release Notes v0.4.0](../release/notes-v0.4.0.md)
- [API-Referenz](../api/reference.md)
