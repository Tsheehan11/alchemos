// System stats: CPU (with history), RAM, CPU package temperature, battery. Uses SysStats,
// which already slows down in battery saver and combat mode. Large / huge: a full dashboard
// (gauges, CPU / GPU / network graphs, disk, uptime) for a monitor of its own.
import QtQuick
import Quickshell
import Quickshell.Io
import ".."

WidgetBody {
    id: w
    title: big ? "SYSTEM // DIAGNOSTICS" : "SYSTEM"
    detail: SysStats.discharging ? "ON BATTERY" : "AC"

    // coretemp package sensor, found once
    property string tempFile: ""
    property real temp: -1
    Process {
        running: true
        command: ["sh", "-c", "for h in /sys/class/hwmon/hwmon*; do [ \"$(cat $h/name)\" = coretemp ] && for l in $h/temp*_label; do grep -q Package $l && echo ${l%_label}_input && exit; done; done"]
        stdout: StdioCollector { onStreamFinished: w.tempFile = text.trim() }
    }
    FileView { id: tf; path: w.tempFile; onLoaded: w.temp = Number(text()) / 1000 }
    Timer { interval: SysStats.interval; running: w.active && w.tempFile !== ""; repeat: true; triggeredOnStart: true; onTriggered: tf.reload() }

    readonly property var rows: [
        { k: "CPU", v: SysStats.cpu, t: Math.round(SysStats.cpu * 100) + "%" },
        { k: "RAM", v: SysStats.ram, t: SysStats.ramUsedGb.toFixed(1) + " GB" },
        { k: "TEMP", v: temp < 0 ? 0 : Math.min(1, temp / 100), t: temp < 0 ? "—" : Math.round(temp) + "°C", hot: temp >= 85 },
        { k: "BAT", v: SysStats.battery, t: Math.round(SysStats.battery * 100) + "%" + (SysStats.charging ? " ⚡" : ""), hot: SysStats.discharging && SysStats.battery < 0.15 }
    ]
    alert: temp >= 95

    implicitWidth: big ? 580 : 270
    implicitHeight: big ? 340 : 150

    // ── compact ──
    Item {
        visible: !w.big
        width: 270; height: 150
        Graph {
            width: 270; height: 34
            values: SysStats.cpuHistory
            maxValue: 1
        }
        Column {
            y: 44; width: 270
            spacing: 7
            Repeater {
                model: w.rows
                delegate: Item {
                    required property var modelData
                    width: 270; height: 18
                    Text { text: modelData.k; color: Theme.dim; font.family: w.mono; font.pixelSize: 11; font.letterSpacing: 2; anchors.verticalCenter: parent.verticalCenter }
                    Rectangle {
                        x: 52; width: 140; height: 4; anchors.verticalCenter: parent.verticalCenter; color: Theme.p(0.12)
                        Rectangle { height: parent.height; width: parent.width * Math.max(0, Math.min(1, modelData.v)); color: modelData.hot ? Theme.secondary : Theme.primary
                            Behavior on width { enabled: w.live; NumberAnimation { duration: 500; easing.type: Easing.OutCubic } } }
                    }
                    Text { anchors.right: parent.right; text: modelData.t; color: modelData.hot ? Theme.secondary : Theme.text; font.family: w.mono; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                }
            }
        }
    }

    // ── dashboard (large / huge) ──
    Item {
        id: dash
        visible: w.big
        width: 580; height: 340
        readonly property var gauges: [
            { k: "CPU", v: SysStats.cpu, t: Math.round(SysStats.cpu * 100) + "%" },
            { k: "GPU", v: SysStats.gpu, t: SysStats.gpuAvailable ? Math.round(SysStats.gpu * 100) + "%" : "—" },
            { k: "RAM", v: SysStats.ram, t: Math.round(SysStats.ram * 100) + "%" },
            { k: "TEMP", v: w.temp < 0 ? 0 : Math.min(1, w.temp / 100), t: w.temp < 0 ? "—" : Math.round(w.temp) + "°", hot: w.temp >= 85 }
        ]
        Row {
            spacing: 36
            x: 6
            Repeater {
                model: dash.gauges
                delegate: Item {
                    required property var modelData
                    width: 112; height: 126
                    Ring {
                        anchors.horizontalCenter: parent.horizontalCenter
                        radius: 48; thickness: 5; value: Math.max(0.001, modelData.v); animated: w.live
                        color: modelData.hot ? Theme.secondary : Theme.primary
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter; y: 36
                        text: modelData.t; color: modelData.hot ? Theme.secondary : Theme.text
                        font.family: w.mono; font.pixelSize: 22
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter; y: 112
                        text: modelData.k; color: Theme.dim; font.family: w.mono; font.pixelSize: 11; font.letterSpacing: 3
                    }
                }
            }
        }
        Column {
            y: 140; width: 580; spacing: 10
            Repeater {
                model: [
                    { k: "CPU", vals: SysStats.cpuHistory, max: 1, t: Math.round(SysStats.cpu * 100) + "%", c: Theme.primary },
                    { k: "GPU", vals: SysStats.gpuHistory, max: 1, t: SysStats.gpuAvailable ? Math.round(SysStats.gpu * 100) + "% · " + Math.round(SysStats.gpuMhz) + " MHz" : "—", c: Theme.primary },
                    { k: "NET ↓", vals: SysStats.rxHistory, max: 0, t: SysStats.fmtRate(SysStats.rxRate) + "  ↑ " + SysStats.fmtRate(SysStats.txRate), c: Theme.secondary }
                ]
                delegate: Item {
                    required property var modelData
                    width: 580; height: 40
                    Text { y: 2; text: modelData.k; color: Theme.dim; font.family: w.mono; font.pixelSize: 11; font.letterSpacing: 2 }
                    Text { anchors.right: parent.right; y: 2; text: modelData.t; color: Theme.text; font.family: w.mono; font.pixelSize: 11 }
                    Graph {
                        y: 16; width: 580; height: 24
                        values: modelData.vals; maxValue: modelData.max
                        lineColor: modelData.c; fillColor: modelData.c === Theme.secondary ? Theme.sc(0.12) : Theme.pc(0.12)
                    }
                }
            }
        }
        Row {
            y: 314; spacing: 28
            Repeater {
                model: [
                    "BAT " + Math.round(SysStats.battery * 100) + "%" + (SysStats.charging ? " ⚡" : SysStats.discharging ? " ▼" : ""),
                    "RAM " + SysStats.ramUsedGb.toFixed(1) + " / " + SysStats.ramTotalGb.toFixed(0) + " GB",
                    "DISK " + Math.round(SysStats.diskUsedGb) + " / " + Math.round(SysStats.diskTotalGb) + " GB",
                    "UP " + SysStats.fmtUptime(SysStats.uptimeS)
                ]
                delegate: Text {
                    required property string modelData
                    text: modelData; color: Theme.textSoft; font.family: w.mono; font.pixelSize: 11; font.letterSpacing: 1
                }
            }
        }
    }
}
