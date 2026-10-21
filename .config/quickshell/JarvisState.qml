// Shared state for Jarvis. The voice listener sends a heartbeat every few
// seconds; if it stops, the bar indicator goes dark on its own.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root
    property bool online: false
    property double lastBeat: 0
    property bool showing: false
    property bool listening: false
    property string message: ""

    function beat() {
        root.lastBeat = Date.now();
        root.online = true;
    }

    // Short pop-up (e.g. "Opening Spotify")
    function heard(msg) {
        root.listening = false;
        root.message = msg;
        root.showing = true;
        hideTimer.interval = 2600;
        hideTimer.restart();
    }

    // Longer-lived status (e.g. "Listening…", "Thinking…")
    function status(msg) {
        root.listening = true;
        root.message = msg;
        root.showing = true;
        hideTimer.interval = 12000;
        hideTimer.restart();
    }

    Timer {
        id: hideTimer
        onTriggered: { root.showing = false; root.listening = false; }
    }

    Timer {
        interval: 5000; running: true; repeat: true
        onTriggered: if (Date.now() - root.lastBeat > 15000) root.online = false
    }

    // ── Auto on/off ──
    // The toggle (control center, or Settings → HUD) only sets userWantsJarvis;
    // plugging into the monitors only changes docked. Jarvis runs when both are
    // true — and not on battery saver / in combat mode, if those are set to pause it.
    readonly property bool userWantsJarvis: Theme.cfg.jarvisDocked   // saved in settings.json
    function setWanted(on) { Theme.cfg.jarvisDocked = on; }
    readonly property bool docked: Roles.docked
    readonly property bool enabled: root.userWantsJarvis && root.docked
                                    && !(PowerMode.saver && Theme.cfg.saverStopJarvis)
                                    && !(GameMode.active && Theme.cfg.gameJarvis)
    readonly property bool running: proc.running

    readonly property string home: Quickshell.env("HOME")
    Process {
        id: proc
        // pdeathsig: if qs dies (pkill qs), Jarvis goes with it instead of lingering as a duplicate
        command: ["setpriv", "--pdeathsig", "TERM",
                  root.home + "/.config/jarvis/.venv/bin/python", root.home + "/.config/jarvis/jarvis.py"]
        onExited: root.online = false
    }

    function sync() { proc.running = root.enabled; }
    onEnabledChanged: syncTimer.restart()
    Component.onCompleted: syncTimer.restart()
    // Short delay so a dock that briefly drops a monitor doesn't bounce Jarvis
    Timer { id: syncTimer; interval: 1500; onTriggered: root.sync() }
}
