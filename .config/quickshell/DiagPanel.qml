// Diagnostics wall for STATS screens (Roles.shows; the middle monitor by default): live graphs +
// system readouts. Sits behind your windows, like the reactor. In combat mode it switches to the
// COMBAT TELEMETRY layout (CombatTelemetry.qml) on one STATS screen without the game, or on a
// CLOCK screen while combat lasts if none is free (Perf.telemetryScreen).
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: diag
    required property var modelData
    screen: modelData
    readonly property bool telemetry: Perf.telemetryScreen === modelData.name
    visible: (telemetry || Roles.shows(modelData) === "stats") && Theme.cfg.showDiag
             && !Perf.hidden(modelData, telemetry ? "telemetry" : "diag")

    WlrLayershell.layer: WlrLayer.Bottom
    WlrLayershell.namespace: "stark-diag"
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; right: true }
    margins { top: 70; right: 60 }
    implicitWidth: 600
    implicitHeight: telemetry ? combat.implicitHeight : col.implicitHeight
    color: "transparent"

    // Telemetry beside windows: reserve its strip so windows (Discord…) tile to the left of it.
    // A separate 1 px surface on the bar's layer: made after the bar, so the bar keeps its width
    // (a reserved zone on this Bottom-layer window squeezed the bar too). Clicks pass through.
    PanelWindow {
        screen: diag.modelData
        visible: diag.visible && diag.telemetry && Perf.telemetryBeside
        WlrLayershell.layer: WlrLayer.Top
        WlrLayershell.namespace: "stark-telemetry-zone"
        anchors { top: true; right: true; bottom: true }
        exclusiveZone: diag.implicitWidth + 60 + 30     // panel + its right margin + a gap
        implicitWidth: 1
        color: "transparent"
        mask: Region {}
    }

    // Combat mode: SysStats speeds back up to 2.5 s while a wall is on screen
    onVisibleChanged: SysStats.setDiag(modelData.name, visible)
    Component.onCompleted: SysStats.setDiag(modelData.name, visible)
    Component.onDestruction: SysStats.setDiag(modelData.name, false)

    DesktopMenuArea { screen: diag.modelData }
    readonly property color cyan: Theme.primary
    readonly property color amber: Theme.secondary
    readonly property color dim: Theme.dim
    readonly property string mono: Style.mono

    Loader {
        id: combat
        width: parent.width
        active: diag.telemetry
        sourceComponent: CombatTelemetry { width: diag.width; screenName: diag.modelData.name }
    }

    Column {
        id: col
        visible: !diag.telemetry
        width: parent.width
        spacing: 18

        Text {
            text: "DIAGNOSTICS // " + diag.modelData.name
            color: diag.cyan
            font.family: diag.mono; font.pixelSize: 13; font.letterSpacing: 4
        }

        // CPU + GPU graph
        HudFrame {
            fill: 0.55   // ambient wall panel: keeps its see-through look
            width: parent.width; height: 190
            title: "PROCESSOR LOAD"
            detail: "CPU " + Math.round(SysStats.cpu * 100) + "%   GPU " + (SysStats.gpuAvailable ? Math.round(SysStats.gpu * 100) + "%" : "--")
            Graph { anchors.fill: parent; values: SysStats.cpuHistory }
            Graph {
                anchors.fill: parent
                values: SysStats.gpuHistory
                lineColor: Theme.secondary
                fillColor: Theme.sc(0.08)
            }
        }

        // Network graph
        HudFrame {
            fill: 0.55   // ambient wall panel: keeps its see-through look
            width: parent.width; height: 190
            title: "NETWORK"
            detail: "↓ " + SysStats.fmtRate(SysStats.rxRate) + "   ↑ " + SysStats.fmtRate(SysStats.txRate)
            Graph { anchors.fill: parent; values: SysStats.rxHistory; maxValue: 0 }
            Graph {
                anchors.fill: parent
                values: SysStats.txHistory
                maxValue: 0
                lineColor: Theme.secondary
                fillColor: Theme.sc(0.08)
            }
        }

        // Readouts
        Row {
            width: parent.width
            spacing: 18

            Repeater {
                model: [
                    { label: "MEMORY", value: SysStats.ramUsedGb.toFixed(1) + " / " + SysStats.ramTotalGb.toFixed(0) + " GB", frac: SysStats.ram },
                    { label: "STORAGE", value: Math.round(SysStats.diskUsedGb) + " / " + Math.round(SysStats.diskTotalGb) + " GB", frac: SysStats.diskTotalGb > 0 ? SysStats.diskUsedGb / SysStats.diskTotalGb : 0 },
                    { label: "WI-FI", value: Math.round(SysStats.wifi * 100) + "%", frac: SysStats.wifi }
                ]
                delegate: HudFrame {
                    fill: 0.55   // ambient wall panel: keeps its see-through look
                    required property var modelData
                    width: (col.width - 36) / 3; height: 112
                    title: modelData.label
                    Column {
                        width: parent.width
                        spacing: 10
                        Text {
                            text: modelData.value
                            color: Theme.text
                            font.family: diag.mono; font.pixelSize: 17
                        }
                        Rectangle {
                            width: parent.width; height: 4
                            color: Theme.p(0.12)
                            Rectangle {
                                width: parent.width * Math.max(0, Math.min(1, modelData.frac)); height: parent.height
                                color: diag.cyan
                                Behavior on width { enabled: !Perf.lite; NumberAnimation { duration: 600 } }
                            }
                        }
                    }
                }
            }
        }

        HudFrame {
            fill: 0.55   // ambient wall panel: keeps its see-through look
            width: parent.width; height: 74
            title: "UPTIME"
            detail: Quickshell.env("USER") + "@" + "stark"
            Text {
                text: SysStats.fmtUptime(SysStats.uptimeS)
                color: Theme.text
                font.family: diag.mono; font.pixelSize: 17
            }
        }
    }
}
