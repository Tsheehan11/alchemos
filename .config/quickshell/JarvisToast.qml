// JARVIS pop-up on the focused screen (the one Quickshell treats as focused). Follows JarvisState.phase:
//   LISTENING (waveform) → transcript → PROCESSING (tool calls appear one by one,
//   "◆ THEME → MARK III") → RESPONSE / AWAITING CONFIRMATION → FOLLOW-UP.
// Clicking it opens the JARVIS console on the same monitor.
// Timers and reminders use the same panel (phase "alert").
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

PanelWindow {
    id: toast
    required property var modelData
    screen: modelData

    visible: JarvisState.showing && Hyprland.focusedMonitor?.name === modelData.name

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-jarvis"
    exclusionMode: ExclusionMode.Ignore
    anchors { bottom: true }
    margins { bottom: 60 }
    implicitWidth: 640
    implicitHeight: Math.max(104, Math.min(360, body.implicitHeight + 36))
    color: "transparent"

    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property string phase: JarvisState.phase
    readonly property bool hot: phase === "confirm" || phase === "alert" || phase === "error"     // secondary colour
    readonly property color accent: hot ? Theme.secondary : Theme.primary
    readonly property bool busy: phase === "thinking"
    readonly property string phaseLabel: ({
        listening: "LISTENING", followup: "LISTENING · FOLLOW-UP", thinking: "PROCESSING",
        reply: "RESPONSE", confirm: "AWAITING CONFIRMATION", alert: JarvisState.alertTitle,
        error: "⚠ " + JarvisState.errorReason, idle: ""
    })[phase] || ""

    Item {
        id: panel
        anchors.fill: parent
        opacity: 0
        scale: 0.94
        states: State {
            name: "on"; when: toast.visible
            PropertyChanges { target: panel; opacity: 1; scale: 1 }
        }
        transitions: Transition {
            NumberAnimation { properties: "opacity,scale"; duration: 240; easing.type: Easing.OutCubic }
        }

        // click anywhere on it → the JARVIS console (Super + J) on this monitor; drawn first, so it sits
        // under everything else in the panel
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: JarvisLink.show(toast.modelData.name)
        }

        // ── Hologram glass ──
        Rectangle {
            id: glass
            anchors.fill: parent
            color: Theme.d(Math.max(0.82, Theme.panelAlpha))
            border.color: Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.55)
            border.width: 1
            clip: true
            Behavior on border.color { ColorAnimation { duration: 300 } }

            // fine scanlines
            Column {
                anchors.fill: parent
                spacing: 3
                Repeater {
                    model: Math.ceil(glass.height / 4)
                    Rectangle { width: glass.width; height: 1; color: Theme.p(0.035) }
                }
            }
            // sweeping scan band
            Rectangle {
                width: parent.width; height: 46
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.09) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                NumberAnimation on y {
                    running: toast.visible
                    from: -46; to: glass.height; duration: toast.busy ? 1400 : 2800; loops: Animation.Infinite
                }
            }
            // left edge glow bar
            Rectangle {
                width: 3; height: parent.height; color: toast.accent
                opacity: toast.busy ? 0.55 + 0.45 * Math.sin(glowT.t) : 0.9
            }
        }
        QtObject { id: glowT; property real t: 0; NumberAnimation on t { running: toast.visible && toast.busy; from: 0; to: Math.PI * 2; duration: 900; loops: Animation.Infinite } }

        // corner brackets
        Repeater {
            model: 4
            delegate: Item {
                required property int index
                width: 14; height: 14
                x: index % 2 === 0 ? -3 : panel.width - 11
                y: index < 2 ? -3 : panel.height - 11
                Rectangle { width: 14; height: 2; color: toast.accent; y: index < 2 ? 0 : 12 }
                Rectangle { width: 2; height: 14; color: toast.accent; x: index % 2 === 0 ? 0 : 12 }
            }
        }

        // ── Reactor ──
        Item {
            id: reactor
            width: 68; height: 68
            x: 20; y: 18
            Ring {
                anchors.centerIn: parent
                radius: 30; thickness: 2; value: 1; animated: false
                dashed: true; dash: [5, 3]
                color: toast.accent; trackColor: "transparent"
                RotationAnimation on rotation { running: toast.visible; from: 0; to: 360; duration: toast.busy ? 1100 : 3200; loops: Animation.Infinite }
            }
            Ring {
                anchors.centerIn: parent
                radius: 22; thickness: 1.5; value: toast.busy ? 0.3 : 0.7; animated: false
                color: Qt.lighter(toast.accent, 1.3); trackColor: Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.12)
                RotationAnimation on rotation { running: toast.visible; from: 360; to: 0; duration: toast.busy ? 700 : 2400; loops: Animation.Infinite }
            }
            Rectangle {
                anchors.centerIn: parent
                width: 26; height: 26; radius: 13
                color: Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.28)
                border.color: toast.accent
                SequentialAnimation on scale {
                    running: toast.visible
                    loops: Animation.Infinite
                    NumberAnimation { from: 0.82; to: 1.12; duration: JarvisState.listening ? 380 : 700; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 1.12; to: 0.82; duration: JarvisState.listening ? 380 : 700; easing.type: Easing.InOutSine }
                }
            }
        }

        // ── Text column ──
        Column {
            id: body
            anchors.left: reactor.right; anchors.leftMargin: 20
            anchors.right: parent.right; anchors.rightMargin: 22
            y: 16
            spacing: 7

            // header
            Item {
                width: parent.width; height: 16
                Text {
                    text: "J.A.R.V.I.S"
                    color: Theme.primary
                    font.family: toast.mono; font.pixelSize: 11; font.letterSpacing: 4
                }
                Row {
                    anchors.right: parent.right
                    spacing: 7
                    Rectangle {
                        width: 6; height: 6; radius: 3
                        anchors.verticalCenter: parent.verticalCenter
                        color: toast.accent
                        SequentialAnimation on opacity {
                            running: toast.visible; loops: Animation.Infinite
                            NumberAnimation { from: 1; to: 0.2; duration: 500 }
                            NumberAnimation { from: 0.2; to: 1; duration: 500 }
                        }
                    }
                    Text {
                        text: toast.phaseLabel
                        color: toast.hot ? Theme.secondary : Theme.dim
                        font.family: toast.mono; font.pixelSize: 10; font.letterSpacing: 3
                    }
                }
            }

            // waveform while listening with nothing heard yet
            Row {
                visible: JarvisState.listening && JarvisState.transcript === ""
                height: 26; spacing: 4
                Repeater {
                    model: 18
                    Rectangle {
                        required property int index
                        width: 4; radius: 2
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.p(0.75)
                        height: 6
                        SequentialAnimation on height {
                            running: toast.visible && JarvisState.listening
                            loops: Animation.Infinite
                            NumberAnimation { to: 8 + (index * 37 % 17); duration: 180 + (index * 53 % 160); easing.type: Easing.InOutSine }
                            NumberAnimation { to: 4; duration: 180 + (index * 29 % 140); easing.type: Easing.InOutSine }
                        }
                    }
                }
            }

            // what Trevor said
            Text {
                visible: JarvisState.transcript !== ""
                width: parent.width
                text: "“" + JarvisState.transcript + "”"
                color: Theme.textSoft
                font.family: toast.mono; font.pixelSize: 13; font.italic: true
                wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
            }

            // tool calls as they run
            Column {
                visible: JarvisState.tools.length > 0 && toast.phase !== "alert"
                width: parent.width
                spacing: 3
                Repeater {
                    model: JarvisState.tools
                    Text {
                        id: line
                        required property string modelData
                        required property int index
                        text: "◆ " + modelData
                        color: Theme.secondary
                        font.family: toast.mono; font.pixelSize: 12; font.letterSpacing: 2
                        opacity: 0; x: -14
                        Component.onCompleted: appear.start()
                        ParallelAnimation {
                            id: appear
                            NumberAnimation { target: line; property: "opacity"; to: 1; duration: 260 }
                            NumberAnimation { target: line; property: "x"; to: 0; duration: 260; easing.type: Easing.OutCubic }
                        }
                    }
                }
            }

            // thinking dots
            Text {
                visible: toast.busy && JarvisState.reply === ""
                text: "▸ " + "· · ·".slice(0, 1 + 2 * dots.n)
                color: Theme.dim
                font.family: toast.mono; font.pixelSize: 13
                QtObject { id: dots; property int n: 0 }
                Timer { running: parent.visible && toast.visible; interval: 280; repeat: true; onTriggered: dots.n = (dots.n + 1) % 3 }
            }

            // reply / question / reminder
            Text {
                visible: JarvisState.reply !== "" && ["reply", "confirm", "alert", "followup", "error"].includes(toast.phase)
                width: parent.width
                text: JarvisState.reply
                color: toast.hot ? Qt.lighter(Theme.secondary, 1.15) : Theme.text
                font.family: toast.mono; font.pixelSize: toast.phase === "alert" ? 19 : 16
                wrapMode: Text.Wrap; maximumLineCount: 7; elide: Text.ElideRight
                lineHeight: 1.08
            }
        }
    }
}
