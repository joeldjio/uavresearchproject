import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "../components" as Cmp

// ── ArduPilot SITL Panel — 7 Sub-Tabs ────────────────────────────────────────
Item {
    id: root
    anchors.fill: parent

    // ── Helpers ───────────────────────────────────────────────────────────────
    function ok()  { return typeof sitl !== "undefined" && sitl !== null }
    function vsOk(){ return typeof videoStream !== "undefined" && videoStream !== null }

    // ── State ─────────────────────────────────────────────────────────────────
    property int    _tab:         0          // current sub-tab index
    property string _simStatus:   ok() ? sitl.sitlStatus()   : "stopped"
    property string _buildStatus: ok() ? sitl.buildStatus()  : "idle"
    property bool   _repoValid:   ok() ? sitl.isRepoValid()  : false
    property string _repoPath:    ok() ? sitl.getRepoPath()  : ""

    ListModel { id: consoleModel }           // panel console lines

    Connections {
        target: ok() ? sitl : null
        function onSitlStatusChanged(s)    { root._simStatus   = s }
        function onBuildStatusChanged(s)   { root._buildStatus = s }
        function onRepoValidChanged(v)     { root._repoValid   = v }
        function onSitlInstancesChanged()  { instanceList.model = ok() ? sitl.runningInstances() : [] }
        function onSitlLogLine(line) {
            if (consoleModel.count >= 500) consoleModel.remove(0)
            consoleModel.append({ text: line })
        }
    }

    Component.onCompleted: {
        if (!ok()) return
        var cfg = JSON.parse(sitl.loadConfig())
        root._repoPath  = cfg.repo_path || ""
        root._repoValid = sitl.isRepoValid()

        // pre-fill fields from saved config
        repoPathField.text         = cfg.repo_path       || ""
        buildBoardField.text       = (cfg.build  || {}).board   || "sitl"
        buildVehicleCombo.currentIndex = Math.max(0,
            buildVehicleModel.indexOf((cfg.build || {}).vehicle || "copter"))
        simVehicleCombo.currentIndex   = Math.max(0,
            simVehicleModel.indexOf((cfg.sim    || {}).vehicle  || "ArduCopter"))
        simFrameField.text         = (cfg.sim    || {}).frame   || ""
        simLocationField.text      = (cfg.sim    || {}).location|| "CMAC"
        simTcpPortField.text       = String((cfg.sim || {}).tcp_port || 5760)
        simUdpPortField.text       = String((cfg.sim || {}).udp_port || 14550)
        simUdpHostField.text       = (cfg.sim    || {}).udp_host|| "127.0.0.1"
        swarmCountSpin.value       = (cfg.swarm  || {}).count   || 5
        swarmLocationField.text    = (cfg.swarm  || {}).location|| "CMAC"
        swarmHeadingSpin.value     = (cfg.swarm  || {}).offset_heading || 90
        swarmSpacingSpin.value     = (cfg.swarm  || {}).offset_spacing || 10
        gzWorldField.text          = (cfg.gazebo || {}).world   || "iris_runway.sdf"
        gzWsPathField.text         = (cfg.gazebo || {}).gz_ws_path || (ok() ? sitl.getGzWsPath() : "~/gz_ws/src")
        gzStreamPortField.text     = String((cfg.gazebo || {}).stream_port || 5600)
    }

    // ── Sub-tab labels ────────────────────────────────────────────────────────
    readonly property var _tabs: [
        "Setup & Build", "Sim starten", "Swarm", "Geräte", "Parameter", "Gazebo", "Debug"
    ]

    // ── Helper models (JS arrays used by ComboBoxes) ──────────────────────────
    readonly property var buildVehicleModel: ["copter","plane","rover","sub","heli"]
    readonly property var simVehicleModel:   ["ArduCopter","ArduPlane","ArduRover","ArduSub","ArduHeli"]
    readonly property var speedupModel:      ["1","2","5","10","50"]
    readonly property var simLocations: [
        "CMAC","LLBH","Snowflake","KSFO","KOAK","HOME","ArduPilot_Park"
    ]

    // ── Colour helpers ────────────────────────────────────────────────────────
    function simColor(s) {
        if (s === "running")  return "#22c55e"
        if (s === "starting") return "#f59e0b"
        if (s === "error")    return "#ef4444"
        return "#64748b"
    }
    function simLabel(s) {
        if (s === "running")  return "Running"
        if (s === "starting") return "Starting…"
        if (s === "error")    return "Error"
        return "Stopped"
    }

    // ═════════════════════════════════════════════════════════════════════════
    // ROOT LAYOUT
    // ═════════════════════════════════════════════════════════════════════════
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Title bar ─────────────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 46
            color: "#161b27"

            RowLayout {
                anchors { fill: parent; leftMargin: 16; rightMargin: 16 }

                Column {
                    spacing: 1
                    Text { text: "ArduPilot SITL"; font.pixelSize: 15; font.weight: Font.Bold; color: "#e2e8f0" }
                    Text { text: "Software-In-The-Loop Simulation"; font.pixelSize: 10; color: "#64748b" }
                }

                Item { Layout.fillWidth: true }

                // Repo valid badge
                Rectangle {
                    width: repoBadgeRow.implicitWidth + 16; height: 22; radius: 11
                    color: root._repoValid ? "#0d2117" : "#1a0f0f"
                    border.color: root._repoValid ? "#22c55e" : "#ef4444"; border.width: 1
                    Row {
                        id: repoBadgeRow
                        anchors.centerIn: parent; spacing: 5
                        Rectangle { width: 7; height: 7; radius: 3.5; color: root._repoValid ? "#22c55e" : "#ef4444"; anchors.verticalCenter: parent.verticalCenter }
                        Text {
                            text: root._repoValid ? "Repo OK" : "Kein Repo"
                            color: root._repoValid ? "#86efac" : "#fca5a5"; font.pixelSize: 10
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                Item { width: 8 }

                // Sim status badge
                Rectangle {
                    width: simBadgeRow.implicitWidth + 16; height: 22; radius: 11
                    color: Qt.rgba(Qt.color(simColor(root._simStatus)).r,
                                   Qt.color(root._simStatus === "stopped" ? "#64748b" : simColor(root._simStatus)).g,
                                   Qt.color(root._simStatus === "stopped" ? "#64748b" : simColor(root._simStatus)).b, 0.15)
                    border.color: simColor(root._simStatus); border.width: 1
                    Row {
                        id: simBadgeRow
                        anchors.centerIn: parent; spacing: 5
                        Rectangle { width: 7; height: 7; radius: 3.5; color: simColor(root._simStatus); anchors.verticalCenter: parent.verticalCenter }
                        Text {
                            text: simLabel(root._simStatus)
                            color: simColor(root._simStatus); font.pixelSize: 10
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
        }

        // Orange accent line
        Rectangle { Layout.fillWidth: true; height: 2; color: "#f97316"; opacity: 0.5 }

        // ── Sub-tab bar ────────────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 36
            color: "#0f1117"

            Row {
                anchors { left: parent.left; bottom: parent.bottom; leftMargin: 8 }
                spacing: 2

                Repeater {
                    model: root._tabs
                    delegate: Rectangle {
                        width: tabLbl.implicitWidth + 20; height: 34
                        color: root._tab === index ? "#1e2535" : (tabHover.containsMouse ? "#161b27" : "transparent")
                        radius: 5

                        Rectangle {
                            visible: root._tab === index
                            anchors.bottom: parent.bottom
                            width: parent.width; height: 2
                            color: "#f97316"
                        }

                        Text {
                            id: tabLbl
                            text: modelData
                            anchors.centerIn: parent
                            font.pixelSize: 11; font.weight: root._tab === index ? Font.Bold : Font.Normal
                            color: root._tab === index ? "#f97316" : "#64748b"
                        }

                        MouseArea {
                            id: tabHover
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: root._tab = index
                        }
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: "#2d3748" }

        // ── Tab content ────────────────────────────────────────────────────────
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            // ══════════════════════════════════════════════════════════════════
            // TAB 0 — Setup & Build
            // ══════════════════════════════════════════════════════════════════
            Item {
                anchors.fill: parent
                visible: root._tab === 0

                RowLayout {
                    anchors { fill: parent; margins: 0 }
                    spacing: 0

                    // ── Left: Repo + Build config ─────────────────────────────
                    ScrollView {
                        Layout.preferredWidth: 380
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: 364
                            anchors { left: parent.left; leftMargin: 18; top: parent.top; topMargin: 18 }
                            spacing: 20

                            // ── Repo Path ─────────────────────────────────────
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Text { text: "ARDUPILOT REPO PFAD"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                                // Repo path row
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Rectangle {
                                        Layout.fillWidth: true; height: 36; radius: 6
                                        color: "#1e2535"
                                        border.color: root._repoValid ? "#166534" : (repoPathField.text.length > 0 ? "#7f1d1d" : "#2d3748")
                                        border.width: 1

                                        TextInput {
                                            id: repoPathField
                                            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 10; rightMargin: 10 }
                                            color: "#e2e8f0"; font.pixelSize: 12; font.family: "Consolas"
                                            text: root._repoPath
                                            clip: true
                                            onTextChanged: {
                                                if (!ok()) return
                                                sitl.setRepoPath(text)
                                                root._repoPath = text
                                            }
                                        }
                                    }

                                    // Browse button
                                    Rectangle {
                                        width: 72; height: 36; radius: 6
                                        color: browseM.containsMouse ? "#2d3748" : "#1e2535"
                                        border.color: "#2d3748"; border.width: 1
                                        Text { text: "Browse…"; color: "#94a3b8"; font.pixelSize: 11; anchors.centerIn: parent }
                                        MouseArea {
                                            id: browseM
                                            anchors.fill: parent; hoverEnabled: true
                                            onClicked: repoFolderDialog.open()
                                        }
                                    }
                                }

                                // Validation row
                                Rectangle {
                                    Layout.fillWidth: true; height: 28; radius: 5
                                    color: root._repoValid ? "#0d2117" : (repoPathField.text.length > 2 ? "#1a0f0f" : "#111827")
                                    border.color: root._repoValid ? "#166534" : (repoPathField.text.length > 2 ? "#7f1d1d" : "#1e2535")
                                    border.width: 1
                                    Row {
                                        anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: 10 }
                                        spacing: 6
                                        Text {
                                            text: root._repoValid ? "✓" : "✗"
                                            color: root._repoValid ? "#22c55e" : "#ef4444"; font.pixelSize: 12
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                        Text {
                                            text: root._repoValid
                                                  ? "sim_vehicle.py gefunden"
                                                  : (repoPathField.text.length > 2
                                                     ? "sim_vehicle.py nicht gefunden — Pfad prüfen"
                                                     : "Gib den Pfad zum geklonten ArduPilot-Repo ein")
                                            color: root._repoValid ? "#86efac" : (repoPathField.text.length > 2 ? "#fca5a5" : "#64748b")
                                            font.pixelSize: 10; font.family: "Consolas"
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                    }
                                }

                                // Clone hint (shown when no repo found)
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: cloneCol.implicitHeight + 18; radius: 6
                                    color: "#0a0f1a"; border.color: "#1e3a5f"; border.width: 1
                                    visible: !root._repoValid

                                    ColumnLayout {
                                        id: cloneCol
                                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                                        spacing: 4

                                        Text { text: "Repo noch nicht geklont? Terminal öffnen und ausführen:"; color: "#64748b"; font.pixelSize: 10 }

                                        Rectangle {
                                            Layout.fillWidth: true; height: cloneCmds.implicitHeight + 12; radius: 4
                                            color: "#080b10"
                                            Text {
                                                id: cloneCmds
                                                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                                                text: "git clone https://github.com/ArduPilot/ardupilot ~/ardupilot\ncd ~/ardupilot\ngit submodule update --init --recursive"
                                                color: "#4ade80"; font.family: "Consolas"; font.pixelSize: 10
                                                lineHeight: 1.7
                                            }
                                        }
                                    }
                                }
                            }

                            // ── Build Config ──────────────────────────────────
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Text { text: "BUILD KONFIGURATION"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 2; columnSpacing: 10; rowSpacing: 6

                                    Text { text: "Board"; color: "#64748b"; font.pixelSize: 11 }
                                    Text { text: "Vehicle"; color: "#64748b"; font.pixelSize: 11 }

                                    // Board field (free-text + common presets)
                                    Rectangle {
                                        Layout.fillWidth: true; height: 34; radius: 6
                                        color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                        TextInput {
                                            id: buildBoardField
                                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                            verticalAlignment: TextInput.AlignVCenter
                                            color: "#e2e8f0"; font.pixelSize: 12; font.family: "Consolas"
                                            text: "sitl"
                                        }
                                    }

                                    // Vehicle combobox
                                    ComboBox {
                                        id: buildVehicleCombo
                                        Layout.fillWidth: true; height: 34
                                        model: root.buildVehicleModel
                                        background: Rectangle { color: "#1e2535"; radius: 6; border.color: "#2d3748"; border.width: 1 }
                                        contentItem: Text { leftPadding: 10; text: buildVehicleCombo.currentText; color: "#e2e8f0"; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter }
                                        delegate: ItemDelegate {
                                            width: buildVehicleCombo.width
                                            contentItem: Text { text: modelData; color: "#e2e8f0"; font.pixelSize: 12 }
                                            background: Rectangle { color: hovered ? "#2d3748" : "#1e2535" }
                                        }
                                        popup: Popup {
                                            y: buildVehicleCombo.height; width: buildVehicleCombo.width; padding: 0
                                            background: Rectangle { color: "#1e2535"; border.color: "#2d3748"; radius: 6 }
                                            contentItem: ListView { clip: true; implicitHeight: contentHeight; model: buildVehicleCombo.delegateModel }
                                        }
                                    }
                                }

                                // Generated command preview
                                Rectangle {
                                    Layout.fillWidth: true; height: cmdPreviewBuild.implicitHeight + 14; radius: 6
                                    color: "#080b10"; border.color: "#1e2535"; border.width: 1
                                    Text {
                                        id: cmdPreviewBuild
                                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                                        text: "./waf configure --board " + (buildBoardField.text || "sitl") +
                                              "\n./waf " + (buildVehicleCombo.currentText || "copter")
                                        color: "#38bdf8"; font.family: "Consolas"; font.pixelSize: 11; lineHeight: 1.6
                                    }
                                }
                            }

                            // Build-In-Progress banner
                            Rectangle {
                                Layout.fillWidth: true; height: 38; radius: 6
                                visible: root._buildStatus === "building"
                                color: "#1c1400"; border.color: "#f59e0b"; border.width: 1
                                Row {
                                    anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: 12 }
                                    spacing: 8
                                    Text { text: "🔨"; font.pixelSize: 14; anchors.verticalCenter: parent.verticalCenter }
                                    Text {
                                        text: "Build läuft im externen Terminal — warte bis DONE, dann → Sim starten"
                                        color: "#fde68a"; font.pixelSize: 11
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                            }

                            // ── Build buttons ─────────────────────────────────
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                // Build
                                Rectangle {
                                    Layout.fillWidth: true; height: 38; radius: 7
                                    property bool _en: root._repoValid
                                    color: !_en ? "#0d1117" : (buildM.containsMouse ? "#92400e" : "#78350f")
                                    border.color: _en ? "#f97316" : "#1f2937"; border.width: 1
                                    Behavior on color { ColorAnimation { duration: 100 } }
                                    Row { anchors.centerIn: parent; spacing: 6
                                        Text { text: "▶"; color: parent.parent._en ? "#fed7aa" : "#374151"; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: "Build"; color: parent.parent._en ? "#fff7ed" : "#374151"; font.pixelSize: 13; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                                    }
                                    MouseArea { id: buildM; anchors.fill: parent; hoverEnabled: true; enabled: parent._en
                                        onClicked: { if (ok()) sitl.runBuild(buildBoardField.text, buildVehicleCombo.currentText) } }
                                }

                                // Clean
                                Rectangle {
                                    width: 70; height: 38; radius: 7
                                    color: cleanM.containsMouse ? "#1e2535" : "#111827"
                                    border.color: root._repoValid ? "#2d3748" : "#1f2937"; border.width: 1
                                    Text { text: "Clean"; color: root._repoValid ? "#94a3b8" : "#374151"; font.pixelSize: 12; anchors.centerIn: parent }
                                    MouseArea { id: cleanM; anchors.fill: parent; hoverEnabled: true; enabled: root._repoValid
                                        onClicked: { if (ok()) sitl.runClean() } }
                                }

                                // Distclean
                                Rectangle {
                                    width: 82; height: 38; radius: 7
                                    color: distM.containsMouse ? "#450a0a" : "#1a0a0a"
                                    border.color: root._repoValid ? "#7f1d1d" : "#1f2937"; border.width: 1
                                    Text { text: "Distclean"; color: root._repoValid ? "#fca5a5" : "#374151"; font.pixelSize: 11; anchors.centerIn: parent }
                                    MouseArea { id: distM; anchors.fill: parent; hoverEnabled: true; enabled: root._repoValid
                                        onClicked: { if (ok()) sitl.runDistclean() } }
                                }
                            }

                            Item { height: 12 }
                        }
                    }

                    Rectangle { width: 1; Layout.fillHeight: true; color: "#2d3748" }

                    // ── Right: Console ────────────────────────────────────────
                    ConsolePane { Layout.fillWidth: true; Layout.fillHeight: true }
                }
            }

            // ══════════════════════════════════════════════════════════════════
            // TAB 1 — Sim starten
            // ══════════════════════════════════════════════════════════════════
            Item {
                anchors.fill: parent
                visible: root._tab === 1

                RowLayout {
                    anchors { fill: parent; margins: 0 }
                    spacing: 0

                    ScrollView {
                        Layout.preferredWidth: 380
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: 364
                            anchors { left: parent.left; leftMargin: 18; top: parent.top; topMargin: 18 }
                            spacing: 16

                            Text { text: "SIM KONFIGURATION"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                            GridLayout {
                                Layout.fillWidth: true
                                columns: 2; columnSpacing: 10; rowSpacing: 8

                                Text { text: "Vehicle"; color: "#64748b"; font.pixelSize: 11 }
                                Text { text: "Frame"; color: "#64748b"; font.pixelSize: 11 }

                                ComboBox {
                                    id: simVehicleCombo
                                    Layout.fillWidth: true; height: 34
                                    model: root.simVehicleModel
                                    background: Rectangle { color: "#1e2535"; radius: 6; border.color: "#2d3748"; border.width: 1 }
                                    contentItem: Text { leftPadding: 10; text: simVehicleCombo.currentText; color: "#e2e8f0"; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter }
                                    delegate: ItemDelegate {
                                        width: simVehicleCombo.width
                                        contentItem: Text { text: modelData; color: "#e2e8f0"; font.pixelSize: 12 }
                                        background: Rectangle { color: hovered ? "#2d3748" : "#1e2535" }
                                    }
                                    popup: Popup {
                                        y: simVehicleCombo.height; width: simVehicleCombo.width; padding: 0
                                        background: Rectangle { color: "#1e2535"; border.color: "#2d3748"; radius: 6 }
                                        contentItem: ListView { clip: true; implicitHeight: contentHeight; model: simVehicleCombo.delegateModel }
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true; height: 34; radius: 6
                                    color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    TextInput {
                                        id: simFrameField
                                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                        verticalAlignment: TextInput.AlignVCenter
                                        color: "#e2e8f0"; font.pixelSize: 12; font.family: "Consolas"
                                        Text { text: "X  /  hexa  /  gazebo-iris"; color: "#374151"; font: parent.font; visible: parent.text.length === 0; anchors.fill: parent; verticalAlignment: Text.AlignVCenter }
                                    }
                                }

                                Text { text: "Location"; color: "#64748b"; font.pixelSize: 11 }
                                Text { text: "Speedup"; color: "#64748b"; font.pixelSize: 11 }

                                Rectangle {
                                    Layout.fillWidth: true; height: 34; radius: 6
                                    color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    TextInput {
                                        id: simLocationField
                                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                        verticalAlignment: TextInput.AlignVCenter
                                        color: "#e2e8f0"; font.pixelSize: 12; font.family: "Consolas"
                                        text: "CMAC"
                                    }
                                }

                                ComboBox {
                                    id: speedupCombo
                                    Layout.fillWidth: true; height: 34
                                    model: root.speedupModel
                                    background: Rectangle { color: "#1e2535"; radius: 6; border.color: "#2d3748"; border.width: 1 }
                                    contentItem: Text { leftPadding: 10; text: speedupCombo.currentText + "×"; color: "#e2e8f0"; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter }
                                    delegate: ItemDelegate {
                                        width: speedupCombo.width
                                        contentItem: Text { text: modelData + "×"; color: "#e2e8f0"; font.pixelSize: 12 }
                                        background: Rectangle { color: hovered ? "#2d3748" : "#1e2535" }
                                    }
                                    popup: Popup {
                                        y: speedupCombo.height; width: speedupCombo.width; padding: 0
                                        background: Rectangle { color: "#1e2535"; border.color: "#2d3748"; radius: 6 }
                                        contentItem: ListView { clip: true; implicitHeight: contentHeight; model: speedupCombo.delegateModel }
                                    }
                                }
                            }

                            // GCS connection
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 6

                                Text { text: "GCS VERBINDUNG"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                                Row {
                                    spacing: 12
                                    RadioButton {
                                        id: tcpRadio; text: "TCP"; checked: true
                                        contentItem: Text { text: parent.text; color: "#e2e8f0"; font.pixelSize: 12; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter }
                                    }
                                    RadioButton {
                                        id: udpRadio; text: "UDP (→ GCS)"
                                        contentItem: Text { text: parent.text; color: "#e2e8f0"; font.pixelSize: 12; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter }
                                    }
                                }

                                // TCP port row
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 8
                                    visible: tcpRadio.checked
                                    Text { text: "Port"; color: "#64748b"; font.pixelSize: 11; width: 50 }
                                    Rectangle {
                                        Layout.fillWidth: true; height: 32; radius: 5
                                        color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                        TextInput {
                                            id: simTcpPortField; text: "5760"
                                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                            verticalAlignment: TextInput.AlignVCenter
                                            color: "#38bdf8"; font.pixelSize: 12; font.family: "Consolas"
                                        }
                                    }
                                    Text { text: "→ tcp:127.0.0.1:" + simTcpPortField.text; color: "#38bdf8"; font.pixelSize: 10; font.family: "Consolas" }
                                }

                                // UDP row
                                GridLayout {
                                    Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 6
                                    visible: udpRadio.checked
                                    Text { text: "GCS Host"; color: "#64748b"; font.pixelSize: 11 }
                                    Text { text: "Port"; color: "#64748b"; font.pixelSize: 11 }
                                    Rectangle {
                                        Layout.fillWidth: true; height: 32; radius: 5
                                        color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                        TextInput { id: simUdpHostField; text: "127.0.0.1"; anchors.fill: parent; anchors.leftMargin: 10; verticalAlignment: TextInput.AlignVCenter; color: "#e2e8f0"; font.pixelSize: 12; font.family: "Consolas" }
                                    }
                                    Rectangle {
                                        Layout.fillWidth: true; height: 32; radius: 5
                                        color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                        TextInput { id: simUdpPortField; text: "14550"; anchors.fill: parent; anchors.leftMargin: 10; verticalAlignment: TextInput.AlignVCenter; color: "#38bdf8"; font.pixelSize: 12; font.family: "Consolas" }
                                    }
                                }
                            }

                            // Checkboxes
                            Row { spacing: 16
                                CheckBox { id: simMapCheck; checked: true; text: "--map"; contentItem: Text { text: parent.text; color: "#94a3b8"; font.pixelSize: 11; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                                CheckBox { id: simConsoleCheck; checked: true; text: "--console"; contentItem: Text { text: parent.text; color: "#94a3b8"; font.pixelSize: 11; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                                CheckBox { id: noMavproxyCheck; text: "--no-mavproxy"; contentItem: Text { text: parent.text; color: "#94a3b8"; font.pixelSize: 11; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                            }
                            Row { spacing: 16
                                CheckBox { id: wipeCheck; text: "--wipe-eeprom"; contentItem: Text { text: parent.text; color: "#94a3b8"; font.pixelSize: 11; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                            }

                            // Extra args
                            ColumnLayout { Layout.fillWidth: true; spacing: 4
                                Text { text: "Extra Argumente"; color: "#64748b"; font.pixelSize: 11 }
                                Rectangle {
                                    Layout.fillWidth: true; height: 32; radius: 5
                                    color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    TextInput {
                                        id: simExtraField
                                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                        verticalAlignment: TextInput.AlignVCenter
                                        color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"
                                        Text { text: "--speedup 10  --instance 0  …"; color: "#374151"; font: parent.font; visible: parent.text.length === 0 }
                                    }
                                }
                            }

                            // Generated command
                            Rectangle {
                                Layout.fillWidth: true; height: simCmdText.implicitHeight + 14; radius: 6
                                color: "#080b10"; border.color: "#1e2535"; border.width: 1
                                Text {
                                    id: simCmdText
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                                    text: {
                                        var parts = ["python3 Tools/autotest/sim_vehicle.py",
                                                     "-v " + simVehicleCombo.currentText]
                                        if (simFrameField.text.trim()) parts.push("-f " + simFrameField.text.trim())
                                        if (simLocationField.text.trim()) parts.push("--location " + simLocationField.text.trim())
                                        if (speedupCombo.currentText !== "1") parts.push("--speedup " + speedupCombo.currentText)
                                        if (simMapCheck.checked && !noMavproxyCheck.checked) parts.push("--map")
                                        if (simConsoleCheck.checked && !noMavproxyCheck.checked) parts.push("--console")
                                        if (noMavproxyCheck.checked) parts.push("--no-mavproxy")
                                        if (wipeCheck.checked) parts.push("--wipe-eeprom")
                                        if (tcpRadio.checked && noMavproxyCheck.checked) parts.push('-A "--serial0=tcp:' + simTcpPortField.text + '"')
                                        if (udpRadio.checked) parts.push('-A "--serial0=udpclient:' + simUdpHostField.text + ':' + simUdpPortField.text + '"')
                                        if (simExtraField.text.trim()) parts.push(simExtraField.text.trim())
                                        return parts.join(" \\\n  ")
                                    }
                                    color: "#38bdf8"; font.family: "Consolas"; font.pixelSize: 10; lineHeight: 1.6
                                    wrapMode: Text.WrapAnywhere
                                }
                            }

                            // Start / Stop buttons
                            RowLayout { Layout.fillWidth: true; spacing: 8
                                Rectangle {
                                    Layout.fillWidth: true; height: 40; radius: 7
                                    property bool _en: root._repoValid && root._simStatus !== "running"
                                    color: !_en ? "#0d1117" : (startSimM.containsMouse ? "#15803d" : "#166534")
                                    border.color: _en ? "#22c55e" : "#1f2937"; border.width: 1
                                    Behavior on color { ColorAnimation { duration: 100 } }
                                    Row { anchors.centerIn: parent; spacing: 6
                                        Text { text: "▶"; color: parent.parent._en ? "#bbf7d0" : "#374151"; font.pixelSize: 14; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: "Start Simulation"; color: parent.parent._en ? "#f0fdf4" : "#374151"; font.pixelSize: 13; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                                    }
                                    MouseArea { id: startSimM; anchors.fill: parent; hoverEnabled: true; enabled: parent._en
                                        onClicked: {
                                            if (!ok()) return
                                            sitl.launchSimVehicle(JSON.stringify({
                                                vehicle:     simVehicleCombo.currentText,
                                                frame:       simFrameField.text.trim(),
                                                location:    simLocationField.text.trim(),
                                                speedup:     parseInt(speedupCombo.currentText) || 1,
                                                protocol:    tcpRadio.checked ? "tcp" : "udp",
                                                tcp_port:    parseInt(simTcpPortField.text) || 5760,
                                                udp_host:    simUdpHostField.text.trim(),
                                                udp_port:    parseInt(simUdpPortField.text) || 14550,
                                                use_map:     simMapCheck.checked,
                                                use_console: simConsoleCheck.checked,
                                                no_mavproxy: noMavproxyCheck.checked,
                                                wipe:        wipeCheck.checked,
                                                extra_args:  simExtraField.text.trim()
                                            }))
                                        }
                                    }
                                }

                                Rectangle {
                                    width: 72; height: 40; radius: 7
                                    visible: root._simStatus === "running"
                                    color: stopSimM.containsMouse ? "#7f1d1d" : "#1e2535"
                                    border.color: "#ef4444"; border.width: 1
                                    Row { anchors.centerIn: parent; spacing: 5
                                        Text { text: "■"; color: "#fca5a5"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: "Stop"; color: "#fca5a5"; font.pixelSize: 12; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                                    }
                                    MouseArea { id: stopSimM; anchors.fill: parent; hoverEnabled: true
                                        onClicked: { if (ok()) sitl.stopAll() } }
                                }
                            }

                            // Running instances
                            ListView {
                                id: instanceList
                                Layout.fillWidth: true
                                height: Math.min(contentHeight, 120)
                                clip: true; model: []; spacing: 4
                                delegate: Rectangle {
                                    width: instanceList.width; height: 34; radius: 5
                                    color: "#161b27"; border.color: "#2d3748"; border.width: 1
                                    Row {
                                        anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: 10 }
                                        spacing: 10
                                        Rectangle { width: 7; height: 7; radius: 3.5; color: "#22c55e"; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: "#" + modelData.index + "  " + modelData.vehicle; color: "#e2e8f0"; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: "tcp:127.0.0.1:" + modelData.port; color: "#38bdf8"; font.pixelSize: 11; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: modelData.uptime + "s"; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                                    }
                                }
                            }

                            Item { height: 12 }
                        }
                    }

                    Rectangle { width: 1; Layout.fillHeight: true; color: "#2d3748" }
                    ConsolePane { Layout.fillWidth: true; Layout.fillHeight: true }
                }
            }

            // ══════════════════════════════════════════════════════════════════
            // TAB 2 — Swarm
            // ══════════════════════════════════════════════════════════════════
            Item {
                anchors.fill: parent
                visible: root._tab === 2

                RowLayout {
                    anchors { fill: parent; margins: 0 }
                    spacing: 0

                    ScrollView {
                        Layout.preferredWidth: 380; Layout.fillHeight: true; clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: 364
                            anchors { left: parent.left; leftMargin: 18; top: parent.top; topMargin: 18 }
                            spacing: 16

                            Text { text: "SWARM KONFIGURATION"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                            GridLayout {
                                Layout.fillWidth: true; columns: 2; columnSpacing: 10; rowSpacing: 8

                                Text { text: "Anzahl Drohnen"; color: "#64748b"; font.pixelSize: 11 }
                                Text { text: "Location"; color: "#64748b"; font.pixelSize: 11 }

                                SpinBox {
                                    id: swarmCountSpin; from: 2; to: 20; value: 5
                                    Layout.fillWidth: true; height: 34
                                    background: Rectangle { color: "#1e2535"; radius: 6; border.color: "#2d3748" }
                                    contentItem: TextInput {
                                        text: swarmCountSpin.textFromValue(swarmCountSpin.value)
                                        color: "#e2e8f0"; font.pixelSize: 13; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; readOnly: true
                                    }
                                    up.indicator:   Rectangle { x: swarmCountSpin.width - 28; y: 0; width: 28; height: swarmCountSpin.height / 2; color: "transparent"; Text { text: "▲"; color: "#94a3b8"; font.pixelSize: 9; anchors.centerIn: parent } }
                                    down.indicator: Rectangle { x: swarmCountSpin.width - 28; y: swarmCountSpin.height / 2; width: 28; height: swarmCountSpin.height / 2; color: "transparent"; Text { text: "▼"; color: "#94a3b8"; font.pixelSize: 9; anchors.centerIn: parent } }
                                }

                                Rectangle {
                                    Layout.fillWidth: true; height: 34; radius: 6
                                    color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    TextInput { id: swarmLocationField; text: "CMAC"; anchors.fill: parent; anchors.leftMargin: 10; verticalAlignment: TextInput.AlignVCenter; color: "#e2e8f0"; font.pixelSize: 12; font.family: "Consolas" }
                                }
                            }

                            Row { spacing: 16
                                CheckBox { id: autoSysidCheck; checked: true; text: "--auto-sysid"; contentItem: Text { text: parent.text; color: "#94a3b8"; font.pixelSize: 11; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                                CheckBox { id: mcastCheck; checked: true; text: "--mcast"; contentItem: Text { text: parent.text; color: "#94a3b8"; font.pixelSize: 11; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                            }

                            ColumnLayout { Layout.fillWidth: true; spacing: 6
                                Text { text: "OFFSET METHODE"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                                Row { spacing: 20
                                    RadioButton { id: offsetLineRadio; text: "Linie"; checked: true; contentItem: Text { text: parent.text; color: "#e2e8f0"; font.pixelSize: 12; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                                    RadioButton { id: offsetFileRadio; text: "Datei (swarminit.txt)"; contentItem: Text { text: parent.text; color: "#e2e8f0"; font.pixelSize: 12; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                                }

                                GridLayout {
                                    Layout.fillWidth: true; columns: 2; columnSpacing: 10; rowSpacing: 6
                                    visible: offsetLineRadio.checked

                                    Text { text: "Heading (°)"; color: "#64748b"; font.pixelSize: 11 }
                                    Text { text: "Abstand (m)"; color: "#64748b"; font.pixelSize: 11 }

                                    SpinBox {
                                        id: swarmHeadingSpin; from: 0; to: 359; value: 90
                                        Layout.fillWidth: true; height: 32
                                        background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748" }
                                        contentItem: TextInput { text: swarmHeadingSpin.textFromValue(swarmHeadingSpin.value); color: "#e2e8f0"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; readOnly: true }
                                        up.indicator:   Rectangle { x: swarmHeadingSpin.width - 28; y: 0; width: 28; height: swarmHeadingSpin.height / 2; color: "transparent"; Text { text: "▲"; color: "#94a3b8"; font.pixelSize: 9; anchors.centerIn: parent } }
                                        down.indicator: Rectangle { x: swarmHeadingSpin.width - 28; y: swarmHeadingSpin.height / 2; width: 28; height: swarmHeadingSpin.height / 2; color: "transparent"; Text { text: "▼"; color: "#94a3b8"; font.pixelSize: 9; anchors.centerIn: parent } }
                                    }
                                    SpinBox {
                                        id: swarmSpacingSpin; from: 1; to: 100; value: 10
                                        Layout.fillWidth: true; height: 32
                                        background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748" }
                                        contentItem: TextInput { text: swarmSpacingSpin.textFromValue(swarmSpacingSpin.value); color: "#e2e8f0"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; readOnly: true }
                                        up.indicator:   Rectangle { x: swarmSpacingSpin.width - 28; y: 0; width: 28; height: swarmSpacingSpin.height / 2; color: "transparent"; Text { text: "▲"; color: "#94a3b8"; font.pixelSize: 9; anchors.centerIn: parent } }
                                        down.indicator: Rectangle { x: swarmSpacingSpin.width - 28; y: swarmSpacingSpin.height / 2; width: 28; height: swarmSpacingSpin.height / 2; color: "transparent"; Text { text: "▼"; color: "#94a3b8"; font.pixelSize: 9; anchors.centerIn: parent } }
                                    }
                                }

                                ColumnLayout { Layout.fillWidth: true; spacing: 4; visible: offsetFileRadio.checked
                                    Text { text: "Swarm-Config-Datei"; color: "#64748b"; font.pixelSize: 11 }
                                    RowLayout { Layout.fillWidth: true; spacing: 6
                                        Rectangle { Layout.fillWidth: true; height: 32; radius: 5; color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                            TextInput {
                                                id: swarmFileField
                                                anchors.fill: parent; anchors.leftMargin: 10
                                                verticalAlignment: TextInput.AlignVCenter
                                                color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"
                                                Text { text: "Tools/autotest/swarminit.txt"; color: "#374151"; font: parent.font; visible: parent.text.length === 0; anchors.fill: parent; verticalAlignment: Text.AlignVCenter }
                                            } }
                                        Rectangle { width: 72; height: 32; radius: 5; color: swarmFileM.containsMouse ? "#2d3748" : "#1e2535"; border.color: "#2d3748"; border.width: 1
                                            Text { text: "Browse…"; color: "#94a3b8"; font.pixelSize: 11; anchors.centerIn: parent }
                                            MouseArea { id: swarmFileM; anchors.fill: parent; hoverEnabled: true; onClicked: swarmFileDlg.open() } }
                                    }
                                }
                            }

                            // Generated command
                            Rectangle {
                                Layout.fillWidth: true; height: swarmCmdText.implicitHeight + 14; radius: 6
                                color: "#080b10"; border.color: "#1e2535"; border.width: 1
                                Text {
                                    id: swarmCmdText
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                                    text: {
                                        var p = ["python3 Tools/autotest/sim_vehicle.py",
                                                 "-v " + (root.simVehicleModel[0] || "ArduCopter"),
                                                 "--count " + swarmCountSpin.value,
                                                 "--location " + (swarmLocationField.text || "CMAC")]
                                        if (autoSysidCheck.checked) p.push("--auto-sysid")
                                        if (mcastCheck.checked) p.push("--mcast")
                                        p.push("--map"); p.push("--console")
                                        if (offsetLineRadio.checked)
                                            p.push("--auto-offset-line " + swarmHeadingSpin.value + "," + swarmSpacingSpin.value)
                                        else if (swarmFileField.text.trim())
                                            p.push("--swarm " + swarmFileField.text.trim())
                                        return p.join(" \\\n  ")
                                    }
                                    color: "#38bdf8"; font.family: "Consolas"; font.pixelSize: 10; lineHeight: 1.6; wrapMode: Text.WrapAnywhere
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true; height: 40; radius: 7
                                property bool _en: root._repoValid && root._simStatus !== "running"
                                color: !_en ? "#0d1117" : (startSwarmM.containsMouse ? "#15803d" : "#166534")
                                border.color: _en ? "#22c55e" : "#1f2937"; border.width: 1
                                Behavior on color { ColorAnimation { duration: 100 } }
                                Row { anchors.centerIn: parent; spacing: 6
                                    Text { text: "▶"; color: parent.parent._en ? "#bbf7d0" : "#374151"; font.pixelSize: 14; anchors.verticalCenter: parent.verticalCenter }
                                    Text { text: "Start Swarm (" + swarmCountSpin.value + " Drohnen)"; color: parent.parent._en ? "#f0fdf4" : "#374151"; font.pixelSize: 13; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                                }
                                MouseArea { id: startSwarmM; anchors.fill: parent; hoverEnabled: true; enabled: parent._en
                                    onClicked: {
                                        if (!ok()) return
                                        sitl.launchSwarm(JSON.stringify({
                                            vehicle:        simVehicleCombo.currentText,
                                            count:          swarmCountSpin.value,
                                            auto_sysid:     autoSysidCheck.checked,
                                            mcast:          mcastCheck.checked,
                                            location:       swarmLocationField.text.trim(),
                                            offset_mode:    offsetLineRadio.checked ? "line" : "file",
                                            offset_heading: swarmHeadingSpin.value,
                                            offset_spacing: swarmSpacingSpin.value,
                                            swarm_file:     swarmFileField.text.trim(),
                                            use_map:        true,
                                            use_console:    true
                                        }))
                                    }
                                }
                            }

                            // GCS connection table after launch
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 4
                                visible: root._simStatus === "running" && instanceList2.model && instanceList2.model.length > 0

                                Text { text: "GCS VERBINDUNGEN"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                                ListView {
                                    id: instanceList2
                                    Layout.fillWidth: true; height: Math.min(contentHeight, 160)
                                    clip: true; model: ok() ? sitl.runningInstances() : []; spacing: 4

                                    Timer { interval: 2000; running: root._tab === 2; repeat: true
                                        onTriggered: instanceList2.model = ok() ? sitl.runningInstances() : [] }

                                    delegate: Rectangle {
                                        width: instanceList2.width; height: 32; radius: 5
                                        color: "#161b27"; border.color: "#2d3748"; border.width: 1
                                        Row {
                                            anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; anchors.leftMargin: 10
                                            spacing: 10
                                            Text { text: "#" + modelData.index; color: "#64748b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                                            Text { text: "tcp:127.0.0.1:" + modelData.port; color: "#38bdf8"; font.pixelSize: 11; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter }
                                            Text { text: "SYSID " + (modelData.index + 1); color: "#a78bfa"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                                        }
                                    }
                                }
                            }

                            Item { height: 12 }
                        }
                    }

                    Rectangle { width: 1; Layout.fillHeight: true; color: "#2d3748" }
                    ConsolePane { Layout.fillWidth: true; Layout.fillHeight: true }
                }
            }

            // ══════════════════════════════════════════════════════════════════
            // ══════════════════════════════════════════════════════════════════
            // TAB 3 — Geräte / Peripherals
            // ══════════════════════════════════════════════════════════════════
            Item {
                id: periTab
                anchors.fill: parent
                visible: root._tab === 3

                // Reload catalogue whenever tab becomes visible or devices change
                property var _catalogue: []
                function _reload() {
                    _catalogue = ok() ? sitl.getPeripheralCatalogue() : []
                }
                onVisibleChanged: if (visible) _reload()
                Component.onCompleted: _reload()

                Connections {
                    target: ok() ? sitl : null
                    function onPeripheralDevicesChanged() { periTab._reload() }
                }

                RowLayout {
                    anchors { fill: parent; margins: 0 }
                    spacing: 0

                    ScrollView {
                        Layout.preferredWidth: 420
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: 404
                            anchors { left: parent.left; leftMargin: 18; top: parent.top; topMargin: 18 }
                            spacing: 20

                            Text { text: "SIMULIERTE GERÄTE / PERIPHERALS"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                            // Info banner
                            Rectangle {
                                Layout.fillWidth: true; height: periInfoCol.implicitHeight + 16; radius: 6
                                color: "#0a0f1a"; border.color: "#1e3a5f"; border.width: 1
                                ColumnLayout {
                                    id: periInfoCol
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                                    spacing: 3
                                    Text { text: "Aktivierte Geräte werden beim nächsten Sim-Start als Parameter eingebaut."; color: "#64748b"; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Text { text: "Einige Geräte erfordern einen Neustart nach dem ersten Setzen (EEPROM-Persistierung)."; color: "#64748b"; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                }
                            }

                            // Category: Sensoren
                            Text { text: "SENSOREN"; font.pixelSize: 9; font.weight: Font.Bold; color: "#475569"; font.letterSpacing: 0.8 }
                            PeripheralSection { catalogue: periTab._catalogue; category: "sensor" }

                            // Category: Umgebung
                            Text { text: "UMGEBUNG"; font.pixelSize: 9; font.weight: Font.Bold; color: "#475569"; font.letterSpacing: 0.8 }
                            PeripheralSection { catalogue: periTab._catalogue; category: "environment" }

                            // Category: Kamera / Display
                            Text { text: "KAMERA / DISPLAY"; font.pixelSize: 9; font.weight: Font.Bold; color: "#475569"; font.letterSpacing: 0.8 }
                            PeripheralSection { catalogue: periTab._catalogue; category: "camera" }
                            PeripheralSection { catalogue: periTab._catalogue; category: "display" }

                            // Pending params summary
                            Rectangle {
                                Layout.fillWidth: true; height: pendingParamsCol.implicitHeight + 16; radius: 6
                                color: "#0d1117"; border.color: "#2d3748"; border.width: 1
                                visible: ok() && JSON.parse(sitl.getPendingParams && sitl.getPendingParams() || "{}") !== null

                                ColumnLayout {
                                    id: pendingParamsCol
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                                    spacing: 4
                                    Text { text: "AUSSTEHENDE PARAMETER"; font.pixelSize: 9; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }
                                    Text {
                                        text: {
                                            if (!ok()) return "—"
                                            var p = {}
                                            try { p = JSON.parse(sitl.getPendingParams()) } catch(e) { return "—" }
                                            var keys = Object.keys(p)
                                            if (keys.length === 0) return "Keine ausstehenden Parameter"
                                            return keys.map(function(k){ return k + " = " + p[k] }).join("\n")
                                        }
                                        color: "#38bdf8"; font.pixelSize: 10; font.family: "Consolas"
                                        wrapMode: Text.WordWrap; Layout.fillWidth: true
                                    }
                                }
                            }

                            Item { height: 12 }
                        }
                    }

                    Rectangle { width: 1; Layout.fillHeight: true; color: "#2d3748" }
                    ConsolePane { Layout.fillWidth: true; Layout.fillHeight: true }
                }
            }

            // ══════════════════════════════════════════════════════════════════
            // TAB 4 — Parameter (SIM_* Browser + Live MAVLink)
            // ══════════════════════════════════════════════════════════════════
            Item {
                id: paramTab
                anchors.fill: parent
                visible: root._tab === 4

                // Static catalogue params (from sitl.getKnownParams)
                property var  _params:      []
                property var  _filtered:    []
                property string _filterText: ""
                property string _editName:   ""
                property string _editValue:  ""
                property bool   _editActive: false

                // Live MAVLink params (from swarm.fetchParams)
                property string _liveTargetId: ""   // drone_id whose params are shown
                property var    _liveParams:    ({}) // name → value (float)
                property bool   _liveLoading:  false
                property bool   _liveMode:     false // true = show live params instead of catalogue

                function _swarmOk() { return typeof swarm !== "undefined" && swarm !== null }

                function _reload() {
                    _params = ok() ? JSON.parse(sitl.getKnownParams()) : []
                    _applyFilter()
                }
                function _applyFilter() {
                    var q = _filterText.toLowerCase()
                    if (!q) {
                        _filtered = _params
                    } else {
                        _filtered = _params.filter(function(p){
                            return p.name.toLowerCase().indexOf(q) >= 0 ||
                                   p.desc.toLowerCase().indexOf(q) >= 0 ||
                                   p.category.toLowerCase().indexOf(q) >= 0
                        })
                    }
                }

                // Build filtered live-param list from _liveParams object
                function _liveFiltered() {
                    var q = _filterText.toLowerCase()
                    var keys = Object.keys(_liveParams)
                    if (q) keys = keys.filter(function(k){ return k.toLowerCase().indexOf(q) >= 0 })
                    keys.sort()
                    return keys.map(function(k){ return { name: k, value: _liveParams[k] } })
                }

                function _fetchLive() {
                    if (!_swarmOk() || !_liveTargetId) return
                    _liveLoading = true
                    swarm.fetchParams(_liveTargetId)
                }

                onVisibleChanged: if (visible) _reload()
                Component.onCompleted: _reload()

                Connections {
                    target: ok() ? sitl : null
                    function onParamChanged(name, value) { paramTab._reload() }
                    function onPeripheralDevicesChanged() { paramTab._reload() }
                }

                Connections {
                    target: _swarmOk() ? swarm : null
                    function onParamsLoaded(droneId, paramsJson) {
                        if (droneId !== paramTab._liveTargetId) return
                        paramTab._liveLoading = false
                        paramTab._liveParams = JSON.parse(paramsJson) || {}
                        paramTab._liveMode = true
                    }
                }

                RowLayout {
                    anchors { fill: parent; margins: 0 }
                    spacing: 0

                    ColumnLayout {
                        Layout.preferredWidth: 500
                        Layout.fillHeight: true
                        spacing: 0

                        // ── Header Row 1: mode toggle + drone selector ───────
                        Rectangle {
                            Layout.fillWidth: true; height: 42; color: "#0d1117"
                            RowLayout {
                                anchors { fill: parent; leftMargin: 14; rightMargin: 14 }
                                spacing: 8

                                // Catalogue / Live toggle
                                Rectangle {
                                    width: 90; height: 26; radius: 5
                                    color: !paramTab._liveMode ? "#0d2035" : "#1e2535"
                                    border.color: !paramTab._liveMode ? "#2563eb" : "#2d3748"; border.width: 1
                                    Text { text: "Katalog"; color: !paramTab._liveMode ? "#93c5fd" : "#64748b"; font.pixelSize: 10; font.weight: Font.Bold; anchors.centerIn: parent }
                                    MouseArea { anchors.fill: parent; onClicked: { paramTab._liveMode = false } }
                                }
                                Rectangle {
                                    width: 90; height: 26; radius: 5
                                    color: paramTab._liveMode ? "#0d2117" : "#1e2535"
                                    border.color: paramTab._liveMode ? "#22c55e" : "#2d3748"; border.width: 1
                                    Text { text: "Live (MAVLink)"; color: paramTab._liveMode ? "#86efac" : "#64748b"; font.pixelSize: 10; font.weight: Font.Bold; anchors.centerIn: parent }
                                    MouseArea { anchors.fill: parent; onClicked: { paramTab._liveMode = true } }
                                }

                                // Drone selector (only relevant for live mode)
                                ComboBox {
                                    id: paramDroneCombo
                                    visible: paramTab._liveMode
                                    Layout.preferredWidth: 130; height: 28
                                    model: paramTab._swarmOk() ? swarm.droneIds() : []
                                    onCurrentTextChanged: { paramTab._liveTargetId = currentText }
                                    Component.onCompleted: {
                                        if (count > 0) paramTab._liveTargetId = model[0]
                                    }
                                    background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                    contentItem: Text { leftPadding: 8; text: paramDroneCombo.currentText || "– Drohne –"; color: "#e2e8f0"; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter }
                                    delegate: ItemDelegate {
                                        width: paramDroneCombo.width
                                        contentItem: Text { text: modelData; color: "#e2e8f0"; font.pixelSize: 11 }
                                        background: Rectangle { color: hovered ? "#2d3748" : "#1e2535" }
                                    }
                                    popup: Popup {
                                        y: paramDroneCombo.height; width: paramDroneCombo.width; padding: 0
                                        background: Rectangle { color: "#1e2535"; border.color: "#2d3748"; radius: 5 }
                                        contentItem: ListView { clip: true; implicitHeight: contentHeight; model: paramDroneCombo.delegateModel }
                                    }
                                }

                                // Fetch live params button
                                Rectangle {
                                    visible: paramTab._liveMode
                                    width: fetchLbl.implicitWidth + 20; height: 28; radius: 5
                                    color: fetchM.containsMouse ? "#15803d" : "#166534"; border.color: "#22c55e"; border.width: 1
                                    opacity: paramTab._liveLoading ? 0.5 : 1.0
                                    Text { id: fetchLbl; text: paramTab._liveLoading ? "Laden…" : "Laden"; color: "#bbf7d0"; font.pixelSize: 11; font.weight: Font.Bold; anchors.centerIn: parent }
                                    MouseArea { id: fetchM; anchors.fill: parent; hoverEnabled: true
                                        enabled: !paramTab._liveLoading && paramTab._liveTargetId !== ""
                                        onClicked: paramTab._fetchLive()
                                    }
                                }

                                Item { Layout.fillWidth: true }

                                // Search
                                Rectangle {
                                    width: 180; height: 28; radius: 5
                                    color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    RowLayout {
                                        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                                        Text { text: "⌕"; color: "#475569"; font.pixelSize: 14 }
                                        TextInput {
                                            id: paramSearchField
                                            Layout.fillWidth: true
                                            color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"
                                            verticalAlignment: TextInput.AlignVCenter
                                            Text { text: "Suchen…"; color: "#374151"; font: parent.font; visible: parent.text.length === 0 }
                                            onTextChanged: {
                                                paramTab._filterText = text
                                                paramTab._applyFilter()
                                            }
                                        }
                                        Rectangle {
                                            width: 16; height: 16; radius: 8; color: clrSearchM.containsMouse ? "#2d3748" : "transparent"
                                            visible: paramSearchField.text.length > 0
                                            Text { text: "×"; color: "#94a3b8"; font.pixelSize: 11; anchors.centerIn: parent }
                                            MouseArea { id: clrSearchM; anchors.fill: parent; hoverEnabled: true; onClicked: { paramSearchField.text = ""; paramTab._filterText = ""; paramTab._applyFilter() } }
                                        }
                                    }
                                }

                                // Reload catalogue
                                Rectangle {
                                    visible: !paramTab._liveMode
                                    width: 26; height: 26; radius: 5; color: reloadM.containsMouse ? "#1e2535" : "transparent"; border.color: "#2d3748"; border.width: 1
                                    Text { text: "↺"; color: "#64748b"; font.pixelSize: 14; anchors.centerIn: parent }
                                    MouseArea { id: reloadM; anchors.fill: parent; hoverEnabled: true; onClicked: paramTab._reload() }
                                }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: "#1e2535" }

                        // ── Column header — adapts to catalogue vs live ───────
                        Rectangle {
                            Layout.fillWidth: true; height: 26; color: "#0a0e17"
                            RowLayout {
                                anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                spacing: 0
                                Text { text: "Parameter";   color: "#475569"; font.pixelSize: 10; font.weight: Font.Bold; Layout.preferredWidth: 170 }
                                Text { visible: !paramTab._liveMode; text: "Kategorie";  color: "#475569"; font.pixelSize: 10; font.weight: Font.Bold; Layout.preferredWidth: 80 }
                                Text { visible: !paramTab._liveMode; text: "Standard";   color: "#475569"; font.pixelSize: 10; font.weight: Font.Bold; Layout.preferredWidth: 60 }
                                Text { visible: !paramTab._liveMode; text: "Ausstehend"; color: "#475569"; font.pixelSize: 10; font.weight: Font.Bold; Layout.preferredWidth: 80 }
                                Text { visible: !paramTab._liveMode; text: "Einheit";    color: "#475569"; font.pixelSize: 10; font.weight: Font.Bold; Layout.fillWidth: true }
                                Text { visible: paramTab._liveMode;  text: "Live-Wert";  color: "#86efac"; font.pixelSize: 10; font.weight: Font.Bold; Layout.preferredWidth: 120 }
                                Item { visible: paramTab._liveMode; Layout.fillWidth: true }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: "#1e2535" }

                        // ── Parameter list ───────────────────────────────────
                        // ── Live-loading indicator ───────────────────────────
                        Rectangle {
                            Layout.fillWidth: true; height: 28
                            visible: paramTab._liveMode && paramTab._liveLoading
                            color: "#0d1f12"; border.color: "#16a34a"; border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: "Lade Parameter von " + paramTab._liveTargetId + "…"
                                color: "#86efac"; font.pixelSize: 11
                            }
                        }

                        // ── Catalogue mode list ──────────────────────────────
                        ListView {
                            id: paramListView
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true
                            visible: !paramTab._liveMode
                            model: paramTab._filtered
                            spacing: 0
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                            delegate: Rectangle {
                                id: paramRow
                                width: paramListView.width; height: paramRowCol.implicitHeight + 12
                                color: paramTab._editName === modelData.name
                                       ? "#0f1d2e"
                                       : (index % 2 === 0 ? "#0d1117" : "#0a0e17")
                                border.color: paramTab._editName === modelData.name ? "#2563eb" : "transparent"
                                border.width: 1

                                ColumnLayout {
                                    id: paramRowCol
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                                    spacing: 4

                                    // Main row
                                    RowLayout {
                                        Layout.fillWidth: true; spacing: 0

                                        // Name
                                        Text {
                                            text: modelData.name
                                            color: modelData.pending !== null ? "#38bdf8" : "#e2e8f0"
                                            font.pixelSize: 11; font.family: "Consolas"; font.weight: Font.Bold
                                            Layout.preferredWidth: 170
                                        }

                                        // Category badge
                                        Rectangle {
                                            width: catLabel.implicitWidth + 10; height: 16; radius: 3
                                            color: {
                                                var c = modelData.category
                                                if (c === "SIM")     return "#0d2117"
                                                if (c === "FRAME")   return "#1a0a00"
                                                if (c === "COMPASS") return "#1a0f2e"
                                                if (c === "RNGFND")  return "#0a1628"
                                                if (c === "BARO")    return "#1a1000"
                                                if (c === "CAM")     return "#1a0a17"
                                                if (c === "MNT")     return "#0a1a10"
                                                return "#111827"
                                            }
                                            Layout.preferredWidth: 80
                                            Text {
                                                id: catLabel
                                                text: modelData.category
                                                anchors.centerIn: parent
                                                color: {
                                                    var c = modelData.category
                                                    if (c === "SIM")     return "#4ade80"
                                                    if (c === "FRAME")   return "#f97316"
                                                    if (c === "COMPASS") return "#c4b5fd"
                                                    if (c === "RNGFND")  return "#60a5fa"
                                                    if (c === "BARO")    return "#fbbf24"
                                                    if (c === "CAM")     return "#f472b6"
                                                    if (c === "MNT")     return "#86efac"
                                                    return "#94a3b8"
                                                }
                                                font.pixelSize: 9; font.weight: Font.Bold
                                            }
                                        }

                                        // Default value
                                        Text {
                                            text: modelData.default
                                            color: "#475569"; font.pixelSize: 11; font.family: "Consolas"
                                            Layout.preferredWidth: 60
                                        }

                                        // Pending value
                                        Text {
                                            text: modelData.pending !== null ? modelData.pending : "—"
                                            color: modelData.pending !== null ? "#38bdf8" : "#1f2937"
                                            font.pixelSize: 11; font.family: "Consolas"
                                            Layout.preferredWidth: 80
                                        }

                                        // Unit
                                        Text {
                                            text: modelData.unit || ""
                                            color: "#475569"; font.pixelSize: 10
                                            Layout.fillWidth: true
                                        }

                                        // Edit / Clear buttons
                                        Row { spacing: 4
                                            Rectangle {
                                                width: 36; height: 22; radius: 4
                                                color: editBtnM.containsMouse ? "#1e3a5f" : "#0d1623"; border.color: "#2563eb"; border.width: 1
                                                Text { text: "Setzen"; color: "#93c5fd"; font.pixelSize: 9; anchors.centerIn: parent }
                                                MouseArea { id: editBtnM; anchors.fill: parent; hoverEnabled: true
                                                    onClicked: {
                                                        paramTab._editName  = modelData.name
                                                        paramTab._editValue = modelData.pending !== null ? modelData.pending : String(modelData.default)
                                                        paramTab._editActive = true
                                                        paramEditField.text = paramTab._editValue
                                                        paramEditField.forceActiveFocus()
                                                    }
                                                }
                                            }
                                            Rectangle {
                                                width: 22; height: 22; radius: 4
                                                visible: modelData.pending !== null
                                                color: clrBtnM.containsMouse ? "#450a0a" : "#1a0a0a"; border.color: "#7f1d1d"; border.width: 1
                                                Text { text: "✕"; color: "#fca5a5"; font.pixelSize: 10; anchors.centerIn: parent }
                                                MouseArea { id: clrBtnM; anchors.fill: parent; hoverEnabled: true
                                                    onClicked: { if (ok()) { sitl.clearParam(modelData.name); paramTab._reload() } }
                                                }
                                            }
                                        }
                                    }

                                    // Description
                                    Text {
                                        text: modelData.desc
                                        color: "#475569"; font.pixelSize: 10
                                        Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                                    }

                                    // Inline edit row (shown when this param is being edited)
                                    RowLayout {
                                        Layout.fillWidth: true; spacing: 6
                                        visible: paramTab._editName === modelData.name && paramTab._editActive

                                        Rectangle {
                                            Layout.fillWidth: true; height: 28; radius: 5
                                            color: "#111827"; border.color: "#2563eb"; border.width: 1
                                            TextInput {
                                                id: paramEditField
                                                anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                                verticalAlignment: TextInput.AlignVCenter
                                                color: "#38bdf8"; font.pixelSize: 12; font.family: "Consolas"
                                                Keys.onReturnPressed: {
                                                    if (ok() && paramTab._editName) {
                                                        sitl.setParam(paramTab._editName, text)
                                                        paramTab._editActive = false
                                                        paramTab._reload()
                                                    }
                                                }
                                                Keys.onEscapePressed: { paramTab._editActive = false }
                                            }
                                        }
                                        Rectangle {
                                            width: 52; height: 28; radius: 5
                                            color: saveParamM.containsMouse ? "#15803d" : "#166534"; border.color: "#22c55e"; border.width: 1
                                            Text { text: "Setzen"; color: "#f0fdf4"; font.pixelSize: 11; font.weight: Font.Bold; anchors.centerIn: parent }
                                            MouseArea { id: saveParamM; anchors.fill: parent; hoverEnabled: true
                                                onClicked: {
                                                    if (ok() && paramTab._editName) {
                                                        sitl.setParam(paramTab._editName, paramEditField.text)
                                                        paramTab._editActive = false
                                                        paramTab._reload()
                                                    }
                                                }
                                            }
                                        }
                                        Rectangle {
                                            width: 40; height: 28; radius: 5
                                            color: cancelParamM.containsMouse ? "#1e2535" : "#111827"; border.color: "#2d3748"; border.width: 1
                                            Text { text: "Abb."; color: "#94a3b8"; font.pixelSize: 11; anchors.centerIn: parent }
                                            MouseArea { id: cancelParamM; anchors.fill: parent; hoverEnabled: true; onClicked: { paramTab._editActive = false } }
                                        }
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent; hoverEnabled: true
                                    onClicked: {
                                        paramTab._editName  = modelData.name
                                        paramTab._editValue = modelData.pending !== null ? modelData.pending : String(modelData.default)
                                        paramTab._editActive = true
                                        paramEditField.text = paramTab._editValue
                                        paramEditField.forceActiveFocus()
                                    }
                                    z: -1
                                }
                            }

                            Text { anchors.centerIn: parent; text: "Keine Parameter gefunden"; color: "#1f2937"; font.pixelSize: 12; visible: paramListView.count === 0 }
                        }

                        // ── Live MAVLink param list ──────────────────────────
                        ListView {
                            id: liveParamListView
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true
                            visible: paramTab._liveMode && !paramTab._liveLoading
                            model: paramTab._liveMode ? paramTab._liveFiltered() : []
                            spacing: 0
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                            delegate: Rectangle {
                                width: liveParamListView.width; height: 34
                                color: paramTab._editName === modelData.name
                                       ? "#0f1d2e"
                                       : (index % 2 === 0 ? "#0d1117" : "#0a0e17")
                                border.color: paramTab._editName === modelData.name ? "#22c55e" : "transparent"
                                border.width: 1

                                RowLayout {
                                    anchors { fill: parent; leftMargin: 10; rightMargin: 8 }
                                    spacing: 0

                                    // Name
                                    Text {
                                        text: modelData.name
                                        color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas"; font.weight: Font.Bold
                                        Layout.preferredWidth: 200; elide: Text.ElideRight
                                    }

                                    // Live value
                                    Text {
                                        text: {
                                            var v = modelData.value
                                            // Show as integer if whole number, else 4 decimals
                                            return (v % 1 === 0) ? String(v) : v.toFixed(4)
                                        }
                                        color: "#86efac"; font.pixelSize: 11; font.family: "Consolas"
                                        Layout.preferredWidth: 120
                                    }

                                    Item { Layout.fillWidth: true }

                                    // Edit button
                                    Rectangle {
                                        width: 36; height: 22; radius: 4
                                        color: liveEditM.containsMouse ? "#1e3a5f" : "#0d1623"; border.color: "#2563eb"; border.width: 1
                                        Text { text: "Setzen"; color: "#93c5fd"; font.pixelSize: 9; anchors.centerIn: parent }
                                        MouseArea { id: liveEditM; anchors.fill: parent; hoverEnabled: true
                                            onClicked: {
                                                var v = modelData.value
                                                paramTab._editValue  = (v % 1 === 0) ? String(Math.round(v)) : v.toFixed(4)
                                                paramTab._editName   = modelData.name
                                                paramTab._editActive = true
                                                liveEditInput.text   = paramTab._editValue
                                                liveEditInput.forceActiveFocus()
                                            }
                                        }
                                    }
                                }

                            }

                            Text {
                                anchors.centerIn: parent
                                text: paramTab._liveTargetId ? "Noch keine Params geladen — 'Laden' drücken" : "Drohne wählen und 'Laden' drücken"
                                color: "#374151"; font.pixelSize: 12
                                visible: liveParamListView.count === 0 && !paramTab._liveLoading
                            }
                        }

                        // ── Live inline edit bar (shown above footer when editing live param) ──
                        Rectangle {
                            Layout.fillWidth: true; height: 44; color: "#0d1f2e"
                            border.color: "#22c55e"; border.width: 1
                            visible: paramTab._liveMode && paramTab._editActive && paramTab._editName !== ""

                            RowLayout {
                                anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                spacing: 8

                                Text {
                                    text: paramTab._editName + ":"; color: "#86efac"
                                    font.pixelSize: 11; font.family: "Consolas"; font.weight: Font.Bold
                                    Layout.preferredWidth: 180; elide: Text.ElideRight
                                }

                                Rectangle {
                                    Layout.fillWidth: true; height: 28; radius: 5
                                    color: "#111827"; border.color: "#22c55e"; border.width: 1
                                    TextInput {
                                        id: liveEditInput
                                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                        verticalAlignment: TextInput.AlignVCenter
                                        color: "#86efac"; font.pixelSize: 12; font.family: "Consolas"
                                        Keys.onReturnPressed: {
                                            if (paramTab._swarmOk() && paramTab._liveTargetId && paramTab._editName) {
                                                swarm.setDroneParam(paramTab._liveTargetId, paramTab._editName, parseFloat(text) || 0.0)
                                                var p = paramTab._liveParams
                                                p[paramTab._editName] = parseFloat(text) || 0.0
                                                paramTab._liveParams = p
                                                paramTab._editActive = false
                                            }
                                        }
                                        Keys.onEscapePressed: { paramTab._editActive = false }
                                    }
                                }

                                Rectangle {
                                    width: 52; height: 28; radius: 5
                                    color: liveApplyM.containsMouse ? "#15803d" : "#166534"; border.color: "#22c55e"; border.width: 1
                                    Text { text: "Setzen"; color: "#f0fdf4"; font.pixelSize: 11; font.weight: Font.Bold; anchors.centerIn: parent }
                                    MouseArea { id: liveApplyM; anchors.fill: parent; hoverEnabled: true
                                        onClicked: {
                                            if (paramTab._swarmOk() && paramTab._liveTargetId && paramTab._editName) {
                                                swarm.setDroneParam(paramTab._liveTargetId, paramTab._editName, parseFloat(liveEditInput.text) || 0.0)
                                                var p = paramTab._liveParams
                                                p[paramTab._editName] = parseFloat(liveEditInput.text) || 0.0
                                                paramTab._liveParams = p
                                                paramTab._editActive = false
                                            }
                                        }
                                    }
                                }

                                Rectangle {
                                    width: 36; height: 28; radius: 5
                                    color: liveAbbrM.containsMouse ? "#1e2535" : "#111827"; border.color: "#2d3748"; border.width: 1
                                    Text { text: "Abb."; color: "#94a3b8"; font.pixelSize: 11; anchors.centerIn: parent }
                                    MouseArea { id: liveAbbrM; anchors.fill: parent; hoverEnabled: true; onClicked: { paramTab._editActive = false } }
                                }
                            }
                        }

                        // ── Footer: catalogue pending / live info ────────────
                        Rectangle {
                            Layout.fillWidth: true; height: 36; color: "#080b10"
                            visible: !paramTab._liveMode
                            RowLayout {
                                anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                Text {
                                    text: {
                                        var count = paramTab._params.filter(function(p){ return p.pending !== null }).length
                                        return count > 0 ? count + " Parameter ausstehend (nächster Start)" : "Keine ausstehenden Änderungen"
                                    }
                                    color: "#64748b"; font.pixelSize: 10
                                }
                                Item { Layout.fillWidth: true }
                                Rectangle {
                                    width: 120; height: 24; radius: 5
                                    color: clrAllM.containsMouse ? "#450a0a" : "#1a0a0a"; border.color: "#7f1d1d"; border.width: 1
                                    visible: paramTab._params.filter(function(p){ return p.pending !== null }).length > 0
                                    Text { text: "Alle zurücksetzen"; color: "#fca5a5"; font.pixelSize: 10; anchors.centerIn: parent }
                                    MouseArea { id: clrAllM; anchors.fill: parent; hoverEnabled: true
                                        onClicked: {
                                            if (!ok()) return
                                            paramTab._params.forEach(function(p){
                                                if (p.pending !== null) sitl.clearParam(p.name)
                                            })
                                            paramTab._reload()
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 36; color: "#080b10"
                            visible: paramTab._liveMode
                            RowLayout {
                                anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                                Text {
                                    text: {
                                        var n = Object.keys(paramTab._liveParams).length
                                        return n > 0 ? n + " live Parameter von " + (paramTab._liveTargetId || "—") : "Keine live Parameter geladen"
                                    }
                                    color: "#86efac"; font.pixelSize: 10
                                }
                                Item { Layout.fillWidth: true }
                                Rectangle {
                                    width: 80; height: 24; radius: 5
                                    visible: Object.keys(paramTab._liveParams).length > 0
                                    color: refreshM.containsMouse ? "#1e3a5f" : "#0d1623"; border.color: "#2563eb"; border.width: 1
                                    Text { text: "Neu laden"; color: "#93c5fd"; font.pixelSize: 10; anchors.centerIn: parent }
                                    MouseArea { id: refreshM; anchors.fill: parent; hoverEnabled: true; onClicked: paramTab._fetchLive() }
                                }
                            }
                        }
                    }

                    Rectangle { width: 1; Layout.fillHeight: true; color: "#2d3748" }
                    ConsolePane { Layout.fillWidth: true; Layout.fillHeight: true }
                }
            }

            // ══════════════════════════════════════════════════════════════════
            // TAB 5 — Gazebo
            // ══════════════════════════════════════════════════════════════════
            Item {
                anchors.fill: parent
                visible: root._tab === 5

                RowLayout {
                    anchors { fill: parent; margins: 0 }
                    spacing: 0

                    ScrollView {
                        Layout.preferredWidth: 380; Layout.fillHeight: true; clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: 364
                            anchors { left: parent.left; leftMargin: 18; top: parent.top; topMargin: 18 }
                            spacing: 16

                            // Availability badges
                            Row { spacing: 10
                                Rectangle {
                                    width: gzRow.implicitWidth + 14; height: 22; radius: 11
                                    color: (ok() && sitl.isGazeboAvailable()) ? "#0d2117" : "#1a0f0f"
                                    border.color: (ok() && sitl.isGazeboAvailable()) ? "#22c55e" : "#ef4444"; border.width: 1
                                    Row { id: gzRow; anchors.centerIn: parent; spacing: 5
                                        Rectangle { width: 7; height: 7; radius: 3.5; color: (ok() && sitl.isGazeboAvailable()) ? "#22c55e" : "#ef4444"; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: "gz CLI"; color: (ok() && sitl.isGazeboAvailable()) ? "#86efac" : "#fca5a5"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                                    }
                                }
                                Rectangle {
                                    width: gstRow.implicitWidth + 14; height: 22; radius: 11
                                    color: (ok() && sitl.isGstAvailable()) ? "#0d2117" : "#1a0f0f"
                                    border.color: (ok() && sitl.isGstAvailable()) ? "#22c55e" : "#ef4444"; border.width: 1
                                    Row { id: gstRow; anchors.centerIn: parent; spacing: 5
                                        Rectangle { width: 7; height: 7; radius: 3.5; color: (ok() && sitl.isGstAvailable()) ? "#22c55e" : "#ef4444"; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: "gst-launch-1.0"; color: (ok() && sitl.isGstAvailable()) ? "#86efac" : "#fca5a5"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                                    }
                                }
                            }

                            Text { text: "GAZEBO WORKSPACE"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                            // ── Gazebo workspace path ─────────────────────────
                            ColumnLayout { Layout.fillWidth: true; spacing: 4
                                Text { text: "Workspace-Pfad (gz sim cwd)"; color: "#64748b"; font.pixelSize: 11 }
                                Rectangle { Layout.fillWidth: true; height: 34; radius: 6; color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    RowLayout {
                                        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                                        TextInput {
                                            id: gzWsPathField
                                            Layout.fillWidth: true
                                            text: "~/gz_ws/src"
                                            verticalAlignment: TextInput.AlignVCenter
                                            color: "#38bdf8"; font.pixelSize: 12; font.family: "Consolas"
                                            onEditingFinished: { if (ok()) sitl.setGzWsPath(text.trim()) }
                                        }
                                    }
                                }
                                Text {
                                    text: "gz sim wird in diesem Ordner gestartet — relative World-Pfade werden von hier aufgelöst"
                                    color: "#475569"; font.pixelSize: 9; wrapMode: Text.WordWrap; Layout.fillWidth: true
                                }
                            }

                            Text { text: "GAZEBO KONFIGURATION"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                            ColumnLayout { Layout.fillWidth: true; spacing: 4
                                Text { text: "World (.sdf)"; color: "#64748b"; font.pixelSize: 11 }
                                Rectangle { Layout.fillWidth: true; height: 34; radius: 6; color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    TextInput { id: gzWorldField; text: "iris_runway.sdf"; anchors.fill: parent; anchors.leftMargin: 10; verticalAlignment: TextInput.AlignVCenter; color: "#e2e8f0"; font.pixelSize: 12; font.family: "Consolas" } }
                            }

                            GridLayout { Layout.fillWidth: true; columns: 2; columnSpacing: 10; rowSpacing: 6
                                Text { text: "Verbosity"; color: "#64748b"; font.pixelSize: 11 }
                                Text { text: "SITL Frame"; color: "#64748b"; font.pixelSize: 11 }
                                ComboBox {
                                    id: gzVerbosityCombo
                                    Layout.fillWidth: true; height: 32; model: ["1","2","3","4"]; currentIndex: 3
                                    background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                                    contentItem: Text { leftPadding: 8; text: "-v" + gzVerbosityCombo.currentText; color: "#e2e8f0"; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter }
                                    delegate: ItemDelegate {
                                        width: gzVerbosityCombo.width
                                        contentItem: Text { text: modelData; color: "#e2e8f0"; font.pixelSize: 12 }
                                        background: Rectangle { color: hovered ? "#2d3748" : "#1e2535" }
                                    }
                                    popup: Popup {
                                        y: gzVerbosityCombo.height; width: gzVerbosityCombo.width; padding: 0
                                        background: Rectangle { color: "#1e2535"; border.color: "#2d3748"; radius: 5 }
                                        contentItem: ListView { clip: true; implicitHeight: contentHeight; model: gzVerbosityCombo.delegateModel }
                                    }
                                }
                                Rectangle { Layout.fillWidth: true; height: 32; radius: 5; color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    TextInput { id: gzFrameField; text: "gazebo-iris"; anchors.fill: parent; anchors.leftMargin: 10; verticalAlignment: TextInput.AlignVCenter; color: "#e2e8f0"; font.pixelSize: 12; font.family: "Consolas" } }
                            }

                            // Commands preview
                            Rectangle {
                                Layout.fillWidth: true; height: gzCmdsText.implicitHeight + 14; radius: 6
                                color: "#080b10"; border.color: "#1e2535"; border.width: 1
                                Text {
                                    id: gzCmdsText
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                                    text: "# Terminal 1 — Gazebo:\ngz sim -v" + gzVerbosityCombo.currentText + " -r " + (gzWorldField.text || "iris_runway.sdf") +
                                          "\n\n# Terminal 2 — SITL:\npython3 Tools/autotest/sim_vehicle.py \\\n  -v ArduCopter -f " + (gzFrameField.text || "gazebo-iris") + " \\\n  --model JSON --map --console"
                                    color: "#38bdf8"; font.family: "Consolas"; font.pixelSize: 10; lineHeight: 1.7
                                }
                            }

                            Row { spacing: 8
                                Rectangle {
                                    width: 140; height: 36; radius: 7
                                    color: gzStartM.containsMouse ? "#1e3a5f" : "#0d1623"; border.color: "#2563eb"; border.width: 1
                                    Text { text: "▶ Start Gazebo"; color: "#93c5fd"; font.pixelSize: 12; font.weight: Font.Bold; anchors.centerIn: parent }
                                    MouseArea { id: gzStartM; anchors.fill: parent; hoverEnabled: true
                                        onClicked: {
                                            if (!ok()) return
                                            sitl.launchGazebo(JSON.stringify({
                                                world:      gzWorldField.text.trim(),
                                                verbosity:  parseInt(gzVerbosityCombo.currentText) || 4,
                                                gz_ws_path: gzWsPathField.text.trim()
                                            }))
                                        }
                                    }
                                }
                                Rectangle {
                                    width: 160; height: 36; radius: 7
                                    color: gzSitlM.containsMouse ? "#15803d" : "#166534"; border.color: "#22c55e"; border.width: 1
                                    Text { text: "▶ Start SITL (Gazebo)"; color: "#bbf7d0"; font.pixelSize: 12; font.weight: Font.Bold; anchors.centerIn: parent }
                                    MouseArea { id: gzSitlM; anchors.fill: parent; hoverEnabled: true; enabled: root._repoValid
                                        onClicked: {
                                            if (!ok()) return
                                            sitl.launchSimVehicle(JSON.stringify({ vehicle: "ArduCopter", frame: gzFrameField.text.trim(), extra_args: "--model JSON", use_map: true, use_console: true }))
                                        }
                                    }
                                }
                            }

                            // ── In-App Video Stream ───────────────────────────
                            Rectangle { Layout.fillWidth: true; height: 1; color: "#2d3748"; Layout.topMargin: 4 }
                            Text { text: "IN-APP VIDEO STREAM"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                            // ── Streaming Schritt-für-Schritt ─────────────────
                            Rectangle {
                                Layout.fillWidth: true; height: streamHintCol.implicitHeight + 16; radius: 6
                                color: "#090e1a"; border.color: "#1e3a5f"; border.width: 1
                                ColumnLayout {
                                    id: streamHintCol
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                                    spacing: 5
                                    Text { text: "Schritte zum Aktivieren des Video-Streams"; color: "#38bdf8"; font.pixelSize: 10; font.weight: Font.Bold }
                                    Text { text: "① Gazebo starten (oben)"; color: "#64748b"; font.pixelSize: 10 }
                                    Text { text: "② Topics prüfen → Button unten"; color: "#64748b"; font.pixelSize: 10 }
                                    Text { text: "③ enable_streaming aktivieren → Topic-Feld + Button unten"; color: "#64748b"; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Text { text: "④ GStreamer Preview starten → Port 5600"; color: "#64748b"; font.pixelSize: 10 }
                                }
                            }

                            // ── Schritt 2: Topics prüfen ─────────────────────
                            ColumnLayout { Layout.fillWidth: true; spacing: 4
                                Text { text: "② Topics prüfen"; color: "#475569"; font.pixelSize: 10; font.weight: Font.Bold }
                                Row { spacing: 8
                                    Rectangle {
                                        width: 200; height: 30; radius: 6
                                        color: gzTopicsM.containsMouse ? "#1e3a5f" : "#0d1e30"; border.color: "#2563eb"; border.width: 1
                                        Text { text: "gz topic -l | grep streaming"; color: "#93c5fd"; font.pixelSize: 10; font.family: "Consolas"; anchors.centerIn: parent }
                                        MouseArea { id: gzTopicsM; anchors.fill: parent; hoverEnabled: true
                                            onClicked: { if (ok()) sitl.runGzTopicList() }
                                        }
                                    }
                                }
                            }

                            // ── Schritt 3: enable_streaming aktivieren ────────
                            ColumnLayout { Layout.fillWidth: true; spacing: 4
                                Text { text: "③ Streaming aktivieren"; color: "#475569"; font.pixelSize: 10; font.weight: Font.Bold }
                                Text {
                                    text: "Topic-Pfad (World-Name und Modell anpassen):"
                                    color: "#64748b"; font.pixelSize: 10
                                }
                                Rectangle { Layout.fillWidth: true; height: 34; radius: 6; color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    TextInput {
                                        id: gzEnableStreamingField
                                        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                                        verticalAlignment: TextInput.AlignVCenter
                                        color: "#38bdf8"; font.pixelSize: 10; font.family: "Consolas"
                                        text: "/world/iris_runway/model/iris_with_gimbal/model/gimbal/link/pitch_link/sensor/camera/image/enable_streaming"
                                        wrapMode: TextInput.NoWrap
                                        Text { text: "Topic-Pfad…"; color: "#374151"; font: parent.font; visible: parent.text.length === 0 }
                                    }
                                }
                                Row { spacing: 8
                                    Rectangle {
                                        width: 180; height: 30; radius: 6
                                        color: enableStreamM.containsMouse ? "#15803d" : "#166534"; border.color: "#22c55e"; border.width: 1
                                        Text { text: "Streaming aktivieren"; color: "#bbf7d0"; font.pixelSize: 10; font.weight: Font.Bold; anchors.centerIn: parent }
                                        MouseArea { id: enableStreamM; anchors.fill: parent; hoverEnabled: true
                                            enabled: gzEnableStreamingField.text.trim() !== ""
                                            onClicked: { if (ok()) sitl.enableStreaming(gzEnableStreamingField.text.trim()) }
                                        }
                                    }
                                    // Copy to clipboard hint
                                    Text {
                                        text: "→ gz.msgs.Boolean data:1"
                                        color: "#475569"; font.pixelSize: 9; font.family: "Consolas"
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                            }

                            GridLayout { Layout.fillWidth: true; columns: 2; columnSpacing: 10; rowSpacing: 6
                                Text { text: "Stream URL"; color: "#64748b"; font.pixelSize: 11 }
                                Text { text: "Ziel"; color: "#64748b"; font.pixelSize: 11 }

                                Rectangle { Layout.fillWidth: true; height: 32; radius: 5; color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    TextInput { id: gzStreamUrlField; text: "udp://0.0.0.0:" + (gzStreamPortField.text || "5600"); anchors.fill: parent; anchors.leftMargin: 10; verticalAlignment: TextInput.AlignVCenter; color: "#38bdf8"; font.pixelSize: 12; font.family: "Consolas" } }

                                Row { spacing: 12
                                    RadioButton { id: gzTargetMapRadio; text: "Map (PIP)"; contentItem: Text { text: parent.text; color: "#e2e8f0"; font.pixelSize: 11; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                                    RadioButton { id: gzTargetGimbalRadio; text: "Gimbal"; checked: true; contentItem: Text { text: parent.text; color: "#e2e8f0"; font.pixelSize: 11; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                                }

                                Text { text: "UDP Port"; color: "#64748b"; font.pixelSize: 11 }
                                Item {}  // spacer

                                Rectangle { Layout.fillWidth: true; height: 32; radius: 5; color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    TextInput { id: gzStreamPortField; text: "5600"; anchors.fill: parent; anchors.leftMargin: 10; verticalAlignment: TextInput.AlignVCenter; color: "#e2e8f0"; font.pixelSize: 12; font.family: "Consolas"
                                        onTextChanged: gzStreamUrlField.text = "udp://0.0.0.0:" + text } }
                                Item {}  // spacer
                            }

                            // Stream status
                            property var _streamStatus: {
                                if (!vsOk()) return {}
                                var did = typeof Cmp !== "undefined" && Cmp.AppState ? Cmp.AppState.selectedDroneId : ""
                                did = did || "sitl_drone"
                                return videoStream.getVideoStatus(did) || {}
                            }

                            // ── Schritt 4: GStreamer Befehl-Preview ───────────
                            Rectangle {
                                Layout.fillWidth: true; height: gstCmdPreview.implicitHeight + 14; radius: 6
                                color: "#080b10"; border.color: "#1e2535"; border.width: 1
                                Text {
                                    id: gstCmdPreview
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                                    text: "gst-launch-1.0 -v udpsrc port=" + (gzStreamPortField.text || "5600") +
                                          " caps='application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264'" +
                                          " ! rtph264depay ! avdec_h264 ! videoconvert ! autovideosink sync=false"
                                    color: "#38bdf8"; font.family: "Consolas"; font.pixelSize: 9
                                    wrapMode: Text.WrapAnywhere; lineHeight: 1.5
                                }
                            }

                            Row { spacing: 8
                                Rectangle {
                                    width: 180; height: 36; radius: 7
                                    color: gzStreamM.containsMouse ? "#15803d" : "#166534"; border.color: "#22c55e"; border.width: 1
                                    Text { text: "▶ Stream in GCS anzeigen"; color: "#bbf7d0"; font.pixelSize: 11; font.weight: Font.Bold; anchors.centerIn: parent }
                                    MouseArea { id: gzStreamM; anchors.fill: parent; hoverEnabled: true
                                        onClicked: {
                                            if (!vsOk()) return
                                            var did = (typeof Cmp !== "undefined" && Cmp.AppState && Cmp.AppState.selectedDroneId) ? Cmp.AppState.selectedDroneId : "sitl_drone"
                                            var target = gzTargetMapRadio.checked ? "map" : "gimbal"
                                            videoStream.startStream(gzStreamUrlField.text.trim(), did, target)
                                        }
                                    }
                                }
                                Rectangle {
                                    width: 72; height: 36; radius: 7
                                    color: gzStopStreamM.containsMouse ? "#7f1d1d" : "#1e2535"; border.color: "#ef4444"; border.width: 1
                                    Text { text: "■ Stop"; color: "#fca5a5"; font.pixelSize: 11; font.weight: Font.Bold; anchors.centerIn: parent }
                                    MouseArea { id: gzStopStreamM; anchors.fill: parent; hoverEnabled: true
                                        onClicked: {
                                            if (!vsOk()) return
                                            var did = (typeof Cmp !== "undefined" && Cmp.AppState && Cmp.AppState.selectedDroneId) ? Cmp.AppState.selectedDroneId : "sitl_drone"
                                            videoStream.stopStream(did)
                                        }
                                    }
                                }
                                Rectangle {
                                    width: 100; height: 36; radius: 7
                                    color: gstPrevM.containsMouse ? "#1e3a5f" : "#0d1623"; border.color: "#2563eb"; border.width: 1
                                    Text { text: "▶ GSt Terminal"; color: "#93c5fd"; font.pixelSize: 11; anchors.centerIn: parent }
                                    MouseArea { id: gstPrevM; anchors.fill: parent; hoverEnabled: true
                                        onClicked: { if (ok()) sitl.launchGstPreview("127.0.0.1", parseInt(gzStreamPortField.text) || 5600) } }
                                }
                            }

                            Item { height: 12 }
                        }
                    }

                    Rectangle { width: 1; Layout.fillHeight: true; color: "#2d3748" }
                    ConsolePane { Layout.fillWidth: true; Layout.fillHeight: true }
                }
            }

            // ══════════════════════════════════════════════════════════════════
            // TAB 6 — Debug & MAVProxy
            // ══════════════════════════════════════════════════════════════════
            Item {
                anchors.fill: parent
                visible: root._tab === 6

                RowLayout {
                    anchors { fill: parent; margins: 0 }
                    spacing: 0

                    ScrollView {
                        Layout.preferredWidth: 380; Layout.fillHeight: true; clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: 364
                            anchors { left: parent.left; leftMargin: 18; top: parent.top; topMargin: 18 }
                            spacing: 16

                            Text { text: "MAVPROXY"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                            ColumnLayout { Layout.fillWidth: true; spacing: 4
                                Text { text: "Master"; color: "#64748b"; font.pixelSize: 11 }
                                Rectangle { Layout.fillWidth: true; height: 32; radius: 5; color: "#1e2535"; border.color: "#2d3748"; border.width: 1
                                    TextInput { id: mavMasterField; text: "tcp:127.0.0.1:5760"; anchors.fill: parent; anchors.leftMargin: 10; verticalAlignment: TextInput.AlignVCenter; color: "#38bdf8"; font.pixelSize: 12; font.family: "Consolas" } }
                            }

                            Row { spacing: 12
                                CheckBox { id: mavMapCheck; checked: true; text: "--map"; contentItem: Text { text: parent.text; color: "#94a3b8"; font.pixelSize: 11; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                                CheckBox { id: mavConsoleCheck; checked: true; text: "--console"; contentItem: Text { text: parent.text; color: "#94a3b8"; font.pixelSize: 11; leftPadding: parent.indicator.width + 4; verticalAlignment: Text.AlignVCenter } }
                            }

                            // Buttons row 1
                            Row { spacing: 8
                                Rectangle {
                                    width: 160; height: 34; radius: 6
                                    color: mavStartM.containsMouse ? "#1e3a5f" : "#0d1623"; border.color: "#2563eb"; border.width: 1
                                    Text { text: "▶ MAVProxy starten"; color: "#93c5fd"; font.pixelSize: 11; font.weight: Font.Bold; anchors.centerIn: parent }
                                    MouseArea { id: mavStartM; anchors.fill: parent; hoverEnabled: true
                                        onClicked: { if (ok()) sitl.launchMavproxy(JSON.stringify({ master: mavMasterField.text, use_map: mavMapCheck.checked, use_console: mavConsoleCheck.checked })) } }
                                }
                                Rectangle {
                                    width: 148; height: 34; radius: 6
                                    color: jsM.containsMouse ? "#1e3a5f" : "#0d1623"; border.color: "#7c5cd8"; border.width: 1
                                    Row { anchors.centerIn: parent; spacing: 6
                                        Rectangle { width: 7; height: 7; radius: 3.5; color: (ok() && sitl.isJoystickAvailable()) ? "#22c55e" : "#64748b"; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: "Joystick laden"; color: "#c4b5fd"; font.pixelSize: 11; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
                                    }
                                    MouseArea { id: jsM; anchors.fill: parent; hoverEnabled: true
                                        onClicked: { if (ok()) sitl.launchMavproxyWithJoystick() } }
                                }
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: "#2d3748" }

                            // ── PreArm Quick-Fix Sektion ──────────────────────
                            Text { text: "PREARM FIXES"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                            // Info: what this section does
                            Rectangle {
                                Layout.fillWidth: true; height: preArmInfoRow.implicitHeight + 12; radius: 5
                                color: "#0a0f1a"; border.color: "#1e3a5f"; border.width: 1
                                Row {
                                    id: preArmInfoRow
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                                    spacing: 6
                                    Text { text: "ⓘ"; color: "#38bdf8"; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                                    Text {
                                        text: "Öffnet MAVProxy mit vorgefertigtem Script. SITL muss laufen."
                                        color: "#64748b"; font.pixelSize: 10; wrapMode: Text.WordWrap
                                        width: parent.parent.width - 36
                                    }
                                }
                            }

                            // Fix cards
                            Repeater {
                                id: preArmFixList
                                model: ok() ? sitl.getPreArmFixes() : []

                                delegate: Rectangle {
                                    Layout.fillWidth: true; height: fixCardCol.implicitHeight + 14; radius: 6
                                    color: "#0d1117"; border.color: "#2d3748"; border.width: 1

                                    ColumnLayout {
                                        id: fixCardCol
                                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                                        spacing: 4

                                        // Label + button
                                        RowLayout {
                                            Layout.fillWidth: true; spacing: 8

                                            Text {
                                                text: modelData.label
                                                color: "#e2e8f0"; font.pixelSize: 11; font.weight: Font.Bold
                                                Layout.fillWidth: true; elide: Text.ElideRight
                                            }

                                            Rectangle {
                                                width: 56; height: 26; radius: 5
                                                color: fixM.containsMouse ? "#92400e" : "#78350f"
                                                border.color: "#f97316"; border.width: 1
                                                Text { text: "Fix ▶"; color: "#fed7aa"; font.pixelSize: 10; font.weight: Font.Bold; anchors.centerIn: parent }
                                                MouseArea {
                                                    id: fixM; anchors.fill: parent; hoverEnabled: true
                                                    onClicked: {
                                                        if (!ok()) return
                                                        sitl.launchMavproxyFix(modelData.id, mavMasterField.text)
                                                    }
                                                }
                                            }
                                        }

                                        // Commands preview
                                        Text {
                                            text: (modelData.commands || []).join("  →  ")
                                            color: "#38bdf8"; font.pixelSize: 10; font.family: "Consolas"
                                            Layout.fillWidth: true; elide: Text.ElideRight
                                        }

                                        // Description
                                        Text {
                                            text: (modelData.desc || "").split("\n")[0]
                                            color: "#475569"; font.pixelSize: 10
                                            Layout.fillWidth: true; elide: Text.ElideRight
                                            visible: text.length > 0
                                        }
                                    }
                                }
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: "#2d3748" }
                            Text { text: "GRAPH / TELEMETRIE"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                            Flow { Layout.fillWidth: true; spacing: 6
                                Repeater {
                                    model: ["VFR_HUD.alt", "VFR_HUD.airspeed", "ATTITUDE.roll", "ATTITUDE.pitch", "GPS_RAW_INT.vel"]
                                    delegate: Rectangle {
                                        width: graphLbl.implicitWidth + 18; height: 28; radius: 5
                                        color: graphM.containsMouse ? "#1e2535" : "#111827"; border.color: "#2d3748"; border.width: 1
                                        Text { id: graphLbl; text: modelData; color: "#94a3b8"; font.pixelSize: 10; font.family: "Consolas"; anchors.centerIn: parent }
                                        MouseArea { id: graphM; anchors.fill: parent; hoverEnabled: true
                                            onClicked: { if (ok()) sitl.launchMavproxyGraph(modelData) } }
                                    }
                                }
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: "#2d3748" }
                            Text { text: "TRACE LOG (letzte Events)"; font.pixelSize: 10; font.weight: Font.Bold; color: "#94a3b8"; font.letterSpacing: 0.8 }

                            ListView {
                                Layout.fillWidth: true
                                height: 180; clip: true
                                model: ok() ? sitl.getRecentTraceLogs(30) : []
                                spacing: 1

                                Timer { interval: 4000; running: root._tab === 6; repeat: true
                                    onTriggered: parent.model = ok() ? sitl.getRecentTraceLogs(30) : [] }

                                delegate: Rectangle {
                                    width: parent ? parent.width : 0; height: 28; radius: 3
                                    color: index % 2 === 0 ? "#0d1117" : "#111827"
                                    Row {
                                        anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; anchors.leftMargin: 8
                                        spacing: 8
                                        Text {
                                            text: (modelData.ts || "").substring(11, 19)
                                            color: "#475569"; font.pixelSize: 10; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter
                                        }
                                        Text {
                                            text: (modelData.type || "").replace("sitl/", "")
                                            color: "#f97316"; font.pixelSize: 10; font.family: "Consolas"; anchors.verticalCenter: parent.verticalCenter; width: 120
                                        }
                                        Text {
                                            text: JSON.stringify(modelData.data || {})
                                            color: "#64748b"; font.pixelSize: 10; font.family: "Consolas"
                                            elide: Text.ElideRight; width: 180; anchors.verticalCenter: parent.verticalCenter
                                        }
                                    }
                                }

                                Text { anchors.centerIn: parent; text: "Keine Trace-Events (Trace-Session starten im Log-Tab)"; color: "#1f2937"; font.pixelSize: 11; visible: parent.count === 0 }
                            }

                            Item { height: 12 }
                        }
                    }

                    Rectangle { width: 1; Layout.fillHeight: true; color: "#2d3748" }
                    ConsolePane { Layout.fillWidth: true; Layout.fillHeight: true }
                }
            }
        }
    }

    // ── File dialogs ──────────────────────────────────────────────────────────
    FolderDialog {
        id: repoFolderDialog
        title: "ArduPilot Repo-Pfad wählen"
        onAccepted: {
            var p = selectedFolder.toString().replace("file://", "")
            repoPathField.text = p
            if (ok()) sitl.setRepoPath(p)
        }
    }

    FolderDialog {
        id: swarmFileDlg
        title: "Swarm-Config-Datei wählen"
        onAccepted: swarmFileField.text = selectedFolder.toString().replace("file://", "")
    }

    // ── Peripheral card section component ─────────────────────────────────────
    // Renders all peripheral cards for a given category
    component PeripheralSection: ColumnLayout {
        property var    catalogue: []
        property string category:  ""

        Layout.fillWidth: true
        spacing: 6

        Repeater {
            model: {
                var res = []
                for (var i = 0; i < catalogue.length; i++) {
                    if (catalogue[i].category === category) res.push(catalogue[i])
                }
                return res
            }

            delegate: Rectangle {
                Layout.fillWidth: true
                height: periCardCol.implicitHeight + 16
                radius: 7
                color: modelData.enabled ? "#0d2117" : "#0d1117"
                border.color: modelData.enabled ? "#166534" : "#1e2535"
                border.width: 1

                ColumnLayout {
                    id: periCardCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 6

                    // Header row: toggle + label + hint
                    RowLayout {
                        Layout.fillWidth: true; spacing: 10

                        // Toggle switch (custom)
                        Rectangle {
                            width: 36; height: 20; radius: 10
                            color: modelData.enabled ? "#166534" : "#1e2535"
                            border.color: modelData.enabled ? "#22c55e" : "#2d3748"; border.width: 1
                            Behavior on color { ColorAnimation { duration: 120 } }

                            Rectangle {
                                width: 14; height: 14; radius: 7
                                anchors.verticalCenter: parent.verticalCenter
                                x: modelData.enabled ? 19 : 3
                                color: modelData.enabled ? "#22c55e" : "#64748b"
                                Behavior on x { NumberAnimation { duration: 120 } }
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    if (!ok()) return
                                    var did = modelData.id
                                    if (modelData.enabled) {
                                        sitl.removePeripheralDevice(did)
                                    } else {
                                        sitl.setPeripheralDevice(did, JSON.stringify({
                                            enabled: true,
                                            params: modelData.params || {}
                                        }))
                                    }
                                }
                            }
                        }

                        // Label
                        Text {
                            text: modelData.label
                            color: modelData.enabled ? "#86efac" : "#94a3b8"
                            font.pixelSize: 12; font.weight: Font.Medium
                            Layout.fillWidth: true
                        }

                        // Enabled badge
                        Rectangle {
                            visible: modelData.enabled
                            width: 56; height: 18; radius: 9
                            color: "#0d2117"; border.color: "#22c55e"; border.width: 1
                            Text { text: "Aktiv"; color: "#4ade80"; font.pixelSize: 9; font.weight: Font.Bold; anchors.centerIn: parent }
                        }
                    }

                    // Hint text
                    Text {
                        text: modelData.hint || ""
                        color: "#475569"; font.pixelSize: 10; font.family: "Consolas"
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        visible: text.length > 0
                    }

                    // Active param list (shown when enabled)
                    Flow {
                        Layout.fillWidth: true; spacing: 4
                        visible: modelData.enabled && Object.keys(modelData.activeParams || {}).length > 0

                        Repeater {
                            model: {
                                var p = modelData.activeParams || {}
                                return Object.keys(p).map(function(k){ return k + "=" + p[k] })
                            }
                            delegate: Rectangle {
                                height: 18; width: paramChipLbl.implicitWidth + 12; radius: 4
                                color: "#0a1628"; border.color: "#1e3a5f"; border.width: 1
                                Text {
                                    id: paramChipLbl
                                    text: modelData
                                    color: "#60a5fa"; font.pixelSize: 9; font.family: "Consolas"
                                    anchors.centerIn: parent
                                }
                            }
                        }
                    }

                    // Restart needed warning
                    Rectangle {
                        visible: modelData.enabled && (modelData.hint || "").toLowerCase().indexOf("restart") >= 0
                        Layout.fillWidth: true; height: 24; radius: 4
                        color: "#1c1400"; border.color: "#f59e0b"; border.width: 1
                        Row {
                            anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; anchors.leftMargin: 8
                            spacing: 6
                            Text { text: "⚠"; font.pixelSize: 11; color: "#f59e0b"; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: "Neustart erforderlich"; color: "#fde68a"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }
            }
        }
    }

    // ── Shared console pane component ─────────────────────────────────────────
    component ConsolePane: Rectangle {
        color: "#080b10"

        ColumnLayout {
            anchors.fill: parent; spacing: 0

            Rectangle {
                Layout.fillWidth: true; height: 30; color: "#0d1117"
                RowLayout { anchors { fill: parent; leftMargin: 12; rightMargin: 8 }
                    Text { text: "Console"; font.pixelSize: 10; font.weight: Font.Medium; color: "#64748b"; font.letterSpacing: 0.5 }
                    Item { Layout.fillWidth: true }
                    Rectangle { width: 50; height: 18; radius: 4; color: clrConsM.containsMouse ? "#1e2535" : "transparent"; border.color: "#2d3748"; border.width: 1
                        Text { text: "Clear"; color: "#64748b"; font.pixelSize: 10; anchors.centerIn: parent }
                        MouseArea { id: clrConsM; anchors.fill: parent; hoverEnabled: true; onClicked: consoleModel.clear() } }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#1e2535" }

            ListView {
                id: consoleView
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true; model: consoleModel; spacing: 0
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                onCountChanged: Qt.callLater(positionViewAtEnd)

                delegate: Text {
                    width: consoleView.width; leftPadding: 12; rightPadding: 8
                    text: modelData.text
                    color: {
                        var t = modelData.text || ""
                        if (t.indexOf("ERROR") >= 0) return "#f87171"
                        if (t.indexOf("WARN")  >= 0) return "#fbbf24"
                        if (t.indexOf("[SITL") === 0) return "#4ade80"
                        return "#64748b"
                    }
                    font.pixelSize: 11; font.family: "Consolas"
                    wrapMode: Text.NoWrap; topPadding: 1; bottomPadding: 1
                }

                Text { anchors.centerIn: parent; text: "Keine Ausgabe"; color: "#1f2937"; font.pixelSize: 12; visible: consoleModel.count === 0 }
            }
        }
    }
}
