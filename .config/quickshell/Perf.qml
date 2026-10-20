// Performance governor for the ambient effects.
//
// 1. One shared clock (time) ticks at a capped frame rate (Settings → Appearance →
//    Effects), instead of every animation redrawing at the monitors' full 144 Hz.
// 2. Effects on a screen pause while that screen's workspace has windows on it
//    (you can't see the background then anyway), and resume when it's empty.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root

    property real time: 0                  // seconds, advances at `fps`
    readonly property int fps: PowerMode.saver ? Theme.cfg.batteryFps : Theme.cfg.effectsFps
    readonly property double t0: Date.now()

    Timer {
        interval: Math.max(16, Math.round(1000 / Math.max(1, root.fps)))
        running: root.fps > 0
        repeat: true
        onTriggered: root.time = (Date.now() - root.t0) / 1000
    }

    // Monitor name → true if its visible workspace has windows
    property var busy: ({})

    // Should ambient effects animate on this screen right now?
    function live(screen) {
        if (!screen || root.fps <= 0 || !Theme.cfg.animatedBg) return false;
        if (Theme.cfg.pauseBehindWindows && root.busy[screen.name] === true) return false;
        return true;
    }

    // Should the clock / diagnostics / audio deck hide on this screen right now?
    // (They peek through the gaps between tiled windows otherwise.)
    function hidden(screen) {
        return !!screen && Theme.cfg.hideHudBehindWindows && root.busy[screen.name] === true;
    }

    Process {
        id: poll
        command: ["sh", "-c", "hyprctl monitors -j; echo '@@@'; hyprctl workspaces -j"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const parts = text.split("@@@");
                    const mons = JSON.parse(parts[0]);
                    const wss = JSON.parse(parts[1]);
                    const count = {};
                    for (const w of wss) count[w.id] = w.windows;
                    const b = {};
                    for (const m of mons) b[m.name] = (count[m.activeWorkspace.id] || 0) > 0;
                    root.busy = b;
                } catch (e) {}
            }
        }
    }
    Timer { id: debounce; interval: 150; onTriggered: poll.running = true }
    Timer { interval: 5000; running: true; repeat: true; triggeredOnStart: true; onTriggered: poll.running = true }

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            const n = event.name;
            if (n.startsWith("openwindow") || n.startsWith("closewindow") || n.startsWith("movewindow")
                || n.startsWith("workspace") || n.startsWith("focusedmon") || n.startsWith("monitor"))
                debounce.restart();
        }
    }
}
