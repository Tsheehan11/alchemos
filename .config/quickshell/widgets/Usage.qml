// Claude usage: tokens Jarvis has used this session (since it started) and today, from the Agent SDK's
// per-request usage (ResultMessage.model_usage → jarvis_db.claude_usage → status.json), with the Haiku /
// Sonnet / Opus split. Fresh input + output; cache reads / writes (mostly the CLI's own system prompt) are shown
// apart. Pro plan limits only appear when the Claude CLI itself has reported them (its rate-limit event:
// five-hour and weekly utilization and reset time), marked with when; there is no other source.
import QtQuick
import ".."

WidgetBody {
    id: w
    readonly property var u: JarvisFeed.usage || ({})
    readonly property var today: (u.today || {}).total || ({})
    readonly property var session: (u.session || {}).total || ({})
    readonly property var models: (u.today || {}).models || ({})
    readonly property var plan: u.plan || null
    function fresh(x) { return (x.input || 0) + (x.output || 0); }
    readonly property real split: {
        const h = fresh(models.haiku || {}), s = fresh(models.sonnet || {}), o = fresh(models.opus || {});
        return h + s + o > 0 ? h / (h + s + o) : 0;
    }
    readonly property var parts: ["haiku", "sonnet", "opus"].map(k => ({ k: k, v: fresh(models[k] || {}) })).filter(p => p.v > 0)
    readonly property real total: parts.reduce((a, p) => a + p.v, 0)

    title: "CLAUDE // USAGE"
    detail: JarvisFeed.online ? "PRO LOGIN" : "JARVIS OFF"
    implicitWidth: 320
    implicitHeight: col.height

    readonly property var shade: ({ haiku: Theme.primary, sonnet: Theme.secondary, opus: Theme.text })

    Column {
        id: col
        width: 320
        spacing: 6
        Row {
            spacing: 18
            Column {
                Text { text: JarvisFeed.tokens(w.fresh(w.today)); color: Theme.text; font.family: w.mono; font.pixelSize: 30; font.weight: Font.Light }
                Text { text: "TODAY · " + (w.today.requests || 0) + " REQ"; color: Theme.dim; font.family: w.mono; font.pixelSize: 9; font.letterSpacing: 2 }
            }
            Column {
                Text { text: JarvisFeed.tokens(w.fresh(w.session)); color: Theme.textSoft; font.family: w.mono; font.pixelSize: 20; font.weight: Font.Light; topPadding: 9 }
                Text { text: "SESSION · " + (w.session.requests || 0) + " REQ"; color: Theme.dim; font.family: w.mono; font.pixelSize: 9; font.letterSpacing: 2 }
            }
            Column {
                Text { text: JarvisFeed.tokens((w.today.cache_read || 0) + (w.today.cache_write || 0)); color: Theme.faint; font.family: w.mono; font.pixelSize: 14; topPadding: 15 }
                Text { text: "CACHE R/W"; color: Theme.faint; font.family: w.mono; font.pixelSize: 9; font.letterSpacing: 2 }
            }
        }
        // model split, as segments of light along one rail
        Item {
            width: 320; height: 10
            Rectangle { y: 5; width: 320; height: 1; color: Theme.p(0.16) }
            Row {
                y: 3
                Repeater {
                    model: w.parts
                    delegate: Rectangle {
                        required property var modelData
                        width: 320 * modelData.v / Math.max(1, w.total) - 2; height: 4
                        color: w.shade[modelData.k] || Theme.primary
                        opacity: 0.85
                        Rectangle { anchors.right: parent.right; width: 2; height: parent.height; color: "transparent" }
                    }
                }
            }
        }
        Row {
            spacing: 14
            Repeater {
                model: w.parts.length ? w.parts : [{ k: "no requests yet", v: 0 }]
                delegate: Text {
                    required property var modelData
                    text: (modelData.v ? "■ " : "") + modelData.k.toUpperCase() + (modelData.v ? " " + Math.round(100 * modelData.v / Math.max(1, w.total)) + "%" : "")
                    color: w.shade[modelData.k] || Theme.faint; font.family: w.mono; font.pixelSize: 10; font.letterSpacing: 1
                }
            }
        }
        // plan windows, only if the CLI reported them
        Column {
            visible: w.plan !== null
            width: 320; spacing: 3; topPadding: 4
            Repeater {
                model: w.plan ? [["five_hour", "5 H"], ["seven_day", "WEEK"]].filter(k => w.plan[k[0]]) : []
                delegate: Item {
                    required property var modelData
                    readonly property var win: w.plan[modelData[0]]
                    width: 320; height: 16
                    Text { width: 40; text: modelData[1]; color: Theme.dim; font.family: w.mono; font.pixelSize: 10; font.letterSpacing: 2; anchors.verticalCenter: parent.verticalCenter }
                    HoloBar { x: 42; width: 150; height: 6; anchors.verticalCenter: parent.verticalCenter; value: (win.pct || 0) / 100; color: win.pct >= 80 ? Theme.secondary : Theme.primary }
                    Text {
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        text: Math.round(win.pct || 0) + "%" + (win.resets_at ? " · RESET " + JarvisFeed.until(win.resets_at * 1000).replace(/^IN /, "") : "")
                        color: win.pct >= 80 ? Theme.secondary : Theme.textSoft; font.family: w.mono; font.pixelSize: 10
                    }
                }
            }
            Text {
                text: "PLAN · AS REPORTED BY CLAUDE " + (w.plan && w.plan.at ? Qt.formatDateTime(new Date(w.plan.at * 1000), Theme.cfg.clock24 ? "HH:mm" : "h:mm AP") : "")
                color: Theme.faint; font.family: w.mono; font.pixelSize: 9; font.letterSpacing: 1
            }
        }
        Text {
            visible: w.plan === null
            width: 320; wrapMode: Text.Wrap
            text: "PLAN LIMITS · not reported yet (Claude sends them with a new session's first reply)"
            color: Theme.faint; font.family: w.mono; font.pixelSize: 9; font.letterSpacing: 1
        }
    }
}
