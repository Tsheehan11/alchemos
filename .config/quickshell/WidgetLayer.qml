// One screen's widgets (see Widgets.qml): a WidgetSurface below windows for the normal ones
// and one above them for pinned ones.
import QtQuick
import Quickshell

Scope {
    id: layer
    required property var modelData        // the screen

    WidgetSurface { scr: layer.modelData; pinned: false }
    WidgetSurface { scr: layer.modelData; pinned: true }
}
