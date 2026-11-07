// The glow around a window while Jarvis works it (JarvisControlState). An overlay layer exactly over the
// window plus a margin for the glow, input-transparent (empty mask): clicks, Jarvis's own included, go to
// the window underneath. A tag on the top edge says what it's doing and how to stop it.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: frame
    required property var modelData
    screen: modelData

    readonly property bool here: JarvisControlState.on && JarvisControlState.screenName === modelData.name
    readonly property int pad: 14                      // room for the glow outside the window
    readonly property color tone: JarvisControlState.stopped ? Theme.secondary : Theme.primary
    visible: here || glow.opacity > 0.01

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-jarvis-control"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; left: true }
    margins {
        left: Math.max(0, JarvisControlState.wx - pad)
        top: Math.max(0, JarvisControlState.wy - pad)
    }
    implicitWidth: Math.max(1, JarvisControlState.ww + 2 * pad)
    implicitHeight: Math.max(1, JarvisControlState.wh + 2 * pad)
    color: "transparent"
    Binding { target: frame.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }   // out of screenshots (Shot.qml)
    mask: Region {}

    Item {
        id: glow
        anchors.fill: parent
        opacity: frame.here ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 220 } }

        // soft outer glow: a few widening, fading outlines
        Repeater {
            model: 6
            Rectangle {
                required property int index
                anchors.fill: parent
                anchors.margins: frame.pad - 2 - index * 2
                color: "transparent"; radius: 6 + index * 2
                border.width: 2
                border.color: Qt.rgba(frame.tone.r, frame.tone.g, frame.tone.b, 0.42 - index * 0.065)
            }
        }
        // the line itself, breathing
        Rectangle {
            anchors.fill: parent; anchors.margins: frame.pad - 1
            color: "transparent"; radius: 6
            border.width: 2; border.color: frame.tone
            SequentialAnimation on opacity {
                running: frame.here && !JarvisControlState.stopped; loops: Animation.Infinite
                NumberAnimation { to: 0.55; duration: 900; easing.type: Easing.InOutSine }
                NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
            }
        }
        // what it's doing, on the top edge
        Rectangle {
            x: frame.pad + 14; y: frame.pad - height / 2
            width: tag.implicitWidth + 18; height: 20
            color: Qt.rgba(Theme.bg.r, Theme.bg.g, Theme.bg.b, 0.92); border.color: frame.tone; radius: 3
            Text {
                id: tag; anchors.centerIn: parent
                text: JarvisControlState.text + (JarvisControlState.stopped ? "" : "   ·   SUPER+SHIFT+ESC / \"STOP\" TO STOP")
                color: frame.tone; font.family: Style.fonts.body; font.pixelSize: 10; font.letterSpacing: 1.2
            }
        }
    }
}
