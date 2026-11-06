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
            visible: !Style.engraved
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width; height: 4
            color: Theme.p(0.14)
            Rectangle { width: parent.width * Math.max(0, Math.min(1, sl.value)); height: parent.height; color: sl.accent }
        }
        // engraved: a graduated slot, a metal fill and a stud
        Item {
            visible: Style.engraved
            anchors.fill: parent
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width; height: 6; radius: 3
                color: Qt.rgba(0, 0, 0, 0.45); border.color: Theme.p(0.25)
                Rectangle { x: 2; y: 1; width: parent.width - 4; height: 1; color: Qt.rgba(0, 0, 0, 0.6) }
                Rectangle {
                    x: 1; y: 1; height: parent.height - 2; radius: 2
                    width: Math.max(0, (parent.width - 2) * Math.max(0, Math.min(1, sl.value)))
                    gradient: Gradient {
                        GradientStop { position: 0; color: Theme.mix(sl.accent, "#ffffff", 0.35) }
                        GradientStop { position: 1; color: Theme.mix(sl.accent, "#000000", 0.25) }
                    }
                }
            }
            Repeater {
                model: 11
                delegate: Rectangle {
                    required property int index
                    x: Math.round(index * (sl.width - 1) / 10); y: parent.height - 3
                    width: 1; height: index % 5 === 0 ? 3 : 2
                    color: Theme.p(0.3)
                }
            }
            MetalStud {
                width: 16; height: 16; anchors.verticalCenter: parent.verticalCenter
                x: Math.max(0, Math.min(1, sl.value)) * (parent.width - width)
                metal: sl.accent
            }
        }
        Rectangle {
            visible: !Style.engraved
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
