// Display layout manager (Settings → Display).
//
//   extend   — every screen is its own desktop (default)
//   mirror   — every screen shows the main external monitor
//   external — laptop screen off while docked
//   laptop   — external monitors off, laptop screen only
//
// The arrangement (resolution, scale, rotation, order) and the layout mode are saved
// per display profile (Profiles.qml: home desk, laptop only, the TV, …), and the active
// profile's arrangement is written to ~/.config/hypr/alchemos/display-profile.lua (applied by
// alchemos/monitors.lua). The layout mode is applied live whenever monitors change, so
// "external only" can never leave you with a black laptop screen after you undock: with no
// monitors plugged in, the laptop screen always comes back.
//
// Applying a change by hand starts a 15 s "keep these settings?" countdown on every
// screen; if you don't press KEEP it reverts by itself (even if the HUD crashes). KEEP
// saves into the active profile. Profile switches on hotplug apply without the prompt.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import "Hypr.js" as Hypr

Singleton {
    id: root

    readonly property string laptop: "eDP-1"
    readonly property string flag: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/alchemos-display-pending"

    property bool pending: false
    property int countdown: 0
    property string pendingLayout: "extend"
    property var pendingRules: []
    readonly property string active: pending ? pendingLayout : (Theme.cfg.displayLayout || "extend")

    // ── Apply / keep / revert ──
    function apply(rules, layout) {
        root.pendingRules = rules;
        root.pendingLayout = layout;
        root.pending = true;
        root.countdown = 15;
        tick.restart();
        Quickshell.execDetached(Hypr.monitors(rules.map(Hypr.monitorSpec)));
        enforceSoon.restart();
        // Crash-proof fallback: if nobody confirms, put the saved setup back
        Quickshell.execDetached(["sh", "-c",
            "touch '" + flag + "'; sleep 17; [ -f '" + flag + "' ] && rm -f '" + flag + "' && hyprctl reload"]);
    }
    function keep() {
        if (!root.pending) return;
        tick.stop();
        Quickshell.execDetached(["rm", "-f", root.flag]);
        Profiles.saveLayout(root.pendingRules, root.pendingLayout);   // also writes display-profile.lua
        Theme.cfg.displayLayout = root.pendingLayout;
        root.pending = false;
        root.countdown = 0;
    }
    function revert() {
        tick.stop();
        Quickshell.execDetached(["rm", "-f", root.flag]);
        root.pending = false;
        root.countdown = 0;
        Quickshell.execDetached(["hyprctl", "reload"]);   // configreloaded → enforce()
    }
    // A profile switch (hotplug) while a manual change waits for KEEP: drop the change
    // without reloading; the new profile's reload replaces it.
    function cancelPending() {
        if (!root.pending) return;
        tick.stop();
        Quickshell.execDetached(["rm", "-f", root.flag]);
        root.pending = false;
        root.countdown = 0;
    }
    function writeConf(text) { conf.setText(text); }

    Timer {
        id: tick
        interval: 1000; repeat: true
        onTriggered: { root.countdown--; if (root.countdown <= 0) root.revert(); }
    }

    FileView {
        id: conf
        path: Quickshell.env("HOME") + "/.config/hypr/alchemos/display-profile.lua"
        blockLoading: false
        blockWrites: true       // a profile switch reloads Hyprland right after writing
        printErrors: false
    }

    // ── Keep the layout mode in force as monitors come and go ──
    // Not while a profile switch is settling: the old profile's mode (say, mirror for the
    // TV) must not be applied to the new screens. Nor while the screens themselves are
    // still changing (Hotplug.qml): it runs again once they've settled.
    function enforce() { if (!Profiles.settling && !Hotplug.settling) probe.running = true; }
    Connections {
        target: Hotplug
        function onSettled() { root.enforce(); }
    }

    // Never reload more than once every 20 s, so a monitor that won't take a
    // setting can't put Hyprland into a reload loop (which freezes apps)
    property real lastReload: 0
    function safeReload() {
        const now = Date.now();
        if (now - root.lastReload < 20000) { console.warn("Displays: skipped reload (loop guard)"); return; }
        root.lastReload = now;
        Quickshell.execDetached(["hyprctl", "reload"]);
    }
    // For profile switches: the same guard, but the reload is deferred, not dropped
    function reloadWhenAllowed() {
        const wait = 20000 - (Date.now() - root.lastReload);
        if (wait > 0) console.warn("Displays: profile reload deferred " + Math.ceil(wait / 1000) + " s (loop guard)");
        deferredReload.interval = Math.max(300, wait + 50);
        deferredReload.restart();
    }
    Timer { id: deferredReload; onTriggered: root.safeReload() }
    Timer { id: enforceSoon; interval: 900; onTriggered: root.enforce() }
    Component.onCompleted: enforceSoon.restart()

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            const n = event.name;
            if (n === "monitoradded" || n === "monitoraddedv2" || n === "monitorremoved"
                || n === "monitorremovedv2" || n === "configreloaded")
                enforceSoon.restart();
        }
    }

    Process {
        id: probe
        command: ["hyprctl", "monitors", "all", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                let mons = [];
                try { mons = JSON.parse(text); } catch (e) { return; }
                root.enforceWith(mons);
            }
        }
    }

    function enforceWith(mons) {
        const lap = mons.find(m => m.name === root.laptop);
        const ext = mons.filter(m => m.name !== root.laptop).sort((a, b) => a.x - b.x);
        const mirrored = m => m.mirrorOf !== undefined && m.mirrorOf !== null && String(m.mirrorOf) !== "none" && String(m.mirrorOf) !== "";
        const mirrorsSrc = (m, src) => String(m.mirrorOf) === src.name || String(m.mirrorOf) === String(src.id);
        const specs = [];   // hl.monitor rules

        // Nothing plugged in → the laptop screen must be on, whatever the mode
        if (ext.length === 0) {
            if (lap && (lap.disabled || mirrored(lap))) root.safeReload();
            return;
        }

        const mode = root.active;
        if (mode === "external") {
            if (lap && !lap.disabled) specs.push({ output: root.laptop, disabled: true });
        } else if (mode === "laptop") {
            if (!lap) return;   // never turn everything off
            for (const m of ext) if (!m.disabled) specs.push({ output: "desc:" + m.description, disabled: true });
        } else if (mode === "mirror") {
            const src = ext.find(m => !m.disabled && !mirrored(m)) || ext[0];
            for (const m of mons) {
                if (m.name === src.name || mirrorsSrc(m, src)) continue;
                const key = m.name === root.laptop ? m.name : "desc:" + m.description;
                specs.push({ output: key, mode: "preferred", position: "auto", scale: 1, mirror: src.name });
            }
        } else {
            // extend: anything still off or mirrored from another mode → reload the saved arrangement
            const stale = (lap && (lap.disabled || mirrored(lap))) || ext.some(m => mirrored(m));
            if (stale && !root.pending) { root.safeReload(); return; }
        }
        if (specs.length) Quickshell.execDetached(Hypr.monitors(specs));
    }
}
