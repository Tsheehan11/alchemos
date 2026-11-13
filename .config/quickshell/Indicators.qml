pragma Singleton
// Live state for the bar's status icons (Style.barIndicators): Wi-Fi, Bluetooth, volume, mic, notifications.
// The mic from Pipewire, do-not-disturb from the HUD's own notifications (Notifications.qml); Bluetooth from
// bluetoothctl, polled only while some bar shows that icon (`shown`). (Quickshell.Bluetooth lists no adapter on this machine.)
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root
    readonly property real wifi: SysStats.wifi
    property bool btOn: false
    property bool btConnected: false
    readonly property real volume: OsdState.vol
    readonly property bool muted: OsdState.mute
    readonly property bool micMuted: !!Audio.source && !!Audio.source.audio && Audio.source.audio.muted
    readonly property bool dnd: Notifications.dnd
    property var shown: ({})           // icon name → how many bars show it (SkinIcon users count in / out)
    function show(name, d) { const m = Object.assign({}, shown); m[name] = Math.max(0, (m[name] || 0) + d); shown = m; }

    Process {
        id: bt
        command: ["sh", "-c", "bluetoothctl show 2>/dev/null | awk '/Powered:/ {print $2; exit}'; bluetoothctl devices Connected 2>/dev/null | grep -c '^Device'"]
        stdout: StdioCollector {
            onStreamFinished: {
                const l = text.trim().split("\n");
                root.btOn = l[0] === "yes";
                root.btConnected = root.btOn && Number(l[1] || 0) > 0;
            }
        }
    }
    Timer { interval: 10000; repeat: true; triggeredOnStart: true; running: (root.shown.bluetooth || 0) > 0; onTriggered: bt.running = true }
}
