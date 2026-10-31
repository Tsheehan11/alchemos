// Desktop-layer window holding the arc reactor (CLOCK screens, Roles.shows; made per screen in shell.qml).
// It sits BELOW your windows, so it shows on empty workspaces.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: hud
    required property var modelData
    screen: modelData

    visible: Roles.shows(modelData) === "clock" && Theme.cfg.showReactor && !Perf.hidden(modelData, "reactor")

    WlrLayershell.layer: WlrLayer.Bottom
    WlrLayershell.namespace: "stark-hud"
    exclusionMode: ExclusionMode.Ignore

    // No anchors = centered on the screen
    implicitWidth: reactor.width
    implicitHeight: reactor.height
    color: "transparent"

    // Effects clock: frozen while windows cover this screen
    property real t: 0
    Binding on t { when: Perf.live(hud.modelData); value: Perf.time; restoreMode: Binding.RestoreNone }

    Reactor { id: reactor; t: hud.t; animated: !Perf.lite }
    DesktopMenuArea { screen: hud.modelData }
}
