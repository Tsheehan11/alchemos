// Hologram panel frame: tinted fill, corner brackets, title strip.
// Put content inside it; it's laid out in the area under the title.
import QtQuick

Item {
    id: f
    property string title: ""
    property string detail: ""
    property real fill: Theme.panelAlpha    // background alpha; ambient desktop panels pass their own
    default property alias content: body.data

    readonly property color cyan: Theme.primary
    readonly property string mono: "JetBrainsMono Nerd Font"

    Rectangle {
        anchors.fill: parent
        color: Theme.d(f.fill)
        border.color: Theme.p(0.22)
        border.width: 1
    }

    Repeater {
        model: 4
        delegate: Item {
            required property int index
            width: 14; height: 14
            x: index % 2 === 0 ? -3 : f.width - 11
            y: index < 2 ? -3 : f.height - 11
            Rectangle { width: 14; height: 2; color: f.cyan; y: index < 2 ? 0 : 12 }
            Rectangle { width: 2; height: 14; color: f.cyan; x: index % 2 === 0 ? 0 : 12 }
        }
    }

    Text {
        x: 14; y: 10
        text: f.title
        color: f.cyan
        font.family: f.mono; font.pixelSize: 11; font.letterSpacing: 3
    }
    Text {
        anchors.right: parent.right; anchors.rightMargin: 14
        y: 10
        text: f.detail
        color: Theme.dim
        font.family: f.mono; font.pixelSize: 11
    }

    Item {
        id: body
        anchors.fill: parent
        anchors.topMargin: 34
        anchors.leftMargin: 14; anchors.rightMargin: 14; anchors.bottomMargin: 12
    }
}
