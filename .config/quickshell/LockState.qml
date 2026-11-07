// Lock / unlock / power transitions. Drives the lock scene (the skin's doors) on every screen.
//
//   requestLock()   – Super+L, LOCK buttons: doors slam shut (with sound), then hyprlock
//   locked()        – from stark-lock.sh: snaps the doors shut instantly (lid / idle locks),
//                     so the desktop never flashes when the laptop wakes
//   unlocked()      – ACCESS GRANTED, then the doors open onto the desktop
//   power(action)   – "shutdown" | "reboot" | "logout": doors close, screen powers down, then it happens
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import "Hypr.js" as Hypr

Singleton {
    id: root

    property string doors: "open"        // open | closing | closed | opening
    property real doorPos: 0             // 0 = open, 1 = shut
    property real msgP: 0                // 0..1 how much of the message is typed
    property real crt: 0                 // 0..1 power-off "CRT collapse"
    property real spin: 0                // emblem rotation
    property string message: ""
    property string submessage: ""
    // Lock-scene extras (a scene uses what it has; VaultScene all of them). At rest: sealed, nothing ignited.
    property real inscribe: 1            // 0..1 the seal draws itself as the doors close
    property real ignite: 0              // 0..1 the signs ignite in turn before the doors part
    property real flare: 0               // the centre's flash on a fingerprint unlock
    property bool byFingerprint: false   // set by fingerprint() just before unlocked()

    readonly property string soundDir: Quickshell.env("HOME") + "/.config/quickshell/sounds/"
    function play(file) {
        if (Theme.cfg.unlockSound) Quickshell.execDetached(["pw-play", root.soundDir + file]);
    }

    // The emblem turns while the doors move and always comes to rest at 0° when shut, so the
    // shut doors match the lock screen's picture of them (LockBg) exactly.
    NumberAnimation on spin { from: 0; to: 360; duration: 6000; loops: Animation.Infinite; running: root.doors === "opening" || (powerSeq.running && root.doors === "closing") }

    // ── Manual lock ──
    function requestLock() {
        if (root.doors !== "open") return;
        LauncherState.closeAll();
        Govee.event("lock");
        lockSeq.start();
    }
    SequentialAnimation {
        id: lockSeq
        ScriptAction { script: {
            root.doors = "closing"; root.crt = 0; root.msgP = 0; root.inscribe = 0; root.ignite = 0;
            root.message = Skin.text.lockMessage; root.submessage = Skin.text.lockSub;
            root.play("lock.wav");
        } }
        ParallelAnimation {
            NumberAnimation { target: root; property: "doorPos"; from: 0; to: 1; duration: 700; easing.type: Easing.OutBounce }
            NumberAnimation { target: root; property: "msgP"; from: 0; to: 1; duration: 500 }
            NumberAnimation { target: root; property: "spin"; from: -42; to: 0; duration: 700 }   // same speed as the open spin
            NumberAnimation { target: root; property: "inscribe"; from: 0; to: 1; duration: 700; easing.type: Easing.OutCubic }
        }
        ScriptAction { script: root.doors = "closed" }
        PauseAnimation { duration: 300 }
        // Clear the centre of the emblem — the lock screen puts the clock there
        NumberAnimation { target: root; property: "msgP"; to: 0; duration: 200 }
        ScriptAction { script: { root.message = ""; root.submessage = ""; } }
        PauseAnimation { duration: 60 }
        ScriptAction { script: root.captureAndLock() }
    }

    // Each screen's shut doors are hyprlock's background on that screen (stark-lock-bg-<NAME>.png,
    // one background block per monitor in hyprlock.conf, written by Theme). Lid / idle locks don't
    // capture, so SecurityDoors redraws each picture offscreen whenever it goes stale (colours,
    // size or role; recorded in a .key stamp next to it). Super+L also captures the live doors.
    function bgPath(screenName) {
        return Quickshell.env("HOME") + "/.config/hypr/stark-lock-bg-" + screenName + ".png";
    }
    function bgKey(size, main) {
        return ["v5", Skin.current, Theme.hex(Theme.primary), Theme.hex(Theme.secondary), Theme.hex(Theme.bg), size, main ? "main" : "other"].join(" ");
    }

    // Snapshot every screen's shut doors, then start the lock screen
    signal captureRequested()
    property int pendingCaptures: 0
    function captureAndLock() {
        root.pendingCaptures = Quickshell.screens.length;
        captureFallback.restart();
        root.captureRequested();
    }
    function captureDone() {
        if (root.pendingCaptures <= 0) return;
        if (--root.pendingCaptures > 0) return;
        captureFallback.stop();
        Quickshell.execDetached(["sh", "-c", "~/.config/hypr/stark-lock.sh"]);
    }
    Timer { id: captureFallback; interval: 700; onTriggered: { root.pendingCaptures = 1; root.captureDone(); } }

    // ── Lid / idle lock (no animation — must be instant) ──
    function locked() {
        if (lockSeq.running) return;
        // requestLock() already sent "lock" and stark-lock.sh calls back here once the doors are shut
        if (root.doors !== "closed") Govee.event("lock");
        unlockSeq.stop();
        LauncherState.closeAll();
        root.doorPos = 1; root.crt = 0; root.spin = 0; root.inscribe = 1; root.ignite = 0;
        root.message = ""; root.submessage = ""; root.msgP = 0;     // centre left clear for the clock
        root.doors = "closed";
    }

    // ── Unlock ──
    function unlocked() {
        lockSeq.stop();
        root.doorPos = 1; root.spin = 0; root.inscribe = 1; root.ignite = 0;
        if (root.byFingerprint) flareSeq.restart();
        root.byFingerprint = false;
        unlockSeq.start();
    }
    // stark-lock.sh calls this right before unlocked() when the finger matched
    function fingerprint() { root.byFingerprint = true; }
    SequentialAnimation {
        id: flareSeq
        NumberAnimation { target: root; property: "flare"; from: 0; to: 1; duration: 120; easing.type: Easing.OutCubic }
        NumberAnimation { target: root; property: "flare"; to: 0; duration: 520; easing.type: Easing.InCubic }
    }
    SequentialAnimation {
        id: unlockSeq
        ScriptAction { script: {
            root.doors = "opening"; root.msgP = 0;
            root.message = Skin.text.unlockMessage;
            root.submessage = root.greet(Skin.text.unlockSub);
            root.play("unlock.wav");
        } }
        ParallelAnimation {      // same 900 ms as before: the words type, the signs ignite in turn
            SequentialAnimation {
                NumberAnimation { target: root; property: "msgP"; from: 0; to: 1; duration: 450 }
                PauseAnimation { duration: 450 }
            }
            NumberAnimation { target: root; property: "ignite"; from: 0; to: 1; duration: 900 }
        }
        NumberAnimation { target: root; property: "doorPos"; from: 1; to: 0; duration: 850; easing.type: Easing.InOutCubic }
        ScriptAction { script: { root.doors = "open"; root.ignite = 0; Govee.event("unlock"); } }
    }

    // a skin's wording with {name} = the greeting name
    function greet(s) { return String(s || "").replace("{name}", Theme.cfg.greetName.toUpperCase()); }

    // ── Shut down / restart / log out ──
    property string pendingAction: ""
    function power(action) {
        if (powerSeq.running) return;
        LauncherState.closeAll();
        root.pendingAction = action;
        const w = Skin.text;
        root.message = action === "reboot" ? w.rebootMessage : (action === "logout" ? w.logoutMessage : w.shutdownMessage);
        root.submessage = root.greet(action === "logout" ? w.logoutSub : w.powerSub);
        powerSeq.start();
    }
    SequentialAnimation {
        id: powerSeq
        ScriptAction { script: { root.doors = "closing"; root.crt = 0; root.msgP = 0; root.inscribe = 0; root.ignite = 0; root.play("powerdown.wav"); } }
        ParallelAnimation {
            NumberAnimation { target: root; property: "doorPos"; to: 1; duration: 700; easing.type: Easing.OutBounce }
            NumberAnimation { target: root; property: "msgP"; from: 0; to: 1; duration: 700 }
            NumberAnimation { target: root; property: "inscribe"; from: 0; to: 1; duration: 700; easing.type: Easing.OutCubic }
        }
        ScriptAction { script: root.doors = "closed" }
        PauseAnimation { duration: 900 }
        NumberAnimation { target: root; property: "crt"; from: 0; to: 1; duration: 900; easing.type: Easing.InCubic }
        PauseAnimation { duration: 250 }
        ScriptAction { script: {
            if (root.pendingAction === "reboot") Quickshell.execDetached(["systemctl", "reboot"]);
            else if (root.pendingAction === "logout") { logoutLights.running = true; logoutFallback.restart(); }
            else Quickshell.execDetached(["systemctl", "poweroff"]);
        } }
    }
    // Log out: let the strip finish its drain (event logout --wait returns when it ends), then leave Hyprland
    Process {
        id: logoutLights
        command: ["stark-govee", "event", "logout", "--wait"]
        onExited: root.exitHyprland()
    }
    // daemon hung? leave anyway. The drain is ~1.9 s at NORMAL; stretch for the SLOW setting
    Timer { id: logoutFallback; interval: Math.max(3000, Math.round(2500 / Govee.animSpeed)); onTriggered: root.exitHyprland() }
    function exitHyprland() {
        logoutFallback.stop();
        // Jarvis is its own service: stop it now (music back up, nothing left behind). It would also
        // stop itself once Hyprland is gone (jarvis/core/session.py), this is just sooner.
        Quickshell.execDetached(["systemctl", "--user", "stop", "--no-block", "stark-jarvis.service"]);
        Hyprland.dispatch(Hypr.exit());
    }
}
