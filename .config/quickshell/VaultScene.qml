// The default lock scene (Skin.component("scene"); a skin can override it): two heavy engraved metal doors and an alchemical seal across the
// seam. SecurityDoors drives it from LockState (through SkinScene) and draws it shut, offscreen, for the
// lock screen's background, so at rest (shut, sealed) it must look the same both ways: every input's
// default is that state.
//   doorP     0 open … 1 shut (may overshoot to 1.05)
//   inscribe  0..1 the seal draws itself and its six signs light in turn (locking); 1 = sealed
//   ignite    0..1 the signs flare one by one before the seal splits (unlocking); 0 = at rest
//   flare     0..1 the centre sun's brief flash (a fingerprint unlock)
//   spin      ring rotation (LockState turns it while the doors move; rings counter-rotate)
//   dim       0..1 the power-off CRT collapse fades the seal
// The great circle is engraved into the doors themselves and the inner seal is cut in two at the seam,
// so opening splits it and each half leaves with its door.
import QtQuick

Item {
    id: scene

    property real doorP: 1
    property real emblemOpacity: 1        // the legacy doors' fade; the seal splits instead (unused)
    property bool isMain: true
    property string message: ""
    property string submessage: ""
    property real msgP: 0
    property real spin: 0
    property real inscribe: 1
    property real ignite: 0
    property real flare: 0
    property real dim: 0

    readonly property real halfH: height / 2
    readonly property bool painted: upperDoor.painted && lowerDoor.painted
    readonly property var metals: Skin.glyphs.ring || []       // the skin's signs (ALCHEMOS: the six metals); none = bare seal
    readonly property int count: metals.length
    readonly property real bigR: Style.sealRadius(height)          // the great circle engraved across both doors (hyprlock's text keeps clear of it: Style.lockLayout)
    readonly property real sealA: Math.max(0, 1 - dim)

    function seg(p, a, b) { return Math.max(0, Math.min(1, (p - a) / (b - a))); }

    // ── One door: brushed dark metal, engraved panels and rivets, half the great circle ──
    component Door: Item {
        id: door
        property bool upper: true
        property bool painted: false
        clip: true
        readonly property real seamY: upper ? height : 0          // the seam's y inside this door

        Rectangle { anchors.fill: parent; color: Theme.bg }
        Canvas {
            id: plate
            anchors.fill: parent
            property color tint: Theme.primary
            property color tint2: Theme.secondary
            property real r: scene.bigR
            property int seats: scene.count
            onSeatsChanged: { door.painted = false; requestPaint(); }
            onTintChanged: { door.painted = false; requestPaint(); }
            onTint2Changed: { door.painted = false; requestPaint(); }
            onWidthChanged: { door.painted = false; requestPaint(); }
            onHeightChanged: { door.painted = false; requestPaint(); }
            onRChanged: { door.painted = false; requestPaint(); }
            onPainted: door.painted = true
            onPaint: {
                const ctx = getContext("2d");
                ctx.reset();                                   // not clearRect(): see Graph.qml
                const W = width, H = height, sy = door.seamY, cx = W / 2, R = r;
                if (W < 2 || H < 2 || R < 40) return;          // not laid out yet (the first paint can come at 0×0)
                const dir = door.upper ? -1 : 1;               // away from the seam
                // metal: darker away from the seam, a warm sheen toward it
                const g = ctx.createLinearGradient(0, sy, 0, sy + dir * H);
                g.addColorStop(0, Theme.css(Theme.mix(Theme.bg, Theme.primary, 0.13), 1));
                g.addColorStop(0.45, Theme.css(Theme.mix(Theme.bg, Theme.primary, 0.06), 1));
                g.addColorStop(1, Theme.css(Theme.mix(Theme.bg, "#000000", 0.3), 1));
                ctx.fillStyle = g;
                ctx.fillRect(0, 0, W, H);
                // brushed grain
                ctx.lineWidth = 1;
                for (let y = 1.5, i = 0; y < H; y += 3, i++) {
                    ctx.strokeStyle = Theme.pc(i % 7 === 0 ? 0.035 : i % 3 === 0 ? 0.018 : 0.01);
                    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
                }
                // engraved panels: a frame inset from the outer edge, divided in three
                const m = 46, top = door.upper ? m : 60, bot = door.upper ? H - 60 : H - m;
                ctx.strokeStyle = Theme.pc(0.16); ctx.lineWidth = 1.5;
                ctx.strokeRect(m, top, W - 2 * m, bot - top);
                ctx.strokeStyle = Theme.css(Theme.mix(Theme.bg, "#000000", 0.6), 0.9); ctx.lineWidth = 1;
                ctx.strokeRect(m + 2, top + 2, W - 2 * m - 4, bot - top - 4);       // the cut's shadow
                ctx.strokeStyle = Theme.pc(0.08);
                ctx.strokeRect(m + 10, top + 10, W - 2 * m - 20, bot - top - 20);
                for (const x of [W * 0.25, W * 0.75]) {
                    ctx.beginPath(); ctx.moveTo(x, top + 10); ctx.lineTo(x, bot - 10); ctx.stroke();
                }
                // rivets along the frame
                for (let x = m + 24; x < W - m - 10; x += 64) {
                    for (const y of [top - 18, bot + 18]) {
                        if (y < 8 || y > H - 8) continue;
                        const rg = ctx.createRadialGradient(x - 1.5, y - 1.5, 0.5, x, y, 5);
                        rg.addColorStop(0, Theme.lc(0.5)); rg.addColorStop(0.6, Theme.pc(0.18)); rg.addColorStop(1, Theme.css(Theme.bg, 0.0));
                        ctx.fillStyle = rg;
                        ctx.beginPath(); ctx.arc(x, y, 5, 0, 2 * Math.PI); ctx.fill();
                    }
                }
                // the great circle, cut across both doors (each door has its half): three rings,
                // graduations, and the six signs' seats
                ctx.save();
                ctx.beginPath(); ctx.rect(0, 0, W, H); ctx.clip();
                const ring = (rad, a, w) => { ctx.strokeStyle = Theme.pc(a); ctx.lineWidth = w; ctx.beginPath(); ctx.arc(cx, sy, rad, 0, 2 * Math.PI); ctx.stroke(); };
                // a filled band behind the circle so it reads as a raised plate
                ctx.fillStyle = Theme.css(Theme.mix(Theme.bg, Theme.primary, 0.05), 0.85);
                ctx.beginPath(); ctx.arc(cx, sy, R + 18, 0, 2 * Math.PI); ctx.fill();
                ring(R + 18, 0.28, 2); ring(R + 12, 0.12, 1); ring(R - 22, 0.2, 1); ring(R - 28, 0.1, 1);
                for (let i = 0; i < 180; i++) {
                    const a = i * Math.PI / 90, long = i % 15 === 0;
                    ctx.strokeStyle = Theme.pc(long ? 0.35 : 0.14); ctx.lineWidth = long ? 1.5 : 1;
                    const r0 = R + (long ? 2 : 6), r1 = R + 11;
                    ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * r0, sy + Math.sin(a) * r0);
                    ctx.lineTo(cx + Math.cos(a) * r1, sy + Math.sin(a) * r1); ctx.stroke();
                }
                for (let i = 0; i < seats; i++) {
                    const a = (i * 360 / seats - 90) * Math.PI / 180;
                    const x = cx + Math.cos(a) * (R - 3), y = sy + Math.sin(a) * (R - 3);
                    ctx.fillStyle = Theme.css(Theme.mix(Theme.bg, "#000000", 0.3), 1);
                    ctx.strokeStyle = Theme.pc(0.3); ctx.lineWidth = 1.2;
                    ctx.beginPath(); ctx.arc(x, y, 17, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
                }
                // hexagram inscribed in the great circle: fire △ and water ▽
                ctx.strokeStyle = Theme.sc(0.13); ctx.lineWidth = 1.2;
                for (const off of [-90, 90]) {
                    ctx.beginPath();
                    for (let i = 0; i <= 3; i++) {
                        const a = (off + i * 120) * Math.PI / 180;
                        const x = cx + Math.cos(a) * (R - 28), y = sy + Math.sin(a) * (R - 28);
                        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
                    }
                    ctx.stroke();
                }
                ctx.restore();
                // the seam's lip: a heavy bevel
                const lip = ctx.createLinearGradient(0, sy, 0, sy + dir * 22);
                lip.addColorStop(0, Theme.css(Theme.mix(Theme.bg, Theme.primary, 0.35), 1));
                lip.addColorStop(0.15, Theme.css(Theme.mix(Theme.bg, "#000000", 0.5), 1));
                lip.addColorStop(1, Theme.css(Theme.bg, 0));
                ctx.fillStyle = lip;
                ctx.fillRect(0, Math.min(sy, sy + dir * 22), W, 22);
            }
        }
        // glowing seam
        Rectangle {
            width: parent.width; height: 2
            y: door.upper ? parent.height - 2 : 0
            color: Theme.primary
            opacity: 0.85
        }
        Rectangle {
            width: parent.width; height: 18
            y: door.upper ? parent.height - height : 0
            gradient: Gradient {
                GradientStop { position: 0.0; color: door.upper ? Theme.p(0.0) : Theme.p(0.35) }
                GradientStop { position: 1.0; color: door.upper ? Theme.p(0.35) : Theme.p(0.0) }
            }
        }
        // this door's signs (those above / below the seam), lit in turn as the seal closes, igniting in
        // turn as it opens
        Repeater {
            model: [...Array(scene.count).keys()].filter(i => (Math.sin((i * 360 / scene.count - 90) * Math.PI / 180) < -1e-6) === door.upper)
            delegate: SigilText {
                required property int modelData
                readonly property int n: modelData
                readonly property real a: (n * 360 / scene.count - 90) * Math.PI / 180
                readonly property real step: 0.66 / scene.count
                readonly property real lit: scene.seg(scene.inscribe, 0.25 + n * step, 0.36 + n * step)
                readonly property real flash: Math.sin(Math.PI * scene.seg(scene.ignite, n * step * 12 / 11, n * step * 12 / 11 + 0.3))
                text: scene.metals[n]
                x: door.width / 2 + Math.cos(a) * (scene.bigR - 3) - width / 2
                y: door.seamY + Math.sin(a) * (scene.bigR - 3) - height / 2
                color: flash > 0.05 ? Theme.mix(Theme.primary, "#ffffff", 0.5 * flash) : Theme.primary
                opacity: (0.25 + 0.75 * lit) * scene.sealA
                font.pixelSize: 24
                scale: 1 + 0.45 * flash
                glow: Math.min(1, 0.45 * lit + flash)
            }
        }
        // this door's half of the seal
        Item {
            width: 440; height: 220
            x: (door.width - width) / 2
            y: door.upper ? door.height - height : 0
            clip: true
            Seal { x: 0; y: door.upper ? 0 : -220 }
        }
    }

    // ── The seal: rings, triangle and square, the sun at its centre (made twice, a half in each door) ──
    component Seal: Item {
        width: 440; height: 440
        opacity: scene.sealA
        Ring {
            anchors.centerIn: parent; radius: 205; thickness: 1; value: scene.seg(scene.inscribe, 0, 0.3)
            color: Theme.p(0.6); trackColor: "transparent"; animated: false; rotation: scene.spin
        }
        Ring {
            anchors.centerIn: parent; radius: 196; thickness: 6; value: 1
            dashed: true; dash: [0.3, 1.6]
            color: Theme.p(0.35 * scene.seg(scene.inscribe, 0.05, 0.35)); trackColor: "transparent"; animated: false
            rotation: -scene.spin * 1.5
        }
        Ring {
            anchors.centerIn: parent; radius: 168; thickness: 2; value: scene.seg(scene.inscribe, 0.1, 0.4)
            color: Theme.secondary; opacity: 0.8; trackColor: "transparent"; animated: false; startAngle: 90
            rotation: scene.spin * 0.7
        }
        Sigil {
            anchors.centerIn: parent
            radius: 168; squareRadius: 84
            draw: scene.seg(scene.inscribe, 0.15, 0.75)
            color: Theme.p(0.45); lineWidth: 1.4
            rotation: -scene.spin * 0.4
        }
        // centre: the clock sits here on the lock screen (hyprlock), so it stays clear
        Rectangle {
            anchors.centerIn: parent
            width: 230; height: 230; radius: 115
            color: Theme.deep            // solid: hyprlock draws the clock on it
            border.color: Theme.p(0.6)
            Rectangle {
                anchors.centerIn: parent
                width: 220; height: 220; radius: 110
                color: "transparent"
                border.color: Theme.p(0.18)
            }
        }
        // the sun: big on the other screens; on the main screen only the fingerprint's flash (at rest
        // hyprlock's clock sits there, and the glyph's ring would cut through the digits)
        SigilText {
            anchors.centerIn: parent
            text: Skin.glyphs.sun || ""
            color: Theme.mix(Theme.primary, "#ffffff", 0.6 * scene.flare)
            font.pixelSize: scene.isMain ? 150 : 64
            opacity: (scene.isMain ? 0.6 * scene.flare : 0.9) * scene.seg(scene.inscribe, 0.7, 1)
            scale: 1 + 0.25 * scene.flare
            glow: scene.isMain ? scene.flare : 0.6 + 0.4 * scene.flare
        }
        Rectangle {          // the flash ring: grows and fades as the flare dies down
            anchors.centerIn: parent
            visible: scene.flare > 0
            width: 230 + 300 * (1 - scene.flare); height: width; radius: width / 2
            color: "transparent"
            border.color: Theme.mix(Theme.primary, "#ffffff", 0.5); border.width: 2
            opacity: scene.flare
        }
        // the words stay inside the centre disc (its inner ring is 220 across): a long one shrinks to fit
        Column {
            anchors.centerIn: parent
            width: 196
            spacing: 6
            visible: scene.isMain
            Text {            // sized for the whole message, so it doesn't change size as it types in
                id: fitter
                visible: false
                width: parent.width
                fontSizeMode: Text.HorizontalFit; minimumPixelSize: 12
                text: scene.message
                font.family: Style.fonts.display; font.pixelSize: scene.message.length > 11 ? 17 : 22; font.letterSpacing: 4
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: scene.message.slice(0, Math.ceil(scene.msgP * scene.message.length))
                color: Theme.text
                font.family: Style.fonts.display; font.pixelSize: fitter.fontInfo.pixelSize; font.letterSpacing: 4
            }
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: scene.submessage
                opacity: Math.max(0, (scene.msgP - 0.5) * 2)
                color: Theme.secondary
                font.family: Style.fonts.label; font.pixelSize: 8; font.letterSpacing: 2
            }
        }
    }

    Door { id: upperDoor; upper: true;  width: scene.width; height: scene.halfH + 2; y: -scene.halfH + scene.doorP * scene.halfH - 2 }
    Door { id: lowerDoor; upper: false; width: scene.width; height: scene.halfH + 2; y: scene.height - scene.doorP * scene.halfH }
}
