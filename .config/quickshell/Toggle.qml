// Hologram on/off switch with a label. Emits toggled() when clicked.
import QtQuick

Item {
    id: tg
    property string label: ""
    property string hint: ""
    property bool checked: false
    signal toggled()

    implicitHeight: hint === "" ? 40 : 52
    implicitWidth: 300

    Column {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: sw.left
        anchors.rightMargin: 16
        spacing: 3
        Text { text: tg.label; color: Theme.text; font.family: Style.mono; font.pixelSize: 14 }
        Text {
            visible: tg.hint !== ""
            text: tg.hint; width: parent.width; elide: Text.ElideRight
            color: Theme.dim; font.family: Style.mono; font.pixelSize: 11
        }
    }

    Rectangle {
        id: sw
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 48; height: 24; radius: 12
        color: tg.checked ? Theme.p(0.3) : Theme.d(0.9)
        border.color: tg.checked ? Theme.primary : Theme.p(0.35)
        Behavior on color { ColorAnimation { duration: 150 } }
        Rectangle {
            width: 16; height: 16; radius: 8
            y: 4
            x: tg.checked ? parent.width - width - 4 : 4
            color: tg.checked ? Theme.text : Theme.dim
            Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: tg.toggled()
    }
}
