// Battery saver. When unplugged (and enabled in Settings → System):
//   • ambient effects drop to the battery frame rate (static by default)
//   • window blur + shadows off (the biggest GPU cost in Hyprland)
//   • laptop screen 60 → 48 Hz
//   • power profile → power-saver (if power-profiles-daemon is installed)
//   • stats refresh every 5 s instead of 2 s
//   • optionally pauses Jarvis
// Everything goes back the moment you plug in.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Hyprland

Singleton {
    id: root

    readonly property bool onBattery: SysStats.discharging
    readonly property bool saver: Theme.cfg.autoSaver && onBattery
    property bool stoppedJarvis: false

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
        const hz = (s && Theme.cfg.saverLowRefresh) ? 48 : 60;
        Quickshell.execDetached(["sh", "-c",
            "hyprctl monitors -j | grep -q '\"name\": \"eDP-1\"' && hyprctl keyword monitor 'eDP-1,1920x1200@" + hz + ",5120x120,1'"]);
        Quickshell.execDetached(["sh", "-c",
            "command -v powerprofilesctl >/dev/null && powerprofilesctl set " + (s ? "power-saver" : "balanced")]);

        if (s && Theme.cfg.saverStopJarvis && JarvisState.online) {
            root.stoppedJarvis = true;
            Quickshell.execDetached(["pkill", "-f", "jarvis.py"]);
        } else if (!s && root.stoppedJarvis) {
            root.stoppedJarvis = false;
            Quickshell.execDetached(["sh", "-c", "nohup ~/.config/jarvis/.venv/bin/python ~/.config/jarvis/jarvis.py >/dev/null 2>&1 &"]);
        }
    }
}
