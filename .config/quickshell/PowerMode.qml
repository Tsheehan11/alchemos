// Battery saver. When unplugged (and enabled in Settings → System):
//   • ambient effects drop to the battery frame rate (static by default)
//   • window blur + shadows off (the biggest GPU cost in Hyprland)
//   • laptop screen 60 → 48 Hz
//   • power profile → power-saver (if power-profiles-daemon is installed); the
//     profile you had goes back on plug-in. Only an actual saver on/off changes
//     it — a HUD restart leaves whatever profile you picked alone.
//   • stats refresh every 5 s instead of 2 s
//   • optionally pauses Jarvis (handled in JarvisState)
//   • busy cursor stops spinning (Theme rebuilds it static)
// Everything goes back the moment you plug in.
// While combat mode (GameMode) has taken over blur / the power profile, those
// are left to it, and the saver catches up when the game ends.
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
    // Still busy cursor on battery (Theme rebuilds the cursor when this flips)
    Binding { target: Theme; property: "cursorSaver"; value: root.saver }
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
        if (GameMode.owns.indexOf("hypr") < 0)
            hypr([
                "keyword decoration:blur:enabled " + (blurOn ? "true" : "false"),
                "keyword decoration:shadow:enabled " + (blurOn ? "true" : "false")
            ]);
        laptopProbe.running = true;
        // Wait for the first battery reading: until then `saver` is just a default
        if (GameMode.owns.indexOf("power") < 0 && SysStats.polled)
            Quickshell.execDetached(["sh", "-c", root.profileScript, "sh", s ? "on" : "off"]);
    }

    // Power profile, only on a real saver toggle. The last state acted on is kept in
    // $XDG_RUNTIME_DIR (survives HUD restarts, cleared at logout), so restarting the
    // HUD is a no-op. First run of a session: saver on → power-saver, off → untouched.
    readonly property string profileScript: [
        "command -v powerprofilesctl >/dev/null || exit 0",
        "d=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/stark-power; mkdir -p $d",
        "last=$(cat $d/saver 2>/dev/null)",
        "[ \"$last\" = \"$1\" ] && exit 0",
        "echo $1 > $d/saver",
        "if [ $1 = on ]; then",
        "  cur=$(powerprofilesctl get); [ \"$cur\" != power-saver ] && echo $cur > $d/before",
        "  powerprofilesctl set power-saver",
        "elif [ -n \"$last\" ]; then",
        "  powerprofilesctl set $(cat $d/before 2>/dev/null || echo balanced); rm -f $d/before",
        "fi"
    ].join("\n")

    Connections { target: SysStats; function onPolledChanged() { applyTimer.restart(); } }
    // stark-game restores the blur / profile it found on entry; re-apply in case the
    // saver flipped meanwhile (no-op for the profile if it didn't)
    Connections {
        target: GameMode
        function onActiveChanged() { if (!GameMode.active) applyTimer.restart(); }
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
