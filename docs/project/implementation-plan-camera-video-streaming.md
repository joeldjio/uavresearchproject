# Implementation Plan: Camera & Video Streaming Integration
## SkyMeshX GCS - Seeding & Solar Inspection Improvements

**Date:** 2026-06-20  
**Status:** Planning Phase  
**Priority:** High

---

## Executive Summary

This document outlines the implementation plan to make Seeding and Solar Inspection modes more intuitive and complete by integrating camera settings, video streaming, and thermal imaging capabilities into the Gimbal Panel.

## Current State Analysis

### ✅ What Exists
1. **Solar Inspection Mode** ([`docs/ui/solar-inspection-ui-integration.md`](../ui/solar-inspection-ui-integration.md))
   - Panel row definition on map
   - Mission parameter configuration (altitude, gimbal pitch, trigger distance, overlap)
   - Waypoint generation via [`SolarParkInspectionPlanner`](../../skymeshx/control/solar_inspection.py)
   - Thermal hotspot visualization on map

2. **Seeding Mode** ([`tools/ui/qml/panels/MissionPanel.qml`](../../tools/ui/qml/panels/MissionPanel.qml))
   - Field boundary drawing
   - Seeding pattern generation
   - Basic mission planning

3. **Gimbal Panel** ([`tools/ui/qml/panels/GimbalPanel.qml`](../../tools/ui/qml/panels/GimbalPanel.qml))
   - Pitch/Roll/Yaw sliders
   - Observation UAV detection
   - Basic gimbal control

### ❌ What's Missing

1. **Camera Controls**
   - No camera settings (resolution, FPS, exposure, ISO)
   - No photo/video capture buttons
   - No camera mode selection (Photo/Video/Thermal)

2. **Video Streaming**
   - No live video feed display
   - No video recording controls
   - No stream quality settings

3. **Thermal Camera Integration**
   - No thermal camera settings
   - No temperature range configuration
   - No color palette selection

4. **Workflow Clarity**
   - Solar mode: Unclear what happens after mission generation
   - Seeding mode: No visual feedback during operation
   - No camera preview during mission planning

---

## Implementation Plan

### Phase 1: Camera Control Integration (Week 1-2)

#### 1.1 Extend Gimbal Panel with Camera Section

**File:** `tools/ui/qml/panels/GimbalPanel.qml`

