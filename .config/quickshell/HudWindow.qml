// Desktop-layer window holding the clock (CLOCK screens, Roles.shows; made per screen in shell.qml).
// The clock itself is the skin's (Skin.clockUrl). It sits BELOW your windows, so it shows on empty workspaces.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: hud
    required property var modelData
    screen: modelData

    visible: Roles.shows(modelData) === "clock" && Theme.cfg.showReactor && !Perf.hidden(modelData, "reactor")

    WlrLayershell.layer: WlrLayer.Bottom
    WlrLayershell.namespace: "alchemos-hud"
    exclusionMode: ExclusionMode.Ignore

    // No anchors = centered on the screen
    implicitWidth: Math.max(1, clock.width)
    implicitHeight: Math.max(1, clock.height)
    color: "transparent"

    // Effects clock: frozen while windows cover this screen
    property real t: 0
    Binding on t { when: Perf.live(hud.modelData); value: Perf.time; restoreMode: Binding.RestoreNone }

    // Every clock takes t (effects clock, seconds) and animated (false in combat / lite mode)
    Loader {
        id: clock
        source: Skin.clockUrl
        onLoaded: { item.t = Qt.binding(() => hud.t); item.animated = Qt.binding(() => !Perf.lite); }
    }
    DesktopMenuArea { screen: hud.modelData }
}
