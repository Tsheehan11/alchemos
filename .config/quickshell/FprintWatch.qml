pragma Singleton
// Fingerprint reader watch: when fprintd reports the Elan reader wedged (or a claim left
// stuck), say so on screen instead of the fingerprint just silently doing nothing. The
// sleep hook resets a reader that wedges across suspend by itself (stark-fprint-reset
// --auto, once the lock screen is gone), so wait for that first: only if no "reader OK"
// follows within 90 s, or the reset gives up, does the alert show. At most every 10 min,
// and not behind the lock screen (it waits for the doors to open).
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property var stuck: /machine != NULL|already claimed|already in use/
    property bool pending: false       // a wedge seen, waiting for the automatic reset
    property bool owed: false          // alert due, waiting for the unlock
    property real lastShown: 0
    readonly property bool watching: journal.running

    function due() {
        root.pending = false;
        if (LockState.doors !== "open") { root.owed = true; return; }
        if (Date.now() - root.lastShown < 600000) return;
        root.lastShown = Date.now();
        root.owed = false;
        OrrinState.alert("FINGERPRINT READER STUCK",
                          "Run stark-fprint-reset in a terminal. The password still works.");
    }

    Process {
        id: journal
        running: true
        // fprintd's log and the reset script's (logger -t stark-fprint-reset), from now on
        command: ["journalctl", "-f", "-n0", "-o", "cat",
                  "_SYSTEMD_UNIT=fprintd.service", "+", "SYSLOG_IDENTIFIER=stark-fprint-reset"]
        stdout: SplitParser {
            onRead: line => {
                if (line.indexOf("reader OK") >= 0) { root.pending = false; root.owed = false; grace.stop(); }
                else if (line.indexOf("still stuck") >= 0) { grace.stop(); root.due(); }
                else if (root.stuck.test(line) && !root.pending) { root.pending = true; grace.restart(); }
            }
        }
        onRunningChanged: if (!running) restart.restart()   // journalctl died: follow again
    }
    Timer { id: restart; interval: 5000; onTriggered: journal.running = true }
    Timer { id: grace; interval: 90000; onTriggered: root.due() }

    Connections {
        target: LockState
        function onDoorsChanged() { if (LockState.doors === "open" && root.owed) root.due(); }
    }
}
