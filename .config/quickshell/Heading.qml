// A panel / section heading in the skin's display face (Style.display, small caps per Style.displayCaps),
// with an optional brushed-metal rule in the preset's colour (Style.metalRule) ending in `glyph`.
// The base look (no tokens) is the plain mono label the HUD always had.
import QtQuick

Item {
    id: h
    property string text: ""
    property string glyph: ""
    property color color: Theme.primary
    property real size: 11
    property bool rule: Style.metalRule
    implicitHeight: label.implicitHeight
    implicitWidth: label.implicitWidth

    Text {
        id: label
        anchors.verticalCenter: parent.verticalCenter
        text: h.text
        color: h.color
        font.family: Style.display
        font.pixelSize: Style.display !== Style.mono ? Math.round(h.size * 1.18 * Style.displayScale) : h.size
        font.capitalization: Style.displayCaps ? Font.SmallCaps : Font.MixedCase
        font.letterSpacing: Style.display !== Style.mono ? 2 : 3
    }
    Rectangle {          // brushed metal: a bright core fading out, its shadow under it
        visible: h.rule && h.width > label.width + 60
        anchors.left: label.right; anchors.leftMargin: 12
        anchors.right: g.visible ? g.left : parent.right; anchors.rightMargin: g.visible ? 8 : 0
        anchors.verticalCenter: parent.verticalCenter
        height: 2
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Theme.mix(h.color, "#ffffff", 0.35) }
            GradientStop { position: 0.35; color: h.color }
            GradientStop { position: 0.75; color: Theme.mix(h.color, Theme.bg, 0.6) }
            GradientStop { position: 1; color: Qt.rgba(h.color.r, h.color.g, h.color.b, 0) }
        }
        Rectangle { y: 2; width: parent.width; height: 1; color: Qt.rgba(0, 0, 0, 0.5) }
    }
    SigilText {
        id: g
        visible: h.glyph !== "" && h.rule
        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
        text: h.glyph; color: h.color; font.pixelSize: h.size + 3; glow: 0.4 * Style.glow
    }
}
