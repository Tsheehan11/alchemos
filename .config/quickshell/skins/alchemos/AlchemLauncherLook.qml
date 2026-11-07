// ALCHEMOS launcher look (Skin.component("launcherLook"), loaded by Launcher.qml): a summoning circle.
// The core is an engraved seal (metal rim, the skin's metals turning round it, a hexagram behind the
// name); apps are medallions with a brushed-metal rim; branches are engraved channels with gold motes
// running out along them; dust orbits the core over a turning circle of signs. It opens like a dial
// unwinding (no overshoot) and fades in, warm and low, where the hologram flickered on.
// Same interface as HoloLauncherLook.qml; Launcher.qml owns keys, geometry and the hit areas.
import QtQuick
import QtQuick.Effects
import Quickshell
import "../.."

Item {
    id: look
    required property var win
    required property var core

    readonly property int openMs: 900
    readonly property int openEasing: Easing.OutQuint
    function opened() { fade.restart(); }

    readonly property color metal: Theme.primary
    readonly property color ember: Theme.secondary
    readonly property string symbols: Style.fonts.signs
    readonly property var metals: Skin.glyphs.ring && Skin.glyphs.ring.length ? Skin.glyphs.ring : ["☉", "☽", "♂", "♀", "☿", "♄"]
    readonly property real sp: Math.min(1, Math.max(0, win.spread))
    function lighten(c, k) { return Qt.rgba(c.r + (1 - c.r) * k, c.g + (1 - c.g) * k, c.b + (1 - c.b) * k, 1); }
    function css(c, a) { return Theme.css(c, a); }

    // warm, low glow (the hologram's is cyan and strong)
    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true; shadowColor: look.ember
        shadowBlur: 0.5; shadowOpacity: 0.45 * Style.glow
        shadowHorizontalOffset: 0; shadowVerticalOffset: 0; blurMax: 24
    }
    NumberAnimation { id: fade; target: look; property: "opacity"; from: 0; to: 1; duration: 380; easing.type: Easing.OutCubic }

    // ── The circle of signs under the cloud (drawn once, turned) ──
    Canvas {
        anchors.centerIn: parent
        width: 860; height: 860
        rotation: look.win.t * 2
        scale: 0.85 + 0.15 * look.sp
        opacity: look.sp
        property color m: look.metal
        onMChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d"); ctx.reset();
            const c = width / 2, R = 415;
            const ring = (r, a, w) => { ctx.strokeStyle = look.css(look.metal, a); ctx.lineWidth = w || 1; ctx.beginPath(); ctx.arc(c, c, r, 0, Math.PI * 2); ctx.stroke(); };
            ring(R, 0.35, 1.2); ring(R - 5, 0.2);
            ctx.strokeStyle = look.css(look.metal, 0.28);
            for (let d = 0; d < 360; d += 2) {
                const a = d * Math.PI / 180, l = d % 30 === 0 ? 14 : d % 10 === 0 ? 8 : 4;
                ctx.beginPath(); ctx.moveTo(c + Math.cos(a) * (R - 6), c + Math.sin(a) * (R - 6)); ctx.lineTo(c + Math.cos(a) * (R - 6 - l), c + Math.sin(a) * (R - 6 - l)); ctx.stroke();
            }
            ring(R - 26, 0.18);
            ctx.fillStyle = look.css(look.metal, 0.4); ctx.font = "13px '" + look.symbols + "'"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
            const sig = ["🜁", "🜂", "🜃", "🜄"].concat(look.metals).concat(["🜍"]);
            for (let k = 0; k < 24; k++) {
                const a = (k + 0.5) / 24 * Math.PI * 2;
                ctx.save(); ctx.translate(c + Math.cos(a) * (R - 16), c + Math.sin(a) * (R - 16)); ctx.rotate(a + Math.PI / 2);
                ctx.fillText(sig[k % sig.length], 0, 0); ctx.restore();
            }
        }
    }

    // ── Engraved channels with gold motes running out along them; dust orbiting the core ──
    Canvas {
        anchors.fill: parent
        property real tt: look.win.t
        property real s: look.win.spread
        property int sel: look.win.selected
        onTtChanged: requestPaint(); onSChanged: requestPaint(); onSelChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d"); ctx.reset();
            if (look.win.spread <= 0.02) return;
            const T = look.win.t, sp = look.sp, win = look.win, core = look.core;
            for (let k = 0; k < 70; k++) {      // dust: dots, not streaks
                const r0 = 90 + ((k * 73) % 300), speed = (0.06 + ((k * 37) % 10) / 80) * (k % 2 ? 1 : 0.7);
                const a = k * 2.399 + T * speed, r = (r0 + 14 * Math.sin(T * 0.5 + k)) * sp;
                ctx.fillStyle = k % 5 === 0 ? look.css(look.ember, 0.55) : look.css(look.lighten(look.metal, 0.4), 0.18 + (k % 4) * 0.08);
                ctx.beginPath(); ctx.arc(core.cx + Math.cos(a) * r, core.cy + Math.sin(a) * r, k % 7 === 0 ? 1.8 : 1.1, 0, Math.PI * 2); ctx.fill();
            }
            function channel(ax, ay, bx, by, bend, hot, seed) {
                const mx = (ax + bx) / 2, my = (ay + by) / 2, dx = bx - ax, dy = by - ay;
                const sway = bend + 0.08 * Math.sin(T * 0.7 + seed);
                const qx = mx - dy * sway, qy = my + dx * sway;
                const path = (o) => { ctx.beginPath(); ctx.moveTo(ax + o, ay + o); ctx.quadraticCurveTo(qx + o, qy + o, bx + o, by + o); };
                path(1); ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,0.55)"; ctx.stroke();        // the groove's shadow
                path(0); ctx.lineWidth = hot ? 1.8 : 1.2; ctx.strokeStyle = hot ? look.css(look.lighten(look.ember, 0.3), 0.85) : look.css(look.metal, 0.5); ctx.stroke();
                path(-0.8); ctx.lineWidth = 0.6; ctx.strokeStyle = look.css(look.lighten(look.metal, 0.7), hot ? 0.5 : 0.2); ctx.stroke();  // its lit edge
                for (let m = 0; m < 3; m++) {        // motes flowing out
                    const u = ((T * 0.22 + m / 3 + seed * 0.13) % 1), v = 1 - u;
                    const px = v * v * ax + 2 * v * u * qx + u * u * bx, py = v * v * ay + 2 * v * u * qy + u * u * by;
                    ctx.fillStyle = look.css(look.lighten(hot ? look.ember : look.metal, 0.5), 0.25); ctx.beginPath(); ctx.arc(px, py, 4.5, 0, Math.PI * 2); ctx.fill();
                    ctx.fillStyle = look.css(look.lighten(hot ? look.ember : look.metal, 0.6), 0.9); ctx.beginPath(); ctx.arc(px, py, 1.6, 0, Math.PI * 2); ctx.fill();
                }
            }
            for (let i = 0; i < win.apps.length; i++) {
                const src = win.tierOf(i) === 1 ? i - 1 : -1;
                channel(src < 0 ? core.cx : core.nx(src), src < 0 ? core.cy : core.ny(src), core.nx(i), core.ny(i),
                        win.tierOf(i) === 1 ? -0.16 : -0.2, win.branchOf(i) === win.branchOf(win.selected), i);
            }
        }
    }

    // a brushed-metal medallion rim, drawn once per size / state / preset
    component Rim: Canvas {
        property real d: 94
        property bool hot: false
        property color m: Theme.primary
        width: d + 8; height: d + 8
        onHotChanged: requestPaint(); onMChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d"); ctx.reset();
            const c = width / 2, R = d / 2;
            const g = ctx.createConicalGradient(c, c, Math.PI / 4);
            const hi = Theme.mix(m, "#ffffff", 0.55), lo = Theme.mix(m, "#000000", 0.55);
            g.addColorStop(0, Theme.css(hi, 1)); g.addColorStop(0.25, Theme.css(lo, 1)); g.addColorStop(0.5, Theme.css(m, 1));
            g.addColorStop(0.75, Theme.css(lo, 1)); g.addColorStop(1, Theme.css(hi, 1));
            ctx.lineWidth = hot ? 4 : 3; ctx.strokeStyle = g; ctx.globalAlpha = hot ? 1 : 0.75;
            ctx.beginPath(); ctx.arc(c, c, R - 1.5, 0, Math.PI * 2); ctx.stroke();
            ctx.globalAlpha = 1;
            ctx.strokeStyle = "rgba(0,0,0,0.6)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(c, c, R - 4, 0, Math.PI * 2); ctx.stroke();
            ctx.strokeStyle = Theme.css(m, hot ? 0.55 : 0.3);
            for (let k = 0; k < 36; k++) {
                const a = k / 36 * Math.PI * 2, l = k % 3 === 0 ? 4 : 2;
                ctx.beginPath(); ctx.moveTo(c + Math.cos(a) * (R - 6), c + Math.sin(a) * (R - 6)); ctx.lineTo(c + Math.cos(a) * (R - 6 - l), c + Math.sin(a) * (R - 6 - l)); ctx.stroke();
            }
        }
    }

    // ── The core: a seal with the skin's metals, the preset's own lit ──
    Item {
        x: look.core.cx - width / 2; y: look.core.cy - height / 2
        width: 170; height: 170
        scale: look.sp
        Rectangle {
            anchors.centerIn: parent; width: 150; height: 150; radius: 75
            gradient: Gradient {
                GradientStop { position: 0; color: Theme.mix(Theme.bg, Theme.primary, 0.14) }
                GradientStop { position: 1; color: Theme.back(0.98) }
            }
        }
        Rim { anchors.centerIn: parent; d: 150; hot: true }
        Canvas {         // a hexagram engraved behind the name
            anchors.centerIn: parent; width: 150; height: 150
            rotation: -look.win.t * 4
            property color m: look.metal
            onMChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d"); ctx.reset(); const c = 75, r = 58;
                ctx.strokeStyle = Theme.css(m, 0.16); ctx.lineWidth = 1;
                for (const o of [-Math.PI / 2, Math.PI / 2]) {
                    ctx.beginPath();
                    for (let k = 0; k <= 3; k++) {
                        const a = o + k * Math.PI * 2 / 3;
                        if (k) ctx.lineTo(c + Math.cos(a) * r, c + Math.sin(a) * r); else ctx.moveTo(c + Math.cos(a) * r, c + Math.sin(a) * r);
                    }
                    ctx.stroke();
                }
            }
        }
        Repeater {
            model: look.metals
            delegate: Text {
                required property string modelData
                required property int index
                readonly property real a: (index * 360 / look.metals.length - 90 + look.win.t * 6) * Math.PI / 180
                readonly property bool lit: modelData === Skin.glyphFor(Theme.cfg.preset)
                x: 85 + Math.cos(a) * 84 - width / 2; y: 85 + Math.sin(a) * 84 - height / 2
                text: modelData; font.family: look.symbols; font.pixelSize: lit ? 15 : 12
                color: lit ? look.lighten(look.metal, 0.3) : Theme.p(0.5)
            }
        }
        Column {
            anchors.centerIn: parent; spacing: 3
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "SUMMON"; color: Theme.dim
                font.family: Style.fonts.label; font.pixelSize: 9; font.letterSpacing: 4
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(implicitWidth, 120); horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                text: look.win.current.name.toUpperCase()
                color: look.win.current.available ? Theme.text : Theme.faint
                font.family: Style.fonts.display; font.pixelSize: look.win.current.name.length > 7 ? 15 : 19
                font.weight: Font.DemiBold; font.letterSpacing: 2
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: look.win.current.available ? "TYPE TO SEEK" : "NOT INSTALLED"
                color: look.ember; font.family: Style.fonts.label; font.pixelSize: 7; font.letterSpacing: 3
            }
        }
    }

    // ── Branch labels: small caps between the two apps of a branch ──
    Repeater {
        model: look.win.branchCount
        delegate: Text {
            required property int index
            readonly property var win: look.win
            readonly property var core: look.core
            readonly property int i0: index * 2
            readonly property int i1: i0 + 1 < win.apps.length ? i0 + 1 : -1
            readonly property bool hot: win.branchOf(win.selected) === index
            readonly property real outX: i1 >= 0 ? core.nx(i1) : core.cx + (core.nx(i0) - core.cx) * 1.5
            readonly property real outY: i1 >= 0 ? core.ny(i1) : core.cy + (core.ny(i0) - core.cy) * 1.5
            readonly property real mx: (core.nx(i0) + outX) / 2
            readonly property real my: (core.ny(i0) + outY) / 2
            readonly property real ox: (outY - core.ny(i0))
            readonly property real oy: -(outX - core.nx(i0))
            readonly property real ol: Math.max(1, Math.hypot(ox, oy))
            readonly property string group: (win.apps[i0] || {}).group || (i1 >= 0 ? win.apps[i1].group : "") || ""
            x: mx + ox / ol * 30 - width / 2; y: my + oy / ol * 30 - height / 2
            text: group ? "· " + group.toUpperCase() + " ·" : ""
            color: hot ? look.ember : Theme.dim
            opacity: look.sp * (hot ? 1 : 0.7)
            font.family: Style.fonts.label; font.pixelSize: 11; font.letterSpacing: 4
            z: 5
        }
    }

    // ── App medallions ──
    Repeater {
        model: look.win.apps.length
        delegate: Item {
            id: node
            required property int index
            readonly property bool sel: look.win.selected === index
            readonly property var app: look.win.apps[index] || ({ name: "", icon: "", available: false })
            readonly property int size: look.win.nodeSize(index)
            width: size; height: size
            x: look.core.nx(index) - width / 2; y: look.core.ny(index) - height / 2
            z: sel ? 20 : 10
            scale: look.sp * (sel ? 1.12 : 1)
            opacity: Math.min(1, look.win.spread * 1.3) * (app.available ? 1 : 0.35)
            Behavior on scale { NumberAnimation { duration: 150 } }

            Rectangle {
                anchors.fill: parent; radius: width / 2
                gradient: Gradient {
                    GradientStop { position: 0; color: Theme.mix(Theme.bg, Theme.primary, node.sel ? 0.22 : 0.1) }
                    GradientStop { position: 1; color: Theme.back(0.97) }
                }
            }
            Image {      // stone grain inside the medallion
                anchors.fill: parent; anchors.margins: 4
                source: Qt.resolvedUrl("../../assets/grain.png"); fillMode: Image.Tile; opacity: 0.25; smooth: false
                layer.enabled: true; layer.effect: MultiEffect { maskEnabled: true; maskSource: mask }
            }
            Rectangle { id: mask; visible: false; layer.enabled: true; anchors.fill: parent; radius: width / 2 }
            Rim { anchors.centerIn: parent; d: node.size; hot: node.sel }
            // selected: an outer arc of graduations turning, with quicksilver's sign riding it
            Canvas {
                visible: node.sel
                anchors.centerIn: parent; width: node.size + 30; height: width
                rotation: look.win.t * 40
                property color e: look.ember
                onEChanged: requestPaint()
                onPaint: {
                    const ctx = getContext("2d"); ctx.reset(); const c = width / 2, r = c - 3;
                    ctx.strokeStyle = Theme.css(look.ember, 0.7); ctx.lineWidth = 1;
                    ctx.beginPath(); ctx.arc(c, c, r, -0.3, Math.PI * 1.3); ctx.stroke();
                    for (let k = 0; k < 24; k++) {
                        const a = k / 24 * Math.PI * 2;
                        ctx.beginPath(); ctx.moveTo(c + Math.cos(a) * (r - 3), c + Math.sin(a) * (r - 3)); ctx.lineTo(c + Math.cos(a) * (r - 6), c + Math.sin(a) * (r - 6)); ctx.stroke();
                    }
                    ctx.fillStyle = Theme.css(look.lighten(look.ember, 0.4), 1); ctx.font = "11px '" + look.symbols + "'"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
                    ctx.fillText("☿", c, c - r + 0.5);
                }
            }
            Column {
                anchors.centerIn: parent; spacing: 1
                Image {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: node.app.icon !== "" && status === Image.Ready
                    width: node.size > 80 ? 30 : 24; height: width
                    source: node.app.icon; sourceSize: Qt.size(64, 64); smooth: true
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(implicitWidth, node.size - 16); horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                    text: node.app.name.toUpperCase(); color: node.sel ? Theme.text : Theme.textSoft
                    font.family: Style.fonts.display; font.pixelSize: node.app.name.length > 6 ? 9 : 11
                    font.weight: Font.DemiBold; font.letterSpacing: 1
                }
                Text {       // the app's key (1–9, 0), in the skin's numerals
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: !node.app.available ? "N/A" : node.index < 9 ? Style.numeral(node.index + 1) : node.index === 9 ? "0" : ""
                    color: look.ember; font.family: Style.fonts.label; font.pixelSize: 8; opacity: 0.85
                }
            }
        }
    }
}
