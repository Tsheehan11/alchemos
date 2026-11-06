// A section divider: a hairline (base), or hairlines fading into ◆ glyph ◆ (Style.divider / glyph).
import QtQuick

Item {
    id: d
    property string glyph: Style.divider
    property color color: Theme.primary
    implicitHeight: d.glyph !== "" ? 14 : 1
    Rectangle {
        visible: d.glyph === ""
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width; height: 1; color: Qt.rgba(d.color.r, d.color.g, d.color.b, 0.22)
    }
    Row {
        id: mid
        visible: d.glyph !== ""
        anchors.centerIn: parent; spacing: 5
        Rectangle { width: 4; height: 4; rotation: 45; color: Qt.rgba(d.color.r, d.color.g, d.color.b, 0.6); anchors.verticalCenter: parent.verticalCenter }
        SigilText { text: d.glyph; color: Qt.rgba(d.color.r, d.color.g, d.color.b, 0.85); font.pixelSize: 11 }
        Rectangle { width: 4; height: 4; rotation: 45; color: Qt.rgba(d.color.r, d.color.g, d.color.b, 0.6); anchors.verticalCenter: parent.verticalCenter }
    }
    Rectangle {
        visible: d.glyph !== ""
        anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.right: mid.left; anchors.rightMargin: 7; height: 1
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.rgba(d.color.r, d.color.g, d.color.b, 0) } GradientStop { position: 1; color: Qt.rgba(d.color.r, d.color.g, d.color.b, 0.45) } }
    }
    Rectangle {
        visible: d.glyph !== ""
        anchors.verticalCenter: parent.verticalCenter; anchors.left: mid.right; anchors.leftMargin: 7; anchors.right: parent.right; height: 1
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.rgba(d.color.r, d.color.g, d.color.b, 0.45) } GradientStop { position: 1; color: Qt.rgba(d.color.r, d.color.g, d.color.b, 0) } }
    }
}
