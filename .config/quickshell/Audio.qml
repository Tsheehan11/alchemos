// Audio devices for Settings → Audio (outputs, microphones, per-app streams) and Settings → ORRIN (INPUT DEVICE).
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Services.Pipewire

Singleton {
    id: root

    readonly property var nodes: Pipewire.nodes.values
    readonly property var outputs: nodes.filter(n => n.audio && n.isSink && !n.isStream)
    readonly property var inputs: nodes.filter(n => n.audio && !n.isSink && !n.isStream)
    readonly property var apps: nodes.filter(n => n.audio && n.isSink && n.isStream)
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var source: Pipewire.defaultAudioSource

    PwObjectTracker { objects: root.outputs.concat(root.inputs).concat(root.apps) }

    function label(n) {
        if (!n) return "—";
        return n.description || n.nickname || n.name;
    }
    function appLabel(n) {
        const p = n.properties || {};
        return p["application.name"] || n.description || n.name || "App";
    }
    // A pick here is his explicit choice: `orrin audio` (~/.config/orrin/mcp/audio_devices.py, the same
    // code as Orrin's set_audio_output / set_audio_input) also moves what's playing / recording and
    // records the choice, so Orrin's voice follows it instead of the room speaker until a device comes or goes.
    readonly property string orrinBin: Quickshell.env("HOME") + "/.local/bin/orrin"
    function setOutput(n) {
        if (!n) return;
        Pipewire.preferredDefaultAudioSink = n;          // the UI updates at once
        Quickshell.execDetached([root.orrinBin, "audio", "output", n.name]);
    }
    function setInput(n) {
        if (!n) return;
        Pipewire.preferredDefaultAudioSource = n;
        Quickshell.execDetached([root.orrinBin, "audio", "input", n.name]);
    }
}
