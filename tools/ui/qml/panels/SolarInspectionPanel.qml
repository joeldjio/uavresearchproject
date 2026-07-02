import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components" as Cmp

// Solar Inspection Mission Wizard - 4 Steps
Rectangle {
    id: root
    width: parent.width
    height: Math.max(600, contentColumn.height)
    color: "#0f172a"
    
    Component.onCompleted: {
        console.log("[SolarInspectionPanel] Loaded! Width:", width, "Height:", height, "Column height:", contentColumn.height)
        checkCapabilities()
    }

    // Re-run the capability check whenever the drone type changes.
    // SwarmContext.setDroneType emits telemetryUpdated -- catching it here
    // means the wizard unlocks immediately after the user picks "Observation".
    Connections {
        target: typeof swarm !== "undefined" ? swarm : null
        function onTelemetryUpdated() { root.checkCapabilities() }
    }

    property int currentStep: 0
    property var solarRows: []
    property real rowSpacing: 2.0
    property string panelOrientation: "landscape"
    property real altitude: 50.0
    property real speed: 5.0
    property real cameraAngle: -45.0
    property string triggerMode: "distance"
    property real triggerInterval: 10.0
    property real forwardOverlap: 70.0
    property real sideOverlap: 60.0
    
    // Preview data from backend
    property var previewData: null
    property bool previewLoading: false
    property string previewError: ""
    property bool uploadInProgress: false
    property string uploadError: ""
    
    // Calculated properties
    property real cameraHFOV: 90.0  // Horizontal FOV in degrees
    property real cameraVFOV: 60.0  // Vertical FOV in degrees
    property real sensorWidth: 6.17  // mm (typical for 1/2.3" sensor)
    property real sensorHeight: 4.55 // mm
    property real focalLength: 4.5   // mm (typical for drone camera)
    
    // GSD calculation (Ground Sample Distance in cm/pixel)
    property real calculatedGSD: {
        // GSD = (sensor_width * altitude * 100) / (focal_length * image_width)
        // Assuming 1920x1080 resolution
        var imageWidth = 1920
        return (sensorWidth * altitude * 100) / (focalLength * imageWidth)
    }
    
    // Coverage area per image (in meters)
    property real coverageWidth: {
        // Width = 2 * altitude * tan(HFOV/2)
        return 2 * altitude * Math.tan(cameraHFOV * Math.PI / 360)
    }
    
    property real coverageHeight: {
        // Height = 2 * altitude * tan(VFOV/2)
        return 2 * altitude * Math.tan(cameraVFOV * Math.PI / 360)
    }
    
    // Capability check results
    property var capabilityCheck: null
    property bool capabilitiesSatisfied: false
    property var missingCapabilities: []
    property var capabilityWarnings: []

    readonly property var stepTitles: [
        qsTr("Setup & Hardware Check"),
        qsTr("Site Definition"),
        qsTr("Flight & Camera Settings"),
        qsTr("Preview & Upload")
    ]

    function nextStep() {
        if (currentStep < 3) currentStep++
    }

    function prevStep() {
        if (currentStep > 0) currentStep--
    }

    function reset() {
        currentStep = 0
        solarRows = []
        rowSpacing = 2.0
        panelOrientation = "landscape"
        altitude = 50.0
        speed = 5.0
        cameraAngle = -45.0
        triggerMode = "distance"
        triggerInterval = 10.0
        forwardOverlap = 70.0
        sideOverlap = 60.0
        capabilityCheck = null
        capabilitiesSatisfied = false
        missingCapabilities = []
        capabilityWarnings = []
        previewData = null
        previewLoading = false
        previewError = ""
        uploadInProgress = false
        uploadError = ""
    }
    
    Component.onDestruction: {
        // Clear solar preview overlays when wizard is closed
        if (typeof mapLoader !== "undefined" && mapLoader && mapLoader.item) {
            if (mapLoader.item.clearSolarPreviewOverlays)
                mapLoader.item.clearSolarPreviewOverlays()
        }
    }

    function generatePreview() {
        if (typeof mission === 'undefined') {
            previewError = "Mission context not available"
            return
        }

        previewLoading = true
        previewError = ""

        var params = {
            "rowSpacing": rowSpacing,
            "panelOrientation": panelOrientation,
            "altitude": altitude,
            "speed": speed,
            "gimbalAngle": cameraAngle,
            "triggerMode": triggerMode,
            "triggerDistance": triggerMode === "distance" ? triggerInterval : 0,
            "triggerTime": triggerMode === "time" ? triggerInterval : 0,
            "forwardOverlap": forwardOverlap,
            "sideOverlap": sideOverlap,
            "cameraHFOV": cameraHFOV,
            "cameraVFOV": cameraVFOV,
            "addRTL": true,
            "thermalEnabled": capabilityCheck && capabilityCheck.capabilities && capabilityCheck.capabilities.hasThermalCamera
        }

        console.log("Generating solar preview with params:", JSON.stringify(params))

        try {
            previewData = mission.generateSolarPreview(params)
            previewLoading = false

            if (previewData && !previewData.valid) {
                previewError = previewData.errors ? previewData.errors.join(", ") : "Invalid mission configuration"
            }

            console.log("Solar preview generated:", JSON.stringify(previewData))
            // Map overlays are updated via mission.solarPreviewChanged signal in main.qml
        } catch (e) {
            previewLoading = false
            previewError = "Failed to generate preview: " + e.toString()
            console.error("Solar preview generation error:", e)
        }
    }
    
    function uploadMission() {
        if (!previewData || !previewData.valid) {
            uploadError = "Cannot upload invalid mission"
            return
        }
        if (typeof mission === 'undefined' || !mission) {
            uploadError = "Mission context not available"
            return
        }

        uploadInProgress = true
        uploadError = ""

        console.log("Uploading solar mission...")
        try {
            mission.uploadSolarMission()
            // uploadInProgress cleared via missionUploadFinished signal — not here.
        } catch (e) {
            uploadInProgress = false
            uploadError = "Upload failed: " + e.toString()
            console.error("Solar upload error:", e)
        }
    }
    
    function checkCapabilities() {
        if (typeof capabilities === 'undefined') {
            console.warn("Capabilities context not available")
            capabilitiesSatisfied = false
            return
        }
        
        // Check mode requirements for the globally selected drone when possible.
        var did = Cmp.AppState.selectedDroneId || ""
        capabilityCheck = did !== "" && capabilities.checkDroneModeRequirements
                          ? capabilities.checkDroneModeRequirements(did, "solar")
                          : capabilities.checkModeRequirements("solar")
        
        if (capabilityCheck) {
            capabilitiesSatisfied = capabilityCheck.satisfied || false
            missingCapabilities = capabilityCheck.missing || []
            capabilityWarnings = capabilityCheck.warnings || []
            
            console.log("Solar capability check:", JSON.stringify(capabilityCheck))
        }
    }

    Column {
        id: contentColumn
        width: parent.width
        spacing: 0

        // ── Header ──────────────────────────────────────────────────
        Rectangle {
            width: parent.width
            height: 60
            color: "#1a2035"
            border.color: "#2d3748"
            border.width: 1

            Row {
                anchors { fill: parent; leftMargin: 20; rightMargin: 20 }
                spacing: 12

                Text {
                    text: "☀️"
                    font.pixelSize: 24
                    anchors.verticalCenter: parent.verticalCenter
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        text: qsTr("SOLAR INSPECTION WIZARD")
                        color: "#e2e8f0"
                        font.pixelSize: 14
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }

                    Text {
                        text: (currentStep >= 0 && currentStep < stepTitles.length)
                              ? stepTitles[currentStep] : ""
                        color: "#94a3b8"
                        font.pixelSize: 11
                    }
                }

                Item { Layout.fillWidth: true; width: 1; height: 1 }

                // Step indicator
                Row {
                    spacing: 8
                    anchors.verticalCenter: parent.verticalCenter

                    Repeater {
                        model: 4
                        delegate: Rectangle {
                            width: 32
                            height: 32
                            radius: 16
                            color: index === currentStep ? "#f59e0b" : (index < currentStep ? "#10b981" : "#334155")
                            border.color: index === currentStep ? "#fbbf24" : "transparent"
                            border.width: 2

                            Text {
                                anchors.centerIn: parent
                                text: index < currentStep ? "✓" : (index + 1)
                                color: "#ffffff"
                                font.pixelSize: 14
                                font.weight: Font.Bold
                            }
                        }
                    }
                }
            }
        }

        // ── Content Area ────────────────────────────────────────────
        // No inner ScrollView — outer MissionPanel ScrollView handles scrolling
        // (same pattern as SeedingPanel)
        Loader {
            id: stepLoader
            width: parent.width
            sourceComponent: {
                switch(currentStep) {
                    case 0: return step1Component
                    case 1: return step2Component
                    case 2: return step3Component
                    case 3: return step4Component
                    default: return step1Component
                }
            }
        }

        // ── Footer Navigation ───────────────────────────────────────
        Rectangle {
            width: parent.width
            height: 70
            color: "#1a2035"
            border.color: "#2d3748"
            border.width: 1

            Row {
                anchors { fill: parent; leftMargin: 20; rightMargin: 20 }
                spacing: 12

                Rectangle {
                    width: 120
                    height: 40
                    radius: 6
                    color: backM.containsMouse ? "#374151" : "#1e2535"
                    border.color: "#4b5563"
                    border.width: 1
                    visible: currentStep > 0
                    anchors.verticalCenter: parent.verticalCenter

                    Text {
                        anchors.centerIn: parent
                        text: qsTr("← BACK")
                        color: "#94a3b8"
                        font.pixelSize: 11
                        font.weight: Font.Bold
                    }

                    MouseArea {
                        id: backM
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: prevStep()
                    }
                }

                Item { Layout.fillWidth: true; width: 1; height: 1 }

                Rectangle {
                    width: 120
                    height: 40
                    radius: 6
                    color: {
                        if (currentStep === 0 && !capabilitiesSatisfied) return "#374151"
                        return nextM.containsMouse ? "#1d4ed8" : "#1e3a5f"
                    }
                    border.color: {
                        if (currentStep === 0 && !capabilitiesSatisfied) return "#4b5563"
                        return "#2563eb"
                    }
                    border.width: 1
                    visible: currentStep < 3
                    opacity: (currentStep === 0 && !capabilitiesSatisfied) ? 0.5 : 1.0
                    anchors.verticalCenter: parent.verticalCenter

                    Text {
                        anchors.centerIn: parent
                        text: qsTr("NEXT →")
                        color: {
                            if (currentStep === 0 && !capabilitiesSatisfied) return "#6b7280"
                            return "#93c5fd"
                        }
                        font.pixelSize: 11
                        font.weight: Font.Bold
                    }

                    MouseArea {
                        id: nextM
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: currentStep !== 0 || capabilitiesSatisfied
                        onClicked: nextStep()
                    }
                }

                Rectangle {
                    width: 140
                    height: 40
                    radius: 6
                    color: uploadM.containsMouse ? "#059669" : "#064e3b"
                    border.color: "#10b981"
                    border.width: 1
                    visible: currentStep === 3
                    anchors.verticalCenter: parent.verticalCenter

                    Text {
                        anchors.centerIn: parent
                        text: qsTr("📤 UPLOAD MISSION")
                        color: "#6ee7b7"
                        font.pixelSize: 11
                        font.weight: Font.Bold
                    }

                    MouseArea {
                        id: uploadM
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: !uploadInProgress && previewData && previewData.valid
                        onClicked: uploadMission()
                    }
                }
            }
        }
    }

    // ── Step Components ─────────────────────────────────────────────

    Component {
        id: step1Component
        
        Column {
            width: parent.width
            spacing: 20
            topPadding: 20
            leftPadding: 20
            rightPadding: 20
            bottomPadding: 20

            Text {
                width: parent.width - 40
                text: qsTr("Automated solar panel inspection using camera and gimbal. The drone will fly along solar panel rows, capturing images at optimal angles for defect detection.")
                color: "#94a3b8"
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }

            Rectangle {
                width: parent.width - 40
                height: hwCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1

                Column {
                    id: hwCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 12

                    Text {
                        text: qsTr("HARDWARE STATUS")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }

                    // Camera (Required)
                    Row {
                        width: parent.width
                        spacing: 12
                        Rectangle {
                            width: 24; height: 24; radius: 12
                            color: {
                                if (!capabilityCheck) return "#6b7280"
                                var caps = capabilityCheck.capabilities || {}
                                return caps.hasCamera ? "#10b981" : "#ef4444"
                            }
                            Text {
                                anchors.centerIn: parent
                                text: {
                                    if (!capabilityCheck) return "?"
                                    var caps = capabilityCheck.capabilities || {}
                                    return caps.hasCamera ? "✓" : "✗"
                                }
                                color: "#ffffff"
                                font.pixelSize: 14
                                font.weight: Font.Bold
                            }
                        }
                        Text {
                            text: qsTr("Camera - Required")
                            color: {
                                if (!capabilityCheck) return "#94a3b8"
                                var caps = capabilityCheck.capabilities || {}
                                return caps.hasCamera ? "#e2e8f0" : "#ef4444"
                            }
                            font.pixelSize: 11
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    // Gimbal (Required)
                    Row {
                        width: parent.width
                        spacing: 12
                        Rectangle {
                            width: 24; height: 24; radius: 12
                            color: {
                                if (!capabilityCheck) return "#6b7280"
                                var caps = capabilityCheck.capabilities || {}
                                return caps.hasGimbal ? "#10b981" : "#ef4444"
                            }
                            Text {
                                anchors.centerIn: parent
                                text: {
                                    if (!capabilityCheck) return "?"
                                    var caps = capabilityCheck.capabilities || {}
                                    return caps.hasGimbal ? "✓" : "✗"
                                }
                                color: "#ffffff"
                                font.pixelSize: 14
                                font.weight: Font.Bold
                            }
                        }
                        Text {
                            text: qsTr("Gimbal - Required")
                            color: {
                                if (!capabilityCheck) return "#94a3b8"
                                var caps = capabilityCheck.capabilities || {}
                                return caps.hasGimbal ? "#e2e8f0" : "#ef4444"
                            }
                            font.pixelSize: 11
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    // Thermal Camera (Optional)
                    Row {
                        width: parent.width
                        spacing: 12
                        Rectangle {
                            width: 24; height: 24; radius: 12
                            color: {
                                if (!capabilityCheck) return "#6b7280"
                                var caps = capabilityCheck.capabilities || {}
                                return caps.hasThermalCamera ? "#10b981" : "#f59e0b"
                            }
                            Text {
                                anchors.centerIn: parent
                                text: {
                                    if (!capabilityCheck) return "?"
                                    var caps = capabilityCheck.capabilities || {}
                                    return caps.hasThermalCamera ? "✓" : "⚠"
                                }
                                color: "#ffffff"
                                font.pixelSize: 14
                                font.weight: Font.Bold
                            }
                        }
                        Text {
                            text: qsTr("Thermal Camera - Optional")
                            color: {
                                if (!capabilityCheck) return "#94a3b8"
                                var caps = capabilityCheck.capabilities || {}
                                return caps.hasThermalCamera ? "#e2e8f0" : "#f59e0b"
                            }
                            font.pixelSize: 11
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
            
            // Missing capabilities error
            Rectangle {
                width: parent.width - 40
                height: missingCol.implicitHeight + 16
                radius: 6
                color: "#7f1d1d"
                border.color: "#ef4444"
                border.width: 1
                visible: missingCapabilities.length > 0

                Column {
                    id: missingCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                    spacing: 6

                    Text {
                        text: qsTr("⚠ MISSING REQUIRED HARDWARE")
                        color: "#fca5a5"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                    }

                    Repeater {
                        model: missingCapabilities
                        Text {
                            text: "• " + modelData
                            color: "#fecaca"
                            font.pixelSize: 10
                        }
                    }
                }
            }
            
            // Warnings
            Rectangle {
                width: parent.width - 40
                height: warnCol.implicitHeight + 16
                radius: 6
                color: "#78350f"
                border.color: "#f59e0b"
                border.width: 1
                visible: capabilityWarnings.length > 0

                Column {
                    id: warnCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                    spacing: 6

                    Text {
                        text: qsTr("⚠ WARNINGS")
                        color: "#fcd34d"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                    }

                    Repeater {
                        model: capabilityWarnings
                        Text {
                            width: parent.width
                            text: "• " + modelData
                            color: "#fde68a"
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }
    }

    Component {
        id: step2Component
        
        Column {
            width: parent.width
            spacing: 20
            topPadding: 20
            leftPadding: 20
            rightPadding: 20
            bottomPadding: 20

            Text {
                width: parent.width - 40
                text: qsTr("Define solar panel rows by drawing on the map. Click 'Draw on Map' then click two points to define each row.")
                color: "#94a3b8"
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }

            Row {
                width: parent.width - 40
                spacing: 12

                Rectangle {
                    width: (parent.width - 12) / 2
                    height: 40
                    radius: 6
                    color: drawM.containsMouse ? "#1d4ed8" : "#1e3a5f"
                    border.color: "#2563eb"
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: qsTr("📍 DRAW ON MAP")
                        color: "#93c5fd"
                        font.pixelSize: 11
                        font.weight: Font.Bold
                    }

                    ToolTip.visible: drawM.containsMouse
                    ToolTip.delay: 600
                    ToolTip.text: qsTr("Switch to the Map tab and click two points to define each solar row. Repeat for every row in the array. The drone will fly along each row.")

                    MouseArea {
                        id: drawM
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            if (typeof mission !== 'undefined') {
                                mission.startDrawingSolarRows()
                            }
                        }
                    }
                }

                Rectangle {
                    width: (parent.width - 12) / 2
                    height: 40
                    radius: 6
                    color: clearM.containsMouse ? "#7f1d1d" : "#1e2535"
                    border.color: "#ef4444"
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: qsTr("🗑 CLEAR")
                        color: "#fca5a5"
                        font.pixelSize: 11
                        font.weight: Font.Bold
                    }

                    ToolTip.visible: clearM.containsMouse
                    ToolTip.delay: 600
                    ToolTip.text: qsTr("Remove all drawn solar rows from the map and reset the row list.")

                    MouseArea {
                        id: clearM
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            if (typeof mission !== 'undefined') {
                                mission.clearSolarRows()
                            }
                            solarRows = []
                        }
                    }
                }
            }

            Text {
                width: parent.width - 40
                text: qsTr("Rows drawn: ") + solarRows.length
                color: "#64748b"
                font.pixelSize: 10
            }
        }
    }

    Component {
        id: step3Component
        
        Column {
            width: parent.width
            spacing: 20
            topPadding: 20
            leftPadding: 20
            rightPadding: 20
            bottomPadding: 20

            Text {
                width: parent.width - 40
                text: qsTr("Configure flight parameters and camera settings.")
                color: "#94a3b8"
                font.pixelSize: 11
            }

            Rectangle {
                width: parent.width - 40
                height: settingsCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1

                Column {
                    id: settingsCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 16

                    Text {
                        text: qsTr("FLIGHT PARAMETERS")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }

                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Altitude (AGL)"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 80 }
                            Text { text: altitude.toFixed(1) + " m"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 10.0; to: 120.0; value: altitude; stepSize: 1.0
                            onValueChanged: altitude = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Flight altitude above ground level (10–120 m). Lower = better GSD (detail) but slower. Higher = faster coverage. Affects GSD and footprint calculations below.")
                        }
                    }

                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Speed"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 80 }
                            Text { text: speed.toFixed(1) + " m/s"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 1.0; to: 15.0; value: speed; stepSize: 0.5
                            onValueChanged: speed = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Horizontal flight speed along each solar row (1–15 m/s). Slower = more photos per row and better coverage. Faster = shorter flight time.")
                        }
                    }

                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Camera Angle"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 80 }
                            Text { text: cameraAngle.toFixed(0) + "°"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: -90.0; to: 0.0; value: cameraAngle; stepSize: 5.0
                            onValueChanged: cameraAngle = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Gimbal pitch angle: 0° = horizontal (forward), −45° = diagonal (recommended for panel inspection), −90° = straight down (nadir/orthophoto).")
                        }
                    }

                    Text {
                        text: qsTr("CAMERA TRIGGER SETTINGS")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                        topPadding: 8
                    }
                    
                    // Trigger Mode
                    Column {
                        width: parent.width
                        spacing: 6
                        Text { text: qsTr("Trigger Mode"); color: "#94a3b8"; font.pixelSize: 11 }
                        ComboBox {
                            id: triggerModeCombo
                            width: parent.width
                            height: 32
                            model: ["Distance", "Time", "Waypoint"]
                            currentIndex: triggerMode === "distance" ? 0 : triggerMode === "time" ? 1 : 2
                            onCurrentTextChanged: {
                                triggerMode = currentText.toLowerCase()
                            }
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            contentItem: Text {
                                text: triggerModeCombo.displayText
                                color: "#e2e8f0"
                                font.pixelSize: 11
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                            ToolTip.visible: hovered
                            ToolTip.delay: 600
                            ToolTip.text: qsTr("Distance: take a photo every N metres (consistent ground coverage). Time: every N seconds. Waypoint: only at each waypoint.")
                        }
                    }

                    // Trigger Interval
                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text {
                                text: triggerMode === "distance" ? qsTr("Trigger Interval (m)") : qsTr("Trigger Interval (s)")
                                color: "#94a3b8"
                                font.pixelSize: 11
                                width: parent.width - 80
                            }
                            Text {
                                text: triggerInterval.toFixed(1) + (triggerMode === "distance" ? " m" : " s")
                                color: "#e2e8f0"
                                font.pixelSize: 11
                                font.family: "Consolas"
                            }
                        }
                        Slider {
                            width: parent.width
                            from: triggerMode === "distance" ? 5.0 : 1.0
                            to: triggerMode === "distance" ? 50.0 : 10.0
                            value: triggerInterval
                            stepSize: triggerMode === "distance" ? 1.0 : 0.5
                            onValueChanged: triggerInterval = value
                            ToolTip.visible: pressed
                            ToolTip.text: triggerMode === "distance"
                                ? qsTr("Distance between camera triggers (5–50 m). Smaller = more images per row. Combine with Forward Overlap for accurate coverage.")
                                : qsTr("Time between camera triggers (1–10 s). Combined with speed, determines how many images per row are captured.")
                        }
                    }

                    Text {
                        text: qsTr("IMAGE OVERLAP")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                        topPadding: 8
                    }
                    
                    // Forward Overlap
                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Forward Overlap"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 80 }
                            Text { text: forwardOverlap.toFixed(0) + "%"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 50.0; to: 90.0; value: forwardOverlap; stepSize: 5.0
                            onValueChanged: forwardOverlap = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Percentage of image overlap in the flight direction (50–90 %). 70 % = standard for photogrammetry. Higher = better 3D reconstruction, more images.")
                        }
                    }

                    // Side Overlap
                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Side Overlap"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 80 }
                            Text { text: sideOverlap.toFixed(0) + "%"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 40.0; to: 80.0; value: sideOverlap; stepSize: 5.0
                            onValueChanged: sideOverlap = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Percentage of image overlap between adjacent rows (40–80 %). 60 % = standard. Higher = no gaps between rows but increases total image count.")
                        }
                    }
                }
            }
            
            // Calculated Values Display
            Rectangle {
                width: parent.width - 40
                height: calcCol.implicitHeight + 24
                radius: 8
                color: "#0d1117"
                border.color: "#2d3748"
                border.width: 1
                
                Column {
                    id: calcCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 12
                    
                    Text {
                        text: qsTr("CALCULATED VALUES")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }
                    
                    Grid {
                        width: parent.width
                        columns: 2
                        columnSpacing: 20
                        rowSpacing: 8
                        
                        Text { text: qsTr("GSD:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: calculatedGSD.toFixed(2) + " cm/px"; color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold }
                        
                        Text { text: qsTr("Coverage Width:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: coverageWidth.toFixed(1) + " m"; color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold }
                        
                        Text { text: qsTr("Coverage Height:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: coverageHeight.toFixed(1) + " m"; color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold }
                        
                        Text { text: qsTr("Coverage Area:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: (coverageWidth * coverageHeight).toFixed(1) + " m²"; color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold }
                    }
                    
                    Text {
                        width: parent.width
                        text: qsTr("💡 Lower altitude = better GSD (higher detail). Adjust overlap for better 3D reconstruction.")
                        color: "#64748b"
                        font.pixelSize: 9
                        wrapMode: Text.WordWrap
                        topPadding: 4
                    }
                }
            }
        }
    }

    Component {
        id: step4Component
        
        Column {
            width: parent.width
            spacing: 20
            topPadding: 20
            leftPadding: 20
            rightPadding: 20
            bottomPadding: 20
            
            Component.onCompleted: {
                // Generate preview when entering step 4
                if (!previewData && !previewLoading) {
                    generatePreview()
                }
            }

            Text {
                width: parent.width - 40
                text: qsTr("Review mission parameters and preview before uploading.")
                color: "#94a3b8"
                font.pixelSize: 11
            }
            
            // Generate Preview Button
            Rectangle {
                width: parent.width - 40
                height: 40
                radius: 6
                color: previewBtnM.containsMouse ? "#1d4ed8" : "#1e3a5f"
                border.color: "#2563eb"
                border.width: 1
                visible: !previewLoading && !previewData

                Text {
                    anchors.centerIn: parent
                    text: qsTr("🔄 GENERATE PREVIEW")
                    color: "#93c5fd"
                    font.pixelSize: 11
                    font.weight: Font.Bold
                }

                ToolTip.visible: previewBtnM.containsMouse
                ToolTip.delay: 600
                ToolTip.text: qsTr("Calculate the complete waypoint list from your rows and settings. The result is shown on the Map and in the summary below.")

                MouseArea {
                    id: previewBtnM
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: generatePreview()
                }
            }
            
            // Loading Indicator
            Rectangle {
                width: parent.width - 40
                height: 60
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                visible: previewLoading
                
                Column {
                    anchors.centerIn: parent
                    spacing: 8
                    
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "⏳"
                        font.pixelSize: 24
                    }
                    
                    Text {
                        text: qsTr("Generating preview...")
                        color: "#94a3b8"
                        font.pixelSize: 11
                    }
                }
            }
            
            // Preview Error
            Rectangle {
                width: parent.width - 40
                height: errorCol.implicitHeight + 16
                radius: 6
                color: "#7f1d1d"
                border.color: "#ef4444"
                border.width: 1
                visible: previewError !== ""
                
                Column {
                    id: errorCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                    spacing: 6
                    
                    Text {
                        text: qsTr("⚠ PREVIEW ERROR")
                        color: "#fca5a5"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                    }
                    
                    Text {
                        width: parent.width
                        text: previewError
                        color: "#fecaca"
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // Mission Summary (from preview data)
            Rectangle {
                width: parent.width - 40
                height: summaryCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                visible: previewData !== null

                Column {
                    id: summaryCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 12

                    Text {
                        text: qsTr("MISSION SUMMARY")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }

                    Grid {
                        width: parent.width
                        columns: 2
                        columnSpacing: 20
                        rowSpacing: 8

                        Text { text: qsTr("Waypoints:"); color: "#64748b"; font.pixelSize: 10 }
                        Text {
                            text: previewData && previewData.waypoints ? previewData.waypoints.length.toString() : "0"
                            color: "#e2e8f0"
                            font.pixelSize: 10
                            font.family: "Consolas"
                        }

                        Text { text: qsTr("Images:"); color: "#64748b"; font.pixelSize: 10 }
                        Text {
                            text: previewData && previewData.totalImages ? previewData.totalImages.toString() : "0"
                            color: "#e2e8f0"
                            font.pixelSize: 10
                            font.family: "Consolas"
                        }

                        Text { text: qsTr("Duration:"); color: "#64748b"; font.pixelSize: 10 }
                        Text {
                            text: previewData && previewData.estimatedDuration ? Math.floor(previewData.estimatedDuration / 60) + " min" : "0 min"
                            color: "#e2e8f0"
                            font.pixelSize: 10
                            font.family: "Consolas"
                        }

                        Text { text: qsTr("Battery:"); color: "#64748b"; font.pixelSize: 10 }
                        Text {
                            text: previewData && previewData.estimatedBatteryUsage ? previewData.estimatedBatteryUsage.toFixed(1) + "%" : "0%"
                            color: "#e2e8f0"
                            font.pixelSize: 10
                            font.family: "Consolas"
                        }

                        Text { text: qsTr("Storage:"); color: "#64748b"; font.pixelSize: 10 }
                        Text {
                            text: previewData && previewData.storageRequired ? previewData.storageRequired.toFixed(0) + " MB" : "0 MB"
                            color: "#e2e8f0"
                            font.pixelSize: 10
                            font.family: "Consolas"
                        }

                        Text { text: qsTr("Coverage:"); color: "#64748b"; font.pixelSize: 10 }
                        Text {
                            text: previewData && previewData.coverageArea ? previewData.coverageArea.toFixed(0) + " m²" : "0 m²"
                            color: "#e2e8f0"
                            font.pixelSize: 10
                            font.family: "Consolas"
                        }
                    }
                }
            }
            
            // Validation Warnings
            Rectangle {
                width: parent.width - 40
                height: warnCol2.implicitHeight + 16
                radius: 6
                color: "#78350f"
                border.color: "#f59e0b"
                border.width: 1
                visible: previewData && previewData.warnings && previewData.warnings.length > 0
                
                Column {
                    id: warnCol2
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                    spacing: 6
                    
                    Text {
                        text: qsTr("⚠ WARNINGS")
                        color: "#fcd34d"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                    }
                    
                    Repeater {
                        model: previewData && previewData.warnings ? previewData.warnings : []
                        Text {
                            width: parent.width
                            text: "• " + modelData
                            color: "#fde68a"
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
            
            // Upload Status
            Rectangle {
                width: parent.width - 40
                height: 60
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                visible: uploadInProgress
                
                Column {
                    anchors.centerIn: parent
                    spacing: 8
                    
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "📤"
                        font.pixelSize: 24
                    }
                    
                    Text {
                        text: qsTr("Uploading mission...")
                        color: "#94a3b8"
                        font.pixelSize: 11
                    }
                }
            }

            // Important Note
            Rectangle {
                width: parent.width - 40
                height: noteCol.implicitHeight + 24
                radius: 8
                color: "#1e40af22"
                border.color: "#2563eb"
                border.width: 1
                visible: previewData !== null && !uploadInProgress

                Column {
                    id: noteCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 8

                    Row {
                        spacing: 8
                        Text { text: "ℹ️"; font.pixelSize: 14 }
                        Text {
                            text: qsTr("IMPORTANT")
                            color: "#2563eb"
                            font.pixelSize: 9
                            font.weight: Font.Bold
                            font.letterSpacing: 1
                        }
                    }

                    Text {
                        width: parent.width
                        text: qsTr("Uploading the mission will NOT automatically start it. You must manually arm and start the mission after upload.")
                        color: "#93c5fd"
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }
}
