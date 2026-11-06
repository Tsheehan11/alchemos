// Hologram slider: label, percentage, draggable bar. Emits moved(value 0..1).
import QtQuick

Column {
    id: sl
    property string label: ""
    property real value: 0
    property color accent: Theme.primary
    property string valueText: Math.round(value * 100) + "%"   // for sliders whose range isn't 0–100%
    signal moved(real v)

    spacing: 8

    Item {
        width: sl.width; height: 14
        Text { text: sl.label; color: Theme.dim; font.family: Style.mono; font.pixelSize: 11; font.letterSpacing: 2 }
        Text { anchors.right: parent.right; text: sl.valueText; color: sl.accent; font.family: Style.mono; font.pixelSize: 11 }
    }

    Item {
        width: sl.width; height: 18
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width; height: 4
            color: Theme.p(0.14)
            Rectangle { width: parent.width * Math.max(0, Math.min(1, sl.value)); height: parent.height; color: sl.accent }
        }
        Rectangle {
            width: 12; height: 18
            x: Math.max(0, Math.min(1, sl.value)) * (parent.width - width)
            color: Theme.bg
            border.color: sl.accent; border.width: 2
        }
        MouseArea {
            anchors.fill: parent
            anchors.margins: -6
            cursorShape: Qt.PointingHandCursor
            function apply(mx) { sl.moved(Math.max(0, Math.min(1, (mx - 6) / (width - 12)))); }
            onPressed: mouse => apply(mouse.x)
            onPositionChanged: mouse => { if (pressed) apply(mouse.x); }
        }
    }
}
