pragma Singleton
// Desktop notifications (org.freedesktop.Notifications), drawn by the HUD so every skin styles them:
// NotifPopups.qml shows `popups` on the main-role screen (the laptop when undocked), each card is the
// skin's `notifCard` component (Skin.component; base HoloNotifCard.qml, ALCHEMOS AlchemNotifCard.qml).
//
// D-Bus name: mako is only the fallback now (started by D-Bus activation while the HUD is down,
// ~/.local/share/dbus-1/services/org.freedesktop.Notifications.service). The server here is created
// only after any running mako has been stopped, so the two never race for the name; a HUD restart
// (`pkill qs; qs -d` or alchemos-hud.sh) takes it back.
//
// Behaviour (as mako did): newest on top, at most 4, grouped per app (a new one from the same app
// replaces the card and counts "+N"), timeout = the app's or 6 s (critical: stays), the pointer on a
// card holds its timeout, a click runs the default action (else dismisses), action buttons, app icon /
// image, body markup. Do-not-disturb (combat mode, `qs ipc call notifications dnd on|off|toggle|get`)
// shows nothing but keeps history; it lives in $XDG_RUNTIME_DIR/alchemos-dnd so a HUD restart keeps it.
// Behind the lock (LockState.doors not "open") cards wait, timeouts frozen, and show after the unlock.
// History: the last 50 (`notifications list | restore | clear`).
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Notifications

