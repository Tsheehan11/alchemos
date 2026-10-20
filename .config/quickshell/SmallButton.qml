// Compact hologram button.
import QtQuick

Rectangle {
    id: b
    property string text: ""
    property bool active: false
    signal clicked()

    implicitWidth: label.implicitWidth + 28
    implicitHeight: 32
    width: implicitWidth; height: implicitHeight
    color: active ? Theme.s(0.2) : (ma.containsMouse ? Theme.p(0.16) : Theme.d(0.8))
    border.color: active ? Theme.secondary : (ma.containsMouse ? Theme.primary : Theme.p(0.35))

    Text {
        id: label
        anchors.centerIn: parent
        text: b.text
        color: b.active ? Theme.text : Theme.textSoft
        font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 11; font.letterSpacing: 2
    }
    MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: b.clicked() }
}
