// A reading in the bar: "CPU 34%". With the skin's icon for it (Style.icons): the icon, the label in
// the label face and the value in the numeric face (a fixed-width box: NumText); without, one Text in
// the body face exactly as the bar always drew it.
import QtQuick

Item {
    id: st
    property string icon
    property string label
    property string value
    property color color: Theme.dim
    property bool showLabel: true          // with an icon: also the label (the icon may say it alone)
    property real level: 1
    property bool charging: false
    readonly property bool iconic: Style.hasIcon(icon)
    implicitWidth: iconic ? row.implicitWidth : plain.implicitWidth
    implicitHeight: iconic ? row.implicitHeight : plain.implicitHeight

    Text {
        id: plain
        visible: !st.iconic
        text: st.label + " " + st.value
        color: st.color
        font.family: Style.fonts.body; font.pixelSize: 12; font.letterSpacing: 1
    }
    Row {
        id: row
        visible: st.iconic
        anchors.verticalCenter: parent.verticalCenter
        spacing: 5
        SkinIcon { anchors.verticalCenter: parent.verticalCenter; name: st.icon; color: st.color; size: 14; level: st.level; charging: st.charging }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            visible: st.showLabel
            text: st.label; color: st.color
            font.family: Style.fonts.label; font.pixelSize: 11; font.letterSpacing: 1
        }
        NumText {
            anchors.verticalCenter: parent.verticalCenter
            text: st.value; color: st.color
            font.family: Style.fonts.numeric; font.pixelSize: 13
        }
    }
}
