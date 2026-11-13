// Radial launcher (Super+Space): apps drift out of the mouse cursor in curving branches, consecutive
// pairs sharing a branch. The apps come from Settings → LAUNCHER (LauncherApps.qml). How it looks is
// the skin's (Skin.component("launcherLook"); the base one is the hologram flow cloud,
// HoloLauncherLook.qml); this file owns the behaviour: keys, geometry, the spiral open, the hit areas.
// Keys: arrows/Tab cycle · Enter launch · 1–9 / 0 launch directly
//       start typing a letter → app search · Esc closes
import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

PanelWindow {
    id: win
    required property var modelData
    screen: modelData

    // Show on whichever screen the cursor is on
    readonly property bool cursorHere:
        LauncherState.cx >= modelData.x && LauncherState.cx < modelData.x + modelData.width &&
        LauncherState.cy >= modelData.y && LauncherState.cy < modelData.y + modelData.height
    visible: LauncherState.open && cursorHere

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "alchemos-launcher"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    Binding { target: win.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }   // out of screenshots (Shot.qml)

    readonly property color cyan: Theme.primary
    readonly property color amber: Theme.secondary

    // Apps in launch order. Consecutive pairs form one branch: the first sits
    // close to the core, the second flows out from it.
    readonly property var apps: LauncherApps.list
    readonly property int branchCount: Math.ceil(apps.length / 2)
    function branchOf(i) { return Math.floor(i / 2); }
    function tierOf(i) { return i % 2; }              // 0 = near the core, 1 = flows outward
    onAppsChanged: if (selected >= apps.length) selected = 0

    // Layout: branches fan out evenly; each related app sits further out and
    // a little further round, so every branch curves the same way.
    // Past 6 branches there's no room for the jitter — neighbours would touch.
    readonly property var jitter: [0, 7, -5, 5, -6]
    function branchAngle(b) { return -90 + b * (360 / branchCount) + (branchCount <= 6 ? jitter[b % jitter.length] : 0); }
    function baseAngle(i) { return branchAngle(branchOf(i)) + (tierOf(i) === 1 ? 18 : 0); }
    function baseRadius(i) { return tierOf(i) === 1 ? 325 : 172; }
    function nodeSize(i) { return tierOf(i) === 1 ? 76 : 94; }

    property int selected: 0
    property real spread: 0
    property real t: 0            // drives the gentle floating drift

    function close() { LauncherState.open = false }
    function launch(i) {
        if (LauncherApps.launch(apps[i])) close();
    }
    readonly property var current: apps[selected] || ({ name: "", available: true })

    onVisibleChanged: {
        if (visible) {
            selected = 0;
            spread = 0;
            openAnim.restart();
            if (look.item && typeof look.item.opened === "function") look.item.opened();
            core.forceActiveFocus();
        }
    }

    NumberAnimation {
        id: openAnim
        target: win; property: "spread"
        from: 0; to: 1
        duration: look.item && look.item.openMs !== undefined ? look.item.openMs : 700
        easing.type: look.item && look.item.openEasing !== undefined ? look.item.openEasing : Easing.OutBack
        easing.overshoot: 1.1
    }
    NumberAnimation on t {
        running: win.visible
        from: 0; to: 2 * Math.PI * 20; duration: 160000
        loops: Animation.Infinite
    }

    // Dim backdrop — click anywhere outside to close
    Rectangle {
        anchors.fill: parent
        color: Theme.back(0.55)
        opacity: Math.min(1, win.spread * 1.5)
        MouseArea { anchors.fill: parent; onClicked: win.close() }
    }

    Item {
        id: core
        width: 880; height: 880
        readonly property real cx: width / 2
        readonly property real cy: height / 2

        // Centered on the cursor, nudged inward near screen edges
        x: Math.max(0, Math.min(parent.width - width, (LauncherState.cx - win.modelData.x) - cx))
        y: Math.max(0, Math.min(parent.height - height, (LauncherState.cy - win.modelData.y) - cy))
        focus: true

        // Node positions: spin out along the spiral, then float gently
        function ang(i) { return (win.baseAngle(i) - (1 - win.spread) * 140) * Math.PI / 180; }
        function rad(i) { return win.baseRadius(i) * Math.max(0, win.spread); }
        function nx(i) { return cx + Math.cos(ang(i)) * rad(i) + 8 * Math.sin(win.t * 0.8 + i * 1.7); }
        function ny(i) { return cy + Math.sin(ang(i)) * rad(i) + 8 * Math.cos(win.t * 0.6 + i * 2.3); }

        Keys.onPressed: function(event) {
            const n = win.apps.length;
            if (n === 0 && event.key !== Qt.Key_Escape) return;
            if (event.key === Qt.Key_Escape) {
                win.close();
            } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Down || event.key === Qt.Key_Tab) {
                win.selected = (win.selected + 1) % n;
            } else if (event.key === Qt.Key_Left || event.key === Qt.Key_Up || event.key === Qt.Key_Backtab) {
                win.selected = (win.selected - 1 + n) % n;
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                win.launch(win.selected);
            } else if (event.key >= Qt.Key_1 && event.key <= Qt.Key_9 && event.key - Qt.Key_1 < n) {
                win.launch(event.key - Qt.Key_1);
            } else if (event.key === Qt.Key_0 && n >= 10) {
                win.launch(9);
            } else if (event.text.length === 1 && /[a-zA-Z]/.test(event.text)) {
                LauncherState.openSearch(event.text);   // typing → search
            } else {
                return;
            }
            event.accepted = true;
        }

        // ── The look (the skin's) ──
        Loader {
            id: look
            anchors.fill: parent
            readonly property url want: Skin.component("launcherLook")
            onWantChanged: setSource(want, { win: win, core: core })
            Component.onCompleted: setSource(want, { win: win, core: core })
        }

        // ── Hit areas over the app nodes: hover selects, click launches ──
        Repeater {
            model: win.apps.length
            delegate: MouseArea {
                required property int index
                readonly property int size: win.nodeSize(index)
                width: size; height: size
                x: core.nx(index) - width / 2
                y: core.ny(index) - height / 2
                z: 30
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onEntered: win.selected = index
                onClicked: win.launch(index)
            }
        }
    }
}
