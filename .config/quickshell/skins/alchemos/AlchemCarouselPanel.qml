// ALCHEMOS carousel panel (Skin.component("carouselPanel"), loaded by Overview.qml): an engraved
// plate. Stone with grain instead of scanlines, an outer rule, a dark groove and an inner rule, diamond
// notches at the corners carrying the skin's corner signs, the workspace's number in the display face
// under it; the front plate glows ember. Interface: HoloCarouselPanel.qml.
import QtQuick
import Quickshell
import "../.."

Item {
    id: look
    required property var ov
    required property var panel
    anchors.fill: parent
    readonly property color glowColor: Theme.secondary
    readonly property real glowBlur: 0.6
    readonly property real glowOpacity: 0.5 * Style.glow
    readonly property color ember: Theme.secondary

    // the plate
    Rectangle {
        anchors.fill: parent
        antialiasing: true
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.mix(Theme.bg, Theme.primary, 0.08) }
            GradientStop { position: 1; color: Theme.back(0.96) }
        }
        clip: true
        CarouselWindows { ov: look.ov; panel: look.panel; font: Style.display }
        Text {
            anchors.centerIn: parent
            visible: look.panel.wins.length === 0
            text: "VACANT"; color: Theme.p(0.45)
            font.family: Style.fonts.display; font.pixelSize: 16; font.letterSpacing: 8
        }
        Image {
            anchors.fill: parent
            source: Qt.resolvedUrl("../../assets/grain.png"); fillMode: Image.Tile; opacity: 0.35; smooth: false
        }
    }
    // engraved frame: outer rule, dark groove, inner rule
    Rectangle { anchors.fill: parent; antialiasing: true; color: "transparent"; border.color: look.panel.front ? Theme.primary : Theme.p(0.5); border.width: look.panel.front ? 2 : 1 }
    Rectangle { anchors.fill: parent; anchors.margins: 2; antialiasing: true; color: "transparent"; border.color: Qt.rgba(0, 0, 0, 0.6) }
    Rectangle { anchors.fill: parent; anchors.margins: 5; antialiasing: true; color: "transparent"; border.color: Theme.p(look.panel.front ? 0.45 : 0.22) }
    // notched corners with the skin's corner signs
    Repeater {
        model: 4
        delegate: Item {
            required property int index
            width: 22; height: 22
            x: index % 2 === 0 ? -6 : look.panel.width - 16
            y: index < 2 ? -6 : look.panel.height - 16
            Rectangle { anchors.fill: parent; rotation: 45; scale: 0.72; color: Theme.back(1); border.color: look.panel.front ? look.ember : Theme.primary }
            Text {
                anchors.centerIn: parent
                text: (Style.corners || [])[index] || ""
                color: look.panel.front ? look.ember : Theme.primary
                font.family: Style.fonts.signs; font.pixelSize: 10
            }
        }
    }
    // under the plate: its number, then what's on it
    Row {
        anchors.top: parent.bottom; anchors.topMargin: 14
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 12
        Text {
            text: String(look.panel.modelData)
            color: look.panel.front ? Theme.text : Theme.textSoft
            font.family: Style.fonts.numeric; font.pixelSize: 24; font.letterSpacing: 4
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: look.panel.wins.length + (look.panel.wins.length === 1 ? " WINDOW" : " WINDOWS") + (look.panel.peeked ? "  ·  PEEK" : "") + (look.panel.current ? "  ·  ACTIVE" : "")
            color: look.panel.current ? look.ember : Theme.dim
            font.family: Style.fonts.label; font.pixelSize: 11; font.letterSpacing: 2
        }
    }
}
