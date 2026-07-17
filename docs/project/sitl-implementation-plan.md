# ArduPilot SITL Tab — Detaillierter Implementierungsplan

**Zieldatei:** `tools/ui/context/sitl_context.py` + `tools/ui/qml/panels/SITLPanel.qml`
**Voraussetzung:** ArduPilot-Repository bereits geklont, Gazebo Harmonic bereits installiert
**Stand:** v1 in Bearbeitung — Python-Backend vollständig implementiert

## Implementierungsstatus

| Item | Status |
|------|--------|
| `sitl_context.py` Phase 1 — vollständiges Backend | ✅ Done |
| `_SITLTracer` → ersetzt durch `TraceLogger.log_ui_event` (source="sitl") | ✅ Done |
| `_open_terminal()` mit 6-Terminal-Fallback + temp-script | ✅ Done |
| `setRepoPath()`, `isRepoValid()`, `loadConfig()`, `saveConfig()` | ✅ Done |
| `runBuild()`, `runClean()`, `runDistclean()` | ✅ Done |
| `launchSimVehicle()` — vollständiger sim_vehicle.py Befehlsgenerator | ✅ Done |
| `launchSwarm()` — count/offset-line/swarm-file/mcast | ✅ Done |
| `launchGazebo()`, `stopGazebo()`, `detectGazeboWorlds()` | ✅ Done |
| `detectStreamingTopics()`, `enableStreaming()`, `launchGstPreview()` | ✅ Done |
| `launchMavproxy()`, `launchMavproxyWithJoystick()`, `launchMavproxyGraph()` | ✅ Done |
| `isJoystickAvailable()`, `isGazeboAvailable()`, `isGstAvailable()` | ✅ Done |
| Persistenz `~/.config/skymeshx/sitl.json` | ✅ Done |
| `setPeripheralDevice()`, `removePeripheralDevice()`, `getPeripheralDevices()` | ✅ Done |
| `getKnownParams()`, `setParam()`, `clearParam()`, `getPendingParams()` | ✅ Done |
| `getPreArmFixes()`, `launchMavproxyFix()` — PreArm-Fix-Scripts | ✅ Done |
| `FRAME_CLASS` / `FRAME_TYPE` im Parameter-Katalog | ✅ Done |
| GStreamer caps — verbose Format (real Gazebo-Output bestätigt) | ✅ Done |
| `detectGazeboWorlds()` — gz_ws + GZ_SIM_RESOURCE_PATH Pfade | ✅ Done |
| `SITLPanel.qml` — Sub-Tab-Navigation (7 Tabs) | ✅ Done |
| Tab 1: Setup & Build | ✅ Done |
| Tab 2: Sim starten | ✅ Done |
| Tab 3: Swarm | ✅ Done |
| Tab 4: Geräte / Peripherals — Toggle-Karten + Pending-Params-Summary | ✅ Done |
| Tab 5: Parameter — SIM_*/FRAME_*/COMPASS_* Browser + Inline-Edit | ✅ Done |
| Tab 6: Gazebo + Video-Stream-Integration | ✅ Done |
| Tab 7: Debug / MAVProxy + PreArm-Fixes + Graph + Trace-Log | ✅ Done |

---

## 1. Architekturübersicht

```
SITLPanel.qml  ←→  SITLContext (Python QObject)  ←→  Subprocesses / Terminal
     │                      │
     │                 SITL log → logMessage Signal → SwarmContext (globaler Log)
     │                 SITL log → sitlLogLine Signal → In-Panel Console
     │                      │
     │                 Trace-Logger (JSONL) → diagnose später
     │
  TabBar Tab "SITL" (orange, #f97316)
```

### Tabs innerhalb des Panels (Sub-Navigation)
```
[ Setup & Build ] [ Sim starten ] [ Swarm ] [ Geräte ] [ Parameter ] [ Gazebo ] [ Debug ]
```

---

## 2. Tab 1 — Setup & Build

### 2.1 Repo-Pfad-Konfiguration

**UI-Elemente:**
- `TextField` mit Placeholder `~/ardupilot` — Pfad zum geklonten ArduPilot-Repo
- Button "Browse…" → öffnet nativen Ordner-Dialog (`FileDialog` QML)
- Grünes ✓ / rotes ✗ Badge: prüft ob `{path}/Tools/autotest/sim_vehicle.py` existiert
- Persistenz: Pfad wird in `~/.config/skymeshx/sitl.json` gespeichert und beim Start geladen

**Python-Seite (`SITLContext`):**
```python
@Slot(str)
def setRepoPath(self, path: str) -> None
    # Validiert, setzt self._repo_path
    # Speichert in ~/.config/skymeshx/sitl.json

@Slot(result=str)
def getRepoPath(self) -> str

@Slot(result=bool)
def isRepoValid(self) -> bool
    # prüft: sim_vehicle.py + wscript + ArduCopter/ existieren
```

### 2.2 Build-Konfiguration

