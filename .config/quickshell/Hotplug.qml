// Hotplug settle gate: nothing acts on the screens while they're still changing.
//
// Unplugging a screen (the TV, the dock) leaves Hyprland mid-change for a moment, and
// unplugging the screen every other screen mirrors can leave windows on no monitor at all
// (hyprctl clients: "monitor": -1; workspaces: "monitor": "?"). It's a race inside
// Hyprland: the same unplug sometimes orphans and sometimes doesn't. Hyprland 0.56.2 then
// segfaults as soon as anything captures one of those windows (the Overview thumbnails,
// Orrin's window reader): the crashes of 2026-10-31 23:00 and 2026-11-01 01:35.
//
// Any monitoradded / monitorremoved / configreloaded starts `settling`. 1.5 s after the last
// one, every window is checked; workspaces whose windows lost their monitor move to the
// laptop screen (or the first real screen left), and only then does `settled()` fire:
// Profiles, Displays, Roles and Peek act after it. The same check runs every 30 s while
// idle, in case windows are ever orphaned without a monitor event.
//
// While settling, $XDG_RUNTIME_DIR/alchemos-hotplug-settling exists, touched every 4 s; one
// older than 10 s is stale, so a crashed HUD can't hold anything up. alchemos-lock.sh and
// lid.sh wait for it (2.5 s at most), and Orrin and the Overview capture nothing.
// Journal (tag alchemos-hud, `journalctl --user -t alchemos-hud`): every re-home, with the
// windows' classes and the screen their workspace was last seen on.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import "Hypr.js" as Hypr

Singleton {
    id: root

    readonly property string laptop: "eDP-1"
    readonly property string flag: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/alchemos-hotplug-settling"

    property bool settling: false
    property var removed: []        // screens removed since settling began
    property var homes: ({})        // workspace name → the screen it was last seen on
    property int rounds: 0          // re-home attempts in this settle
    property string why: ""         // the first event of this settle
    property double since: 0        // when it began
    signal settled()

    function log(msg) { Quickshell.execDetached(["logger", "-t", "alchemos-hud", msg]); }

    function begin(ev) {
        if (!root.settling) {
            root.settling = true;
            root.rounds = 0;
            root.why = ev;
            root.since = Date.now();
        }
        Quickshell.execDetached(["touch", root.flag]);
        quiet.restart();
    }

    Timer { id: quiet; interval: 1500; onTriggered: probe.running = true }
    Timer { id: verify; interval: 500; onTriggered: probe.running = true }
    Timer {                         // keep the flag fresh through a long settle
        interval: 4000; repeat: true; running: root.settling
        onTriggered: Quickshell.execDetached(["touch", root.flag])
    }
    Timer {                         // idle check (also learns where workspaces live)
        interval: 30000; repeat: true; running: !root.settling
        onTriggered: probe.running = true
    }
    Component.onCompleted: {
        Quickshell.execDetached(["rm", "-f", root.flag]);   // a previous HUD's
        probe.running = true;
    }

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            const n = event.name;
            if (n === "monitorremoved" || n === "monitorremovedv2") {
                const name = n === "monitorremoved" ? String(event.data) : String(event.data).split(",")[1];
                if (name && root.removed.indexOf(name) < 0) root.removed = root.removed.concat([name]);
            }
            if (n.startsWith("monitoradded") || n.startsWith("monitorremoved") || n === "configreloaded")
                root.begin(n);
        }
    }

    Process {
        id: probe
        command: ["sh", "-c", "hyprctl monitors all -j; echo '@@@'; hyprctl workspaces -j; echo '@@@'; hyprctl clients -j"]
        stdout: StdioCollector { onStreamFinished: root.check(text) }
    }

    function check(text) {
        if (quiet.running) return;          // the screens changed again meanwhile: wait for that
        let mons, wss, wins;
        try {
            const p = text.split("@@@");
            mons = JSON.parse(p[0]); wss = JSON.parse(p[1]); wins = JSON.parse(p[2]);
        } catch (e) {
            if (root.settling) { root.log("settle: couldn't read hyprctl; ending the settle anyway"); root.finish(null, "?"); }
            return;
        }
        const live = mons.filter(m => !m.disabled).map(m => m.id);
        // Workspaces to move: any with a window whose monitor is gone
        const orphans = {};
        for (const c of wins) {
            if (c.mapped === false || live.indexOf(c.monitor) >= 0) continue;
            const ws = c.workspace && c.workspace.name;
            if (!ws) continue;
            (orphans[ws] = orphans[ws] || []).push((c.class || c.initialClass || "?") + " (monitor " + c.monitor + ")");
        }
        const names = Object.keys(orphans);
        const screens = mons.map(m => m.name + (m.disabled ? " off" : m.mirrorOf && m.mirrorOf !== "none" ? " mirror" : "")).join(", ") || "none";
        if (names.length === 0) { root.finish(wss, screens); return; }

        // Never onto a mirror: the laptop screen if it's a real one, else the first real screen
        const real = mons.filter(m => !m.disabled && (!m.mirrorOf || m.mirrorOf === "none"));
        const to = real.find(m => m.name === root.laptop) || real[0];
        const ctx = (root.settling ? "after " + root.why : "no screen change seen")
                  + (root.removed.length ? ", removed " + root.removed.join(" ") : "")
                  + "; screens now: " + screens;
        if (!to) {
            root.log("settle: windows on no monitor but no screen to move them to (" + ctx + "): "
                     + names.map(w => "workspace " + w + " [" + orphans[w].join(", ") + "]").join("; "));
            if (root.settling) root.finish(null, screens);
            return;
        }
        if (root.rounds >= 3) {
            root.log("settle: still orphaned after 3 tries (" + ctx + "): " + names.map(w => "workspace " + w + " [" + orphans[w].join(", ") + "]").join("; "));
            root.finish(wss, screens);
            return;
        }
        for (const w of names)
            root.log("settle: re-homed workspace " + w + " [" + orphans[w].join(", ") + "] from "
                     + (root.homes[w] || "?") + " to " + to.name + " (" + ctx + ")");
        Quickshell.execDetached(Hypr.luaEval(names.map(w =>
            "hl.dispatch(hl.dsp.workspace.move({ workspace = " + Hypr.str(w) + ", monitor = " + Hypr.str(to.name) + " }))").join(" ")));
        root.rounds++;
        if (!root.settling) { root.settling = true; root.why = "orphaned windows"; root.since = Date.now(); Quickshell.execDetached(["touch", root.flag]); }
        verify.restart();                   // look again: settled only once nothing is orphaned
    }

    // One journal line per settle: what started it, what left, how long, the screens after
    function finish(wss, screens) {
        if (wss) {
            const h = Object.assign({}, root.homes);
            for (const w of wss) if (w.monitor && w.monitor !== "?") h[w.name] = w.monitor;
            root.homes = h;
        }
        if (!root.settling) return;
        if (root.why !== "configreloaded" || root.removed.length || root.rounds)
            root.log("settle: " + root.why + (root.removed.length ? ", removed " + root.removed.join(" ") : "")
                     + (root.rounds ? ", " + root.rounds + " re-home round(s)" : "")
                     + "; settled in " + ((Date.now() - root.since) / 1000).toFixed(1) + " s; screens now: " + screens);
        root.settling = false;
        root.removed = [];
        root.why = "";
        Quickshell.execDetached(["rm", "-f", root.flag]);
        root.settled();
    }
}
