// One desktop widget on a WidgetSurface: a projected hologram (HoloFrame, no solid card) around a
// widgets/<Type>.qml body, wherever it was put (Widgets.qml: fractions of its monitor).
//   • Drag it anywhere: the surface takes the whole screen for the drag, the card follows the
//     pointer with a soft snap to the screen edges, centre lines and other widgets (faint guide
//     lines; hold Shift for none). Dropped, it's clamped on screen and nudged off any widget it
//     landed on. Carry it on to another monitor and it lands there, under the pointer.
//   • Drag the corner handle to scale it (per-type min / max, WidgetBody.minScale / maxScale).
//   • Lifts with a glow while held and settles with a scan pulse (Perf clock; none in battery saver).
//   • ◇ pin above windows, × close (on hover).
import QtQuick
import QtQuick.Effects
import Quickshell

Item {
    id: wc
    required property string wid
    required property var surface                  // the WidgetSurface it's drawn on
    readonly property var it: Widgets.get(wid)
    readonly property var scr: surface.scr
    readonly property bool pinned: it ? it.pinned === true : false
    readonly property real k: resizing ? liveK : Widgets.scaleOf(it)
    readonly property string mono: Style.mono
    readonly property bool calm: PowerMode.saver || Perf.fps <= 0      // no edit animations

    // ── where it goes (screen pixels) ──
    readonly property real sw: scr ? scr.width : surface.width
    readonly property real sh: scr ? scr.height : surface.height
    readonly property var base: {
        if (!it || !scr) return { x: 0, y: 0 };
        const p = it.pending;
        if (p && p.pos) return Widgets.slotXY(scr, p.pos, width, height);
        if (p && p.legacy) return Widgets.slotXY(scr, p.legacy, width, height);
        if (p && p.at) return { x: Widgets.clampX(scr, p.at.x - width / 2, width), y: Widgets.clampY(scr, p.at.y - height / 2, height) };
        return Widgets.fromFrac(scr, it.fx || 0, it.fy || 0, width, height);
    }
    readonly property real baseX: base.x
    readonly property real baseY: base.y
    function report() { if (scr) Widgets.setRect(wid, scr.name, baseX, baseY, width, height, wc); }
    onBaseXChanged: report()
    onBaseYChanged: report()
    onWidthChanged: report()
    onHeightChanged: report()
    Component.onCompleted: report()
    Component.onDestruction: Widgets.dropRect(wid, wc)

    width: Math.ceil(card.width * k)
    height: Math.ceil(card.height * k)

    // dragging / resizing: the card is held at dragX / dragY; after the drop it stays there until
    // the new spot is saved (held), so it doesn't jump back for a frame
    property bool dragging: false
    property bool resizing: false
    property bool held: false
    property real liveK: 1
    property real dragX: 0
    property real dragY: 0
    readonly property bool frozen: dragging || resizing || held
    x: frozen ? dragX : baseX
    y: frozen ? dragY : baseY
    Behavior on x { enabled: !wc.frozen && !wc.calm; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    Behavior on y { enabled: !wc.frozen && !wc.calm; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    z: dragging || resizing ? 10 : 0
    onItChanged: if (held) { held = false; pulse(); }
    Timer { id: holdLimit; interval: 700; onTriggered: if (wc.held) { wc.held = false; wc.pulse(); } }
    function hold() { held = true; holdLimit.restart(); }

    // ── edit feel, from the shared Perf clock (only read while it's happening) ──
    property real pressT: 0
    readonly property real lift: (dragging || resizing) && !calm ? Math.min(1, Math.max(0, (Perf.time - pressT) / 0.14)) : 0
    property real pulseT: 0
    property bool pulsing: false
    readonly property real pulseK: pulsing ? Math.max(0, (Perf.time - pulseT) / 0.55) : 0
    onPulseKChanged: if (pulseK >= 1) pulsing = false
    function pulse() { if (!calm) { pulseT = Perf.time; pulsing = true; } }

    // its share of the surface's input region
    property Region region: Region { item: wc }

    readonly property bool live: surface.live
    readonly property bool done: body.item ? body.item.alert === true : false
    readonly property color accent: done ? Theme.secondary : Theme.primary
    readonly property bool wantsKeyboard: body.item ? body.item.wantsKeyboard === true : false
    readonly property bool hovered: dragArea.containsMouse || pinMa.containsMouse || closeMa.containsMouse || gripMa.containsMouse

    Item {
        id: liftBox
        width: wc.width; height: wc.height
        transform: [
            Scale { origin.x: wc.width / 2; origin.y: wc.height / 2; xScale: 1 + 0.03 * wc.lift; yScale: 1 + 0.03 * wc.lift },
            Translate { y: -4 * wc.lift }
        ]

    Item {
        id: card
        transform: Scale { xScale: wc.k; yScale: wc.k }
        width: Math.max(160, (body.item ? body.item.implicitWidth : 200) + 28)
        height: (body.item ? body.item.implicitHeight : 80) + 34 + 14
        // ── hologram: draws on when the card appears, retracts when it's closed (Widgets.closing) ──
        property real boot: 0
        readonly property bool closing: Widgets.closing[wc.wid] === true
        Component.onCompleted: bootIn.start()
        onClosingChanged: if (closing) { bootIn.stop(); bootOut.start(); }
        NumberAnimation { id: bootIn; target: card; property: "boot"; from: 0; to: 1; duration: PowerMode.saver ? 200 : 520; easing.type: Easing.OutCubic }
        NumberAnimation { id: bootOut; target: card; property: "boot"; to: 0; duration: 260; easing.type: Easing.InCubic }

        HoloFrame {
            anchors.fill: parent
            t: wc.surface.t
            still: !wc.live || PowerMode.saver
            boot: card.boot
            accent: wc.accent
            strong: wc.dragging || wc.resizing || wc.hovered
            lift: wc.lift
            pulse: wc.pulsing ? Math.min(1, wc.pulseK) : 0
            // an alert (timer done) pulses the strokes with the effects clock, else they stay lit
            opacity: wc.done && wc.live ? 0.55 + 0.45 * Math.abs(Math.sin(wc.surface.t * 4)) : 1
        }

        // ── drag (under the body, so its own buttons still work) ──
        MouseArea {
            id: dragArea
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            cursorShape: wc.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            property real px: 0
            property real py: 0
            property real sx: 0
            property real sy: 0
            property bool moved: false
            onPressed: m => {
                const p = mapToItem(null, m.x, m.y);
                px = p.x; py = p.y; sx = wc.x; sy = wc.y; moved = false;
                holdLimit.stop(); wc.held = false;
                wc.dragX = wc.x; wc.dragY = wc.y;
                wc.pressT = Perf.time;
                wc.dragging = true;
                wc.surface.grab(wc);                   // whole screen takes input until release
            }
            onPositionChanged: m => {
                if (!pressed) return;
                const p = mapToItem(null, m.x, m.y);
                if (!moved && Math.hypot(p.x - px, p.y - py) < 6) return;
                moved = true;
                const s = wc.scr;
                const rx = Widgets.clampX(s, sx + p.x - px, wc.width), ry = Widgets.clampY(s, sy + p.y - py, wc.height);
                if (m.modifiers & Qt.ShiftModifier) {
                    wc.dragX = rx; wc.dragY = ry;
                    wc.surface.guides = ({ v: [], h: [] });
                } else {
                    const r = Widgets.snap(s, wc.wid, rx, ry, wc.width, wc.height);
                    wc.dragX = r.x; wc.dragY = r.y;
                    wc.surface.guides = ({ v: r.v, h: r.h });
                }
                wc.surface.point = p;
            }
            onReleased: m => {
                const wasDrag = moved;
                finish(mapToItem(null, m.x, m.y));
                if (!wasDrag && body.item && body.item.clicked) body.item.clicked();   // a plain click, not a drag
            }
            onCanceled: finish(null)
            function finish(p) {
                const was = moved;
                moved = false;
                if (was && p) {
                    wc.hold();
                    Widgets.drop(wc.wid, wc.scr, wc.dragX, wc.dragY, wc.width, wc.height, px - sx, py - sy);
                }
                wc.dragging = false;
                wc.surface.release(wc);
            }
            onDoubleClicked: if (body.item && body.item.doubleClicked) body.item.doubleClicked()
        }

        // ── header + body, with a soft themed halo behind the text (not a box) so it reads over
        //    bright windows as well as the desktop: every Text gets a faint outline in the theme's
        //    background colour (halo()), and the whole layer a soft shadow of the same colour.
        //    A blurred-only shadow is too thin around thin glyphs; MultiEffect masks for a
        //    dilated halo are ignored (see HoloFrame), so it's outline + shadow. ──
        Item {
            id: content
            anchors.fill: parent
            layer.enabled: card.boot > 0
            layer.textureSize: Qt.size(Math.ceil(width * wc.k), Math.ceil(height * wc.k))
            layer.smooth: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Theme.back(1)
                blurMax: 16
                shadowBlur: 1
                shadowOpacity: 1
                shadowHorizontalOffset: 0
                shadowVerticalOffset: 0
                autoPaddingEnabled: true
            }

            Text {
                x: 26; y: 10
                opacity: Math.max(0, card.boot * 2 - 1)
                width: card.width - 40 - (buttons.visible ? buttons.width : 0)
                elide: Text.ElideRight
                text: (body.item ? body.item.title : (wc.it ? wc.it.type.toUpperCase() : ""))
                color: wc.accent
                style: Text.Outline; styleColor: wc.haloColor
                font.family: wc.mono; font.pixelSize: 10; font.letterSpacing: 3
            }
            Text {
                visible: !buttons.visible
                opacity: Math.max(0, card.boot * 2 - 1)
                anchors.right: parent.right; anchors.rightMargin: 14; y: 10
                text: (wc.pinned ? "◆ " : "") + (body.item ? body.item.detail : "")
                color: Theme.dim
                style: Text.Outline; styleColor: wc.haloColor
                font.family: wc.mono; font.pixelSize: 10; font.letterSpacing: 2
            }
            Row {
                id: buttons
                visible: !wc.dragging && !wc.resizing && wc.hovered
                anchors.right: parent.right; anchors.rightMargin: 8; y: 5
                spacing: 2
                Rectangle {
                    width: 22; height: 20; color: "transparent"; border.width: pinMa.containsMouse ? 1 : 0; border.color: Theme.p(0.5)
                    Text { anchors.centerIn: parent; text: wc.pinned ? "◆" : "◇"; color: wc.pinned ? Theme.secondary : Theme.dim; font.family: wc.mono; font.pixelSize: 12 }
                    MouseArea { id: pinMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Widgets.pin(wc.wid, !wc.pinned) }
                }
                Rectangle {
                    width: 22; height: 20; color: "transparent"; border.width: closeMa.containsMouse ? 1 : 0; border.color: Theme.s(0.7)
                    Text { anchors.centerIn: parent; text: "×"; color: closeMa.containsMouse ? Theme.text : Theme.dim; font.family: wc.mono; font.pixelSize: 15 }
                    MouseArea { id: closeMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Widgets.remove(wc.wid) }
                }
            }

            // ── body: widgets/<Type>.qml ──
            Loader {
                id: body
                x: 14; y: 34
                opacity: Math.max(0, card.boot * 1.6 - 0.6)
                source: wc.it ? Widgets.source(wc.it.type) : ""
                onLoaded: { if (item && wc.it) Widgets.setLimits(wc.it.type, item.minScale || 0.6, item.maxScale || 2.5); Qt.callLater(wc.halo); }
            }
            Connections {        // rows come and go (agenda, due…): outline the new ones
                target: body.item
                function onImplicitHeightChanged() { Qt.callLater(wc.halo); }
                function onImplicitWidthChanged() { Qt.callLater(wc.halo); }
            }
        }
        Binding { target: body.item; property: "widget"; value: wc.it; when: body.item !== null }
        Binding { target: body.item; property: "active"; value: wc.surface.visible; when: body.item !== null }
        Binding { target: body.item; property: "live"; value: wc.live; when: body.item !== null }
        Binding { target: body.item; property: "t"; value: wc.surface.t; when: body.item !== null }
        Binding { target: body.item; property: "size"; value: Widgets.sizeName(wc.k); when: body.item !== null }
    }
    }

    // ── resize: the bottom-right corner (outside the scaled card, so it stays one size) ──
    Item {
        id: grip
        width: 22; height: 22
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.rightMargin: 1; anchors.bottomMargin: 1          // inside the card: its input region (mask) is the card
        visible: wc.hovered || wc.resizing
        Item {          // a small corner bracket
            anchors.fill: parent
            opacity: gripMa.containsMouse || wc.resizing ? 1 : 0.6
            Rectangle { x: 17; y: 6; width: 1.5; height: 13.5; color: Theme.primary }
            Rectangle { x: 6; y: 18; width: 13; height: 1.5; color: Theme.primary }
            Rectangle { x: 12; y: 11; width: 1.5; height: 3.5; color: Theme.primary }
            Rectangle { x: 10; y: 13; width: 3.5; height: 1.5; color: Theme.primary }
        }
        MouseArea {
            id: gripMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.SizeFDiagCursor
            property real px: 0
            property real py: 0
            property real k0: 1
            property real w0: 1
            property real h0: 1
            onPressed: m => {
                const p = mapToItem(null, m.x, m.y);
                px = p.x; py = p.y; k0 = wc.k; w0 = wc.width; h0 = wc.height;
                holdLimit.stop(); wc.held = false;
                wc.dragX = wc.x; wc.dragY = wc.y;
                wc.liveK = k0;
                wc.pressT = Perf.time;
                wc.resizing = true;
                wc.surface.grab(wc);
            }
            onPositionChanged: m => {
                if (!pressed) return;
                const p = mapToItem(null, m.x, m.y);
                let k = wc.k0Scale(k0 * Math.max((w0 + p.x - px) / w0, (h0 + p.y - py) / h0));
                k = Math.min(k, k0 * (wc.sw - wc.dragX) / w0, k0 * (wc.sh - wc.dragY) / h0);      // stays on screen
                wc.liveK = Math.max(0.3, k);
            }
            onReleased: done()
            onCanceled: done()
            function done() {
                if (!wc.resizing) return;
                wc.hold();
                Widgets.resizeAt(wc.wid, wc.scr, wc.liveK, wc.dragX, wc.dragY, wc.width, wc.height);
                wc.resizing = false;
                wc.surface.release(wc);
            }
        }
    }
    readonly property color haloColor: Theme.back(0.6)
    onHaloColorChanged: Qt.callLater(halo)
    function halo() {
        function walk(o) {
            if (!o) return;
            if (o.styleColor !== undefined && o.textFormat !== undefined && (o.style === Text.Normal || o.styleColor === wc.lastHalo)) {
                o.style = Text.Outline;
                o.styleColor = wc.haloColor;
            }
            for (let i = 0; i < o.children.length; i++) walk(o.children[i]);
        }
        walk(body.item);
        wc.lastHalo = wc.haloColor;
    }
    property color lastHalo: "transparent"
    function k0Scale(k) { return it ? Widgets.clampScale(it.type, k) : k; }
}
