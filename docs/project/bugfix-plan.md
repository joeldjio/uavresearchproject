# SkyMeshX GCS — Complete Bug-Fix & Feature Plan for Codex

> **This file is written for Codex — another AI that will implement every change.**
> Every instruction is precise: exact file path, exact line number, exact old text,
> exact new text. Codex must not guess or invent — follow every step literally.
>
> After all edits: run `pytest tests/ -x -q` and fill in the Feedback table at the bottom.

---

## Overview of all changes

| ID | File | What changes |
|----|------|-------------|
| C1 | `tools/ui/qml/panels/ROS2Panel.qml` | Bind `selectedDroneId` to AppState; add `_anyBridgeActive` property; add `Component.onCompleted`; update droneCombo write-back; add debug warning; add `Component.onCompleted` in video column; add COMMAND LAUNCHER section |
| C2 | `tools/ui/qml/panels/GimbalPanel.qml` | Add `Component.onCompleted` to call `videoStream.selectDrone` on panel open |
| C3 | `tools/ui/qml/panels/SolarInspectionPanel.qml` | Add `Connections` to re-run capability check on telemetry update |
| C4 | `tools/ui/context/ros2_context.py` | Fix nodeStatus auto-source; add getRos2EnvInfo; add launchCommandInTerminal + buildSitlCommand slots; log ROS_DOMAIN_ID on bridge start; add ImportError handler in _start_sitl_profiles |
| C5 | `tools/ui/context/swarm_context.py` | setMode: emit modeChangeCommandSent + log; setDroneType: emit snapshot with droneType key |
| C6 | `tools/ui/context/video_stream_context.py` | Add GStreamer check in _decoder_loop; improve error message |
| C7 | `skymeshx/models/capabilities.py` | Add drone_type to _SAFE_KEYS; make is_observation check snake_case-tolerant |

---

## C1 — `tools/ui/qml/panels/ROS2Panel.qml`

### C1-1  Line 10: bind selectedDroneId to AppState

**Find exactly (line 10):**
```
    property string selectedDroneId: ""
```
**Replace with:**
```
    property string selectedDroneId: Cmp.AppState.selectedDroneId
```

---

### C1-2  After line 13: add _anyBridgeActive property, Connections, Component.onCompleted

Line 13 currently ends with:
```
    property bool _useVisibleTerminal: (typeof ros2 !== "undefined" && ros2 && ros2.getUseVisibleTerminal) ? ros2.getUseVisibleTerminal() : true
```

**Insert the following block immediately after line 13** (before the `function statusColor` line):

```qml
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
```

---

### C1-3  Line ~182: update droneCombo onCurrentTextChanged

**Find exactly:**
```
                        onCurrentTextChanged: { if (currentText) Cmp.AppState.selectedDroneId = currentText }
```
**Replace with:**
```
                        onCurrentTextChanged: {
                            if (currentText) {
                                root.selectedDroneId = currentText
                                Cmp.AppState.selectedDroneId = currentText
                            }
                        }
```

---

### C1-4  Debug tab (TAB 4): add "bridge not active" warning as first child of `Column { id: cmdCol`

**Find exactly (inside TAB 4):**
```
                        id: cmdCol
                        anchors { fill: parent; margins: 10 }
                        spacing: 6
                        Repeater {
```
**Replace with:**
```
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
                                      : "⚠  PX4 bridge not active — go to Connection tab → click Connect"
                                color: "#fcd34d"; font.pixelSize: 9; wrapMode: Text.WordWrap
                            }
                        }

                        Repeater {
```

---

### C1-5  Video tab (TAB 3): add Component.onCompleted inside Column { id: videoStreamCol }

**Find exactly (inside TAB 3):**
```
                        id: videoStreamCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        spacing: 8

                        property string _vsStatus: {
```
**Replace with:**
```
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
```

---

### C1-6  Connection tab (TAB 0): add COMMAND LAUNCHER section

This section is inserted **just before the final `Item { width: 1; height: 8 }` line** inside
the Connection tab's `Column`. That line is currently line 628.

