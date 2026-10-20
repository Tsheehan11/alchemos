// Row of color swatches. Emits picked("#rrggbb").
import QtQuick

Row {
    id: sw
    property string selected: ""
    signal picked(string color)
    spacing: 10

    readonly property var colors: [
        "#4fd8ff", "#7fe0ff", "#d6f1ff", "#6fa8ff", "#b48cff", "#ff6bd6",
        "#ff5a4d", "#ff6b8a", "#ffb347", "#ffd24d", "#d4ff4d", "#4dff88"
    ]

    Repeater {
        model: sw.colors
        delegate: Rectangle {
            required property var modelData
            readonly property bool on: sw.selected.toLowerCase() === modelData
            width: 30; height: 30; radius: 15
            color: modelData
            border.color: on ? "#ffffff" : Qt.rgba(1, 1, 1, 0.15)
            border.width: on ? 3 : 1
            scale: ma.containsMouse ? 1.12 : 1
            Behavior on scale { NumberAnimation { duration: 100 } }
            MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: sw.picked(modelData) }
        }
    }
}
