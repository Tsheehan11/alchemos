// The base carousel panel: hologram glass with scanlines, corner brackets, "WS 0N" and the window
// count under it.
//
// Carousel looks (Overview.qml, Super+Tab) come in two slots: a stage (Skin.component("carouselStage"):
// floor and header, under the panels) and a panel (Skin.component("carouselPanel"): one per workspace,
// inside the panel's placed, turned and scaled box). Overview.qml owns the ring geometry, keys, clicks
// and the glow layer; a look only draws. Both get `ov` (ids, n, pos, step, ringR, ringRy, panelW, cx, cy,
// appear, focusedHere, modelData = the screen, mono); a panel also gets `panel` (modelData = workspace
// id, index, front, current, wins, peeked, mon, k, width, height) and may set glowColor / glowBlur /
// glowOpacity for the front panel's glow. Window previews: CarouselWindows.qml.
import QtQuick
import Quickshell

Item {
    id: look
    required property var ov
    required property var panel
    anchors.fill: parent
    readonly property color glowColor: Theme.primary
    readonly property real glowBlur: 0.7
    readonly property real glowOpacity: 0.7

            // Glass
            Rectangle {
                anchors.fill: parent
                color: Theme.d(0.82)
                border.color: panel.front ? Theme.primary : Theme.p(0.45)
                border.width: panel.front ? 2 : 1
                clip: true

                // Window previews (CarouselWindows.qml: the capture rules live there)
                CarouselWindows { ov: look.ov; panel: look.panel }

                // Empty workspace
                Text {
                    anchors.centerIn: parent
                    visible: panel.wins.length === 0
                    text: "EMPTY"
                    color: Theme.p(0.45)
                    font.family: Style.fonts.body; font.pixelSize: 16; font.letterSpacing: 8
                }

                // Hologram scanlines
                Column {
                    anchors.fill: parent
                    Repeater {
                        model: Math.ceil(panel.height / 4)
                        Rectangle { width: panel.width; height: 4; color: index % 2 === 0 ? Theme.p(0.05) : "transparent" }
                    }
                }
            }

            // Corner brackets
            Repeater {
                model: 4
                delegate: Item {
                    required property int index
                    width: 18; height: 18
                    x: index % 2 === 0 ? -5 : panel.width - 13
                    y: index < 2 ? -5 : panel.height - 13
                    Rectangle { width: 18; height: 2; color: panel.front ? Theme.secondary : Theme.primary; y: index < 2 ? 0 : 16 }
                    Rectangle { width: 2; height: 18; color: panel.front ? Theme.secondary : Theme.primary; x: index % 2 === 0 ? 0 : 16 }
                }
            }

            // Label under the panel
            Row {
                anchors.top: parent.bottom; anchors.topMargin: 14
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 12
                Text {
                    text: "WS " + String(panel.modelData).padStart(2, "0")
                    color: panel.front ? Theme.text : Theme.textSoft
                    font.family: Style.fonts.body; font.pixelSize: 18; font.letterSpacing: 4
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: panel.wins.length + (panel.wins.length === 1 ? " WINDOW" : " WINDOWS") + (panel.peeked ? "  ·  PEEK" : "") + (panel.current ? "  ·  ACTIVE" : "")
                    color: panel.current ? Theme.secondary : Theme.dim
                    font.family: Style.fonts.body; font.pixelSize: 11; font.letterSpacing: 2
                }
            }
}
