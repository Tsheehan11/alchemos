pragma Singleton
// Desktop widgets: clocks, timers, stopwatches, now playing, system stats, notes, agenda, due dates,
// Orrin status, Claude usage, weather, network, DJ deck (data for the last seven: OrrinFeed.qml).
//
// Each widget is { id, type, mon, fx, fy, scale, pinned, params }:
//   mon      — the monitor it lives on, by Hyprland description (Roles.keyOf: the laptop on its
//              own is "<desc>@solo", so docked and undocked keep separate layouts, like screen
//              roles). A widget whose monitor isn't plugged in is hidden, not moved, and comes
//              back to its spot when the monitor does.
//   fx, fy   — where it sits, as a fraction of the room left for it on that monitor:
//              x = fx · (width − w), y = bar + fy · (height − bar − h). 0 = flush left / top,
//              1 = right / bottom, 0.5 = centred, so it survives resolution / scale changes and
//              a widget on an edge stays on that edge whatever its size.
//   scale    — its size (corner handle, voice "bigger"), clamped per type (WidgetBody min/maxScale).
//   pinned   — above windows (layer Top) instead of hiding behind them like the panels.
//   pending  — placement to finish once the card knows its size (add, voice moves, reset,
//              migration): it's clamped and nudged off other widgets, then turned into fx/fy.
// Saved to widgets.json next to this file (not committed, like settings.json). Old files
// ({ screen: role, position: slot }) are migrated where the widgets were showing.
//
// Types are the files in widgets/ (Clock.qml → "clock"): a new type is one QML file there.
// Shown by WidgetLayer / WidgetSurface / WidgetCard; driven by `qs ipc call widgets …`
// (shell.qml), Settings → WIDGETS / HUD, and Orrin (mcp/alchemos_actions.py widget_* tools).
//
// Timers live here, not in their window: they go off even while hidden (chime, Govee
// flash, the Orrin toast, a spoken line), and keep their end time across restarts.
import QtQuick
import Qt.labs.folderlistmodel
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root

    readonly property var positions: ["top-left", "top", "top-right", "left", "center", "right", "bottom-left", "bottom", "bottom-right"]
    readonly property var roles: ["main", "diag", "media"]
    readonly property var defaultPosition: ({ clock: "top-right", timer: "top-right", stopwatch: "top-right", media: "bottom-right", stats: "right", note: "left",
                                              calendar: "top-left", due: "left", orrin: "bottom-left", usage: "bottom-left", weather: "top-right", network: "bottom-right", dj: "right" })
    readonly property string home: Quickshell.env("HOME")
    readonly property int gap: 14
    readonly property var sizes: ({ small: 0.8, normal: 1.0, large: 1.5, huge: 2.0 })

    // ── geometry (screen pixels) ──
    readonly property int bar: 40           // nothing goes above this (the bar is 34)
    readonly property int gutter: 28        // edge snap / named positions keep this far from the edges
    readonly property int topGutter: 54     // …and this far down from the top (under the bar)
    readonly property int snapDist: 10

    property var items: []
    property int seq: 0
    property bool loaded: false
    // id → { s: screen name, x, y, w, h }: where each card is drawn (reported by WidgetCard).
    // Mutated in place on purpose: nothing binds to it, it's read when dragging / placing.
    property var rects: ({})

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
    function keyOf(s) { return s ? Roles.keyOf(s) : ""; }
    // The monitor a key names, if it's plugged in (and descriptions are known)
    function screenOfKey(key) {
        if (!key || !Roles.ready) return null;
        return Quickshell.screens.find(s => Roles.keyOf(s) === key) || null;
    }
    function screenOfItem(it) { return it && it.mon ? screenOfKey(it.mon) : null; }
    function roleOf(s) { const r = Roles.role(s); return root.roles.indexOf(r) >= 0 ? r : "main"; }
    function roleOfItem(it) { const s = screenOfItem(it); return s ? roleOf(s) : ""; }
    function currentRole() { return roleOf(screenOf(Hyprland.focusedMonitor?.name || "")); }
    // Spoken / typed screen → role ("" = not a screen). "" or "current" = where the cursor is.
    function normScreen(s) {
        s = String(s || "").toLowerCase().replace(/[_\s]+/g, " ").trim();
        if (s === "" || s === "-" || s === "current" || s === "here" || s === "this") return currentRole();
        if (root.roles.indexOf(s) >= 0) return s;
        if (/^(laptop|laptop screen|edp|edp 1|edp-1|media|built in|internal)$/.test(s)) return "media";
        if (/^(1|one|monitor 1|monitor one|first|first monitor|left|left monitor|main monitor|main screen|primary)$/.test(s)) return "main";
        if (/^(2|two|monitor 2|monitor two|second|second monitor|middle|middle monitor|diagnostics|diag screen)$/.test(s)) return "diag";
        const out = Quickshell.screens.find(x => x.name.toLowerCase() === s);
        if (out) return roleOf(out);
        return "";
    }
    // Spoken / typed screen → a plugged-in screen, or null. Port names, descriptions, tv, laptop,
    // "monitor N" (Roles.targets), then the role words above. Undocked, "laptop" / "main" /
    // "current" are the laptop and "monitor 2" is nothing (so nothing lands on the wrong screen).
    function screenFromQuery(q) {
        const t = String(q || "").toLowerCase().replace(/[_]+/g, " ").replace(/\s+/g, " ").replace(/^the /, "").trim();
        const m = t.match(/^(?:monitor|screen|display) (one|two|three)$/);
        const direct = Roles.targets(m ? t.replace(m[1], { one: "1", two: "2", three: "3" }[m[1]]) : t);
        if (direct.length === 1) return direct[0];
        const role = normScreen(t);
        if (!role) return null;
        if (!Roles.docked) return role === "main" ? Quickshell.screens[0] || null : (role === "media" ? Quickshell.screens.find(s => s.name === Roles.laptopName) || null : null);
        return Quickshell.screens.find(s => Roles.role(s) === role) || null;
    }
    function normPosition(p) {
        p = String(p || "").toLowerCase().replace(/centre/g, "center").replace(/middle/g, "center")
            .replace(/upper/g, "top").replace(/lower/g, "bottom").replace(/[_\s]+/g, "-").replace(/^the-/, "")
            .replace(/-(corner|side|of-the-screen)$/, "").trim();
        p = p.replace(/^(top|bottom)-center$/, "$1").replace(/^center-(left|right)$/, "$1").replace(/^(left|right)-center$/, "$1")
             .replace(/^(left|right)-(top|bottom)$/, "$2-$1");
        return root.positions.indexOf(p) >= 0 ? p : "";
    }

    // ── geometry helpers ──
    function clampX(s, x, w) { return Math.round(Math.max(0, Math.min(s.width - w, x))); }
    function clampY(s, y, h) { return Math.round(Math.max(root.bar, Math.min(s.height - h, y))); }
    function toFrac(s, x, y, w, h) {
        const rw = s.width - w, rh = s.height - root.bar - h;
        return { fx: rw > 0 ? Math.max(0, Math.min(1, x / rw)) : 0, fy: rh > 0 ? Math.max(0, Math.min(1, (y - root.bar) / rh)) : 0 };
    }
    function fromFrac(s, fx, fy, w, h) {
        return { x: clampX(s, fx * (s.width - w), w), y: clampY(s, root.bar + fy * (s.height - root.bar - h), h) };
    }
    // A named position → pixels (the old slots, kept off the edges by the gutter)
    function slotXY(s, pos, w, h) {
        const c = pos.endsWith("left") ? 0 : pos.endsWith("right") ? 2 : 1;
        const r = pos.startsWith("top") ? 0 : pos.startsWith("bottom") ? 2 : 1;
        return { x: c === 0 ? root.gutter : c === 2 ? s.width - w - root.gutter : Math.round((s.width - w) / 2),
                 y: r === 0 ? root.topGutter : r === 2 ? s.height - h - root.gutter : Math.round((s.height - h) / 2) };
    }
    // …and back: the slot a widget is nearest to (list() / Orrin still talk in slots)
    function slotOf(it) {
        if (!it || it.fx === undefined) return it && it.pending && it.pending.pos ? it.pending.pos : "center";
        const c = it.fx < 0.25 ? "left" : it.fx > 0.75 ? "right" : "";
        const r = it.fy < 0.25 ? "top" : it.fy > 0.75 ? "bottom" : "";
        return (r && c) ? r + "-" + c : (r || c || "center");
    }
    function slotAt(s, cx, cy) {       // a point on screen s → slot (the maker's hint)
        const c = cx < s.width / 3 ? "left" : cx > s.width * 2 / 3 ? "right" : "";
        const r = cy < s.height / 3 ? "top" : cy > s.height * 2 / 3 ? "bottom" : "";
        return (r && c) ? r + "-" + c : (r || c || "center");
    }
    // Other cards on screen s (as drawn), for snapping and overlap
    function othersOn(s, id) {
        const out = [];
        for (const k in root.rects) {
            const r = root.rects[k];
            if (k === id || !r || r.s !== s.name || root.closing[k] === true) continue;
            const it = get(k);
            if (!it || it.pending) continue;          // not placed yet
            out.push(r);
        }
        return out;
    }
    function hits(a, b) { return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h; }

    // Soft snap while dragging: screen edges (at the gutter), the centre lines, and other cards'
    // edges / centres. → { x, y, v: [guide x…], h: [guide y…] }
    function snap(s, id, x, y, w, h) {
        const d = root.snapDist, g = root.gap;
        const xs = [[root.gutter, root.gutter], [s.width - root.gutter - w, s.width - root.gutter], [(s.width - w) / 2, s.width / 2]];
        const ys = [[root.topGutter, root.topGutter], [s.height - root.gutter - h, s.height - root.gutter], [(s.height - h) / 2, s.height / 2]];
        for (const o of othersOn(s, id)) {
            xs.push([o.x, o.x], [o.x + o.w - w, o.x + o.w], [o.x + o.w + g, o.x + o.w + g / 2], [o.x - g - w, o.x - g / 2], [o.x + (o.w - w) / 2, o.x + o.w / 2]);
            ys.push([o.y, o.y], [o.y + o.h - h, o.y + o.h], [o.y + o.h + g, o.y + o.h + g / 2], [o.y - g - h, o.y - g / 2], [o.y + (o.h - h) / 2, o.y + o.h / 2]);
        }
        function best(list, v) {
            let b = null;
            for (const c of list) if (Math.abs(c[0] - v) <= d && (!b || Math.abs(c[0] - v) < Math.abs(b[0] - v))) b = c;
            return b;
        }
        const bx = best(xs, x), by = best(ys, y);
        return { x: bx ? Math.round(bx[0]) : x, y: by ? Math.round(by[0]) : y, v: bx ? [Math.round(bx[1])] : [], h: by ? [Math.round(by[1])] : [] };
    }

    // Clamp inside the screen (under the bar), then if it overlaps another card, the nearest
    // spot where it doesn't: beside / above / below the cards in the way, else a scan of the screen.
    function resolve(s, id, x, y, w, h) {
        const others = othersOn(s, id), g = root.gap;
        const cx = clampX(s, x, w), cy = clampY(s, y, h);
        function free(px, py) {
            if (px < 0 || py < root.bar || px + w > s.width || py + h > s.height) return false;
            const r = { x: px - g / 2 + 0.5, y: py - g / 2 + 0.5, w: w + g - 1, h: h + g - 1 };
            for (const o of others) if (hits(r, o)) return false;
            return true;
        }
        if (free(cx, cy)) return { x: cx, y: cy };
        const xs = [cx], ys = [cy];
        for (const o of others) { xs.push(o.x - g - w, o.x + o.w + g, o.x, o.x + o.w - w); ys.push(o.y - g - h, o.y + o.h + g, o.y, o.y + o.h - h); }
        let best = null, bd = Infinity;
        for (const px of xs) for (const py of ys) {
            const qx = clampX(s, px, w), qy = clampY(s, py, h);
            const dd = Math.hypot(qx - cx, qy - cy);
            if (dd < bd && free(qx, qy)) { best = { x: qx, y: qy }; bd = dd; }
        }
        if (best) return best;
        for (let py = root.bar; py + h <= s.height; py += 16)          // crowded: scan for any gap
            for (let px = 0; px + w <= s.width; px += 16) {
                const dd = Math.hypot(px - cx, py - cy);
                if (dd < bd && free(px, py)) { best = { x: px, y: py }; bd = dd; }
            }
        return best || { x: cx, y: cy };
    }

    // ── lookups ──
    function get(id) { return root.items.find(i => i.id === id) || null; }
    function idsOn(screenName, pinned) {
        return root.items.filter(i => screenOfItem(i)?.name === screenName && (pinned === undefined || (i.pinned === true) === pinned)).map(i => i.id);
    }
    // "clock3" | "clock" | "clock:diag" | "diag" | "all" → matching widgets, oldest first
    function match(query) {
        query = String(query || "").toLowerCase().trim();
        const items = root.items.filter(i => root.closing[i.id] !== true);
        const exact = items.filter(i => i.id === query);
        if (exact.length) return exact;
        const [what, where] = query.split(/[:\s]+/);
        const role = where ? normScreen(where) : "";
        if (where && role === "") return [];
        if (what === "all" || what === "*") return items.filter(i => !role || roleOfItem(i) === role);
        if (root.types.indexOf(what) >= 0) return items.filter(i => i.type === what && (!role || roleOfItem(i) === role));
        const asScreen = normScreen(what);
        if (what && asScreen && !where && what !== "current") return items.filter(i => roleOfItem(i) === asScreen);
        return [];
    }
    function normSize(s) {
        s = String(s || "").toLowerCase().trim();
        if (/^(small|smaller|tiny|little|mini|compact)$/.test(s)) return "small";
        if (/^(normal|medium|default|regular|standard|mid)$/.test(s)) return "normal";
        if (/^(large|big|bigger|larger|xl)$/.test(s)) return "large";
        if (/^(huge|giant|gigantic|enormous|massive|full|biggest|max|maximum|xxl|dashboard)$/.test(s)) return "huge";
        return "";
    }
    // scale → the size name bodies lay out for (stats turns into a dashboard from "large")
    function sizeName(k) { return k < 0.9 ? "small" : k < 1.25 ? "normal" : k < 1.75 ? "large" : "huge"; }
    function scaleOf(it) { return it ? (it.scale || root.sizes[it.size || "normal"] || 1) : 1; }
    // Per-type size limits, reported by each card from its body (WidgetBody.minScale / maxScale)
    property var limits: ({})
    function setLimits(type, lo, hi) { if (!root.limits[type]) root.limits[type] = { lo: lo, hi: hi }; }
    function clampScale(type, k) {
        const l = root.limits[type] || { lo: 0.6, hi: 2.5 };
        return Math.max(l.lo, Math.min(l.hi, k));
    }

    // ── placing ──
    // Cards report where they're drawn; any widget still waiting to be placed is placed then.
    // owner = the card: when a widget changes surface (pin / unpin, another monitor) the new card
    // reports before the old one is destroyed, and the old one must not wipe the new rect.
    function setRect(id, s, x, y, w, h, owner) {
        root.rects[id] = { s: s, x: x, y: y, w: w, h: h, owner: owner || null };
        if (root.items.some(i => i.pending)) Qt.callLater(root.settle);
    }
    function dropRect(id, owner) { if (root.rects[id] && root.rects[id].owner === owner) delete root.rects[id]; }
    // Put a widget on screen s with its top-left at x, y (size w × h), clamped and nudged free,
    // and save it there. nudge = false keeps it exactly there (migration).
    function placeAt(id, s, x, y, w, h, nudge) {
        const p = nudge === false ? { x: clampX(s, x, w), y: clampY(s, y, h) } : resolve(s, id, x, y, w, h);
        const f = toFrac(s, p.x, p.y, w, h);
        root.rects[id] = Object.assign({}, root.rects[id] || {}, { s: s.name, x: p.x, y: p.y, w: w, h: h });
        const it = get(id);
        if (!it) return null;
        const fields = { mon: keyOf(s), fx: f.fx, fy: f.fy, pending: undefined };
        root.items = root.items.map(i => {
            if (i.id !== id) return i;
            const o = Object.assign({}, i, fields);
            delete o.pending; delete o.screen; delete o.position; delete o.size;
            return o;
        });
        save();
        return p;
    }
    // Widgets waiting for their size: placed in list order, each one avoiding those before it.
    //   pending.pos     a named position ("top-right")
    //   pending.at      { x, y } its centre (maker: where you right-clicked)
    //   pending.keep    keep its fractions, just nudge it free (resize, resolution)
    //   pending.legacy  { position, stackOf } migrated from a slot layout: exactly where the old
    //                   layout drew it; only widgets that stacked in one slot are nudged apart
    function settle() {
        for (const it of root.items) {
            if (!it.pending) continue;
            const s = screenOfItem(it), r = root.rects[it.id];
            if (!s || !r || r.s !== s.name) continue;      // not on screen yet
            const p = it.pending;
            let x = r.x, y = r.y;
            if (p.pos) { const q = slotXY(s, p.pos, r.w, r.h); x = q.x; y = q.y; }
            else if (p.at) { x = p.at.x - r.w / 2; y = p.at.y - r.h / 2; }
            else if (p.keep) { const q = fromFrac(s, it.fx || 0, it.fy || 0, r.w, r.h); x = q.x; y = q.y; }
            if (p.legacy) {
                const q = slotXY(s, p.legacy, r.w, r.h);
                const mates = root.items.filter(o => o.id !== it.id && !o.pending && o.mon === it.mon && o.legacySlot === p.legacy);
                const clash = mates.some(o => { const or = root.rects[o.id]; return or && hits({ x: q.x, y: q.y, w: r.w, h: r.h }, or); });
                placeAt(it.id, s, q.x, q.y, r.w, r.h, clash);
                root.items = root.items.map(i => i.id === it.id ? Object.assign({}, i, { legacySlot: p.legacy }) : i);
            } else {
                placeAt(it.id, s, x, y, r.w, r.h, true);
            }
        }
        if (!root.items.some(i => i.pending) && root.items.some(i => i.legacySlot)) {   // migration done
            root.items = root.items.map(i => { const o = Object.assign({}, i); delete o.legacySlot; return o; });
            save();
        }
    }
    function setPending(id, fields, pending) {
        root.items = root.items.map(i => i.id === id ? Object.assign({}, i, fields, { pending: pending }) : i);
        save();
        Qt.callLater(root.settle);
    }

    // ── migration: { screen: role, position: slot } → { mon, fx, fy } ──
    // Done while docked (roles mean a real monitor then); undocked, old widgets wait hidden.
    function migrate() {
        if (!root.loaded || !Roles.ready || !Roles.docked || !root.items.some(i => !i.mon && i.screen)) return;
        let n = 0;
        root.items = root.items.map(i => {
            if (i.mon || !i.screen) return i;
            const s = Quickshell.screens.find(x => Roles.role(x) === i.screen);
            if (!s || !Roles.keyOf(s)) return i;
            n++;
            const o = Object.assign({}, i, { mon: Roles.keyOf(s), scale: root.sizes[i.size || "normal"] || 1, pending: { legacy: i.position } });
            delete o.screen; delete o.position; delete o.size;
            return o;
        });
        if (n) { console.log("Widgets: migrated " + n + " widget(s) to free placement"); save(); Qt.callLater(root.settle); }
    }
    Connections { target: Roles; function onReadyChanged() { Qt.callLater(root.migrate); } function onMonsChanged() { Qt.callLater(root.migrate); } }

    // ── widget maker: right-click the empty desktop (DesktopMenuArea → WidgetMaker) ──
    property var maker: null            // { screen: name, x, y } (screen pixels) while open
    function openMaker(screen) {
        makerProc.screenName = screen ? screen.name : "";
        makerProc.running = true;
    }
    function closeMaker() { root.maker = null; }
    // Add from the maker: centred where you right-clicked
    function addAt(type, params) {
        const m = root.maker, s = m ? screenOf(m.screen) : null;
        if (!s) return { ok: false, error: "no screen" };
        const r = add(type, s.name, "-", params || {}, { x: m.x, y: m.y });
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
    // End of a drag at x, y on screen s. If the pointer went on to another monitor the press
    // ended at this screen's edge, so ask Hyprland where the cursor really is: another screen →
    // the card lands there with the same grab point under the cursor.
    function drop(id, s, x, y, w, h, gx, gy) {
        dropProc.req = { id: id, screen: s.name, x: x, y: y, w: w, h: h, gx: gx, gy: gy };
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
                if (o && o.name !== s.name) root.placeAt(q.id, o, c.x - o.x - q.gx, c.y - o.y - q.gy, q.w, q.h);
                else root.placeAt(q.id, s, q.x, q.y, q.w, q.h);
            }
        }
    }
    // End of a corner resize: new scale, top-left kept where it was (then nudged free)
    function resizeAt(id, s, k, x, y, w, h) {
        const it = get(id);
        if (!it) return;
        root.items = root.items.map(i => i.id === id ? Object.assign({}, i, { scale: Math.round(clampScale(it.type, k) * 100) / 100 }) : i);
        placeAt(id, s, x, y, w, h);
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
        if (type === "calendar" && p.due === false) out.due = false;     // agenda without the tracker's due dates
        if (type === "stopwatch") { out.running = p.running !== false; out.start = Date.now(); out.acc = 0; }
        return out;
    }

    // ── actions (IPC, Settings, Orrin) → result objects ──
    // at = { x, y } centre on the screen (maker), else position (a slot name, "" / "-" = the type's default)
    function add(type, screen, position, params, at) {
        type = String(type || "").toLowerCase().trim();
        if (type === "jarvis") type = "orrin";                 // the pre-AlchemOS name
        if (root.types.indexOf(type) < 0) return { ok: false, error: "unknown widget type " + type + " (have: " + root.types.join(", ") + ")" };
        const s = screenFromQuery(screen);
        if (!s) return { ok: false, error: "no screen " + screen + " is connected (main, diag, laptop, monitor 2, current)" };
        if (!Roles.keyOf(s)) return { ok: false, error: "screens aren't known yet, try again in a moment" };
        const huge = params && normSize(params.size) === "huge";       // a dashboard-sized card goes in the middle
        const pos = (position === "" || position === "-" || position === undefined) ? (huge ? "center" : root.defaultPosition[type] || "top-right") : normPosition(position);
        if (!pos) return { ok: false, error: "unknown position " + position + " (" + root.positions.join(", ") + ")" };
        const pr = cleanParams(type, params);
        if (pr.error) return { ok: false, error: pr.error };
        const size = params && params.size ? normSize(params.size) : "normal";
        if (!size) return { ok: false, error: "unknown size " + params.size + " (small, normal, large, huge)" };
        root.seq += 1;
        const it = { id: type + root.seq, type: type, mon: Roles.keyOf(s), pinned: params && params.pinned === true, scale: root.sizes[size],
                     params: pr, pending: at ? { at: { x: at.x, y: at.y } } : { pos: pos } };
        root.items = root.items.concat([it]);
        save();
        return { ok: true, id: it.id, type: type, screen: roleOf(s), monitor: s.name, position: pos, size: size, shown_on: s.name };
    }
    function remove(query) {
        const hit = match(query).map(i => i.id);
        if (!hit.length) return { ok: false, error: "no widget matches " + query };
        dismiss(hit);
        return { ok: true, removed: hit };
    }
    // Closing plays the card's dismiss (WidgetCard: the hologram retracts), then the widget goes.
    // A closing widget no longer matches anything (Orrin / IPC see it gone at once).
    property var closing: ({})          // id → true while its card animates out
    function dismiss(ids) {
        const c = Object.assign({}, root.closing);
        for (const id of ids) c[id] = true;
        root.closing = c;
        reaper.restart();
    }
    Timer {
        id: reaper
        interval: 300
        onTriggered: {
            const gone = Object.keys(root.closing);
            root.items = root.items.filter(i => gone.indexOf(i.id) < 0);
            for (const g of gone) delete root.rects[g];
            root.closing = ({});
            root.save();
        }
    }
    // Move the newest match. screen: as screenFromQuery ("" / "-" = where it is). x: a named
    // position ("top-right", y empty), or x and y as fractions 0–1 of the room on that screen
    // (0 0 = top-left, 0.5 0.5 = centre) or as pixels (> 1). Clamped and nudged off other widgets.
    function move(query, screen, x, y) {
        const hits = match(query);
        if (!hits.length) return { ok: false, error: "no widget matches " + query };
        const it = hits[hits.length - 1];
        const keepScreen = screen === "" || screen === "-" || screen === undefined;
        const s = keepScreen ? screenOfItem(it) : screenFromQuery(screen);
        if (!s) return { ok: false, error: keepScreen ? it.id + "'s monitor isn't connected; name a screen" : "no screen " + screen + " is connected" };
        if (!Roles.keyOf(s)) return { ok: false, error: "screens aren't known yet, try again in a moment" };
        const xs = String(x === undefined ? "" : x).trim(), ys = String(y === undefined ? "" : y).trim();
        const r = root.rects[it.id];
        const w = r ? r.w : 300, h = r ? r.h : 200;
        let px, py, pos = "";
        if ((xs === "" || xs === "-") && (ys === "" || ys === "-")) {           // same spot, another screen
            if (it.fx === undefined) { pos = slotOf(it); const q = slotXY(s, pos, w, h); px = q.x; py = q.y; }
            else { const q = fromFrac(s, it.fx, it.fy, w, h); px = q.x; py = q.y; }
        } else if (isFinite(Number(xs)) && isFinite(Number(ys)) && xs !== "" && ys !== "" && ys !== "-") {
            const nx = Number(xs), ny = Number(ys);
            if (nx >= 0 && nx <= 1 && ny >= 0 && ny <= 1) { const q = fromFrac(s, nx, ny, w, h); px = q.x; py = q.y; }
            else { px = nx; py = ny; }
        } else {
            pos = normPosition(ys && ys !== "-" ? xs + " " + ys : xs);
            if (!pos) return { ok: false, error: "unknown position " + xs + (ys && ys !== "-" ? " " + ys : "") + " (" + root.positions.join(", ") + ", or x y fractions 0-1)" };
            const q = slotXY(s, pos, w, h); px = q.x; py = q.y;
        }
        if (r) {
            const p = placeAt(it.id, s, px, py, w, h);
            return { ok: true, id: it.id, screen: roleOf(s), monitor: s.name, position: slotOf(get(it.id)), x: p.x, y: p.y };
        }
        // not drawn yet (its monitor was unplugged): place it when it shows up
        setPending(it.id, { mon: Roles.keyOf(s) }, pos ? { pos: pos } : { at: { x: px + w / 2, y: py + h / 2 } });
        return { ok: true, id: it.id, screen: roleOf(s), monitor: s.name, position: pos || "custom" };
    }
    function resize(query, size) {
        const hits = match(query);
        if (!hits.length) return { ok: false, error: "no widget matches " + query };
        const it = hits[hits.length - 1];
        const w = String(size).toLowerCase().trim(), k0 = scaleOf(it);
        let k;
        if (w === "bigger" || w === "larger") k = k0 * 1.25;
        else if (w === "smaller") k = k0 / 1.25;
        else if (normSize(w)) k = root.sizes[normSize(w)];
        else if (isFinite(Number(w)) && Number(w) > 0) k = Number(w);
        else return { ok: false, error: "unknown size " + size + " (small, normal, large, huge, bigger, smaller, or a scale like 1.3)" };
        k = Math.round(clampScale(it.type, k) * 100) / 100;
        setPending(it.id, { scale: k }, { keep: true });
        return { ok: true, id: it.id, size: sizeName(k), scale: k };
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
        const gone = root.items.filter(i => (all || roleOfItem(i) === role) && root.closing[i.id] !== true).map(i => i.id);
        dismiss(gone);
        return { ok: true, removed: gone };
    }
    // Every widget on a plugged-in monitor back to its type's default spot (sizes kept), laid
    // out in order so none overlap. Widgets on unplugged monitors keep their places.
    function reset() {
        const ids = [];
        root.items = root.items.map(i => {
            if (!screenOfItem(i) || root.closing[i.id] === true) return i;
            ids.push(i.id);
            const huge = scaleOf(i) >= 1.75;          // dashboard-sized cards go in the middle, as when added
            return Object.assign({}, i, { pending: { pos: huge ? "center" : root.defaultPosition[i.type] || "top-right" } });
        });
        save();
        Qt.callLater(root.settle);
        return { ok: true, reset: ids };
    }
    function list() {
        const now = Date.now();
        return root.items.filter(i => root.closing[i.id] !== true).map(i => {
            const s = screenOfItem(i);
            const o = { id: i.id, type: i.type, screen: s ? roleOf(s) : "", monitor: i.mon || "", position: slotOf(i), pinned: i.pinned === true,
                        size: sizeName(scaleOf(i)), scale: scaleOf(i), shown_on: s ? s.name : "" };
            if (i.fx !== undefined) { o.x = Math.round(i.fx * 1000) / 1000; o.y = Math.round(i.fy * 1000) / 1000; }
            if (!s) o.hidden = "its monitor isn't connected";
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
        Quickshell.execDetached(["pw-play", "-P", "{ media.name = \"Orrin timer\" state.restore-props = false }", root.home + "/.config/quickshell/sounds/widget-alarm.wav"]);
        Quickshell.execDetached(["alchemos-govee", "anim", "alert"]);
        OrrinState.alert("TIMER", (label ? label.toUpperCase() + " · " : "") + "TIME'S UP");
        if (Theme.cfg.orrinSpeak) {
            const line = (late ? "While I was away, sir, your " : "Your ") + (label ? label + " " : "") + "timer is done" + (late ? "." : ", sir.");
            speakTimer.line = line;
            speakTimer.restart();
        }
    }
    Timer {     // after the chime
        id: speakTimer
        property string line: ""
        interval: 900
        onTriggered: Quickshell.execDetached([root.home + "/.local/bin/orrin", "--say", line])
    }

    // ── persistence ──
    FileView {
        id: store
        path: root.home + "/.config/quickshell/widgets.json"
        property bool renamedType: false
        onLoaded: {
            try {
                const d = JSON.parse(text());
                root.seq = d.seq || 0;
                root.items = (d.items || []).filter(i => i && i.id && i.type && i.params
                    && (i.mon || (root.roles.indexOf(i.screen) >= 0 && root.positions.indexOf(i.position) >= 0)))
                    .map(i => i.type === "jarvis" ? Object.assign({}, i, { type: "orrin" }) : i);   // pre-AlchemOS name
                renamedType = (d.items || []).some(i => i && i.type === "jarvis");
            } catch (e) {}
            root.loaded = true;
            if (renamedType) root.save();
            root.checkTimers(true);
            root.migrate();
        }
        onLoadFailed: root.loaded = true
    }
    // Written right away: changes are rare (add / move / close), and a `pkill qs` right after one must not lose it
    function save() { if (root.loaded) store.setText(JSON.stringify({ version: 2, seq: root.seq, items: root.items }, null, 1) + "\n"); }
}
