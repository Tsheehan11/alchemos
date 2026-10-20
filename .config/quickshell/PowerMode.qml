// Battery saver. When unplugged (and enabled in Settings → System):
//   • ambient effects drop to the battery frame rate (static by default)
//   • window blur + shadows off (the biggest GPU cost in Hyprland)
//   • laptop screen 60 → 48 Hz
//   • power profile → power-saver (if power-profiles-daemon is installed)
//   • stats refresh every 5 s instead of 2 s
//   • optionally pauses Jarvis (handled in JarvisState)
// Everything goes back the moment you plug in.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root

    readonly property bool onBattery: SysStats.discharging
    readonly property bool saver: Theme.cfg.autoSaver && onBattery

    onSaverChanged: applyTimer.restart()
    Component.onCompleted: applyTimer.restart()
    Timer { id: applyTimer; interval: 400; onTriggered: root.apply() }

    // `hyprctl reload` resets these, so re-apply after any reload
    Connections {
        target: Hyprland
        function onRawEvent(event) { if (event.name === "configreloaded") applyTimer.restart(); }
    }

    function hypr(cmds) {
        Quickshell.execDetached(["hyprctl", "--batch", cmds.join(" ; ")]);
    }

    function apply() {
        const s = root.saver;
        const blurOn = !(s && Theme.cfg.saverNoBlur);
        hypr([
            "keyword decoration:blur:enabled " + (blurOn ? "true" : "false"),
            "keyword decoration:shadow:enabled " + (blurOn ? "true" : "false")
        ]);
        laptopProbe.running = true;
        Quickshell.execDetached(["sh", "-c",
            "command -v powerprofilesctl >/dev/null && powerprofilesctl set " + (s ? "power-saver" : "balanced")]);
    }

    // Laptop screen 60 ↔ 48 Hz, keeping whatever position / scale / rotation
    // Settings → Display gave it (and leaving it alone if it's off or mirrored)
    Process {
        id: laptopProbe
        command: ["hyprctl", "monitors", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                let mons = [];
                try { mons = JSON.parse(text); } catch (e) { return; }
                const m = mons.find(x => x.name === "eDP-1");
                if (!m || (m.mirrorOf && m.mirrorOf !== "none")) return;
                const low = root.saver && Theme.cfg.saverLowRefresh;
                const hz = Math.round(m.refreshRate);
                let want = hz;
                if (low && hz > 48) want = 48;
                else if (!low && hz === 48) want = 60;
                if (want === hz) return;
                Quickshell.execDetached(["hyprctl", "keyword", "monitor",
                    "eDP-1," + m.width + "x" + m.height + "@" + want + "," + m.x + "x" + m.y + "," + m.scale + ",transform," + m.transform]);
            }
        }
    }
}
