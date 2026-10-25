// One screen's widgets (see Widgets.qml): a WidgetWindow per widget shown on this screen.
// Keyed by widget id, so editing one widget doesn't rebuild the others.
import QtQuick
import Quickshell

Scope {
    id: layer
    required property var modelData        // the screen

    Variants {
        model: Widgets.idsOn(layer.modelData.name)
        WidgetWindow { screen: layer.modelData }
    }
}
