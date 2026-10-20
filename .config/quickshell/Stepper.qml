// Label + [−] value [+] control.
import QtQuick

Item {
    id: sp
    property string label: ""
    property string hint: ""
    property string valueText: ""
    signal dec()
    signal inc()

    implicitHeight: hint === "" ? 40 : 52

    Column {
        anchors.left: parent.left
        anchors.right: ctl.left; anchors.rightMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 3
        Text { width: parent.width; elide: Text.ElideRight; text: sp.label; color: Theme.text; font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 14 }
        Text { width: parent.width; elide: Text.ElideRight; visible: sp.hint !== ""; text: sp.hint; color: Theme.dim; font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 11 }
    }
    Row {
        id: ctl
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8
        SmallButton { text: "−"; onClicked: sp.dec() }
        Text {
            // Grows to fit long values like "2560 × 1440 @ 144 Hz"
            width: Math.max(90, implicitWidth + 16); anchors.verticalCenter: parent.verticalCenter
            horizontalAlignment: Text.AlignHCenter
            text: sp.valueText
            color: Theme.primary
            font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 13; font.letterSpacing: 2
        }
        SmallButton { text: "+"; onClicked: sp.inc() }
    }
}
