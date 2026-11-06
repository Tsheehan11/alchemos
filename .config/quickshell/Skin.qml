pragma Singleton
// Skins: the look of the HUD, never its behaviour. A skin picks the built-in colour presets,
// the clock and lock-scene components, persona display names / glyphs, the words on the bar,
// lock screen and settings, the busy-cursor art and its own switch transition. Keybinds, IPC,
// voices, wake word and custom presets are the same in every skin.
//
//   alchemos  built in (the default)
//   legacy    the private overlay in skins/legacy/ (its own repo, ignored here): skin.json +
//             the components it names. Missing folder = the skin doesn't exist and the HUD
//             quietly stays on ALCHEMOS.
//
// Settings: cfg.skin (asked-for skin), cfg.skinPresets ({ skin: { name, primary, secondary,
// background } }: each skin's last look), cfg.skinUnlocked (the SKIN row shows in Settings).
//   qs ipc call skin get | set legacy | set alchemos | toggle | list
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property string dir: Quickshell.env("HOME") + "/.config/quickshell/skins/"

    // ── ALCHEMOS (built in) ─────────────────────
    readonly property var alchemos: ({
        id: "alchemos",
        label: "ALCHEMOS",
        // ☉ gold · ☽ silver · ♂ iron · ♀ copper · ☿ quicksilver · ♄ lead
        presets: [
            { name: "AURUM",     glyph: "☉", primary: "#ffc04a", secondary: "#ff8f3a", background: "#0b0803" },
            { name: "ARGENT",    glyph: "☽", primary: "#d4dde8", secondary: "#9fb6d6", background: "#06080b" },
            { name: "IRON",      glyph: "♂", primary: "#e23b2e", secondary: "#ffb27a", background: "#0d0505" },
            { name: "VERDIGRIS", glyph: "♀", primary: "#3fd6b0", secondary: "#e0915a", background: "#03100c" },
            { name: "MERCURY",   glyph: "☿", primary: "#5fdcff", secondary: "#cfe9f5", background: "#04090e" },
            { name: "LEAD",      glyph: "♄", primary: "#a497c8", secondary: "#7d8db0", background: "#07060b" }
        ],
        // the STARK OS preset each metal replaced (closest hue); spoken / typed old names still work
        aliases: { "SOLAR": "AURUM", "ARCTIC": "ARGENT", "MARK III": "IRON", "MATRIX": "VERDIGRIS",
                   "STARK": "MERCURY", "VIBRANIUM": "LEAD" },
        clock: "AlchemCircle.qml",
        scene: "VaultScene.qml",
        cursor: "sigil",
        transition: "transmute",
        personas: {
            jarvis: { name: "ORRIN",  call: "Orrin",  dotted: "O.R.R.I.N",   glyph: "☉", idle: "☉", starting: "☉", accent: "#ffc04a" },
            friday: { name: "SELENE", call: "Selene", dotted: "S.E.L.E.N.E", glyph: "☽", idle: "☽", starting: "☽", accent: "#d4dde8" }
        },
        text: {
            os: "ALCHEMOS",
            control: "ALCHEMOS // CONTROL",
            settings: "ALCHEMOS // SETTINGS",
            lockMessage: "SEALING",
            lockSub: "ALCHEMOS // THE VAULT CLOSES",
            unlockMessage: "SEAL BROKEN",
            lockTitle: "ALCHEMOS // SEALED",
            denied: "THE SEAL HOLDS",
            lockGlyph: "☉",
            mark: "",                 // bar corner: "" = the sign of the metal in use
            clockName: "Alchemical circle clock",
            cursorHint: "The sigil turns while apps load · off shows a still frame",
            transitionTitle: "TRANSMUTATION",
            transitionSub: "ALCHEMOS // THE WORK BEGINS"
        }
    })

    // ── LEGACY (private overlay) ────────────────
    FileView {
        id: legacyFile
        path: root.dir + "legacy/skin.json"
        watchChanges: true
        printErrors: false
        blockLoading: true
        onFileChanged: reload()
        onLoadFailed: root.legacyText = ""
        onLoaded: root.legacyText = text()
    }
    property string legacyText: ""
    readonly property var legacyData: {
        if (!legacyText) return null;
        try {
            const d = JSON.parse(legacyText);
            return Array.isArray(d.presets) && d.presets.length > 0 ? d : null;
        } catch (e) { return null; }
    }
    readonly property bool legacyAvailable: legacyData !== null

    // ── The skin in use ─────────────────────────
    readonly property string current: Theme.cfg.skin === "legacy" && legacyAvailable ? "legacy" : "alchemos"
    readonly property bool isLegacy: current === "legacy"
    readonly property var data: isLegacy ? merged(alchemos, legacyData) : alchemos

    // a legacy skin.json that leaves something out gets ALCHEMOS's value for it
    function merged(a, b) {
        const out = Object.assign({}, a, b);
        out.text = Object.assign({}, a.text, b.text || {});
        out.personas = {
            jarvis: Object.assign({}, a.personas.jarvis, (b.personas || {}).jarvis || {}),
            friday: Object.assign({}, a.personas.friday, (b.personas || {}).friday || {})
        };
        out.aliases = b.aliases || {};
        return out;
    }

    readonly property var presets: data.presets
    readonly property var text: data.text
    readonly property var aliases: data.aliases || {}
    readonly property string label: data.label
    readonly property string cursor: data.cursor
    readonly property string transition: data.transition
    // Components resolve inside the shell (qs:@/qs/…, like widgets/): a file:// URL would load a second
    // copy of every singleton the component imports. One expression each, so a switch never pairs one
    // skin's folder with the other's file name.
    function component(key) {
        return isLegacy && legacyData[key] ? Qt.resolvedUrl("skins/legacy/" + legacyData[key]) : Qt.resolvedUrl(alchemos[key]);
    }
    readonly property url clockUrl: component("clock")
    readonly property url sceneUrl: component("scene")
    function persona(who) { return data.personas[who === "friday" ? "friday" : "jarvis"]; }
    function glyphFor(presetName) {
        const p = presets.find(x => x.name === presetName);
        return p ? (p.glyph || "") : "";
    }
    // Every built-in name of every skin (custom presets can't take one)
    readonly property var reservedNames: alchemos.presets.map(p => p.name)
        .concat(Object.keys(alchemos.aliases)).concat(legacyAvailable ? legacyData.presets.map(p => p.name) : [])

    // ── Switching ───────────────────────────────
    signal switched(string to)          // Ignite.qml plays the new skin's transition
    readonly property var names: ["alchemos", "legacy"]

    // → "" on success, else why not
    function set(name, unlock) {
        const n = String(name || "").trim().toLowerCase();
        if (names.indexOf(n) < 0) return "unknown skin " + n + " (alchemos | legacy)";
        if (n === "legacy" && !legacyAvailable) return "legacy skin not installed";
        if (unlock && !Theme.cfg.skinUnlocked) Theme.cfg.skinUnlocked = true;
        if (n === current) return "";
        Theme.switchSkin(current, n);
        root.switched(n);
        return "";
    }
    function toggle(unlock) { return set(isLegacy ? "alchemos" : "legacy", unlock); }

    // The app search's hidden word (Qt.md5 of it; the word itself isn't kept anywhere)
    readonly property string secretHash: "c08b2c550f28b9569e2bf83ffb37e2d1"
    function isSecret(q) { return q.length >= 8 && Qt.md5(q.trim().toLowerCase()) === secretHash; }

    IpcHandler {
        target: "skin"
        function get(): string { return root.current }
        function list(): string {
            return JSON.stringify({ current: root.current, asked: Theme.cfg.skin, available: root.legacyAvailable ? root.names : ["alchemos"] });
        }
        function set(name: string): string {
            const why = root.set(name, true);
            return why || "skin " + root.current;
        }
        function toggle(): string {
            const why = root.toggle(true);
            return why || "skin " + root.current;
        }
    }
}
