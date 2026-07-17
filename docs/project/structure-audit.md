# SkyMeshX — Projektstruktur Audit

> Stand: 2026-07-15 | Branch: `feat/logging-and-tracing`

---

## 1 — Root-Verzeichnis (falsch platzierte Dateien)

| Datei / Ordner | Problem | Zielaktion |
|---|---|---|
| `test_solar_ui.py` | Test-Datei im Root, nicht in `tests/` | → `tests/test_solar_ui.py` |
| `mav.parm` | MAVProxy-Artefakt, wird bei jedem Connect überschrieben | bereits in `.gitignore` — aus Git entfernen |
| `mav.tlog`, `mav.tlog.raw` | MAVProxy-Telemetrie-Artefakt | bereits in `.gitignore` — aus Git entfernen |
| `BUGFIX_PLAN.md` | Internes Planungsdokument gehört nicht ins Root | → `docs/project/bugfix-plan.md` |
| `MIGRATION.md` | Migrationsnotizen gehören in `docs/` | → `docs/project/migration.md` |
| `plots/` (3 PNG-Dateien) | Generierte Plots gehören nicht ins Repo | `.gitignore`: `plots/` hinzufügen |

---

## 2 — tools/ (Durcheinander verschiedener Tool-Kategorien)

| Datei | Problem | Zielaktion |
|---|---|---|
| `rebrand_uav.py`, `rebrand_github.py`, `rebrand_imports.py`, `rebrand_batch.py`, `do_rebrand.py` | 5 Rebrand-Skripte — einmalige Migrations-Tools die abgeschlossen sind | → `tools/migrations/` |
| `migrate_to_pyside6.py` | Migrations-Skript, bereits erledigt | → `tools/migrations/` |
| `plot_flight.py`, `plot_swarm.py`, `live_swarm_map.py` | Visualisierungs-Tools, gehören zusammen | → `tools/analysis/` |
| `analyze_trace.py`, `benchmark_bag_compression.py`, `profile_memory.py` | Analyse- & Profiling-Tools | → `tools/analysis/` |
| `launch_px4_sitl.sh` | Shell-Skript, allein im `tools/` Root | → `tools/scripts/` |
| `tools/installer/` | ✅ OK — eigener Unterordner | kein Handlungsbedarf |
| `tools/ui/` | ✅ OK — GCS-Anwendung sinnvoll getrennt | kein Handlungsbedarf |

---

## 3 — tools/ui/ (Legacy-Reste im Package)

| Datei | Problem | Zielaktion |
|---|---|---|
| `dashboard_tab.py`, `experiment_tab.py`, `log_tab.py`, `map_tab.py`, `safety_tab.py`, `swarm_tab.py`, `main_window.py`, `widgets.py`, `style.py` | Altes QWidget-UI (`--legacy` Flag) — nicht vom neuen Code getrennt | → `tools/ui/legacy/` als eigenes Unterpaket |
| `gz_bridge/` (enthält `gazebo_mavlink_sensor_bridge.py`) | Name ist irreführend — enthält nicht nur Viewer sondern auch die Bridge | → `tools/ui/gz_bridge/` umbenennen |
| `app_logger.py` | ✅ Neu erstellt, korrekt platziert | bleibt |

---

## 4 — skymeshx/ SDK (größtenteils OK)

| Modul | Bewertung | Aktion |
|---|---|---|
| `skymeshx/communication/` | Mögliche Überlappung mit `core/` und `ros/` | Inhalt prüfen, ggf. in `core/` zusammenführen |
| `skymeshx/data/` | Name zu generisch | Inhalt prüfen, ggf. umbenennen |
| `skymeshx/simulation/` | ✅ OK — `sitl.py`, `px4_gazebo.py`, `replay.py` | kein Handlungsbedarf |
| alle anderen Module | ✅ OK | kein Handlungsbedarf |

---

## 5 — logs/ (flache Struktur, ~200 Dateien auf einer Ebene)

| Ist-Zustand | Problem | Zielzustand |
|---|---|---|
| `20260702_*_drone1_events.jsonl` (~200 Dateien) | Alle Drone-Logs flach gemischt mit anderen Dateien | → `logs/drone/` |
| `export_*.txt` (4 Dateien) | Unklar was diese Exports sind, liegen flach | → `logs/export/` |
| `logs/mavproxy/` (leer) | ✅ OK — korrekt benannt | bleibt, wird von MAVProxy befüllt |
| `logs/sitl_sensor/` (leer) | ✅ OK — korrekt benannt | bleibt |
| `logs/batterylogs/` | ✅ OK — eigener Unterordner | bleibt |
| `logs/app/` | fehlt noch | → von `app_logger.py` erstellt (`gcs.log`, rotierend) |
| `logs/bridge/` | fehlt noch | → Bridge stdout/stderr |
| `logs/sitl/` | fehlt noch | → ArduPilot SITL stdout/stderr |

---

## 6 — docs/ (ein paar Ausreißer im Root)

