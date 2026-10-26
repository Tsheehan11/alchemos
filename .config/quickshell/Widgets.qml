pragma Singleton
// Desktop widgets: clocks, timers, stopwatches, now playing, system stats, notes.
//
// Each widget is { id, type, screen, position, pinned, params }:
//   screen   — a Roles role: "main" | "diag" | "media" (not a port name, so a dock that
//              renames DP-5 → DP-7 doesn't lose them). Undocked, everything shows on
//              the laptop; docking again puts them back.
//   position — one of POSITIONS; widgets sharing a slot stack.
//   pinned   — above windows (layer Top) instead of hiding behind them like the panels.
//   size     — small | normal | large | huge (stats turns into a full dashboard when large).
// Saved to widgets.json next to this file (not committed, like settings.json).
//
// Types are the files in widgets/ (Clock.qml → "clock"): a new type is one QML file there.
// Shown by WidgetLayer / WidgetWindow; driven by `qs ipc call widgets …` (shell.qml),
// Settings → WIDGETS, and Jarvis (mcp/stark_actions.py widget_* tools).
//
// Timers live here, not in their window: they go off even while hidden (chime, Govee
// flash, the Jarvis toast, a spoken line), and keep their end time across restarts.
import QtQuick
import Qt.labs.folderlistmodel
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root

    readonly property var positions: ["top-left", "top", "top-right", "left", "center", "right", "bottom-left", "bottom", "bottom-right"]
    readonly property var roles: ["main", "diag", "media"]
    readonly property var defaultPosition: ({ clock: "top-right", timer: "top-right", stopwatch: "top-right", media: "bottom-right", stats: "right", note: "left" })
    readonly property string home: Quickshell.env("HOME")
    readonly property int gap: 14
    readonly property var sizes: ({ small: 0.8, normal: 1.0, large: 1.5, huge: 2.0 })

    property var items: []
    property int seq: 0
    property var heights: ({})          // id → height of its window (reported by WidgetWindow), for stacking
    property var widths: ({})           // id → width, for the move ghost
    property bool loaded: false

    // ── types: widgets/*.qml ──
    property var types: []
    FolderListModel {
        id: typeFiles
        folder: Qt.resolvedUrl("widgets")
        nameFilters: ["*.qml"]
        showDirs: false
        onStatusChanged: if (status === FolderListModel.Ready) root.scanTypes()
        onCountChanged: root.scanTypes()
    }
    function scanTypes() {
        const t = [];
        for (let i = 0; i < typeFiles.count; i++) t.push(typeFiles.get(i, "fileBaseName").toLowerCase());
        root.types = t;
    }
    function source(type) {
        for (let i = 0; i < typeFiles.count; i++)
            if (typeFiles.get(i, "fileBaseName").toLowerCase() === type) return Qt.resolvedUrl("widgets/" + typeFiles.get(i, "fileName"));
        return "";
    }

    // ── screens ──
    function screenOf(name) { return Quickshell.screens.find(s => s.name === name) || null; }
    function currentRole() {
        const r = Roles.role(screenOf(Hyprland.focusedMonitor?.name || ""));
        return root.roles.indexOf(r) >= 0 ? r : "main";
    }
    // Spoken / typed screen → role ("" = not a screen). "" or "current" = where the cursor is.
    function normScreen(s) {
        s = String(s || "").toLowerCase().replace(/[_\s]+/g, " ").trim();
        if (s === "" || s === "-" || s === "current" || s === "here" || s === "this") return currentRole();
        if (root.roles.indexOf(s) >= 0) return s;
        if (/^(laptop|laptop screen|edp|edp 1|edp-1|media|built in|internal)$/.test(s)) return "media";
        if (/^(1|one|monitor 1|monitor one|first|first monitor|left|left monitor|main monitor|main screen|primary)$/.test(s)) return "main";
        if (/^(2|two|monitor 2|monitor two|second|second monitor|middle|middle monitor|diagnostics|diag screen)$/.test(s)) return "diag";
        const out = Quickshell.screens.find(x => x.name.toLowerCase() === s);
        if (out) { const r = Roles.role(out); return root.roles.indexOf(r) >= 0 ? r : "main"; }
        return "";
    }
    // The screen a role shows on now: undocked (or a missing monitor) → the main screen
    function screenFor(role) {
        return Quickshell.screens.find(s => Roles.role(s) === role)
            || Quickshell.screens.find(s => Roles.role(s) === "main")
            || Quickshell.screens[0] || null;
    }
    function normPosition(p) {
        p = String(p || "").toLowerCase().replace(/centre/g, "center").replace(/middle/g, "center")
            .replace(/upper/g, "top").replace(/lower/g, "bottom").replace(/[_\s]+/g, "-").replace(/^the-/, "").trim();
        p = p.replace(/^(top|bottom)-center$/, "$1").replace(/^center-(left|right)$/, "$1").replace(/^(left|right)-center$/, "$1")
             .replace(/^(left|right)-(top|bottom)$/, "$2-$1");
        return root.positions.indexOf(p) >= 0 ? p : "";
    }

    // ── lookups ──
    function get(id) { return root.items.find(i => i.id === id) || null; }
    function idsOn(screenName, pinned) {
        return root.items.filter(i => screenFor(i.screen)?.name === screenName && (pinned === undefined || (i.pinned === true) === pinned)).map(i => i.id);
    }
    // "clock3" | "clock" | "clock:diag" | "diag" | "all" → matching widgets, oldest first
    function match(query) {
        query = String(query || "").toLowerCase().trim();
        const exact = root.items.filter(i => i.id === query);
        if (exact.length) return exact;
        const [what, where] = query.split(/[:\s]+/);
        const role = where ? normScreen(where) : "";
        if (where && role === "") return [];
        if (what === "all" || what === "*") return root.items.filter(i => !role || i.screen === role);
        if (root.types.indexOf(what) >= 0) return root.items.filter(i => i.type === what && (!role || i.screen === role));
        const asScreen = normScreen(what);
        if (what && asScreen && !where && what !== "current") return root.items.filter(i => i.screen === asScreen);
        return [];
    }
    // Pixels from the slot's edge for a stacked widget: the cards before it in the same slot
    function stackOffset(id) {
        const it = get(id);
        if (!it) return 0;
        const name = screenFor(it.screen)?.name;
        let off = 0;
        for (const o of root.items) {
            if (o.id === id) break;
            if (o.position === it.position && screenFor(o.screen)?.name === name) off += (root.heights[o.id] || 0) + root.gap;
        }
        return off;
    }
    function slotHeight(id) {     // the whole stack in this widget's slot (centre rows centre the stack)
        const it = get(id);
        if (!it) return 0;
        const name = screenFor(it.screen)?.name;
        let h = -root.gap;
        for (const o of root.items)
            if (o.position === it.position && screenFor(o.screen)?.name === name) h += (root.heights[o.id] || 0) + root.gap;
        return Math.max(0, h);
    }
    function setSize(id, w, h) {
        if (root.heights[id] !== h) { const m = Object.assign({}, root.heights); m[id] = h; root.heights = m; }
        if (root.widths[id] !== w) { const m = Object.assign({}, root.widths); m[id] = w; root.widths = m; }
    }
    function normSize(s) {
        s = String(s || "").toLowerCase().trim();
        if (/^(small|smaller|tiny|little|mini|compact)$/.test(s)) return "small";
        if (/^(normal|medium|default|regular|standard|mid)$/.test(s)) return "normal";
        if (/^(large|big|bigger|larger|xl)$/.test(s)) return "large";
        if (/^(huge|giant|gigantic|enormous|massive|full|biggest|max|maximum|xxl|dashboard)$/.test(s)) return "huge";
        return "";
    }

    // ── widget maker: right-click the empty desktop (DesktopMenuArea → WidgetMaker) ──
    property var maker: null            // { screen: name, x, y } (screen pixels) while open
    function openMaker(screen) {
        makerProc.screenName = screen ? screen.name : "";
        makerProc.running = true;
    }
    function closeMaker() { root.maker = null; }
    // Add from the maker: lands in the slot nearest where you right-clicked
    function addAt(type, params) {
        const m = root.maker, s = m ? screenOf(m.screen) : null;
        if (!s) return { ok: false, error: "no screen" };
        let role = Roles.role(s);
        if (root.roles.indexOf(role) < 0) role = "main";
        const huge = params && params.size === "huge";
        const r = add(type, role, huge ? "center" : slotAt(s, m.x, m.y), params || {});
        closeMaker();
        return r;
    }
    Process {
        id: makerProc
        property string screenName: ""
        command: ["hyprctl", "cursorpos", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                let c;
                try { c = JSON.parse(text); } catch (e) { return; }
                const s = root.screenOf(makerProc.screenName) || root.screenAt(c.x, c.y);
                if (s) root.maker = { screen: s.name, x: c.x - s.x, y: c.y - s.y };
            }
        }
    }

    // ── moving by mouse (WidgetCard) ──
    function screenAt(x, y) {
        return Quickshell.screens.find(s => x >= s.x && x < s.x + s.width && y >= s.y && y < s.y + s.height) || null;
    }
    function slotAt(s, cx, cy) {       // a point on screen s (screen pixels) → slot
        const c = cx < s.width / 3 ? "left" : cx > s.width * 2 / 3 ? "right" : "";
        const r = cy < s.height / 3 ? "top" : cy > s.height * 2 / 3 ? "bottom" : "";
        return (r && c) ? r + "-" + c : (r || c || "center");
    }
    function roleOf(s) { const r = Roles.role(s); return root.roles.indexOf(r) >= 0 ? r : "main"; }
    function place(id, s, position) {
        const it = get(id), role = roleOf(s);
        if (it && (it.screen !== role || it.position !== position)) update(id, { screen: role, position: position });
    }
    // End of a drag. If the pointer went on to another monitor the press ended at this screen's
    // edge, so ask Hyprland where the cursor really is: another screen → the slot under it there
    // (card centred on the cursor), else the slot the card was dropped in.
    function drop(id, s, slot, w, h) {
        dropProc.req = { id: id, screen: s.name, slot: slot, w: w, h: h };
        dropProc.running = true;
    }
    Process {
        id: dropProc
        property var req: null
        command: ["hyprctl", "cursorpos", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                const q = dropProc.req, s = root.screenOf(q ? q.screen : "");
                if (!q || !s) return;
                let c = null;
                try { c = JSON.parse(text); } catch (e) {}
                const o = c ? root.screenAt(c.x, c.y) : null;
                if (o && o.name !== s.name) root.place(q.id, o, root.slotAt(o, c.x - o.x, c.y - o.y));
                else root.place(q.id, s, q.slot);
            }
        }
    }

    // ── params: every key is checked; anything else is dropped ──
    function parseDuration(p) {
        let s = 0;
        if (p.seconds !== undefined) s += Number(p.seconds);
        if (p.minutes !== undefined) s += Number(p.minutes) * 60;
        if (p.hours !== undefined) s += Number(p.hours) * 3600;
        return isFinite(s) ? Math.round(s) : 0;
    }
    function cleanParams(type, p) {
        p = (p && typeof p === "object") ? p : {};
        const out = {};
        if (typeof p.label === "string" && p.label.trim()) out.label = p.label.trim().slice(0, 32);
        if (type === "note") out.text = typeof p.text === "string" ? p.text.slice(0, 600) : "";
        if (type === "clock") {
            if (typeof p.tz === "string" && /^[A-Za-z_]+(\/[A-Za-z0-9_+\-]+){0,2}$/.test(p.tz)) out.tz = p.tz;
            out.analog = p.analog === true || p.style === "analog";
        }
        if (type === "timer") {
            const secs = parseDuration(p);
            if (!(secs >= 1 && secs <= 86400)) return { error: "timer needs a duration between 1 second and 24 hours (seconds / minutes / hours)" };
            out.duration = secs;
            out.end = Date.now() + secs * 1000;
            out.done = false;
        }
        if (type === "stopwatch") { out.running = p.running !== false; out.start = Date.now(); out.acc = 0; }
        return out;
    }

    // ── actions (IPC, Settings, Jarvis) → result objects ──
    function add(type, screen, position, params) {
        type = String(type || "").toLowerCase().trim();
        if (root.types.indexOf(type) < 0) return { ok: false, error: "unknown widget type " + type + " (have: " + root.types.join(", ") + ")" };
        const role = normScreen(screen);
        if (!role) return { ok: false, error: "unknown screen " + screen + " (main, diag, media / laptop, current)" };
        const huge = params && normSize(params.size) === "huge";       // a dashboard-sized card goes in the middle
        const pos = (position === "" || position === "-" || position === undefined) ? (huge ? "center" : root.defaultPosition[type] || "top-right") : normPosition(position);
        if (!pos) return { ok: false, error: "unknown position " + position + " (" + root.positions.join(", ") + ")" };
        const pr = cleanParams(type, params);
        if (pr.error) return { ok: false, error: pr.error };
        root.seq += 1;
        const size = params && params.size ? normSize(params.size) : "normal";
        if (!size) return { ok: false, error: "unknown size " + params.size + " (small, normal, large, huge)" };
        const it = { id: type + root.seq, type: type, screen: role, position: pos, pinned: params && params.pinned === true, size: size, params: pr };
        root.items = root.items.concat([it]);
        save();
        return { ok: true, id: it.id, type: type, screen: role, position: pos, size: size, shown_on: screenFor(role)?.name || "" };
    }
    function remove(query) {
        const hit = match(query).map(i => i.id);
        if (!hit.length) return { ok: false, error: "no widget matches " + query };
        root.items = root.items.filter(i => hit.indexOf(i.id) < 0);
        save();
        return { ok: true, removed: hit };
    }
    function move(query, screen, position) {
        const hits = match(query);
        if (!hits.length) return { ok: false, error: "no widget matches " + query };
        const it = hits[hits.length - 1];          // the newest one
        const keepScreen = screen === "" || screen === "-" || screen === undefined;
        const keepPos = position === "" || position === "-" || position === undefined;
        const role = keepScreen ? it.screen : normScreen(screen);
        const pos = keepPos ? it.position : normPosition(position);
        if (!role) return { ok: false, error: "unknown screen " + screen };
        if (!pos) return { ok: false, error: "unknown position " + position };
        update(it.id, { screen: role, position: pos });
        return { ok: true, id: it.id, screen: role, position: pos };
    }
    function resize(query, size) {
        const hits = match(query);
        if (!hits.length) return { ok: false, error: "no widget matches " + query };
        const it = hits[hits.length - 1];
        let sz = normSize(size);
        if (String(size).toLowerCase() === "bigger" || String(size).toLowerCase() === "smaller") {   // one step
            const order = ["small", "normal", "large", "huge"], i = order.indexOf(it.size || "normal");
            sz = order[Math.max(0, Math.min(3, i + (String(size).toLowerCase() === "bigger" ? 1 : -1)))];
        }
        if (!sz) return { ok: false, error: "unknown size " + size + " (small, normal, large, huge, bigger, smaller)" };
        update(it.id, { size: sz });
        return { ok: true, id: it.id, size: sz };
    }
    function pin(query, on) {
        const hits = match(query);
        if (!hits.length) return { ok: false, error: "no widget matches " + query };
        for (const h of hits) update(h.id, { pinned: on });
        return { ok: true, pinned: on, ids: hits.map(h => h.id) };
    }
    function clear(screen) {
        const all = String(screen || "").toLowerCase() === "all";
        const role = all ? "" : normScreen(screen);
        if (!all && !role) return { ok: false, error: "unknown screen " + screen };
        const gone = root.items.filter(i => all || i.screen === role).map(i => i.id);
        root.items = root.items.filter(i => gone.indexOf(i.id) < 0);
        save();
        return { ok: true, removed: gone };
    }
    function list() {
        const now = Date.now();
        return root.items.map(i => {
            const o = { id: i.id, type: i.type, screen: i.screen, position: i.position, pinned: i.pinned, size: i.size || "normal", shown_on: screenFor(i.screen)?.name || "" };
            if (i.params.label) o.label = i.params.label;
            if (i.type === "timer") { o.seconds_left = Math.max(0, Math.round((i.params.end - now) / 1000)); o.done = i.params.done; }
            if (i.type === "clock" && i.params.tz) o.tz = i.params.tz;
            if (i.type === "note") o.text = i.params.text;
            return o;
        });
    }
    function update(id, fields) {
        root.items = root.items.map(i => i.id === id ? Object.assign({}, i, fields) : i);
        save();
    }
    function setParams(id, fields) {
        const it = get(id);
        if (it) update(id, { params: Object.assign({}, it.params, fields) });
    }

    // ── timers ──
    Timer {
        interval: 1000; repeat: true
        running: root.loaded && root.items.some(i => i.type === "timer")
        onTriggered: root.checkTimers(false)
    }
    function checkTimers(atStartup) {
        const now = Date.now();
        for (const i of root.items) {
            if (i.type !== "timer") continue;
            if (!i.params.done && now >= i.params.end) {
                setParams(i.id, { done: true });
                // Went off while the HUD was down: ring if it's recent, otherwise just show it done
                if (!atStartup || now - i.params.end < 10 * 60000) root.alarm(i, atStartup);
            } else if (i.params.done && now - i.params.end > 5 * 60000) {
                remove(i.id);              // a finished timer clears itself after five minutes
            }
        }
    }
    function alarm(it, late) {
        const label = it.params.label || "";
        Quickshell.execDetached(["pw-play", "-P", "{ media.name = \"Jarvis timer\" state.restore-props = false }", root.home + "/.config/quickshell/sounds/widget-alarm.wav"]);
        Quickshell.execDetached(["stark-govee", "anim", "alert"]);
        JarvisState.alert("TIMER", (label ? label.toUpperCase() + " · " : "") + "TIME'S UP");
        if (Theme.cfg.jarvisSpeak) {
            const line = (late ? "While I was away, sir, your " : "Your ") + (label ? label + " " : "") + "timer is done" + (late ? "." : ", sir.");
            speakTimer.line = line;
            speakTimer.restart();
        }
    }
    Timer {     // after the chime
        id: speakTimer
        property string line: ""
        interval: 900
        onTriggered: Quickshell.execDetached([root.home + "/.local/bin/jarvis", "--say", line])
    }

    // ── persistence ──
    FileView {
        id: store
        path: root.home + "/.config/quickshell/widgets.json"
        onLoaded: {
            try {
                const d = JSON.parse(text());
                root.seq = d.seq || 0;
                root.items = (d.items || []).filter(i => i && i.id && i.type && root.roles.indexOf(i.screen) >= 0 && root.positions.indexOf(i.position) >= 0);
            } catch (e) {}
            root.loaded = true;
            root.checkTimers(true);
        }
        onLoadFailed: root.loaded = true
    }
    // Written right away: changes are rare (add / move / close), and a `pkill qs` right after one must not lose it
    function save() { if (root.loaded) store.setText(JSON.stringify({ seq: root.seq, items: root.items }, null, 1) + "\n"); }
}