**New Components:**
```qml
// ── CAMERA CONTROLS ────────────────────────────────────────
Rectangle {
    width: parent.width
    height: cameraCol.implicitHeight + 20
    radius: 8
    color: "#1a2035"
    border.color: "#2d3748"
    border.width: 1
    
    Column {
        id: cameraCol
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
        spacing: 12
        
        // Camera Mode Selection
        Row {
            width: parent.width
            spacing: 8
            
            Text {
                text: "Camera Mode:"
                color: "#94a3b8"
                font.pixelSize: 10
                anchors.verticalCenter: parent.verticalCenter
            }
            
            // Photo / Video / Thermal buttons
            ButtonGroup { id: cameraModeGroup }
            
            Repeater {
                model: [
                    { id: "photo", label: "📷 Photo", color: "#3b82f6" },
                    { id: "video", label: "🎥 Video", color: "#ef4444" },
                    { id: "thermal", label: "🌡 Thermal", color: "#f59e0b" }
                ]
                
                delegate: Rectangle {
                    width: 90
                    height: 32
                    radius: 6
                    color: cameraMode === modelData.id ? modelData.color : "#1e2535"
                    border.color: modelData.color
                    border.width: 1
                    
                    Text {
                        anchors.centerIn: parent
                        text: modelData.label
                        color: cameraMode === modelData.id ? "#ffffff" : "#94a3b8"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                    }
                    
                    MouseArea {
                        anchors.fill: parent
                        onClicked: camera.setCameraMode(modelData.id)
                    }
                }
            }
        }
        
        // Camera Settings (Resolution, FPS, etc.)
        Grid {
            width: parent.width
            columns: 2
            columnSpacing: 12
            rowSpacing: 8
            
            // Resolution
            Column {
                width: (parent.width - 12) / 2
                spacing: 2
                
                Text {
                    text: "Resolution"
                    color: "#64748b"
                    font.pixelSize: 9
                }
                
                ComboBox {
                    width: parent.width
                    height: 28
                    model: ["4K (3840x2160)", "1080p (1920x1080)", "720p (1280x720)"]
                    currentIndex: 1
                    onCurrentIndexChanged: camera.setResolution(currentIndex)
                }
            }
            
            // FPS
            Column {
                width: (parent.width - 12) / 2
                spacing: 2
                
                Text {
                    text: "Frame Rate"
                    color: "#64748b"
                    font.pixelSize: 9
                }
                
                ComboBox {
                    width: parent.width
                    height: 28
                    model: ["60 FPS", "30 FPS", "24 FPS"]
                    currentIndex: 1
                    onCurrentIndexChanged: camera.setFPS(currentIndex)
                }
            }
            
            // Exposure
            Column {
                width: (parent.width - 12) / 2
                spacing: 2
                
                Text {
                    text: "Exposure"
                    color: "#64748b"
                    font.pixelSize: 9
                }
                
                Slider {
                    id: exposureSlider
                    width: parent.width
                    from: -3
                    to: 3
                    stepSize: 0.5
                    value: 0
                    onMoved: camera.setExposure(value)
                }
            }
            
            // ISO
            Column {
                width: (parent.width - 12) / 2
                spacing: 2
                
                Text {
                    text: "ISO"
                    color: "#64748b"
                    font.pixelSize: 9
                }
                
                ComboBox {
                    width: parent.width
                    height: 28
                    model: ["Auto", "100", "200", "400", "800", "1600"]
                    currentIndex: 0
                    onCurrentIndexChanged: camera.setISO(currentIndex)
                }
            }
        }
        
        // Capture Buttons
        Row {
            width: parent.width
            spacing: 8
            
            // Take Photo
            Rectangle {
                width: (parent.width - 8) / 2
                height: 40
                radius: 6
                color: photoMouseArea.pressed ? "#2563eb" : "#3b82f6"
                
                Row {
                    anchors.centerIn: parent
                    spacing: 6
                    
                    Text {
                        text: "📷"
                        font.pixelSize: 16
                    }
                    
                    Text {
                        text: "Take Photo"
                        color: "#ffffff"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                    }
                }
                
                MouseArea {
                    id: photoMouseArea
                    anchors.fill: parent
                    onClicked: camera.takePhoto()
                }
            }
            
            // Record Video
            Rectangle {
                width: (parent.width - 8) / 2
                height: 40
                radius: 6
                color: camera.isRecording ? "#dc2626" : (videoMouseArea.pressed ? "#b91c1c" : "#ef4444")
                
                Row {
                    anchors.centerIn: parent
                    spacing: 6
                    
                    Rectangle {
                        width: 12
                        height: 12
                        radius: camera.isRecording ? 2 : 6
                        color: "#ffffff"
                        anchors.verticalCenter: parent.verticalCenter
                        
                        // Blinking animation when recording
                        SequentialAnimation on opacity {
                            running: camera.isRecording
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.3; duration: 500 }
                            NumberAnimation { to: 1.0; duration: 500 }
                        }
                    }
                    
                    Text {
                        text: camera.isRecording ? "Stop Recording" : "Start Recording"
                        color: "#ffffff"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                    }
                }
                
                MouseArea {
                    id: videoMouseArea
                    anchors.fill: parent
                    onClicked: camera.toggleRecording()
                }
            }
        }
    }
}
```

#### 1.2 Backend Camera Context

**New File:** `tools/ui/context/camera_context.py`

