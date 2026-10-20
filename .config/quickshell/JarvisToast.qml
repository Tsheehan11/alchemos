// "JARVIS" pop-up that appears on the focused screen when the wake word is heard.
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
    implicitWidth: 500
    implicitHeight: 88
    color: "transparent"

    readonly property color cyan: Theme.primary
    readonly property string mono: "JetBrainsMono Nerd Font"

    Rectangle {
        id: panel
        anchors.fill: parent
        color: Theme.d(0.9)
        border.color: Theme.p(0.6)
        border.width: 1

        opacity: 0
        scale: 0.9
        states: State {
            name: "on"; when: toast.visible
            PropertyChanges { target: panel; opacity: 1; scale: 1 }
        }
        transitions: Transition {
            NumberAnimation { properties: "opacity,scale"; duration: 220; easing.type: Easing.OutCubic }
        }

        Row {
            anchors.fill: parent
            anchors.leftMargin: 20
            spacing: 20

            // Pulsing rings
            Item {
                width: 56; height: 56
                anchors.verticalCenter: parent.verticalCenter
                Ring {
                    anchors.centerIn: parent
                    radius: 25; thickness: 2; value: 1
                    dashed: true; dash: [6, 3]
                    color: toast.cyan; trackColor: "transparent"
                    RotationAnimation on rotation { running: toast.visible; from: 0; to: 360; duration: 2400; loops: Animation.Infinite }
                }
                Rectangle {
                    anchors.centerIn: parent
                    width: 30; height: 30; radius: 15
                    color: Theme.p(0.25)
                    border.color: toast.cyan
                    SequentialAnimation on scale {
                        running: toast.visible
                        loops: Animation.Infinite
                        NumberAnimation { from: 0.85; to: 1.15; duration: 500; easing.type: Easing.InOutSine }
                        NumberAnimation { from: 1.15; to: 0.85; duration: 500; easing.type: Easing.InOutSine }
                    }
                }
            }

            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                Text {
                    text: "JARVIS"
                    color: toast.cyan
                    font.family: toast.mono; font.pixelSize: 11; font.letterSpacing: 3
                }
                Text {
                    text: JarvisState.message
                    color: Theme.text
                    font.family: toast.mono; font.pixelSize: 17
                }
            }
        }
    }
}
