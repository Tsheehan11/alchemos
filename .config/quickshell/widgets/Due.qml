// What's due: open SE tracker rows (overdue first, then the next two weeks), from the same feed as the
// agenda (orrin feed → agenda.json; refreshed after Orrin writes to the tracker). The nearest one sits
// in a countdown ring that closes over the last week. Double-click: sync now.
import QtQuick
import ".."

WidgetBody {
    id: w
    readonly property var all: (OrrinFeed.agenda || {}).due_all || (OrrinFeed.agenda || {}).due || []
    readonly property int count: size === "huge" ? 10 : size === "large" ? 7 : size === "small" ? 3 : 5
    readonly property var items: all.slice(0, count)
    readonly property var first: all.find(d => d.days >= 0) || null
    readonly property int late: all.filter(d => d.days < 0).length
    title: "DUE // TRACKER"
    detail: late ? late + " OVERDUE" : all.length ? all.length + " OPEN" : ""
    function doubleClicked() { OrrinFeed.refresh(); }
    function when(d) { return d.days < 0 ? (-d.days) + " D LATE" : d.days === 0 ? "TONIGHT" : d.days === 1 ? "TOMORROW" : d.days + " DAYS"; }

    implicitWidth: 320
    implicitHeight: Math.max(84, list.height)

    Item {
        width: 76; height: 76
        Ring { anchors.centerIn: parent; radius: 34; thickness: 1; value: 1; animated: false; color: Theme.p(0.3); trackColor: "transparent" }
        Ring {
            anchors.centerIn: parent; radius: 28; thickness: 4; animated: w.live
            value: w.first ? Math.max(0.02, 1 - Math.min(7, w.first.days + 0.5) / 7) : 0
            color: w.first && w.first.days <= 1 ? Theme.secondary : Theme.primary
        }
        Ring {
            anchors.centerIn: parent; radius: 20; thickness: 2; value: 1; animated: false; dashed: true; dash: [1, 6]
            color: Theme.p(0.4); trackColor: "transparent"
            rotation: w.live && !w.saver ? -w.t * 6 : 0
        }
        Column {
            anchors.centerIn: parent
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: w.first ? String(w.first.days) : "—"; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 20 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: w.first ? (w.first.days === 1 ? "DAY" : "DAYS") : ""; color: Theme.dim; font.family: Style.fonts.label; font.pixelSize: 8; font.letterSpacing: 2 }
        }
    }
    Column {
        id: list
        x: 88; width: 232; spacing: 4
        Text { visible: w.all.length === 0; width: parent.width; wrapMode: Text.WordWrap; text: !(OrrinFeed.agenda || {}).updated ? "READING TRACKER…" : OrrinFeed.problem("tracker") || "ALL CLEAR"; color: Theme.faint; font.family: Style.fonts.label; font.pixelSize: 12; font.letterSpacing: 2 }
        Repeater {
            model: w.items
            delegate: Column {
                required property var modelData
                width: 232
                Text {
                    width: 232; elide: Text.ElideRight
                    text: modelData.label || (modelData.course + " " + modelData.title)
                    color: modelData.days < 0 ? Theme.secondary : modelData.days <= 1 ? Theme.text : Theme.textSoft
                    font.family: Style.fonts.body; font.pixelSize: 12
                }
                Text {
                    text: "▲ " + w.when(modelData) + (modelData.status && modelData.status !== "Not Started" ? " · " + modelData.status.toUpperCase() : "")
                    color: modelData.days < 0 ? Theme.secondary : Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1
                }
            }
        }
    }
}
