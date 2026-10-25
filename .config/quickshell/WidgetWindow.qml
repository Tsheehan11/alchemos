// A desktop widget: hologram card (HudFrame look) around a widgets/<Type>.qml body.
//   • Unpinned it sits under your windows and hides when they cover the screen, like the
//     clock and panels (Perf.hidden). Pinned (◆) it floats above them.
//   • Drag it anywhere, onto any monitor: WidgetMoveOverlay takes over while it moves, and on
//     release it snaps to the nearest of the nine slots there.
//   • × closes it. Hover shows the buttons. Size (small → huge) scales the whole card.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: win
    required property string modelData            // widget id
    readonly property string wid: modelData
    readonly property var it: Widgets.get(wid)
    readonly property bool pinned: it ? it.pinned === true : false
    readonly property real k: Widgets.sizes[it && it.size ? it.size : "normal"] || 1

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
    readonly property real w: Math.ceil(card.width * k)
    readonly property real h: Math.ceil(card.height * k)
    readonly property real stack: Widgets.stackOffset(wid)
    readonly property real baseX: col === 0 ? edge : col === 2 ? sw - w - edge : Math.round((sw - w) / 2)
    readonly property real baseY: row === 0 ? topInset + stack
                                : row === 2 ? sh - edge - stack - h
                                : Math.round((sh - Widgets.slotHeight(wid)) / 2) + stack
    onWChanged: Widgets.setSize(wid, w, h)
    onHChanged: Widgets.setSize(wid, w, h)
    Component.onCompleted: Widgets.setSize(wid, w, h)
    Component.onDestruction: Widgets.setSize(wid, 0, 0)

    anchors { top: true; left: true }
    margins { top: Math.max(0, baseY); left: Math.max(0, baseX) }
    implicitWidth: w
    implicitHeight: h

    // Effects clock, frozen while hidden or covered (Perf), like the reactor
    readonly property bool live: shown && Perf.live(screen) && !Perf.lite
    property real t: 0
    Binding on t { when: win.live; value: Perf.time; restoreMode: Binding.RestoreNone }

    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property bool lifted: Widgets.moving === wid

    Item {
        id: card
        transform: Scale { xScale: win.k; yScale: win.k }
        width: Math.max(160, (body.item ? body.item.implicitWidth : 200) + 28)
        height: (body.item ? body.item.implicitHeight : 80) + 34 + 14

        // entrance: fade + settle; faded while it's being moved (the ghost shows where it goes)
        opacity: 0
        states: State { name: "in"; when: win.shown; PropertyChanges { target: card; opacity: win.lifted ? 0.25 : 1 } }
        transitions: Transition { NumberAnimation { properties: "opacity"; duration: 220; easing.type: Easing.OutCubic } }

        readonly property bool done: body.item ? body.item.alert === true : false
        readonly property color accent: done ? Theme.secondary : Theme.primary

        // ── hologram glass ──
        Rectangle {
            id: glass
            anchors.fill: parent
            color: Theme.d(Math.max(0.9, Theme.panelAlpha))      // solid enough that a HUD panel behind can't show through
            border.color: Qt.rgba(card.accent.r, card.accent.g, card.accent.b, 0.4)
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

        // ── press to move (under the body, so its own buttons still work) ──
        MouseArea {
            id: dragArea
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            cursorShape: win.lifted ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            onPressed: m => Widgets.arm(win.wid, m.x * win.k, m.y * win.k)
            onReleased: Widgets.release()
            onCanceled: if (!Widgets.moving) Widgets.cancelMove()    // moving: the overlay finishes it
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
            visible: dragArea.containsMouse || pinMa.containsMouse || closeMa.containsMouse || sizeMa.containsMouse
            anchors.right: parent.right; anchors.rightMargin: 8; y: 5
            spacing: 2
            Rectangle {     // size: click to cycle small → normal → large → huge
                width: 22; height: 20; color: sizeMa.containsMouse ? Theme.p(0.18) : "transparent"
                Text { anchors.centerIn: parent; text: "⤢"; color: Theme.dim; font.family: win.mono; font.pixelSize: 12 }
                MouseArea {
                    id: sizeMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        const order = ["small", "normal", "large", "huge"];
                        Widgets.resize(win.wid, order[(order.indexOf(win.it.size || "normal") + 1) % 4]);
                    }
                }
            }
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
        Binding { target: body.item; property: "size"; value: win.it && win.it.size ? win.it.size : "normal"; when: body.item !== null }
    }
}
