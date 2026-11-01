pragma Singleton
// The JARVIS app's connection to the voice process (~/.config/jarvis/core/appserver.py):
// a Unix socket in $XDG_RUNTIME_DIR/jarvis/app.sock, JSON lines both ways. While Jarvis isn't
// running (undocked, or starting) history is still readable through `jarvis app-data …`.
// Super + J (hypr/stark/binds.lua) → qs ipc call jarvisapp toggle → JarvisApp.qml.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root
    property bool open: false
    readonly property bool connected: sock.connected
    readonly property string bin: Quickshell.env("HOME") + "/.local/bin/jarvis"

    property var threads: []
    property string query: ""
    property bool showQuick: false
    property var current: null            // the thread new turns go into (id), null = next turn starts one
    property var shownThread: null        // thread object open in the middle column
    property var messages: []
    property var tasks: []
    property var selectedTask: null       // id
    property var taskLines: []
    property var confirms: []
    property var watchers: []             // core/watch.py: live ones first (active / paused), then the last few finished
    property bool busy: false
    property string busyText: ""
    property string liveTool: ""
    property var usage: ({})
    property string mode: "ASK"           // ASK = a request now · TASK = a background task

    property string screenName: ""        // the monitor it opened on (it stays there until closed)

    function toggle() { if (root.open) root.open = false; else show(); }
    function show(screen) {
        LauncherState.closeAll();
        root.screenName = screen || Hyprland.focusedMonitor?.name || "";
        root.open = true;
        refresh();
        // open on the conversation that's going on (new turns land there), unless one is already shown
        if (root.current !== null && !root.shownThread) openThread(root.current);
    }
    function refresh() {
        if (sock.connected) { send({op: "hello"}); send({op: "threads", q: root.query, quick: root.showQuick}); }
        else offline(["threads"].concat(root.query ? [root.query] : []).concat(root.showQuick ? ["--quick"] : []));
        if (!sock.connected) { offline(["tasks"]); offline(["watchers"]); }
    }

    function send(o) {
        if (!sock.connected) return false;
        sock.write(JSON.stringify(o) + "\n");
        sock.flush();
        return true;
    }
    function ask(text) {
        text = text.trim();
        if (!text) return;
        if (root.mode === "TASK") send({op: "task", text: text});
        else {
            // the reply lands in the current thread: show that one
            if (root.shownThread && root.shownThread.id !== root.current) {
                if (root.current !== null) openThread(root.current); else { root.messages = []; root.shownThread = null; }
            }
            send({op: "ask", text: text});
        }
    }
    function openThread(id) {
        if (sock.connected) send({op: "thread", id: id}); else offline(["thread", String(id)]);
    }
    function resume(id) { send({op: "resume", id: id}); }
    function newThread() { root.messages = []; root.shownThread = null; send({op: "new"}); }
    function search(q) { root.query = q; refresh(); }
    function setQuick(on) { root.showQuick = on; refresh(); }
    function selectTask(id) {
        root.selectedTask = id; root.taskLines = [];
        if (sock.connected) send({op: "task_log", id: id}); else offline(["task", String(id)]);
    }
    function cancelTask(id) { send({op: "cancel", id: id}); }
    function resumeTask(id) { send({op: "task_resume", id: id}); }
    function answer(id, yes) { send({op: "answer", id: id, yes: yes}); }
    function pauseWatch(id, on) { send({op: "watch_pause", id: id, on: on}); }
    function stopWatch(id) { send({op: "watch_stop", id: id}); }

    function upsert(list, item) {
        const out = list.filter(x => x.id !== item.id);
        out.unshift(item);
        return out;
    }

    function handle(m) {
        switch (m.ev) {
        case "state":
            if (m.current !== undefined) {
                root.current = m.current;
                if (root.open && !root.shownThread && m.current !== null) openThread(m.current);
            }
            if (m.busy !== undefined) root.busy = m.busy;
            break;
        case "threads":
            if ((m.q || "") === root.query) root.threads = m.items;
            break;
        case "thread":
            if (m.item && (root.showQuick || m.item.kind !== "quick") && !root.query) root.threads = upsert(root.threads, m.item);
            break;
        case "messages":
            root.shownThread = m.thread; root.messages = m.items;
            break;
        case "message": {
            const t = m.thread;
            // only a conversation turn makes its thread current; a background task's thread never does
            const task = t.kind === "task" || m.item.source === "task";
            if (!task) root.current = t.id;
            if (root.showQuick || t.kind !== "quick") { if (!root.query) root.threads = upsert(root.threads, t); }
            if ((!root.shownThread && !task) || (root.shownThread && root.shownThread.id === t.id)) {
                root.shownThread = t;
                root.messages = root.messages.concat([m.item]);
            }
            break;
        }
        case "busy":
            root.busy = m.on; root.busyText = m.on ? (m.text || "") : ""; if (!m.on) root.liveTool = "";
            break;
        case "tool": root.liveTool = m.label; break;
        case "tasks": root.tasks = m.items; break;
        case "task": {
            const i = root.tasks.findIndex(x => x.id === m.item.id);
            const copy = root.tasks.slice();
            if (i >= 0) copy[i] = m.item; else copy.unshift(m.item);
            root.tasks = copy;
            if (root.selectedTask === null) root.selectedTask = m.item.id;
            break;
        }
        case "task_log": if (m.id === root.selectedTask) root.taskLines = m.items; break;
        case "task_line":
            if (m.id === root.selectedTask) root.taskLines = root.taskLines.concat([{kind: m.kind, text: m.text, ts: m.ts}]).slice(-300);
            break;
        case "confirm": root.confirms = root.confirms.filter(c => c.id !== m.item.id).concat([m.item]); break;
        case "confirm_done": root.confirms = root.confirms.filter(c => c.id !== m.id); break;
        case "usage": root.usage = Object.assign({}, root.usage, m); break;
        case "watchers": root.watchers = m.items; break;
        case "watch": {
            const i = root.watchers.findIndex(x => x.id === m.item.id);
            const copy = root.watchers.slice();
            if (i >= 0) copy[i] = m.item; else copy.unshift(m.item);
            root.watchers = copy;
            break;
        }
        }
    }

    Socket {
        id: sock
        path: (Quickshell.env("XDG_RUNTIME_DIR") || "/run/user/1000") + "/jarvis/app.sock"
        parser: SplitParser {
            onRead: data => { try { root.handle(JSON.parse(data)); } catch (e) { console.log("jarvis app: " + e); } }
        }
        onConnectedChanged: { if (connected) root.refresh(); else { root.busy = false; root.confirms = []; } }
    }
    // Connect whenever the voice process is up; after a restart (dock, reload) try again
    Timer {
        interval: 2000; repeat: true; triggeredOnStart: true
        running: JarvisState.online && !sock.connected
        onTriggered: { sock.connected = false; sock.connected = true; }
    }

    // Offline: read-only history from the database
    Process {
        id: offlineProc
        stdout: SplitParser { onRead: data => { try { root.handle(JSON.parse(data)); } catch (e) {} } }
    }
    property var offlineQueue: []
    function offline(args) {
        if (offlineProc.running) { root.offlineQueue = root.offlineQueue.concat([args]); return; }
        offlineProc.command = [root.bin, "app-data"].concat(args);
        offlineProc.running = true;
    }
    Connections {
        target: offlineProc
        function onExited() {
            if (root.offlineQueue.length) { const next = root.offlineQueue[0]; root.offlineQueue = root.offlineQueue.slice(1); root.offline(next); }
        }
    }
}