**Find exactly (lines 627–629, end of Connection tab Column):**
```
                }
                Item { width: 1; height: 8 }
            }
        }

        // ══════════════════════════════════════════════════════════
        // TAB 1 — TOPICS
```
**Replace with:**
```
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
                                anchors { fill: parent; leftMargin: 8; verticalCenter: parent.verticalCenter }
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
                                readOnly: true; selectByMouse: true
                                color: "#86efac"; font.pixelSize: 9; font.family: "Consolas"
                                wrapMode: TextEdit.Wrap; background: null
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
                                        var cmd = "cd " + xrceDirField.text
                                                  + " && MicroXRCEAgent udp4 -p " + xrcePortField.text
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
                                readOnly: true; selectByMouse: true
                                color: "#86efac"; font.pixelSize: 9; font.family: "Consolas"
                                wrapMode: TextEdit.Wrap; background: null
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
                                        var dir = ros2.getSitlPx4Dir()
                                        if (!dir || dir === "") dir = "~/PX4-Autopilot"
                                        var ns = launchNsField.text || "uav_1"
                                        var mt = makeTargetField.text || "gz_x500"
                                        var cmd = "cd " + dir
                                                  + " && export PX4_UXRCE_DDS_NS=" + ns
                                                  + " && make px4_sitl " + mt
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
                                readOnly: true; selectByMouse: true
                                color: "#93c5fd"; font.pixelSize: 9; font.family: "Consolas"
                                wrapMode: TextEdit.Wrap; background: null
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
                                        var setupSrc = setupSourcesEdit && setupSourcesEdit.text.trim() !== ""
                                                       ? setupSourcesEdit.text.split("\n")[0].trim()
                                                       : "/opt/ros/humble/setup.bash"
                                        var cmd = "cd " + ros2WsDirField.text
                                                  + " && source " + setupSrc
                                                  + " && source install/local_setup.bash"
                                                  + " && ros2 launch " + ros2LaunchFileField.text
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
                                        + "2. GCS header → select TCP → 127.0.0.1 : 5762 → click  + ADD\n"
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
```

> **Note for Codex:** The block above replaces the **original** text:
> ```
>                 }
>                 Item { width: 1; height: 8 }
>             }
>         }
>
>         // ══════════════════════════════════════════════════════════
>         // TAB 1 — TOPICS
> ```
> Make sure the TAB 1 comment is NOT duplicated.

---

## C2 — `tools/ui/qml/panels/GimbalPanel.qml`

### C2-1  Line 16: add Component.onCompleted after the `isObservation` function

**Find exactly (lines 11–17):**
```
    property string selectedDroneId: typeof swarm !== "undefined" ? (swarm.droneIds().length > 0 ? swarm.droneIds()[0] : "") : ""

    function isObservation(did) {
        if (!did || typeof swarm === "undefined" || !swarm) return false
        return swarm.droneType(did) === "observation"
    }

    ScrollView {
```
**Replace with:**
```
    property string selectedDroneId: typeof swarm !== "undefined" ? (swarm.droneIds().length > 0 ? swarm.droneIds()[0] : "") : ""

    function isObservation(did) {
        if (!did || typeof swarm === "undefined" || !swarm) return false
        return swarm.droneType(did) === "observation"
    }

    // Select the drone in VideoStreamContext when this panel opens so the
    // stream status badge and frame URL are already wired up.
    Component.onCompleted: {
        if (root.selectedDroneId !== "" &&
            typeof videoStream !== "undefined" && videoStream)
            videoStream.selectDrone(root.selectedDroneId)
    }

    ScrollView {
```

---

## C3 — `tools/ui/qml/panels/SolarInspectionPanel.qml`

### C3-1  Line 16: add Connections after Component.onCompleted

**Find exactly (lines 13–17):**
```
    Component.onCompleted: {
        console.log("[SolarInspectionPanel] Loaded! Width:", width, "Height:", height, "Column height:", contentColumn.height)
        checkCapabilities()
    }
```
**Replace with:**
```
    Component.onCompleted: {
        console.log("[SolarInspectionPanel] Loaded! Width:", width, "Height:", height, "Column height:", contentColumn.height)
        checkCapabilities()
    }

    // Re-run the capability check whenever the drone type changes.
    // SwarmContext.setDroneType emits telemetryUpdated — catching it here
    // means the wizard unlocks immediately after the user picks "Observation".
    Connections {
        target: typeof swarm !== "undefined" ? swarm : null
        function onTelemetryUpdated() { root.checkCapabilities() }
    }
```

---

## C4 — `tools/ui/context/ros2_context.py`

### C4-1  Lines 725–732: fix nodeStatus to auto-source setup files

