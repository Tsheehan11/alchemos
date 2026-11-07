// ALCHEMOS desktop scene (Skin.component("backdrop"), hosted by GridBackground.qml): an engraved
// astrolabe / transmutation circle turning slowly over a star chart on dark stone, metal veins that
// catch the light in the preset's metal, gold dust and embers drifting up. Activity (the assistant at
// work, CPU load) brightens the rete and the circle at the centre.
//
// The great circle stands to the right, about half off screen, its limb just clear of where the clock's
// dial sits (centred; on CLOCK screens it's there), the same on every screen.
//
// Performance: everything heavy is drawn once into Canvas textures (again only on resize, a preset
// change or a resolution change); motion is rotation / translation / opacity of those textures off the
// shared Perf clock (t), about 100 cheap property updates a tick (≈ 2–4 % of one core at 24 fps). Not live → a still frame (t frozen).
// Texture memory: the ground is one screen-sized texture; ring bands are cut into wedge tiles so their
// empty middles cost nothing. res 0.5 (laptop panel, battery saver) draws every texture at half size.
// About 25 MB at 2560×1440, 5 MB for 1920×1200 at half resolution.
import QtQuick
import "../.."

Item {
    id: sc
    // backdrop interface (HoloBackdrop.qml)
    property var modelData
    property real t: 0
    property bool live: false
    property real res: 1
    property real activity: 0

    // activity, eased on the Perf clock (no animation of its own)
    property real pulse: 0
    onTChanged: pulse += (activity - pulse) * 0.08

    readonly property color metal: Theme.primary
    readonly property color ember: Theme.secondary
    readonly property real rad: Math.min(height * 0.47, width * 0.36)        // the great circle
    // the clock window (HudWindow) is centred on the screen; the skin's clock (AlchemCircle) has a dial
    // of radius 240 k-units
    readonly property real clockR: 240 * (Theme.cfg.reactorScale || 1)
    readonly property real cx: width / 2 + clockR + rad * 0.92
    readonly property real cy: height * 0.56
    readonly property string glyphFont: Style.fonts.signs
    readonly property var metals: Skin.glyphs.ring && Skin.glyphs.ring.length ? Skin.glyphs.ring : ["☉", "☽", "♂", "♀", "☿", "♄"]

    function rng(seed) { let s = seed >>> 0; return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; }; }
    readonly property real ink: 1.35          // engraving strength (alpha multiplier for every stroke)
    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + Math.min(1, a * ink) + ")"; }
    function q(c, a) { return Qt.rgba(c.r, c.g, c.b, a); }
    function lighten(c, k) { return Qt.rgba(c.r + (1 - c.r) * k, c.g + (1 - c.g) * k, c.b + (1 - c.b) * k, 1); }

    // Metal veins: branching polylines across the stone (the same for a given screen size)
    readonly property var veins: {
        if (width <= 0 || height <= 0) return [];
        const r = rng(7 + Math.round(width) * 3 + Math.round(height)), out = [];
        const grow = (x, y, a, len, depth) => {
            const pts = [[x, y]];
            for (let i = 0; i < len; i++) {
                a += (r() - 0.5) * 0.7;
                x += Math.cos(a) * (18 + r() * 26); y += Math.sin(a) * (18 + r() * 26);
                pts.push([x, y]);
                if (depth < 2 && r() < 0.12) grow(x, y, a + (r() < 0.5 ? -1 : 1) * (0.5 + r() * 0.6), Math.floor(len * 0.45), depth + 1);
            }
            out.push({ pts: pts, w: depth === 0 ? 1.4 : depth === 1 ? 0.9 : 0.6 });
        };
        grow(-20, height * 0.78, -0.35, 34, 0);
        grow(width * 0.18, -20, 1.25, 22, 0);
        grow(width + 20, height * 0.22, Math.PI + 0.3, 30, 0);
        grow(width * 0.82, height + 20, -1.9, 18, 0);
        return out;
    }

    // ── Stone, light, star chart, veins: one texture ──
    Canvas {
        id: ground
        width: Math.ceil(sc.width * sc.res); height: Math.ceil(sc.height * sc.res)
        scale: 1 / sc.res; transformOrigin: Item.TopLeft
        property color m: sc.metal
        property color e: sc.ember
        property color b: Theme.bg
        property var v: sc.veins
        property real lx: sc.cx                // the light pools behind the circle's centre
        property real ly: sc.cy
        onMChanged: requestPaint(); onEChanged: requestPaint(); onBChanged: requestPaint(); onVChanged: requestPaint()
        onLxChanged: requestPaint(); onLyChanged: requestPaint()
        onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            if (sc.width <= 0) return;
            ctx.scale(sc.res, sc.res);
            const W = sc.width, H = sc.height, r = sc.rng(1234);
            ctx.fillStyle = Theme.bg; ctx.fillRect(0, 0, W, H);
            // warm light pooled behind the great circle
            let g = ctx.createRadialGradient(sc.cx, sc.cy, 0, sc.cx, sc.cy, sc.rad * 1.5);
            g.addColorStop(0, sc.rgba(sc.metal, 0.10)); g.addColorStop(0.45, sc.rgba(sc.ember, 0.035)); g.addColorStop(1, "rgba(0,0,0,0)");
            ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
            // star chart graticule: curved meridians and parallels of a planisphere, very faint
            ctx.strokeStyle = sc.rgba(sc.metal, 0.05); ctx.lineWidth = 1;
            const px = W * 0.22, py = H * 0.3;
            for (let k = 1; k <= 6; k++) { ctx.beginPath(); ctx.arc(px, py, k * H * 0.17, 0, Math.PI * 2); ctx.stroke(); }
            for (let k = 0; k < 12; k++) {
                const a = k * Math.PI / 6;
                ctx.beginPath(); ctx.moveTo(px, py);
                ctx.quadraticCurveTo(px + Math.cos(a + 0.4) * H * 0.5, py + Math.sin(a + 0.4) * H * 0.5, px + Math.cos(a) * H * 1.1, py + Math.sin(a) * H * 1.1);
                ctx.stroke();
            }
            // stars
            for (let i = 0; i < 260; i++) {
                const x = r() * W, y = r() * H, s = r();
                ctx.fillStyle = sc.rgba(sc.lighten(sc.metal, 0.6), 0.08 + s * s * 0.35);
                ctx.fillRect(x, y, s > 0.93 ? 2 : 1, s > 0.93 ? 2 : 1);
            }
            // constellations: a few stick figures with ringed stars
            const cons = [[0.08, 0.16], [0.30, 0.10], [0.12, 0.62], [0.88, 0.80], [0.93, 0.36], [0.40, 0.86]];
            for (const c of cons) {
                let x = c[0] * W, y = c[1] * H;
                const n = 4 + Math.floor(r() * 4), pts = [];
                for (let i = 0; i < n; i++) { pts.push([x, y]); x += (r() - 0.5) * 140; y += (r() - 0.5) * 100; }
                ctx.strokeStyle = sc.rgba(sc.metal, 0.13); ctx.lineWidth = 0.8;
                ctx.setLineDash([2, 4]);
                ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]); for (const p of pts) ctx.lineTo(p[0], p[1]); ctx.stroke();
                ctx.setLineDash([]);
                for (const p of pts) {
                    ctx.fillStyle = sc.rgba(sc.lighten(sc.metal, 0.5), 0.5); ctx.beginPath(); ctx.arc(p[0], p[1], 1.6, 0, Math.PI * 2); ctx.fill();
                    ctx.strokeStyle = sc.rgba(sc.metal, 0.18); ctx.beginPath(); ctx.arc(p[0], p[1], 4.5, 0, Math.PI * 2); ctx.stroke();
                }
            }
            // metal veins: a dark groove, the metal, a thin highlight on one edge
            for (const v of sc.veins) {
                const path = () => { ctx.beginPath(); ctx.moveTo(v.pts[0][0], v.pts[0][1]); for (const p of v.pts) ctx.lineTo(p[0], p[1]); };
                ctx.lineJoin = "round"; ctx.lineCap = "round";
                path(); ctx.strokeStyle = "rgba(0,0,0,0.5)"; ctx.lineWidth = v.w + 2.5; ctx.stroke();
                path(); ctx.strokeStyle = sc.rgba(sc.metal, 0.20); ctx.lineWidth = v.w; ctx.stroke();
                ctx.save(); ctx.translate(-0.6, -0.6);
                path(); ctx.strokeStyle = sc.rgba(sc.lighten(sc.metal, 0.6), 0.10); ctx.lineWidth = Math.max(0.5, v.w * 0.5); ctx.stroke();
                ctx.restore();
            }
            // vignette
            g = ctx.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, Math.hypot(W, H) * 0.62);
            g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, "rgba(0,0,0,0.55)");
            ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
        }
    }
    Image {
        anchors.fill: parent
        visible: Theme.cfg.showGrid !== false
        source: Qt.resolvedUrl("../../assets/grain.png")
        fillMode: Image.Tile; smooth: false
        opacity: Style.grainNow * 0.8
    }

    // ── Light travelling along the veins: one soft glint sprite, reused ──
    Canvas {
        id: glintSprite
        width: 46; height: 46; visible: false
        property color m: sc.metal
        onMChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d"); ctx.reset();
            const g = ctx.createRadialGradient(23, 23, 0, 23, 23, 23);
            g.addColorStop(0, sc.rgba(sc.lighten(sc.metal, 0.7), 0.9)); g.addColorStop(0.25, sc.rgba(sc.metal, 0.35)); g.addColorStop(1, sc.rgba(sc.metal, 0));
            ctx.fillStyle = g; ctx.fillRect(0, 0, 46, 46);
        }
    }
    Repeater {
        model: sc.veins.length
        delegate: ShaderEffectSource {
            required property int index
            readonly property var pts: sc.veins[index].pts
            readonly property real period: 14 + (index * 5) % 9
            readonly property real u: ((sc.t + index * 3.7) % period) / period * 1.6       // 0..1 travels, then rests
            readonly property real f: Math.min(0.999, u) * (pts.length - 1)
            readonly property int i0: Math.floor(f)
            visible: sc.veins[index].w > 1 && u < 1
            sourceItem: glintSprite; hideSource: false
            width: 46; height: 46
            x: pts[i0][0] + (pts[i0 + 1][0] - pts[i0][0]) * (f - i0) - 23
            y: pts[i0][1] + (pts[i0 + 1][1] - pts[i0][1]) * (f - i0) - 23
            opacity: Math.sin(Math.PI * Math.min(1, u)) * 0.85
        }
    }

    // ── An engraved ring: drawn once, then only rotated about its centre (the Item's origin) ──
    // band > 0: only the annulus from r − band to r holds strokes; it's drawn in wedge tiles, each just
    // big enough for its arc, instead of one texture the size of the whole disc.
    component Engraving: Item {
        id: eng
        property real r: 100
        property real band: 0
        property var draw: null          // (ctx, c, r) → strokes, centre (c, c)
        readonly property int tiles: band > 0 ? 16 : 1
        readonly property real pad: 6
        readonly property real ro: r + pad
        readonly property real ri: Math.max(0, r - band - pad)
        Repeater {
            model: eng.tiles
            delegate: Canvas {
                required property int index
                readonly property real a0: index / eng.tiles * Math.PI * 2
                readonly property real a1: (index + 1) / eng.tiles * Math.PI * 2
                // the tile's box in ring coordinates (centre 0, 0)
                readonly property var box: {
                    if (eng.tiles === 1) return [-eng.ro, -eng.ro, eng.ro * 2, eng.ro * 2];
                    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
                    for (let k = 0; k <= 8; k++) {
                        const a = a0 + (a1 - a0) * k / 8;
                        for (const rr of [eng.ro, eng.ri]) {
                            const x = Math.cos(a) * rr, y = Math.sin(a) * rr;
                            x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
                        }
                    }
                    return [Math.floor(x0) - 1, Math.floor(y0) - 1, Math.ceil(x1 - x0) + 3, Math.ceil(y1 - y0) + 3];
                }
                x: box[0]; y: box[1]
                width: Math.ceil(box[2] * sc.res); height: Math.ceil(box[3] * sc.res)
                scale: 1 / sc.res; transformOrigin: Item.TopLeft
                property color m: sc.metal
                property color e: sc.ember
                property real rr: eng.r
                onMChanged: requestPaint(); onEChanged: requestPaint(); onRrChanged: requestPaint()
                onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
                onPaint: {
                    const ctx = getContext("2d"); ctx.reset();
                    if (!eng.draw || eng.r <= 0) return;
                    ctx.scale(sc.res, sc.res);
                    ctx.translate(-box[0], -box[1]);
                    if (eng.tiles > 1) {         // only this wedge (no seams doubled up)
                        ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, eng.ro + 2, a0, a1); ctx.closePath(); ctx.clip();
                    }
                    eng.draw(ctx, 0, eng.r);
                }
            }
        }
    }
    function circle(ctx, c, r, a, w) { ctx.strokeStyle = rgba(metal, a); ctx.lineWidth = w || 1; ctx.beginPath(); ctx.arc(c, c, r, 0, Math.PI * 2); ctx.stroke(); }
    function glyphRing(ctx, c, r, glyphs, px, a, upright) {
        ctx.fillStyle = rgba(lighten(metal, 0.2), a);
        ctx.font = px + "px '" + glyphFont + "'"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        for (let i = 0; i < glyphs.length; i++) {
            const ang = i / glyphs.length * Math.PI * 2 - Math.PI / 2;
            ctx.save(); ctx.translate(c + Math.cos(ang) * r, c + Math.sin(ang) * r);
            if (!upright) ctx.rotate(ang + Math.PI / 2);
            ctx.fillText(glyphs[i], 0, 0); ctx.restore();
        }
    }
    function poly(ctx, c, r, n, step, rot) {
        ctx.beginPath();
        for (let i = 0; i <= n; i++) {
            const a = rot + (i * step % n) / n * Math.PI * 2;
            const x = c + Math.cos(a) * r, y = c + Math.sin(a) * r;
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }

    readonly property var zodiac: ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"]
    readonly property var script: ["🜀", "🜁", "🜂", "🜃", "🜄", "🜍", "🜔", "🜕", "🜖", "🜗", "🜘", "🜚", "🜛", "🜞", "🜢", "🜥", "🜨", "🜩", "🜪", "🜫", "🜬", "🜭", "🜮", "🜯", "🜰", "🜱", "🜲", "🜳", "🜴", "🜵", "🜶", "🜷", "🜸", "🜹", "🜺", "🜻", "🜼", "🜽", "🜾", "🜿"]

    Item {
        id: great
        x: sc.cx; y: sc.cy
        opacity: 0.95
        // 1. Outer limb: double rule, graduations, the zodiac band
        Engraving {
            r: sc.rad; band: 54
            rotation: sc.t * 0.5
            draw: (ctx, c, r) => {
                sc.circle(ctx, c, r, 0.30, 1.2); sc.circle(ctx, c, r - 5, 0.18);
                ctx.strokeStyle = sc.rgba(sc.metal, 0.22); ctx.lineWidth = 1;
                for (let d = 0; d < 360; d++) {
                    const a = d * Math.PI / 180, l = d % 10 === 0 ? 13 : d % 5 === 0 ? 8 : 4;
                    ctx.beginPath(); ctx.moveTo(c + Math.cos(a) * (r - 6), c + Math.sin(a) * (r - 6));
                    ctx.lineTo(c + Math.cos(a) * (r - 6 - l), c + Math.sin(a) * (r - 6 - l)); ctx.stroke();
                }
                sc.circle(ctx, c, r - 20, 0.2); sc.circle(ctx, c, r - 50, 0.2);
                for (let k = 0; k < 12; k++) {
                    const a = k * Math.PI / 6;
                    ctx.beginPath(); ctx.moveTo(c + Math.cos(a) * (r - 20), c + Math.sin(a) * (r - 20)); ctx.lineTo(c + Math.cos(a) * (r - 50), c + Math.sin(a) * (r - 50)); ctx.stroke();
                }
                ctx.save(); ctx.translate(c, c); ctx.rotate(Math.PI / 12); ctx.translate(-c, -c);
                sc.glyphRing(ctx, c, r - 35, sc.zodiac, 17, 0.42, false);
                ctx.restore();
            }
        }
        // 2. Inscription band: a line of alchemical script, turning the other way
        Engraving {
            r: sc.rad * 0.8; band: 26
            rotation: -sc.t * 0.35
            draw: (ctx, c, r) => {
                sc.circle(ctx, c, r, 0.22); sc.circle(ctx, c, r - 22, 0.22);
                sc.glyphRing(ctx, c, r - 11, sc.script, 13, 0.30, false);
            }
        }
        // 3. Heptagram and its circle
        Engraving {
            r: sc.rad * 0.74
            rotation: sc.t * 0.8
            draw: (ctx, c, r) => {
                ctx.strokeStyle = sc.rgba(sc.metal, 0.17); ctx.lineWidth = 1;
                sc.poly(ctx, c, r - 4, 7, 3, -Math.PI / 2);
                sc.circle(ctx, c, (r - 4) * 0.62, 0.12);
                for (let k = 0; k < 7; k++) {    // small rings at the points
                    const a = -Math.PI / 2 + k * Math.PI * 2 / 7;
                    ctx.beginPath(); ctx.arc(c + Math.cos(a) * (r - 4), c + Math.sin(a) * (r - 4), 4, 0, Math.PI * 2);
                    ctx.strokeStyle = sc.rgba(sc.metal, 0.35); ctx.stroke();
                }
            }
        }
        // 4. Squared circle: square, triangle, circle (the emblem of the stone)
        Engraving {
            r: sc.rad * 0.46
            rotation: -sc.t * 1.2
            draw: (ctx, c, r) => {
                ctx.strokeStyle = sc.rgba(sc.ember, 0.24); ctx.lineWidth = 1.1;
                sc.poly(ctx, c, r, 4, 1, Math.PI / 4);
                sc.poly(ctx, c, r * 0.707, 3, 1, -Math.PI / 2);
                ctx.strokeStyle = sc.rgba(sc.metal, 0.22);
                ctx.beginPath(); ctx.arc(c, c, r * 0.3535, 0, Math.PI * 2); ctx.stroke();
                ctx.beginPath(); ctx.arc(c, c, r, 0, Math.PI * 2); ctx.stroke();
            }
        }
        // 5. Rete: the astrolabe's pierced star map (eccentric ecliptic, star pointers), fastest;
        //    it brightens with activity
        Engraving {
            r: sc.rad * 0.3
            rotation: sc.t * 2.2
            opacity: 0.75 + sc.pulse * 0.25
            draw: (ctx, c, r) => {
                ctx.strokeStyle = sc.rgba(sc.metal, 0.32); ctx.lineWidth = 1.2;
                ctx.beginPath(); ctx.arc(c + r * 0.22, c, r * 0.72, 0, Math.PI * 2); ctx.stroke();
                ctx.beginPath(); ctx.arc(c, c, r, 0, Math.PI * 2); ctx.stroke();
                const r2 = sc.rng(99);
                for (let k = 0; k < 9; k++) {
                    const a = k / 9 * Math.PI * 2 + r2() * 0.3, l = r * (0.55 + r2() * 0.4);
                    const x = c + Math.cos(a) * l, y = c + Math.sin(a) * l;
                    ctx.beginPath(); ctx.moveTo(c + Math.cos(a - 0.12) * l * 0.7, c + Math.sin(a - 0.12) * l * 0.7);
                    ctx.quadraticCurveTo(x, y, x, y); ctx.lineTo(c + Math.cos(a + 0.12) * l * 0.7, c + Math.sin(a + 0.12) * l * 0.7);
                    ctx.stroke();
                    ctx.fillStyle = sc.rgba(sc.lighten(sc.metal, 0.4), 0.55); ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI * 2); ctx.fill();
                }
            }
        }
        // activity: a soft breath of light in the middle of the circle
        Rectangle {
            width: sc.rad * 0.7; height: width; radius: width / 2
            x: -width / 2; y: -height / 2
            color: "transparent"
            border.color: sc.lighten(sc.metal, 0.3)
            border.width: 1
            opacity: 0.12 + sc.pulse * 0.35 + (sc.live ? 0.06 * Math.sin(sc.t * 1.3) : 0)
        }
        // planets riding the circle: the skin's metals, each on its own slow orbit; the preset's own is lit
        Repeater {
            model: sc.metals
            delegate: Item {
                required property string modelData
                required property int index
                readonly property real a: (index * 360 / sc.metals.length + sc.t * (0.9 + index * 0.37) * (index % 2 ? -1 : 1)) * Math.PI / 180
                readonly property real rr: sc.rad * (index % 2 ? 0.88 : 0.62)
                readonly property bool lit: modelData === Skin.glyphFor(Theme.cfg.preset)
                x: Math.cos(a) * rr; y: Math.sin(a) * rr
                Rectangle {
                    anchors.centerIn: parent
                    width: 22; height: 22; radius: 11
                    color: Theme.back(0.9)
                    border.color: parent.lit ? sc.metal : sc.q(sc.metal, 0.45)
                }
                Text {
                    anchors.centerIn: parent
                    text: parent.modelData
                    font.family: sc.glyphFont; font.pixelSize: 13
                    color: parent.lit ? sc.lighten(sc.metal, 0.3) : sc.q(sc.metal, 0.7)
                }
            }
        }
    }

    // a second, smaller astrolabe low on the left, half off screen
    Item {
        x: sc.width * 0.06; y: sc.height * 0.95
        opacity: 0.55
        Engraving {
            r: sc.height * 0.24; band: 18
            rotation: -sc.t * 0.7
            draw: (ctx, c, r) => {
                sc.circle(ctx, c, r, 0.3); sc.circle(ctx, c, r - 4, 0.15);
                ctx.strokeStyle = sc.rgba(sc.metal, 0.22);
                for (let d = 0; d < 360; d += 3) {
                    const a = d * Math.PI / 180, l = d % 15 === 0 ? 10 : 4;
                    ctx.beginPath(); ctx.moveTo(c + Math.cos(a) * (r - 5), c + Math.sin(a) * (r - 5)); ctx.lineTo(c + Math.cos(a) * (r - 5 - l), c + Math.sin(a) * (r - 5 - l)); ctx.stroke();
                }
            }
        }
        Engraving {
            r: sc.height * 0.24 * 0.8
            rotation: -sc.t * 0.7
            draw: (ctx, c, r) => { ctx.strokeStyle = sc.rgba(sc.metal, 0.14); sc.poly(ctx, c, r, 6, 2, 0); sc.circle(ctx, c, r * 0.5, 0.2); }
        }
        Engraving {
            r: sc.height * 0.16; band: 4
            rotation: sc.t * 1.4
            draw: (ctx, c, r) => { ctx.setLineDash([3, 7]); sc.circle(ctx, c, r, 0.4, 2); ctx.setLineDash([]); }
        }
    }
    // and an arc of one in the top-right corner
    Item {
        x: sc.width * 0.97; y: sc.height * 0.02
        opacity: 0.45
        Engraving {
            r: sc.height * 0.2; band: 20
            rotation: sc.t * 0.9
            draw: (ctx, c, r) => {
                sc.circle(ctx, c, r, 0.3); sc.circle(ctx, c, r - 18, 0.2);
                sc.glyphRing(ctx, c, r - 9, sc.metals.concat(sc.metals), 10, 0.4, false);
            }
        }
    }

    // ── Gold dust and embers drifting up through the light ──
    Repeater {
        model: 40
        delegate: Rectangle {
            required property int index
            readonly property var rr: sc.rng(500 + index * 17)
            readonly property real x0: rr() * sc.width
            readonly property real speed: 6 + rr() * 16                // px/s, slow
            readonly property real off: rr() * 4000
            readonly property real sway: 10 + rr() * 30
            readonly property real ph: rr() * 6.28
            readonly property bool emb: index % 6 === 0
            readonly property real span: sc.height + 60
            width: emb ? 4 : 2 + (index % 3 === 0 ? 1 : 0); height: width; radius: width / 2
            color: emb ? sc.lighten(sc.ember, 0.25) : sc.lighten(sc.metal, 0.45)
            x: x0 + Math.sin(sc.t * 0.25 + ph) * sway
            y: sc.height + 30 - ((sc.t * speed + off) % span)
            // embers flicker; dust keeps its own brightness (a binding fewer per mote)
            opacity: emb ? 0.75 * (0.55 + 0.45 * Math.sin(sc.t * (0.8 + index % 5 * 0.3) + ph)) : 0.45 * (0.55 + 0.45 * Math.sin(ph))
            Rectangle {      // halo
                visible: parent.emb
                anchors.centerIn: parent
                width: 14; height: 14; radius: 7
                color: sc.q(sc.ember, 0.12)
            }
        }
    }

    // status readout, as the hologram had one: in the display face, quiet
    Column {
        x: 28; y: 58; spacing: 4; opacity: 0.42
        Text { text: Skin.text.os + "  ·  " + (sc.live ? "THE WORK PROCEEDS" : "AT REST"); color: Theme.primary; font.family: Style.fonts.label; font.pixelSize: 11; font.letterSpacing: 3 }
        Text { text: "ÆTHER   " + Math.round(SysStats.wifi * 100) + "%"; color: Theme.primary; font.family: Style.fonts.label; font.pixelSize: 11 }
    }
}
