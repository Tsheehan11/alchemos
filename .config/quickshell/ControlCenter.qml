// STARK control center — quick settings in the hologram style.
// Open: CONTROL in the helix launcher, or Super + C.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
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
        Hyprland.dispatch("exec " + cmd);
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
                SmallButton { text: "☾ SLEEP"; onClicked: { LauncherState.closeAll(); Quickshell.execDetached(["systemctl", "suspend"]); } }
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
                        { label: "JARVIS", sub: JarvisState.online ? "listening" : "offline", on: JarvisState.online,
                          act: () => cc.run(JarvisState.online
                                ? "pkill -f jarvis.py"
                                : "~/.config/jarvis/.venv/bin/python ~/.config/jarvis/jarvis.py >/dev/null 2>&1 &") }
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
