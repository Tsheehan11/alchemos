// Hologram text field. accepted() on Enter, cancelled() on Esc.
import QtQuick

Rectangle {
    id: hi
    property alias text: input.text
    property string placeholder: ""
    property int maximumLength: 200
    signal accepted()
    signal cancelled()
    function focusInput() { input.forceActiveFocus(); input.selectAll(); }

    implicitWidth: 240; implicitHeight: 32
    width: implicitWidth; height: implicitHeight
    color: Theme.d(0.9)
    border.color: input.activeFocus ? Theme.primary : Theme.p(0.4)
    clip: true

    TextInput {
        id: input
        anchors.fill: parent; anchors.margins: 7
        maximumLength: hi.maximumLength
        color: Theme.text
        selectionColor: Theme.p(0.4)
        selectByMouse: true
        clip: true
        font.family: Style.fonts.body; font.pixelSize: 13
        Keys.onReturnPressed: hi.accepted()
        Keys.onEnterPressed: hi.accepted()
        Keys.onEscapePressed: hi.cancelled()
        Text { visible: input.text === ""; text: hi.placeholder; color: Theme.faint; font: input.font }
    }
}
