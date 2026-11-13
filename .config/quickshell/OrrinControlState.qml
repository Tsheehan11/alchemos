pragma Singleton
// Orrin working a window (stage 4, ~/.config/orrin/core/control.py): which window, where, and what it's doing.
// core/control.Session beats `qs ipc call orrincontrol frame SCREEN X Y W H TEXT` every 0.5 s (X/Y relative to
// that screen, logical pixels); without a beat for 2 s the border goes (the plan's process died). `stop` is
// the kill switch (Super+Shift+Escape → `orrin control stop`, or "stop"): the border flashes STOPPED and goes.
import QtQuick
import Quickshell

Singleton {
    id: root
    property bool on: false
    property string screenName: ""
    property int wx: 0
    property int wy: 0
    property int ww: 0
    property int wh: 0
    property string text: ""
    property double lastBeat: 0
    property bool stopped: false          // shows STOPPED for a moment after the kill switch

    function show(scr, x, y, w, h, label) {
        if (root.stopped) return;          // a beat already in flight after the kill switch
        root.screenName = scr; root.wx = x; root.wy = y; root.ww = w; root.wh = h; root.text = label;
        root.lastBeat = Date.now();
        root.on = true;
    }
    function hide() { root.on = false; }
    function stop() {
        if (!root.on) return;
        root.stopped = true; root.text = "J.A.R.V.I.S CONTROL · STOPPED";
        stoppedTimer.restart();
    }

    Timer {
        interval: 500; running: root.on && !root.stopped; repeat: true
        onTriggered: if (Date.now() - root.lastBeat > 2000) root.on = false
    }
    Timer {
        id: stoppedTimer
        interval: 1200
        onTriggered: { root.on = false; root.stopped = false; }
    }
}
