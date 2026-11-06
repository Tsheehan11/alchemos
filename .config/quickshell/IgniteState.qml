pragma Singleton
// Drives Ignite.qml on every screen: one animation at a time.
//   skin()            the new skin's transition component (Skin.component("transition"))
//   preset(p)         the ignite flare in the preset's colour, with its glyph
import QtQuick
import Quickshell

Singleton {
    id: root
    property bool playing: false
    // busy: playing, or just finished (a short tail so the last frames and the window unmapping are smooth).
    // Theme's external pushes and the lock-picture redraws wait for it.
    readonly property bool busy: playing || tail.running
    readonly property bool moving: run.running          // the motion itself (after the warm start)
    Timer { id: tail; interval: 250 }
    property string mode: ""
    property real p: 0
    property color color: Theme.primary
    property string glyph: ""
    property string title: ""
    property string sub: ""
    // 0 fps (battery saver at static, or locked): only a short tint
    readonly property bool lite: Perf.fps === 0

    function skin() {
        if (GameMode.quiet) return;
        root.mode = "skin";
        root.color = Theme.primary;
        root.title = Skin.text.transitionTitle || "";
        root.sub = Skin.text.transitionSub || "";
        root.glyph = "";
        run.duration = root.lite ? 350 : 1900;
        root.arm();
    }
    function preset(p) {
        if (GameMode.quiet || (run.running && root.mode !== "ignite")) return;   // a skin switch is showing
        root.mode = "ignite";
        root.color = p.primary;
        root.glyph = p.glyph || "";
        root.title = ""; root.sub = "";
        run.duration = root.lite ? 300 : 1000;
        root.arm();
    }

    // Warm start: map the overlay windows (p = 0 draws nothing) and let the recolour and the windows'
    // first frames land, then start the motion, so their one-off cost never shows as a stutter.
    function arm() {
        run.stop();
        root.p = 0;
        root.playing = true;
        warm.ticks = 0;
        warm.start();
    }
    FrameAnimation {
        id: warm
        property int ticks: 0
        property real spent: 0
        onRunningChanged: if (running) spent = 0
        onTriggered: {
            spent += frameTime * 1000;
            if (++ticks >= 3) { stop(); console.log("ignite warm start: " + spent.toFixed(0) + " ms before the motion"); run.start(); }
        }
    }
    NumberAnimation {
        id: run
        target: root; property: "p"; from: 0; to: 1
        easing.type: Easing.Linear
        onFinished: { root.playing = false; root.p = 0; tail.restart(); }
    }
    Connections {
        target: Skin
        function onSwitched(to) { Qt.callLater(root.skin); }    // after the new skin's colours are in
    }
    Connections {
        target: Theme
        function onPresetApplied(p) { root.preset(p); }
    }
}
