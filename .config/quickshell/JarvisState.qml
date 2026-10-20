// Shared state for Jarvis. The voice listener sends a heartbeat every few
// seconds; if it stops, the bar indicator goes dark on its own.
pragma Singleton
import QtQuick
import Quickshell

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
    // Docked → on, laptop only → off (both changeable in Settings → HUD),
    // and off on battery if the battery saver is set to pause it.
    readonly property bool wanted: (Roles.docked ? Theme.cfg.jarvisDocked : Theme.cfg.jarvisLaptop)
                                   && !(PowerMode.saver && Theme.cfg.saverStopJarvis)
    function start() {
        Quickshell.execDetached(["sh", "-c",
            "pgrep -f '[j]arvis.py' >/dev/null || nohup ~/.config/jarvis/.venv/bin/python ~/.config/jarvis/jarvis.py >/dev/null 2>&1 &"]);
    }
    function stop() {
        Quickshell.execDetached(["pkill", "-f", "jarvis.py"]);
        root.online = false;
    }
    function sync() { if (root.wanted) root.start(); else root.stop(); }
    onWantedChanged: syncTimer.restart()
    Component.onCompleted: syncTimer.restart()
    Timer { id: syncTimer; interval: 3000; onTriggered: root.sync() }
}
