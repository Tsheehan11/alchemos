// STARK control center — quick settings in the hologram style.
// Open: CONTROL in the helix launcher, or Super + C.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import "Hypr.js" as Hypr
import Quickshell.Services.Pipewire

PanelWindow {
    id: cc
    required property var modelData
    screen: modelData

    visible: LauncherState.controlOpen && Hyprland.focusedMonitor?.name === modelData.name

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-control"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    Binding { target: cc.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }   // out of screenshots (Shot.qml)

    readonly property color cyan: Theme.primary
    readonly property color amber: Theme.secondary
    readonly property color dim: Theme.dim
    readonly property string mono: "JetBrainsMono Nerd Font"

    // ── Live state ──
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property real volume: sink && sink.audio ? sink.audio.volume : 0
    readonly property bool muted: sink && sink.audio ? sink.audio.muted : false
    PwObjectTracker { objects: cc.sink ? [cc.sink] : [] }

    property bool wifiOn: false
    property string ssid: ""
    property bool btOn: false
    property real brightness: -1       // -1 = no backlight control
    property string powerProfile: ""   // "" = power-profiles not available

    function run(cmd) { Quickshell.execDetached(["sh", "-c", cmd]); refreshSoon.restart(); }
    function openApp(cmd) {
        if (cmd.startsWith("@settings")) { LauncherState.openSettings(cmd.split(":")[1] || ""); return; }
        Hyprland.dispatch(Hypr.exec(cmd));
        LauncherState.closeAll();
    }

    Process {
        id: poll
        command: ["sh", "-c", [
            "echo \"WIFI $(nmcli radio wifi 2>/dev/null)\"",
            "echo \"SSID $(nmcli -t -f ACTIVE,SSID dev wifi 2>/dev/null | grep '^yes' | head -1 | cut -d: -f2-)\"",
            "echo \"BT $(bluetoothctl show 2>/dev/null | awk '/Powered:/ {print $2; exit}')\"",
            "echo \"BRI $(brightnessctl -m 2>/dev/null | cut -d, -f4 | tr -d %)\"",
            "echo \"PWR $(powerprofilesctl get 2>/dev/null)\""
        ].join("\n")]
        stdout: StdioCollector {
            onStreamFinished: {
                for (const line of text.split("\n")) {
                    const key = line.split(" ")[0];
                    const val = line.slice(key.length + 1).trim();
                    if (key === "WIFI") cc.wifiOn = val === "enabled";
                    else if (key === "SSID") cc.ssid = val;
                    else if (key === "BT") cc.btOn = val === "yes";
                    else if (key === "BRI") cc.brightness = val === "" ? -1 : Number(val) / 100;
                    else if (key === "PWR") cc.powerProfile = val;
                }
            }
        }
    }
    Timer { interval: 3000; repeat: true; running: cc.visible; triggeredOnStart: true; onTriggered: poll.running = true }
    Timer { id: refreshSoon; interval: 700; onTriggered: poll.running = true }

    // Click outside to close
    MouseArea { anchors.fill: parent; onClicked: LauncherState.closeAll() }

    Item {
        anchors.fill: parent
        focus: cc.visible
        Keys.onEscapePressed: LauncherState.closeAll()
    }

    // ── Panel ──
    HudFrame {
        id: panel
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: 24
        anchors.topMargin: 50
        width: 420
        height: body.implicitHeight + 56
        title: "STARK // CONTROL"
        detail: Qt.formatDateTime(new Date(), "hh:mm")

        opacity: cc.visible ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }

        MouseArea { anchors.fill: parent }   // don't close when clicking inside

        Column {
            id: body
            width: parent.width
            spacing: 16

            // Session buttons
            Row {
                spacing: 8
                SmallButton { text: "◈ LOCK"; onClicked: LockState.requestLock() }
                SmallButton { text: "☾ SLEEP"; onClicked: { LauncherState.closeAll(); Quickshell.execDetached(["stark-govee", "suspend"]); } }
                SmallButton { text: "⏻ POWER"; onClicked: LauncherState.togglePower() }
            }

            // Toggles
            Grid {
                columns: 2
                columnSpacing: 10; rowSpacing: 10
                width: parent.width

                Repeater {
                    model: [
                        { label: "WI-FI", sub: cc.wifiOn ? (cc.ssid || "on") : "off", on: cc.wifiOn,
                          act: () => cc.run("nmcli radio wifi " + (cc.wifiOn ? "off" : "on")) },
                        { label: "BLUETOOTH", sub: cc.btOn ? "on" : "off", on: cc.btOn,
                          act: () => cc.run("bluetoothctl power " + (cc.btOn ? "off" : "on")) },
                        { label: "MUTE", sub: cc.muted ? "muted" : "sound on", on: cc.muted,
                          act: () => { if (cc.sink && cc.sink.audio) cc.sink.audio.muted = !cc.muted; } },
                        { label: "JARVIS", on: JarvisState.toggleOn,
                          sub: !JarvisState.toggleOn ? (JarvisState.docked ? "off" : "off · laptop")
                             : JarvisState.laptopMode ? "on · laptop, until dock change"
                             : JarvisState.online ? "on · listening" : "on · starting…",
                          act: () => JarvisState.toggle() },
                        { label: "AMBIENT LIGHTS", on: Govee.mode !== "off", sub: Govee.mode,
                          act: () => Govee.setMode(Govee.mode === "off" ? "auto" : "off") },
                        { label: "COMBAT MODE", on: GameMode.active,
                          sub: GameMode.batteryWarn ? "engaged · on battery"
                             : GameMode.active ? (GameMode.manual ? "engaged · manual" : "engaged · " + (GameMode.games[0] || "gamemode"))
                             : Theme.cfg.gameAuto ? "auto-detect" : "off",
                          act: () => GameMode.toggle() }
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        width: (body.width - 10) / 2; height: 62
                        color: modelData.on ? Theme.p(0.2) : Theme.d(0.9)
                        border.color: modelData.on ? cc.cyan : Theme.p(0.3)
                        border.width: 1
                        Column {
                            anchors.left: parent.left; anchors.leftMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 3
                            Text { text: modelData.label; color: modelData.on ? Theme.text : cc.dim; font.family: cc.mono; font.pixelSize: 13; font.letterSpacing: 2 }
                            Text {
                                text: modelData.sub; width: (body.width - 10) / 2 - 28; elide: Text.ElideRight
                                color: modelData.on ? cc.cyan : Theme.faint; font.family: cc.mono; font.pixelSize: 11
                            }
                        }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: modelData.act() }
                    }
                }
            }

            // VPN (VPN.qml): tap toggles the picked provider, chips pick one
            Rectangle {
                id: vpnTile
                readonly property bool on: VPN.connected
                readonly property bool busy: VPN.busy
                width: body.width; height: 62
                color: VPN.blocked ? Qt.rgba(1, 0.37, 0.37, 0.14) : on ? Theme.p(0.2) : busy ? Theme.s(0.1) : Theme.d(0.9)
                border.color: VPN.blocked ? "#ff5f5f" : on ? cc.cyan : busy ? cc.amber : Theme.p(0.3)
                border.width: 1
                // Scanning edge while the tunnel comes up / goes down
                Rectangle {
                    visible: vpnTile.busy
                    width: parent.width * 0.3; height: 2
                    anchors.bottom: parent.bottom
                    color: cc.amber
                    NumberAnimation on x {
                        running: vpnTile.busy && cc.visible
                        from: 0; to: vpnTile.width * 0.7
                        duration: 900; loops: Animation.Infinite; easing.type: Easing.InOutSine
                    }
                }
                Column {
                    anchors.left: parent.left; anchors.leftMargin: 14
                    anchors.right: chips.left; anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 3
                    Text {
                        text: "VPN · " + VPN.current.name
                        color: vpnTile.on ? Theme.text : cc.dim; font.family: cc.mono; font.pixelSize: 13; font.letterSpacing: 2
                    }
                    Text {
                        width: parent.width; elide: Text.ElideRight
                        text: VPN.current.error ? "failed · " + VPN.current.error
                            : VPN.blocked ? "BLOCKED · tap to restore internet"
                            : VPN.state === "disabled" ? "not set up"
                            : VPN.state.toUpperCase() + (VPN.connected && VPN.where() ? " · " + VPN.where() : "")
                        color: VPN.current.error || VPN.blocked ? "#ff5f5f" : vpnTile.on ? cc.cyan : vpnTile.busy ? cc.amber : Theme.faint
                        font.family: cc.mono; font.pixelSize: 11
                    }
                }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: if (VPN.state !== "disabled") VPN.toggle(VPN.selected)
                }
                Row {
                    id: chips
                    anchors.right: parent.right; anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    visible: VPN.providers.length > 1
                    Repeater {
                        model: VPN.providers
                        delegate: Rectangle {
                            required property var modelData
                            readonly property bool sel: VPN.selected === modelData.id
                            width: chipText.implicitWidth + 16; height: 24
                            color: sel ? Theme.p(0.22) : "transparent"
                            border.color: sel ? cc.cyan : Theme.p(0.3)
                            opacity: modelData.enabled ? 1 : 0.45
                            Text {
                                id: chipText
                                anchors.centerIn: parent
                                text: modelData.name
                                color: parent.sel ? Theme.text : cc.dim
                                font.family: cc.mono; font.pixelSize: 10; font.letterSpacing: 1
                            }
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                // Can't switch the pick away from a live tunnel; disconnect first
                                onClicked: if (VPN.active === "") VPN.pick(modelData.id)
                            }
                        }
                    }
                }
            }

            // SCREENSHOT (Shot.qml): tap = region, chips = this monitor / focused window / region → annotate.
            // The panel closes itself first, so it's never in the shot.
            Rectangle {
                id: shotTile
                width: body.width; height: 62
                color: shotMa.containsMouse ? Theme.p(0.14) : Theme.d(0.9)
                border.color: shotMa.containsMouse ? cc.cyan : Theme.p(0.3)
                border.width: 1
                Column {
                    anchors.left: parent.left; anchors.leftMargin: 14
                    anchors.right: shotChips.left; anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 3
                    Text { text: "SCREENSHOT"; color: shotMa.containsMouse ? Theme.text : cc.dim; font.family: cc.mono; font.pixelSize: 13; font.letterSpacing: 2 }
                    Text {
                        width: parent.width; elide: Text.ElideRight
                        text: Shot.last.ok ? "last · " + Shot.last.name.replace(/^stark-|\.png$/g, "") : "tap · select a region"
                        color: Theme.faint; font.family: cc.mono; font.pixelSize: 11
                    }
                }
                MouseArea { id: shotMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Shot.take("region") }
                Row {
                    id: shotChips
                    anchors.right: parent.right; anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Repeater {
                        model: [["SCREEN", "screen"], ["WINDOW", "window"], ["✎ MARK", "annotate"]]
                        delegate: Rectangle {
                            required property var modelData
                            width: chipLabel.implicitWidth + 16; height: 24
                            color: chipMa.containsMouse ? Theme.p(0.22) : "transparent"
                            border.color: chipMa.containsMouse ? cc.cyan : Theme.p(0.3)
                            Text {
                                id: chipLabel
                                anchors.centerIn: parent
                                text: modelData[0]
                                color: chipMa.containsMouse ? Theme.text : cc.dim
                                font.family: cc.mono; font.pixelSize: 10; font.letterSpacing: 1
                            }
                            MouseArea { id: chipMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Shot.take(modelData[1]) }
                        }
                    }
                }
            }

            // Sliders
            Slider {
                width: parent.width
                label: "VOLUME"
                value: cc.volume
                onMoved: v => { if (cc.sink && cc.sink.audio) cc.sink.audio.volume = v; }
            }
            Slider {
                width: parent.width
                visible: cc.brightness >= 0
                label: "BRIGHTNESS"
                value: Math.max(0, cc.brightness)
                accent: cc.amber
                onMoved: v => { cc.brightness = v; Quickshell.execDetached(["brightnessctl", "set", Math.max(1, Math.round(v * 100)) + "%"]); }
            }

            // Power profiles (only if available)
            Column {
                visible: cc.powerProfile !== ""
                width: parent.width
                spacing: 8
                Text { text: "POWER"; color: cc.dim; font.family: cc.mono; font.pixelSize: 11; font.letterSpacing: 2 }
                Row {
                    spacing: 8
                    Repeater {
                        model: [["power-saver", "SAVER"], ["balanced", "BALANCED"], ["performance", "PERFORMANCE"]]
                        delegate: Rectangle {
                            required property var modelData
                            readonly property bool on: cc.powerProfile === modelData[0]
                            width: (body.width - 16) / 3; height: 34
                            color: on ? Theme.s(0.2) : "transparent"
                            border.color: on ? cc.amber : Theme.p(0.3)
                            Text { anchors.centerIn: parent; text: modelData[1]; color: parent.on ? Theme.text : cc.dim; font.family: cc.mono; font.pixelSize: 10; font.letterSpacing: 1 }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: cc.run("powerprofilesctl set " + modelData[0]) }
                        }
                    }
                }
            }

            // Shortcuts
            Column {
                width: parent.width
                spacing: 6
                Text { text: "OPEN"; color: cc.dim; font.family: cc.mono; font.pixelSize: 11; font.letterSpacing: 2 }
                Repeater {
                    model: [
                        ["STARK settings", "@settings"],
                        ["Wi-Fi networks", "@settings:NETWORK"],
                        ["Bluetooth devices", "@settings:BLUETOOTH"],
                        ["Displays & monitors", "@settings:DISPLAY"],
                        ["Colors & theme", "@settings:APPEARANCE"],
                        ["Full KDE settings", "systemsettings"]
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        width: body.width; height: 34
                        color: ma.containsMouse ? Theme.p(0.14) : "transparent"
                        border.color: ma.containsMouse ? Theme.p(0.5) : "transparent"
                        Text {
                            anchors.left: parent.left; anchors.leftMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            text: "›  " + modelData[0]
                            color: Theme.textSoft; font.family: cc.mono; font.pixelSize: 13
                        }
                        MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: cc.openApp(modelData[1]) }
                    }
                }
            }
        }
    }
}
