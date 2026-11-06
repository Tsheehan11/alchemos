// Projected-hologram frame for desktop widgets (WidgetCard) and anything else that wants the look:
// no solid card, just light. A translucent fill that fades out towards the edges, faint scanlines,
// thin glowing corner brackets, partial edge strokes with a travelling shimmer, a small reticle
// whose ticks turn slowly, a scan sweep and an occasional micro-flicker.
//
//   t        effects clock (seconds) from Perf, via the surface; nothing here runs its own timer
//   still    static: no shimmer, idle motion, sweep or flicker (battery saver, effects paused,
//            hidden / covered screens: Perf.live is false there)
//   boot     0 → 1 draws the frame on (brackets grow from the corners, strokes draw along the
//            edges, one sweep passes over it); 1 → 0 takes it away again (dismiss)
//   accent   stroke colour (WidgetCard passes the secondary colour when a widget wants attention)
//   strong   brighter strokes (hover / drag)
//   lift     0 → 1 while a widget is held (drag / resize): a wider glow around the brackets
//   pulse    0 → 1 once when it's dropped: a scan line passes over it and the brackets flare
//
// The fill is light, not glass: a faint accent tint plus a very light shade, both fading out
// to the edges, so the window or wallpaper behind shows through (tinted) instead of a dark
// slab over bright windows. Text legibility comes from the card's halo (WidgetCard).
import QtQuick
import QtQuick.Shapes
import QtQuick.Effects

