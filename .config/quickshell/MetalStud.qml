// A small metal stud (engraved toggles and sliders): a domed disc in `metal`, its rim in shadow, a rivet dimple.
import QtQuick

Rectangle {
    id: m
    property color metal: Theme.primary
    width: 18; height: 18; radius: width / 2
    border.color: Qt.rgba(0, 0, 0, 0.6)
    gradient: Gradient {
        GradientStop { position: 0; color: Theme.mix(m.metal, "#ffffff", 0.45) }
        GradientStop { position: 0.55; color: m.metal }
        GradientStop { position: 1; color: Theme.mix(m.metal, "#000000", 0.45) }
    }
    Rectangle { anchors.centerIn: parent; width: 5; height: 5; radius: 3; color: Qt.rgba(0, 0, 0, 0.3) }
}