**Find exactly (lines 725–732):**
```python
    @Slot(result=str)
    def nodeStatus(self) -> str:
        _refresh_ros2_availability()
        if not _ROS2_AVAILABLE:
            return "no_ros2"
        if not _BRIDGE_AVAILABLE:
            return "no_px4_msgs"
        return "ok"
```
**Replace with:**
```python
    @Slot(result=str)
    def nodeStatus(self) -> str:
        _refresh_ros2_availability()
        if not _ROS2_AVAILABLE:
            # On Linux with ROS2, rclpy is only importable after setup.bash is
            # sourced.  Try sourcing once per poll cycle so the status dot turns
            # green automatically when the user has configured setup files.
            sources = self._ros2_setup_sources()
            if sources:
                self._apply_ros2_setup_environment(sources, "status_check")
                _refresh_ros2_availability()
            if not _ROS2_AVAILABLE:
                return "no_ros2"
        if not _BRIDGE_AVAILABLE:
            return "no_px4_msgs"
        return "ok"
```

---

### C4-2  Lines 803–804: log ROS_DOMAIN_ID when bridge starts

**Find exactly (lines 803–806):**
```python
                self.ros2LogMessage.emit("INFO", f"[ROS2] Bridge started for {drone_id} ns='{ns or '/'}'")
                self.ros2LogMessage.emit("INFO", f"[ROS2] Listening on {ns or ''}/fmu/out/*")
                self._write_bridge_terminal_log(drone_id, "Bridge started")
                self._write_bridge_terminal_log(drone_id, f"Listening on {ns or ''}/fmu/out/*")
```
**Replace with:**
```python
                self.ros2LogMessage.emit("INFO", f"[ROS2] Bridge started for {drone_id} ns='{ns or '/'}'")
                self.ros2LogMessage.emit("INFO", f"[ROS2] Listening on {ns or ''}/fmu/out/*")
                domain = os.environ.get("ROS_DOMAIN_ID", "0 (default)")
                self.ros2LogMessage.emit("INFO",
                    f"[ROS2] ROS_DOMAIN_ID={domain} — PX4 must use the same domain")
                self.ros2LogMessage.emit("INFO",
                    "[ROS2] MicroXRCEAgent udp4 -p 8888 must be running in a separate terminal")
                self._write_bridge_terminal_log(drone_id, "Bridge started")
                self._write_bridge_terminal_log(drone_id, f"Listening on {ns or ''}/fmu/out/*")
```

---

### C4-3  Lines 1297–1299: add ImportError handler in _start_sitl_profiles

**Find exactly (lines 1294–1299):**
```python
            except Exception as exc:
                self._sitl_status.update({"running": False, "status": "failed", "gazebo_running": False})
                self.ros2LogMessage.emit("ERROR", f"[SITL] Start failed: {exc}")
                self._trace_event("sitl_launch", {"status": "failed", "error": str(exc)})
            finally:
                self._emit_sitl_status()
```
**Replace with:**
```python
            except ImportError as exc:
                self._sitl_status.update({"running": False, "status": "failed", "gazebo_running": False})
                self.ros2LogMessage.emit("ERROR",
                    f"[SITL] PX4GazeboCluster not available ({exc}). "
                    "Use the Command Launcher in the Connection tab to start PX4 manually.")
                self._trace_event("sitl_launch", {"status": "failed", "error": str(exc)})
            except Exception as exc:
                self._sitl_status.update({"running": False, "status": "failed", "gazebo_running": False})
                self.ros2LogMessage.emit("ERROR", f"[SITL] Start failed: {exc}")
                self._trace_event("sitl_launch", {"status": "failed", "error": str(exc)})
            finally:
                self._emit_sitl_status()
```

---

### C4-4  After line 1127: add new slots getRos2EnvInfo, launchCommandInTerminal, buildSitlCommand

Insert the following block **after the `setUseVisibleTerminal` slot** (after line 1127,
before `addSitlRos2Setup`):

