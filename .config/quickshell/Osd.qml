// Volume / brightness pop-up: a holographic gauge near the bottom of the
// screen you're on. Click-through; fades out after a moment.
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

PanelWindow {
    id: osd
    required property var modelData
    screen: modelData

    readonly property bool here: Hyprland.focusedMonitor?.name === modelData.name
    visible: here && (OsdState.showing || panel.opacity > 0.01)

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-osd"
    exclusionMode: ExclusionMode.Ignore
    anchors { bottom: true }
    margins { bottom: 90 }
    implicitWidth: 420
    implicitHeight: 96
    color: "transparent"
    mask: Region {}

    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property bool isVol: OsdState.kind === "volume"
    readonly property color accent: isVol && OsdState.muted ? "#ff5f5f" : (isVol ? Theme.primary : Theme.secondary)
    readonly property string icon: isVol
        ? (OsdState.muted || OsdState.value === 0 ? String.fromCodePoint(0xF0581)
           : OsdState.value < 0.34 ? String.fromCodePoint(0xF057F)
           : OsdState.value < 0.67 ? String.fromCodePoint(0xF0580) : String.fromCodePoint(0xF057E))
        : String.fromCodePoint(0xF00E0)
    property real shown: OsdState.value
    Behavior on shown { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }

    Rectangle {
        id: panel
        anchors.fill: parent
        color: Theme.d(0.88)
        border.color: Qt.rgba(osd.accent.r, osd.accent.g, osd.accent.b, 0.55)
        border.width: 1
        opacity: OsdState.showing ? 1 : 0
        scale: OsdState.showing ? 1 : 0.92
        Behavior on opacity { NumberAnimation { duration: OsdState.showing ? 140 : 380; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutBack } }

        // Corner brackets
        Repeater {
            model: 4
            delegate: Item {
                required property int index
                width: 14; height: 14
                x: index % 2 === 0 ? -1 : panel.width - 13
                y: index < 2 ? -1 : panel.height - 13
                Rectangle { width: 14; height: 2; color: osd.accent; y: index < 2 ? 0 : 12 }
                Rectangle { width: 2; height: 14; color: osd.accent; x: index % 2 === 0 ? 0 : 12 }
            }
        }

        // Ring gauge with the icon inside
        Canvas {
            id: ring
            width: 70; height: 70
            anchors.left: parent.left; anchors.leftMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            property real v: osd.shown
            property color c: osd.accent
            onVChanged: requestPaint()
            onCChanged: requestPaint()
            onPaint: {
                const g = getContext("2d");
                g.reset();
                const cx = width / 2, cy = height / 2, r = 29;
                const a0 = Math.PI * 0.75, span = Math.PI * 1.5;
                g.lineWidth = 4; g.lineCap = "round";
                g.strokeStyle = Qt.rgba(c.r, c.g, c.b, 0.16);
                g.beginPath(); g.arc(cx, cy, r, a0, a0 + span); g.stroke();
                g.strokeStyle = c;
                g.beginPath(); g.arc(cx, cy, r, a0, a0 + span * v); g.stroke();
                g.lineWidth = 1;
                g.strokeStyle = Qt.rgba(c.r, c.g, c.b, 0.35);
                g.beginPath(); g.arc(cx, cy, r - 8, 0, Math.PI * 2); g.stroke();
            }
            Text {
                anchors.centerIn: parent
                text: osd.icon
                color: osd.accent
                font.family: osd.mono; font.pixelSize: 22
            }
        }

        Column {
            anchors.left: ring.right; anchors.leftMargin: 16
            anchors.right: parent.right; anchors.rightMargin: 22
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10

            Item {
                width: parent.width; height: 16
                Text {
                    text: osd.isVol ? (OsdState.muted ? "AUDIO // MUTED" : "AUDIO // OUTPUT") : "DISPLAY // BRIGHTNESS"
                    color: Theme.dim; font.family: osd.mono; font.pixelSize: 11; font.letterSpacing: 3
                }
                Text {
                    anchors.right: parent.right
                    text: Math.round(OsdState.value * 100) + "%"
                    color: osd.accent; font.family: osd.mono; font.pixelSize: 15; font.bold: true
                }
            }
            // Segmented bar
            Row {
                id: segs
                spacing: 3
                readonly property int n: 24
                Repeater {
                    model: segs.n
                    delegate: Rectangle {
                        required property int index
                        readonly property bool lit: (index + 0.5) / segs.n <= osd.shown
                        width: (segs.parent.width - (segs.n - 1) * 3) / segs.n
                        height: 10 + (index / segs.n) * 8
                        anchors.bottom: parent.bottom
                        color: lit ? osd.accent : Theme.p(0.12)
                        opacity: lit ? 0.55 + 0.45 * (index / segs.n) : 1
                    }
                }
            }
        }
    }
}
