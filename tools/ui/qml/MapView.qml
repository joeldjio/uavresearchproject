import QtQuick
import QtQuick.Controls
import QtWebEngine
import "components" as Cmp

// Full-screen OSM map + HUD instruments + 3D drone overlay
Item {
    id: root

    // ── live telemetry helpers (first drone or selected) ──────────────────
    // Use global selectedDroneId from AppState (set by Header dropdown)
    property string selectedDroneId: Cmp.AppState.selectedDroneId

    function snap(key, def) {
        if (telemetryModel.count === 0) return def
        // resolve which drone ID to use
        var ids = swarm.droneIds()
        if (ids.length === 0) return def
        var did = (selectedDroneId !== "" && ids.indexOf(selectedDroneId) >= 0)
                  ? selectedDroneId
                  : ids[0]
        var s = telemetryModel.snapshotFor(did)
        return (s && s[key] !== undefined) ? s[key] : def
    }

    property bool pickMode: false
    property bool boundaryDrawMode: false
    property bool solarRowDrawMode: false
    property var solarRowStart: null
    property string currentMapType: "dark"

    function setMapType(typeName) {
        currentMapType = typeName
        webView.runJavaScript("setMapType(" + JSON.stringify(typeName) + ")")
    }

    function setPickMode(enabled) {
        pickMode = enabled
        webView.runJavaScript("setPickMode(" + enabled + ")")
    }

    function setBoundaryDrawMode(enabled) {
        boundaryDrawMode = enabled
        webView.runJavaScript("setBoundaryDrawMode(" + enabled + ")")
    }

    function setSolarRowDrawMode(enabled) {
        solarRowDrawMode = enabled
        solarRowStart = null
        webView.runJavaScript("setSolarRowDrawMode(" + enabled + ")")
    }

    function updateFieldBoundary(points) {
        webView.runJavaScript("updateFieldBoundary(" + JSON.stringify(points) + ")")
    }

    function updateExclusionZones(zones) {
        webView.runJavaScript("updateExclusionZones(" + JSON.stringify(zones) + ")")
    }

    function updateCoverageWaypoints(waypoints) {
        webView.runJavaScript("updateCoverageWaypoints(" + JSON.stringify(waypoints) + ")")
    }

    function clearFieldCoverage() {
        webView.runJavaScript("clearFieldCoverage()")
    }

    function updateCollisionPredictions(predictions) {
        webView.runJavaScript("updateCollisionPredictions(" + JSON.stringify(predictions) + ")")
    }

    function clearCollisionPredictions() {
        webView.runJavaScript("clearCollisionVisualization()")
    }

    function updateSolarPanelRows(rows) {
        webView.runJavaScript("updateSolarPanelRows(" + JSON.stringify(rows) + ")")
    }

    function updateThermalHotspots(hotspots) {
        webView.runJavaScript("updateThermalHotspots(" + JSON.stringify(hotspots) + ")")
    }

    function clearSolarInspection() {
        webView.runJavaScript("clearSolarInspection()")
    }

    function updateSolarTriggerPoints(points) {
        webView.runJavaScript("updateSolarTriggerPoints(" + JSON.stringify(points) + ")")
    }

    function updateSolarFootprints(points) {
        webView.runJavaScript("updateSolarFootprints(" + JSON.stringify(points) + ")")
    }

    function updateSolarMissionRows(rows) {
        webView.runJavaScript("updateSolarMissionRows(" + JSON.stringify(rows) + ")")
    }

    function clearSolarPreviewOverlays() {
        webView.runJavaScript("clearSolarPreviewOverlays()")
    }

    function updateSeedingDropPoints(points) {
        webView.runJavaScript("updateSeedingDropPoints(" + JSON.stringify(points) + ")")
    }

    function updateSeedingFlightRows(rows) {
        webView.runJavaScript("updateSeedingFlightRows(" + JSON.stringify(rows) + ")")
    }

    function updateSeedingExclusionZones(zones) {
        webView.runJavaScript("updateSeedingExclusionZones(" + JSON.stringify(zones) + ")")
    }

    function clearSeedingMission() {
        webView.runJavaScript("clearSeedingMission()")
    }

    // ── Map ──────────────────────────────────────────────────────────────
    WebEngineView {
        id: webView
        anchors.fill: parent
        z: 0
        Component.onCompleted: loadHtml(root.mapHtml, "qrc:/")
        onLoadingChanged: function(info) {
            if (info.status === WebEngineLoadingInfo.LoadSucceededStatus)
                console.log("[MapView] Local map loaded")
        }
        onNavigationRequested: function(req) {
            var url = req.url.toString()
            if (url.startsWith("qrc://pick?")) {
                req.reject()
                var params = url.substring("qrc://pick?".length).split("&")
                var lat = 0, lon = 0
                for (var i = 0; i < params.length; i++) {
                    var kv = params[i].split("=")
                    if (kv[0] === "lat") lat = parseFloat(kv[1])
                    if (kv[0] === "lon") lon = parseFloat(kv[1])
                }
                root.mapPickSelected(lat, lon)
            } else if (url.startsWith("qrc://boundary-point?")) {
                req.reject()
                var params = url.substring("qrc://boundary-point?".length).split("&")
                var lat = 0, lon = 0
                for (var i = 0; i < params.length; i++) {
                    var kv = params[i].split("=")
                    if (kv[0] === "lat") lat = parseFloat(kv[1])
                    if (kv[0] === "lon") lon = parseFloat(kv[1])
                }
                root.boundaryPointSelected(lat, lon)
            } else if (url.startsWith("qrc://solar-row-point?")) {
                req.reject()
                var params = url.substring("qrc://solar-row-point?".length).split("&")
                var lat = 0, lon = 0
                for (var i = 0; i < params.length; i++) {
                    var kv = params[i].split("=")
                    if (kv[0] === "lat") lat = parseFloat(kv[1])
                    if (kv[0] === "lon") lon = parseFloat(kv[1])
                }
                root.solarRowPointSelected(lat, lon)
            } else if (url.startsWith("qrc://waypoint-moved?")) {
                req.reject()
                var params = url.substring("qrc://waypoint-moved?".length).split("&")
                var index = -1, lat = 0, lon = 0
                for (var i = 0; i < params.length; i++) {
                    var kv = params[i].split("=")
                    if (kv[0] === "index") index = parseInt(kv[1])
                    if (kv[0] === "lat") lat = parseFloat(kv[1])
                    if (kv[0] === "lon") lon = parseFloat(kv[1])
                }
                if (index >= 0) {
                    root.waypointMoved(index, lat, lon)
                }
            } else if (url.startsWith("qrc://boundary-moved?")) {
                req.reject()
                var params = url.substring("qrc://boundary-moved?".length).split("&")
                var index = -1, lat = 0, lon = 0
                for (var i = 0; i < params.length; i++) {
                    var kv = params[i].split("=")
                    if (kv[0] === "index") index = parseInt(kv[1])
                    if (kv[0] === "lat") lat = parseFloat(kv[1])
                    if (kv[0] === "lon") lon = parseFloat(kv[1])
                }
                if (index >= 0) {
                    root.boundaryPointMoved(index, lat, lon)
                }
            } else if (url === "about:blank" || url.startsWith("qrc:/") || url.startsWith("data:")) {
                // Allow the initial blank page load and qrc/data URIs
                req.accept()
            } else {
                // Reject navigation to external URLs — map content is self-contained
                req.reject()
                console.warn("[MapView] Blocked external navigation to: " + url)
            }
        }
    }

    // ── Map type switcher overlay ─────────────────────────────────────
    Row {
        anchors { top: parent.top; right: parent.right; topMargin: 10; rightMargin: 10 }
        spacing: 4
        z: 10

        Repeater {
            model: [
                { id: "dark",      label: "Dark",      icon: "◐" },
                { id: "street",    label: "Street",    icon: "▢" },
                { id: "satellite", label: "Satellite", icon: "◈" },
                { id: "hybrid",    label: "Hybrid",    icon: "◆" },
                { id: "topo",      label: "Topo",      icon: "⛰" },
            ]
            delegate: Rectangle {
                width: 70; height: 26; radius: 5
                color: root.currentMapType === modelData.id
                       ? "#2563eb" : "#cc0d1117"
                border.color: root.currentMapType === modelData.id
                              ? "#3b82f6" : "#334155"
                border.width: 1
                Behavior on color { ColorAnimation { duration: 120 } }
                Row {
                    anchors.centerIn: parent; spacing: 4
                    Text { text: modelData.icon; font.pixelSize: 11 }
                    Text {
                        text: modelData.label
                        color: root.currentMapType === modelData.id ? "white" : "#94a3b8"
                        font.pixelSize: 9; font.weight: Font.Bold
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: root.setMapType(modelData.id)
                }
            }
        }
    }

    // ── Video PIP Overlay — bottom-right, only visible when stream is receiving ──
    // R-10: absolutely no blank/broken video before status === "receiving"
    Rectangle {
        id: videoPipOverlay
        anchors { bottom: parent.bottom; right: parent.right; bottomMargin: 12; rightMargin: 12 }
        width: 360; height: 202   // 16:9
        radius: 8
        z: 10
        color: "#cc0d1117"
        border.color: "#22c55e"; border.width: 1
        clip: true
        property var _videoStatus: ({})

        // Only show when a stream is being received
        visible: {
            var s = _videoStatus
            return !!(s && s.status === "receiving" && s.activeTarget === "map" && s.hasFrame)
        }

        // Refresh visibility every 1s
        Timer { interval: 250; running: true; repeat: true
            onTriggered: {
                if (typeof videoStream === "undefined" || !videoStream) { videoPipOverlay._videoStatus = {}; return }
                // Prefer the UI-selected drone; fall back to whichever drone has an active stream
                var did = (typeof Cmp !== "undefined" && Cmp.AppState ? Cmp.AppState.selectedDroneId : "")
                          || videoStream.activeDroneId
                videoPipOverlay._videoStatus = did ? videoStream.getVideoStatus(did) : {}
                if (did && videoPipOverlay.visible)
                    mapVideoFrame.source = videoStream.frameUrl(did)
            }
        }

        Connections {
            target: typeof videoStream !== "undefined" ? videoStream : null
            function onFrameChanged(droneId, frameUrl) {
                var did = (typeof Cmp !== "undefined" && Cmp.AppState ? Cmp.AppState.selectedDroneId : "")
                          || videoStream.activeDroneId
                if (droneId === did && videoPipOverlay._videoStatus.activeTarget === "map")
                    mapVideoFrame.source = frameUrl
            }
        }

        Image {
            id: mapVideoFrame
            anchors.fill: parent
            anchors.margins: 2
            cache: false
            asynchronous: true
            fillMode: Image.PreserveAspectCrop
            source: ""
        }

        // Phase 1: status/info placeholder (Phase 2 replaces with VideoOutput)
        Column {
            visible: false
            anchors.centerIn: parent
            spacing: 4

            Text {
                text: "📡  LIVE"
                color: "#22c55e"; font.pixelSize: 13; font.weight: Font.Bold
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Text {
                text: {
                    if (typeof videoStream === "undefined" || !videoStream) return ""
                    var did = typeof Cmp !== "undefined" && Cmp.AppState ? Cmp.AppState.selectedDroneId : ""
                    var s = did ? videoStream.getVideoStatus(did) : null
                    return s && s.url ? s.url : ""
                }
                color: "#475569"; font.pixelSize: 8; font.family: "Consolas"
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }

        // Corner badge: "CAMERA"
        Rectangle {
            anchors { top: parent.top; left: parent.left; margins: 6 }
            width: camBadgeTxt.implicitWidth + 10; height: 18; radius: 4
            color: "#22c55e"
            Text { id: camBadgeTxt; anchors.centerIn: parent; text: "CAM"; color: "white"; font.pixelSize: 8; font.weight: Font.Bold }
        }

        // Minimize/close button
        Rectangle {
            anchors { top: parent.top; right: parent.right; margins: 4 }
            width: 18; height: 18; radius: 4; color: "#334155"
            Text { anchors.centerIn: parent; text: "✕"; color: "#94a3b8"; font.pixelSize: 9 }
            MouseArea {
                anchors.fill: parent
                onClicked: {
                    if (typeof videoStream !== "undefined" && videoStream) {
                        var did = ((typeof Cmp !== "undefined" && Cmp.AppState) ? Cmp.AppState.selectedDroneId : "")
                                  || videoStream.activeDroneId
                        if (did) videoStream.stopStream(did)
                    }
                }
            }
        }
    }

    // ── Sensor Overlay PIPs — bottom-left ─────────────────────────────────────
    // LiDAR (OBSTACLE_DISTANCE) and Optical Flow (OPTICAL_FLOW) overlays.
    // Both are independent toggles; they stack left-to-right above their buttons.
    property bool _lidarOverlayVisible: false
    property bool _flowOverlayVisible:  false

    // Wire sitl.sensorOverlayToggled so the SITL Gazebo panel can show/hide
    // these overlays (same as clicking the toggle buttons directly).
    Connections {
        target: typeof sitl !== "undefined" ? sitl : null
        function onSensorOverlayToggled(sensorType, visible) {
            if (sensorType === "lidar") root._lidarOverlayVisible = visible
            else if (sensorType === "flow") root._flowOverlayVisible = visible
        }
    }

    // ── Toggle buttons row (bottom-left) ──────────────────────────────────────
    Row {
        anchors { bottom: parent.bottom; left: parent.left; bottomMargin: 12; leftMargin: 12 }
        spacing: 6; z: 11

        // LiDAR toggle
        Rectangle {
            id: lidarToggleBtn
            width: lidarToggleTxt.implicitWidth + 18; height: 26; radius: 5
            // Lift up above its overlay when visible
            y: root._lidarOverlayVisible ? -(_lidarOverlay.height + 6) : 0
            color: root._lidarOverlayVisible ? "#1e3a5f" : "#0d1117cc"
            border.color: root._lidarOverlayVisible ? "#2563eb" : "#334155"; border.width: 1
            Behavior on color { ColorAnimation { duration: 120 } }
            Text {
                id: lidarToggleTxt
                anchors.centerIn: parent
                text: root._lidarOverlayVisible ? "◉ LiDAR" : "◎ LiDAR"
                color: root._lidarOverlayVisible ? "#93c5fd" : "#475569"
                font.pixelSize: 10; font.weight: Font.Bold
            }
            MouseArea { anchors.fill: parent; onClicked: root._lidarOverlayVisible = !root._lidarOverlayVisible }
        }

        // Flow toggle
        Rectangle {
            id: flowToggleBtn
            width: flowToggleTxt.implicitWidth + 18; height: 26; radius: 5
            y: root._flowOverlayVisible ? -(_flowOverlay.height + 6) : 0
            color: root._flowOverlayVisible ? "#3b0764" : "#0d1117cc"
            border.color: root._flowOverlayVisible ? "#7c3aed" : "#334155"; border.width: 1
            Behavior on color { ColorAnimation { duration: 120 } }
            Text {
                id: flowToggleTxt
                anchors.centerIn: parent
                text: root._flowOverlayVisible ? "◉ Flow" : "◎ Flow"
                color: root._flowOverlayVisible ? "#c4b5fd" : "#475569"
                font.pixelSize: 10; font.weight: Font.Bold
            }
            MouseArea { anchors.fill: parent; onClicked: root._flowOverlayVisible = !root._flowOverlayVisible }
        }
    }

    // ── LiDAR Overlay — OpenCV-Frame 1:1 als JPEG auf der Karte ──────────────
    Rectangle {
        id: _lidarOverlay
        anchors { bottom: parent.bottom; left: parent.left; bottomMargin: 44; leftMargin: 12 }
        width: 320; height: 320
        radius: 8; z: 10
        color: "#dd040710"
        border.color: "#1e3a5f"; border.width: 1
        clip: true
        visible: root._lidarOverlayVisible

        property string _b64: ""

        Connections {
            target: typeof sitl !== "undefined" ? sitl : null
            function onLidarFrameReady(b64) { _lidarOverlay._b64 = b64 }
        }

        // OpenCV-Frame direkt anzeigen
        Image {
            anchors { fill: parent; margins: 2 }
            source: _lidarOverlay._b64 !== "" ? "data:image/jpeg;base64," + _lidarOverlay._b64 : ""
            fillMode: Image.Stretch
            cache: false
            visible: _lidarOverlay._b64 !== ""
        }

        // Warte-Text solange noch kein Frame da
        Text {
            anchors.centerIn: parent
            text: "◎ LiDAR\n'Auf Karte zeigen' klicken"
            color: "#374151"; font.pixelSize: 9; font.family: "Consolas"
            horizontalAlignment: Text.AlignHCenter
            visible: _lidarOverlay._b64 === ""
        }

        // Header-Badge
        Rectangle {
            anchors { top: parent.top; left: parent.left; margins: 4 }
            width: lidarBadge.implicitWidth + 8; height: 16; radius: 3; color: "#1e3a5f"
            Text { id: lidarBadge; anchors.centerIn: parent; text: "◉ LiDAR"
                color: "#60a5fa"; font.pixelSize: 8; font.weight: Font.Bold }
        }

        // Close button
        Rectangle {
            anchors { top: parent.top; right: parent.right; margins: 4 }
            width: 16; height: 16; radius: 4; color: "#334155"
            Text { anchors.centerIn: parent; text: "✕"; color: "#94a3b8"; font.pixelSize: 8 }
            MouseArea { anchors.fill: parent; onClicked: root._lidarOverlayVisible = false }
        }
    }

    // ── Flow Overlay — OpenCV-Frame 1:1 als JPEG auf der Karte ───────────────
    Rectangle {
        id: _flowOverlay
        anchors { bottom: parent.bottom; left: _lidarOverlay.right; bottomMargin: 44; leftMargin: 6 }
        width: 320; height: 240
        radius: 8; z: 10
        color: "#dd04070e"
        border.color: "#3b0764"; border.width: 1
        clip: true
        visible: root._flowOverlayVisible

        property string _b64: ""

        Connections {
            target: typeof sitl !== "undefined" ? sitl : null
            function onFlowFrameReady(b64) { _flowOverlay._b64 = b64 }
        }

        // OpenCV-Frame direkt anzeigen
        Image {
            anchors { fill: parent; margins: 2 }
            source: _flowOverlay._b64 !== "" ? "data:image/jpeg;base64," + _flowOverlay._b64 : ""
            fillMode: Image.Stretch
            cache: false
            visible: _flowOverlay._b64 !== ""
        }

        // Warte-Text
        Text {
            anchors.centerIn: parent
            text: "◎ Optical Flow\n'Auf Karte zeigen' klicken"
            color: "#374151"; font.pixelSize: 9; font.family: "Consolas"
            horizontalAlignment: Text.AlignHCenter
            visible: _flowOverlay._b64 === ""
        }

        // Header-Badge
        Rectangle {
            anchors { top: parent.top; left: parent.left; margins: 4 }
            width: flowBadge.implicitWidth + 8; height: 16; radius: 3; color: "#3b0764"
            Text { id: flowBadge; anchors.centerIn: parent; text: "◉ Flow"
                color: "#c4b5fd"; font.pixelSize: 8; font.weight: Font.Bold }
        }

        // Close button
        Rectangle {
            anchors { top: parent.top; right: parent.right; margins: 4 }
            width: 16; height: 16; radius: 4; color: "#334155"
            Text { anchors.centerIn: parent; text: "✕"; color: "#94a3b8"; font.pixelSize: 8 }
            MouseArea { anchors.fill: parent; onClicked: root._flowOverlayVisible = false }
        }
    }

    // Pick mode cursor overlay
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        visible: root.pickMode
        border.color: "#f59e0b"; border.width: 2
        Rectangle {
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 32; color: "#ccf59e0b"
            Text {
                anchors.centerIn: parent
                text: "WAYPOINT MODE  —  Click on map to set waypoint  —  ESC to cancel"
                color: "white"; font.pixelSize: 12; font.weight: Font.Bold
            }
            MouseArea { anchors.fill: parent }
        }
        Keys.onEscapePressed: root.deliverMapPick(0, 0)
        focus: visible
    }

    // Boundary Drawing mode overlay (for Coverage/Seeding field boundary)
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        visible: root.boundaryDrawMode
        border.color: "#22c55e"; border.width: 2
        Rectangle {
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 32; color: "#cc22c55e"
            Text {
                anchors.centerIn: parent
                text: "FIELD BOUNDARY  —  Click to add points  —  ESC to finish"
                color: "white"; font.pixelSize: 12; font.weight: Font.Bold
            }
            MouseArea { anchors.fill: parent }
        }
        Keys.onEscapePressed: {
            if (typeof mission !== "undefined" && mission) {
                mission.finishDrawingBoundary()
            }
        }
        focus: visible
    }

    // Solar Row Drawing mode overlay
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        visible: root.solarRowDrawMode
        border.color: "#3b82f6"; border.width: 2
        Rectangle {
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 32; color: "#cc3b82f6"
            Text {
                anchors.centerIn: parent
                text: root.solarRowStart ? "SOLAR ROW  —  Click end point  —  ESC to cancel" : "SOLAR ROW  —  Click start point  —  ESC to cancel"
                color: "white"; font.pixelSize: 12; font.weight: Font.Bold
            }
            MouseArea { anchors.fill: parent }
        }
        MouseArea {
            anchors.fill: parent
            z: -1
            cursorShape: Qt.CrossCursor
            acceptedButtons: Qt.NoButton
            hoverEnabled: true
        }
        Keys.onEscapePressed: {
            if (typeof mission !== "undefined" && mission) {
                mission.cancelSolarRowDrawing()
            }
        }
        focus: visible
    }

    // ── ESCAPE Visualization ───────────────────────────────────────────────
    // B-M5: QML Repeater overlays removed — the old implementation used NED
    // coordinates (metres) as raw pixel offsets, which is geometrically wrong
    // and caused a hoverEnabled hit-test on every QML item for every mouse move.
    // TODO: render obstacles/voxels via Leaflet JS (updateEscapeObstacles /
    //       updateEscapeVoxels) with proper lat/lon projection once ESCAPE
    //       context exposes GPS-referenced positions.

    // Called from main.qml on telemetry
    // B-M3: single combined call to avoid double IPC round-trip
    function updateDronesAndSelect(jsonStr, did) {
        webView.runJavaScript("updateDronesAndSelect(" + jsonStr + ", " + JSON.stringify(did) + ")")
    }
    // Legacy individual calls kept for compatibility (header drone-select, etc.)
    function updateDrones(jsonStr)      { webView.runJavaScript("updateDrones(" + jsonStr + ")") }
    function updateWaypoints(jsonStr)   { webView.runJavaScript("updateWaypoints(" + jsonStr + ")") }
    // Snapshot the current pending waypoints into the "dispatched" layer so
    // they stay visible on the map (different colour) after the WP list is
    // cleared post-mission-start.
    function commitDispatchedWaypoints(jsonStr) { webView.runJavaScript("commitDispatchedWaypoints(" + jsonStr + ")") }
    function clearDispatchedWaypoints()         { webView.runJavaScript("clearDispatchedWaypoints()") }
    function updateGeofence(lat,lon,r)  { webView.runJavaScript("updateGeofence("+lat+","+lon+","+r+")") }
    function centerMap(lat, lon)        { webView.runJavaScript("map.setView(["+lat+","+lon+"], map.getZoom())") }
    function clearTracks()              { webView.runJavaScript("clearTracks()") }
    function flyTo(lat, lon)            { webView.runJavaScript("map.flyTo(["+lat+","+lon+"], 18);") }
    function setSelectedDrone(did)      { webView.runJavaScript("setSelectedDrone('" + did + "')") }

    // Swarm algorithm visualization functions
    function clearSwarmVisualization() {
        webView.runJavaScript("clearSwarmVisualization()")
    }

    function updateFormation(leaderId, positions) {
        webView.runJavaScript("updateFormation('"+leaderId+"', "+JSON.stringify(positions)+")")
    }

    function updateBoidsVisualization(activeDrones) {
        webView.runJavaScript("updateBoidsVisualization("+JSON.stringify(activeDrones)+")")
    }

    function updateConsensusVisualization(votingDrones) {
        webView.runJavaScript("updateConsensusVisualization("+JSON.stringify(votingDrones)+")")
    }

    function updateBehaviorTreeVisualization(missionType, activeDrones) {
        webView.runJavaScript("updateBehaviorTreeVisualization("+missionType+", "+JSON.stringify(activeDrones)+")")
    }

    signal mapPickSelected(real lat, real lon)
    signal waypointMoved(int index, real lat, real lon)
    signal boundaryPointSelected(real lat, real lon)
    signal boundaryPointMoved(int index, real lat, real lon)
    signal solarRowPointSelected(real lat, real lon)

    // Drone-color palette (mirrors Python DRONE_COLORS)
    readonly property var droneColors: [
        "#2563eb","#22c55e","#f59e0b","#8b5cf6","#ef4444",
        "#06b6d4","#f97316","#ec4899","#84cc16","#14b8a6"
    ]

    property string mapHtml: '
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
  html,body,#map { margin:0;padding:0;width:100%;height:100%;background:#0f1117; }
  /* Hide all map tooltips - drone names shown in QML overlay */
  .leaflet-tooltip { display:none !important; visibility:hidden !important; }
  .drone-label { display:none !important; visibility:hidden !important; }
</style>
</head>
<body>
<div id="map"></div>
<script>
if (typeof L !== "undefined") {
  console.log("[MapView] Leaflet OK");
} else {
  console.error("[MapView] Leaflet failed to load");
}

var map = L.map("map", {
  center: [48.137, 11.575],
  zoom: 15,
  zoomControl: true,
  attributionControl: false,
  preferCanvas: true
});
var seedingCanvasRenderer = L.canvas({padding: 0.4});

// Remove all drone tooltips on map load (name shown in QML overlay instead)
function removeAllDroneTooltips() {
  Object.keys(droneMarkers).forEach(function(id) {
    if (droneMarkers[id] && droneMarkers[id].getTooltip()) {
      droneMarkers[id].unbindTooltip();
    }
  });
}

var mapLayers = {
  dark: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 19,
    opacity: 0.85
  }),
  street: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 19,
    opacity: 0.95
  }),
  satellite: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    attribution: "© Esri",
    maxZoom: 19,
    opacity: 0.95
  }),
  hybrid: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    attribution: "© Esri",
    maxZoom: 19,
    opacity: 0.95
  }),
  topo: L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenTopoMap contributors",
    maxZoom: 17,
    opacity: 0.9
  }),
};
// Road overlay for hybrid mode
var roadOverlay = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  opacity: 0.35,
  className: "hybrid-roads"
});
var hybridActive = false;

