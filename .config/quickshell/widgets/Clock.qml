// Clock: digital (default) or analog ({"analog": true}), local or any time zone
// ({"tz": "America/New_York", "label": "New York"}).
import QtQuick
import Quickshell
import Quickshell.Io
import ".."

WidgetBody {
    id: w
    readonly property bool analog: params.analog === true
    readonly property string tz: params.tz || ""
    readonly property string place: params.label ? params.label.toUpperCase()
                                   : tz ? tz.split("/").pop().replace(/_/g, " ").toUpperCase() : ""
    title: "CLOCK" + (place ? " // " + place : "")
    detail: tz ? (tzOk ? utcLabel : "UNKNOWN ZONE") : "LOCAL"

    property int offsetMin: 0            // the zone's UTC offset
    property bool tzOk: true
    readonly property string utcLabel: "UTC" + (offsetMin >= 0 ? "+" : "−") + Math.floor(Math.abs(offsetMin) / 60) + (Math.abs(offsetMin) % 60 ? ":" + String(Math.abs(offsetMin) % 60).padStart(2, "0") : "")

    property var now: new Date()
    Timer { interval: w.saver ? 10000 : 1000; running: w.active; repeat: true; triggeredOnStart: true; onTriggered: w.now = new Date() }
    // The zone's wall time as a local Date (so Qt.formatDateTime can print it)
    function zoned(d) { return w.tz ? new Date(d.getTime() + (w.offsetMin + d.getTimezoneOffset()) * 60000) : d; }
    readonly property var shown: zoned(now)

    Process {
        id: tzProc
        command: ["sh", "-c", "[ -f \"/usr/share/zoneinfo/$0\" ] && TZ=\"$0\" date +%z || echo bad", w.tz]
        stdout: StdioCollector {
            onStreamFinished: {
                const s = text.trim();
                if (!/^[+-]\d{4}$/.test(s)) { w.tzOk = false; return; }
                w.tzOk = true;
                w.offsetMin = (s[0] === "-" ? -1 : 1) * (Number(s.slice(1, 3)) * 60 + Number(s.slice(3, 5)));
            }
        }
    }
    Timer { interval: 30 * 60000; running: w.tz !== "" && w.active; repeat: true; triggeredOnStart: true; onTriggered: tzProc.running = true }

    implicitWidth: analog ? 200 : 250
    implicitHeight: analog ? 214 : 92

    // ── digital ──
    Column {
        visible: !w.analog
        spacing: 2
        Row {
            spacing: 6
            Text {
                text: Qt.formatDateTime(w.shown, Theme.cfg.clock24 ? "HH:mm" : "h:mm")
                color: Theme.text
                font.family: w.mono; font.pixelSize: 46; font.weight: Font.Light
            }
            Column {
                anchors.bottom: parent.bottom; anchors.bottomMargin: 8
                Text { visible: !Theme.cfg.clock24; text: Qt.formatDateTime(w.shown, "AP"); color: Theme.secondary; font.family: w.mono; font.pixelSize: 13 }
                Text { visible: !w.saver; text: Qt.formatDateTime(w.shown, ":ss"); color: Theme.dim; font.family: w.mono; font.pixelSize: 15 }
            }
        }
        Text {
            text: Qt.formatDateTime(w.shown, "dddd · d MMM").toUpperCase()
            color: Theme.dim
            font.family: w.mono; font.pixelSize: 11; font.letterSpacing: 2
        }
    }

    // ── analog ──
    Item {
        id: dial
        visible: w.analog
        width: 172; height: 172
        x: 0
        readonly property real secs: {
            w.t;            // smooth sweep while effects run
            const d = w.live ? w.zoned(new Date()) : w.shown;
            return d.getSeconds() + (w.live ? d.getMilliseconds() / 1000 : 0);
        }
        readonly property real mins: w.shown.getMinutes() + secs / 60
        readonly property real hours: (w.shown.getHours() % 12) + mins / 60
        Ring { anchors.centerIn: parent; radius: 80; thickness: 1.5; value: 1; animated: false; color: Theme.p(0.55); trackColor: "transparent" }
        Ring { anchors.centerIn: parent; radius: 70; thickness: 1; value: 1; animated: false; dashed: true; dash: [1, 9]; color: Theme.p(0.35); trackColor: "transparent" }
        Repeater {
            model: 12
            delegate: Rectangle {
                required property int index
                x: 86 - width / 2; y: 8
                width: index % 3 === 0 ? 3 : 1.5; height: index % 3 === 0 ? 12 : 7
                color: index % 3 === 0 ? Theme.primary : Theme.p(0.6)
                transform: Rotation { origin.x: width / 2; origin.y: 78; angle: index * 30 }
            }
        }
        Rectangle {     // hour
            x: 86 - 2; y: 86 - 44; width: 4; height: 44; radius: 2; color: Theme.text; antialiasing: true
            transform: Rotation { origin.x: 2; origin.y: 44; angle: dial.hours * 30 }
        }
        Rectangle {     // minute
            x: 86 - 1.5; y: 86 - 64; width: 3; height: 64; radius: 1.5; color: Theme.primary; antialiasing: true
            transform: Rotation { origin.x: 1.5; origin.y: 64; angle: dial.mins * 6 }
        }
        Rectangle {     // second
            visible: !w.saver
            x: 86 - 0.75; y: 86 - 72; width: 1.5; height: 84; color: Theme.secondary; antialiasing: true
            transform: Rotation { origin.x: 0.75; origin.y: 72; angle: dial.secs * 6 }
        }
        Rectangle { anchors.centerIn: parent; width: 9; height: 9; radius: 4.5; color: Theme.secondary }
    }
    Text {
        visible: w.analog
        y: 178; width: 172; horizontalAlignment: Text.AlignHCenter
        text: Qt.formatDateTime(w.shown, Theme.cfg.clock24 ? "HH:mm · ddd" : "h:mm AP · ddd").toUpperCase()
        color: Theme.dim; font.family: w.mono; font.pixelSize: 11; font.letterSpacing: 2
    }
}
