// Desktop notification cards (Notifications.qml), top-right of the main-role screen (Roles: the
// leftmost external when docked, the laptop when not). Each card is the skin's `notifCard` component
// (Skin.component; HoloNotifCard.qml by default). Only the cards take clicks; the rest of the window
// is click-through, and it is unmapped when nothing shows. Held behind the lock (Notifications.held),
// out of screenshots (Shot.hiding).
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: win
    required property var modelData
    screen: modelData

    readonly property bool here: Roles.role(modelData) === "main"
    readonly property bool calm: PowerMode.saver
    visible: here && Notifications.showing && Notifications.popups.count > 0

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "alchemos-notifications"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; right: true }
    margins { top: 44; right: 16 }            // under the bar
    implicitWidth: 400
    implicitHeight: Math.min(modelData.height - 80, column.implicitHeight + 24)
    color: "transparent"
    mask: Region { item: column }

    Binding { target: win.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }

    Column {
        id: column
        x: 12; y: 6
        width: win.implicitWidth - 24
        spacing: 10
        Repeater {
            model: Notifications.popups
            delegate: Loader {
                id: slot
                required property int index
                required property var model
                width: column.width
                // the row's roles, as one object the card reads (a fresh object when anything changes)
                readonly property var n: ({ nid: model.nid, app: model.app, summary: model.summary, body: model.body,
                                            icon: model.icon, image: model.image, urgency: model.urgency,
                                            actions: JSON.parse(model.actions || "[]"), count: model.count,
                                            persona: model.persona, time: model.time })
                source: Skin.component("notifCard")
                onLoaded: { item.n = Qt.binding(() => slot.n); item.calm = Qt.binding(() => win.calm);
                            item.closing = Qt.binding(() => slot.model.closing); item.ctl = Notifications; }
                // closing: let the card play its exit, then drop the row
                Timer {
                    running: slot.model.closing
                    interval: slot.item && !win.calm ? slot.item.exitMs : 60
                    onTriggered: Notifications.remove(slot.model.nid)
                }
                HoverHandler { onHoveredChanged: Notifications.hover(slot.model.nid, hovered) }
            }
        }
    }
}
