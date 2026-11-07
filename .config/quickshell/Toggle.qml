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
        Text { text: tg.label; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 14 }
        Text {
            visible: tg.hint !== ""
            text: tg.hint; width: parent.width; elide: Text.ElideRight
            color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11
        }
    }

    // engraved: a metal stud in a slot cut into the plate
    Rectangle {
        visible: Style.engraved
        anchors.right: parent.right; anchors.rightMargin: 2
        anchors.verticalCenter: parent.verticalCenter
        width: 46; height: 16; radius: 8
        color: tg.checked ? Theme.p(0.24) : Qt.rgba(0, 0, 0, 0.45)
        border.color: tg.checked ? Theme.p(0.75) : Theme.p(0.28)
        Behavior on color { ColorAnimation { duration: 150 } }
        Rectangle { x: 3; y: 2; width: parent.width - 6; height: 1; radius: 1; color: Qt.rgba(0, 0, 0, 0.6) }
        MetalStud {
            width: 20; height: 20; anchors.verticalCenter: parent.verticalCenter
            x: tg.checked ? parent.width - width + 2 : -2
            metal: tg.checked ? Theme.primary : Theme.faint
            Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        }
    }
    Rectangle {
        id: sw
        visible: !Style.engraved
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
