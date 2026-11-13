// Agenda: the next events from his main Google Calendar and the Outlook ICS feed, merged with the SE
// tracker's due dates, with live countdowns. Data: OrrinFeed (jarvis feed → agenda.json; it syncs every
// few minutes and right after Jarvis edits the calendar or the tracker). Double-click: sync now.
// params: {"due": false} leaves the tracker out; size large / huge shows more.
//   ◆ Google   ◇ Outlook   ◈ both   ▲ due (tracker)
import QtQuick
import ".."

WidgetBody {
    id: w
    readonly property var ag: OrrinFeed.agenda || ({})
    readonly property double now: OrrinFeed.now
    readonly property bool withDue: params.due !== false
    readonly property int count: size === "huge" ? 10 : size === "large" ? 7 : size === "small" ? 3 : 5

    // events not over yet + open tracker rows, by time; all-day items first within their day
    readonly property var items: {
        const ev = (ag.events || []).filter(e => e.end > w.now);
        const due = w.withDue ? (ag.due || []) : [];
        const all = ev.concat(due.map(d => Object.assign({ start: d.due, all_day: false }, d)));
        all.sort((a, b) => (a.all_day && !b.all_day && OrrinFeed.dayLabel(a.start) === OrrinFeed.dayLabel(b.start) ? -1
                          : !a.all_day && b.all_day && OrrinFeed.dayLabel(a.start) === OrrinFeed.dayLabel(b.start) ? 1
                          : a.start - b.start));
        return all.slice(0, w.count);
    }
    readonly property var next: items.find(e => e.kind === "event" && !e.all_day) || null
    readonly property bool ongoing: next !== null && next.start <= now

    title: "AGENDA"
    detail: !ag.updated ? "SYNCING" : (ag.notes && ag.notes.length ? "STALE" : "LIVE")
    function doubleClicked() { OrrinFeed.refresh(); }

    implicitWidth: 330
    implicitHeight: hero.height + list.height + 10

    function glyph(e) { return e.kind === "due" || e.tracker ? "▲" : e.source === "outlook" ? "◇" : e.source === "both" ? "◈" : "◆"; }
    function when(e) {
        if (e.kind === "due" || e.tracker) return e.days < 0 ? "LATE" : "DUE";
        if (e.all_day) return "ALL DAY";
        return Qt.formatDateTime(new Date(e.start), Theme.cfg.clock24 ? "HH:mm" : "h:mm");
    }
    function rightText(e) {
        if (e.kind === "due" || (e.tracker && e.days !== undefined)) return e.days < 0 ? (-e.days) + " D AGO" : e.days === 0 ? "TONIGHT" : e.days === 1 ? "TOMORROW" : "IN " + e.days + " D";
        if (e.all_day) return OrrinFeed.dayLabel(e.start);
        if (e.start <= w.now) return "NOW";
        return OrrinFeed.until(e.start);
    }

    // ── next timed event, large ──
    Item {
        id: hero
        width: 330
        height: w.next ? 62 : Math.max(30, empty.implicitHeight + 8)
        Text {
            id: empty
            visible: !w.next
            width: parent.width; wrapMode: Text.WordWrap
            text: !ag.updated ? "LINKING CALENDAR…" : OrrinFeed.problem("calendar") || "NOTHING SCHEDULED"
            color: Theme.faint; font.family: Style.fonts.label; font.pixelSize: 12; font.letterSpacing: 2
        }
        Column {
            visible: w.next !== null
            width: 330
            spacing: 3
            Text {
                width: parent.width; elide: Text.ElideRight
                text: w.next ? w.next.title : ""
                color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 15
            }
            Row {
                spacing: 10
                Text {
                    text: w.next ? (w.ongoing ? "NOW" : OrrinFeed.until(w.next.start)) : ""
                    color: w.ongoing || (w.next && w.next.start - w.now < 15 * 60000) ? Theme.secondary : Theme.primary
                    font.family: Style.fonts.body; font.pixelSize: 20; font.weight: Font.Light
                }
                Text {
                    anchors.baseline: parent.children[0].baseline
                    text: w.next ? Qt.formatDateTime(new Date(w.next.start), Theme.cfg.clock24 ? "HH:mm" : "h:mm AP") + "–"
                                   + Qt.formatDateTime(new Date(w.next.end), Theme.cfg.clock24 ? "HH:mm" : "h:mm AP")
                                   + (w.next.where ? "  · " + w.next.where : "") : ""
                    width: 330 - parent.children[0].width - 10; elide: Text.ElideRight
                    color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 10
                }
            }
            HoloBar {      // ongoing: how far through; else the last hour before it, filling up
                width: 330; height: 6; ticks: 12
                color: w.ongoing ? Theme.secondary : Theme.primary
                value: !w.next ? 0 : w.ongoing ? (w.now - w.next.start) / Math.max(1, w.next.end - w.next.start)
                                               : Math.max(0, 1 - (w.next.start - w.now) / 3600000)
            }
        }
    }

    // ── the rest ──
    Column {
        id: list
        y: hero.height + 8
        width: 330
        spacing: 4
        Repeater {
            model: w.items.filter(e => e !== w.next)
            delegate: Item {
                required property var modelData
                readonly property bool isDue: modelData.kind === "due" || modelData.tracker === true
                readonly property bool late: isDue && modelData.days < 0
                width: 330; height: 18
                Text {
                    width: 16; text: w.glyph(modelData)
                    color: parent.isDue ? Theme.secondary : modelData.source === "outlook" ? Theme.dim : Theme.primary
                    font.family: Style.fonts.body; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    x: 16; width: 54; text: w.when(modelData)
                    color: parent.isDue ? Theme.secondary : Theme.dim
                    font.family: Style.fonts.body; font.pixelSize: 10; font.letterSpacing: 1; anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    x: 72; width: 330 - 72 - rt.width - 8; elide: Text.ElideRight
                    text: modelData.kind === "due" ? (modelData.label || modelData.title) : modelData.title
                    color: parent.late ? Theme.secondary : Theme.textSoft
                    font.family: Style.fonts.body; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    id: rt
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    text: w.rightText(modelData)
                    color: parent.late ? Theme.secondary : Theme.faint
                    font.family: Style.fonts.body; font.pixelSize: 10; font.letterSpacing: 1
                }
            }
        }
    }
}