var darkStyle = document.createElement("style");
darkStyle.id = "dark-filter";
darkStyle.innerHTML = ".leaflet-tile { filter: invert(1) hue-rotate(180deg) brightness(0.85) saturate(1.1); }";
document.head.appendChild(darkStyle);

var currentLayer = mapLayers.dark;
currentLayer.addTo(map);

function setMapType(type) {
  if (hybridActive) { try { map.removeLayer(roadOverlay); } catch(e){} hybridActive = false; }
  if (currentLayer) map.removeLayer(currentLayer);
  currentLayer = mapLayers[type] || mapLayers.dark;
  currentLayer.addTo(map);
  if (type === "hybrid") { roadOverlay.addTo(map); hybridActive = true; }
  var ds = document.getElementById("dark-filter");
  if (type === "dark") {
    ds.innerHTML = ".leaflet-tile { filter: invert(1) hue-rotate(180deg) brightness(0.85) saturate(1.1); }";
  } else if (type === "topo") {
    ds.innerHTML = ".leaflet-tile { filter: brightness(0.85) saturate(0.9); }";
  } else if (type === "satellite" || type === "hybrid") {
    ds.innerHTML = ".leaflet-tile { filter: brightness(1.05) saturate(1.1); }";
  } else {
    ds.innerHTML = ".leaflet-tile { filter: none; }";
  }
}

