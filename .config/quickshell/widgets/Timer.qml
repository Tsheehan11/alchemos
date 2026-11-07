// Countdown ({"minutes": 10, "label": "tea"}). Widgets.qml rings it (chime, Govee
// flash, toast, spoken line) even while hidden, and keeps the end time across restarts.
import QtQuick
import QtQml as Q      // this file is "Timer", so the QML timer needs its full name
import ".."

WidgetBody {
    id: w
    readonly property double end: params.end || 0
    readonly property real duration: params.duration || 1
    property double now: Date.now()
    Q.Timer { interval: 1000; running: w.active && !w.alert; repeat: true; triggeredOnStart: true; onTriggered: w.now = Date.now() }
    readonly property real remaining: Math.max(0, (end - now) / 1000)
    alert: params.done === true || (end > 0 && now >= end)
    title: "TIMER" + (params.label ? " // " + params.label.toUpperCase() : "")
    detail: alert ? "DONE" : "ENDS " + Qt.formatDateTime(new Date(end), Theme.cfg.clock24 ? "HH:mm" : "h:mm AP")

    function fmt(s) {
        s = Math.ceil(s);
        const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
        return (h > 0 ? h + ":" + String(m).padStart(2, "0") : String(m)) + ":" + String(sec).padStart(2, "0");
    }

    // Blink when done: with the effects clock if it runs, else a slow timer
    property bool blink: true
    Q.Timer { interval: 600; running: w.active && w.alert && !w.live; repeat: true; onTriggered: w.blink = !w.blink }
    readonly property real flash: w.live ? 0.35 + 0.65 * Math.abs(Math.sin(w.t * 3)) : (w.blink ? 1 : 0.35)

    implicitWidth: 250
    implicitHeight: 86

    Text {
        text: w.alert ? "TIME'S UP" : w.fmt(w.remaining)
        color: w.alert ? Theme.secondary : Theme.text
        opacity: w.alert ? w.flash : 1
        font.family: Style.fonts.numeric; font.pixelSize: w.alert ? 34 : 44; font.weight: Font.Light
    }
    HoloBar {       // time left
        y: 59; width: 250; height: 8; ticks: 10
        value: w.alert ? 1 : Math.min(1, w.remaining / w.duration)
        color: w.alert ? Theme.secondary : Theme.primary
        opacity: w.alert ? w.flash : 1
    }
    Text {
        y: 70; text: w.alert ? "CLOSE WITH ×" : Math.round(w.duration / 60) + " MIN"
        color: Theme.faint; font.family: Style.fonts.label; font.pixelSize: 10; font.letterSpacing: 2
    }
}
