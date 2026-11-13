// Battery saver. When unplugged (and enabled in Settings → System):
//   • ambient effects drop to the battery frame rate (static by default)
//   • window blur + shadows off (the biggest GPU cost in Hyprland)
//   • laptop screen 60 → 48 Hz
//   • power profile → power-saver (if power-profiles-daemon is installed); the
//     profile you had goes back on plug-in. Only an actual saver on/off changes
//     it — a HUD restart leaves whatever profile you picked alone.
//   • stats refresh every 5 s instead of 2 s
//   • optionally pauses Jarvis (handled in JarvisState)
// Picking BALANCED / PERFORMANCE by hand while unplugged (pickProfile) turns the
// saver off until the next plug-in; picking SAVER turns it back on.
// Everything goes back the moment you plug in.
// While combat mode (GameMode) has taken over blur / the power profile, those
// are left to it, and the saver catches up when the game ends.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import "Hypr.js" as Hypr

Singleton {
    id: root

    readonly property bool onBattery: SysStats.discharging
    readonly property bool saver: Theme.cfg.autoSaver && onBattery && !overridden

    // Saver switched off by hand for this unplug. Kept in $XDG_RUNTIME_DIR/alchemos-power/override
    // so a HUD restart doesn't bring the saver back; loaded before any profile is touched.
    property bool overridden: false
    property bool loaded: false
    readonly property string stateDir: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/alchemos-power"

    onSaverChanged: applyTimer.restart()
    onOnBatteryChanged: if (!onBattery) clearOverride()
    onLoadedChanged: applyTimer.restart()
    Component.onCompleted: { overrideProbe.running = true; applyTimer.restart(); }
    Process {
        id: overrideProbe
        command: ["sh", "-c", "[ -e \"$1/override\" ] && echo 1 || echo 0", "sh", root.stateDir]
        stdout: StdioCollector { onStreamFinished: { root.overridden = text.trim() === "1"; root.loaded = true; } }
    }

    function clearOverride() {
        if (!overridden) return;
        overridden = false;
        Quickshell.execDetached(["rm", "-f", stateDir + "/override"]);
    }

    // Control center / Settings power buttons. Returns the argv to run. Choosing a
    // non-saver profile on battery also records the saver as "off" (and drops the
    // remembered profile) so the profile script won't undo the pick when the saver flips.
    function pickProfile(p) {
        const manualOff = p !== "power-saver" && onBattery && Theme.cfg.autoSaver;
        if (p === "power-saver") clearOverride();
        else if (manualOff) overridden = true;
        return ["sh", "-c", [
            "d=$1; mkdir -p $d",
            "if [ $3 = 1 ]; then touch $d/override; echo off > $d/saver; rm -f $d/before; fi",
            "powerprofilesctl set $2"
        ].join("\n"), "sh", stateDir, p, manualOff ? "1" : "0"];
    }
    Timer { id: applyTimer; interval: 400; onTriggered: root.apply() }

    // `hyprctl reload` resets these, so re-apply after any reload
    Connections {
        target: Hyprland
        function onRawEvent(event) { if (event.name === "configreloaded") applyTimer.restart(); }
    }

    function apply() {
        const s = root.saver;
        const blurOn = !(s && Theme.cfg.saverNoBlur);
        if (GameMode.owns.indexOf("hypr") < 0)
            Quickshell.execDetached(Hypr.config({ decoration: { blur: { enabled: blurOn }, shadow: { enabled: blurOn } } }));
        laptopProbe.running = true;
        // plugged in while the HUD was down: a stale override goes
        if (SysStats.polled && !root.onBattery) root.clearOverride();
        // Wait for the first battery reading (until then `saver` is just a default)
        // and for the override flag
        if (GameMode.owns.indexOf("power") < 0 && SysStats.polled && root.loaded)
            Quickshell.execDetached(["sh", "-c", root.profileScript, "sh", s ? "on" : "off"]);
    }

    // Power profile, only on a real saver toggle. The last state acted on is kept in
    // $XDG_RUNTIME_DIR (survives HUD restarts, cleared at logout), so restarting the
    // HUD is a no-op. First run of a session: saver on → power-saver, off → untouched.
    readonly property string profileScript: [
        "command -v powerprofilesctl >/dev/null || exit 0",
        "d=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/alchemos-power; mkdir -p $d",
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
    // alchemos-game restores the blur / profile it found on entry; re-apply in case the
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
                Quickshell.execDetached(Hypr.monitors([{ output: "eDP-1", mode: m.width + "x" + m.height + "@" + want,
                    position: m.x + "x" + m.y, scale: m.scale, transform: m.transform }]));
            }
        }
    }
}
