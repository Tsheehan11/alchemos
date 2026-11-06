pragma Singleton
// Drives Ignite.qml on every screen: one animation at a time.
//   skin(name)        the new skin's transition (Skin.transition: transmute | reactor)
//   preset(p)         the ignite flare in the preset's colour, with its glyph
import QtQuick
import Quickshell

Singleton {
    id: root
    property bool playing: false
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
        root.mode = Skin.transition;
        root.color = Theme.primary;
        root.title = Skin.text.transitionTitle || "";
        root.sub = Skin.text.transitionSub || "";
        root.glyph = "";
        run.duration = root.lite ? 350 : 1900;
        run.restart();
    }
    function preset(p) {
        if (GameMode.quiet || (run.running && root.mode !== "ignite")) return;   // a skin switch is showing
        root.mode = "ignite";
        root.color = p.primary;
        root.glyph = p.glyph || "";
        root.title = ""; root.sub = "";
        run.duration = root.lite ? 300 : 1000;
        run.restart();
    }

    NumberAnimation {
        id: run
        target: root; property: "p"; from: 0; to: 1
        easing.type: Easing.Linear
        onStarted: root.playing = true
        onFinished: { root.playing = false; root.p = 0; }
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
