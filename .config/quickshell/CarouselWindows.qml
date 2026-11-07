// Window previews inside a carousel panel (Overview.qml; used by every skin's carouselPanel): a live
// capture of each window, taken once as the overview opens, over a fallback tile (icon + class).
// Never a capture of a window on no monitor or while screens settle (OverviewData.capturable): that
// capture segfaults Hyprland 0.56.2. `font` sets the fallback tile's label face.
import QtQuick
import Quickshell
import Quickshell.Wayland

Item {
    id: cw
    required property var ov
    required property var panel
    property string font: ov.mono
    anchors.fill: parent

                // Window previews (dimmed while Peek hides them)
                Repeater {
                    model: panel.wins
                    delegate: Item {
                        required property var modelData
                        opacity: panel.peeked ? 0.4 : 1
                        readonly property var wm: OverviewData.monitorById(modelData.monitor) || panel.mon
                        x: (modelData.at[0] - wm.x) * panel.k
                        y: (modelData.at[1] - wm.y) * panel.k
                        width: Math.max(8, modelData.size[0] * panel.k)
                        height: Math.max(8, modelData.size[1] * panel.k)

                        // Fallback tile: icon + title (shows if a live preview isn't available)
                        Rectangle {
                            anchors.fill: parent
                            color: Theme.p(0.08)
                            border.color: Theme.p(0.5)
                            Column {
                                anchors.centerIn: parent
                                spacing: 4
                                Image {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    readonly property string src: OverviewData.iconFor(modelData.class)
                                    source: src
                                    visible: src !== ""
                                    width: 36; height: 36; sourceSize: Qt.size(72, 72)
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: (modelData.class || "").toUpperCase()
                                    color: Theme.textSoft
                                    font.family: cw.font; font.pixelSize: 10; font.letterSpacing: 1
                                }
                            }
                        }
                        // Live preview (captured once when the overview opens). Never for a
                        // window on no monitor or while screens settle (OverviewData.capturable):
                        // that capture segfaults Hyprland 0.56.2. The fallback tile shows instead.
                        ScreencopyView {
                            anchors.fill: parent
                            captureSource: ov.visible && OverviewData.capturable(modelData) ? OverviewData.toplevelFor(modelData.address) : null
                            live: false
                            opacity: 0.92
                        }
                        Rectangle { anchors.fill: parent; color: "transparent"; border.color: Theme.p(0.6); border.width: 1 }
                    }
                }
}
