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

            // ── Video Stream Display ────────────────────────────────────
            Text { text: qsTr("VIDEO STREAM"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; topPadding: 10 }

            Rectangle {
                id: videoDisplayBox
                width: parent.width
                height: Math.min(parent.width * 9/16, 400) // 16:9 aspect ratio, max 400px
                radius: 8
                color: "#0d1117"
                border.color: "#2d3748"
                border.width: 1

                // Determine stream status via VideoStreamContext (R-10: never show blank video)
                property string _vsStatus: {
                    if (typeof videoStream === "undefined" || !videoStream) return "unconfigured"
                    var did = root.selectedDroneId || ""
                    if (!did) return "unconfigured"
                    var s = videoStream.getVideoStatus(did)
                    return s ? (s.status || "unconfigured") : "unconfigured"
                }
                property string _activeTarget: ""
                property bool _hasFrame: false
                Timer { interval: 250; running: true; repeat: true
                    onTriggered: {
                        if (typeof videoStream === "undefined" || !videoStream || !root.selectedDroneId) return
                        var s = videoStream.getVideoStatus(root.selectedDroneId)
                        parent._vsStatus = s ? (s.status || "unconfigured") : "unconfigured"
                        parent._activeTarget = s ? (s.activeTarget || "") : ""
                        parent._hasFrame = !!(s && s.hasFrame)
                        if (parent._vsStatus === "receiving" && parent._activeTarget === "gimbal" && parent._hasFrame)
                            gimbalVideoFrame.source = videoStream.frameUrl(root.selectedDroneId)
                    }
                }

                // Video stream placeholder/display area
                Rectangle {
                    anchors { fill: parent; margins: 2 }
                    radius: 6
                    color: "#000000"

                    Connections {
                        target: typeof videoStream !== "undefined" ? videoStream : null
                        function onFrameChanged(droneId, frameUrl) {
                            if (droneId === root.selectedDroneId && videoDisplayBox._activeTarget === "gimbal")
                                gimbalVideoFrame.source = frameUrl
                        }
                    }

                    Image {
                        id: gimbalVideoFrame
                        anchors.fill: parent
                        cache: false
                        asynchronous: true
                        fillMode: Image.PreserveAspectFit
                        visible: videoDisplayBox._vsStatus === "receiving" && videoDisplayBox._activeTarget === "gimbal" && videoDisplayBox._hasFrame
                        source: ""
                    }

                    // Placeholder — visible for ALL states except "receiving"
                    // R-10: no blank video rectangle before stream is available
                    Column {
                        anchors.centerIn: parent
                        spacing: 12
                        visible: videoDisplayBox._vsStatus !== "receiving" || videoDisplayBox._activeTarget !== "gimbal" || !videoDisplayBox._hasFrame

                        Text {
                            text: {
                                var s = videoDisplayBox._vsStatus
                                if (s === "waiting")  return "⏳"
                                if (s === "stalled")  return "⚠"
                                if (s === "error")    return "✕"
                                return "📹"
                            }
                            color: {
                                var s = videoDisplayBox._vsStatus
                                if (s === "waiting")  return "#f59e0b"
                                if (s === "stalled")  return "#f97316"
                                if (s === "error")    return "#ef4444"
                                return "#64748b"
                            }
                            font.pixelSize: 48
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        Text {
                            text: {
                                var s = videoDisplayBox._vsStatus
                                if (s === "waiting")  return qsTr("Waiting for stream …")
                                if (s === "stalled")  return qsTr("Stream stalled")
                                if (s === "error")    return qsTr("Stream error")
                                return qsTr("No Active Stream")
                            }
                            color: {
                                var s = videoDisplayBox._vsStatus
                                if (s === "waiting")  return "#f59e0b"
                                if (s === "stalled")  return "#f97316"
                                if (s === "error")    return "#ef4444"
                                return "#64748b"
                            }
                            font.pixelSize: 14
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        Text {
                            text: {
                                if (typeof videoStream === "undefined" || !videoStream || !root.selectedDroneId) return ""
                                var s = videoStream.getVideoStatus(root.selectedDroneId)
                                return s && s.url ? s.url : qsTr("Configure stream in ROS2 Panel → Video Stream")
                            }
                            color: "#475569"
                            font.pixelSize: 9; font.family: "Consolas"
                            anchors.horizontalCenter: parent.horizontalCenter
                            wrapMode: Text.WordWrap; width: parent.width * 0.9
                        }
                    }

                    // Stream active indicator (ONLY when receiving)
                    Rectangle {
                        anchors { top: parent.top; left: parent.left; margins: 8 }
                        width: streamLabel.width + 16
                        height: 24
                        radius: 4
                        color: "#059669"
                        visible: videoDisplayBox._vsStatus === "receiving" && videoDisplayBox._activeTarget === "gimbal" && videoDisplayBox._hasFrame

                        Row {
                            anchors.centerIn: parent
                            spacing: 6
                            Rectangle {
                                width: 8; height: 8; radius: 4
                                color: "#ffffff"
                                anchors.verticalCenter: parent.verticalCenter
                                SequentialAnimation on opacity {
                                    running: true
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1.0; to: 0.3; duration: 800 }
                                    NumberAnimation { from: 0.3; to: 1.0; duration: 800 }
                                }
                            }
                            Text {
                                id: streamLabel
                                text: qsTr("LIVE")
                                color: "#ffffff"
                                font.pixelSize: 10
                                font.weight: Font.Bold
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }

                    // Stream info overlay (bottom) — only when receiving
                    Rectangle {
                        anchors { bottom: parent.bottom; left: parent.left; right: parent.right; margins: 8 }
                        height: 28
                        radius: 4
                        color: "#1a2035cc"
                        visible: videoDisplayBox._vsStatus === "receiving" && videoDisplayBox._activeTarget === "gimbal" && videoDisplayBox._hasFrame

                        Row {
                            anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                            spacing: 12

                            Text {
                                text: typeof camera !== "undefined" ? camera.currentSource : "—"
                                color: "#e2e8f0"
                                font.pixelSize: 10
                                font.family: "Consolas"
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Rectangle {
                                width: 1; height: 16
                                color: "#334155"
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Text {
                                text: {
                                    if (typeof camera === "undefined") return "—"
                                    var status = camera.getCameraStatus()
                                    return status.resolution || "—"
                                }
                                color: "#94a3b8"
                                font.pixelSize: 10
                                font.family: "Consolas"
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Text {
                                text: {
                                    if (typeof camera === "undefined") return "—"
                                    var status = camera.getCameraStatus()
                                    return status.fps ? status.fps + " fps" : "—"
                                }
                                color: "#94a3b8"
                                font.pixelSize: 10
                                font.family: "Consolas"
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Item { width: 1; height: 1; Layout.fillWidth: true }

                            // Recording indicator in stream overlay
                            Row {
                                spacing: 4
                                visible: typeof camera !== "undefined" && camera.recordingActive
                                anchors.verticalCenter: parent.verticalCenter

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
                                    text: qsTr("REC")
                                    color: "#ef4444"
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }
                    }

                }
            }

            // ── Gimbal controls ─────────────────────────────────────────
            Row {
                width: parent.width
                spacing: 8

                Rectangle {
                    width: (parent.width - 8) / 2
                    height: 34
                    radius: 5
                    color: gimbalStartStreamM.containsMouse ? "#166534" : "#14532d"
                    border.color: "#22c55e"; border.width: 1
                    Text { anchors.centerIn: parent; text: "Start Stream"; color: "#86efac"; font.pixelSize: 10; font.weight: Font.Bold }
                    MouseArea {
                        id: gimbalStartStreamM
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            if (typeof videoStream === "undefined" || !videoStream || !root.selectedDroneId) return
                            var s = videoStream.getVideoStatus(root.selectedDroneId)
                            var url = s && s.url ? s.url : "udp://0.0.0.0:" + (s && s.port ? s.port : 5600)
                            videoStream.startStream(url, root.selectedDroneId, "gimbal")
                        }
                    }
                }

                Rectangle {
                    width: (parent.width - 8) / 2
                    height: 34
                    radius: 5
                    color: gimbalEndStreamM.containsMouse ? "#7f1d1d" : "#450a0a"
                    border.color: "#ef4444"; border.width: 1
                    Text { anchors.centerIn: parent; text: "End Stream"; color: "#fca5a5"; font.pixelSize: 10; font.weight: Font.Bold }
                    MouseArea {
                        id: gimbalEndStreamM
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: { if (typeof videoStream !== "undefined" && videoStream && root.selectedDroneId) videoStream.stopStream(root.selectedDroneId) }
                    }
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
            Text { text: qsTr("CAMERA CONTROLS"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; topPadding: 10 }

            Rectangle {
                width: parent.width; height: cameraCol.implicitHeight + 20; radius: 8
                color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                enabled: isObservation(root.selectedDroneId)
                opacity: enabled ? 1.0 : 0.4

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
            Text { text: qsTr("CAMERA SETTINGS"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; topPadding: 10 }

            Rectangle {
                width: parent.width; height: settingsCol.implicitHeight + 20; radius: 8
                color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                enabled: isObservation(root.selectedDroneId)
                opacity: enabled ? 1.0 : 0.4

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
            Text { text: qsTr("THERMAL SETTINGS"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; topPadding: 10 }

            Rectangle {
                width: parent.width; height: thermalCol.implicitHeight + 20; radius: 8
                color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                enabled: isObservation(root.selectedDroneId)
                opacity: enabled ? 1.0 : 0.4

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
            Text { text: qsTr("CAMERA STATUS"); color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; topPadding: 10 }

            Rectangle {
                width: parent.width; height: statusCol.implicitHeight + 20; radius: 8
                color: "#0d1117"; border.color: "#2d3748"; border.width: 1

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
                        Text { text: qsTr("Source:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: sourceText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Profile:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: profileText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Resolution:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: resText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("FPS:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: fpsText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Frame Age:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: frameAgeText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Dropped Frames:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: droppedText; text: "—"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: qsTr("Status:"); color: "#64748b"; font.pixelSize: 10; width: 100 }
                        Text { id: gimbalErrorText; text: qsTr("No errors"); color: "#10b981"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                }
            }
        }
    }
}
