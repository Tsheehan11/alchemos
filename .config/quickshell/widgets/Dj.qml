// DJ deck: now playing (MPRIS, Spotify first) and Jarvis's DJ mode: the set name, mood, chatter level and
// the next three tracks (JarvisFeed.dj ← ~/.config/jarvis/core/dj.py, pushed, never polled). Buttons:
// prev / play / next on the player; MORE / LESS steer the running set, START builds one (one Claude call
// each, in the voice process). A slow arc turns round the art while a set runs; it's still in battery
// saver or when effects are paused.
import QtQuick
import Quickshell
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
    readonly property var dj: JarvisFeed.dj || ({})
    readonly property bool on: JarvisFeed.djOn
    readonly property bool building: JarvisFeed.djBuilding
    readonly property var next: on ? (dj.next || []).slice(0, 3) : []

    title: "DJ // DECK"
    detail: !JarvisFeed.online ? JarvisState.assistant + " OFF" : building && !on ? "BUILDING SET" : on ? "LIVE · " + (dj.chatter || "rare").toUpperCase()
                                                                                       : "STANDBY"
    function jarvis(args) { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/jarvis", "dj"].concat(args)); }
    function fmt(s) { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }
    Timer {
        interval: w.saver ? 5000 : 1000; repeat: true
        running: w.active && w.has && w.player.isPlaying
        onTriggered: w.player.positionChanged()
    }

    implicitWidth: 340
    implicitHeight: col.height

    Column {
        id: col
        width: 340
        spacing: 7

        // ── now playing: art in a turning arc, title, artist ──
        Row {
            spacing: 12
            Item {
                width: 72; height: 72
                Ring {      // the set is live: an arc turning slowly round the art
                    anchors.centerIn: parent; radius: 35; thickness: 1.5; value: w.on ? 0.3 : 1; animated: false
                    color: w.on ? Theme.primary : Theme.p(0.25); trackColor: "transparent"
                    rotation: w.on && w.live && !w.saver ? w.t * 40 : 0
                }
                Image {
                    id: art
                    anchors.centerIn: parent; width: 54; height: 54
                    source: w.has ? (w.player.trackArtUrl || "") : ""
                    opacity: 0.9
                    fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 108; sourceSize.height: 108
                }
                Image {     // scanlines, so it reads as projected
                    anchors.fill: art; fillMode: Image.Tile; smooth: false; opacity: 0.7
                    source: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAADCAYAAABS3WWCAAAADElEQVR4nGNgQAZRAABpAFvrZBgXAAAAAElFTkSuQmCC"
                }
                Text { visible: art.status !== Image.Ready; anchors.centerIn: parent; text: "♪"; color: Theme.p(0.6); font.family: Style.fonts.glyph; font.pixelSize: 24 }
            }
            Column {
                width: 256; spacing: 2
                anchors.verticalCenter: parent.verticalCenter
                Text { width: parent.width; elide: Text.ElideRight; text: w.has ? (w.player.trackTitle || "Unknown track") : "Nothing playing"; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 14 }
                Text { width: parent.width; elide: Text.ElideRight; text: w.has ? (w.player.trackArtist || "") : ""; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11 }
                Text {
                    width: parent.width; elide: Text.ElideRight; topPadding: 3
                    text: w.on ? Skin.text.lockGlyph + " " + (w.dj.set || "SET").toUpperCase() : w.building ? Skin.text.lockGlyph + " BUILDING A SET…" : "◇ DJ MODE OFF"
                    color: w.on || w.building ? Theme.primary : Theme.faint
                    font.family: Style.fonts.label; font.pixelSize: 11; font.letterSpacing: 2
                }
            }
        }
        HoloBar {
            width: 340; height: 6; ticks: 24
            value: w.has && w.player.length > 0 ? Math.min(1, w.player.position / w.player.length) : 0
        }

        // ── the set: mood, then the next three ──
        Text {
            visible: w.on
            width: 340; elide: Text.ElideRight
            text: [(w.dj.mood || "").toUpperCase(), w.dj.keep ? "VIBE HELD" : "", w.dj.remote && w.dj.device ? "ON " + w.dj.device.toUpperCase() : "",
                   w.building ? "RESHAPING…" : "", w.dj.left ? w.dj.left + " LEFT" : ""].filter(x => x).join(" · ")
            color: Theme.faint; font.family: Style.fonts.label; font.pixelSize: 9; font.letterSpacing: 2
        }
        Repeater {
            model: w.next
            delegate: Row {
                required property var modelData
                required property int index
                spacing: 8
                Text { text: "0" + (index + 1); color: Theme.secondary; font.family: Style.fonts.body; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                Text {
                    width: 314; elide: Text.ElideRight
                    text: modelData.title + (modelData.artist ? "  ·  " + modelData.artist : "")
                    color: index === 0 ? Theme.textSoft : Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11
                    opacity: 1 - index * 0.18
                }
            }
        }
        Text {
            visible: !w.on && !w.building && (w.dj.note || "") !== ""
            width: 340; elide: Text.ElideRight
            text: "LAST SET ENDED · " + (w.dj.note || "").toUpperCase()
            color: Theme.faint; font.family: Style.fonts.label; font.pixelSize: 9; font.letterSpacing: 2
        }

        // ── controls ──
        Row {
            spacing: 4
            Repeater {
                model: [{ g: "⏮", a: "prev" }, { g: w.has && w.player.isPlaying ? "⏸" : "▶", a: "play" }, { g: "⏭", a: "next" }]
                delegate: HoloButton {
                    required property var modelData
                    text: modelData.g; pixelSize: 12; usable: w.has
                    onClicked: modelData.a === "play" ? w.player.togglePlaying() : modelData.a === "next" ? w.player.next() : w.player.previous()
                }
            }
            Item { width: 10; height: 1 }
            HoloButton { visible: w.on; text: "MORE"; pixelSize: 10; usable: !w.building; onClicked: w.jarvis(["more"]) }
            HoloButton { visible: w.on; text: "LESS"; pixelSize: 10; usable: !w.building; onClicked: w.jarvis(["less"]) }
            HoloButton { visible: w.on; text: "■"; pixelSize: 10; onClicked: w.jarvis(["stop"]) }
            HoloButton { visible: !w.on; text: w.building ? "BUILDING…" : "START DJ"; pixelSize: 10; usable: JarvisFeed.online && !w.building; onClicked: w.jarvis(["start"]) }
            Text {
                anchors.verticalCenter: parent.verticalCenter; leftPadding: 6
                text: w.has ? w.fmt(w.player.position) + " / " + w.fmt(w.player.length) : ""
                color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 10
            }
        }
    }
}