**UI-Elemente:**
- ComboBox "Board" mit Defaults: `sitl`, `MatekH743`, `Pixhawk4`, `CubeOrange`, `SITL_x86_64_linux_gnu`
- Freies TextField zum Editieren des Board-Namens
- ComboBox "Vehicle" (Ziel des Build): `copter`, `plane`, `rover`, `sub`, `heli`
- Readonly TextField: zeigt den generierten Build-Befehl:
  ```
  ./waf configure --board {board}
  ./waf {vehicle}
  ```
- Button **"Build"** (orange) → öffnet externen Terminal mit Build-Befehl
- Button **"Clean"** (grau) → `./waf clean` im externen Terminal
- Button **"Distclean"** (rot) → `./waf distclean`

**Nachricht nach Button-Klick (in-Panel Banner):**
```
🔨 Build läuft in externem Terminal.
   Warte bis "Build OK" erscheint, dann klicke "Sim starten".
```

**Terminal-Launch-Logik (Python):**
```python
@Slot(str, str)
def runBuild(self, board: str, vehicle: str) -> None:
    """
    Öffnet ein neues Terminal-Fenster mit dem Build-Befehl.
    Versucht in dieser Reihenfolge:
      1. gnome-terminal
      2. xterm
      3. konsole
      4. xfce4-terminal
      5. fallback: subprocess direkt (ohne Terminal-Fenster)
    Logs: emit logMessage("INFO", "[SITL][BUILD] Befehl gestartet: …")
    """
    cmd_configure = f"./waf configure --board {board}"
    cmd_build     = f"./waf {vehicle}"
    script = f"cd {self._repo_path} && {cmd_configure} && {cmd_build} ; echo '--- DONE ---' ; read"
    self._open_terminal(script, title=f"ArduPilot Build — {vehicle}")
    self._emit_trace("build_start", {"board": board, "vehicle": vehicle})

@Slot()
def runClean(self) -> None:
    script = f"cd {self._repo_path} && ./waf clean ; echo '--- DONE ---' ; read"
    self._open_terminal(script, title="ArduPilot Clean")
    self._emit_trace("build_clean", {})

def _open_terminal(self, script: str, title: str = "SITL") -> None:
    """
    Öffnet ein Terminal-Fenster. Fallback-Kette:
    gnome-terminal → xterm → konsole → xfce4-terminal.
    Emit logMessage mit verwendetem Terminal und PID.
    """
```

**Trace-Event (JSONL):**
```json
{"ts": 1720000000.123, "event": "build_start", "board": "sitl", "vehicle": "copter"}
{"ts": 1720000120.456, "event": "build_clean", "repo": "/home/user/ardupilot"}
```

---

## 3. Tab 2 — Sim starten

### 3.1 Basis-Konfiguration

**Felder:**
| Feld | Default | Beschreibung |
|------|---------|--------------|
| Vehicle | `ArduCopter` | ComboBox: Copter / Plane / Rover / Sub / Heli |
| Frame | `` (leer) | z.B. `X`, `quad`, `hexa`, `gazebo-iris` |
| Location | `CMAC` | Bekannte Locations oder `lat,lon,alt,heading` |
| Speedup | `1` | ComboBox: 1×/2×/5×/10×/50× |
| Wipe EEPROM | `false` | CheckBox `--wipe-eeprom` |

**GCS-Verbindung:**
| Option | Typ | Default |
|--------|-----|---------|
| Protokoll | RadioButton | TCP / UDP |
| TCP Port | `5760` | `--serial0=tcp:5760` |
| UDP client → GCS | `127.0.0.1:14550` | `--serial0=udpclient:127.0.0.1:14550` |

**Zusatzoptionen:**
- CheckBox `--map` — MAVProxy-Map öffnen
- CheckBox `--console` — MAVProxy-Console öffnen
- CheckBox `--no-mavproxy` — ohne MAVProxy starten (direkter TCP)
- TextField "Extra Args" — frei editierbar

**Generierter Befehl (readonly, kopierbar):**
```
sim_vehicle.py -v ArduCopter -f X --map --console -A "--serial0=tcp:5760"
```

### 3.2 Sim-Start-Button

- Button **"▶ Start Simulation"** (grün)
  → öffnet externen Terminal mit `sim_vehicle.py`-Befehl
  → emittiert `sitlStatusChanged("running")`

- Button **"■ Stop"** (rot) → SIGTERM auf alle SITL-Prozesse

**Python-Logik:**
```python
@Slot(str)
def launchSimVehicle(self, config_json: str) -> None:
    """
    Startet sim_vehicle.py in einem externen Terminal.
    Parsed config_json → baut Kommando → _open_terminal().
    Emittiert:
      logMessage("INFO", "[SITL] sim_vehicle.py gestartet: {cmd}")
      sitlStatusChanged("running")
    Trace: {"event": "sim_start", "vehicle": …, "frame": …, "location": …, "cmd": …}
    """
```

---

## 4. Tab 3 — Swarm