```python
from PySide6.QtCore import QObject, Signal, Slot, Property
from typing import Optional
import cv2
import numpy as np

class CameraContext(QObject):
    """
    Camera control and video streaming backend.
    
    Manages:
    - Camera mode (Photo/Video/Thermal)
    - Camera settings (resolution, FPS, exposure, ISO)
    - Photo capture and video recording
    - Live video streaming
    - Thermal camera integration
    """
    
    # Signals
    cameraModeChanged = Signal(str, arguments=["mode"])
    resolutionChanged = Signal(int, arguments=["index"])
    fpsChanged = Signal(int, arguments=["fps"])
    exposureChanged = Signal(float, arguments=["value"])
    isoChanged = Signal(int, arguments=["iso"])
    isRecordingChanged = Signal(bool, arguments=["recording"])
    photoTaken = Signal(str, arguments=["filepath"])
    videoFrameReady = Signal(object, arguments=["frame"])
    thermalFrameReady = Signal(object, arguments=["frame"])
    logMessage = Signal(str, str, arguments=["level", "message"])
    
    def __init__(self):
        super().__init__()
        self._camera_mode = "photo"  # "photo", "video", "thermal"
        self._resolution_index = 1  # 0=4K, 1=1080p, 2=720p
        self._fps = 30
        self._exposure = 0.0
        self._iso = 0  # 0=Auto
        self._is_recording = False
        self._video_writer: Optional[cv2.VideoWriter] = None
        self._camera: Optional[cv2.VideoCapture] = None
        self._thermal_camera: Optional[object] = None
        
    @Property(str, notify=cameraModeChanged)
    def cameraMode(self):
        return self._camera_mode
    
    @Slot(str)
    def setCameraMode(self, mode: str):
        """Set camera mode (photo/video/thermal)."""
        if mode in ["photo", "video", "thermal"]:
            self._camera_mode = mode
            self.cameraModeChanged.emit(mode)
            self.logMessage.emit("INFO", f"[CAMERA] Mode: {mode}")
    
    @Slot(int)
    def setResolution(self, index: int):
        """Set camera resolution."""
        resolutions = [(3840, 2160), (1920, 1080), (1280, 720)]
        if 0 <= index < len(resolutions):
            self._resolution_index = index
            width, height = resolutions[index]
            if self._camera:
                self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.resolutionChanged.emit(index)
            self.logMessage.emit("INFO", f"[CAMERA] Resolution: {width}x{height}")
    
    @Slot(int)
    def setFPS(self, index: int):
        """Set camera frame rate."""
        fps_values = [60, 30, 24]
        if 0 <= index < len(fps_values):
            self._fps = fps_values[index]
            if self._camera:
                self._camera.set(cv2.CAP_PROP_FPS, self._fps)
            self.fpsChanged.emit(self._fps)
            self.logMessage.emit("INFO", f"[CAMERA] FPS: {self._fps}")
    
    @Slot(float)
    def setExposure(self, value: float):
        """Set camera exposure (-3 to +3)."""
        self._exposure = value
        if self._camera:
            self._camera.set(cv2.CAP_PROP_EXPOSURE, value)
        self.exposureChanged.emit(value)
    
    @Slot(int)
    def setISO(self, index: int):
        """Set camera ISO."""
        iso_values = [0, 100, 200, 400, 800, 1600]  # 0 = Auto
        if 0 <= index < len(iso_values):
            self._iso = iso_values[index]
            if self._camera and self._iso > 0:
                self._camera.set(cv2.CAP_PROP_ISO_SPEED, self._iso)
            self.isoChanged.emit(self._iso)
    
    @Slot()
    def takePhoto(self):
        """Capture a single photo."""
        if not self._camera:
            self.logMessage.emit("ERROR", "[CAMERA] No camera connected")
            return
        
        ret, frame = self._camera.read()
        if ret:
            import time
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filepath = f"photos/photo_{timestamp}.jpg"
            cv2.imwrite(filepath, frame)
            self.photoTaken.emit(filepath)
            self.logMessage.emit("INFO", f"[CAMERA] Photo saved: {filepath}")
        else:
            self.logMessage.emit("ERROR", "[CAMERA] Failed to capture photo")
    
    @Slot()
    def toggleRecording(self):
        """Start/stop video recording."""
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()
    
    def _start_recording(self):
        """Start video recording."""
        if not self._camera:
            self.logMessage.emit("ERROR", "[CAMERA] No camera connected")
            return
        
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filepath = f"videos/video_{timestamp}.mp4"
        
        resolutions = [(3840, 2160), (1920, 1080), (1280, 720)]
        width, height = resolutions[self._resolution_index]
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self._video_writer = cv2.VideoWriter(filepath, fourcc, self._fps, (width, height))
        
        self._is_recording = True
        self.isRecordingChanged.emit(True)
        self.logMessage.emit("INFO", f"[CAMERA] Recording started: {filepath}")
    
    def _stop_recording(self):
        """Stop video recording."""
        if self._video_writer:
            self._video_writer.release()
            self._video_writer = None
        
        self._is_recording = False
        self.isRecordingChanged.emit(False)
        self.logMessage.emit("INFO", "[CAMERA] Recording stopped")
    
    @Property(bool, notify=isRecordingChanged)
    def isRecording(self):
        return self._is_recording
    
    def start_streaming(self):
        """Start live video streaming."""
        # Implementation for MAVLink video streaming
        pass
    
    def stop_streaming(self):
        """Stop live video streaming."""
        pass
```

