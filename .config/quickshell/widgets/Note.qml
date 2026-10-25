// Sticky note ({"text": "...", "label": "..."}). Double-click to edit; Enter saves,
// Shift+Enter for a new line, Esc cancels.
import QtQuick
import ".."

WidgetBody {
    id: w
    title: "NOTE" + (params.label ? " // " + params.label.toUpperCase() : "")
    detail: editing ? "ENTER TO SAVE" : ""
    property bool editing: false
    wantsKeyboard: editing
    function doubleClicked() { editing = true; edit.text = params.text || ""; edit.forceActiveFocus(); edit.cursorPosition = edit.length; }
    function save() { setParams({ text: edit.text.slice(0, 600) }); editing = false; }

    implicitWidth: 280
    implicitHeight: Math.max(40, (editing ? edit.contentHeight : txt.contentHeight) + 6)

    Text {
        id: txt
        visible: !w.editing
        width: 280
        text: params.text || "Empty note · double-click to write"
        color: params.text ? Theme.text : Theme.faint
        wrapMode: Text.Wrap
        font.family: w.mono; font.pixelSize: 14
        lineHeight: 1.15
    }
    TextEdit {
        id: edit
        visible: w.editing
        width: 280
        color: Theme.text; selectionColor: Theme.p(0.4)
        wrapMode: TextEdit.Wrap
        font.family: w.mono; font.pixelSize: 14
        Keys.onReturnPressed: e => { if (e.modifiers & Qt.ShiftModifier) e.accepted = false; else w.save(); }
        Keys.onEnterPressed: w.save()
        Keys.onEscapePressed: w.editing = false
        onActiveFocusChanged: if (!activeFocus && w.editing) w.save()
        Rectangle { anchors.fill: parent; anchors.margins: -4; color: "transparent"; border.color: Theme.p(0.4); z: -1 }
    }
}
