// The base carousel stage: the hologram projector floor (ellipse rings turning with the ring) and the
// header.
//
// Carousel looks (Overview.qml, Super+Tab) come in two slots: a stage (Skin.component("carouselStage"):
// floor and header, under the panels) and a panel (Skin.component("carouselPanel"): one per workspace,
// inside the panel's placed, turned and scaled box). Overview.qml owns the ring geometry, keys, clicks
// and the glow layer; a look only draws. Both get `ov` (ids, n, pos, step, ringR, ringRy, panelW, cx, cy,
// appear, focusedHere, modelData = the screen, mono); a panel also gets `panel` (modelData = workspace
// id, index, front, current, wins, peeked, mon, k, width, height) and may set glowColor / glowBlur /
// glowOpacity for the front panel's glow. Window previews: CarouselWindows.qml.
import QtQuick
import Quickshell

Item {
    id: look
    required property var ov
    anchors.fill: parent

    // Projector floor: ellipse rings under the carousel
    Item {
        x: ov.cx - width / 2; y: ov.cy + ov.ringRy + ov.panelW * 0.32 - height / 2
        width: ov.ringR * 2.6; height: width
        opacity: 0.55 * ov.appear
        transform: Rotation { origin.x: ov.ringR * 1.3; origin.y: ov.ringR * 1.3; axis { x: 1; y: 0; z: 0 } angle: 78; distanceToPlane: 100000 }
        Ring { anchors.centerIn: parent; radius: ov.ringR * 1.25; thickness: 2; value: 1; trackColor: "transparent" }
        Ring { anchors.centerIn: parent; radius: ov.ringR * 1.15; thickness: 8; value: 1; dashed: true; dash: [0.3, 2]; color: Theme.p(0.4); trackColor: "transparent"; rotation: -ov.pos * ov.step }
        Ring { anchors.centerIn: parent; radius: ov.ringR * 0.9; thickness: 1; value: 1; color: Theme.secondary; dashed: true; dash: [8, 6]; trackColor: "transparent"; rotation: ov.pos * ov.step }
    }

    // Header
    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        y: 70
        spacing: 6
        opacity: ov.appear
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "WORKSPACES // " + (Roles.docked ? ov.modelData.name : "ALL")
            color: Theme.primary
            font.family: Style.display; font.pixelSize: 13; font.letterSpacing: 6
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: ov.focusedHere
            text: "← → TURN   ·   ENTER SELECT   ·   1–9 JUMP   ·   ESC CLOSE"
            color: Theme.dim
            font.family: ov.mono; font.pixelSize: 10; font.letterSpacing: 3
        }
    }
}