### Phase 2: Video Streaming Display (Week 3-4)

#### 2.1 Add Video Feed to Gimbal Panel

**Component:** Video preview window with overlay controls

```qml
// ── VIDEO STREAM PREVIEW ───────────────────────────────────
Rectangle {
    width: parent.width
    height: 300
    radius: 8
    color: "#000000"
    border.color: "#2d3748"
    border.width: 1
    
    // Video display area
    Image {
        id: videoFeed
        anchors.fill: parent
        anchors.margins: 2
        fillMode: Image.PreserveAspectFit
        source: camera.videoFrameUrl
        
        // No signal overlay
        Rectangle {
            anchors.fill: parent
            color: "#1a2035"
            visible: !camera.isStreaming
            
            Column {
                anchors.centerIn: parent
                spacing: 12
                
                Text {
                    text: "📡"
                    font.pixelSize: 48
                    color: "#64748b"
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                
                Text {
                    text: "No Video Signal"
                    color: "#94a3b8"
                    font.pixelSize: 12
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                
                Rectangle {
                    width: 120
                    height: 32
                    radius: 6
                    color: "#3b82f6"
                    anchors.horizontalCenter: parent.horizontalCenter
                    
                    Text {
                        anchors.centerIn: parent
                        text: "Start Stream"
                        color: "#ffffff"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                    }
                    
                    MouseArea {
                        anchors.fill: parent
                        onClicked: camera.startStreaming()
                    }
                }
            }
        }
        
        // Recording indicator
        Rectangle {
            anchors { top: parent.top; right: parent.right; margins: 8 }
            width: recordingRow.width + 12
            height: 24
            radius: 12
            color: "#dc2626"
            visible: camera.isRecording
            
            Row {
                id: recordingRow
                anchors.centerIn: parent
                spacing: 6
                
                Rectangle {
                    width: 8
                    height: 8
                    radius: 4
                    color: "#ffffff"
                    anchors.verticalCenter: parent.verticalCenter
                    
                    SequentialAnimation on opacity {
                        running: camera.isRecording
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.3; duration: 500 }
                        NumberAnimation { to: 1.0; duration: 500 }
                    }
                }
                
                Text {
                    text: "REC"
                    color: "#ffffff"
                    font.pixelSize: 9
                    font.weight: Font.Bold
                }
            }
        }
        
        // Crosshair overlay
        Canvas {
            anchors.fill: parent
            visible: camera.showCrosshair
            
            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.strokeStyle = "#22c55e"
                ctx.lineWidth = 2
                
                // Center crosshair
                var cx = width / 2
                var cy = height / 2
                var size = 20
                
                ctx.beginPath()
                ctx.moveTo(cx - size, cy)
                ctx.lineTo(cx + size, cy)
                ctx.moveTo(cx, cy - size)
                ctx.lineTo(cx, cy + size)
                ctx.stroke()
                
                // Center circle
                ctx.beginPath()
                ctx.arc(cx, cy, 5, 0, 2 * Math.PI)
                ctx.stroke()
            }
        }
        
        // Telemetry overlay
        Column {
            anchors { left: parent.left; top: parent.top; margins: 8 }
            spacing: 2
            
            Text {
                text: "ALT: " + telemetry.altitude.toFixed(1) + " m"
                color: "#22c55e"
                font.pixelSize: 10
                font.family: "Consolas"
                style: Text.Outline
                styleColor: "#000000"
            }
            
            Text {
                text: "SPD: " + telemetry.groundSpeed.toFixed(1) + " m/s"
                color: "#22c55e"
                font.pixelSize: 10
                font.family: "Consolas"
                style: Text.Outline
                styleColor: "#000000"
            }
            
            Text {
                text: "BAT: " + telemetry.batteryPercent + "%"
                color: telemetry.batteryPercent > 30 ? "#22c55e" : "#ef4444"
                font.pixelSize: 10
                font.family: "Consolas"
                style: Text.Outline
                styleColor: "#000000"
            }
        }
    }
    
    // Stream controls
    Row {
        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: 8 }
        spacing: 8
        
        // Quality selector
        Rectangle {
            width: 80
            height: 28
            radius: 14
            color: "#1a2035cc"
            border.color: "#3b82f6"
            border.width: 1
            
            Text {
                anchors.centerIn: parent
                text: camera.streamQuality
                color: "#e2e8f0"
                font.pixelSize: 9
                font.weight: Font.Bold
            }
            
            MouseArea {
                anchors.fill: parent
                onClicked: camera.cycleStreamQuality()
            }
        }
        
        // Fullscreen toggle
        Rectangle {
            width: 28
            height: 28
            radius: 14
            color: "#1a2035cc"
            border.color: "#3b82f6"
            border.width: 1
            
            Text {
                anchors.centerIn: parent
                text: "⛶"
                color: "#e2e8f0"
                font.pixelSize: 14
            }
            
            MouseArea {
                anchors.fill: parent
                onClicked: camera.toggleFullscreen()
            }
        }
    }
}
```

