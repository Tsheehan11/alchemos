// Volume / brightness pop-up state.
//   Volume: follows the default output's volume + mute, whatever changed it
//   Brightness: the brightness keys call `qs ipc call osd brightness`
//   Screen role: Super+Shift+V (Roles.cycle) shows what the focused screen shows now
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Pipewire

Singleton {
    id: root

    property string kind: "volume"     // volume | brightness | role
    property string screenName: ""     // role: the screen it was changed on
    property string text: ""           // role: "MUSIC", "AUTO · CLOCK"
    property real value: 0
    property bool muted: false
    property bool showing: false

    function show(k, v, m) {
        if (!Theme.cfg.osd) return;
        root.kind = k;
        root.value = Math.max(0, Math.min(1, v));
        root.muted = !!m;
        root.showing = true;
        hide.restart();
    }
    Timer { id: hide; interval: 1600; onTriggered: root.showing = false }
    function role(name, text) {
        if (!Theme.cfg.osd) return;
        root.kind = "role";
        root.screenName = name;
        root.text = text;
        root.showing = true;
        hide.restart();
    }

    // ── Volume ──
    readonly property var sink: Pipewire.defaultAudioSink
    PwObjectTracker { objects: root.sink ? [root.sink] : [] }
    readonly property real vol: sink && sink.audio ? sink.audio.volume : 0
    readonly property bool mute: sink && sink.audio ? sink.audio.muted : false

    // Don't pop up at login, when switching outputs, or while a panel with its own slider is open
    property bool armed: false
    Timer { running: true; interval: 3000; onTriggered: root.armed = true }
    onSinkChanged: { root.armed = false; rearm.restart(); }
    Timer { id: rearm; interval: 800; onTriggered: root.armed = true }
    function volumeChanged() {
        if (!root.armed || LauncherState.controlOpen || LauncherState.settingsOpen) return;
        root.show("volume", root.vol, root.mute);
    }
    onVolChanged: volumeChanged()
    onMuteChanged: volumeChanged()

    // ── Brightness ──
    function brightness() { bright.running = true; }
    Process {
        id: bright
        command: ["brightnessctl", "-m"]
        stdout: StdioCollector {
            onStreamFinished: {
                // intel_backlight,backlight,12000,50%,24000
                const f = text.trim().split("\n")[0].split(",");
                if (f.length >= 5) root.show("brightness", Number(f[2]) / Number(f[4]), false);
            }
        }
    }
}
