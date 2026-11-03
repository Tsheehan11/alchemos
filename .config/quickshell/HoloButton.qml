// A control drawn as light: a glyph inside four corner ticks, a soft glow when hovered. No filled box.
import QtQuick

Item {
    id: hb
    property string text: ""
    property color color: Theme.primary
    property int pixelSize: 13
    property bool usable: true
    signal clicked()
    implicitWidth: 30; implicitHeight: 26
    readonly property bool hot: ma.containsMouse && hb.usable

    Rectangle {     // glow
        anchors.centerIn: parent
        width: parent.width + 6; height: parent.height + 6; radius: width / 2
        visible: hb.hot
        gradient: Gradient {
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 0.5; color: Qt.rgba(hb.color.r, hb.color.g, hb.color.b, 0.16) }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }
    Repeater {
        model: 4
        delegate: Item {
            required property int index
            width: 5; height: 5
            x: index % 2 === 0 ? 0 : hb.width - 5
            y: index < 2 ? 0 : hb.height - 5
            opacity: hb.hot ? 0.95 : 0.4
            Rectangle { width: 5; height: 1; color: hb.color; y: index < 2 ? 0 : 4 }
            Rectangle { width: 1; height: 5; color: hb.color; x: index % 2 === 0 ? 0 : 4 }
        }
    }
    Text {
        anchors.centerIn: parent
        text: hb.text
        color: hb.usable ? (hb.hot ? Qt.lighter(hb.color, 1.4) : hb.color) : Theme.faint
        font.family: "JetBrainsMono Nerd Font"; font.pixelSize: hb.pixelSize
    }
    MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; enabled: hb.usable; onClicked: hb.clicked() }
}
