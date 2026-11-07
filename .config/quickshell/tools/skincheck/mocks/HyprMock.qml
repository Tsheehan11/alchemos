pragma Singleton
import QtQuick
import Quickshell
// Hyprland stand-in for the window renders (pin.py points Hyprland.* here): a fixed monitor and workspaces
Singleton {
    property var focusedMonitor: ({ name: "DP-1" })
    property var focusedWorkspace: ({ id: 2 })
    property var workspaces: ({ values: [1, 2, 3, 7].map(i => ({ id: i, monitor: { name: "DP-1" } })) })
    signal rawEvent(var event)
    function dispatch(c) {}
}
