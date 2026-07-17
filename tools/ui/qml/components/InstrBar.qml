import QtQuick
import QtQuick.Controls
import "." as Cmp

Rectangle {
    id: root
    height: 110
    color: "#080c14"

    // Explicit swarm reference (passed from Loader)
    property var swarmRef: (typeof swarm !== "undefined") ? swarm : null
    property string selectedDroneId: ""

    // ── Resolve target list for quick commands / mode switch ─────────────
    // 1. If the user ticked one or more drones in the SwarmPanel mission-target
    //    list, those win (multi-drone fan-out).
    // 2. Otherwise fall back to the globally selected drone.
    // 3. Last resort: first drone in the swarm.
    function _commandTargets() {
        var sw = root.swarmRef
        if (!sw) return []
        var targets = (typeof Cmp.AppState !== "undefined" && Cmp.AppState)
                      ? Cmp.AppState.effectiveMissionTargets() : []
        if (targets && targets.length > 0) return targets
        var did = root.selectedDroneId
        if (did && did !== "") return [did]
        var ids = sw.droneIds ? sw.droneIds() : []
        return (ids && ids.length > 0) ? [ids[0]] : []
    }

    // ── Telemetry helper ──────────────────────────────────────────────────
    function snap(key, def) {
        var sw = root.swarmRef
        if (!sw) return def
        var did = root.selectedDroneId
        if (!did || did === "") return def   // no drone selected → show defaults, no jump to ids[0]
        var s = sw.droneSnapshot(did)
        return (s && s[key] !== undefined) ? s[key] : def
    }

    function battColor() {
        var pct = snap("battery_pct", 50)
        return pct > 50 ? "#22c55e" : pct > 20 ? "#f59e0b" : "#ef4444"
    }

    function climbColor() {
        var c = snap("climb", 0)
        return c > 0.3 ? "#22c55e" : c < -0.3 ? "#ef4444" : "#94a3b8"
    }

    // ── Reactive telemetry properties (updated by timer) ─────────────────
    property bool   t_armed:       false
    property string t_mode:        "---"
    property real   t_roll:        0
    property real   t_pitch:       0
    property real   t_yaw:         0
    property real   t_alt_rel:     0
    property real   t_alt:         0
    property real   t_groundspeed: 0
    property real   t_climb:       0
    property real   t_throttle:    0
    property real   t_battery_pct: -1
    property real   t_battery_v:   0
    property int    t_gps_fix:     0
    property int    t_satellites:  0

    function climbColor2()  { return t_climb > 0.3 ? "#22c55e" : t_climb < -0.3 ? "#ef4444" : "#94a3b8" }
    function battColor2()   { return t_battery_pct > 50 ? "#22c55e" : t_battery_pct > 20 ? "#f59e0b" : "#ef4444" }

    // ── Refresh timer (200 ms = 5 Hz — matches typical MAVLink stream rate)
    // Guard every assignment: QML fires property-change notifications even when
    // the new value equals the old one, which triggers re-evaluation of all
    // bound expressions (colors, Behaviors, Canvas repaints).  In a swarm
    // scenario the timer is shared across all drones and the redundant
    // re-evaluations cause visible flickering.
    Timer {
        interval: 200; running: true; repeat: true
        onTriggered: {
            var v
            v = snap("armed", false);       if (v !== root.t_armed)       root.t_armed       = v
            v = snap("flight_mode", "---"); if (v !== root.t_mode)        root.t_mode        = v
            v = snap("yaw",         0);     if (v !== root.t_yaw)         root.t_yaw         = v
            v = snap("alt_rel",     0);     if (v !== root.t_alt_rel)     root.t_alt_rel     = v
            v = snap("alt",         0);     if (v !== root.t_alt)         root.t_alt         = v
            v = snap("groundspeed", 0);     if (v !== root.t_groundspeed) root.t_groundspeed = v
            v = snap("climb",       0);     if (v !== root.t_climb)       root.t_climb       = v
            v = snap("throttle",    0);     if (v !== root.t_throttle)    root.t_throttle    = v
            v = snap("battery_pct", -1);    if (v !== root.t_battery_pct) root.t_battery_pct = v
            v = snap("battery_v",   0);     if (v !== root.t_battery_v)   root.t_battery_v   = v
            v = snap("gps_fix",     0);     if (v !== root.t_gps_fix)     root.t_gps_fix     = v
            v = snap("satellites",  0);     if (v !== root.t_satellites)  root.t_satellites  = v
            // Attitude: only repaint canvas when values actually changed
            var newRoll  = snap("roll",  0)
            var newPitch = snap("pitch", 0)
            if (newRoll !== root.t_roll || newPitch !== root.t_pitch) {
                root.t_roll        = newRoll
                root.t_pitch       = newPitch
                attCanvas.rollVal  = newRoll
                attCanvas.pitchVal = newPitch
                attCanvas.requestPaint()
            }
        }
    }

    // Top accent line
    Rectangle { anchors.top: parent.top; width: parent.width; height: 2
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "#2563eb" }
            GradientStop { position: 0.5; color: "#8b5cf6" }
            GradientStop { position: 1.0; color: "#22c55e" }
        }
    }

    // Horizontal Flickable for the scrollable middle section.
    Flickable {
        id: barFlick
        anchors { fill: parent; leftMargin: 12; rightMargin: 12; topMargin: 6; bottomMargin: 6 }
        clip: true
        contentWidth:  instrRow.implicitWidth + 12
        contentHeight: height
        flickableDirection: Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.horizontal: ScrollBar {
            policy: ScrollBar.AsNeeded
            height: 4
        }

        // Convert vertical wheel to horizontal scroll
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.NoButton
            propagateComposedEvents: true
            onWheel: function(wheelEvent) {
                if (barFlick.contentWidth > barFlick.width) {
                    barFlick.contentX = Math.max(0, Math.min(
                        barFlick.contentWidth - barFlick.width,
                        barFlick.contentX - wheelEvent.angleDelta.y / 2
                    ))
                    wheelEvent.accepted = true
                }
            }
        }

    Row {
        id: instrRow
        anchors { top: parent.top; bottom: parent.bottom }
        spacing: 6

        // ═══════════════════════════════════════════════════════════════════
        // NEW INSTRUMENT TILES
        // ═══════════════════════════════════════════════════════════════════

        // ── DRONE SELECTOR ────────────────────────────────────────────────
        Rectangle {
            width: 110; height: 90; radius: 8
            anchors.verticalCenter: parent.verticalCenter
            color: "#0d1117"
            border.color: "#1e293b"; border.width: 1

            Column {
                anchors.centerIn: parent; spacing: 4
                width: parent.width - 12

                Text {
                    text: "DRONE"
                    color: "#334155"; font.pixelSize: 8; font.weight: Font.Bold
                    font.letterSpacing: 0.8
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                // Combo with all known drones
                ComboBox {
                    id: droneSel
                    width: parent.width
                    height: 24
                    font.pixelSize: 10
                    font.family: "Consolas"
                    flat: true

                    property var _ids: (root.swarmRef && root.swarmRef.droneIds)
                                       ? root.swarmRef.droneIds() : []
                    model: _ids.length > 0 ? _ids : ["—"]

                    function _refresh() {
                        _ids = (root.swarmRef && root.swarmRef.droneIds)
                               ? root.swarmRef.droneIds() : []
                    }

                    onActivated: {
                        if (_ids.length > 0 && _ids[currentIndex]) {
                            root.selectedDroneId = _ids[currentIndex]
                        }
                    }

                    Connections {
                        target: root.swarmRef
                        function onDroneAdded()   { droneSel._refresh() }
                        function onDroneRemoved() { droneSel._refresh() }
                    }

                    // Keep combo selection in sync with global selectedDroneId
                    Connections {
                        target: root
                        function onSelectedDroneIdChanged() {
                            var idx = droneSel._ids.indexOf(root.selectedDroneId)
                            if (idx >= 0 && idx !== droneSel.currentIndex)
                                droneSel.currentIndex = idx
                        }
                    }
                }

                // Connection indicator
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter; spacing: 4
                    Rectangle {
                        width: 7; height: 7; radius: 3.5
                        anchors.verticalCenter: parent.verticalCenter
                        property bool _conn: {
                            if (!root.swarmRef || !root.selectedDroneId) return false
                            var s = root.swarmRef.droneSnapshot(root.selectedDroneId)
                            return s ? (s.connected === true) : false
                        }
                        color: _conn ? "#22c55e" : "#6b7280"
                    }
                    Text {
                        text: {
                            if (!root.swarmRef) return ""
                            var n = (root.swarmRef.droneIds ? root.swarmRef.droneIds().length : 0)
                            return n + " total"
                        }
                        color: "#64748b"; font.pixelSize: 8
                        font.family: "Consolas"
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }

        // Divider
        Rectangle { width: 1; height: 80; color: "#1e293b"; anchors.verticalCenter: parent.verticalCenter }

        // ── ARMED / MODE tile ─────────────────────────────────────────────
        Rectangle {
            width: 88; height: 90; radius: 8
            anchors.verticalCenter: parent.verticalCenter
            color: root.t_armed ? "#052e1a" : "#0d1117"
            border.color: root.t_armed ? "#22c55e" : "#1e293b"; border.width: 1.5
            Behavior on color { ColorAnimation { duration: 200 } }
            Behavior on border.color { ColorAnimation { duration: 200 } }

            Column {
                anchors.centerIn: parent; spacing: 4

                // Armed pulse dot
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 12; height: 12; radius: 6
                    color: root.t_armed ? "#22c55e" : "#374151"
                    Behavior on color { ColorAnimation { duration: 200 } }
                    SequentialAnimation on opacity {
                        running: root.t_armed
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.3; duration: 600 }
                        NumberAnimation { to: 1.0; duration: 600 }
                    }
                    opacity: root.t_armed ? 1.0 : 0.4
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.t_armed ? "ARMED" : "SAFE"
                    color: root.t_armed ? "#22c55e" : "#64748b"
                    font.pixelSize: 13; font.weight: Font.Black; font.letterSpacing: 0.5
                }

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 76; height: 20; radius: 4
                    color: "#0a0f1a"
                    border.color: "#2d3748"; border.width: 1
                    Text {
                        anchors.centerIn: parent
                        text: root.t_mode
                        color: "#60a5fa"; font.pixelSize: 10; font.weight: Font.Bold
                        font.family: "Consolas"
                    }
                }

                // Drone name removed - now shown in map overlay at top-center
            }
        }

        // Divider
        Rectangle { width: 1; height: 80; color: "#1e293b"; anchors.verticalCenter: parent.verticalCenter }

        // ── ATTITUDE INDICATOR ────────────────────────────────────────────
        Item {
            width: 90; height: 90; anchors.verticalCenter: parent.verticalCenter

            Canvas {
                id: attCanvas
                anchors.fill: parent
                property real rollVal:  0
                property real pitchVal: 0
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    var cx = width/2, cy = height/2, r = 42
                    // Background
                    ctx.fillStyle = "#0d1117"; ctx.fillRect(0,0,width,height)
                    // Clip circle
                    ctx.save()
                    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI*2); ctx.clip()
                    ctx.translate(cx, cy)
                    ctx.rotate(-attCanvas.rollVal * Math.PI / 180)
                    var po = attCanvas.pitchVal * 1.5
                    // Sky
                    ctx.fillStyle = "#0c2040"
                    ctx.fillRect(-r*2, -r*2, r*4, r*2 + po)
                    // Ground
                    ctx.fillStyle = "#3d1a00"
                    ctx.fillRect(-r*2, po, r*4, r*2)
                    // Horizon line
                    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1.5
                    ctx.beginPath(); ctx.moveTo(-r*2, po); ctx.lineTo(r*2, po); ctx.stroke()
                    // Pitch lines
                    ctx.strokeStyle = "#ffffff88"; ctx.lineWidth = 1
                    for (var pd = -20; pd <= 20; pd += 10) {
                        if (pd === 0) continue
                        var py = po - pd * 1.5
                        var lw = Math.abs(pd) === 10 ? 14 : 22
                        ctx.beginPath(); ctx.moveTo(-lw, py); ctx.lineTo(lw, py); ctx.stroke()
                    }
                    ctx.restore()
                    // Roll arc
                    ctx.strokeStyle = "#ffffff44"; ctx.lineWidth = 1
                    ctx.beginPath(); ctx.arc(cx, cy, r-3, Math.PI*1.15, Math.PI*1.85); ctx.stroke()
                    // Roll pointer
                    ctx.save(); ctx.translate(cx, cy); ctx.rotate(-attCanvas.rollVal * Math.PI / 180)
                    ctx.fillStyle = "#f59e0b"
                    ctx.beginPath(); ctx.moveTo(0,-(r-3)); ctx.lineTo(-4,-(r-12)); ctx.lineTo(4,-(r-12)); ctx.closePath(); ctx.fill()
                    ctx.restore()
                    // Aircraft symbol
                    ctx.strokeStyle = "#f59e0b"; ctx.lineWidth = 2; ctx.lineCap = "round"
                    ctx.beginPath()
                    ctx.moveTo(cx-22, cy); ctx.lineTo(cx-8, cy)
                    ctx.moveTo(cx+8,  cy); ctx.lineTo(cx+22, cy)
                    ctx.moveTo(cx, cy-5); ctx.lineTo(cx, cy+3)
                    ctx.stroke()
                    ctx.fillStyle = "#f59e0b"
                    ctx.beginPath(); ctx.arc(cx, cy, 2.5, 0, Math.PI*2); ctx.fill()
                    // Circle border
                    ctx.strokeStyle = "#334155"; ctx.lineWidth = 2
                    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI*2); ctx.stroke()
                }
            }
            Text {
                anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: 0 }
                text: "ATT  R:" + root.t_roll.toFixed(0) + "°  P:" + root.t_pitch.toFixed(0) + "°"
                color: "#475569"; font.pixelSize: 7; font.family: "Consolas"
            }
        }

        // Divider
        Rectangle { width: 1; height: 80; color: "#1e293b"; anchors.verticalCenter: parent.verticalCenter }

        // ── COMPASS ───────────────────────────────────────────────────────
        Item {
            width: 90; height: 90; anchors.verticalCenter: parent.verticalCenter

            Cmp.CompassInstrument {
                anchors { top: parent.top; horizontalCenter: parent.horizontalCenter }
                heading: root.t_yaw
                size: 80
                showLabel: true
            }
        }

        // Divider
        Rectangle { width: 1; height: 80; color: "#1e293b"; anchors.verticalCenter: parent.verticalCenter }

        // ── NUMERIC TILES: ALT / SPEED / CLIMB ───────────────────────────
        Row {
            spacing: 5; anchors.verticalCenter: parent.verticalCenter

            // ALT
            Rectangle {
                width: 80; height: 90; radius: 8; color: "#0a0f1a"
                border.color: "#1e3a5f"; border.width: 1
                Column { anchors.centerIn: parent; spacing: 2
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: "ALT"; color: "#3b82f6"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: root.t_alt_rel.toFixed(1)
                           color: "#93c5fd"; font.pixelSize: 22; font.weight: Font.Black; font.family: "Consolas" }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: "meters"; color: "#334155"; font.pixelSize: 8 }
                    Rectangle { anchors.horizontalCenter: parent.horizontalCenter
                                width: 60; height: 4; radius: 2; color: "#1e293b"
                        Rectangle { width: Math.min(parent.width, parent.width * root.t_alt_rel / 120)
                                    height: parent.height; radius: 2; color: "#3b82f6"
                            Behavior on width { NumberAnimation { duration: 200 } } }
                    }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: "AMSL " + root.t_alt.toFixed(0) + "m"
                           color: "#334155"; font.pixelSize: 7; font.family: "Consolas" }
                }
            }

            // SPEED
            Rectangle {
                width: 80; height: 90; radius: 8; color: "#0a0f1a"
                border.color: "#1a3a1a"; border.width: 1
                Column { anchors.centerIn: parent; spacing: 2
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: "SPEED"; color: "#22c55e"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: root.t_groundspeed.toFixed(1)
                           color: "#86efac"; font.pixelSize: 22; font.weight: Font.Black; font.family: "Consolas" }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: "m/s"; color: "#334155"; font.pixelSize: 8 }
                    Rectangle { anchors.horizontalCenter: parent.horizontalCenter
                                width: 60; height: 4; radius: 2; color: "#1e293b"
                        Rectangle { width: Math.min(parent.width, parent.width * root.t_groundspeed / 20)
                                    height: parent.height; radius: 2; color: "#22c55e"
                            Behavior on width { NumberAnimation { duration: 200 } } }
                    }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: (root.t_groundspeed * 3.6).toFixed(1) + " km/h"
                           color: "#334155"; font.pixelSize: 7; font.family: "Consolas" }
                }
            }

            // CLIMB
            Rectangle {
                width: 80; height: 90; radius: 8; color: "#0a0f1a"
                border.color: root.t_climb > 0.3 ? "#14532d" : root.t_climb < -0.3 ? "#450a0a" : "#1e293b"
                border.width: 1
                Behavior on border.color { ColorAnimation { duration: 300 } }
                Column { anchors.centerIn: parent; spacing: 2
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: "CLIMB"; color: climbColor2(); font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                    Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 2
                        Text { text: root.t_climb > 0.3 ? "▲" : root.t_climb < -0.3 ? "▼" : "─"
                               color: climbColor2(); font.pixelSize: 14; font.weight: Font.Bold
                               anchors.verticalCenter: parent.verticalCenter }
                        Text { text: Math.abs(root.t_climb).toFixed(1)
                               color: climbColor2(); font.pixelSize: 22; font.weight: Font.Black; font.family: "Consolas" }
                    }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: "m/s"; color: "#334155"; font.pixelSize: 8 }
                    // VSI tape bar
                    Item { anchors.horizontalCenter: parent.horizontalCenter; width: 60; height: 8
                        Rectangle { anchors.centerIn: parent; width: 60; height: 4; radius: 2; color: "#1e293b" }
                        Rectangle {
                            height: 4; radius: 2
                            width: Math.min(30, Math.abs(root.t_climb) / 5 * 30)
                            color: climbColor2()
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: root.t_climb >= 0 ? parent.horizontalCenter : undefined
                            anchors.right: root.t_climb < 0  ? parent.horizontalCenter : undefined
                            Behavior on width { NumberAnimation { duration: 200 } }
                        }
                    }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
                           text: root.t_throttle.toFixed(0) + "% thr"
                           color: "#334155"; font.pixelSize: 7; font.family: "Consolas" }
                }
            }
        }

        // Divider
        Rectangle { width: 1; height: 80; color: "#1e293b"; anchors.verticalCenter: parent.verticalCenter }

        // ── BATTERY + GPS tile ────────────────────────────────────────────
        Rectangle {
            width: 90; height: 90; radius: 8; color: "#0a0f1a"
            border.color: {
                var pct = root.t_battery_pct
                return pct < 0 ? "#1e293b" : pct < 20 ? "#7f1d1d" : "#1e293b"
            }
            border.width: 1
            Column {
                anchors { fill: parent; margins: 8 }
                spacing: 5

                // Battery header
                Row { spacing: 4
                    Text { text: "⚡"; font.pixelSize: 11; color: battColor2(); anchors.verticalCenter: parent.verticalCenter }
                    Text { text: "BATTERY"; color: battColor2(); font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 0.5; anchors.verticalCenter: parent.verticalCenter }
                }

                // Big % value
                Row { spacing: 4; anchors.horizontalCenter: parent.horizontalCenter
                    Text {
                        text: root.t_battery_pct >= 0 ? root.t_battery_pct.toFixed(0) : "—"
                        color: battColor2(); font.pixelSize: 26; font.weight: Font.Black; font.family: "Consolas"
                    }
                    Text {
                        text: root.t_battery_pct >= 0 ? "%" : ""
                        color: battColor2(); font.pixelSize: 13; font.weight: Font.Bold
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 4
                    }
                }

                // Bar
                Rectangle {
                    width: parent.width; height: 5; radius: 2.5; color: "#1e293b"
                    Rectangle {
                        width: root.t_battery_pct >= 0 ? Math.max(0, parent.width * root.t_battery_pct / 100) : 0
                        height: parent.height; radius: 2.5; color: battColor2()
                        Behavior on width { NumberAnimation { duration: 400 } }
                    }
                }

                // Voltage
                Text {
                    text: root.t_battery_v > 0 ? root.t_battery_v.toFixed(2) + " V" : "— V"
                    color: "#64748b"; font.pixelSize: 9; font.family: "Consolas"
                }

                // GPS row
                Row { spacing: 4
                    Rectangle { width: 7; height: 7; radius: 3.5
                                 color: root.t_gps_fix >= 3 ? "#22c55e" : "#f59e0b"
                                 anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        text: ["NoFix","NoFix","2D","3D","RTK"][Math.min(root.t_gps_fix,4)]
                              + "  " + root.t_satellites + " sat"
                        color: "#64748b"; font.pixelSize: 8; font.family: "Consolas"
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }

        // Divider
        Rectangle { width: 1; height: 80; color: "#1e293b"; anchors.verticalCenter: parent.verticalCenter }

        // ── QUICK COMMANDS ────────────────────────────────────────────────
        Column {
            anchors.verticalCenter: parent.verticalCenter; spacing: 5

            Text { text: "QUICK CMD"; color: "#334155"; font.pixelSize: 8; font.weight: Font.Bold
                   font.letterSpacing: 0.8; anchors.horizontalCenter: parent.horizontalCenter }

            Grid {
                columns: 3; spacing: 5; anchors.horizontalCenter: parent.horizontalCenter

                Repeater {
                    model: [
                        { label: "ARM",    icon: "▶",  color: "#22c55e", cmd: "arm"     },
                        { label: "DISARM", icon: "■",  color: "#ef4444", cmd: "disarm"  },
                        { label: "TAKEOFF",icon: "↑",  color: "#2563eb", cmd: "takeoff" },
                        { label: "LAND",   icon: "↓",  color: "#f59e0b", cmd: "land"    },
                        { label: "RTL",    icon: "⌂",  color: "#f97316", cmd: "rtl"     },
                        { label: "HOLD",   icon: "⊙",  color: "#8b5cf6", cmd: "hold"    },
                    ]
                    delegate: Rectangle {
                        width: 52; height: 32; radius: 6
                        color: qMa.containsPress ? Qt.darker(modelData.color, 1.8)
                             : qMa.containsMouse  ? (modelData.color + "22") : "#0d1117"
                        border.color: qMa.containsMouse ? modelData.color : "#1e293b"; border.width: 1
                        Behavior on color { ColorAnimation { duration: 80 } }
                        Column { anchors.centerIn: parent; spacing: 1
                            Text { anchors.horizontalCenter: parent.horizontalCenter
                                   text: modelData.icon; color: modelData.color; font.pixelSize: 11 }
                            Text { anchors.horizontalCenter: parent.horizontalCenter
                                   text: modelData.label; color: modelData.color
                                   font.pixelSize: 7; font.weight: Font.Bold }
                        }
                        MouseArea {
                            id: qMa; anchors.fill: parent; hoverEnabled: true
                            onClicked: {
                                var sw = root.swarmRef
                                if (!sw) return
                                var targets = root._commandTargets()
                                if (targets.length === 0) return
                                var alt = parseFloat(setAltField.text) || 10
                                for (var i = 0; i < targets.length; i++) {
                                    var did = targets[i]
                                    if      (modelData.cmd === "arm")     sw.armDrone(did)
                                    else if (modelData.cmd === "disarm")  sw.disarmDrone(did)
                                    else if (modelData.cmd === "takeoff") sw.takeoffDrone(did, alt)
                                    else if (modelData.cmd === "land")    sw.landDrone(did)
                                    else if (modelData.cmd === "rtl")     sw.rtlDrone(did)
                                }
                            }
                        }
                    }
                }
            }
        }

        // Divider
        Rectangle { width: 1; height: 80; color: "#1e293b"; anchors.verticalCenter: parent.verticalCenter }

        // ── FLIGHT MODE SWITCHER ─────────────────────────────────────────
        Column {
            anchors.verticalCenter: parent.verticalCenter; spacing: 5

            Text { text: "FLIGHT MODE"; color: "#334155"; font.pixelSize: 8; font.weight: Font.Bold
                   font.letterSpacing: 0.8; anchors.horizontalCenter: parent.horizontalCenter }

            Grid {
                columns: 3; spacing: 4; anchors.horizontalCenter: parent.horizontalCenter

                Repeater {
                    model: [
                        { label: "STAB",   mode: "STABILIZE", color: "#94a3b8" },
                        { label: "ALT-H",  mode: "ALT_HOLD",  color: "#06b6d4" },
                        { label: "LOITER", mode: "LOITER",    color: "#22c55e" },
                        { label: "GUIDED", mode: "GUIDED",    color: "#2563eb" },
                        { label: "AUTO",   mode: "AUTO",      color: "#8b5cf6" },
                        { label: "POSHLD", mode: "POSHOLD",   color: "#f59e0b" },
                    ]
                    delegate: Rectangle {
                        width: 44; height: 30; radius: 5
                        property bool _active: root.t_mode === modelData.mode
                        color: mMa.containsPress ? Qt.darker(modelData.color, 1.8)
                             : _active ? (modelData.color + "33")
                             : mMa.containsMouse ? (modelData.color + "18") : "#0d1117"
                        border.color: _active ? modelData.color
                                     : mMa.containsMouse ? modelData.color : "#1e293b"
                        border.width: _active ? 1.5 : 1
                        Behavior on color { ColorAnimation { duration: 80 } }
                        Text {
                            anchors.centerIn: parent
                            text: modelData.label
                            color: _active || mMa.containsMouse ? modelData.color : "#64748b"
                            font.pixelSize: 8; font.weight: Font.Bold
                            font.family: "Consolas"
                        }
                        MouseArea {
                            id: mMa; anchors.fill: parent; hoverEnabled: true
                            onClicked: {
                                var sw = root.swarmRef
                                if (!sw) return
                                var targets = root._commandTargets()
                                for (var i = 0; i < targets.length; i++)
                                    sw.setMode(targets[i], modelData.mode)
                            }
                        }
                    }
                }
            }
        }

        // Divider
        Rectangle { width: 1; height: 80; color: "#1e293b"; anchors.verticalCenter: parent.verticalCenter }

        // ── ALTITUDE CONTROL ─────────────────────────────────────────────
        Column {
            anchors.verticalCenter: parent.verticalCenter; spacing: 4

            Text { text: "ALTITUDE"; color: "#334155"; font.pixelSize: 8; font.weight: Font.Bold
                   font.letterSpacing: 0.8; anchors.horizontalCenter: parent.horizontalCenter }

            // Set Altitude (also used for T/O)
            Row {
                spacing: 4; anchors.horizontalCenter: parent.horizontalCenter

                Text { text: "Set Alt:"; color: "#64748b"; font.pixelSize: 8; anchors.verticalCenter: parent.verticalCenter }

                Rectangle {
                    width: 52; height: 22; radius: 4
                    color: "#0d1117"; border.color: "#334155"; border.width: 1
                    TextField {
                        id: setAltField
                        anchors.fill: parent
                        text: "10"
                        horizontalAlignment: Text.AlignHCenter
                        background: null
                        color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"
                        inputMethodHints: Qt.ImhFormattedNumbersOnly
                        validator: DoubleValidator { bottom: 0.5; top: 200; decimals: 1 }
                    }
                }

                Text { text: "m"; color: "#64748b"; font.pixelSize: 8; anchors.verticalCenter: parent.verticalCenter }

                Rectangle {
                    width: 52; height: 22; radius: 4
                    color: setAltMa.containsMouse ? "#1d4ed8" : "#1e3a5f"
                    border.color: "#2563eb"; border.width: 1
                    Behavior on color { ColorAnimation { duration: 80 } }
                    Text { anchors.centerIn: parent; text: "▲ Set"; color: "#93c5fd"; font.pixelSize: 9; font.weight: Font.Bold }
                    MouseArea {
                        id: setAltMa; anchors.fill: parent; hoverEnabled: true
                        onClicked: {
                            if (typeof swarm === "undefined" || !swarm) return
                            var alt = parseFloat(setAltField.text)
                            if (isNaN(alt) || alt <= 0) return
                            var ids = root._commandTargets()
                            for (var i = 0; i < ids.length; i++) {
                                var did = ids[i]
                                var s = swarm.droneSnapshot(did)
                                if (!s) continue
                                var lat   = s.lat || 0
                                var lon   = s.lon || 0
                                var armed = s.armed || false
                                if (lat === 0 || lon === 0) continue
                                if (armed) swarm.gotoDrone(did, lat, lon, alt)
                                else       swarm.smartGotoDrone(did, lat, lon, alt)
                            }
                        }
                    }
                }
            }

        }

        // Divider
        Rectangle { width: 1; height: 80; color: "#1e293b"; anchors.verticalCenter: parent.verticalCenter }

        // ── APF / SAFETY ──────────────────────────────────────────────────
        Column {
            anchors.verticalCenter: parent.verticalCenter; spacing: 4

            Text { text: "SAFETY / APF"; color: "#334155"; font.pixelSize: 8; font.weight: Font.Bold
                   font.letterSpacing: 0.8; anchors.horizontalCenter: parent.horizontalCenter }

            // APF Status + Enable toggle
            Row {
                spacing: 6; anchors.horizontalCenter: parent.horizontalCenter

                // Status indicator
                Rectangle {
                    width: 80; height: 26; radius: 5
                    color: (typeof safety !== "undefined" && safety && safety.apfActive) ? "#14532d" : "#1a2035"
                    border.color: (typeof safety !== "undefined" && safety && safety.apfActive) ? "#22c55e" : "#374151"
                    border.width: 1
                    Row {
                        anchors.centerIn: parent; spacing: 4
                        Rectangle {
                            width: 7; height: 7; radius: 3.5; anchors.verticalCenter: parent.verticalCenter
                            color: (typeof safety !== "undefined" && safety && safety.apfActive) ? "#22c55e" : "#6b7280"
                        }
                        Text {
                            text: (typeof safety !== "undefined" && safety && safety.apfActive) ? "APF ON" : "APF OFF"
                            color: (typeof safety !== "undefined" && safety && safety.apfActive) ? "#86efac" : "#9ca3af"
                            font.pixelSize: 9; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                // Enable/Disable toggle button
                Rectangle {
                    width: 60; height: 26; radius: 5
                    color: apfTogMa.containsMouse
                           ? ((typeof safety !== "undefined" && safety && safety.apfActive) ? "#7f1d1d" : "#166534")
                           : "#1e2535"
                    border.color: (typeof safety !== "undefined" && safety && safety.apfActive) ? "#ef4444" : "#22c55e"
                    border.width: 1
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Text {
                        anchors.centerIn: parent
                        text: (typeof safety !== "undefined" && safety && safety.apfActive) ? "Disable" : "Enable"
                        color: (typeof safety !== "undefined" && safety && safety.apfActive) ? "#fca5a5" : "#86efac"
                        font.pixelSize: 8; font.weight: Font.Bold
                    }
                    MouseArea {
                        id: apfTogMa; anchors.fill: parent; hoverEnabled: true
                        onClicked: {
                            if (typeof safety === "undefined" || !safety) return
                            if (safety.apfActive) safety.disableAPF()
                            else safety.configureAPF({})
                        }
                    }
                }
            }

            // Violations counter
            Row {
                spacing: 6; anchors.horizontalCenter: parent.horizontalCenter
                Text { text: "Violations:"; color: "#64748b"; font.pixelSize: 8; anchors.verticalCenter: parent.verticalCenter }
                Rectangle {
                    width: 36; height: 20; radius: 10
                    color: (typeof safety !== "undefined" && safety && safety.violationCount > 0) ? "#7f1d1d" : "#1e2535"
                    Text {
                        anchors.centerIn: parent
                        text: (typeof safety !== "undefined" && safety) ? safety.violationCount : "0"
                        color: (typeof safety !== "undefined" && safety && safety.violationCount > 0) ? "#fca5a5" : "#64748b"
                        font.pixelSize: 10; font.weight: Font.Bold; font.family: "Consolas"
                    }
                }
            }
        }

        // Stretch filler
        Item { height: 1; width: 1 }
    }   // end Row
    }   // end Flickable
}