### 4.1 Swarm-Konfiguration

**Felder:**
| Feld | Default | Beschreibung |
|------|---------|--------------|
| Anzahl Drohnen | `5` | SpinBox 1–20 |
| Vehicle | `ArduCopter` | ComboBox |
| Location | `CMAC` | Bekannte Orte oder koordinaten |
| Auto SysID | `true` | CheckBox `--auto-sysid` |
| Multicast | `true` | CheckBox `--mcast` |
| **Offset-Methode** | RadioButton | Linie / Swarm-Config-File |

**Offset Line:**
- Heading (°): `90`
- Abstand (m): `10`
- → `--auto-offset-line {heading},{abstand}`

**Swarm Config File:**
- Path TextField + Browse-Button
- Zeigt Inhalt von `Tools/autotest/swarminit.txt` als Referenz
- → `--swarm {path}`

**Generierter Befehl (readonly):**
```
sim_vehicle.py -v Copter --map --console --count 5 --auto-sysid
  --location CMAC --auto-offset-line 90,10 --mcast
```

**MAVProxy Multi-Vehicle Hinweise:**
- Info-Box: Link zu MAVProxy Multi-Vehicle Doku
- `vehicle 1` / `vehicle 2` Befehlssyntax erklärt

**GCS-Verbindungs-Tabelle** (generiert nach Start):
```
Instance 0  → tcp:127.0.0.1:5760  SYSID: 1
Instance 1  → tcp:127.0.0.1:5770  SYSID: 2
Instance 2  → tcp:127.0.0.1:5780  SYSID: 3
...
```

**Swarm Connect Button:**
- "🔗 Alle verbinden" → iteriert Ports und ruft `swarm.connectDrone(id, endpoint)` auf

---

## 5. Tab 4 — Geräte (Peripherals)

Basiert auf: https://ardupilot.org/dev/docs/adding_simulated_devices.html

### 5.1 Gerät-Kategorien

#### A) Start-Parameter-Geräte (werden direkt in sim_vehicle.py eingebaut)
Diese werden beim nächsten Sim-Start automatisch hinzugefügt.

| Gerät | Parameter/Flag | Kategorie |
|-------|---------------|-----------|
| Gimbal (2-Axis) | `-A --sim-instance0-params=SIM_SHUTTER_COUNT=0,SIM_RATE_HZ=200` | camera |
| OSD (Onscreen Display) | `--osd` | display |
| GPS (zweites) | `--sim-instance0-params=SIM_GPS2_ENABLE=1` | sensor |
| Lidar / Rangefinder | `SIM_SONAR_SCALE`, SERIAL-config | sensor |
| Baro (zweites) | `SIM_BARO_COUNT=2` | sensor |
| Windspeed-Sensor | `SIM_WIND_SPD`, `SIM_WIND_DIR` | environment |
| Magnetometer | `COMPASS_ENABLE=1` | sensor |

**UI:**
- CheckBox-Liste mit je einem "Konfigurieren"-Button
- Aktive Geräte werden farbig hervorgehoben
- Beim Klick auf "Konfigurieren": erweitertes Formular mit gerätespezifischen Parametern

#### B) MAVProxy-Runtime-Geräte (erfordern Neustart)
MAVProxy muss zuerst laufen, Parameter setzen, dann SITL neu starten.

**Workflow anzeigen (Info-Box):**
```
1. Sim starten (ohne Gerät)
2. Im MAVProxy-Terminal: {parameter setzen}
3. Sim stoppen (Stop-Button)
4. Sim erneut starten (Parameter persistieren in EEPROM)
```

Konkrete Beispiele:
- **I2C Compass:** `param set COMPASS_EXTERNAL 1` → Neustart
- **Barometer Kalibrierung:** `param set BARO_FIELD_ELV 488`
- **Rangefinder Setup:** `param set RNGFND1_TYPE 10`, Serial-Config

#### C) Gazebo-Plugins (nur im Gazebo-Modus)
Werden im Gazebo-Tab konfiguriert (→ Tab 6).

### 5.2 Geräte-State (Python)

```python
# In SITLContext
_peripheral_devices: Dict[str, dict] = {}
# z.B. {"gimbal": {"enabled": True, "params": {"SIM_RATE_HZ": 200}}}

@Slot(str, str)
def setPeripheralDevice(self, device_id: str, config_json: str) -> None:
    """Aktiviert ein Gerät mit Konfiguration. Wird beim nächsten Start eingebaut."""
    self._peripheral_devices[device_id] = json.loads(config_json)
    self._emit_trace("peripheral_set", {"device": device_id, "config": config_json})
    self.peripheralDevicesChanged.emit()

@Slot(str)
def removePeripheralDevice(self, device_id: str) -> None: ...

@Slot(result=str)
def getPeripheralDevices(self) -> str:
    """Gibt JSON der aktiven Geräte zurück."""
```

---

## 6. Tab 5 — Parameter

Basiert auf: https://ardupilot.org/dev/docs/sitl-parameters.html