Singleton {
    id: root

    readonly property int maxVisible: 4
    readonly property int defaultTimeoutMs: 6000
    property bool ready: false                   // mako out of the way: the server may take the name
    property bool dnd: false
    readonly property bool held: LockState.doors !== "open"
    readonly property bool showing: !dnd && !held
    readonly property string dndFile: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/alchemos-dnd"

    // nid → Notification (live D-Bus object), for actions / dismiss / expire
    property var live: ({})
    property var history: []                     // newest first: plain copies
    ListModel { id: model }
    readonly property alias popups: model

    // ── start-up: stop the fallback daemon, then serve ──
    Process {
        id: takeover
        running: true
        command: ["sh", "-c", "systemctl --user stop mako.service 2>/dev/null; pkill -x mako; for i in 1 2 3 4 5 6 7 8 9 10; do pgrep -x mako >/dev/null || exit 0; sleep 0.1; done; exit 0"]
        onExited: root.ready = true
    }
    Process {
        id: dndProbe
        running: true
        command: ["sh", "-c", "[ -e \"$1\" ] && echo 1 || echo 0", "sh", root.dndFile]
        stdout: StdioCollector { onStreamFinished: root.dnd = text.trim() === "1" }
    }
    LazyLoader {
        active: root.ready
        NotificationServer {
            keepOnReload: false
            actionsSupported: true
            bodySupported: true
            bodyMarkupSupported: true
            bodyHyperlinksSupported: false
            imageSupported: true
            persistenceSupported: true
            onNotification: n => root.arrive(n)
        }
    }

    // ── arrivals ──
    function urgencyName(u) { return u === NotificationUrgency.Critical ? "critical" : u === NotificationUrgency.Low ? "low" : "normal"; }
    // "Orrin" / "Selene" (or the active skin's names for them) get their sun / moon sigil
    function personaOf(app) {
        const a = String(app || "").toLowerCase();
        for (const who of ["orrin", "selene"]) {
            if (a === who || a === String(OrrinState.callOf(who)).toLowerCase()) return who;
        }
        if (a === "jarvis") return "orrin";
        if (a === "friday") return "selene";
        return "";
    }
    function copy(n) {
        const acts = (n.actions || []).map(a => ({ id: a.identifier, text: a.text }));
        const t = n.expireTimeout > 0 ? Math.round(n.expireTimeout * 1000) : 0;
        const urgency = urgencyName(n.urgency);
        return {
            nid: n.id, app: n.appName || "", summary: n.summary || "", body: n.body || "",
            icon: n.appIcon || "", image: n.image || "", urgency: urgency,
            actions: JSON.stringify(acts.filter(a => a.id !== "default" && a.text)),
            hasDefault: acts.some(a => a.id === "default"),
            persona: personaOf(n.appName), time: Date.now(),
            timeoutMs: urgency === "critical" ? 0 : (t > 0 ? t : defaultTimeoutMs),
            count: 1, closing: false, hover: false, left: 0
        };
    }
    function rowOf(nid) { for (let i = 0; i < model.count; i++) if (model.get(i).nid === nid) return i; return -1; }
    function rowOfApp(app) {
        for (let i = 0; i < model.count; i++) { const r = model.get(i); if (!r.closing && r.app === app && r.urgency !== "critical") return i; }
        return -1;
    }
    function arrive(n) {
        n.tracked = true;
        const c = copy(n);
        root.live[n.id] = n;
        n.closed.connect(() => root.gone(c.nid));
        // a replacement (same id) can arrive as an update of this object: follow it
        for (const sig of [n.summaryChanged, n.bodyChanged, n.appIconChanged, n.imageChanged, n.urgencyChanged, n.actionsChanged])
            sig.connect(() => root.refresh(n));
        remember(c);
        if (root.dnd) return;                   // history only
        const same = rowOf(c.nid);              // replaces-id: the same notification, updated
        if (same >= 0) { c.count = model.get(same).count; c.left = c.timeoutMs; model.set(same, c); return; }
        const grp = c.urgency === "critical" || !c.app ? -1 : rowOfApp(c.app);
        if (grp >= 0) {                         // same app: the newest takes the card, "+N"
            const old = model.get(grp);
            c.count = old.count + 1; c.left = c.timeoutMs;
            const o = root.live[old.nid]; if (o) { delete root.live[old.nid]; o.expire(); }
            model.set(grp, c); model.move(grp, 0, 1);
            return;
        }
        c.left = c.timeoutMs;
        model.insert(0, c);
        // beyond what fits: the oldest non-critical goes (still in history)
        let shown = 0;
        for (let i = 0; i < model.count; i++) {
            const r = model.get(i);
            if (r.closing) continue;
            if (++shown > root.maxVisible && r.urgency !== "critical") close(r.nid, "expire");
        }
    }
    function refresh(n) {
        const i = rowOf(n.id);
        if (i < 0 || !root.live[n.id]) return;
        const c = copy(n), r = model.get(i);
        c.count = r.count; c.left = c.timeoutMs; c.hover = r.hover;
        model.set(i, c);
        remember(c);
    }
    function remember(c) {
        const h = [Object.assign({}, c)].concat(root.history.filter(x => x.nid !== c.nid));
        root.history = h.slice(0, 50);
    }
    // the app closed it (or it expired / was dismissed): play the card's exit
    function gone(nid) {
        delete root.live[nid];
        const i = rowOf(nid);
        if (i >= 0 && !model.get(i).closing) model.setProperty(i, "closing", true);
    }

    // ── from the cards ──
    function close(nid, how) {
        const n = root.live[nid];
        if (n) { delete root.live[nid]; how === "expire" ? n.expire() : n.dismiss(); }
        const i = rowOf(nid);
        if (i >= 0) model.setProperty(i, "closing", true);
    }
    function dismiss(nid) { close(nid, "dismiss"); }
    function invoke(nid, actionId) {
        const n = root.live[nid];
        const a = n ? (n.actions || []).find(x => x.identifier === actionId) : null;
        if (a) a.invoke();                       // the app decides; most close it themselves
        if (n && !n.resident) close(nid, "dismiss");
    }
    // a click on the card: its default action, else just dismiss
    function activate(nid) { const i = rowOf(nid); if (i >= 0 && model.get(i).hasDefault) invoke(nid, "default"); else dismiss(nid); }
    function hover(nid, on) { const i = rowOf(nid); if (i >= 0) model.setProperty(i, "hover", on); }
    function remove(nid) { const i = rowOf(nid); if (i >= 0) model.remove(i); }

    // ── timeouts: counted only while shown and not hovered (the lock freezes them) ──
    Timer {
        interval: 250; repeat: true
        running: model.count > 0 && root.showing
        onTriggered: {
            for (let i = model.count - 1; i >= 0; i--) {
                const r = model.get(i);
                if (r.closing || r.hover || r.timeoutMs <= 0) continue;
                const left = r.left - interval;
                if (left <= 0) close(r.nid, "expire"); else model.setProperty(i, "left", left);
            }
        }
    }

    // ── do-not-disturb ──
    function setDnd(on) {
        root.dnd = on;
        Quickshell.execDetached(["sh", "-c", on ? "touch \"$1\"" : "rm -f \"$1\"", "sh", root.dndFile]);
        if (on) for (let i = 0; i < model.count; i++) model.setProperty(i, "closing", true);   // out of sight, kept in history
        return on ? "on" : "off";
    }

    // ── history ──
    function restore() {                          // the most recent one not on screen, back as a card
        const h = root.history.find(x => rowOf(x.nid) < 0);
        if (!h) return "nothing to restore";
        const c = Object.assign({}, h, { closing: false, hover: false, count: 1, timeoutMs: h.urgency === "critical" ? 0 : defaultTimeoutMs });
        c.left = c.timeoutMs;
        model.insert(0, c);
        return "ok";
    }
    function list() { return JSON.stringify(root.history.map(h => ({ app: h.app, summary: h.summary, urgency: h.urgency, time: h.time }))); }
    function clear() { for (let i = 0; i < model.count; i++) close(model.get(i).nid, "dismiss"); root.history = []; return "ok"; }
}
