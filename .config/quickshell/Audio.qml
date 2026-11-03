// Audio devices for Settings → Audio (outputs, microphones, per-app streams) and Settings → JARVIS (INPUT DEVICE).
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
    // A pick here is his explicit choice: `jarvis audio` (~/.config/jarvis/mcp/audio_devices.py, the same
    // code as Jarvis's set_audio_output / set_audio_input) also moves what's playing / recording and
    // records the choice, so Jarvis's voice follows it instead of the room speaker until a device comes or goes.
    readonly property string jarvisBin: Quickshell.env("HOME") + "/.local/bin/jarvis"
    function setOutput(n) {
        if (!n) return;
        Pipewire.preferredDefaultAudioSink = n;          // the UI updates at once
        Quickshell.execDetached([root.jarvisBin, "audio", "output", n.name]);
    }
    function setInput(n) {
        if (!n) return;
        Pipewire.preferredDefaultAudioSource = n;
        Quickshell.execDetached([root.jarvisBin, "audio", "input", n.name]);
    }
}
