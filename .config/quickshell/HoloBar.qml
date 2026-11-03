// A gauge as light, not a box: faint tick rail, a thin glowing fill and a bright head.
import QtQuick

Item {
    id: b
    property real value: 0                 // 0..1
    property color color: Theme.primary
    property bool animated: false
    property int ticks: 10
    implicitHeight: 6
    readonly property real v: Math.max(0, Math.min(1, value))
    property real shown: v
    Behavior on shown { enabled: b.animated; NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }

    Rectangle { y: b.height / 2; width: b.width; height: 1; color: Theme.p(0.16) }
    Repeater {
        model: b.ticks + 1
        delegate: Rectangle {
            required property int index
            x: Math.round(index * (b.width - 1) / b.ticks); y: b.height / 2 - (index % 5 === 0 ? 2 : 1)
            width: 1; height: index % 5 === 0 ? 5 : 3
            color: Theme.p(0.22)
        }
    }
    Rectangle {    // glow
        y: b.height / 2 - 2.5; height: 6; width: b.width * b.shown
        gradient: Gradient {
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 0.5; color: Qt.rgba(b.color.r, b.color.g, b.color.b, 0.22) }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }
    Rectangle {    // fill, fading in from the left
        y: b.height / 2 - 0.5; height: 2; width: b.width * b.shown
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Qt.rgba(b.color.r, b.color.g, b.color.b, 0.25) }
            GradientStop { position: 1.0; color: b.color }
        }
    }
    Rectangle {    // head
        visible: b.shown > 0.005
        x: b.width * b.shown - 2; y: b.height / 2 - 2.5
        width: 4; height: 6; radius: 1
        color: Qt.lighter(b.color, 1.5)
    }
}
