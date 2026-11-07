// Stopwatch: ▶ / ⏸ and reset. Survives restarts (start time + time banked so far).
import QtQuick
import ".."

WidgetBody {
    id: w
    readonly property bool running: params.running === true
    property double now: Date.now()
    // tenths while effects run on this screen, whole seconds otherwise
    Timer { interval: w.live ? 100 : 1000; running: w.active && w.running; repeat: true; triggeredOnStart: true; onTriggered: w.now = Date.now() }
    readonly property real elapsed: (params.acc || 0) + (running ? Math.max(0, now - (params.start || now)) : 0)
    title: "STOPWATCH" + (params.label ? " // " + params.label.toUpperCase() : "")
    detail: running ? "RUNNING" : "PAUSED"

    function fmt(ms) {
        const s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
        return (h > 0 ? h + ":" + String(m).padStart(2, "0") : String(m).padStart(2, "0")) + ":" + String(sec).padStart(2, "0");
    }
    function toggle() {
        if (running) setParams({ running: false, acc: elapsed });
        else setParams({ running: true, start: Date.now() });
        now = Date.now();
    }
    function reset() { setParams({ acc: 0, start: Date.now() }); now = Date.now(); }

    implicitWidth: 250
    implicitHeight: 64

    Row {
        spacing: 2
        NumText { text: w.fmt(w.elapsed); color: w.running ? Theme.text : Theme.textSoft; font.family: Style.fonts.numeric; font.pixelSize: 40; font.weight: Font.Light }
        Text {
            visible: w.live || !w.running
            anchors.baseline: parent.children[0].baseline
            text: "." + Math.floor(w.elapsed % 1000 / 100)
            color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 20
        }
    }
    Row {
        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
        spacing: 6
        Repeater {
            model: [{ g: w.running ? "⏸" : "▶", f: () => w.toggle() }, { g: "↺", f: () => w.reset() }]
            delegate: HoloButton {
                required property var modelData
                width: 30; height: 30
                text: modelData.g
                onClicked: modelData.f()
            }
        }
    }
}
