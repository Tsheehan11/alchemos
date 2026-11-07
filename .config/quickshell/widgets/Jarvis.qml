// Jarvis status: what he's doing (listening / thinking / speaking / standing by), the request in hand,
// background tasks from the console with their progress, and the last command. Click: the Super+J console.
// Live state comes from JarvisState (IPC from the voice process); tasks and the last command from
// JarvisFeed (status.json). The core ring turns and breathes with the effects clock only.
import QtQuick
import ".."

WidgetBody {
    id: w
    readonly property bool on: JarvisState.online
    readonly property string mode: !JarvisState.online ? (JarvisState.running ? "starting" : "offline")
                                  : JarvisState.paused ? "paused" : JarvisState.speaking ? "speaking"
                                  : JarvisState.phase === "thinking" || JarvisState.phase === "confirm" ? "thinking"
                                  : JarvisState.listening ? "listening" : "idle"
    readonly property var labels: ({ offline: "OFFLINE", starting: "COMING ONLINE", paused: "PAUSED · COMBAT", speaking: "SPEAKING",
                                     thinking: "THINKING", listening: "LISTENING", idle: "STANDING BY" })
    readonly property color tone: mode === "paused" ? Theme.secondary : mode === "offline" ? Theme.faint : JarvisState.accent
    readonly property var tasks: JarvisFeed.tasks.filter(t => t.status === "running" || t.status === "queued")
    readonly property var last: JarvisFeed.last
    readonly property string now: JarvisState.phase !== "idle" && JarvisState.transcript ? JarvisState.transcript : ""

    title: JarvisState.glyph + " " + JarvisState.name
    detail: labels[mode]
    function clicked() { JarvisLink.show(); }

    implicitWidth: 340
    implicitHeight: Math.max(86, info.height)

    function ago(ts) {
        const s = Math.max(0, Math.round(JarvisFeed.now / 1000 - ts));
        return s < 60 ? "JUST NOW" : s < 3600 ? Math.round(s / 60) + " MIN AGO" : Math.round(s / 3600) + " H AGO";
    }

    // ── core: rings that show the state ──
    Item {
        id: core
        width: 78; height: 78
        readonly property bool moving: w.live && !w.saver
        readonly property real pulse: !moving ? 0.5 : w.mode === "listening" ? 0.5 + 0.5 * Math.sin(w.t * 6)
                                    : w.mode === "speaking" ? 0.5 + 0.5 * Math.abs(Math.sin(w.t * 11) * Math.sin(w.t * 3.7))
                                    : 0.5 + 0.2 * Math.sin(w.t * 1.2)
        Ring { anchors.centerIn: parent; radius: 36; thickness: 1; value: 1; animated: false; color: Qt.rgba(w.tone.r, w.tone.g, w.tone.b, 0.35); trackColor: "transparent" }
        Ring {      // tick ring, slowly turning (faster while thinking)
            anchors.centerIn: parent; radius: 30; thickness: 3; value: 1; animated: false; dashed: true; dash: [1, 5]
            color: Qt.rgba(w.tone.r, w.tone.g, w.tone.b, 0.55); trackColor: "transparent"
            rotation: core.moving ? w.t * (w.mode === "thinking" ? 90 : 8) : 0
        }
        Ring {      // thinking: a partial arc sweeping round
            visible: w.mode === "thinking"
            anchors.centerIn: parent; radius: 23; thickness: 2; value: 0.28; animated: false
            color: w.tone; trackColor: "transparent"
            rotation: core.moving ? -w.t * 200 : 0
        }
        Rectangle {     // the core light
            anchors.centerIn: parent
            width: 16 + 10 * core.pulse; height: width; radius: width / 2
            color: Qt.rgba(w.tone.r, w.tone.g, w.tone.b, w.on ? 0.18 + 0.25 * core.pulse : 0.08)
            border.color: w.tone; border.width: 1
        }
    }

    // ── words ──
    Column {
        id: info
        x: 92; width: 248
        spacing: 3
        Text {
            text: w.labels[w.mode]
            color: w.tone; font.family: Style.fonts.label; font.pixelSize: 15; font.letterSpacing: 3
        }
        Text {
            visible: w.now !== ""
            width: parent.width; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.Wrap
            text: "“" + w.now + "”"
            color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 11
        }
        Text {
            visible: JarvisState.tools.length > 0 && JarvisState.phase !== "idle"
            width: parent.width; elide: Text.ElideRight
            text: "› " + (JarvisState.tools[JarvisState.tools.length - 1] || "")
            color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 10; font.letterSpacing: 1
        }
        Item { width: 1; height: 3 }
        Repeater {      // background tasks: steps used of the task's budget, what it's on now
            model: w.tasks.slice(0, 3)
            delegate: Column {
                required property var modelData
                width: 248; spacing: 1
                Row {
                    spacing: 6
                    Text { text: modelData.status === "running" ? "▸" : "…"; color: Theme.secondary; font.family: Style.fonts.body; font.pixelSize: 11 }
                    Text { width: 236; elide: Text.ElideRight; text: modelData.title; color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 11 }
                }
                HoloBar {
                    visible: modelData.status === "running"
                    width: 248; height: 6; ticks: 8; color: Theme.secondary
                    value: (modelData.steps || 0) / Math.max(1, modelData.max_steps || 40)
                }
                Text {
                    width: 248; elide: Text.ElideRight
                    text: modelData.status === "queued" ? "QUEUED"
                        : modelData.waiting ? "WAITING FOR YOUR YES · " + modelData.waiting
                        : "STEP " + (modelData.steps || 0) + (modelData.now ? " · " + modelData.now : "")
                    color: modelData.waiting ? Theme.secondary : Theme.faint; font.family: Style.fonts.body; font.pixelSize: 9; font.letterSpacing: 1
                }
            }
        }
        Text {
            visible: w.last.text !== undefined && w.now === ""
            width: parent.width; elide: Text.ElideRight
            text: "LAST · " + (w.last.text || "")
            color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 10
        }
        Text {
            visible: w.last.ts !== undefined && w.now === ""
            text: (w.last.tier ? String(w.last.tier).split(":").pop().toUpperCase() + " · " : "") + w.ago(w.last.ts || 0)
            color: Theme.faint; font.family: Style.fonts.label; font.pixelSize: 9; font.letterSpacing: 2
        }
        Text {
            visible: !JarvisState.running && !JarvisState.online
            width: parent.width; wrapMode: Text.Wrap
            text: JarvisState.docked ? "Switched off · Settings → " + JarvisState.assistant : "Off on the laptop · Control center to switch on"
            color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 10
        }
    }
}
