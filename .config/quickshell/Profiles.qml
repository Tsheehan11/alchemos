// Display profiles, keyed by what's connected (Settings → Display shows the active one).
//
//   HOME DESK    — the USB-C dock + both Acers: extend, left Acer / middle Acer / laptop,
//                  workspaces 1–3 / 4–6 / 7–9 (Roles), Jarvis on, Govee strip on.
//   LAPTOP ONLY  — Jarvis off, strip off, battery saver.
//   anything else (a TV over HDMI, …) — its own profile per set of monitors; starts as
//                  extend with Jarvis and the strip off.
//
// Each profile remembers its own arrangement and layout mode (extend / mirror / …), so
// mirroring the TV never leaks into the desk. KEEP in Settings → Display saves into the
// active profile; switching profiles applies the saved one at once, without the 15 s
// keep-or-revert prompt.
//
// Switches happen on hotplug (Hyprland's monitoradded / monitorremoved, debounced: the
// dock brings its monitors up one at a time) and after a resume. While a switch is
// settling, Displays.enforce() stands still so the old layout mode isn't re-applied to
// the new screens. Saved in display-profiles.json next to this file.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import "ProfileLogic.js" as Logic

Singleton {
    id: root

    property string key: ""
    readonly property string name: key === "" ? "…" : Logic.nameFor(key)
    readonly property bool saved: key !== "" && !!(store.profiles || {})[key]
    readonly property var current: key === "" ? null : profileFor(key, root.mons)
    property bool settling: true          // until the first detection
    property var mons: []
    property int retries: 0
    property bool force: false
    property string status: ""

    FileView {
        id: file
        path: Quickshell.env("HOME") + "/.config/quickshell/display-profiles.json"
        watchChanges: true
        onFileChanged: reload()
        onAdapterUpdated: writeAdapter()
        onLoadFailed: error => writeAdapter()

        JsonAdapter {
            id: store
            property var profiles: ({})     // key → { rules, layout, jarvis, govee, saver }
            property string active: ""      // the profile last applied
            property string deskGovee: ""   // the strip mode last used at the desk
        }
    }

    function profileFor(k, mons) {
        const saved = (store.profiles || {})[k];
        const def = Logic.defaults(k, mons, store.deskGovee || Govee.mode);
        return saved ? Object.assign({}, def, saved) : def;
    }

    // Remember the strip mode picked at the desk, so coming back from the laptop / TV
    // profile (strip off) turns it back on in that mode
    Connections {
        target: Govee
        function onModeChanged() {
            if (root.key === "desk" && !root.settling && Govee.mode !== "off") store.deskGovee = Govee.mode;
        }
    }

    // ── Detection ──
    function recheck(forceApply) {
        root.settling = true;
        if (forceApply) root.force = true;
        settle.restart();
    }
    Timer { id: settle; interval: 2500; onTriggered: detect.running = true }
    Component.onCompleted: settle.restart()

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            const n = event.name;
            if (n === "monitoradded" || n === "monitoraddedv2" || n === "monitorremoved" || n === "monitorremovedv2")
                root.recheck(false);
        }
    }

    // Resume from suspend: timers don't run while the session is frozen, so a long gap
    // between ticks means we just woke up (maybe somewhere else).
    property double lastTick: Date.now()
    Timer {
        interval: 2000; running: true; repeat: true
        onTriggered: {
            const now = Date.now();
            if (now - root.lastTick > 10000) root.recheck(false);
            root.lastTick = now;
        }
    }

    Process {
        id: detect
        command: ["sh", "-c",
            "hyprctl monitors all -j; echo '@@@'; " +
            "for d in /sys/bus/usb/devices/*; do [ -f $d/idVendor ] && " +
            "echo \"$(cat $d/idVendor):$(cat $d/idProduct):$(cat $d/serial 2>/dev/null)\"; done"]
        stdout: StdioCollector {
            onStreamFinished: {
                const parts = text.split("@@@");
                let mons = [];
                try { mons = JSON.parse(parts[0]); } catch (e) { root.settling = false; return; }
                const usb = (parts[1] || "").split("\n").map(s => s.trim()).filter(s => s);
                root.decide(mons, usb);
            }
        }
    }

    function decide(mons, usb) {
        // Both Acers but the dock's USB devices not up yet? Give it a moment before
        // treating this as some other setup.
        if (Logic.acersPresent(mons) && !Logic.dockPresent(usb) && root.retries < 2) {
            root.retries++;
            settle.restart();
            return;
        }
        root.retries = 0;
        root.mons = mons;
        const k = Logic.keyFor(mons, usb);
        root.key = k;
        if (k === "desk" && store.active === "desk" && !store.deskGovee && Govee.mode !== "off")
            store.deskGovee = Govee.mode;
        if (k !== store.active || root.force) root.apply(k);
        else { root.settling = false; Displays.enforce(); }
        root.force = false;
    }

    // ── Apply ──
    function apply(k) {
        const p = profileFor(k, root.mons);
        console.log("Profiles: " + Logic.nameFor(k) + (store.profiles[k] ? "" : " (defaults)") + ", " + p.layout);
        Displays.cancelPending();
        Theme.cfg.displayLayout = p.layout;
        Theme.cfg.jarvisDocked = p.jarvis;
        Theme.cfg.autoSaver = p.saver;
        if (p.govee && Govee.mode !== p.govee) Govee.setMode(p.govee);
        store.active = k;
        Displays.writeConf(Logic.confText(k, p.rules));
        root.settling = false;
        Displays.reloadWhenAllowed();       // configreloaded → enforce() puts the layout mode on top
        arrange.restart();
    }
    // Workspaces back to their home screens once the new arrangement is in place
    Timer { id: arrange; interval: 2500; onTriggered: Roles.arrangeWorkspaces() }

    // ── Saving ──
    // Saves into profile k and writes its arrangement to stark/display-profile.lua
    function put(k, patch) {
        const all = Object.assign({}, store.profiles || {});
        all[k] = Object.assign({}, profileFor(k, root.mons), patch);
        store.profiles = all;               // new object → JsonAdapter notices and saves
        Displays.writeConf(Logic.confText(k, all[k].rules));
    }
    // KEEP in Settings → Display
    function saveLayout(rules, layout) {
        if (root.key !== "") put(root.key, { rules: rules, layout: layout });
    }
    // "Save current as this profile": the arrangement on screen right now plus the
    // current Jarvis / strip / battery-saver settings
    function saveCurrent() { if (root.key !== "") snap.running = true; }
    Process {
        id: snap
        command: ["hyprctl", "monitors", "all", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                let mons = [];
                try { mons = JSON.parse(text); } catch (e) { root.status = "Couldn't read monitors"; return; }
                const layout = Theme.cfg.displayLayout || "extend";
                root.put(root.key, {
                    rules: Logic.rulesFromMonitors(mons, layout), layout: layout,
                    jarvis: Theme.cfg.jarvisDocked, govee: Govee.mode, saver: Theme.cfg.autoSaver
                });
                root.status = "Saved as the " + root.name + " profile";
            }
        }
    }
    // Forget what was saved for this profile and put its defaults back
    function reset() {
        if (root.key === "") return;
        const all = Object.assign({}, store.profiles || {});
        delete all[root.key];
        store.profiles = all;
        root.status = root.name + " is back to its defaults";
        root.apply(root.key);
    }
}
