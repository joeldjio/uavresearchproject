import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components" as Cmp

Rectangle {
    id: root
    height: 52
    color: "#161b27"

    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#2d3748" }

    // ── Connection state ──────────────────────────────────────────────────
    property var  connTypes:   ["Serial", "UDP", "TCP"]
    property int  connTypeIdx: 0
    property var  serialPorts: []
    property int  droneCounter: 0

    function refreshPorts() {
        serialPorts = swarm.availableSerialPorts()
        // Update port input with first available port
        if (serialPorts.length > 0) {
            var firstPort = serialPorts[0]
            portInput.text = typeof firstPort === "object" ? firstPort.port : firstPort
        }
    }

    Component.onCompleted: refreshPorts()

    // Build connection string from current inputs
    function buildConnStr() {
        var t = connTypes[connTypeIdx]
        if (t === "Serial") return portInput.text + ":" + baudBox.currentText
        if (t === "UDP")    return (addrInput.text === "0.0.0.0" ? "udpin:" : "udp:") + addrInput.text + ":" + udpPortInput.text
        if (t === "TCP")    return "tcp:" + addrInput.text + ":" + udpPortInput.text
        return portInput.text
    }

    signal droneSelected(string droneId)

    function doConnect() {
        var cs = buildConnStr()
        if (cs === "") return
        // Guard: refuse duplicate connection string
        var ids = swarm.droneIds()
        for (var i = 0; i < ids.length; i++) {
            var snap = swarm.droneSnapshot(ids[i])
            if (snap && snap.connectionString && snap.connectionString === cs) {
                duplicateFlash.visible = true
                duplicateTimer.restart()
                return
            }
        }
        
        // Generate drone ID based on connection type
        var did = ""
        var baud = 0
        
        if (root.connTypeIdx === 0) {  // Serial
            baud = parseInt(baudBox.currentText)
            cs = portInput.text  // Use just the port, not port:baud
            // Use port name as ID (e.g., "COM5")
            did = portInput.text
        } else {
            // For TCP/UDP, use traditional counter
            droneCounter++
            did = "drone" + droneCounter
        }
        
        swarm.addDroneTyped(did, cs, "generic", baud)
    }

    // Refresh badge list on swarm events
    Connections {
        target: swarm
        function onDroneAdded()       { badgeRepeater.model = swarm.droneIds() }
        function onDroneRemoved()     { badgeRepeater.model = swarm.droneIds() }
        function onConnectedChanged() { badgeRepeater.model = swarm.droneIds() }
    }

    // ─────────────────────────────────────────────────────────────────────
    RowLayout {
        anchors { fill: parent; leftMargin: 16; rightMargin: 16 }
        spacing: 10

        // Logo + title
        Text { text: "◉"; color: "#2563eb"; font.pixelSize: 22 }
        Text {
            text: "SkyMeshX GCS"
            color: "#e2e8f0"; font.pixelSize: 15; font.weight: Font.Bold; font.letterSpacing: 0.5
        }
        Text {
            text: (typeof updater !== "undefined" && updater) ? "v" + updater.currentVersion : "v?"
            color: "#4a6fa5"; font.pixelSize: 11
        }

        Rectangle { width: 1; height: 24; color: "#2d3748" }

        // Clock
        Text {
            id: clockLabel
            color: "#64748b"; font.pixelSize: 12; font.family: "Consolas"
            Timer { interval: 1000; running: true; repeat: true
                onTriggered: clockLabel.text = Qt.formatTime(new Date(), "hh:mm:ss") }
            Component.onCompleted: clockLabel.text = Qt.formatTime(new Date(), "hh:mm:ss")
        }

        Rectangle { width: 1; height: 24; color: "#2d3748" }

        // ── CONNECTION AREA ───────────────────────────────────────────────
        Row {
            spacing: 6
            Layout.alignment: Qt.AlignVCenter

            // Type tabs: Serial / UDP / TCP
            Repeater {
                model: root.connTypes
                delegate: Rectangle {
                    width: typeText.implicitWidth + 14; height: 26; radius: 5
                    color: root.connTypeIdx === index ? "#1e40af" : (typeHov.containsMouse ? "#1e2535" : "transparent")
                    border.color: root.connTypeIdx === index ? "#2563eb" : "#2d3748"; border.width: 1
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Text {
                        id: typeText
                        anchors.centerIn: parent
                        text: modelData
                        color: root.connTypeIdx === index ? "#93c5fd" : "#64748b"
                        font.pixelSize: 10; font.weight: Font.Medium
                    }
                    MouseArea { id: typeHov; anchors.fill: parent; hoverEnabled: true
                        onClicked: root.connTypeIdx = index }
                }
            }

            // ── Serial fields ─────────────────────────────────────────────
            Row {
                spacing: 4
                visible: root.connTypeIdx === 0

                // Port ComboBox (with refresh button)
                Rectangle {
                    width: 100; height: 28; radius: 5
                    color: "#0d1117"; border.color: "#374151"; border.width: 1
                    Row {
                        anchors { fill: parent; leftMargin: 6; rightMargin: 2 }
                        spacing: 0
                        TextInput {
                            id: portInput
                            width: parent.width - 22; height: parent.height
                            text: {
                                if (root.serialPorts.length > 0) {
                                    var p = root.serialPorts[0]
                                    return typeof p === "object" ? p.port : p
                                }
                                return "COM1"
                            }
                            color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"
                            verticalAlignment: TextInput.AlignVCenter
                            selectByMouse: true
                        }
                        // Dropdown arrow / refresh
                        Rectangle {
                            width: 20; height: parent.height; color: "transparent"
                            Text { anchors.centerIn: parent; text: "▼"; color: "#64748b"; font.pixelSize: 10 }
                            MouseArea { anchors.fill: parent
                                onClicked: {
                                    root.refreshPorts()
                                    if (root.serialPorts.length > 0) {
                                        var firstPort = root.serialPorts[0]
                                        portInput.text = typeof firstPort === "object" ? firstPort.port : firstPort
                                    }
                                    portsPopup.open()
                                }
                            }
                            // Simple port list popup
                            Popup {
                                id: portsPopup
                                y: parent.height + 2; width: 220
                                padding: 4
                                background: Rectangle { color: "#1a2035"; border.color: "#374151"; radius: 5 }
                                Column {
                                    spacing: 2
                                    Repeater {
                                        model: root.serialPorts.length > 0 ? root.serialPorts : [{"port": "(no ports)", "description": "No serial ports found"}]
                                        delegate: Rectangle {
                                            property var portData: modelData
                                            property string portName: typeof portData === "object" ? portData.port : portData
                                            property string portDesc: typeof portData === "object" ? portData.description : portData
                                            width: portsPopup.width - 8; height: portDescText.visible ? 38 : 24; radius: 4
                                            color: portItemHov.containsMouse ? "#2563eb22" : "transparent"
                                            Column {
                                                anchors { fill: parent; leftMargin: 8; rightMargin: 8; topMargin: 4; bottomMargin: 4 }
                                                spacing: 2
                                                Text {
                                                    text: portName
                                                    color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"; font.weight: Font.Bold
                                                }
                                                Text {
                                                    id: portDescText
                                                    text: portDesc
                                                    color: "#94a3b8"; font.pixelSize: 9
                                                    visible: portDesc !== portName && portDesc !== ""
                                                    elide: Text.ElideRight
                                                    width: parent.width
                                                }
                                            }
                                            MouseArea { id: portItemHov; anchors.fill: parent; hoverEnabled: true
                                                onClicked: { portInput.text = portName; portsPopup.close() } }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Baud rate
                ComboBox {
                    id: baudBox
                    width: 86; height: 28
                    model: ["57600", "115200", "921600"]
                    currentIndex: 1
                    font.pixelSize: 11; font.family: "Consolas"
                    background: Rectangle { color: "#0d1117"; border.color: "#374151"; border.width: 1; radius: 5 }
                    contentItem: Text {
                        leftPadding: 8; text: baudBox.displayText
                        color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            // ── UDP / TCP fields ──────────────────────────────────────────
            Row {
                spacing: 4
                visible: root.connTypeIdx > 0

                Rectangle {
                    width: 120; height: 28; radius: 5
                    color: "#0d1117"; border.color: "#374151"; border.width: 1
                    TextInput {
                        id: addrInput
                        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                        text: "127.0.0.1"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"
                        verticalAlignment: TextInput.AlignVCenter; selectByMouse: true
                    }
                }
                Rectangle {
                    width: 58; height: 28; radius: 5
                    color: "#0d1117"; border.color: "#374151"; border.width: 1
                    TextInput {
                        id: udpPortInput
                        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                        text: "14550"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"
                        verticalAlignment: TextInput.AlignVCenter; selectByMouse: true
                        validator: IntValidator { bottom: 1; top: 65535 }
                    }
                }
            }

            // Connect button
            Rectangle {
                id: connectBtn
                width: 72; height: 28; radius: 5
                color: connectBtnMouse.containsPress ? "#1d4ed8"
                     : (connectBtnMouse.containsMouse ? "#2563eb" : "#1e40af")
                Behavior on color { ColorAnimation { duration: 100 } }
                Text {
                    anchors.centerIn: parent
                    text: qsTr("+ ADD")
                    color: "white"; font.pixelSize: 11; font.weight: Font.Bold
                }
                MouseArea {
                    id: connectBtnMouse
                    anchors.fill: parent; hoverEnabled: true
                    onClicked: root.doConnect()
                }
            }

            // Duplicate-connection warning
            Rectangle {
                id: duplicateFlash
                visible: false
                width: dupText.implicitWidth + 16; height: 28; radius: 5
                color: "#7f1d1d"; border.color: "#ef4444"; border.width: 1
                Text { id: dupText; anchors.centerIn: parent; text: qsTr("Already connected!"); color: "#fca5a5"; font.pixelSize: 10; font.weight: Font.Bold }
                Timer { id: duplicateTimer; interval: 2500; onTriggered: duplicateFlash.visible = false }
            }
        }

        // ── Active connection badges ──────────────────────────────────────
        Row {
            id: connectionBadges
            spacing: 5
            Layout.alignment: Qt.AlignVCenter

            Repeater {
                id: badgeRepeater
                model: swarm ? swarm.droneIds() : []
                delegate: Rectangle {
                    property string did: modelData
                    property bool   ok:  swarm ? swarm.isDroneConnected(did) : false
                    property var    snap: swarm ? swarm.droneSnapshot(did) : null
                    property string autopilot: snap && snap.autopilot ? snap.autopilot : ""
                    property string displayText: {
                        if (ok && autopilot !== "" && autopilot !== "unknown") {
                            return did + " (" + autopilot + ")"
                        }
                        return did
                    }
                    width: badgeLabel.implicitWidth + 50; height: 26; radius: 13
                    color: ok ? "#14532d" : "#1c1917"
                    border.width: 1

                    // Pulse dot
                    Rectangle {
                        id: pulseDot
                        width: 6; height: 6; radius: 3
                        anchors { left: parent.left; leftMargin: 8; verticalCenter: parent.verticalCenter }
                        color: ok ? "#22c55e" : "#78716c"
                        SequentialAnimation on opacity {
                            running: ok; loops: Animation.Infinite
                            NumberAnimation { to: 0.3; duration: 800 }
                            NumberAnimation { to: 1.0; duration: 800 }
                        }
                    }

                    Text {
                        id: badgeLabel
                        anchors { left: pulseDot.right; leftMargin: 5; verticalCenter: parent.verticalCenter; right: disconnectBtn.left; rightMargin: 4 }
                        text: displayText
                        color: ok ? "#86efac" : "#a8a29e"
                        font.pixelSize: 10; font.weight: Font.Medium
                    }

                    // Disconnect button
                    Rectangle {
                        id: disconnectBtn
                        anchors { right: parent.right; rightMargin: 5; verticalCenter: parent.verticalCenter }
                        width: 18; height: 18; radius: 9
                        color: disconnectHov.containsMouse ? "#dc2626" : "#7f1d1d"
                        border.color: "#ef4444"; border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                        
                        Text {
                            anchors.centerIn: parent
                            text: "⏻"  // Power symbol
                            color: "#fca5a5"
                            font.pixelSize: 11
                            font.weight: Font.Bold
                        }
                        
                        MouseArea {
                            id: disconnectHov
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                // Disconnect and remove the drone
                                swarm.disconnectDrone(did)
                                swarm.removeDrone(did)
                            }
                        }
                        
                        ToolTip.visible: disconnectHov.containsMouse
                        ToolTip.text: qsTr("Disconnect")
                        ToolTip.delay: 400
                    }

                    // Click badge → select this drone globally
                    property bool isSelected: (typeof selectedDroneId !== "undefined") && selectedDroneId === did
                    border.color: isSelected ? "#f59e0b" : (ok ? "#22c55e" : "#44403c")  // single binding

                    ToolTip.visible: badgeHov.containsMouse
                    ToolTip.text: did
                    ToolTip.delay: 400
                    MouseArea { id: badgeHov; anchors.fill: parent; hoverEnabled: true; propagateComposedEvents: true
                        onClicked: function(mouse) { root.droneSelected(did); mouse.accepted = false } }
                }
            }
        }

        Item { Layout.fillWidth: true }

        // Emergency Stop
        Rectangle {
            width: estopLabel.implicitWidth + 24; height: 34; radius: 6
            color: estopMouse.containsPress ? "#7f1d1d" : (estopMouse.containsMouse ? "#b91c1c" : "#dc2626")
            Behavior on color { ColorAnimation { duration: 100 } }
            Row {
                anchors.centerIn: parent; spacing: 6
                Text { text: "⛔"; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                Text { id: estopLabel; text: qsTr("E-STOP"); color: "white"; font.pixelSize: 11; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
            }
            MouseArea {
                id: estopMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                    var droneId = Cmp.AppState.selectedDroneId
                    if (droneId && droneId !== "") {
                        swarm.emergencyStopSelected(droneId)
                    } else {
                        console.log("E-STOP: No drone selected")
                    }
                }
            }
        }
    }
}