var droneMarkers = {}, droneTracks = {}, waypointMarkers = [], waypointLine = null, geofenceCircle = null;
// "Dispatched" waypoints — already sent to drones via Mission Start.
// Drawn in a different colour and kept on the map until the user manually
// clears them (so the user can visually follow what has been flown).
var dispatchedMarkers = [], dispatchedLine = null;
var droneTypes = {};  // id -> droneType
var selectedDroneId = "";

// Swarm algorithm visualization
var formationLines = [], leaderMarker = null, formationCircles = [];

function droneColor(id) {
  return droneTypes[id] === "observation" ? "#8b5cf6" : "#2563eb";
}

function droneIconKey(id, d, selected) {
  var headingBucket = Math.round(Number(d.heading || 0) / 5) * 5;
  return [
    headingBucket,
    d.armed ? "armed" : "safe",
    selected ? "selected" : "normal",
    droneTypes[id] || "generic"
  ].join("|");
}

function setDroneIconIfChanged(id, marker, d, selected, force) {
  var key = droneIconKey(id, d, selected);
  if (force || marker._iconKey !== key) {
    marker.setIcon(makeDroneIcon(id, d, selected));
    marker._iconKey = key;
  }
  marker.setZIndexOffset(selected ? 1000 : 0);
}

function setSelectedDrone(did) {
  selectedDroneId = did;
  // Remove all tooltips first
  removeAllDroneTooltips();
  // Update icons
  Object.keys(droneMarkers).forEach(function(id) {
    var m = droneMarkers[id];
    if (m && m._lastData) {
      setDroneIconIfChanged(id, m, m._lastData, id === did, false);
    }
  });
}

