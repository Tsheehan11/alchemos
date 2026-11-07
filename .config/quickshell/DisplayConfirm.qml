// "Keep these display settings?" banner — shown on EVERY screen after you
// apply a display change, so you can always reach it even if the screen the
// Settings window was on just turned off. Reverts by itself after 15 s.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: win
    required property var modelData
    screen: modelData

    visible: Displays.pending

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-display-confirm"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true }
    margins { top: 70 }
    implicitWidth: 620
    implicitHeight: 96
    color: "transparent"
    Binding { target: win.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }   // out of screenshots (Shot.qml)


    Rectangle {
        Engraving { visible: Style.engraved; fillAlpha: 0.96; corners: []; emberColor: Theme.secondary }     // engraved skins: the plate (Engraving.qml)
        anchors.fill: parent
        color: Style.engraved ? "transparent" : Theme.d(0.94)
        border.color: Style.engraved ? "transparent" : Theme.secondary
        border.width: 1
        focus: true
        Keys.onReturnPressed: Displays.keep()
        Keys.onEscapePressed: Displays.revert()

        // Countdown bar
        Rectangle {
            anchors.left: parent.left; anchors.bottom: parent.bottom
            height: 3
            width: parent.width * Displays.countdown / 15
            color: Theme.secondary
            Behavior on width { NumberAnimation { duration: 950 } }
        }

        Column {
            anchors.left: parent.left; anchors.leftMargin: 22
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            Text { text: "KEEP THESE DISPLAY SETTINGS?"; color: Theme.text; font.family: Style.fonts.label; font.pixelSize: 15; font.letterSpacing: 2 }
            Text { text: "Reverting in " + Displays.countdown + " s  ·  Enter = keep, Esc = revert"; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 11 }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            SmallButton { text: "KEEP"; active: true; onClicked: Displays.keep() }
            SmallButton { text: "REVERT"; onClicked: Displays.revert() }
        }
    }
}