| Datei | Problem | Zielaktion |
|---|---|---|
| `docs/implementation-plan-camera-video-streaming.md` | Liegt in `docs/`, alle anderen Plans sind in `docs/project/` | → `docs/project/` |
| `docs/SITL_IMPLEMENTATION_PLAN.md` | Gleicher Fehler — liegt in `docs/` Root | → `docs/project/` |
| `docs/SOFTWARE_DOCUMENTATION.md` | ✅ OK — Hauptdoku, Root ist akzeptabel | bleibt |

---

## 7 — tests/ (größtenteils OK)

| Problem | Aktion |
|---|---|
| `test_solar_ui.py` liegt im Root-Verzeichnis | → `tests/test_solar_ui.py` verschieben |
| Alle anderen Tests bereits korrekt in `tests/` | ✅ kein Handlungsbedarf |

---

## 8 — Zielstruktur (nach Bereinigung)

```
skymeshx/                     # SDK-Paket (installierbar via pip)
  core/                       # MAVLink, Telemetrie, FSM, TraceLogger
  sdk/                        # öffentliche API (Drone, SwarmAPI)
  models/                     # GenericUAV, ObservationUAV
  safety/                     # APF, Collision, Battery
  simulation/                 # SITL, PX4Gazebo, Replay
  autopilot/                  # ArduPilot/PX4 backends
  control/                    # Mission, Coverage, Formation
  sensors/                    # Tiefenkamera, Flow
  ros/                        # ROS2-Integration
  llm/                        # LLM-Steuerung
  cli/                        # skymeshx CLI

tools/
  ui/                         # GCS-Anwendung (python -m tools.ui)
    app.py / backend.py / ...
    app_logger.py             # NEU: zentrales Logging
    context/                  # QObject-Contexts für QML
    qml/                      # QML-UI
    gz_bridge/                # umbenannt von gz_bridge/
      gazebo_mavlink_sensor_bridge.py
      lidar_viewer.py
      flow_viewer.py
    legacy/                   # verschoben (--legacy Flag)
      main_window.py
      dashboard_tab.py / experiment_tab.py / log_tab.py
      map_tab.py / safety_tab.py / swarm_tab.py
      widgets.py / style.py
  analysis/                   # NEU: Analyse-Tools zusammen
    analyze_trace.py
    plot_flight.py / plot_swarm.py / live_swarm_map.py
    benchmark_bag_compression.py / profile_memory.py
  scripts/                    # NEU: Shell/Launch-Skripte
    launch_px4_sitl.sh
  migrations/                 # NEU: abgeschlossene Migrations-Skripte
    rebrand_*.py / migrate_to_pyside6.py / do_rebrand.py
  installer/                  # Windows/Linux-Installer-Build (OK)

tests/
  conftest.py
  test_*.py                   # alle Tests hier
  test_solar_ui.py            # verschoben vom Root
  e2e/ / security/

logs/                         # gitignored, strukturiert nach Typ
  app/
    <YYYY-MM-DD>/gcs.log      # NEU: GCS App-Log (rotierend, JSON-lines)
  drone/                      # NEU: Drone-Events + Telemetrie
    <timestamp>_<id>_events.jsonl
    <timestamp>_<id>_telemetry.csv
  sitl/                       # NEU: ArduPilot SITL stdout/stderr
  bridge/                     # NEU: Sensor-Bridge stdout/stderr
  mavproxy/                   # MAVProxy logs (vorhanden, leer)
  batterylogs/                # Battery history (vorhanden)
  export/                     # export_*.txt Dateien

trace_runs/                   # gitignored, Trace-Sessions
  <timestamp>_<scenario>/
    manifest.json
    ui_events.jsonl
    sitl_events.jsonl         # NEU
    bridge_events.jsonl       # NEU
    apf_events.jsonl          # NEU
    mission_trace.jsonl
    ros2_topic_health.json
    video/ / config/

docs/
  project/
    bugfix-plan.md            # verschoben von Root/BUGFIX_PLAN.md
    migration.md              # verschoben von Root/MIGRATION.md
    implementation-plan-camera-video-streaming.md
    sitl-implementation-plan.md
  api/ / features/ / setup/ / testing/ / security/ / ui/ / release/

pi/                           # Raspberry Pi Deployment (OK)
docker/                       # Docker-Config (OK)
examples/                     # SDK-Beispiele (OK)
experiments/                  # Forschungs-Skripte (OK)
```

---

## 9 — Prioritäten

| Priorität | Aktion | Aufwand |
|---|---|---|
| 🔴 Hoch | `test_solar_ui.py` → `tests/` verschieben | 1 min |
| 🔴 Hoch | `logs/` Drone-Dateien → `logs/drone/` | Shell-Befehl |
| 🔴 Hoch | `gz_bridge/` → `gz_bridge/` umbenennen + Imports anpassen | 10 min |
| 🟡 Mittel | Legacy-UI → `tools/ui/legacy/` verschieben + `__main__.py` Pfad anpassen | 15 min |
| 🟡 Mittel | `tools/` Analyse/Migrations-Skripte in Unterordner | 5 min |
| 🟡 Mittel | `.gitignore`: `plots/` hinzufügen | 1 min |
| 🔵 Niedrig | `BUGFIX_PLAN.md` / `MIGRATION.md` → `docs/project/` | 1 min |
| 🔵 Niedrig | `docs/` Root-Plan-Dateien → `docs/project/` | 1 min |