### Phase 3: Thermal Camera Integration (Week 5-6)

#### 3.1 Thermal Camera Settings

```qml
// ── THERMAL CAMERA SETTINGS ────────────────────────────────
Rectangle {
    width: parent.width
    height: thermalCol.implicitHeight + 20
    radius: 8
    color: "#1a2035"
    border.color: "#2d3748"
    border.width: 1
    visible: camera.cameraMode === "thermal"
    
    Column {
        id: thermalCol
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
        spacing: 12
        
        Text {
            text: "THERMAL CAMERA SETTINGS"
            color: "#f59e0b"
            font.pixelSize: 10
            font.weight: Font.Bold
            font.letterSpacing: 1
        }
        
        // Temperature Range
        Column {
            width: parent.width
            spacing: 4
            
            Text {
                text: "Temperature Range"
                color: "#64748b"
                font.pixelSize: 9
            }
            
            Row {
                width: parent.width
                spacing: 8
                
                Column {
                    width: (parent.width - 8) / 2
                    spacing: 2
                    
                    Text {
                        text: "Min: " + thermalMinSlider.value.toFixed(0) + "°C"
                        color: "#94a3b8"
                        font.pixelSize: 8
                    }
                    
                    Slider {
                        id: thermalMinSlider
                        width: parent.width
                        from: -20
                        to: 50
                        value: 0
                        onMoved: thermal.setMinTemp(value)
                    }
                }
                
                Column {
                    width: (parent.width - 8) / 2
                    spacing: 2
                    
                    Text {
                        text: "Max: " + thermalMaxSlider.value.toFixed(0) + "°C"
                        color: "#94a3b8"
                        font.pixelSize: 8
                    }
                    
                    Slider {
                        id: thermalMaxSlider
                        width: parent.width
                        from: 50
                        to: 150
                        value: 100
                        onMoved: thermal.setMaxTemp(value)
                    }
                }
            }
        }
        
        // Color Palette
        Column {
            width: parent.width
            spacing: 4
            
            Text {
                text: "Color Palette"
                color: "#64748b"
                font.pixelSize: 9
            }
            
            Row {
                width: parent.width
                spacing: 4
                
                Repeater {
                    model: [
                        { id: "ironbow", label: "Ironbow" },
                        { id: "rainbow", label: "Rainbow" },
                        { id: "grayscale", label: "Grayscale" },
                        { id: "hot", label: "Hot" }
                    ]
                    
                    delegate: Rectangle {
                        width: (parent.width - 12) / 4
                        height: 32
                        radius: 4
                        color: thermal.palette === modelData.id ? "#f59e0b" : "#1e2535"
                        border.color: "#f59e0b"
                        border.width: 1
                        
                        Text {
                            anchors.centerIn: parent
                            text: modelData.label
                            color: thermal.palette === modelData.id ? "#0f172a" : "#94a3b8"
                            font.pixelSize: 8
                            font.weight: Font.Bold
                        }
                        
                        MouseArea {
                            anchors.fill: parent
                            onClicked: thermal.setPalette(modelData.id)
                        }
                    }
                }
            }
        }
        
        // Hotspot Detection
        Row {
            width: parent.width
            spacing: 8
            
            Text {
                text: "Hotspot Detection"
                color: "#64748b"
                font.pixelSize: 9
                anchors.verticalCenter: parent.verticalCenter
            }
            
            Item { width: parent.width - 200; height: 1 }
            
            Switch {
                id: hotspotSwitch
                checked: thermal.hotspotDetectionEnabled
                onToggled: thermal.setHotspotDetection(checked)
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        
        // Hotspot Threshold
        Column {
            width: parent.width
            spacing: 2
            visible: hotspotSwitch.checked
            
            Text {
                text: "Hotspot Threshold: " + hotspotThresholdSlider.value.toFixed(0) + "°C"
                color: "#64748b"
                font.pixelSize: 9
            }
            
            Slider {
                id: hotspotThresholdSlider
                width: parent.width
                from: 50
                to: 120
                value: 80
                onMoved: thermal.setHotspotThreshold(value)
            }
        }
    }
}
```

