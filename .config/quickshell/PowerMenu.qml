// Power menu (power button, Super + Escape, or POWER in the control center).
// ←/→ choose · Enter select · restart / shut down / log out ask to confirm · Esc closes.
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

PanelWindow {
    id: pm
    required property var modelData
    screen: modelData

    visible: LauncherState.powerOpen && Hyprland.focusedMonitor?.name === modelData.name

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-power"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    Binding { target: pm.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }   // out of screenshots (Shot.qml)

    readonly property var items: [
        { key: "lock",     label: "LOCK",      glyph: Skin.text.lockGlyph, confirm: false },
        { key: "sleep",    label: "SLEEP",     glyph: "☾", confirm: false },
        { key: "logout",   label: "LOG OUT",   glyph: "⇥", confirm: true },
        { key: "reboot",   label: "RESTART",   glyph: "⟳", confirm: true },
        { key: "shutdown", label: "SHUT DOWN", glyph: "⏻", confirm: true }
    ]
    property int sel: 4
    property string confirming: ""        // key awaiting confirmation
    property real appear: 0

    onVisibleChanged: {
        if (visible) { sel = 4; confirming = ""; appearAnim.restart(); keys.forceActiveFocus(); }
    }
    NumberAnimation { id: appearAnim; target: pm; property: "appear"; from: 0; to: 1; duration: 260; easing.type: Easing.OutCubic }

    function choose(i) {
        const it = items[i];
        if (it.confirm && confirming !== it.key) { sel = i; confirming = it.key; autoCancel.restart(); return; }
        LauncherState.closeAll();
        if (it.key === "lock") LockState.requestLock();
        else if (it.key === "sleep") Quickshell.execDetached(["stark-govee", "suspend"]);
        else LockState.power(it.key);
    }
    Timer { id: autoCancel; interval: 8000; onTriggered: pm.confirming = "" }

    Rectangle {
        anchors.fill: parent
        color: Theme.back(0.8)
        opacity: pm.appear
        MouseArea { anchors.fill: parent; onClicked: LauncherState.closeAll() }
    }

    Item {
        id: keys
        focus: true
        Keys.onPressed: function(e) {
            if (e.key === Qt.Key_Escape) { if (pm.confirming) pm.confirming = ""; else LauncherState.closeAll(); }
            else if (e.key === Qt.Key_Left) { pm.sel = Math.max(0, pm.sel - 1); pm.confirming = ""; }
            else if (e.key === Qt.Key_Right || e.key === Qt.Key_Tab) { pm.sel = Math.min(pm.items.length - 1, pm.sel + 1); pm.confirming = ""; }
            else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) pm.choose(pm.sel);
            else return;
            e.accepted = true;
        }
    }

    Column {
        anchors.centerIn: parent
        spacing: 34
        opacity: pm.appear
        scale: 0.96 + 0.04 * pm.appear

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: pm.confirming ? "CONFIRM // " + pm.items[pm.sel].label + "?" : "POWER // SELECT"
            color: pm.confirming ? Theme.secondary : Theme.primary
            font.family: Style.fonts.display; font.pixelSize: 15; font.letterSpacing: 6
        }

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 26
            Repeater {
                model: pm.items
                delegate: Item {
                    id: tile
                    required property var modelData
                    required property int index
                    readonly property bool on: pm.sel === index
                    readonly property bool asking: pm.confirming === modelData.key
                    width: 150; height: 176

                    Ring {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 0
                        radius: 60; thickness: tile.on ? 3 : 1; value: 1
                        dashed: tile.asking; dash: [5, 4]
                        color: tile.asking ? Theme.secondary : (tile.on ? Theme.primary : Theme.p(0.45))
                        trackColor: "transparent"
                        RotationAnimation on rotation { running: tile.asking && pm.visible; from: 0; to: 360; duration: 3000; loops: Animation.Infinite }
                    }
                    // engraved skins: an engraved, graduated ring that draws itself in as the menu appears
                    // and turns on the chosen tile (the legacy menu is as it was)
                    Ring {
                        visible: Style.engraved
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 63 - width / 2      // concentric with the tile ring and disc (centre y 63)
                        radius: 70; thickness: 5; value: pm.appear; animated: false
                        dashed: true; dash: [0.25, 2.6]
                        color: tile.asking ? Theme.s(0.7) : Theme.p(tile.on ? 0.6 : 0.22)
                        trackColor: "transparent"
                        RotationAnimation on rotation { running: tile.on && pm.visible && Style.engraved; from: 0; to: 360; duration: 24000; loops: Animation.Infinite }
                    }
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 13
                        width: 100; height: 100; radius: 50
                        color: tile.asking ? Theme.s(0.22) : (tile.on ? Theme.p(0.22) : Theme.d(0.9))
                        scale: tile.on ? 1.06 : 1
                        Behavior on scale { NumberAnimation { duration: 120 } }
                        Text {
                            anchors.centerIn: parent
                            text: tile.modelData.glyph
                            color: tile.asking ? Theme.secondary : (tile.on ? Theme.text : Theme.textSoft)
                            font.family: Style.fonts.glyph; font.pixelSize: 40
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 140
                        text: tile.asking ? "CLICK AGAIN" : tile.modelData.label
                        color: tile.asking ? Theme.secondary : (tile.on ? Theme.text : Theme.textSoft)
                        font.family: Style.fonts.label; font.pixelSize: 13; font.letterSpacing: 3
                    }
                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onEntered: if (!pm.confirming) pm.sel = tile.index
                        onClicked: pm.choose(tile.index)
                    }
                }
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: pm.confirming ? "ENTER CONFIRM   ·   ESC CANCEL" : "← → CHOOSE   ·   ENTER SELECT   ·   ESC CLOSE"
            color: Theme.dim
            font.family: Style.fonts.label; font.pixelSize: 10; font.letterSpacing: 3
        }
    }
}
