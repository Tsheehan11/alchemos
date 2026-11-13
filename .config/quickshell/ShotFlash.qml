// Screenshot effect host (Shot.qml): after a shot is SAVED, plays the skin's `shotEffect` component
// (Skin.component; base HoloShotEffect.qml, ALCHEMOS AlchemShotEffect.qml) over the part of the shot on
// this monitor, one window per monitor. The capture is finished before anything here draws, so the
// effect can neither end up in it nor delay it; it gets the saved PNG cropped to this monitor
// (`frame`) to play on a frozen image. Click-through, mapped only while it plays and without
// Hyprland's fade (hypr/alchemos/rules.lua), so it never sits over a fullscreen game. Battery saver
// (Shot.calm): the component's calmMs (0 = nothing at all, the base).
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: fx
    required property var modelData
    screen: modelData

    property var box: null              // { x, y, w, h } in this screen's coordinates
    property var frame: null            // { source, clip } this screen's part of the saved PNG
    property real t: 0                  // 0 → 1 over the effect
    property bool calm: false
    visible: box !== null

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "alchemos-shot-flash"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    mask: Region {}

    Loader {
        id: eff
        anchors.fill: parent
        source: Skin.component("shotEffect")
        onLoaded: {
            item.box = Qt.binding(() => fx.box);
            item.t = Qt.binding(() => fx.t);
            item.last = Qt.binding(() => Shot.last);
            item.frame = Qt.binding(() => fx.frame);
            item.calm = Qt.binding(() => fx.calm);
            if ("main" in item) item.main = Qt.binding(() => fx.modelData.name === Shot.mainScreen());
        }
    }

    // where this screen's part sits in the PNG: its layout position minus the shot's, in PNG pixels
    function cropOf(r) {
        const g = Shot.last.geom || [0, 0, r.w, r.h];
        const sx = (Shot.last.width || g[2]) / Math.max(1, g[2]), sy = (Shot.last.height || g[3]) / Math.max(1, g[3]);
        return Qt.rect(Math.round((fx.modelData.x + r.x - g[0]) * sx), Math.round((fx.modelData.y + r.y - g[1]) * sy),
                       Math.round(r.w * sx), Math.round(r.h * sy));
    }

    Connections {
        target: Shot
        function onSerialChanged() {
            const r = Shot.last.ok ? Shot.rectOn(fx.modelData.name) : null;
            const it = eff.item;
            if (!r || !it) return;
            const ms = Shot.calm ? it.calmMs : it.durationMs;
            if (ms <= 0) return;
            fx.calm = Shot.calm;
            fx.frame = { source: "file://" + Shot.last.path, clip: fx.cropOf(r) };
            fx.box = r;
            run.duration = ms;
            run.restart();
        }
    }
    NumberAnimation {
        id: run
        target: fx; property: "t"; from: 0; to: 1; duration: 700
        onFinished: { fx.box = null; fx.frame = null; }
    }
}
