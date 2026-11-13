// Shutter effect over what was just captured (Shot.qml): a flash, brackets snapping onto the box and a
// scan line sweeping down it, on every monitor the shot covers. Click-through, mapped only while it plays
// (~0.7 s) and without Hyprland's fade (hypr/stark/rules.lua), so it never sits over a fullscreen game.
// Battery saver (Shot.calm): no effect at all.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: fx
    required property var modelData
    screen: modelData

    property var box: null              // { x, y, w, h } in this screen's coordinates
    property real t: 0                  // 0 → 1 over the effect
    visible: box !== null

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "alchemos-shot-flash"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    mask: Region {}

    readonly property color c: Theme.primary

    Connections {
        target: Shot
        function onSerialChanged() {
            const r = Shot.last.ok ? Shot.rectOn(fx.modelData.name) : null;
            if (!r || Shot.calm) return;
            fx.box = r;
            run.restart();
        }
    }
    NumberAnimation {
        id: run
        target: fx; property: "t"; from: 0; to: 1; duration: 700
        onFinished: fx.box = null
    }

    function ease(a, b) { return Math.max(0, Math.min(1, (fx.t - a) / (b - a))); }   // 0 → 1 between t = a and b

    Item {
        id: area
        visible: fx.box !== null
        x: fx.box ? fx.box.x : 0; y: fx.box ? fx.box.y : 0
        width: fx.box ? fx.box.w : 0; height: fx.box ? fx.box.h : 0

        // Flash: bright at once, gone by a third of the way
        Rectangle {
            anchors.fill: parent
            color: Qt.lighter(fx.c, 1.6)
            opacity: 0.34 * Math.pow(1 - fx.ease(0, 0.35), 2)
        }
        // Outline
        Rectangle {
            anchors.fill: parent
            color: "transparent"
            border.color: fx.c; border.width: 2
            opacity: 0.9 * (1 - fx.ease(0.45, 1))
        }
        // Brackets: start 22 px out, snap onto the corners
        Repeater {
            model: 4
            delegate: Item {
                required property int index
                readonly property real off: 22 * Math.pow(1 - fx.ease(0, 0.28), 3)
                readonly property bool atRight: index % 2 === 1
                readonly property bool atBottom: index >= 2
                width: 30; height: 30
                x: atRight ? area.width - width + off : -off
                y: atBottom ? area.height - height + off : -off
                opacity: 1 - fx.ease(0.6, 1)
                Rectangle { width: 30; height: 3; color: fx.c; y: parent.atBottom ? 27 : 0 }
                Rectangle { width: 3; height: 30; color: fx.c; x: parent.atRight ? 27 : 0 }
            }
        }
        // Scan line with a fading trail above it
        Item {
            width: parent.width
            height: Math.min(80, parent.height)
            y: fx.ease(0.05, 0.75) * (area.height + height) - height
            opacity: 1 - fx.ease(0.7, 0.85)
            clip: false
            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 1; color: Qt.rgba(fx.c.r, fx.c.g, fx.c.b, 0.28) }
                }
            }
            Rectangle { width: parent.width; height: 2; anchors.bottom: parent.bottom; color: Qt.lighter(fx.c, 1.4) }
        }
        // Readout on the box's top edge
        Rectangle {
            visible: area.width > 160 && area.height > 60
            x: 10; y: 10
            width: readout.implicitWidth + 16; height: 22
            color: Theme.d(0.85)
            border.color: fx.c; border.width: 1
            opacity: fx.ease(0.08, 0.2) * (1 - fx.ease(0.75, 1))
            Text {
                id: readout
                anchors.centerIn: parent
                text: "CAPTURED · " + (Shot.last.width || 0) + "×" + (Shot.last.height || 0)
                color: fx.c; font.family: Style.fonts.label; font.pixelSize: 11; font.letterSpacing: 2
            }
        }
    }
}
