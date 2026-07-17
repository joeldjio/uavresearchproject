import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components" as Cmp

Rectangle {
    id: root
    width: parent.width
    height: Math.max(700, contentColumn.height)
    color: "#0f172a"
    
    Component.onCompleted: {
        console.log("[SeedingPanel] Loaded! Width:", width, "Height:", height)
    }
    
    Component.onDestruction: {
        // Clear map overlays when wizard is closed — use mapLoader.item (not mapView)
        if (typeof mapLoader !== "undefined" && mapLoader && mapLoader.item) {
            if (mapLoader.item.clearSeedingMission)
                mapLoader.item.clearSeedingMission()
        }
    }
    
    // Wizard state
    property int currentStep: 1
    property int totalSteps: 6
    
    // Step 1: Field Definition
    property real fieldArea: 1000  // m² (placeholder)
    property int exclusionZoneCount: 0
    property var fieldBoundary: []
    property var exclusionZones: []
    
    // Step 2: Crop & Seed Configuration
    property string cropType: "Wheat"
    property string seedType: ""
    property real seedSpacing: 10.0  // meters between seeds (practical range: 1-600m)
    property real seedWeight: 0.05  // grams per seed
    
    // Calculated seed density from spacing
    property real seedDensity: seedSpacing > 0 ? (1.0 / (seedSpacing * seedSpacing)) : 0
    
    // Step 3: Dispenser Configuration
    property string dispenserType: "Pneumatic"
    property real dispenserCapacity: 5000  // grams
    property real dispenserRate: 10  // seeds/second
    property bool dispenserCalibrated: false
    
    // Step 4: Flight Parameters
    property real flightAltitude: 5  // meters AGL
    property real flightSpeed: 3  // m/s
    property real rowSpacing: 10  // meters
    property string flightDirection: "Auto"
    
    // Calculated values
    property real totalSeedsNeeded: fieldArea * seedDensity
    property real totalWeightNeeded: totalSeedsNeeded * seedWeight
    property int numberOfRows: fieldArea > 0 ? Math.ceil(Math.sqrt(fieldArea) / rowSpacing) : 0
    property real flightDistance: numberOfRows * Math.sqrt(fieldArea)
    
    // Preview data from backend
    property var previewData: null
    property bool previewLoading: false
    property string previewError: ""
    property bool uploadInProgress: false
    property string uploadError: ""
    
    function generatePreview() {
        if (typeof mission === 'undefined') {
            previewError = "Mission context not available"
            return
        }
        if (mission.fieldBoundaryPoints < 3) {
            previewError = qsTr("No field defined — draw a boundary on the Map tab first (min. 3 points)")
            return
        }
        
        previewLoading = true
        previewError = ""
        
        // Build params object for backend
        // NOTE: Don't pass boundary/exclusionZones - backend will use its stored points
        var params = {
            "seedSpacing": seedSpacing,  // meters between seeds
            "rowSpacing": rowSpacing,
            "altitude": flightAltitude,
            "speed": flightSpeed,
            "seedCapacity": totalSeedsNeeded,
            "seedWeightG": seedWeight,
            "tankCapacityG": dispenserCapacity,
            "dispenseRate": dispenserRate
        }
        
        console.log("Generating seeding preview with params:", JSON.stringify(params))
        
        try {
            previewData = mission.generateSeedingPreview(params)
            previewLoading = false
            
            if (previewData && !previewData.valid) {
                previewError = previewData.errors ? previewData.errors.join(", ") : "Invalid mission configuration"
            }
            
            console.log("Seeding preview generated:", JSON.stringify(previewData))
            // Map overlays are updated via mission.seedingPreviewChanged signal in main.qml
        } catch (e) {
            previewLoading = false
            previewError = "Failed to generate preview: " + e.toString()
            console.error("Preview generation error:", e)
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

        console.log("Uploading seeding mission...")
        try {
            mission.uploadSeedingMission()
            // uploadInProgress is cleared by the missionUploadFinished signal
            // wired in main.qml — do NOT set it to false here synchronously.
        } catch (e) {
            uploadInProgress = false
            uploadError = "Upload failed: " + e.toString()
            console.error("Seeding upload error:", e)
        }
    }
    
    Column {
        id: contentColumn
        width: parent.width
        spacing: 16
        
        // ── HEADER ────────────────────────────────────────────────────
        Rectangle {
            width: parent.width
            height: 60
            color: "#1e293b"
            radius: 8
            border.color: "#334155"
            border.width: 1
            
            Row {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12
                
                Rectangle {
                    width: 4
                    height: parent.height
                    color: "#10b981"
                    radius: 2
                }
                
                Column {
                    width: parent.width - 20
                    spacing: 4
                    anchors.verticalCenter: parent.verticalCenter
                    
                    Text {
                        text: "SEEDING MISSION WIZARD"
                        color: "#10b981"
                        font.pixelSize: 14
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }
                    
                    Text {
                        text: "Step " + currentStep + " of " + totalSteps
                        color: "#94a3b8"
                        font.pixelSize: 10
                    }
                }
            }
        }
        
        // ── PROGRESS INDICATOR ────────────────────────────────────────
        Row {
            width: parent.width
            spacing: 4
            
            Repeater {
                model: totalSteps
                
                Rectangle {
                    width: (parent.width - (totalSteps - 1) * 4) / totalSteps
                    height: 4
                    radius: 2
                    color: index < currentStep ? "#10b981" : "#334155"
                    
                    Behavior on color {
                        ColorAnimation { duration: 200 }
                    }
                }
            }
        }
        
        // ── STEP CONTENT ──────────────────────────────────────────────
        Loader {
            width: parent.width
            sourceComponent: {
                switch(currentStep) {
                    case 1: return step1Component
                    case 2: return step2Component
                    case 3: return step3Component
                    case 4: return step4Component
                    case 5: return step5Component
                    case 6: return step6Component
                    default: return null
                }
            }
        }
        
        // ── NAVIGATION BUTTONS ────────────────────────────────────────
        Row {
            width: parent.width
            spacing: 8
            
            // Back Button
            Rectangle {
                width: (parent.width - 8) / 2
                height: 40
                radius: 6
                color: "#334155"
                border.color: "#475569"
                border.width: 1
                visible: currentStep > 1 && currentStep < 6
                opacity: enabled ? 1.0 : 0.5
                
                Row {
                    anchors.centerIn: parent
                    spacing: 8
                    
                    Cmp.Icon {
                        name: "chevron-left"
                        size: 16
                        color: "#e2e8f0"
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    
                    Text {
                        text: "Back"
                        color: "#e2e8f0"
                        font.pixelSize: 12
                        font.weight: Font.Bold
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                
                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        if (currentStep > 1) currentStep--
                    }
                }
            }
            
            // Next/Upload/Start Button
            Rectangle {
                width: currentStep > 1 && currentStep < 6 ? (parent.width - 8) / 2 : parent.width
                height: 40
                radius: 6
                color: {
                    if (currentStep === 5) return "#3b82f6"
                    if (currentStep === 6) return "#10b981"
                    return "#10b981"
                }
                border.color: {
                    if (currentStep === 5) return "#2563eb"
                    if (currentStep === 6) return "#059669"
                    return "#059669"
                }
                border.width: 1
                opacity: enabled ? 1.0 : 0.5
                
                Row {
                    anchors.centerIn: parent
                    spacing: 8
                    
                    Text {
                        text: {
                            if (currentStep === 5) return "Upload Mission"
                            if (currentStep === 6) return "Start Mission"
                            return "Next"
                        }
                        color: "#ffffff"
                        font.pixelSize: 12
                        font.weight: Font.Bold
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    
                    Cmp.Icon {
                        name: currentStep < 5 ? "chevron-right" : (currentStep === 5 ? "upload" : "play")
                        size: 16
                        color: "#ffffff"
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                
                MouseArea {
                    anchors.fill: parent
                    enabled: {
                        if (currentStep === 5) return !uploadInProgress
                        if (currentStep === 6) return !uploadInProgress && uploadError === ""
                        return true
                    }
                    onClicked: {
                        if (currentStep === 5) {
                            // Upload Mission — never auto-starts execution.
                            uploadMission()
                        } else if (currentStep === 6) {
                            // Start Mission — separate step, upload must have
                            // completed without error first (enforced by enabled above).
                            if (typeof mission !== 'undefined' && mission) {
                                mission.startMission()
                            }
                        } else if (currentStep < totalSteps) {
                            currentStep++
                        }
                    }
                }
            }
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    // STEP COMPONENTS PLACEHOLDER
    // ══════════════════════════════════════════════════════════════════
    
    // ══════════════════════════════════════════════════════════════════
    // STEP 1: FIELD DEFINITION
    // ══════════════════════════════════════════════════════════════════
    
    Component {
        id: step1Component
        
        Column {
            width: parent.width
            spacing: 16
            
            Text {
                width: parent.width
                text: qsTr("Define the field boundary and any exclusion zones where seeding should not occur.")
                color: "#94a3b8"
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
            
            // Field Boundary
            Rectangle {
                width: parent.width
                height: fieldCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                
                Column {
                    id: fieldCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 12
                    
                    Text {
                        text: qsTr("FIELD BOUNDARY")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }
                    
                    Row {
                        width: parent.width
                        spacing: 12
                        
                        Rectangle {
                            width: (parent.width - 12) / 2
                            height: 40
                            radius: 6
                            color: drawFieldM.containsMouse ? "#1d4ed8" : "#1e3a5f"
                            border.color: "#2563eb"
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                text: qsTr("📍 DRAW BOUNDARY")
                                color: "#93c5fd"
                                font.pixelSize: 11
                                font.weight: Font.Bold
                            }

                            ToolTip.visible: drawFieldM.containsMouse
                            ToolTip.delay: 600
                            ToolTip.text: qsTr("Switch to the Map tab and click to place boundary vertices. Minimum 3 points required to define the field.")

                            MouseArea {
                                id: drawFieldM
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    if (typeof mission !== 'undefined') {
                                        mission.startDrawingBoundary()
                                    }
                                }
                            }
                        }

                        Rectangle {
                            width: (parent.width - 12) / 2
                            height: 40
                            radius: 6
                            color: clearFieldM.containsMouse ? "#7f1d1d" : "#1e2535"
                            border.color: "#ef4444"
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                text: qsTr("🗑 CLEAR")
                                color: "#fca5a5"
                                font.pixelSize: 11
                                font.weight: Font.Bold
                            }

                            ToolTip.visible: clearFieldM.containsMouse
                            ToolTip.delay: 600
                            ToolTip.text: qsTr("Remove all boundary points and reset the field area.")

                            MouseArea {
                                id: clearFieldM
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    if (typeof mission !== 'undefined') {
                                        mission.clearBoundary()
                                    }
                                    fieldArea = 0
                                    fieldBoundary = []
                                }
                            }
                        }
                    }
                    
                    Text {
                        text: qsTr("Field Area: ") + fieldArea.toFixed(0) + " m²"
                        color: fieldArea > 0 ? "#10b981" : "#64748b"
                        font.pixelSize: 10
                        font.family: "Consolas"
                    }
                }
            }
            
            // Exclusion Zones
            Rectangle {
                width: parent.width
                height: exclusionCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                
                Column {
                    id: exclusionCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 12
                    
                    Text {
                        text: qsTr("EXCLUSION ZONES (Optional)")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }
                    
                    Text {
                        width: parent.width
                        text: qsTr("Mark areas to avoid (e.g., water bodies, buildings, protected areas)")
                        color: "#64748b"
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                    
                    Rectangle {
                        width: parent.width
                        height: 40
                        radius: 6
                        color: drawExclusionM.containsMouse ? "#f59e0b" : "#78350f"
                        border.color: "#fbbf24"
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: qsTr("⚠ DRAW EXCLUSION ZONE")
                            color: "#fde68a"
                            font.pixelSize: 11
                            font.weight: Font.Bold
                        }

                        ToolTip.visible: drawExclusionM.containsMouse
                        ToolTip.delay: 600
                        ToolTip.text: qsTr("Draw a no-fly/no-seed polygon on the map (e.g. water body, building, protected area). Multiple zones allowed.")

                        MouseArea {
                            id: drawExclusionM
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                if (typeof mission !== 'undefined') {
                                    mission.startDrawingExclusionZone()
                                }
                            }
                        }
                    }
                    
                    Text {
                        text: qsTr("Exclusion Zones: ") + exclusionZoneCount
                        color: "#64748b"
                        font.pixelSize: 10
                        font.family: "Consolas"
                    }
                }
            }
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    // STEP 2: CROP & SEED CONFIGURATION
    // ══════════════════════════════════════════════════════════════════
    
    Component {
        id: step2Component
        
        Column {
            width: parent.width
            spacing: 16
            
            Text {
                width: parent.width
                text: qsTr("Configure crop type and seed specifications.")
                color: "#94a3b8"
                font.pixelSize: 11
            }
            
            Rectangle {
                width: parent.width
                height: cropCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                
                Column {
                    id: cropCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 16
                    
                    Text {
                        text: qsTr("CROP & SEED SETTINGS")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }
                    
                    // Crop Type
                    Column {
                        width: parent.width
                        spacing: 6
                        Text { text: qsTr("Crop Type"); color: "#94a3b8"; font.pixelSize: 11 }
                        ComboBox {
                            id: cropTypeCombo
                            width: parent.width
                            height: 32
                            model: ["Wheat", "Corn", "Rice", "Soybean", "Barley", "Oats", "Custom"]
                            currentIndex: 0
                            onCurrentTextChanged: cropType = currentText
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            contentItem: Text {
                                text: cropTypeCombo.displayText
                                color: "#e2e8f0"
                                font.pixelSize: 11
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                            ToolTip.visible: hovered
                            ToolTip.delay: 600
                            ToolTip.text: qsTr("Select the crop to be seeded. Affects default seed spacing and weight recommendations.")
                        }
                    }

                    // Seed Type
                    Column {
                        width: parent.width
                        spacing: 6
                        Text { text: qsTr("Seed Type/Variety"); color: "#94a3b8"; font.pixelSize: 11 }
                        TextField {
                            width: parent.width
                            height: 32
                            placeholderText: qsTr("e.g., Winter Wheat Variety A")
                            text: seedType
                            onTextChanged: seedType = text
                            color: "#e2e8f0"
                            font.pixelSize: 11
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            ToolTip.visible: hovered
                            ToolTip.delay: 600
                            ToolTip.text: qsTr("Optional: enter the exact seed variety name for record-keeping (e.g. 'Pionier P0023').")
                        }
                    }

                    // Seed Spacing
                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Seed Spacing"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 120 }
                            Text { text: seedSpacing.toFixed(1) + " m"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 1.0; to: 600.0; value: seedSpacing; stepSize: 1.0
                            onValueChanged: seedSpacing = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Distance between individual seed drop points (1–600 m). Smaller spacing = higher density. Calculated density shown below.")
                        }
                        Text {
                            text: qsTr("Density: ") + seedDensity.toFixed(3) + " seeds/m²"
                            color: "#64748b"
                            font.pixelSize: 9
                            font.italic: true
                        }
                    }

                    // Seed Weight
                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Seed Weight"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 120 }
                            Text { text: seedWeight.toFixed(3) + " g/seed"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 0.01; to: 0.5; value: seedWeight; stepSize: 0.01
                            onValueChanged: seedWeight = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Weight per individual seed in grams (0.01–0.5 g). Used to calculate total seed load and tank refill requirements.")
                        }
                    }
                }
            }
            
            // Calculated Requirements
            Rectangle {
                width: parent.width
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
                        text: qsTr("CALCULATED REQUIREMENTS")
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
                        
                        Text { text: qsTr("Total Seeds:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: totalSeedsNeeded.toFixed(0); color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold }
                        
                        Text { text: qsTr("Total Weight:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: totalWeightNeeded.toFixed(0) + " g"; color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold }
                    }
                }
            }
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    // STEP 3: DISPENSER CONFIGURATION
    // ══════════════════════════════════════════════════════════════════
    
    Component {
        id: step3Component
        
        Column {
            width: parent.width
            spacing: 16
            
            Text {
                width: parent.width
                text: qsTr("Configure the seed dispenser and run calibration tests.")
                color: "#94a3b8"
                font.pixelSize: 11
            }
            
            Rectangle {
                width: parent.width
                height: dispenserCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                
                Column {
                    id: dispenserCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 16
                    
                    Text {
                        text: qsTr("DISPENSER SETTINGS")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }
                    
                    // Dispenser Type
                    Column {
                        width: parent.width
                        spacing: 6
                        Text { text: qsTr("Dispenser Type"); color: "#94a3b8"; font.pixelSize: 11 }
                        ComboBox {
                            id: dispenserTypeCombo
                            width: parent.width
                            height: 32
                            model: ["Pneumatic", "Gravity", "Centrifugal", "Auger"]
                            currentIndex: 0
                            onCurrentTextChanged: dispenserType = currentText
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            contentItem: Text {
                                text: dispenserTypeCombo.displayText
                                color: "#e2e8f0"
                                font.pixelSize: 11
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                            ToolTip.visible: hovered
                            ToolTip.delay: 600
                            ToolTip.text: qsTr("Pneumatic: air-pressure ejection (fast, precise). Gravity: passive drop (simple). Centrifugal: spinning disc (wide spread). Auger: screw-feed (steady rate).")
                        }
                    }

                    // Dispenser Capacity
                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Tank Capacity"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 120 }
                            Text { text: dispenserCapacity.toFixed(0) + " g"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 1000; to: 20000; value: dispenserCapacity; stepSize: 500
                            onValueChanged: dispenserCapacity = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Maximum seed load the tank can hold (1 000–20 000 g). A warning appears if the mission requires more than this capacity.")
                        }
                    }

                    // Dispenser Rate
                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Dispense Rate"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 120 }
                            Text { text: dispenserRate.toFixed(1) + " seeds/s"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 1; to: 50; value: dispenserRate; stepSize: 1
                            onValueChanged: dispenserRate = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("How many seeds per second the dispenser releases (1–50 seeds/s). Higher rate = faster seeding but may reduce accuracy.")
                        }
                    }

                    // Calibration Test
                    Rectangle {
                        width: parent.width
                        height: 40
                        radius: 6
                        color: calibrateM.containsMouse ? "#059669" : "#064e3b"
                        border.color: "#10b981"
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: qsTr("🔧 RUN CALIBRATION TEST")
                            color: "#6ee7b7"
                            font.pixelSize: 11
                            font.weight: Font.Bold
                        }

                        ToolTip.visible: calibrateM.containsMouse
                        ToolTip.delay: 600
                        ToolTip.text: qsTr("Trigger a short dispenser test cycle to verify the mechanism and confirm the configured rate. Mark as calibrated before proceeding.")

                        MouseArea {
                            id: calibrateM
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                console.log("Run dispenser calibration")
                                dispenserCalibrated = true
                            }
                        }
                    }
                    
                    Row {
                        spacing: 8
                        visible: dispenserCalibrated
                        Rectangle {
                            width: 20; height: 20; radius: 10
                            color: "#10b981"
                            Text {
                                anchors.centerIn: parent
                                text: "✓"
                                color: "#ffffff"
                                font.pixelSize: 12
                                font.weight: Font.Bold
                            }
                        }
                        Text {
                            text: qsTr("Dispenser calibrated")
                            color: "#10b981"
                            font.pixelSize: 10
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
            
            // Tank Refill Warning
            Rectangle {
                width: parent.width
                height: refillCol.implicitHeight + 16
                radius: 6
                color: "#78350f"
                border.color: "#f59e0b"
                border.width: 1
                visible: totalWeightNeeded > dispenserCapacity
                
                Column {
                    id: refillCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                    spacing: 6
                    
                    Text {
                        text: qsTr("⚠ TANK REFILL REQUIRED")
                        color: "#fcd34d"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                    }
                    
                    Text {
                        width: parent.width
                        text: qsTr("Mission requires ") + totalWeightNeeded.toFixed(0) + qsTr(" g but tank capacity is only ") + dispenserCapacity.toFixed(0) + qsTr(" g. Plan for mid-mission refill.")
                        color: "#fde68a"
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    // STEP 4: FLIGHT PARAMETERS
    // ══════════════════════════════════════════════════════════════════
    
    Component {
        id: step4Component
        
        Column {
            width: parent.width
            spacing: 16
            
            Text {
                width: parent.width
                text: qsTr("Configure flight altitude, speed, and row spacing.")
                color: "#94a3b8"
                font.pixelSize: 11
            }
            
            Rectangle {
                width: parent.width
                height: flightCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                
                Column {
                    id: flightCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 16
                    
                    Text {
                        text: qsTr("FLIGHT PARAMETERS")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }
                    
                    // Altitude
                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Altitude (AGL)"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 80 }
                            Text { text: flightAltitude.toFixed(1) + " m"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 2; to: 20; value: flightAltitude; stepSize: 0.5
                            onValueChanged: flightAltitude = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Height above ground level during seeding (2–20 m). Lower = more precise seed placement. Must clear obstacles and crop canopy.")
                        }
                    }

                    // Speed
                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Flight Speed"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 80 }
                            Text { text: flightSpeed.toFixed(1) + " m/s"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 1; to: 10; value: flightSpeed; stepSize: 0.5
                            onValueChanged: flightSpeed = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Horizontal speed during the seeding run (1–10 m/s). Faster = shorter mission time but reduced dispenser accuracy.")
                        }
                    }

                    // Row Spacing
                    Column {
                        width: parent.width
                        spacing: 6
                        Row {
                            width: parent.width
                            Text { text: qsTr("Row Spacing"); color: "#94a3b8"; font.pixelSize: 11; width: parent.width - 80 }
                            Text { text: rowSpacing.toFixed(1) + " m"; color: "#e2e8f0"; font.pixelSize: 11; font.family: "Consolas" }
                        }
                        Slider {
                            width: parent.width
                            from: 5; to: 30; value: rowSpacing; stepSize: 1
                            onValueChanged: rowSpacing = value
                            ToolTip.visible: pressed
                            ToolTip.text: qsTr("Distance between adjacent flight lines (5–30 m). Should match the crop row width or the dispenser's spread radius.")
                        }
                    }

                    // Flight Direction
                    Column {
                        width: parent.width
                        spacing: 6
                        Text { text: qsTr("Flight Direction"); color: "#94a3b8"; font.pixelSize: 11 }
                        ComboBox {
                            id: directionCombo
                            width: parent.width
                            height: 32
                            model: ["Auto", "North-South", "East-West", "Custom"]
                            currentIndex: 0
                            onCurrentTextChanged: flightDirection = currentText
                            background: Rectangle { color: "#1e2535"; radius: 5; border.color: "#2d3748"; border.width: 1 }
                            contentItem: Text {
                                text: directionCombo.displayText
                                color: "#e2e8f0"
                                font.pixelSize: 11
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                            ToolTip.visible: hovered
                            ToolTip.delay: 600
                            ToolTip.text: qsTr("Auto: chooses the direction that minimises turns. North-South / East-West: fixed axis. Custom: set a specific bearing.")
                        }
                    }
                }
            }
            
            // Calculated Flight Info
            Rectangle {
                width: parent.width
                height: flightInfoCol.implicitHeight + 24
                radius: 8
                color: "#0d1117"
                border.color: "#2d3748"
                border.width: 1
                
                Column {
                    id: flightInfoCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 12
                    
                    Text {
                        text: qsTr("CALCULATED FLIGHT INFO")
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
                        
                        Text { text: qsTr("Number of Rows:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: numberOfRows.toString(); color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold }
                        
                        Text { text: qsTr("Flight Distance:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: flightDistance.toFixed(0) + " m"; color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold }
                    }
                }
            }
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    // STEP 5: PREVIEW & UPLOAD
    // ══════════════════════════════════════════════════════════════════
    
    Component {
        id: step5Component
        
        Column {
            width: parent.width
            spacing: 16
            
            Text {
                width: parent.width
                text: qsTr("Review mission parameters before uploading.")
                color: "#94a3b8"
                font.pixelSize: 11
            }
            
            Rectangle {
                width: parent.width
                height: previewCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                
                Column {
                    id: previewCol
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
                        
                        Text { text: qsTr("Field Area:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: fieldArea.toFixed(0) + " m²"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                        
                        Text { text: qsTr("Crop Type:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: cropType; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                        
                        Text { text: qsTr("Seed Spacing:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: seedSpacing.toFixed(1) + " m"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                        
                        Text { text: qsTr("Total Seeds:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: totalSeedsNeeded.toFixed(0); color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                        
                        Text { text: qsTr("Altitude:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: flightAltitude.toFixed(1) + " m"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                        
                        Text { text: qsTr("Speed:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: flightSpeed.toFixed(1) + " m/s"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                        
                        Text { text: qsTr("Row Spacing:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: rowSpacing.toFixed(1) + " m"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                        
                        Text { text: qsTr("Number of Rows:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: numberOfRows.toString(); color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                }
            }
            
            // Generate Preview Button
            Rectangle {
                width: parent.width
                height: 50
                radius: 8
                color: generatePreviewM.containsMouse ? "#059669" : "#047857"
                border.color: "#10b981"
                border.width: 2
                
                Row {
                    anchors.centerIn: parent
                    spacing: 12
                    
                    Text {
                        text: previewLoading ? "⏳" : "🔍"
                        font.pixelSize: 20
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    
                    Text {
                        text: previewLoading ? qsTr("Generating Preview...") : qsTr("GENERATE PREVIEW")
                        color: "#ffffff"
                        font.pixelSize: 13
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                
                MouseArea {
                    id: generatePreviewM
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: !previewLoading && fieldArea > 0
                    onClicked: {
                        console.log("Generate seeding preview clicked")
                        generatePreview()
                    }
                    ToolTip.visible: !enabled && containsMouse
                    ToolTip.text: qsTr("Draw a boundary on the Map tab first")
                    ToolTip.delay: 400
                }
            }
            
            // Preview Results (if available)
            Rectangle {
                width: parent.width
                height: previewResultCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: previewData && previewData.valid ? "#10b981" : "#ef4444"
                border.width: 1
                visible: previewData !== null
                
                Column {
                    id: previewResultCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 12
                    
                    Text {
                        text: previewData && previewData.valid ? qsTr("✅ PREVIEW GENERATED") : qsTr("❌ PREVIEW ERROR")
                        color: previewData && previewData.valid ? "#10b981" : "#ef4444"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }
                    
                    Grid {
                        width: parent.width
                        columns: 2
                        columnSpacing: 20
                        rowSpacing: 8
                        visible: previewData && previewData.valid
                        
                        Text { text: qsTr("Waypoints:"); color: "#64748b"; font.pixelSize: 10 }
                        Text {
                            text: previewData && previewData.waypoints ? previewData.waypoints.length.toString() : "0"
                            color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold
                        }
                        
                        Text { text: qsTr("Drop Points:"); color: "#64748b"; font.pixelSize: 10 }
                        Text {
                            text: previewData && previewData.dropPoints ? previewData.dropPoints.length.toString() : "0"
                            color: "#8b5cf6"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold
                        }
                        
                        Text { text: qsTr("Est. Duration:"); color: "#64748b"; font.pixelSize: 10 }
                        Text {
                            text: previewData && previewData.estimatedDuration ? (previewData.estimatedDuration / 60).toFixed(1) + " min" : "0 min"
                            color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"
                        }
                        
                        Text { text: qsTr("Battery Usage:"); color: "#64748b"; font.pixelSize: 10 }
                        Text {
                            text: previewData && previewData.estimatedBatteryUsage ? previewData.estimatedBatteryUsage.toFixed(1) + " %" : "0 %"
                            color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas"
                        }
                    }
                    
                    // Preview Error
                    Text {
                        width: parent.width
                        text: previewError
                        color: "#ef4444"
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                        visible: previewError !== ""
                    }
                    
                    // Warnings
                    Column {
                        width: parent.width
                        spacing: 4
                        visible: previewData && previewData.warnings && previewData.warnings.length > 0
                        
                        Text {
                            text: qsTr("⚠ WARNINGS")
                            color: "#fcd34d"
                            font.pixelSize: 9
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
            }
            
            // Important Note
            Rectangle {
                width: parent.width
                height: noteCol.implicitHeight + 24
                radius: 8
                color: "#1e40af22"
                border.color: "#2563eb"
                border.width: 1
                
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
                        text: qsTr("Uploading the mission will NOT automatically start it. You must manually proceed to the execution step.")
                        color: "#93c5fd"
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    // STEP 6: EXECUTION & MONITORING
    // ══════════════════════════════════════════════════════════════════
    
    Component {
        id: step6Component
        
        Column {
            width: parent.width
            spacing: 16
            
            Text {
                width: parent.width
                text: qsTr("Monitor mission execution and seed dispensing.")
                color: "#94a3b8"
                font.pixelSize: 11
            }
            
            // Mission Control
            Rectangle {
                width: parent.width
                height: controlCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                
                Column {
                    id: controlCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 16
                    
                    Text {
                        text: qsTr("MISSION CONTROL")
                        color: "#64748b"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1
                    }
                    
                    // Progress Bar
                    Column {
                        width: parent.width
                        spacing: 6
                        
                        Row {
                            width: parent.width
                            Text { text: qsTr("Progress"); color: "#94a3b8"; font.pixelSize: 10; width: parent.width - 60 }
                            Text { text: "0%"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                        }
                        
                        Rectangle {
                            width: parent.width
                            height: 8
                            radius: 4
                            color: "#1e2535"
                            border.color: "#2d3748"
                            border.width: 1
                            
                            Rectangle {
                                width: parent.width * 0
                                height: parent.height
                                radius: 4
                                color: "#10b981"
                            }
                        }
                    }
                    
                    // Control Buttons
                    Row {
                        width: parent.width
                        spacing: 8
                        
                        Rectangle {
                            width: (parent.width - 8) / 2
                            height: 40
                            radius: 6
                            color: "#f59e0b"
                            border.color: "#fbbf24"
                            border.width: 1
                            
                            Text {
                                anchors.centerIn: parent
                                text: qsTr("⏸ PAUSE")
                                color: "#ffffff"
                                font.pixelSize: 11
                                font.weight: Font.Bold
                            }
                            
                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    if (typeof mission !== 'undefined') {
                                        mission.pauseMission()
                                    }
                                }
                            }
                        }
                        
                        Rectangle {
                            width: (parent.width - 8) / 2
                            height: 40
                            radius: 6
                            color: "#ef4444"
                            border.color: "#f87171"
                            border.width: 1
                            
                            Text {
                                anchors.centerIn: parent
                                text: qsTr("⏹ ABORT")
                                color: "#ffffff"
                                font.pixelSize: 11
                                font.weight: Font.Bold
                            }
                            
                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    if (typeof mission !== 'undefined') {
                                        mission.abortMission()
                                    }
                                    // Reset wizard to Step 1
                                    currentStep = 1
                                    previewData = null
                                    previewError = ""
                                    uploadError = ""
                                }
                            }
                        }
                    }
                }
            }
            
            // Seed Dispensing Status
            Rectangle {
                width: parent.width
                height: seedStatusCol.implicitHeight + 24
                radius: 8
                color: "#1a2035"
                border.color: "#2d3748"
                border.width: 1
                
                Column {
                    id: seedStatusCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 12
                    
                    Text {
                        text: qsTr("SEED DISPENSING STATUS")
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
                        
                        Text { text: qsTr("Seeds Dispensed:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: "0"; color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold }
                        
                        Text { text: qsTr("Remaining Capacity:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: dispenserCapacity.toFixed(0) + " g"; color: "#10b981"; font.pixelSize: 10; font.family: "Consolas"; font.weight: Font.Bold }
                        
                        Text { text: qsTr("Drop Points:"); color: "#64748b"; font.pixelSize: 10 }
                        Text { text: "0 / 0"; color: "#e2e8f0"; font.pixelSize: 10; font.family: "Consolas" }
                    }
                }
            }
        }
    }
}
