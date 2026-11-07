// The base backdrop (Skin.component("backdrop")): the hologram background. Grid, blinking nodes,
// data streams, an occasional scanline sweep, slowly turning corner rings and readouts; a skin with
// texture "grain" gets stone grain and a vignette instead of the grid. GridBackground.qml hosts it.
//
// Backdrop interface (every skin's backdrop has these; GridBackground binds them):
//   modelData  the screen        t     seconds off the shared Perf clock, frozen while not live
//   live       animating now      res   texture resolution, 1 or 0.5 (laptop panel, battery saver)
//   activity   0..1: the assistant listening / speaking, else CPU load
import QtQuick
import Quickshell

Item {
    id: bg
    property var modelData
    property real t: 0
    property bool live: false
    property real res: 1
    property real activity: 0

    readonly property int step: 40
    readonly property string mono: Style.mono

    readonly property bool holo: Style.texture === "holo"      // grid, data streams, scanline (base look)

    // Grain texture (Style.texture "grain"): static stone grain and a soft vignette instead of the grid
    Image {
        anchors.fill: parent
        visible: Theme.cfg.showGrid && Style.texture === "grain"
        source: "assets/grain.png"
        fillMode: Image.Tile
        opacity: Style.grainNow * 0.8
        smooth: false
    }
    Rectangle {
        visible: !bg.holo
        width: parent.width; height: parent.height * 0.35
        gradient: Gradient { GradientStop { position: 0; color: Qt.rgba(0, 0, 0, 0.35) } GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0) } }
    }
    Rectangle {
        visible: !bg.holo
        width: parent.width; height: parent.height * 0.35; anchors.bottom: parent.bottom
        gradient: Gradient { GradientStop { position: 0; color: Qt.rgba(0, 0, 0, 0) } GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0.4) } }
    }

    // Static grid (drawn once)
    Canvas {
        anchors.fill: parent
        visible: Theme.cfg.showGrid && bg.holo
        property color tint: Theme.primary
        onTintChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();       // not clearRect(): see Graph.qml
            const s = bg.step;
            ctx.lineWidth = 1;
            ctx.strokeStyle = Theme.pc(0.045);
            ctx.beginPath();
            for (let x = 0.5; x < width; x += s) { ctx.moveTo(x, 0); ctx.lineTo(x, height); }
            for (let y = 0.5; y < height; y += s) { ctx.moveTo(0, y); ctx.lineTo(width, y); }
            ctx.stroke();
            ctx.strokeStyle = Theme.pc(0.09);
            ctx.beginPath();
            for (let x = 0.5; x < width; x += s * 5) { ctx.moveTo(x, 0); ctx.lineTo(x, height); }
            for (let y = 0.5; y < height; y += s * 5) { ctx.moveTo(0, y); ctx.lineTo(width, y); }
            ctx.stroke();
            ctx.strokeStyle = Theme.pc(0.35);
            ctx.beginPath();
            for (let x = s * 5 + 0.5; x < width; x += s * 5)
                for (let y = s * 5 + 0.5; y < height; y += s * 5) {
                    ctx.moveTo(x - 4, y); ctx.lineTo(x + 4, y);
                    ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4);
                }
            ctx.stroke();
        }
    }

    // Blinking grid nodes
    Repeater {
        model: 30
        delegate: Rectangle {
            readonly property real fx: Math.random()
            readonly property real fy: Math.random()
            readonly property real phase: Math.random()
            readonly property real period: 5 + Math.random() * 6
            readonly property real w: (bg.t / period + phase) % 1          // 0..1 cycle
            width: 5; height: 5; radius: 2.5
            color: Math.random() < 0.2 ? Theme.secondary : Theme.primary
            x: Math.round(fx * bg.width / bg.step) * bg.step - 2
            y: Math.round(fy * bg.height / bg.step) * bg.step - 2
            // quick flash near the start of each cycle, dark otherwise
            opacity: bg.live ? (w < 0.08 ? w / 0.08 * 0.9 : (w < 0.3 ? 0.9 * (1 - (w - 0.08) / 0.22) : 0)) : 0.25
        }
    }

    // Vertical data streams (up the grid columns)
    Repeater {
        model: 7
        delegate: Rectangle {
            readonly property int col: Math.floor(Math.random() * (bg.width / bg.step))
            readonly property real speed: 90 + Math.random() * 120      // px per second
            readonly property real offset: Math.random() * 3000
            readonly property real span: bg.height + height + 600       // includes a pause off-screen
            visible: bg.live && bg.holo
            width: 2; height: 90 + Math.random() * 120
            x: col * bg.step
            y: bg.height - ((bg.t * speed + offset) % span)
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.p(0.75) }
                GradientStop { position: 1.0; color: Theme.p(0.0) }
            }
        }
    }

    // Horizontal data streams (along the grid rows)
    Repeater {
        model: 4
        delegate: Rectangle {
            readonly property int row: Math.floor(Math.random() * (bg.height / bg.step))
            readonly property real speed: 80 + Math.random() * 100
            readonly property real offset: Math.random() * 3000
            readonly property real span: bg.width + width + 900
            visible: bg.live && bg.holo
            height: 2; width: 120 + Math.random() * 160
            y: row * bg.step
            x: ((bg.t * speed + offset) % span) - width
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Theme.s(0.0) }
                GradientStop { position: 1.0; color: Theme.s(0.6) }
            }
        }
    }

    // Scanline: one sweep every 40 seconds (it touches the whole screen, so it's rationed)
    Rectangle {
        id: scan
        readonly property real cyc: bg.t % 40
        visible: bg.live && bg.holo && cyc < 9
        width: parent.width; height: 140
        y: -height + (cyc / 9) * (bg.height + height)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.p(0.0) }
            GradientStop { position: 0.85; color: Theme.p(0.05) }
            GradientStop { position: 1.0; color: Theme.p(0.16) }
        }
    }

    // Corner ring cluster — bottom left
    Item {
        x: -180; y: bg.height - 260
        width: 440; height: 440
        opacity: 0.35
        Ring { anchors.centerIn: parent; radius: 210; thickness: 1; value: 1; dashed: true; dash: [3, 6]; trackColor: "transparent"; rotation: bg.t * 3 }
        Ring { anchors.centerIn: parent; radius: 170; thickness: 3; value: 0.3; trackColor: "transparent"; rotation: -bg.t * 8 }
        Ring { anchors.centerIn: parent; radius: 140; thickness: 1; value: 1; color: Theme.secondary; dashed: true; dash: [12, 6]; trackColor: "transparent"; rotation: bg.t * 5 }
    }

    // Corner ring cluster — top right
    Item {
        x: bg.width - 220; y: -120
        width: 380; height: 380
        opacity: 0.3
        Ring { anchors.centerIn: parent; radius: 180; thickness: 1; value: 1; dashed: true; dash: [2, 10]; trackColor: "transparent"; rotation: -bg.t * 3.6 }
        Ring { anchors.centerIn: parent; radius: 130; thickness: 2; value: 0.55; trackColor: Theme.p(0.08); rotation: bg.t * 9 }
    }

    // Scrolling hex readout — bottom right
    Text {
        id: hex
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.rightMargin: 28; anchors.bottomMargin: 24
        horizontalAlignment: Text.AlignRight
        color: Theme.p(0.28)
        font.family: bg.mono; font.pixelSize: 11
        lineHeight: 1.3
        function word() { return (Math.floor(Math.random() * 0xFFFFFFFF) >>> 0).toString(16).toUpperCase().padStart(8, "0"); }
        function gen() {
            let s = "";
            for (let i = 0; i < 5; i++) s += word() + "  " + word() + "  " + word() + "\n";
            return s + "DISPLAY " + bg.modelData.name + " // " + bg.modelData.width + "×" + bg.modelData.height;
        }
        Timer {
            interval: 1500; running: bg.live; repeat: true; triggeredOnStart: true
            onTriggered: hex.text = hex.gen()
        }
    }

    // Status readout — top left (under the bar)
    Column {
        x: 28; y: 58
        spacing: 4
        opacity: 0.4
        Text { text: (bg.holo ? "SYS.GRID // " : Skin.text.os + " // ") + (bg.live ? "ONLINE" : "STANDBY"); color: Theme.primary; font.family: bg.mono; font.pixelSize: 11; font.letterSpacing: 2 }
        Text {
            readonly property int level: Math.round(SysStats.wifi * 8)
            text: "WIFI   " + "▮".repeat(level) + "▯".repeat(8 - level) + "  " + Math.round(SysStats.wifi * 100) + "%"
            color: Theme.primary; font.family: bg.mono; font.pixelSize: 11
        }
        Text {
            text: "NET    ↓ " + SysStats.fmtRate(SysStats.rxRate) + "   ↑ " + SysStats.fmtRate(SysStats.txRate)
            color: Theme.primary; font.family: bg.mono; font.pixelSize: 11
        }
    }
}
