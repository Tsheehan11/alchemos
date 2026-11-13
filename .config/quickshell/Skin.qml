pragma Singleton
// Skins: the look of the HUD, never its behaviour. Every feature lives in the main tree and works in
// every skin; a skin is just a folder, skins/<id>/, holding skin.json and, optionally, files it names.
// See docs/SKINS.md and skins/_template/.
//
// A skin provides (all optional; anything left out comes from BASE below, today's hologram look):
//   presets + aliases   built-in colour presets (with glyphs) and other names for them
//   personas, text      names / glyphs / accents of the two personas, the HUD's wording
//   osName              what the assistant calls the desktop
//   glyphs              { ring: [...] signs round the clock, the lock seal and the skin transition; sun }
//   style               tokens read by the shared components (Style.qml)
//   components          overrides of the default clock / scene / transition (files in the skin's folder)
//   cursor              a folder of busy-cursor templates (wait.svg, progress.svg) for alchemos-cursor/build.sh
//   namer, voices       preset auto-namer (Settings → SAVE AS PRESET) and voice defaults
//   hidden              listed in Settings only once skins have been unlocked (the legacy skin)
//
//   alchemos   skins/alchemos (this repo; the default)
//   legacy     skins/legacy: the private overlay (its own repo, ignored here). Missing = no such skin.
//   _template  skins/_template: never listed; the starting point for a new skin
//
// The skin in use is read synchronously (no flicker at start-up); the list of installed skins is
// scanned in the background (Settings' SKIN row, `skin list`).
// Settings: cfg.skin, cfg.skinPresets (each skin's last look), cfg.skinUnlocked.
//   qs ipc call skin get | set <id> | toggle | list
import QtQuick
import Qt.labs.folderlistmodel
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property string defaultSkin: "alchemos"
    readonly property string hiddenSkin: "legacy"        // the app search's hidden word toggles to and from it

    // ── BASE: what a skin leaves out. Today's hologram look, neutral wording ──
    readonly property var base: ({
        id: "base",
        label: "HUD",
        osName: "the desktop",
        presets: [
            { name: "CYAN",    primary: "#4fd8ff", secondary: "#ffb347", background: "#05090f" },
            { name: "CRIMSON", primary: "#ff5a4d", secondary: "#ffd24d", background: "#0c0505" },
            { name: "VIOLET",  primary: "#b48cff", secondary: "#7fe0ff", background: "#08050f" },
            { name: "EMERALD", primary: "#4dff88", secondary: "#d4ff4d", background: "#030a05" },
            { name: "ICE",     primary: "#d6f1ff", secondary: "#6fa8ff", background: "#05080f" },
            { name: "AMBER",   primary: "#ffb347", secondary: "#ff6b8a", background: "#0c0705" }
        ],
        aliases: {},
        glyphs: { ring: [], sun: "" },
        components: {},
        cursor: "",
        personas: {
            orrin: { name: "JARVIS", call: "Jarvis", dotted: "J.A.R.V.I.S", glyph: "◉", idle: "○", starting: "◌", accent: "" },
            selene: { name: "FRIDAY", call: "Friday", dotted: "F.R.I.D.A.Y", glyph: "◈", idle: "◇", starting: "◇", accent: "" }
        },
        text: {
            os: "HUD", control: "HUD // CONTROL", settings: "HUD // SETTINGS",
            host: "stark",          // the diagnostics wall's user@host line (LEGACY reads this base value)
            lockMessage: "LOCKING", lockSub: "", unlockMessage: "UNLOCKED", lockTitle: "LOCKED", denied: "TRY AGAIN",
            lockGlyph: "◆", mark: "◆", clockName: "Clock",
            // hyprlock's password box and fingerprint lines; the HUD's unlock / power words ({name} = greetName)
            lockPrompt: "ENTER PASSPHRASE", fprintReady: "PASSPHRASE OR FINGERPRINT", fprintPresent: "SCANNING…",
            unlockSub: "WELCOME BACK, {name}", powerTitle: "POWER // SELECT",
            shutdownMessage: "SHUTTING DOWN", rebootMessage: "REBOOTING", logoutMessage: "SIGNING OFF",
            powerSub: "SAVING STATE // POWERING DOWN SYSTEMS", logoutSub: "SEE YOU SOON, {name}",
            cursorHint: "The busy cursor turns while apps load · off shows a still frame",
            transitionTitle: "", transitionSub: ""
        },
        style: {},
        namer: null,
        voices: null,
        // AUTO's effect per output (core/effects.py BASE_ROUTING; skin.json voiceRouting per persona)
        voiceRouting: { orrin: { headphones: "SUIT", speaker: "HOLOGRAM", btSpeaker: "HOLOGRAM" },
                        selene: { headphones: "SUIT", speaker: "HOLOGRAM", btSpeaker: "HOLOGRAM" } },
        hidden: false
    })
    // Default implementations, used when a skin doesn't override them
    readonly property var defaults: ({ clock: "AlchemCircle.qml", scene: "VaultScene.qml", transition: "TransmuteTransition.qml",
                                      backdrop: "HoloBackdrop.qml", launcherLook: "HoloLauncherLook.qml",
                                      carouselStage: "HoloCarouselStage.qml", carouselPanel: "HoloCarouselPanel.qml",
                                      notifCard: "HoloNotifCard.qml" })

    // ── The skin in use (read synchronously) ────
    function parse(text) {
        if (!text) return null;
        try { const d = JSON.parse(text); return d && typeof d === "object" ? normPersonas(d) : null; } catch (e) { return null; }
    }
    // A skin keyed by the pre-AlchemOS persona ids (jarvis / friday: the legacy skin, never edited) reads
    // as orrin / selene. Same rule as ~/.config/orrin/core/persona.py norm_skin().
    readonly property var personaAliases: ({ jarvis: "orrin", friday: "selene" })
    function normPersonas(d) {
        for (const k of ["personas", "voiceRouting", "voices"]) {
            const v = d[k];
            if (!v || typeof v !== "object" || Array.isArray(v)) continue;
            const out = {};
            for (const p of Object.keys(v)) out[root.personaAliases[p] || p] = v[p];
            d[k] = out;
        }
        return d;
    }
    readonly property string asked: String(Theme.cfg.skin || defaultSkin)
    // Each FileView remembers which file its last load came from: right after the path changes, text()
    // can still be the previous file's, and the new id must never be paired with the old skin's data.
    FileView {
        id: askedFile
        property string loadedPath: ""
        property var loadedData: null
        path: Quickshell.shellPath("skins/" + root.asked + "/skin.json")
        watchChanges: true; printErrors: false; blockLoading: true
        onFileChanged: reload()
        onLoaded: { loadedData = root.parse(text()); loadedPath = path; root.resolve(); }
        onLoadFailed: { loadedData = null; loadedPath = path; root.resolve(); }
    }
    FileView {
        id: defaultFile
        property string loadedPath: ""
        property var loadedData: null
        path: Quickshell.shellPath("skins/" + root.defaultSkin + "/skin.json")
        watchChanges: true; printErrors: false; blockLoading: true
        onFileChanged: reload()
        onLoaded: { loadedData = root.parse(text()); loadedPath = path; root.resolve(); }
        onLoadFailed: { loadedData = null; loadedPath = path; root.resolve(); }
    }
    onAskedChanged: resolve()
    Component.onCompleted: resolve()
    // The skin in use: { id, own (its skin.json) }, updated only once the asked skin's own file has been read
    property var resolved: ({ id: "base", own: {} })
    function resolve() {
        // compare with the path the asked id means now (the FileView's own path binding may not have
        // caught up yet when `asked` changes)
        const want = id => Quickshell.shellPath("skins/" + id + "/skin.json");
        const ownOf = (f, id) => f.loadedPath === want(id) ? f.loadedData : undefined;   // undefined: not read yet
        const hidden = root.asked.charAt(0) === "_" && root.asked !== Quickshell.env("SKINCHECK_SKIN");
        const a = hidden ? null : ownOf(askedFile, root.asked);
        const d = ownOf(defaultFile, root.defaultSkin);
        if (a === undefined) {
            Qt.callLater(() => { if (askedFile.loadedPath !== want(root.asked)) askedFile.reload(); else root.resolve(); });
            return;                                  // keep the skin as it is until the asked one is read
        }
        const next = a ? { id: root.asked, own: a } : d ? { id: root.defaultSkin, own: d } : { id: "base", own: {} };
        if (next.id !== root.resolved.id || JSON.stringify(next.own) !== JSON.stringify(root.resolved.own)) root.resolved = next;
    }
    readonly property string current: resolved.id
    readonly property var own: resolved.own
    readonly property var data: merged(base, resolved.own)
    readonly property bool isLegacy: current === hiddenSkin

    // a skin's skin.json over BASE: objects merge a level deep, lists and values replace
    function merged(a, b) {
        const out = Object.assign({}, a, b);
        for (const k of ["text", "glyphs", "style", "components"]) out[k] = Object.assign({}, a[k], b[k] || {});
        out.personas = {
            orrin: Object.assign({}, a.personas.orrin, (b.personas || {}).orrin || {}),
            selene: Object.assign({}, a.personas.selene, (b.personas || {}).selene || {})
        };
        if (!Array.isArray(out.presets) || out.presets.length === 0) out.presets = a.presets;
        return out;
    }

    readonly property var presets: data.presets
    readonly property var text: data.text
    readonly property var aliases: data.aliases || {}
    readonly property var glyphs: data.glyphs
    readonly property var style: data.style
    readonly property string label: data.label
    readonly property string osName: data.osName

    // Components resolve inside the shell (qs:@/qs/…, like widgets/): a file:// URL would load a second
    // copy of every singleton the component imports. A skin's own file, else the default.
    function component(name) {
        const r = root.resolved;
        const file = (r.own.components || {})[name];
        if (file && r.id !== "base") return Qt.resolvedUrl("skins/" + r.id + "/" + file);
        return root.defaults[name] ? Qt.resolvedUrl(root.defaults[name]) : "";
    }
    readonly property url clockUrl: component("clock")
    readonly property url sceneUrl: component("scene")
    readonly property url transitionUrl: component("transition")
    // alchemos-cursor/build.sh: the skin's busy-cursor template folder ("" = the default art)
    readonly property string cursorDir: resolved.own.cursor && resolved.id !== "base" ? Quickshell.shellPath("skins/" + resolved.id + "/" + resolved.own.cursor) : ""

    // AUTO's effect per output for who: the skin's voiceRouting over the base's
    function voiceRouting(who) {
        const w = who === "selene" ? "selene" : "orrin";
        return Object.assign({}, base.voiceRouting[w], ((resolved.own.voiceRouting || {})[w]) || {});
    }
    // A skin's wording (its skin.json text over BASE) by id, whether or not it is the one in use yet
    function textOf(id) {
        const d = id === root.current ? root.own : (installed[id] || {});
        return Object.assign({}, base.text, d.text || {});
    }
    function persona(who) { return data.personas[who === "selene" ? "selene" : "orrin"]; }
    function glyphFor(presetName) {
        const p = presets.find(x => x.name === presetName);
        return p ? (p.glyph || "") : "";
    }

    // ── Installed skins (scanned in the background) ──
    FolderListModel {
        id: folders
        folder: "file://" + Quickshell.shellPath("skins")
        showDirs: true; showFiles: false; showDotAndDotDot: false
    }
    property var installed: ({})                         // id → skin.json data
    Instantiator {
        model: folders
        delegate: FileView {
            required property string fileName
            path: Quickshell.shellPath("skins/" + fileName + "/skin.json")
            watchChanges: true; printErrors: false
            onFileChanged: reload()
            onLoaded: root.note(fileName, root.parse(text()))
            onLoadFailed: root.note(fileName, null)
        }
    }
    function note(id, d) {
        const m = Object.assign({}, root.installed);
        if (d && id.charAt(0) !== "_") m[id] = d; else delete m[id];
        root.installed = m;
    }
    function has(id) { return !!root.installed[id] || id === root.current; }
    // what Settings lists: every skin, hidden ones once unlocked
    readonly property var listed: Object.keys(installed).filter(id => !installed[id].hidden || Theme.cfg.skinUnlocked)
        .sort((a, b) => (a === root.defaultSkin ? -1 : b === root.defaultSkin ? 1 : a.localeCompare(b)))
    // a second skin is on offer (the hidden one only after its first unlock): the same rule as Settings'
    // SKIN row. The control center's SKIN tile, the power menu's SWITCH SKIN and Super+Shift+K follow it.
    readonly property bool switchable: listed.length > 1
    // the skin a toggle goes to
    readonly property string other: isLegacy || !legacyAvailable ? defaultSkin : hiddenSkin
    function labelOf(id) { return (installed[id] && installed[id].label) || id.toUpperCase(); }
    // compatibility with the two-skin API
    readonly property bool legacyAvailable: !!installed[hiddenSkin] || current === hiddenSkin
    readonly property var legacyData: installed[hiddenSkin] || null
    // Every built-in name of every installed skin (custom presets can't take one)
    readonly property var reservedNames: {
        let names = presets.map(p => p.name).concat(Object.keys(aliases));
        for (const id in installed) {
            const d = installed[id];
            names = names.concat((d.presets || []).map(p => p.name)).concat(Object.keys(d.aliases || {}));
        }
        return names;
    }
    function presetsOf(id) {
        const d = id === root.current ? root.own : installed[id];
        return d && Array.isArray(d.presets) && d.presets.length ? d.presets : base.presets;
    }

    // ── Switching ───────────────────────────────
    signal switched(string to)          // Ignite.qml plays the new skin's transition

    // → "" on success, else why not
    function set(name, unlock) {
        const n = String(name || "").trim().toLowerCase();
        if (n.charAt(0) === "_" || !installed[n] && n !== current)
            return "skin " + n + " not installed (" + Object.keys(installed).join(" | ") + ")";
        if (unlock && !Theme.cfg.skinUnlocked) Theme.cfg.skinUnlocked = true;
        if (n === current) return "";
        Theme.switchSkin(current, n);
        root.switched(n);
        return "";
    }
    // the hidden skin and back (the app search's word, `skin toggle`, "switch skins")
    function toggle(unlock) { return set(isLegacy || !legacyAvailable ? defaultSkin : hiddenSkin, unlock); }

    // The app search's hidden word (Qt.md5 of it; the word itself isn't kept anywhere)
    readonly property string secretHash: "c08b2c550f28b9569e2bf83ffb37e2d1"
    function isSecret(q) { return q.length >= 8 && Qt.md5(q.trim().toLowerCase()) === secretHash; }

    IpcHandler {
        target: "skin"
        function get(): string { return root.current }
        function list(): string {
            return JSON.stringify({ current: root.current, asked: Theme.cfg.skin, available: Object.keys(root.installed).sort(),
                                    listed: root.listed });
        }
        // the reply names the skin switched to (the switch itself lands once that skin's file is read)
        function set(name: string): string {
            const why = root.set(name, true);
            return why || "skin " + root.asked;
        }
        function toggle(): string {
            const why = root.toggle(true);
            return why || "skin " + root.asked;
        }
        // Super+Shift+K: toggle, but only once there is a choice (never unlocks the hidden skin)
        function swap(): string {
            if (!root.switchable) return "no other skin yet";
            const why = root.toggle(false);
            return why || "skin " + root.asked;
        }
    }
}
