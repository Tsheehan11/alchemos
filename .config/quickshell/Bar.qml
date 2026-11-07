// Thin hologram bar across the top of each screen.
import QtQuick
import Quickshell
import Quickshell.Hyprland
import "Hypr.js" as Hypr

PanelWindow {
    id: bar
    required property var modelData
    screen: modelData

    readonly property bool isMain: Roles.role(modelData) === "main"
    // This screen's workspaces: its default set + any others currently on it
    readonly property var wsList: {
        const base = Roles.baseWorkspaces(modelData);
        const here = Hyprland.workspaces.values
            .filter(w => w.id > 0 && w.id <= 9 && w.monitor && w.monitor.name === modelData.name)
            .map(w => w.id);
        return Array.from(new Set(base.concat(here))).sort((a, b) => a - b);
    }

    readonly property color cyan: Theme.primary
    readonly property color dim: Theme.dim

    anchors { top: true; left: true; right: true }
    implicitHeight: 34
    color: "transparent"

    // Minute ticks in combat mode instead of a redraw every second
    SystemClock { id: clock; precision: GameMode.quiet ? SystemClock.Minutes : SystemClock.Seconds }

    Rectangle {
        visible: !Style.engraved
        anchors.fill: parent
        color: Theme.d(0.85)
        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width; height: 1
            color: Theme.p(0.35)
        }
    }
    // engraved: a stone strip with grain and an engraved double line along its foot
    Item {
        id: strip
        visible: Style.engraved
        anchors.fill: parent
        readonly property color stone: Theme.mix(Theme.bg, Theme.primary, 0.05)
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.rgba(strip.stone.r, strip.stone.g, strip.stone.b, 0.9) }
                GradientStop { position: 1; color: Theme.back(0.9) }
            }
        }
        Image { anchors.fill: parent; source: "assets/grain.png"; fillMode: Image.Tile; opacity: Style.grainNow; smooth: false }
        Rectangle { anchors.bottom: parent.bottom; anchors.bottomMargin: 3; width: parent.width; height: 1; color: Theme.p(0.18) }
        Rectangle { anchors.bottom: parent.bottom; anchors.bottomMargin: 1; width: parent.width; height: 1; color: Qt.rgba(0, 0, 0, 0.6) }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.p(0.5) }
    }

    // Left: name + workspace dots
    Row {
        anchors.left: parent.left
        anchors.leftMargin: 18
        anchors.verticalCenter: parent.verticalCenter
        spacing: 18

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: bar.isMain ? Skin.text.os : bar.modelData.name
            color: bar.isMain ? bar.cyan : bar.dim
            font.family: bar.isMain ? Style.fonts.display : Style.fonts.label
            font.pixelSize: bar.isMain && Style.display !== Style.mono ? 15 : 13
            font.bold: bar.isMain
            font.letterSpacing: 2
        }

        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Repeater {
                model: bar.wsList
                delegate: Rectangle {
                    required property var modelData
                    readonly property int ws: modelData
                    readonly property bool active: Hyprland.focusedWorkspace?.id === ws

                    width: 22; height: 22; radius: 11
                    color: active ? Theme.p(0.25) : "transparent"
                    border.color: active ? bar.cyan : Theme.p(0.6)
                    border.width: 1
                    Rectangle {      // engraved: a second, inner ring (a little seal)
                        visible: Style.engraved
                        anchors.fill: parent; anchors.margins: 3
                        radius: width / 2
                        color: "transparent"
                        border.color: parent.active ? Theme.p(0.5) : Theme.p(0.2)
                    }

                    Text {
                        anchors.centerIn: parent
                        text: parent.ws
                        color: parent.active ? Theme.text : Theme.textSoft
                        font.family: Style.fonts.body
                        font.pixelSize: 11
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: Hyprland.dispatch(Hypr.workspace(parent.ws))
                    }
                }
            }
        }
    }

    // Center: clock
    NumText {
        anchors.centerIn: parent
        text: Qt.formatDateTime(clock.date, GameMode.quiet ? (Theme.cfg.clock24 ? "hh:mm" : "h:mm AP")
                                                          : (Theme.cfg.clock24 ? "hh:mm:ss" : "h:mm:ss AP"))
        color: Theme.textSoft
        font.family: Style.fonts.numeric
        font.pixelSize: 13
        font.letterSpacing: 2
    }

    // Right: stats — click to open the control center
    Rectangle {
        id: statsBtn
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        width: stats.implicitWidth + 24
        height: 26
        color: statsMa.containsMouse || LauncherState.controlOpen ? Theme.p(0.14) : "transparent"
        border.color: statsMa.containsMouse || LauncherState.controlOpen ? Theme.p(0.5) : "transparent"
        border.width: 1

        Row {
            id: stats
            anchors.centerIn: parent
            spacing: 16
            Text {
                visible: bar.isMain
                // listening / starting / off glyphs and the name of the persona answering now (the skin's: ☉ ORRIN,
                // ☽ SELENE; legacy ◉ ◌ ○ JARVIS, ◈ ◇ FRIDAY), in its accent; then ON / OFF / ON (LAPTOP, …)
                text: (JarvisState.online ? JarvisState.glyph : JarvisState.toggleOn ? JarvisState.glyphStarting : JarvisState.glyphIdle) + " " + JarvisState.name + " " + JarvisState.stateLabel.toUpperCase()
                color: JarvisState.online ? (JarvisState.laptopMode ? Theme.secondary : JarvisState.accent) : Theme.faint
                font.family: Style.fonts.body; font.pixelSize: 12; font.letterSpacing: 1
            }
            Text { text: "CPU " + Math.round(SysStats.cpu * 100) + "%"; color: bar.dim; font.family: Style.fonts.body; font.pixelSize: 12; font.letterSpacing: 1 }
            Text { text: "GPU " + (SysStats.gpuAvailable ? Math.round(SysStats.gpu * 100) + "%" : "--"); color: bar.dim; font.family: Style.fonts.body; font.pixelSize: 12; font.letterSpacing: 1 }
            Text { text: "RAM " + Math.round(SysStats.ram * 100) + "%"; color: bar.dim; font.family: Style.fonts.body; font.pixelSize: 12; font.letterSpacing: 1 }
            Text { text: "BAT " + Math.round(SysStats.battery * 100) + "%"; color: SysStats.charging ? "#7cf5c1" : bar.dim; font.family: Style.fonts.body; font.pixelSize: 12; font.letterSpacing: 1 }
            Text {
                visible: VPN.connected || VPN.busy || VPN.blocked
                text: String.fromCodePoint(0xF0582) + " " + (VPN.blocked ? "VPN DOWN · BLOCKED" : VPN.busy ? "VPN…" : (VPN.current.countryCode || "VPN"))
                color: VPN.blocked ? "#ff5f5f" : VPN.busy ? Theme.secondary : bar.cyan
                font.family: Style.fonts.label; font.pixelSize: 12; font.letterSpacing: 2
            }
            // Hyprland 0.57 (the unplug-crash fix) out or installed: HyprFix.qml
            Text { visible: bar.isMain && HyprFix.pending; text: HyprFix.label; color: Theme.secondary; font.family: Style.fonts.label; font.pixelSize: 12; font.letterSpacing: 2 }
            Text { visible: PowerMode.saver; text: "SAVER"; color: Theme.secondary; font.family: Style.fonts.label; font.pixelSize: 12; font.letterSpacing: 2 }
            Text { visible: Peek.active; text: "PEEK"; color: Theme.secondary; font.family: Style.fonts.label; font.pixelSize: 12; font.letterSpacing: 2 }
            Text {
                visible: GameMode.active
                text: String.fromCodePoint(0xF0170) + (GameMode.batteryWarn ? " COMBAT · BATTERY" : " COMBAT")
                color: GameMode.batteryWarn ? "#ff5f5f" : Theme.secondary
                font.family: Style.fonts.label; font.pixelSize: 12; font.bold: true; font.letterSpacing: 2
            }
            // the skin's mark: ALCHEMOS the sign of the metal in use (☉ for a custom preset), legacy ◈
            Text { text: Skin.text.mark || Skin.glyphFor(Theme.cfg.preset) || "☉"; color: bar.cyan; font.family: Style.fonts.glyph; font.pixelSize: 13 }
        }

        MouseArea {
            id: statsMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: LauncherState.toggleControl()
        }
    }
}
