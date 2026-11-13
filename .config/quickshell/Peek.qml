// Peek (Super + D): every window on the active workspace hidden in special:peek<id>, back
// on the next Super + D. The toggle lives in hypr/alchemos/peek.lua. Hyprland's special:peek<id>
// workspaces are the only state: this follows them (for the bar) and puts windows back
// whenever leaving them hidden would be wrong:
//   lock          the doors start to shut (Super+L, lid, idle): nothing stays hidden behind it
//   dock change   screens come or go and workspaces move between them
//   new window    one opens on a peeked workspace: its siblings come back with it
//   start-up      a HUD (re)start finds windows still hidden
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Hyprland
import "Hypr.js" as Hypr

Singleton {
    id: root

    readonly property string prefix: "special:peek"
    // ids of the workspaces whose windows are hidden
    readonly property var peeked: Hyprland.workspaces.values
        .map(w => /^special:peek(\d+)$/.exec(w.name)).filter(m => m).map(m => Number(m[1]))
    readonly property bool active: (peeked || []).length > 0

    // "special:peek4" → 4: the workspace those windows belong to (-1 for any other name)
    function homeOf(name) {
        const m = /^special:peek(\d+)$/.exec(String(name || ""));
        return m ? Number(m[1]) : -1;
    }

    function run(call) { Quickshell.execDetached(Hypr.luaEval("require(\"alchemos.peek\")." + call)); }
    function toggle() { run("toggle()"); }
    function restore(id) { run("restore(" + Number(id) + ")"); }
    // While the screens are still changing (Hotplug.qml), wait until they've settled
    property bool restoreAfterSettle: false
    function restoreAll() {
        if (Hotplug.settling) { root.restoreAfterSettle = true; return; }
        run("restore_all()");
    }
    Connections {
        target: Hotplug
        function onSettled() { if (root.restoreAfterSettle) { root.restoreAfterSettle = false; root.run("restore_all()"); } }
    }
    function go(id) { run("go(" + Number(id) + ")"); }   // overview: restore, then switch there

    Connections {
        target: LockState
        function onDoorsChanged() { if (LockState.doors === "closing" || LockState.doors === "closed") root.restoreAll(); }
    }
    Connections {
        target: Roles
        function onDockedChanged() { root.restoreAll(); }
    }
    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (event.name !== "openwindow" || !root.active) return;
            const ws = Number(event.data.split(",")[1]);   // address,workspace,class,title
            if (root.peeked.indexOf(ws) >= 0) root.restore(ws);
        }
    }

    // Start-up recovery; a moment late so Hyprland's workspace list is in
    Timer { id: startup; interval: 1500; onTriggered: root.restoreAll() }
    Component.onCompleted: startup.restart()
}