### Phase 4: Solar Inspection Workflow Improvements (Week 7-8)

#### 4.1 Solar Inspection Wizard

**New Component:** Step-by-step wizard for solar inspection setup

```qml
// ── SOLAR INSPECTION WIZARD ────────────────────────────────
Rectangle {
    id: solarWizard
    width: parent.width
    height: wizardCol.implicitHeight + 24
    radius: 8
    color: "#1a2035"
    border.color: "#f59e0b"
    border.width: 2
    visible: mission && mission.missionMode === 2
    
    property int currentStep: 0  // 0=Setup, 1=Rows, 2=Camera, 3=Review
    
    Column {
        id: wizardCol
        width: parent.width - 24
        anchors.centerIn: parent
        spacing: 16
        
        // Step Indicator
        Row {
            width: parent.width
            spacing: 8
            
            Repeater {
                model: [
                    { label: "1. Setup", icon: "⚙" },
                    { label: "2. Panel Rows", icon: "☀" },
                    { label: "3. Camera", icon: "📷" },
                    { label: "4. Review", icon: "✓" }
                ]
                
                delegate: Rectangle {
                    width: (parent.width - 24) / 4
                    height: 48
                    radius: 6
                    color: solarWizard.currentStep === index ? "#f59e0b" : "#1e2535"
                    border.color: solarWizard.currentStep >= index ? "#f59e0b" : "#334155"
                    border.width: 2
                    
                    Column {
                        anchors.centerIn: parent
                        spacing: 4
                        
                        Text {
                            text: modelData.icon
                            font.pixelSize: 18
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        
                        Text {
                            text: modelData.label
                            color: solarWizard.currentStep === index ? "#0f172a" : "#94a3b8"
                            font.pixelSize: 8
                            font.weight: Font.Bold
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                    }
                }
            }
        }
        
        Rectangle { width: parent.width; height: 1; color: "#2d3748" }
        
        // Step Content
        Loader {
            width: parent.width
            sourceComponent: {
                switch (solarWizard.currentStep) {
                    case 0: return setupStep
                    case 1: return rowsStep
                    case 2: return cameraStep
                    case 3: return reviewStep
                    default: return setupStep
                }
            }
        }
        
        // Navigation Buttons
        Row {
            width: parent.width
            spacing: 8
            
            Rectangle {
                width: (parent.width - 8) / 2
                height: 36
                radius: 6
                color: "#334155"
                visible: solarWizard.currentStep > 0
                
                Text {
                    anchors.centerIn: parent
                    text: "← Previous"
                    color: "#e2e8f0"
                    font.pixelSize: 10
                    font.weight: Font.Bold
                }
                
                MouseArea {
                    anchors.fill: parent
                    onClicked: solarWizard.currentStep--
                }
            }
            
            Item { width: solarWizard.currentStep === 0 ? (parent.width - 8) / 2 : 0; height: 1 }
            
            Rectangle {
                width: (parent.width - 8) / 2
                height: 36
                radius: 6
                color: solarWizard.currentStep === 3 ? "#22c55e" : "#f59e0b"
                
                Text {
                    anchors.centerIn: parent
                    text: solarWizard.currentStep === 3 ? "✓ Start Mission" : "Next →"
                    color: "#ffffff"
                    font.pixelSize: 10
                    font.weight: Font.Bold
                }
                
                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        if (solarWizard.currentStep === 3) {
                            mission.generateSolarInspection()
                            root.Window.window.startGlobalMission()
                        } else {
                            solarWizard.currentStep++
                        }
                    }
                }
            }
        }
    }
}

// Step Components
Component {
    id: setupStep
    Column {
        width: parent.width
        spacing: 12
        
        Text {
            text: "Configure inspection parameters"
            color: "#e2e8f0"
            font.pixelSize: 11
        }
        
        // Altitude, Gimbal, etc. (existing controls)
    }
}

Component {
    id: rowsStep
    Column {
        width: parent.width
        spacing: 12
        
        Text {
            text: "Define solar panel rows on the map"
            color: "#e2e8f0"
            font.pixelSize: 11
        }
        
        Text {
            text: "Click 'Add Panel Row' and then click two points on the map to define each row"
            color: "#94a3b8"
            font.pixelSize: 9
            wrapMode: Text.WordWrap
            width: parent.width
        }
        
        // Row list (existing)
    }
}

Component {
    id: cameraStep
    Column {
        width: parent.width
        spacing: 12
        
        Text {
            text: "Configure camera settings"
            color: "#e2e8f0"
            font.pixelSize: 11
        }
        
        // Camera mode selection
        // Thermal settings if thermal mode
    }
}

Component {
    id: reviewStep
    Column {
        width: parent.width
        spacing: 12
        
        Text {
            text: "Review mission plan"
            color: "#e2e8f0"
            font.pixelSize: 11
        }
        
        // Mission statistics
        // Preview on map
    }
}
```

