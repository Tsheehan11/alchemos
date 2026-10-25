// Now playing (MPRIS: Spotify first, then whatever is playing), with transport controls.
import QtQuick
import Quickshell.Services.Mpris
import ".."

WidgetBody {
    id: w
    readonly property var player: {
        const ps = Mpris.players.values;
        return ps.find(p => (p.identity || "").toLowerCase().includes("spotify"))
            || ps.find(p => p.isPlaying) || (ps.length > 0 ? ps[0] : null);
    }
    readonly property bool has: player !== null
    title: "NOW PLAYING"
    detail: has ? (player.identity || "").toUpperCase() : "NO SIGNAL"
    function fmt(s) { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }
    Timer {
        interval: w.saver ? 5000 : 1000; repeat: true
        running: w.active && w.has && w.player.isPlaying
        onTriggered: w.player.positionChanged()
    }

    implicitWidth: 320
    implicitHeight: 96

    Rectangle {
        width: 64; height: 64
        color: Theme.p(0.08); border.color: Theme.p(0.35)
        Image {
            id: art
            anchors.fill: parent; anchors.margins: 1
            source: w.has ? (w.player.trackArtUrl || "") : ""
            fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 128; sourceSize.height: 128
        }
        Text { visible: art.status !== Image.Ready; anchors.centerIn: parent; text: "♪"; color: Theme.p(0.6); font.pixelSize: 26 }
    }
    Column {
        x: 76; width: 244
        spacing: 2
        Text { width: parent.width; elide: Text.ElideRight; text: w.has ? (w.player.trackTitle || "Unknown track") : "Nothing playing"; color: Theme.text; font.family: w.mono; font.pixelSize: 14 }
        Text { width: parent.width; elide: Text.ElideRight; text: w.has ? (w.player.trackArtist || "") : ""; color: Theme.dim; font.family: w.mono; font.pixelSize: 11 }
        Row {
            spacing: 4
            topPadding: 6
            Repeater {
                model: [{ g: "⏮", a: "prev" }, { g: w.has && w.player.isPlaying ? "⏸" : "▶", a: "play" }, { g: "⏭", a: "next" }]
                delegate: Rectangle {
                    required property var modelData
                    width: 30; height: 26
                    color: ma.containsMouse ? Theme.p(0.2) : Theme.p(0.06); border.color: Theme.p(0.35)
                    Text { anchors.centerIn: parent; text: modelData.g; color: Theme.primary; font.family: w.mono; font.pixelSize: 12 }
                    MouseArea {
                        id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        enabled: w.has
                        onClicked: modelData.a === "play" ? w.player.togglePlaying() : modelData.a === "next" ? w.player.next() : w.player.previous()
                    }
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter; leftPadding: 8
                text: w.has ? w.fmt(w.player.position) + " / " + w.fmt(w.player.length) : ""
                color: Theme.faint; font.family: w.mono; font.pixelSize: 10
            }
        }
    }
    Rectangle {
        y: 76; width: 320; height: 3; color: Theme.p(0.12)
        Rectangle { height: parent.height; color: Theme.primary; width: parent.width * (w.has && w.player.length > 0 ? Math.min(1, w.player.position / w.player.length) : 0) }
    }
}
