// HUD theme + preferences. Everything here is saved to settings.json
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
            property string preset: "AURUM"
            property string primary: "#ffc04a"
            property string secondary: "#ff8f3a"
            property string background: "#0b0803"
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
            property string jarvisPersona: "jarvis"   // jarvis | friday: who answers by default (~/.config/jarvis/core/persona.py)
            property string fridayVoice: "bf_emma"    // FRIDAY's Kokoro voice (jarvis-voices --friday to audition)
            property real fridaySpeed: 1.15           // FRIDAY's speech rate (JARVIS keeps jarvisSpeed / jarvisPitch)
            property real fridayPitch: 0.0
            property string fridayEffect: ""          // FRIDAY's own effect preset; "" = the same as jarvisEffect
            property int jarvisVoiceVolume: 60        // VOICE VOLUME 0–100 %: Jarvis's voice + chime, a gain after its effects; other audio untouched
            property int jarvisSpeakerVolume: -1      // own level on the Bluetooth speaker, 0–100 %; -1 = same as VOICE VOLUME
            property real jarvisPitch: 0.0            // semitones, on top of the effect preset
            property string jarvisEffect: "AUTO"      // AUTO = the skin's pick for the output (skin.json voiceRouting); presets in ~/.config/jarvis/effects.json
            property bool jarvisSpeak: true           // spoken replies (the toast shows them either way)
            property bool jarvisDuck: true            // lower the music while Jarvis talks
            property int jarvisFollowup: 8            // seconds to listen for a follow-up without the wake word (0 = off)
            property string jarvisSpeaker: ""         // Bluetooth MAC: speaker for Jarvis when not on headphones ("" = off)
            property string jarvisMic: "auto"         // wake-word mic: auto (headset mic if plugged in, else the laptop DMIC) | default | a PipeWire source node.name
            property bool jarvisMicBluetooth: false   // AUTO may pick a Bluetooth headset mic (the headphones drop to call quality while Jarvis listens)
            property string jarvisPlace: "Waterloo, Ontario"   // home town for "what's the weather"
            property bool jarvisAutoAddAssignments: false   // LEARN sync writes to the "STARK – Assignments" calendar without asking (that calendar only)
            property bool jarvisAutoUpdateTracker: false    // grade notices / new LEARN work / moved deadlines write to the SE tracker sheet without asking
            property string jarvisAssignmentsAccount: "google"   // where that calendar lives: google | microsoft
            property string jarvisDecisions: "local"   // local = fast path → local router → Claude | claude = fast path → Claude
            property real jarvisRouterThreshold: 0.70  // similarity the local router needs to act (~/.config/jarvis/tools/eval_router.py)
            property bool jarvisRouterAsk: true        // local router: "Did you mean …?" on near misses (~/.config/jarvis/core/router_local.py)
            property int jarvisWatchInterval: 10      // seconds between a watcher's captures (~/.config/jarvis/core/watch.py)
            property string jarvisDjChatter: "rare"   // DJ mode lines between tracks: off | rare (every 4–5) | normal (every 2–3) (~/.config/jarvis/core/dj.py)
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
            property int cursorSize: 24                // ALCHEMOS cursor: 24 | 32 | 48
            property bool cursorAnimated: true         // spinning arc-reactor busy cursor (static frame when off)
            property int cursorOpacity: 45             // cursor body fill, % (20–90)
            property real panelOpacity: 0.85           // HUD panel backgrounds: settings, control center, search (0.5–1)
            property var customPresets: []             // user presets: [{ name, primary, secondary, background }]
            // Combat mode (GameMode.qml); the alchemos-game daemon reads these too
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
            property string vpnProvider: "proton"       // VPN the tile / Settings act on (VPN.qml, alchemos-vpn providers.json)
            // Skins (Skin.qml): the look only, never behaviour
            property string skin: "alchemos"            // alchemos | legacy (needs the private skins/legacy overlay)
            property bool skinUnlocked: false           // the SKIN row shows in Settings → APPEARANCE
            property var skinPresets: ({})              // each skin's last look: { skin: { name, primary, secondary, background } }
            property int skinVersion: 0                 // 1 = STARK OS presets moved to their metals; 2 = voices per skin; 3 = ALCHEMOS voice picks; 4 = ALCHEMOS Pocket voices, Orrin/Selene designed (migrateSkins)
            property var skinVoices: ({})               // each skin's last voices: { skin: { jarvisVoice, jarvisSpeed, … } } (voiceKeys)
        }
    }
    property bool loaded: false   // settings.json has been read at least once
    Timer { id: saveTimer; interval: 50; onTriggered: file.writeAdapter() }

    // ── Presets ─────────────────────────────────
    // The built-ins come from the skin (Skin.qml); each has a glyph shown on its tile
    readonly property var presets: Skin.presets
    // Sets every colour field, so nothing from the previous preset survives.
    // presetApplied: Ignite.qml flares the new colour over the HUD ("ignite"); not for a skin switch,
    // which plays its own transition.
    signal presetApplied(var preset)
    property bool switchingSkin: false
    function applyPreset(p) {
        const changed = adapter.preset !== p.name || adapter.primary !== filled(p).primary;
        adapter.preset = p.name;
        p = filled(p);
        for (const k of presetFields) adapter[k] = p[k];
        if (changed && !switchingSkin && loaded) presetApplied(p);
    }

    // ── Custom presets ──────────────────────────
    // Built-ins first, then the user's (tagged custom: true). Colour fields are
    // whatever a built-in defines, so new fields get saved automatically.
    readonly property var presetFields: ["primary", "secondary", "background"]
    readonly property var allPresets: presets.concat((adapter.customPresets || []).map(c => filled(Object.assign({ custom: true }, c))))
    // A custom preset saved before a field existed (or hand-edited) gets its own accent for the
    // secondary and STARK's value for anything else, so nothing reads undefined → black
    function filled(p) {
        const out = Object.assign({}, p);
        for (const k of presetFields)
            if (typeof out[k] !== "string" || out[k] === "") out[k] = k === "secondary" && p.primary ? p.primary : presets[0][k];
        return out;
    }
    // The preset wheel (the clock's ring of signs): the skin's signs, then the signs of the custom presets,
    // the 6 most recently saved plus the one in use, each once. signFor: a preset's sign, built-in or custom.
    readonly property int customSignMax: 6
    readonly property var customSigns: {
        const ring = Skin.glyphs.ring || [];
        const list = (adapter.customPresets || []).filter(c => c.glyph);
        let pick = list.slice(-customSignMax);
        const cur = list.find(c => c.name === adapter.preset);
        if (cur && pick.indexOf(cur) < 0) pick = pick.slice(1).concat([cur]);
        const out = [];
        for (const c of pick) if (ring.indexOf(c.glyph) < 0 && out.indexOf(c.glyph) < 0) out.push(c.glyph);
        return out;
    }
    function signFor(name) {
        const b = Skin.glyphFor(name);
        if (b) return b;
        const c = (adapter.customPresets || []).find(x => x.name === name);
        return c && c.glyph ? c.glyph : "";
    }
    readonly property string activeSign: signFor(adapter.preset)
    readonly property string activeName: adapter.preset || "CUSTOM"
    function presetName(raw) { return (raw || "").trim().toUpperCase().slice(0, 14); }
    // Every name a new preset can't take: built-ins of every installed skin and the saved custom ones
    function takenNames() { return Skin.reservedNames.concat((adapter.customPresets || []).map(c => c.name)).concat(["CUSTOM"]); }
    function isBuiltin(name) { return presets.some(b => b.name === name) || Skin.reservedNames.indexOf(name) >= 0; }
    // By name, case-insensitive; the other skin's names map through the skin's aliases (MARK III → IRON)
    function findPreset(raw) {
        const n = presetName(raw);
        const hit = allPresets.find(x => x.name === n);
        if (hit) return hit;
        const alias = Skin.aliases[n];
        return alias ? allPresets.find(x => x.name === alias) || null : null;
    }

    // ── Skins ───────────────────────────────────
    // Each skin keeps its own last look; switching saves the one being left and puts the other back.
    function lookRecord() {
        return { name: adapter.preset, primary: adapter.primary, secondary: adapter.secondary, background: adapter.background };
    }
    // r: a saved look; builtins: the skin's own presets (passed in: during a switch Theme.presets may still
    // be the old skin's); fallback: what an empty record gets
    function applyRecord(r, fallback, builtins) {
        if (!r || !r.name) { applyPreset(fallback); return; }
        const built = (builtins || presets).find(x => x.name === r.name) || allPresets.find(x => x.custom && x.name === r.name);
        if (built) { applyPreset(built); return; }      // built-in / custom: its current colours
        adapter.preset = r.name;                        // CUSTOM (hand-mixed): the colours as they were
        for (const k of presetFields) adapter[k] = typeof r[k] === "string" && r[k] ? r[k] : fallback[k];
    }
    // Once: settings from before skins. A STARK OS preset in use becomes its metal (MARK III → IRON) and is
    // kept as the legacy skin's look; a custom look stays as it is, for both skins.
    function migrateSkins() {
        if (adapter.skinVersion === 3) {
            // v4: ALCHEMOS moved to Pocket TTS (pocket/orrin_2, pocket/selene_1, speed 1): drop its saved record so
            // the new defaults apply; Kokoro speeds tuned for the old voices would rush the new ones
            const sv = Object.assign({}, adapter.skinVoices || {});
            delete sv.alchemos;
            adapter.skinVoices = sv;
            adapter.skinVersion = 4;
            applySkinVoiceDefaults();
            return;
        }
        if (adapter.skinVersion === 2) {
            // v3: ALCHEMOS's voices were picked (audition): drop the record saved for it before there were any
            // (and a stray one under "base"), so its defaults apply
            const sv = Object.assign({}, adapter.skinVoices || {});
            delete sv.alchemos; delete sv.base;
            adapter.skinVoices = sv;
            adapter.skinVersion = 4;
            applySkinVoiceDefaults();
            return;
        }
        if (adapter.skinVersion < 2) {
            // v2: voices became part of the skin. The voices set until now stay the legacy skin's, as they are.
            const sv = Object.assign({}, adapter.skinVoices || {});
            if (!sv.legacy) sv.legacy = voiceRecord();
            adapter.skinVoices = sv;
            if (adapter.skinVersion >= 1) { adapter.skinVersion = 4; applySkinVoiceDefaults(); return; }
        }
        if (adapter.skinVersion >= 1) { applySkinVoiceDefaults(); return; }
        const alch = Skin.current === "alchemos" ? Skin.own : (Skin.installed.alchemos || {});
        const al = alch.aliases || {};
        const sp = Object.assign({}, adapter.skinPresets || {});
        const old = lookRecord();
        if (al[old.name]) {
            sp.legacy = old;
            const metal = Skin.presetsOf("alchemos").find(x => x.name === al[old.name]);
            sp.alchemos = { name: metal.name, primary: metal.primary, secondary: metal.secondary, background: metal.background };
            switchingSkin = true;             // no flare for a migration
            if (Skin.current === "alchemos") applyPreset(metal);
            switchingSkin = false;
        } else {
            if (!sp.legacy || al[sp.legacy.name] === undefined) sp.legacy = old;
            sp.alchemos = old;
        }
        adapter.skinPresets = sp;
        adapter.skinVersion = 4;
        applySkinVoiceDefaults();
    }
    // ── Voices per skin ─────────────────────────
    // A skin's skin.json "voices" ({ jarvis: { voice, speed, pitch }, friday: {…}, effect }) are its defaults;
    // what's set in Settings is remembered per skin (skinVoices) and comes back with the skin.
    readonly property var voiceKeys: ["jarvisVoice", "jarvisSpeed", "jarvisPitch", "fridayVoice", "fridaySpeed", "fridayPitch",
                                      "jarvisEffect", "fridayEffect"]
    function voiceRecord() {
        const r = {};
        for (const k of voiceKeys) r[k] = adapter[k];
        return r;
    }
    function voiceDefaults(v) {          // skin.json voices → settings keys (only the ones it gives)
        const r = {};
        if (!v) return r;
        for (const who of ["jarvis", "friday"]) {
            const p = v[who] || {};
            if (p.voice) r[who + "Voice"] = p.voice;
            if (typeof p.speed === "number") r[who + "Speed"] = p.speed;
            if (typeof p.pitch === "number") r[who + "Pitch"] = p.pitch;
            if (typeof p.effect === "string") r[who + "Effect"] = p.effect;     // per persona
        }
        if (v.effect && !r.jarvisEffect) r.jarvisEffect = v.effect;               // one for both
        if (v.effect && r.fridayEffect === undefined) r.fridayEffect = "";
        return r;
    }
    function applyVoices(r) {
        if (r.fridayEffect === undefined) r = Object.assign({ fridayEffect: "" }, r);   // records from before it existed: SAME
        for (const k of voiceKeys) if (r[k] !== undefined && adapter[k] !== r[k]) adapter[k] = r[k];
    }
    // The skin in use has no remembered voices yet but brings defaults: apply them once and remember them
    function applySkinVoiceDefaults() {
        const r = Skin.resolved;              // the id and its skin.json together (never one skin's id with another's data)
        if (r.id === "base") return;
        const sv = adapter.skinVoices || {};
        if (sv[r.id]) return;
        const d = voiceDefaults(r.own.voices);
        if (Object.keys(d).length === 0) return;
        applyVoices(d);
        adapter.skinVoices = Object.assign({}, sv, { [r.id]: voiceRecord() });
    }
    Connections { target: Skin; function onResolvedChanged() { if (root.loaded && adapter.skinVersion >= 3) root.applySkinVoiceDefaults(); } }

    function switchSkin(from, to) {
        const sv = Object.assign({}, adapter.skinVoices || {});
        sv[from] = voiceRecord();
        adapter.skinVoices = sv;
        if (sv[to]) applyVoices(sv[to]);       // else the new skin's defaults, once its file is read (onDataChanged)

        const sp = Object.assign({}, adapter.skinPresets || {});
        sp[from] = lookRecord();
        adapter.skinPresets = sp;
        adapter.skin = to;                    // Skin.presets follows once the skin's file is read
        const builtins = Skin.presetsOf(to);
        switchingSkin = true;
        applyRecord(sp[to], builtins[0], builtins);
        switchingSkin = false;
    }


    // Saves the colours currently applied (with an optional glyph, e.g. the namer's). "" on success, else the reason.
    function savePreset(raw, glyph) {
        const name = presetName(raw);
        if (name === "") return "Give it a name";
        if (isBuiltin(name) || name === "CUSTOM") return name + " is a built-in name";
        const entry = { name: name };
        if (glyph) entry.glyph = String(glyph);
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
    readonly property string lockMonitors: Quickshell.screens.map(s => s.name + ":" + Roles.role(s) + ":" + s.height).join(" ") + " " + Skin.current
    onLockMonitorsChanged: hyprSync.restart()
    function lockConf() {
        const t = lockTemplate.text();
        if (!t) return "";
        const back = "rgb(" + hex(bg) + ")";
        const blocks = ["background {\n    monitor =\n    color = " + back + "\n}"];
        let main = "", mainH = 0;
        for (const s of Quickshell.screens) {
            if (Roles.role(s) === "main") { main = s.name; mainH = s.height; }
            blocks.push("background {\n    monitor = " + s.name + "\n    path = " + LockState.bgPath(s.name) +
                        "\n    color = " + back + "\n}");
        }
        // One pass, so a colour that's swapped in (SOLAR's primary is STARK's secondary)
        // isn't swapped again. 8fb4c4 = muted text (placeholder, battery) → the HUD's label colour.
        // __Y_*__: where the words sit on the main screen (Style.lockLayout: clear of the skin's seal there;
        // with no main screen they show on every screen, so the smallest decides).
        const h = mainH || Math.min(...Quickshell.screens.map(s => s.height));
        const txt = Skin.text;
        const swap = { "4fd8ff": hex(primary), "ffb347": hex(secondary), "05090f": hex(bg), "8fb4c4": hex(dim),
                       "__HOME__": Quickshell.env("HOME"), "__BACKGROUNDS__": blocks.join("\n"), "__MAIN__": main,
                       "__LOCKTITLE__": txt.lockTitle, "__DENIED__": txt.denied,
                       "__FONT_LABEL__": Style.fonts.label, "__FONT_NUMERIC__": Style.fonts.numeric, "__FONT_FIELD__": Style.fonts.field,
                       "__LOCKPROMPT__": txt.lockPrompt, "__FP_READY__": txt.fprintReady, "__FP_PRESENT__": txt.fprintPresent,
                       "__Y_TITLE__": Style.lockY("title", h), "__Y_CLOCK__": Style.lockY("clock", h), "__Y_DATE__": Style.lockY("date", h),
                       "__Y_FIELD__": Style.lockY("field", h), "__Y_PROMPT__": Style.lockY("prompt", h),
                       "__BATTERY_POS__": Style.lockLayout.battery.join(", ") };
        return t.replace(new RegExp(Object.keys(swap).join("|"), "g"), m => String(swap[m]));
    }
    function pushLockConf() {
        const conf = lockConf();
        if (conf === "") return;
        Quickshell.execDetached(["sh", "-c",
            "d=~/.config/hypr; printf '%s' \"$1\" > $d/.hyprlock.tmp && mv $d/.hyprlock.tmp $d/hyprlock.conf",
            "sh", conf]);
    }
    // ── Kitty ───────────────────────────────────
    // Writes ~/.config/kitty/alchemos-theme.conf (included from kitty.conf) and
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
            "d=~/.config/kitty; mkdir -p $d && printf '%s' \"$1\" > $d/.alchemos-theme.tmp && mv $d/.alchemos-theme.tmp $d/alchemos-theme.conf && pkill -USR1 -x kitty",
            "sh", kittyConf()]);
    }

    // ── Heroic ──────────────────────────────────
    // Writes ~/.config/heroic/themes/alchemos.css (Heroic's custom theme "alchemos",
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
            "d=~/.config/heroic; [ -d $d ] || exit 0; mkdir -p $d/themes && printf '%s' \"$1\" > $d/themes/.alchemos.tmp && mv $d/themes/.alchemos.tmp $d/themes/alchemos.css",
            "sh", heroicCss()]);
    }

    // ── VS Code ─────────────────────────────────
    // alchemos-code-theme merges just these two keys into ~/.config/Code/User/settings.json;
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
        Quickshell.execDetached(["alchemos-code-theme", codeTheme()]);
    }

    // ── Ambient lights (Govee strip) ────────────
    function pushToGovee() {
        Quickshell.execDetached(["alchemos-govee", "theme", hex(primary), hex(secondary)]);
    }

    // ── Cursor ──────────────────────────────────
    // ~/.config/alchemos-cursor/build.sh renders the ALCHEMOS cursor theme in the accent
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
        cursorBuild.command = [Quickshell.env("HOME") + "/.config/alchemos-cursor/build.sh", hex(primary),
            cursorAnimated ? "animated" : "static", String(cursorStep(0)), String(cursorFill()),
            Skin.cursorDir];          // the skin's busy-cursor templates ("" = the default art)
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
    Connections { target: Skin; function onCursorDirChanged() { cursorSync.restart(); } }
    onLoadedChanged: { if (loaded) migrateSkins(); cursorSync.restart(); }
    // External pushes wait for a skin / ignite animation to end (IgniteState.busy), then go out one
    // after another (pushQueue), so a theme change never stalls the animation: hyprctl, kitty's
    // SIGUSR1, VS Code reloading its settings and the cursor build all compete for the CPU. The Govee
    // command goes at once: the strip's own wipe should run alongside the HUD's.
    property var pushQueue: []
    function push(fn) {
        if (pushQueue.indexOf(fn) < 0) pushQueue = pushQueue.concat([fn]);
        if (!IgniteState.busy && !pushRunner.running) pushRunner.start();
    }
    Timer {
        id: pushRunner
        interval: 120                 // a little air between pushes
        repeat: true
        onTriggered: {
            if (IgniteState.busy) { stop(); return; }
            if (root.pushQueue.length === 0) { stop(); return; }
            const fn = root.pushQueue[0];
            root.pushQueue = root.pushQueue.slice(1);
            fn();
        }
    }
    Connections { target: IgniteState; function onBusyChanged() { if (!IgniteState.busy && root.pushQueue.length) pushRunner.start(); } }
    Timer { id: hyprSync; interval: 300; onTriggered: root.push(root.pushToHyprland) }
    Timer { id: kittySync; interval: 300; onTriggered: root.push(root.pushToKitty) }
    Timer { id: heroicSync; interval: 300; onTriggered: root.push(root.pushToHeroic) }
    Timer { id: codeSync; interval: 300; onTriggered: root.push(root.pushToCode) }
    Timer { id: goveeSync; interval: 300; onTriggered: root.pushToGovee() }
    Timer { id: cursorSync; interval: 600; onTriggered: root.push(root.pushCursor) }   // longer: a cold build is ~1 s
    Component.onCompleted: { hyprSync.restart(); kittySync.restart(); heroicSync.restart(); codeSync.restart(); goveeSync.restart(); }
    // `hyprctl reload` resets border colors → push them again
    Connections {
        target: Hyprland
        function onRawEvent(event) { if (event.name === "configreloaded") { hyprSync.restart(); cursorSync.restart(); } }
    }
}