### Phase 5: Seeding Mode Improvements (Week 9-10)

#### 5.1 Seeding Visual Feedback

**Add to MissionPanel.qml:**

```qml
// ── SEEDING OPERATION STATUS ───────────────────────────────
Rectangle {
    width: parent.width
    height: seedingStatusCol.implicitHeight + 20
    radius: 8
    color: "#1a2035"
    border.color: "#8b5cf6"
    border.width: 1
    visible: mission && mission.missionMode === 1 && mission.seedingActive
    
    Column {
        id: seedingStatusCol
        width: parent.width - 20
        anchors.centerIn: parent
        spacing: 12
        
        Row {
            width: parent.width
            spacing: 8
            
            Rectangle {
                width: 4
                height: 20
                color: "#8b5cf6"
                radius: 2
            }
            
            Text {
                text: "SEEDING IN PROGRESS"
                color: "#8b5cf6"
                font.pixelSize: 11
                font.weight: Font.Bold
                font.letterSpacing: 1
            }
        }
        
        // Progress bar
        Rectangle {
            width: parent.width
            height: 24
            radius: 12
            color: "#1e2535"
            border.color: "#8b5cf6"
            border.width: 1
            
            Rectangle {
                width: parent.width * (mission.seedingProgress / 100)
                height: parent.height
                radius: 12
                color: "#8b5cf6"
                
                Behavior on width {
                    NumberAnimation { duration: 300 }
                }
            }
            
            Text {
                anchors.centerIn: parent
                text: mission.seedingProgress.toFixed(0) + "%"
                color: "#ffffff"
                font.pixelSize: 10
                font.weight: Font.Bold
                font.family: "Consolas"
            }
        }
        
        // Statistics
        Grid {
            width: parent.width
            columns: 2
            columnSpacing: 12
            rowSpacing: 4
            
            Text {
                text: "Seeds Dispensed:"
                color: "#64748b"
                font.pixelSize: 9
            }
            Text {
                text: mission.seedsDispensed + " / " + mission.totalSeeds
                color: "#e2e8f0"
                font.pixelSize: 9
                font.family: "Consolas"
            }
            
            Text {
                text: "Area Covered:"
                color: "#64748b"
                font.pixelSize: 9
            }
            Text {
                text: mission.areaCovered.toFixed(1) + " / " + mission.totalArea.toFixed(1) + " m²"
                color: "#e2e8f0"
                font.pixelSize: 9
                font.family: "Consolas"
            }
            
            Text {
                text: "Time Elapsed:"
                color: "#64748b"
                font.pixelSize: 9
            }
            Text {
                text: formatTime(mission.elapsedTime)
                color: "#e2e8f0"
                font.pixelSize: 9
                font.family: "Consolas"
            }
        }
        
        // Camera preview (if available)
        Rectangle {
            width: parent.width
            height: 150
            radius: 6
            color: "#000000"
            visible: camera.isStreaming
            
            Image {
                anchors.fill: parent
                anchors.margins: 2
                source: camera.videoFrameUrl
                fillMode: Image.PreserveAspectFit
            }
            
            Text {
                anchors { bottom: parent.bottom; left: parent.left; margins: 8 }
                text: "LIVE FEED"
                color: "#22c55e"
                font.pixelSize: 8
                font.weight: Font.Bold
                style: Text.Outline
                styleColor: "#000000"
            }
        }
    }
}
```

