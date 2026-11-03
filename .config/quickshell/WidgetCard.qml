// One desktop widget on a WidgetSurface: a projected hologram (HoloFrame, no solid card) around a
// widgets/<Type>.qml body, placed in its slot (stacked with others in the same slot).
//   • Drag it: the surface takes the whole screen for the drag, the card follows the pointer
//     and snaps to the nearest slot on release; carry it on to another monitor and it lands
//     there, in the slot under the cursor.
//   • ⤢ size, ◇ pin above windows, × close (on hover).
import QtQuick
import Quickshell

Item {
    id: wc
    required property string wid
    required property var surface                  // the WidgetSurface it's drawn on
    readonly property var it: Widgets.get(wid)
    readonly property bool pinned: it ? it.pinned === true : false
    readonly property real k: Widgets.sizes[it && it.size ? it.size : "normal"] || 1
    readonly property string mono: "JetBrainsMono Nerd Font"

    // ── where it goes (screen pixels) ──
    readonly property int edge: 28
    readonly property int topInset: 34 + 20                // under the bar
    readonly property real sw: surface.width
    readonly property real sh: surface.height
    readonly property string pos: it ? it.position : "top-right"
    readonly property int col: pos.endsWith("left") ? 0 : pos.endsWith("right") ? 2 : 1
    readonly property int row: pos.startsWith("top") ? 0 : pos.startsWith("bottom") ? 2 : 1
    readonly property real stack: Widgets.stackOffset(wid)
    readonly property real baseX: col === 0 ? edge : col === 2 ? sw - width - edge : Math.round((sw - width) / 2)
    readonly property real baseY: row === 0 ? topInset + stack
                                : row === 2 ? sh - edge - stack - height
                                : Math.round((sh - Widgets.slotHeight(wid)) / 2) + stack

    width: Math.ceil(card.width * k)
    height: Math.ceil(card.height * k)
    onWidthChanged: Widgets.setSize(wid, width, height)
    onHeightChanged: Widgets.setSize(wid, width, height)
    Component.onCompleted: Widgets.setSize(wid, width, height)
    Component.onDestruction: Widgets.setSize(wid, 0, 0)

    property bool dragging: false
    property real dragX: 0
    property real dragY: 0
    x: dragging ? dragX : baseX
    y: dragging ? dragY : baseY
    Behavior on x { enabled: !wc.dragging; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    Behavior on y { enabled: !wc.dragging; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    z: dragging ? 10 : 0

    // its share of the surface's input region
    property Region region: Region { item: wc }

    readonly property bool live: surface.live
    readonly property bool done: body.item ? body.item.alert === true : false
    readonly property color accent: done ? Theme.secondary : Theme.primary
    readonly property bool wantsKeyboard: body.item ? body.item.wantsKeyboard === true : false

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
            strong: wc.dragging || dragArea.containsMouse
            fillAlpha: wc.pinned ? 0.8 : 0.66          // pinned ones sit over windows: a little more glass behind the text
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
                wc.dragX = wc.x; wc.dragY = wc.y;
                wc.dragging = true;
                wc.surface.grab(wc);                   // whole screen takes input until release
            }
            onPositionChanged: m => {
                if (!pressed) return;
                const p = mapToItem(null, m.x, m.y);
                if (!moved && Math.hypot(p.x - px, p.y - py) < 6) return;
                moved = true;
                wc.dragX = Math.max(-wc.width / 2, Math.min(wc.sw - wc.width / 2, sx + p.x - px));
                wc.dragY = Math.max(0, Math.min(wc.sh - wc.height / 2, sy + p.y - py));
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
                    const s = wc.surface.scr;
                    Widgets.drop(wc.wid, s, Widgets.slotAt(s, wc.dragX + wc.width / 2, wc.dragY + wc.height / 2), wc.width, wc.height);
                }
                wc.dragging = false;
                wc.surface.release(wc);
            }
            onDoubleClicked: if (body.item && body.item.doubleClicked) body.item.doubleClicked()
        }

        // ── header ──
        Text {
            x: 26; y: 10
            opacity: Math.max(0, card.boot * 2 - 1)
            width: card.width - 40 - (buttons.visible ? buttons.width : 0)
            elide: Text.ElideRight
            text: (body.item ? body.item.title : (wc.it ? wc.it.type.toUpperCase() : ""))
            color: wc.accent
            font.family: wc.mono; font.pixelSize: 10; font.letterSpacing: 3
        }
        Text {
            visible: !buttons.visible
            opacity: Math.max(0, card.boot * 2 - 1)
            anchors.right: parent.right; anchors.rightMargin: 14; y: 10
            text: (wc.pinned ? "◆ " : "") + (body.item ? body.item.detail : "")
            color: Theme.dim
            font.family: wc.mono; font.pixelSize: 10; font.letterSpacing: 2
        }
        Row {
            id: buttons
            visible: !wc.dragging && (dragArea.containsMouse || pinMa.containsMouse || closeMa.containsMouse || sizeMa.containsMouse)
            anchors.right: parent.right; anchors.rightMargin: 8; y: 5
            spacing: 2
            Rectangle {     // size: small → normal → large → huge
                width: 22; height: 20; color: "transparent"; border.width: sizeMa.containsMouse ? 1 : 0; border.color: Theme.p(0.5)
                Text { anchors.centerIn: parent; text: "⤢"; color: Theme.dim; font.family: wc.mono; font.pixelSize: 12 }
                MouseArea {
                    id: sizeMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        const order = ["small", "normal", "large", "huge"];
                        Widgets.resize(wc.wid, order[(order.indexOf(wc.it.size || "normal") + 1) % 4]);
                    }
                }
            }
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
        }
        Binding { target: body.item; property: "widget"; value: wc.it; when: body.item !== null }
        Binding { target: body.item; property: "active"; value: wc.surface.visible; when: body.item !== null }
        Binding { target: body.item; property: "live"; value: wc.live; when: body.item !== null }
        Binding { target: body.item; property: "t"; value: wc.surface.t; when: body.item !== null }
        Binding { target: body.item; property: "size"; value: wc.it && wc.it.size ? wc.it.size : "normal"; when: body.item !== null }
    }
}