### 6.1 Parameter-Browser

**UI:**
- Search-TextField (Echtzeit-Filterung)
- TreeView nach Kategorie (SIM_*, FLIGHT_*, COMPASS_*, etc.)
- Jede Zeile: `PARAM_NAME` | aktueller Wert | Einheit | Beschreibung
- Double-click → inline editieren → `set`-Button

**Kategorien:**
```
SIM_*        — Simulation-Parameter (Wind, GPS, Sensoren)
FLIGHT_*     — Flugregler-Parameter
COMPASS_*    — Magnetometer
BARO_*       — Barometer
RNGFND_*     — Rangefinder
CAM_*        — Kamera
MNT_*        — Gimbal/Mount
```

**Python-Seite:**

```python
# Bekannte SIM_* Parameter (Subset für schnellen Zugriff)
_SIM_PARAMS = {
    "SIM_WIND_SPD":    {"default": 0, "unit": "m/s",    "desc": "Windgeschwindigkeit"},
    "SIM_WIND_DIR":    {"default": 0, "unit": "deg",    "desc": "Windrichtung (0=Nord)"},
    "SIM_WIND_TURB":   {"default": 0, "unit": "",       "desc": "Turbulenz-Amplitude"},
    "SIM_GPS_DELAY":   {"default": 1, "unit": "ticks",  "desc": "GPS-Verzögerung"},
    "SIM_GPS_NOISE":   {"default": 0, "unit": "m",      "desc": "GPS-Rauschen"},
    "SIM_BARO_RND":    {"default": 0, "unit": "Pa",     "desc": "Baro-Rauschen"},
    "SIM_DRIFT_SPEED": {"default": 0, "unit": "m/s",    "desc": "Drift-Geschwindigkeit"},
    "SIM_RATE_HZ":     {"default": 1200, "unit": "Hz",  "desc": "Simulationsrate"},
    "SIM_SONAR_SCALE": {"default": 1, "unit": "",       "desc": "Sonar-Skalierung"},
}

@Slot(str, str)
def setParam(self, name: str, value: str) -> None:
    """
    Setzt MAVLink-Parameter via MAVLink PARAM_SET (über aktive Verbindung).
    Fallback: in pending_params speichern → wird beim nächsten MAVProxy-Start
    als --param gesetzt.
    Trace: {"event": "param_set", "name": …, "value": …}
    """

@Slot(result=str)
def getKnownParams(self) -> str:
    """Gibt JSON aller bekannten SIM_* Parameter zurück."""
```

---

## 7. Tab 6 — Gazebo

### 7.1 Gazebo-Erkennung

```python
@Slot(result=bool)
def isGazeboAvailable(self) -> bool:
    """Prüft ob 'gz' CLI-Tool erreichbar ist."""
    return shutil.which("gz") is not None

@Slot(result="QVariantList")
def detectGazeboWorlds(self) -> List[str]:
    """
    Scannt bekannte Pfade nach .sdf Dateien:
    - ~/ardupilot_gazebo/worlds/
    - /usr/share/gazebo*/worlds/
    - ~/.gz/*/worlds/
    """
```

### 7.2 Gazebo-Konfiguration

**UI:**
- Badge: Gazebo verfügbar ✓ / nicht gefunden ✗
- ComboBox "World": `iris_runway.sdf` (default), dropdown aller gefundenen SDF-Dateien
- TextField "SDF-Pfad": frei editierbar
- TextField "Verbosity": `-v4` (default)
- CheckBox "Model JSON": `--model JSON` (für ArduPilot-Plugin)
- ComboBox "Vehicle": `ArduCopter` (mit `-f gazebo-iris`)

**Befehle (readonly, zweiteilig):**
```
# Terminal 1 — Gazebo starten:
gz sim -v4 -r iris_runway.sdf

# Terminal 2 — SITL starten:
sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --map --console
```

**Start-Buttons:**
- Button **"▶ Start Gazebo"** → öffnet Terminal 1
- Button **"▶ Start SITL (Gazebo-Mode)"** → öffnet Terminal 2
- Button **"■ Stop Alles"**

### 7.3 Kamera-Streaming (GStreamer)

**Erkennung:**
```python
@Slot(result=bool)
def isGstAvailable(self) -> bool:
    return shutil.which("gst-launch-1.0") is not None

@Slot(result="QVariantList")
def detectStreamingTopics(self) -> List[str]:
    """
    Führt: gz topic -l | grep -i streaming
    Gibt Liste der verfügbaren Streaming-Topics zurück.
    Timeout: 3 Sekunden.
    """
```

**UI:**
- Section "GStreamer Video Streaming"
- UDP-Host: `127.0.0.1`
- UDP-Port: `5600`
- ComboBox Topic (aus `detectStreamingTopics()`)
- Button **"Enable Streaming"** → führt aus:
  ```
  gz topic -t {topic}/enable_streaming -m gz.msgs.Boolean -p "data: 1"
  ```
