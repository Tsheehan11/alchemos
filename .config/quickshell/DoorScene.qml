// The security-doors picture: two door panels plus the emblem across the seam.
// SecurityDoors drives it live from LockState; LockBgRender draws it shut, offscreen,
// for the lock screen background. Both must stay pixel-identical when shut.
import QtQuick

Item {
    id: scene

    property real doorP: 1               // 0 = open, 1 = shut (may overshoot to 1.05)
    property real emblemOpacity: 1
    property bool isMain: true
    property string message: ""
    property string submessage: ""
    property real msgP: 0
    property real spin: 0

    readonly property real halfH: height / 2
    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property bool painted: upperDoor.painted && lowerDoor.painted

    // One door panel (top or bottom)
    component Door: Rectangle {
        id: door
        property bool upper: true
        property bool painted: false
        color: Theme.bg
        clip: true

        // faint grid
        Canvas {
            anchors.fill: parent
            property color tint: Theme.primary
            property color tint2: Theme.secondary
            onTintChanged: { door.painted = false; requestPaint(); }
            onTint2Changed: { door.painted = false; requestPaint(); }
            onWidthChanged: { door.painted = false; requestPaint(); }
            onHeightChanged: { door.painted = false; requestPaint(); }
            onPainted: door.painted = true
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

    Door { id: upperDoor; upper: true;  width: scene.width; height: scene.halfH + 2; y: -scene.halfH + scene.doorP * scene.halfH - 2 }
    Door { id: lowerDoor; upper: false; width: scene.width; height: scene.halfH + 2; y: scene.height - scene.doorP * scene.halfH }

    // Emblem + message across the seam (main screen gets the text)
    Item {
        anchors.centerIn: parent
        width: 420; height: 420
        opacity: scene.emblemOpacity

        Ring { anchors.centerIn: parent; radius: 190; thickness: 1; value: 1; dashed: true; dash: [3, 7]; trackColor: "transparent"; rotation: scene.spin }
        Ring { anchors.centerIn: parent; radius: 165; thickness: 5; value: 0.75; color: Theme.p(0.6); trackColor: Theme.p(0.1); rotation: -scene.spin * 1.5 }
        Ring { anchors.centerIn: parent; radius: 140; thickness: 2; value: 1; color: Theme.secondary; dashed: true; dash: [10, 6]; trackColor: "transparent"; rotation: scene.spin * 0.7 }
        Rectangle {
            anchors.centerIn: parent
            width: 230; height: 230; radius: 115
            color: Theme.d(0.95)
            border.color: Theme.p(0.6)
        }
        Column {
            anchors.centerIn: parent
            spacing: 6
            visible: scene.isMain
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: scene.message.slice(0, Math.ceil(scene.msgP * scene.message.length))
                color: Theme.text
                font.family: scene.mono; font.pixelSize: scene.message.length > 11 ? 17 : 22; font.letterSpacing: 4
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: scene.submessage
                opacity: Math.max(0, (scene.msgP - 0.5) * 2)
                color: Theme.secondary
                font.family: scene.mono; font.pixelSize: 8; font.letterSpacing: 2
            }
        }
        Text {
            anchors.centerIn: parent
            visible: !scene.isMain
            text: "◈"
            color: Theme.primary
            font.pixelSize: 40
        }
    }
}
