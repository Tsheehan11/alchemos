pragma Singleton
import QtQuick
import Quickshell
Singleton { property real cpu: 0.34; property real ram: 0.58; property real gpu: 0.12; property real battery: 0.81; property bool charging: false
            property bool gpuAvailable: true; property bool discharging: false; property real wifi: 0.7; property var cpuHistory: []
            property real rxRate: 125000; property real txRate: 18000; property bool polled: true
            function fmtRate(b) { return b >= 1e6 ? (b / 1e6).toFixed(1) + " MB/s" : Math.round(b / 1e3) + " KB/s"; } }
