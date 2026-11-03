// A screen's widgets on one full-screen, transparent layer (two per screen: pinned ones above
// windows, the rest below them). Only the cards take input (the mask), except while one is
// dragged: then the whole screen does, so the pointer never leaves the surface it pressed on
// and the drag can't be lost however fast it moves (Hyprland doesn't always keep a pointer
// grab on layer surfaces). Faint guide lines show what the dragged card snapped to. Dragged on
// to another monitor, the press ends at this screen's edge; Widgets.drop asks Hyprland where the
// cursor really is and puts the widget there.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: surf
    property bool pinned: false
    required property var scr              // the screen (fixed; reading the window's own `screen` looped)
    screen: scr

    // Card list, kept stable (a ListModel synced by id) so editing one widget doesn't rebuild the rest
    readonly property string idKey: Widgets.idsOn(scr ? scr.name : "", pinned).join(",")
    onIdKeyChanged: sync()
    Component.onCompleted: sync()
    ListModel { id: cards }
    function sync() {
        const want = idKey ? idKey.split(",") : [];
        for (let i = cards.count - 1; i >= 0; i--)
            if (want.indexOf(cards.get(i).wid) < 0) cards.remove(i);
        const have = [];
        for (let i = 0; i < cards.count; i++) have.push(cards.get(i).wid);
        for (const w of want) if (have.indexOf(w) < 0) cards.append({ wid: w });
    }

    visible: cards.count > 0 && Theme.cfg.showWidgets
        && (pinned ? !Perf.locked && !(GameMode.quiet && Perf.gameScreens[scr?.name] === true)
                   : !Perf.hidden(scr, "widgets"))
    WlrLayershell.layer: pinned ? WlrLayer.Top : WlrLayer.Bottom
    WlrLayershell.namespace: pinned ? "stark-widgets-pinned" : "stark-widgets"
    WlrLayershell.keyboardFocus: editing ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"

    // Effects clock, frozen while hidden or covered (Perf), like the reactor
    readonly property bool live: visible && Perf.live(scr) && !Perf.lite
    property real t: 0
    Binding on t { when: surf.live; value: Perf.time; restoreMode: Binding.RestoreNone }

    // ── input: the cards, or everything while dragging ──
    property var dragged: null
    property point point: Qt.point(-1, -1)
    property var regions: []
    property bool editing: false
    function updateRegions() {
        const r = [];
        let ed = false;
        for (let i = 0; i < rep.count; i++) {
            const c = rep.itemAt(i);
            if (c) { r.push(c.region); ed = ed || c.wantsKeyboard; }
        }
        regions = r;
        editing = ed;
    }
    function grab(card) { dragged = card; }
    function release(card) { if (dragged === card) dragged = null; point = Qt.point(-1, -1); guides = ({ v: [], h: [] }); }
    property var guides: ({ v: [], h: [] })      // snap lines of the dragged card (x's, y's)
    Item { id: whole; anchors.fill: parent }
    property Region wholeRegion: Region { item: whole }
    mask: Region { regions: surf.dragged ? [surf.wholeRegion] : surf.regions }

    // ── snap guides, while dragging: faint holographic lines fading out along their length ──
    Repeater {
        model: surf.dragged ? surf.guides.v : []
        delegate: Rectangle {
            required property int modelData
            x: modelData; y: 0; width: 1; height: surf.height
            gradient: Gradient {
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.5; color: Theme.p(0.55) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }
    }
    Repeater {
        model: surf.dragged ? surf.guides.h : []
        delegate: Rectangle {
            required property int modelData
            x: 0; y: modelData; width: surf.width; height: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.5; color: Theme.p(0.55) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }
    }
    Text {
        visible: surf.dragged !== null && surf.point.x >= 0
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom; anchors.bottomMargin: 90
        text: "SHIFT · NO SNAP  ·  DRAG OFF THE EDGE FOR THE NEXT MONITOR"
        color: Theme.dim; font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 12; font.letterSpacing: 3
        style: Text.Outline; styleColor: Theme.back(0.5)
    }

    Repeater {
        id: rep
        model: cards
        delegate: WidgetCard {           // wid comes from the model
            surface: surf
            onWantsKeyboardChanged: Qt.callLater(surf.updateRegions)
        }
        onItemAdded: Qt.callLater(surf.updateRegions)
        onItemRemoved: Qt.callLater(surf.updateRegions)
    }
}
