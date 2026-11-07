// ALCHEMOS carousel stage (Skin.component("carouselStage"), loaded by Overview.qml): a transmutation
// circle laid on the floor in perspective, turning with the ring, and the header in the display face.
// The circle is drawn once (at half size: it's seen nearly edge-on) and only while the overview is open.
// Interface: HoloCarouselStage.qml.
import QtQuick
import Quickshell
import "../.."

Item {
    id: look
    required property var ov
    anchors.fill: parent
    readonly property string symbols: "Noto Sans Symbols"
    readonly property var metals: Skin.glyphs.ring && Skin.glyphs.ring.length ? Skin.glyphs.ring : ["☉", "☽", "♂", "♀", "☿", "♄"]

    Image {
        anchors.fill: parent
        source: Qt.resolvedUrl("../../assets/grain.png"); fillMode: Image.Tile; smooth: false
        opacity: Style.grainNow * 0.6 * look.ov.appear
    }

    // the floor: a transmutation circle in perspective, turning with the ring
    Item {
        x: look.ov.cx - width / 2; y: look.ov.cy + look.ov.ringRy + look.ov.panelW * 0.32 - height / 2
        width: look.ov.ringR * 2.6; height: width
        opacity: 0.7 * look.ov.appear
        transform: Rotation { origin.x: look.ov.ringR * 1.3; origin.y: look.ov.ringR * 1.3; axis { x: 1; y: 0; z: 0 } angle: 76; distanceToPlane: 100000 }
        Item {          // turns with the ring
            anchors.fill: parent
            rotation: -look.ov.pos * look.ov.step
            Loader {
                active: look.ov.visible
                sourceComponent: Canvas {
                    // a half-size texture, scaled up (the floor is seen nearly edge-on)
                    width: Math.ceil(look.ov.ringR * 1.3); height: width
                    scale: 2; transformOrigin: Item.TopLeft
                    property color m: Theme.primary
                    property color e: Theme.secondary
                    onMChanged: requestPaint(); onEChanged: requestPaint(); onWidthChanged: requestPaint()
                    onPaint: {
                        const ctx = getContext("2d"); ctx.reset();
                        const c = width / 2, R = c * 1.25 / 1.3;
                        const ring = (r, a, w) => { ctx.strokeStyle = Theme.pc(a); ctx.lineWidth = w || 1; ctx.beginPath(); ctx.arc(c, c, r, 0, Math.PI * 2); ctx.stroke(); };
                        ring(R, 0.55, 2); ring(R - 7, 0.35); ring(R * 0.62, 0.3, 1.2);
                        ctx.strokeStyle = Theme.pc(0.4); ctx.lineWidth = 1;
                        for (let d = 0; d < 360; d += 2) {
                            const a = d * Math.PI / 180, l = d % 10 ? 3 : 7;
                            ctx.beginPath(); ctx.moveTo(c + Math.cos(a) * (R - 8), c + Math.sin(a) * (R - 8)); ctx.lineTo(c + Math.cos(a) * (R - 8 - l), c + Math.sin(a) * (R - 8 - l)); ctx.stroke();
                        }
                        ctx.strokeStyle = Theme.sc(0.3); ctx.lineWidth = 1.2;
                        for (const o of [0, Math.PI]) {
                            ctx.beginPath();
                            for (let k = 0; k <= 3; k++) {
                                const a = o - Math.PI / 2 + k * Math.PI * 2 / 3, x = c + Math.cos(a) * R * 0.62, y = c + Math.sin(a) * R * 0.62;
                                if (k) ctx.lineTo(x, y); else ctx.moveTo(x, y);
                            }
                            ctx.stroke();
                        }
                        ctx.fillStyle = Theme.pc(0.6); ctx.font = Math.round(R * 0.08) + "px '" + look.symbols + "'"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
                        const sig = look.metals.concat(["🜁", "🜂", "🜃", "🜄"]);
                        for (let k = 0; k < sig.length; k++) {
                            const a = k / sig.length * Math.PI * 2;
                            ctx.save(); ctx.translate(c + Math.cos(a) * (R * 0.8), c + Math.sin(a) * (R * 0.8)); ctx.rotate(a + Math.PI / 2);
                            ctx.fillText(sig[k], 0, 0); ctx.restore();
                        }
                    }
                }
            }
        }
    }

    // header
    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        y: 70; spacing: 8
        opacity: look.ov.appear
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "THE WORKS  ·  " + (Roles.docked ? look.ov.modelData.name : "ALL")
            color: Theme.primary
            font.family: Style.display; font.pixelSize: 15; font.letterSpacing: 6
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: look.ov.focusedHere
            text: "← → TURN   ·   ENTER SELECT   ·   1–9 JUMP   ·   ESC CLOSE"
            color: Theme.dim
            font.family: Style.display; font.pixelSize: 10; font.letterSpacing: 3
        }
    }
}