- Button **"▶ GStreamer Preview"** → öffnet externes Terminal (gst-launch-1.0)
- **Neu: "In-App anzeigen"-Bereich** → nutzt `videoStream` (bereits vorhanden)

### 7.3a In-App Video-Stream (VideoStreamContext-Integration)

Das GCS hat einen voll funktionsfähigen `VideoStreamContext` mit:
- `videoStream.startStream(url, droneId, target)` — `target` = `"map"` oder `"gimbal"`
- Map-Tab zeigt PIP (bottom-right) wenn `activeTarget === "map"`
- Gimbal-Tab zeigt Vollbild wenn `activeTarget === "gimbal"`

**UI-Elemente (im Gazebo-Tab):**

```
┌─ In-App Stream ───────────────────────────────────────┐
│  URL:  [udp://0.0.0.0:5600          ]                 │
│  Ziel: ○ Map (PIP)   ● Gimbal (Vollbild)               │
│                                                       │
│  [ ▶ Stream in GCS anzeigen ]  [ ■ Stop ]             │
│                                                       │
│  Status: ● receiving  fps: 30  target: gimbal         │
└───────────────────────────────────────────────────────┘
```

**QML-Logik (nutzt bereits vorhandene API):**

```qml
// "Stream in GCS anzeigen" Button
onClicked: {
    if (typeof videoStream === "undefined" || !videoStream) return
    var url = streamUrlField.text   // z.B. "udp://0.0.0.0:5600"
    var droneId = root.selectedDroneId || "sitl_drone"
    var target = mapTargetRadio.checked ? "map" : "gimbal"
    videoStream.startStream(url, droneId, target)
}

// "Stop" Button
onClicked: {
    if (typeof videoStream !== "undefined" && videoStream)
        videoStream.stopStream(root.selectedDroneId || "sitl_drone")
}

// Status-Badge
property var _vsStatus: {
    if (typeof videoStream === "undefined" || !videoStream) return {}
    var did = root.selectedDroneId || "sitl_drone"
    return videoStream.getVideoStatus(did) || {}
}
```

**Keine Backend-Änderungen nötig** — `videoStream` ist bereits als QML-Context-Property registriert
und vollständig funktionsfähig (wie im ROS2-Tab gezeigt).

**Wichtig: Nicht gleichzeitig Map + Gimbal** — `startStream` setzt `activeTarget` global.
Nur ein Target kann gleichzeitig aktiv sein (durch `setActiveTarget()` im VideoStreamContext sichergestellt).

### 7.4 Trace-Events Gazebo

```json
{"ts": …, "event": "gazebo_start",  "world": "iris_runway.sdf", "verbosity": 4}
{"ts": …, "event": "sitl_gz_start", "vehicle": "ArduCopter", "frame": "gazebo-iris"}
{"ts": …, "event": "stream_enable", "topic": "/world/iris_runway/…/enable_streaming"}
```

---

## 8. Tab 7 — Debug & Tools

### 8.1 MAVProxy-Befehle

**Problem:** MAVProxy läuft im externen Terminal, direkter Zugriff nicht möglich.

**Lösung — MAVProxy Script-Datei:**
```python
def _write_mavproxy_script(self, commands: List[str]) -> Path:
    """
    Schreibt Befehle in eine temporäre `.scr`-Datei.
    Terminal-Start: mavproxy.py --master=tcp:127.0.0.1:5760 --script={path}
    """
```

**UI — Befehl-Shortcuts:**
| Button | Befehl |
|--------|--------|
| Load Joystick | `module load joystick` |
| Load Graph | `module load graph` |
| Graph: altitude | `graph VFR_HUD.alt` |
| Graph: airspeed | `graph VFR_HUD.airspeed` |
| ARM | `arm throttle` |
| Disarm | `disarm` |
| Mode GUIDED | `mode guided` |
| Takeoff 10m | `takeoff 10` |

**MAVProxy starten (Button):**
```
mavproxy.py --master=tcp:127.0.0.1:5760 --console --map
```
→ öffnet externes Terminal

### 8.2 Joystick

```python
@Slot(result=bool)
def isJoystickAvailable(self) -> bool:
    """Prüft ob /dev/input/js0 existiert."""

@Slot()
def launchMavproxyWithJoystick(self) -> None:
    """
    Startet MAVProxy mit Joystick-Modul:
    mavproxy.py --master=tcp:127.0.0.1:5760 --console --map
                --load-module joystick
    """
```

### 8.3 Graphing

```python
@Slot(str)
def launchMavproxyGraph(self, field: str) -> None:
    """
    Startet MAVProxy mit Graph-Modul für ein bestimmtes Feld:
    mavproxy.py --master=tcp:127.0.0.1:5760 --console
                --load-module graph --cmd "graph {field}"
    Bekannte Felder: VFR_HUD.alt, VFR_HUD.airspeed, ATTITUDE.roll, etc.
    """
```

### 8.4 Diagnose-Log-Viewer

