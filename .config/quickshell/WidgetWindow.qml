// A desktop widget: hologram card (HudFrame look) around a widgets/<Type>.qml body.
//   • Unpinned it sits under your windows and hides when they cover the screen, like the
//     clock and panels (Perf.hidden). Pinned (📌) it floats above them.
//   • Drag it anywhere; on release it snaps to the nearest of the nine slots.
//   • × closes it. Hover shows the buttons.
// While dragging, the pointer position comes from Hyprland (hyprctl cursorpos, ~30×/s, only
// during a drag): pointer coordinates inside a surface that is itself moving lag behind,
// and growing the window to full screen dropped the pointer grab.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

PanelWindow {
    id: win
    required property string modelData            // widget id
    readonly property string wid: modelData
    readonly property var it: Widgets.get(wid)
    readonly property bool pinned: it ? it.pinned === true : false

    readonly property bool shown: it !== null && Theme.cfg.showWidgets
        && (pinned ? !Perf.locked && !(GameMode.quiet && Perf.gameScreens[screen?.name] === true)
                   : !Perf.hidden(screen, "widgets"))
    visible: shown

    WlrLayershell.layer: pinned ? WlrLayer.Top : WlrLayer.Bottom
    WlrLayershell.namespace: "stark-widget"
    WlrLayershell.keyboardFocus: body.item && body.item.wantsKeyboard ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    // ── where it goes ──
    readonly property int edge: 28
    readonly property int topInset: 34 + 20             // under the bar
    readonly property real sw: screen ? screen.width : 1920
    readonly property real sh: screen ? screen.height : 1080
    readonly property string pos: it ? it.position : "top-right"
    readonly property int col: pos.endsWith("left") ? 0 : pos.endsWith("right") ? 2 : 1
    readonly property int row: pos.startsWith("top") ? 0 : pos.startsWith("bottom") ? 2 : 1
    readonly property real stack: Widgets.stackOffset(wid)
    readonly property real baseX: col === 0 ? edge : col === 2 ? sw - card.width - edge : Math.round((sw - card.width) / 2)
    readonly property real baseY: row === 0 ? topInset + stack
                                : row === 2 ? sh - edge - stack - card.height
                                : Math.round((sh - Widgets.slotHeight(wid)) / 2) + stack

    property bool dragging: false
    property real dragX: 0
    property real dragY: 0

    anchors { top: true; left: true }
    margins { top: dragging ? dragY : baseY; left: dragging ? dragX : baseX }
    implicitWidth: card.width
    implicitHeight: card.height

    // ── drag: follow the global cursor ──
    property real grabX: 0                // where in the card it was grabbed
    property real grabY: 0
    property real startGX: -1             // cursor at press (global), to tell a click from a drag
    property real startGY: -1
    Process {
        id: cursor
        command: ["hyprctl", "cursorpos", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                let c;
                try { c = JSON.parse(text); } catch (e) { return; }
                if (!dragTick.running) return;
                const sx = c.x - (win.screen ? win.screen.x : 0), sy = c.y - (win.screen ? win.screen.y : 0);
                if (win.startGX < 0) { win.startGX = c.x; win.startGY = c.y; return; }
                if (!win.dragging && Math.hypot(c.x - win.startGX, c.y - win.startGY) < 6) return;
                win.dragX = Math.max(0, Math.min(win.sw - card.width, sx - win.grabX));
                win.dragY = Math.max(0, Math.min(win.sh - card.height, sy - win.grabY));
                win.dragging = true;
            }
        }
    }
    Timer { id: dragTick; interval: 33; repeat: true; triggeredOnStart: true; onTriggered: if (!cursor.running) cursor.running = true }

    // Effects clock, frozen while hidden or covered (Perf), like the reactor
    readonly property bool live: shown && Perf.live(screen) && !Perf.lite
    property real t: 0
    Binding on t { when: win.live; value: Perf.time; restoreMode: Binding.RestoreNone }

    readonly property string mono: "JetBrainsMono Nerd Font"

    Item {
        id: card
        width: Math.max(160, (body.item ? body.item.implicitWidth : 200) + 28)
        height: (body.item ? body.item.implicitHeight : 80) + 34 + 14
        onHeightChanged: Widgets.setHeight(win.wid, height)
        Component.onCompleted: Widgets.setHeight(win.wid, height)

        // entrance: fade + settle
        opacity: 0
        scale: 0.94
        Component.onDestruction: Widgets.setHeight(win.wid, 0)
        states: State { name: "in"; when: win.shown; PropertyChanges { target: card; opacity: 1; scale: 1 } }
        transitions: Transition { NumberAnimation { properties: "opacity,scale"; duration: 260; easing.type: Easing.OutCubic } }

        readonly property bool done: body.item ? body.item.alert === true : false
        readonly property color accent: done ? Theme.secondary : Theme.primary

        // ── hologram glass ──
        Rectangle {
            id: glass
            anchors.fill: parent
            color: Theme.d(Math.max(0.72, Theme.panelAlpha - 0.1))
            border.color: Qt.rgba(card.accent.r, card.accent.g, card.accent.b, win.dragging ? 0.8 : 0.4)
            border.width: 1
            clip: true
            // sweeping scan band, only while effects run on this screen
            Rectangle {
                visible: win.live
                width: parent.width; height: 38
                y: ((win.t * 0.35) % 1) * (glass.height + 76) - 38
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: Qt.rgba(card.accent.r, card.accent.g, card.accent.b, 0.07) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }
            // left edge bar
            Rectangle { width: 2; height: parent.height; color: card.accent; opacity: card.done ? 0.5 + 0.5 * Math.abs(Math.sin(win.t * 4)) : 0.75 }
        }
        Repeater {      // corner brackets
            model: 4
            delegate: Item {
                required property int index
                width: 12; height: 12
                x: index % 2 === 0 ? -3 : card.width - 9
                y: index < 2 ? -3 : card.height - 9
                Rectangle { width: 12; height: 2; color: card.accent; y: index < 2 ? 0 : 10 }
                Rectangle { width: 2; height: 12; color: card.accent; x: index % 2 === 0 ? 0 : 10 }
            }
        }

        // ── drag / snap (under the body, so its own buttons still work) ──
        MouseArea {
            id: dragArea
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            cursorShape: win.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            preventStealing: true
            onPressed: m => {
                win.grabX = m.x; win.grabY = m.y;
                win.dragX = win.baseX; win.dragY = win.baseY;
                win.startGX = -1; win.startGY = -1;
                dragTick.start();
            }
            onReleased: {
                dragTick.stop();
                if (!win.dragging) return;
                const cx = win.dragX + card.width / 2, cy = win.dragY + card.height / 2;
                const c = cx < win.sw / 3 ? "left" : cx > win.sw * 2 / 3 ? "right" : "";
                const r = cy < win.sh / 3 ? "top" : cy > win.sh * 2 / 3 ? "bottom" : "";
                const p = (r && c) ? r + "-" + c : (r || c || "center");
                win.dragging = false;
                if (p !== win.pos) Widgets.move(win.wid, "-", p);
            }
            onCanceled: { dragTick.stop(); win.dragging = false; }
            onDoubleClicked: if (body.item && body.item.doubleClicked) body.item.doubleClicked()
        }

        // ── header ──
        Text {
            x: 14; y: 10
            width: card.width - 28 - (buttons.visible ? buttons.width : 0)
            elide: Text.ElideRight
            text: (body.item ? body.item.title : (win.it ? win.it.type.toUpperCase() : ""))
            color: card.accent
            font.family: win.mono; font.pixelSize: 10; font.letterSpacing: 3
        }
        Text {
            visible: !buttons.visible
            anchors.right: parent.right; anchors.rightMargin: 14; y: 10
            text: (win.pinned ? "◆ " : "") + (body.item ? body.item.detail : "")
            color: Theme.dim
            font.family: win.mono; font.pixelSize: 10; font.letterSpacing: 2
        }
        Row {
            id: buttons
            visible: dragArea.containsMouse || pinMa.containsMouse || closeMa.containsMouse
            anchors.right: parent.right; anchors.rightMargin: 8; y: 5
            spacing: 2
            Rectangle {
                width: 22; height: 20; color: pinMa.containsMouse ? Theme.p(0.18) : "transparent"
                Text { anchors.centerIn: parent; text: win.pinned ? "◆" : "◇"; color: win.pinned ? Theme.secondary : Theme.dim; font.family: win.mono; font.pixelSize: 12 }
                MouseArea { id: pinMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Widgets.pin(win.wid, !win.pinned) }
            }
            Rectangle {
                width: 22; height: 20; color: closeMa.containsMouse ? Theme.s(0.25) : "transparent"
                Text { anchors.centerIn: parent; text: "×"; color: closeMa.containsMouse ? Theme.text : Theme.dim; font.family: win.mono; font.pixelSize: 15 }
                MouseArea { id: closeMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Widgets.remove(win.wid) }
            }
        }

        // ── body: widgets/<Type>.qml ──
        Loader {
            id: body
            x: 14; y: 34
            source: win.it ? Widgets.source(win.it.type) : ""
        }
        Binding { target: body.item; property: "widget"; value: win.it; when: body.item !== null }
        Binding { target: body.item; property: "active"; value: win.shown; when: body.item !== null }
        Binding { target: body.item; property: "live"; value: win.live; when: body.item !== null }
        Binding { target: body.item; property: "t"; value: win.t; when: body.item !== null }
    }
}
