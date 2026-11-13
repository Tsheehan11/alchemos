// JARVIS console: conversations (voice + typed, one thread per conversation), typed requests through
// the same path as speech (fast path → local router → Claude), background tasks with a live log,
// and YES / NO for anything Jarvis is waiting on. Super + J, on the focused monitor (or a click on the
// JARVIS pop-up, on its monitor); Esc closes.
// Data: OrrinLink.qml (socket to ~/.config/jarvis/core/appserver.py).
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

PanelWindow {
    id: app
    required property var modelData
    screen: modelData
    // on the monitor it was opened on (OrrinLink.screenName), and mapped until it has faded out
    readonly property bool shown: OrrinLink.open && (OrrinLink.screenName ? OrrinLink.screenName === modelData.name
                                                                           : Hyprland.focusedMonitor?.name === modelData.name)
    visible: shown || backdrop.opacity > 0.01

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-jarvis-app"
    WlrLayershell.keyboardFocus: shown ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"

    readonly property var link: OrrinLink
    onShownChanged: if (shown) { OrrinState.dismiss(); Qt.callLater(() => input.focusInput()); }

    function when(ts) {
        if (!ts) return "";
        const d = new Date(ts * 1000), now = new Date();
        return d.toDateString() === now.toDateString() ? Qt.formatTime(d, "hh:mm") : Qt.formatDateTime(d, "ddd d MMM · hh:mm");
    }
    function statusColor(s) {
        return s === "running" ? Theme.primary : s === "done" ? Theme.dim : s === "queued" ? Theme.textSoft : Theme.secondary;
    }
    // "1m 12s" from seconds
    function span(sec) {
        sec = Math.max(0, Math.round(sec));
        return sec < 60 ? sec + "s" : sec < 3600 ? Math.floor(sec / 60) + "m " + (sec % 60) + "s" : Math.floor(sec / 3600) + "h " + Math.floor(sec % 3600 / 60) + "m";
    }
    // "GOOGLE → CALENDAR FIND" → "Google: calendar find"
    function plain(label) {
        const t = String(label || "").toLowerCase().replace(/\s*→\s*/, ": ").replace(/_/g, " ");
        return t.charAt(0).toUpperCase() + t.slice(1);
    }
    property double now: Date.now() / 1000
    property bool showHelp: false
    Timer { running: app.visible && (app.runningTasks > 0 || app.watchLive > 0); interval: 1000; repeat: true; onTriggered: app.now = Date.now() / 1000 }
    onVisibleChanged: if (visible) app.now = Date.now() / 1000
    readonly property int runningTasks: link.tasks.filter(t => t.status === "running").length
    readonly property var watchShown: link.watchers.filter(w => w.status === "active" || w.status === "paused"
                                                               || (w.finished && app.now - w.finished < 900))
    readonly property int watchLive: link.watchers.filter(w => w.status === "active" || w.status === "paused").length
    readonly property var selTask: link.tasks.find(t => t.id === link.selectedTask) || null

    // ── backdrop ──
    Rectangle {
        id: backdrop
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.55)
        opacity: app.shown ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: app.shown ? 180 : 220; easing.type: Easing.OutCubic } }
        MouseArea { anchors.fill: parent; enabled: app.shown; onClicked: OrrinLink.open = false }
    }

    HudFrame {
        id: panel
        width: Math.min(1320, app.width * 0.88)
        height: Math.min(820, app.height * 0.86)
        anchors.centerIn: parent
        opacity: app.shown ? 1 : 0
        scale: app.shown ? 1 : 0.965
        Behavior on opacity { NumberAnimation { duration: app.shown ? 220 : 200; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
        fill: 0.94
        title: (OrrinState.persona === "friday" ? "F.R.I.D.A.Y" : "J.A.R.V.I.S") + "  ·  CONSOLE"
        detail: (OrrinState.online ? (OrrinState.paused ? "PAUSED · COMBAT MODE" : "ONLINE")
                                    : OrrinState.toggleOn ? "STARTING…"
                                    : OrrinState.docked ? "OFFLINE · HISTORY ONLY · " + OrrinState.assistant + " IS OFF"
                                    : "OFFLINE · HISTORY ONLY · OFF ON THE LAPTOP (TURN ON: " + OrrinState.assistant + " TOGGLE)")
                + (OrrinState.laptopMode ? "   ·   LAPTOP MODE" : "")
                + "   ·   CLAUDE TURNS TODAY " + (link.usage.turns ?? 0)
                + ((link.usage.watch ?? 0) > 0 || (link.usage.control ?? 0) > 0
                   ? " (" + [(link.usage.watch ?? 0) > 0 ? "WATCHERS " + link.usage.watch : "",
                             (link.usage.control ?? 0) > 0 ? "CONTROL " + link.usage.control : ""].filter(x => x).join(" · ") + ")" : "")
                + (link.usage.five_hour !== undefined ? "   ·   5H " + link.usage.five_hour + "%" : "")
                + (link.usage.seven_day !== undefined ? "   ·   WEEK " + link.usage.seven_day + "%" : "")
        MouseArea { anchors.fill: parent; onClicked: {} }   // clicks inside don't close

        // a slow scan line across the frame
        Rectangle {
            id: scan
            width: parent.width; height: 1; y: -20
            color: Theme.p(0.35)
            SequentialAnimation on y {
                running: app.visible; loops: Animation.Infinite
                NumberAnimation { from: -20; to: panel.height - 34; duration: 6000; easing.type: Easing.InOutSine }
                NumberAnimation { from: panel.height - 34; to: -20; duration: 6000; easing.type: Easing.InOutSine }
            }
        }

        Row {
            anchors.fill: parent
            spacing: 14

            // ════ threads ════
            Column {
                id: left
                width: 260; height: parent.height
                spacing: 8
                HudInput {
                    id: search
                    width: parent.width
                    placeholder: "search conversations"
                    onTextChanged: searchDelay.restart()
                    onCancelled: OrrinLink.open = false
                    Timer { id: searchDelay; interval: 250; onTriggered: OrrinLink.search(search.text) }
                }
                Row {
                    spacing: 6
                    SmallButton { text: "NEW THREAD"; onClicked: { OrrinLink.newThread(); input.focusInput(); } }
                    SmallButton { text: "QUICK"; active: link.showQuick; onClicked: OrrinLink.setQuick(!link.showQuick) }
                }
                ListView {
                    id: threadList
                    width: parent.width; height: parent.height - 84
                    clip: true; spacing: 4
                    model: link.threads
                    delegate: Rectangle {
                        required property var modelData
                        width: threadList.width; height: 46
                        readonly property bool shown: link.shownThread && link.shownThread.id === modelData.id
                        readonly property bool active: modelData.id === link.current
                        color: shown ? Theme.p(0.16) : tma.containsMouse ? Theme.p(0.08) : "transparent"
                        border.color: active ? Theme.primary : Theme.p(shown ? 0.4 : 0.12)
                        Behavior on color { ColorAnimation { duration: 140 } }
                        // the active thread: a lit bar down its edge
                        Rectangle {
                            visible: parent.active
                            width: 3; height: parent.height; color: Theme.primary
                            SequentialAnimation on opacity {
                                running: parent.visible && app.visible && link.busy; loops: Animation.Infinite
                                NumberAnimation { to: 0.35; duration: 600 }
                                NumberAnimation { to: 1; duration: 600 }
                            }
                        }
                        Column {
                            anchors.fill: parent; anchors.margins: 6; anchors.leftMargin: 10; spacing: 2
                            Text {
                                width: parent.width; elide: Text.ElideRight
                                text: (modelData.kind === "task" ? "▣ " : modelData.kind === "quick" ? "· " : "") + modelData.title
                                color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 12
                            }
                            Text {
                                text: (parent.parent.active ? "● ACTIVE  ·  " : "") + app.when(modelData.updated) + "  ·  " + (modelData.n || 0) + " msg"
                                color: parent.parent.active ? Theme.primary : Theme.faint; font.family: Style.fonts.body; font.pixelSize: 10
                            }
                        }
                        MouseArea { id: tma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { OrrinLink.openThread(modelData.id); input.focusInput(); } }
                    }
                    Text {
                        visible: threadList.count === 0
                        width: parent.width; wrapMode: Text.Wrap
                        text: link.query ? "Nothing matches." : "No conversations yet. Talk to " + OrrinState.callOf("jarvis") + " or type below."
                        color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11
                    }
                }
            }

            Rectangle { width: 1; height: parent.height; color: Theme.p(0.15) }

            // ════ conversation ════
            Column {
                id: mid
                width: parent.width - left.width - right.width - 2 - 4 * 14
                height: parent.height
                spacing: 8

                Item {
                    id: midHead
                    width: parent.width; height: 28
                    readonly property bool active: !link.shownThread ? link.current === null : link.shownThread.id === link.current
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - resumeBtn.width - 10
                        spacing: 10
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: badge.implicitWidth + 14; height: 20
                            color: midHead.active ? Theme.p(0.18) : "transparent"
                            border.color: midHead.active ? Theme.primary : Theme.p(0.3)
                            Text {
                                id: badge; anchors.centerIn: parent
                                text: !link.shownThread ? "● NEW · STARTS WITH YOUR NEXT MESSAGE"
                                      : link.shownThread.kind === "task" ? "▣ TASK THREAD"
                                      : midHead.active ? "● ACTIVE · NEW MESSAGES GO HERE" : "OLDER THREAD · RESUME TO CONTINUE IT"
                                color: midHead.active ? Theme.primary : Theme.dim
                                font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 260; elide: Text.ElideRight
                            text: link.shownThread ? link.shownThread.title.toUpperCase() : ""
                            color: Theme.primary; font.family: Style.fonts.body; font.pixelSize: 12; font.letterSpacing: 2
                        }
                    }
                    SmallButton {
                        id: resumeBtn
                        anchors.right: parent.right
                        visible: link.connected && link.shownThread && link.shownThread.id !== link.current
                        text: "RESUME"
                        onClicked: { OrrinLink.resume(link.shownThread.id); input.focusInput(); }
                    }
                }

                // Jarvis is waiting for a yes. A window-control plan (core/control.plan_text) shows in full; a background
                // task's plan can also be answered ALLOW TASK (its later plans for that window, for that task only).
                Column {
                    id: confirmCol
                    visible: link.confirms.length > 0
                    width: mid.width; spacing: 8
                    Repeater {
                        model: link.confirms
                        delegate: Rectangle {
                            id: cf
                            required property var modelData
                            readonly property bool plan: modelData.prompt.indexOf("\nPLAN · ") >= 0
                            width: mid.width; height: plan ? planText.implicitHeight + 20 : 44
                            color: Theme.s(0.14); border.color: Theme.secondary
                            Text {
                                id: planText
                                anchors.left: parent.left; anchors.leftMargin: 10
                                anchors.top: cf.plan ? parent.top : undefined; anchors.topMargin: 10
                                anchors.verticalCenter: cf.plan ? undefined : parent.verticalCenter
                                width: parent.width - (cf.modelData.allow_task ? 270 : 170)
                                elide: cf.plan ? Text.ElideNone : Text.ElideRight
                                wrapMode: cf.plan ? Text.Wrap : Text.NoWrap
                                text: (cf.modelData.title ? cf.modelData.title.toUpperCase() + " · " : "") + cf.modelData.prompt
                                color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 12; lineHeight: 1.15
                            }
                            Row {
                                anchors.right: parent.right; anchors.rightMargin: 6
                                anchors.top: cf.plan ? parent.top : undefined; anchors.topMargin: 8
                                anchors.verticalCenter: cf.plan ? undefined : parent.verticalCenter
                                spacing: 6
                                SmallButton { text: "YES"; active: true; onClicked: OrrinLink.answer(cf.modelData.id, true) }
                                SmallButton { visible: cf.modelData.allow_task === true; text: "ALLOW TASK"; onClicked: OrrinLink.answer(cf.modelData.id, "task") }
                                SmallButton { text: "NO"; onClicked: OrrinLink.answer(cf.modelData.id, false) }
                            }
                        }
                    }
                }

                ListView {
                    id: msgList
                    width: parent.width
                    height: parent.height - 28 - 8 - (link.confirms.length ? confirmCol.height + 8 : 0) - liveLine.height - 8 - inputRow.height - 16
                    clip: true; spacing: 12
                    model: link.messages
                    boundsBehavior: Flickable.StopAtBounds
                    flickDeceleration: 2500; maximumFlickVelocity: 4000
                    // follow new messages only while he's reading the end (or it's his own message / a new thread)
                    property bool follow: true
                    onMovementEnded: follow = atYEnd
                    onCountChanged: {
                        const last = link.messages[link.messages.length - 1];
                        if (follow || count <= 1 || (last && last.role === "user")) { follow = true; Qt.callLater(() => msgList.positionViewAtEnd()); }
                    }
                    Connections {
                        target: OrrinLink
                        function onShownThreadChanged() { msgList.follow = true; Qt.callLater(() => msgList.positionViewAtEnd()); }
                    }
                    delegate: Column {
                        required property var modelData
                        width: msgList.width
                        spacing: 3
                        readonly property bool me: modelData.role === "user"
                        Text {
                            text: (me ? "YOU" : OrrinState.nameOf(modelData.persona)) + "  ·  " + (modelData.source || "").toUpperCase() + "  ·  " + app.when(modelData.ts)
                                  + (!me && modelData.tier ? "  ·  " + modelData.tier.toUpperCase() : "")
                            color: me ? Theme.dim : Theme.primary
                            font.family: Style.fonts.body; font.pixelSize: 10; font.letterSpacing: 1
                        }
                        Text {
                            width: parent.width; wrapMode: Text.Wrap
                            text: modelData.text
                            color: me ? Theme.text : Theme.textSoft
                            font.family: Style.fonts.body; font.pixelSize: 13
                            textFormat: Text.PlainText
                        }
                        Flow {
                            width: parent.width; spacing: 6
                            visible: (modelData.tools || []).length > 0
                            Repeater {
                                model: modelData.tools || []
                                delegate: Rectangle {
                                    required property var modelData
                                    width: chip.implicitWidth + 12; height: 20
                                    color: Theme.p(0.08); border.color: modelData.indexOf("[declined]") >= 0 || modelData.indexOf("[failed]") >= 0 ? Theme.secondary : Theme.p(0.25)
                                    Text {
                                        id: chip; anchors.centerIn: parent
                                        text: "◆ " + (modelData.length > 70 ? modelData.slice(0, 70) + "…" : modelData)
                                        color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 10
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        visible: msgList.count === 0
                        anchors.centerIn: parent
                        text: link.connected ? "Ask " + OrrinState.callOf(OrrinState.persona) + " anything, or switch to TASK for a background job." : OrrinState.callOf("jarvis") + " is offline. History stays readable."
                        color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 12
                    }
                    // scroll position
                    Rectangle {
                        visible: msgList.contentHeight > msgList.height
                        anchors.right: parent.right
                        width: 3; radius: 1.5; color: Theme.p(0.45)
                        height: Math.max(24, msgList.height * msgList.visibleArea.heightRatio)
                        y: msgList.visibleArea.yPosition * msgList.height
                        opacity: msgList.moving ? 1 : 0.45
                        Behavior on opacity { NumberAnimation { duration: 200 } }
                    }
                    SmallButton {
                        visible: !msgList.follow && !msgList.atYEnd
                        anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                        text: "▼ LATEST"
                        onClicked: { msgList.follow = true; msgList.positionViewAtEnd(); }
                    }
                }

                Text {
                    id: liveLine
                    width: parent.width; height: 16; elide: Text.ElideRight
                    text: link.busy ? "◇ " + (OrrinState.phase === "listening" ? "LISTENING" : "WORKING") + (link.liveTool ? "  ·  " + link.liveTool : "")
                                      + (link.busyText ? "  ·  " + link.busyText : "") : ""
                    color: Theme.primary; font.family: Style.fonts.body; font.pixelSize: 11
                    SequentialAnimation on opacity {
                        running: link.busy; loops: Animation.Infinite
                        NumberAnimation { to: 0.35; duration: 600 }
                        NumberAnimation { to: 1; duration: 600 }
                    }
                }

                Row {
                    id: inputRow
                    width: parent.width; height: 36; spacing: 8
                    SmallButton {
                        text: link.mode
                        active: link.mode === "TASK"
                        height: 36
                        onClicked: OrrinLink.mode = link.mode === "ASK" ? "TASK" : "ASK"
                    }
                    HudInput {
                        id: input
                        width: parent.width - 90; height: 36
                        maximumLength: 2000
                        placeholder: !link.connected ? OrrinState.callOf("jarvis") + " is offline" : link.mode === "TASK" ? "describe a background task…  (Enter)" : "ask " + OrrinState.callOf(OrrinState.persona) + "…  (Enter)"
                        onAccepted: { if (link.connected && text.trim()) { OrrinLink.ask(text); text = ""; } }
                        onCancelled: OrrinLink.open = false
                    }
                }
            }

            Rectangle { width: 1; height: parent.height; color: Theme.p(0.15) }

            // ════ watchers + tasks ════
            Column {
                id: right
                width: 320; height: parent.height
                spacing: 8
                // ── watchers (core/watch.py): live ones, plus any that finished in the last 15 minutes ──
                Column {
                    id: watchBox
                    width: parent.width
                    spacing: 6
                    visible: app.watchShown.length > 0
                    height: visible ? implicitHeight : 0
                    Text {
                        text: "WATCHERS  ·  " + app.watchLive + "/3"
                        color: Theme.primary; font.family: Style.fonts.body; font.pixelSize: 12; font.letterSpacing: 2
                    }
                    Repeater {
                        model: app.watchShown
                        delegate: Rectangle {
                            id: wcard
                            required property var modelData
                            readonly property var w: modelData
                            readonly property bool live: w.status === "active" || w.status === "paused"
                            readonly property string chipText: w.status === "active" ? (w.combat ? "PAUSED · COMBAT" : w.laptop ? "PAUSED · ON LAPTOP" : link.connected ? "WATCHING" : "PAUSED · " + OrrinState.assistant + " OFF")
                                                            : w.status === "paused" ? "PAUSED" : w.status === "done" ? "SEEN" : w.status.toUpperCase()
                            readonly property color tone: w.status === "active" && !w.combat && !w.laptop && link.connected ? Theme.primary
                                                        : w.status === "done" ? Theme.secondary : Theme.dim
                            width: watchBox.width
                            height: wcol.implicitHeight + 14
                            color: Theme.p(live ? 0.06 : 0.0)
                            border.color: w.status === "done" ? Theme.secondary : Theme.p(0.18)
                            opacity: live ? 1 : 0.75
                            Column {
                                id: wcol
                                x: 8; y: 7; width: parent.width - 16
                                spacing: 4
                                Row {
                                    spacing: 8; width: parent.width
                                    Rectangle {
                                        width: wchip.implicitWidth + 10; height: 16
                                        color: Qt.rgba(wcard.tone.r, wcard.tone.g, wcard.tone.b, 0.15); border.color: wcard.tone
                                        Text { id: wchip; anchors.centerIn: parent; text: wcard.chipText; color: wcard.tone; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1 }
                                        SequentialAnimation on opacity {
                                            running: wcard.chipText === "WATCHING" && app.visible; loops: Animation.Infinite
                                            NumberAnimation { to: 0.45; duration: 900 }
                                            NumberAnimation { to: 1; duration: 900 }
                                        }
                                    }
                                    Text {
                                        width: parent.width - wchip.implicitWidth - 18; elide: Text.ElideRight
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: wcard.w.label; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 11
                                        textFormat: Text.PlainText
                                    }
                                }
                                Text {
                                    width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                                    text: "For: " + wcard.w.condition; color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 11
                                    textFormat: Text.PlainText
                                }
                                Text {
                                    width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
                                    visible: text !== ""
                                    text: wcard.w.result || wcard.w.note || ""
                                    color: wcard.w.status === "done" ? Theme.secondary : Theme.dim; font.family: Style.fonts.body; font.pixelSize: 10
                                    textFormat: Text.PlainText
                                }
                                Text {
                                    visible: wcard.live
                                    text: "every " + Math.round(wcard.w.interval) + "s  ·  " + app.span(Math.max(0, wcard.w.expires - app.now)) + " left  ·  "
                                          + wcard.w.calls + (wcard.w.calls === 1 ? " Claude look" : " Claude looks")
                                    color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 10
                                }
                                Row {
                                    visible: wcard.live && link.connected
                                    spacing: 6
                                    SmallButton { text: wcard.w.status === "paused" ? "RESUME" : "PAUSE"; onClicked: OrrinLink.pauseWatch(wcard.w.id, wcard.w.status !== "paused") }
                                    SmallButton { text: "STOP"; onClicked: OrrinLink.stopWatch(wcard.w.id) }
                                }
                            }
                        }
                    }
                }
                Item {
                    width: parent.width; height: 18
                    Text {
                        width: parent.width - helpBtn.width - 8; elide: Text.ElideRight
                        anchors.verticalCenter: parent.verticalCenter
                        text: "TASKS  ·  " + app.runningTasks + "/2 RUNNING"
                        color: Theme.primary; font.family: Style.fonts.body; font.pixelSize: 12; font.letterSpacing: 2
                    }
                    SmallButton {
                        id: helpBtn
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        visible: link.tasks.length > 0
                        text: app.showHelp ? "HIDE HELP" : "HELP"
                        onClicked: app.showHelp = !app.showHelp
                    }
                }
                // what a task is (always shown while there are none)
                Rectangle {
                    id: help
                    visible: link.tasks.length === 0 || app.showHelp
                    width: parent.width; height: visible ? helpText.implicitHeight + 20 : 0
                    color: Theme.p(0.05); border.color: Theme.p(0.18)
                    Text {
                        id: helpText
                        x: 10; y: 10; width: parent.width - 20
                        wrapMode: Text.Wrap; textFormat: Text.StyledText
                        color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 11; lineHeight: 1.15
                        text: "<b>A task is a job " + OrrinState.callOf("jarvis") + " does in the background</b> while you carry on: many steps "
                            + "(up to 40 tool calls), its own thread, and a spoken note when it's done. Two run at once.<br><br>"
                            + "<b>Start one</b><br>"
                            + "· <b>Type</b>: switch the box below from ASK to <b>TASK</b>, describe the job, Enter.<br>"
                            + "· <b>Say</b>: \"Jarvis, do this in the background: …\"<br>"
                            + "· Ask for something long, and " + OrrinState.callOf("jarvis") + " may hand it to a task itself.<br><br>"
                            + "<b>Examples</b><br>"
                            + "· Compare my tracker with LEARN and list what's different<br>"
                            + "· Summarise this week's course emails<br>"
                            + "· Check my calendar and tracker and plan my week<br><br>"
                            + "Anything that changes something still waits for your yes; it shows here as NEEDS YOUR YES."
                    }
                }
                ListView {
                    id: taskList
                    width: parent.width
                    height: Math.min(contentHeight, (parent.height - help.height) * 0.5)
                    clip: true; spacing: 6
                    model: link.tasks
                    delegate: Rectangle {
                        id: card
                        required property var modelData
                        readonly property var t: modelData
                        readonly property var ask: link.confirms.find(c => c.origin === "task:" + t.id) || null
                        readonly property string state_: ask || t.waiting ? "waiting" : t.status
                        readonly property color tone: state_ === "waiting" ? Theme.secondary : app.statusColor(t.status)
                        readonly property double elapsed: t.started ? ((t.finished || app.now) - t.started) : 0
                        width: taskList.width
                        height: col.implicitHeight + 14
                        color: link.selectedTask === t.id ? Theme.p(0.14) : Theme.p(state_ === "running" ? 0.06 : 0.0)
                        border.color: state_ === "waiting" ? Theme.secondary : link.selectedTask === t.id ? Theme.p(0.45) : Theme.p(0.18)
                        Behavior on height { NumberAnimation { duration: 160 } }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: OrrinLink.selectTask(card.t.id) }
                        Column {
                            id: col
                            x: 8; y: 7; width: parent.width - 16
                            spacing: 5
                            Row {
                                spacing: 8; width: parent.width
                                Rectangle {
                                    width: chip.implicitWidth + 10; height: 16
                                    color: Qt.rgba(card.tone.r, card.tone.g, card.tone.b, 0.15); border.color: card.tone
                                    Text {
                                        id: chip; anchors.centerIn: parent
                                        text: ({waiting: "NEEDS YOUR YES", running: "RUNNING", queued: "QUEUED", done: "DONE",
                                                failed: "FAILED", cancelled: "CANCELLED", interrupted: "INTERRUPTED"})[card.state_] || card.state_.toUpperCase()
                                        color: card.tone; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1
                                    }
                                    SequentialAnimation on opacity {
                                        running: app.visible && (card.state_ === "running" || card.state_ === "waiting"); loops: Animation.Infinite
                                        NumberAnimation { to: 0.45; duration: 700 }
                                        NumberAnimation { to: 1; duration: 700 }
                                    }
                                }
                                Text {
                                    width: parent.width - chip.implicitWidth - 18; elide: Text.ElideRight
                                    text: card.t.title; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 12
                                }
                            }
                            // progress: steps used of the budget, with a sweep while it works
                            Rectangle {
                                visible: card.state_ === "running" || card.state_ === "waiting"
                                width: parent.width; height: 4; color: Theme.p(0.1); clip: true
                                Rectangle {
                                    width: parent.width * Math.min(1, Math.max(0.04, card.t.steps / (card.t.max_steps || 40)))
                                    height: parent.height; color: card.tone
                                    Behavior on width { NumberAnimation { duration: 300 } }
                                }
                                Rectangle {
                                    width: 40; height: parent.height; opacity: 0.6
                                    gradient: Gradient { orientation: Gradient.Horizontal
                                        GradientStop { position: 0; color: "transparent" } GradientStop { position: 0.5; color: Theme.text } GradientStop { position: 1; color: "transparent" } }
                                    NumberAnimation on x { running: app.visible && card.state_ === "running"; from: -40; to: card.width; duration: 1400; loops: Animation.Infinite }
                                }
                            }
                            Text {
                                width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
                                font.family: Style.fonts.body; font.pixelSize: 10
                                color: card.state_ === "waiting" ? Theme.secondary : Theme.dim
                                text: {
                                    const t = card.t, steps = t.steps + (t.steps === 1 ? " step" : " steps");
                                    switch (card.state_) {
                                    case "waiting": return "Waiting for you: " + ((card.ask && card.ask.prompt) || t.waiting).split("\n")[0] + "  ·  " + app.span(card.elapsed);
                                    case "running": return (t.now ? "Now: " + app.plain(t.now) : "Starting…") + "  ·  " + steps + "  ·  " + app.span(card.elapsed);
                                    case "queued": return "Waiting for a free slot (" + (t.slots || 2) + " run at once)";
                                    case "done": return "Done in " + app.span(card.elapsed) + "  ·  " + steps + "  ·  " + app.when(t.finished);
                                    case "failed": return "Failed after " + app.span(card.elapsed) + "  ·  " + steps + "  ·  see the log";
                                    case "cancelled": return "Cancelled  ·  " + steps;
                                    case "interrupted": return "Stopped when " + OrrinState.callOf("jarvis") + " restarted  ·  RESUME picks it up";
                                    }
                                    return steps;
                                }
                            }
                            Row {
                                visible: card.ask !== null
                                spacing: 6
                                SmallButton { text: "YES"; active: true; onClicked: OrrinLink.answer(card.ask.id, true) }
                                SmallButton { visible: card.ask !== null && card.ask.allow_task === true; text: "ALLOW TASK"; onClicked: OrrinLink.answer(card.ask.id, "task") }
                                SmallButton { text: "NO"; onClicked: OrrinLink.answer(card.ask.id, false) }
                            }
                        }
                    }
                }
                Row {
                    spacing: 6
                    visible: app.selTask !== null
                    SmallButton { visible: app.selTask && (app.selTask.status === "running" || app.selTask.status === "queued"); text: "CANCEL"; onClicked: OrrinLink.cancelTask(app.selTask.id) }
                    SmallButton { visible: app.selTask && ["interrupted", "failed", "cancelled"].indexOf(app.selTask.status) >= 0 && link.connected; text: "RESUME"; onClicked: OrrinLink.resumeTask(app.selTask.id) }
                    SmallButton { visible: app.selTask && app.selTask.thread; text: "THREAD"; onClicked: OrrinLink.openThread(app.selTask.thread) }
                }
                Rectangle {
                    width: parent.width
                    height: parent.height - 18 - help.height - taskList.height - (app.selTask ? 34 : 0) - 4 * 8
                            - (watchBox.visible ? watchBox.height + 8 : 0)
                    color: Theme.d(0.6); border.color: Theme.p(0.12)
                    ListView {
                        id: logList
                        anchors.fill: parent; anchors.margins: 8
                        clip: true; spacing: 3
                        model: link.taskLines
                        onCountChanged: Qt.callLater(() => logList.positionViewAtEnd())
                        delegate: Text {
                            required property var modelData
                            width: logList.width; wrapMode: Text.Wrap
                            text: (modelData.kind === "step" ? "◆ " : modelData.kind === "error" ? "✕ " : modelData.kind === "note" ? "· " : "") + modelData.text
                            color: modelData.kind === "error" ? Theme.secondary : modelData.kind === "text" ? Theme.textSoft : Theme.dim
                            font.family: Style.fonts.body; font.pixelSize: 11
                            textFormat: Text.PlainText
                        }
                        Text {
                            visible: logList.count === 0
                            text: app.selTask ? "No log yet." : "Select a task to see its log."
                            color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 11
                        }
                    }
                }
            }
        }
    }
}
