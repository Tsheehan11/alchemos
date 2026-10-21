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
            property bool jarvisDocked: true          // Jarvis listens when docked
            property bool jarvisLaptop: false         // …and when it's just the laptop
            property string displayLayout: "extend"  // extend | mirror | external | laptop
            property bool hideHudBehindWindows: true  // clock / panels hide when windows are open
            property bool osd: true                   // volume / brightness pop-up
            property int idleDim: 3                  // minutes (0 = never)
            property int idleLock: 5
            property int idleScreenOff: 10
            property int idleSleep: 20
            property bool terminalGlass: false         // kitty background_opacity 0.85 instead of solid
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
    // ── Kitty ───────────────────────────────────
    // Writes ~/.config/kitty/stark-theme.conf (included from kitty.conf) and
    // SIGUSR1s every kitty so open windows recolor live.
    function luma(c) {
        const f = v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
    }
    function contrast(a, b) {
        const x = luma(a), y = luma(b);
        return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
    }
    // Lighten an HSL color until it reads at `need`:1 against `under`
    function readable(hue, sat, light, need, under) {
        let c = Qt.hsla(((hue % 360) + 360) % 360 / 360, sat, light, 1);
        while (contrast(c, under) < need && light < 0.95) {
            light += 0.01;
            c = Qt.hsla(((hue % 360) + 360) % 360 / 360, sat, light, 1);
        }
        return c;
    }
    function kittyConf() {
        const hue = Math.max(0, primary.hslHue) * 360;
        const sat = Math.min(1, primary.hslSaturation);
        const back = mix(bg, primary, 0.06);
        const pal = [];
        pal[0] = Qt.hsla(hue / 360, sat * 0.35, 0.16, 1);
        pal[7] = Qt.hsla(hue / 360, sat * 0.2, 0.78, 1);
        pal[8] = readable(hue, sat * 0.18, 0.45, 4.0, back);          // fish autosuggestions, comments
        pal[15] = Qt.hsla(hue / 360, sat * 0.3, 0.93, 1);
        // red green yellow blue magenta cyan — nudged ≤8° toward the theme hue so they stay distinct
        [355, 125, 48, 215, 300, 182].forEach((h, i) => {
            const d = ((hue - h + 540) % 360) - 180;
            const h2 = h + Math.max(-8, Math.min(8, d * 0.15));
            pal[i + 1] = readable(h2, 0.68, 0.58, 5.0, back);
            pal[i + 9] = readable(h2, 0.85, 0.72, 7.5, back);
        });
        const c = x => "#" + hex(x);
        const lines = [
            "# Generated by quickshell/Theme.qml — edits are overwritten on theme change",
            "foreground " + c(mix(primary, "#ffffff", 0.85)),
            "background " + c(back),
            "background_opacity " + (adapter.terminalGlass ? "0.85" : "1.0"),
            "selection_foreground " + c(back),
            "selection_background " + c(primary),
            "cursor " + c(primary),
            "cursor_text_color " + c(back),
            "url_color " + c(secondary),
            "active_border_color " + c(primary),
            "inactive_border_color " + c(mix(back, primary, 0.3)),
            "tab_bar_background " + c(back),
            "active_tab_foreground " + c(back),
            "active_tab_background " + c(primary),
            "inactive_tab_foreground " + c(dim),
            "inactive_tab_background " + c(mix(back, primary, 0.15))
        ];
        for (let i = 0; i < 16; i++) lines.push("color" + i + " " + c(pal[i]));
        return lines.join("\n") + "\n";
    }
    function pushToKitty() {
        Quickshell.execDetached(["sh", "-c",
            "d=~/.config/kitty; mkdir -p $d && printf '%s' \"$1\" > $d/.stark-theme.tmp && mv $d/.stark-theme.tmp $d/stark-theme.conf && pkill -USR1 -x kitty",
            "sh", kittyConf()]);
    }

    // ── Ambient lights (Govee strip) ────────────
    function pushToGovee() {
        Quickshell.execDetached(["stark-govee", "theme", hex(primary), hex(secondary)]);
    }

    onPrimaryChanged: { hyprSync.restart(); kittySync.restart(); goveeSync.restart(); }
    onBgChanged: { hyprSync.restart(); kittySync.restart(); }
    onSecondaryChanged: { hyprSync.restart(); kittySync.restart(); goveeSync.restart(); }
    Connections {
        target: adapter
        function onTerminalGlassChanged() { kittySync.restart(); }
    }
    Timer { id: hyprSync; interval: 300; onTriggered: root.pushToHyprland() }
    Timer { id: kittySync; interval: 300; onTriggered: root.pushToKitty() }
    Timer { id: goveeSync; interval: 300; onTriggered: root.pushToGovee() }
    Component.onCompleted: { hyprSync.restart(); kittySync.restart(); goveeSync.restart(); }
    // `hyprctl reload` resets border colors → push them again
    Connections {
        target: Hyprland
        function onRawEvent(event) { if (event.name === "configreloaded") hyprSync.restart(); }
    }
}