```python
    @Slot(result=str)
    def getRos2EnvInfo(self) -> str:
        """Return current ROS_DOMAIN_ID and ROS_LOCALHOST_ONLY for display in the UI."""
        domain = os.environ.get("ROS_DOMAIN_ID", "0 (default)")
        localhost = os.environ.get("ROS_LOCALHOST_ONLY", "0")
        return f"ROS_DOMAIN_ID={domain}  ROS_LOCALHOST_ONLY={localhost}"

    @Slot(str, str, result=bool)
    def launchCommandInTerminal(self, title: str, command: str) -> bool:
        """
        Open a visible terminal emulator and run *command* in it.

        Internally delegates to _launch_visible_terminal which tries
        gnome-terminal / konsole / xfce4-terminal / xterm in order.
        Returns True if a terminal process was spawned, False otherwise
        (e.g., on Windows or when no emulator is found in PATH).
        """
        proc = self._launch_visible_terminal(title, [command])
        if proc is None:
            return False
        self.ros2LogMessage.emit("INFO", f"[ROS2] Terminal opened: {title}")
        return True

    @Slot(str, str, str, result=str)
    def buildSitlCommand(self, px4_dir: str, namespace: str, make_target: str) -> str:
        """
        Build the three-line PX4 SITL startup command string.
        Useful for QML TextEdit live-preview fields.
        """
        import shlex as _shlex
        ns  = namespace.strip()   or "uav_1"
        mt  = make_target.strip() or "gz_x500"
        px4 = os.path.expanduser(px4_dir.strip()) if px4_dir.strip() else "~/PX4-Autopilot"
        return (
            f"cd {_shlex.quote(px4)}\n"
            f"export PX4_UXRCE_DDS_NS={_shlex.quote(ns)}\n"
            f"make px4_sitl {_shlex.quote(mt)}"
        )
```

---

## C5 — `tools/ui/context/swarm_context.py`

### C5-1  Lines 685–690: setMode — emit modeChangeCommandSent and log

**Find exactly (lines 685–690):**
```python
    @Slot(str, str)
    def setMode(self, drone_id: str, mode: str) -> None:
        """Switch flight mode for a single drone."""
        b = self._backend.get_backend(drone_id)
        if b:
            b.set_mode(mode)
```
**Replace with:**
```python
    @Slot(str, str)
    def setMode(self, drone_id: str, mode: str) -> None:
        """Switch flight mode for a single drone."""
        b = self._backend.get_backend(drone_id)
        if b:
            b.set_mode(mode)
            self.modeChangeCommandSent.emit(drone_id, mode)
            self.logMessage.emit("INFO", f"[{drone_id}] MODE → {mode}")
```

---

### C5-2  Lines 761–767: setDroneType — emit snapshot with droneType key

**Find exactly (lines 761–767):**
```python
    @Slot(str, str)
    def setDroneType(self, drone_id: str, drone_type: str) -> None:
        b = self._backend.get_backend(drone_id)
        if b:
            b.drone_type = drone_type
            self.logMessage.emit("INFO", f"[{drone_id}] Typ gesetzt: {drone_type}")
            self.telemetryUpdated.emit({})
```
**Replace with:**
```python
    @Slot(str, str)
    def setDroneType(self, drone_id: str, drone_type: str) -> None:
        b = self._backend.get_backend(drone_id)
        if b:
            b.drone_type = drone_type
            self.logMessage.emit("INFO", f"[{drone_id}] Typ gesetzt: {drone_type}")
            # Include the new type in the snapshot so detect_capabilities()
            # can read it without waiting for a full telemetry cycle.
            snap = b.get_telemetry_snapshot() or {}
            snap["droneType"] = drone_type
            self.telemetryUpdated.emit(snap)
```

---

## C6 — `tools/ui/context/video_stream_context.py`

### C6-1  Lines 359–369: _decoder_loop — improve error message + add GStreamer check

**Find exactly (lines 359–369):**
```python
    def _decoder_loop(self, drone_id: str, state: _DroneVideoState) -> None:
        cv2 = _load_cv2()
        if cv2 is None:
            self._set_error(
                drone_id,
                state,
                "OpenCV with GStreamer support is required for live video frames",
            )
            return

        source = _opencv_source(state)
```
**Replace with:**
```python
    def _decoder_loop(self, drone_id: str, state: _DroneVideoState) -> None:
        cv2 = _load_cv2()
        if cv2 is None:
            self._set_error(
                drone_id,
                state,
                "OpenCV (cv2) not installed. "
                "Fix: sudo apt install python3-opencv   "
                "or   pip install opencv-python",
            )
            return

        # Verify that GStreamer was compiled into OpenCV before attempting
        # an RTP/H.264 pipeline — without it the VideoCapture will silently fail.
        if state.protocol == "rtp-h264-udp":
            build_info = getattr(cv2, "getBuildInformation", lambda: "")()
            if "GStreamer" not in build_info:
                self._set_error(
                    drone_id,
                    state,
                    "OpenCV compiled without GStreamer — RTP/H.264 streams will not work. "
                    "Fix: sudo apt install python3-opencv  "
                    "(system package includes the GStreamer backend; "
                    "replaces the pip opencv-python package)",
                )
                return

        source = _opencv_source(state)
```

