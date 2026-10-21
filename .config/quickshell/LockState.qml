// Lock / unlock / power transitions. Drives the "security doors" on every screen.
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

Singleton {
    id: root

    property string doors: "open"        // open | closing | closed | opening
    property real doorPos: 0             // 0 = open, 1 = shut
    property real msgP: 0                // 0..1 how much of the message is typed
    property real crt: 0                 // 0..1 power-off "CRT collapse"
    property real spin: 0                // emblem rotation
    property string message: ""
    property string submessage: ""

    readonly property string soundDir: Quickshell.env("HOME") + "/.config/quickshell/sounds/"
    function play(file) {
        if (Theme.cfg.unlockSound) Quickshell.execDetached(["pw-play", root.soundDir + file]);
    }

    NumberAnimation on spin { from: 0; to: 360; duration: 6000; loops: Animation.Infinite; running: root.doors !== "open" }

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
            root.doors = "closing"; root.crt = 0; root.msgP = 0;
            root.message = "SECURING"; root.submessage = "STARK OS // LOCKDOWN";
            root.play("lock.wav");
        } }
        ParallelAnimation {
            NumberAnimation { target: root; property: "doorPos"; from: 0; to: 1; duration: 700; easing.type: Easing.OutBounce }
            NumberAnimation { target: root; property: "msgP"; from: 0; to: 1; duration: 500 }
        }
        ScriptAction { script: root.doors = "closed" }
        PauseAnimation { duration: 300 }
        // Clear the centre of the emblem — the lock screen puts the clock there
        NumberAnimation { target: root; property: "msgP"; to: 0; duration: 200 }
        ScriptAction { script: { root.message = ""; root.submessage = ""; } }
        PauseAnimation { duration: 60 }
        ScriptAction { script: root.captureAndLock() }
    }

    // Snapshot the shut doors for the lock screen background, then start the lock screen
    readonly property string lockBg: Quickshell.env("HOME") + "/.config/hypr/stark-lock-bg.png"
    signal captureRequested(string path)
    property bool waitingCapture: false
    function captureAndLock() {
        root.waitingCapture = true;
        captureFallback.restart();
        root.captureRequested(root.lockBg);
    }
    function captureDone() {
        if (!root.waitingCapture) return;
        root.waitingCapture = false;
        captureFallback.stop();
        Quickshell.execDetached(["sh", "-c", "~/.config/hypr/stark-lock.sh"]);
    }
    Timer { id: captureFallback; interval: 700; onTriggered: root.captureDone() }

    // ── Lid / idle lock (no animation — must be instant) ──
    function locked() {
        if (lockSeq.running) return;
        // requestLock() already sent "lock" and stark-lock.sh calls back here once the doors are shut
        if (root.doors !== "closed") Govee.event("lock");
        unlockSeq.stop();
        LauncherState.closeAll();
        root.doorPos = 1; root.crt = 0;
        root.message = ""; root.submessage = ""; root.msgP = 0;     // centre left clear for the clock
        root.doors = "closed";
    }

    // ── Unlock ──
    function unlocked() {
        lockSeq.stop();
        root.doorPos = 1;
        unlockSeq.start();
    }
    SequentialAnimation {
        id: unlockSeq
        ScriptAction { script: {
            root.doors = "opening"; root.msgP = 0;
            root.message = "ACCESS GRANTED";
            root.submessage = "WELCOME BACK, " + Theme.cfg.greetName.toUpperCase();
            root.play("unlock.wav");
        } }
        NumberAnimation { target: root; property: "msgP"; from: 0; to: 1; duration: 450 }
        PauseAnimation { duration: 450 }
        NumberAnimation { target: root; property: "doorPos"; from: 1; to: 0; duration: 850; easing.type: Easing.InOutCubic }
        ScriptAction { script: { root.doors = "open"; Govee.event("unlock"); } }
    }

    // ── Shut down / restart / log out ──
    property string pendingAction: ""
    function power(action) {
        if (powerSeq.running) return;
        LauncherState.closeAll();
        root.pendingAction = action;
        root.message = action === "reboot" ? "REBOOTING" : (action === "logout" ? "SIGNING OFF" : "SHUTTING DOWN");
        root.submessage = action === "logout" ? "SEE YOU SOON, " + Theme.cfg.greetName.toUpperCase() : "SAVING STATE // POWERING DOWN SYSTEMS";
        powerSeq.start();
    }
    SequentialAnimation {
        id: powerSeq
        ScriptAction { script: { root.doors = "closing"; root.crt = 0; root.msgP = 0; root.play("powerdown.wav"); } }
        ParallelAnimation {
            NumberAnimation { target: root; property: "doorPos"; to: 1; duration: 700; easing.type: Easing.OutBounce }
            NumberAnimation { target: root; property: "msgP"; from: 0; to: 1; duration: 700 }
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
    // Log out: let the strip finish its sign-off animation (~2 s), then leave Hyprland
    Process {
        id: logoutLights
        command: ["stark-govee", "event", "logout", "--wait"]
        onExited: root.exitHyprland()
    }
    Timer { id: logoutFallback; interval: 6000; onTriggered: root.exitHyprland() }   // daemon hung? leave anyway
    function exitHyprland() {
        logoutFallback.stop();
        Hyprland.dispatch("exit");
    }
}
