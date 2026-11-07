// COMBAT TELEMETRY: DiagPanel's layout while combat mode is on (Telemetry.qml + SysStats).
// Refreshes with the 2.5 s poll; nothing animates.
import QtQuick
import Quickshell

Column {
    id: tel
    property string screenName: ""
    spacing: 18

    readonly property color cyan: Theme.primary
    readonly property color amber: Theme.secondary
    readonly property color warn: "#ff5f5f"
    readonly property real third: (width - 36) / 3

    function ghz(v) { return v > 0 ? v.toFixed(2) + " GHz" : "--"; }
    function hours(h) { const m = Math.round(h * 60); return Math.floor(m / 60) + "h " + String(m % 60).padStart(2, "0") + "m"; }

    Text {
        text: "COMBAT TELEMETRY // " + tel.screenName
        color: tel.amber
        font.family: Style.fonts.display; font.pixelSize: 13; font.letterSpacing: 4
    }

    // Game + session
    HudFrame {
        fill: 0.55
        width: parent.width; height: 92
        title: "ENGAGED"
        detail: GameMode.since > 0 && Telemetry.prevAt > 0 ? "SESSION " + Telemetry.fmtSession(Telemetry.prevAt / 1000 - GameMode.since) : ""
        Column {
            width: parent.width
            spacing: 4
            Text {
                width: parent.width
                text: Telemetry.gameName || (GameMode.manual ? "Manual override" : GameMode.games.length ? GameMode.games[0] : "gamemode")
                color: Theme.text
                font.family: Style.fonts.body; font.pixelSize: 20
                elide: Text.ElideRight
            }
            Text {
                text: (GameMode.games.join(", ") || (GameMode.manual ? "manual" : "gamemode")) + "   ·   " + (Object.keys(Perf.gameScreens).join(" ") || "no game window")
                color: Theme.dim
                font.family: Style.fonts.body; font.pixelSize: 11
            }
        }
    }

    // CPU: total, clocks, package temp, throttling, per-core load
    HudFrame {
        fill: 0.55
        width: parent.width; height: 210
        title: "PROCESSOR // " + Telemetry.cores.length + " THREADS"
        detail: Telemetry.pkgTemp >= 0 ? "PKG " + Math.round(Telemetry.pkgTemp) + "°C" : ""
        Row {
            anchors.fill: parent
            spacing: 18
            Column {
                width: 150
                spacing: 6
                Text { text: Math.round(SysStats.cpu * 100) + "%"; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 34 }
                Text { text: "AVG  " + tel.ghz(Telemetry.clockAvgGhz); color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 12 }
                Text { text: "PEAK " + tel.ghz(Telemetry.clockMaxGhz); color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 12 }
                Item { width: 1; height: 6 }
                Text {
                    text: Telemetry.cpuThrottling ? "▲ THERMAL THROTTLE" : "● NO THROTTLING"
                    color: Telemetry.cpuThrottling ? tel.warn : Theme.dim
                    font.family: Style.fonts.body; font.pixelSize: 11; font.letterSpacing: 1
                }
            }
            // Per-core bars
            Item {
                id: coreBox
                width: parent.width - 168; height: parent.height
                readonly property int n: Math.max(1, Telemetry.cores.length)
                Row {
                    anchors.fill: parent
                    spacing: 3
                    Repeater {
                        model: Telemetry.cores.length
                        delegate: Rectangle {
                            required property int index
                            readonly property real load: Telemetry.cores[index] || 0
                            width: (coreBox.width - (coreBox.n - 1) * 3) / coreBox.n
                            height: coreBox.height
                            color: Theme.p(0.08)
                            Rectangle {
                                anchors.bottom: parent.bottom
                                width: parent.width
                                height: Math.max(1, parent.height * parent.load)
                                color: parent.load > 0.9 ? tel.amber : tel.cyan
                                opacity: 0.85
                            }
                        }
                    }
                }
            }
        }
    }

    // iGPU: busy, frequency, throttle reasons
    HudFrame {
        fill: 0.55
        width: parent.width; height: 170
        title: "iGPU // INTEL ARC"
        detail: Telemetry.gpuThrottling ? "THROTTLED" + (Telemetry.gpuReasons.length ? " · " + Telemetry.gpuReasons.join(" ").toUpperCase() : "") : ""
        Row {
            anchors.fill: parent
            spacing: 18
            Column {
                width: 150
                spacing: 6
                Text { text: SysStats.gpuAvailable ? Math.round(SysStats.gpu * 100) + "%" : "--"; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 34 }
                Text {
                    text: Telemetry.gpuMaxMhz <= 0 ? "-- MHz" : Telemetry.gpuMhz + " / " + Telemetry.gpuMaxMhz + " MHz"
                    color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 12
                }
                Rectangle {
                    width: parent.width; height: 4
                    color: Theme.p(0.12)
                    Rectangle {
                        width: parent.width * (Telemetry.gpuMaxMhz > 0 ? Math.min(1, Telemetry.gpuMhz / Telemetry.gpuMaxMhz) : 0)
                        height: parent.height
                        color: Telemetry.gpuThrottling ? tel.warn : tel.amber
                    }
                }
                // i915 has no temperature sensor for the integrated GPU; it shares the package's
                Text { text: "TEMP: PKG SENSOR"; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11 }
            }
            Graph {
                width: parent.width - 168; height: parent.height
                values: SysStats.gpuHistory
                lineColor: Theme.secondary
                fillColor: Theme.sc(0.08)
            }
        }
    }

    // Memory · cooling · power
    Row {
        width: parent.width
        spacing: 18

        HudFrame {
            fill: 0.55
            width: tel.third; height: 128
            title: "MEMORY"
            Column {
                width: parent.width
                spacing: 8
                Text { text: SysStats.ramUsedGb.toFixed(1) + " / " + SysStats.ramTotalGb.toFixed(0) + " GB"; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 17 }
                Rectangle {
                    width: parent.width; height: 4
                    color: Theme.p(0.12)
                    Rectangle { width: parent.width * Math.max(0, Math.min(1, SysStats.ram)); height: parent.height; color: tel.cyan }
                }
                Text { text: "SHARED WITH iGPU"; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11 }
            }
        }

        HudFrame {
            fill: 0.55
            width: tel.third; height: 128
            title: "COOLING"
            Column {
                width: parent.width
                spacing: 5
                Repeater {
                    model: Telemetry.fans
                    delegate: Text {
                        required property var modelData
                        text: modelData.rpm + " RPM"
                        color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 17
                    }
                }
                Text { visible: Telemetry.fans.length === 0; text: "NO FAN SENSOR"; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 12 }
                Repeater {
                    model: Telemetry.temps.slice(0, 3)
                    delegate: Text {
                        required property var modelData
                        text: modelData.label.toUpperCase() + "  " + Math.round(modelData.c) + "°C"
                        color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11
                    }
                }
            }
        }

        HudFrame {
            fill: 0.55
            width: tel.third; height: 128
            title: "POWER"
            detail: "BAT " + Math.round(SysStats.battery * 100) + "%"
            Column {
                width: parent.width
                spacing: 6
                Text {
                    text: Telemetry.powerW >= 0 ? Telemetry.powerW.toFixed(1) + " W" : "AC POWER"
                    color: SysStats.discharging ? tel.amber : Theme.text
                    font.family: Style.fonts.body; font.pixelSize: 17
                }
                Text {
                    text: Telemetry.batteryHours > 0 ? tel.hours(Telemetry.batteryHours) + " LEFT"
                        : SysStats.charging ? "CHARGING" : SysStats.discharging ? "ON BATTERY" : "DRAW N/A ON AC"
                    color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11
                }
                Rectangle {
                    width: parent.width; height: 4
                    color: Theme.p(0.12)
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(1, SysStats.battery)); height: parent.height
                        color: SysStats.battery < 0.2 && SysStats.discharging ? tel.warn : tel.cyan
                    }
                }
            }
        }
    }

    // Game disk (Windows partition)
    HudFrame {
        visible: Telemetry.disk !== ""
        fill: 0.55
        width: parent.width; height: 150
        title: "GAME DISK // " + Telemetry.disk.toUpperCase()
        detail: "R " + SysStats.fmtRate(Telemetry.diskRead) + "   W " + SysStats.fmtRate(Telemetry.diskWrite)
                + "   ·   " + Math.round(Telemetry.diskUsedGb) + " / " + Math.round(Telemetry.diskTotalGb) + " GB"
        Graph { anchors.fill: parent; values: Telemetry.diskReadHistory; maxValue: 0 }
        Graph {
            anchors.fill: parent
            values: Telemetry.diskWriteHistory
            maxValue: 0
            lineColor: Theme.secondary
            fillColor: Theme.sc(0.08)
        }
    }
}