function makeDroneIcon(id, d, selected) {
  var col = droneColor(id);
  var hdg = d.heading || 0;
  var armed = d.armed || false;
  var sz = selected ? 52 : 42;
  var cx = sz / 2;
  var armR = cx * 0.75;
  var rotR = cx * 0.18;
  var bodyR = cx * 0.26;
  // Glow ring (selected)
  var glow = selected
    ? \'<circle cx="\'+cx+\'" cy="\'+cx+\'" r="\'+(cx-1)+\'" fill="none" stroke="#f59e0b" stroke-width="2.5" opacity="0.95"/>\' : \'\';
  // Armed pulse ring
  var ring = armed
    ? \'<circle cx="\'+cx+\'" cy="\'+cx+\'" r="\'+(cx*0.52)+\'" fill="none" stroke="\'+col+\'" stroke-width="1.2" opacity="0.45" stroke-dasharray="3 3"/>\' : \'\';
  // 4 arms (X-config, 45/135/225/315 deg)
  var arms = \'\';
  var aAngles = [45,135,225,315];
  for (var i=0;i<4;i++) {
    var rad = (aAngles[i]-90)*Math.PI/180;
    var bx = cx + bodyR*Math.cos(rad), by = cx + bodyR*Math.sin(rad);
    var tx = cx + armR*Math.cos(rad), ty = cx + armR*Math.sin(rad);
    arms += \'<line x1="\'+bx+\'" y1="\'+by+\'" x2="\'+tx+\'" y2="\'+ty+\'" stroke="\'+col+\'" stroke-width="\'+(sz*0.075)+\'" stroke-linecap="round"/>\';
    arms += \'<circle cx="\'+tx+\'" cy="\'+ty+\'" r="\'+rotR+\'" fill="\'+col+\'" opacity="0.28"/>\';
    arms += \'<circle cx="\'+tx+\'" cy="\'+ty+\'" r="\'+rotR+\'" fill="none" stroke="\'+col+\'" stroke-width="1.2" opacity="0.8"/>\';
  }
  // Body
  var body = \'<circle cx="\'+cx+\'" cy="\'+cx+\'" r="\'+bodyR+\'" fill="\'+col+\'" opacity="0.95"/>\';
  body += \'<circle cx="\'+cx+\'" cy="\'+cx+\'" r="\'+(bodyR*0.48)+\'" fill="#0f1117"/>\';
  // Heading arrow (points forward, rotated by heading)
  var arrowTip = cx - armR*0.82;
  var arrowW   = sz*0.065;
  var arrow = \'<g transform="rotate(\'+hdg+\',\'+cx+\',\'+cx+\')">\';
  arrow += \'<line x1="\'+cx+\'" y1="\'+cx+\'" x2="\'+cx+\'" y2="\'+arrowTip+\'" stroke="white" stroke-width="\'+(sz*0.055)+\'" stroke-linecap="round" opacity="0.9"/>\';
  arrow += \'<polygon points="\'+cx+\',\'+(arrowTip-1)+\' \'+(cx-arrowW)+\',\'+(arrowTip+sz*0.11)+\' \'+(cx+arrowW)+\',\'+(arrowTip+sz*0.11)+\'" fill="white" opacity="0.9"/>\';
  arrow += \'</g>\';
  var svg = \'<svg xmlns="http://www.w3.org/2000/svg" width="\'+sz+\'" height="\'+sz+\'" viewBox="0 0 \'+sz+\' \'+sz+\'">\' + glow + ring + arms + body + arrow + \'</svg>\';
  return L.divIcon({ className:"", html:svg, iconSize:[sz,sz], iconAnchor:[cx,cx] });
}

// B-M1: max track points kept per drone — older points are trimmed
var TRACK_MAX_PTS = 300;
// B-M8: min position delta (degrees) to trigger a marker/track update
var DRONE_MOVE_THRESHOLD = 0.000001;

function updateDrones(data) {
  var ids = Object.keys(data);
  ids.forEach(function(id) {
    var d = data[id];
    if (d.lat === null || d.lat === undefined || d.lon === null || d.lon === undefined) return;
    var prevType = droneTypes[id];
    droneTypes[id] = d.droneType || "generic";
    var col = droneColor(id);
    var sel = (id === selectedDroneId);

    if (!droneMarkers[id]) {
      // First time — create marker and track
      var icon = makeDroneIcon(id, d, sel);
      droneMarkers[id] = L.marker([d.lat,d.lon],{icon:icon,zIndexOffset:sel?1000:0}).addTo(map);
      droneMarkers[id]._iconKey = droneIconKey(id, d, sel);
      droneMarkers[id]._lastData = d;
      droneTracks[id] = L.polyline([[d.lat,d.lon]],{color:col,weight:2,opacity:0.55}).addTo(map);
    } else {
      var prev = droneMarkers[id]._lastData || {};
      // B-M8: skip update if position has not changed meaningfully
      var moved = Math.abs((d.lat - (prev.lat||0))) + Math.abs((d.lon - (prev.lon||0))) > DRONE_MOVE_THRESHOLD;
      var headingChanged = Math.abs(Math.round(d.heading||0) - Math.round(prev.heading||0)) >= 1;
      var armedChanged = (d.armed !== prev.armed);
      var typeChanged = (prevType !== droneTypes[id]);

      if (moved) {
        droneMarkers[id].setLatLng([d.lat,d.lon]);
      }
      if (headingChanged || armedChanged || typeChanged) {
        setDroneIconIfChanged(id, droneMarkers[id], d, sel, false);
      }
      if (typeChanged && droneTracks[id]) droneTracks[id].setStyle({color:col});
      if (moved || headingChanged || armedChanged || typeChanged) {
        droneMarkers[id]._lastData = d;
      }

      // B-M1: add track point only when drone actually moved
      if (moved) {
        droneTracks[id].addLatLng([d.lat,d.lon]);
        // Trim oldest points when track exceeds cap
        var pts = droneTracks[id].getLatLngs();
        if (pts.length > TRACK_MAX_PTS) {
          droneTracks[id].setLatLngs(pts.slice(pts.length - TRACK_MAX_PTS));
        }
      }
    }
    // ALWAYS remove tooltip after marker update
    if (droneMarkers[id] && droneMarkers[id].getTooltip()) droneMarkers[id].unbindTooltip();
  });
  // Remove stale markers
  Object.keys(droneMarkers).forEach(function(id) {
    if (!data[id]) {
      map.removeLayer(droneMarkers[id]);
      map.removeLayer(droneTracks[id]);
      delete droneMarkers[id]; delete droneTracks[id];
      delete droneTypes[id];
    }
  });
}

