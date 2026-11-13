// ALCHEMOS screenshot effect (skin.json components.shotEffect; the contract is in HoloShotEffect.qml).
// Plays on the frozen, already-saved image (`frame`), ~1.15 s:
//   1. solve: the captured region dims a little while a transmutation circle inscribes itself: the rim
//      traces the region's edge clockwise, lighting the four element signs at its corners, and an
//      inscribed circle with its ticks draws with it
//   2. coagula: a front of molten metal sweeps across on the diagonal and "fixes" the image behind it:
//      bright again, a brief metal sheen, a hot edge (molten gold on warm presets, quicksilver on cool)
//   3. the seal: the active preset's sign stamps into an engraved ring at the centre, COAGULATUM · W×H
//      (on the screen holding most of the shot; the others only trace and sweep)
//   4. the frozen image fades back to the live screen
// Battery saver (calm): only the seal, 320 ms, no glow.
import QtQuick
import QtQuick.Shapes
import Quickshell
import "../.."

Item {
    id: eff
    property var box: null
    property real t: 0
    property var last: ({})
    property var frame: null
    property bool calm: false
    property bool main: true
    property int durationMs: 1150
    property int calmMs: 320

    function ease(a, b) { return Math.max(0, Math.min(1, (eff.t - a) / (b - a))); }
    function smooth(a, b) { const x = ease(a, b); return x * x * (3 - 2 * x); }

    // warm presets get molten gold, cool ones quicksilver
    readonly property real hue: Theme.primary.hslHue
    readonly property bool warm: hue < 0 || hue < 0.17 || hue > 0.9
    readonly property color metal: warm ? Theme.mix("#ffc04a", Theme.primary, 0.35) : Theme.mix("#dfe7f2", Theme.primary, 0.25)
    readonly property color hot: Theme.mix(metal, "#ffffff", 0.55)
    readonly property real out: 1 - smooth(0.86, 1)             // everything leaves together
    readonly property real diag: box ? Math.sqrt(box.w * box.w + box.h * box.h) : 0

    Item {
        id: area
        visible: eff.box !== null
        x: eff.box ? eff.box.x : 0; y: eff.box ? eff.box.y : 0
        width: eff.box ? eff.box.w : 0; height: eff.box ? eff.box.h : 0

        // ── the frozen frame: the saved image, exactly where it was ──
        Image {
            anchors.fill: parent
            visible: !eff.calm && !!eff.frame
            source: eff.frame ? eff.frame.source : ""
            sourceClipRect: eff.frame ? eff.frame.clip : Qt.rect(0, 0, 0, 0)
            fillMode: Image.Stretch
            cache: false
            asynchronous: true
            smooth: true
            opacity: eff.out
        }

        // ── coagula: veil ahead of the front, sheen + hot edge at it, clear behind ──
        Item {
            id: coag
            anchors.fill: parent
            clip: true
            visible: !eff.calm && eff.t < 0.86
            readonly property real f: eff.smooth(0.3, 0.76)       // the front's progress
            readonly property real veil: 0.34 * eff.ease(0, 0.18)
            Rectangle {
                width: eff.diag * 2; height: eff.diag * 3
                y: (area.height - height) / 2
                x: -eff.diag * 1.3 + coag.f * (area.width + eff.diag * 0.6)
                rotation: 18
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.40; color: "transparent" }
                    GradientStop { position: 0.47; color: Qt.rgba(eff.metal.r, eff.metal.g, eff.metal.b, 0.16 * Style.glow) }
                    GradientStop { position: 0.497; color: Qt.rgba(eff.hot.r, eff.hot.g, eff.hot.b, 0.85) }
                    GradientStop { position: 0.506; color: Qt.rgba(eff.metal.r, eff.metal.g, eff.metal.b, 0.5) }
                    GradientStop { position: 0.53; color: Qt.rgba(0, 0, 0, coag.veil * 0.7) }
                    GradientStop { position: 0.56; color: Qt.rgba(0, 0, 0, coag.veil) }
                    GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, coag.veil) }
                }
            }
        }

        // ── solve: the circle inscribes itself (rim around the region + inscribed circle) ──
        // GPU items only (no Canvas): a full-monitor canvas repaints on the GUI thread and stalls the effect.
        Item {
            id: rim
            anchors.fill: parent
            visible: !eff.calm
            opacity: eff.out
            readonly property real draw: eff.smooth(0, 0.34)
            readonly property real m: 3
            readonly property real w: width - 2 * m
            readonly property real h: height - 2 * m
            readonly property real per: 2 * (w + h)
            // how far along each leg the trace is (clockwise from the top-left)
            function leg(start, len) { return Math.max(0, Math.min(len, draw * per - start)); }
            readonly property color c: eff.metal
            Repeater {          // a soft wide line under the sharp one: the glow
                model: [3, 1]
                delegate: Item {
                    required property var modelData
                    readonly property real lw: modelData === 3 ? 6 : 2
                    readonly property real a: modelData === 3 ? 0.22 * Style.glow : 0.95
                    anchors.fill: parent
                    Rectangle { x: rim.m - lw / 2 + 1; y: rim.m - lw / 2 + 1; height: lw; width: rim.leg(0, rim.w); color: Qt.rgba(rim.c.r, rim.c.g, rim.c.b, a) }
                    Rectangle { x: rim.m + rim.w - lw / 2 - 1; y: rim.m; width: lw; height: rim.leg(rim.w, rim.h); color: Qt.rgba(rim.c.r, rim.c.g, rim.c.b, a) }
                    Rectangle { readonly property real l: rim.leg(rim.w + rim.h, rim.w)
                                x: rim.m + rim.w - l; y: rim.m + rim.h - lw / 2 - 1; height: lw; width: l; color: Qt.rgba(rim.c.r, rim.c.g, rim.c.b, a) }
                    Rectangle { readonly property real l: rim.leg(2 * rim.w + rim.h, rim.h)
                                x: rim.m - lw / 2 + 1; y: rim.m + rim.h - l; width: lw; height: l; color: Qt.rgba(rim.c.r, rim.c.g, rim.c.b, a) }
                }
            }
            // the inscribed circle (outer clockwise from the top, inner counter-clockwise from the bottom)
            readonly property real r: Math.min(width, height) * 0.42
            Shape {
                anchors.fill: parent
                visible: rim.r > 24
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeColor: Qt.rgba(rim.c.r, rim.c.g, rim.c.b, 0.6); strokeWidth: 1.4; fillColor: "transparent"
                    PathAngleArc { centerX: rim.width / 2; centerY: rim.height / 2; radiusX: rim.r; radiusY: rim.r; startAngle: -90; sweepAngle: 360 * rim.draw }
                }
                ShapePath {
                    strokeColor: Qt.rgba(rim.c.r, rim.c.g, rim.c.b, 0.32); strokeWidth: 1; fillColor: "transparent"
                    PathAngleArc { centerX: rim.width / 2; centerY: rim.height / 2; radiusX: rim.r * 0.93; radiusY: rim.r * 0.93; startAngle: 90; sweepAngle: -360 * rim.draw }
                }
            }
            Repeater {          // six ticks, each as the circle reaches it
                model: rim.r > 24 ? 6 : 0
                delegate: Rectangle {
                    required property int index
                    readonly property real a: -90 + index * 60
                    width: rim.r * 0.13; height: 1.2
                    color: Qt.rgba(rim.c.r, rim.c.g, rim.c.b, 0.45)
                    x: rim.width / 2 + Math.cos(a * Math.PI / 180) * rim.r * 0.995 - width / 2
                    y: rim.height / 2 + Math.sin(a * Math.PI / 180) * rim.r * 0.995
                    rotation: a
                    visible: rim.draw >= index / 6
                }
            }
        }
        // the element signs light as the rim passes each corner
        Repeater {
            model: !eff.calm && area.width > 90 && area.height > 60 ? 4 : 0
            delegate: SigilText {
                required property int index
                readonly property var at: [[0, 0], [1, 0], [1, 1], [0, 1]][index]     // TL TR BR BL: the trace's order
                readonly property real lit: eff.ease(index * 0.085, index * 0.085 + 0.06)
                text: (Style.corners && Style.corners.length === 4) ? Style.corners[[0, 1, 3, 2][index]] : "◆"
                color: eff.metal
                font.pixelSize: 14
                glow: 0.6 * Style.glow * lit
                x: at[0] ? area.width - width - 8 : 8
                y: at[1] ? area.height - height - 6 : 6
                opacity: lit * eff.out
            }
        }

        // ── the seal ──
        Item {
            id: seal
            visible: eff.main && sealIn > 0 && area.width > 60 && area.height > 60
            readonly property real sealIn: eff.calm ? eff.ease(0, 0.3) : eff.ease(0.66, 0.8)
            readonly property real sealOut: eff.calm ? 1 - eff.ease(0.7, 1) : eff.out
            readonly property real size: Math.min(220, Math.min(area.width, area.height) * 0.5)
            width: size; height: size
            anchors.centerIn: parent
            opacity: sealIn * sealOut
            scale: eff.calm ? 1 : 1.35 - 0.35 * (1 - Math.pow(1 - sealIn, 3))     // stamped in
            Rectangle {
                anchors.fill: parent; radius: width / 2
                color: Qt.rgba(Theme.bg.r, Theme.bg.g, Theme.bg.b, 0.82)
                border.width: 2; border.color: eff.metal
            }
            Rectangle {
                anchors.fill: parent; anchors.margins: 7; radius: width / 2
                color: "transparent"
                border.width: 1; border.color: Qt.rgba(eff.metal.r, eff.metal.g, eff.metal.b, 0.5)
            }
            SigilText {
                anchors.centerIn: parent
                anchors.verticalCenterOffset: -seal.size * 0.06
                text: Theme.activeSign || Skin.text.mark || "☉"
                color: eff.metal
                font.pixelSize: seal.size * 0.38
                glow: eff.calm ? 0 : 0.7 * Style.glow
            }
            Text {
                visible: seal.size >= 110
                anchors.horizontalCenter: parent.horizontalCenter
                y: parent.height * 0.7
                text: "COAGULATUM"
                color: Theme.mix(eff.metal, "#ffffff", 0.4)
                font.family: Style.fonts.label; font.pixelSize: 10; font.letterSpacing: 2
            }
        }
        Text {                              // the size, under the seal
            visible: seal.visible && seal.size >= 110
            anchors.horizontalCenter: parent.horizontalCenter
            y: seal.y + seal.height + 8
            text: (eff.last.width || 0) + " × " + (eff.last.height || 0)
            color: Theme.mix(eff.metal, "#ffffff", 0.3)
            font.family: Style.fonts.numeric; font.pixelSize: 13; font.letterSpacing: 1
            opacity: seal.opacity
        }
    }
}
