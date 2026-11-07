// skincheck: what a PanelWindow becomes in the window renders (pin.py swaps it in), an Item the gallery can grab
import QtQuick

Item {
    id: w
    property var screen
    property color color: "transparent"
    property var mask
    property int exclusiveZone: 0
    readonly property Item contentItem: w
    Rectangle { anchors.fill: parent; color: w.color; z: -1000 }
}
