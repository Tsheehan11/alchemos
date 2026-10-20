// STARK OS theme + preferences. Everything here is saved to settings.json
// (next to this file) and edited from the Settings screen (Super + ,).
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root

    // ── Saved preferences ──────────────────────
    property alias cfg: adapter

    FileView {
        id: file
        path: Quickshell.env("HOME") + "/.config/quickshell/settings.json"
        watchChanges: true
        onFileChanged: reload()
        onAdapterUpdated: writeAdapter()
        onLoadFailed: error => writeAdapter()   // first run: create the file with defaults

        JsonAdapter {
            id: adapter
            property string preset: "STARK"
            property string primary: "#4fd8ff"
            property string secondary: "#ffb347"
            property string background: "#05090f"
            property bool animatedBg: true
            property bool showGrid: true
            property bool showReactor: true
            property bool showDiag: true
            property bool showMedia: true
            property bool clock24: true
            property real reactorScale: 1.45
            property bool unlockSound: true
            property string greetName: "TREVOR"
            property int effectsFps: 24             // 0 = static, 12 eco, 24 balanced, 40 smooth
            property bool pauseBehindWindows: true
            property bool autoSaver: true            // battery saver when unplugged
            property int batteryFps: 0               // effects frame rate on battery (0 = static)
            property bool saverNoBlur: true
            property bool saverLowRefresh: true      // laptop screen 60 → 48 Hz on battery
            property bool saverStopJarvis: false
            property int idleDim: 3                  // minutes (0 = never)
            property int idleLock: 5
            property int idleScreenOff: 10
            property int idleSleep: 20
        }
    }

    // ── Presets ─────────────────────────────────
    readonly property var presets: [
        { name: "STARK",     primary: "#4fd8ff", secondary: "#ffb347", background: "#05090f" },
        { name: "MARK III",  primary: "#ff5a4d", secondary: "#ffd24d", background: "#0c0505" },
        { name: "VIBRANIUM", primary: "#b48cff", secondary: "#7fe0ff", background: "#08050f" },
        { name: "MATRIX",    primary: "#4dff88", secondary: "#d4ff4d", background: "#030a05" },
        { name: "ARCTIC",    primary: "#d6f1ff", secondary: "#6fa8ff", background: "#05080f" },
        { name: "SOLAR",     primary: "#ffb347", secondary: "#ff6b8a", background: "#0c0705" }
    ]
    function applyPreset(p) {
        adapter.preset = p.name;
        adapter.primary = p.primary;
        adapter.secondary = p.secondary;
        adapter.background = p.background;
    }

    // ── Colors ──────────────────────────────────
    readonly property color primary: adapter.primary
    readonly property color secondary: adapter.secondary
    readonly property color bg: adapter.background

    function mix(a, b, t) {
        a = Qt.darker(a, 1.0); b = Qt.darker(b, 1.0);   // turns "#rrggbb" strings into colors
        return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, 1);
    }
    readonly property color text: mix(primary, "#ffffff", 0.88)      // bright text
    readonly property color textSoft: mix(primary, "#ffffff", 0.7)   // body text
    readonly property color dim: Qt.hsla(primary.hslHue, Math.min(1, primary.hslSaturation) * 0.38, 0.68, 1)   // labels
    readonly property color faint: Qt.hsla(primary.hslHue, Math.min(1, primary.hslSaturation) * 0.25, 0.42, 1)  // hints
    readonly property color deep: mix(bg, primary, 0.09)             // panel fill

    function p(a)  { return Qt.rgba(primary.r, primary.g, primary.b, a); }
    function s(a)  { return Qt.rgba(secondary.r, secondary.g, secondary.b, a); }
    function d(a)  { return Qt.rgba(deep.r, deep.g, deep.b, a); }
    function back(a) { return Qt.rgba(bg.r, bg.g, bg.b, a); }

    // CSS-style strings for Canvas drawing
    function css(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")"; }
    function pc(a)  { return css(primary, a); }
    function sc(a)  { return css(secondary, a); }
    function lc(a)  { return css(mix(primary, "#ffffff", 0.6), a); }
    function slc(a) { return css(mix(secondary, "#ffffff", 0.5), a); }
    function hex(c) { return c.toString().replace("#", "").slice(-6); }

    // Keep Hyprland's window borders in the theme colors
    function pushToHyprland() {
        Quickshell.execDetached(["hyprctl", "keyword", "general:col.active_border",
            "rgba(" + hex(primary) + "ee) rgba(" + hex(primary) + "55) 45deg"]);
        Quickshell.execDetached(["hyprctl", "keyword", "general:col.inactive_border",
            "rgba(" + hex(primary) + "22)"]);
        Quickshell.execDetached(["hyprctl", "keyword", "decoration:shadow:color",
            "rgba(" + hex(primary) + "40)"]);
        Quickshell.execDetached(["hyprctl", "keyword", "misc:background_color",
            "rgb(" + hex(bg) + ")"]);
        // Re-color the lock screen from its template
        Quickshell.execDetached(["sh", "-c",
            "t=~/.config/hypr/hyprlock.template.conf; [ -f $t ] && sed -e 's/4fd8ff/" + hex(primary) +
            "/g' -e 's/ffb347/" + hex(secondary) + "/g' -e 's/05090f/" + hex(bg) + "/g' -e \"s#__HOME__#$HOME#g\" $t > ~/.config/hypr/hyprlock.conf"]);
    }
    onPrimaryChanged: hyprSync.restart()
    onBgChanged: hyprSync.restart()
    onSecondaryChanged: hyprSync.restart()
    Timer { id: hyprSync; interval: 300; onTriggered: root.pushToHyprland() }
    Component.onCompleted: hyprSync.restart()
    // `hyprctl reload` resets border colors → push them again
    Connections {
        target: Hyprland
        function onRawEvent(event) { if (event.name === "configreloaded") hyprSync.restart(); }
    }
}
