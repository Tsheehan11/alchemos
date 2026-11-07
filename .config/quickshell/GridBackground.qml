// The desktop background on every screen: the skin's backdrop (Skin.component("backdrop"); the base one
// is the hologram grid, HoloBackdrop.qml) in a background-layer window.
//
// Performance: everything moves off the shared Perf.time clock (capped frame rate) and freezes while
// windows cover this screen, while locked, in combat mode and in battery saver (Perf.fps 0 there).
// Drawn backdrops draw their textures at half resolution on the laptop panel and in battery saver.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: bg
    required property var modelData
    screen: modelData

    readonly property bool live: Perf.live(modelData)
    // Frozen clock when paused, so nothing on this screen redraws
    property real t: 0
    Binding on t { when: bg.live; value: Perf.time; restoreMode: Binding.RestoreNone }

    // texture resolution for drawn backdrops: half on the laptop panel and in battery saver (the iGPU's
    // memory is system RAM)
    readonly property real res: modelData.name === Roles.laptopName || PowerMode.saver ? 0.5 : 1
    // what the backdrop may answer with a little light: the assistant at work, else CPU load
    readonly property real activity: JarvisState.listening || JarvisState.speaking ? 1 : Math.min(1, SysStats.cpu * 1.4)

    WlrLayershell.layer: WlrLayer.Background
    WlrLayershell.namespace: "stark-grid"
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: Theme.bg

    DesktopMenuArea { screen: bg.modelData }    // right-click → widget maker

    Loader {
        id: scene
        anchors.fill: parent
        source: Skin.component("backdrop")
    }
    Binding { target: scene.item; property: "modelData"; value: bg.modelData; when: scene.status === Loader.Ready }
    Binding { target: scene.item; property: "t"; value: bg.t; when: scene.status === Loader.Ready }
    Binding { target: scene.item; property: "live"; value: bg.live; when: scene.status === Loader.Ready }
    Binding { target: scene.item; property: "res"; value: bg.res; when: scene.status === Loader.Ready }
    Binding { target: scene.item; property: "activity"; value: bg.activity; when: scene.status === Loader.Ready }
}