- ListView zeigt letzte N Events aus dem SITL Trace-Log
- Filter-TextField
- Button "Log kopieren" → Clipboard
- Button "Log öffnen" → öffnet JSONL in System-Editor

---

## 9. Python-Backend — Vollständige API v1

### 9.1 Neue Signals

```python
# Bereits vorhanden:
sitlStatusChanged    = Signal(str)       # "stopped"|"starting"|"running"|"error"
sitlLogLine          = Signal(str)       # eine Zeile SITL-Output
sitlInstancesChanged = Signal()
logMessage           = Signal(str, str)  # (level, text)

# Neu in v1:
buildStatusChanged   = Signal(str)       # "idle"|"building"|"done"|"error"
repoValidChanged     = Signal(bool)
peripheralDevicesChanged = Signal()
paramChanged         = Signal(str, str)  # (name, value)
gazeboStatusChanged  = Signal(str)       # "stopped"|"running"|"error"
streamingTopicsReady = Signal("QVariantList")  # Liste der gefundenen Topics
```

### 9.2 Neue Slots

```python
# Repo & Build
setRepoPath(path: str)
getRepoPath() -> str
isRepoValid() -> bool
runBuild(board: str, vehicle: str)
runClean()
runDistclean()

# Simulation
launchSimVehicle(config_json: str)
stopAll()
stopInstance(index: int)
sitlStatus() -> str
isRunning() -> bool
runningInstances() -> list

# Swarm
launchSwarm(config_json: str)

# Geräte
setPeripheralDevice(device_id: str, config_json: str)
removePeripheralDevice(device_id: str)
getPeripheralDevices() -> str

# Parameter
setParam(name: str, value: str)
getKnownParams() -> str

# Gazebo
isGazeboAvailable() -> bool
detectGazeboWorlds() -> list
launchGazebo(config_json: str)
stopGazebo()
isGstAvailable() -> bool
detectStreamingTopics() -> list
enableStreaming(topic: str)
launchGstPreview(host: str, port: int)

# Debug / MAVProxy
launchMavproxy(config_json: str)
launchMavproxyWithJoystick()
launchMavproxyGraph(field: str)
isJoystickAvailable() -> bool

# Persistenz
loadConfig() -> str          # JSON der gespeicherten Einstellungen
saveConfig(config_json: str) # in ~/.config/skymeshx/sitl.json

# Diagnose
getTraceLog(max_lines: int) -> str   # JSONL Inhalt
clearTraceLog()
```

### 9.3 Persistenz-Schema (`~/.config/skymeshx/sitl.json`)

```json
{
  "repo_path": "/home/user/ardupilot",
  "build": {
    "board": "sitl",
    "vehicle": "copter"
  },
  "sim": {
    "vehicle": "ArduCopter",
    "frame": "",
    "location": "CMAC",
    "speedup": 1,
    "protocol": "tcp",
    "tcp_port": 5760,
    "udp_host": "127.0.0.1",
    "udp_port": 14550,
    "use_map": true,
    "use_console": true,
    "no_mavproxy": false,
    "extra_args": ""
  },
  "swarm": {
    "count": 5,
    "auto_sysid": true,
    "mcast": true,
    "offset_mode": "line",
    "offset_heading": 90,
    "offset_spacing": 10,
    "swarm_file": ""
  },
  "gazebo": {
    "world": "iris_runway.sdf",
    "verbosity": 4,
    "use_json_model": true,
    "stream_host": "127.0.0.1",
    "stream_port": 5600
  },
  "peripheral_devices": {},
  "known_params": {}
}
```

---

## 10. Trace- und Diagnose-Logging

### 10.1 Log-Datei — ✅ Implementiert (abweichend vom ursprünglichen Plan)

**Ursprünglich:** Separate `~/.local/share/skymeshx/sitl_trace.jsonl`

**Tatsächliche Implementierung:** SITL-Events werden in die **bestehende TraceLogger-Session**
geschrieben → `trace_runs/<session>/ui_events.jsonl` als `source="sitl"`.

```python
# In SITLContext._trace():
TraceLogger.get().log_ui_event(f"sitl/{event_type}", {**data, "source": "sitl"})
```

Jede Zeile in `ui_events.jsonl` folgt dem bestehenden Schema:
```json
{"ts": "2026-07-02T22:20:34+02:00", "type": "sitl/repo_set",    "source": "sitl", "data": {"path": "/home/user/ardupilot", "valid": true}}
{"ts": "2026-07-02T22:21:00+02:00", "type": "sitl/build_start", "source": "sitl", "data": {"board": "sitl", "vehicle": "copter", "cmd": "..."}}
{"ts": "2026-07-02T22:22:00+02:00", "type": "sitl/sim_start",   "source": "sitl", "data": {"vehicle": "ArduCopter", "protocol": "tcp", "port": 5760}}
{"ts": "2026-07-02T22:25:00+02:00", "type": "sitl/swarm_start", "source": "sitl", "data": {"count": 5, "location": "CMAC"}}
{"ts": "2026-07-02T22:30:00+02:00", "type": "sitl/gazebo_start","source": "sitl", "data": {"world": "iris_runway.sdf"}}
{"ts": "2026-07-02T22:35:00+02:00", "type": "sitl/sim_exit",    "source": "sitl", "data": {"reason": "terminal_closed"}}
```

