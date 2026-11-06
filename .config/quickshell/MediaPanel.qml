// Audio deck for MUSIC screens (Roles.shows; the laptop by default): now playing, controls, volume
// and a live visualizer (Cava.qml, one cava shared by every deck). Works with Spotify (or any
// player) running in the background. While Jarvis's DJ mode runs, the set name, mood and next three
// tracks show under the controls.
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Services.Mpris
import Quickshell.Services.Pipewire

PanelWindow {
    id: media
    required property var modelData
    screen: modelData
    visible: Roles.shows(modelData) === "music" && Theme.cfg.showMedia && !Perf.hidden(modelData, "media")

    WlrLayershell.layer: WlrLayer.Bottom
    WlrLayershell.namespace: "stark-media"
    exclusionMode: ExclusionMode.Ignore
    implicitWidth: 1120
    implicitHeight: 800
    color: "transparent"

    DesktopMenuArea { screen: media.modelData }
    readonly property color cyan: Theme.primary

    // Pause the visualizer + spinning while windows cover the laptop screen
    readonly property bool covered: Theme.cfg.pauseBehindWindows && Perf.busy[modelData.name] === true
    property real spinT: 0
    Binding on spinT {
        when: Perf.live(media.modelData) && media.hasPlayer && media.player.isPlaying
        value: Perf.time; restoreMode: Binding.RestoreNone
    }
    readonly property color amber: Theme.secondary
    readonly property color dim: Theme.dim
    readonly property string mono: Style.mono

    // Prefer Spotify, then anything playing, then any player
    readonly property var player: {
        const ps = Mpris.players.values;
        return ps.find(p => (p.identity || "").toLowerCase().includes("spotify"))
            || ps.find(p => p.isPlaying)
            || (ps.length > 0 ? ps[0] : null);
    }
    readonly property bool hasPlayer: player !== null
    readonly property real progress: hasPlayer && player.length > 0 ? player.position / player.length : 0

    readonly property var sink: Pipewire.defaultAudioSink
    readonly property real volume: sink && sink.audio ? sink.audio.volume : 0
    PwObjectTracker { objects: media.sink ? [media.sink] : [] }

    function fmt(s) {
        s = Math.max(0, Math.floor(s || 0));
        return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
    }
    function setVolume(v) {
        if (sink && sink.audio) sink.audio.volume = Math.max(0, Math.min(1, v));
    }

    // Keep the progress position fresh while playing
    Timer {
        interval: 1000; repeat: true
        running: media.visible && media.hasPlayer && media.player.isPlaying
        onTriggered: media.player.positionChanged()
    }

    // ── Visualizer feed from the shared cava ──
    // Combat mode (Perf.lite) stops cava; the bars then fall to flat in ~0.35 s (vizGain → 0) and stay
    // blank until combat ends, when they rise back with the first new frames.
    readonly property bool vizOn: media.visible && !media.covered && !Perf.lite
    onVizOnChanged: Cava.want(modelData.name, vizOn)
    Component.onCompleted: Cava.want(modelData.name, vizOn)
    Component.onDestruction: Cava.want(modelData.name, false)
    property var bars: []
    Binding on bars { when: media.vizOn; value: Cava.bars; restoreMode: Binding.RestoreNone }
    property real vizGain: Perf.lite ? 0 : 1
    Behavior on vizGain { NumberAnimation { duration: Perf.lite ? 350 : 250; easing.type: Easing.OutCubic } }
    onVizGainChanged: if (vizGain === 0 && Perf.lite) media.bars = []      // decayed: drop the frame for good

    // Scroll anywhere on the deck to change volume
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        onWheel: wheel => media.setVolume(media.volume + (wheel.angleDelta.y > 0 ? 0.05 : -0.05))
    }

    Text {
        x: 0; y: 0
        text: "AUDIO // " + (media.hasPlayer ? (media.player.identity || "PLAYER").toUpperCase() : "NO SIGNAL") + (media.dj ? "  ·  DJ" : "")
        color: media.cyan
        font.family: media.mono; font.pixelSize: 13; font.letterSpacing: 4
    }

    // ── Album art inside progress rings ──
    Item {
        id: disc
        x: 0; y: 40
        width: 460; height: 460

        Ring {
            anchors.centerIn: parent
            radius: 222; thickness: 1; value: 1
            dashed: true; dash: [2, 7]
            color: Theme.p(0.45); trackColor: "transparent"
            rotation: media.spinT * 18
        }
        // Track progress
        Ring {
            anchors.centerIn: parent
            radius: 204; thickness: 6
            value: media.progress
            animated: !Perf.lite
            color: media.cyan
        }
        // Volume
        Ring {
            anchors.centerIn: parent
            radius: 188; thickness: 3
            value: media.volume
            animated: !Perf.lite
            color: media.amber
            trackColor: Theme.s(0.1)
        }

        Rectangle {
            id: artFrame
            anchors.centerIn: parent
            width: 250; height: 250
            color: Theme.d(0.9)
            border.color: Theme.p(0.6)
            border.width: 1

            Image {
                anchors.fill: parent
                anchors.margins: 1
                source: media.hasPlayer ? (media.player.trackArtUrl || "") : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                opacity: 0.92
            }
            // Hologram scanlines over the art
            Column {
                anchors.fill: parent
                clip: true
                Repeater {
                    model: 84
                    Rectangle { width: artFrame.width; height: 3; color: index % 2 === 0 ? Theme.p(0.07) : "transparent" }
                }
            }
            Text {
                anchors.centerIn: parent
                visible: !media.hasPlayer || !media.player.trackArtUrl
                text: "♪"
                color: media.cyan
                font.pixelSize: 72
                opacity: 0.6
            }
        }
    }

    // ── Track info + controls ──
    readonly property bool dj: JarvisFeed.djOn || JarvisFeed.djBuilding
    Column {
        x: 500; y: media.dj ? 80 : 110
        width: media.width - 500
        spacing: media.dj ? 10 : 14

        Text {
            width: parent.width
            text: media.hasPlayer ? (media.player.trackTitle || "Unknown track") : "Nothing playing"
            color: Theme.text
            font.family: media.mono; font.pixelSize: 34
            elide: Text.ElideRight
        }
        Text {
            width: parent.width
            text: media.hasPlayer ? (media.player.trackArtist || "") : "Open Spotify to start the deck"
            color: media.dim
            font.family: media.mono; font.pixelSize: 19
            elide: Text.ElideRight
        }
        Text {
            width: parent.width
            visible: media.hasPlayer && (media.player.trackAlbum || "") !== ""
            text: media.hasPlayer ? (media.player.trackAlbum || "") : ""
            color: Theme.faint
            font.family: media.mono; font.pixelSize: 14
            elide: Text.ElideRight
        }

        Item { width: 1; height: 10 }

        // Progress bar (click to seek)
        Column {
            width: parent.width
            spacing: 6
            Rectangle {
                width: parent.width; height: 4
                color: Theme.p(0.14)
                Rectangle { width: parent.width * media.progress; height: parent.height; color: media.cyan }
                MouseArea {
                    anchors.fill: parent; anchors.margins: -8
                    enabled: media.hasPlayer && media.player.canSeek
                    onClicked: mouse => media.player.position = media.player.length * Math.max(0, Math.min(1, (mouse.x - 8) / (width - 16)))
                }
            }
            Item {
                width: parent.width; height: 16
                Text { text: media.hasPlayer ? media.fmt(media.player.position) : "0:00"; color: media.dim; font.family: media.mono; font.pixelSize: 12 }
                Text { anchors.right: parent.right; text: media.hasPlayer ? media.fmt(media.player.length) : "0:00"; color: media.dim; font.family: media.mono; font.pixelSize: 12 }
            }
        }

        // Controls
        Row {
            spacing: 22
            Repeater {
                model: [
                    { glyph: "⏮", big: false, act: "prev" },
                    { glyph: (media.hasPlayer && media.player.isPlaying) ? "⏸" : "▶", big: true, act: "play" },
                    { glyph: "⏭", big: false, act: "next" }
                ]
                delegate: Rectangle {
                    required property var modelData
                    width: modelData.big ? 84 : 62; height: width; radius: width / 2
                    anchors.verticalCenter: parent.verticalCenter
                    color: ma.containsMouse ? Theme.p(0.22) : Theme.d(0.9)
                    border.color: modelData.big ? media.cyan : Theme.p(0.55)
                    border.width: modelData.big ? 2 : 1
                    Text {
                        anchors.centerIn: parent
                        text: modelData.glyph
                        color: Theme.text
                        font.pixelSize: modelData.big ? 30 : 20
                    }
                    MouseArea {
                        id: ma
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!media.hasPlayer) { Quickshell.execDetached(["spotify-launcher"]); return; }
                            if (modelData.act === "play") media.player.togglePlaying();
                            else if (modelData.act === "next") media.player.next();
                            else media.player.previous();
                        }
                    }
                }
            }
        }

        Text {
            text: "VOL " + Math.round(media.volume * 100) + "%   ·   SCROLL TO ADJUST"
            color: media.amber
            font.family: media.mono; font.pixelSize: 12; font.letterSpacing: 2
            opacity: 0.85
        }

        // ── DJ mode (JarvisFeed.dj ← ~/.config/jarvis/core/dj.py): set name, mood, the next three ──
        Column {
            width: parent.width
            visible: media.dj
            spacing: 4
            topPadding: 4
            Row {
                spacing: 10
                Rectangle {
                    width: 8; height: 8; radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    color: JarvisFeed.djBuilding ? media.amber : media.cyan
                    opacity: Perf.live(media.modelData) ? 0.55 + 0.45 * Math.sin(Perf.time * 3) : 1
                }
                Text { text: "DJ MODE"; color: media.cyan; font.family: media.mono; font.pixelSize: 13; font.letterSpacing: 3 }
                Text {
                    width: media.width - 500 - 130; elide: Text.ElideRight
                    text: JarvisFeed.djBuilding && !JarvisFeed.djOn ? "BUILDING SET…" : (JarvisFeed.dj.set || "").toUpperCase()
                    color: Theme.text; font.family: media.mono; font.pixelSize: 13; font.letterSpacing: 2
                }
            }
            Text {
                text: [(JarvisFeed.dj.mood || "").toUpperCase(), JarvisFeed.dj.keep ? "VIBE HELD" : "",
                       "CHATTER " + (JarvisFeed.dj.chatter || "rare").toUpperCase(),
                       JarvisFeed.dj.remote && JarvisFeed.dj.device ? "ON " + JarvisFeed.dj.device.toUpperCase() : "",
                       JarvisFeed.djBuilding && JarvisFeed.djOn ? "RESHAPING…" : ""].filter(x => x).join("  ·  ")
                color: Theme.faint; font.family: media.mono; font.pixelSize: 11; font.letterSpacing: 2
            }
            Repeater {
                model: (JarvisFeed.dj.next || []).slice(0, 3)
                delegate: Row {
                    required property var modelData
                    required property int index
                    spacing: 10
                    Text { text: "0" + (index + 1); color: media.amber; font.family: media.mono; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        width: media.width - 500 - 34; elide: Text.ElideRight
                        text: modelData.title + (modelData.artist ? "  ·  " + modelData.artist : "")
                        color: index === 0 ? Theme.textSoft : Theme.dim
                        font.family: media.mono; font.pixelSize: 13
                    }
                }
            }
        }
    }

    // ── Visualizer ──
    Item {
        id: viz
        x: 0
        y: 540
        width: media.width
        height: 240

        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right
            y: 170
            height: 1
            color: Theme.p(0.4)
        }

        Row {
            anchors.left: parent.left; anchors.right: parent.right
            spacing: 4
            Repeater {
                model: 48
                delegate: Item {
                    required property int index
                    readonly property real level: (media.bars[index] || 0) / 100 * media.vizGain
                    width: (viz.width - 47 * 4) / 48
                    height: viz.height

                    // Bar
                    Rectangle {
                        width: parent.width
                        height: Math.max(2, parent.level * 166)
                        y: 170 - height
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: Theme.text }
                            GradientStop { position: 0.25; color: Theme.primary }
                            GradientStop { position: 1.0; color: Theme.p(0.25) }
                        }
                    }
                    // Reflection
                    Rectangle {
                        width: parent.width
                        height: Math.max(1, parent.level * 60)
                        y: 172
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: Theme.p(0.22) }
                            GradientStop { position: 1.0; color: Theme.p(0.0) }
                        }
                    }
                }
            }
        }
    }
}
