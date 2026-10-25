// System stats: CPU (with history), RAM, CPU package temperature, battery. Uses SysStats,
// which already slows down in battery saver and combat mode.
import QtQuick
import Quickshell
import Quickshell.Io
import ".."

WidgetBody {
    id: w
    title: "SYSTEM"
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

    implicitWidth: 270
    implicitHeight: 150

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
