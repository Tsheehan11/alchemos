// Claude usage for the whole account, not just Orrin (OrrinFeed.claude ← usage.json from `orrin usage --watch`,
// ~/.config/orrin/core/usage.py; no tokens spent on any of it):
//   headline   the Pro plan's 5-hour and weekly %, with reset times: the Claude CLI's /usage report, polled every
//              5 min (click the widget for now). Older than 15 min → shown as stale, never as current.
//   split bar  under each %: how much Orrin and Claude Code on this machine explain (their price-weighted tokens ×
//              a calibrated %/token), and the rest as "claude.ai + other devices", an ESTIMATE (hatched): there
//              are no local logs or API for claude.ai, so it's whatever the plan % has that this machine can't explain.
//   sources    fresh tokens (input + output) today and this plan week: Orrin (its SDK records), Claude Code (the
//              session logs' usage blocks only, never their content).
//   models     every model actually used, with its tokens; one model today → "TODAY: HAIKU 5.5 ONLY".
//   local      % of Orrin requests answered on this PC (regex fast path, local router, a "Did you mean" yes):
//              no Claude tokens at all (usage.json "local", from orrin.db action_log).
import QtQuick
import ".."

WidgetBody {
    id: w
    readonly property var u: OrrinFeed.claude || ({})
    readonly property var plan: u.plan || null
    readonly property bool current: plan !== null && !plan.stale
    readonly property var today: u.today || ({})
    readonly property var week: u.week || ({})
    readonly property var modelsToday: (u.models || {}).today || []
    readonly property var modelsWeek: (u.models || {}).week || []
    readonly property var localToday: (u.local || {}).today || ({})
    readonly property var localWeek: (u.local || {}).week || ({})
    readonly property var windows: [["five_hour", "5-HOUR"], ["seven_day", "WEEKLY"]]
    readonly property color cOrrin: Theme.primary
    readonly property color cCode: Theme.secondary
    readonly property color cOther: Theme.textSoft

    title: "CLAUDE // USAGE"
    detail: !u.updated ? "STARTING…" : !plan ? "NO PLAN REPORT" : plan.stale ? "REPORT STALE" : "PRO PLAN"
    alert: current && ((plan.five_hour || {}).pct || 0) >= 90
    implicitWidth: 340
    implicitHeight: col.height
    function clicked() { OrrinFeed.usageNow(); }

    function fresh(r) { return r ? (r.input || 0) + (r.output || 0) : 0; }
    function clock(sec) { return Qt.formatDateTime(new Date(sec * 1000), Theme.cfg.clock24 ? "HH:mm" : "h:mm AP"); }
    function resetText(sec) { return sec ? "RESETS " + OrrinFeed.until(sec * 1000).replace(/^IN /, "IN ") : ""; }
    function pctText(v) { return v < 10 && v > 0 ? v.toFixed(1) : String(Math.round(v)); }

    Column {
        id: col
        width: 340
        spacing: 6

        // ── plan windows: % + reset, then the split bar ──
        Repeater {
            model: w.plan ? w.windows.filter(k => w.plan[k[0]]) : []
            delegate: Column {
                id: pw
                required property var modelData
                readonly property var win: w.plan[modelData[0]]
                readonly property var sp: (w.plan.split || {})[modelData[0]] || ({})
                readonly property real pct: win.pct || 0
                readonly property color tone: !w.current ? Theme.faint : pct >= 80 ? Theme.secondary : Theme.text
                width: 340
                spacing: 3

                Item {
                    width: 340; height: 30
                    Text {
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 4
                        text: pw.modelData[1]; color: Theme.dim; font.family: Style.fonts.label; font.pixelSize: 9; font.letterSpacing: 2
                    }
                    Text {
                        x: 62; anchors.bottom: parent.bottom
                        text: Math.round(pw.pct) + "%"; color: pw.tone
                        font.family: Style.fonts.body; font.pixelSize: pw.modelData[0] === "five_hour" ? 26 : 20; font.weight: Font.Light
                    }
                    Text {
                        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.bottomMargin: 4
                        text: w.current ? w.resetText(pw.win.resets_at) : "LAST REPORT · NOT CURRENT"
                        color: w.current ? Theme.textSoft : Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1
                    }
                }
                // split bar: ORRIN | CLAUDE CODE | claude.ai + other (estimate, hatched) | free
                Item {
                    width: 340; height: 8
                    opacity: w.current ? 1 : 0.4
                    Rectangle { y: 4; width: 340; height: 1; color: Theme.p(0.16) }
                    Row {
                        y: 1
                        visible: pw.sp.calibrated === true
                        Rectangle { width: 340 * (pw.sp.orrin || 0) / 100; height: 6; color: w.cOrrin; opacity: 0.9 }
                        Rectangle { width: 340 * (pw.sp.code || 0) / 100; height: 6; color: w.cCode; opacity: 0.9 }
                        Item {     // the estimate: hatched, never solid
                            width: 340 * (pw.sp.other || 0) / 100; height: 6; clip: true
                            Rectangle { anchors.fill: parent; color: "transparent"; border.width: 1; border.color: Qt.rgba(w.cOther.r, w.cOther.g, w.cOther.b, 0.55) }
                            Row {
                                spacing: 2
                                Repeater {
                                    model: Math.ceil(parent.parent.width / 3)
                                    delegate: Rectangle { width: 1; height: 6; color: w.cOther; opacity: 0.5 }
                                }
                            }
                        }
                    }
                    // not calibrated yet: just the total
                    Rectangle {
                        visible: pw.sp.calibrated !== true
                        y: 1; width: 340 * Math.min(1, pw.pct / 100); height: 6; color: Theme.primary; opacity: 0.55
                    }
                }
                Text {
                    width: 340; wrapMode: Text.Wrap
                    textFormat: Text.StyledText
                    font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1; color: Theme.dim
                    text: pw.sp.calibrated === true
                          ? "<font color='" + w.cOrrin + "'>■</font> " + OrrinState.assistant + " " + w.pctText(pw.sp.orrin) + "%  "
                            + "<font color='" + w.cCode + "'>■</font> CLAUDE CODE " + w.pctText(pw.sp.code) + "%  "
                            + "<font color='" + w.cOther + "'>▨</font> CLAUDE.AI + OTHER DEVICES ~" + w.pctText(pw.sp.other) + "% (ESTIMATE)"
                          : "SPLIT · CALIBRATING (needs a window with some local use)"
                }
            }
        }

        // ── report status: when, from where; or plainly that there isn't one ──
        Text {
            width: 340; wrapMode: Text.Wrap
            font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1
            color: w.current ? Theme.faint : Theme.secondary
            text: !w.u.updated ? "Reading local usage…"
                  : !w.plan ? "NO PLAN REPORT · " + (w.u.plan_error || "the Claude CLI hasn't reported one yet")
                  : w.plan.stale ? "NO CURRENT REPORT · last one " + w.clock(w.plan.at) + (w.u.plan_error ? " · " + w.u.plan_error : "")
                  : "UPDATED " + w.clock(w.plan.at) + " · CLAUDE CLI /USAGE REPORT · EVERY 5 MIN · CLICK TO REFRESH"
        }

        Rectangle { width: 340; height: 1; color: Theme.p(0.12) }

        // ── by source: fresh tokens today / this plan week ──
        Column {
            width: 340; spacing: 2
            Row {
                Text { width: 150; text: "TOKENS IN + OUT"; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1 }
                Text { width: 95; text: "TODAY"; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1 }
                Text { width: 95; text: "PLAN WEEK"; color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1 }
            }
            Repeater {
                model: [["orrin", OrrinState.assistant], ["code", "CLAUDE CODE"]]
                delegate: Row {
                    required property var modelData
                    readonly property var td: w.today[modelData[0]] || ({})
                    readonly property var wk: w.week[modelData[0]] || ({})
                    Text {
                        width: 150; textFormat: Text.StyledText
                        text: "<font color='" + (modelData[0] === "orrin" ? w.cOrrin : w.cCode) + "'>■</font> " + modelData[1]
                        color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 11
                    }
                    Text { width: 95; text: OrrinFeed.tokens(w.fresh(td)) + (td.requests ? "  ·" + td.requests : ""); color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 11 }
                    Text { width: 95; text: OrrinFeed.tokens(w.fresh(wk)) + (wk.requests ? "  ·" + wk.requests : ""); color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 11 }
                }
            }
            Text {
                width: 340; wrapMode: Text.Wrap
                text: "·N = REQUESTS · CACHE R/W TODAY " + OrrinFeed.tokens(((w.today.orrin || {}).cache_read || 0) + ((w.today.code || {}).cache_read || 0))
                      + " / " + OrrinFeed.tokens(((w.today.orrin || {}).cache_write || 0) + ((w.today.code || {}).cache_write || 0))
                      + " · CLAUDE.AI HAS NO LOCAL RECORD (ESTIMATED ABOVE)"
                color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 8; font.letterSpacing: 1
            }
        }

        // ── Orrin requests answered on this PC (no tokens) ──
        Item {
            width: 340; height: 18
            visible: w.localWeek.pct !== undefined && w.localWeek.pct !== null
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: OrrinState.assistant + " HANDLED LOCALLY"; color: Theme.dim; font.family: Style.fonts.label; font.pixelSize: 9; font.letterSpacing: 2
            }
            HoloBar { x: 150; width: 70; height: 6; ticks: 4; anchors.verticalCenter: parent.verticalCenter; value: (w.localWeek.pct || 0) / 100; color: Theme.primary }
            Text {
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                text: (w.localToday.pct === null || w.localToday.pct === undefined ? "—" : Math.round(w.localToday.pct) + "%") + " TODAY · "
                      + Math.round(w.localWeek.pct || 0) + "% WEEK"
                color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 10
            }
        }

        Rectangle { width: 340; height: 1; color: Theme.p(0.12) }

        // ── models actually used ──
        Text {
            width: 340; wrapMode: Text.Wrap
            font.family: Style.fonts.body; font.pixelSize: 10; font.letterSpacing: 1
            color: Theme.textSoft
            text: w.modelsToday.length === 0 ? "TODAY: NO CLAUDE REQUESTS"
                  : w.modelsToday.length === 1 ? "TODAY: " + w.modelsToday[0].name.toUpperCase() + " ONLY · " + OrrinFeed.tokens(w.modelsToday[0].tokens)
                  : "TODAY: " + w.modelsToday.map(m => m.name.toUpperCase() + " " + OrrinFeed.tokens(m.tokens)).join(" · ")
        }
        Repeater {
            model: w.modelsWeek
            delegate: Item {
                required property var modelData
                readonly property real share: modelData.tokens / Math.max(1, w.modelsWeek.reduce((a, m) => a + m.tokens, 0))
                width: 340; height: 14
                Text { width: 96; text: modelData.name.toUpperCase(); color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1; anchors.verticalCenter: parent.verticalCenter }
                HoloBar { x: 98; width: 120; height: 6; ticks: 5; anchors.verticalCenter: parent.verticalCenter; value: parent.share; color: modelData.family === "haiku" ? Theme.primary : modelData.family === "opus" ? Theme.secondary : Theme.text }
                Text {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    text: OrrinFeed.tokens(modelData.tokens) + " · " + modelData.sources.map(s => s === "code" ? "CODE" : OrrinState.assistant).join("+")
                    color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 9
                }
            }
        }
        Text {
            visible: w.modelsWeek.length > 0
            text: "PLAN WEEK, BY MODEL"
            color: Theme.faint; font.family: Style.fonts.label; font.pixelSize: 8; font.letterSpacing: 2
        }
    }
}
