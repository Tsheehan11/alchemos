// "COMBAT MODE ENGAGED / DISENGAGED" banner, in the volume pop-up's style,
// on the screen you're on. Click-through; unmaps once faded so it never sits
// over a fullscreen game.
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

PanelWindow {
    id: toast
    required property var modelData
    screen: modelData

    readonly property bool here: Hyprland.focusedMonitor?.name === modelData.name
    visible: here && (GameMode.showing || panel.opacity > 0.01)

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-combat"
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true }
    margins { top: 110 }
    implicitWidth: 520
    implicitHeight: 92
    color: "transparent"
    Binding { target: toast.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }   // out of screenshots (Shot.qml)
    mask: Region {}

    readonly property bool on: GameMode.active
    readonly property color accent: GameMode.batteryWarn ? "#ff5f5f" : (on ? Theme.secondary : Theme.primary)
    readonly property string sub: !on ? "SYSTEMS RESTORED · HUD ONLINE"
        : GameMode.batteryWarn ? "ON BATTERY · BALANCED PROFILE · PLUG IN FOR FULL POWER"
        : [GameMode.owns.indexOf("power") >= 0 ? "PERFORMANCE PROFILE" : "",
           GameMode.owns.indexOf("hypr") >= 0 ? "EFFECTS OFFLINE" : "",
           Theme.cfg.gameHud ? "HUD SILENT" : ""].filter(x => x).join(" · ") || "STANDING BY FOR TARGETS"

    Rectangle {
        Engraving { visible: Style.engraved; fillAlpha: 0.92; corners: []; notch: 12; emberColor: toast.accent }     // engraved skins: the plate (Engraving.qml)
        id: panel
        anchors.fill: parent
        color: Style.engraved ? "transparent" : Theme.d(0.9)
        border.color: Style.engraved ? "transparent" : Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.55)
        border.width: 1
        opacity: GameMode.showing ? 1 : 0
        scale: GameMode.showing ? 1 : 0.92
        Behavior on opacity { NumberAnimation { duration: GameMode.showing ? 140 : 420; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutBack } }

        // Corner brackets
        Repeater {
            model: Style.engraved ? 0 : 4
            delegate: Item {
                required property int index
                width: 14; height: 14
                x: index % 2 === 0 ? -1 : panel.width - 13
                y: index < 2 ? -1 : panel.height - 13
                Rectangle { width: 14; height: 2; color: toast.accent; y: index < 2 ? 0 : 12 }
                Rectangle { width: 2; height: 14; color: toast.accent; x: index % 2 === 0 ? 0 : 12 }
            }
        }

        // Crosshair badge
        Rectangle {
            id: badge
            width: 60; height: 60; radius: 30
            anchors.left: parent.left; anchors.leftMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            color: "transparent"
            border.color: Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.45)
            border.width: 2
            Rectangle {
                anchors.centerIn: parent
                width: 46; height: 46; radius: 23
                color: Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, toast.on ? 0.16 : 0.06)
            }
            Text {
                anchors.centerIn: parent
                text: String.fromCodePoint(toast.on ? 0xF0170 : 0xF0297)   // crosshairs / gamepad
                color: toast.accent
                font.family: Style.fonts.body; font.pixelSize: 26
            }
        }

        Column {
            anchors.left: badge.right; anchors.leftMargin: 18
            anchors.right: parent.right; anchors.rightMargin: 20
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            Text {
                text: toast.on ? "COMBAT MODE ENGAGED" : "COMBAT MODE DISENGAGED"
                color: toast.on ? Theme.text : Theme.textSoft
                font.family: Style.fonts.label; font.pixelSize: 19; font.bold: true; font.letterSpacing: 3
            }
            Text {
                width: parent.width; elide: Text.ElideRight
                text: toast.sub
                color: toast.accent
                font.family: Style.fonts.label; font.pixelSize: 11; font.letterSpacing: 2
            }
            // Status bar
            Row {
                spacing: 3
                Repeater {
                    model: 28
                    delegate: Rectangle {
                        required property int index
                        width: 9; height: 3
                        color: toast.accent
                        opacity: toast.on ? 0.25 + 0.75 * (index / 28) : 0.75 - 0.6 * (index / 28)
                    }
                }
            }
        }
    }
}