// B-M3: single combined entry point used by main.qml telemetry bridge
function updateDronesAndSelect(data, did) {
  updateDrones(data);
  // Only re-render selection ring when the selected drone actually changed —
  // calling setSelectedDrone on every telemetry tick forces setIcon() on all
  // markers which causes the brief DOM-removal flicker (visual blink).
  if (did !== selectedDroneId) {
    setSelectedDrone(did);
  }
}

function waypointIcon(index) {
  return L.divIcon({ className:"", iconSize:[22,22], iconAnchor:[11,11],
    html:\'<div style="width:22px;height:22px;border-radius:50%;border:2px solid #f59e0b;background:#78350f;display:flex;align-items:center;justify-content:center;color:#fcd34d;font-size:9px;font-weight:bold;">\' + (index+1) + \'</div>\'});
}

function waypointTooltip(wp, index) {
  return "WP" + (index+1) + ": " + wp.alt + "m";
}

function updateWaypointLineFromMarkers() {
  if (waypointMarkers.length < 2) {
    if (waypointLine) { map.removeLayer(waypointLine); waypointLine = null; }
    return;
  }
  var latlngs = waypointMarkers.map(function(m) { return m.getLatLng(); });
  if (waypointLine) {
    waypointLine.setLatLngs(latlngs);
  } else {
    waypointLine = L.polyline(latlngs, {
      color: "#f59e0b",
      weight: 2,
      opacity: 0.7,
      dashArray: "8,4"
    }).addTo(map);
  }
}

function createWaypointMarker(wp, i) {
  var marker = L.marker([wp.lat,wp.lon], {
    icon: waypointIcon(i),
    draggable: true,
    autoPan: true
  }).bindTooltip(waypointTooltip(wp, i), {direction:"top"}).addTo(map);

  marker._wpIndex = i;
  marker._wpAlt = wp.alt;
  marker._wpTooltip = waypointTooltip(wp, i);

  marker.on("dragstart", function(e) {
    e.target.setOpacity(0.6);
    if (waypointLine) waypointLine.setStyle({opacity: 0.3});
  });

  marker.on("drag", function() {
    updateWaypointLineFromMarkers();
  });

  marker.on("dragend", function(e) {
    e.target.setOpacity(1.0);
    if (waypointLine) waypointLine.setStyle({opacity: 0.7});

    var newPos = e.target.getLatLng();
    var idx = -1;
    for (var j = 0; j < waypointMarkers.length; j++) {
      if (waypointMarkers[j] === e.target) {
        idx = j;
        break;
      }
    }

    if (idx >= 0) {
      e.target._wpLat = newPos.lat;
      e.target._wpLon = newPos.lng;
      window.location = "qrc://waypoint-moved?index=" + idx + "&lat=" + newPos.lat + "&lon=" + newPos.lng;
    }
  });

  marker._wpLat = wp.lat;
  marker._wpLon = wp.lon;
  return marker;
}

function updateWaypointMarker(marker, wp, i) {
  if (marker._wpIndex !== i) {
    marker.setIcon(waypointIcon(i));
    marker._wpIndex = i;
  }
  if (Math.abs((marker._wpLat || 0) - wp.lat) + Math.abs((marker._wpLon || 0) - wp.lon) > 0.0000001) {
    marker.setLatLng([wp.lat, wp.lon]);
    marker._wpLat = wp.lat;
    marker._wpLon = wp.lon;
  }
  var tooltip = waypointTooltip(wp, i);
  if (marker._wpTooltip !== tooltip) {
    marker.setTooltipContent(tooltip);
    marker._wpTooltip = tooltip;
  }
  marker._wpAlt = wp.alt;
}

function updateWaypoints(wps) {
  if (!wps || wps.length === 0) {
    waypointMarkers.forEach(function(m){ map.removeLayer(m); });
    waypointMarkers = [];
    if (waypointLine) { map.removeLayer(waypointLine); waypointLine = null; }
    return;
  }

  while (waypointMarkers.length > wps.length) {
    map.removeLayer(waypointMarkers.pop());
  }

  wps.forEach(function(wp, i) {
    if (!waypointMarkers[i]) {
      waypointMarkers[i] = createWaypointMarker(wp, i);
    } else {
      updateWaypointMarker(waypointMarkers[i], wp, i);
    }
  });

  updateWaypointLineFromMarkers();
}

function commitDispatchedWaypoints(wps) {
  if (!wps || wps.length === 0) return;
  var idxOffset = dispatchedMarkers.length;
  var latlngs = [];
  // Preserve any previous polyline endpoints so successive dispatches connect
  if (dispatchedLine) {
    dispatchedLine.getLatLngs().forEach(function(p){ latlngs.push(p); });
  }
  wps.forEach(function(wp, i) {
    var n = idxOffset + i + 1;
    var icon = L.divIcon({ className:"", iconSize:[22,22], iconAnchor:[11,11],
      html:\'<div style="width:22px;height:22px;border-radius:50%;border:2px solid #22c55e;background:#14532d;display:flex;align-items:center;justify-content:center;color:#bbf7d0;font-size:9px;font-weight:bold;">\' + n + \'</div>\'});
    dispatchedMarkers.push(
      L.marker([wp.lat, wp.lon], { icon: icon })
        .bindTooltip("Mission WP " + n + ": " + wp.alt + "m", { direction: "top" })
        .addTo(map)
    );
    latlngs.push([wp.lat, wp.lon]);
  });
  if (dispatchedLine) map.removeLayer(dispatchedLine);
  dispatchedLine = L.polyline(latlngs, {
    color: "#22c55e", weight: 2, opacity: 0.6, dashArray: "6,4"
  }).addTo(map);
}

function clearDispatchedWaypoints() {
  dispatchedMarkers.forEach(function(m){ map.removeLayer(m); });
  dispatchedMarkers = [];
  if (dispatchedLine) { map.removeLayer(dispatchedLine); dispatchedLine = null; }
}

function updateGeofence(lat, lon, r) {
  if (geofenceCircle) map.removeLayer(geofenceCircle);
  geofenceCircle = L.circle([lat,lon],{radius:r,color:"#ef4444",fillColor:"#ef4444",fillOpacity:0.04,weight:2,dashArray:"6 4"}).addTo(map);
}

function clearTracks() {
  Object.values(droneTracks).forEach(function(t){ t.setLatLngs([]); });
}

var _pickMode = false;
function setPickMode(enabled) {
  _pickMode = enabled;
  map.getContainer().style.cursor = enabled ? "crosshair" : "";
}

// ── Field Coverage Planning ──────────────────────────────────────────────────
var _boundaryDrawMode = false;
var boundaryMarkers = [], boundaryLine = null, exclusionZoneLayers = [];

var _solarRowDrawMode = false;
var _solarRowStart = null;
var solarRowTempLine = null;

function setSolarRowDrawMode(enabled) {
  _solarRowDrawMode = enabled;
  _solarRowStart = null;
  if (solarRowTempLine) {
    map.removeLayer(solarRowTempLine);
    solarRowTempLine = null;
  }
}
var coverageWaypointMarkers = [], coverageWaypointLine = null;

function setBoundaryDrawMode(enabled) {
  _boundaryDrawMode = enabled;
  map.getContainer().style.cursor = enabled ? "crosshair" : "";
}

function updateFieldBoundary(points) {
  // Clear existing boundary always — even when points is empty
  boundaryMarkers.forEach(function(m){ map.removeLayer(m); });
  boundaryMarkers = [];
  if (boundaryLine) { map.removeLayer(boundaryLine); boundaryLine = null; }
  
  if (!points || points.length === 0) return;
  
  var latlngs = [];
  points.forEach(function(pt, i) {
    var icon = L.divIcon({
      className:"",
      iconSize:[18,18],
      iconAnchor:[9,9],
      html:\'<div style="width:18px;height:18px;border-radius:50%;border:2px solid #22c55e;background:#14532d;display:flex;align-items:center;justify-content:center;color:#bbf7d0;font-size:8px;font-weight:bold;">\' + (i+1) + \'</div>\'
    });
    
    var marker = L.marker([pt.lat, pt.lon], {icon: icon})
      .bindTooltip("Boundary Point " + (i+1), {direction:"top"})
      .addTo(map);
    
    boundaryMarkers.push(marker);
    latlngs.push([pt.lat, pt.lon]);
  });
  
  // Close the polygon
  if (latlngs.length >= 3) {
    latlngs.push(latlngs[0]);
    boundaryLine = L.polyline(latlngs, {
      color: "#22c55e",
      weight: 2,
      opacity: 0.7,
      dashArray: "5, 5"
    }).addTo(map);
  }
}

function updateExclusionZones(zones) {
  // Always clear existing zones first — even when zones is empty
  exclusionZoneLayers.forEach(function(layer){ map.removeLayer(layer); });
  exclusionZoneLayers = [];

  if (!zones || zones.length === 0) return;

  zones.forEach(function(zone, zoneIndex) {
    if (!zone || zone.length === 0) return;

    var latlngs = [];
    zone.forEach(function(pt) {
      if (pt && typeof pt.lat === "number" && typeof pt.lon === "number") {
        latlngs.push([pt.lat, pt.lon]);
      }
    });
    if (latlngs.length === 0) return;

    var layer = null;
    if (latlngs.length >= 3 && typeof L.polygon === "function") {
      layer = L.polygon(latlngs, {
        color: "#ef4444",
        weight: 2,
        opacity: 0.9,
        fillColor: "#7f1d1d",
        fillOpacity: 0.22,
        dashArray: "6, 4"
      });
    } else {
      layer = L.polyline(latlngs, {
        color: "#ef4444",
        weight: 2,
        opacity: 0.9,
        dashArray: "6, 4"
      });
    }
    layer.bindTooltip("Exclusion Zone " + (zoneIndex + 1), {direction:"top"});
    layer.addTo(map);
    exclusionZoneLayers.push(layer);

    latlngs.forEach(function(pos, pointIndex) {
      var icon = L.divIcon({
        className:"",
        iconSize:[16,16],
        iconAnchor:[8,8],
        html:\'<div style="width:16px;height:16px;border-radius:50%;border:2px solid #fca5a5;background:#7f1d1d;display:flex;align-items:center;justify-content:center;color:#fee2e2;font-size:7px;font-weight:bold;">\' + (pointIndex+1) + \'</div>\'
      });
      var marker = L.marker(pos, {icon: icon})
        .bindTooltip("Exclusion Point " + (pointIndex+1), {direction:"top"})
        .addTo(map);
      exclusionZoneLayers.push(marker);
    });
  });
}

function updateCoverageWaypoints(waypoints) {
  // Clear existing coverage waypoints
  coverageWaypointMarkers.forEach(function(m){ map.removeLayer(m); });
  coverageWaypointMarkers = [];
  if (coverageWaypointLine) { map.removeLayer(coverageWaypointLine); coverageWaypointLine = null; }
  
  if (!waypoints || waypoints.length === 0) return;
  
  var latlngs = [];
  waypoints.forEach(function(wp, i) {
    // Different styling for seed drop points
    var isSeedPoint = wp.isSeedPoint === true;
    var seedSvg = \'<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1C6 1 4 3 4 5C4 6.1 4.9 7 6 7C7.1 7 8 6.1 8 5C8 3 6 1 6 1Z" fill="#86efac"/><path d="M6 7V11" stroke="#86efac" stroke-width="1.5" stroke-linecap="round"/><path d="M4 9C4 9 5 8.5 6 8.5C7 8.5 8 9 8 9" stroke="#86efac" stroke-width="1" stroke-linecap="round"/></svg>\';
    var iconHtml = isSeedPoint
      ? \'<div style="width:20px;height:20px;border-radius:50%;border:2px solid #22c55e;background:#14532d;display:flex;align-items:center;justify-content:center;">\' + seedSvg + \'</div>\'
      : \'<div style="width:16px;height:16px;border-radius:50%;border:2px solid #3b82f6;background:#1e3a8a;display:flex;align-items:center;justify-content:center;color:#93c5fd;font-size:7px;font-weight:bold;">\' + (i+1) + \'</div>\';
    
    var icon = L.divIcon({
      className:"",
      iconSize: isSeedPoint ? [20,20] : [16,16],
      iconAnchor: isSeedPoint ? [10,10] : [8,8],
      html: iconHtml
    });
    
    var tooltipText = isSeedPoint
      ? "Seed Drop #" + (i+1) + ": " + wp.alt + "m"
      : "Coverage WP" + (i+1) + ": " + wp.alt + "m";
    
    var marker = L.marker([wp.lat, wp.lon], {icon: icon})
      .bindTooltip(tooltipText, {direction:"top"})
      .addTo(map);
    
    coverageWaypointMarkers.push(marker);
    latlngs.push([wp.lat, wp.lon]);
  });
  
  // Draw coverage path
  if (latlngs.length > 1) {
    coverageWaypointLine = L.polyline(latlngs, {
      color: "#3b82f6",
      weight: 2,
      opacity: 0.6,
      dashArray: "4, 4"
    }).addTo(map);
  }
}

function clearFieldCoverage() {
  boundaryMarkers.forEach(function(m){ map.removeLayer(m); });
  boundaryMarkers = [];
  if (boundaryLine) { map.removeLayer(boundaryLine); boundaryLine = null; }
  exclusionZoneLayers.forEach(function(layer){ map.removeLayer(layer); });
  exclusionZoneLayers = [];
  
  coverageWaypointMarkers.forEach(function(m){ map.removeLayer(m); });
  coverageWaypointMarkers = [];
  if (coverageWaypointLine) { map.removeLayer(coverageWaypointLine); coverageWaypointLine = null; }
}

map.on("click", function(e) {
  if (_pickMode) {
    window.location = "qrc://pick?lat=" + e.latlng.lat + "&lon=" + e.latlng.lng;
  } else if (_boundaryDrawMode) {
    window.location = "qrc://boundary-point?lat=" + e.latlng.lat + "&lon=" + e.latlng.lng;
  } else if (_solarRowDrawMode) {
    // Always send the click to backend - it will handle start/end logic
    window.location = "qrc://solar-row-point?lat=" + e.latlng.lat + "&lon=" + e.latlng.lng;
  }
});

// Swarm algorithm visualization functions
function clearSwarmVisualization() {
  formationLines.forEach(function(line) { map.removeLayer(line); });
  formationLines = [];
  formationCircles.forEach(function(circle) { map.removeLayer(circle); });
  formationCircles = [];
  if (leaderMarker) { map.removeLayer(leaderMarker); leaderMarker = null; }
}

function _validLatLng(p) {
  // Accepts [lat, lon, ...] arrays AND {0:lat,1:lon,...} pseudo-arrays.
  if (p === null || p === undefined) return null;
  var lat = (p[0] !== undefined) ? p[0] : p.lat;
  var lon = (p[1] !== undefined) ? p[1] : p.lon;
  if (typeof lat !== "number" || typeof lon !== "number") return null;
  if (isNaN(lat) || isNaN(lon)) return null;
  if (lat === 0 && lon === 0) return null;
  return [lat, lon];
}

var AIRBORNE_THRESHOLD = 1.5; // metres — below this, formation lines are suppressed

function updateFormation(leaderId, positions) {
  clearSwarmVisualization();

  if (!leaderId || !positions || positions.length === 0) return;

  // Find leader drone position — only draw if leader is airborne
  var leaderPos = null;
  if (droneMarkers[leaderId] && droneMarkers[leaderId]._lastData) {
    var ld = droneMarkers[leaderId]._lastData;
    if ((ld.alt || 0) < AIRBORNE_THRESHOLD) return;
    leaderPos = _validLatLng([ld.lat, ld.lon]);
  }

  if (!leaderPos) return;

  // Draw formation lines from leader to followers
  positions.forEach(function(pos, index) {
    if (index === 0) return; // Skip leader position

    var followerPos = _validLatLng(pos);
    if (!followerPos) return;

    // Suppress line if follower is not airborne
    if ((pos.alt || 0) < AIRBORNE_THRESHOLD) return;

    // Draw line from leader to follower
    var line = L.polyline([leaderPos, followerPos], {
      color: "#f97316",
      weight: 2,
      opacity: 0.7,
      dashArray: "5, 5"
    }).addTo(map);
    formationLines.push(line);

    // Draw circle at follower position
    var circle = L.circle(followerPos, {
      radius: 15,
      color: "#f97316",
      fillColor: "#f97316",
      fillOpacity: 0.3,
      weight: 2
    }).addTo(map);
    formationCircles.push(circle);
  });

  // Highlight leader with special marker
  if (droneMarkers[leaderId]) {
    var leaderIcon = L.divIcon({
      className: "",
      iconSize: [30, 30],
      iconAnchor: [15, 15],
      html: \'<div style="width:30px;height:30px;border-radius:50%;border:3px solid #f97316;background:#f97316;display:flex;align-items:center;justify-content:center;color:white;font-size:12px;font-weight:bold;">👑</div>\'
    });
    leaderMarker = L.marker(leaderPos, { icon: leaderIcon, zIndexOffset: 2000 }).addTo(map);
  }
}

function updateBoidsVisualization(activeDrones) {
  clearSwarmVisualization();

  if (!activeDrones || activeDrones.length === 0) return;

  // Draw perception radius circles for active boids
  activeDrones.forEach(function(droneId) {
    if (droneMarkers[droneId] && droneMarkers[droneId]._lastData) {
      var d = droneMarkers[droneId]._lastData;
      var pos = [d.lat, d.lon];

      // Draw perception radius circle (50m default)
      var circle = L.circle(pos, {
        radius: 50,
        color: "#22c55e",
        fillColor: "#22c55e",
        fillOpacity: 0.1,
        weight: 1,
        dashArray: "3, 3"
      }).addTo(map);
      formationCircles.push(circle);
    }
  });
}

function updateConsensusVisualization(votingDrones) {
  clearSwarmVisualization();

  if (!votingDrones || votingDrones.length === 0) return;

  // Visualize voting drones with special indicators
  votingDrones.forEach(function(droneId) {
    if (droneMarkers[droneId] && droneMarkers[droneId]._lastData) {
      var d = droneMarkers[droneId]._lastData;
      var pos = [d.lat, d.lon];

      // Draw voting indicator
      var circle = L.circle(pos, {
        radius: 25,
        color: "#3b82f6",
        fillColor: "#3b82f6",
        fillOpacity: 0.2,
        weight: 2
      }).addTo(map);
      formationCircles.push(circle);
    }
  });
}

function updateBehaviorTreeVisualization(missionType, activeDrones) {
  clearSwarmVisualization();

  if (!activeDrones || activeDrones.length === 0) return;

  // Different visualization based on mission type
  var colors = {
    0: "#ef4444", // Surveillance - red
    1: "#f59e0b", // Search & Rescue - amber
    2: "#8b5cf6", // Formation Flight - purple
    3: "#06b6d4"  // Area Coverage - cyan
  };

  var color = colors[missionType] || "#64748b";

  activeDrones.forEach(function(droneId) {
    if (droneMarkers[droneId] && droneMarkers[droneId]._lastData) {
      var d = droneMarkers[droneId]._lastData;
      var pos = [d.lat, d.lon];

      // Draw mission area indicator
      var circle = L.circle(pos, {
        radius: 35,
        color: color,
        fillColor: color,
        fillOpacity: 0.15,
        weight: 2
      }).addTo(map);
      formationCircles.push(circle);
    }
  });
}

// ── Collision Prediction Visualization ──────────────────────────────────────
var collisionLines = [], collisionMarkers = [], collisionZones = [];

function clearCollisionVisualization() {
  collisionLines.forEach(function(line) { map.removeLayer(line); });
  collisionLines = [];
  collisionMarkers.forEach(function(marker) { map.removeLayer(marker); });
  collisionMarkers = [];
  collisionZones.forEach(function(zone) { map.removeLayer(zone); });
  collisionZones = [];
}

function updateCollisionPredictions(predictions) {
  clearCollisionVisualization();
  
  if (!predictions || predictions.length === 0) return;
  
  predictions.forEach(function(pred) {
    // Get drone positions
    var droneA = droneMarkers[pred.droneA];
    var droneB = droneMarkers[pred.droneB];
    
    if (!droneA || !droneB || !droneA._lastData || !droneB._lastData) return;
    
    var posA = [droneA._lastData.lat, droneA._lastData.lon];
    var posB = [droneB._lastData.lat, droneB._lastData.lon];
    
    // Determine color based on severity
    var colors = {
      "critical": "#ef4444",  // red
      "warning": "#f59e0b",   // amber
      "caution": "#eab308"    // yellow
    };
    var color = colors[pred.severity] || "#64748b";
    
    // Draw warning line between drones
    var line = L.polyline([posA, posB], {
      color: color,
      weight: 3,
      opacity: 0.8,
      dashArray: "10, 5"
    }).addTo(map);
    collisionLines.push(line);
    
    // Add tooltip to line
    var tooltipText = pred.droneA + " ↔ " + pred.droneB +
                     "<br>Collision in " + pred.timeToCollision + "s" +
                     "<br>Min distance: " + pred.minDistance + "m" +
                     "<br>Severity: " + pred.severity.toUpperCase();
    line.bindTooltip(tooltipText, {permanent: false, sticky: true});
    
    // Convert collision point from local NED to lat/lon
    // This requires the reference point from SafetyContext
    // For now, we will mark the midpoint between drones
    var midLat = (droneA._lastData.lat + droneB._lastData.lat) / 2;
    var midLon = (droneA._lastData.lon + droneB._lastData.lon) / 2;
    
    // Draw collision zone circle
    var radius = pred.minDistance * 2; // meters
    var zone = L.circle([midLat, midLon], {
      radius: radius,
      color: color,
      fillColor: color,
      fillOpacity: 0.15,
      weight: 2,
      dashArray: "5, 5"
    }).addTo(map);
    collisionZones.push(zone);
    
    // Draw collision point marker
    var icon = L.divIcon({
      className: "",
      iconSize: [32, 32],
      iconAnchor: [16, 16],
      html: \'<div style="width:32px;height:32px;border-radius:50%;border:3px solid \' + color + \';background:rgba(239,68,68,0.2);display:flex;align-items:center;justify-content:center;font-size:18px;">⚠</div>\'
    });
    
    var marker = L.marker([midLat, midLon], {
      icon: icon,
      zIndexOffset: 1500
    }).addTo(map);
    
    marker.bindTooltip(tooltipText, {permanent: false, direction: "top"});
    collisionMarkers.push(marker);
    
    // Pulse animation for critical collisions
    if (pred.severity === "critical") {
      var pulseCircle = L.circle([midLat, midLon], {
        radius: radius * 1.5,
        color: color,
        fillColor: "none",
        weight: 2,
        opacity: 0.6,
        dashArray: "3, 3"
      }).addTo(map);
      collisionZones.push(pulseCircle);
    }
  });
}

// ── Solar Inspection Visualization ──────────────────────────────────────
var solarPanelLines = [], thermalHotspotMarkers = [];

function clearSolarInspection() {
  solarPanelLines.forEach(function(line) { map.removeLayer(line); });
  solarPanelLines = [];
  thermalHotspotMarkers.forEach(function(marker) { map.removeLayer(marker); });
  thermalHotspotMarkers = [];
}

function updateSolarPanelRows(rows) {
  // Clear existing solar panel visualization
  solarPanelLines.forEach(function(line) { map.removeLayer(line); });
  solarPanelLines = [];
  
  if (!rows || rows.length === 0) return;
  
  rows.forEach(function(row, index) {
    if (!row.start || !row.end) return;
    
    var startPos = [row.start.lat, row.start.lon];
    var endPos = [row.end.lat, row.end.lon];
    
    // Draw solar panel row as thick blue line
    var line = L.polyline([startPos, endPos], {
      color: "#3b82f6",
      weight: 4,
      opacity: 0.8
    }).addTo(map);
    
    // Add tooltip showing row info
    var tooltipText = "Solar Row " + (index + 1) +
                     "<br>Length: " + (row.length || 0).toFixed(1) + "m" +
                     "<br>Panels: " + (row.panelCount || 0);
    line.bindTooltip(tooltipText, {permanent: false, sticky: true});
    
    solarPanelLines.push(line);
    
    // Add start/end markers
    var startIcon = L.divIcon({
      className: "",
      iconSize: [16, 16],
      iconAnchor: [8, 8],
      html: \'<div style="width:16px;height:16px;border-radius:50%;border:2px solid #3b82f6;background:#1e40af;"></div>\'
    });
    
    var startMarker = L.marker(startPos, {
      icon: startIcon,
      zIndexOffset: 100
    }).addTo(map);
    solarPanelLines.push(startMarker);
    
    var endIcon = L.divIcon({
      className: "",
      iconSize: [16, 16],
      iconAnchor: [8, 8],
      html: \'<div style="width:16px;height:16px;border-radius:50%;border:2px solid #3b82f6;background:#3b82f6;"></div>\'
    });
    
    var endMarker = L.marker(endPos, {
      icon: endIcon,
      zIndexOffset: 100
    }).addTo(map);
    solarPanelLines.push(endMarker);
  });
}

function updateThermalHotspots(hotspots) {
  // Clear existing thermal hotspot markers
  thermalHotspotMarkers.forEach(function(marker) { map.removeLayer(marker); });
  thermalHotspotMarkers = [];
  
  if (!hotspots || hotspots.length === 0) return;
  
  hotspots.forEach(function(hotspot, index) {
    if (!hotspot.lat || !hotspot.lon) return;
    
    var pos = [hotspot.lat, hotspot.lon];
    
    // Determine color based on temperature severity
    var temp = hotspot.temperature || 0;
    var color = "#ef4444"; // red for hot
    var severity = "HOT";
    
    if (temp < 50) {
      color = "#f59e0b"; // amber for warm
      severity = "WARM";
    } else if (temp < 40) {
      color = "#eab308"; // yellow for mild
      severity = "MILD";
    }
    
    // Draw thermal hotspot as pulsing circle
    var circle = L.circle(pos, {
      radius: hotspot.radius || 2,
      color: color,
      fillColor: color,
      fillOpacity: 0.4,
      weight: 2
    }).addTo(map);
    thermalHotspotMarkers.push(circle);
    
    // Add hotspot marker icon
    var icon = L.divIcon({
      className: "",
      iconSize: [24, 24],
      iconAnchor: [12, 12],
      html: \'<svg width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="\' + color + \'" opacity="0.6"/><circle cx="12" cy="12" r="4" fill="\' + color + \'" opacity="0.9"/></svg>\'
    });
    
    var marker = L.marker(pos, {
      icon: icon,
      zIndexOffset: 1000
    }).addTo(map);
    
    // Add tooltip with hotspot details
    var tooltipText = "Thermal Hotspot #" + (index + 1) +
                     "<br>Temperature: " + temp.toFixed(1) + "°C" +
                     "<br>Severity: " + severity +
                     "<br>Panel: " + (hotspot.panelId || "Unknown");
    marker.bindTooltip(tooltipText, {permanent: false, direction: "top"});
    
    thermalHotspotMarkers.push(marker);
  });
}

// ── Seeding Mission Visualization ──────────────────────────────────────
var seedingDropMarkers = [], seedingFlightLines = [], seedingExclusionPolygons = [];
var seedingDropPointCount = 0;

function clearSeedingMission() {
  seedingDropMarkers.forEach(function(marker) { map.removeLayer(marker); });
  seedingDropMarkers = [];
  seedingDropPointCount = 0;
  seedingFlightLines.forEach(function(line) { map.removeLayer(line); });
  seedingFlightLines = [];
  seedingExclusionPolygons.forEach(function(poly) { map.removeLayer(poly); });
  seedingExclusionPolygons = [];
}

function updateSeedingDropPoints(dropPoints) {
  seedingDropMarkers.forEach(function(marker) { map.removeLayer(marker); });
  seedingDropMarkers = [];
  seedingDropPointCount = dropPoints ? dropPoints.length : 0;
  if (!dropPoints || dropPoints.length === 0) return;

  // > 300 points: use lightweight circleMarker (canvas, no DOM node per point)
  var large = dropPoints.length > 300;
  var layers = [];
  dropPoints.forEach(function(point, index) {
    // Explicit null/undefined check — lat=0 is valid at equator
    if (point.lat === undefined || point.lat === null ||
        point.lon === undefined || point.lon === null) return;
    var pos = [point.lat, point.lon];
    var marker;
    if (large) {
      marker = L.circleMarker(pos, {
        radius: 3,
        color: "#16a34a",
        fillColor: "#22c55e",
        fillOpacity: 0.85,
        weight: 1,
        interactive: false,
        renderer: seedingCanvasRenderer
      });
    } else {
      var icon = L.divIcon({
        className: "",
        iconSize: [8, 8],
        iconAnchor: [4, 4],
        html: \'<div style="width:8px;height:8px;border-radius:50%;background:#22c55e;border:1px solid #16a34a;"></div>\'
      });
      marker = L.marker(pos, {icon: icon, zIndexOffset: 50});
      marker.bindTooltip(
        "Drop Point " + (index + 1) + "<br>Seeds: " + (point.seedCount || 1) +
        "<br>Alt: " + (point.alt || 0).toFixed(1) + "m",
        {permanent: false, direction: "top"}
      );
    }
    layers.push(marker);
  });
  // Add all at once via LayerGroup — single DOM operation
  var group = L.layerGroup(layers).addTo(map);
  seedingDropMarkers.push(group);
}

function updateSeedingFlightRows(rows) {
  seedingFlightLines.forEach(function(line) { map.removeLayer(line); });
  seedingFlightLines = [];
  if (!rows || rows.length === 0) return;
  if (seedingDropPointCount > 3000) return;
  rows.forEach(function(row, index) {
    if (!row.start || !row.end) return;
    var startPos = [row.start.lat, row.start.lon];
    var endPos = [row.end.lat, row.end.lon];
    var line = L.polyline([startPos, endPos], {
      color: "#3b82f6", weight: 2, opacity: 0.6, dashArray: "8,4"
    }).addTo(map);
    line.bindTooltip("Flight Row " + (row.index || index + 1), {permanent: false, sticky: true});
    seedingFlightLines.push(line);
  });
}

function updateSeedingExclusionZones(zones) {
  seedingExclusionPolygons.forEach(function(poly) { map.removeLayer(poly); });
  seedingExclusionPolygons = [];
  if (!zones || zones.length === 0) return;
  zones.forEach(function(zone, index) {
    if (!zone || zone.length < 3) return;
    var latlngs = zone.map(function(pt) { return [pt.lat, pt.lon]; });
    var poly = L.polygon(latlngs, {
      color: "#ef4444", fillColor: "#ef4444", fillOpacity: 0.2, weight: 2, dashArray: "4,4"
    }).addTo(map);
    poly.bindTooltip("Exclusion Zone " + (index + 1), {permanent: false, sticky: true});
    seedingExclusionPolygons.push(poly);
  });
}

// ── Solar Mission Preview Overlays ──────────────────────────────────────
var solarTriggerMarkers = [], solarFootprintPolygons = [], solarMissionRowLines = [];

function clearSolarPreviewOverlays() {
  solarTriggerMarkers.forEach(function(m) { map.removeLayer(m); });
  solarTriggerMarkers = [];
  solarFootprintPolygons.forEach(function(p) { map.removeLayer(p); });
  solarFootprintPolygons = [];
  solarMissionRowLines.forEach(function(l) { map.removeLayer(l); });
  solarMissionRowLines = [];
}

function updateSolarTriggerPoints(triggerPoints) {
  solarTriggerMarkers.forEach(function(m) { map.removeLayer(m); });
  solarTriggerMarkers = [];
  if (!triggerPoints || triggerPoints.length === 0) return;
  triggerPoints.forEach(function(tp) {
    if (tp.lat === null || tp.lat === undefined || tp.lon === null || tp.lon === undefined) return;
    var gimbal = (tp.gimbalAngle || 0).toFixed(1);
    var icon = L.divIcon({
      className: "",
      iconSize: [22, 22],
      iconAnchor: [11, 11],
      html: \'<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22" role="img" aria-label="Solar camera trigger"><title>Gimbal: \' + gimbal + \' deg</title><circle cx="11" cy="11" r="10" fill="#0f172a" stroke="#38bdf8" stroke-width="1.4"/><path d="M6.2 8.1h2l.8-1.3h4l.8 1.3h2c.8 0 1.4.6 1.4 1.4v5.2c0 .8-.6 1.4-1.4 1.4H6.2c-.8 0-1.4-.6-1.4-1.4V9.5c0-.8.6-1.4 1.4-1.4z" fill="#e0f2fe"/><circle cx="11" cy="12.1" r="2.5" fill="#0284c7"/><circle cx="11" cy="12.1" r="1.2" fill="#bae6fd"/></svg>\'
    });
    var marker = L.marker([tp.lat, tp.lon], {icon: icon, zIndexOffset: 200}).addTo(map);
    marker.bindTooltip("Trigger Point<br>Gimbal: " + gimbal + "&deg;", {permanent: false, direction: "top"});
    solarTriggerMarkers.push(marker);
  });
}

function updateSolarFootprints(triggerPoints) {
  solarFootprintPolygons.forEach(function(p) { map.removeLayer(p); });
  solarFootprintPolygons = [];
  if (!triggerPoints || triggerPoints.length === 0) return;
  triggerPoints.forEach(function(tp) {
    if (!tp.footprint || tp.footprint.length < 3) return;
    var latlngs = tp.footprint.map(function(p) { return [p.lat, p.lon]; });
    var poly = L.polygon(latlngs, {
      color: "#3b82f6", fillColor: "#3b82f6", fillOpacity: 0.12, weight: 1, opacity: 0.5
    }).addTo(map);
    solarFootprintPolygons.push(poly);
  });
}

function updateSolarMissionRows(rows) {
  solarMissionRowLines.forEach(function(l) { map.removeLayer(l); });
  solarMissionRowLines = [];
  if (!rows || rows.length === 0) return;
  rows.forEach(function(row, index) {
    if (!row.start || !row.end) return;
    var line = L.polyline([
      [row.start.lat, row.start.lon],
      [row.end.lat, row.end.lon]
    ], {color: "#f59e0b", weight: 3, opacity: 0.75}).addTo(map);
    line.bindTooltip("Solar Row " + (index + 1), {permanent: false, sticky: true});
    solarMissionRowLines.push(line);
  });
}
</script>
</body>
</html>
'
}
