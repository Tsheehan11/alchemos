// Right-click on the empty desktop (the background, or the clock / diagnostics / audio deck
// panels) opens the widget maker there. Left clicks and the panels' own controls are untouched.
import QtQuick

MouseArea {
    required property var screen
    anchors.fill: parent
    z: -1                                   // under a panel's own mouse areas
    acceptedButtons: Qt.RightButton
    onClicked: Widgets.openMaker(screen)
}
