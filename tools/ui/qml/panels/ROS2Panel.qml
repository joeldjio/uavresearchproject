import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components" as Cmp

Item {
    id: root
    anchors.fill: parent

    property string selectedDroneId: Cmp.AppState.selectedDroneId
    property string _nodeStatus: (typeof ros2 !== "undefined" && ros2) ? ros2.nodeStatus() : "no_ros2"
    property var globalWaypoints: null  // Injected from main.qml
    property bool _useVisibleTerminal: (typeof ros2 !== "undefined" && ros2 && ros2.getUseVisibleTerminal) ? ros2.getUseVisibleTerminal() : true

    // Tracks whether the bridge for the currently selected drone is active.
    // Polled every 500ms so the Debug-tab warning and the Connection-tab status
    // stay in sync without needing cross-tab id references.
    property bool _anyBridgeActive: false
    Timer {
        interval: 500; running: true; repeat: true
        onTriggered: root._anyBridgeActive =
            (typeof ros2 !== "undefined" && ros2 && root.selectedDroneId !== "")
            ? ros2.isBridgeActive(root.selectedDroneId) : false
    }

    // Keep selectedDroneId in sync when any other panel changes the global selection.
    Connections {
        target: Cmp.AppState
        function onSelectedDroneIdChanged() {
            root.selectedDroneId = Cmp.AppState.selectedDroneId
            var model = droneCombo.model
            if (!model) return
            var idx = -1
            for (var i = 0; i < model.length; i++) {
                if (model[i] === Cmp.AppState.selectedDroneId) { idx = i; break }
            }
            if (idx >= 0 && droneCombo.currentIndex !== idx)
                droneCombo.currentIndex = idx
        }
    }

    // Force a fresh nodeStatus check when the panel first loads so the status
    // dot shows the correct colour immediately (not stale from import time).
    Component.onCompleted: {
        root._nodeStatus = (typeof ros2 !== "undefined" && ros2)
                           ? ros2.nodeStatus() : "no_ros2"
        if (Cmp.AppState.selectedDroneId !== "")
            root.selectedDroneId = Cmp.AppState.selectedDroneId
    }

    function statusColor(s) {
        if (s === "ok")           return "#22c55e"
        if (s === "no_px4_msgs") return "#f59e0b"
        return "#ef4444"
    }
    function statusLabel(s) {
        if (s === "ok")           return "ROS2 + px4_msgs OK"
        if (s === "no_px4_msgs") return "ROS2 OK — px4_msgs missing"
        return "rclpy not installed"
    }
    function worldProfileWarnings(model, worldProfile) {
        if (typeof ros2 === "undefined" || !ros2 || !ros2.getWorldProfileWarnings)
            return []
        return ros2.getWorldProfileWarnings(model, worldProfile)
    }
    function setupSourceListFromText(text) {
        var raw = text.split(/\r?\n/)
        var result = []
        for (var i = 0; i < raw.length; ++i) {
            var line = raw[i].trim()
            if (line.indexOf("source ") === 0)
                line = line.substring(7).trim()
            if (line.indexOf(". ") === 0)
                line = line.substring(2).trim()
            if (line.length > 0 && result.indexOf(line) < 0)
                result.push(line)
        }
        return result
    }
    function shellCommandFromText(text) {
        var raw = text.split(/\r?\n/)
        var result = []
        for (var i = 0; i < raw.length; ++i) {
            var line = raw[i].trim()
            if (line.length > 0)
                result.push(line)
        }
        return result.join(" && ")
    }
    function ros2SetupSourceList() {
        if (!setupSourcesEdit)
            return []
        return root.setupSourceListFromText(setupSourcesEdit.text)
    }
    function sitlRos2SetupSourceList() {
        if (!sitlSetupSourcesEdit)
            return []
        return root.setupSourceListFromText(sitlSetupSourcesEdit.text)
    }
    function syncRos2SetupSources() {
        if (typeof ros2 !== "undefined" && ros2 && ros2.setRos2SetupSourcesText)
            ros2.setRos2SetupSourcesText(setupSourcesEdit.text)
    }
    function setVisibleTerminalEnabled(enabled) {
        root._useVisibleTerminal = enabled
        if (typeof ros2 !== "undefined" && ros2 && ros2.setUseVisibleTerminal)
            ros2.setUseVisibleTerminal(enabled)
    }

    Timer { interval: 2000; running: true; repeat: true
        onTriggered: root._nodeStatus = (typeof ros2 !== "undefined" && ros2) ? ros2.nodeStatus() : "no_ros2"
    }

    // ── Tab bar ──────────────────────────────────────────────────────────────
    Rectangle {
        id: tabBar
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: 34
        color: "#0d1117"
        border.color: "#1e2535"; border.width: 1

        Row {
            anchors { fill: parent; leftMargin: 8 }
            spacing: 2

            Repeater {
                model: ["Connection", "Topics", "Bag", "Video", "Debug"]
                delegate: Rectangle {
                    width: 90; height: parent.height
                    color: tabView.currentIndex === index ? "#1a2035" : "transparent"
                    border.color: tabView.currentIndex === index ? "#3b82f6" : "transparent"
                    border.width: tabView.currentIndex === index ? 0 : 0
                    // bottom indicator line
                    Rectangle {
                        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
                        height: 2
                        color: tabView.currentIndex === index ? "#3b82f6" : "transparent"
                    }
                    Text {
                        anchors.centerIn: parent
                        text: modelData
                        color: tabView.currentIndex === index ? "#93c5fd" : "#64748b"
                        font.pixelSize: 10; font.weight: tabView.currentIndex === index ? Font.Bold : Font.Normal
                    }
                    MouseArea { anchors.fill: parent; onClicked: tabView.currentIndex = index }
                }
            }

            // Node status dot (right-aligned)
            Item { width: 1; height: 1 }
        }

        // Status dot (right side)
        Row {
            anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
            spacing: 5
            Rectangle {
                width: 8; height: 8; radius: 4; anchors.verticalCenter: parent.verticalCenter
                color: statusColor(root._nodeStatus)
                SequentialAnimation on opacity {
                    running: root._nodeStatus === "ok"; loops: Animation.Infinite
                    NumberAnimation { to: 0.3; duration: 800 }
                    NumberAnimation { to: 1.0; duration: 800 }
                }
            }
            Text {
                text: statusLabel(root._nodeStatus)
                color: statusColor(root._nodeStatus)
                font.pixelSize: 9; anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // ── Tab content ──────────────────────────────────────────────────────────
    StackLayout {
        id: tabView
        anchors { top: tabBar.bottom; left: parent.left; right: parent.right; bottom: parent.bottom }
        currentIndex: 0

        // ══════════════════════════════════════════════════════════
        // TAB 0 — CONNECTION
        // ══════════════════════════════════════════════════════════
        ScrollView {
            clip: true; contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                width: parent.width
                padding: 12; spacing: 10

                // ── ROS2 node info (only when not OK) ──────────────
                Rectangle {
                    width: parent.width - 24; radius: 8
                    height: infoCol.implicitHeight + 16
                    color: "#1a1500"; border.color: "#78350f"; border.width: 1
                    visible: root._nodeStatus !== "ok"
                    Column {
                        id: infoCol
                        anchors { fill: parent; margins: 10 }
                        spacing: 4
                        Text { text: root._nodeStatus === "no_ros2" ? "Install ROS2 Humble+:" : "Build px4_msgs:"; color: "#fcd34d"; font.pixelSize: 10; font.weight: Font.Bold }
                        Text {
                            text: root._nodeStatus === "no_ros2"
                                ? "sudo apt install ros-humble-desktop\nsource /opt/ros/humble/setup.bash\npip install rclpy"
                                : "cd ~/ros2_ws/src\ngit clone https://github.com/PX4/px4_msgs\ncd ~/ros2_ws && colcon build\nsource install/setup.bash"
                            color: "#94a3b8"; font.pixelSize: 9; font.family: "Consolas"; wrapMode: Text.WordWrap; width: parent.width
                        }
                        Text { text: "uXRCE-DDS Agent:"; color: "#fcd34d"; font.pixelSize: 10; font.weight: Font.Bold; visible: root._nodeStatus === "no_px4_msgs" }
                        Text { visible: root._nodeStatus === "no_px4_msgs"; text: "MicroXRCEAgent udp4 -p 8888"; color: "#94a3b8"; font.pixelSize: 9; font.family: "Consolas" }
                    }
                }

                // ── Bridge Connect ──────────────────────────────────
                Text { text: "PX4 BRIDGE"; visible: false; height: 0; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1; leftPadding: 0 }
                Rectangle {
                    visible: false
                    width: parent.width - 24; height: 0; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: connCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        spacing: 8

                        ComboBox {
                            id: droneCombo; width: parent.width; height: 28
                            model: (typeof swarm !== "undefined" && swarm) ? swarm.droneIds() : []
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            contentItem: Text { text: droneCombo.displayText; color: "#e2e8f0"; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: 6 }
                            Component.onCompleted: {
                                if (Cmp.AppState.selectedDroneId !== "") {
                                    for (var i = 0; i < model.length; i++) {
                                        if (model[i] === Cmp.AppState.selectedDroneId) {
                                            currentIndex = i
                                            break
                                        }
                                    }
                                } else if (currentText) {
                                    root.selectedDroneId = currentText
                                    Cmp.AppState.selectedDroneId = currentText
                                }
                            }
                            onCurrentTextChanged: {
                                if (currentText) {
                                    root.selectedDroneId = currentText
                                    Cmp.AppState.selectedDroneId = currentText
                                }
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "NS:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 22 }
                            TextField {
                                id: nsField; width: parent.width - 28; height: 26
                                text: (typeof ros2 !== "undefined" && ros2) ? ros2.getSitlNamespace() : "uav_1"
                                placeholderText: "uav_1  (empty = /fmu/*)"
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 6
                            }
                        }
                        Text {
                            width: parent.width
                            text: nsField.text.trim() === "" ? "/fmu/out/*  /fmu/in/*" : "/" + nsField.text.trim() + "/fmu/out|in/*"
                            color: "#475569"; font.pixelSize: 8; font.family: "Consolas"
                        }

                        Row {
                            width: parent.width; spacing: 6; height: 18
                            Text { text: "ROS2 setup sources (Bridge + SITL)"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                            Rectangle {
                                width: 16; height: 16; radius: 8
                                color: setupSourceHelp.containsMouse ? "#1e3a5f" : "#1e2535"
                                border.color: "#3b82f6"; border.width: 1
                                Text { anchors.centerIn: parent; text: "?"; color: "#93c5fd"; font.pixelSize: 10; font.weight: Font.Bold }
                                MouseArea {
                                    id: setupSourceHelp; anchors.fill: parent; hoverEnabled: true
                                    ToolTip.visible: containsMouse
                                    ToolTip.delay: 350
                                    ToolTip.text: "Source these setup.bash files before starting the PX4 bridge or SITL. Put one path per line."
                                }
                            }
                        }
                        TextArea {
                            id: setupSourcesEdit
                            width: parent.width; height: 58
                            text: (typeof ros2 !== "undefined" && ros2 && ros2.getRos2SetupSourcesText) ? ros2.getRos2SetupSourcesText() : "/opt/ros/humble/setup.bash\n/home/iruz/ws_sensor_combined/install/setup.bash"
                            wrapMode: TextEdit.NoWrap
                            selectByMouse: true
                            color: "#e2e8f0"; selectedTextColor: "#0f172a"; selectionColor: "#93c5fd"
                            font.pixelSize: 9; font.family: "Consolas"
                            leftPadding: 6; rightPadding: 6; topPadding: 5; bottomPadding: 5
                            background: Rectangle { color: "#111827"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            onActiveFocusChanged: { if (!activeFocus) root.syncRos2SetupSources() }
                        }
                        Row {
                            width: parent.width; spacing: 8; height: 24
                            CheckBox {
                                id: visibleTerminalToggle
                                width: 22; height: 22
                                checked: root._useVisibleTerminal
                                onCheckedChanged: { if (checked !== root._useVisibleTerminal) root.setVisibleTerminalEnabled(checked) }
                            }
                            Text {
                                width: parent.width - 30
                                text: "Open visible terminal on Bridge start"
                                color: "#94a3b8"; font.pixelSize: 9; wrapMode: Text.WordWrap
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }

                        property bool _bridgeActive: (typeof ros2 !== "undefined" && ros2 && root.selectedDroneId !== "") ? ros2.isBridgeActive(root.selectedDroneId) : false
                        Timer { interval: 500; running: true; repeat: true
                            onTriggered: connCol._bridgeActive = (typeof ros2 !== "undefined" && ros2 && root.selectedDroneId !== "") ? ros2.isBridgeActive(root.selectedDroneId) : false
                        }

                        Rectangle {
                            width: parent.width; height: 32; radius: 6
                            color: {
                                return bridgeTogM.containsMouse ? (connCol._bridgeActive ? "#7f1d1d" : "#166534") : (connCol._bridgeActive ? "#450a0a" : "#14532d")
                            }
                            border.color: connCol._bridgeActive ? "#ef4444" : "#22c55e"; border.width: 1
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Row {
                                anchors.centerIn: parent; spacing: 6
                                Text { text: connCol._bridgeActive ? "■" : "▶"; color: root._nodeStatus !== "ok" ? "#64748b" : (connCol._bridgeActive ? "#fca5a5" : "#86efac"); font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: root._nodeStatus !== "ok" ? "Connect (ROS2 required)" : (connCol._bridgeActive ? "Disconnect" : "Connect to PX4"); color: root._nodeStatus !== "ok" ? "#64748b" : (connCol._bridgeActive ? "#fca5a5" : "#86efac"); font.pixelSize: 10; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                            }
                            MouseArea {
                                id: bridgeTogM; anchors.fill: parent; hoverEnabled: true
                                enabled: root.selectedDroneId !== ""
                                onClicked: {
                                    if (typeof ros2 === "undefined" || !ros2) return
                                    root.syncRos2SetupSources()
                                    connCol._bridgeActive ? ros2.stopBridge(root.selectedDroneId) : ros2.startBridge(root.selectedDroneId, nsField.text.trim())
                                }
                            }
                        }
                        Text {
                            width: parent.width
                            visible: root._nodeStatus !== "ok"
                            text: "Connect sources the setup files first, then checks ROS2 again."
                            color: "#fbbf24"; font.pixelSize: 8; wrapMode: Text.WordWrap
                        }
                    }
                }

                // ── PX4 SITL ───────────────────────────────────────
                Text { text: "PX4 SITL"; visible: false; height: 0; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    visible: false
                    width: parent.width - 24; height: 0; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: sitlCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        spacing: 8

                        property bool _sitlRunning: (typeof ros2 !== "undefined" && ros2) ? ros2.isSitlRunning() : false
                        Timer { interval: 1000; running: true; repeat: true
                            onTriggered: sitlCol._sitlRunning = (typeof ros2 !== "undefined" && ros2) ? ros2.isSitlRunning() : false
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "PX4:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 30 }
                            TextField {
                                id: px4DirField; width: parent.width - 36; height: 26
                                text: (typeof ros2 !== "undefined" && ros2) ? ros2.getSitlPx4Dir() : ""
                                placeholderText: "/home/user/PX4-Autopilot"
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 9; font.family: "Consolas"; leftPadding: 6
                                onEditingFinished: { if (typeof ros2 !== "undefined" && ros2) ros2.setSitlPx4Dir(text) }
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6; height: 18
                            Text { text: "ROS2 setup sources (SITL)"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                            Rectangle {
                                width: 16; height: 16; radius: 8
                                color: sitlSetupSourceHelp.containsMouse ? "#1e3a5f" : "#1e2535"
                                border.color: "#3b82f6"; border.width: 1
                                Text { anchors.centerIn: parent; text: "?"; color: "#93c5fd"; font.pixelSize: 10; font.weight: Font.Bold }
                                MouseArea {
                                    id: sitlSetupSourceHelp; anchors.fill: parent; hoverEnabled: true
                                    ToolTip.visible: containsMouse
                                    ToolTip.delay: 350
                                    ToolTip.text: "These setup.bash files are sourced only for PX4 SITL startup. Put one path per line."
                                }
                            }
                        }
                        TextArea {
                            id: sitlSetupSourcesEdit
                            width: parent.width; height: 58
                            text: (typeof ros2 !== "undefined" && ros2 && ros2.getRos2SetupSourcesText) ? ros2.getRos2SetupSourcesText() : "/opt/ros/humble/setup.bash\n/home/iruz/ws_sensor_combined/install/setup.bash"
                            wrapMode: TextEdit.NoWrap
                            selectByMouse: true
                            color: "#e2e8f0"; selectedTextColor: "#0f172a"; selectionColor: "#93c5fd"
                            font.pixelSize: 9; font.family: "Consolas"
                            leftPadding: 6; rightPadding: 6; topPadding: 5; bottomPadding: 5
                            background: Rectangle { color: "#111827"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Model:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 40 }
                            ComboBox {
                                id: modelCombo; width: parent.width - 46; height: 26
                                model: ["gz_x500", "gz_x500_gimbal", "gz_x500_mono_cam", "gz_x500_lidar_down",
                                        "gz_standard_vtol", "gz_rc_cessna", "iris", "sih_quadx"]
                                currentIndex: {
                                    if (typeof ros2 === "undefined" || !ros2) return 0
                                    var m = ros2.getSitlModel(); var idx = model.indexOf(m); return idx >= 0 ? idx : 0
                                }
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                contentItem: Text { text: modelCombo.displayText; color: "#e2e8f0"; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter; leftPadding: 6 }
                                onCurrentTextChanged: { if (typeof ros2 !== "undefined" && ros2) ros2.setSitlModel(currentText) }
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "World:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 40 }
                            ComboBox {
                                id: worldCombo; width: parent.width - 46; height: 26
                                model: ["empty_default", "aruco_precision_landing", "baylands_water",
                                        "ridge_terrain", "walls_collision", "windy_disturbance",
                                        "moving_platform", "rover_grid"]
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                contentItem: Text { text: worldCombo.displayText; color: "#e2e8f0"; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter; leftPadding: 6 }
                            }
                        }

                        // World/model compatibility warning
                        Rectangle {
                            width: parent.width; height: worldWarnTxt.implicitHeight + 10; radius: 5
                            color: "#78350f22"; border.color: "#f59e0b"; border.width: 1
                            visible: root.worldProfileWarnings(modelCombo.currentText, worldCombo.currentText).length > 0
                            Text {
                                id: worldWarnTxt; anchors { fill: parent; margins: 5 }
                                text: {
                                    var w = worldCombo.currentText; var m = modelCombo.currentText
                                    if (w === "moving_platform") return "⚠ Set PX4_GZ_MODEL_POSE=0,0,2.2"
                                    if (w === "ridge_terrain" && !m.includes("lidar")) return "⚠ ridge works best with x500_lidar_down"
                                    if (w === "aruco_precision_landing" && !m.includes("mono_cam")) return "⚠ aruco needs x500_mono_cam"
                                    return ""
                                }
                                color: "#fcd34d"; font.pixelSize: 8; wrapMode: Text.WordWrap
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "NS:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 30 }
                            TextField {
                                id: sitlNsField; width: parent.width - 36; height: 26
                                text: (typeof ros2 !== "undefined" && ros2) ? ros2.getSitlNamespace() : "uav_1"
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 6
                                onEditingFinished: { if (typeof ros2 !== "undefined" && ros2) ros2.setSitlNamespace(text) }
                            }
                        }

                        Row {
                            width: parent.width; spacing: 8
                            visible: modelCombo.currentText.includes("gimbal") || modelCombo.currentText.includes("cam")
                            CheckBox {
                                id: cameraToggle; checked: true
                                contentItem: Text { text: "Camera"; color: "#e2e8f0"; font.pixelSize: 10; leftPadding: cameraToggle.indicator.width + 4; verticalAlignment: Text.AlignVCenter }
                            }
                            CheckBox {
                                id: gimbalToggle; checked: modelCombo.currentText.includes("gimbal")
                                contentItem: Text { text: "Gimbal"; color: "#e2e8f0"; font.pixelSize: 10; leftPadding: gimbalToggle.indicator.width + 4; verticalAlignment: Text.AlignVCenter }
                            }
                        }

                        Text { visible: modelCombo.currentText.includes("sih"); text: "SIH: headless — no Gazebo"; color: "#60a5fa"; font.pixelSize: 8; width: parent.width }

                        Row {
                            width: parent.width; spacing: 8; height: 24
                            CheckBox {
                                id: sitlVisibleTerminalToggle
                                width: 22; height: 22
                                checked: root._useVisibleTerminal
                                onCheckedChanged: { if (checked !== root._useVisibleTerminal) root.setVisibleTerminalEnabled(checked) }
                            }
                            Text {
                                width: parent.width - 30
                                text: "Open visible terminal on SITL start"
                                color: "#94a3b8"; font.pixelSize: 9; wrapMode: Text.WordWrap
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }

                        // Start / Stop SITL
                        Rectangle {
                            width: parent.width; height: 32; radius: 6
                            color: sitlTogM.containsMouse ? (sitlCol._sitlRunning ? "#7f1d1d" : "#166534") : (sitlCol._sitlRunning ? "#450a0a" : "#14532d")
                            border.color: sitlCol._sitlRunning ? "#ef4444" : "#22c55e"; border.width: 1
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Row {
                                anchors.centerIn: parent; spacing: 6
                                Text { text: sitlCol._sitlRunning ? "■" : "▶"; color: sitlCol._sitlRunning ? "#fca5a5" : "#86efac"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: sitlCol._sitlRunning ? "Stop SITL" : "Start SITL"; color: sitlCol._sitlRunning ? "#fca5a5" : "#86efac"; font.pixelSize: 10; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                            }
                            MouseArea {
                                id: sitlTogM; anchors.fill: parent; hoverEnabled: true
                                onClicked: {
                                    if (typeof ros2 === "undefined" || !ros2) return
                                    if (sitlCol._sitlRunning) {
                                        ros2.stopSitl()
                                    } else {
                                        ros2.startSitl({ model: modelCombo.currentText, worldProfile: worldCombo.currentText,
                                                         namespace: sitlNsField.text, cameraEnabled: cameraToggle.checked,
                                                         gimbalEnabled: gimbalToggle.checked, px4Dir: px4DirField.text,
                                                         ros2Setups: root.sitlRos2SetupSourceList() })
                                    }
                                }
                            }
                        }

                        // SITL Status box
                        Rectangle {
                            width: parent.width; height: sitlStatusCol.implicitHeight + 10; radius: 5
                            color: "#0d1117"; border.color: sitlCol._sitlRunning ? "#22c55e33" : "#2d3748"; border.width: 1
                            visible: sitlCol._sitlRunning
                            Column {
                                id: sitlStatusCol
                                anchors { fill: parent; margins: 5 }
                                spacing: 2
                                property var _st: ({})
                                Timer { interval: 2000; running: sitlCol._sitlRunning; repeat: true
                                    onTriggered: sitlStatusCol._st = (typeof ros2 !== "undefined" && ros2 && ros2.getSitlStatus) ? ros2.getSitlStatus() : {}
                                }
                                Repeater {
                                    model: [{ key:"model",label:"Model"},{key:"namespace",label:"NS"},{key:"pid",label:"PID"},{key:"uptime_s",label:"Up"},{key:"gazebo_running",label:"Gazebo"}]
                                    delegate: Row {
                                        spacing: 4; width: sitlStatusCol.width
                                        Text { text: modelData.label + ":"; color: "#475569"; font.pixelSize: 8; width: 44 }
                                        Text {
                                            text: { var v = sitlStatusCol._st[modelData.key]; if (v === undefined) return "—"; if (modelData.key === "uptime_s") return v.toFixed(0)+"s"; if (modelData.key === "gazebo_running") return v ? "✓" : "✗"; return v.toString() }
                                            color: { var v = sitlStatusCol._st[modelData.key]; if (modelData.key === "gazebo_running") return v ? "#22c55e" : "#ef4444"; return "#e2e8f0" }
                                            font.pixelSize: 8; font.family: "Consolas"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // ── Multi-Vehicle SITL ──────────────────────────────
                Text { text: "MULTI-VEHICLE SITL"; visible: false; height: 0; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    visible: false
                    width: parent.width - 24; height: 0; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: multiCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        spacing: 8

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Count:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 50 }
                            SpinBox {
                                id: multiCountSpin; from: 1; to: 5; value: 1; width: parent.width - 56; height: 26
                                contentItem: Text { text: multiCountSpin.textFromValue(multiCountSpin.value); color: "#e2e8f0"; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Base port:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 60 }
                            TextField {
                                id: basePortField; width: parent.width - 66; height: 26; text: "5762"
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 6
                            }
                        }

                        Text {
                            width: parent.width
                            text: "Ports: " + Array.from({length: multiCountSpin.value}, function(_, i) { return parseInt(basePortField.text || 5762) + i }).join(", ")
                            color: "#475569"; font.pixelSize: 8; font.family: "Consolas"
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 30; radius: 5
                                color: startAllM.containsMouse ? "#166534" : "#14532d"; border.color: "#22c55e"; border.width: 1
                                Text { anchors.centerIn: parent; text: "▶ Start All"; color: "#86efac"; font.pixelSize: 10; font.weight: Font.Bold }
                                MouseArea { id: startAllM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: { if (typeof ros2 !== "undefined" && ros2) { root.syncRos2SetupSources(); ros2.startMultiSitl(multiCountSpin.value, parseInt(basePortField.text) || 5762) } }
                                }
                            }
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 30; radius: 5
                                color: stopAllM.containsMouse ? "#7f1d1d" : "#450a0a"; border.color: "#ef4444"; border.width: 1
                                Text { anchors.centerIn: parent; text: "■ Stop All"; color: "#fca5a5"; font.pixelSize: 10; font.weight: Font.Bold }
                                MouseArea { id: stopAllM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: { if (typeof ros2 !== "undefined" && ros2) ros2.stopAllSitl() }
                                }
                            }
                        }
                    }
                }

                // ── Formation Control ───────────────────────────────
                Text { text: "FORMATION CONTROL"; visible: false; height: 0; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    visible: false
                    width: parent.width - 24; height: 0; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: formCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        spacing: 8

                        property bool _formActive: (typeof ros2 !== "undefined" && ros2) ? ros2.isFormationActive() : false
                        Timer { interval: 500; running: true; repeat: true
                            onTriggered: formCol._formActive = (typeof ros2 !== "undefined" && ros2) ? ros2.isFormationActive() : false
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Leader:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 50 }
                            ComboBox {
                                id: leaderCombo; width: parent.width - 56; height: 26
                                model: (typeof swarm !== "undefined" && swarm) ? swarm.droneIds() : []
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                contentItem: Text { text: leaderCombo.displayText; color: "#e2e8f0"; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter; leftPadding: 6 }
                            }
                        }
                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Shape:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 50 }
                            ComboBox {
                                id: shapeCombo; width: parent.width - 56; height: 26; currentIndex: 1
                                model: ["line", "v", "grid", "circle", "wedge"]
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                contentItem: Text { text: shapeCombo.displayText; color: "#e2e8f0"; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter; leftPadding: 6 }
                            }
                        }
                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Spacing:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 50 }
                            Slider {
                                id: spacingSlider; width: parent.width - 100; from: 2.0; to: 20.0; value: 5.0; stepSize: 0.5
                                background: Rectangle { x: spacingSlider.leftPadding; y: spacingSlider.topPadding + spacingSlider.availableHeight/2 - height/2; width: spacingSlider.availableWidth; height: 4; radius: 2; color: "#2d3748"
                                    Rectangle { width: spacingSlider.visualPosition * parent.width; height: parent.height; radius: 2; color: "#3b82f6" }
                                }
                                handle: Rectangle { x: spacingSlider.leftPadding + spacingSlider.visualPosition*(spacingSlider.availableWidth-width); y: spacingSlider.topPadding + spacingSlider.availableHeight/2 - height/2; width: 16; height: 16; radius: 8; color: spacingSlider.pressed ? "#60a5fa" : "#3b82f6"; border.color: "#1e293b"; border.width: 1 }
                            }
                            Text { text: spacingSlider.value.toFixed(1)+"m"; color: "#e2e8f0"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 40 }
                        }
                        Rectangle {
                            width: parent.width; height: 32; radius: 6
                            color: formTogM.containsMouse ? (formCol._formActive ? "#7f1d1d" : "#166534") : (formCol._formActive ? "#450a0a" : "#14532d")
                            border.color: formCol._formActive ? "#ef4444" : "#22c55e"; border.width: 1
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Row { anchors.centerIn: parent; spacing: 6
                                Text { text: formCol._formActive ? "■" : "▶"; color: formCol._formActive ? "#fca5a5" : "#86efac"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: formCol._formActive ? "Stop Formation" : "Start Formation"; color: formCol._formActive ? "#fca5a5" : "#86efac"; font.pixelSize: 10; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                            }
                            MouseArea { id: formTogM; anchors.fill: parent; hoverEnabled: true
                                onClicked: {
                                    if (typeof ros2 === "undefined" || !ros2) return
                                    if (formCol._formActive) { ros2.stopFormation() } else {
                                        var all = (typeof swarm !== "undefined" && swarm) ? swarm.droneIds() : []
                                        if (all.length < 2) return
                                        var leader = leaderCombo.currentText
                                        ros2.startFormation(leader, all.filter(function(id){return id!==leader}), shapeCombo.currentText, spacingSlider.value)
                                    }
                                }
                            }
                        }
                        Row {
                            width: parent.width; spacing: 4; visible: formCol._formActive
                            Rectangle { width:(parent.width-8)/3;height:28;radius:5; color:armM.containsMouse?"#166534":"#14532d"; border.color:"#22c55e";border.width:1
                                Text{anchors.centerIn:parent;text:"ARM ALL";color:"#86efac";font.pixelSize:9;font.weight:Font.Bold}
                                MouseArea{id:armM;anchors.fill:parent;hoverEnabled:true;onClicked:{if(typeof ros2!=="undefined"&&ros2)ros2.armFormation()}}
                            }
                            Rectangle { width:(parent.width-8)/3;height:28;radius:5; color:offbM.containsMouse?"#1e40af":"#1e3a8a"; border.color:"#3b82f6";border.width:1
                                Text{anchors.centerIn:parent;text:"OFFBOARD";color:"#93c5fd";font.pixelSize:9;font.weight:Font.Bold}
                                MouseArea{id:offbM;anchors.fill:parent;hoverEnabled:true;onClicked:{if(typeof ros2!=="undefined"&&ros2)ros2.enableOffboardFormation()}}
                            }
                            Rectangle { width:(parent.width-8)/3;height:28;radius:5; color:disarmM.containsMouse?"#7f1d1d":"#450a0a"; border.color:"#ef4444";border.width:1
                                Text{anchors.centerIn:parent;text:"DISARM";color:"#fca5a5";font.pixelSize:9;font.weight:Font.Bold}
                                MouseArea{id:disarmM;anchors.fill:parent;hoverEnabled:true;onClicked:{if(typeof ros2!=="undefined"&&ros2)ros2.disarmFormation()}}
                            }
                        }
                    }
                }

                // ═══════════════════════════════════════════════════
                // COMMAND LAUNCHER
                // Generates the exact shell commands the user needs to run,
                // with live editing and "▶ Run in Terminal" buttons.
                // ═══════════════════════════════════════════════════
                Text {
                    text: "COMMAND LAUNCHER"
                    color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold
                    font.letterSpacing: 1
                }
                Rectangle {
                    width: parent.width - 24
                    height: launchCol.implicitHeight + 20
                    radius: 8; color: "#0d1117"; border.color: "#2d3748"; border.width: 1

                    Column {
                        id: launchCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        spacing: 10

                        // ─── Step 1: MicroXRCE-DDS Agent ───────────────────────
                        Rectangle {
                            width: parent.width; height: 22; radius: 4
                            color: "#1a1500"; border.color: "#f59e0b"; border.width: 1
                            Text {
                                anchors { fill: parent; leftMargin: 8 }
                                text: "Step 1  —  Start MicroXRCE-DDS Agent (own terminal)"
                                color: "#fcd34d"; font.pixelSize: 9; font.weight: Font.Bold
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Port:"; color: "#64748b"; font.pixelSize: 9; width: 32; anchors.verticalCenter: parent.verticalCenter }
                            TextField {
                                id: xrcePortField; width: 64; height: 26; text: "8888"
                                background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 6
                                inputMethodHints: Qt.ImhDigitsOnly
                            }
                            Text { text: "Agent dir:"; color: "#64748b"; font.pixelSize: 9; width: 56; anchors.verticalCenter: parent.verticalCenter }
                            TextField {
                                id: xrceDirField; width: parent.width - 64 - 32 - 56 - 18; height: 26
                                text: "~/Micro-XRCE-DDS-Agent"
                                placeholderText: "~/Micro-XRCE-DDS-Agent"
                                background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 9; font.family: "Consolas"; leftPadding: 6
                            }
                        }

                        // Live command preview (read-only, selectable for copy-paste)
                        Rectangle {
                            width: parent.width; height: xrceCmdEdit.implicitHeight + 10
                            radius: 4; color: "#111827"; border.color: "#374151"; border.width: 1
                            TextEdit {
                                id: xrceCmdEdit
                                anchors { fill: parent; margins: 5 }
                                text: "cd " + xrceDirField.text + "\nMicroXRCEAgent udp4 -p " + xrcePortField.text
                                readOnly: false; selectByMouse: true
                                color: "#86efac"; font.pixelSize: 9; font.family: "Consolas"
                                wrapMode: TextEdit.Wrap
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 30; radius: 5
                                color: xrceRunM.containsMouse ? "#166534" : "#14532d"; border.color: "#22c55e"; border.width: 1
                                Text { anchors.centerIn: parent; text: "▶  Run Agent in Terminal"; color: "#86efac"; font.pixelSize: 9; font.weight: Font.Bold }
                                MouseArea {
                                    id: xrceRunM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: {
                                        if (typeof ros2 === "undefined" || !ros2) return
                                        var cmd = root.shellCommandFromText(xrceCmdEdit.text)
                                        if (!ros2.launchCommandInTerminal("MicroXRCE-DDS Agent", cmd))
                                            ros2.ros2LogMessage("WARN",
                                                "[ROS2] No terminal found. Run manually:\n" + cmd)
                                    }
                                }
                            }
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 30; radius: 5
                                color: xrceCopyM.containsMouse ? "#1e3a5f" : "#1e2535"; border.color: "#3b82f6"; border.width: 1
                                Text { anchors.centerIn: parent; text: "⎘  Copy command"; color: "#93c5fd"; font.pixelSize: 9; font.weight: Font.Bold }
                                MouseArea {
                                    id: xrceCopyM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: { xrceCmdEdit.selectAll(); xrceCmdEdit.copy(); xrceCmdEdit.deselect() }
                                }
                            }
                        }

                        Rectangle { width: parent.width; height: 1; color: "#1e2535" }

                        // ─── Step 2: PX4 SITL ──────────────────────────────────
                        Rectangle {
                            width: parent.width; height: 22; radius: 4
                            color: "#1a1500"; border.color: "#f59e0b"; border.width: 1
                            Text {
                                anchors { fill: parent; leftMargin: 8 }
                                text: "Step 2  —  Start PX4 SITL (own terminal)"
                                color: "#fcd34d"; font.pixelSize: 9; font.weight: Font.Bold
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "NS:"; color: "#64748b"; font.pixelSize: 9; width: 24; anchors.verticalCenter: parent.verticalCenter }
                            TextField {
                                id: launchNsField; width: 80; height: 26
                                text: (typeof ros2 !== "undefined" && ros2) ? ros2.getSitlNamespace() : "uav_1"
                                background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 6
                                onEditingFinished: { if (typeof ros2 !== "undefined" && ros2) ros2.setSitlNamespace(text) }
                            }
                            Text { text: "Make target:"; color: "#64748b"; font.pixelSize: 9; anchors.verticalCenter: parent.verticalCenter }
                        }
                        TextField {
                            id: makeTargetField; width: parent.width; height: 26
                            text: "gz_x500_gimbal_baylands"
                            placeholderText: "gz_x500  /  gz_x500_gimbal  /  gz_x500_gimbal_baylands"
                            background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#3b82f6"; border.width: 2 }
                            color: "#93c5fd"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 6
                            ToolTip.visible: hovered; ToolTip.delay: 500
                            ToolTip.text: "PX4 make target used as:  make px4_sitl <this>\n"
                                        + "Examples:\n  gz_x500\n  gz_x500_gimbal\n  gz_x500_gimbal_baylands"
                        }

                        // Live command preview
                        Rectangle {
                            width: parent.width; height: px4CmdEdit.implicitHeight + 10
                            radius: 4; color: "#111827"; border.color: "#374151"; border.width: 1
                            TextEdit {
                                id: px4CmdEdit
                                anchors { fill: parent; margins: 5 }
                                text: {
                                    var dir = (typeof ros2 !== "undefined" && ros2 && ros2.getSitlPx4Dir())
                                              ? ros2.getSitlPx4Dir() : "~/PX4-Autopilot"
                                    if (!dir || dir === "") dir = "~/PX4-Autopilot"
                                    return "cd " + dir + "\n"
                                         + "export PX4_UXRCE_DDS_NS=" + launchNsField.text + "\n"
                                         + "make px4_sitl " + makeTargetField.text
                                }
                                readOnly: false; selectByMouse: true
                                color: "#86efac"; font.pixelSize: 9; font.family: "Consolas"
                                wrapMode: TextEdit.Wrap
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 30; radius: 5
                                color: px4RunM.containsMouse ? "#166534" : "#14532d"; border.color: "#22c55e"; border.width: 1
                                Text { anchors.centerIn: parent; text: "▶  Run PX4 SITL in Terminal"; color: "#86efac"; font.pixelSize: 9; font.weight: Font.Bold }
                                MouseArea {
                                    id: px4RunM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: {
                                        if (typeof ros2 === "undefined" || !ros2) return
                                        var cmd = root.shellCommandFromText(px4CmdEdit.text)
                                        if (!ros2.launchCommandInTerminal("PX4 SITL", cmd))
                                            ros2.ros2LogMessage("WARN",
                                                "[ROS2] No terminal found. Run manually:\n" + cmd)
                                    }
                                }
                            }
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 30; radius: 5
                                color: px4CopyM.containsMouse ? "#1e3a5f" : "#1e2535"; border.color: "#3b82f6"; border.width: 1
                                Text { anchors.centerIn: parent; text: "⎘  Copy command"; color: "#93c5fd"; font.pixelSize: 9; font.weight: Font.Bold }
                                MouseArea {
                                    id: px4CopyM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: { px4CmdEdit.selectAll(); px4CmdEdit.copy(); px4CmdEdit.deselect() }
                                }
                            }
                        }

                        Rectangle { width: parent.width; height: 1; color: "#1e2535" }

                        // ─── Step 3: ROS2 Workspace (px4_ros_com listener) ──────
                        Rectangle {
                            width: parent.width; height: 22; radius: 4
                            color: "#0f1e35"; border.color: "#3b82f6"; border.width: 1
                            Text {
                                anchors { fill: parent; leftMargin: 8 }
                                text: "Step 3  —  Source & launch ROS2 workspace (optional, own terminal)"
                                color: "#93c5fd"; font.pixelSize: 9; font.weight: Font.Bold
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Workspace dir:"; color: "#64748b"; font.pixelSize: 9; width: 90; anchors.verticalCenter: parent.verticalCenter }
                            TextField {
                                id: ros2WsDirField; width: parent.width - 90 - 6; height: 26
                                text: "~/ws_sensor_combined"
                                placeholderText: "~/ws_sensor_combined"
                                background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 9; font.family: "Consolas"; leftPadding: 6
                            }
                        }
                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Launch file:"; color: "#64748b"; font.pixelSize: 9; width: 90; anchors.verticalCenter: parent.verticalCenter }
                            TextField {
                                id: ros2LaunchFileField; width: parent.width - 90 - 6; height: 26
                                text: "px4_ros_com sensor_combined_listener.launch.py"
                                placeholderText: "px4_ros_com sensor_combined_listener.launch.py"
                                background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 9; font.family: "Consolas"; leftPadding: 6
                            }
                        }

                        Rectangle {
                            width: parent.width; height: 22; radius: 4
                            color: "#101827"; border.color: "#64748b"; border.width: 1
                            Text {
                                anchors { fill: parent; leftMargin: 8 }
                                text: "Build ROS 2 Workspace (px4_msgs + px4_ros_com)"
                                color: "#cbd5e1"; font.pixelSize: 9; font.weight: Font.Bold
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        Rectangle {
                            width: parent.width; height: ros2BuildCmdEdit.implicitHeight + 10
                            radius: 4; color: "#111827"; border.color: "#374151"; border.width: 1
                            TextEdit {
                                id: ros2BuildCmdEdit
                                anchors { fill: parent; margins: 5 }
                                text: {
                                    var setupSrc = setupSourcesEdit && setupSourcesEdit.text.trim() !== ""
                                                   ? setupSourcesEdit.text.split("\n")[0].trim()
                                                   : "/opt/ros/humble/setup.bash"
                                    return "mkdir -p " + ros2WsDirField.text + "/src\n"
                                         + "cd " + ros2WsDirField.text + "/src\n"
                                         + "if [ ! -d px4_msgs ]; then git clone https://github.com/PX4/px4_msgs.git; fi\n"
                                         + "if [ ! -d px4_ros_com ]; then git clone https://github.com/PX4/px4_ros_com.git; fi\n"
                                         + "cd " + ros2WsDirField.text + "\n"
                                         + "source " + setupSrc + "\n"
                                         + "colcon build"
                                }
                                readOnly: false; selectByMouse: true
                                color: "#cbd5e1"; font.pixelSize: 9; font.family: "Consolas"
                                wrapMode: TextEdit.Wrap
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 30; radius: 5
                                color: ros2BuildRunM.containsMouse ? "#334155" : "#1f2937"; border.color: "#64748b"; border.width: 1
                                Text { anchors.centerIn: parent; text: "▶  Build ROS2 workspace"; color: "#cbd5e1"; font.pixelSize: 9; font.weight: Font.Bold }
                                MouseArea {
                                    id: ros2BuildRunM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: {
                                        if (typeof ros2 === "undefined" || !ros2) return
                                        var cmd = root.shellCommandFromText(ros2BuildCmdEdit.text)
                                        if (!ros2.launchCommandInTerminal("Build ROS2 Workspace", cmd))
                                            ros2.ros2LogMessage("WARN",
                                                "[ROS2] No terminal found. Run manually:\n" + cmd)
                                    }
                                }
                            }
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 30; radius: 5
                                color: ros2BuildCopyM.containsMouse ? "#1e3a5f" : "#1e2535"; border.color: "#3b82f6"; border.width: 1
                                Text { anchors.centerIn: parent; text: "⎘  Copy build command"; color: "#93c5fd"; font.pixelSize: 9; font.weight: Font.Bold }
                                MouseArea {
                                    id: ros2BuildCopyM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: { ros2BuildCmdEdit.selectAll(); ros2BuildCmdEdit.copy(); ros2BuildCmdEdit.deselect() }
                                }
                            }
                        }

                        // Live command preview for Step 3
                        Rectangle {
                            width: parent.width; height: ros2WsCmdEdit.implicitHeight + 10
                            radius: 4; color: "#111827"; border.color: "#374151"; border.width: 1
                            TextEdit {
                                id: ros2WsCmdEdit
                                anchors { fill: parent; margins: 5 }
                                text: {
                                    var setupSrc = setupSourcesEdit && setupSourcesEdit.text.trim() !== ""
                                                   ? setupSourcesEdit.text.split("\n")[0].trim()
                                                   : "/opt/ros/humble/setup.bash"
                                    return "cd " + ros2WsDirField.text + "\n"
                                         + "source " + setupSrc + "\n"
                                         + "source install/local_setup.bash\n"
                                         + "ros2 launch " + ros2LaunchFileField.text
                                }
                                readOnly: false; selectByMouse: true
                                color: "#93c5fd"; font.pixelSize: 9; font.family: "Consolas"
                                wrapMode: TextEdit.Wrap
                            }
                        }

                        Row {
                            width: parent.width; spacing: 6
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 30; radius: 5
                                color: ros2WsRunM.containsMouse ? "#1e40af" : "#1e3a8a"; border.color: "#3b82f6"; border.width: 1
                                Text { anchors.centerIn: parent; text: "▶  Launch ROS2 node"; color: "#93c5fd"; font.pixelSize: 9; font.weight: Font.Bold }
                                MouseArea {
                                    id: ros2WsRunM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: {
                                        if (typeof ros2 === "undefined" || !ros2) return
                                        var cmd = root.shellCommandFromText(ros2WsCmdEdit.text)
                                        if (!ros2.launchCommandInTerminal("ROS2 Workspace", cmd))
                                            ros2.ros2LogMessage("WARN",
                                                "[ROS2] No terminal found. Run manually:\n" + cmd)
                                    }
                                }
                            }
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 30; radius: 5
                                color: ros2WsCopyM.containsMouse ? "#1e3a5f" : "#1e2535"; border.color: "#3b82f6"; border.width: 1
                                Text { anchors.centerIn: parent; text: "⎘  Copy command"; color: "#93c5fd"; font.pixelSize: 9; font.weight: Font.Bold }
                                MouseArea {
                                    id: ros2WsCopyM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: { ros2WsCmdEdit.selectAll(); ros2WsCmdEdit.copy(); ros2WsCmdEdit.deselect() }
                                }
                            }
                        }

                        Rectangle { width: parent.width; height: 1; color: "#1e2535" }

                        // ─── Step 4: Connect via TCP header ────────────────────
                        Rectangle {
                            width: parent.width; height: step4Col.implicitHeight + 14
                            radius: 6; color: "#0f2d1a"; border.color: "#22c55e"; border.width: 1
                            Column {
                                id: step4Col
                                anchors { fill: parent; margins: 8 }
                                spacing: 4
                                Text {
                                    text: "Step 4  —  Connect from GCS header (after SITL ready)"
                                    color: "#22c55e"; font.pixelSize: 9; font.weight: Font.Bold
                                }
                                Text {
                                    width: parent.width
                                    text: "1. Wait for PX4 console:  INFO [commander] Ready for takeoff!\n"
                                        + "2. PX4 SITL MAVLink: select UDP/listen → 0.0.0.0 : 14550 → click  + ADD\n"
                                        + "   ArduCopter raw SITL only: TCP → 127.0.0.1 : 5762\n"
                                        + "3. Green badge appears → drone connected"
                                    color: "#86efac"; font.pixelSize: 8; font.family: "Consolas"
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                    }
                }
                Item { width: 1; height: 8 }
            }
        }

        // ══════════════════════════════════════════════════════════
        // TAB 1 — TOPICS
        // ══════════════════════════════════════════════════════════
        ScrollView {
            clip: true; contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                width: parent.width
                padding: 12; spacing: 10

                // ── Topic Browser ───────────────────────────────────
                Text { text: "TOPIC BROWSER"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    width: parent.width - 24; height: topicBrowserCol.implicitHeight + 20; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: topicBrowserCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        spacing: 8
                        property var discoveredTopics: []

                        TextField {
                            id: topicFilterField; width: parent.width; height: 26
                            placeholderText: "Filter topics (e.g. /fmu/out)"
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            color: "#e2e8f0"; font.pixelSize: 9; font.family: "Consolas"; leftPadding: 6
                        }

                        Rectangle {
                            width: parent.width; height: 28; radius: 5
                            color: discoverM.containsMouse ? "#1e40af" : "#1e3a8a"; border.color: "#3b82f6"; border.width: 1
                            Text { anchors.centerIn: parent; text: "Discover Topics"; color: "#93c5fd"; font.pixelSize: 9; font.weight: Font.Bold }
                            MouseArea { id: discoverM; anchors.fill: parent; hoverEnabled: true
                                onClicked: {
                                    if (typeof ros2 === "undefined" || !ros2 || !root.selectedDroneId) return
                                    topicBrowserCol.discoveredTopics = ros2.discoverTopics ? ros2.discoverTopics(root.selectedDroneId) : ros2.getBridgeTopics(root.selectedDroneId)
                                }
                            }
                        }

                        Rectangle {
                            width: parent.width; height: Math.min(topicRepeater.count * 22 + 8, 240); radius: 5
                            color: "#0d1117"; border.color: "#2d3748"; border.width: 1
                            visible: topicBrowserCol.discoveredTopics.length > 0
                            ScrollView { anchors.fill: parent; clip: true; contentWidth: availableWidth; ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                                Column { width: parent.width; spacing: 1; topPadding: 4; bottomPadding: 4
                                    Repeater {
                                        id: topicRepeater
                                        model: topicBrowserCol.discoveredTopics.filter(function(t){ var f=topicFilterField.text.trim(); return f===""||t.indexOf(f)>=0 })
                                        delegate: Rectangle {
                                            width: parent.width; height: 22
                                            color: topicItemM.containsMouse ? "#1e2535" : "transparent"
                                            Row {
                                                anchors { fill: parent; leftMargin: 6 }
                                                spacing: 4
                                                Rectangle { width:5;height:5;radius:2.5;anchors.verticalCenter:parent.verticalCenter; color:modelData.includes("/out/")?"#22c55e":"#3b82f6" }
                                                Text { text:modelData; color:"#94a3b8";font.pixelSize:8;font.family:"Consolas";anchors.verticalCenter:parent.verticalCenter;elide:Text.ElideMiddle;width:parent.width-50 }
                                            }
                                            MouseArea { id:topicItemM;anchors.fill:parent;hoverEnabled:true
                                                onClicked:{ if(typeof ros2!=="undefined"&&ros2&&ros2.subscribeToTopic) ros2.subscribeToTopic(modelData,root.selectedDroneId) }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        Text { visible: topicBrowserCol.discoveredTopics.length === 0; text: "Click 'Discover Topics' to list topics"; color: "#374151"; font.pixelSize: 9 }
                    }
                }

                // ── uORB Active Topics ──────────────────────────────
                Text { text: "uORB ACTIVE TOPICS"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    width: parent.width - 24; height: topicsCol.implicitHeight + 16; radius: 8
                    color: "#0d1117"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: topicsCol
                        anchors { fill: parent; margins: 8 }
                        spacing: 3
                        property var topics: root.selectedDroneId !== "" && typeof ros2 !== "undefined" && ros2 ? ros2.getBridgeTopics(root.selectedDroneId) : []
                        Repeater {
                            model: topicsCol.topics
                            delegate: Row { width: topicsCol.width; spacing: 4
                                Rectangle { width:6;height:6;radius:3;anchors.verticalCenter:parent.verticalCenter;color:modelData.includes("/out/")?"#22c55e":"#2563eb" }
                                Text { text:modelData;color:"#64748b";font.pixelSize:8;font.family:"Consolas";anchors.verticalCenter:parent.verticalCenter;elide:Text.ElideMiddle;width:topicsCol.width-40 }
                            }
                        }
                        Text { visible: topicsCol.topics.length === 0; text: "No drone selected"; color: "#374151"; font.pixelSize: 10; anchors.horizontalCenter: parent.horizontalCenter }
                    }
                }

                // ── Live uORB Snapshot ──────────────────────────────
                Text { text: "LIVE uORB SNAPSHOT"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    width: parent.width - 24; height: snapCol.implicitHeight + 16; radius: 8
                    color: "#0d1117"; border.color: "#2d3748"; border.width: 1
                    property var snap: ({})
                    Timer { interval: 200; running: true; repeat: true
                        onTriggered: { if (typeof ros2 === "undefined" || !ros2 || root.selectedDroneId === "") return; parent.snap = ros2.bridgeSnapshot(root.selectedDroneId) }
                    }
                    Column {
                        id: snapCol
                        anchors { fill: parent; margins: 8 }
                        spacing: 2
                        property var snap: parent.snap
                        Repeater {
                            model: [
                                { key:"armed",       label:"Armed",     fmt:function(v){return v?"ARMED":"DISARMED"},   color:function(v){return v?"#22c55e":"#ef4444"} },
                                { key:"flight_mode", label:"Nav State", fmt:function(v){return v!==undefined?v.toString():"—"},  color:function(v){return"#8be9fd"} },
                                { key:"lat",         label:"Lat",       fmt:function(v){return v?v.toFixed(6):"—"},     color:function(v){return"#8be9fd"} },
                                { key:"lon",         label:"Lon",       fmt:function(v){return v?v.toFixed(6):"—"},     color:function(v){return"#8be9fd"} },
                                { key:"alt_rel",     label:"Alt(rel)",  fmt:function(v){return v!==undefined?v.toFixed(2)+"m":"—"},  color:function(v){return"#8be9fd"} },
                                { key:"roll",        label:"Roll",      fmt:function(v){return v!==undefined?v.toFixed(1)+"°":"—"},  color:function(v){return"#8be9fd"} },
                                { key:"pitch",       label:"Pitch",     fmt:function(v){return v!==undefined?v.toFixed(1)+"°":"—"},  color:function(v){return"#8be9fd"} },
                                { key:"yaw",         label:"Yaw",       fmt:function(v){return v!==undefined?v.toFixed(1)+"°":"—"},  color:function(v){return"#8be9fd"} },
                                { key:"battery_pct", label:"Battery",   fmt:function(v){return v!==undefined&&v>=0?v.toFixed(0)+"%":"—"}, color:function(v){return v>20?"#22c55e":"#ef4444"} },
                                { key:"battery_v",   label:"Voltage",   fmt:function(v){return v?v.toFixed(2)+"V":"—"}, color:function(v){return"#8be9fd"} },
                                { key:"gps_fix",     label:"GPS Fix",   fmt:function(v){return["NoFix","NoFix","2D","3D","RTK"][Math.min(v||0,4)]}, color:function(v){return v>=3?"#22c55e":"#f59e0b"} },
                                { key:"satellites",  label:"Sats",      fmt:function(v){return v!==undefined?v.toString():"—"}, color:function(v){return"#8be9fd"} },
                            ]
                            delegate: Row { width:snapCol.width;height:17;spacing:4
                                Text{text:modelData.label+":";color:"#475569";font.pixelSize:9;width:68}
                                Text{
                                    text:{var s=snapCol.snap;var v=(s&&s[modelData.key]!==undefined)?s[modelData.key]:undefined;return v!==undefined?modelData.fmt(v):"—"}
                                    color:{var s=snapCol.snap;var v=(s&&s[modelData.key]!==undefined)?s[modelData.key]:undefined;return v!==undefined?modelData.color(v):"#374151"}
                                    font.pixelSize:9;font.family:"Consolas";font.weight:Font.Bold
                                }
                            }
                        }
                        Text { visible: Object.keys(snapCol.snap).length === 0; text: "Bridge not active"; color: "#374151"; font.pixelSize: 10; anchors.horizontalCenter: parent.horizontalCenter }
                    }
                }
                Item { width: 1; height: 8 }
            }
        }

        // ══════════════════════════════════════════════════════════
        // TAB 2 — BAG
        // ══════════════════════════════════════════════════════════
        ScrollView {
            clip: true; contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                width: parent.width
                padding: 12; spacing: 10

                Text { text: "BAG RECORDER"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    width: parent.width - 24; height: bagCol.implicitHeight + 20; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: bagCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        spacing: 8

                        property bool _recording: (typeof ros2 !== "undefined" && ros2) ? ros2.isBagRecording() : false
                        property var  _status:    (typeof ros2 !== "undefined" && ros2) ? ros2.getBagRecordingStatus() : ({})
                        Timer { interval: 500; running: true; repeat: true
                            onTriggered: {
                                bagCol._recording = (typeof ros2 !== "undefined" && ros2) ? ros2.isBagRecording() : false
                                bagCol._status    = (typeof ros2 !== "undefined" && ros2) ? ros2.getBagRecordingStatus() : ({})
                            }
                        }

                        // Preset selector
                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Preset:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 46 }
                            ComboBox {
                                id: bagPresetCombo; width: parent.width - 52; height: 26
                                model: ["minimal_mission", "full_px4_out", "camera_gimbal", "swarm_multi_vehicle", "custom"]
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                contentItem: Text { text: bagPresetCombo.displayText; color: "#e2e8f0"; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter; leftPadding: 6 }
                            }
                        }

                        // Custom topics (only for "custom" preset)
                        Column {
                            width: parent.width; spacing: 2
                            visible: bagPresetCombo.currentText === "custom"
                            Text { text: "Topics (one per line):"; color: "#64748b"; font.pixelSize: 9 }
                            TextArea {
                                id: bagCustomTopics; width: parent.width; height: 80
                                placeholderText: "/fmu/out/vehicle_odometry\n/fmu/out/vehicle_status"
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 9; font.family: "Consolas"; leftPadding: 6; topPadding: 6; wrapMode: TextArea.NoWrap
                            }
                        }

                        // Output dir
                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Out:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 28 }
                            TextField {
                                id: bagOutDir; width: parent.width - 34; height: 26
                                placeholderText: "./bags  (empty = default)"
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 9; font.family: "Consolas"; leftPadding: 6
                            }
                        }

                        // Recording indicator + Start/Stop
                        Rectangle {
                            width: parent.width; height: 32; radius: 6
                            color: bagTogM.containsMouse ? (bagCol._recording ? "#7f1d1d" : "#166534") : (bagCol._recording ? "#450a0a" : "#14532d")
                            border.color: bagCol._recording ? "#ef4444" : "#22c55e"; border.width: 1
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Row { anchors.centerIn: parent; spacing: 6
                                // blinking dot when recording
                                Rectangle {
                                    width: 10; height: 10; radius: 5; anchors.verticalCenter: parent.verticalCenter
                                    color: "#ef4444"; visible: bagCol._recording
                                    SequentialAnimation on opacity { running: bagCol._recording; loops: Animation.Infinite
                                        NumberAnimation { to: 0.2; duration: 500 }
                                        NumberAnimation { to: 1.0; duration: 500 }
                                    }
                                }
                                Text { text: bagCol._recording ? "Stop Recording" : "⏺ Start Recording"; color: bagCol._recording ? "#fca5a5" : "#86efac"; font.pixelSize: 10; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                            }
                            MouseArea { id: bagTogM; anchors.fill: parent; hoverEnabled: true
                                onClicked: {
                                    if (typeof ros2 === "undefined" || !ros2) return
                                    if (bagCol._recording) {
                                        ros2.stopBagRecord()
                                    } else {
                                        var topics = []
                                        if (bagPresetCombo.currentText === "custom") {
                                            topics = bagCustomTopics.text.split("\n").filter(function(t){ return t.trim() !== "" })
                                        }
                                        ros2.startBagRecord(topics, bagOutDir.text.trim(), bagPresetCombo.currentText === "custom" ? "" : bagPresetCombo.currentText)
                                    }
                                }
                            }
                        }

                        // Recording status
                        Column {
                            width: parent.width; spacing: 4; visible: bagCol._recording
                            Repeater {
                                model: [{key:"duration_sec",label:"Duration",fmt:function(v){return v?v.toFixed(1)+"s":"0.0s"}},
                                        {key:"size_mb",label:"Size",fmt:function(v){return v?v.toFixed(2)+" MB":"0.00 MB"}},
                                        {key:"bag_path",label:"Path",fmt:function(v){return v||"./bags/"}}]
                                delegate: Row { width: parent.width; spacing: 4
                                    Text { text: modelData.label+":"; color: "#64748b"; font.pixelSize: 9; width: 60 }
                                    Text { text: modelData.fmt(bagCol._status[modelData.key]); color: "#e2e8f0"; font.pixelSize: modelData.key==="bag_path"?8:9; elide: modelData.key==="bag_path"?Text.ElideMiddle:Text.ElideNone; width: parent.width - 64 }
                                }
                            }
                        }

                        Text { text: "Bags saved to: <project_root>/bags/"; color: "#374151"; font.pixelSize: 8 }
                    }
                }
                Item { width: 1; height: 8 }
            }
        }

        // ══════════════════════════════════════════════════════════
        // TAB 3 — VIDEO
        // ══════════════════════════════════════════════════════════
        ScrollView {
            clip: true; contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                width: parent.width
                padding: 12; spacing: 10

                Text { text: "VIDEO STREAM"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    width: parent.width - 24; height: videoStreamCol.implicitHeight + 20; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: videoStreamCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        spacing: 8

                        // Select the drone in videoStream context when this tab opens,
                        // because the drone combo may already have a value from another panel.
                        Component.onCompleted: {
                            if (root.selectedDroneId !== "" &&
                                typeof videoStream !== "undefined" && videoStream)
                                videoStream.selectDrone(root.selectedDroneId)
                        }

                        property string _vsStatus: {
                            if (typeof videoStream === "undefined" || !videoStream || !root.selectedDroneId) return "unconfigured"
                            var s = videoStream.getVideoStatus(root.selectedDroneId)
                            return s ? (s.status || "unconfigured") : "unconfigured"
                        }
                        Timer { interval: 1000; running: true; repeat: true
                            onTriggered: {
                                if (typeof videoStream === "undefined" || !videoStream || !root.selectedDroneId) return
                                var s = videoStream.getVideoStatus(root.selectedDroneId)
                                videoStreamCol._vsStatus = s ? (s.status || "unconfigured") : "unconfigured"
                            }
                        }
                        function vsColor(s) {
                            if (s === "receiving") return "#22c55e"
                            if (s === "waiting")   return "#f59e0b"
                            if (s === "stalled")   return "#f97316"
                            if (s === "error")     return "#ef4444"
                            return "#475569"
                        }

                        // Status badge
                        Rectangle {
                            width: parent.width; height: 32; radius: 5
                            color: "#0d1117"; border.color: videoStreamCol.vsColor(videoStreamCol._vsStatus); border.width: 1
                            Row {
                                anchors { fill: parent; leftMargin: 10 }
                                spacing: 8
                                Rectangle {
                                    width: 10; height: 10; radius: 5; anchors.verticalCenter: parent.verticalCenter
                                    color: videoStreamCol.vsColor(videoStreamCol._vsStatus)
                                    SequentialAnimation on opacity { running: videoStreamCol._vsStatus === "receiving"; loops: Animation.Infinite
                                        NumberAnimation { to: 0.3; duration: 700 }
                                        NumberAnimation { to: 1.0; duration: 700 }
                                    }
                                }
                                Text {
                                    text: {
                                        var s = videoStreamCol._vsStatus
                                        if (s === "receiving") return "Stream receiving"
                                        if (s === "waiting")   return "Waiting for stream …"
                                        if (s === "stalled")   return "Stream stalled"
                                        if (s === "error")     return "Stream error"
                                        return "Not configured"
                                    }
                                    color: videoStreamCol.vsColor(videoStreamCol._vsStatus)
                                    font.pixelSize: 10; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }

                        // Drone selector
                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Drone:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 40 }
                            ComboBox {
                                id: vsDroneCombo; width: parent.width - 46; height: 26
                                model: (typeof swarm !== "undefined" && swarm) ? swarm.droneIds() : []
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                contentItem: Text { text: vsDroneCombo.displayText; color: "#e2e8f0"; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter; leftPadding: 6 }
                                onCurrentTextChanged: { if (currentText && typeof videoStream !== "undefined" && videoStream) videoStream.selectDrone(currentText) }
                            }
                        }

                        // ── Port + Host (primary config) ───────────────
                        Text { text: "STREAM PORT"; color: "#475569"; font.pixelSize: 8; font.weight: Font.Bold; font.letterSpacing: 1 }

                        // Port input — the main thing the user needs
                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "Port:"; color: "#e2e8f0"; font.pixelSize: 11; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter; width: 36 }
                            TextField {
                                id: vsPortField; width: 80; height: 32
                                text: "5600"
                                placeholderText: "5600"
                                inputMethodHints: Qt.ImhDigitsOnly
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#3b82f6"; border.width: 2 }
                                color: "#93c5fd"; font.pixelSize: 13; font.family: "Consolas"; font.weight: Font.Bold; leftPadding: 8
                                onTextChanged: {
                                    var p = parseInt(text)
                                    if (!isNaN(p) && p > 0)
                                        videoUrlField.text = "udp://0.0.0.0:" + p
                                }
                            }
                            Text { text: "Host:"; color: "#94a3b8"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 36 }
                            TextField {
                                id: vsHostField; width: parent.width - 80 - 36 - 36 - 18; height: 32
                                text: "0.0.0.0"
                                placeholderText: "0.0.0.0"
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 6
                                onTextChanged: {
                                    var p = parseInt(vsPortField.text)
                                    if (!isNaN(p) && p > 0)
                                        videoUrlField.text = "udp://" + (text || "0.0.0.0") + ":" + p
                                }
                            }
                        }

                        // PX4 Quick-Port Buttons
                        Text { text: "PX4 Gazebo Defaults — klicken zum Übernehmen:"; color: "#475569"; font.pixelSize: 8 }
                        Row {
                            width: parent.width; spacing: 6
                            Repeater {
                                model: [
                                    { label: "px4_1", port: 5600, color: "#166534", border: "#22c55e", text: "#86efac" },
                                    { label: "px4_2", port: 5601, color: "#1e3a8a", border: "#3b82f6", text: "#93c5fd" },
                                    { label: "px4_3", port: 5602, color: "#78350f", border: "#f59e0b", text: "#fcd34d" },
                                    { label: "px4_4", port: 5603, color: "#312e81", border: "#8b5cf6", text: "#c4b5fd" },
                                    { label: "px4_5", port: 5604, color: "#1e3a4a", border: "#67e8f9", text: "#a5f3fc" },
                                ]
                                delegate: Rectangle {
                                    width: (parent.width - 24) / 5; height: 38; radius: 5
                                    color: px4PortM.containsMouse ? Qt.lighter(modelData.color, 1.3) : modelData.color
                                    border.color: modelData.border; border.width: 1
                                    Column {
                                        anchors.centerIn: parent; spacing: 1
                                        Text { text: modelData.label; color: modelData.text; font.pixelSize: 8; font.weight: Font.Bold; anchors.horizontalCenter: parent.horizontalCenter }
                                        Text { text: ":" + modelData.port; color: modelData.border; font.pixelSize: 11; font.weight: Font.Bold; font.family: "Consolas"; anchors.horizontalCenter: parent.horizontalCenter }
                                    }
                                    MouseArea {
                                        id: px4PortM; anchors.fill: parent; hoverEnabled: true
                                        onClicked: {
                                            vsPortField.text = modelData.port
                                            vsHostField.text = "0.0.0.0"
                                            videoUrlField.text = "udp://0.0.0.0:" + modelData.port
                                        }
                                    }
                                }
                            }
                        }

                        // Full URL (auto-built, also editable manually)
                        Text { text: "FULL URL (auto)"; color: "#475569"; font.pixelSize: 8; font.weight: Font.Bold; font.letterSpacing: 1 }
                        Row {
                            width: parent.width; spacing: 6
                            Text { text: "URL:"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; width: 28 }
                            TextField {
                                id: videoUrlField; width: parent.width - 34; height: 26
                                text: {
                                    if (typeof videoStream === "undefined" || !videoStream || !root.selectedDroneId) return "udp://0.0.0.0:5600"
                                    var s = videoStream.getVideoStatus(root.selectedDroneId)
                                    return s && s.url ? s.url : "udp://0.0.0.0:5600"
                                }
                                placeholderText: "udp://0.0.0.0:5600"
                                background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                color: "#94a3b8"; font.pixelSize: 9; font.family: "Consolas"; leftPadding: 6
                            }
                        }

                        // Protocol hint
                        Text {
                            width: parent.width
                            text: {
                                var u = videoUrlField.text
                                if (u.startsWith("udp://"))  return "UDP RTP/H.264 (PX4 Gazebo default)"
                                if (u.startsWith("rtsp://")) return "RTSP stream"
                                if (u.startsWith("http://")) return "MJPEG over HTTP"
                                return "Unknown protocol"
                            }
                            color: "#475569"; font.pixelSize: 8; font.family: "Consolas"
                        }

                        // Start / Stop
                        Row {
                            width: parent.width; spacing: 6
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 34; radius: 5
                                color: vsStartM.containsMouse ? "#166534" : "#14532d"; border.color: "#22c55e"; border.width: 1
                                Text { anchors.centerIn: parent; text: "Start Map Stream"; color: "#86efac"; font.pixelSize: 10; font.weight: Font.Bold }
                                MouseArea { id: vsStartM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: {
                                        if (typeof videoStream === "undefined" || !videoStream || !root.selectedDroneId) return
                                        videoStream.startStream(videoUrlField.text, root.selectedDroneId, "map")
                                    }
                                }
                            }
                            Rectangle {
                                width: (parent.width - 6) / 2; height: 34; radius: 5
                                color: vsStopM.containsMouse ? "#7f1d1d" : "#450a0a"; border.color: "#ef4444"; border.width: 1
                                Text { anchors.centerIn: parent; text: "■ Stop"; color: "#fca5a5"; font.pixelSize: 10; font.weight: Font.Bold }
                                MouseArea { id: vsStopM; anchors.fill: parent; hoverEnabled: true
                                    onClicked: { if (typeof videoStream !== "undefined" && videoStream && root.selectedDroneId) videoStream.stopStream(root.selectedDroneId) }
                                }
                            }
                        }
                    }
                }
                Item { width: 1; height: 8 }
            }
        }

        // ══════════════════════════════════════════════════════════
        // TAB 4 — DEBUG
        // ══════════════════════════════════════════════════════════
        ScrollView {
            clip: true; contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                width: parent.width
                padding: 12; spacing: 10

                // ── Vehicle Commands ────────────────────────────────
                Text { text: "VEHICLE COMMANDS (uXRCE-DDS)"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    width: parent.width - 24; height: cmdCol.implicitHeight + 20; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: cmdCol
                        anchors { fill: parent; margins: 10 }
                        spacing: 6

                        // Warning shown when no bridge is active or no drone selected
                        Rectangle {
                            width: parent.width; height: bridgeWarnTxt.implicitHeight + 12
                            radius: 5; color: "#1a1500"; border.color: "#f59e0b"; border.width: 1
                            visible: !root._anyBridgeActive || root.selectedDroneId === ""
                            Text {
                                id: bridgeWarnTxt
                                anchors { fill: parent; margins: 6 }
                                text: root.selectedDroneId === ""
                                      ? "⚠  No drone selected — select a drone in the Connection tab first"
                                      : "⚠  PX4 bridge not active — start the ROS2/PX4 stack from the Command Launcher first"
                                color: "#fcd34d"; font.pixelSize: 9; wrapMode: Text.WordWrap
                            }
                        }

                        Repeater {
                            model: [{label:"ARM",color:"#22c55e",fn:"armBridge"},{label:"DISARM",color:"#ef4444",fn:"disarmBridge"},{label:"LAND",color:"#f59e0b",fn:"landBridge"},{label:"RTL",color:"#f97316",fn:"rtlBridge"}]
                            delegate: Rectangle {
                                width: parent.width - 20; height: 32; radius: 5
                                color: cMa.containsMouse ? Qt.rgba(Qt.color(modelData.color).r, Qt.color(modelData.color).g, Qt.color(modelData.color).b, 0.2) : "#1e2535"
                                border.color: cMa.containsMouse ? modelData.color : "#334155"; border.width: 1
                                Behavior on color { ColorAnimation { duration: 80 } }
                                Text { anchors.centerIn: parent; text: modelData.label; color: modelData.color; font.pixelSize: 11; font.weight: Font.Bold }
                                MouseArea { id: cMa; anchors.fill: parent; hoverEnabled: true
                                    onClicked: {
                                        if (typeof ros2 === "undefined" || !ros2 || root.selectedDroneId === "") return
                                        if      (modelData.fn === "armBridge")    ros2.armBridge(root.selectedDroneId)
                                        else if (modelData.fn === "disarmBridge") ros2.disarmBridge(root.selectedDroneId)
                                        else if (modelData.fn === "landBridge")   ros2.landBridge(root.selectedDroneId)
                                        else if (modelData.fn === "rtlBridge")    ros2.rtlBridge(root.selectedDroneId)
                                    }
                                }
                            }
                        }
                        Row { spacing: 4
                            Rectangle {
                                width: parent.parent.width - 84 - 20 - 8; height: 32; radius: 5
                                color: toMa.containsMouse ? "#1e3a5f" : "#1e2535"; border.color: toMa.containsMouse ? "#2563eb" : "#334155"; border.width: 1
                                Text { anchors.centerIn: parent; text: "TAKEOFF"; color: "#2563eb"; font.pixelSize: 10; font.weight: Font.Bold }
                                MouseArea { id: toMa; anchors.fill: parent; hoverEnabled: true; onClicked: { if (typeof ros2 !== "undefined" && ros2 && root.selectedDroneId !== "") ros2.takeoffBridge(root.selectedDroneId, parseFloat(toAlt.text) || 10) } }
                            }
                            TextField {
                                id: toAlt; width: 52; height: 32; text: "10"
                                color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 6
                                background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748" }
                            }
                            Text { text: "m"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }

                // ── Offboard Control ────────────────────────────────
                Text { text: "OFFBOARD (TrajectorySetpoint)"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    width: parent.width - 24; height: offboardCol.implicitHeight + 16; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: offboardCol
                        anchors { fill: parent; margins: 10 }
                        spacing: 6
                        Row {
                            id: offboardModeRow; spacing: 5; property int mode: 0
                            Rectangle { width:84;height:24;radius:5; color:offboardModeRow.mode===0?"#1e3a5f":"#1e2535"; border.color:offboardModeRow.mode===0?"#2563eb":"#334155";border.width:1
                                Text{anchors.centerIn:parent;text:"Position";color:offboardModeRow.mode===0?"#93c5fd":"#64748b";font.pixelSize:9}
                                MouseArea{anchors.fill:parent;onClicked:offboardModeRow.mode=0}
                            }
                            Rectangle { width:84;height:24;radius:5; color:offboardModeRow.mode===1?"#1e3a5f":"#1e2535"; border.color:offboardModeRow.mode===1?"#f97316":"#334155";border.width:1
                                Text{anchors.centerIn:parent;text:"Velocity";color:offboardModeRow.mode===1?"#fb923c":"#64748b";font.pixelSize:9}
                                MouseArea{anchors.fill:parent;onClicked:offboardModeRow.mode=1}
                            }
                        }
                        Row { width: parent.width; spacing: 4; visible: offboardModeRow.mode === 0
                            Column { width: (parent.width-8)/4; spacing: 1
                                Text { text: "N(m)"; color: "#64748b"; font.pixelSize: 8 }
                                TextField { id: northField; width: parent.width; height: 24; text: "0.0"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 4; background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748" } }
                            }
                            Column { width: (parent.width-8)/4; spacing: 1
                                Text { text: "E(m)"; color: "#64748b"; font.pixelSize: 8 }
                                TextField { id: eastField; width: parent.width; height: 24; text: "0.0"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 4; background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748" } }
                            }
                            Column { width: (parent.width-8)/4; spacing: 1
                                Text { text: "D(m)"; color: "#64748b"; font.pixelSize: 8 }
                                TextField { id: downField; width: parent.width; height: 24; text: "-5.0"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 4; background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748" } }
                            }
                            Column { width: (parent.width-8)/4; spacing: 1
                                Text { text: "Yaw(r)"; color: "#64748b"; font.pixelSize: 8 }
                                TextField { id: yawPosField; width: parent.width; height: 24; text: "0.0"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 4; background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748" } }
                            }
                        }
                        Row { width: parent.width; spacing: 4; visible: offboardModeRow.mode === 1
                            Column { width: (parent.width-8)/4; spacing: 1
                                Text { text: "vN"; color: "#64748b"; font.pixelSize: 8 }
                                TextField { id: vnField; width: parent.width; height: 24; text: "0.0"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 4; background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748" } }
                            }
                            Column { width: (parent.width-8)/4; spacing: 1
                                Text { text: "vE"; color: "#64748b"; font.pixelSize: 8 }
                                TextField { id: veField; width: parent.width; height: 24; text: "0.0"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 4; background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748" } }
                            }
                            Column { width: (parent.width-8)/4; spacing: 1
                                Text { text: "vD"; color: "#64748b"; font.pixelSize: 8 }
                                TextField { id: vdField; width: parent.width; height: 24; text: "0.0"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 4; background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748" } }
                            }
                            Column { width: (parent.width-8)/4; spacing: 1
                                Text { text: "YawR"; color: "#64748b"; font.pixelSize: 8 }
                                TextField { id: yawRateField; width: parent.width; height: 24; text: "0.0"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"; leftPadding: 4; background: Rectangle { color: "#1e2535"; radius: 4; border.color: "#2d3748" } }
                            }
                        }
                        Row { id: offboardActionsRow; width: parent.width; spacing: 5
                            readonly property real _w: (width - 10) / 4
                            Rectangle { width:offboardActionsRow._w*2;height:28;radius:5;color:activateM.containsMouse?"#c2410c":"#9a3412";border.color:"#f97316";border.width:1
                                Text{anchors.centerIn:parent;text:"OFFBOARD";color:"#fed7aa";font.pixelSize:9;font.weight:Font.Bold;elide:Text.ElideRight}
                                MouseArea{id:activateM;anchors.fill:parent;hoverEnabled:true;onClicked:{if(typeof ros2!=="undefined"&&ros2&&root.selectedDroneId!=="")ros2.activateOffboardMode(root.selectedDroneId)}}
                            }
                            Rectangle { width:offboardActionsRow._w;height:28;radius:5;color:sendM.containsMouse?"#1d4ed8":"#1e3a5f";border.color:"#2563eb";border.width:1
                                Text{anchors.centerIn:parent;text:"▶ SEND";color:"#93c5fd";font.pixelSize:9;font.weight:Font.Bold;elide:Text.ElideRight}
                                MouseArea{id:sendM;anchors.fill:parent;hoverEnabled:true
                                    onClicked:{
                                        if(typeof ros2==="undefined"||!ros2||root.selectedDroneId==="")return
                                        if(offboardModeRow.mode===0)
                                            ros2.setOffboardPosition(root.selectedDroneId,parseFloat(northField.text)||0,parseFloat(eastField.text)||0,parseFloat(downField.text)||-5,parseFloat(yawPosField.text)||0)
                                        else
                                            ros2.setOffboardVelocity(root.selectedDroneId,parseFloat(vnField.text)||0,parseFloat(veField.text)||0,parseFloat(vdField.text)||0,parseFloat(yawRateField.text)||0)
                                    }
                                }
                            }
                            Rectangle { width:offboardActionsRow._w;height:28;radius:5;color:stopOffM.containsMouse?"#7f1d1d":"#1e2535";border.color:"#ef4444";border.width:1
                                Text{anchors.centerIn:parent;text:"■ STOP";color:"#fca5a5";font.pixelSize:9;font.weight:Font.Bold;elide:Text.ElideRight}
                                MouseArea{id:stopOffM;anchors.fill:parent;hoverEnabled:true;onClicked:{if(typeof ros2!=="undefined"&&ros2&&root.selectedDroneId!=="")ros2.stopOffboard(root.selectedDroneId)}}
                            }
                        }
                    }
                }

                // ── Mission Management ──────────────────────────────
                Text { text: "MISSION MANAGEMENT"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    width: parent.width - 24; height: missionCol.implicitHeight + 20; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    Column {
                        id: missionCol
                        anchors { fill: parent; margins: 10 }
                        spacing: 8
                        property var missionStatus: ({})
                        Timer { interval: 500; running: true; repeat: true
                            onTriggered: { if (typeof ros2 === "undefined" || !ros2 || root.selectedDroneId === "") return; missionCol.missionStatus = ros2.getMissionStatus(root.selectedDroneId) }
                        }
                        Rectangle {
                            width: parent.width; height: 52; radius: 6
                            color: "#0d1117"; border.color: missionCol.missionStatus.active ? "#22c55e" : "#374151"; border.width: 1
                            Column {
                                anchors { fill: parent; margins: 8 }
                                spacing: 4
                                Row { spacing: 6
                                    Rectangle { width:8;height:8;radius:4;anchors.verticalCenter:parent.verticalCenter;color:(missionCol.missionStatus.active||false)?"#22c55e":"#6b7280"
                                        SequentialAnimation on opacity {
                                            running: missionCol.missionStatus.active || false
                                            loops: Animation.Infinite
                                            NumberAnimation { to: 0.3; duration: 800 }
                                            NumberAnimation { to: 1.0; duration: 800 }
                                        }
                                    }
                                    Text {
                                        text: missionCol.missionStatus.finished?"Mission Complete":missionCol.missionStatus.failure?"Mission Failed":missionCol.missionStatus.active?"Mission Active":"No Mission"
                                        color: missionCol.missionStatus.finished?"#22c55e":missionCol.missionStatus.failure?"#ef4444":missionCol.missionStatus.active?"#22c55e":"#6b7280"
                                        font.pixelSize: 10; font.weight: Font.Bold
                                    }
                                }
                                Rectangle {
                                    width: parent.width; height: 20; radius: 4
                                    color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    visible: missionCol.missionStatus.total_count > 0
                                    Rectangle {
                                        width: missionCol.missionStatus.total_count>0?(parent.width-2)*(missionCol.missionStatus.current_seq/missionCol.missionStatus.total_count):0
                                        height: parent.height-2; radius: 3; color: "#22c55e"
                                        anchors { left: parent.left; top: parent.top; margins: 1 }
                                        Behavior on width { NumberAnimation { duration: 200 } }
                                    }
                                    Text { anchors.centerIn: parent; text: "WP "+(missionCol.missionStatus.current_seq+1)+" / "+missionCol.missionStatus.total_count; color: "#e2e8f0"; font.pixelSize: 9; font.weight: Font.Bold }
                                }
                            }
                        }
                        Row { width: parent.width; spacing: 4
                            Rectangle{width:(parent.width-8)/3;height:28;radius:5;color:startMa.containsMouse?"#166534":"#14532d";border.color:"#22c55e";border.width:1
                                Text{anchors.centerIn:parent;text:"▶ START";color:"#86efac";font.pixelSize:9;font.weight:Font.Bold}
                                MouseArea{id:startMa;anchors.fill:parent;hoverEnabled:true;onClicked:{if(typeof ros2!=="undefined"&&ros2&&root.selectedDroneId!=="")ros2.startMission(root.selectedDroneId)}}
                            }
                            Rectangle{width:(parent.width-8)/3;height:28;radius:5;color:pauseMa.containsMouse?"#c2410c":"#9a3412";border.color:"#f97316";border.width:1
                                Text{anchors.centerIn:parent;text:"⏸ PAUSE";color:"#fed7aa";font.pixelSize:9;font.weight:Font.Bold}
                                MouseArea{id:pauseMa;anchors.fill:parent;hoverEnabled:true;onClicked:{if(typeof ros2!=="undefined"&&ros2&&root.selectedDroneId!=="")ros2.pauseMission(root.selectedDroneId)}}
                            }
                            Rectangle{width:(parent.width-8)/3;height:28;radius:5;color:clearMa.containsMouse?"#7f1d1d":"#450a0a";border.color:"#ef4444";border.width:1
                                Text{anchors.centerIn:parent;text:"✕ CLEAR";color:"#fca5a5";font.pixelSize:9;font.weight:Font.Bold}
                                MouseArea{id:clearMa;anchors.fill:parent;hoverEnabled:true;onClicked:{if(typeof ros2!=="undefined"&&ros2&&root.selectedDroneId!=="")ros2.clearMission(root.selectedDroneId)}}
                            }
                        }
                        Rectangle { width:parent.width;height:32;radius:5;color:uploadMa.containsMouse?"#1e3a5f":"#1e2535";border.color:"#2563eb";border.width:1
                            Text{anchors.centerIn:parent;text:"⬆ UPLOAD MISSION";color:"#93c5fd";font.pixelSize:10;font.weight:Font.Bold}
                            MouseArea{id:uploadMa;anchors.fill:parent;hoverEnabled:true;onClicked:missionDialog.open()}
                        }
                        Text { width: parent.width; text: "ARM + TAKEOFF before starting mission"; color: "#64748b"; font.pixelSize: 8; wrapMode: Text.WordWrap }
                    }
                }

                // ── Frame Conversion Debug ──────────────────────────
                Text { text: "FRAME CONVERSION (NED ↔ ENU)"; color: "#64748b"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1 }
                Rectangle {
                    width: parent.width - 24; height: frameCol.implicitHeight + 16; radius: 8
                    color: "#1a2035"; border.color: "#2d3748"; border.width: 1
                    property var frameData: ({})
                    Timer { interval: 200; running: true; repeat: true
                        onTriggered: { if (typeof ros2 === "undefined" || !ros2 || root.selectedDroneId === "") return; parent.frameData = ros2.getFrameData(root.selectedDroneId) }
                    }
                    Column {
                        id: frameCol
                        anchors { fill: parent; margins: 10 }
                        spacing: 8
                        Text { width: parent.width; text: "PX4: NED (North-East-Down)  ↔  ROS2: ENU (East-North-Up)  [E,N,U]=[E,N,−D]"; color: "#64748b"; font.pixelSize: 8; wrapMode: Text.WordWrap }
                        Row {
                            width: parent.width; spacing: 10
                            Column { width: (parent.width-10)/2; spacing: 4
                                Rectangle{width:parent.width;height:22;radius:4;color:"#7f1d1d";border.color:"#ef4444";border.width:1;Text{anchors.centerIn:parent;text:"NED (PX4)";color:"#fca5a5";font.pixelSize:10;font.weight:Font.Bold}}
                                Repeater {
                                    model:[{key:"ned_north",label:"North",color:"#ef4444"},{key:"ned_east",label:"East",color:"#ef4444"},{key:"ned_down",label:"Down",color:"#ef4444"}]
                                    delegate:Row{width:parent.width;height:20;spacing:4
                                        Text{text:modelData.label+":";color:"#94a3b8";font.pixelSize:9;width:50}
                                        Text {
                                            text: {
                                                var v = frameCol.parent.frameData[modelData.key]
                                                return v !== undefined ? v.toFixed(2) + "m" : "—"
                                            }
                                            color: modelData.color
                                            font.pixelSize: 10
                                            font.family: "Consolas"
                                            font.weight: Font.Bold
                                        }
                                    }
                                }
                            }
                            Column { width: (parent.width-10)/2; spacing: 4
                                Rectangle{width:parent.width;height:22;radius:4;color:"#14532d";border.color:"#22c55e";border.width:1;Text{anchors.centerIn:parent;text:"ENU (ROS2)";color:"#86efac";font.pixelSize:10;font.weight:Font.Bold}}
                                Repeater {
                                    model:[{key:"enu_east",label:"East",color:"#22c55e"},{key:"enu_north",label:"North",color:"#22c55e"},{key:"enu_up",label:"Up",color:"#22c55e"}]
                                    delegate:Row{width:parent.width;height:20;spacing:4
                                        Text{text:modelData.label+":";color:"#94a3b8";font.pixelSize:9;width:50}
                                        Text {
                                            text: {
                                                var v = frameCol.parent.frameData[modelData.key]
                                                return v !== undefined ? v.toFixed(2) + "m" : "—"
                                            }
                                            color: modelData.color
                                            font.pixelSize: 10
                                            font.family: "Consolas"
                                            font.weight: Font.Bold
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Item { width: 1; height: 8 }
            }
        }
    }

    // ── Mission Upload Dialog ─────────────────────────────────────────────
    Dialog {
        id: missionDialog
        title: "Upload Mission"
        modal: true
        anchors.centerIn: parent
        width: 500; height: 600

        background: Rectangle { color: "#1a2035"; radius: 8; border.color: "#2d3748"; border.width: 1 }

        ListModel { id: dialogWaypoints }

        onOpened: {
            dialogWaypoints.clear()
            if (root.globalWaypoints && root.globalWaypoints.count > 0) {
                for (var i = 0; i < root.globalWaypoints.count; i++) {
                    var wp = root.globalWaypoints.get(i)
                    dialogWaypoints.append({ lat: wp.lat || 0, lon: wp.lon || 0, alt: wp.alt || 15.0, hold_time: wp.hold_time || 2.0 })
                }
            }
        }

        contentItem: Column {
            anchors { fill: parent; margins: 12 }
            spacing: 8

            Text { text: "Waypoints (" + dialogWaypoints.count + ")"; color: "#e2e8f0"; font.pixelSize: 11; font.weight: Font.Bold }

            Rectangle {
                width: parent.width; height: 260; radius: 6
                color: "#0d1117"; border.color: "#2d3748"; border.width: 1
                ScrollView { anchors.fill: parent; clip: true; contentWidth: availableWidth; ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    Column { width: parent.width; spacing: 1; topPadding: 4
                        Repeater {
                            model: dialogWaypoints
                            delegate: Rectangle {
                                width: parent.width; height: 30; color: index % 2 === 0 ? "#0d1117" : "#131a2a"
                                Row {
                                    anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                                    spacing: 6
                                    Text { text: (index+1)+"."; color:"#475569"; font.pixelSize:9; width:20; anchors.verticalCenter:parent.verticalCenter }
                                    Text { text:"Lat:"; color:"#64748b"; font.pixelSize:9; anchors.verticalCenter:parent.verticalCenter }
                                    Text { text:lat.toFixed(6); color:"#8be9fd"; font.pixelSize:9; font.family:"Consolas"; width:80; anchors.verticalCenter:parent.verticalCenter }
                                    Text { text:"Lon:"; color:"#64748b"; font.pixelSize:9; anchors.verticalCenter:parent.verticalCenter }
                                    Text { text:lon.toFixed(6); color:"#8be9fd"; font.pixelSize:9; font.family:"Consolas"; width:80; anchors.verticalCenter:parent.verticalCenter }
                                    Text { text:"Alt:"; color:"#64748b"; font.pixelSize:9; anchors.verticalCenter:parent.verticalCenter }
                                    Text { text:alt.toFixed(1)+"m"; color:"#86efac"; font.pixelSize:9; font.family:"Consolas"; anchors.verticalCenter:parent.verticalCenter }
                                }
                            }
                        }
                    }
                }
            }

            Text { text: "No waypoints. Add from Map or load test mission."; color: "#374151"; font.pixelSize: 10; visible: dialogWaypoints.count === 0 }

            Row { spacing: 8
                Rectangle { width: 140; height: 32; radius: 5; color: dlgUpM.containsMouse ? "#1e3a5f" : "#1e2535"; border.color: "#2563eb"; border.width: 1
                    Text { anchors.centerIn: parent; text: "⬆ Upload"; color: "#93c5fd"; font.pixelSize: 10; font.weight: Font.Bold }
                    MouseArea { id: dlgUpM; anchors.fill: parent; hoverEnabled: true
                        onClicked: {
                            if (typeof ros2 === "undefined" || !ros2 || root.selectedDroneId === "") { missionDialog.close(); return }
                            var wps = []; for (var i = 0; i < dialogWaypoints.count; i++) { var w = dialogWaypoints.get(i); wps.push({lat:w.lat,lon:w.lon,alt:w.alt,hold_time:w.hold_time}) }
                            if (ros2.uploadMission(root.selectedDroneId, wps)) missionDialog.close()
                        }
                    }
                }
                Rectangle { width: 140; height: 32; radius: 5; color: dlgTestM.containsMouse ? "#1e2535" : "#0d1117"; border.color: "#334155"; border.width: 1
                    Text { anchors.centerIn: parent; text: "Load Test Mission"; color: "#64748b"; font.pixelSize: 10 }
                    MouseArea { id: dlgTestM; anchors.fill: parent; hoverEnabled: true
                        onClicked: {
                            dialogWaypoints.clear()
                            dialogWaypoints.append({lat:47.397742,lon:8.545594,alt:15.0,hold_time:2.0})
                            dialogWaypoints.append({lat:47.397842,lon:8.545694,alt:20.0,hold_time:3.0})
                            dialogWaypoints.append({lat:47.397942,lon:8.545794,alt:15.0,hold_time:2.0})
                        }
                    }
                }
                Rectangle { width: 80; height: 32; radius: 5; color: dlgCancelM.containsMouse ? "#450a0a" : "#1e2535"; border.color: "#ef4444"; border.width: 1
                    Text { anchors.centerIn: parent; text: "Cancel"; color: "#fca5a5"; font.pixelSize: 10 }
                    MouseArea { id: dlgCancelM; anchors.fill: parent; hoverEnabled: true; onClicked: missionDialog.close() }
                }
            }
        }
    }
}
