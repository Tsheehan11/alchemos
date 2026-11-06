// Holographic workspace overview (Super + Tab).
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

    readonly property string mono: Style.mono
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

    // Projector floor: ellipse rings under the carousel
    Item {
        x: ov.cx - width / 2; y: ov.cy + ov.ringRy + ov.panelW * 0.32 - height / 2
        width: ov.ringR * 2.6; height: width
        opacity: 0.55 * ov.appear
        transform: Rotation { origin.x: ov.ringR * 1.3; origin.y: ov.ringR * 1.3; axis { x: 1; y: 0; z: 0 } angle: 78; distanceToPlane: 100000 }
        Ring { anchors.centerIn: parent; radius: ov.ringR * 1.25; thickness: 2; value: 1; trackColor: "transparent" }
        Ring { anchors.centerIn: parent; radius: ov.ringR * 1.15; thickness: 8; value: 1; dashed: true; dash: [0.3, 2]; color: Theme.p(0.4); trackColor: "transparent"; rotation: -ov.pos * ov.step }
        Ring { anchors.centerIn: parent; radius: ov.ringR * 0.9; thickness: 1; value: 1; color: Theme.secondary; dashed: true; dash: [8, 6]; trackColor: "transparent"; rotation: ov.pos * ov.step }
    }

    // Header
    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        y: 70
        spacing: 6
        opacity: ov.appear
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "WORKSPACES // " + (Roles.docked ? ov.modelData.name : "ALL")
            color: Theme.primary
            font.family: Style.display; font.pixelSize: 13; font.letterSpacing: 6
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: ov.focusedHere
            text: "← → TURN   ·   ENTER SELECT   ·   1–9 JUMP   ·   ESC CLOSE"
            color: Theme.dim
            font.family: ov.mono; font.pixelSize: 10; font.letterSpacing: 3
        }
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

            // Glow
            layer.enabled: panel.front
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Theme.primary
                shadowBlur: 0.7
                shadowOpacity: 0.7
                shadowHorizontalOffset: 0; shadowVerticalOffset: 0
                blurMax: 32
            }

            // Glass
            Rectangle {
                anchors.fill: parent
                color: Theme.d(0.82)
                border.color: panel.front ? Theme.primary : Theme.p(0.45)
                border.width: panel.front ? 2 : 1
                clip: true

                // Window previews (dimmed while Peek hides them)
                Repeater {
                    model: panel.wins
                    delegate: Item {
                        required property var modelData
                        opacity: panel.peeked ? 0.4 : 1
                        readonly property var wm: OverviewData.monitorById(modelData.monitor) || panel.mon
                        x: (modelData.at[0] - wm.x) * panel.k
                        y: (modelData.at[1] - wm.y) * panel.k
                        width: Math.max(8, modelData.size[0] * panel.k)
                        height: Math.max(8, modelData.size[1] * panel.k)

                        // Fallback tile: icon + title (shows if a live preview isn't available)
                        Rectangle {
                            anchors.fill: parent
                            color: Theme.p(0.08)
                            border.color: Theme.p(0.5)
                            Column {
                                anchors.centerIn: parent
                                spacing: 4
                                Image {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    readonly property string src: OverviewData.iconFor(modelData.class)
                                    source: src
                                    visible: src !== ""
                                    width: 36; height: 36; sourceSize: Qt.size(72, 72)
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: (modelData.class || "").toUpperCase()
                                    color: Theme.textSoft
                                    font.family: ov.mono; font.pixelSize: 10; font.letterSpacing: 1
                                }
                            }
                        }
                        // Live preview (captured once when the overview opens). Never for a
                        // window on no monitor or while screens settle (OverviewData.capturable):
                        // that capture segfaults Hyprland 0.56.2. The fallback tile shows instead.
                        ScreencopyView {
                            anchors.fill: parent
                            captureSource: ov.visible && OverviewData.capturable(modelData) ? OverviewData.toplevelFor(modelData.address) : null
                            live: false
                            opacity: 0.92
                        }
                        Rectangle { anchors.fill: parent; color: "transparent"; border.color: Theme.p(0.6); border.width: 1 }
                    }
                }

                // Empty workspace
                Text {
                    anchors.centerIn: parent
                    visible: panel.wins.length === 0
                    text: "EMPTY"
                    color: Theme.p(0.45)
                    font.family: ov.mono; font.pixelSize: 16; font.letterSpacing: 8
                }

                // Hologram scanlines
                Column {
                    anchors.fill: parent
                    Repeater {
                        model: Math.ceil(panel.height / 4)
                        Rectangle { width: panel.width; height: 4; color: index % 2 === 0 ? Theme.p(0.05) : "transparent" }
                    }
                }
            }

            // Corner brackets
            Repeater {
                model: 4
                delegate: Item {
                    required property int index
                    width: 18; height: 18
                    x: index % 2 === 0 ? -5 : panel.width - 13
                    y: index < 2 ? -5 : panel.height - 13
                    Rectangle { width: 18; height: 2; color: panel.front ? Theme.secondary : Theme.primary; y: index < 2 ? 0 : 16 }
                    Rectangle { width: 2; height: 18; color: panel.front ? Theme.secondary : Theme.primary; x: index % 2 === 0 ? 0 : 16 }
                }
            }

            // Label under the panel
            Row {
                anchors.top: parent.bottom; anchors.topMargin: 14
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 12
                Text {
                    text: "WS " + String(panel.modelData).padStart(2, "0")
                    color: panel.front ? Theme.text : Theme.textSoft
                    font.family: ov.mono; font.pixelSize: 18; font.letterSpacing: 4
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: panel.wins.length + (panel.wins.length === 1 ? " WINDOW" : " WINDOWS") + (panel.peeked ? "  ·  PEEK" : "") + (panel.current ? "  ·  ACTIVE" : "")
                    color: panel.current ? Theme.secondary : Theme.dim
                    font.family: ov.mono; font.pixelSize: 11; font.letterSpacing: 2
                }
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
