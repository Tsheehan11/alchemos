// The default skin transition (Skin.component("transition")): a circle inscribes itself, a triangle
// and square inside it, the skin's ring glyphs light in turn, the sun glyph appears. A skin with no
// glyphs gets the circles alone. Ignite.qml drives it while switching to the skin.
//   p     0 → 1 over the animation      tint  the new skin's colour      r0  base radius (px)
import QtQuick

Item {
    id: tr
    property real p: 0
    property color tint: Theme.primary
    property real r0: Math.min(width, height) / 2.6
    function tc(a) { return Qt.rgba(tint.r, tint.g, tint.b, a); }
    function seg(a, b) { return Math.max(0, Math.min(1, (p - a) / (b - a))); }
    function bell(a, b) { const x = seg(a, b); return Math.sin(Math.PI * x); }
    readonly property var ring: Skin.glyphs.ring || []

    Ring { anchors.centerIn: parent; radius: tr.r0; thickness: 2; animated: false; startAngle: -90
           value: tr.seg(0, 0.35); color: tr.tint; opacity: 0.9; trackColor: "transparent" }
    Ring { anchors.centerIn: parent; radius: tr.r0 * 0.86; thickness: 1; animated: false; startAngle: 90
           value: tr.seg(0.08, 0.42); color: tr.tint; opacity: 0.6; trackColor: "transparent" }
    Sigil {
        anchors.centerIn: parent
        radius: tr.r0 * 0.86
        draw: tr.seg(0.2, 0.55)
        color: tr.tc(0.7)
    }
    Repeater {
        model: tr.ring
        delegate: SigilText {
            required property string modelData
            required property int index
            readonly property real a: (index / tr.ring.length) * 2 * Math.PI - Math.PI / 2
            readonly property real lit: tr.seg(0.3 + index * 0.07, 0.38 + index * 0.07)
            x: tr.width / 2 + Math.cos(a) * tr.r0 * 1.12 - width / 2
            y: tr.height / 2 + Math.sin(a) * tr.r0 * 1.12 - height / 2
            text: modelData
            color: tr.tc(1)
            font.pixelSize: tr.r0 * 0.16
            opacity: lit
            scale: 0.6 + 0.4 * lit + 0.5 * tr.bell(0.3 + index * 0.07, 0.5 + index * 0.07)
            glow: 1             // fixed: the halo is rendered once, opacity fades it
        }
    }
    SigilText {
        anchors.centerIn: parent
        text: Skin.glyphs.sun || ""
        color: tr.tc(1)
        font.pixelSize: tr.r0 * 0.7
        opacity: tr.seg(0.6, 0.75)
        scale: 0.7 + 0.5 * tr.seg(0.05, 0.9)
        glow: 1
    }
}
