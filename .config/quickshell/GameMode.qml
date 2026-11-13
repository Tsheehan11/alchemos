// Combat mode (gaming mode). ~/.local/bin/alchemos-game (daemon started from
// hypr/alchemos/autostart.lua) does the switching: it spots game windows, turns Hyprland
// effects / the power profile / notifications over and puts them back after.
// The HUD just follows its state file:
//   • quiet: ambient effects + the visualizer stop, panels hide on the game screen
//     and go lightweight on the others (Perf),
//     bar stats + clock refresh slowly (SysStats, Bar)
//   • Orrin pauses its wake word (orrin.py reads the same state file)
//   • "COMBAT MODE ENGAGED / DISENGAGED" toast + sound (GameToast)
// Options are the game* settings in Theme (Settings → System → Combat mode).
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property bool active: false
    property var owns: []                 // what the daemon took over: hypr | power | notify
    property var games: []                // window classes that triggered it
    property bool manual: false
    property real since: 0                // unix seconds it engaged
    readonly property bool quiet: active && Theme.cfg.gameHud
    readonly property bool batteryWarn: active && owns.indexOf("power") >= 0 && PowerMode.onBattery

    function toggle() { Quickshell.execDetached(["alchemos-game", "toggle"]); }
    function refresh() { file.reload(); }

    // Toast
    property bool showing: false
    property bool loaded: false
    readonly property string soundDir: Quickshell.env("HOME") + "/.config/quickshell/sounds/"
    Timer { id: hide; interval: 2600; onTriggered: root.showing = false }

    FileView {
        id: file
        path: (Quickshell.env("XDG_RUNTIME_DIR") || "/run/user/1000") + "/alchemos-game/state.json"
        blockLoading: true                // known before PowerMode / Orrin act at startup
        watchChanges: true
        onFileChanged: reload()
        onLoaded: root.read(text())
        onLoadFailed: root.read("{}")
    }

    function read(t) {
        let s = {};
        try { s = JSON.parse(t); } catch (e) {}
        root.owns = s.owns || [];
        root.games = s.games || [];
        root.manual = s.manual === true;
        root.since = Number(s.since) || 0;
        const a = !!s.active;
        if (a !== root.active) {
            root.active = a;
            // No toast for the state we find on HUD start
            if (root.loaded) {
                root.showing = true;
                hide.restart();
                Quickshell.execDetached(["pw-play", root.soundDir + (a ? "combat-on.wav" : "combat-off.wav")]);
            }
        }
        root.loaded = true;
    }
}