Filterung nachträglich: `[r for r in rows if r.get("source") == "sitl"]`

Abfrage per Slot: `sitl.getRecentTraceLogs(50)` → letzte 50 SITL-Events

**Vorteil:** Alle Events (SITL, Mission, ROS2, Video) in einer Datei pro Session → einfachere Diagnose.

### 10.3 Log-Level-Konvention

| Level | Verwendung |
|-------|-----------|
| `INFO` | Normale Operationen (Sim gestartet, Parameter gesetzt) |
| `WARN` | Prozess unerwartet beendet, Timeout, Binary nicht gefunden |
| `ERROR` | Kritischer Fehler (falscher Pfad, Build fehlgeschlagen, kein Terminal verfügbar) |
| `DEBUG` | Detaillierte SITL-Stdout-Zeilen (nur im Debug-Tab sichtbar, nicht im globalen Log) |

**Filterung:**
- SITL-Stdout-Zeilen → nur in `sitlLogLine` Signal (Panel-Konsole), NICHT in `logMessage` (globaler Log)
- Build/Start/Stop-Events → in `logMessage` (globaler Log) UND `sitlLogLine`
- Fehler → immer in `logMessage`

---

## 11. UI-Komponenten-Details

### 11.1 Sub-Tab-Navigation

```qml
// In SITLPanel.qml — Tab-Bar oben
Row {
    id: subTabBar
    spacing: 0
    property int currentSubTab: 0
    
    Repeater {
        model: ["Setup & Build", "Sim starten", "Swarm", "Geräte", "Parameter", "Gazebo", "Debug"]
        delegate: SITLTabButton { ... }
    }
}
```

### 11.2 Befehlsvorschau-Komponente

Wiederverwendbar in Tab 2, 3, 6:
```qml
// SITLCommandPreview.qml
Rectangle {
    property string cmd: ""
    // Readonly ScrollView mit monospace-Text
    // Copy-Button rechts oben
    // Syntax-Highlighting: --flags blau, Werte gelb
}
```

### 11.3 Banners

```qml
// Build-In-Progress Banner
Rectangle {
    visible: sitlOk() && sitl.buildStatus() === "building"
    color: "#1c1400"
    border.color: "#f59e0b"
    Text { text: "🔨 Build läuft im externen Terminal.\nWarte bis fertig, dann → 'Sim starten'." }
}
```

### 11.4 Gerät-Karte (Peripheral Card)

```qml
// SITLPeripheralCard.qml
Rectangle {
    property string deviceId: ""
    property string label: ""
    property bool enabled: false
    property string configSummary: ""
    // Toggle-Switch + Label + Config-Button + Restart-Hinweis-Badge
}
```

---

## 12. Externe Terminal-Strategie

### 12.1 Terminal-Erkennung (Python)

```python
_TERMINAL_CANDIDATES = [
    ("gnome-terminal", ["gnome-terminal", "--title={title}", "--", "bash", "-c", "{script}"]),
    ("xterm",          ["xterm", "-T", "{title}", "-e", "bash", "-c", "{script}"]),
    ("konsole",        ["konsole", "--title", "{title}", "-e", "bash", "-c", "{script}"]),
    ("xfce4-terminal", ["xfce4-terminal", "--title={title}", "-e", "bash -c '{script}'"]),
    ("lxterminal",     ["lxterminal", "--title={title}", "-e", "bash -c '{script}'"]),
    ("tilix",          ["tilix", "-t", "{title}", "-e", "bash -c '{script}'"]),
]

def _open_terminal(self, script: str, title: str = "SITL") -> Optional[subprocess.Popen]:
    for name, template in _TERMINAL_CANDIDATES:
        if shutil.which(name):
            cmd = [
                part.format(title=title, script=script)
                for part in template
            ]
            try:
                proc = subprocess.Popen(cmd)
                self._emit_log("INFO", f"[SITL] Terminal '{name}' geöffnet (PID {proc.pid})")
                self._emit_trace("terminal_open", {"terminal": name, "title": title, "pid": proc.pid})
                return proc
            except Exception as exc:
                self._emit_log("WARN", f"[SITL] Terminal '{name}' fehlgeschlagen: {exc}")
    # Kein Terminal gefunden
    self._emit_log("ERROR", "[SITL] Kein Terminal-Emulator gefunden (gnome-terminal / xterm / konsole erwartet)")
    return None
```

### 12.2 Script-Template für Build

```bash
#!/bin/bash
set -e
cd /home/user/ardupilot
echo "=== ./waf configure --board sitl ==="
./waf configure --board sitl
echo "=== ./waf copter ==="
./waf copter
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ BUILD FERTIG — Drücke ENTER zum Schließen"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read
```

