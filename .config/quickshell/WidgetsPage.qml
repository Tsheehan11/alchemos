// Settings → WIDGETS: add, pin, close and reset desktop widgets by mouse (Widgets.qml).
// Jarvis and `qs ipc call widgets …` do the same by voice / script.
import QtQuick
import Quickshell

Column {
    id: page
    spacing: 12
    signal releaseFocus()

    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property var screenNames: ({ main: "MAIN MONITOR", diag: "SECOND MONITOR", media: "LAPTOP SCREEN" })
    readonly property var zones: [["", "LOCAL"], ["America/New_York", "NEW YORK"], ["America/Los_Angeles", "LOS ANGELES"],
                                  ["Europe/London", "LONDON"], ["Europe/Paris", "PARIS"], ["Asia/Tokyo", "TOKYO"],
                                  ["Asia/Shanghai", "SHANGHAI"], ["Australia/Sydney", "SYDNEY"], ["UTC", "UTC"]]
    readonly property var minuteSteps: [1, 2, 3, 5, 10, 15, 20, 25, 30, 45, 60, 90, 120]

    property string type: "clock"
    property string screen: "main"
    property string position: "top-right"
    property int zone: 0
    property bool analog: false
    property int minutes: 10
    property bool pinned: false
    property string size: "normal"
    readonly property var sizeList: ["small", "normal", "large", "huge"]
    property string result: ""

    function cycle(list, cur, dir) { const i = list.indexOf(cur); return list[((i < 0 ? 0 : i) + dir + list.length) % list.length]; }
    function add() {
        const p = { pinned: page.pinned, size: page.size };
        if (type === "clock") { p.analog = page.analog; if (zones[zone][0]) { p.tz = zones[zone][0]; p.label = zones[zone][1].toLowerCase().replace(/\b\w/g, c => c.toUpperCase()); } }
        if (type === "timer") p.minutes = page.minutes;
        if (type === "note") p.text = noteText.text;
        if (label.text.trim()) p.label = label.text.trim();
        const r = Widgets.add(type, screen, position, p);
        page.result = r.ok ? "✓ Added " + type + " to the " + (screenNames[r.screen] || r.monitor).toLowerCase() : "✕ " + r.error;
        if (r.ok) { noteText.text = ""; label.text = ""; }
    }

    Toggle { width: parent.width; label: "Desktop widgets"; hint: "Clocks, timers, now playing, stats and notes · \"Hey Jarvis, show a clock on monitor 2\""; checked: Theme.cfg.showWidgets; onToggled: Theme.cfg.showWidgets = !Theme.cfg.showWidgets }

    Text { text: "ADD A WIDGET"; color: Theme.dim; font.family: page.mono; font.pixelSize: 11; font.letterSpacing: 3; topPadding: 6 }
    Stepper { width: parent.width; label: "Type"; valueText: page.type.toUpperCase(); onDec: page.type = page.cycle(Widgets.types, page.type, -1); onInc: page.type = page.cycle(Widgets.types, page.type, 1) }
    Stepper { width: parent.width; label: "Screen"; hint: Roles.docked ? "" : "Undocked: the laptop has its own layout; widgets on the monitors come back when you dock"; valueText: page.screenNames[page.screen]; onDec: page.screen = page.cycle(Widgets.roles, page.screen, -1); onInc: page.screen = page.cycle(Widgets.roles, page.screen, 1) }
    Stepper { width: parent.width; label: "Position"; hint: "Where it starts; drag it anywhere after"; valueText: page.position.toUpperCase().replace("-", " "); onDec: page.position = page.cycle(Widgets.positions, page.position, -1); onInc: page.position = page.cycle(Widgets.positions, page.position, 1) }
    Stepper { visible: page.type === "clock"; width: parent.width; label: "Time zone"; valueText: page.zones[page.zone][1]; onDec: page.zone = (page.zone + page.zones.length - 1) % page.zones.length; onInc: page.zone = (page.zone + 1) % page.zones.length }
    Toggle { visible: page.type === "clock"; width: parent.width; label: "Analog"; checked: page.analog; onToggled: page.analog = !page.analog }
    Stepper { visible: page.type === "timer"; width: parent.width; label: "Minutes"; valueText: page.minutes + " MIN"; onDec: page.minutes = page.cycle(page.minuteSteps, page.minutes, -1); onInc: page.minutes = page.cycle(page.minuteSteps, page.minutes, 1) }
    Stepper { width: parent.width; label: "Size"; hint: page.type === "stats" ? "Large / huge: the full diagnostics dashboard" : "Or ⤢ on the widget"; valueText: page.size.toUpperCase(); onDec: page.size = page.cycle(page.sizeList, page.size, -1); onInc: page.size = page.cycle(page.sizeList, page.size, 1) }
    Toggle { width: parent.width; label: "Pinned"; hint: "Stays above windows instead of hiding behind them"; checked: page.pinned; onToggled: page.pinned = !page.pinned }
    Row {
        spacing: 10
        HudInput { id: label; width: 200; placeholder: "label (optional)"; maximumLength: 32; onAccepted: page.add(); onCancelled: page.releaseFocus() }
        HudInput { id: noteText; visible: page.type === "note"; width: 320; placeholder: "note text"; maximumLength: 600; onAccepted: page.add(); onCancelled: page.releaseFocus() }
        SmallButton { text: "ADD"; onClicked: page.add() }
    }
    Text { visible: page.result !== ""; text: page.result; color: page.result.startsWith("✓") ? Theme.dim : Theme.secondary; font.family: page.mono; font.pixelSize: 11 }

    Text { text: "ON SCREEN NOW · " + Widgets.items.length; color: Theme.dim; font.family: page.mono; font.pixelSize: 11; font.letterSpacing: 3; topPadding: 10 }
    Text { visible: Widgets.items.length === 0; text: "No widgets. Add one above, or ask Jarvis."; color: Theme.faint; font.family: page.mono; font.pixelSize: 12 }
    Repeater {
        model: Widgets.items
        delegate: Rectangle {
            required property var modelData
            width: page.width; height: 40
            color: rowMa.containsMouse ? Theme.p(0.07) : "transparent"
            border.color: Theme.p(0.15)
            MouseArea { id: rowMa; anchors.fill: parent; hoverEnabled: true }
            Text {
                anchors.left: parent.left; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 360; elide: Text.ElideRight
                text: modelData.type.toUpperCase() + (modelData.params.label ? " · " + modelData.params.label.toUpperCase() : "")
                      + (modelData.type === "note" && modelData.params.text ? " · " + modelData.params.text : "")
                color: Theme.text; font.family: page.mono; font.pixelSize: 13
            }
            Text {
                anchors.right: btns.left; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                readonly property var sc: Widgets.screenOfItem(modelData)
                text: sc ? (page.screenNames[Widgets.roleOf(sc)] || sc.name).split(" ")[0] + " · " + Widgets.slotOf(modelData).toUpperCase().replace("-", " ")
                         : "HIDDEN · MONITOR UNPLUGGED"
                color: Theme.dim; font.family: page.mono; font.pixelSize: 11
            }
            Row {
                id: btns
                anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                spacing: 6
                SmallButton { readonly property string sz: Widgets.sizeName(Widgets.scaleOf(modelData)); text: "⤢ " + sz.toUpperCase(); onClicked: Widgets.resize(modelData.id, page.cycle(page.sizeList, sz, 1)) }
                SmallButton { text: modelData.pinned ? "◆ PINNED" : "◇ PIN"; active: modelData.pinned; onClicked: Widgets.pin(modelData.id, !modelData.pinned) }
                SmallButton { text: "×"; onClicked: Widgets.remove(modelData.id) }
            }
        }
    }
    Row {
        spacing: 10
        topPadding: 4
        ConfirmButton { label: "RESET LAYOUT"; onConfirmed: { Widgets.reset(); page.result = "✓ Widgets back in their default spots"; } }
        ConfirmButton { label: "CLOSE ALL WIDGETS"; onConfirmed: { Widgets.clear("all"); page.result = "✓ All widgets closed"; } }
        SmallButton { text: "EDIT WIDGET TYPES"; onClicked: { Quickshell.execDetached(["kate", Quickshell.env("HOME") + "/.config/quickshell/widgets"]); LauncherState.closeAll(); } }
    }
    Text { width: parent.width; wrapMode: Text.Wrap; text: "Saved in ~/.config/quickshell/widgets.json · a new type is one QML file in quickshell/widgets/"; color: Theme.faint; font.family: page.mono; font.pixelSize: 11 }
}