---

## Implementation Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1: Camera Controls | 2 weeks | Camera settings UI, photo/video capture |
| Phase 2: Video Streaming | 2 weeks | Live video feed, stream controls |
| Phase 3: Thermal Integration | 2 weeks | Thermal camera settings, hotspot detection |
| Phase 4: Solar Workflow | 2 weeks | Step-by-step wizard, improved UX |
| Phase 5: Seeding Improvements | 2 weeks | Visual feedback, progress tracking |
| **Total** | **10 weeks** | **Complete camera/video integration** |

---

## Technical Requirements

### Hardware
- Camera-equipped drone (RGB camera)
- Thermal camera (optional, for solar inspection)
- MAVLink video streaming support
- Gimbal with 3-axis control

### Software Dependencies
- OpenCV (`cv2`) for video processing
- MAVLink camera protocol support
- Thermal camera SDK (manufacturer-specific)
- Video codec support (H.264/H.265)

### Backend Integration Points
1. **MAVLink Camera Commands**
   - `MAV_CMD_DO_DIGICAM_CONTROL` (203) - Trigger camera
   - `MAV_CMD_VIDEO_START_CAPTURE` (2500) - Start recording
   - `MAV_CMD_VIDEO_STOP_CAPTURE` (2501) - Stop recording
   - `MAV_CMD_REQUEST_VIDEO_STREAM_INFORMATION` (2504)

2. **Video Streaming**
   - RTSP/RTP stream from drone
   - GStreamer pipeline for decoding
   - Qt Multimedia for display

3. **Thermal Camera**
   - FLIR Lepton SDK integration
   - Temperature calibration
   - Hotspot detection algorithm

---

## Testing Strategy

### Unit Tests
- Camera mode switching
- Resolution/FPS changes
- Photo capture
- Video recording start/stop
- Thermal palette selection

### Integration Tests
- MAVLink camera command sending
- Video stream reception
- Gimbal + camera coordination
- Solar inspection workflow end-to-end

### User Acceptance Tests
- Intuitive camera controls
- Clear visual feedback
- Responsive video streaming
- Accurate thermal readings

---

## Success Criteria

✅ **Camera Integration**
- [ ] Camera mode selection (Photo/Video/Thermal)
- [ ] Resolution and FPS configuration
- [ ] Exposure and ISO control
- [ ] Photo capture with timestamp
- [ ] Video recording with start/stop

✅ **Video Streaming**
- [ ] Live video feed display
- [ ] Stream quality selection
- [ ] Fullscreen mode
- [ ] Telemetry overlay
- [ ] Recording indicator

✅ **Thermal Camera**
- [ ] Temperature range configuration
- [ ] Color palette selection
- [ ] Hotspot detection
- [ ] Temperature overlay on map

✅ **Solar Inspection**
- [ ] Step-by-step wizard
- [ ] Clear workflow guidance
- [ ] Camera preview during planning
- [ ] Automatic mission generation
- [ ] Visual feedback during execution

✅ **Seeding Mode**
- [ ] Progress tracking
- [ ] Real-time statistics
- [ ] Camera feed integration
- [ ] Visual feedback on map

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Prioritize phases** based on user needs
3. **Set up development environment** with camera hardware
4. **Begin Phase 1 implementation**
5. **Iterate based on user feedback**

---

## References

- [Solar Inspection UI Integration](../ui/solar-inspection-ui-integration.md)
- [Gimbal Panel Documentation](../../tools/ui/qml/panels/GimbalPanel.qml)
- [MAVLink Camera Protocol](https://mavlink.io/en/services/camera.html)
- [OpenCV Python Documentation](https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html)