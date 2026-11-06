// Settings → Audio: output + input device, volumes, per-app volume.
import QtQuick
import Quickshell

Column {
    id: ap
    spacing: 14
    readonly property string mono: Style.mono

    component DeviceRow: Rectangle {
        id: row
        property var node
        property bool current: false
        signal picked()
        width: ap.width; height: 40
        color: current ? Theme.p(0.16) : (ma.containsMouse ? Theme.p(0.08) : "transparent")
        border.color: current ? Theme.p(0.7) : Theme.p(0.18)
        Text {
            anchors.left: parent.left; anchors.leftMargin: 12
            anchors.right: tag.left; anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight
            text: (row.current ? "◉  " : "○  ") + Audio.label(row.node)
            color: row.current ? Theme.text : Theme.textSoft
            font.family: Style.mono; font.pixelSize: 13
        }
        Text {
            id: tag
            anchors.right: parent.right; anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            text: row.current ? "IN USE" : ""
            color: Theme.secondary; font.family: Style.mono; font.pixelSize: 10; font.letterSpacing: 2
        }
        MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: row.picked() }
    }

    // ── Output ──
    Text { text: "OUTPUT"; color: Theme.dim; font.family: ap.mono; font.pixelSize: 11; font.letterSpacing: 3 }
    Repeater {
        model: Audio.outputs
        delegate: DeviceRow {
            required property var modelData
            node: modelData
            current: Audio.sink === modelData
            onPicked: Audio.setOutput(modelData)
        }
    }
    Slider {
        width: parent.width
        label: Audio.sink && Audio.sink.audio && Audio.sink.audio.muted ? "VOLUME (MUTED)" : "VOLUME"
        value: Audio.sink && Audio.sink.audio ? Audio.sink.audio.volume : 0
        onMoved: v => { if (Audio.sink && Audio.sink.audio) Audio.sink.audio.volume = v; }
    }
    Toggle {
        width: parent.width
        label: "Mute output"
        checked: Audio.sink && Audio.sink.audio ? Audio.sink.audio.muted : false
        onToggled: if (Audio.sink && Audio.sink.audio) Audio.sink.audio.muted = !Audio.sink.audio.muted
    }

    // ── Input ──
    Text { text: "MICROPHONE"; color: Theme.dim; font.family: ap.mono; font.pixelSize: 11; font.letterSpacing: 3; topPadding: 8 }
    Text { visible: Audio.inputs.length === 0; text: "No microphones found"; color: Theme.faint; font.family: ap.mono; font.pixelSize: 12 }
    Repeater {
        model: Audio.inputs
        delegate: DeviceRow {
            required property var modelData
            node: modelData
            current: Audio.source === modelData
            onPicked: Audio.setInput(modelData)
        }
    }
    Slider {
        width: parent.width
        visible: Audio.source !== null
        label: Audio.source && Audio.source.audio && Audio.source.audio.muted ? "MIC LEVEL (MUTED)" : "MIC LEVEL"
        value: Audio.source && Audio.source.audio ? Audio.source.audio.volume : 0
        onMoved: v => { if (Audio.source && Audio.source.audio) Audio.source.audio.volume = v; }
    }
    Toggle {
        width: parent.width
        visible: Audio.source !== null
        label: "Mute microphone"
        hint: JarvisState.callOf("jarvis") + " can't hear you while muted"
        checked: Audio.source && Audio.source.audio ? Audio.source.audio.muted : false
        onToggled: if (Audio.source && Audio.source.audio) Audio.source.audio.muted = !Audio.source.audio.muted
    }

    // ── Apps ──
    Text { text: "APPS"; color: Theme.dim; font.family: ap.mono; font.pixelSize: 11; font.letterSpacing: 3; topPadding: 8 }
    Text { visible: Audio.apps.length === 0; text: "Nothing is playing sound right now"; color: Theme.faint; font.family: ap.mono; font.pixelSize: 12 }
    Repeater {
        model: Audio.apps
        delegate: Slider {
            required property var modelData
            width: ap.width
            label: Audio.appLabel(modelData).toUpperCase()
            value: modelData.audio ? modelData.audio.volume : 0
            onMoved: v => { if (modelData.audio) modelData.audio.volume = v; }
        }
    }
}
