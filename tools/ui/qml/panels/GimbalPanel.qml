import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components" as Cmp

Item {
    id: root
    anchors.fill: parent

    property string selectedDroneId: Cmp.AppState.selectedDroneId !== ""
                                      ? Cmp.AppState.selectedDroneId
                                      : (typeof swarm !== "undefined" ? (swarm.droneIds().length > 0 ? swarm.droneIds()[0] : "") : "")

    function isObservation(did) {
        if (!did || typeof swarm === "undefined" || !swarm) return false
        return String(swarm.droneType(did) || "").toLowerCase() === "observation"
    }

    // Select the drone in VideoStreamContext when this panel opens so the
    // stream status badge and frame URL are already wired up.
    Component.onCompleted: {
        if (root.selectedDroneId !== "" &&
            typeof videoStream !== "undefined" && videoStream)
            videoStream.selectDrone(root.selectedDroneId)
    }

    Connections {
        target: Cmp.AppState
        function onSelectedDroneIdChanged() {
            root.selectedDroneId = Cmp.AppState.selectedDroneId
            if (typeof videoStream !== "undefined" && videoStream && root.selectedDroneId !== "")
                videoStream.selectDrone(root.selectedDroneId)
        }
    }

    ScrollView {
        id: sv
        anchors { fill: parent; margins: 12 }
        clip: true
        contentWidth: availableWidth
        contentHeight: colMain.implicitHeight
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        Column {
            id: colMain
            width: sv.availableWidth
            spacing: 10

            // ── Drone selector ──────────────────────────────────────────
            Text { text: qsTr("GIMBAL / CAMERA"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }

            Rectangle {
                width: parent.width; height: 36; radius: 8
                color: "#1a2035"; border.color: "#2d3748"; border.width: 1

                Row {
                    anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                    spacing: 8

                    Text { text: qsTr("Drone:"); color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                    ComboBox {
                        id: droneCombo
                        width: parent.width - 60; height: 26
                        model: (typeof swarm !== "undefined" && swarm) ? swarm.droneIds() : []
                        background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                        contentItem: Text { text: droneCombo.displayText; color: "#e2e8f0"; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: 6 }
                        onCurrentTextChanged: {
                            if (currentText) {
                                root.selectedDroneId = currentText
                                Cmp.AppState.selectedDroneId = currentText
                                if (typeof videoStream !== "undefined" && videoStream)
                                    videoStream.selectDrone(currentText)
                            }
                        }
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }

            // ── Observation-only warning ────────────────────────────────
            Rectangle {
                width: parent.width; height: 34; radius: 6
                color: "#78350f22"
                border.color: "#f59e0b"; border.width: 1
                visible: root.selectedDroneId !== "" && !isObservation(root.selectedDroneId)

                Row {
                    anchors { fill: parent; leftMargin: 10 }
                    spacing: 6
                    Text { text: "⚠"; color: "#f59e0b"; font.pixelSize: 14; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        text: qsTr("Gimbal only for Observation UAV (Drone type = observation)")
                        color: "#fcd34d"; font.pixelSize: 10
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }

            // ── Stream type selector ────────────────────────────────────
            Text { text: qsTr("STREAM ANZEIGE"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; topPadding: 10 }

            Rectangle {
                width: parent.width; height: 36; radius: 8
                color: "#1a2035"; border.color: "#2d3748"; border.width: 1

                Row {
                    anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                    spacing: 8
                    Text { text: qsTr("Anzeige:"); color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                    ComboBox {
                        id: streamTypeCombo
                        width: parent.width - 70; height: 26
                        model: [
                            qsTr("Kamera (Video-Stream)"),
                            qsTr("LiDAR — /lidar/scan"),
                            qsTr("Optical Flow — /flow_camera/image"),
                        ]
                        background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                        contentItem: Text {
                            text: streamTypeCombo.displayText; color: "#e2e8f0"
                            font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: 6
                        }
                        delegate: ItemDelegate {
                            width: streamTypeCombo.width
                            contentItem: Text { text: modelData; color: "#e2e8f0"; font.pixelSize: 11 }
                            background: Rectangle { color: hovered ? "#2d3748" : "#1e2535" }
                        }
                        popup: Popup {
                            y: streamTypeCombo.height; width: streamTypeCombo.width; padding: 0
                            background: Rectangle { color: "#1e2535"; border.color: "#2d3748"; radius: 5 }
                            contentItem: ListView { clip: true; implicitHeight: contentHeight; model: streamTypeCombo.delegateModel }
                        }
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }

            // ── Unified stream display area ─────────────────────────────
            // One box, three layers: Camera / LiDAR / Flow — selected via dropdown above.
            // Height is fixed at 280px for LiDAR/Flow, 16:9 for Camera.
            Rectangle {
                id: streamDisplayBox
                width: parent.width
                height: streamTypeCombo.currentIndex === 0
                        ? Math.min(parent.width * 9/16, 360)
                        : 280
                radius: 8; clip: true
                color: streamTypeCombo.currentIndex === 1 ? "#040710"
                     : streamTypeCombo.currentIndex === 2 ? "#040710"
                     : "#0d1117"
                border.color: streamTypeCombo.currentIndex === 1 ? "#1e3a5f"
                            : streamTypeCombo.currentIndex === 2 ? "#3b0764"
                            : "#2d3748"
                border.width: 1

                // ── Badge top-left showing which stream is active ──────
                Rectangle {
                    anchors { top: parent.top; left: parent.left; margins: 6 }
                    width: badgeTxt.implicitWidth + 12; height: 20; radius: 4; z: 4
                    color: streamTypeCombo.currentIndex === 1 ? "#1e3a5f"
                         : streamTypeCombo.currentIndex === 2 ? "#3b0764"
                         : "#059669"
                    visible: streamTypeCombo.currentIndex !== 0 ||
                             (videoDisplayBox._vsStatus === "receiving" && videoDisplayBox._activeTarget === "gimbal" && videoDisplayBox._hasFrame)
                    Text {
                        id: badgeTxt
                        anchors.centerIn: parent
                        text: streamTypeCombo.currentIndex === 1 ? "◉ LiDAR"
                            : streamTypeCombo.currentIndex === 2 ? "◉ Flow"
                            : "● LIVE"
                        color: "white"; font.pixelSize: 9; font.weight: Font.Bold
                    }
                }

                // ════════════════════════════════════════════════════════
                // LAYER 0 — Camera (GStreamer / VideoStream)
                // ════════════════════════════════════════════════════════
                Item {
                    anchors.fill: parent
                    visible: streamTypeCombo.currentIndex === 0

                    // Shared properties for stream status
                    property string _vsStatus: "unconfigured"
                    property string _activeTarget: ""
                    property bool   _hasFrame: false
                    id: videoDisplayBox

                    Timer { interval: 250; running: streamTypeCombo.currentIndex === 0; repeat: true
                        onTriggered: {
                            if (typeof videoStream === "undefined" || !videoStream || !root.selectedDroneId) return
                            var s = videoStream.getVideoStatus(root.selectedDroneId)
                            videoDisplayBox._vsStatus     = s ? (s.status     || "unconfigured") : "unconfigured"
                            videoDisplayBox._activeTarget = s ? (s.activeTarget || "")           : ""
                            videoDisplayBox._hasFrame     = !!(s && s.hasFrame)
                            if (videoDisplayBox._vsStatus === "receiving" &&
                                videoDisplayBox._activeTarget === "gimbal" &&
                                videoDisplayBox._hasFrame)
                                gimbalVideoFrame.source = videoStream.frameUrl(root.selectedDroneId)
                        }
                    }
                    Connections {
                        target: typeof videoStream !== "undefined" ? videoStream : null
                        function onFrameChanged(droneId, frameUrl) {
                            if (droneId !== root.selectedDroneId) return
                            var s = videoStream.getVideoStatus(droneId)
                            videoDisplayBox._vsStatus     = s ? (s.status      || "unconfigured") : "unconfigured"
                            videoDisplayBox._activeTarget = s ? (s.activeTarget || "")            : ""
                            videoDisplayBox._hasFrame     = !!(s && s.hasFrame)
                            if (videoDisplayBox._activeTarget === "gimbal")
                                gimbalVideoFrame.source = frameUrl
                        }
                    }

                    Rectangle { anchors.fill: parent; color: "#000000"; radius: 6
                        Image {
                            id: gimbalVideoFrame
                            anchors.fill: parent; cache: false; asynchronous: true
                            fillMode: Image.PreserveAspectFit; source: ""
                            visible: videoDisplayBox._vsStatus === "receiving" &&
                                     videoDisplayBox._activeTarget === "gimbal" &&
                                     videoDisplayBox._hasFrame
                        }

                        // No-stream placeholder
                        Column {
                            anchors.centerIn: parent; spacing: 10
                            visible: !(videoDisplayBox._vsStatus === "receiving" &&
                                       videoDisplayBox._activeTarget === "gimbal" &&
                                       videoDisplayBox._hasFrame)
                            Text {
                                text: { var s = videoDisplayBox._vsStatus
                                    if (s === "waiting") return "⏳"
                                    if (s === "stalled") return "⚠"
                                    if (s === "error")   return "✕"
                                    return "📹" }
                                color: { var s = videoDisplayBox._vsStatus
                                    if (s === "waiting") return "#f59e0b"
                                    if (s === "stalled") return "#f97316"
                                    if (s === "error")   return "#ef4444"
                                    return "#64748b" }
                                font.pixelSize: 40; anchors.horizontalCenter: parent.horizontalCenter
                            }
                            Text {
                                text: { var s = videoDisplayBox._vsStatus
                                    if (s === "waiting") return qsTr("Warte auf Stream…")
                                    if (s === "stalled") return qsTr("Stream gestoppt")
                                    if (s === "error")   return qsTr("Stream-Fehler")
                                    return qsTr("Kein aktiver Stream") }
                                color: { var s = videoDisplayBox._vsStatus
                                    if (s === "waiting") return "#f59e0b"
                                    if (s === "stalled") return "#f97316"
                                    if (s === "error")   return "#ef4444"
                                    return "#64748b" }
                                font.pixelSize: 13; anchors.horizontalCenter: parent.horizontalCenter
                            }
                            Text {
                                text: { if (typeof videoStream === "undefined" || !videoStream || !root.selectedDroneId) return ""
                                    var s = videoStream.getVideoStatus(root.selectedDroneId)
                                    return s && s.url ? s.url : qsTr("Stream in ROS2-Panel → Video Stream konfigurieren") }
                                color: "#475569"; font.pixelSize: 9; font.family: "Consolas"
                                anchors.horizontalCenter: parent.horizontalCenter
                                wrapMode: Text.WordWrap; width: parent.width * 0.9
                            }
                        }

                        // Bottom status bar — only when receiving
                        Rectangle {
                            anchors { bottom: parent.bottom; left: parent.left; right: parent.right; margins: 6 }
                            height: 26; radius: 4; color: "#cc1a2035"
                            visible: videoDisplayBox._vsStatus === "receiving" &&
                                     videoDisplayBox._activeTarget === "gimbal" &&
                                     videoDisplayBox._hasFrame
                            Row {
                                anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                                spacing: 10
                                Text { text: typeof camera !== "undefined" ? camera.currentSource : "—"
                                    color: "#e2e8f0"; font.pixelSize: 9; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter }
                                Rectangle { width: 1; height: 14; color: "#334155"; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: { if (typeof camera === "undefined") return "—"
                                    var st = camera.getCameraStatus(); return st.resolution || "—" }
                                    color: "#94a3b8"; font.pixelSize: 9; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: { if (typeof camera === "undefined") return "—"
                                    var st = camera.getCameraStatus(); return st.fps ? st.fps + " fps" : "—" }
                                    color: "#94a3b8"; font.pixelSize: 9; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter }
                                Item { width: 1; height: 1; Layout.fillWidth: true }
                                Row { spacing: 4; anchors.verticalCenter: parent.verticalCenter
                                    visible: typeof camera !== "undefined" && camera.recordingActive
                                    Rectangle { width: 7; height: 7; radius: 3.5; color: "#ef4444"; anchors.verticalCenter: parent.verticalCenter
                                        SequentialAnimation on opacity { running: true; loops: Animation.Infinite
                                            NumberAnimation { from: 1.0; to: 0.2; duration: 600 }
                                            NumberAnimation { from: 0.2; to: 1.0; duration: 600 } } }
                                    Text { text: "REC"; color: "#ef4444"; font.pixelSize: 9; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                                }
                            }
                        }
                    }
                }

                // ════════════════════════════════════════════════════════
                // LAYER 1 — LiDAR polar (MAVLink OBSTACLE_DISTANCE)
                // ════════════════════════════════════════════════════════
                Item {
                    anchors.fill: parent
                    visible: streamTypeCombo.currentIndex === 1
                    id: lidarLayer

                    property var  _ranges:    []
                    property real _angleMin:  0
                    property real _angleStep: 0.5
                    property real _maxRange:  20.0

                    Timer {
                        interval: 200; running: lidarLayer.visible; repeat: true
                        onTriggered: {
                            if (typeof telemetryModel === "undefined" || !telemetryModel || !root.selectedDroneId) return
                            var snap = telemetryModel.snapshotFor(root.selectedDroneId)
                            if (!snap) return
                            var od = snap["obstacle_distance"] || snap["OBSTACLE_DISTANCE"]
                            if (!od || !od.distances) return
                            lidarLayer._ranges    = od.distances    || []
                            lidarLayer._angleMin  = od.angle_offset || 0
                            lidarLayer._angleStep = od.increment_f  || 0.5
                            lidarLayer._maxRange  = od.max_distance ? od.max_distance / 100.0 : 20.0
                            lidarGimbalCanvas.requestPaint()
                        }
                    }

                    Canvas {
                        id: lidarGimbalCanvas
                        anchors.fill: parent
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            var cx = width / 2; var cy = height / 2
                            var R  = Math.min(width, height) / 2 - 20

                            // Grid rings + spokes
                            ctx.strokeStyle = "#1e2535"; ctx.lineWidth = 1
                            for (var r = 1; r <= 4; r++) {
                                ctx.beginPath(); ctx.arc(cx, cy, R * r / 4, 0, Math.PI * 2); ctx.stroke()
                            }
                            for (var a = 0; a < 360; a += 45) {
                                var rad = a * Math.PI / 180
                                ctx.beginPath(); ctx.moveTo(cx, cy)
                                ctx.lineTo(cx + Math.sin(rad) * R, cy - Math.cos(rad) * R); ctx.stroke()
                            }
                            // Range labels
                            ctx.fillStyle = "#475569"; ctx.font = "9px Consolas"; ctx.textAlign = "left"
                            for (var ri = 1; ri <= 4; ri++) {
                                var lr = lidarLayer._maxRange * ri / 4
                                ctx.fillText(lr.toFixed(0) + "m", cx + R * ri / 4 + 3, cy - 2)
                            }

                            var distances = lidarLayer._ranges
                            if (!distances || distances.length === 0) {
                                ctx.fillStyle = "#374151"; ctx.font = "11px Consolas"; ctx.textAlign = "center"
                                ctx.fillText("Keine LiDAR-Daten", cx, cy - 8)
                                ctx.fillText("(PRX1_TYPE=2 oder RNGFND1_TYPE=10)", cx, cy + 8)
                                return
                            }

                            var maxD     = lidarLayer._maxRange * 100
                            var aMin     = lidarLayer._angleMin
                            var aStep    = lidarLayer._angleStep
                            ctx.beginPath()
                            ctx.fillStyle = "rgba(96,165,250,0.25)"
                            ctx.strokeStyle = "#60a5fa"; ctx.lineWidth = 1.5
                            var first = true
                            for (var i = 0; i < distances.length; i++) {
                                var d = distances[i]
                                if (d === 65535) d = maxD
                                var dist   = Math.min(d, maxD) / maxD
                                var aDeg   = aMin + i * aStep
                                var aRad   = (aDeg - 90) * Math.PI / 180
                                var px = cx + Math.cos(aRad) * R * dist
                                var py = cy + Math.sin(aRad) * R * dist
                                if (first) { ctx.moveTo(px, py); first = false } else ctx.lineTo(px, py)
                            }
                            ctx.closePath(); ctx.fill(); ctx.stroke()
                            // Drone dot
                            ctx.beginPath(); ctx.arc(cx, cy, 4, 0, Math.PI * 2)
                            ctx.fillStyle = "#22c55e"; ctx.fill()
                        }
                    }

                    // Compass N
                    Text { text: "N"; color: "#60a5fa"; font.pixelSize: 10; font.weight: Font.Bold
                        anchors { top: parent.top; horizontalCenter: parent.horizontalCenter; topMargin: 6 } }
                    // Footer stats
                    Text { text: lidarLayer._ranges.length + " Strahlen | max " + lidarLayer._maxRange.toFixed(0) + " m"
                        color: "#475569"; font.pixelSize: 9; font.family: "Consolas"
                        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: 4 } }
                }

                // ════════════════════════════════════════════════════════
                // LAYER 2 — Optical Flow vector (MAVLink OPTICAL_FLOW)
                // ════════════════════════════════════════════════════════
                Item {
                    anchors.fill: parent
                    visible: streamTypeCombo.currentIndex === 2
                    id: flowLayer

                    property real _flowX: 0; property real _flowY: 0
                    property real _quality: 0; property real _groundDist: 0

                    Timer {
                        interval: 200; running: flowLayer.visible; repeat: true
                        onTriggered: {
                            if (typeof telemetryModel === "undefined" || !telemetryModel || !root.selectedDroneId) return
                            var snap = telemetryModel.snapshotFor(root.selectedDroneId)
                            if (!snap) return
                            var of = snap["optical_flow"] || snap["OPTICAL_FLOW"]
                            if (!of) return
                            flowLayer._flowX      = of.flow_comp_m_x   || 0
                            flowLayer._flowY      = of.flow_comp_m_y   || 0
                            flowLayer._quality    = of.quality         || 0
                            flowLayer._groundDist = of.ground_distance || 0
                            flowGimbalCanvas.requestPaint()
                        }
                    }

                    Canvas {
                        id: flowGimbalCanvas
                        anchors { fill: parent; margins: 16 }
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            var cx = width / 2; var cy = height / 2

                            // Crosshair
                            ctx.strokeStyle = "#1e2535"; ctx.lineWidth = 1
                            ctx.beginPath(); ctx.moveTo(0, cy); ctx.lineTo(width, cy); ctx.stroke()
                            ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, height); ctx.stroke()

                            // Quality circle
                            var qual = Math.min(1, flowLayer._quality / 255.0)
                            ctx.strokeStyle = "rgba(167,139,250," + (0.15 + 0.25 * qual) + ")"
                            ctx.lineWidth = 1
                            ctx.beginPath(); ctx.arc(cx, cy, Math.min(cx, cy) - 4, 0, Math.PI * 2); ctx.stroke()

                            if (flowLayer._quality === 0) {
                                ctx.fillStyle = "#374151"; ctx.font = "11px Consolas"; ctx.textAlign = "center"
                                ctx.fillText("Keine Flow-Daten (quality=0)", cx, cy - 8)
                                ctx.fillText("(Optical-Flow-Plugin aktivieren)", cx, cy + 8)
                                return
                            }

                            var scale = Math.min(cx, cy) * 0.7
                            var dx = flowLayer._flowX * scale; var dy = flowLayer._flowY * scale
                            var ex = cx + dx; var ey = cy + dy

                            // Arrow shaft
                            ctx.strokeStyle = "rgba(167,139,250," + (0.5 + 0.5 * qual) + ")"
                            ctx.lineWidth = 2.5
                            ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(ex, ey); ctx.stroke()

                            // Arrowhead
                            var headLen = 10; var ang = Math.atan2(ey - cy, ex - cx)
                            ctx.beginPath()
                            ctx.moveTo(ex, ey)
                            ctx.lineTo(ex - headLen * Math.cos(ang - Math.PI / 6), ey - headLen * Math.sin(ang - Math.PI / 6))
                            ctx.lineTo(ex - headLen * Math.cos(ang + Math.PI / 6), ey - headLen * Math.sin(ang + Math.PI / 6))
                            ctx.closePath(); ctx.fillStyle = "#a78bfa"; ctx.fill()

                            // Centre dot
                            ctx.beginPath(); ctx.arc(cx, cy, 4, 0, Math.PI * 2)
                            ctx.fillStyle = "#22c55e"; ctx.fill()
                        }
                    }

                    // Stats overlay (bottom)
                    Column {
                        anchors { bottom: parent.bottom; left: parent.left; margins: 8 }
                        spacing: 2
                        Text { text: "vx=" + flowLayer._flowX.toFixed(3) + " m/s   vy=" + flowLayer._flowY.toFixed(3) + " m/s"
                            color: "#a78bfa"; font.pixelSize: 9; font.family: "Consolas" }
                        Text { text: "quality=" + flowLayer._quality + "   gnd=" + flowLayer._groundDist.toFixed(2) + " m"
                            color: "#475569"; font.pixelSize: 9; font.family: "Consolas" }
                    }
                    // Quality bar (right edge)
                    Rectangle {
                        anchors { top: parent.top; right: parent.right; bottom: parent.bottom; margins: 8 }
                        width: 6; radius: 3; color: "#1e2535"
                        Rectangle {
                            width: parent.width
                            height: parent.height * Math.min(1, flowLayer._quality / 255.0)
                            anchors.bottom: parent.bottom; radius: 3
                            color: flowLayer._quality > 150 ? "#22c55e"
                                 : flowLayer._quality > 80  ? "#f59e0b"
                                 : "#ef4444"
                        }
                    }
                }
            }

            // ── Action buttons (Kamera / LiDAR / Flow) ──────────────────
            // Index 0 (Kamera): Start / End GStreamer video stream
            // Index 1 (LiDAR):  OpenCV LiDAR polar-plot viewer (gz.transport13)
            // Index 2 (Flow):   OpenCV flow-camera viewer (gz.transport13)
            Row {
                width: parent.width
                spacing: 8

                // Kamera: Start Stream
                Rectangle {
                    width: (parent.width - 8) / 2; height: 34; radius: 5
                    visible: streamTypeCombo.currentIndex === 0
                    color: gimbalStartStreamM.containsMouse ? "#166534" : "#14532d"
                    border.color: "#22c55e"; border.width: 1
                    Text { anchors.centerIn: parent; text: "Start Stream"; color: "#86efac"; font.pixelSize: 10; font.weight: Font.Bold }
                    MouseArea {
                        id: gimbalStartStreamM; anchors.fill: parent; hoverEnabled: true
                        onClicked: {
                            if (typeof videoStream === "undefined" || !videoStream || !root.selectedDroneId) return
                            var s = videoStream.getVideoStatus(root.selectedDroneId)
                            var url = s && s.url ? s.url : "udp://0.0.0.0:" + (s && s.port ? s.port : 5600)
                            videoStream.startStream(url, root.selectedDroneId, "gimbal")
                        }
                    }
                }
                // Kamera: End Stream
                Rectangle {
                    width: (parent.width - 8) / 2; height: 34; radius: 5
                    visible: streamTypeCombo.currentIndex === 0
                    color: gimbalEndStreamM.containsMouse ? "#7f1d1d" : "#450a0a"
                    border.color: "#ef4444"; border.width: 1
                    Text { anchors.centerIn: parent; text: "End Stream"; color: "#fca5a5"; font.pixelSize: 10; font.weight: Font.Bold }
                    MouseArea {
                        id: gimbalEndStreamM; anchors.fill: parent; hoverEnabled: true
                        onClicked: { if (typeof videoStream !== "undefined" && videoStream && root.selectedDroneId) videoStream.stopStream(root.selectedDroneId) }
                    }
                }

                // LiDAR: OpenCV polar-plot viewer
                Rectangle {
                    width: parent.width; height: 34; radius: 5
                    visible: streamTypeCombo.currentIndex === 1
                    property bool _ok: typeof sitl !== "undefined" && sitl !== null
                    color: !_ok ? "#0d1117" : (lidarViewGimbalM.containsMouse ? "#1e3a5f" : "#0d1623")
                    border.color: _ok ? "#2563eb" : "#1f2937"; border.width: 1
                    Text { anchors.centerIn: parent; text: "◉ LiDAR Viewer öffnen (OpenCV)"; color: parent._ok ? "#93c5fd" : "#374151"; font.pixelSize: 10; font.weight: Font.Bold }
                    MouseArea { id: lidarViewGimbalM; anchors.fill: parent; hoverEnabled: true; enabled: parent._ok
                        onClicked: sitl.launchLidarViewer("/lidar/scan") }
                }

                // Flow: OpenCV camera viewer
                Rectangle {
                    width: parent.width; height: 34; radius: 5
                    visible: streamTypeCombo.currentIndex === 2
                    property bool _ok: typeof sitl !== "undefined" && sitl !== null
                    color: !_ok ? "#0d1117" : (flowViewGimbalM.containsMouse ? "#3b0764" : "#1a0a28")
                    border.color: _ok ? "#7c3aed" : "#1f2937"; border.width: 1
                    Text { anchors.centerIn: parent; text: "◉ Flow Viewer öffnen (OpenCV)"; color: parent._ok ? "#c4b5fd" : "#374151"; font.pixelSize: 10; font.weight: Font.Bold }
                    MouseArea { id: flowViewGimbalM; anchors.fill: parent; hoverEnabled: true; enabled: parent._ok
                        onClicked: sitl.launchFlowViewer("/flow_camera/image") }
                }
            }

            Rectangle {
                width: parent.width; height: gimbalCol.implicitHeight + 20; radius: 8
                color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                enabled: isObservation(root.selectedDroneId)
                opacity: enabled ? 1.0 : 0.4

                Column {
                    id: gimbalCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 10

                    // PITCH
                    Column {
                        width: parent.width; spacing: 3
                        Row {
                            width: parent.width
                            Text { text: "PITCH"; color: "#94a3b8"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; anchors.verticalCenter: parent.verticalCenter }
                            Item { width: parent.width - 80; height: 1 }
                            Text { text: pitchSlider.value.toFixed(0) + "°"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter }
                        }
                        Slider {
                            id: pitchSlider
                            width: parent.width; from: -90; to: 0; value: 0
                            background: Rectangle {
                                x: pitchSlider.leftPadding; y: pitchSlider.topPadding + pitchSlider.availableHeight / 2 - height / 2
                                width: pitchSlider.availableWidth; height: 4; radius: 2; color: "#1e293b"
                                Rectangle { width: pitchSlider.visualPosition * parent.width; height: parent.height; radius: 2; color: "#2563eb" }
                            }
                            handle: Rectangle {
                                x: pitchSlider.leftPadding + pitchSlider.visualPosition * (pitchSlider.availableWidth - width)
                                y: pitchSlider.topPadding + pitchSlider.availableHeight / 2 - height / 2
                                width: 16; height: 16; radius: 8; color: "#2563eb"; border.color: "#93c5fd"; border.width: 2
                            }
                        }
                        Row {
                            width: parent.width
                            Text { text: "-90°"; color: "#334155"; font.pixelSize: 8 }
                            Item { width: parent.width - 30; height: 1 }
                            Text { text: "0°"; color: "#334155"; font.pixelSize: 8 }
                        }
                    }

                    // ROLL
                    Column {
                        width: parent.width; spacing: 3
                        Row {
                            width: parent.width
                            Text { text: "ROLL"; color: "#94a3b8"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; anchors.verticalCenter: parent.verticalCenter }
                            Item { width: parent.width - 80; height: 1 }
                            Text { text: rollSlider.value.toFixed(0) + "°"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter }
                        }
                        Slider {
                            id: rollSlider
                            width: parent.width; from: -45; to: 45; value: 0
                            background: Rectangle {
                                x: rollSlider.leftPadding; y: rollSlider.topPadding + rollSlider.availableHeight / 2 - height / 2
                                width: rollSlider.availableWidth; height: 4; radius: 2; color: "#1e293b"
                                Rectangle { x: Math.min(rollSlider.visualPosition, 0.5) * parent.width; width: Math.abs(rollSlider.visualPosition - 0.5) * parent.width; height: parent.height; radius: 2; color: "#8b5cf6" }
                            }
                            handle: Rectangle {
                                x: rollSlider.leftPadding + rollSlider.visualPosition * (rollSlider.availableWidth - width)
                                y: rollSlider.topPadding + rollSlider.availableHeight / 2 - height / 2
                                width: 16; height: 16; radius: 8; color: "#8b5cf6"; border.color: "#c4b5fd"; border.width: 2
                            }
                        }
                    }

                    // YAW
                    Column {
                        width: parent.width; spacing: 3
                        Row {
                            width: parent.width
                            Text { text: "YAW"; color: "#94a3b8"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; anchors.verticalCenter: parent.verticalCenter }
                            Item { width: parent.width - 80; height: 1 }
                            Text { text: yawSlider.value.toFixed(0) + "°"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter }
                        }
                        Slider {
                            id: yawSlider
                            width: parent.width; from: -180; to: 180; value: 0
                            background: Rectangle {
                                x: yawSlider.leftPadding; y: yawSlider.topPadding + yawSlider.availableHeight / 2 - height / 2
                                width: yawSlider.availableWidth; height: 4; radius: 2; color: "#1e293b"
                                Rectangle { width: yawSlider.visualPosition * parent.width; height: parent.height; radius: 2; color: "#06b6d4" }
                            }
                            handle: Rectangle {
                                x: yawSlider.leftPadding + yawSlider.visualPosition * (yawSlider.availableWidth - width)
                                y: yawSlider.topPadding + yawSlider.availableHeight / 2 - height / 2
                                width: 16; height: 16; radius: 8; color: "#06b6d4"; border.color: "#67e8f9"; border.width: 2
                            }
                        }
                    }

                    // Action buttons
                    Row {
                        width: parent.width; spacing: 8

                        Rectangle {
                            width: (parent.width - 8) * 0.6; height: 32; radius: 6
                            color: applyM.containsMouse ? "#1d4ed8" : "#1e3a5f"
                            border.color: "#2563eb"; border.width: 1
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Text { anchors.centerIn: parent; text: qsTr("APPLY GIMBAL"); color: "#93c5fd"; font.pixelSize: 10; font.weight: Font.Bold; font.letterSpacing: 1 }
                            MouseArea {
                                id: applyM; anchors.fill: parent; hoverEnabled: true
                                onClicked: {
                                    if (!root.selectedDroneId || typeof swarm === "undefined") return
                                    swarm.gimbalPoint(root.selectedDroneId,
                                        pitchSlider.value, rollSlider.value, yawSlider.value)
                                }
                            }
                        }

                        Rectangle {
                            width: (parent.width - 8) * 0.4; height: 32; radius: 6
                            color: homeM.containsMouse ? "#374151" : "#1e2535"
                            border.color: "#4b5563"; border.width: 1
                            Text { anchors.centerIn: parent; text: qsTr("⌂ HOME"); color: "#94a3b8"; font.pixelSize: 10 }
                            MouseArea {
                                id: homeM; anchors.fill: parent; hoverEnabled: true
                                onClicked: {
                                    if (!root.selectedDroneId || typeof swarm === "undefined") return
                                    pitchSlider.value = 0; rollSlider.value = 0; yawSlider.value = 0
                                    swarm.gimbalHome(root.selectedDroneId)
                                }
                            }
                        }
                    }

                    // Quick presets
                    Text { text: qsTr("PRESETS"); color: "#64748b"; font.pixelSize: 8; font.weight: Font.Bold; font.letterSpacing: 1 }
                    Row {
                        width: parent.width; spacing: 6

                        Repeater {
                            model: [
                                { label: qsTr("Down"),    pitch: -90, roll: 0, yaw: 0 },
                                { label: qsTr("Forward"), pitch: 0,   roll: 0, yaw: 0 },
                                { label: qsTr("45°"),     pitch: -45, roll: 0, yaw: 0 },
                            ]
                            delegate: Rectangle {
                                width: (parent.width - 12) / 3; height: 28; radius: 5
                                color: pM.containsMouse ? "#334155" : "#1e2535"
                                border.color: "#334155"; border.width: 1
                                Text { anchors.centerIn: parent; text: modelData.label; color: "#94a3b8"; font.pixelSize: 10 }
                                MouseArea {
                                    id: pM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: {
                                        pitchSlider.value = modelData.pitch
                                        rollSlider.value  = modelData.roll
                                        yawSlider.value   = modelData.yaw
                                        if (root.selectedDroneId && typeof swarm !== "undefined")
                                            swarm.gimbalPoint(root.selectedDroneId, modelData.pitch, modelData.roll, modelData.yaw)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── Current gimbal state ────────────────────────────────────
            Text { text: qsTr("CURRENT STATUS"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }

            Rectangle {
                width: parent.width; height: 44; radius: 8
                color: "#0d1117"; border.color: "#2d3748"; border.width: 1

                Timer {
                    interval: 500; running: true; repeat: true
                    onTriggered: {
                        if (!root.selectedDroneId || typeof swarm === "undefined") return
                        var s = swarm.gimbalState(root.selectedDroneId)
                        if (s) {
                            pitchLabel.text = "P: " + (s.pitch || 0).toFixed(0) + "°"
                            rollLabel.text  = "R: " + (s.roll  || 0).toFixed(0) + "°"
                            yawLabel.text   = "Y: " + (s.yaw   || 0).toFixed(0) + "°"
                        }
                    }
                }

                Row {
                    anchors.centerIn: parent; spacing: 24
                    Text { id: pitchLabel; text: "P: —"; color: "#2563eb"; font.pixelSize: 13; font.family: "Consolas"; font.weight: Font.Bold }
                    Text { id: rollLabel;  text: "R: —"; color: "#8b5cf6"; font.pixelSize: 13; font.family: "Consolas"; font.weight: Font.Bold }
                    Text { id: yawLabel;   text: "Y: —"; color: "#06b6d4"; font.pixelSize: 13; font.family: "Consolas"; font.weight: Font.Bold }
                }
            }

            // ── Camera Controls ─────────────────────────────────────────
            // Only visible in Kamera mode (index 0) — hidden for LiDAR / Flow
            Text { text: qsTr("KAMERA STEUERUNG"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; topPadding: 10
                visible: streamTypeCombo.currentIndex === 0
            }

            Rectangle {
                width: parent.width; height: cameraCol.implicitHeight + 20; radius: 8
                color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                enabled: isObservation(root.selectedDroneId)
                opacity: enabled ? 1.0 : 0.4
                visible: streamTypeCombo.currentIndex === 0

                Column {
                    id: cameraCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 10

                    // Camera Source Selection
                    Column {
                        width: parent.width; spacing: 3
                        Text { text: qsTr("CAMERA SOURCE"); color: "#94a3b8"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                        ComboBox {
                            id: cameraSourceCombo
                            width: parent.width; height: 32
                            model: ["Test Source", "RGB Camera", "Thermal Camera", "External USB"]
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            contentItem: Text {
                                text: cameraSourceCombo.displayText
                                color: "#e2e8f0"
                                font.pixelSize: 11
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                        }
                    }

                    // Stream Controls
                    Row {
                        width: parent.width; spacing: 8

                        Rectangle {
                            width: (parent.width - 8) / 2; height: 32; radius: 6
                            color: streamStartM.containsMouse ? "#059669" : "#064e3b"
                            border.color: "#10b981"; border.width: 1
                            visible: typeof camera !== "undefined" ? !camera.streamActive : true
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Text {
                                anchors.centerIn: parent
                                text: qsTr("▶ START STREAM")
                                color: "#6ee7b7"
                                font.pixelSize: 10
                                font.weight: Font.Bold
                                font.letterSpacing: 1
                            }
                            MouseArea {
                                id: streamStartM
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    if (typeof camera !== "undefined")
                                        camera.cameraStartStream(cameraSourceCombo.currentText)
                                }
                            }
                        }

                        Rectangle {
                            width: (parent.width - 8) / 2; height: 32; radius: 6
                            color: streamStopM.containsMouse ? "#b91c1c" : "#7f1d1d"
                            border.color: "#ef4444"; border.width: 1
                            visible: typeof camera !== "undefined" ? camera.streamActive : false
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Text {
                                anchors.centerIn: parent
                                text: qsTr("■ STOP STREAM")
                                color: "#fca5a5"
                                font.pixelSize: 10
                                font.weight: Font.Bold
                                font.letterSpacing: 1
                            }
                            MouseArea {
                                id: streamStopM
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    if (typeof camera !== "undefined")
                                        camera.cameraStopStream()
                                }
                            }
                        }
                    }

                    // Stream Status Indicator
                    Rectangle {
                        width: parent.width; height: 28; radius: 5
                        color: "#0d1117"; border.color: "#2d3748"; border.width: 1
                        Row {
                            anchors { fill: parent; leftMargin: 10 }
                            spacing: 8
                            Rectangle {
                                width: 8; height: 8; radius: 4
                                color: (typeof camera !== "undefined" && camera.streamActive) ? "#10b981" : "#64748b"
                                anchors.verticalCenter: parent.verticalCenter
                                SequentialAnimation on opacity {
                                    running: typeof camera !== "undefined" && camera.streamActive
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1.0; to: 0.3; duration: 800 }
                                    NumberAnimation { from: 0.3; to: 1.0; duration: 800 }
                                }
                            }
                            Text {
                                text: (typeof camera !== "undefined" && camera.streamActive) ? qsTr("Stream Active") : qsTr("Stream Inactive")
                                color: "#94a3b8"
                                font.pixelSize: 10
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }

                    // Snapshot & Recording Controls
                    Row {
                        width: parent.width; spacing: 8

                        Rectangle {
                            width: (parent.width - 16) / 3; height: 32; radius: 6
                            color: snapshotM.containsMouse ? "#1d4ed8" : "#1e3a5f"
                            border.color: "#2563eb"; border.width: 1
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Text {
                                anchors.centerIn: parent
                                text: qsTr("📷 SNAPSHOT")
                                color: "#93c5fd"
                                font.pixelSize: 9
                                font.weight: Font.Bold
                            }
                            MouseArea {
                                id: snapshotM
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    if (typeof camera !== "undefined")
                                        camera.cameraSnapshot()
                                }
                            }
                        }

                        Rectangle {
                            width: (parent.width - 16) / 3; height: 32; radius: 6
                            color: recordStartM.containsMouse ? "#b91c1c" : "#7f1d1d"
                            border.color: "#ef4444"; border.width: 1
                            visible: typeof camera !== "undefined" ? !camera.recordingActive : true
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Text {
                                anchors.centerIn: parent
                                text: qsTr("⏺ RECORD")
                                color: "#fca5a5"
                                font.pixelSize: 9
                                font.weight: Font.Bold
                            }
                            MouseArea {
                                id: recordStartM
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    if (typeof camera !== "undefined") {
                                        var timestamp = new Date().toISOString().replace(/[:.]/g, "-")
                                        var path = "recordings/video_" + timestamp + ".mp4"
                                        camera.cameraStartRecording(path)
                                    }
                                }
                            }
                        }

                        Rectangle {
                            width: (parent.width - 16) / 3; height: 32; radius: 6
                            color: recordStopM.containsMouse ? "#374151" : "#1e2535"
                            border.color: "#4b5563"; border.width: 1
                            visible: typeof camera !== "undefined" ? camera.recordingActive : false
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Row {
                                anchors.centerIn: parent
                                spacing: 4
                                Rectangle {
                                    width: 8; height: 8; radius: 4
                                    color: "#ef4444"
                                    anchors.verticalCenter: parent.verticalCenter
                                    SequentialAnimation on opacity {
                                        running: true
                                        loops: Animation.Infinite
                                        NumberAnimation { from: 1.0; to: 0.2; duration: 600 }
                                        NumberAnimation { from: 0.2; to: 1.0; duration: 600 }
                                    }
                                }
                                Text {
                                    text: qsTr("■ STOP")
                                    color: "#94a3b8"
                                    font.pixelSize: 9
                                    font.weight: Font.Bold
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                            MouseArea {
                                id: recordStopM
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    if (typeof camera !== "undefined")
                                        camera.cameraStopRecording()
                                }
                            }
                        }
                    }

                    // Recording Duration Display
                    Rectangle {
                        width: parent.width; height: 28; radius: 5
                        color: "#0d1117"; border.color: "#2d3748"; border.width: 1
                        visible: typeof camera !== "undefined" ? camera.recordingActive : false
                        Row {
                            anchors.centerIn: parent
                            spacing: 6
                            Text {
                                text: qsTr("Recording:")
                                color: "#64748b"
                                font.pixelSize: 10
                            }
                            Text {
                                text: {
                                    if (typeof camera === "undefined") return "00:00"
                                    var sec = camera.recordingDuration
                                    var min = Math.floor(sec / 60)
                                    var s = sec % 60
                                    return (min < 10 ? "0" : "") + min + ":" + (s < 10 ? "0" : "") + s
                                }
                                color: "#ef4444"
                                font.pixelSize: 12
                                font.family: "Consolas"
                                font.weight: Font.Bold
                            }
                        }
                    }
                }
            }

            // ── Camera Settings ─────────────────────────────────────────
            Text { text: qsTr("KAMERA EINSTELLUNGEN"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; topPadding: 10
                visible: streamTypeCombo.currentIndex === 0
            }

            Rectangle {
                width: parent.width; height: settingsCol.implicitHeight + 20; radius: 8
                color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                enabled: isObservation(root.selectedDroneId)
                opacity: enabled ? 1.0 : 0.4
                visible: streamTypeCombo.currentIndex === 0

                Column {
                    id: settingsCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 10

                    // Resolution
                    Column {
                        width: parent.width; spacing: 3
                        Text { text: qsTr("RESOLUTION"); color: "#94a3b8"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                        ComboBox {
                            id: resolutionCombo
                            width: parent.width; height: 32
                            model: ["1920x1080", "1280x720", "640x480", "3840x2160"]
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            contentItem: Text {
                                text: resolutionCombo.displayText
                                color: "#e2e8f0"
                                font.pixelSize: 11
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                        }
                    }

                    // FPS
                    Column {
                        width: parent.width; spacing: 3
                        Row {
                            width: parent.width
                            Text { text: qsTr("FPS"); color: "#94a3b8"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; anchors.verticalCenter: parent.verticalCenter }
                            Item { width: parent.width - 80; height: 1 }
                            Text { text: fpsSlider.value.toFixed(0); color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter }
                        }
                        Slider {
                            id: fpsSlider
                            width: parent.width; from: 15; to: 60; value: 30; stepSize: 15
                            background: Rectangle {
                                x: fpsSlider.leftPadding; y: fpsSlider.topPadding + fpsSlider.availableHeight / 2 - height / 2
                                width: fpsSlider.availableWidth; height: 4; radius: 2; color: "#1e293b"
                                Rectangle { width: fpsSlider.visualPosition * parent.width; height: parent.height; radius: 2; color: "#8b5cf6" }
                            }
                            handle: Rectangle {
                                x: fpsSlider.leftPadding + fpsSlider.visualPosition * (fpsSlider.availableWidth - width)
                                y: fpsSlider.topPadding + fpsSlider.availableHeight / 2 - height / 2
                                width: 16; height: 16; radius: 8; color: "#8b5cf6"; border.color: "#c4b5fd"; border.width: 2
                            }
                        }
                    }

                    // Camera Profile
                    Column {
                        width: parent.width; spacing: 3
                        Text { text: qsTr("PROFILE"); color: "#94a3b8"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                        ComboBox {
                            id: profileCombo
                            width: parent.width; height: 32
                            model: ["RGB Camera", "High Resolution", "Low Light", "Fast Motion"]
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            contentItem: Text {
                                text: profileCombo.displayText
                                color: "#e2e8f0"
                                font.pixelSize: 11
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                            // Profile changes are applied via "APPLY SETTINGS" button
                            // Don't auto-apply on combo change to avoid errors during initialization
                        }
                    }

                    // Apply Settings Button
                    Rectangle {
                        width: parent.width; height: 32; radius: 6
                        color: applySettingsM.containsMouse ? "#1d4ed8" : "#1e3a5f"
                        border.color: "#2563eb"; border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                        Text {
                            anchors.centerIn: parent
                            text: qsTr("APPLY SETTINGS")
                            color: "#93c5fd"
                            font.pixelSize: 10
                            font.weight: Font.Bold
                            font.letterSpacing: 1
                        }
                        MouseArea {
                            id: applySettingsM
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                if (typeof camera !== "undefined") {
                                    var profile = {
                                        "name": profileCombo.currentText,
                                        "resolution": resolutionCombo.currentText,
                                        "fps": fpsSlider.value,
                                        "hfov": 90.0,
                                        "vfov": 60.0,
                                        "format": "H264"
                                    }
                                    camera.setCameraProfile(profile)
                                }
                            }
                        }
                    }
                }
            }

            // ── Thermal Settings ────────────────────────────────────────
            Text { text: qsTr("WÄRME EINSTELLUNGEN"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; topPadding: 10
                visible: streamTypeCombo.currentIndex === 0
            }

            Rectangle {
                width: parent.width; height: thermalCol.implicitHeight + 20; radius: 8
                color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                enabled: isObservation(root.selectedDroneId)
                opacity: enabled ? 1.0 : 0.4
                visible: streamTypeCombo.currentIndex === 0

                Column {
                    id: thermalCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 10

                    // Temperature Range
                    Column {
                        width: parent.width; spacing: 3
                        Text { text: qsTr("TEMPERATURE RANGE"); color: "#94a3b8"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }

                        Row {
                            width: parent.width; spacing: 8
                            Column {
                                width: (parent.width - 8) / 2; spacing: 3
                                Text { text: qsTr("Min °C"); color: "#64748b"; font.pixelSize: 8 }
                                Row {
                                    width: parent.width; spacing: 4
                                    Slider {
                                        id: tempMinSlider
                                        width: parent.width - 40; from: -20; to: 100; value: 0
                                        background: Rectangle {
                                            x: tempMinSlider.leftPadding; y: tempMinSlider.topPadding + tempMinSlider.availableHeight / 2 - height / 2
                                            width: tempMinSlider.availableWidth; height: 4; radius: 2; color: "#1e293b"
                                            Rectangle { width: tempMinSlider.visualPosition * parent.width; height: parent.height; radius: 2; color: "#06b6d4" }
                                        }
                                        handle: Rectangle {
                                            x: tempMinSlider.leftPadding + tempMinSlider.visualPosition * (tempMinSlider.availableWidth - width)
                                            y: tempMinSlider.topPadding + tempMinSlider.availableHeight / 2 - height / 2
                                            width: 14; height: 14; radius: 7; color: "#06b6d4"; border.color: "#67e8f9"; border.width: 2
                                        }
                                    }
                                    Text { text: tempMinSlider.value.toFixed(0); color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; width: 30 }
                                }
                            }
                            Column {
                                width: (parent.width - 8) / 2; spacing: 3
                                Text { text: qsTr("Max °C"); color: "#64748b"; font.pixelSize: 8 }
                                Row {
                                    width: parent.width; spacing: 4
                                    Slider {
                                        id: tempMaxSlider
                                        width: parent.width - 40; from: 0; to: 150; value: 100
                                        background: Rectangle {
                                            x: tempMaxSlider.leftPadding; y: tempMaxSlider.topPadding + tempMaxSlider.availableHeight / 2 - height / 2
                                            width: tempMaxSlider.availableWidth; height: 4; radius: 2; color: "#1e293b"
                                            Rectangle { width: tempMaxSlider.visualPosition * parent.width; height: parent.height; radius: 2; color: "#ef4444" }
                                        }
                                        handle: Rectangle {
                                            x: tempMaxSlider.leftPadding + tempMaxSlider.visualPosition * (tempMaxSlider.availableWidth - width)
                                            y: tempMaxSlider.topPadding + tempMaxSlider.availableHeight / 2 - height / 2
                                            width: 14; height: 14; radius: 7; color: "#ef4444"; border.color: "#fca5a5"; border.width: 2
                                        }
                                    }
                                    Text { text: tempMaxSlider.value.toFixed(0); color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; width: 30 }
                                }
                            }
                        }
                    }

                    // Color Palette
                    Column {
                        width: parent.width; spacing: 3
                        Text { text: qsTr("COLOR PALETTE"); color: "#94a3b8"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                        ComboBox {
                            id: paletteCombo
                            width: parent.width; height: 32
                            model: ["Iron", "Rainbow", "Grayscale", "Hot", "Cool", "Jet"]
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            contentItem: Text {
                                text: paletteCombo.displayText
                                color: "#e2e8f0"
                                font.pixelSize: 11
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                            // Palette changes are applied via "APPLY THERMAL SETTINGS" button
                            // Don't auto-apply on combo change to avoid errors during initialization
                        }
                    }

                    // Hotspot Detection
                    Row {
                        width: parent.width; spacing: 8
                        Text {
                            text: qsTr("HOTSPOT DETECTION")
                            color: "#94a3b8"
                            font.pixelSize: 9
                            font.weight: Font.Bold
                            font.letterSpacing: 1
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Item { width: parent.width - 200; height: 1 }
                        Rectangle {
                            width: 50; height: 26; radius: 13
                            color: hotspotToggle.checked ? "#059669" : "#374151"
                            border.color: hotspotToggle.checked ? "#10b981" : "#4b5563"
                            border.width: 1
                            Behavior on color { ColorAnimation { duration: 150 } }
                            anchors.verticalCenter: parent.verticalCenter

                            Rectangle {
                                width: 20; height: 20; radius: 10
                                x: hotspotToggle.checked ? parent.width - width - 3 : 3
                                y: 3
                                color: "#e2e8f0"
                                Behavior on x { NumberAnimation { duration: 150 } }
                            }

                            MouseArea {
                                id: hotspotToggle
                                anchors.fill: parent
                                property bool checked: false
                                onClicked: {
                                    checked = !checked
                                    if (typeof camera !== "undefined")
                                        camera.setHotspotDetection(checked)
                                }
                            }
                        }
                    }

                    // Apply Thermal Settings Button
                    Rectangle {
                        width: parent.width; height: 32; radius: 6
                        color: applyThermalM.containsMouse ? "#b91c1c" : "#7f1d1d"
                        border.color: "#ef4444"; border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                        Text {
                            anchors.centerIn: parent
                            text: qsTr("APPLY THERMAL SETTINGS")
                            color: "#fca5a5"
                            font.pixelSize: 10
                            font.weight: Font.Bold
                            font.letterSpacing: 1
                        }
                        MouseArea {
                            id: applyThermalM
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                if (typeof camera !== "undefined") {
                                    camera.setTempRange(tempMinSlider.value, tempMaxSlider.value)
                                    camera.setColorPalette(paletteCombo.currentText)
                                    camera.setHotspotDetection(hotspotToggle.checked)
                                }
                            }
                        }
                    }
                }
            }

            // ── Camera Status ───────────────────────────────────────────
            Text { text: qsTr("KAMERA STATUS"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; topPadding: 10
                visible: streamTypeCombo.currentIndex === 0
            }

            Rectangle {
                width: parent.width; height: statusCol.implicitHeight + 20; radius: 8
                color: "#0d1117"; border.color: "#2d3748"; border.width: 1
                visible: streamTypeCombo.currentIndex === 0

                Column {
                    id: statusCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 8

                    Timer {
                        interval: 500; running: true; repeat: true
                        onTriggered: {
                            if (typeof camera === "undefined") return
                            var status = camera.getCameraStatus()
                            if (status) {
                                sourceText.text = status.source || "—"
                                profileText.text = status.profile || "—"
                                resText.text = status.resolution || "—"
                                fpsText.text = status.fps ? status.fps + " fps" : "—"
                                frameAgeText.text = status.frameAgeMs ? status.frameAgeMs + " ms" : "—"
                                droppedText.text = status.droppedFrames !== undefined ? status.droppedFrames.toString() : "—"
                                gimbalErrorText.text = status.lastError || qsTr("No errors")
                                gimbalErrorText.color = status.lastError ? "#ef4444" : "#10b981"
                            }
                        }
                    }

                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Quelle:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: sourceText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Profil:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: profileText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Auflösung:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: resText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("FPS:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: fpsText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Frame-Alter:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: frameAgeText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Verlorene Frames:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: droppedText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Status:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: gimbalErrorText; text: qsTr("Kein Fehler"); color: "#10b981"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                }
            }

        // ══════════════════════════════════════════════════════════════════
        // SENSOR BRIDGE — Gazebo → ArduPilot MAVLink
        // Optical Flow + LiDAR direkt an den Autopiloten senden
        // ══════════════════════════════════════════════════════════════════

        Rectangle { width: parent.width; height: 1; color: "#2d3748" }

        Text {
            text: qsTr("SENSOR BRIDGE — GAZEBO → ARDUPILOT")
            color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold
            font.letterSpacing: 1
        }

        // Info-Box
        Rectangle {
            width: parent.width
            height: bridgeInfoCol.implicitHeight + 16
            radius: 6; color: "#07101a"
            border.color: "#1e3a5f"; border.width: 1

            Column {
                id: bridgeInfoCol
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                spacing: 4

                Text {
                    width: parent.width; wrapMode: Text.WordWrap
                    text: "Sendet berechneten Optical Flow (OPTICAL_FLOW_RAD), "
                        + "Bodenabstand (DISTANCE_SENSOR) und LiDAR-Hindernisdaten "
                        + "(OBSTACLE_DISTANCE) direkt an ArduPilot per MAVLink.\n"
                        + "Funktioniert für SITL und echte Hardware."
                    color: "#64748b"; font.pixelSize: 10; lineHeight: 1.5
                }
                Text {
                    width: parent.width
                    text: "ⓘ  Vor dem Start: Parameter setzen → Reboot → Bridge starten"
                    color: "#38bdf8"; font.pixelSize: 10
                }
            }
        }

        // ── Verbindungs-Konfiguration ──────────────────────────────────
        Text { text: qsTr("VERBINDUNG"); color: "#475569"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 0.8 }

        Rectangle {
            width: parent.width; height: bridgeCfgGrid.implicitHeight + 20
            radius: 6; color: "#0d1117"; border.color: "#2d3748"; border.width: 1

            Grid {
                id: bridgeCfgGrid
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                columns: 2; columnSpacing: 10; rowSpacing: 8

                Text { text: "MAVLink"; color: "#64748b"; font.pixelSize: 11 }
                Text { text: "Kamera-Topic"; color: "#64748b"; font.pixelSize: 11 }

                Rectangle {
                    width: (bridgeCfgGrid.width - 10) / 2; height: 30; radius: 5
                    color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                    TextInput {
                        id: bridgeMavlinkField
                        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                        text: "udpin:0.0.0.0:14550"
                        verticalAlignment: TextInput.AlignVCenter
                        color: "#38bdf8"; font.pixelSize: 11; font.family: "Consolas"
                    }
                }
                Rectangle {
                    width: (bridgeCfgGrid.width - 10) / 2; height: 30; radius: 5
                    color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                    TextInput {
                        id: bridgeCameraField
                        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                        text: "/flow_camera/image"
                        verticalAlignment: TextInput.AlignVCenter
                        color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"
                    }
                }

                Text { text: "LiDAR-Topic"; color: "#64748b"; font.pixelSize: 11 }
                Item {}   // Spacer

                Rectangle {
                    width: (bridgeCfgGrid.width - 10) / 2; height: 30; radius: 5
                    color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                    TextInput {
                        id: bridgeLidarField
                        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                        text: "/lidar/scan"
                        verticalAlignment: TextInput.AlignVCenter
                        color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"
                    }
                }
                Item {}   // Spacer
            }
        }

        // ── Parameter-Liste ────────────────────────────────────────────
        Text { text: qsTr("ARDUPILOT PARAMETER"); color: "#475569"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 0.8 }

        Rectangle {
            width: parent.width; height: bridgeParamCol.implicitHeight + 16
            radius: 6; color: "#0d1117"; border.color: "#2d3748"; border.width: 1

            Column {
                id: bridgeParamCol
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                spacing: 3

                Repeater {
                    model: (typeof sitl !== "undefined" && sitl) ? sitl.getBridgeParamList() : []
                    delegate: Row {
                        spacing: 8; width: parent.width
                        Text {
                            text: modelData.name
                            color: "#60a5fa"; font.pixelSize: 10; font.family: "Consolas"
                            width: 140
                        }
                        Text {
                            text: "= " + modelData.value
                            color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"
                        }
                    }
                }

                Rectangle { width: parent.width; height: 1; color: "#1e2535" }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap
                    text: "ⓘ  EK3_SRC1_VELXY=5 + EK3_SRC1_POSXY=0 nur setzen wenn\n"
                        + "    Flow-Richtung geprüft und GPS deaktiviert werden soll."
                    color: "#475569"; font.pixelSize: 9; font.family: "Consolas"
                }
            }
        }

        // ── Master-Feld für Parameter-Apply ───────────────────────────
        Text { text: qsTr("PARAMETER SENDEN"); color: "#475569"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 0.8 }

        Rectangle {
            width: parent.width; height: 32; radius: 5
            color: "#1e2535"; border.color: "#2d3748"; border.width: 1
            Row {
                anchors { fill: parent; leftMargin: 8 }
                spacing: 6
                Text { text: "Master:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                TextInput {
                    id: bridgeParamMasterField
                    width: parent.width - 80
                    text: "tcp:127.0.0.1:5760"
                    verticalAlignment: TextInput.AlignVCenter
                    anchors.verticalCenter: parent.verticalCenter
                    color: "#38bdf8"; font.pixelSize: 11; font.family: "Consolas"
                }
            }
        }

        // ── Status-Anzeige ─────────────────────────────────────────────
        // Aktualisiert per Timer — getrennt von den Buttons um Flackern zu vermeiden.
        property string _bridgeStatus: "stopped"
        Timer {
            interval: 1500; running: true; repeat: true
            onTriggered: {
                if (typeof sitl !== "undefined" && sitl)
                    parent._bridgeStatus = sitl.getBridgeStatus()
            }
        }

        Rectangle {
            width: parent.width; height: 30; radius: 5
            color: parent._bridgeStatus === "running" ? "#052e16"
                 : parent._bridgeStatus === "error"   ? "#1c0505"
                 : "#0a0f1a"
            border.color: parent._bridgeStatus === "running" ? "#22c55e"
                        : parent._bridgeStatus === "error"   ? "#ef4444"
                        : "#2d3748"
            border.width: 1

            Row {
                anchors.centerIn: parent; spacing: 8
                Rectangle {
                    width: 8; height: 8; radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    color: parent.parent.parent._bridgeStatus === "running" ? "#22c55e"
                         : parent.parent.parent._bridgeStatus === "error"   ? "#ef4444"
                         : "#475569"
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: {
                        var s = parent.parent.parent._bridgeStatus
                        if (s === "running") return "Bridge aktiv — sendet OPTICAL_FLOW_RAD + OBSTACLE_DISTANCE"
                        if (s === "error")   return "Bridge fehlgeschlagen — Log prüfen"
                        return "Bridge gestoppt"
                    }
                    color: parent.parent.parent._bridgeStatus === "running" ? "#86efac"
                         : parent.parent.parent._bridgeStatus === "error"   ? "#fca5a5"
                         : "#475569"
                    font.pixelSize: 10
                }
            }
        }

        // ── Aktion-Buttons ─────────────────────────────────────────────
        Row {
            spacing: 8; width: parent.width

            // Parameter setzen + reboot
            Rectangle {
                width: 150; height: 36; radius: 7
                property bool _ok: typeof sitl !== "undefined" && sitl
                color: bridgeParamM.containsMouse ? "#1e3a5f" : "#0a1020"
                border.color: _ok ? "#2563eb" : "#1f2937"; border.width: 1
                Column {
                    anchors.centerIn: parent; spacing: 1
                    Text { text: "⚙ Parameter setzen"; color: parent.parent._ok ? "#93c5fd" : "#374151"
                           font.pixelSize: 10; font.weight: Font.Bold; anchors.horizontalCenter: parent.horizontalCenter }
                    Text { text: "→ reboot"; color: "#475569"; font.pixelSize: 9; anchors.horizontalCenter: parent.horizontalCenter }
                }
                MouseArea {
                    id: bridgeParamM; anchors.fill: parent; hoverEnabled: true; enabled: parent._ok
                    onClicked: sitl.applyBridgeParams(bridgeParamMasterField.text.trim() || "tcp:127.0.0.1:5760")
                }
            }

            // Bridge starten
            Rectangle {
                width: 120; height: 36; radius: 7
                property bool _ok: typeof sitl !== "undefined" && sitl
                property bool _running: parent.parent._bridgeStatus === "running"
                color: _running ? "#052e16" : (bridgeStartM.containsMouse ? "#15803d" : "#0a1a0a")
                border.color: _ok ? "#22c55e" : "#1f2937"; border.width: 1
                Text {
                    anchors.centerIn: parent
                    text: parent._running ? "◉ Bridge aktiv" : "▶ Bridge starten"
                    color: parent._ok ? "#86efac" : "#374151"
                    font.pixelSize: 10; font.weight: Font.Bold
                }
                MouseArea {
                    id: bridgeStartM; anchors.fill: parent; hoverEnabled: true
                    enabled: parent._ok && !parent._running
                    onClicked: {
                        var cfg = JSON.stringify({
                            mavlink:       bridgeMavlinkField.text.trim()  || "udpin:0.0.0.0:14550",
                            camera_topic:  bridgeCameraField.text.trim()   || "/flow_camera/image",
                            lidar_topic:   bridgeLidarField.text.trim()    || "/lidar/scan"
                        })
                        sitl.launchSensorBridge(cfg)
                    }
                }
            }

            // Bridge stoppen
            Rectangle {
                width: 100; height: 36; radius: 7
                property bool _running: parent.parent._bridgeStatus === "running"
                color: _running && bridgeStopM.containsMouse ? "#7f1d1d" : "#1e2535"
                border.color: _running ? "#ef4444" : "#2d3748"; border.width: 1
                Text {
                    anchors.centerIn: parent
                    text: "■ Stoppen"
                    color: parent._running ? "#fca5a5" : "#374151"
                    font.pixelSize: 10; font.weight: Font.Bold
                }
                MouseArea {
                    id: bridgeStopM; anchors.fill: parent; hoverEnabled: true
                    enabled: parent._running
                    onClicked: { if (typeof sitl !== "undefined" && sitl) sitl.stopSensorBridge() }
                }
            }
        }

        // EKF Non-GPS Hinweis (ausklappbar)
        Rectangle {
            id: ekfHintBox
            width: parent.width
            height: ekfHintContent.implicitHeight + 20
            radius: 6; color: "#07101a"
            border.color: "#334155"; border.width: 1

            Column {
                id: ekfHintContent
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                spacing: 4

                Text {
                    text: "⚠  Optical Flow ohne GPS aktivieren (nach Flow-Prüfung)"
                    color: "#f59e0b"; font.pixelSize: 10; font.weight: Font.Bold
                }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap
                    text: "param set EK3_SRC1_POSXY 0\n"
                        + "param set EK3_SRC1_VELXY 5\n"
                        + "reboot"
                    color: "#38bdf8"; font.pixelSize: 10; font.family: "Consolas"
                    lineHeight: 1.6
                }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap
                    text: "Nur setzen wenn die Flow-Richtung bereits mit aktivem GPS "
                        + "geprüft wurde (watch OPTICAL_FLOW_RAD in MAVProxy)."
                    color: "#475569"; font.pixelSize: 9
                }
            }
        }

    }   // Column colMain
    }   // ScrollView
}