### 12.3 Script-Template für SITL-Start

```bash
#!/bin/bash
cd /home/user/ardupilot
echo "=== ArduPilot SITL starten ==="
python3 Tools/autotest/sim_vehicle.py -v ArduCopter -f X --map --console -A "--serial0=tcp:5760"
# Terminal bleibt offen wenn sim_vehicle endet
echo "--- SITL beendet ---"
read
```

---

## 13. Implementierungs-Reihenfolge

### Phase 1 — Basis-Refactoring (diese PR)
1. [ ] `SITLContext` erweitern: `setRepoPath`, `isRepoValid`, `loadConfig`, `saveConfig`
2. [ ] `_SITLTracer` Klasse hinzufügen
3. [ ] `_open_terminal` mit Fallback-Kette implementieren
4. [ ] `runBuild`, `runClean`, `runDistclean` implementieren
5. [ ] `launchSimVehicle` (ersetzt bisheriges `launch`) implementieren
6. [ ] Bestehende direkte `subprocess.Popen`-Launch durch Terminal-Launch ersetzen

### Phase 2 — Panel Refactoring
7. [ ] Sub-Tab-Navigation in `SITLPanel.qml` einbauen
8. [ ] Tab 1 (Setup & Build) vollständig implementieren
9. [ ] Tab 2 (Sim starten) mit vollständiger Konfiguration
10. [ ] Befehlsvorschau-Komponente (`SITLCommandPreview`)
11. [ ] Build-In-Progress-Banner

### Phase 3 — Swarm
12. [ ] Tab 3 (Swarm) Konfiguration + Befehlsgenerator
13. [ ] `launchSwarm` in Python
14. [ ] GCS-Verbindungs-Tabelle nach Start

### Phase 4 — Geräte & Parameter
15. [ ] Tab 4 (Geräte) Peripheral-Karten
16. [ ] `setPeripheralDevice` / `removePeripheralDevice`
17. [ ] Tab 5 (Parameter) SIM_*-Browser
18. [ ] `getKnownParams` / `setParam`

### Phase 5 — Gazebo
19. [ ] Tab 6 (Gazebo) — Weltauswahl, dual-Terminal-Start
20. [ ] Streaming-Topic-Erkennung
21. [ ] GStreamer-Preview-Button

### Phase 6 — Debug
22. [ ] Tab 7 (Debug) — MAVProxy-Shortcuts, Joystick, Graph
23. [ ] Trace-Log-Viewer
24. [ ] `launchMavproxy*`-Methoden

---

## 14. Abhängigkeiten & Voraussetzungen

| Komponente | Voraussetzung |
|-----------|--------------|
| Build | ArduPilot-Repo geklont, Python 3, cmake, gcc |
| SITL Start | `sim_vehicle.py` in Repo (`Tools/autotest/`) |
| Gazebo | `gz` CLI verfügbar, `ardupilot_gazebo` Plugin installiert |
| Streaming | `gst-launch-1.0`, GStreamer-Plugins (`gst-plugins-good`, `gst-libav`) |
| Joystick | `/dev/input/js0` vorhanden, MAVProxy Joystick-Module |
| MAVProxy | `mavproxy.py` in PATH |
| Externer Terminal | Mindestens eines: gnome-terminal / xterm / konsole |

---

## 15. Tests

### Unit Tests (`tests/test_sitl_context.py`)
```python
# Markierung: @pytest.mark.unit
def test_repo_validation_valid_path()
def test_repo_validation_invalid_path()
def test_build_command_generation()
def test_swarm_command_generation()
def test_sim_vehicle_command_generation_tcp()
def test_sim_vehicle_command_generation_udp()
def test_terminal_candidate_ordering()
def test_config_serialization()
def test_tracer_writes_jsonl()
def test_peripheral_device_management()
```

### Integration Tests (`tests/test_sitl_integration.py`)
```python
# Markierung: @pytest.mark.sitl
# Opt-in: SITL_AVAILABLE=1
def test_sitl_launch_and_heartbeat()
def test_sitl_swarm_launch_5_drones()
def test_gazebo_start_with_sitl()
```

---

## 16. Offene Fragen / Entscheidungen

| Frage | Optionen | Empfehlung |
|-------|---------|-----------|
| MAVProxy-Befehle senden | Script-Datei / Named Pipe / `expect` | Script-Datei (einfachste) |
| Parameter setzen | MAVLink direkt / MAVProxy Script | MAVLink via bestehenden `MAVLinkConnection` |
| Locations-Datenbank | Hardcodiert / von MAVProxy laden | Hardcodiert (Top 20) + Custom-Eingabe |
| Terminal PID tracken | Ja (für Stop) | Ja, in `_terminal_procs: List[Popen]` |
| Repo-Pfad-Validierung | Nur `sim_vehicle.py` prüfen | `sim_vehicle.py` + `wscript` + `ArduCopter/` |
