pragma Singleton
// Data the desktop widgets show, all pushed, none polled:
//   status.json   $XDG_RUNTIME_DIR/jarvis/status.json, written by the Jarvis voice process when something
//                 changes (~/.config/jarvis/core/status.py): mic, last command, background tasks, token usage
//   agenda.json   ~/.local/share/jarvis/feed/, from `jarvis feed` (core/feed.py): main Google Calendar +
//   weather.json  Outlook ICS + SE tracker due dates, home-town weather. That process runs only while a
//                 calendar / due / weather widget is up, and syncs on its own clock (no Claude, ever).
// FileView watches each file (inotify). The one clock here ticks on the minute, only while a widget
// that shows countdowns is up.
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root
    readonly property string home: Quickshell.env("HOME")
    readonly property string runtime: Quickshell.env("XDG_RUNTIME_DIR") || "/run/user/1000"

    // ── Jarvis status ──
    property var status: ({})
    readonly property bool online: JarvisState.online && (status.pid || 0) > 0
    readonly property var mic: online ? (status.mic || {}) : ({})
    readonly property var last: status.last || ({})
    readonly property var tasks: status.tasks || []
    readonly property var usage: status.usage || ({})
    FileView {
        id: statusFile
        path: root.runtime + "/jarvis/status.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: { try { root.status = JSON.parse(text()); } catch (e) {} }
        onLoadFailed: root.status = ({})
    }
    // the file appears / goes with the Jarvis process
    Connections {
        target: JarvisState
        function onOnlineChanged() { statusFile.reload(); }
        function onRunningChanged() { statusFile.reload(); }
    }

    // ── agenda + weather ──
    property var agenda: ({ events: [], due: [], notes: [], updated: 0 })
    property var weather: ({})
    FileView {
        id: agendaFile
        path: root.home + "/.local/share/jarvis/feed/agenda.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: { try { root.agenda = JSON.parse(text()); } catch (e) {} }
    }
    FileView {
        id: weatherFile
        path: root.home + "/.local/share/jarvis/feed/weather.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: { try { root.weather = JSON.parse(text()); } catch (e) {} }
    }

    readonly property var feedTypes: ["calendar", "due", "weather"]
    readonly property bool needFeed: Widgets.items.some(i => root.feedTypes.indexOf(i.type) >= 0)
    Process {
        id: feed
        running: root.needFeed
        // pdeathsig: it goes with the HUD; no-new-privs like Jarvis itself
        command: ["setpriv", "--pdeathsig", "TERM", "--no-new-privs", root.home + "/.local/bin/jarvis", "feed"]
        onRunningChanged: if (running) { agendaFile.reload(); weatherFile.reload(); }
        onExited: if (root.needFeed) feedRetry.restart()
    }
    Timer { id: feedRetry; interval: 30000; onTriggered: if (root.needFeed && !feed.running) feed.running = true }
    function refresh() { Quickshell.execDetached([root.home + "/.local/bin/jarvis", "feed", "--kick"]); }

    // ── minute clock for countdowns: fires as the minute turns, only while it's needed ──
    property double now: Date.now()
    readonly property bool needClock: Widgets.items.some(i => ["calendar", "due", "usage", "jarvis"].indexOf(i.type) >= 0)
    Timer {
        id: minute
        running: root.needClock
        repeat: false
        interval: 60050 - (Date.now() % 60000)
        triggeredOnStart: true
        onTriggered: { root.now = Date.now(); interval = 60050 - (root.now % 60000); restart(); }
    }

    // ── formatting shared by the widgets ──
    function until(ms) {        // "IN 12 MIN" / "IN 3 H 05" / "NOW" / "TOMORROW 9:00"
        const d = ms - root.now;
        if (d <= 0) return "NOW";
        const m = Math.round(d / 60000);
        if (m < 60) return "IN " + Math.max(1, m) + " MIN";
        if (m < 12 * 60) return "IN " + Math.floor(m / 60) + " H " + String(m % 60).padStart(2, "0");
        return dayLabel(ms) + " " + Qt.formatDateTime(new Date(ms), Theme.cfg.clock24 ? "HH:mm" : "h:mm AP");
    }
    function dayLabel(ms) {
        const a = new Date(root.now); a.setHours(0, 0, 0, 0);
        const days = Math.floor((ms - a.getTime()) / 86400000);
        if (days <= 0) return "TODAY";
        if (days === 1) return "TOMORROW";
        return Qt.formatDateTime(new Date(ms), "ddd").toUpperCase();
    }
    function tokens(n) {        // 1234 → "1.2K", 3400000 → "3.4M"
        n = n || 0;
        if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M";
        if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "K";
        return String(n);
    }
}
