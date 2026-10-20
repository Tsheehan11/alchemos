// Blast doors that close over every screen when locking / shutting down and
// slide open onto the desktop after unlocking. Driven by LockState.
// Always click-through, so it can never trap you.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: dw
    required property var modelData
    screen: modelData

    visible: LockState.doors !== "open"

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-doors"
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    mask: Region {}
    color: "transparent"

    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property bool isMain: Roles.role(modelData) === "main"
    readonly property real halfH: height / 2
    readonly property real doorP: Math.min(1.05, LockState.doorPos)

    // One door panel (top or bottom)
    component Door: Rectangle {
        id: door
        property bool upper: true
        color: Theme.bg
        clip: true

        // faint grid
        Canvas {
            anchors.fill: parent
            property color tint: Theme.primary
            onTintChanged: requestPaint()
            onWidthChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                ctx.strokeStyle = Theme.pc(0.05); ctx.lineWidth = 1;
                ctx.beginPath();
                for (let x = 0.5; x < width; x += 40) { ctx.moveTo(x, 0); ctx.lineTo(x, height); }
                for (let y = 0.5; y < height; y += 40) { ctx.moveTo(0, y); ctx.lineTo(width, y); }
                ctx.stroke();
                // hazard chevrons along the meeting edge
                const ey = door.upper ? height - 34 : 34;
                ctx.strokeStyle = Theme.sc(0.35); ctx.lineWidth = 3;
                ctx.beginPath();
                for (let x = -40; x < width + 40; x += 46) {
                    ctx.moveTo(x, ey - 10); ctx.lineTo(x + 18, ey); ctx.lineTo(x, ey + 10);
                }
                ctx.stroke();
            }
        }
        // glowing edge where the doors meet
        Rectangle {
            width: parent.width; height: 26
            y: door.upper ? parent.height - height : 0
            gradient: Gradient {
                GradientStop { position: 0.0; color: door.upper ? Theme.p(0.0) : Theme.p(0.55) }
                GradientStop { position: 1.0; color: door.upper ? Theme.p(0.55) : Theme.p(0.0) }
            }
        }
        Rectangle {
            width: parent.width; height: 2
            y: door.upper ? parent.height - 2 : 0
            color: Theme.primary
        }
    }

    // Everything that makes up the closed-doors picture (captured for the lock screen)
    Item {
        id: scene
        anchors.fill: parent
        Door { upper: true;  width: dw.width; height: dw.halfH + 2; y: -dw.halfH + dw.doorP * dw.halfH - 2 }
        Door { upper: false; width: dw.width; height: dw.halfH + 2; y: dw.height - dw.doorP * dw.halfH }

        // Emblem + message across the seam (main screen gets the text)
        Item {
            anchors.centerIn: parent
            width: 420; height: 420
            opacity: Math.max(0, Math.min(1, (LockState.doorPos - 0.85) / 0.15)) * (1 - LockState.crt)

            Ring { anchors.centerIn: parent; radius: 190; thickness: 1; value: 1; dashed: true; dash: [3, 7]; trackColor: "transparent"; rotation: LockState.spin }
            Ring { anchors.centerIn: parent; radius: 165; thickness: 5; value: 0.75; color: Theme.p(0.6); trackColor: Theme.p(0.1); rotation: -LockState.spin * 1.5 }
            Ring { anchors.centerIn: parent; radius: 140; thickness: 2; value: 1; color: Theme.secondary; dashed: true; dash: [10, 6]; trackColor: "transparent"; rotation: LockState.spin * 0.7 }
            Rectangle {
                anchors.centerIn: parent
                width: 230; height: 230; radius: 115
                color: Theme.d(0.95)
                border.color: Theme.p(0.6)
            }
            Column {
                anchors.centerIn: parent
                spacing: 6
                visible: dw.isMain
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: LockState.message.slice(0, Math.ceil(LockState.msgP * LockState.message.length))
                    color: Theme.text
                    font.family: dw.mono; font.pixelSize: LockState.message.length > 11 ? 17 : 22; font.letterSpacing: 4
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: LockState.submessage
                    opacity: Math.max(0, (LockState.msgP - 0.5) * 2)
                    color: Theme.secondary
                    font.family: dw.mono; font.pixelSize: 8; font.letterSpacing: 2
                }
            }
            Text {
                anchors.centerIn: parent
                visible: !dw.isMain
                text: "◈"
                color: Theme.primary
                font.pixelSize: 40
            }
        }
    }

    // On the main screen, save a picture of the shut doors → becomes the lock screen's background,
    // so the lock screen lines up exactly with the doors.
    Connections {
        target: LockState
        enabled: dw.isMain
        function onCaptureRequested(path) {
            scene.grabToImage(function(result) {
                result.saveToFile(path);
                LockState.captureDone();
            });
        }
    }

    // Power-off "CRT collapse": the picture squeezes to a line, then a dot, then black
    Rectangle {
        anchors.fill: parent
        visible: LockState.crt > 0
        color: "black"
        opacity: Math.min(1, LockState.crt * 3)
    }
    Rectangle {
        visible: LockState.crt > 0 && LockState.crt < 1
        anchors.centerIn: parent
        readonly property real c: LockState.crt
        width: c < 0.55 ? dw.width : Math.max(4, dw.width * (1 - (c - 0.55) / 0.35))
        height: c < 0.55 ? Math.max(3, dw.height * (1 - c / 0.55)) : 3
        radius: c > 0.85 ? 2 : 0
        color: Theme.text
        opacity: c > 0.9 ? (1 - c) * 10 : 0.95
    }
}
