// While a widget is being moved (Widgets.moving), every screen gets this transparent layer:
// the nine drop slots (the one it would land in lit up) and a ghost of the card under the
// cursor, on whichever monitor the cursor is on. Release, or click, to drop; Esc cancels.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: ov
    required property var modelData
    screen: modelData

    visible: Widgets.moving !== ""
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-widget-move"
    WlrLayershell.keyboardFocus: here ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: Theme.back(here ? 0.22 : 0.12)

    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property bool here: Widgets.curX >= modelData.x && Widgets.curX < modelData.x + modelData.width
                              && Widgets.curY >= modelData.y && Widgets.curY < modelData.y + modelData.height
    readonly property var target: { Widgets.curX; Widgets.curY; return Widgets.dropSlot(); }
    readonly property real gw: Widgets.widths[Widgets.moving] || 200
    readonly property real gh: Widgets.heights[Widgets.moving] || 100
    readonly property var it: Widgets.get(Widgets.moving)

    // the nine slots
    Repeater {
        model: Widgets.positions
        delegate: Rectangle {
            required property string modelData
            readonly property int c: modelData.endsWith("left") ? 0 : modelData.endsWith("right") ? 2 : 1
            readonly property int r: modelData.startsWith("top") ? 0 : modelData.startsWith("bottom") ? 2 : 1
            readonly property bool lit: ov.here && ov.target && ov.target.position === modelData
            width: Math.min(ov.gw, ov.width / 3 - 40); height: Math.min(ov.gh, ov.height / 3 - 40)
            x: c === 0 ? 28 : c === 2 ? ov.width - width - 28 : (ov.width - width) / 2
            y: r === 0 ? 54 : r === 2 ? ov.height - height - 28 : (ov.height - height) / 2
            color: lit ? Theme.p(0.14) : "transparent"
            border.color: lit ? Theme.primary : Theme.p(0.25)
            border.width: lit ? 2 : 1
            Behavior on color { ColorAnimation { duration: 120 } }
        }
    }

    // ghost of the card, under the cursor
    Rectangle {
        visible: ov.here
        x: Widgets.curX - ov.modelData.x - Widgets.grabX
        y: Widgets.curY - ov.modelData.y - Widgets.grabY
        width: ov.gw; height: ov.gh
        color: Theme.d(0.55)
        border.color: Theme.secondary; border.width: 1
        Text {
            x: 14; y: 10
            text: ov.it ? ov.it.type.toUpperCase() : ""
            color: Theme.secondary; font.family: ov.mono; font.pixelSize: 11; font.letterSpacing: 3
        }
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom; anchors.bottomMargin: 90
        visible: ov.here
        text: "RELEASE OR CLICK TO PLACE  ·  ESC CANCELS"
        color: Theme.dim; font.family: ov.mono; font.pixelSize: 12; font.letterSpacing: 3
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.ClosedHandCursor
        onPositionChanged: m => Widgets.setCursor(m.x + ov.modelData.x, m.y + ov.modelData.y)
        onPressed: m => { Widgets.setCursor(m.x + ov.modelData.x, m.y + ov.modelData.y); Widgets.drop(); }
    }
    Item {
        focus: ov.here
        Keys.onEscapePressed: Widgets.cancelMove()
    }
}
