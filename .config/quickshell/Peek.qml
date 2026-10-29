// Peek (Super + D): every window on the active workspace hidden in special:peek<id>, back
// on the next Super + D. The toggle lives in hypr/stark/peek.lua. Hyprland's special:peek<id>
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
        .filter(w => w.name.startsWith(root.prefix))
        .map(w => Number(w.name.slice(root.prefix.length)))
    readonly property bool active: peeked.length > 0

    function run(call) { Quickshell.execDetached(Hypr.luaEval("require(\"stark.peek\")." + call)); }
    function toggle() { run("toggle()"); }
    function restore(id) { run("restore(" + Number(id) + ")"); }
    function restoreAll() { run("restore_all()"); }

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
