// Settings → the assistant (tab id JARVIS; the label is the skin's assistant name). Moved out of
// Settings.qml and split into sub-pages: GENERAL · VOICES · LISTENING · DECISIONS · CONNECTIONS · PRIVACY.
// Every control is the one that was there before (same Theme.cfg keys and commands).
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import "Hypr.js" as Hypr

Column {
    id: jarvisPage
    spacing: 12

    readonly property var subs: ["GENERAL", "VOICES", "LISTENING", "DECISIONS", "CONNECTIONS", "PRIVACY"]
    property string sub: "GENERAL"
    // a section title, as on the other settings pages
    component Title: Text { topPadding: 6; color: Theme.dim; font.family: Style.fonts.display; font.pixelSize: Style.display !== Style.mono ? 13 : 11; font.letterSpacing: 3 }
    component Section: Column { width: jarvisPage.width; spacing: 12 }

    readonly property var models: ["auto", "haiku", "sonnet", "opus"]
    readonly property var modelHints: ({ auto: "Haiku · Sonnet for harder questions", haiku: "Fastest", sonnet: "Smarter, a little slower", opus: "Strongest, slowest · uses the plan fastest" })
    readonly property var follows: [0, 4, 6, 8, 10, 15]
    property var voices: ["bm_george"]
    property var femaleVoices: ["bf_emma"]  // FRIDAY: English female Kokoro voices (jarvis-voices --list)
    property var effects: ["AUTO", "CLEAN", "HOLOGRAM", "SUIT"]
    // AUTO: what the skin's routing picks for each output (core/effects.py routing())
    function autoHint(who) {
        const r = Skin.voiceRouting(who);
        return "Headphones " + r.headphones + " · speakers " + r.speaker + " · Bluetooth speaker " + r.btSpeaker;
    }
    readonly property var effectHints: ({ AUTO: autoHint("jarvis"), CLEAN: "No processing",
        HOLOGRAM: "Warm EQ, small room, faint chorus", SUIT: "Narrower, radio-like, inside the helmet",
        CHAMBER: "A small stone room: warm, a little hard-walled", RESONANT: "A faint metallic ring under the voice",
        ALEMBIC: "Band-limited, glassy, a very short echo",
        CHAMBER_SUBTLE: "CHAMBER at a quarter of the colour", RESONANT_SUBTLE: "RESONANT at a quarter of the colour",
        ALEMBIC_SUBTLE: "ALEMBIC at a quarter of the colour, full band" })
    function fridayFx(dir) {
        const v = cycle(["SAME"].concat(effects), Theme.cfg.fridayEffect || "SAME", dir);
        return v === "SAME" ? "" : v;
    }
    property var speakers: []          // [{mac, name}] paired Bluetooth speakers (not headphones)
    property var integrations: []      // `jarvis integrations --json`: [{key, name, label, auth, connected, state, detail}]
    property var spotify: ({})         // `jarvis spotify status --json`: {connected, user, premium, client, missing, detail}
    property var djMoods: []           // preset names from ~/.config/jarvis/dj_moods.json + saved ones
    property var router: ({})          // `jarvis router stats --json` (core/router_learn.py)
    function speakerName(mac) { const s = speakers.find(x => x.mac === mac); return mac === "" ? "OFF" : (s ? s.name : mac).toUpperCase(); }
    function voiceName(v) {
        if (/^[a-z][fm]_/.test(v)) return v.slice(3).toUpperCase() + (v[1] === "m" ? " · KOKORO" : " · KOKORO ♀");
        // "<engine>/<voice>" (core/tts): Pocket's designed voices end in a take number (orrin_2) → "ORRIN · POCKET DESIGNED"
        const m = /^([a-z0-9]+)\/(.+)$/.exec(v);
        if (m && m[1] !== "piper") return /_\d+$/.test(m[2]) ? m[2].replace(/_\d+$/, "").toUpperCase() + " · " + m[1].toUpperCase() + " DESIGNED"
                                                           : m[2].replace(/_/g, " ").toUpperCase() + " · " + m[1].toUpperCase();
        return v.replace(/^en_GB-/, "").replace(/-(medium|low|high)/, "").replace(/_/g, " ").replace(":", " · ").toUpperCase() + " · PIPER";
    }
    function preview() { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/jarvis", "--say", "Good evening, sir. All systems are online.", "--as", "jarvis"]); }
    function previewFriday() { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/jarvis", "--say", "Hey boss, " + JarvisState.nameOf("friday") + " here. All systems are green.", "--as", "friday"]); }
    function cycle(list, cur, dir) { const i = list.indexOf(cur); return list[((i < 0 ? 0 : i) + dir + list.length) % list.length]; }
    onVisibleChanged: if (visible) voiceList.running = true
    Process {
        id: voiceList
        command: [Quickshell.env("HOME") + "/.local/bin/jarvis-voices", "--list"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const d = JSON.parse(text);
                    if (d.voices.length) jarvisPage.voices = d.voices;
                    if ((d.female || []).length) jarvisPage.femaleVoices = d.female;
                    if (d.effects.length) jarvisPage.effects = d.effects;
                    jarvisPage.speakers = d.speakers || [];
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
        command: [Quickshell.env("HOME") + "/.local/bin/jarvis", "router", "stats", "--json"]
        stdout: StdioCollector { onStreamFinished: { try { jarvisPage.router = JSON.parse(text); } catch (e) {} } }
    }
    Timer { id: routerRefresh; interval: 1500; onTriggered: routerStats.running = true }
    function routerCmd(args) { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/jarvis", "router"].concat(args)); routerRefresh.interval = args[0] === "approve" ? 6000 : 800; routerRefresh.restart(); }
    function evAge(ts) { const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 60 ? m + "M" : m < 1440 ? Math.round(m / 60) + "H" : Math.round(m / 1440) + "D"; }
    // Phase-2 integrations: entries in ~/.config/jarvis/servers.json, tokens in the system keyring.
    // CONNECT opens a terminal running the sign-in flow (`jarvis connect …`).
    Process {
        id: integrationList
        command: [Quickshell.env("HOME") + "/.local/bin/jarvis", "integrations", "--json"]
        stdout: StdioCollector { onStreamFinished: { try { jarvisPage.integrations = JSON.parse(text); } catch (e) {} } }
    }
    Timer { interval: 4000; repeat: true; triggeredOnStart: true; running: jarvisPage.visible; onTriggered: { integrationList.running = true; spotifyStatus.running = true; if (Theme.cfg.jarvisDecisions === "local") routerStats.running = true; } }
    // Spotify: his own developer app, PKCE sign-in, tokens in the keyring (~/.config/jarvis/mcp/spotify_api.py);
    // DJ mode runs in the voice process (~/.config/jarvis/core/dj.py).
    Process {
        id: spotifyStatus
        command: [Quickshell.env("HOME") + "/.local/bin/jarvis", "spotify", "status", "--json"]
        stdout: StdioCollector { onStreamFinished: { try { jarvisPage.spotify = JSON.parse(text); } catch (e) {} } }
    }
    FileView {
        path: Quickshell.env("HOME") + "/.config/jarvis/dj_moods.json"
        watchChanges: true; onFileChanged: reload()
        onLoaded: { try { jarvisPage.djMoods = Object.keys(JSON.parse(text()).moods || {}); } catch (e) {} }
    }
    FileView {
        id: savedMoods
        property var names: []
        path: Quickshell.env("HOME") + "/.local/share/jarvis/dj/moods.json"
        watchChanges: true; onFileChanged: reload(); printErrors: false
        onLoaded: { try { names = Object.keys(JSON.parse(text())); } catch (e) {} }
    }
    Timer { id: volumePreview; interval: 450; onTriggered: jarvisPage.preview() }   // speak once the slider settles

    // sub-page picker
    Flow {
        width: parent.width; spacing: 8
        Repeater {
            model: jarvisPage.subs
            delegate: SmallButton { required property string modelData; text: modelData; active: jarvisPage.sub === modelData; onClicked: jarvisPage.sub = modelData }
        }
    }
    Rectangle { width: parent.width; height: 1; color: Theme.p(0.18) }

    // ── GENERAL ──
    Section {
        visible: jarvisPage.sub === "GENERAL"
        Toggle { width: parent.width; label: JarvisState.callOf("jarvis"); hint: (!JarvisState.toggleOn ? (JarvisState.docked ? "Off" : "Off on the laptop · switch on for now (until the next dock change)") : JarvisState.laptopMode ? "On (laptop, until dock change) · no academic sync, watchers or room speaker; stops under 20 % on battery" : JarvisState.paused ? "On · paused for combat mode" : JarvisState.online ? "On · listening for \"Hey Jarvis\"" : "On · starting…"); checked: JarvisState.toggleOn; onToggled: JarvisState.toggle() }
        // PERSONA: who answers by default. Same brain, tools, memory and threads; FRIDAY has her own voice
        // and manner. "hey Friday" wakes FRIDAY when its wake model is installed (JarvisFeed.status.wake).
        Stepper {
            width: parent.width; label: "Persona"
            hint: (JarvisFeed.status.wake || []).indexOf("friday") >= 0
                  ? "Who answers by default · \"hey Jarvis\" and \"hey Friday\" each wake their own"
                  : "Who answers by default · both answer \"hey Jarvis\" (no \"hey Friday\" model yet)"
            valueText: Skin.persona(JarvisState.persona).glyph + " " + JarvisState.nameOf(JarvisState.persona)
            onDec: JarvisState.setPersona(JarvisState.persona === "friday" ? "jarvis" : "friday")
            onInc: JarvisState.setPersona(JarvisState.persona === "friday" ? "jarvis" : "friday")
        }
        Stepper { width: parent.width; label: "Claude model"; hint: jarvisPage.modelHints[Theme.cfg.jarvisModel] || ""; valueText: Theme.cfg.jarvisModel.toUpperCase(); onDec: Theme.cfg.jarvisModel = jarvisPage.cycle(jarvisPage.models, Theme.cfg.jarvisModel, -1); onInc: Theme.cfg.jarvisModel = jarvisPage.cycle(jarvisPage.models, Theme.cfg.jarvisModel, 1) }
        Toggle { width: parent.width; label: "Spoken replies"; hint: "Off = replies only show on the toast"; checked: Theme.cfg.jarvisSpeak; onToggled: Theme.cfg.jarvisSpeak = !Theme.cfg.jarvisSpeak }
        Toggle { width: parent.width; label: "Lower music while speaking"; hint: "Spotify and other MPRIS players"; checked: Theme.cfg.jarvisDuck; onToggled: Theme.cfg.jarvisDuck = !Theme.cfg.jarvisDuck }
        Toggle { width: parent.width; label: "Pause in combat mode"; hint: "Wake word off, mic released · timers still go off"; checked: Theme.cfg.gameJarvis; onToggled: Theme.cfg.gameJarvis = !Theme.cfg.gameJarvis }
        Toggle { width: parent.width; label: "Confirm sensitive actions"; hint: "Always on · power, closing windows, deleting, kill switch, messages sent as you"; checked: true; enabled: false; opacity: 0.6 }
        Title { text: "TOOLS" }
        Row {
            spacing: 10
            SmallButton { text: "TEST VOICE"; onClicked: Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/jarvis", "--say", "At your service, sir."]) }
            SmallButton { text: "MISSED COMMANDS"; onClicked: { Hyprland.dispatch(Hypr.exec("kitty --hold " + Quickshell.env("HOME") + "/.local/bin/jarvis --misses")); LauncherState.closeAll(); } }
            SmallButton { text: "EDIT " + JarvisState.assistant; onClicked: { Hyprland.dispatch(Hypr.exec("kate ~/.config/jarvis")); LauncherState.closeAll(); } }
        }
        Text { width: parent.width; wrapMode: Text.Wrap; text: "Claude runs on your Pro login (no API key). Memory: ~/.local/share/jarvis/jarvis.db"; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11 }
    }

    // ── VOICES ──
    Section {
        visible: jarvisPage.sub === "VOICES"
        Title { text: JarvisState.nameOf("jarvis") }
        Stepper { width: parent.width; label: "Voice"; hint: "British voices · audition them all: jarvis-voices"; preview: true; onPlay: jarvisPage.preview(); valueText: jarvisPage.voiceName(Theme.cfg.jarvisVoice); onDec: Theme.cfg.jarvisVoice = jarvisPage.cycle(jarvisPage.voices, Theme.cfg.jarvisVoice, -1); onInc: Theme.cfg.jarvisVoice = jarvisPage.cycle(jarvisPage.voices, Theme.cfg.jarvisVoice, 1) }
        Stepper { width: parent.width; label: "Speech rate"; preview: true; onPlay: jarvisPage.preview(); valueText: Theme.cfg.jarvisSpeed.toFixed(1) + "×"; onDec: Theme.cfg.jarvisSpeed = Math.max(0.7, Math.round((Theme.cfg.jarvisSpeed - 0.1) * 10) / 10); onInc: Theme.cfg.jarvisSpeed = Math.min(1.5, Math.round((Theme.cfg.jarvisSpeed + 0.1) * 10) / 10) }
        Stepper { width: parent.width; label: "Pitch"; hint: "Semitones, on top of the effect preset"; preview: true; onPlay: jarvisPage.preview(); valueText: (Theme.cfg.jarvisPitch > 0 ? "+" : "") + Theme.cfg.jarvisPitch.toFixed(1); onDec: Theme.cfg.jarvisPitch = Math.max(-3, Theme.cfg.jarvisPitch - 0.5); onInc: Theme.cfg.jarvisPitch = Math.min(2, Theme.cfg.jarvisPitch + 0.5) }
        Stepper { width: parent.width; label: "Effect"; hint: jarvisPage.effectHints[Theme.cfg.jarvisEffect] || "Custom preset · ~/.config/jarvis/effects.json"; preview: true; onPlay: jarvisPage.preview(); valueText: Theme.cfg.jarvisEffect; onDec: Theme.cfg.jarvisEffect = jarvisPage.cycle(jarvisPage.effects, Theme.cfg.jarvisEffect, -1); onInc: Theme.cfg.jarvisEffect = jarvisPage.cycle(jarvisPage.effects, Theme.cfg.jarvisEffect, 1) }
        Title { text: JarvisState.nameOf("friday") }
        Stepper { width: parent.width; label: "Voice"; hint: "No Irish voice in Kokoro · audition: jarvis-voices --friday"; preview: true; onPlay: jarvisPage.previewFriday(); valueText: jarvisPage.voiceName(Theme.cfg.fridayVoice); onDec: Theme.cfg.fridayVoice = jarvisPage.cycle(jarvisPage.femaleVoices, Theme.cfg.fridayVoice, -1); onInc: Theme.cfg.fridayVoice = jarvisPage.cycle(jarvisPage.femaleVoices, Theme.cfg.fridayVoice, 1) }
        Stepper { width: parent.width; label: "Speech rate"; preview: true; onPlay: jarvisPage.previewFriday(); valueText: Theme.cfg.fridaySpeed.toFixed(2) + "×"; onDec: Theme.cfg.fridaySpeed = Math.max(0.7, Math.round((Theme.cfg.fridaySpeed - 0.05) * 100) / 100); onInc: Theme.cfg.fridaySpeed = Math.min(1.6, Math.round((Theme.cfg.fridaySpeed + 0.05) * 100) / 100) }
        Stepper { width: parent.width; label: "Pitch"; hint: "Semitones, on top of the effect preset"; preview: true; onPlay: jarvisPage.previewFriday(); valueText: (Theme.cfg.fridayPitch > 0 ? "+" : "") + Theme.cfg.fridayPitch.toFixed(1); onDec: Theme.cfg.fridayPitch = Math.max(-3, Theme.cfg.fridayPitch - 0.5); onInc: Theme.cfg.fridayPitch = Math.min(3, Theme.cfg.fridayPitch + 0.5) }
        // the second persona's own effect (fridayEffect); SAME = the one above
        Stepper {
            width: parent.width; label: "Effect"
            hint: Theme.cfg.fridayEffect === "" ? "Same as " + JarvisState.nameOf("jarvis") + "'s effect" : Theme.cfg.fridayEffect === "AUTO" ? jarvisPage.autoHint("friday") : (jarvisPage.effectHints[Theme.cfg.fridayEffect] || "Custom preset · ~/.config/jarvis/effects.json")
            preview: true; onPlay: jarvisPage.previewFriday()
            valueText: Theme.cfg.fridayEffect || "SAME"
            onDec: Theme.cfg.fridayEffect = jarvisPage.fridayFx(-1)
            onInc: Theme.cfg.fridayEffect = jarvisPage.fridayFx(1)
        }
        Title { text: "OUTPUT" }
        Slider {
            width: parent.width
            label: "VOICE VOLUME"
            value: Theme.cfg.jarvisVoiceVolume / 100
            onMoved: v => { Theme.cfg.jarvisVoiceVolume = Math.round(v * 100); volumePreview.restart(); }
        }
        Text { width: parent.width; wrapMode: Text.Wrap; text: JarvisState.callOf("jarvis") + "'s voice and chime only · music and other apps are untouched · the same level on headphones, speakers and Bluetooth · \"speak louder / quieter\", \"set your volume to 40 percent\""; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11 }
        Stepper { width: parent.width; label: "Speaker without headphones"; hint: "Used when the output is the laptop speakers or a monitor · headphones, headsets and USB audio keep " + JarvisState.callOf("jarvis"); preview: Theme.cfg.jarvisSpeaker !== ""; onPlay: jarvisPage.preview(); valueText: jarvisPage.speakerName(Theme.cfg.jarvisSpeaker); onDec: Theme.cfg.jarvisSpeaker = jarvisPage.cycle([""].concat(jarvisPage.speakers.map(s => s.mac)), Theme.cfg.jarvisSpeaker, -1); onInc: Theme.cfg.jarvisSpeaker = jarvisPage.cycle([""].concat(jarvisPage.speakers.map(s => s.mac)), Theme.cfg.jarvisSpeaker, 1) }
        Stepper { width: parent.width; visible: Theme.cfg.jarvisSpeaker !== ""; label: "Bluetooth speaker volume"; hint: JarvisState.callOf("jarvis") + "'s level on the room speaker · SAME follows VOICE VOLUME"; preview: Theme.cfg.jarvisSpeakerVolume >= 0; onPlay: jarvisPage.preview(); valueText: Theme.cfg.jarvisSpeakerVolume < 0 ? "SAME" : Theme.cfg.jarvisSpeakerVolume + "%"; onDec: Theme.cfg.jarvisSpeakerVolume = Theme.cfg.jarvisSpeakerVolume < 0 ? -1 : Theme.cfg.jarvisSpeakerVolume <= 0 ? -1 : Math.max(0, Theme.cfg.jarvisSpeakerVolume - 5); onInc: Theme.cfg.jarvisSpeakerVolume = Theme.cfg.jarvisSpeakerVolume < 0 ? Theme.cfg.jarvisVoiceVolume : Math.min(100, Theme.cfg.jarvisSpeakerVolume + 5) }
    }

    // ── LISTENING ──
    Section {
        visible: jarvisPage.sub === "LISTENING"
        // INPUT DEVICE: Jarvis's own wake-word mic (jarvis.py Mic), not the system default input
        Stepper {
            width: parent.width; label: "Input device"
            hint: (Theme.cfg.jarvisMic === "auto" ? "Headset mic while one is plugged in, else the laptop mic · " : "")
                  + (JarvisFeed.mic.label ? "listening on " + JarvisFeed.mic.label : JarvisState.running ? "" : "used when " + JarvisState.callOf("jarvis") + " is on")
            valueText: jarvisPage.micName(Theme.cfg.jarvisMic)
            onDec: Theme.cfg.jarvisMic = jarvisPage.cycle(jarvisPage.micChoices, Theme.cfg.jarvisMic === "" ? "default" : Theme.cfg.jarvisMic, -1)
            onInc: Theme.cfg.jarvisMic = jarvisPage.cycle(jarvisPage.micChoices, Theme.cfg.jarvisMic === "" ? "default" : Theme.cfg.jarvisMic, 1)
        }
        Toggle { width: parent.width; visible: Theme.cfg.jarvisMic === "auto"; label: "AUTO uses Bluetooth headset mics"; hint: "Off: Bluetooth headphones keep full music quality (their mic switches them to call quality while " + JarvisState.callOf("jarvis") + " listens)"; checked: Theme.cfg.jarvisMicBluetooth; onToggled: Theme.cfg.jarvisMicBluetooth = !Theme.cfg.jarvisMicBluetooth }
        Stepper { width: parent.width; label: "Follow-up window"; hint: "Keeps listening after a reply, no wake word needed"; valueText: Theme.cfg.jarvisFollowup > 0 ? Theme.cfg.jarvisFollowup + " S" : "OFF"; onDec: Theme.cfg.jarvisFollowup = jarvisPage.cycle(jarvisPage.follows, Theme.cfg.jarvisFollowup, -1); onInc: Theme.cfg.jarvisFollowup = jarvisPage.cycle(jarvisPage.follows, Theme.cfg.jarvisFollowup, 1) }
    }

    // ── DECISIONS ──
    Section {
        visible: jarvisPage.sub === "DECISIONS"
        Stepper { width: parent.width; label: "Decisions"; hint: Theme.cfg.jarvisDecisions === "local" ? "Common commands decided on this PC (offline, ~5 ms) · Claude for the rest" : "Everything the regex rules miss goes to Claude"; valueText: Theme.cfg.jarvisDecisions === "local" ? "LOCAL+CLAUDE" : "CLAUDE ONLY"; onDec: Theme.cfg.jarvisDecisions = Theme.cfg.jarvisDecisions === "local" ? "claude" : "local"; onInc: Theme.cfg.jarvisDecisions = Theme.cfg.jarvisDecisions === "local" ? "claude" : "local" }
        Stepper { width: parent.width; visible: Theme.cfg.jarvisDecisions === "local"; label: "Local confidence"; hint: "Higher = fewer local actions, more sent to Claude · tune with tools/eval_router.py"; valueText: Theme.cfg.jarvisRouterThreshold.toFixed(2); onDec: Theme.cfg.jarvisRouterThreshold = Math.max(0.5, Math.round((Theme.cfg.jarvisRouterThreshold - 0.01) * 100) / 100); onInc: Theme.cfg.jarvisRouterThreshold = Math.min(0.95, Math.round((Theme.cfg.jarvisRouterThreshold + 0.01) * 100) / 100) }
        // ROUTER: what the local router learned and how often it answers without Claude
        // (~/.config/jarvis/core/router_learn.py; `jarvis router stats --json`, polled with INTEGRATIONS)
        Toggle { width: parent.width; visible: Theme.cfg.jarvisDecisions === "local"; label: "Ask when unsure"; hint: "A near miss gets \"Did you mean …?\" · yes runs it and teaches it, no sends it to Claude"; checked: Theme.cfg.jarvisRouterAsk; onToggled: Theme.cfg.jarvisRouterAsk = !Theme.cfg.jarvisRouterAsk }
        Text { visible: Theme.cfg.jarvisDecisions === "local"; text: "ROUTER"; topPadding: 10; color: Theme.dim; font.family: Style.fonts.display; font.pixelSize: Style.display !== Style.mono ? 13 : 11; font.letterSpacing: 3 }
        Column {
            id: routerBox
            width: parent.width; spacing: 6
            visible: Theme.cfg.jarvisDecisions === "local"
            readonly property var r: jarvisPage.router
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
                    width: jarvisPage.width; elide: Text.ElideRight; font.family: Style.fonts.body; font.pixelSize: 11
                    color: ["promoted", "approved"].indexOf(modelData.kind) >= 0 ? Theme.primary : ["rejected", "demoted", "deleted", "corrected"].indexOf(modelData.kind) >= 0 ? Theme.secondary : Theme.textSoft
                    text: jarvisPage.evAge(modelData.ts) + "  " + modelData.kind.toUpperCase() + "  " + (modelData.text ? "\"" + modelData.text + "\" → " : "") + modelData.intent + (modelData.why ? " · " + modelData.why : "")
                }
            }
            Text { visible: (parent.r.review || []).length > 0; text: "LEARNED · REVIEW"; topPadding: 4; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 2 }
            Text { visible: parent.r.review !== undefined && parent.r.review.length === 0; text: "Nothing learned yet · it learns from Claude's simple answers, your corrections and \"yes\" to \"Did you mean…\""; width: jarvisPage.width; wrapMode: Text.Wrap; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11 }
            Repeater {
                // waiting on you first (candidates, rejections), then what's live
                model: (parent.r.review || []).slice().sort((a, b) => (a.state === "active") - (b.state === "active")).slice(0, 14)
                delegate: Item {
                    required property var modelData
                    width: jarvisPage.width; height: 40
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
                        SmallButton { visible: modelData.state !== "active"; text: "APPROVE"; onClicked: jarvisPage.routerCmd(["approve", modelData.id]) }
                        ConfirmButton { label: "REMOVE"; onConfirmed: jarvisPage.routerCmd(["forget", modelData.id]) }
                    }
                }
            }
            Text {
                width: jarvisPage.width; wrapMode: Text.Wrap; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1
                text: "APPROVE still has to pass the router eval (0 wrong actions) · learned data stays in ~/.local/share/jarvis · jarvis router stats | review | forget ID | reset-learned"
            }
        }
    }

    // ── CONNECTIONS ──
    Section {
        visible: jarvisPage.sub === "CONNECTIONS"
        // Phase-2 integrations: entries in ~/.config/jarvis/servers.json, tokens in the system keyring.
        // CONNECT opens a terminal running the sign-in flow (`jarvis connect …`).
        Title { text: "INTEGRATIONS" }
        Repeater {
            model: jarvisPage.integrations
            delegate: Item {
                required property var modelData
                width: jarvisPage.width; height: 52
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
                    onClicked: { Hyprland.dispatch(Hypr.exec("kitty --hold " + Quickshell.env("HOME") + "/.local/bin/jarvis connect " + modelData.auth)); LauncherState.closeAll(); }
                }
            }
        }
        Title { text: "COURSEWORK" }
        Toggle { width: parent.width; label: "Auto-update tracker"; hint: Theme.cfg.jarvisAutoUpdateTracker ? "Grades, new LEARN work and moved deadlines go into your SE tracker and are announced · \"jarvis tracker undo\" reverts the last write" : "Each tracker update is offered first, spoken and on the HUD · your own requests always ask"; checked: Theme.cfg.jarvisAutoUpdateTracker; onToggled: Theme.cfg.jarvisAutoUpdateTracker = !Theme.cfg.jarvisAutoUpdateTracker }
        Toggle { width: parent.width; label: "Auto-add assignments"; hint: "Fallback while no tracker sheet is set up · LEARN due dates go into \"STARK – Assignments\" without asking · that calendar only, never your main one"; checked: Theme.cfg.jarvisAutoAddAssignments; onToggled: Theme.cfg.jarvisAutoAddAssignments = !Theme.cfg.jarvisAutoAddAssignments }
        Stepper { width: parent.width; label: "Assignments calendar"; hint: "Account that holds \"STARK – Assignments\""; valueText: Theme.cfg.jarvisAssignmentsAccount === "microsoft" ? "OUTLOOK" : "GOOGLE"; onDec: Theme.cfg.jarvisAssignmentsAccount = Theme.cfg.jarvisAssignmentsAccount === "microsoft" ? "google" : "microsoft"; onInc: Theme.cfg.jarvisAssignmentsAccount = Theme.cfg.jarvisAssignmentsAccount === "microsoft" ? "google" : "microsoft" }
        Title { text: "SPOTIFY" }
        Item {
            width: jarvisPage.width; height: 52
            Column {
                anchors.left: parent.left; anchors.right: spotifyBtns.left; anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                spacing: 3
                Row {
                    spacing: 10
                    Text { text: "Spotify"; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 14 }
                    Text {
                        text: jarvisPage.spotify.connected ? "CONNECTED" : "NOT CONNECTED"
                        color: jarvisPage.spotify.connected ? Theme.primary : Theme.dim
                        font.family: Style.fonts.body; font.pixelSize: 11; font.letterSpacing: 2
                    }
                }
                Text {
                    width: parent.width; elide: Text.ElideRight
                    text: (jarvisPage.spotify.user ? jarvisPage.spotify.user + " · " : "") + (jarvisPage.spotify.detail || "Your own developer app · CONNECT walks you through it")
                    color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11
                }
            }
            Row {
                id: spotifyBtns
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                ConfirmButton {
                    visible: jarvisPage.spotify.connected === true
                    label: "DISCONNECT"
                    onConfirmed: { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/jarvis", "spotify", "disconnect"]); spotifyStatus.running = true; }
                }
                SmallButton {
                    text: jarvisPage.spotify.connected ? "RECONNECT" : "CONNECT"
                    active: jarvisPage.spotify.connected === true
                    onClicked: { Hyprland.dispatch(Hypr.exec("kitty --hold " + Quickshell.env("HOME") + "/.local/bin/jarvis spotify connect")); LauncherState.closeAll(); }
                }
            }
        }
        Stepper {
            width: parent.width; label: "DJ chatter"
            hint: ({ off: "DJ mode never talks between tracks", rare: "A short line every 4–5 tracks, music ducked under it", normal: "A short line every 2–3 tracks" })[Theme.cfg.jarvisDjChatter] || ""
            valueText: Theme.cfg.jarvisDjChatter.toUpperCase()
            onDec: Theme.cfg.jarvisDjChatter = jarvisPage.cycle(["off", "rare", "normal"], Theme.cfg.jarvisDjChatter, -1)
            onInc: Theme.cfg.jarvisDjChatter = jarvisPage.cycle(["off", "rare", "normal"], Theme.cfg.jarvisDjChatter, 1)
        }
        Text {
            width: parent.width; wrapMode: Text.Wrap
            text: "MOODS · " + jarvisPage.djMoods.concat(savedMoods.names).join(" · ").toUpperCase()
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
        visible: jarvisPage.sub === "PRIVACY"
        Title { text: "WINDOW READING" }
        Stepper { width: parent.width; label: "Watch every"; hint: "How often a watcher looks at its window · compared on this machine, Claude only looks when enough changed"; valueText: Theme.cfg.jarvisWatchInterval + " S"; onDec: Theme.cfg.jarvisWatchInterval = Math.max(3, Theme.cfg.jarvisWatchInterval - (Theme.cfg.jarvisWatchInterval > 30 ? 10 : Theme.cfg.jarvisWatchInterval > 10 ? 5 : 1)); onInc: Theme.cfg.jarvisWatchInterval = Math.min(300, Theme.cfg.jarvisWatchInterval + (Theme.cfg.jarvisWatchInterval >= 30 ? 10 : Theme.cfg.jarvisWatchInterval >= 10 ? 5 : 1)) }
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
                    text: (Theme.cfg.jarvisCaptureBlocklist || []).join(", ")
                    function save() {
                        const terms = text.split(/[,\n]/).map(t => t.trim().toLowerCase()).filter(t => t !== "");
                        Theme.cfg.jarvisCaptureBlocklist = terms.filter((t, i) => terms.indexOf(t) === i);
                        text = Theme.cfg.jarvisCaptureBlocklist.join(", ");
                    }
                    Keys.onReturnPressed: { save(); focus = false; }
                    Keys.onEnterPressed: { save(); focus = false; }
                    onActiveFocusChanged: if (!activeFocus) save()
                }
            }
            Text { width: parent.width; wrapMode: Text.Wrap; text: "Always refused, whatever this says: the lock screen, password / permission / keyring prompts and password managers. " + JarvisState.callOf("jarvis") + " only reads a window you name; captures stay in memory, never on disk, and what's on screen is data, never an instruction."; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11 }
        }
        Text { width: parent.width; wrapMode: Text.Wrap; text: "Read-only by default. Sending, creating, deleting or editing anything needs your spoken yes. Email, calendar and document text is treated as data, never as commands. Setup: ~/.config/jarvis/docs"; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11 }
    }

}
