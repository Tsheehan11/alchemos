pragma Singleton
import QtQuick
import Quickshell
Singleton {
    readonly property var mon: ({ id: 0, name: "DP-1", x: 0, y: 0, width: 2560, height: 1440, activeWorkspace: { id: 2 } })
    property var monitors: [mon]
    property var workspaces: []
    readonly property var wins: ({
        1: [{ address: "0x1", class: "zen", monitor: 0, at: [10, 40], size: [1260, 1390] }, { address: "0x2", class: "kitty", monitor: 0, at: [1290, 40], size: [1260, 1390] }],
        2: [{ address: "0x3", class: "code", monitor: 0, at: [10, 40], size: [2540, 1390] }],
        3: []
    })
    function workspacesFor(s) { return [1, 2, 3]; }
    function activeOn(n) { return 2; }
    function clientsOn(id) { return wins[id] || []; }
    function isPeeked(id) { return false; }
    function homeId(w) { return w ? w.id : -1; }
    function monitorByName(n) { return mon; }
    function monitorById(i) { return mon; }
    function iconFor(c) { return ""; }
    function capturable(c) { return false; }
    function toplevelFor(a) { return null; }
}
