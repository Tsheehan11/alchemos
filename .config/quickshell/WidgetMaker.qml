// Widget maker: right-click the empty desktop (DesktopMenuArea) and pick a widget. It lands
// centred where you clicked (nudged off other widgets), on that screen. Timer, clock and note ask one quick question
// first; the rest are added straight away. Esc or a click outside closes it.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: mk
    required property var modelData
    screen: modelData

    readonly property var m: Widgets.maker
    visible: m !== null && m.screen === modelData.name
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "alchemos-widget-maker"
    WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    Binding { target: mk.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }   // out of screenshots (Shot.qml)

    property string step: ""                 // "" (pick a type) | timer | clock | note
    onVisibleChanged: { step = ""; if (visible) keys.forceActiveFocus(); }

    function add(type, params) { Widgets.addAt(type, params); }

    readonly property var tiles: [
        { t: "clock", g: "", n: "CLOCK", next: "clock" },
        { t: "timer", g: "", n: "TIMER", next: "timer" },
        { t: "stopwatch", g: "\u{f051b}", n: "STOPWATCH" },
        { t: "media", g: "", n: "NOW PLAYING" },
        { t: "stats", g: "", n: "SYSTEM STATS" },
        { t: "stats", g: "\u{f056e}", n: "DASHBOARD", p: { size: "huge" } },
        { t: "note", g: "", n: "NOTE", next: "note" },
        { t: "calendar", g: "\uf073", n: "AGENDA" },
        { t: "due", g: "\uf0ae", n: "DUE" },
        { t: "jarvis", g: "\uf2db", n: JarvisState.assistant },
        { t: "usage", g: "\uf080", n: "CLAUDE USAGE" },
        { t: "weather", g: "\ue30d", n: "WEATHER" },
        { t: "network", g: "\uf1eb", n: "NETWORK" },
        { t: "dj", g: "\uf001", n: "DJ DECK" },
        { t: "", g: "", n: "MORE…", settings: true }
    ]
    readonly property var minutes: [1, 3, 5, 10, 15, 20, 25, 30, 45, 60, 90, 120]
    readonly property var zones: [["", "LOCAL"], ["analog", "ANALOG"], ["America/New_York", "NEW YORK"], ["America/Los_Angeles", "LOS ANGELES"],
                                  ["Europe/London", "LONDON"], ["Europe/Paris", "PARIS"], ["Asia/Tokyo", "TOKYO"], ["Australia/Sydney", "SYDNEY"]]

    // click outside closes
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton; onClicked: Widgets.closeMaker() }
    Item { id: keys; focus: true; Keys.onEscapePressed: mk.step !== "" ? mk.step = "" : Widgets.closeMaker() }

    HudFrame {
        id: card
        width: 452
        height: (mk.step === "" ? grid.implicitHeight : (mk.step === "note" ? 96 : chips.implicitHeight)) + 34 + 22
        x: mk.m ? Math.max(12, Math.min(mk.width - width - 12, mk.m.x + 4)) : 0
        y: mk.m ? Math.max(46, Math.min(mk.height - height - 12, mk.m.y + 4)) : 0
        title: mk.step === "" ? "NEW WIDGET" : "NEW " + mk.step.toUpperCase()
        detail: "→ HERE"
        fill: Math.max(0.92, Theme.panelAlpha)
        opacity: mk.visible ? 1 : 0
        scale: mk.visible ? 1 : 0.96
        Behavior on opacity { NumberAnimation { duration: 140 } }
        Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton }   // clicks inside don't close it

        // ── step 1: pick a type ──
        Grid {
            id: grid
            visible: mk.step === ""
            columns: 4; spacing: 8
            Repeater {
                model: mk.tiles
                delegate: Rectangle {
                    required property var modelData
                    width: 100; height: 76
                    color: tileMa.containsMouse ? Theme.p(0.16) : Theme.p(0.05)
                    border.color: tileMa.containsMouse ? Theme.primary : Theme.p(0.3)
                    Column {
                        anchors.centerIn: parent
                        spacing: 6
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.g; color: modelData.settings ? Theme.dim : Theme.primary; font.family: Style.fonts.body; font.pixelSize: 22 }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.n; color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1.5 }
                    }
                    MouseArea {
                        id: tileMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (modelData.settings) { Widgets.closeMaker(); LauncherState.openSettings("WIDGETS"); }
                            else if (modelData.next) { mk.step = modelData.next; if (modelData.next === "note") noteIn.focusInput(); }
                            else mk.add(modelData.t, modelData.p || {});
                        }
                    }
                }
            }
        }

        // ── step 2: timer minutes / clock zone ──
        Flow {
            id: chips
            visible: mk.step === "timer" || mk.step === "clock"
            width: 424; spacing: 8
            Repeater {
                model: mk.step === "timer" ? mk.minutes : mk.step === "clock" ? mk.zones : []
                delegate: SmallButton {
                    required property var modelData
                    text: mk.step === "timer" ? (modelData >= 60 ? Math.floor(modelData / 60) + " H" + (modelData % 60 ? " " + modelData % 60 : "") : modelData + " MIN") : modelData[1]
                    onClicked: {
                        if (mk.step === "timer") mk.add("timer", { minutes: modelData });
                        else if (modelData[0] === "analog") mk.add("clock", { analog: true });
                        else if (modelData[0]) mk.add("clock", { tz: modelData[0], label: modelData[1].toLowerCase().replace(/\b\w/g, c => c.toUpperCase()) });
                        else mk.add("clock", {});
                    }
                }
            }
            SmallButton { text: "‹ BACK"; onClicked: mk.step = "" }
        }

        // ── step 2: note text ──
        Column {
            visible: mk.step === "note"
            spacing: 10
            HudInput {
                id: noteIn; width: 424; placeholder: "note text · Enter to add"; maximumLength: 600
                onAccepted: { mk.add("note", { text: text }); text = ""; }
                onCancelled: mk.step = ""
            }
            Row {
                spacing: 8
                SmallButton { text: "ADD"; onClicked: { mk.add("note", { text: noteIn.text }); noteIn.text = ""; } }
                SmallButton { text: "‹ BACK"; onClicked: mk.step = "" }
            }
        }
    }
}
