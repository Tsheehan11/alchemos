// Shared state for Jarvis. The voice listener sends a heartbeat every few
// seconds; if it stops, the bar indicator goes dark on its own.
// ~/.config/jarvis/jarvis.py drives the toast through `qs ipc call jarvis …`:
//   listening → transcript → thinking → tool (one per call) → reply / confirm → followup → idle
//   error: something failed after the chime; Jarvis says a line and the toast shows why
//   speak / speechDone: each spoken sentence as it starts (characters start..end of total, ms long);
//   the pop-up stays up while he's speaking or the pointer is on it, then a few seconds scaled to length
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root
    property bool online: false
    property double lastBeat: 0
    property bool showing: false
    property bool paused: false          // combat mode: wake word off, mic released
    // idle | listening | thinking | reply | confirm | followup | alert | error
    property string phase: "idle"
    property string transcript: ""
    property string reply: ""
    property var tools: []               // "THEME → MARK III", newest last
    property string alertTitle: ""       // timer / reminder going off
    property string errorReason: ""      // "NO NETWORK", "DIDN'T CATCH THAT", …
    readonly property bool listening: phase === "listening" || phase === "followup"
    property bool speaking: false
    property bool hovered: false         // the pointer is on the pop-up: it stays
    property int holdMs: 4000
    // speech progress, in characters of the spoken text: the sentence playing now runs from
    // speakStart to speakEnd (of speakTotal) over speakMs, starting at speakAt
    property int speakStart: 0
    property int speakEnd: 0
    property int speakTotal: 0
    property int speakMs: 0
    property double speakAt: 0
    property int replySerial: 0          // bumps when a new reply arrives (the pop-up resets its scrolling)
    readonly property string message: reply !== "" ? reply : transcript   // old one-line API

    // Jarvis runs as its own service (stark-jarvis.service), so it outlives a qs restart / hot reload.
    // This instance hasn't had Jarvis's state yet: the next heartbeat answers "resync" and Jarvis
    // sends restore() with the toast state (core/hud.py). Reset whenever Jarvis goes offline.
    property bool synced: false
    function beat() {
        root.lastBeat = Date.now();
        root.online = true;
        return root.synced ? "" : "resync";
    }
    function goOffline() { root.online = false; root.paused = false; root.synced = false; }
    // {phase, transcript, reply, tools, paused}: only a live phase comes back on screen
    function restore(json) {
        let s = {};
        try { s = JSON.parse(json); } catch (e) { return; }
        root.synced = true;
        root.paused = s.paused === true;
        const live = ["listening", "thinking", "followup", "confirm"];
        if (live.indexOf(s.phase) < 0) return;
        root.transcript = s.transcript || ""; root.reply = s.reply || ""; root.tools = s.tools || [];
        show(s.phase, s.phase === "thinking" ? 35000 : 15000);
    }

    function show(ph, holdMs) {
        root.phase = ph;
        root.showing = true;
        root.holdMs = holdMs;
        rearm();
    }
    // the hide countdown only runs while he isn't speaking and the pointer isn't on the pop-up
    function rearm() {
        if (root.speaking || root.hovered) { hideTimer.stop(); return; }
        hideTimer.interval = root.holdMs;
        hideTimer.restart();
    }
    onHoveredChanged: if (root.showing) rearm()
    function speak(start, end, total, ms) {
        if (start === 0) root.speakTotal = 0;
        root.speakStart = start; root.speakEnd = end; root.speakTotal = Math.max(root.speakTotal, total);
        root.speakMs = ms; root.speakAt = Date.now();
        root.speaking = true;
        speechGuard.interval = ms + 15000; speechGuard.restart();
        if (root.showing) rearm();
    }
    function speechDone() {
        if (!root.speaking) return;
        root.speaking = false;
        root.speakStart = root.speakEnd = root.speakTotal;
        // a few seconds after he stops, longer for a long answer
        if (root.showing && (root.phase === "reply" || root.phase === "error"))
            root.holdMs = Math.max(3500, Math.min(12000, 2500 + root.reply.length * 12));
        if (root.showing) rearm();
    }
    // a lost speechDone never keeps the pop-up up for ever
    Timer { id: speechGuard; onTriggered: root.speechDone() }
    function startListening() {
        root.transcript = ""; root.reply = ""; root.tools = [];
        show("listening", 15000);
    }
    function setTranscript(t) { root.transcript = t; show(root.phase === "idle" ? "thinking" : root.phase, 15000); }
    function thinking() { show("thinking", 35000); }
    function tool(label) {
        root.tools = root.tools.concat([label]).slice(-5);
        show("thinking", 35000);
    }
    // Not spoken (voice off, typed, CLI): long enough to read, ~60 ms a character, 4 s minimum.
    // Spoken: held while he speaks, then speechDone() sets the tail.
    function setReply(t) {
        if (!root.showing) { root.transcript = ""; root.tools = []; }    // a reply on its own (an offer, a reminder)
        if (t !== root.reply) root.replySerial++;
        root.reply = t;
        show("reply", Math.max(4000, 2500 + t.length * 60));
    }
    function confirm(t) { root.reply = t; show("confirm", 15000); }
    function followup() { show("followup", 12000); }
    function idle() { if (root.phase !== "reply" && root.phase !== "alert" && root.phase !== "error") { hideTimer.interval = 400; hideTimer.restart(); } }
    function fail(reason, text) {
        root.errorReason = reason; root.reply = text;
        show("error", Math.max(5000, 2500 + text.length * 60));
    }
    function note(label) { if (root.tools[root.tools.length - 1] !== label) root.tools = root.tools.concat([label]).slice(-5); }
    function alert(title, text) {
        root.alertTitle = title; root.transcript = ""; root.tools = []; root.reply = text; root.replySerial++;
        show("alert", 9000);
    }

    // Old API, still used by anything that just wants a line on screen
    function heard(msg) { root.transcript = ""; root.tools = []; setReply(msg); }
    function dismiss() { root.speaking = false; root.hovered = false; hideTimer.stop(); root.showing = false; root.phase = "idle"; }
    function status(msg) { root.transcript = msg; root.reply = ""; show("listening", 12000); }

    Timer {
        id: hideTimer
        onTriggered: { root.showing = false; root.phase = "idle"; }
    }

    Timer {
        interval: 5000; running: true; repeat: true
        onTriggered: if (root.online && Date.now() - root.lastBeat > 15000) root.goOffline()
    }

    // ── Auto on/off ──
    // Docked: the toggle (control center, or Settings → HUD / JARVIS) sets userWantsJarvis (saved) and
    // Jarvis runs while it's on, and not on battery saver if that's set to stop it.
    // Undocked: off by default. The same toggle switches it on for now only (laptopOn, never saved): any
    // dock or undock clears it, so the next undocked spell starts off again and docking goes back to the
    // docked rule. Laptop mode is lighter (jarvis.py sees STARK_JARVIS_LAPTOP=1: no academic sync, no
    // watchers, no Bluetooth room speaker) and stops itself under 20 % on battery (battery saver doesn't stop it).
    // Combat mode doesn't stop the process: Jarvis pauses its own wake word (frees the mic) so timers
    // still fire and the conversation survives (Theme.cfg.gameJarvis).
    readonly property bool userWantsJarvis: Theme.cfg.jarvisDocked   // saved in settings.json
    function setWanted(on) { Theme.cfg.jarvisDocked = on; }
    readonly property bool docked: Roles.docked
    property bool laptopOn: false
    readonly property bool laptopMode: !root.docked && root.laptopOn
    onDockedChanged: root.laptopOn = false          // any dock / undock event ends a laptop switch-on
    readonly property bool lowBattery: SysStats.polled && SysStats.discharging && SysStats.battery < 0.20
    readonly property bool enabled: root.docked ? root.userWantsJarvis && !(PowerMode.saver && Theme.cfg.saverStopJarvis)
                                                : root.laptopOn
    // what the toggles show and do, docked or not
    readonly property bool toggleOn: root.docked ? root.userWantsJarvis : root.laptopOn
    readonly property string stateLabel: !root.toggleOn ? "OFF" : root.laptopMode ? "ON (laptop, until dock change)" : "ON"
    function toggle() {
        if (root.docked) root.setWanted(!root.userWantsJarvis);
        else root.setLaptop(!root.laptopOn);
    }
    function setLaptop(on) {
        if (on && root.docked) return;
        if (on && root.powerReason() !== "") {
            root.alert("JARVIS STAYS OFF", "Not on the laptop right now, sir: " + root.powerReason() + ".");
            return;
        }
        root.laptopOn = on;
    }
    // laptop mode ignores battery saver (it's on whenever he's on battery); only a low battery stops it
    function powerReason() {
        return root.lowBattery ? "the battery is under 20 percent" : "";
    }
    // laptop mode keeps an eye on the battery and lets go by itself
    Timer {
        interval: 5000; running: root.laptopMode; repeat: true; triggeredOnStart: true
        onTriggered: {
            const why = root.powerReason();
            if (why !== "") {
                root.laptopOn = false;
                root.alert("JARVIS OFF", "I've switched myself off to save power, sir: " + why + ".");
            }
        }
    }
    // ── The service ──
    // stark-jarvis.service (~/.config/systemd/user) through ~/.config/jarvis/stark-jarvis:
    //   start docked|laptop (no-op if already running in that mode, restarts it in the other one), stop, status.
    // systemd restarts it after a crash (Restart=on-failure); while it should be on but isn't online,
    // the watchdog below asks for it again every 15 s. Logs: journalctl --user -u stark-jarvis
    property string svcState: "unknown"     // systemd ActiveState: active | activating | inactive | failed…
    property string svcMode: "docked"
    readonly property bool running: root.online || root.svcState === "active" || root.svcState === "activating"
                                    || root.svcState === "reloading"

    readonly property string home: Quickshell.env("HOME")
    readonly property string ctl: root.home + "/.config/jarvis/stark-jarvis"
    property var pending: null             // the next command, while one is running
    function svc(args) {
        if (ctlProc.running) { root.pending = args; return; }
        ctlProc.command = [root.ctl].concat(args);
        ctlProc.running = true;
    }
    Process {
        id: ctlProc
        stdout: SplitParser {
            onRead: line => {
                const f = line.trim().split(/\s+/);         // "<state> <mode> <pid>"
                if (f.length >= 2) { root.svcState = f[0]; root.svcMode = f[1]; }
            }
        }
        onExited: {
            if (root.pending) { const next = root.pending; root.pending = null; root.svc(next); return; }
            if (!root.ready) root.adopt();
        }
    }

    // ── Start-up: adopt what's already running ──
    // A qs restart mustn't stop (or bounce) a Jarvis that's running fine. Wait until the screens and
    // settings are known, read the service's state, and if it runs in laptop mode while undocked,
    // that was a laptop switch-on (laptopOn isn't saved): carry it over. Only then apply the rules.
    property bool ready: false
    readonly property bool settled: Theme.loaded && Roles.ready && SysStats.polled
    onSettledChanged: if (root.settled && !root.ready) adoptTimer.restart()
    Component.onCompleted: if (root.settled) adoptTimer.restart()
    Timer { id: adoptTimer; interval: 1500; onTriggered: root.svc(["status"]) }
    function adopt() {
        if (root.svcState === "active" && root.svcMode === "laptop" && !root.docked && root.powerReason() === "")
            root.laptopOn = true;
        root.ready = true;
        root.sync();
    }

    function sync() {
        if (!root.ready) return;
        if (root.enabled) root.svc(["start", root.laptopMode ? "laptop" : "docked"]);
        else if (root.running || root.svcState !== "inactive") root.svc(["stop"]);
    }
    onLaptopModeChanged: syncTimer.restart()    // docked ↔ laptop while on: stark-jarvis restarts it in the other mode
    onEnabledChanged: syncTimer.restart()
    // Short delay so a dock that briefly drops a monitor doesn't bounce Jarvis
    Timer { id: syncTimer; interval: 1500; onTriggered: root.sync() }
    // should be on but no heartbeat: (re)start it (start is a no-op while it's coming up)
    Timer {
        interval: 15000; repeat: true
        running: root.ready && root.enabled && !root.online
        onTriggered: root.sync()
    }
    onOnlineChanged: if (!root.online && root.ready) root.svc(["status"])
}
