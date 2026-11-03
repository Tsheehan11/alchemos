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

    Item {
        width: 64; height: 64
        Image {
            id: art
            anchors.fill: parent; anchors.margins: 1
            source: w.has ? (w.player.trackArtUrl || "") : ""
            opacity: 0.92
            fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 128; sourceSize.height: 128
        }
        Text { visible: art.status !== Image.Ready; anchors.centerIn: parent; text: "♪"; color: Theme.p(0.6); font.pixelSize: 26 }
        Repeater {     // projected frame: corner ticks only
            model: 4
            delegate: Item {
                required property int index
                width: 8; height: 8
                x: index % 2 === 0 ? -2 : 58; y: index < 2 ? -2 : 58
                Rectangle { width: 8; height: 1.5; color: Theme.primary; y: index < 2 ? 0 : 6.5 }
                Rectangle { width: 1.5; height: 8; color: Theme.primary; x: index % 2 === 0 ? 0 : 6.5 }
            }
        }
        Image {        // scanlines over the art, so it reads as projected
            anchors.fill: art; fillMode: Image.Tile; smooth: false; opacity: 0.7
            source: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAADCAYAAABS3WWCAAAADElEQVR4nGNgQAZRAABpAFvrZBgXAAAAAElFTkSuQmCC"
        }
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
                delegate: HoloButton {
                    required property var modelData
                    text: modelData.g
                    pixelSize: 12
                    usable: w.has
                    onClicked: modelData.a === "play" ? w.player.togglePlaying() : modelData.a === "next" ? w.player.next() : w.player.previous()
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter; leftPadding: 8
                text: w.has ? w.fmt(w.player.position) + " / " + w.fmt(w.player.length) : ""
                color: Theme.faint; font.family: w.mono; font.pixelSize: 10
            }
        }
    }
    HoloBar {
        y: 74; width: 320; height: 6; ticks: 20
        value: w.has && w.player.length > 0 ? Math.min(1, w.player.position / w.player.length) : 0
    }
}
