pragma Singleton
// Decides what each screen is for, based on what's plugged in.
//
//   Laptop only:  laptop = "main"  (arc-reactor clock, workspaces 1–5)
//   Docked:       leftmost external monitor = "main"  (clock, workspaces 1–3)
//                 next external monitor     = "diag"  (diagnostics, 4–6)
//                 laptop screen             = "media" (audio deck, 7–9)
//
// Works by position, not port name, so it doesn't matter if the dock
// renames the monitors (DP-5, DP-7, …) when you replug.
//
// What a screen SHOWS is separate (shows(): clock / stats / music / none), picked per
// physical monitor in Settings → Display or with Super+Shift+V and saved in
// Theme.cfg.screenRoles by Hyprland description. AUTO = by position, as above (other
// screens: nothing). Picking never moves workspaces: those follow role() only.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import "Hypr.js" as Hypr

Singleton {
    id: root

    readonly property string laptopName: "eDP-1"

    readonly property var externals: {
        const arr = [];
        for (let i = 0; i < Quickshell.screens.length; i++) {
            const s = Quickshell.screens[i];
            if (s.name !== root.laptopName) arr.push(s);
        }
        return arr.sort((a, b) => a.x - b.x);
    }
    readonly property bool docked: externals.length > 0

    function role(screen) {
        if (!screen) return "none";
        if (!root.docked) return "main";
        if (screen.name === root.laptopName) return "media";
        const i = root.externals.findIndex(s => s.name === screen.name);
        return i === 0 ? "main" : (i === 1 ? "diag" : "extra");
    }

    // ── What each screen shows ──
    readonly property var picks: ["auto", "clock", "stats", "music", "none"]
    readonly property var autoShows: ({ main: "clock", diag: "stats", media: "music", extra: "none" })
    property var mons: ({})         // port name → { desc, mirrorOf } from hyprctl (QML's description is empty)
    property bool ready: false      // descriptions known: until then nothing is shown, so no flicker at login

    function descOf(screen) { const m = screen ? root.mons[screen.name] : null; return m ? m.desc : ""; }
    // What's saved for this monitor: auto | clock | stats | music | none
    function pickOf(desc) {
        const p = desc ? (Theme.cfg.screenRoles || {})[desc] : undefined;
        return root.picks.indexOf(p) >= 0 ? p : "auto";
    }
    function pick(screen) { return pickOf(descOf(screen)); }
    // What the screen shows right now; a mirrored screen goes by its source
    function shows(screen) {
        if (!screen || !root.ready) return "none";
        const m = root.mons[screen.name];
        if (m && m.mirrorOf) {
            const src = Quickshell.screens.find(s => s.name === m.mirrorOf);
            if (src) screen = src;
        }
        const p = pick(screen);
        return p === "auto" ? root.autoShows[role(screen)] : p;
    }
    function label(p) { return p.toUpperCase(); }

    function setDesc(desc, p) {
        if (!desc || root.picks.indexOf(p) < 0) return false;
        const all = Object.assign({}, Theme.cfg.screenRoles || {});
        if (p === "auto") delete all[desc]; else all[desc] = p;
        Theme.cfg.screenRoles = all;         // new object → JsonAdapter notices and saves
        return true;
    }

    // "DP-6" | a description (or part of one) | tv | laptop | monitor 2 | main | diag | media | current
    function targets(q) {
        const t = String(q || "").trim().toLowerCase().replace(/\s+/g, " ");
        const all = Quickshell.screens.slice();
        if (t === "" || t === "-" || t === "current" || t === "focused" || t === "here") {
            const f = Hyprland.focusedMonitor;
            return all.filter(s => f && s.name === f.name);
        }
        if (t === "tv") return all.filter(s => s.name !== root.laptopName && !/^(dell|acer)/i.test(descOf(s)));
        if (t === "laptop" || t === "laptop screen") return all.filter(s => s.name === root.laptopName);
        const n = t.match(/^(?:monitor|screen) ?(\d)$/);
        if (n) { const s = root.externals[Number(n[1]) - 1]; return s ? [s] : []; }
        if (["main", "diag", "media", "extra"].indexOf(t) >= 0) return all.filter(s => role(s) === t);
        const exact = all.filter(s => s.name.toLowerCase() === t || descOf(s).toLowerCase() === t);
        return exact.length ? exact : all.filter(s => descOf(s).toLowerCase().indexOf(t) >= 0);
    }
    function entry(s) { return { name: s.name, desc: descOf(s), pick: pick(s), shows: shows(s), slot: role(s) }; }
    function setFor(q, p) {
        p = String(p || "").trim().toLowerCase();
        if (root.picks.indexOf(p) < 0) return { ok: false, error: "role must be one of: " + root.picks.join(", ") };
        const list = targets(q);
        if (!list.length) return { ok: false, error: String(q).toLowerCase() === "tv" ? "no TV connected" : "no screen matches " + q };
        for (const s of list) setDesc(descOf(s), p);
        return { ok: true, set: list.map(entry) };
    }
    function status() {
        return { ok: true, screens: Quickshell.screens.map(entry), saved: Theme.cfg.screenRoles || {} };
    }
    // Super+Shift+V: next pick on the focused monitor, with an OSD toast
    function cycle() {
        const s = targets("current")[0];
        if (!s || !descOf(s)) return { ok: false, error: "no focused screen" };
        const p = root.picks[(root.picks.indexOf(pick(s)) + 1) % root.picks.length];
        setDesc(descOf(s), p);
        OsdState.role(s.name, p === "auto" ? "AUTO · " + label(root.autoShows[role(s)]) : label(p));
        return { ok: true, set: [entry(s)] };
    }

    Process {
        id: probe
        command: ["hyprctl", "monitors", "all", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                let list = [];
                try { list = JSON.parse(text); } catch (e) { return; }
                const byId = {}, out = {};
                for (const m of list) byId[m.id] = m.name;
                for (const m of list) {
                    const mo = m.mirrorOf === undefined || m.mirrorOf === null ? "none" : String(m.mirrorOf);
                    const src = mo === "none" || mo === "" ? "" : (byId[mo] || mo);
                    out[m.name] = { desc: m.description || "", mirrorOf: src === m.name ? "" : src };
                }
                root.mons = out;
                root.ready = true;
            }
        }
    }
    Timer { id: reprobe; interval: 400; onTriggered: probe.running = true }

    function baseWorkspaces(screen) {
        switch (role(screen)) {
        case "main":  return root.docked ? [1, 2, 3] : [1, 2, 3, 4, 5];
        case "diag":  return [4, 5, 6];
        case "media": return [7, 8, 9];
        default:      return [];
        }
    }

    // After docking, send workspaces back to their home screens
    function arrangeWorkspaces() {
        if (!root.docked) return;
        const homes = {};
        homes[1] = homes[2] = homes[3] = root.externals[0].name;
        const second = root.externals.length > 1 ? root.externals[1].name : root.externals[0].name;
        homes[4] = homes[5] = homes[6] = second;
        homes[7] = homes[8] = homes[9] = root.laptopName;
        const existing = Hyprland.workspaces.values.map(w => w.id);
        for (const ws in homes) {
            if (existing.indexOf(Number(ws)) >= 0)
                Hyprland.dispatch(Hypr.workspaceTo(ws, homes[ws]));
        }
    }

    // At login: laptop only → start on workspace 1; docked → make sure everything is home
    Component.onCompleted: {
        probe.running = true;
        if (!root.docked) Hyprland.dispatch(Hypr.workspace(1));
        else redock.restart();
    }

    // Also re-arrange whenever the set of screens changes
    Connections {
        target: Quickshell
        function onScreensChanged() { redock.restart(); reprobe.restart(); }
    }

    // Re-arrange shortly after a monitor is plugged in
    Connections {
        target: Hyprland
        function onRawEvent(event) {
            const n = event.name;
            if (n === "monitoradded" || n === "monitoraddedv2")
                redock.restart();
            if (n.startsWith("monitor") || n === "configreloaded")
                reprobe.restart();
        }
    }
    Timer {
        id: redock
        interval: 1500
        onTriggered: root.arrangeWorkspaces()
    }
}
