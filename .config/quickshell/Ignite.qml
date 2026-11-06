// Full-screen flourish over every screen, click-through, gone when idle.
//   skin       switching skins: the new skin's transition component (Skin.component("transition")), flash
//   ignite     a preset applied: the new metal's glyph flares in its colour and a ring sweeps out
// Combat mode skips it; at 0 fps (battery saver at static, locked) only a short tint plays.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: win
    required property var modelData
    screen: modelData

    visible: IgniteState.playing && !GameMode.quiet
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-ignite"
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    mask: Region {}
    color: "transparent"

    readonly property real p: IgniteState.p                  // 0 → 1 over the animation
    readonly property string mode: IgniteState.mode
    readonly property bool lite: IgniteState.lite
    readonly property color tint: IgniteState.color
    readonly property real r0: Math.min(width, height) * 0.24
    readonly property string mono: Style.mono
    function tc(a) { return Qt.rgba(tint.r, tint.g, tint.b, a); }

    // Frame probe: one log line per screen per animation (frame intervals as this window saw them)
    property var frames: []
    FrameAnimation {
        running: win.visible && IgniteState.moving
        onTriggered: win.frames.push(frameTime * 1000)
        onRunningChanged: {
            if (running) { win.frames = []; return; }
            const raw = win.frames.slice(1);
            const f = raw.slice().sort((a, b) => a - b);
            const slow = raw.map((x, i) => x > 25 ? i + "@" + x.toFixed(0) : "").filter(x => x).join(" ");
            if (f.length < 3) return;
            const mean = f.reduce((a, b) => a + b, 0) / f.length;
            console.log("ignite " + IgniteState.mode + " " + win.modelData.name + ": first " + (win.frames[0] || 0).toFixed(0) + " ms, " + f.length + " frames, mean "
                        + mean.toFixed(1) + " ms, p95 " + f[Math.floor(f.length * 0.95)].toFixed(1) + " ms, max "
                        + f[f.length - 1].toFixed(1) + " ms, >25 ms: " + f.filter(x => x > 25).length + (slow ? " (" + slow + ")" : ""));
        }
    }
    function seg(a, b) { return Math.max(0, Math.min(1, (p - a) / (b - a))); }   // progress inside [a, b]
    function bell(a, b) { const x = seg(a, b); return Math.sin(Math.PI * x); }

    // Wash: a faint tint of the new colour, peaking at the flash
    Rectangle {
        anchors.fill: parent
        color: win.tc(1)
        opacity: win.lite ? 0.12 * win.bell(0, 1) : 0.10 * win.bell(0.55, 1) + 0.04 * win.bell(0, 0.6)
    }
    // Edge glow (gradient frames top / bottom)
    Rectangle {
        visible: !win.lite
        width: parent.width; height: parent.height * 0.18
        opacity: win.bell(0.5, 1)
        gradient: Gradient { GradientStop { position: 0; color: win.tc(0.35) } GradientStop { position: 1; color: win.tc(0) } }
    }
    Rectangle {
        visible: !win.lite
        width: parent.width; height: parent.height * 0.18; anchors.bottom: parent.bottom
        opacity: win.bell(0.5, 1)
        gradient: Gradient { GradientStop { position: 0; color: win.tc(0) } GradientStop { position: 1; color: win.tc(0.35) } }
    }

    Item {
        id: stage
        visible: !win.lite
        anchors.centerIn: parent
        width: win.r0 * 2.6; height: width
        opacity: 1 - win.seg(0.86, 1)

        // ── ignite (every preset change): complete rings that only scale and fade, so no frame rebuilds geometry ──
        Item {
            anchors.fill: parent
            visible: win.mode === "ignite"
            Ring { anchors.centerIn: parent; radius: win.r0; thickness: 2; animated: false; startAngle: -90; value: 1
                   color: win.tint; opacity: 0.9 * win.bell(0, 0.8); trackColor: "transparent"; scale: 0.75 + 0.25 * win.seg(0, 0.5) }
            Ring { anchors.centerIn: parent; radius: win.r0 * 0.86; thickness: 1; animated: false; startAngle: 90; value: 1
                   color: win.tint; opacity: 0.6 * win.bell(0.05, 0.85); trackColor: "transparent"; scale: 1.2 - 0.2 * win.seg(0, 0.5) }
        }

        // ── skin: the new skin's transition (Skin.component("transition"); default TransmuteTransition) ──
        Loader {
            anchors.fill: parent
            active: win.mode === "skin"
            source: Skin.transitionUrl
            onLoaded: {
                item.p = Qt.binding(() => win.p);
                item.tint = Qt.binding(() => win.tint);
                item.r0 = Qt.binding(() => win.r0);
            }
        }

        // ── centre: the new metal's glyph (ignite) or the flash core ──
        SigilText {
            anchors.centerIn: parent
            visible: win.mode === "ignite"
            text: IgniteState.glyph
            color: win.tc(1)
            font.pixelSize: win.r0 * 0.7
            opacity: win.bell(0.05, 0.9)
            scale: 0.7 + 0.5 * win.seg(0.05, 0.9)
            glow: 1
        }
        // flash
        Rectangle {
            anchors.centerIn: parent
            width: win.r0 * 4.4; height: width; radius: width / 2            // fixed size: scaled, not resized
            scale: (0.4 + 4 * (win.mode === "ignite" ? win.seg(0.2, 1) : win.seg(0.62, 1))) / 4.4
            color: "transparent"
            border.color: win.tc(0.9); border.width: 3
            opacity: win.mode === "ignite" ? win.bell(0.2, 1) : win.bell(0.62, 1)
        }
    }

    // title (main screen)
    Column {
        visible: !win.lite && win.mode !== "ignite" && Roles.role(win.modelData) === "main"
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height / 2 + win.r0 * 1.45
        spacing: 6
        opacity: win.bell(0.15, 1)
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: IgniteState.title.slice(0, Math.ceil(win.seg(0.15, 0.45) * IgniteState.title.length))
            color: Theme.text; font.family: win.mono; font.pixelSize: 22; font.letterSpacing: 6
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: IgniteState.sub
            color: win.tc(1); font.family: win.mono; font.pixelSize: 10; font.letterSpacing: 3
            opacity: win.seg(0.4, 0.6)
        }
    }
}
