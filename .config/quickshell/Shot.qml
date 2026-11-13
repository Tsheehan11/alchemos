pragma Singleton
// Screenshots: Print = region, Shift+Print = this monitor, Super+Shift+S = region → annotate (hypr/stark/binds.lua),
// the SCREENSHOT tile in the control center, `qs ipc call shot region|screen|window|annotate`, Jarvis.
// The capture itself is ~/.local/bin/alchemos-shot (grim / slurp / wl-copy / satty); this only clears the HUD out
// of the way first, then plays the shutter (ShotFlash.qml) and shows the toast (ShotToast.qml).
//
// Keeping the HUD out of the picture: Hyprland fades a layer out over ~400 ms when it unmaps, so hiding an
// overlay by unmapping it would leave its ghost in the shot. Instead every overlay binds its contentItem's
// opacity to `hiding` (transparent at once, still mapped); a frame later the transient pop-ups are closed
// (their fade-out is of an empty buffer by then), and a frame after that alchemos-shot runs. The desktop itself
// (bar, clock, panels, widgets, background) stays in; so do Settings and the JARVIS console, as windows you
// may want to capture.
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property var modes: ["region", "screen", "window", "annotate"]
    property bool hiding: false        // HUD overlays transparent while a capture is being taken
    property bool busy: false
    property string mode: ""
    property var last: ({})            // alchemos-shot's --json result for the latest saved shot
    property int serial: 0             // +1 per saved shot; ShotFlash / ShotToast react to it
    property bool toastShowing: false
    property bool toastHover: false    // the pointer is on the toast: it doesn't time out
    readonly property bool calm: PowerMode.saver   // battery saver: no flash, no sweep, no slide

    readonly property string home: Quickshell.env("HOME")
    readonly property string bin: home + "/.local/bin/alchemos-shot"
    readonly property string sound: home + "/.config/quickshell/sounds/shutter.wav"
    property string output: ""

    // "ok" once started, else why not (the IPC returns it)
    function take(m, out) {
        m = String(m || "region").toLowerCase();
        if (root.modes.indexOf(m) < 0) return "unknown mode " + m + " (region | screen | window | annotate)";
        if (root.busy) return "busy";
        root.busy = true;
        root.mode = m;
        root.output = out || "";
        root.toastShowing = false;
        root.hiding = true;
        closeStep.restart();
        return "ok";
    }

    function closePopups() {
        LauncherState.open = false;
        LauncherState.searchOpen = false;
        LauncherState.controlOpen = false;
        LauncherState.overviewOpen = false;
        LauncherState.powerOpen = false;
        Widgets.closeMaker();                    // right-click "add widget" menu (WidgetMaker)
    }

    Timer { id: closeStep; interval: 50; onTriggered: { root.closePopups(); runStep.restart(); } }
    Timer {
        id: runStep
        interval: 70
        onTriggered: {
            proc.command = [root.bin, root.mode, "--json"].concat(root.output ? ["--output", root.output] : []);
            proc.running = true;
            watchdog.restart();
        }
    }
    // A selection left open for minutes would keep the HUD hidden; give up after 3 min
    Timer { id: watchdog; interval: 180000; onTriggered: if (proc.running) proc.signal(15) }

    Process {
        id: proc
        stdout: StdioCollector {
            onStreamFinished: {
                watchdog.stop();
                let r = null;
                try { r = JSON.parse(text.trim().split("\n").pop()); } catch (e) {}
                root.hiding = false;
                root.busy = false;
                if (!r) { console.warn("alchemos-shot: no result", text); return; }
                if (!r.ok) {
                    if (!r.cancelled) {
                        console.warn("alchemos-shot:", r.error);
                        root.last = r;               // the toast shows the failure
                        root.serial++;
                        root.toastShowing = true;
                        toastTimer.restart();
                    }
                    return;
                }
                root.last = r;
                Quickshell.execDetached(["pw-play", "--volume", "0.7", "-P",
                    "{ media.name = \"HUD shutter\" state.restore-props = false }", root.sound]);
                root.serial++;
                root.toastShowing = true;
                toastTimer.restart();
            }
        }
    }

    Timer { id: toastTimer; interval: 7000; onTriggered: if (root.toastHover) restart(); else root.toastShowing = false }
    function dismiss() { root.toastShowing = false; }
    function openShot() { if (root.last.path) Quickshell.execDetached(["xdg-open", root.last.path]); root.dismiss(); }
    function openFolder() {
        if (!root.last.dir) return;
        // Dolphin (the files app, Super+E) opens the folder with the shot selected
        Quickshell.execDetached(["sh", "-c", "command -v dolphin >/dev/null && exec dolphin --select \"$1\" || exec xdg-open \"$2\"",
                                 "sh", root.last.path || root.last.dir, root.last.dir]);
        root.dismiss();
    }

    // The toast / flash go on the monitor that holds most of the shot
    function mainScreen() { return root.last.monitors && root.last.monitors.length ? root.last.monitors[0].name : ""; }
    function rectOn(name) { return (root.last.monitors || []).find(m => m.name === name) || null; }
}
