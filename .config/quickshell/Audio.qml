// Audio devices for Settings → Audio (outputs, microphones, per-app streams).
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
    function setOutput(n) { if (n) Pipewire.preferredDefaultAudioSink = n; }
    function setInput(n) { if (n) Pipewire.preferredDefaultAudioSource = n; }
}
