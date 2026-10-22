// Flow-cloud launcher — apps drift out of the mouse cursor in five curving
// branches (AI, NET, MEDIA, SYS, CTRL) fed by streams of light from the core, with a swirl of particles
// flowing around everything.
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
    WlrLayershell.namespace: "stark-launcher"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"

    readonly property color cyan: Theme.primary
    readonly property color amber: Theme.secondary
    readonly property string mono: "JetBrainsMono Nerd Font"

    // ── Edit your apps here ──────────────────
    // Apps come in pairs that form one branch: [main app, related app].
    // The main app sits close to the core; the related one flows out from it.
    readonly property var branches: [
        { name: "AI",     apps: [{ label: "CLAUDE",  cmd: "zen-browser --new-window https://claude.ai" },
                                 { label: "CODE",    cmd: "kitty -e claude" }] },
        { name: "NET",    apps: [{ label: "WEB",     cmd: "zen-browser" },
                                 { label: "DISCORD", cmd: "discord" }] },
        { name: "MEDIA",  apps: [{ label: "MUSIC",   cmd: "spotify-launcher" },
                                 { label: "GAMES",   cmd: "steam" }] },
        { name: "DEV",    apps: [{ label: "VS CODE", cmd: "code" },
                                 { label: "HUD",     cmd: "code " + Quickshell.env("HOME") + "/.config/quickshell" }] },
        { name: "SYS",    apps: [{ label: "TERM",    cmd: "kitty" },
                                 { label: "FILES",   cmd: "dolphin" }] },
        { name: "CTRL",   apps: [{ label: "CONTROL", cmd: "@control" },
                                 { label: "LOCK",    cmd: "@lock" }] }
    ]
    readonly property var apps: {
        const out = [];
        for (const b of branches) for (const a of b.apps) out.push(a);
        return out;
    }
    function branchOf(i) { return Math.floor(i / 2); }
    function tierOf(i) { return i % 2; }              // 0 = near the core, 1 = flows outward

    // Layout: branches fan out evenly; each related app sits further out and
    // a little further round, so every branch curves the same way.
    readonly property var jitter: [0, 7, -5, 5, -6]
    function branchAngle(b) { return -90 + b * (360 / branches.length) + jitter[b % jitter.length]; }
    function baseAngle(i) { return branchAngle(branchOf(i)) + (tierOf(i) === 1 ? 18 : 0); }
    function baseRadius(i) { return tierOf(i) === 1 ? 325 : 172; }
    function nodeSize(i) { return tierOf(i) === 1 ? 76 : 94; }

    property int selected: 0
    property real spread: 0
    property real t: 0            // drives the gentle floating drift

    function close() { LauncherState.open = false }
    function launch(i) {
        const cmd = apps[i].cmd;
        if (cmd === "@control") { LauncherState.openControl(); return; }
        if (cmd === "@lock") { LockState.requestLock(); return; }
        Hyprland.dispatch("exec " + cmd);
        close();
    }

    onVisibleChanged: {
        if (visible) {
            selected = 0;
            spread = 0;
            openAnim.restart();
            flicker.restart();
            core.forceActiveFocus();
        }
    }

    NumberAnimation {
        id: openAnim
        target: win; property: "spread"
        from: 0; to: 1; duration: 700
        easing.type: Easing.OutBack; easing.overshoot: 1.1
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

        // Hologram glow + flicker on open
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.primary
            shadowBlur: 0.8
            shadowOpacity: 0.8
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
            blurMax: 36
        }
        SequentialAnimation {
            id: flicker
            NumberAnimation { target: core; property: "opacity"; to: 0.35; duration: 50 }
            NumberAnimation { target: core; property: "opacity"; to: 1; duration: 60 }
            NumberAnimation { target: core; property: "opacity"; to: 0.6; duration: 40 }
            NumberAnimation { target: core; property: "opacity"; to: 1; duration: 90 }
        }

        Keys.onPressed: function(event) {
            const n = win.apps.length;
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

        // ── Flow streams + swirling particle cloud ──
        Canvas {
            anchors.fill: parent
            property real tt: win.t
            property real sp: win.spread
            property int sel: win.selected
            onTtChanged: requestPaint()
            onSpChanged: requestPaint()
            onSelChanged: requestPaint()

            onPaint: {
                const ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                if (win.spread <= 0.02) return;
                const sp = Math.min(1, win.spread);
                const T = win.t;

                // Swirling particle cloud: short streaks orbiting the core
                for (let k = 0; k < 90; k++) {
                    const r0 = 90 + ((k * 73) % 300);
                    const speed = (0.08 + ((k * 37) % 10) / 60) * (k % 2 === 0 ? 1 : 0.7);
                    const a = k * 2.399 + T * speed;
                    const wob = 18 * Math.sin(T * 0.5 + k);
                    const r = (r0 + wob) * sp;
                    const a2 = a - 0.09;
                    ctx.beginPath();
                    ctx.moveTo(core.cx + Math.cos(a2) * r, core.cy + Math.sin(a2) * r);
                    ctx.lineTo(core.cx + Math.cos(a) * r, core.cy + Math.sin(a) * r);
                    ctx.lineWidth = k % 7 === 0 ? 2 : 1.2;
                    ctx.strokeStyle = k % 6 === 0 ? Theme.sc(0.45) : "rgba(79, 216, 255, " + (0.15 + (k % 4) * 0.08) + ")";
                    ctx.stroke();
                }

                // Curving streams: core → inner apps, inner → outer apps
                function stream(ax, ay, bx, by, bend, hot, seed) {
                    const mx = (ax + bx) / 2, my = (ay + by) / 2;
                    const dx = bx - ax, dy = by - ay, L = Math.hypot(dx, dy) || 1;
                    const sway = bend + 0.08 * Math.sin(T * 0.7 + seed);
                    const qx = mx - dy / L * L * sway, qy = my + dx / L * L * sway;
                    ctx.beginPath();
                    ctx.moveTo(ax, ay);
                    ctx.quadraticCurveTo(qx, qy, bx, by);
                    ctx.setLineDash([]);
                    ctx.lineWidth = hot ? 7 : 5;
                    ctx.strokeStyle = hot ? Theme.sc(0.10) : Theme.pc(0.06);
                    ctx.stroke();
                    ctx.lineWidth = hot ? 1.6 : 1;
                    ctx.strokeStyle = hot ? Theme.slc(0.8) : Theme.pc(0.35);
                    ctx.stroke();
                    ctx.setLineDash([4, 16]);
                    ctx.lineDashOffset = -T * 22 - seed * 7;
                    ctx.lineWidth = 2.2;
                    ctx.strokeStyle = hot ? Theme.slc(0.95) : Theme.lc(0.7);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }
                // Each branch: core → main app → related app, curving the same way
                for (let i = 0; i < win.apps.length; i++) {
                    const src = win.tierOf(i) === 1 ? i - 1 : -1;
                    const ax = src < 0 ? core.cx : core.nx(src), ay = src < 0 ? core.cy : core.ny(src);
                    const hot = win.branchOf(i) === win.branchOf(win.selected);
                    stream(ax, ay, core.nx(i), core.ny(i), win.tierOf(i) === 1 ? -0.16 : -0.2, hot, i);
                }
            }
        }

        // ── Nucleus at the cursor ──
        Item {
            x: core.cx - width / 2; y: core.cy - height / 2
            width: 156; height: 156
            scale: Math.min(1, win.spread)

            Ring {
                anchors.centerIn: parent
                radius: 76; thickness: 1; value: 1
                dashed: true; dash: [3, 6]
                color: win.cyan; trackColor: "transparent"
                RotationAnimation on rotation { running: win.visible; from: 0; to: 360; duration: 14000; loops: Animation.Infinite }
            }
            Ring {
                anchors.centerIn: parent
                radius: 66; thickness: 3; value: 0.6
                color: win.amber; trackColor: Theme.s(0.1)
                RotationAnimation on rotation { running: win.visible; from: 360; to: 0; duration: 7000; loops: Animation.Infinite }
            }
            Rectangle {
                anchors.centerIn: parent
                width: 120; height: 120; radius: 60
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.p(0.28) }
                    GradientStop { position: 1.0; color: Theme.d(0.95) }
                }
                border.color: Theme.p(0.7)
            }
            Column {
                anchors.centerIn: parent
                spacing: 2
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "LAUNCH"
                    color: Theme.dim
                    font.family: win.mono; font.pixelSize: 9; font.letterSpacing: 3
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: win.apps[win.selected].label
                    color: "#ffffff"
                    font.family: win.mono; font.pixelSize: win.apps[win.selected].label.length > 6 ? 14 : 18
                    font.letterSpacing: 1
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "TYPE TO SEARCH"
                    color: win.amber
                    font.family: win.mono; font.pixelSize: 7; font.letterSpacing: 2
                }
            }
        }

        // ── Branch labels ──
        Repeater {
            model: win.branches.length
            delegate: Text {
                required property int index
                readonly property int i0: index * 2
                readonly property bool hot: win.branchOf(win.selected) === index
                // halfway between the two apps, nudged off the stream
                readonly property real mx: (core.nx(i0) + core.nx(i0 + 1)) / 2
                readonly property real my: (core.ny(i0) + core.ny(i0 + 1)) / 2
                readonly property real ox: (core.ny(i0 + 1) - core.ny(i0))
                readonly property real oy: -(core.nx(i0 + 1) - core.nx(i0))
                readonly property real ol: Math.max(1, Math.hypot(ox, oy))
                x: mx + ox / ol * 30 - width / 2
                y: my + oy / ol * 30 - height / 2
                text: win.branches[index].name
                color: hot ? win.amber : Theme.dim
                opacity: Math.min(1, win.spread) * (hot ? 1 : 0.6)
                font.family: win.mono; font.pixelSize: 11; font.letterSpacing: 4
                z: 5
            }
        }

        // ── App nodes ──
        Repeater {
            model: win.apps.length
            delegate: Rectangle {
                id: node
                required property int index
                readonly property bool sel: win.selected === index
                readonly property int size: win.nodeSize(index)
                readonly property bool branchHot: win.branchOf(index) === win.branchOf(win.selected)
                readonly property color tint: win.branchOf(index) % 2 === 1 ? win.amber : win.cyan

                width: size; height: size; radius: size / 2
                x: core.nx(index) - width / 2
                y: core.ny(index) - height / 2
                z: sel ? 20 : 10
                scale: Math.min(1, win.spread) * (sel ? 1.15 : 1)
                opacity: Math.min(1, win.spread * 1.3)
                Behavior on scale { NumberAnimation { duration: 150 } }

                gradient: Gradient {
                    GradientStop { position: 0.0; color: node.sel ? Theme.p(0.45) : Theme.p(0.16) }
                    GradientStop { position: 1.0; color: Theme.d(0.94) }
                }
                border.color: node.sel ? "#ffffff" : node.tint
                border.width: node.sel ? 2 : 1

                // Glass glint
                Rectangle {
                    x: node.size * 0.2; y: node.size * 0.12
                    width: node.size * 0.6; height: node.size * 0.16; radius: height / 2
                    color: Qt.rgba(1, 1, 1, 0.10)
                }
                // Electron orbit on the selected atom
                Ring {
                    anchors.centerIn: parent
                    visible: node.sel
                    radius: node.size / 2 + 10; thickness: 1; value: 1
                    dashed: true; dash: [3, 5]
                    color: win.amber; trackColor: "transparent"
                    RotationAnimation on rotation { running: win.visible; from: 0; to: 360; duration: 3000; loops: Animation.Infinite }
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 1
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: win.apps[node.index].label
                        color: node.sel ? "#ffffff" : Theme.textSoft
                        font.family: win.mono
                        font.pixelSize: win.apps[node.index].label.length > 6 ? 10 : 12
                        font.letterSpacing: 1
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: (node.index + 1) % 10
                        color: node.tint
                        font.family: win.mono; font.pixelSize: 9
                        opacity: 0.8
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: win.selected = node.index
                    onClicked: win.launch(node.index)
                }
            }
        }
    }
}
