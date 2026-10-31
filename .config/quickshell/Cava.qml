pragma Singleton
// One cava for every MUSIC screen's visualizer (MediaPanel). Runs while at least one deck's
// visualizer is on screen and not covered by windows; off in combat mode (Perf.lite).
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property var bars: []
    property var users: ({})        // screen name → true while that deck wants bars
    readonly property bool wanted: Object.keys(users).length > 0

    function want(name, on) {
        if ((root.users[name] === true) === on) return;
        const u = Object.assign({}, root.users);
        if (on) u[name] = true; else delete u[name];
        root.users = u;
    }

    Process {
        running: root.wanted && !Perf.lite
        command: ["cava", "-p", Quickshell.env("HOME") + "/.config/quickshell/cava.conf"]
        stdout: SplitParser {
            onRead: data => {
                const v = data.split(";").filter(s => s.length > 0).map(Number);
                if (v.length > 0) root.bars = v;
            }
        }
    }
}
