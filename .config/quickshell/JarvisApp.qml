// JARVIS console: conversations (voice + typed, one thread per conversation), typed requests through
// the same path as speech (fast path → local router → Claude), background tasks with a live log,
// and YES / NO for anything Jarvis is waiting on. Super + J, on the focused monitor (or a click on the
// JARVIS pop-up, on its monitor); Esc closes.
// Data: JarvisLink.qml (socket to ~/.config/jarvis/core/appserver.py).
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

PanelWindow {
    id: app
    required property var modelData
    screen: modelData
    visible: JarvisLink.open && (JarvisLink.screenName ? JarvisLink.screenName === modelData.name
                                                       : Hyprland.focusedMonitor?.name === modelData.name)

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-jarvis-app"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"

    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property var link: JarvisLink
    onVisibleChanged: if (visible) input.focusInput()

    function when(ts) {
        if (!ts) return "";
        const d = new Date(ts * 1000), now = new Date();
        return d.toDateString() === now.toDateString() ? Qt.formatTime(d, "hh:mm") : Qt.formatDateTime(d, "ddd d MMM · hh:mm");
    }
    function statusColor(s) {
        return s === "running" ? Theme.primary : s === "done" ? Theme.dim : s === "queued" ? Theme.textSoft : Theme.secondary;
    }
    readonly property int runningTasks: link.tasks.filter(t => t.status === "running").length
    readonly property var selTask: link.tasks.find(t => t.id === link.selectedTask) || null

    // ── backdrop ──
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.55)
        MouseArea { anchors.fill: parent; onClicked: JarvisLink.open = false }
    }

    HudFrame {
        id: panel
        width: Math.min(1320, app.width * 0.88)
        height: Math.min(820, app.height * 0.86)
        anchors.centerIn: parent
        fill: 0.94
        title: "J.A.R.V.I.S  ·  CONSOLE"
        detail: (JarvisState.online ? (JarvisState.paused ? "PAUSED · COMBAT MODE" : "ONLINE")
                                    : "OFFLINE · HISTORY ONLY · RUNS WHILE DOCKED")
                + "   ·   CLAUDE TURNS TODAY " + (link.usage.turns ?? 0)
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
                    onCancelled: JarvisLink.open = false
                    Timer { id: searchDelay; interval: 250; onTriggered: JarvisLink.search(search.text) }
                }
                Row {
                    spacing: 6
                    SmallButton { text: "NEW"; onClicked: { JarvisLink.newThread(); input.focusInput(); } }
                    SmallButton { text: "QUICK"; active: link.showQuick; onClicked: JarvisLink.setQuick(!link.showQuick) }
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
                        color: shown ? Theme.p(0.16) : tma.containsMouse ? Theme.p(0.08) : "transparent"
                        border.color: modelData.id === link.current ? Theme.primary : Theme.p(shown ? 0.4 : 0.12)
                        Column {
                            anchors.fill: parent; anchors.margins: 6; spacing: 2
                            Text {
                                width: parent.width; elide: Text.ElideRight
                                text: (modelData.kind === "task" ? "▣ " : modelData.kind === "quick" ? "· " : "") + modelData.title
                                color: Theme.text; font.family: app.mono; font.pixelSize: 12
                            }
                            Text {
                                text: app.when(modelData.updated) + "  ·  " + (modelData.n || 0) + " msg" + (modelData.id === link.current ? "  ·  CURRENT" : "")
                                color: Theme.faint; font.family: app.mono; font.pixelSize: 10
                            }
                        }
                        MouseArea { id: tma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: JarvisLink.openThread(modelData.id) }
                    }
                    Text {
                        visible: threadList.count === 0
                        width: parent.width; wrapMode: Text.Wrap
                        text: link.query ? "Nothing matches." : "No conversations yet. Talk to Jarvis or type below."
                        color: Theme.faint; font.family: app.mono; font.pixelSize: 11
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
                    width: parent.width; height: 28
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - resumeBtn.width - 10; elide: Text.ElideRight
                        text: link.shownThread ? link.shownThread.title.toUpperCase() : "NEW CONVERSATION"
                        color: Theme.primary; font.family: app.mono; font.pixelSize: 12; font.letterSpacing: 2
                    }
                    SmallButton {
                        id: resumeBtn
                        anchors.right: parent.right
                        visible: link.connected && link.shownThread && link.shownThread.id !== link.current
                        text: "RESUME"
                        onClicked: { JarvisLink.resume(link.shownThread.id); input.focusInput(); }
                    }
                }

                // Jarvis is waiting for a yes
                Repeater {
                    model: link.confirms
                    delegate: Rectangle {
                        required property var modelData
                        width: mid.width; height: 44
                        color: Theme.s(0.14); border.color: Theme.secondary
                        Text {
                            anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 170; elide: Text.ElideRight
                            text: (modelData.title ? modelData.title.toUpperCase() + " · " : "") + modelData.prompt
                            color: Theme.text; font.family: app.mono; font.pixelSize: 12
                        }
                        Row {
                            anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                            spacing: 6
                            SmallButton { text: "YES"; active: true; onClicked: JarvisLink.answer(modelData.id, true) }
                            SmallButton { text: "NO"; onClicked: JarvisLink.answer(modelData.id, false) }
                        }
                    }
                }

                ListView {
                    id: msgList
                    width: parent.width
                    height: parent.height - 28 - 8 - link.confirms.length * 52 - liveLine.height - 8 - inputRow.height - 16
                    clip: true; spacing: 12
                    model: link.messages
                    onCountChanged: Qt.callLater(() => msgList.positionViewAtEnd())
                    delegate: Column {
                        required property var modelData
                        width: msgList.width
                        spacing: 3
                        readonly property bool me: modelData.role === "user"
                        Text {
                            text: (me ? "YOU" : "JARVIS") + "  ·  " + (modelData.source || "").toUpperCase() + "  ·  " + app.when(modelData.ts)
                                  + (!me && modelData.tier ? "  ·  " + modelData.tier.toUpperCase() : "")
                            color: me ? Theme.dim : Theme.primary
                            font.family: app.mono; font.pixelSize: 10; font.letterSpacing: 1
                        }
                        Text {
                            width: parent.width; wrapMode: Text.Wrap
                            text: modelData.text
                            color: me ? Theme.text : Theme.textSoft
                            font.family: app.mono; font.pixelSize: 13
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
                                        color: Theme.dim; font.family: app.mono; font.pixelSize: 10
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        visible: msgList.count === 0
                        anchors.centerIn: parent
                        text: link.connected ? "Ask Jarvis anything, or switch to TASK for a background job." : "Jarvis is offline. History stays readable."
                        color: Theme.faint; font.family: app.mono; font.pixelSize: 12
                    }
                }

                Text {
                    id: liveLine
                    width: parent.width; height: 16; elide: Text.ElideRight
                    text: link.busy ? "◇ " + (JarvisState.phase === "listening" ? "LISTENING" : "WORKING") + (link.liveTool ? "  ·  " + link.liveTool : "")
                                      + (link.busyText ? "  ·  " + link.busyText : "") : ""
                    color: Theme.primary; font.family: app.mono; font.pixelSize: 11
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
                        onClicked: JarvisLink.mode = link.mode === "ASK" ? "TASK" : "ASK"
                    }
                    HudInput {
                        id: input
                        width: parent.width - 90; height: 36
                        maximumLength: 2000
                        placeholder: !link.connected ? "Jarvis is offline" : link.mode === "TASK" ? "describe a background task…  (Enter)" : "ask Jarvis…  (Enter)"
                        onAccepted: { if (link.connected && text.trim()) { JarvisLink.ask(text); text = ""; } }
                        onCancelled: JarvisLink.open = false
                    }
                }
            }

            Rectangle { width: 1; height: parent.height; color: Theme.p(0.15) }

            // ════ tasks ════
            Column {
                id: right
                width: 320; height: parent.height
                spacing: 8
                Text {
                    text: "TASKS  ·  " + app.runningTasks + "/2 RUNNING"
                    color: Theme.primary; font.family: app.mono; font.pixelSize: 12; font.letterSpacing: 2
                }
                ListView {
                    id: taskList
                    width: parent.width; height: Math.min(contentHeight, parent.height * 0.38)
                    clip: true; spacing: 4
                    model: link.tasks
                    delegate: Rectangle {
                        required property var modelData
                        width: taskList.width; height: 40
                        color: link.selectedTask === modelData.id ? Theme.p(0.14) : "transparent"
                        border.color: Theme.p(0.18)
                        Text {
                            x: 8; y: 5; width: parent.width - 16; elide: Text.ElideRight
                            text: modelData.title; color: Theme.text; font.family: app.mono; font.pixelSize: 12
                        }
                        Text {
                            x: 8; y: 22
                            text: modelData.status.toUpperCase() + "  ·  " + modelData.steps + " STEPS  ·  " + app.when(modelData.started || modelData.created)
                            color: app.statusColor(modelData.status); font.family: app.mono; font.pixelSize: 10
                        }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: JarvisLink.selectTask(modelData.id) }
                    }
                    Text {
                        visible: taskList.count === 0
                        width: parent.width; wrapMode: Text.Wrap
                        text: "No tasks. Switch the input to TASK, or ask Jarvis to do something long."
                        color: Theme.faint; font.family: app.mono; font.pixelSize: 11
                    }
                }
                Row {
                    spacing: 6
                    visible: app.selTask !== null
                    SmallButton { visible: app.selTask && (app.selTask.status === "running" || app.selTask.status === "queued"); text: "CANCEL"; onClicked: JarvisLink.cancelTask(app.selTask.id) }
                    SmallButton { visible: app.selTask && ["interrupted", "failed", "cancelled"].indexOf(app.selTask.status) >= 0 && link.connected; text: "RESUME"; onClicked: JarvisLink.resumeTask(app.selTask.id) }
                    SmallButton { visible: app.selTask && app.selTask.thread; text: "THREAD"; onClicked: JarvisLink.openThread(app.selTask.thread) }
                }
                Rectangle {
                    width: parent.width
                    height: parent.height - taskList.height - 24 - (app.selTask ? 40 : 0) - 16
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
                            font.family: app.mono; font.pixelSize: 11
                            textFormat: Text.PlainText
                        }
                        Text {
                            visible: logList.count === 0
                            text: app.selTask ? "No log yet." : "Select a task to see its log."
                            color: Theme.faint; font.family: app.mono; font.pixelSize: 11
                        }
                    }
                }
            }
        }
    }
}