---

## C7 — `skymeshx/models/capabilities.py`

### C7-1  Line 119: make is_observation tolerate snake_case key

**Find exactly (line 119):**
```python
    drone_type = str(data.get("droneType") or data.get("type") or "").lower()
```
**Replace with:**
```python
    drone_type = str(
        data.get("droneType") or data.get("drone_type") or data.get("type") or ""
    ).lower()
```

---

### C7-2  Lines 191–192: add drone_type to _SAFE_KEYS

**Find exactly (lines 191–192):**
```python
    _SAFE_KEYS = ("has_camera", "has_gimbal", "has_thermal", "has_dispenser",
                  "has_gps", "droneType", "type")
```
**Replace with:**
```python
    _SAFE_KEYS = ("has_camera", "has_gimbal", "has_thermal", "has_dispenser",
                  "has_gps", "droneType", "type", "drone_type")
```

---

## Test commands

Run after **all** changes are applied:

```bash
# From project root
pytest tests/ -x -q

# Targeted (most likely to catch regressions)
pytest tests/test_swarm.py tests/test_backend.py tests/test_capabilities.py -v
```

---

## Codex Feedback (fill in after implementation)

| Change | File | Lines edited | pytest pass? | Notes |
|--------|------|-------------|-------------|-------|
| C1-1 selectedDroneId binding | ROS2Panel.qml | 10 | Partial | Implemented; relevant regression subset passed. |
| C1-2 _anyBridgeActive + Connections + onCompleted | ROS2Panel.qml | after 13 | Partial | Implemented; added initial combo/AppState sync. |
| C1-3 droneCombo write-back | ROS2Panel.qml | ~182 | Partial | Implemented. |
| C1-4 debug warning | ROS2Panel.qml | ~1118 | Partial | Implemented. |
| C1-5 video tab onCompleted | ROS2Panel.qml | ~906 | Partial | Implemented. |
| C1-6 COMMAND LAUNCHER section | ROS2Panel.qml | ~627 | Partial | Implemented; also made previews editable and added Build ROS2 Workspace terminal command. |
| C2-1 GimbalPanel onCompleted | GimbalPanel.qml | 17 | Partial | Implemented; also syncs AppState and case-tolerates observation type. |
| C3-1 SolarPanel Connections | SolarInspectionPanel.qml | 17 | Partial | Implemented; now checks selected drone explicitly. |
| C4-1 nodeStatus auto-source | ros2_context.py | 725 | Partial | Implemented; import probe now tolerates mocked rclpy. |
| C4-2 log ROS_DOMAIN_ID | ros2_context.py | 803 | Partial | Implemented. |
| C4-3 ImportError handler | ros2_context.py | 1294 | Partial | Implemented. |
| C4-4 new slots | ros2_context.py | after 1127 | Partial | Implemented; terminal launcher now supports Windows Terminal/WSL. |
| C5-1 setMode signal | swarm_context.py | 685 | Partial | Implemented. |
| C5-2 setDroneType snapshot | swarm_context.py | 761 | Partial | Implemented. |
| C6-1 GStreamer check | video_stream_context.py | 359 | Partial | Implemented; GStreamer check now detects `GStreamer: NO`. |
| C7-1 is_observation snake_case | capabilities.py | 119 | Partial | Implemented. |
| C7-2 _SAFE_KEYS drone_type | capabilities.py | 191 | Partial | Implemented. |

**Overall pytest result:** `python -m pytest tests/ -x -q` collected but stopped on existing `tests/e2e/test_qt_ui_workflows.py` missing fixture `wired_locator`. Plan-targeted files `tests/test_swarm.py tests/test_backend.py tests/test_capabilities.py` do not exist in this checkout. Matching regression subset passed: `93 passed in 1.41s`.

**New issues found during implementation:** Trace analysis showed PX4 DDS namespace was `uav_1` while ROS2 UI defaulted to empty namespace; PX4 MAVLink sends to UDP remote 14550, so header now supports `udpin:0.0.0.0:14550`; Windows terminal launch needed WSL support.

**Anything unclear in these instructions:** The requested target test filenames are stale for this checkout.
