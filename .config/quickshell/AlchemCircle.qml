// The alchemical-circle clock (ALCHEMOS's Skin.clock): CPU / RAM / GPU / battery gauge rings around the
// time, inside engraved concentric circles that carry the six metals, with a triangle-and-square
// inscription. The sign of the metal in use glows brightest. Change k to resize the whole thing.
//   t        effects clock (seconds, from HudWindow); frozen while windows cover the screen
//   animated false in combat mode: gauges jump, no seconds sweep
import QtQuick
import Quickshell

Item {
    id: r
    property real k: Theme.cfg.reactorScale
    property real t: 0
    property bool animated: true

    width: 480 * k
    height: 560 * k

    readonly property color c1: Theme.primary
    readonly property color c2: Theme.secondary
    readonly property color dim: Theme.dim
    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property var metals: ["☉", "☽", "♂", "♀", "☿", "♄"]
    readonly property string active: Skin.glyphFor(Theme.cfg.preset)

    SystemClock { id: clock; precision: SystemClock.Seconds }

    Item {
        id: core
        width: 480 * r.k
        height: 480 * r.k

        // ── Engraved outer border: a double line with fine graduations ──
        Ring { anchors.centerIn: parent; radius: 234 * r.k; thickness: 1; value: 1; color: Theme.p(0.45); trackColor: "transparent"; animated: false }
        Ring { anchors.centerIn: parent; radius: 229 * r.k; thickness: 1; value: 1; color: Theme.p(0.25); trackColor: "transparent"; animated: false }
        Ring {
            anchors.centerIn: parent
            radius: 231.5 * r.k; thickness: 4 * r.k; value: 1
            dashed: true; dash: [0.25, 3.2]
            color: Theme.p(0.3); trackColor: "transparent"; animated: false
            rotation: r.t * 2
        }

        // Seconds: a small diamond travelling the border
        Item {
            anchors.fill: parent
            rotation: clock.date.getSeconds() * 6
            Behavior on rotation { enabled: r.animated; RotationAnimation { duration: 300; direction: RotationAnimation.Clockwise } }
            Rectangle {
                width: 7 * r.k; height: width; rotation: 45
                color: r.c1
                x: parent.width / 2 - width / 2
                y: parent.height / 2 - 231.5 * r.k - height / 2
            }
        }

        // ── The metals, slowly turning; the one in use glows ──
        Item {
            id: band
            anchors.fill: parent
            rotation: r.t * 3
            Repeater {
                model: r.metals
                delegate: Item {
                    id: g
                    required property string modelData
                    required property int index
                    readonly property bool lit: modelData === r.active
                    readonly property real a: index * 60 - 90
                    x: band.width / 2 + Math.cos(a * Math.PI / 180) * 214 * r.k
                    y: band.height / 2 + Math.sin(a * Math.PI / 180) * 214 * r.k
                    // a little engraved cartouche round each sign
                    Rectangle {
                        anchors.centerIn: parent
                        width: 24 * r.k; height: width; radius: width / 2
                        color: Theme.back(0.85)
                        border.color: g.lit ? r.c1 : Theme.p(0.3); border.width: 1
                    }
                    SigilText {
                        anchors.centerIn: parent
                        rotation: -band.rotation          // signs stay upright
                        text: g.modelData
                        color: g.lit ? r.c1 : Theme.p(0.55)
                        font.pixelSize: 15 * r.k
                        glow: g.lit ? 0.9 : 0
                    }
                }
            }
            // dots between the signs
            Repeater {
                model: 6
                delegate: Rectangle {
                    required property int index
                    readonly property real a: (index * 60 - 60) * Math.PI / 180
                    width: 3 * r.k; height: width; radius: width / 2
                    color: Theme.p(0.4)
                    x: band.width / 2 + Math.cos(a) * 214 * r.k - width / 2
                    y: band.height / 2 + Math.sin(a) * 214 * r.k - height / 2
                }
            }
        }
        Ring { anchors.centerIn: parent; radius: 199 * r.k; thickness: 1; value: 1; color: Theme.p(0.3); trackColor: "transparent"; animated: false }

        // ── Inscription: triangle (its incircle is the core's rim) and a square, turning apart ──
        Sigil {
            anchors.centerIn: parent
            radius: 199 * r.k; square: false
            color: Theme.p(0.22); lineWidth: Math.max(1, 1.1 * r.k)
            rotation: r.t * 1.5
        }
        Sigil {
            anchors.centerIn: parent
            radius: 199 * r.k; triangle: false; incircle: false; squareRadius: 199 * r.k
            color: Theme.s(0.16); lineWidth: Math.max(1, 1.1 * r.k)
            rotation: -r.t * 1
        }

        // ── Gauges: CPU / RAM / GPU / battery ──
        Ring { animated: r.animated; anchors.centerIn: parent; radius: 186 * r.k; thickness: 5 * r.k; value: SysStats.cpu; color: r.c1; trackColor: Theme.p(0.08) }
        Ring { animated: r.animated; anchors.centerIn: parent; radius: 173 * r.k; thickness: 5 * r.k; value: SysStats.ram; color: r.c1; opacity: 0.8; trackColor: Theme.p(0.08) }
        Ring { animated: r.animated; anchors.centerIn: parent; radius: 160 * r.k; thickness: 5 * r.k; value: SysStats.gpu; color: r.c2; opacity: 0.85; trackColor: Theme.p(0.08) }
        Ring { animated: r.animated; anchors.centerIn: parent; radius: 147 * r.k; thickness: 5 * r.k; value: SysStats.battery; color: SysStats.charging ? "#7cf5c1" : r.c1; opacity: 0.5; trackColor: Theme.p(0.08) }

        // Engraved inner ring: fine marks, counter-turning, with three small notches
        Ring { anchors.centerIn: parent; radius: 132 * r.k; thickness: 1; value: 1; color: Theme.p(0.4); trackColor: "transparent"; animated: false }
        Item {
            anchors.fill: parent
            rotation: -r.t * 9
            Ring {
                anchors.centerIn: parent
                radius: 119 * r.k; thickness: 3 * r.k; value: 1
                dashed: true; dash: [0.6, 2.4]
                color: r.c2; opacity: 0.55; trackColor: "transparent"; animated: false
            }
            Repeater {
                model: 3
                delegate: Rectangle {
                    required property int index
                    readonly property real a: (index * 120 - 90) * Math.PI / 180
                    width: 6 * r.k; height: width; rotation: 45
                    color: r.c2
                    x: parent.width / 2 + Math.cos(a) * 119 * r.k - width / 2
                    y: parent.height / 2 + Math.sin(a) * 119 * r.k - height / 2
                }
            }
        }

        // Core: the sun's disc
        Rectangle {
            anchors.centerIn: parent
            width: 204 * r.k; height: width; radius: width / 2
            color: Theme.p(0.06)
            border.color: Theme.p(0.3)
            border.width: 1
        }

        // Time + date
        Column {
            anchors.centerIn: parent
            spacing: 4
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Qt.formatDateTime(clock.date, Theme.cfg.clock24 ? "hh:mm" : "h:mm")
                color: Theme.text
                font.family: r.mono
                font.pixelSize: 56 * r.k
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Qt.formatDateTime(clock.date, "ddd · dd MMM").toUpperCase()
                color: r.dim
                font.family: r.mono
                font.pixelSize: 13 * r.k
                font.letterSpacing: 3
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: ":" + Qt.formatDateTime(clock.date, "ss")
                color: r.c2
                font.family: r.mono
                font.pixelSize: 12 * r.k
                opacity: 0.8
            }
        }
    }

    // Legend
    Row {
        anchors.top: core.bottom
        anchors.topMargin: 16 * r.k
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 26 * r.k
        Text { text: "◇ CPU " + Math.round(SysStats.cpu * 100) + "%"; color: r.c1; font.family: r.mono; font.pixelSize: 13 * r.k; font.letterSpacing: 1 }
        Text { text: "◇ RAM " + Math.round(SysStats.ram * 100) + "%"; color: r.dim; font.family: r.mono; font.pixelSize: 13 * r.k; font.letterSpacing: 1 }
        Text { text: "◇ GPU " + (SysStats.gpuAvailable ? Math.round(SysStats.gpu * 100) + "%" : "--"); color: r.c2; font.family: r.mono; font.pixelSize: 13 * r.k; font.letterSpacing: 1 }
        Text { text: "◇ BAT " + Math.round(SysStats.battery * 100) + "%" + (SysStats.charging ? " ⚡" : ""); color: Theme.dim; font.family: r.mono; font.pixelSize: 13 * r.k; font.letterSpacing: 1 }
    }
}
