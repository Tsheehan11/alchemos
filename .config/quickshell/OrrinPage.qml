// Settings → the assistant (tab id ORRIN; the label is the skin's assistant name). Moved out of
// Settings.qml and split into sub-pages: GENERAL · VOICES · LISTENING · DECISIONS · CONNECTIONS · PRIVACY.
// Every control is the one that was there before (same Theme.cfg keys and commands).
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import "Hypr.js" as Hypr

Column {
    id: orrinPage
    spacing: 12

    readonly property var subs: ["GENERAL", "VOICES", "LISTENING", "DECISIONS", "CONNECTIONS", "PRIVACY"]
    property string sub: "GENERAL"
    // a section title, as on the other settings pages
    component Title: Text { topPadding: 6; color: Theme.dim; font.family: Style.fonts.display; font.pixelSize: Style.display !== Style.mono ? 13 : 11; font.letterSpacing: 3 }
    component Section: Column { width: orrinPage.width; spacing: 12 }

    readonly property var models: ["auto", "haiku", "sonnet", "opus"]
    readonly property var modelHints: ({ auto: "Haiku · Sonnet for harder questions", haiku: "Fastest", sonnet: "Smarter, a little slower", opus: "Strongest, slowest · uses the plan fastest" })
    readonly property var follows: [0, 4, 6, 8, 10, 15]
    property var voices: ["bm_george"]
    property var femaleVoices: ["bf_emma"]  // SELENE: English female Kokoro voices (orrin-voices --list)
    property var effects: ["AUTO", "CLEAN", "HOLOGRAM", "SUIT"]
    // AUTO: what the skin's routing picks for each output (core/effects.py routing())
    function autoHint(who) {
        const r = Skin.voiceRouting(who);
        return "Headphones " + r.headphones + " · speakers " + r.speaker + " · Bluetooth speaker " + r.btSpeaker;
    }
    readonly property var effectHints: ({ AUTO: autoHint("orrin"), CLEAN: "No processing",
        HOLOGRAM: "Warm EQ, small room, faint chorus", SUIT: "Narrower, radio-like, inside the helmet",
        CHAMBER: "A small stone room: warm, a little hard-walled", RESONANT: "A faint metallic ring under the voice",
        ALEMBIC: "Band-limited, glassy, a very short echo",
        CHAMBER_SUBTLE: "CHAMBER at a quarter of the colour", RESONANT_SUBTLE: "RESONANT at a quarter of the colour",
        ALEMBIC_SUBTLE: "ALEMBIC at a quarter of the colour, full band" })
    function seleneFx(dir) {
        const v = cycle(["SAME"].concat(effects), Theme.cfg.seleneEffect || "SAME", dir);
        return v === "SAME" ? "" : v;
    }
    property var speakers: []          // [{mac, name}] paired Bluetooth speakers (not headphones)
    property var integrations: []      // `orrin integrations --json`: [{key, name, label, auth, connected, state, detail}]
    property var spotify: ({})         // `orrin spotify status --json`: {connected, user, premium, client, missing, detail}
    property var djMoods: []           // preset names from ~/.config/orrin/dj_moods.json + saved ones
    property var router: ({})          // `orrin router stats --json` (core/router_learn.py)
    function speakerName(mac) { const s = speakers.find(x => x.mac === mac); return mac === "" ? "OFF" : (s ? s.name : mac).toUpperCase(); }
    function voiceName(v) {
        if (/^[a-z][fm]_/.test(v)) return v.slice(3).toUpperCase() + (v[1] === "m" ? " · KOKORO" : " · KOKORO ♀");
        // "<engine>/<voice>" (core/tts): Pocket's designed voices end in a take number (orrin_2) → "ORRIN · POCKET DESIGNED"
        const m = /^([a-z0-9]+)\/(.+)$/.exec(v);
        if (m && m[1] !== "piper") return /_\d+$/.test(m[2]) ? m[2].replace(/_\d+$/, "").toUpperCase() + " · " + m[1].toUpperCase() + " DESIGNED"
                                                           : m[2].replace(/_/g, " ").toUpperCase() + " · " + m[1].toUpperCase();
        return v.replace(/^en_GB-/, "").replace(/-(medium|low|high)/, "").replace(/_/g, " ").replace(":", " · ").toUpperCase() + " · PIPER";
    }
    function preview() { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/orrin", "--say", "Good evening, sir. All systems are online.", "--as", "orrin"]); }
    function previewSelene() { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/orrin", "--say", OrrinState.nameOf("selene") + " here. All is quiet and well.", "--as", "selene"]); }
    function cycle(list, cur, dir) { const i = list.indexOf(cur); return list[((i < 0 ? 0 : i) + dir + list.length) % list.length]; }
    onVisibleChanged: if (visible) voiceList.running = true
    Process {
        id: voiceList
        command: [Quickshell.env("HOME") + "/.local/bin/orrin-voices", "--list"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const d = JSON.parse(text);
                    if (d.voices.length) orrinPage.voices = d.voices;
                    if ((d.female || []).length) orrinPage.femaleVoices = d.female;
                    if (d.effects.length) orrinPage.effects = d.effects;
                    orrinPage.speakers = d.speakers || [];
                } catch (e) {}
            }
        }
    }

    readonly property var micChoices: ["auto", "default"].concat(Audio.inputs.map(n => n.name))
    function micName(v) {
        if (v === "auto" || v === "") return v === "" ? "SYSTEM DEFAULT" : "AUTO";
        if (v === "default") return "SYSTEM DEFAULT";
        const n = Audio.inputs.find(x => x.name === v);
        return (n ? Audio.label(n).replace(/^.*Controller\s+/, "") : v + " (unplugged)").toUpperCase();
    }
    Process {
        id: routerStats
        command: [Quickshell.env("HOME") + "/.local/bin/orrin", "router", "stats", "--json"]
        stdout: StdioCollector { onStreamFinished: { try { orrinPage.router = JSON.parse(text); } catch (e) {} } }
    }
    Timer { id: routerRefresh; interval: 1500; onTriggered: routerStats.running = true }
    function routerCmd(args) { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/orrin", "router"].concat(args)); routerRefresh.interval = args[0] === "approve" ? 6000 : 800; routerRefresh.restart(); }
    function evAge(ts) { const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 60 ? m + "M" : m < 1440 ? Math.round(m / 60) + "H" : Math.round(m / 1440) + "D"; }
    // Phase-2 integrations: entries in ~/.config/orrin/servers.json, tokens in the system keyring.
    // CONNECT opens a terminal running the sign-in flow (`orrin connect …`).
    Process {
        id: integrationList
        command: [Quickshell.env("HOME") + "/.local/bin/orrin", "integrations", "--json"]
        stdout: StdioCollector { onStreamFinished: { try { orrinPage.integrations = JSON.parse(text); } catch (e) {} } }
    }
    Timer { interval: 4000; repeat: true; triggeredOnStart: true; running: orrinPage.visible; onTriggered: { integrationList.running = true; spotifyStatus.running = true; if (Theme.cfg.orrinDecisions === "local") routerStats.running = true; } }
    // Spotify: his own developer app, PKCE sign-in, tokens in the keyring (~/.config/orrin/mcp/spotify_api.py);
    // DJ mode runs in the voice process (~/.config/orrin/core/dj.py).
    Process {
        id: spotifyStatus
        command: [Quickshell.env("HOME") + "/.local/bin/orrin", "spotify", "status", "--json"]
        stdout: StdioCollector { onStreamFinished: { try { orrinPage.spotify = JSON.parse(text); } catch (e) {} } }
    }
    FileView {
        path: Quickshell.env("HOME") + "/.config/orrin/dj_moods.json"
        watchChanges: true; onFileChanged: reload()
        onLoaded: { try { orrinPage.djMoods = Object.keys(JSON.parse(text()).moods || {}); } catch (e) {} }
    }
    FileView {
        id: savedMoods
        property var names: []
        path: Quickshell.env("HOME") + "/.local/share/orrin/dj/moods.json"
        watchChanges: true; onFileChanged: reload(); printErrors: false
        onLoaded: { try { names = Object.keys(JSON.parse(text())); } catch (e) {} }
    }
    Timer { id: volumePreview; interval: 450; onTriggered: orrinPage.preview() }   // speak once the slider settles

    // sub-page picker
    Flow {
        width: parent.width; spacing: 8
        Repeater {
            model: orrinPage.subs
            delegate: SmallButton { required property string modelData; text: modelData; active: orrinPage.sub === modelData; onClicked: orrinPage.sub = modelData }
        }
    }
    Rectangle { width: parent.width; height: 1; color: Theme.p(0.18) }

    // ── GENERAL ──
    Section {
        visible: orrinPage.sub === "GENERAL"
        Toggle { width: parent.width; label: OrrinState.callOf("orrin"); hint: (!OrrinState.toggleOn ? (OrrinState.docked ? "Off" : "Off on the laptop · switch on for now (until the next dock change)") : OrrinState.laptopMode ? "On (laptop, until dock change) · no academic sync, watchers or room speaker; stops under 20 % on battery" : OrrinState.paused ? "On · paused for combat mode" : OrrinState.online ? "On · listening for " + ((OrrinFeed.status.wake || []).indexOf("selene") >= 0 ? "\"hey Orrin\" / \"hey Selene\"" : "\"hey Jarvis\"") : "On · starting…"); checked: OrrinState.toggleOn; onToggled: OrrinState.toggle() }
        // PERSONA: who answers by default. Same brain, tools, memory and threads; SELENE has her own voice
        // and manner. "hey Selene" wakes SELENE when its wake model is installed (OrrinFeed.status.wake);
        // "hey Jarvis" (openWakeWord's built-in model) is the fallback for both.
        Stepper {
            width: parent.width; label: "Persona"
            hint: (OrrinFeed.status.wake || []).indexOf("selene") >= 0
                  ? "Who answers by default · \"hey Orrin\" and \"hey Selene\" each wake their own"
                  : "Who answers by default · both answer \"hey Jarvis\" (no \"hey Selene\" model yet)"
            valueText: Skin.persona(OrrinState.persona).glyph + " " + OrrinState.nameOf(OrrinState.persona)
            onDec: OrrinState.setPersona(OrrinState.persona === "selene" ? "orrin" : "selene")
            onInc: OrrinState.setPersona(OrrinState.persona === "selene" ? "orrin" : "selene")
        }
        Stepper { width: parent.width; label: "Claude model"; hint: orrinPage.modelHints[Theme.cfg.orrinModel] || ""; valueText: Theme.cfg.orrinModel.toUpperCase(); onDec: Theme.cfg.orrinModel = orrinPage.cycle(orrinPage.models, Theme.cfg.orrinModel, -1); onInc: Theme.cfg.orrinModel = orrinPage.cycle(orrinPage.models, Theme.cfg.orrinModel, 1) }
        Toggle { width: parent.width; label: "Spoken replies"; hint: "Off = replies only show on the toast"; checked: Theme.cfg.orrinSpeak; onToggled: Theme.cfg.orrinSpeak = !Theme.cfg.orrinSpeak }
        Toggle { width: parent.width; label: "Lower music while speaking"; hint: "Spotify and other MPRIS players"; checked: Theme.cfg.orrinDuck; onToggled: Theme.cfg.orrinDuck = !Theme.cfg.orrinDuck }
        Toggle { width: parent.width; label: "Pause in combat mode"; hint: "Wake word off, mic released · timers still go off"; checked: Theme.cfg.gameOrrin; onToggled: Theme.cfg.gameOrrin = !Theme.cfg.gameOrrin }
        Toggle { width: parent.width; label: "Confirm sensitive actions"; hint: "Always on · power, closing windows, deleting, kill switch, messages sent as you"; checked: true; enabled: false; opacity: 0.6 }
        Title { text: "TOOLS" }
        Row {
            spacing: 10
            SmallButton { text: "TEST VOICE"; onClicked: Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/orrin", "--say", "At your service, sir."]) }
            SmallButton { text: "MISSED COMMANDS"; onClicked: { Hyprland.dispatch(Hypr.exec("kitty --hold " + Quickshell.env("HOME") + "/.local/bin/orrin --misses")); LauncherState.closeAll(); } }
            SmallButton { text: "EDIT " + OrrinState.assistant; onClicked: { Hyprland.dispatch(Hypr.exec("kate ~/.config/orrin")); LauncherState.closeAll(); } }
        }
        Text { width: parent.width; wrapMode: Text.Wrap; text: "Claude runs on your Pro login (no API key). Memory: ~/.local/share/orrin/orrin.db"; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11 }
    }

    // ── VOICES ──
    Section {
        visible: orrinPage.sub === "VOICES"
        Title { text: OrrinState.nameOf("orrin") }
        Stepper { width: parent.width; label: "Voice"; hint: "British voices · audition them all: orrin-voices"; preview: true; onPlay: orrinPage.preview(); valueText: orrinPage.voiceName(Theme.cfg.orrinVoice); onDec: Theme.cfg.orrinVoice = orrinPage.cycle(orrinPage.voices, Theme.cfg.orrinVoice, -1); onInc: Theme.cfg.orrinVoice = orrinPage.cycle(orrinPage.voices, Theme.cfg.orrinVoice, 1) }
        Stepper { width: parent.width; label: "Speech rate"; preview: true; onPlay: orrinPage.preview(); valueText: Theme.cfg.orrinSpeed.toFixed(1) + "×"; onDec: Theme.cfg.orrinSpeed = Math.max(0.7, Math.round((Theme.cfg.orrinSpeed - 0.1) * 10) / 10); onInc: Theme.cfg.orrinSpeed = Math.min(1.5, Math.round((Theme.cfg.orrinSpeed + 0.1) * 10) / 10) }
        Stepper { width: parent.width; label: "Pitch"; hint: "Semitones, on top of the effect preset"; preview: true; onPlay: orrinPage.preview(); valueText: (Theme.cfg.orrinPitch > 0 ? "+" : "") + Theme.cfg.orrinPitch.toFixed(1); onDec: Theme.cfg.orrinPitch = Math.max(-3, Theme.cfg.orrinPitch - 0.5); onInc: Theme.cfg.orrinPitch = Math.min(2, Theme.cfg.orrinPitch + 0.5) }
        Stepper { width: parent.width; label: "Effect"; hint: orrinPage.effectHints[Theme.cfg.orrinEffect] || "Custom preset · ~/.config/orrin/effects.json"; preview: true; onPlay: orrinPage.preview(); valueText: Theme.cfg.orrinEffect; onDec: Theme.cfg.orrinEffect = orrinPage.cycle(orrinPage.effects, Theme.cfg.orrinEffect, -1); onInc: Theme.cfg.orrinEffect = orrinPage.cycle(orrinPage.effects, Theme.cfg.orrinEffect, 1) }
        Title { text: OrrinState.nameOf("selene") }
        Stepper { width: parent.width; label: "Voice"; hint: "No Irish voice in Kokoro · audition: orrin-voices --friday"; preview: true; onPlay: orrinPage.previewSelene(); valueText: orrinPage.voiceName(Theme.cfg.seleneVoice); onDec: Theme.cfg.seleneVoice = orrinPage.cycle(orrinPage.femaleVoices, Theme.cfg.seleneVoice, -1); onInc: Theme.cfg.seleneVoice = orrinPage.cycle(orrinPage.femaleVoices, Theme.cfg.seleneVoice, 1) }
        Stepper { width: parent.width; label: "Speech rate"; preview: true; onPlay: orrinPage.previewSelene(); valueText: Theme.cfg.seleneSpeed.toFixed(2) + "×"; onDec: Theme.cfg.seleneSpeed = Math.max(0.7, Math.round((Theme.cfg.seleneSpeed - 0.05) * 100) / 100); onInc: Theme.cfg.seleneSpeed = Math.min(1.6, Math.round((Theme.cfg.seleneSpeed + 0.05) * 100) / 100) }
        Stepper { width: parent.width; label: "Pitch"; hint: "Semitones, on top of the effect preset"; preview: true; onPlay: orrinPage.previewSelene(); valueText: (Theme.cfg.selenePitch > 0 ? "+" : "") + Theme.cfg.selenePitch.toFixed(1); onDec: Theme.cfg.selenePitch = Math.max(-3, Theme.cfg.selenePitch - 0.5); onInc: Theme.cfg.selenePitch = Math.min(3, Theme.cfg.selenePitch + 0.5) }
        // the second persona's own effect (seleneEffect); SAME = the one above
        Stepper {
            width: parent.width; label: "Effect"
            hint: Theme.cfg.seleneEffect === "" ? "Same as " + OrrinState.nameOf("orrin") + "'s effect" : Theme.cfg.seleneEffect === "AUTO" ? orrinPage.autoHint("selene") : (orrinPage.effectHints[Theme.cfg.seleneEffect] || "Custom preset · ~/.config/orrin/effects.json")
            preview: true; onPlay: orrinPage.previewSelene()
            valueText: Theme.cfg.seleneEffect || "SAME"
            onDec: Theme.cfg.seleneEffect = orrinPage.seleneFx(-1)
            onInc: Theme.cfg.seleneEffect = orrinPage.seleneFx(1)
        }
        Title { text: "OUTPUT" }
        Slider {
            width: parent.width
            label: "VOICE VOLUME"
            value: Theme.cfg.orrinVoiceVolume / 100
            onMoved: v => { Theme.cfg.orrinVoiceVolume = Math.round(v * 100); volumePreview.restart(); }
        }
        Text { width: parent.width; wrapMode: Text.Wrap; text: OrrinState.callOf("orrin") + "'s voice and chime only · music and other apps are untouched · the same level on headphones, speakers and Bluetooth · \"speak louder / quieter\", \"set your volume to 40 percent\""; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11 }
        Stepper { width: parent.width; label: "Speaker without headphones"; hint: "Used when the output is the laptop speakers or a monitor · headphones, headsets and USB audio keep " + OrrinState.callOf("orrin"); preview: Theme.cfg.orrinSpeaker !== ""; onPlay: orrinPage.preview(); valueText: orrinPage.speakerName(Theme.cfg.orrinSpeaker); onDec: Theme.cfg.orrinSpeaker = orrinPage.cycle([""].concat(orrinPage.speakers.map(s => s.mac)), Theme.cfg.orrinSpeaker, -1); onInc: Theme.cfg.orrinSpeaker = orrinPage.cycle([""].concat(orrinPage.speakers.map(s => s.mac)), Theme.cfg.orrinSpeaker, 1) }
        Stepper { width: parent.width; visible: Theme.cfg.orrinSpeaker !== ""; label: "Bluetooth speaker volume"; hint: OrrinState.callOf("orrin") + "'s level on the room speaker · SAME follows VOICE VOLUME"; preview: Theme.cfg.orrinSpeakerVolume >= 0; onPlay: orrinPage.preview(); valueText: Theme.cfg.orrinSpeakerVolume < 0 ? "SAME" : Theme.cfg.orrinSpeakerVolume + "%"; onDec: Theme.cfg.orrinSpeakerVolume = Theme.cfg.orrinSpeakerVolume < 0 ? -1 : Theme.cfg.orrinSpeakerVolume <= 0 ? -1 : Math.max(0, Theme.cfg.orrinSpeakerVolume - 5); onInc: Theme.cfg.orrinSpeakerVolume = Theme.cfg.orrinSpeakerVolume < 0 ? Theme.cfg.orrinVoiceVolume : Math.min(100, Theme.cfg.orrinSpeakerVolume + 5) }
    }

    // ── LISTENING ──
    Section {
        visible: orrinPage.sub === "LISTENING"
        // INPUT DEVICE: Orrin's own wake-word mic (orrin.py Mic), not the system default input
        Stepper {
            width: parent.width; label: "Input device"
            hint: (Theme.cfg.orrinMic === "auto" ? "Laptop mic; pick the headset here to use it · " : "")
                  + (OrrinFeed.mic.label ? "listening on " + OrrinFeed.mic.label : OrrinState.running ? "" : "used when " + OrrinState.callOf("orrin") + " is on")
            valueText: orrinPage.micName(Theme.cfg.orrinMic)
            onDec: Theme.cfg.orrinMic = orrinPage.cycle(orrinPage.micChoices, Theme.cfg.orrinMic === "" ? "default" : Theme.cfg.orrinMic, -1)
            onInc: Theme.cfg.orrinMic = orrinPage.cycle(orrinPage.micChoices, Theme.cfg.orrinMic === "" ? "default" : Theme.cfg.orrinMic, 1)
        }
        Stepper { width: parent.width; label: "Follow-up window"; hint: "Keeps listening after a reply, no wake word needed"; valueText: Theme.cfg.orrinFollowup > 0 ? Theme.cfg.orrinFollowup + " S" : "OFF"; onDec: Theme.cfg.orrinFollowup = orrinPage.cycle(orrinPage.follows, Theme.cfg.orrinFollowup, -1); onInc: Theme.cfg.orrinFollowup = orrinPage.cycle(orrinPage.follows, Theme.cfg.orrinFollowup, 1) }
    }

    // ── DECISIONS ──
    Section {
        visible: orrinPage.sub === "DECISIONS"
        Stepper { width: parent.width; label: "Decisions"; hint: Theme.cfg.orrinDecisions === "local" ? "Common commands decided on this PC (offline, ~5 ms) · Claude for the rest" : "Everything the regex rules miss goes to Claude"; valueText: Theme.cfg.orrinDecisions === "local" ? "LOCAL+CLAUDE" : "CLAUDE ONLY"; onDec: Theme.cfg.orrinDecisions = Theme.cfg.orrinDecisions === "local" ? "claude" : "local"; onInc: Theme.cfg.orrinDecisions = Theme.cfg.orrinDecisions === "local" ? "claude" : "local" }
        Stepper { width: parent.width; visible: Theme.cfg.orrinDecisions === "local"; label: "Local confidence"; hint: "Higher = fewer local actions, more sent to Claude · tune with tools/eval_router.py"; valueText: Theme.cfg.orrinRouterThreshold.toFixed(2); onDec: Theme.cfg.orrinRouterThreshold = Math.max(0.5, Math.round((Theme.cfg.orrinRouterThreshold - 0.01) * 100) / 100); onInc: Theme.cfg.orrinRouterThreshold = Math.min(0.95, Math.round((Theme.cfg.orrinRouterThreshold + 0.01) * 100) / 100) }
        // ROUTER: what the local router learned and how often it answers without Claude
        // (~/.config/orrin/core/router_learn.py; `orrin router stats --json`, polled with INTEGRATIONS)
        Toggle { width: parent.width; visible: Theme.cfg.orrinDecisions === "local"; label: "Ask when unsure"; hint: "A near miss gets \"Did you mean …?\" · yes runs it and teaches it, no sends it to Claude"; checked: Theme.cfg.orrinRouterAsk; onToggled: Theme.cfg.orrinRouterAsk = !Theme.cfg.orrinRouterAsk }
        Text { visible: Theme.cfg.orrinDecisions === "local"; text: "ROUTER"; topPadding: 10; color: Theme.dim; font.family: Style.fonts.display; font.pixelSize: Style.display !== Style.mono ? 13 : 11; font.letterSpacing: 3 }
        Column {
            id: routerBox
            width: parent.width; spacing: 6
            visible: Theme.cfg.orrinDecisions === "local"
            readonly property var r: orrinPage.router
            Row {
                spacing: 22
                Repeater {
                    model: [["LOCAL", "local_pct", "fast path + router + \"yes\""], ["ROUTER", "router_pct", "embedding router"], ["CLAUDE", "claude_pct", "escalated"], ["ASKED", "ask_pct", "did you mean"]]
                    delegate: Column {
                        required property var modelData
                        Text { text: (routerBox.r[modelData[1]] !== undefined ? Math.round(routerBox.r[modelData[1]]) : "—") + "%"; color: modelData[0] === "CLAUDE" ? Theme.textSoft : Theme.primary; font.family: Style.fonts.body; font.pixelSize: 20; font.weight: Font.Light }
                        Text { text: modelData[0]; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 2 }
                    }
                }
            }
            Text {
                width: parent.width; wrapMode: Text.Wrap; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11
                text: parent.r.requests === undefined ? "Reading the router log…"
                      : "Last 7 days · " + parent.r.requests + " requests · today " + parent.r.today.local_pct + "% local of " + parent.r.today.requests
                        + " · outcomes +" + parent.r.outcomes.pos + " −" + parent.r.outcomes.neg + " · asked yes " + parent.r.outcomes.ask_yes + " / no " + parent.r.outcomes.ask_no
                        + (Object.keys(parent.r.offsets || {}).length ? " · tuned: " + Object.keys(parent.r.offsets).map(k => k + " " + (parent.r.offsets[k] > 0 ? "+" : "") + parent.r.offsets[k].toFixed(2)).join(", ") : "")
            }
            readonly property var shownEvents: (r.events || []).filter(e => ["promoted", "rejected", "demoted", "deleted", "approved", "threshold", "corrected", "decayed", "forgotten"].indexOf(e.kind) >= 0).slice(0, 6)
            Text { visible: parent.shownEvents.length > 0; text: "RECENT"; topPadding: 4; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 2 }
            Repeater {
                model: parent.shownEvents
                delegate: Text {
                    required property var modelData
                    width: orrinPage.width; elide: Text.ElideRight; font.family: Style.fonts.body; font.pixelSize: 11
                    color: ["promoted", "approved"].indexOf(modelData.kind) >= 0 ? Theme.primary : ["rejected", "demoted", "deleted", "corrected"].indexOf(modelData.kind) >= 0 ? Theme.secondary : Theme.textSoft
                    text: orrinPage.evAge(modelData.ts) + "  " + modelData.kind.toUpperCase() + "  " + (modelData.text ? "\"" + modelData.text + "\" → " : "") + modelData.intent + (modelData.why ? " · " + modelData.why : "")
                }
            }
            Text { visible: (parent.r.review || []).length > 0; text: "LEARNED · REVIEW"; topPadding: 4; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 2 }
            Text { visible: parent.r.review !== undefined && parent.r.review.length === 0; text: "Nothing learned yet · it learns from Claude's simple answers, your corrections and \"yes\" to \"Did you mean…\""; width: orrinPage.width; wrapMode: Text.Wrap; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11 }
            Repeater {
                // waiting on you first (candidates, rejections), then what's live
                model: (parent.r.review || []).slice().sort((a, b) => (a.state === "active") - (b.state === "active")).slice(0, 14)
                delegate: Item {
                    required property var modelData
                    width: orrinPage.width; height: 40
                    Column {
                        anchors.left: parent.left; anchors.right: reviewBtns.left; anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Text { width: parent.width; elide: Text.ElideRight; text: "\"" + modelData.text + "\"  →  " + modelData.intent; color: modelData.state === "active" ? Theme.text : Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 12 }
                        Text {
                            width: parent.width; elide: Text.ElideRight; font.family: Style.fonts.body; font.pixelSize: 10
                            color: modelData.state === "rejected" ? Theme.secondary : Theme.dim
                            text: modelData.state.toUpperCase() + " · #" + modelData.id + " · " + modelData.source + " · seen " + modelData.seen + " · +" + modelData.pos + " −" + modelData.neg + (modelData.why ? " · " + modelData.why : "")
                        }
                    }
                    Row {
                        id: reviewBtns
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        spacing: 8
                        SmallButton { visible: modelData.state !== "active"; text: "APPROVE"; onClicked: orrinPage.routerCmd(["approve", modelData.id]) }
                        ConfirmButton { label: "REMOVE"; onConfirmed: orrinPage.routerCmd(["forget", modelData.id]) }
                    }
                }
            }
            Text {
                width: orrinPage.width; wrapMode: Text.Wrap; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1
                text: "APPROVE still has to pass the router eval (0 wrong actions) · learned data stays in ~/.local/share/orrin · orrin router stats | review | forget ID | reset-learned"
            }
        }
    }

    // ── CONNECTIONS ──
    Section {
        visible: orrinPage.sub === "CONNECTIONS"
        // Phase-2 integrations: entries in ~/.config/orrin/servers.json, tokens in the system keyring.
        // CONNECT opens a terminal running the sign-in flow (`orrin connect …`).
        Title { text: "INTEGRATIONS" }
        Repeater {
            model: orrinPage.integrations
            delegate: Item {
                required property var modelData
                width: orrinPage.width; height: 52
                Column {
                    anchors.left: parent.left; anchors.right: connectBtn.left; anchors.rightMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 3
                    Row {
                        spacing: 10
                        Text { text: modelData.name; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 14 }
                        Text {
                            text: modelData.state
                            color: modelData.connected ? Theme.primary : Theme.dim
                            font.family: Style.fonts.body; font.pixelSize: 11; font.letterSpacing: 2
                        }
                    }
                    Text { width: parent.width; elide: Text.ElideRight; text: modelData.label + " · " + modelData.detail; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11 }
                }
                SmallButton {
                    id: connectBtn
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    text: modelData.connected ? "RECONNECT" : modelData.optional ? "SET UP" : "CONNECT"
                    active: modelData.connected
                    opacity: modelData.optional && !modelData.connected ? 0.6 : 1
                    onClicked: { Hyprland.dispatch(Hypr.exec("kitty --hold " + Quickshell.env("HOME") + "/.local/bin/orrin connect " + modelData.auth)); LauncherState.closeAll(); }
                }
            }
        }
        Title { text: "COURSEWORK" }
        Toggle { width: parent.width; label: "Auto-update tracker"; hint: Theme.cfg.orrinAutoUpdateTracker ? "Grades, new LEARN work and moved deadlines go into your SE tracker and are announced · \"orrin tracker undo\" reverts the last write" : "Each tracker update is offered first, spoken and on the HUD · your own requests always ask"; checked: Theme.cfg.orrinAutoUpdateTracker; onToggled: Theme.cfg.orrinAutoUpdateTracker = !Theme.cfg.orrinAutoUpdateTracker }
        Toggle { width: parent.width; label: "Auto-add assignments"; hint: "Fallback while no tracker sheet is set up · LEARN due dates go into \"STARK – Assignments\" without asking · that calendar only, never your main one"; checked: Theme.cfg.orrinAutoAddAssignments; onToggled: Theme.cfg.orrinAutoAddAssignments = !Theme.cfg.orrinAutoAddAssignments }
        Stepper { width: parent.width; label: "Assignments calendar"; hint: "Account that holds \"STARK – Assignments\""; valueText: Theme.cfg.orrinAssignmentsAccount === "microsoft" ? "OUTLOOK" : "GOOGLE"; onDec: Theme.cfg.orrinAssignmentsAccount = Theme.cfg.orrinAssignmentsAccount === "microsoft" ? "google" : "microsoft"; onInc: Theme.cfg.orrinAssignmentsAccount = Theme.cfg.orrinAssignmentsAccount === "microsoft" ? "google" : "microsoft" }
        Title { text: "SPOTIFY" }
        Item {
            width: orrinPage.width; height: 52
            Column {
                anchors.left: parent.left; anchors.right: spotifyBtns.left; anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                spacing: 3
                Row {
                    spacing: 10
                    Text { text: "Spotify"; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 14 }
                    Text {
                        text: orrinPage.spotify.connected ? "CONNECTED" : "NOT CONNECTED"
                        color: orrinPage.spotify.connected ? Theme.primary : Theme.dim
                        font.family: Style.fonts.body; font.pixelSize: 11; font.letterSpacing: 2
                    }
                }
                Text {
                    width: parent.width; elide: Text.ElideRight
                    text: (orrinPage.spotify.user ? orrinPage.spotify.user + " · " : "") + (orrinPage.spotify.detail || "Your own developer app · CONNECT walks you through it")
                    color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11
                }
            }
            Row {
                id: spotifyBtns
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                ConfirmButton {
                    visible: orrinPage.spotify.connected === true
                    label: "DISCONNECT"
                    onConfirmed: { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/orrin", "spotify", "disconnect"]); spotifyStatus.running = true; }
                }
                SmallButton {
                    text: orrinPage.spotify.connected ? "RECONNECT" : "CONNECT"
                    active: orrinPage.spotify.connected === true
                    onClicked: { Hyprland.dispatch(Hypr.exec("kitty --hold " + Quickshell.env("HOME") + "/.local/bin/orrin spotify connect")); LauncherState.closeAll(); }
                }
            }
        }
        Stepper {
            width: parent.width; label: "DJ chatter"
            hint: ({ off: "DJ mode never talks between tracks", rare: "A short line every 4–5 tracks, music ducked under it", normal: "A short line every 2–3 tracks" })[Theme.cfg.orrinDjChatter] || ""
            valueText: Theme.cfg.orrinDjChatter.toUpperCase()
            onDec: Theme.cfg.orrinDjChatter = orrinPage.cycle(["off", "rare", "normal"], Theme.cfg.orrinDjChatter, -1)
            onInc: Theme.cfg.orrinDjChatter = orrinPage.cycle(["off", "rare", "normal"], Theme.cfg.orrinDjChatter, 1)
        }
        Text {
            width: parent.width; wrapMode: Text.Wrap
            text: "MOODS · " + orrinPage.djMoods.concat(savedMoods.names).join(" · ").toUpperCase()
                  + "\nSay \"DJ for me\", \"play something for studying\", \"more / less like this\", \"save this vibe as …\""
            color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11; lineHeight: 1.3
        }
        Text {
            width: parent.width; wrapMode: Text.Wrap
            text: "CROSSFADE · Spotify's API can't set it: Spotify → Settings → Playback → Crossfade songs (6–8 s suits DJ mode)"
            color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11
        }
    }

    // ── PRIVACY ──
    Section {
        visible: orrinPage.sub === "PRIVACY"
        Title { text: "WINDOW READING" }
        Stepper { width: parent.width; label: "Watch every"; hint: "How often a watcher looks at its window · compared on this machine, Claude only looks when enough changed"; valueText: Theme.cfg.orrinWatchInterval + " S"; onDec: Theme.cfg.orrinWatchInterval = Math.max(3, Theme.cfg.orrinWatchInterval - (Theme.cfg.orrinWatchInterval > 30 ? 10 : Theme.cfg.orrinWatchInterval > 10 ? 5 : 1)); onInc: Theme.cfg.orrinWatchInterval = Math.min(300, Theme.cfg.orrinWatchInterval + (Theme.cfg.orrinWatchInterval >= 30 ? 10 : Theme.cfg.orrinWatchInterval >= 10 ? 5 : 1)) }
        Column {
            width: parent.width; spacing: 4
            Text { text: "Never read or watch (window titles / apps, comma-separated · Enter to save)"; color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 12 }
            Rectangle {
                width: parent.width; height: Math.max(32, blockIn.contentHeight + 14)
                color: Theme.d(0.9)
                border.color: blockIn.activeFocus ? Theme.primary : Theme.p(0.4)
                TextEdit {
                    id: blockIn
                    anchors.fill: parent; anchors.margins: 7
                    wrapMode: TextEdit.Wrap
                    color: Theme.text; selectByMouse: true
                    font.family: Style.fonts.body; font.pixelSize: 12
                    text: (Theme.cfg.orrinCaptureBlocklist || []).join(", ")
                    function save() {
                        const terms = text.split(/[,\n]/).map(t => t.trim().toLowerCase()).filter(t => t !== "");
                        Theme.cfg.orrinCaptureBlocklist = terms.filter((t, i) => terms.indexOf(t) === i);
                        text = Theme.cfg.orrinCaptureBlocklist.join(", ");
                    }
                    Keys.onReturnPressed: { save(); focus = false; }
                    Keys.onEnterPressed: { save(); focus = false; }
                    onActiveFocusChanged: if (!activeFocus) save()
                }
            }
            Text { width: parent.width; wrapMode: Text.Wrap; text: "Always refused, whatever this says: the lock screen, password / permission / keyring prompts and password managers. " + OrrinState.callOf("orrin") + " only reads a window you name; captures stay in memory, never on disk, and what's on screen is data, never an instruction."; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11 }
        }
        Text { width: parent.width; wrapMode: Text.Wrap; text: "Read-only by default. Sending, creating, deleting or editing anything needs your spoken yes. Email, calendar and document text is treated as data, never as commands. Setup: ~/.config/orrin/docs"; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11 }
    }

}
