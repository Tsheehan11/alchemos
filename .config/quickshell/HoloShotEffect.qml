// The base screenshot effect (Skin.component "shotEffect"; LEGACY uses it): the hologram shutter.
// A flash, brackets snapping onto the box and a scan line sweeping down it, plus a CAPTURED · W×H
// readout. Moved here unchanged from ShotFlash.qml (which now hosts whichever skin's effect).
//
// Contract for any skin's shotEffect (ShotFlash.qml sets these; it fills the screen):
//   box         { x, y, w, h }: the part of the shot on this screen, in its coordinates
//   t           0 → 1 over the effect (durationMs, or calmMs in battery saver)
//   last        Shot.last: path, width, height, mode, geom …
//   frame       the frozen frame: { source (file URL of the saved PNG), clip (Qt.rect: this screen's part
//               of the PNG, in its pixels) }; draw it under the effect to play on the captured image
//               (the capture is already saved: nothing here can end up in it or delay it)
//   calm        battery saver
//   main        (optional property) true on the screen holding most of the shot: one-off marks go there
//   durationMs  how long it plays;  calmMs  how long in battery saver (0 = nothing at all)
import QtQuick

Item {
    id: eff
    property var box: null
    property real t: 0
    property var last: ({})
    property var frame: null
    property bool calm: false
    property int durationMs: 700
    property int calmMs: 0
    readonly property color c: Theme.primary

    function ease(a, b) { return Math.max(0, Math.min(1, (eff.t - a) / (b - a))); }   // 0 → 1 between t = a and b

    Item {
        id: area
        visible: eff.box !== null
        x: eff.box ? eff.box.x : 0; y: eff.box ? eff.box.y : 0
        width: eff.box ? eff.box.w : 0; height: eff.box ? eff.box.h : 0

        // Flash: bright at once, gone by a third of the way
        Rectangle {
            anchors.fill: parent
            color: Qt.lighter(eff.c, 1.6)
            opacity: 0.34 * Math.pow(1 - eff.ease(0, 0.35), 2)
        }
        // Outline
        Rectangle {
            anchors.fill: parent
            color: "transparent"
            border.color: eff.c; border.width: 2
            opacity: 0.9 * (1 - eff.ease(0.45, 1))
        }
        // Brackets: start 22 px out, snap onto the corners
        Repeater {
            model: 4
            delegate: Item {
                required property int index
                readonly property real off: 22 * Math.pow(1 - eff.ease(0, 0.28), 3)
                readonly property bool atRight: index % 2 === 1
                readonly property bool atBottom: index >= 2
                width: 30; height: 30
                x: atRight ? area.width - width + off : -off
                y: atBottom ? area.height - height + off : -off
                opacity: 1 - eff.ease(0.6, 1)
                Rectangle { width: 30; height: 3; color: eff.c; y: parent.atBottom ? 27 : 0 }
                Rectangle { width: 3; height: 30; color: eff.c; x: parent.atRight ? 27 : 0 }
            }
        }
        // Scan line with a fading trail above it
        Item {
            width: parent.width
            height: Math.min(80, parent.height)
            y: eff.ease(0.05, 0.75) * (area.height + height) - height
            opacity: 1 - eff.ease(0.7, 0.85)
            clip: false
            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 1; color: Qt.rgba(eff.c.r, eff.c.g, eff.c.b, 0.28) }
                }
            }
            Rectangle { width: parent.width; height: 2; anchors.bottom: parent.bottom; color: Qt.lighter(eff.c, 1.4) }
        }
        // Readout on the box's top edge
        Rectangle {
            visible: area.width > 160 && area.height > 60
            x: 10; y: 10
            width: readout.implicitWidth + 16; height: 22
            color: Theme.d(0.85)
            border.color: eff.c; border.width: 1
            opacity: eff.ease(0.08, 0.2) * (1 - eff.ease(0.75, 1))
            Text {
                id: readout
                anchors.centerIn: parent
                text: "CAPTURED · " + (eff.last.width || 0) + "×" + (eff.last.height || 0)
                color: eff.c; font.family: Style.fonts.label; font.pixelSize: 11; font.letterSpacing: 2
            }
        }
    }
}
