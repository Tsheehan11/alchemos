// STARK OS theme + preferences. Everything here is saved to settings.json
// (next to this file) and edited from the Settings screen (Super + ,).
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import "Hypr.js" as Hypr

Singleton {
    id: root

    // ── Saved preferences ──────────────────────
    property alias cfg: adapter

    FileView {
        id: file
        path: Quickshell.env("HOME") + "/.config/quickshell/settings.json"
        watchChanges: true
        onFileChanged: reload()
        // One write per batch of changes: applying a preset sets several fields, and writing
        // after each one let the change watcher reload a half-written file over the rest.
        onAdapterUpdated: saveTimer.restart()
        onLoaded: root.loaded = true
        onLoadFailed: error => { writeAdapter(); root.loaded = true; }   // first run: create the file with defaults

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
            // Read by ~/.config/jarvis (core/config.py); edited in Settings → JARVIS
            property string jarvisModel: "auto"       // auto (haiku, sonnet when needed) | haiku | sonnet | opus
            property string jarvisVoice: "bm_george"  // Kokoro voice (bm_*), or piper model[:speaker] in ~/.local/share/jarvis/voices
            property real jarvisSpeed: 1.0            // speech rate
            property int jarvisVoiceVolume: 60        // VOICE VOLUME 0–100 %: Jarvis's voice + chime, a gain after its effects; other audio untouched
            property int jarvisSpeakerVolume: -1      // own level on the Bluetooth speaker, 0–100 %; -1 = same as VOICE VOLUME
            property real jarvisPitch: 0.0            // semitones, on top of the effect preset
            property string jarvisEffect: "AUTO"      // AUTO = SUIT on headphones, HOLOGRAM on speakers; presets in ~/.config/jarvis/effects.json
            property bool jarvisSpeak: true           // spoken replies (the toast shows them either way)
            property bool jarvisDuck: true            // lower the music while Jarvis talks
            property int jarvisFollowup: 8            // seconds to listen for a follow-up without the wake word (0 = off)
            property string jarvisSpeaker: ""         // Bluetooth MAC: speaker for Jarvis when not on headphones ("" = off)
            property string jarvisMic: ""             // PipeWire source node.name for the wake word ("" = default input)
            property string jarvisPlace: "Waterloo, Ontario"   // home town for "what's the weather"
            property bool jarvisAutoAddAssignments: false   // LEARN sync writes to the "STARK – Assignments" calendar without asking (that calendar only)
            property bool jarvisAutoUpdateTracker: false    // grade notices / new LEARN work / moved deadlines write to the SE tracker sheet without asking
            property string jarvisAssignmentsAccount: "google"   // where that calendar lives: google | microsoft
            property string jarvisDecisions: "local"   // local = fast path → local router → Claude | claude = fast path → Claude
            property real jarvisRouterThreshold: 0.70  // similarity the local router needs to act (~/.config/jarvis/tools/eval_router.py)
            property int jarvisWatchInterval: 10      // seconds between a watcher's captures (~/.config/jarvis/core/watch.py)
            property var jarvisCaptureBlocklist: ["bank", "banking", "rbc royal", "td canada", "scotiabank", "cibc", "bmo", "tangerine", "wealthsimple", "paypal", "interac", "password", "1password", "bitwarden", "keepass", "lastpass", "proton pass", "authenticator", "2fa", "credit card"]   // titles / apps Jarvis never reads or watches (lock screen + password prompts always refused)
            property string displayLayout: "extend"  // extend | mirror | external | laptop
            property var screenRoles: ({})            // monitor description → clock | stats | music | none (missing = auto; Roles.qml)
            property bool hideHudBehindWindows: true  // clock / panels hide when windows are open
            property bool osd: true                   // volume / brightness pop-up
            property bool showWidgets: true           // desktop widgets (Widgets.qml; the list itself is in widgets.json)
            property int idleDim: 3                  // minutes (0 = never)
            property int idleLock: 5
            property int idleScreenOff: 10
            property int idleSleep: 20
            property bool terminalGlass: false         // kitty background_opacity 0.85 instead of solid
            property int cursorSize: 24                // STARK-OS cursor: 24 | 32 | 48
            property bool cursorAnimated: true         // spinning arc-reactor busy cursor (static frame when off)
            property int cursorOpacity: 45             // cursor body fill, % (20–90)
            property real panelOpacity: 0.85           // HUD panel backgrounds: settings, control center, search (0.5–1)
            property var customPresets: []             // user presets: [{ name, primary, secondary, background }]
            // Combat mode (GameMode.qml); the stark-game daemon reads these too
            property bool gameAuto: true                // engage when a game window opens / gamemode starts
            property bool gameHypr: true                // blur, shadows, animations off + tearing for the game
            property bool gameNoVfr: false              // also debug:vfr off (Hyprland advises against it)
            property bool gamePower: true               // performance profile on AC, balanced on battery
            property bool gameHud: true                 // HUD effects / panels pause, stats refresh slowly
            property bool gameKeepPanels: true          // …but panels stay (lightweight) on screens without the game
            property bool gameKeepMedia: true           //   audio deck: controls work, visualizer frozen, cava off
            property bool gameKeepDiag: true            //   diagnostics: stats every 2.5 s, no animations
            property bool gameTelemetry: true           //   …as the expanded COMBAT TELEMETRY layout
            property bool gameTelemetryBeside: true     //   …which stays up with windows open, tiling them beside it
            property bool gameJarvis: true              // pause Jarvis (frees the mic)
            property bool gameNotify: true              // do-not-disturb on the notification daemon
            property var launcherApps: []               // radial launcher (LauncherApps.qml); seeded on first run
            property string vpnProvider: "proton"       // VPN the tile / Settings act on (VPN.qml, stark-vpn providers.json)
        }
    }
    property bool loaded: false   // settings.json has been read at least once
    Timer { id: saveTimer; interval: 50; onTriggered: file.writeAdapter() }

    // ── Presets ─────────────────────────────────
    readonly property var presets: [
        { name: "STARK",     primary: "#4fd8ff", secondary: "#ffb347", background: "#05090f" },
        { name: "MARK III",  primary: "#ff5a4d", secondary: "#ffd24d", background: "#0c0505" },
        { name: "VIBRANIUM", primary: "#b48cff", secondary: "#7fe0ff", background: "#08050f" },
        { name: "MATRIX",    primary: "#4dff88", secondary: "#d4ff4d", background: "#030a05" },
        { name: "ARCTIC",    primary: "#d6f1ff", secondary: "#6fa8ff", background: "#05080f" },
        { name: "SOLAR",     primary: "#ffb347", secondary: "#ff6b8a", background: "#0c0705" }
    ]
    // Sets every colour field, so nothing from the previous preset survives.
    function applyPreset(p) {
        adapter.preset = p.name;
        p = filled(p);
        for (const k of presetFields) adapter[k] = p[k];
    }

    // ── Custom presets ──────────────────────────
    // Built-ins first, then the user's (tagged custom: true). Colour fields are
    // whatever a built-in defines, so new fields get saved automatically.
    readonly property var presetFields: Object.keys(presets[0]).filter(k => k !== "name")
    readonly property var allPresets: presets.concat((adapter.customPresets || []).map(c => filled(Object.assign({ custom: true }, c))))
    // A custom preset saved before a field existed (or hand-edited) gets its own accent for the
    // secondary and STARK's value for anything else, so nothing reads undefined → black
    function filled(p) {
        const out = Object.assign({}, p);
        for (const k of presetFields)
            if (typeof out[k] !== "string" || out[k] === "") out[k] = k === "secondary" && p.primary ? p.primary : presets[0][k];
        return out;
    }
    function presetName(raw) { return (raw || "").trim().toUpperCase().slice(0, 14); }
    function isBuiltin(name) { return presets.some(b => b.name === name); }

    // Saves the colours currently applied. Returns "" on success, else the reason.
    function savePreset(raw) {
        const name = presetName(raw);
        if (name === "") return "Give it a name";
        if (isBuiltin(name) || name === "CUSTOM") return name + " is a built-in name";
        const entry = { name: name };
        for (const k of presetFields) entry[k] = adapter[k];
        const list = (adapter.customPresets || []).filter(c => c.name !== name);
        list.push(entry);
        adapter.customPresets = list;     // new array → JsonAdapter notices and saves
        adapter.preset = name;
        return "";
    }
    function deletePreset(name) {
        adapter.customPresets = (adapter.customPresets || []).filter(c => c.name !== name);
        if (adapter.preset === name) adapter.preset = "CUSTOM";   // colours stay as they are
    }

    // ── Colors ──────────────────────────────────
    // Anything that isn't a colour (hand-edited settings.json, an old custom preset) falls back
    // to the accent / STARK instead of turning into black
    readonly property color rawPrimary: adapter.primary || ""
    readonly property color rawSecondary: adapter.secondary || ""
    readonly property color rawBg: adapter.background || ""
    readonly property color primary: rawPrimary.valid ? rawPrimary : presets[0].primary
    readonly property color secondary: rawSecondary.valid ? rawSecondary : primary
    readonly property color bg: rawBg.valid ? rawBg : presets[0].background

    function mix(a, b, t) {
        a = Qt.darker(a, 1.0); b = Qt.darker(b, 1.0);   // turns "#rrggbb" strings into colors
        return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, 1);
    }
    readonly property color text: mix(primary, "#ffffff", 0.88)      // bright text
    readonly property color textSoft: mix(primary, "#ffffff", 0.7)   // body text
    readonly property color dim: Qt.hsla(primary.hslHue, Math.min(1, primary.hslSaturation) * 0.38, 0.68, 1)   // labels
    readonly property color faint: Qt.hsla(primary.hslHue, Math.min(1, primary.hslSaturation) * 0.25, 0.42, 1)  // hints
    readonly property color deep: mix(bg, primary, 0.09)             // panel fill
    readonly property real panelAlpha: Math.max(0.5, Math.min(1, adapter.panelOpacity))   // HudFrame / search panel background

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
        const p = hex(primary);
        Quickshell.execDetached(Hypr.config({
            general: { col: {
                active_border: { colors: ["rgba(" + p + "ee)", "rgba(" + p + "55)"], angle: 45 },
                inactive_border: "rgba(" + p + "22)"
            } },
            decoration: { shadow: { color: "rgba(" + p + "40)" } },
            misc: { background_color: "rgb(" + hex(bg) + ")" }
        }));
        pushLockConf();
    }

    // ── Lock screen ─────────────────────────────
    // hyprlock.conf = hyprlock.template.conf with the theme colours, one background block per
    // monitor (that screen's picture of its shut doors, LockState.bgPath) and the clock /
    // password on the main screen. Rewritten when the colours or the monitors change.
    FileView { id: lockTemplate; path: Quickshell.env("HOME") + "/.config/hypr/hyprlock.template.conf"; watchChanges: true; onFileChanged: { reload(); hyprSync.restart(); } }
    readonly property string lockMonitors: Quickshell.screens.map(s => s.name + ":" + Roles.role(s)).join(" ")
    onLockMonitorsChanged: hyprSync.restart()
    function lockConf() {
        const t = lockTemplate.text();
        if (!t) return "";
        const back = "rgb(" + hex(bg) + ")";
        const blocks = ["background {\n    monitor =\n    color = " + back + "\n}"];
        let main = "";
        for (const s of Quickshell.screens) {
            if (Roles.role(s) === "main") main = s.name;
            blocks.push("background {\n    monitor = " + s.name + "\n    path = " + LockState.bgPath(s.name) +
                        "\n    color = " + back + "\n}");
        }
        // One pass, so a colour that's swapped in (SOLAR's primary is STARK's secondary)
        // isn't swapped again. 8fb4c4 = muted text (placeholder, battery) → the HUD's label colour.
        const swap = { "4fd8ff": hex(primary), "ffb347": hex(secondary), "05090f": hex(bg), "8fb4c4": hex(dim),
                       "__HOME__": Quickshell.env("HOME"), "__BACKGROUNDS__": blocks.join("\n"), "__MAIN__": main };
        return t.replace(/4fd8ff|ffb347|05090f|8fb4c4|__HOME__|__BACKGROUNDS__|__MAIN__/g, m => swap[m]);
    }
    function pushLockConf() {
        const conf = lockConf();
        if (conf === "") return;
        Quickshell.execDetached(["sh", "-c",
            "d=~/.config/hypr; printf '%s' \"$1\" > $d/.hyprlock.tmp && mv $d/.hyprlock.tmp $d/hyprlock.conf",
            "sh", conf]);
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
    readonly property color termBack: mix(bg, primary, 0.06)
    // 16 ANSI colours tuned to the theme — shared by kitty and VS Code's terminal
    function termPalette() {
        const hue = Math.max(0, primary.hslHue) * 360;
        const sat = Math.min(1, primary.hslSaturation);
        const back = termBack;
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
        return pal;
    }
    function kittyConf() {
        const back = termBack;
        const pal = termPalette();
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

    // ── Heroic ──────────────────────────────────
    // Writes ~/.config/heroic/themes/stark.css (Heroic's custom theme "stark",
    // customThemesPath = that folder). Heroic reads it on its next launch.
    function heroicCss() {
        const c = x => "#" + hex(x);
        const back = bg;
        const vars = {
            "accent": c(secondary), "accent-overlay": c(mix(secondary, "#ffffff", 0.4)), "navbar-accent": c(primary),
            "background": c(back), "body-background": "var(--background)", "background-darker": c(mix(back, "#000000", 0.4)),
            "current-background": "var(--body-background)",
            "navbar-background": c(mix(back, primary, 0.06)), "navbar-active-background": c(mix(back, primary, 0.14)),
            "gradient-body-background": "linear-gradient( 90deg, var(--background-darker) -32px, var(--body-background) 64px, var(--body-background) 100% )",
            "input-background": c(mix(back, primary, 0.09)), "modal-background": c(mix(back, primary, 0.04)), "modal-border": c(primary) + "55",
            "success": c(secondary), "success-hover": c(mix(secondary, "#000000", 0.15)),
            "primary": c(primary), "primary-hover": c(mix(primary, "#000000", 0.15)), "danger": c(termPalette()[9]),
            "text-title": c(mix(primary, "#ffffff", 0.85)), "text-default": c(textSoft), "text-secondary": "#ffffff",
            "osk-background": "var(--body-background)", "osk-button-background": "var(--input-background)", "osk-button-border": "var(--navbar-background)",
            "action-icon": c(dim), "action-icon-hover": "var(--accent)", "action-icon-active": "var(--text-default)",
            "download-button": c(primary), "success-button": c(secondary), "secondary-button": c(primary),
            "titlebar-color": c(back), "titlebar-symbol-color": c(primary)
        };
        return "/* Generated by quickshell/Theme.qml — edits are overwritten on theme change */\nbody.stark {\n"
            + Object.keys(vars).map(k => "  --" + k + ": " + vars[k] + ";").join("\n") + "\n}\n";
    }
    function pushToHeroic() {
        Quickshell.execDetached(["sh", "-c",
            "d=~/.config/heroic; [ -d $d ] || exit 0; mkdir -p $d/themes && printf '%s' \"$1\" > $d/themes/.stark.tmp && mv $d/themes/.stark.tmp $d/themes/stark.css",
            "sh", heroicCss()]);
    }

    // ── VS Code ─────────────────────────────────
    // stark-code-theme merges just these two keys into ~/.config/Code/User/settings.json;
    // VS Code watches that file, so open windows recolor live. Overlays use alpha,
    // every background stays solid.
    function ink(c, under) {          // lighten toward white until it reads at 4.5:1
        let x = c;
        for (let t = 0.05; contrast(x, under) < 4.5 && t <= 1; t += 0.05) x = mix(c, Qt.rgba(1, 1, 1, 1), t);
        return x;
    }
    function codeTheme() {
        const back = termBack;
        const side = mix(bg, primary, 0.035);              // title / activity / side bars
        const raised = mix(back, primary, 0.1);            // inputs, menus, widgets
        const line = mix(back, primary, 0.22);
        const fg = mix(primary, "#ffffff", 0.85);
        const pal = termPalette();
        const c = x => "#" + hex(x);
        const a = (x, alpha) => c(x) + alpha;
        const on = x => contrast(x, back) >= contrast(x, Qt.rgba(1, 1, 1, 1)) ? c(back) : "#ffffff";
        const P = c(primary), S = c(secondary);
        // Syntax colours — shared by TextMate tokens, semantic tokens and bracket pairs
        const kw = ink(primary, back), fn = ink(mix(primary, "#ffffff", 0.45), back),
              str = ink(secondary, back), num = ink(mix(secondary, "#ffffff", 0.35), back),
              typ = ink(mix(primary, secondary, 0.5), back);
        const wb = {
            "focusBorder": P, "foreground": c(fg), "descriptionForeground": c(dim), "icon.foreground": c(textSoft),
            "selection.background": a(primary, "66"), "widget.shadow": "#00000080",
            "editor.background": c(back), "editor.foreground": c(fg), "editorGutter.background": c(back),
            "editorCursor.foreground": P, "editorCursor.background": c(back),
            "editor.selectionBackground": a(primary, "4d"), "editor.inactiveSelectionBackground": a(primary, "26"),
            "editor.selectionHighlightBackground": a(primary, "26"), "editor.selectionHighlightBorder": a(primary, "80"),
            "editor.wordHighlightBackground": a(primary, "1f"), "editor.wordHighlightStrongBackground": a(primary, "33"),
            "editor.findMatchBackground": a(secondary, "55"), "editor.findMatchBorder": S, "editor.findMatchHighlightBackground": a(secondary, "26"),
            "editor.lineHighlightBackground": c(mix(back, primary, 0.04)), "editor.lineHighlightBorder": c(mix(back, primary, 0.04)),
            "editorLineNumber.foreground": c(faint), "editorLineNumber.activeForeground": P,
            "editorIndentGuide.background1": a(primary, "1a"), "editorIndentGuide.activeBackground1": a(primary, "66"),
            "editorBracketMatch.border": P, "editorBracketMatch.background": a(primary, "1a"),
            "editorWidget.background": c(raised), "editorWidget.border": c(line),
            "editorSuggestWidget.background": c(raised), "editorSuggestWidget.border": c(line),
            "editorSuggestWidget.selectedBackground": a(primary, "33"), "editorSuggestWidget.highlightForeground": P,
            "editorHoverWidget.background": c(raised), "editorHoverWidget.border": c(line),
            "editorGroup.border": c(line), "editorGroupHeader.tabsBackground": c(side),
            "tab.activeBackground": c(back), "tab.activeForeground": c(fg), "tab.activeBorderTop": P, "tab.activeBorder": c(back),
            "tab.inactiveBackground": c(side), "tab.inactiveForeground": c(dim), "tab.border": c(side), "tab.hoverBackground": c(raised),
            "titleBar.activeBackground": c(side), "titleBar.activeForeground": c(fg), "titleBar.border": c(line),
            "titleBar.inactiveBackground": c(side), "titleBar.inactiveForeground": c(dim),
            "activityBar.background": c(side), "activityBar.foreground": P, "activityBar.inactiveForeground": c(dim),
            "activityBar.activeBorder": P, "activityBar.border": c(line),
            "activityBarBadge.background": P, "activityBarBadge.foreground": on(primary),
            "sideBar.background": c(side), "sideBar.foreground": c(textSoft), "sideBar.border": c(line), "sideBarTitle.foreground": P,
            "sideBarSectionHeader.background": c(side), "sideBarSectionHeader.foreground": c(dim), "sideBarSectionHeader.border": c(line),
            "list.activeSelectionBackground": a(primary, "33"), "list.activeSelectionForeground": c(fg),
            "list.inactiveSelectionBackground": a(primary, "1f"), "list.hoverBackground": a(primary, "14"),
            "list.focusOutline": P, "list.highlightForeground": P,
            "statusBar.background": P, "statusBar.foreground": on(primary), "statusBar.border": P, "statusBar.noFolderBackground": P,
            "statusBar.debuggingBackground": S, "statusBar.debuggingForeground": on(secondary),
            "statusBarItem.remoteBackground": S, "statusBarItem.remoteForeground": on(secondary),
            "button.background": P, "button.foreground": on(primary), "button.hoverBackground": c(mix(primary, "#ffffff", 0.2)),
            "button.secondaryBackground": c(raised), "button.secondaryForeground": c(fg),
            "badge.background": P, "badge.foreground": on(primary), "progressBar.background": P,
            "input.background": c(raised), "input.border": c(line), "input.foreground": c(fg), "inputOption.activeBorder": P,
            "dropdown.background": c(raised), "dropdown.border": c(line), "checkbox.border": c(line),
            "menu.background": c(raised), "menu.border": c(line), "menu.selectionBackground": a(primary, "33"),
            "quickInput.background": c(raised), "quickInputList.focusBackground": a(primary, "33"),
            "notifications.background": c(raised), "notifications.border": c(line),
            "textLink.foreground": S, "textLink.activeForeground": S,
            "scrollbarSlider.background": a(primary, "26"), "scrollbarSlider.hoverBackground": a(primary, "40"),
            "scrollbarSlider.activeBackground": a(primary, "66"),
            "panel.background": c(back), "panel.border": c(line),
            "panelTitle.activeBorder": P, "panelTitle.activeForeground": c(fg), "panelTitle.inactiveForeground": c(dim),
            "terminal.background": c(back), "terminal.foreground": c(fg), "terminalCursor.foreground": P,
            "terminal.selectionBackground": a(primary, "4d"), "terminal.border": c(line), "sash.hoverBorder": P,
            // Errors / git / diffs keep their meaning but use the terminal's theme-nudged hues
            "editorError.foreground": c(pal[9]), "editorWarning.foreground": c(pal[11]), "editorInfo.foreground": c(pal[12]),
            "gitDecoration.addedResourceForeground": c(pal[10]), "gitDecoration.untrackedResourceForeground": c(pal[14]),
            "gitDecoration.modifiedResourceForeground": c(str), "gitDecoration.deletedResourceForeground": c(pal[9]),
            "gitDecoration.conflictingResourceForeground": c(pal[13]), "gitDecoration.ignoredResourceForeground": c(faint),
            "editorGutter.addedBackground": c(pal[2]), "editorGutter.modifiedBackground": S, "editorGutter.deletedBackground": c(pal[1]),
            "diffEditor.insertedTextBackground": a(pal[2], "33"), "diffEditor.removedTextBackground": a(pal[1], "33"),
            "diffEditor.insertedLineBackground": a(pal[2], "14"), "diffEditor.removedLineBackground": a(pal[1], "14"),
            "editorOverviewRuler.border": c(line), "editorOverviewRuler.selectionHighlightForeground": a(primary, "99"),
            "editorOverviewRuler.findMatchForeground": a(secondary, "99"), "editorOverviewRuler.modifiedForeground": S,
            "editorOverviewRuler.addedForeground": c(pal[2]), "editorOverviewRuler.deletedForeground": c(pal[1]),
            "editorOverviewRuler.errorForeground": c(pal[9]), "editorOverviewRuler.warningForeground": c(pal[11]),
            "editorBracketHighlight.unexpectedBracket.foreground": c(pal[9])
        };
        ["Black", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"].forEach((n, i) => {
            wb["terminal.ansi" + n] = c(pal[i]);
            wb["terminal.ansiBright" + n] = c(pal[i + 8]);
        });
        // Nested brackets cycle through the accent variations; their guides are dimmer copies
        [kw, str, fn, num, typ, dim].forEach((x, i) => {
            wb["editorBracketHighlight.foreground" + (i + 1)] = c(x);
            wb["editorBracketPairGuide.activeBackground" + (i + 1)] = a(x, "99");
            wb["editorBracketPairGuide.background" + (i + 1)] = a(x, "33");
        });
        const tok = {
            "comments": c(pal[8]), "keywords": c(kw), "functions": c(fn), "strings": c(str),
            "numbers": c(num), "types": c(typ), "variables": c(textSoft)
        };
        // Python / C++ extensions colour code semantically, which would bypass the rules above
        const sem = { "enabled": true, "rules": {
            "keyword": c(kw), "function": c(fn), "method": c(fn), "macro": c(fn),
            "class": c(typ), "struct": c(typ), "type": c(typ), "interface": c(typ), "enum": c(typ),
            "typeParameter": c(typ), "namespace": c(mix(typ, "#ffffff", 0.3)),
            "string": c(str), "number": c(num), "enumMember": c(num), "comment": c(pal[8]),
            "variable": c(textSoft), "parameter": c(mix(textSoft, secondary, 0.25)),
            "property": c(mix(textSoft, primary, 0.25)), "variable.readonly": c(num), "*.decorator": c(str)
        } };
        return JSON.stringify({ "workbench.colorCustomizations": wb, "editor.tokenColorCustomizations": tok,
                                "editor.semanticTokenColorCustomizations": sem });
    }
    function pushToCode() {
        Quickshell.execDetached(["stark-code-theme", codeTheme()]);
    }

    // ── Ambient lights (Govee strip) ────────────
    function pushToGovee() {
        Quickshell.execDetached(["stark-govee", "theme", hex(primary), hex(secondary)]);
    }

    // ── Cursor ──────────────────────────────────
    // ~/.config/stark-cursor/build.sh renders the STARK-OS cursor theme in the accent
    // (cached per colour) and applies it with `hyprctl setcursor`. One build at a time;
    // a change mid-build runs once more afterwards with whatever is current then.
    readonly property bool cursorAnimated: adapter.cursorAnimated
    readonly property var cursorSizes: [24, 32, 48]
    function cursorFill() { return Math.max(20, Math.min(90, Math.round(adapter.cursorOpacity / 5) * 5)); }   // 5% steps keep the cache useful
    function cursorStep(dir) {
        const i = cursorSizes.indexOf(adapter.cursorSize);
        return cursorSizes[Math.max(0, Math.min(cursorSizes.length - 1, (i < 0 ? 0 : i) + dir))];
    }
    property bool cursorPending: false
    function pushCursor() {
        if (!root.loaded) return;
        if (cursorBuild.running) { cursorPending = true; return; }
        cursorBuild.command = [Quickshell.env("HOME") + "/.config/stark-cursor/build.sh", hex(primary),
            cursorAnimated ? "animated" : "static", String(cursorStep(0)), String(cursorFill())];
        cursorBuild.running = true;
    }
    Process {
        id: cursorBuild
        onExited: if (root.cursorPending) { root.cursorPending = false; root.pushCursor(); }
    }

    onPrimaryChanged: { hyprSync.restart(); kittySync.restart(); heroicSync.restart(); codeSync.restart(); goveeSync.restart(); cursorSync.restart(); }
    onBgChanged: { hyprSync.restart(); kittySync.restart(); heroicSync.restart(); codeSync.restart(); }
    onSecondaryChanged: { hyprSync.restart(); kittySync.restart(); heroicSync.restart(); codeSync.restart(); goveeSync.restart(); }
    Connections {
        target: adapter
        function onTerminalGlassChanged() { kittySync.restart(); }
        function onCursorSizeChanged() { cursorSync.restart(); }
        function onCursorOpacityChanged() { cursorSync.restart(); }
    }
    onCursorAnimatedChanged: cursorSync.restart()
    onLoadedChanged: cursorSync.restart()
    Timer { id: hyprSync; interval: 300; onTriggered: root.pushToHyprland() }
    Timer { id: kittySync; interval: 300; onTriggered: root.pushToKitty() }
    Timer { id: heroicSync; interval: 300; onTriggered: root.pushToHeroic() }
    Timer { id: codeSync; interval: 300; onTriggered: root.pushToCode() }
    Timer { id: goveeSync; interval: 300; onTriggered: root.pushToGovee() }
    Timer { id: cursorSync; interval: 600; onTriggered: root.pushCursor() }   // longer: a cold build is ~1 s
    Component.onCompleted: { hyprSync.restart(); kittySync.restart(); heroicSync.restart(); codeSync.restart(); goveeSync.restart(); }
    // `hyprctl reload` resets border colors → push them again
    Connections {
        target: Hyprland
        function onRawEvent(event) { if (event.name === "configreloaded") { hyprSync.restart(); cursorSync.restart(); } }
    }
}
