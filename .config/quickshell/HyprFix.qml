pragma Singleton
// Is the Hyprland that fixes the unplug crash (0.57.0) out, installed, running?
// ~/.config/hypr/stark-hypr-check does the work (also `stark-rescue status`); this runs it
// with --sync (a private, root-free copy of the package databases) a minute after the HUD
// starts and every 6 hours, and the bar shows HYPR 0.57 while there's something to do:
// "available" (sudo pacman -Syu) or "installed" (log out and back in). The settle gate
// (Hotplug.qml) stays after the upgrade either way.
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property string state: ""        // waiting | available | installed | running
    property string repo: ""
    property string installed: ""
    property string running: ""
    readonly property bool pending: state === "available" || state === "installed"
    readonly property string label: state === "available" ? "HYPR " + repo.replace(/-.*/, "") + " READY"
                                  : state === "installed" ? "HYPR " + installed.replace(/-.*/, "") + " · RELOG" : ""

    Process {
        id: check
        command: [Quickshell.env("HOME") + "/.config/hypr/stark-hypr-check", "--sync"]
        stdout: StdioCollector {
            onStreamFinished: {
                const kv = {};
                for (const part of text.trim().split(/\s+/)) {
                    const i = part.indexOf("=");
                    if (i > 0) kv[part.slice(0, i)] = part.slice(i + 1);
                }
                if (!kv.state) return;
                root.repo = kv.repo || ""; root.installed = kv.installed || ""; root.running = kv.running || "";
                root.state = kv.state;
            }
        }
    }
    Timer { interval: 60000; running: true; onTriggered: check.running = true }
    Timer { interval: 6 * 3600 * 1000; repeat: true; running: true; onTriggered: check.running = true }
}
