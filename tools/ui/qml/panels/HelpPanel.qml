import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components" as Cmp

// ─────────────────────────────────────────────────────────────────────────────
// HelpPanel — Complete Feature Reference for SkyMeshX GCS
//
// Modernized with new theme integration and improved accessibility
// ─────────────────────────────────────────────────────────────────────────────
Item {
    id: root
    anchors.fill: parent

    // ── Inline section component with modern design ─────────────────────────
    component HelpSection: Rectangle {
        id: helpSection
        property string title: ""
        property string subtitle: ""
        property color  accent: Cmp.Theme.accent
        property string body: ""
        width: parent ? parent.width : 600
        radius: Cmp.Theme.radiusMd
        color: Cmp.Theme.bgPanel
        border.color: Cmp.Theme.border
        border.width: 1
        height: secCol.implicitHeight + Cmp.Theme.spacing(3)

        // Accent bar with smooth gradient
        Rectangle {
            width: 4
            height: parent.height - Cmp.Theme.spacing(2)
            anchors {
                left: parent.left
                leftMargin: Cmp.Theme.spacing(1)
                verticalCenter: parent.verticalCenter
            }
            radius: 2
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.lighter(helpSection.accent, 1.2) }
                GradientStop { position: 1.0; color: helpSection.accent }
            }
        }

        Column {
            id: secCol
            anchors {
                left: parent.left
                leftMargin: Cmp.Theme.spacing(2.5)
                right: parent.right
                rightMargin: Cmp.Theme.spacing(2)
                top: parent.top
                topMargin: Cmp.Theme.spacing(1.5)
            }
            spacing: Cmp.Theme.spacing(1)

            Text {
                text: helpSection.title
                color: helpSection.accent
                font.pixelSize: Cmp.Theme.fontMd
                font.weight: Font.Bold
                font.letterSpacing: 0.5
            }
            Text {
                visible: helpSection.subtitle.length > 0
                text: helpSection.subtitle
                color: Cmp.Theme.textSecondary
                font.pixelSize: Cmp.Theme.fontXs
                font.italic: true
                wrapMode: Text.WordWrap
                width: parent.width
            }
            Text {
                text: helpSection.body
                color: Cmp.Theme.textPrimary
                font.pixelSize: Cmp.Theme.fontSm
                wrapMode: Text.WordWrap
                width: parent.width
                lineHeight: 1.5
                textFormat: Text.RichText
            }
        }

        // Subtle hover effect
        Behavior on border.color {
            ColorAnimation { duration: Cmp.Theme.durationFast }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            onEntered: parent.border.color = Qt.lighter(Cmp.Theme.border, 1.3)
            onExited: parent.border.color = Cmp.Theme.border
            propagateComposedEvents: true
        }
    }

    // ── Two-column glossary row component ────────────────────────────────────
    component GlossaryRow: Row {
        property string term: ""
        property string def: ""
        spacing: Cmp.Theme.spacing(1.5)
        width: parent ? parent.width : 0
        
        Text {
            text: parent.term
            color: Cmp.Theme.info
            font.pixelSize: Cmp.Theme.fontSm
            font.weight: Font.Bold
            font.family: "Consolas"
            width: 170
            wrapMode: Text.WordWrap
        }
        Text {
            text: parent.def
            color: Cmp.Theme.textPrimary
            font.pixelSize: Cmp.Theme.fontSm
            width: parent.width - 180
            wrapMode: Text.WordWrap
            textFormat: Text.RichText
            lineHeight: 1.4
        }
    }

    ScrollView {
        anchors {
            fill: parent
            margins: Cmp.Theme.spacing(2)
        }
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        Column {
            width: parent.availableWidth
            spacing: Cmp.Theme.spacing(2)

            // ── Modern Header with gradient ─────────────────────────────────
            Rectangle {
                width: parent.width
                height: 100
                radius: Cmp.Theme.radiusLg
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.darker(Cmp.Theme.warning, 1.8) }
                    GradientStop { position: 1.0; color: Qt.darker(Cmp.Theme.warning, 2.2) }
                }
                border.color: Cmp.Theme.warning
                border.width: 2
                
                Column {
                    anchors {
                        left: parent.left
                        leftMargin: Cmp.Theme.spacing(3)
                        verticalCenter: parent.verticalCenter
                    }
                    spacing: Cmp.Theme.spacing(0.5)
                    
                    Text {
                        text: qsTr("SkyMeshX Ground Control Station")
                        color: Cmp.Theme.warning
                        font.pixelSize: Cmp.Theme.fontXl
                        font.weight: Font.Bold
                    }
                    Text {
                        text: qsTr("Complete Feature Reference · Workflows · Conventions")
                        color: Cmp.Theme.textSecondary
                        font.pixelSize: Cmp.Theme.fontMd
                    }
                    Text {
                        text: qsTr("⚠ Read at least Quickstart + Global Concepts before arming a drone.")
                        color: Cmp.Theme.textMuted
                        font.pixelSize: Cmp.Theme.fontSm
                        font.italic: true
                    }
                }
            }

            // ── License + update banners ────────────────────────────────────
            Cmp.UpdateBanner {
                width: parent.width
            }
            Cmp.LicenseStatusBanner {
                width: parent.width
            }
            

            // ── 1. Quickstart ───────────────────────────────────────────────
            HelpSection {
                title: qsTr("1 · QUICKSTART (5 Steps to First Mission)")
                subtitle: qsTr("Assumption: SITL already running (e.g. ArduCopter on tcp:127.0.0.1:5762)")
                accent: Cmp.Theme.success
                body:
                    qsTr("<b>① Add Drone</b><br>") +
                    qsTr("&nbsp;&nbsp;Swarm Tab → <b>+ DRONE</b> → ID (e.g. <code>UAV_1</code>) + Connection String (<code>tcp:127.0.0.1:5762</code>) → <b>Connect</b>. ") +
                    qsTr("Status badge turns <span style='color:#22c55e'>green</span>, FSM jumps from <code>DISCONNECTED</code> to <code>IDLE</code>.<br><br>") +
                    qsTr("<b>② Set Waypoints</b><br>") +
                    qsTr("&nbsp;&nbsp;Map Tab → <b>ADD WAYPOINT</b> activate → left click on map. ") +
                    qsTr("Set altitude (AGL) top right. ESC cancels mode. ") +
                    qsTr("Alternative: Swarm Tab → type Lat/Lon/Alt → <b>Add WP</b>.<br><br>") +
                    qsTr("<b>③ Select Mission Targets</b><br>") +
                    qsTr("&nbsp;&nbsp;Swarm Tab → checkboxes ☑ left of each drone that should fly. ") +
                    qsTr("No checkboxes → currently <i>selected</i> drone is target. Multiple checkboxes → Multi-Drone Dispatch.<br><br>") +
                    qsTr("<b>④ Safety Check</b><br>") +
                    qsTr("&nbsp;&nbsp;Open Safety Tab → <b>APF ENABLE</b> (collision protection on). ") +
                    qsTr("Check geofence radius (default 50 m is usually too small for multi-drone → set to 200 m).<br><br>") +
                    qsTr("<b>⑤ Start Mission</b><br>") +
                    qsTr("&nbsp;&nbsp;Swarm Tab → <b>START MISSION</b>. ") +
                    qsTr("UI arms → takeoff → flies WPs → lands. ") +
                    qsTr("During mission you see path as <span style='color:#22c55e'>green markers + dashed line</span> on map. ") +
                    qsTr("FSM badge in Telemetry Tab follows: <code>ARMED → TAKEOFF → MISSION → RTL → LANDING → IDLE</code>.")
            }

            // ── 2. Globale Konzepte ────────────────────────────────────────
            HelpSection {
                title: "2 · GLOBAL CONCEPTS (Must Understand Before Operating)"
                accent: Cmp.Theme.info
                body:
                    "<b>Selected Drone vs. Mission Targets</b><br>" +
                    "&nbsp;&nbsp;• <b>Selected</b> (in header / combo box) = the <i>one</i> drone whose telemetry is currently displayed in Telemetry Tab and InstrBar.<br>" +
                    "&nbsp;&nbsp;• <b>Mission Targets</b> (checkbox set in Swarm Tab) = drones that receive <i>actions</i> (ARM, TAKEOFF, GOTO, MISSION, Mode Switch). " +
                    "Empty set → automatically falls back to Selected.<br>" +
                    "&nbsp;&nbsp;<span style='color:#f59e0b'>Consequence:</span> You can <i>view</i> Drone A (Selected) while Drones B+C fly a mission (Targets).<br><br>" +
                    "<b>FSM (Finite State Machine) per Drone</b><br>" +
                    "&nbsp;&nbsp;Each drone has a local state: <code>DISCONNECTED → IDLE → ARMING → ARMED → TAKEOFF → FLYING → MISSION → RTL → LANDING → IDLE</code>. " +
                    "<code>EMERGENCY</code> and <code>ERROR</code> are dead-end states requiring reconnect/reset. " +
                    "Invalid transitions are logged as <code>FSM rejected X → Y</code>.<br><br>" +
                    "<b>APF (Artificial Potential Field) — Collision Protection</b><br>" +
                    "&nbsp;&nbsp;Runs at 10 Hz in background. Pushes drones apart when they approach below <i>min_distance</i>. " +
                    "Push is sent as GOTO override to the <i>alphabetically larger</i> drone ID → deterministic, no mutual oscillation.<br>" +
                    "&nbsp;&nbsp;<span style='color:#ef4444'>Important:</span> APF can override Formation and Mission commands. If formation slots are tighter than <i>min_distance</i>, APF wins and formation collapses.<br><br>" +
                    "<b>Altitudes are AGL</b> (above ground at launch). " +
                    "A takeoff altitude of 10 m means 10 m above spawn point, <i>not</i> 10 m MSL.<br><br>" +
                    "<b>Log Persistence:</b> Everything you see in Log Tab is also written to <code>tools/ui/syslogs/&lt;date&gt;_&lt;time&gt;.txt</code>. " +
                    "Include this file in bug reports."
            }

            // ── 3. Tab: Map ────────────────────────────────────────────────
            HelpSection {
                title: qsTr("TAB · MAP")
                subtitle: qsTr("Leaflet-based map with live drone markers, tracks, waypoints and geofence overlay.")
                accent: Cmp.Theme.info
                body:
                    qsTr("<b>What you see</b><br>") +
                    qsTr("&nbsp;&nbsp;• Drone markers with live position (update ~5 Hz).<br>") +
                    qsTr("&nbsp;&nbsp;• Track polyline (history), colored by type: blue = generic, purple = observation.<br>") +
                    qsTr("&nbsp;&nbsp;• Waypoint markers (orange, numbered) — set via ADD WAYPOINT mode or Swarm Tab.<br>") +
                    qsTr("&nbsp;&nbsp;• Already dispatched mission path (green markers + dashed line) — remains after mission start as visual reference.<br>") +
                    qsTr("&nbsp;&nbsp;• Geofence (red dashed circle, if enabled in Safety).<br>") +
                    qsTr("&nbsp;&nbsp;• <b>ESCAPE Obstacles</b> (red spheres when perception enabled).<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Voxel Map</b> (red cubes when distributed mapping enabled).<br><br>") +
                    qsTr("<b>How to use it</b><br>") +
                    qsTr("&nbsp;&nbsp;• <b>ADD WAYPOINT</b> (toolbar top) → cursor becomes crosshair → click on map creates WP.<br>") +
                    qsTr("&nbsp;&nbsp;• <b>ESC</b> cancels mode without setting WP.<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Altitude field</b> top right = AGL for next WP to be set.<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Map style</b> switchable: Light · Dark · Topo.<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Center-on-Drone</b>: Click on drone in sidebar zooms map to its position.<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Mouse wheel</b>: Zoom. Right-click + Drag: Pan.<br><br>") +
                    qsTr("<span style='color:#f59e0b'><b>Common Pitfalls</b></span><br>") +
                    qsTr("&nbsp;&nbsp;• Map appears empty → drone spawn is outside viewport. Sidebar click on drone centers it.<br>") +
                    qsTr("&nbsp;&nbsp;• WP not being set → WP mode is off. Press toolbar button again.<br>") +
                    qsTr("&nbsp;&nbsp;• Drone jumps visibly on map → telemetry gap (common on first GPS fix in SITL). Normal.")
            }

            // ── 4. Tab: Telemetry ──────────────────────────────────────────
            HelpSection {
                title: "TAB · TELEMETRY (Dashboard)"
                subtitle: "Live-Cockpit für eine einzelne Drohne — die per Combo-Box oder Sidebar ausgewählte."
                accent: Cmp.Theme.accent
                body:
                    "<b>Was du siehst</b><br>" +
                    "&nbsp;&nbsp;• <b>FSM-Badge</b> oben: aktueller Zustand der Drohne mit animiertem Indikator bei Übergängen.<br>" +
                    "&nbsp;&nbsp;• <b>Typ- und Rollen-Badge</b>: generic/observation, Leader/Follower/none.<br>" +
                    "&nbsp;&nbsp;• <b>FSM Flight-Hint</b>: kontextspezifischer Tipp je nach Zustand (z. B. „Drohne ist ARMED – sichere Stelle? TAKEOFF drücken“).<br>" +
                    "&nbsp;&nbsp;• <b>FSM-Verlauf</b>: letzte ~30 Übergänge, neueste oben.<br>" +
                    "&nbsp;&nbsp;• <b>KPI-Grid</b>: Altitude (rel + AMSL), Speed (groundspeed + km/h), Heading, Climb-Rate, Satellites, Throttle.<br>" +
                    "&nbsp;&nbsp;• <b>Battery-Bar</b>: %-Anzeige farbcodiert (grün &gt; 50 %, gelb &gt; 20 %, rot ≤ 20 %) plus Spannung in V.<br>" +
                    "&nbsp;&nbsp;• <b>GPS-Strip</b>: Fix-Type (NoFix/2D/3D/RTK) und Satelliten-Anzahl.<br><br>" +
                    "<b>Wie du es benutzt</b><br>" +
                    "&nbsp;&nbsp;Combo-Box ändern → globale Selected-Drohne wird ebenfalls umgeschaltet (überall in der UI synchron). " +
                    "Auto-Pick: die erste verbundene Drohne wird beim Öffnen des Tabs ausgewählt.<br><br>" +
                    "<span style='color:#f59e0b'><b>Häufige Stolpersteine</b></span><br>" +
                    "&nbsp;&nbsp;• Alle Werte zeigen 0 / „—“ → Drohne ist nicht verbunden oder Telemetry-Stream wurde noch nicht angefordert. " +
                    "In SITL kann das erste GPS-Fix bis 30 s dauern.<br>" +
                    "&nbsp;&nbsp;• <code>flight_mode</code> bleibt „UNKNOWN“ → SDK kennt den FC-Modus nicht. Reconnect oft hilfreich."
            }

            // ── 5. Tab: Swarm ──────────────────────────────────────────────
            HelpSection {
                title: "TAB · SWARM CONTROL"
                subtitle: "Hauptarbeitsplatz für Multi-Drohnen-Operationen: Verbindung, Mission, Formationen, Algorithmen."
                accent: Cmp.Theme.success
                body:
                    "<b>Linke Spalte — Drohnen-Management</b><br>" +
                    "&nbsp;&nbsp;• <b>+ DROHNE</b>: Dialog mit ID + Connection-String (<code>tcp:…</code>, <code>udp:…</code>, <code>serial:…</code>).<br>" +
                    "&nbsp;&nbsp;• Typ-Toggle: <i>generic</i> (Standard) vs. <i>observation</i> (mit Gimbal-Modell).<br>" +
                    "&nbsp;&nbsp;• Drohnen-Liste mit ☑ Mission-Target-Häkchen, Verbindungs-Status, Disconnect- und Remove-Buttons.<br><br>" +
                    "<b>Rechte Spalte — Mission & Algorithmen</b><br>" +
                    "&nbsp;&nbsp;<u>Swarm-Quick-Commands</u> (oberer Block): ARM/DISARM/TAKEOFF/LAND/RTL für <i>alle</i> verbundenen Drohnen.<br>" +
                    "&nbsp;&nbsp;<u>WP-Editor</u>: Lat/Lon/Alt manuell tippen oder per Map-Pick (Button „Karte“). " +
                    "Distanz-Preview zeigt Luftlinie zur aktuell ersten Target-Drohne.<br>" +
                    "&nbsp;&nbsp;<u>GOTO (N)</u>: feuert SET_POSITION an <i>alle</i> Mission-Targets. Label zeigt Anzahl.<br>" +
                    "&nbsp;&nbsp;<u>Mission-Liste</u>: alle gesetzten Wegpunkte mit Index. <b>MISSION STARTEN</b> dispatched die Liste als " +
                    "echte MAVLink-Mission (Upload-Phase) oder fällt auf sequentielles GOTO zurück, falls der Autopilot kein Upload unterstützt.<br><br>" +
                    "<b>Swarm-Algorithmen (eigene Sektion)</b><br>" +
                    "&nbsp;&nbsp;• <b>Boids</b> – Separation / Alignment / Cohesion mit konfigurierbaren Gewichten. Gut für „Schwarm-Look“ ohne Mission.<br>" +
                    "&nbsp;&nbsp;• <b>Leader-Follower</b> – Du wählst einen Leader, alle anderen berechnen relative Slot-Positionen.<br>" +
                    "&nbsp;&nbsp;&nbsp;&nbsp;Formation-Typen: <i>Line · V-Shape · Circle · Grid · Diamond · Letter R · Letter Z</i>.<br>" +
                    "&nbsp;&nbsp;&nbsp;&nbsp;<b>Formation Size</b>: <code>0</code> = alle verbundenen Drohnen werden eingebunden. Sonst: Leader + (Size−1) Follower.<br>" +
                    "&nbsp;&nbsp;&nbsp;&nbsp;<b>Follow Distance</b>: Slot-Abstand in m (Default 8 m, sicher gegen APF min_distance 2 m).<br>" +
                    "&nbsp;&nbsp;• <b>Consensus</b> – Verteilte Voting-Logik (z. B. Mehrheitsbeschluss über RTL).<br>" +
                    "&nbsp;&nbsp;• <b>Behavior Trees</b> – Vorgefertigte Missions-Templates (Surveillance, Search&amp;Rescue, Coverage …).<br><br>" +
                    "<b>Letter-Templates – Drohnen-Anforderungen</b><br>" +
                    "&nbsp;&nbsp;Letter R = 14 Drohnen · Letter Z = 12 · Diamond = 25. Bei weniger Drohnen wird das Template gestaucht oder Slots bleiben leer.<br><br>" +
                    "<span style='color:#f59e0b'><b>Häufige Stolpersteine</b></span><br>" +
                    "&nbsp;&nbsp;• Formation läuft nicht an → Formation Size kleiner als Drohnen-Anzahl, oder kein Leader gesetzt.<br>" +
                    "&nbsp;&nbsp;• Drohnen kollidieren in der Formation → Follow Distance &lt; APF min_distance. Beide aufeinander abstimmen.<br>" +
                    "&nbsp;&nbsp;• Mission startet nicht → keine Mission-Targets markiert + keine Drohne selected.<br>" +
                    "&nbsp;&nbsp;• Mission-Liste verschwindet nach Start → das ist Absicht (One-Shot-Queue). Die grünen Map-Marker bleiben."
            }

            // ── 6. Tab: Mission Planning ────────────────────────────────────
            HelpSection {
                title: qsTr("TAB · MISSION PLANNING")
                subtitle: qsTr("Advanced mission generation: Field Coverage, Seeding, Solar Inspection")
                accent: "#8b5cf6"
                body:
                    qsTr("<b>Mission Mode Toggle</b><br>") +
                    qsTr("&nbsp;&nbsp;Three modes: <b>Coverage</b> (green) · <b>Seeding</b> (purple) · <b>Solar</b> (amber).<br><br>") +
                    qsTr("<b>Coverage Mode — Field Coverage Planning</b><br>") +
                    qsTr("&nbsp;&nbsp;• Draw field boundary on map (click corners, close polygon).<br>") +
                    qsTr("&nbsp;&nbsp;• Pattern: <i>Parallel Lines</i> (default), <i>Spiral</i>, <i>Grid</i>, <i>Zigzag</i>.<br>") +
                    qsTr("&nbsp;&nbsp;• Parameters: Altitude (10-50m), Line Spacing (5-40m), Overlap (0-50%), Heading (0-360°).<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Generate Coverage</b> → creates optimized waypoint pattern.<br>") +
                    qsTr("&nbsp;&nbsp;• Statistics: Coverage area (m²), estimated time, waypoint count.<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Multi-Drone Coverage</b>: Enable checkbox → field is split into N sectors (one per drone).<br>") +
                    qsTr("&nbsp;&nbsp;&nbsp;&nbsp;Each drone gets its own sub-mission. Parallel execution reduces total time by ~N.<br><br>") +
                    qsTr("<b>Seeding Mode — Precision Seeding</b><br>") +
                    qsTr("&nbsp;&nbsp;• Define seeding points on map (click to add).<br>") +
                    qsTr("&nbsp;&nbsp;• Parameters: Drop altitude, hover time, seed spacing.<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Generate Seeding Mission</b> → creates waypoints with DO_SET_SERVO commands.<br><br>") +
                    qsTr("<b>Solar Mode — Solar Park Inspection</b><br>") +
                    qsTr("&nbsp;&nbsp;• Add panel rows by clicking start/end points on map.<br>") +
                    qsTr("&nbsp;&nbsp;• Parameters: Altitude (10-30m), Gimbal Pitch (-90° to -45°), Trigger Distance (2-10m), Overlap (0-50%).<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Generate Inspection</b> → creates thermal imaging mission with DO_DIGICAM_CONTROL commands.<br>") +
                    qsTr("&nbsp;&nbsp;• Statistics: Coverage area, photo count, estimated time.<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Thermal Overlay</b>: Hotspots appear as red circles on map with temperature labels.<br><br>") +
                    qsTr("<span style='color:#f59e0b'><b>Best Practices</b></span><br>") +
                    qsTr("&nbsp;&nbsp;• <b>Coverage</b>: 15-20m spacing with 20% overlap for crop monitoring.<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Solar</b>: -90° gimbal (straight down) for best thermal detection.<br>") +
                    qsTr("&nbsp;&nbsp;• <b>Multi-Drone</b>: Ensure drones start from different positions to avoid collisions.")
            }

            // ── 7. Tab: Safety ─────────────────────────────────────────────
            HelpSection {
                title: "TAB · SAFETY / APF"
                subtitle: "Aktiver Kollisionsschutz, Geofence und Battery-Limits — die einzige Schicht zwischen dir und Crashes."
                accent: Cmp.Theme.danger
                body:
                    "<b>APF (Artificial Potential Field)</b><br>" +
                    "&nbsp;&nbsp;Schiebt Drohnen mit einer repulsiven Kraft auseinander. Konfigurierbar:<br>" +
                    "&nbsp;&nbsp;• <b>min separation</b> (m) – ab wann der Push einsetzt.<br>" +
                    "&nbsp;&nbsp;• <b>max speed</b> (m/s) – Kappung der Avoidance-Geschwindigkeit.<br>" +
                    "&nbsp;&nbsp;• <b>repulsion gain</b> – Stärke des Pushs.<br>" +
                    "&nbsp;&nbsp;<b>ENABLE APF</b> startet das 10-Hz-Monitoring; <b>DISABLE</b> stoppt es. Aktiv-State pulsiert grün.<br><br>" +
                    "<b>Geofence</b><br>" +
                    "&nbsp;&nbsp;• <b>Radius</b> (m vom Spawn-Punkt) – horizontale Begrenzung.<br>" +
                    "&nbsp;&nbsp;• <b>Alt min/max</b> – vertikale Begrenzung in m AGL.<br>" +
                    "&nbsp;&nbsp;Verletzung → <code>geofenceBreached</code>-Signal, Log-ERROR, je nach Konfig Auto-RTL.<br><br>" +
                    "<b>Obstacles</b><br>" +
                    "&nbsp;&nbsp;Statische Hindernis-Sphären (Lat/Lon/Alt/Radius) hinzufügbar. APF behandelt sie wie Drohnen.<br><br>" +
                    "<b>Live-Violations-Tabelle</b><br>" +
                    "&nbsp;&nbsp;Aktuelle Konflikt-Paare mit Distanz. Rate-limitiert (max. 1 Log-Eintrag / 2 s pro Paar) damit das System-Log nicht überflutet wird.<br><br>" +
                    "<span style='color:#f59e0b'><b>Häufige Stolpersteine</b></span><br>" +
                    "&nbsp;&nbsp;• APF „kämpft“ gegen Formation → Follow Distance &lt; min_distance. Lösung: Follow Distance erhöhen oder min_distance senken.<br>" +
                    "&nbsp;&nbsp;• SITL spawnt alle Drohnen am exakt gleichen Punkt → APF eskaliert beim Takeoff. " +
                    "Lösung: Drohnen in Höhenstaffeln starten (5/8/11/14 m) <i>vor</i> dem Aktivieren von APF.<br>" +
                    "&nbsp;&nbsp;• Geofence-Default 50 m ist für Letter-Templates zu klein (Diamond spannt ~25 m + Spawn-Streuung)."
            }

            // ── 7. Tab: Gimbal ─────────────────────────────────────────────
            HelpSection {
                title: "TAB · GIMBAL / CAMERA"
                subtitle: "Pan/Tilt-Steuerung und Live-Preview für Observation-Drohnen."
                accent: "#8b5cf6"  // Purple - keeping original
                body:
                    "<b>Steuerung</b><br>" +
                    "&nbsp;&nbsp;• Pan- und Tilt-Slider in Grad, sofortige MAVLink-Mount-Command-Sendung.<br>" +
                    "&nbsp;&nbsp;• <b>Presets</b>: Forward (0°/0°), Down/Nadir (0°/−90°), Tracking-Modus (folgt aktuellem Mission-WP).<br>" +
                    "&nbsp;&nbsp;• <b>Snapshot</b>: speichert den aktuellen Frame nach <code>logs/snapshots/&lt;timestamp&gt;_&lt;drone&gt;.png</code>.<br><br>" +
                    "<b>Voraussetzungen</b><br>" +
                    "&nbsp;&nbsp;• Drohne muss als <i>observation</i>-Typ hinzugefügt sein.<br>" +
                    "&nbsp;&nbsp;• Autopilot muss MAV_CMD_DO_MOUNT_CONTROL unterstützen (ArduCopter: ja, PX4: teilweise).<br><br>" +
                    "<span style='color:#f59e0b'><b>Häufige Stolpersteine</b></span><br>" +
                    "&nbsp;&nbsp;• Slider bewegen sich, aber nichts passiert → SITL-Build ohne Gimbal-Mount kompiliert.<br>" +
                    "&nbsp;&nbsp;• Kein Live-Bild → in SITL ist normalerweise kein Stream verfügbar; das Panel zeigt Placeholder."
            }

            // ── 8. Tab: ROS2 ───────────────────────────────────────────────
            HelpSection {
                title: "TAB · ROS2 / uXRCE-DDS (PX4-Bridge)"
                subtitle: "Direkter ROS2-Bridge-Zugriff für PX4-Drohnen über uXRCE-DDS — ohne MAVLink-Umweg."
                accent: Cmp.Theme.info
                body:
                    "<b>Drei-Spalten-Layout</b><br><br>" +
                    "<b>Links — Status &amp; Konfig</b><br>" +
                    "&nbsp;&nbsp;• <b>Node-Status</b>: <span style='color:#22c55e'>ok</span> · <span style='color:#f59e0b'>no_px4_msgs</span> (rclpy da, aber px4_msgs fehlt) · <span style='color:#ef4444'>no_ros2</span> (rclpy nicht installiert).<br>" +
                    "&nbsp;&nbsp;• <b>Installations-Hinweise</b>: zeigen direkt die nötigen Shell-Commands für ROS2 Humble + px4_msgs + MicroXRCEAgent.<br>" +
                    "&nbsp;&nbsp;• <b>Bridge-Konfig</b>: Drohne wählen, Namespace setzen (leer = <code>/fmu/*</code>), Bridge per Button starten/stoppen.<br>" +
                    "&nbsp;&nbsp;• <b>uORB Topics</b>: Live-Liste aller subscribed/published Topics für diese Bridge.<br><br>" +
                    "<b>Mitte — Live uORB Snapshot &amp; Offboard</b><br>" +
                    "&nbsp;&nbsp;• Aktuelle Telemetrie aus den uORB-Streams (lat/lon/alt/roll/pitch/yaw/battery/gps, 5 Hz).<br>" +
                    "&nbsp;&nbsp;• <b>Offboard-Modus</b> aktivieren, dann <i>Position</i>- oder <i>Velocity</i>-Setpoints in NED-Frame senden.<br>" +
                    "&nbsp;&nbsp;• <b>STOP</b> deaktiviert die kontinuierliche Setpoint-Stream sofort.<br><br>" +
                    "<b>Rechts — Vehicle Commands</b><br>" +
                    "&nbsp;&nbsp;ARM / DISARM / LAND / RTL / TAKEOFF direkt über VEHICLE_COMMAND (umgeht MAVLink-Path).<br><br>" +
                    "<b>Voraussetzungen</b><br>" +
                    "&nbsp;&nbsp;1. ROS2 Humble oder Jazzy installiert (Linux/WSL2).<br>" +
                    "&nbsp;&nbsp;2. <code>px4_msgs</code> in einem ROS2-Workspace gebaut und gesourced.<br>" +
                    "&nbsp;&nbsp;3. <code>MicroXRCEAgent udp4 -p 8888</code> läuft im Hintergrund.<br>" +
                    "&nbsp;&nbsp;4. PX4 mit DDS-Client gestartet (SITL: läuft per Default).<br><br>" +
                    "<span style='color:#f59e0b'><b>Häufige Stolpersteine</b></span><br>" +
                    "&nbsp;&nbsp;• Status bleibt <i>no_ros2</i> auf Windows-nativ → ROS2 läuft nur in WSL2. Die GCS muss in WSL gestartet werden.<br>" +
                    "&nbsp;&nbsp;• Bridge startet, aber Snapshot bleibt leer → MicroXRCEAgent läuft nicht oder falscher Port."
            }

            // ── 9. Tab: Scenario / Experiment ──────────────────────────────
            HelpSection {
                title: "TAB · SCENARIO (Experiment Runner)"
                subtitle: "Zwei Modi: Python-Scripts ad-hoc oder JSON-Szenarien aus Files. Beide nutzen den ExperimentContext."
                accent: Cmp.Theme.warning
                body:
                    "<b>Modus 1 — Python Script</b><br>" +
                    "&nbsp;&nbsp;• <b>OPEN</b>: lädt eine .py-Datei in den Editor.<br>" +
                    "&nbsp;&nbsp;• <b>SAVE</b>: speichert den aktuellen Editor-Inhalt nach <code>experiments/uploads/&lt;name&gt;.py</code> und startet ihn sofort.<br>" +
                    "&nbsp;&nbsp;• <b>RUN/STOP</b>: führt Editor-Inhalt direkt aus (ohne zu speichern) bzw. stoppt den laufenden Script kooperativ via <code>stop_event</code>. " +
                    "Wenn Stop nicht reagiert: Force-Stop benutzt <code>PyThreadState_SetAsyncExc</code> (Best-Effort, kann C-Blockings nicht unterbrechen).<br>" +
                    "&nbsp;&nbsp;• <b>Beispiel</b>: lädt ein Hover-Stability-Experiment (3 SITL-Drohnen, Hover 30 s, Land).<br>" +
                    "&nbsp;&nbsp;• Script-Output (print/stderr) wird in den globalen Log gestreamt mit Prefix <code>[SCRIPT]</code>.<br><br>" +
                    "<b>Modus 2 — JSON Scenario</b><br>" +
                    "&nbsp;&nbsp;• Vordefinierte Schritt-Liste (<code>takeoff</code>, <code>hover</code>, <code>goto</code>, <code>land</code>) wird vom <code>ScenarioRunner</code> ausgeführt.<br>" +
                    "&nbsp;&nbsp;• <i>Use SITL</i>-Checkbox: erzeugt SITL-Instanzen automatisch.<br>" +
                    "&nbsp;&nbsp;• Ergebnisse landen in der <b>RESULTS</b>-Liste (Pass/Fail + Dauer).<br><br>" +
                    "<b>Globaler Watchdog</b><br>" +
                    "&nbsp;&nbsp;Per <code>experiment.setScriptTimeout(seconds)</code> kann ein Hard-Timeout gesetzt werden, der nach Ablauf force_stop() triggert.<br><br>" +
                    "<span style='color:#f59e0b'><b>Häufige Stolpersteine</b></span><br>" +
                    "&nbsp;&nbsp;• Script läuft nicht weiter → <code>exit()</code>/<code>quit()</code> sind im Sandbox-Namespace disabled, benutze <code>return</code> auf Modul-Ebene oder Exception.<br>" +
                    "&nbsp;&nbsp;• <i>Busy</i>-State hängt → Script in C-Bibliothek geblockt. Force-Stop probieren; sonst App neu starten."
            }

            // ── 10. Tab: FlightLog ─────────────────────────────────────────
            HelpSection {
                title: "TAB · FLIGHT LOG"
                subtitle: "Offline-Replay & Plots aus den Telemetry-CSVs jeder vergangenen Verbindung."
                accent: "#a78bfa"  // Light purple - keeping original
                body:
                    "<b>Datenquelle</b><br>" +
                    "&nbsp;&nbsp;Jede Drohnen-Verbindung schreibt <code>logs/&lt;timestamp&gt;_&lt;drone&gt;_telemetry.csv</code> via <code>TelemetryLogger</code>. " +
                    "Bei Queue-Sättigung werden Frames gedroppt und am Ende als <code>dropped_count</code> protokolliert (rate-limited Warnings).<br><br>" +
                    "<b>Funktionen</b><br>" +
                    "&nbsp;&nbsp;• Datei-Auswahl (Multi-Select für Vergleichs-Overlay).<br>" +
                    "&nbsp;&nbsp;• Plots: Altitude · Battery · Speed · Heading über Zeit.<br>" +
                    "&nbsp;&nbsp;• Multi-Drohne-Overlay mit Farbcode pro Drohne.<br>" +
                    "&nbsp;&nbsp;• PNG-Export der Plots für Berichte.<br><br>" +
                    "<span style='color:#f59e0b'><b>Häufige Stolpersteine</b></span><br>" +
                    "&nbsp;&nbsp;• Plot leer → CSV ist leer (Drohne war nie verbunden) oder Spalten-Header nicht erkannt. " +
                    "TelemetryLogger schreibt einen Header beim ersten Frame."
            }

            // ── 11. Tab: Log ───────────────────────────────────────────────
            HelpSection {
                title: "TAB · SYSTEM LOG"
                subtitle: "Aggregierter Live-Stream aller Backend-Logs aus swarm/experiment/safety/ros2."
                accent: Cmp.Theme.textSecondary
                body:
                    "<b>Was du siehst</b><br>" +
                    "&nbsp;&nbsp;• Live-Einträge mit Zeitstempel (HH:MM:SS), Level-Badge (INFO/WARN/ERROR), Drohnen-Tag (farbcodiert per Hash) und Nachricht.<br>" +
                    "&nbsp;&nbsp;• Auto-Scroll am unteren Ende; bei neuer Nachricht wird gescrollt.<br>" +
                    "&nbsp;&nbsp;• Error-Counter-Badge im Header zeigt Anzahl ERROR-Einträge.<br><br>" +
                    "<b>Filter</b><br>" +
                    "&nbsp;&nbsp;• Level-Dropdown: ALL / INFO / WARN / ERROR.<br>" +
                    "&nbsp;&nbsp;• Suchfeld (case-insensitive, sucht in Level + Text).<br>" +
                    "&nbsp;&nbsp;• <b>CLEAR</b>: leert das in-memory Log (die auto-save-Datei bleibt erhalten).<br><br>" +
                    "<b>Persistenz</b><br>" +
                    "&nbsp;&nbsp;Alles wird <i>zusätzlich</i> nach <code>tools/ui/syslogs/&lt;datum&gt;_&lt;zeit&gt;.txt</code> geschrieben (Throttle 1 s, Ring-Buffer 3000 in memory). " +
                    "Bei Bug-Reports immer mitschicken."
            }

            // ── 12. InstrBar (oben) ────────────────────────────────────────
            HelpSection {
                title: "INSTRBAR (oberer Streifen, immer sichtbar)"
                subtitle: "Cockpit-Instrumente + Quick-Commands über alle Tabs hinweg."
                accent: Cmp.Theme.accent
                body:
                    "<b>Tiles (links → rechts)</b><br>" +
                    "&nbsp;&nbsp;1. <b>DRONE</b> – Combo + Connection-Indikator. Wechseln synchronisiert globale Selected.<br>" +
                    "&nbsp;&nbsp;2. <b>ARMED/MODE</b> – pulsierender Indikator wenn ARMED, Flight-Mode-Anzeige, Drohnen-ID.<br>" +
                    "&nbsp;&nbsp;3. <b>Künstlicher Horizont</b> – Roll/Pitch live aus ATTITUDE-Stream (Canvas, 10 Hz refresh).<br>" +
                    "&nbsp;&nbsp;4. <b>Kompass</b> – Heading mit Cardinal-Labels.<br>" +
                    "&nbsp;&nbsp;5. <b>ALT/SPEED/CLIMB</b> – Numeric Tiles mit Trend-Bars und Einheiten-Konversion (m/s → km/h).<br>" +
                    "&nbsp;&nbsp;6. <b>BATTERY/GPS</b> – %-Anzeige + Voltage + Fix-Type + Sat-Count.<br>" +
                    "&nbsp;&nbsp;7. <b>QUICK CMD</b> – 6 Buttons: ARM · DISARM · TAKEOFF · LAND · RTL · HOLD. Set-Altitude-Feld daneben für Takeoff-Höhe.<br>" +
                    "&nbsp;&nbsp;8. <b>FLIGHT MODE</b> – 6 Modi: Stab · Alt-H · Loiter · Guided · Auto · PosHld. Klick switched <i>alle</i> Mission-Targets.<br><br>" +
                    "<b>Wichtig:</b> alle Quick-Cmds und Mode-Switches feuern auf <i>alle markierten Mission-Targets</i> simultan. " +
                    "Wenn keine markiert sind, fallen sie auf die Selected-Drohne zurück."
            }

            // ── 13. Konventionen & Gotchas ─────────────────────────────────
            HelpSection {
                title: "KONVENTIONEN, GOTCHAS & TROUBLESHOOTING"
                accent: Cmp.Theme.danger
                body:
                    "<b>Connection-Strings</b><br>" +
                    "&nbsp;&nbsp;• <code>tcp:127.0.0.1:5762</code> – ArduCopter SITL Standard.<br>" +
                    "&nbsp;&nbsp;• <code>tcp:127.0.0.1:5772</code> – SITL Drohne #2 (jede +10).<br>" +
                    "&nbsp;&nbsp;• <code>udp:127.0.0.1:14550</code> – PX4 SITL Standard.<br>" +
                    "&nbsp;&nbsp;• <code>serial:/dev/ttyACM0:57600</code> oder <code>serial:COM5:57600</code> – Hardware.<br><br>" +
                    "<b>Höhen</b><br>" +
                    "&nbsp;&nbsp;• Alle Eingaben in der UI sind <b>AGL</b> (above ground at launch).<br>" +
                    "&nbsp;&nbsp;• <code>alt_rel</code> = Höhe über Spawn. <code>alt</code> bzw. <code>alt_amsl</code> = MSL.<br>" +
                    "&nbsp;&nbsp;• SITL CMAC spawnt typischerweise auf 583 m MSL.<br><br>" +
                    "<b>Mission-Queue ist One-Shot</b><br>" +
                    "&nbsp;&nbsp;Nach <i>MISSION STARTEN</i> wird die Editier-Liste geleert. Die <i>grünen</i> Map-Marker bleiben als visuelle Referenz. " +
                    "Neue WPs hinzufügen → nächster Mission-Start nimmt nur die neuen.<br><br>" +
                    "<b>SITL-Spawn am gleichen Punkt</b><br>" +
                    "&nbsp;&nbsp;Standardmäßig spawnen alle SITL-Drohnen auf derselben Lat/Lon. APF eskaliert beim Takeoff. " +
                    "Lösung: in Höhenstaffeln starten (5/8/11/14 m) oder Spawn-Offset im SITL-Build-Skript setzen.<br><br>" +
                    "<b>Throttling</b><br>" +
                    "&nbsp;&nbsp;• Formation-Goto: 2 Hz pro Drohne (verhindert MAVLink-Bus-Saturation).<br>" +
                    "&nbsp;&nbsp;• GOTO-Buttons: unbeschränkt (Operator-Triggered).<br>" +
                    "&nbsp;&nbsp;• Telemetry-Aggregation: 5 Hz. Per-Drone-Polling: 10 Hz.<br><br>" +
                    "<b>FSM-Sackgassen</b><br>" +
                    "&nbsp;&nbsp;• <code>EMERGENCY</code> – nur per Reset/Reconnect verlassbar.<br>" +
                    "&nbsp;&nbsp;• <code>ERROR</code> – Hard-Fault, Drohne neu verbinden.<br>" +
                    "&nbsp;&nbsp;• <code>DISCONNECTED</code> – Verbindung verloren; Auto-Reconnect-Versuch alle 5 s.<br><br>" +
                    "<b>Diagnose-Sammlung bei Bug-Reports</b><br>" +
                    "&nbsp;&nbsp;1. Aktuelle <code>tools/ui/syslogs/&lt;datum&gt;_&lt;zeit&gt;.txt</code><br>" +
                    "&nbsp;&nbsp;2. Konsolen-Output der GCS (stdout + stderr)<br>" +
                    "&nbsp;&nbsp;3. Relevante <code>logs/&lt;timestamp&gt;_&lt;drone&gt;_telemetry.csv</code><br>" +
                    "&nbsp;&nbsp;4. SITL-Konsolen-Output falls Simulation"
            }

            // ── 14. Glossar ────────────────────────────────────────────────
            Rectangle {
                width: parent.width
                radius: Cmp.Theme.radiusMd
                color: Cmp.Theme.bgPanel
                border.color: Cmp.Theme.border
                border.width: 1
                height: glossCol.implicitHeight + Cmp.Theme.spacing(3)

                Rectangle {
                    width: 4
                    height: parent.height - Cmp.Theme.spacing(2)
                    anchors {
                        left: parent.left
                        leftMargin: Cmp.Theme.spacing(1)
                        verticalCenter: parent.verticalCenter
                    }
                    radius: 2
                    color: Cmp.Theme.info
                }

                Column {
                    id: glossCol
                    anchors {
                        left: parent.left
                        leftMargin: Cmp.Theme.spacing(2.5)
                        right: parent.right
                        rightMargin: Cmp.Theme.spacing(2)
                        top: parent.top
                        topMargin: Cmp.Theme.spacing(1.5)
                    }
                    spacing: Cmp.Theme.spacing(1)

                    Text {
                        text: qsTr("GLOSSARY")
                        color: Cmp.Theme.info
                        font.pixelSize: Cmp.Theme.fontMd
                        font.weight: Font.Bold
                        font.letterSpacing: 0.5
                    }

                    GlossaryRow { term: "AGL";           def: qsTr("Above Ground at Launch — altitude above takeoff point.") }
                    GlossaryRow { term: "AMSL / MSL";    def: qsTr("Above Mean Sea Level — absolute altitude.") }
                    GlossaryRow { term: "APF";           def: qsTr("Artificial Potential Field — repulsive collision protection, 10 Hz.") }
                    GlossaryRow { term: "FSM";           def: qsTr("Finite State Machine — state automaton per drone (IDLE/ARMED/FLYING/…).") }
                    GlossaryRow { term: "Selected Drone";def: qsTr("The <i>one</i> drone whose telemetry is currently displayed.") }
                    GlossaryRow { term: "Mission-Target";def: qsTr("Drone with ☑ — receives actions (ARM, GOTO, MISSION, …).") }
                    GlossaryRow { term: "WP";            def: qsTr("Waypoint — Lat/Lon/Alt point in mission.") }
                    GlossaryRow { term: "RTL";           def: qsTr("Return To Launch — drone flies back to spawn point.") }
                    GlossaryRow { term: "SITL";          def: qsTr("Software In The Loop — drone simulation without hardware.") }
                    GlossaryRow { term: "uXRCE-DDS";     def: qsTr("Micro XRCE-DDS — PX4 bridge to ROS2 (replaces MAVLink bridge).") }
                    GlossaryRow { term: "uORB";          def: qsTr("Micro Object Request Broker — PX4 internal message bus.") }
                    GlossaryRow { term: "NED";           def: qsTr("North-East-Down local coordinate system (PX4 standard).") }
                    GlossaryRow { term: "Geofence";      def: qsTr("Virtual boundary (radius + alt min/max); violation → log + auto-RTL.") }
                    GlossaryRow { term: "Boids";         def: qsTr("Swarm algorithm with Separation/Alignment/Cohesion.") }
                    GlossaryRow { term: "Leader-Follower"; def: qsTr("Formation model: one leader, N followers with relative slot offsets.") }
                }
            }

            // ── 15. Tastatur ───────────────────────────────────────────────
            HelpSection {
                title: "TASTATUR & MAUS — SHORTCUTS"
                accent: Cmp.Theme.warning
                body:
                    // ─── Flug-Befehle ───────────────────────────────────────
                    "<b style='color:#fbbf24;letter-spacing:1px;'>FLUG-BEFEHLE</b><br>" +
                    "<table cellspacing='0' cellpadding='0' style='margin-top:4px;margin-bottom:10px;'>" +
                    "<tr><td style='width:180px'><b style='color:#93c5fd;font-family:Consolas'>Strg + A</b></td>" +
                        "<td style='color:#cbd5e1'>ARM &mdash; alle Mission-Targets armen (fällt auf Selected zurück)</td></tr>" +
                    "<tr><td><b style='color:#93c5fd;font-family:Consolas'>Strg + D</b></td>" +
                        "<td style='color:#cbd5e1'>DISARM &mdash; alle Mission-Targets disarmen</td></tr>" +
                    "<tr><td><b style='color:#93c5fd;font-family:Consolas'>Strg + T</b></td>" +
                        "<td style='color:#cbd5e1'>TAKEOFF auf 10 m AGL</td></tr>" +
                    "<tr><td><b style='color:#93c5fd;font-family:Consolas'>Strg + L</b></td>" +
                        "<td style='color:#cbd5e1'>LAND &mdash; in-place landen</td></tr>" +
                    "<tr><td><b style='color:#93c5fd;font-family:Consolas'>Strg + Pos1</b></td>" +
                        "<td style='color:#cbd5e1'>RTL &mdash; Return to Launch</td></tr>" +
                    "<tr><td><b style='color:#ef4444;font-family:Consolas'>Strg + E</b></td>" +
                        "<td style='color:#fca5a5'>EMERGENCY STOP &mdash; alle Drohnen sofort disarmen &#x26A0;</td></tr>" +
                    "</table>" +

                    // ─── Navigation ─────────────────────────────────────────
                    "<b style='color:#fbbf24;letter-spacing:1px;'>NAVIGATION</b><br>" +
                    "<table cellspacing='0' cellpadding='0' style='margin-top:4px;margin-bottom:10px;'>" +
                    "<tr><td style='width:180px'><b style='color:#93c5fd;font-family:Consolas'>Strg + M</b></td>" +
                        "<td style='color:#cbd5e1'>Zum Map-Tab springen</td></tr>" +
                    "<tr><td><b style='color:#93c5fd;font-family:Consolas'>Strg + 1 … 9</b></td>" +
                        "<td style='color:#cbd5e1'>Tab 1–9 direkt auswählen (1 = Map, 2 = Telemetry, 3 = Swarm, …)</td></tr>" +
                    "</table>" +

                    // ─── Karte / Mission ─────────────────────────────────────
                    "<b style='color:#fbbf24;letter-spacing:1px;'>KARTE &amp; MISSION</b><br>" +
                    "<table cellspacing='0' cellpadding='0' style='margin-top:4px;margin-bottom:10px;'>" +
                    "<tr><td style='width:180px'><b style='color:#93c5fd;font-family:Consolas'>Strg + W</b></td>" +
                        "<td style='color:#cbd5e1'>Waypoint-Modus aktivieren / deaktivieren</td></tr>" +
                    "<tr><td><b style='color:#93c5fd;font-family:Consolas'>ESC</b></td>" +
                        "<td style='color:#cbd5e1'>Waypoint-Modus / Map-Pick abbrechen (ohne WP zu setzen)</td></tr>" +
                    "<tr><td><b style='color:#93c5fd;font-family:Consolas'>Linksklick (WP-Modus)</b></td>" +
                        "<td style='color:#cbd5e1'>Wegpunkt auf Karte setzen</td></tr>" +
                    "</table>" +

                    // ─── System ──────────────────────────────────────────────
                    "<b style='color:#fbbf24;letter-spacing:1px;'>SYSTEM</b><br>" +
                    "<table cellspacing='0' cellpadding='0' style='margin-top:4px;margin-bottom:10px;'>" +
                    "<tr><td style='width:180px'><b style='color:#93c5fd;font-family:Consolas'>F5</b></td>" +
                        "<td style='color:#cbd5e1'>Serial-Ports im Header aktualisieren</td></tr>" +
                    "<tr><td><b style='color:#93c5fd;font-family:Consolas'>Strg + S (Script-Editor)</b></td>" +
                        "<td style='color:#cbd5e1'>Save &amp; Run im Experiment-Tab</td></tr>" +
                    "</table>" +

                    // ─── Maus ────────────────────────────────────────────────
                    "<b style='color:#fbbf24;letter-spacing:1px;'>MAUS</b><br>" +
                    "<table cellspacing='0' cellpadding='0' style='margin-top:4px;'>" +
                    "<tr><td style='width:180px'><b style='color:#94a3b8'>Klick auf Drohne (Sidebar)</b></td>" +
                        "<td style='color:#cbd5e1'>Selected-Drone setzen — Telemetrie-Anzeige folgt</td></tr>" +
                    "<tr><td><b style='color:#94a3b8'>Klick auf ☑ (Swarm-Tab)</b></td>" +
                        "<td style='color:#cbd5e1'>Mission-Target toggeln (Multi-Select)</td></tr>" +
                    "<tr><td><b style='color:#94a3b8'>Mausrad auf Map</b></td>" +
                        "<td style='color:#cbd5e1'>Zoom</td></tr>" +
                    "<tr><td><b style='color:#94a3b8'>Rechtsklick + Drag</b></td>" +
                        "<td style='color:#cbd5e1'>Karte schwenken (Pan)</td></tr>" +
                    "<tr><td><b style='color:#94a3b8'>Klick auf Drohnen-Marker</b></td>" +
                        "<td style='color:#cbd5e1'>Selected-Drone setzen + Karte zentrieren</td></tr>" +
                    "</table>" +

                    // ─── Hinweis ─────────────────────────────────────────────
                    "<br><span style='color:#475569;font-style:italic;font-size:10px;'>" +
                    "Alle Strg+-Shortcuts wirken auf die aktiven Mission-Targets (Häkchen-Set im Swarm-Tab). " +
                    "Leeres Set: fällt auf Selected Drone zurück. Leere Selection: erste Drohne in der Liste.<br>" +
                    "<b style='color:#f59e0b'>Einschränkung:</b> Strg+A/D/T/L werden vom Chromium-Renderer blockiert, " +
                    "solange der Map-Tab aktiv ist (WebEngineView konsumiert diese Tasten intern). " +
                    "Wechsle zuerst auf einen anderen Tab (z. B. Strg+3 für Swarm), dann funktionieren alle Shortcuts." +
                    "</span>"
            }

            // ── Modern Footer ───────────────────────────────────────────────
            Rectangle {
                width: parent.width
                height: 64
                radius: Cmp.Theme.radiusMd
                color: Cmp.Theme.bgPanel
                border.color: Cmp.Theme.border
                border.width: 1
                
                Column {
                    anchors.centerIn: parent
                    spacing: Cmp.Theme.spacing(0.5)
                    
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: qsTr("ⓘ For issues: collect System Log + syslogs/*.txt + console output.")
                        color: Cmp.Theme.textSecondary
                        font.pixelSize: Cmp.Theme.fontSm
                        font.italic: true
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: qsTr("ℹ️ This Help Panel is read-only — no bindings, no side effects.")
                        color: Cmp.Theme.textMuted
                        font.pixelSize: Cmp.Theme.fontXs
                        font.italic: true
                    }
                }
            }

            Item { width: 1; height: Cmp.Theme.spacing(1) }
        }
    }
}
