// Network: VPN state (VPN.qml, stark-vpn's state file), Wi-Fi name + signal, and live throughput
// (SysStats, which already slows down in battery saver / combat mode). The Wi-Fi name comes from
// `nmcli monitor` events while the widget is on screen, not a poll.
import QtQuick
import Quickshell.Io
import ".."

WidgetBody {
    id: w
    title: "NETWORK"
    detail: VPN.connected ? "SECURED" : VPN.blocked ? "BLOCKED" : VPN.busy ? VPN.state.toUpperCase() : "OPEN"
    property string ssid: ""
    function clicked() {}
    function doubleClicked() { VPN.toggle(); }

    Process {
        id: ssidProc
        command: ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"]
        stdout: StdioCollector { onStreamFinished: { const l = text.split("\n").find(x => x.startsWith("yes:")); w.ssid = l ? l.slice(4) : ""; } }
    }
    Process {       // nmcli prints a line on every connection / device change: re-read the SSID then
        running: w.active
        command: ["nmcli", "monitor"]
        stdout: SplitParser { onRead: debounce.restart() }
        onRunningChanged: if (running) ssidProc.running = true
    }
    Timer { id: debounce; interval: 800; onTriggered: ssidProc.running = true }

    implicitWidth: 300
    implicitHeight: 104

    readonly property color vpnTone: VPN.connected ? Theme.primary : VPN.blocked ? Theme.secondary : Theme.faint
    Item {
        width: 70; height: 70
        Ring { anchors.centerIn: parent; radius: 32; thickness: 2; value: 1; animated: false; color: Qt.rgba(w.vpnTone.r, w.vpnTone.g, w.vpnTone.b, 0.8); trackColor: "transparent"; dashed: !VPN.connected; dash: [3, 5]
               rotation: VPN.busy && w.live && !w.saver ? w.t * 120 : 0 }
        Ring { anchors.centerIn: parent; radius: 24; thickness: 3; value: Math.max(0.001, SysStats.wifi); animated: w.live; color: Theme.primary; gauge: true }
        Text { anchors.centerIn: parent; text: VPN.connected ? "⛨" : "◌"; color: w.vpnTone; font.pixelSize: 18 }
    }
    Column {
        x: 82; width: 218; spacing: 2
        Text { width: 218; elide: Text.ElideRight; text: (VPN.connected || VPN.busy ? (VPN.current.name || "VPN") + " · " + (VPN.where() || VPN.state) : "VPN OFF").toUpperCase(); color: w.vpnTone; font.family: w.mono; font.pixelSize: 11; font.letterSpacing: 2 }
        Text { width: 218; elide: Text.ElideRight; text: (w.ssid || "NO WI-FI") + (SysStats.wifi > 0 ? " · " + Math.round(SysStats.wifi * 100) + "%" : ""); color: Theme.textSoft; font.family: w.mono; font.pixelSize: 12 }
        Text { text: "↓ " + SysStats.fmtRate(SysStats.rxRate) + "   ↑ " + SysStats.fmtRate(SysStats.txRate); color: Theme.dim; font.family: w.mono; font.pixelSize: 10 }
        Graph { width: 218; height: 26; values: SysStats.rxHistory; maxValue: 0; lineColor: Theme.primary; fillColor: Theme.pc(0.1) }
    }
}
