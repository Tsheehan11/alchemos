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
    readonly property string mono: Style.mono

    Rectangle {
        visible: !Style.engraved
        anchors.fill: parent
        color: Theme.d(f.fill)
        border.color: Theme.p(0.22)
        border.width: 1
    }
    Engraving { visible: Style.engraved; fillAlpha: f.fill }

    Repeater {
        model: Style.engraved ? 0 : 4
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
        visible: !Style.engraved
        x: 14; y: 10
        text: f.title
        color: f.cyan
        font.family: f.mono; font.pixelSize: 11; font.letterSpacing: 3
    }
    // engraved: the title in the display face with a metal rule up to the detail
    Heading {
        visible: Style.engraved
        x: 24; y: 9; height: 18
        width: f.width - 48 - (f.detail !== "" ? detail.implicitWidth + 16 : 0)
        text: f.title
        color: f.cyan
    }
    Text {
        id: detail
        anchors.right: parent.right; anchors.rightMargin: Style.engraved ? 24 : 14
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
