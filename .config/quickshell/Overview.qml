// Workspace overview (Super + Tab). How it looks is the skin's: Skin.component("carouselStage") (floor,
// header) and ("carouselPanel") (each workspace; the base ones are the hologram, HoloCarousel*.qml).
// Each screen's workspaces stand in a full 3D ring that you look down onto —
// every panel stays visible, and the ring turns endlessly in either direction.
// Docked: each monitor's 3. Laptop only: all of them.
// ←/→ or scroll to turn · click a panel to bring it round · Enter / click the
// front panel to go there · 1–9 jumps straight to one · Esc closes.
import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import "Hypr.js" as Hypr

PanelWindow {
    id: ov
    required property var modelData
    screen: modelData

    readonly property bool focusedHere: Hyprland.focusedMonitor?.name === modelData.name
    visible: LauncherState.overviewOpen

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-overview"
    WlrLayershell.keyboardFocus: focusedHere ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    Binding { target: ov.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }   // out of screenshots (Shot.qml)

    readonly property var ids: OverviewData.workspacesFor(modelData)
    readonly property int n: ids.length

    // Ring position. `target` counts turns without wrapping, so turning past the
    // last workspace keeps spinning the same way and comes round to the first.
    property int target: 0
    property real pos: target
    Behavior on pos { NumberAnimation { duration: 480; easing.type: Easing.OutCubic } }
    readonly property int frontIndex: n > 0 ? ((target % n) + n) % n : 0
    function turn(d) { target += d; }
    function bringToFront(i) {
        let d = i - frontIndex;
        if (d > n / 2) d -= n;
        if (d < -n / 2) d += n;
        target += d;
    }

    property real appear: 0
    NumberAnimation { id: appearAnim; target: ov; property: "appear"; from: 0; to: 1; duration: 450; easing.type: Easing.OutCubic }

    onVisibleChanged: {
        if (visible) {
            const i = ids.indexOf(OverviewData.activeOn(modelData.name));
            target = i >= 0 ? i : 0;
            appearAnim.restart();
            if (focusedHere) keys.forceActiveFocus();
        }
    }

    function go(i) {
        if (i < 0 || i >= n) return;
        goTo(ids[i]);
    }
    function goTo(id) {
        if (OverviewData.isPeeked(id)) Peek.go(id);   // its windows back first, then there
        else Hyprland.dispatch(Hypr.workspace(id));
        LauncherState.closeAll();
    }

    // Geometry: panels sit on an ellipse (a ring seen from above)
    readonly property real step: n > 0 ? 360 / n : 0               // degrees between panels
    readonly property real ringR: width * (n <= 3 ? 0.31 : 0.37)   // half-width of the ring
    readonly property real ringRy: height * (n <= 3 ? 0.13 : 0.17) // how "deep" the ring looks
    readonly property real panelW: width * (n <= 3 ? 0.34 : 0.27)
    readonly property real cx: width / 2
    readonly property real cy: height / 2 - 10

    // ── Backdrop ──
    Rectangle {
        anchors.fill: parent
        color: Theme.back(0.86)
        opacity: ov.appear
        MouseArea { anchors.fill: parent; onClicked: LauncherState.closeAll(); onWheel: w => ov.turn(w.angleDelta.y < 0 ? 1 : -1) }
    }

    // ── Stage: floor and header (the skin's) ──
    Loader {
        id: stage
        anchors.fill: parent
        readonly property url want: Skin.component("carouselStage")
        onWantChanged: setSource(want, { ov: ov })
        Component.onCompleted: setSource(want, { ov: ov })
    }

    Item {
        id: keys
        focus: ov.focusedHere
        Keys.onPressed: function(e) {
            if (e.key === Qt.Key_Escape) LauncherState.closeAll();
            else if (e.key === Qt.Key_Left || e.key === Qt.Key_Up || e.key === Qt.Key_Backtab) ov.turn(-1);
            else if (e.key === Qt.Key_Right || e.key === Qt.Key_Down || e.key === Qt.Key_Tab) ov.turn(1);
            else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) ov.go(ov.frontIndex);
            else if (e.key >= Qt.Key_1 && e.key <= Qt.Key_9) ov.goTo(e.key - Qt.Key_0);
            else return;
            e.accepted = true;
        }
    }

    // ── The hologram panels ──
    Repeater {
        model: ov.ids
        delegate: Item {
            id: panel
            required property var modelData       // workspace id
            required property int index
            readonly property real ang: (index - ov.pos) * ov.step     // where it is on the ring
            readonly property real rad: ang * Math.PI / 180
            readonly property real depth: (Math.cos(rad) + 1) / 2          // 1 = front, 0 = back
            readonly property bool front: index === ov.frontIndex
            readonly property bool current: modelData === OverviewData.activeOn(ov.modelData.name) || (!Roles.docked && modelData === (Hyprland.focusedWorkspace ? Hyprland.focusedWorkspace.id : -1))
            readonly property var wins: OverviewData.clientsOn(modelData)
            readonly property bool peeked: OverviewData.isPeeked(modelData)
            readonly property var mon: {
                const w = OverviewData.workspaces.find(w => OverviewData.homeId(w) === modelData);
                return (w && OverviewData.monitorByName(w.monitor)) || OverviewData.monitorByName(ov.modelData.name) || { x: 0, y: 0, width: ov.width, height: ov.height };
            }
            readonly property real k: ov.panelW / mon.width

            width: ov.panelW
            height: ov.panelW * mon.height / mon.width
            x: ov.cx + Math.sin(rad) * ov.ringR - width / 2
            y: ov.cy + Math.cos(rad) * ov.ringRy - height / 2 + (1 - ov.appear) * 60
            z: depth * 100
            scale: (0.5 + 0.5 * depth) * (0.9 + 0.1 * ov.appear)
            opacity: ov.appear * (0.45 + 0.55 * depth)
            // side panels turn to follow the ring; front and back face you
            transform: Rotation {
                origin.x: panel.width / 2; origin.y: panel.height / 2
                axis { x: 0; y: 1; z: 0 }
                angle: -Math.sin(panel.rad) * 38
            }

            // Glow (its colour and strength are the look's)
            layer.enabled: panel.front
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: pl.item && pl.item.glowColor !== undefined ? pl.item.glowColor : Theme.primary
                shadowBlur: pl.item && pl.item.glowBlur !== undefined ? pl.item.glowBlur : 0.7
                shadowOpacity: pl.item && pl.item.glowOpacity !== undefined ? pl.item.glowOpacity : 0.7
                shadowHorizontalOffset: 0; shadowVerticalOffset: 0
                blurMax: 32
            }

            // ── The panel's look (the skin's) ──
            Loader {
                id: pl
                anchors.fill: parent
                readonly property url want: Skin.component("carouselPanel")
                onWantChanged: setSource(want, { ov: ov, panel: panel })
                Component.onCompleted: setSource(want, { ov: ov, panel: panel })
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: panel.front ? ov.go(panel.index) : ov.bringToFront(panel.index)
                onWheel: w => ov.turn(w.angleDelta.y < 0 ? 1 : -1)
            }
        }
    }
}
