// The base launcher look (Skin.component("launcherLook")): the hologram flow cloud. Streams of light
// from the core to each app, a swirl of particle streaks, a nucleus with turning rings, glass atoms for
// the apps, a cyan glow and a flicker on open. Launcher.qml owns everything else (keys, geometry, the
// spiral open, launching, the hit areas); a look only draws.
//
// Launcher-look interface: required win (the launcher: apps, selected, current, spread, t, visible,
// branchOf / tierOf / nodeSize, cyan / amber / mono) and core (cx, cy, nx(i), ny(i)); optional openMs and
// openEasing (the spiral's opening), opened() (called as it opens).
import QtQuick
import QtQuick.Effects
import Quickshell

Item {
    id: look
    required property var win
    required property var core

    readonly property int openMs: 700
    readonly property int openEasing: Easing.OutBack
    function opened() { flicker.restart(); }

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
        NumberAnimation { target: look; property: "opacity"; to: 0.35; duration: 50 }
        NumberAnimation { target: look; property: "opacity"; to: 1; duration: 60 }
        NumberAnimation { target: look; property: "opacity"; to: 0.6; duration: 40 }
        NumberAnimation { target: look; property: "opacity"; to: 1; duration: 90 }
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
                ctx.reset();       // not clearRect(): see Graph.qml
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
                    ctx.strokeStyle = k % 6 === 0 ? Theme.sc(0.45) : Theme.pc(0.15 + (k % 4) * 0.08);
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
                Rectangle {      // engraved: the core's inner ring and its sign
                    visible: Style.engraved
                    anchors.fill: parent; anchors.margins: 5
                    radius: width / 2; color: "transparent"; border.color: Theme.p(0.3)
                }
            }
            Column {
                anchors.centerIn: parent
                spacing: 2
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "LAUNCH"
                    color: Theme.dim
                    font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 3
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(implicitWidth, 108)
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                    text: win.current.name
                    color: win.current.available ? "#ffffff" : Theme.faint
                    font.family: Style.fonts.body; font.pixelSize: win.current.name.length > 6 ? 14 : 18
                    font.capitalization: Font.AllUppercase
                    font.letterSpacing: 1
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: win.current.available ? "TYPE TO SEARCH" : "NOT INSTALLED"
                    color: win.amber
                    font.family: Style.fonts.body; font.pixelSize: 7; font.letterSpacing: 2
                }
            }
        }

        // ── Branch labels ──
        Repeater {
            model: win.branchCount
            delegate: Text {
                required property int index
                readonly property int i0: index * 2
                // A lone app (odd count) gets its label just beyond it, on the way out from the core
                readonly property int i1: i0 + 1 < win.apps.length ? i0 + 1 : -1
                readonly property bool hot: win.branchOf(win.selected) === index
                readonly property real outX: i1 >= 0 ? core.nx(i1) : core.cx + (core.nx(i0) - core.cx) * 1.5
                readonly property real outY: i1 >= 0 ? core.ny(i1) : core.cy + (core.ny(i0) - core.cy) * 1.5
                // halfway between the two apps, nudged off the stream
                readonly property real mx: (core.nx(i0) + outX) / 2
                readonly property real my: (core.ny(i0) + outY) / 2
                readonly property real ox: (outY - core.ny(i0))
                readonly property real oy: -(outX - core.nx(i0))
                readonly property real ol: Math.max(1, Math.hypot(ox, oy))
                x: mx + ox / ol * 30 - width / 2
                y: my + oy / ol * 30 - height / 2
                // The inner app's label, else the outer one's — so labels survive reordering
                text: (win.apps[i0] || {}).group || (i1 >= 0 ? win.apps[i1].group : "") || ""
                font.capitalization: Font.AllUppercase
                color: hot ? win.amber : Theme.dim
                opacity: Math.min(1, win.spread) * (hot ? 1 : 0.6)
                font.family: Style.fonts.body; font.pixelSize: 11; font.letterSpacing: 4
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
                readonly property var app: win.apps[index] || ({ name: "", icon: "", available: false })
                readonly property int size: win.nodeSize(index)
                readonly property bool branchHot: win.branchOf(index) === win.branchOf(win.selected)
                readonly property color tint: win.branchOf(index) % 2 === 1 ? win.amber : win.cyan

                width: size; height: size; radius: size / 2
                x: core.nx(index) - width / 2
                y: core.ny(index) - height / 2
                z: sel ? 20 : 10
                scale: Math.min(1, win.spread) * (sel ? 1.15 : 1)
                // Not installed (any more): dimmed, and launching does nothing
                opacity: Math.min(1, win.spread * 1.3) * (app.available ? 1 : 0.35)
                Behavior on scale { NumberAnimation { duration: 150 } }

                gradient: Gradient {
                    GradientStop { position: 0.0; color: node.sel ? Theme.p(0.45) : Theme.p(0.16) }
                    GradientStop { position: 1.0; color: Theme.d(0.94) }
                }
                border.color: node.sel ? "#ffffff" : node.tint
                border.width: node.sel ? 2 : 1

                // engraved: an inner ring, like a seal
                Rectangle {
                    visible: Style.engraved
                    anchors.fill: parent; anchors.margins: 4
                    radius: width / 2
                    color: "transparent"
                    border.color: node.sel ? Theme.p(0.8) : Theme.p(0.25)
                }
                // Glass glint
                Rectangle {
                    visible: !Style.engraved
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
                    Image {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: node.app.icon !== "" && status === Image.Ready
                        width: node.size > 80 ? 28 : 22; height: width
                        source: node.app.icon
                        sourceSize: Qt.size(64, 64)
                        smooth: true
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: Math.min(implicitWidth, node.size - 14)
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                        text: node.app.name
                        color: node.sel ? "#ffffff" : Theme.textSoft
                        font.family: Style.fonts.body
                        font.pixelSize: node.app.name.length > 6 ? 10 : 12
                        font.capitalization: Font.AllUppercase
                        font.letterSpacing: 1
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: !node.app.available ? "N/A" : node.index < 10 ? (node.index + 1) % 10 : ""   // keys 1–9, 0
                        color: node.tint
                        font.family: Style.fonts.body; font.pixelSize: 9
                        opacity: 0.8
                    }
                }
            }
        }
}
