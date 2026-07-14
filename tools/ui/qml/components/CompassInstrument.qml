import QtQuick

// ── Compass Instrument ───────────────────────────────────────────────
// A circular compass showing heading with cardinal directions
// Properties:
//   heading: current heading in degrees (0-360, 0=North)
//   size: diameter of the compass (default 80)
//   showLabel: show heading text below compass (default true)
Item {
    id: root
    width: size
    height: size + (showLabel ? 16 : 0)

    property real heading: 0.0
    property int size: 80
    property bool showLabel: true

    // Internal smoothed heading drives the visual — avoids animation stacking
    // when new values arrive faster than the animation completes.
    property real _smoothHeading: 0.0
    onHeadingChanged: _smoothHeading = heading

    // Dark circular background
    Rectangle {
        id: compassBg
        anchors.centerIn: parent
        width: root.size
        height: root.size
        radius: root.size / 2
        color: "#1a1f2e"
        border.color: "#2d3748"
        border.width: 2

        // Compass rose (rotates with heading)
        Item {
            id: compassRose
            anchors.centerIn: parent
            width: parent.width
            height: parent.height
            rotation: -root._smoothHeading

            // Cardinal direction markers
            Repeater {
                model: [
                    { angle: 0, label: "N", color: "#ef4444" },
                    { angle: 45, label: "", color: "#64748b" },
                    { angle: 90, label: "E", color: "#64748b" },
                    { angle: 135, label: "", color: "#64748b" },
                    { angle: 180, label: "S", color: "#64748b" },
                    { angle: 225, label: "", color: "#64748b" },
                    { angle: 270, label: "W", color: "#64748b" },
                    { angle: 315, label: "", color: "#64748b" }
                ]

                Item {
                    width: compassRose.width
                    height: compassRose.height
                    rotation: modelData.angle

                    // Tick mark
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 4
                        width: modelData.label !== "" ? 2 : 1
                        height: modelData.label !== "" ? 8 : 4
                        color: modelData.color
                    }

                    // Cardinal letter
                    Text {
                        visible: modelData.label !== ""
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 14
                        text: modelData.label
                        color: modelData.color
                        font.pixelSize: 11
                        font.weight: Font.Bold
                        font.family: "Consolas"
                        rotation: -modelData.angle // Keep text upright
                    }
                }
            }
        }

        // Red arrow pointer (fixed, points to heading)
        Canvas {
            id: arrowCanvas
            anchors.centerIn: parent
            width: parent.width * 0.5
            height: parent.height * 0.5

            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                
                var centerX = width / 2
                var centerY = height / 2
                var arrowLength = height * 0.7
                var arrowWidth = width * 0.3

                // Draw red arrow pointing up
                ctx.fillStyle = "#ef4444"
                ctx.beginPath()
                ctx.moveTo(centerX, centerY - arrowLength) // Tip
                ctx.lineTo(centerX - arrowWidth / 2, centerY + arrowLength / 3) // Left base
                ctx.lineTo(centerX, centerY) // Center notch
                ctx.lineTo(centerX + arrowWidth / 2, centerY + arrowLength / 3) // Right base
                ctx.closePath()
                ctx.fill()

                // Outline
                ctx.strokeStyle = "#7f1d1d"
                ctx.lineWidth = 1
                ctx.stroke()
            }
        }

        // Center dot
        Rectangle {
            anchors.centerIn: parent
            width: 6
            height: 6
            radius: 3
            color: "#ef4444"
            border.color: "#7f1d1d"
            border.width: 1
        }
    }

    // Heading text below compass
    Rectangle {
        visible: root.showLabel
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: compassBg.bottom
        anchors.topMargin: 4
        width: headingText.implicitWidth + 12
        height: 18
        radius: 3
        color: "#1a1f2e"
        border.color: "#2d3748"
        border.width: 1

        Text {
            id: headingText
            anchors.centerIn: parent
            text: Math.round(root.heading) + "°"
            color: "#e2e8f0"
            font.pixelSize: 10
            font.weight: Font.Bold
            font.family: "Consolas"
        }
    }

    // Smooth rotation — applied to the internal display property only
    Behavior on _smoothHeading {
        RotationAnimation {
            duration: 180
            direction: RotationAnimation.Shortest
        }
    }
}