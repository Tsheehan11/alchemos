// Base for a widget type (widgets/<Type>.qml). WidgetCard fills in the first four;
// a type sets title / detail / its implicit size, and alert when it wants attention
// (the card turns the secondary colour). Update only while `active` (shown), animate
// only while `live`, and slow down in battery saver (`saver`).
import QtQuick

Item {
    property var widget: null            // { id, type, screen, position, pinned, params }
    property bool active: false          // on screen
    property bool live: false            // …and effects are running there (Perf)
    property real t: 0                   // effects clock (seconds), frozen when not live
    property string title: ""
    property string detail: ""
    property bool alert: false
    property bool wantsKeyboard: false   // true while editing text (note)
    property string size: "normal"       // small | normal | large | huge (the card is scaled; a type may also re-lay out)
    property real minScale: 0.6          // corner-handle limits (WidgetCard)
    property real maxScale: 2.5
    readonly property bool big: size === "large" || size === "huge"
    readonly property var params: widget ? widget.params : ({})
    readonly property bool saver: PowerMode.saver
    readonly property string mono: Style.mono
    function clicked() {}                // a click on the card that wasn't a drag
    function doubleClicked() {}
    function setParams(fields) { if (widget) Widgets.setParams(widget.id, fields); }
}
