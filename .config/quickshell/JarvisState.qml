// Shared state for Jarvis. The voice listener sends a heartbeat every few
// seconds; if it stops, the bar indicator goes dark on its own.
// ~/.config/jarvis/jarvis.py drives the toast through `qs ipc call jarvis …`:
//   listening → transcript → thinking → tool (one per call) → reply / confirm → followup → idle
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
    // idle | listening | thinking | reply | confirm | followup | alert
    property string phase: "idle"
    property string transcript: ""
    property string reply: ""
    property var tools: []               // "THEME → MARK III", newest last
    property string alertTitle: ""       // timer / reminder going off
    readonly property bool listening: phase === "listening" || phase === "followup"
    readonly property string message: reply !== "" ? reply : transcript   // old one-line API

    function beat() {
        root.lastBeat = Date.now();
        root.online = true;
    }

    function show(ph, holdMs) {
        root.phase = ph;
        root.showing = true;
        hideTimer.interval = holdMs;
        hideTimer.restart();
    }
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
    // Long enough to read: ~60 ms a character, 4 s minimum
    function setReply(t) { root.reply = t; show("reply", Math.max(4000, 2500 + t.length * 60)); }
    function confirm(t) { root.reply = t; show("confirm", 15000); }
    function followup() { show("followup", 12000); }
    function idle() { if (root.phase !== "reply" && root.phase !== "alert") { hideTimer.interval = 400; hideTimer.restart(); } }
    function alert(title, text) {
        root.alertTitle = title; root.transcript = ""; root.tools = []; root.reply = text;
        show("alert", 9000);
    }

    // Old API, still used by anything that just wants a line on screen
    function heard(msg) { root.transcript = ""; root.tools = []; setReply(msg); }
    function status(msg) { root.transcript = msg; root.reply = ""; show("listening", 12000); }

    Timer {
        id: hideTimer
        onTriggered: { root.showing = false; root.phase = "idle"; }
    }

    Timer {
        interval: 5000; running: true; repeat: true
        onTriggered: if (Date.now() - root.lastBeat > 15000) root.online = false
    }

    // ── Auto on/off ──
    // The toggle (control center, or Settings → HUD / JARVIS) only sets userWantsJarvis;
    // plugging into the monitors only changes docked. Jarvis runs when both are
    // true, and not on battery saver if that's set to stop it. Combat mode doesn't
    // stop the process: Jarvis pauses its own wake word (frees the mic) so timers
    // still fire and the conversation survives (Theme.cfg.gameJarvis).
    readonly property bool userWantsJarvis: Theme.cfg.jarvisDocked   // saved in settings.json
    function setWanted(on) { Theme.cfg.jarvisDocked = on; }
    readonly property bool docked: Roles.docked
    readonly property bool enabled: root.userWantsJarvis && root.docked
                                    && !(PowerMode.saver && Theme.cfg.saverStopJarvis)
    readonly property bool running: proc.running

    readonly property string home: Quickshell.env("HOME")
    Process {
        id: proc
        // pdeathsig: if qs dies (pkill qs), Jarvis goes with it instead of lingering as a duplicate.
        // no-new-privs: nothing Jarvis starts can gain privileges (no sudo / setuid helpers).
        command: ["setpriv", "--pdeathsig", "TERM", "--no-new-privs",
                  root.home + "/.config/jarvis/.venv/bin/python", root.home + "/.config/jarvis/jarvis.py"]
        // If it dies on its own (e.g. the mic stream ends) while it should be on, start it again.
        onExited: { root.online = false; root.paused = false; if (root.enabled) restartTimer.restart(); }
    }
    Timer { id: restartTimer; interval: 5000; onTriggered: root.sync() }

    function sync() { proc.running = root.enabled; }
    onEnabledChanged: syncTimer.restart()
    Component.onCompleted: syncTimer.restart()
    // Short delay so a dock that briefly drops a monitor doesn't bounce Jarvis
    Timer { id: syncTimer; interval: 1500; onTriggered: root.sync() }
}