Item {
    id: f
    property real t: 0
    property bool still: true
    property real boot: 1
    property color accent: Theme.primary
    property bool strong: false
    property bool reticle: true
    property real lift: 0
    property real pulse: 0
    property real shade: 0.16              // background-colour shade at the centre (edges fade to nothing)
    property real tint: 0.10               // accent tint at the centre

    readonly property real arm: 14 * Math.min(1, f.boot * 1.6)                      // bracket arm
    readonly property real draw: Math.max(0, Math.min(1, (f.boot - 0.25) / 0.75))  // edge strokes, after the brackets
    readonly property real flare: f.pulse > 0 && f.pulse < 1 ? Math.sin(Math.PI * f.pulse) : 0
    readonly property real glowA: (f.strong ? 0.34 : 0.2) + 0.25 * f.flare
    readonly property real lineA: f.strong || f.flare > 0 ? 1.0 : 0.85
    function a(c, al) { return Qt.rgba(c.r, c.g, c.b, al); }

    // micro-flicker: ~1.5 % of 1/12 s slots dip briefly (deterministic hash of the slot)
    readonly property real flick: {
        if (f.still) return 1;
        const slot = Math.floor(f.t * 12);
        const h = Math.abs(Math.sin(slot * 12.9898 + 78.233) * 43758.5453) % 1;
        return h < 0.015 ? 0.78 + h * 6 : 1;
    }
    opacity: f.flick

    // engraved skins (Style.frame "engraved"): a stone plate with an engraved double line instead of light;
    // the same inputs drive it (boot fades it in, strong / lift / pulse raise its ember)
    Engraving {
        visible: Style.engraved
        opacity: Math.min(1, f.boot * 1.4)
        fillAlpha: 0.78
        notch: 14
        corners: []
        ember: (0.08 + (f.strong ? 0.14 : 0) + 0.25 * f.flare + 0.2 * f.lift) * Style.glow
    }

    // ── the hologram (base look) ──
    Item {
    anchors.fill: parent
    visible: !Style.engraved
    // ── fill: elliptical fade (a circle in a square, squashed to the card) + a faint primary tint ──
    Item {
        id: fillBox
        width: f.width; height: f.width
        opacity: Math.min(1, f.boot * 1.4)
        transform: Scale { yScale: f.height / Math.max(1, f.width) }
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: "transparent"
                fillGradient: RadialGradient {
                    centerX: fillBox.width / 2; centerY: fillBox.height / 2; centerRadius: fillBox.width * 0.6
                    focalX: centerX; focalY: centerY
                    GradientStop { position: 0.0; color: Theme.back(f.shade) }
                    GradientStop { position: 0.6; color: Theme.back(f.shade * 0.8) }
                    GradientStop { position: 0.85; color: Theme.back(f.shade * 0.3) }
                    GradientStop { position: 1.0; color: Theme.back(0) }
                }
                PathRectangle { x: 0; y: 0; width: fillBox.width; height: fillBox.height }
            }
            ShapePath {
                strokeColor: "transparent"
                fillGradient: RadialGradient {
                    centerX: fillBox.width / 2; centerY: fillBox.height / 2; centerRadius: fillBox.width * 0.6
                    focalX: centerX; focalY: centerY
                    GradientStop { position: 0.0; color: f.a(f.accent, f.tint * (1 + 0.6 * f.lift)) }
                    GradientStop { position: 0.7; color: f.a(f.accent, f.tint * 0.7 * (1 + 0.6 * f.lift)) }
                    GradientStop { position: 1.0; color: f.a(f.accent, 0) }
                }
                PathRectangle { x: 0; y: 0; width: fillBox.width; height: fillBox.height }
            }
        }
    }

    // ── scanlines: light lines in the accent colour (dark ones read as a grey slab over bright
    //    windows), faded out towards the edges with the same ellipse as the fill (so no box edge) ──
    Image {
        id: lines
        anchors.fill: parent
        fillMode: Image.Tile
        smooth: false
        visible: false
        layer.enabled: true
        source: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAADCAYAAABS3WWCAAAAEElEQVR4nGNggIP////nAQAJdANsWx7rxQAAAABJRU5ErkJggg=="
    }
    Image {         // alpha mask: solid in the middle, fading to nothing at the edges (stretched to the card)
        id: fade
        anchors.fill: parent
        visible: false
        source: "holo-fade.png"
        smooth: true
    }
    MultiEffect {
        anchors.fill: parent
        source: lines
        maskEnabled: true
        maskSource: fade
        colorization: 1
        colorizationColor: f.accent
        opacity: 0.22 * Math.min(1, f.boot * 1.4)
    }

    // ── sweep: one pass while booting, then a slow faint one while effects run ──
    Item {
        anchors.fill: parent
        clip: true
        Rectangle {
            id: sweep
            readonly property bool pulsing: f.pulse > 0 && f.pulse < 1
            readonly property bool booting: f.boot < 1 || pulsing
            readonly property real k: f.boot < 1 ? f.boot : f.pulse
            visible: booting || !f.still
            width: parent.width; height: booting ? 3 : 36
            y: booting ? k * (parent.height + 6) - 3 : ((f.t * 0.12) % 1) * (parent.height + 72) - 36
            opacity: booting ? 0.9 : 1
            gradient: Gradient {
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.5; color: f.a(f.accent, sweep.booting ? 0.6 : 0.06) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }
    }

    // ── strokes: glow underneath, the line on top ──
    component Strokes: Shape {
        id: st
        property real w: 1.4
        property color c: f.accent
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: st.c; strokeWidth: st.w; fillColor: "transparent"
            capStyle: ShapePath.FlatCap; joinStyle: ShapePath.MiterJoin
            // corner brackets (just outside the card)
            PathMove { x: -3; y: -3 + f.arm }        PathLine { x: -3; y: -3 }                  PathLine { x: -3 + f.arm; y: -3 }
            PathMove { x: f.width + 3 - f.arm; y: -3 } PathLine { x: f.width + 3; y: -3 }      PathLine { x: f.width + 3; y: -3 + f.arm }
            PathMove { x: -3; y: f.height + 3 - f.arm } PathLine { x: -3; y: f.height + 3 }    PathLine { x: -3 + f.arm; y: f.height + 3 }
            PathMove { x: f.width + 3 - f.arm; y: f.height + 3 } PathLine { x: f.width + 3; y: f.height + 3 } PathLine { x: f.width + 3; y: f.height + 3 - f.arm }
        }
    }
    component Edges: Shape {
        id: ed
        property real w: 1
        property color c: f.accent
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: ed.c; strokeWidth: ed.w; fillColor: "transparent"; capStyle: ShapePath.FlatCap
            // top: from the left bracket to ~40 %, then a notch down
            PathMove { x: 18; y: -3 }
            PathLine { x: 18 + (f.width * 0.42 - 18) * f.draw; y: -3 }
            PathLine { x: 18 + (f.width * 0.42 - 18) * f.draw + 5 * f.draw; y: 2 * f.draw - 3 + 3 * f.draw }
            // bottom: from ~58 % to the right bracket, drawn from the right
            PathMove { x: f.width - 18; y: f.height + 3 }
            PathLine { x: f.width - 18 - (f.width * 0.42 - 18) * f.draw; y: f.height + 3 }
            // left: a short rail in the middle
            PathMove { x: -3; y: f.height * (0.5 - 0.22 * f.draw) }
            PathLine { x: -3; y: f.height * (0.5 + 0.22 * f.draw) }
        }
    }
    Strokes { visible: f.lift > 0; w: 12; c: f.a(f.accent, 0.12 * f.lift) }
    Strokes { w: 4; c: f.a(f.accent, f.glowA) }
    Strokes { w: 1.4; c: f.a(f.accent, f.lineA) }
    Edges { w: 3; c: f.a(f.accent, f.glowA * 0.6) }
    Edges { w: 1; c: f.a(f.accent, 0.5) }

    // ── shimmer: a bright glint running along the top stroke, then the bottom one ──
    Rectangle {
        visible: !f.still && f.boot >= 1
        readonly property real k: (f.t * 0.22) % 2.4          // 0..1 top, 1..2 bottom, then a pause
        width: 46; height: 2
        x: k < 1 ? 18 + (f.width * 0.42 - 18) * k - width / 2 : f.width - 18 - (f.width * 0.42 - 18) * (k - 1) - width / 2
        y: k < 1 ? -3.5 : f.height + 2.5
        opacity: k < 2 ? Math.sin(Math.PI * (k % 1)) : 0
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 0.5; color: Qt.lighter(f.accent, 1.6) }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }

    // ── reticle: ticks on a small ring, turning slowly while effects run ──
    Item {
        visible: f.reticle
        x: 9; y: 11
        width: 12; height: 12
        opacity: f.draw
        rotation: f.still ? 0 : f.t * 24
        Repeater {
            model: 6
            delegate: Rectangle {
                required property int index
                x: 5.25; y: 0; width: 1.5; height: index % 3 === 0 ? 3.5 : 2.2
                color: f.accent
                antialiasing: true
                transform: Rotation { origin.x: 0.75; origin.y: 6; angle: index * 60 }
            }
        }
        Rectangle { anchors.centerIn: parent; width: 3; height: 3; radius: 1.5; color: f.accent; opacity: 0.8 }
    }
    }
}
