// Decides what each screen is for, based on what's plugged in.
//
//   Laptop only:  laptop = "main"  (arc-reactor clock, workspaces 1–5)
//   Docked:       leftmost external monitor = "main"  (clock, workspaces 1–3)
//                 next external monitor     = "diag"  (diagnostics, 4–6)
//                 laptop screen             = "media" (audio deck, 7–9)
//
// Works by position, not port name, so it doesn't matter if the dock
// renames the monitors (DP-5, DP-7, …) when you replug.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Hyprland

Singleton {
    id: root

    readonly property string laptopName: "eDP-1"

    readonly property var externals: {
        const arr = [];
        for (let i = 0; i < Quickshell.screens.length; i++) {
            const s = Quickshell.screens[i];
            if (s.name !== root.laptopName && s.name !== "STARK-TV") arr.push(s);
        }
        return arr.sort((a, b) => a.x - b.x);
    }
    readonly property bool docked: externals.length > 0

    function role(screen) {
        if (!screen) return "none";
        // Virtual TV screen while casting: the full HUD if it's the only screen
        // showing (duplicate mode), otherwise just background + bar
        if (screen.name === "STARK-TV") return Quickshell.screens.length > 1 ? "extra" : "main";
        if (!root.docked) return "main";
        if (screen.name === root.laptopName) return "media";
        const i = root.externals.findIndex(s => s.name === screen.name);
        return i === 0 ? "main" : (i === 1 ? "diag" : "extra");
    }

    function baseWorkspaces(screen) {
        switch (role(screen)) {
        case "main":  return root.docked ? [1, 2, 3] : [1, 2, 3, 4, 5];
        case "diag":  return [4, 5, 6];
        case "media": return [7, 8, 9];
        default:      return [];
        }
    }

    // After docking, send workspaces back to their home screens
    function arrangeWorkspaces() {
        if (!root.docked || Cast.active) return;   // don't shuffle workspaces mid-cast
        const homes = {};
        homes[1] = homes[2] = homes[3] = root.externals[0].name;
        const second = root.externals.length > 1 ? root.externals[1].name : root.externals[0].name;
        homes[4] = homes[5] = homes[6] = second;
        homes[7] = homes[8] = homes[9] = root.laptopName;
        const existing = Hyprland.workspaces.values.map(w => w.id);
        for (const ws in homes) {
            if (existing.indexOf(Number(ws)) >= 0)
                Hyprland.dispatch("moveworkspacetomonitor " + ws + " " + homes[ws]);
        }
    }

    // At login: laptop only → start on workspace 1; docked → make sure everything is home
    Component.onCompleted: {
        if (!root.docked) Hyprland.dispatch("workspace 1");
        else redock.restart();
    }

    // Also re-arrange whenever the set of screens changes
    Connections {
        target: Quickshell
        function onScreensChanged() { redock.restart(); }
    }

    // Re-arrange shortly after a monitor is plugged in
    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (event.name === "monitoradded" || event.name === "monitoraddedv2")
                redock.restart();
        }
    }
    Timer {
        id: redock
        interval: 1500
        onTriggered: root.arrangeWorkspaces()
    }
}
