// Hologram app search — every installed app, searchable.
// Open with Super + R, or start typing while the radial wheel is open.
// Keys: type to filter · ↑/↓ select · Enter launch · Esc close
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

PanelWindow {
    id: win
    required property var modelData
    screen: modelData

    visible: LauncherState.searchOpen && Hyprland.focusedMonitor?.name === modelData.name

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-search"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    Binding { target: win.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }   // out of screenshots (Shot.qml)

    readonly property color cyan: Theme.primary
    readonly property color amber: Theme.secondary
    readonly property color dim: Theme.dim
    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property int maxResults: 8

    property string query: ""
    property int selected: 0

    readonly property var allApps: DesktopEntries.applications.values.filter(e => !e.noDisplay)

    function score(e, q) {
        if (!q) return 1;
        const n = (e.name || "").toLowerCase();
        const g = (e.genericName || "").toLowerCase();
        const c = (e.comment || "").toLowerCase();
        if (n.startsWith(q)) return 100 - n.length * 0.1;
        if (n.split(/[\s\-_.]+/).some(w => w.startsWith(q))) return 80;
        if (n.includes(q)) return 60;
        if (g.includes(q)) return 45;
        // loose "fuzzy" match: letters in order (e.g. "sttg" → Settings)
        let i = 0;
        for (const ch of n) if (ch === q[i]) i++;
        if (i === q.length) return 25;
        if (c.includes(q)) return 10;
        return 0;
    }

    readonly property var results: {
        const q = query.toLowerCase().trim();
        return allApps
            .map(e => ({ e: e, s: score(e, q) }))
            .filter(x => x.s > 0)
            .sort((a, b) => (b.s - a.s) || a.e.name.localeCompare(b.e.name))
            .slice(0, maxResults)
            .map(x => x.e);
    }

    function launch(i) {
        if (i < 0 || i >= results.length) return;
        results[i].execute();
        LauncherState.closeAll();
    }

    onVisibleChanged: {
        if (visible) {
            input.text = LauncherState.initialQuery;
            input.cursorPosition = input.text.length;
            selected = 0;
            input.forceActiveFocus();
        }
    }

    // Dim backdrop
    Rectangle {
        anchors.fill: parent
        color: Theme.back(0.65)
        MouseArea { anchors.fill: parent; onClicked: LauncherState.closeAll() }
    }

    // The panel
    Rectangle {
        id: panel
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height * 0.22
        width: 660
        height: col.implicitHeight + 40
        color: Theme.d(Theme.panelAlpha)
        border.color: Theme.p(0.45)
        border.width: 1

        opacity: win.visible ? 1 : 0
        scale: win.visible ? 1 : 0.96
        Behavior on opacity { NumberAnimation { duration: 160 } }
        Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

        // Swallow clicks so they don't close the panel
        MouseArea { anchors.fill: parent }

        // Hologram corner brackets
        Repeater {
            model: 4
            delegate: Item {
                required property int index
                width: 18; height: 18
                x: index % 2 === 0 ? -4 : panel.width - 14
                y: index < 2 ? -4 : panel.height - 14
                Rectangle { width: 18; height: 2; color: win.cyan; y: index < 2 ? 0 : 16 }
                Rectangle { width: 2; height: 18; color: win.cyan; x: index % 2 === 0 ? 0 : 16 }
            }
        }

        Column {
            id: col
            x: 20; y: 20
            width: parent.width - 40
            spacing: 14

            // Header
            Item {
                width: parent.width; height: 16
                Text {
                    text: "SEARCH // APPLICATIONS"
                    color: win.cyan
                    font.family: win.mono; font.pixelSize: 11; font.letterSpacing: 3
                }
                Text {
                    anchors.right: parent.right
                    text: win.results.length + " / " + win.allApps.length
                    color: win.dim
                    font.family: win.mono; font.pixelSize: 11
                }
            }

            // Search box
            Rectangle {
                width: parent.width; height: 52
                color: Theme.p(0.06)
                border.color: input.activeFocus ? win.cyan : Theme.p(0.4)
                border.width: 1

                Text {
                    id: prompt
                    anchors.left: parent.left; anchors.leftMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    text: "›"
                    color: win.amber
                    font.family: win.mono; font.pixelSize: 22
                }
                TextInput {
                    id: input
                    anchors.left: prompt.right; anchors.leftMargin: 12
                    anchors.right: parent.right; anchors.rightMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.text
                    selectionColor: Theme.p(0.4)
                    font.family: win.mono; font.pixelSize: 18
                    cursorDelegate: Rectangle {
                        width: 2; color: win.cyan
                        SequentialAnimation on opacity {
                            running: win.visible
                            loops: Animation.Infinite
                            NumberAnimation { to: 0; duration: 500 }
                            NumberAnimation { to: 1; duration: 500 }
                        }
                    }
                    onTextChanged: { win.query = text; win.selected = 0; }

                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Escape) {
                            LauncherState.closeAll();
                        } else if (event.key === Qt.Key_Down || event.key === Qt.Key_Tab) {
                            win.selected = Math.min(win.results.length - 1, win.selected + 1);
                        } else if (event.key === Qt.Key_Up || event.key === Qt.Key_Backtab) {
                            win.selected = Math.max(0, win.selected - 1);
                        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                            win.launch(win.selected);
                        } else {
                            return;
                        }
                        event.accepted = true;
                    }

                    Text {
                        visible: input.text.length === 0
                        text: "Search apps…"
                        color: Theme.faint
                        font: input.font
                    }
                }
            }

            // Results
            Column {
                width: parent.width
                spacing: 4

                Repeater {
                    model: win.results
                    delegate: Rectangle {
                        id: row
                        required property var modelData
                        required property int index
                        readonly property bool sel: win.selected === index
                        readonly property string iconSrc: Quickshell.iconPath(modelData.icon, true)

                        width: parent.width; height: 54
                        color: sel ? Theme.p(0.16) : "transparent"
                        border.color: sel ? Theme.p(0.6) : "transparent"
                        border.width: 1

                        Row {
                            anchors.left: parent.left; anchors.leftMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 14

                            Item {
                                width: 32; height: 32
                                anchors.verticalCenter: parent.verticalCenter
                                Image {
                                    anchors.fill: parent
                                    source: row.iconSrc
                                    sourceSize: Qt.size(64, 64)
                                    visible: row.iconSrc !== "" && status === Image.Ready
                                    smooth: true
                                }
                                Rectangle {
                                    anchors.fill: parent
                                    visible: row.iconSrc === ""
                                    color: "transparent"
                                    border.color: win.cyan
                                    Text {
                                        anchors.centerIn: parent
                                        text: (row.modelData.name || "?").charAt(0).toUpperCase()
                                        color: win.cyan
                                        font.family: win.mono; font.pixelSize: 15
                                    }
                                }
                            }

                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2
                                Text {
                                    text: row.modelData.name
                                    color: row.sel ? Theme.text : Theme.textSoft
                                    font.family: win.mono; font.pixelSize: 15
                                }
                                Text {
                                    visible: text !== ""
                                    text: row.modelData.genericName || row.modelData.comment || ""
                                    width: 480
                                    elide: Text.ElideRight
                                    color: win.dim
                                    font.family: win.mono; font.pixelSize: 11
                                }
                            }
                        }

                        Text {
                            anchors.right: parent.right; anchors.rightMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            visible: row.sel
                            text: "ENTER ⏎"
                            color: win.amber
                            font.family: win.mono; font.pixelSize: 10; font.letterSpacing: 1
                        }

                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onEntered: win.selected = row.index
                            onClicked: win.launch(row.index)
                        }
                    }
                }

                Text {
                    visible: win.results.length === 0
                    text: "NO MATCHES"
                    color: win.dim
                    font.family: win.mono; font.pixelSize: 12; font.letterSpacing: 2
                    topPadding: 8; bottomPadding: 8
                }
            }

            // Footer
            Text {
                text: "↑↓ SELECT   ·   ENTER LAUNCH   ·   ESC CLOSE"
                color: Theme.faint
                font.family: win.mono; font.pixelSize: 10; font.letterSpacing: 2
            }
        }
    }
}
