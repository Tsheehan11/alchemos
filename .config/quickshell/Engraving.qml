// An engraved surface (Style.frame "engraved"): a stone / ink plate in the preset's background, lifted
// a touch toward its metal at the top, a static grain (Style.grain), an engraved double line (a bright
// cut, its shadow, a faint inner line), corner notches carrying Style.corners (or a small diamond when
// there's no glyph: nothing dark sticks out over a white window), and a low ember glow at the rim.
// Fills its parent; put it first, under the content.
import QtQuick

Item {
    id: e
    anchors.fill: parent
    property real fillAlpha: Theme.panelAlpha
    property real ember: 0.12 * Style.glow       // rim glow, 0 = none
    property color emberColor: Theme.primary     // e.g. a persona's accent
    property var corners: Style.corners
    property int notch: 18
    property bool inner: true                    // the faint inner line
    readonly property color topColor: Theme.mix(Theme.bg, Theme.primary, 0.06)
    readonly property color bottomColor: Theme.mix(Theme.bg, "#000000", 0.28)

    Rectangle {          // ember: a soft halo just outside the plate
        visible: e.ember > 0
        anchors.fill: parent; anchors.margins: -6
        radius: 8
        color: "transparent"
        border.width: 6
        border.color: Qt.rgba(e.emberColor.r, e.emberColor.g, e.emberColor.b, Math.min(0.5, e.ember))
        opacity: 0.6
    }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(e.topColor.r, e.topColor.g, e.topColor.b, e.fillAlpha) }
            GradientStop { position: 1; color: Qt.rgba(e.bottomColor.r, e.bottomColor.g, e.bottomColor.b, e.fillAlpha) }
        }
    }
    Image {
        anchors.fill: parent
        visible: Style.grainNow > 0
        source: "assets/grain.png"
        fillMode: Image.Tile
        opacity: Style.grainNow
        smooth: false
    }
    Rectangle { anchors.fill: parent; color: "transparent"; border.color: Theme.p(0.55); border.width: 1 }
    Rectangle { anchors.fill: parent; anchors.margins: 1; color: "transparent"; border.color: Qt.rgba(0, 0, 0, 0.55); border.width: 1 }
    Rectangle { visible: e.inner; anchors.fill: parent; anchors.margins: 5; color: "transparent"; border.color: Theme.p(0.2); border.width: 1 }
    Repeater {
        model: 4
        delegate: Item {
            required property int index
            readonly property string glyph: (e.corners && e.corners.length === 4) ? (e.corners[index] || "") : ""
            width: e.notch; height: e.notch
            x: index % 2 ? e.width - width : 0
            y: index > 1 ? e.height - height : 0
            Rectangle {        // a notch with a glyph: a small plate of the panel's own fill (never a dark block)
                visible: parent.glyph !== ""
                anchors.fill: parent
                color: Qt.rgba(e.topColor.r, e.topColor.g, e.topColor.b, e.fillAlpha)
                border.color: Theme.p(0.55)
                SigilText { anchors.centerIn: parent; text: parent.parent.glyph; color: Theme.primary; font.pixelSize: e.notch * 0.55; glow: 0.3 * Style.glow }
            }
            Rectangle {        // no glyph: a small diamond set into the corner
                visible: parent.glyph === ""
                width: 5; height: 5; rotation: 45
                x: index % 2 ? parent.width - 9 : 4
                y: index > 1 ? parent.height - 9 : 4
                color: Theme.p(0.6)
            }
        }
    }
}
