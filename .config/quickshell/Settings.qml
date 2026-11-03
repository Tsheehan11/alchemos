// STARK OS settings — Wi-Fi, Bluetooth, appearance, HUD, launcher and system.
// Open with Super + , (comma), the SETTINGS button in the control center,
// or: qs ipc call settings toggle
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import "Hypr.js" as Hypr

PanelWindow {
    id: st
    required property var modelData
    screen: modelData

    visible: LauncherState.settingsOpen && Hyprland.focusedMonitor?.name === modelData.name

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-settings"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"

    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property var tabs: ["NETWORK", "BLUETOOTH", "DISPLAY", "AUDIO", "APPEARANCE", "HUD", "WIDGETS", "JARVIS", "LAUNCHER", "SYSTEM"]
    property string status: ""            // last action result, shown at the bottom

    // A finished action's result (✓ / ✕ line at the bottom) is cleared on close, so an old
    // error doesn't greet you next time; one still running keeps its "…" until it ends.
    onVisibleChanged: if (visible) { focusCatcher.forceActiveFocus(); refreshAll(); } else if (!actProc.running) status = ""

    function refreshAll() {
        wifiPoll.running = true;
        btPoll.running = true;
        sysPoll.running = true;
    }

    // Run a command (array, no shell) and show its result
    function act(cmd, label) {
        st.status = label + "…";
        actProc.label = label;
        actProc.command = cmd;
        actProc.running = true;
    }
    Process {
        id: actProc
        property string label: ""
        stdout: StdioCollector { id: actOut }
        stderr: StdioCollector { id: actErr }
        onExited: (code, status) => {
            const msg = (actErr.text || actOut.text || "").trim().split("\n").pop();
            st.status = (code === 0 ? "✓ " : "✕ ") + actProc.label + (msg && code !== 0 ? " — " + msg : "");
            st.refreshAll();
        }
    }

    // ── Backdrop ──
    Rectangle {
        anchors.fill: parent
        color: Theme.back(0.7)
        MouseArea { anchors.fill: parent; onClicked: LauncherState.closeAll() }
    }

    Item {
        id: focusCatcher
        focus: true
        Keys.onEscapePressed: LauncherState.closeAll()
    }

    // ── Window ──
    HudFrame {
        id: frame
        anchors.centerIn: parent
        width: Math.min(1080, parent.width - 80)
        height: Math.min(720, parent.height - 100)
        title: "STARK OS // SETTINGS"
        detail: "ESC TO CLOSE"

        opacity: st.visible ? 1 : 0
        scale: st.visible ? 1 : 0.97
        Behavior on opacity { NumberAnimation { duration: 160 } }
        Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

        MouseArea { anchors.fill: parent }   // don't close when clicking inside

        // Left: tabs
        Column {
            id: nav
            width: 200
            anchors.top: parent.top; anchors.bottom: parent.bottom
            spacing: 6
            Repeater {
                model: st.tabs
                delegate: Rectangle {
                    required property var modelData
                    readonly property bool on: LauncherState.settingsTab === modelData
                    width: nav.width; height: 44
                    color: on ? Theme.p(0.16) : (ma.containsMouse ? Theme.p(0.07) : "transparent")
                    border.color: on ? Theme.p(0.6) : "transparent"
                    Rectangle { visible: parent.on; width: 3; height: parent.height; color: Theme.secondary }
                    Text {
                        anchors.left: parent.left; anchors.leftMargin: 18
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData
                        color: parent.on ? Theme.text : Theme.textSoft
                        font.family: st.mono; font.pixelSize: 13; font.letterSpacing: 3
                    }
                    MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: LauncherState.settingsTab = modelData }
                }
            }
        }

        // Right: page
        Flickable {
            id: page
            anchors.left: nav.right; anchors.leftMargin: 28
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: statusLine.top; anchors.bottomMargin: 10
            contentHeight: pageCol.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: pageCol
                width: page.width
                spacing: 14

                // ════════ NETWORK ════════
                Column {
                    visible: LauncherState.settingsTab === "NETWORK"
                    width: parent.width
                    spacing: 12

                    Toggle {
                        width: parent.width
                        label: "Wi-Fi"
                        hint: wifi.on ? (wifi.current ? "Connected to " + wifi.current : "Not connected") : "Off"
                        checked: wifi.on
                        onToggled: st.act(["nmcli", "radio", "wifi", wifi.on ? "off" : "on"], wifi.on ? "Wi-Fi off" : "Wi-Fi on")
                    }

                    Row {
                        spacing: 10
                        visible: wifi.on
                        SmallButton { text: "RESCAN"; onClicked: st.act(["nmcli", "dev", "wifi", "rescan"], "Scanning") }
                        SmallButton { text: "ADVANCED (NMTUI)"; onClicked: { Hyprland.dispatch(Hypr.exec("kitty -e nmtui")); LauncherState.closeAll(); } }
                    }

                    // VPN (VPN.qml / stark-vpn)
                    Text { text: "VPN"; topPadding: 10; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Row {
                        spacing: 8
                        visible: VPN.providers.length > 1
                        Repeater {
                            model: VPN.providers
                            delegate: SmallButton {
                                required property var modelData
                                text: modelData.label.toUpperCase() + (modelData.enabled ? "" : " · NOT SET UP")
                                active: VPN.selected === modelData.id
                                opacity: modelData.enabled ? 1 : 0.5
                                onClicked: if (VPN.active === "") VPN.pick(modelData.id)
                            }
                        }
                    }
                    Item {
                        width: parent.width; height: 44
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 3
                            Text {
                                text: VPN.state === "disabled" ? "Not set up"
                                    : VPN.state.charAt(0).toUpperCase() + VPN.state.slice(1)
                                color: VPN.blocked ? "#ff5f5f" : VPN.connected ? Theme.primary : VPN.busy ? Theme.secondary : Theme.textSoft
                                font.family: st.mono; font.pixelSize: 13
                            }
                            Text {
                                text: VPN.current.error ? "✕ " + VPN.current.error
                                    : VPN.blocked ? "The VPN dropped and the kill switch is holding the internet off"
                                    : VPN.state === "disabled" ? "Fill in ~/.config/stark-vpn/providers.json to enable it"
                                    : VPN.connected ? "Server " + VPN.current.server + " · " + [VPN.current.city, VPN.current.country].filter(x => x).join(", ")
                                    : VPN.current.type === "protonvpn" ? "Fastest free server · LAN (Govee, printers) stays reachable"
                                    : VPN.current.auth === "terminal" ? "Connect opens a login window · password + Duo each time, nothing saved" : ""
                                color: VPN.current.error ? "#ff5f5f" : Theme.dim
                                font.family: st.mono; font.pixelSize: 11
                            }
                        }
                        SmallButton {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            visible: VPN.state !== "disabled"
                            text: VPN.blocked ? "RESTORE INTERNET" : VPN.connected || VPN.state === "connecting" ? "DISCONNECT" : VPN.busy ? "…" : "CONNECT"
                            active: VPN.connected
                            onClicked: VPN.connected || VPN.blocked || VPN.state === "connecting" ? VPN.disconnect() : VPN.connect(VPN.selected)
                        }
                    }
                    Toggle {
                        width: parent.width
                        visible: !!VPN.current.hasKillSwitch
                        label: "Kill switch"
                        hint: "Blocks the internet if the VPN drops while connected · off by default, disconnecting always restores it"
                        checked: VPN.killSwitch
                        onToggled: VPN.setKillSwitch(!VPN.killSwitch)
                    }

                    Text { visible: wifi.on; text: "WI-FI NETWORKS"; topPadding: 10; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Repeater {
                        model: wifi.on ? wifi.networks : []
                        delegate: Rectangle {
                            id: net
                            required property var modelData
                            property bool askPw: false
                            width: pageCol.width
                            height: askPw ? 96 : 52
                            color: modelData.inUse ? Theme.p(0.14) : (nma.containsMouse ? Theme.p(0.06) : Theme.d(0.6))
                            border.color: modelData.inUse ? Theme.p(0.6) : Theme.p(0.15)

                            Row {
                                x: 14; y: 14
                                spacing: 14
                                // signal bars
                                Row {
                                    spacing: 2
                                    anchors.verticalCenter: parent.verticalCenter
                                    Repeater {
                                        model: 4
                                        Rectangle {
                                            required property int index
                                            width: 4; height: 6 + index * 4
                                            anchors.bottom: parent.bottom
                                            color: net.modelData.signal > index * 25 ? Theme.primary : Theme.p(0.2)
                                        }
                                    }
                                }
                                Text {
                                    text: net.modelData.ssid
                                    color: Theme.text
                                    font.family: st.mono; font.pixelSize: 14
                                    width: 360; elide: Text.ElideRight
                                }
                                Text {
                                    text: (net.modelData.secure ? "🔒 " : "") + (net.modelData.saved ? "SAVED" : "")
                                    color: Theme.dim
                                    font.family: st.mono; font.pixelSize: 11
                                }
                            }
                            Text {
                                anchors.right: parent.right; anchors.rightMargin: 14; y: 17
                                text: net.modelData.inUse ? "DISCONNECT" : "CONNECT"
                                color: net.modelData.inUse ? Theme.secondary : Theme.primary
                                font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 2
                                visible: nma.containsMouse || net.modelData.inUse
                            }
                            MouseArea {
                                id: nma
                                width: parent.width; height: 52
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    const n = net.modelData;
                                    if (n.inUse) st.act(["nmcli", "connection", "down", "id", n.ssid], "Disconnecting");
                                    else if (n.saved) st.act(["nmcli", "connection", "up", "id", n.ssid], "Connecting to " + n.ssid);
                                    else if (!n.secure) st.act(["nmcli", "dev", "wifi", "connect", n.ssid], "Connecting to " + n.ssid);
                                    else { net.askPw = true; pw.forceActiveFocus(); }
                                }
                            }
                            // Password entry
                            Rectangle {
                                visible: net.askPw
                                x: 14; y: 52
                                width: parent.width - 28; height: 34
                                color: Theme.d(0.9)
                                border.color: pw.activeFocus ? Theme.primary : Theme.p(0.4)
                                TextInput {
                                    id: pw
                                    anchors.fill: parent; anchors.margins: 8
                                    echoMode: TextInput.Password
                                    color: Theme.text
                                    font.family: st.mono; font.pixelSize: 14
                                    Keys.onReturnPressed: {
                                        st.act(["nmcli", "dev", "wifi", "connect", net.modelData.ssid, "password", text], "Connecting to " + net.modelData.ssid);
                                        text = ""; net.askPw = false;
                                    }
                                    Keys.onEscapePressed: { text = ""; net.askPw = false; focusCatcher.forceActiveFocus(); }
                                    Text { visible: pw.text === ""; text: "Password — Enter to connect"; color: Theme.faint; font: pw.font }
                                }
                            }
                        }
                    }

                }

                // ════════ BLUETOOTH ════════
                Column {
                    visible: LauncherState.settingsTab === "BLUETOOTH"
                    width: parent.width
                    spacing: 12

                    Toggle {
                        width: parent.width
                        label: "Bluetooth"
                        hint: bt.on ? (bt.devices.filter(d => d.connected).map(d => d.name).join(", ") || "On — nothing connected") : "Off"
                        checked: bt.on
                        onToggled: st.act(["bluetoothctl", "power", bt.on ? "off" : "on"], bt.on ? "Bluetooth off" : "Bluetooth on")
                    }
                    Row {
                        spacing: 10
                        visible: bt.on
                        SmallButton {
                            text: btScan.running ? "SCANNING…" : "SCAN FOR DEVICES"
                            onClicked: if (!btScan.running) btScan.running = true
                        }
                    }

                    Text { visible: bt.on; text: "DEVICES"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }

                    Repeater {
                        model: bt.on ? bt.devices : []
                        delegate: Rectangle {
                            id: dev
                            required property var modelData
                            width: pageCol.width; height: 52
                            color: modelData.connected ? Theme.p(0.14) : Theme.d(0.6)
                            border.color: modelData.connected ? Theme.p(0.6) : Theme.p(0.15)
                            Column {
                                x: 14; anchors.verticalCenter: parent.verticalCenter
                                spacing: 2
                                Text { text: dev.modelData.name; color: Theme.text; font.family: st.mono; font.pixelSize: 14 }
                                Text {
                                    text: dev.modelData.connected ? "CONNECTED" : (dev.modelData.paired ? "PAIRED" : "AVAILABLE")
                                    color: dev.modelData.connected ? Theme.primary : Theme.dim
                                    font.family: st.mono; font.pixelSize: 10; font.letterSpacing: 2
                                }
                            }
                            Row {
                                anchors.right: parent.right; anchors.rightMargin: 12
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 8
                                SmallButton {
                                    visible: dev.modelData.connected
                                    text: "DISCONNECT"
                                    onClicked: st.act(["bluetoothctl", "disconnect", dev.modelData.mac], "Disconnecting " + dev.modelData.name)
                                }
                                SmallButton {
                                    visible: !dev.modelData.connected && dev.modelData.paired
                                    text: "CONNECT"
                                    onClicked: st.act(["bluetoothctl", "connect", dev.modelData.mac], "Connecting " + dev.modelData.name)
                                }
                                SmallButton {
                                    visible: !dev.modelData.paired
                                    text: "PAIR"
                                    onClicked: st.act(["sh", "-c", "bluetoothctl pair " + dev.modelData.mac + " && bluetoothctl trust " + dev.modelData.mac + " && bluetoothctl connect " + dev.modelData.mac], "Pairing " + dev.modelData.name)
                                }
                                SmallButton {
                                    visible: dev.modelData.paired
                                    text: "FORGET"
                                    onClicked: st.act(["bluetoothctl", "remove", dev.modelData.mac], "Forgetting " + dev.modelData.name)
                                }
                            }
                        }
                    }
                }

                // ════════ APPEARANCE ════════
                Column {
                    id: look
                    visible: LauncherState.settingsTab === "APPEARANCE"
                    width: parent.width
                    spacing: 16
                    property bool naming: false        // SAVE AS PRESET name field open
                    property string saveError: ""
                    function startNaming() {
                        look.saveError = "";
                        presetIn.text = Theme.isBuiltin(Theme.cfg.preset) || Theme.cfg.preset === "CUSTOM" ? "" : Theme.cfg.preset;
                        look.naming = true;
                        presetIn.forceActiveFocus();
                        presetIn.selectAll();
                    }
                    function finishNaming(save) {
                        if (save) {
                            look.saveError = Theme.savePreset(presetIn.text);
                            if (look.saveError !== "") return;
                            st.status = "✓ Saved preset " + Theme.presetName(presetIn.text);
                        }
                        look.naming = false;
                        focusCatcher.forceActiveFocus();
                    }

                    Text { text: "THEME"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Grid {
                        columns: 3
                        columnSpacing: 12; rowSpacing: 12
                        Repeater {
                            model: Theme.allPresets
                            delegate: Rectangle {
                                required property var modelData
                                readonly property bool on: Theme.cfg.preset === modelData.name
                                width: (pageCol.width - 24) / 3; height: 72
                                color: modelData.background
                                border.color: on ? modelData.primary : Qt.rgba(1, 1, 1, 0.12)
                                border.width: on ? 2 : 1
                                Row {
                                    x: 14; y: 14; spacing: 6
                                    Rectangle { width: 18; height: 18; radius: 9; color: modelData.primary }
                                    Rectangle { width: 18; height: 18; radius: 9; color: modelData.secondary }
                                }
                                Text {
                                    x: 14; y: 42
                                    text: modelData.name
                                    color: modelData.primary
                                    font.family: st.mono; font.pixelSize: 12; font.letterSpacing: 3
                                }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Theme.applyPreset(modelData) }
                                // Custom presets: marker + delete
                                Text {
                                    visible: modelData.custom === true
                                    anchors.right: parent.right; anchors.top: parent.top
                                    anchors.rightMargin: 10; anchors.topMargin: 8
                                    text: "◆ USER"
                                    color: modelData.secondary
                                    font.family: st.mono; font.pixelSize: 9; font.letterSpacing: 2
                                }
                                ConfirmButton {
                                    visible: modelData.custom === true
                                    anchors.right: parent.right; anchors.bottom: parent.bottom
                                    anchors.rightMargin: 8; anchors.bottomMargin: 8
                                    label: "✕"
                                    onConfirmed: Theme.deletePreset(modelData.name)
                                }
                            }
                        }
                    }

                    // Save the colours currently applied as a new preset
                    Row {
                        spacing: 10
                        SmallButton { visible: !look.naming; text: "+ SAVE AS PRESET"; onClicked: look.startNaming() }
                        Rectangle {
                            visible: look.naming
                            width: 240; height: 32
                            color: Theme.d(0.9)
                            border.color: presetIn.activeFocus ? Theme.primary : Theme.p(0.4)
                            TextInput {
                                id: presetIn
                                anchors.fill: parent; anchors.margins: 7
                                maximumLength: 14
                                color: Theme.text
                                font.family: st.mono; font.pixelSize: 14; font.letterSpacing: 2
                                font.capitalization: Font.AllUppercase
                                onTextEdited: look.saveError = ""
                                Keys.onReturnPressed: look.finishNaming(true)
                                Keys.onEnterPressed: look.finishNaming(true)
                                Keys.onEscapePressed: look.finishNaming(false)
                                Text { visible: presetIn.text === ""; text: "PRESET NAME"; color: Theme.faint; font: presetIn.font }
                            }
                        }
                        SmallButton { visible: look.naming; text: "SAVE"; onClicked: look.finishNaming(true) }
                        SmallButton { visible: look.naming; text: "CANCEL"; onClicked: look.finishNaming(false) }
                        Text {
                            visible: look.naming
                            anchors.verticalCenter: parent.verticalCenter
                            text: look.saveError !== "" ? "✕ " + look.saveError
                                : (Theme.cfg.customPresets || []).some(c => c.name === Theme.presetName(presetIn.text)) ? "overwrites existing preset" : ""
                            color: look.saveError !== "" ? Theme.secondary : Theme.dim
                            font.family: st.mono; font.pixelSize: 11
                        }
                    }

                    Text { text: "CUSTOM — MAIN COLOR"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Swatches { selected: Theme.cfg.primary; onPicked: c => { Theme.cfg.primary = c; Theme.cfg.preset = "CUSTOM"; } }
                    Text { text: "CUSTOM — ACCENT COLOR"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Swatches { selected: Theme.cfg.secondary; onPicked: c => { Theme.cfg.secondary = c; Theme.cfg.preset = "CUSTOM"; } }

                    Column {
                        spacing: 8
                        Text { text: "AMBIENT LIGHTS"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                        Text { text: "Govee strip: AUTO follows the theme and pulses to music when audio plays."; color: Theme.textSoft; font.family: st.mono; font.pixelSize: 12 }
                        Row {
                            spacing: 10
                            Repeater {
                                model: Govee.modes
                                delegate: SmallButton {
                                    required property var modelData
                                    text: modelData.toUpperCase()
                                    active: Govee.mode === modelData
                                    onClicked: Govee.setMode(modelData)
                                }
                            }
                        }
                        Text { text: "ANIMATION SPEED"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                        Row {
                            spacing: 10
                            Repeater {
                                model: [[0.6, "SLOW"], [1.0, "NORMAL"], [1.5, "FAST"]]
                                delegate: SmallButton {
                                    required property var modelData
                                    text: modelData[1]
                                    active: Math.abs(Govee.animSpeed - modelData[0]) < 0.01
                                    onClicked: Govee.setSpeed(modelData[0])
                                }
                            }
                        }
                    }

                    Toggle { width: parent.width; label: "TERMINAL GLASS"; hint: "Kitty turns 85% see-through — off keeps it solid"; checked: Theme.cfg.terminalGlass; onToggled: Theme.cfg.terminalGlass = !Theme.cfg.terminalGlass }
                    Toggle { width: parent.width; label: "Animated background"; hint: "Data streams, scanline, blinking nodes, spinning rings"; checked: Theme.cfg.animatedBg; onToggled: Theme.cfg.animatedBg = !Theme.cfg.animatedBg }
                    Toggle { width: parent.width; label: "Pause effects behind windows"; hint: "Big GPU saver — effects only run on screens you can actually see"; checked: Theme.cfg.pauseBehindWindows; onToggled: Theme.cfg.pauseBehindWindows = !Theme.cfg.pauseBehindWindows }
                    Column {
                        spacing: 8
                        Text { text: "EFFECTS FRAME RATE"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                        Row {
                            spacing: 10
                            Repeater {
                                model: [[0, "STATIC"], [12, "ECO · 12"], [24, "BALANCED · 24"], [40, "SMOOTH · 40"]]
                                delegate: SmallButton {
                                    required property var modelData
                                    text: modelData[1]
                                    active: Theme.cfg.effectsFps === modelData[0]
                                    onClicked: Theme.cfg.effectsFps = modelData[0]
                                }
                            }
                        }
                    }
                    Slider {
                        width: parent.width
                        label: "PANEL OPACITY"
                        valueText: Math.round(Theme.panelAlpha * 100) + "%"
                        value: (Theme.panelAlpha - 0.5) / 0.5
                        onMoved: v => Theme.cfg.panelOpacity = Math.round((0.5 + v * 0.5) * 100) / 100
                    }
                    Column {
                        width: parent.width
                        spacing: 8
                        Text { text: "CURSOR"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                        Stepper { width: parent.width; label: "Cursor size"; hint: "24 standard · 32 / 48 for HiDPI screens"; valueText: Theme.cursorStep(0) + " PX"; onDec: Theme.cfg.cursorSize = Theme.cursorStep(-1); onInc: Theme.cfg.cursorSize = Theme.cursorStep(1) }
                        Slider {
                            width: parent.width
                            label: "CURSOR OPACITY"
                            valueText: Theme.cursorFill() + "%"
                            value: (Theme.cursorFill() - 20) / 70
                            onMoved: v => Theme.cfg.cursorOpacity = Math.round((20 + v * 70) / 5) * 5
                        }
                        Toggle { width: parent.width; label: "ANIMATED BUSY CURSOR"; hint: "Arc reactor spins while apps load · off shows a still frame"; checked: Theme.cfg.cursorAnimated; onToggled: Theme.cfg.cursorAnimated = !Theme.cfg.cursorAnimated }
                    }
                    Toggle { width: parent.width; label: "Background grid"; checked: Theme.cfg.showGrid; onToggled: Theme.cfg.showGrid = !Theme.cfg.showGrid }
                    Toggle { width: parent.width; label: "24-hour clock"; checked: Theme.cfg.clock24; onToggled: Theme.cfg.clock24 = !Theme.cfg.clock24 }
                    Toggle { width: parent.width; label: "Lock / unlock sounds"; checked: Theme.cfg.unlockSound; onToggled: Theme.cfg.unlockSound = !Theme.cfg.unlockSound }

                    Slider {
                        width: parent.width
                        label: "CLOCK SIZE"
                        value: (Theme.cfg.reactorScale - 1) / 0.8
                        onMoved: v => Theme.cfg.reactorScale = Math.round((1 + v * 0.8) * 100) / 100
                    }

                    Item {
                        width: parent.width; height: 40
                        Text { anchors.verticalCenter: parent.verticalCenter; text: "Unlock greeting name"; color: Theme.text; font.family: st.mono; font.pixelSize: 14 }
                        Rectangle {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            width: 240; height: 34
                            color: Theme.d(0.9)
                            border.color: nameIn.activeFocus ? Theme.primary : Theme.p(0.4)
                            TextInput {
                                id: nameIn
                                anchors.fill: parent; anchors.margins: 8
                                text: Theme.cfg.greetName
                                color: Theme.text
                                font.family: st.mono; font.pixelSize: 14
                                onEditingFinished: Theme.cfg.greetName = text
                            }
                        }
                    }
                }

                // ════════ DISPLAY ════════
                DisplayPage {
                    visible: LauncherState.settingsTab === "DISPLAY" && st.visible
                    width: parent.width
                }

                // ════════ AUDIO ════════
                AudioPage {
                    visible: LauncherState.settingsTab === "AUDIO" && st.visible
                    width: parent.width
                }

                // ════════ HUD ════════
                Column {
                    visible: LauncherState.settingsTab === "HUD"
                    width: parent.width
                    spacing: 12

                    Toggle { width: parent.width; label: "Arc-reactor clock"; hint: "CLOCK screens (Display → HUD on this screen)"; checked: Theme.cfg.showReactor; onToggled: Theme.cfg.showReactor = !Theme.cfg.showReactor }
                    Toggle { width: parent.width; label: "Diagnostics wall"; hint: "STATS screens"; checked: Theme.cfg.showDiag; onToggled: Theme.cfg.showDiag = !Theme.cfg.showDiag }
                    Toggle { width: parent.width; label: "Audio deck"; hint: "MUSIC screens"; checked: Theme.cfg.showMedia; onToggled: Theme.cfg.showMedia = !Theme.cfg.showMedia }
                    Toggle { width: parent.width; label: "Hide panels behind windows"; hint: "Clock, diagnostics and audio deck only show on screens with no windows open"; checked: Theme.cfg.hideHudBehindWindows; onToggled: Theme.cfg.hideHudBehindWindows = !Theme.cfg.hideHudBehindWindows }
                    Toggle { width: parent.width; label: "Volume & brightness pop-up"; hint: "Shows on the screen you're using"; checked: Theme.cfg.osd; onToggled: Theme.cfg.osd = !Theme.cfg.osd }
                    Toggle { width: parent.width; label: "Jarvis"; hint: (!JarvisState.toggleOn ? (JarvisState.docked ? "Off" : "Off on the laptop · switch on for now (until the next dock change)") : JarvisState.laptopMode ? "On (laptop, until dock change) · no academic sync, watchers or room speaker; stops under 20 % on battery" : JarvisState.paused ? "On · paused for combat mode" : JarvisState.online ? "On · listening for \"Hey Jarvis\"" : "On · starting…"); checked: JarvisState.toggleOn; onToggled: JarvisState.toggle() }
                    Row {
                        spacing: 10
                        SmallButton { text: "RELOAD HUD"; onClicked: Quickshell.reload(true) }
                        SmallButton { text: "EDIT HUD FILES"; onClicked: { Hyprland.dispatch(Hypr.exec("kate ~/.config/quickshell")); LauncherState.closeAll(); } }
                    }
                }

                // ════════ WIDGETS ════════
                WidgetsPage {
                    visible: LauncherState.settingsTab === "WIDGETS"
                    width: parent.width
                    onReleaseFocus: focusCatcher.forceActiveFocus()
                }

                // ════════ JARVIS ════════
                Column {
                    id: jarvisPage
                    visible: LauncherState.settingsTab === "JARVIS"
                    width: parent.width
                    spacing: 12

                    readonly property var models: ["auto", "haiku", "sonnet", "opus"]
                    readonly property var modelHints: ({ auto: "Haiku · Sonnet for harder questions", haiku: "Fastest", sonnet: "Smarter, a little slower", opus: "Strongest, slowest · uses the plan fastest" })
                    readonly property var follows: [0, 4, 6, 8, 10, 15]
                    property var voices: ["bm_george"]
                    property var effects: ["AUTO", "CLEAN", "HOLOGRAM", "SUIT"]
                    property var speakers: []          // [{mac, name}] paired Bluetooth speakers (not headphones)
                    property var integrations: []      // `jarvis integrations --json`: [{key, name, label, auth, connected, state, detail}]
                    property var spotify: ({})         // `jarvis spotify status --json`: {connected, user, premium, client, missing, detail}
                    property var djMoods: []           // preset names from ~/.config/jarvis/dj_moods.json + saved ones
                    function speakerName(mac) { const s = speakers.find(x => x.mac === mac); return mac === "" ? "OFF" : (s ? s.name : mac).toUpperCase(); }
                    function voiceName(v) {
                        if (/^[a-z][fm]_/.test(v)) return v.slice(3).toUpperCase() + (v[1] === "m" ? " · KOKORO" : " · KOKORO ♀");
                        return v.replace(/^en_GB-/, "").replace(/-(medium|low|high)/, "").replace(/_/g, " ").replace(":", " · ").toUpperCase() + " · PIPER";
                    }
                    function preview() { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/jarvis", "--say", "Good evening, sir. All systems are online."]); }
                    function cycle(list, cur, dir) { const i = list.indexOf(cur); return list[((i < 0 ? 0 : i) + dir + list.length) % list.length]; }
                    onVisibleChanged: if (visible) voiceList.running = true
                    Process {
                        id: voiceList
                        command: [Quickshell.env("HOME") + "/.local/bin/jarvis-voices", "--list"]
                        stdout: StdioCollector {
                            onStreamFinished: {
                                try {
                                    const d = JSON.parse(text);
                                    if (d.voices.length) jarvisPage.voices = d.voices;
                                    if (d.effects.length) jarvisPage.effects = d.effects;
                                    jarvisPage.speakers = d.speakers || [];
                                } catch (e) {}
                            }
                        }
                    }

                    Toggle { width: parent.width; label: "Jarvis"; hint: (!JarvisState.toggleOn ? (JarvisState.docked ? "Off" : "Off on the laptop · switch on for now (until the next dock change)") : JarvisState.laptopMode ? "On (laptop, until dock change) · no academic sync, watchers or room speaker; stops under 20 % on battery" : JarvisState.paused ? "On · paused for combat mode" : JarvisState.online ? "On · listening for \"Hey Jarvis\"" : "On · starting…"); checked: JarvisState.toggleOn; onToggled: JarvisState.toggle() }
                    Stepper { width: parent.width; label: "Claude model"; hint: jarvisPage.modelHints[Theme.cfg.jarvisModel] || ""; valueText: Theme.cfg.jarvisModel.toUpperCase(); onDec: Theme.cfg.jarvisModel = jarvisPage.cycle(jarvisPage.models, Theme.cfg.jarvisModel, -1); onInc: Theme.cfg.jarvisModel = jarvisPage.cycle(jarvisPage.models, Theme.cfg.jarvisModel, 1) }
                    Stepper { width: parent.width; label: "Voice"; hint: "British voices · audition them all: jarvis-voices"; preview: true; onPlay: jarvisPage.preview(); valueText: jarvisPage.voiceName(Theme.cfg.jarvisVoice); onDec: Theme.cfg.jarvisVoice = jarvisPage.cycle(jarvisPage.voices, Theme.cfg.jarvisVoice, -1); onInc: Theme.cfg.jarvisVoice = jarvisPage.cycle(jarvisPage.voices, Theme.cfg.jarvisVoice, 1) }
                    Slider {
                        width: parent.width
                        label: "VOICE VOLUME"
                        value: Theme.cfg.jarvisVoiceVolume / 100
                        onMoved: v => { Theme.cfg.jarvisVoiceVolume = Math.round(v * 100); volumePreview.restart(); }
                    }
                    Text { width: parent.width; wrapMode: Text.Wrap; text: "Jarvis's voice and chime only · music and other apps are untouched · the same level on headphones, speakers and Bluetooth · \"speak louder / quieter\", \"set your volume to 40 percent\""; color: Theme.dim; font.family: st.mono; font.pixelSize: 11 }
                    Timer { id: volumePreview; interval: 450; onTriggered: jarvisPage.preview() }   // speak once the slider settles
                    Stepper { width: parent.width; visible: Theme.cfg.jarvisSpeaker !== ""; label: "Bluetooth speaker volume"; hint: "Jarvis's level on the room speaker · SAME follows VOICE VOLUME"; preview: Theme.cfg.jarvisSpeakerVolume >= 0; onPlay: jarvisPage.preview(); valueText: Theme.cfg.jarvisSpeakerVolume < 0 ? "SAME" : Theme.cfg.jarvisSpeakerVolume + "%"; onDec: Theme.cfg.jarvisSpeakerVolume = Theme.cfg.jarvisSpeakerVolume < 0 ? -1 : Theme.cfg.jarvisSpeakerVolume <= 0 ? -1 : Math.max(0, Theme.cfg.jarvisSpeakerVolume - 5); onInc: Theme.cfg.jarvisSpeakerVolume = Theme.cfg.jarvisSpeakerVolume < 0 ? Theme.cfg.jarvisVoiceVolume : Math.min(100, Theme.cfg.jarvisSpeakerVolume + 5) }
                    Stepper { width: parent.width; label: "Speech rate"; preview: true; onPlay: jarvisPage.preview(); valueText: Theme.cfg.jarvisSpeed.toFixed(1) + "×"; onDec: Theme.cfg.jarvisSpeed = Math.max(0.7, Math.round((Theme.cfg.jarvisSpeed - 0.1) * 10) / 10); onInc: Theme.cfg.jarvisSpeed = Math.min(1.5, Math.round((Theme.cfg.jarvisSpeed + 0.1) * 10) / 10) }
                    Stepper { width: parent.width; label: "Pitch"; hint: "Semitones, on top of the effect preset"; preview: true; onPlay: jarvisPage.preview(); valueText: (Theme.cfg.jarvisPitch > 0 ? "+" : "") + Theme.cfg.jarvisPitch.toFixed(1); onDec: Theme.cfg.jarvisPitch = Math.max(-3, Theme.cfg.jarvisPitch - 0.5); onInc: Theme.cfg.jarvisPitch = Math.min(2, Theme.cfg.jarvisPitch + 0.5) }
                    Stepper { width: parent.width; label: "Voice effect"; hint: ({ AUTO: "SUIT on headphones, HOLOGRAM on speakers", CLEAN: "No processing", HOLOGRAM: "Warm EQ, small room, faint chorus", SUIT: "Narrower, radio-like, inside the helmet" })[Theme.cfg.jarvisEffect] || "Custom preset · ~/.config/jarvis/effects.json"; preview: true; onPlay: jarvisPage.preview(); valueText: Theme.cfg.jarvisEffect; onDec: Theme.cfg.jarvisEffect = jarvisPage.cycle(jarvisPage.effects, Theme.cfg.jarvisEffect, -1); onInc: Theme.cfg.jarvisEffect = jarvisPage.cycle(jarvisPage.effects, Theme.cfg.jarvisEffect, 1) }
                    Stepper { width: parent.width; label: "Speaker without headphones"; hint: "Used when the output is the laptop speakers or a monitor · headphones, headsets and USB audio keep Jarvis"; preview: Theme.cfg.jarvisSpeaker !== ""; onPlay: jarvisPage.preview(); valueText: jarvisPage.speakerName(Theme.cfg.jarvisSpeaker); onDec: Theme.cfg.jarvisSpeaker = jarvisPage.cycle([""].concat(jarvisPage.speakers.map(s => s.mac)), Theme.cfg.jarvisSpeaker, -1); onInc: Theme.cfg.jarvisSpeaker = jarvisPage.cycle([""].concat(jarvisPage.speakers.map(s => s.mac)), Theme.cfg.jarvisSpeaker, 1) }
                    // INPUT DEVICE: Jarvis's own wake-word mic (jarvis.py Mic), not the system default input
                    readonly property var micChoices: ["auto", "default"].concat(Audio.inputs.map(n => n.name))
                    function micName(v) {
                        if (v === "auto" || v === "") return v === "" ? "SYSTEM DEFAULT" : "AUTO";
                        if (v === "default") return "SYSTEM DEFAULT";
                        const n = Audio.inputs.find(x => x.name === v);
                        return (n ? Audio.label(n).replace(/^.*Controller\s+/, "") : v + " (unplugged)").toUpperCase();
                    }
                    Stepper {
                        width: parent.width; label: "INPUT DEVICE"
                        hint: (Theme.cfg.jarvisMic === "auto" ? "Headset mic while one is plugged in, else the laptop mic · " : "")
                              + (JarvisFeed.mic.label ? "listening on " + JarvisFeed.mic.label : JarvisState.running ? "" : "used when Jarvis is on")
                        valueText: jarvisPage.micName(Theme.cfg.jarvisMic)
                        onDec: Theme.cfg.jarvisMic = jarvisPage.cycle(jarvisPage.micChoices, Theme.cfg.jarvisMic === "" ? "default" : Theme.cfg.jarvisMic, -1)
                        onInc: Theme.cfg.jarvisMic = jarvisPage.cycle(jarvisPage.micChoices, Theme.cfg.jarvisMic === "" ? "default" : Theme.cfg.jarvisMic, 1)
                    }
                    Toggle { width: parent.width; visible: Theme.cfg.jarvisMic === "auto"; label: "AUTO uses Bluetooth headset mics"; hint: "Off: Bluetooth headphones keep full music quality (their mic switches them to call quality while Jarvis listens)"; checked: Theme.cfg.jarvisMicBluetooth; onToggled: Theme.cfg.jarvisMicBluetooth = !Theme.cfg.jarvisMicBluetooth }
                    Stepper { width: parent.width; label: "Follow-up window"; hint: "Keeps listening after a reply, no wake word needed"; valueText: Theme.cfg.jarvisFollowup > 0 ? Theme.cfg.jarvisFollowup + " S" : "OFF"; onDec: Theme.cfg.jarvisFollowup = jarvisPage.cycle(jarvisPage.follows, Theme.cfg.jarvisFollowup, -1); onInc: Theme.cfg.jarvisFollowup = jarvisPage.cycle(jarvisPage.follows, Theme.cfg.jarvisFollowup, 1) }
                    Stepper { width: parent.width; label: "DECISIONS"; hint: Theme.cfg.jarvisDecisions === "local" ? "Common commands decided on this PC (offline, ~5 ms) · Claude for the rest" : "Everything the regex rules miss goes to Claude"; valueText: Theme.cfg.jarvisDecisions === "local" ? "LOCAL+CLAUDE" : "CLAUDE ONLY"; onDec: Theme.cfg.jarvisDecisions = Theme.cfg.jarvisDecisions === "local" ? "claude" : "local"; onInc: Theme.cfg.jarvisDecisions = Theme.cfg.jarvisDecisions === "local" ? "claude" : "local" }
                    Stepper { width: parent.width; visible: Theme.cfg.jarvisDecisions === "local"; label: "Local confidence"; hint: "Higher = fewer local actions, more sent to Claude · tune with tools/eval_router.py"; valueText: Theme.cfg.jarvisRouterThreshold.toFixed(2); onDec: Theme.cfg.jarvisRouterThreshold = Math.max(0.5, Math.round((Theme.cfg.jarvisRouterThreshold - 0.01) * 100) / 100); onInc: Theme.cfg.jarvisRouterThreshold = Math.min(0.95, Math.round((Theme.cfg.jarvisRouterThreshold + 0.01) * 100) / 100) }
                    Toggle { width: parent.width; label: "Spoken replies"; hint: "Off = replies only show on the toast"; checked: Theme.cfg.jarvisSpeak; onToggled: Theme.cfg.jarvisSpeak = !Theme.cfg.jarvisSpeak }
                    Toggle { width: parent.width; label: "Lower music while speaking"; hint: "Spotify and other MPRIS players"; checked: Theme.cfg.jarvisDuck; onToggled: Theme.cfg.jarvisDuck = !Theme.cfg.jarvisDuck }
                    Toggle { width: parent.width; label: "Pause in combat mode"; hint: "Wake word off, mic released · timers still go off"; checked: Theme.cfg.gameJarvis; onToggled: Theme.cfg.gameJarvis = !Theme.cfg.gameJarvis }
                    Toggle { width: parent.width; label: "Confirm sensitive actions"; hint: "Always on · power, closing windows, deleting, kill switch, messages sent as you"; checked: true; enabled: false; opacity: 0.6 }

                    // Phase-2 integrations: entries in ~/.config/jarvis/servers.json, tokens in the system keyring.
                    // CONNECT opens a terminal running the sign-in flow (`jarvis connect …`).
                    Text { text: "INTEGRATIONS"; topPadding: 10; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Process {
                        id: integrationList
                        command: [Quickshell.env("HOME") + "/.local/bin/jarvis", "integrations", "--json"]
                        stdout: StdioCollector { onStreamFinished: { try { jarvisPage.integrations = JSON.parse(text); } catch (e) {} } }
                    }
                    Timer { interval: 4000; repeat: true; triggeredOnStart: true; running: jarvisPage.visible; onTriggered: { integrationList.running = true; spotifyStatus.running = true; } }
                    Repeater {
                        model: jarvisPage.integrations
                        delegate: Item {
                            required property var modelData
                            width: jarvisPage.width; height: 52
                            Column {
                                anchors.left: parent.left; anchors.right: connectBtn.left; anchors.rightMargin: 16
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 3
                                Row {
                                    spacing: 10
                                    Text { text: modelData.name; color: Theme.text; font.family: st.mono; font.pixelSize: 14 }
                                    Text {
                                        text: modelData.state
                                        color: modelData.connected ? Theme.primary : Theme.dim
                                        font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 2
                                    }
                                }
                                Text { width: parent.width; elide: Text.ElideRight; text: modelData.label + " · " + modelData.detail; color: Theme.dim; font.family: st.mono; font.pixelSize: 11 }
                            }
                            SmallButton {
                                id: connectBtn
                                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                text: modelData.connected ? "RECONNECT" : modelData.optional ? "SET UP" : "CONNECT"
                                active: modelData.connected
                                opacity: modelData.optional && !modelData.connected ? 0.6 : 1
                                onClicked: { Hyprland.dispatch(Hypr.exec("kitty --hold " + Quickshell.env("HOME") + "/.local/bin/jarvis connect " + modelData.auth)); LauncherState.closeAll(); }
                            }
                        }
                    }
                    Toggle { width: parent.width; label: "AUTO-UPDATE TRACKER"; hint: Theme.cfg.jarvisAutoUpdateTracker ? "Grades, new LEARN work and moved deadlines go into your SE tracker and are announced · \"jarvis tracker undo\" reverts the last write" : "Each tracker update is offered first, spoken and on the HUD · your own requests always ask"; checked: Theme.cfg.jarvisAutoUpdateTracker; onToggled: Theme.cfg.jarvisAutoUpdateTracker = !Theme.cfg.jarvisAutoUpdateTracker }
                    Toggle { width: parent.width; label: "AUTO-ADD ASSIGNMENTS"; hint: "Fallback while no tracker sheet is set up · LEARN due dates go into \"STARK – Assignments\" without asking · that calendar only, never your main one"; checked: Theme.cfg.jarvisAutoAddAssignments; onToggled: Theme.cfg.jarvisAutoAddAssignments = !Theme.cfg.jarvisAutoAddAssignments }
                    Stepper { width: parent.width; label: "Assignments calendar"; hint: "Account that holds \"STARK – Assignments\""; valueText: Theme.cfg.jarvisAssignmentsAccount === "microsoft" ? "OUTLOOK" : "GOOGLE"; onDec: Theme.cfg.jarvisAssignmentsAccount = Theme.cfg.jarvisAssignmentsAccount === "microsoft" ? "google" : "microsoft"; onInc: Theme.cfg.jarvisAssignmentsAccount = Theme.cfg.jarvisAssignmentsAccount === "microsoft" ? "google" : "microsoft" }
                    // Spotify: his own developer app, PKCE sign-in, tokens in the keyring (~/.config/jarvis/mcp/spotify_api.py);
                    // DJ mode runs in the voice process (~/.config/jarvis/core/dj.py).
                    Text { text: "SPOTIFY"; topPadding: 10; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Process {
                        id: spotifyStatus
                        command: [Quickshell.env("HOME") + "/.local/bin/jarvis", "spotify", "status", "--json"]
                        stdout: StdioCollector { onStreamFinished: { try { jarvisPage.spotify = JSON.parse(text); } catch (e) {} } }
                    }
                    Item {
                        width: jarvisPage.width; height: 52
                        Column {
                            anchors.left: parent.left; anchors.right: spotifyBtns.left; anchors.rightMargin: 16
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 3
                            Row {
                                spacing: 10
                                Text { text: "Spotify"; color: Theme.text; font.family: st.mono; font.pixelSize: 14 }
                                Text {
                                    text: jarvisPage.spotify.connected ? "CONNECTED" : "NOT CONNECTED"
                                    color: jarvisPage.spotify.connected ? Theme.primary : Theme.dim
                                    font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 2
                                }
                            }
                            Text {
                                width: parent.width; elide: Text.ElideRight
                                text: (jarvisPage.spotify.user ? jarvisPage.spotify.user + " · " : "") + (jarvisPage.spotify.detail || "Your own developer app · CONNECT walks you through it")
                                color: Theme.dim; font.family: st.mono; font.pixelSize: 11
                            }
                        }
                        Row {
                            id: spotifyBtns
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            spacing: 8
                            ConfirmButton {
                                visible: jarvisPage.spotify.connected === true
                                label: "DISCONNECT"
                                onConfirmed: { Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/jarvis", "spotify", "disconnect"]); spotifyStatus.running = true; }
                            }
                            SmallButton {
                                text: jarvisPage.spotify.connected ? "RECONNECT" : "CONNECT"
                                active: jarvisPage.spotify.connected === true
                                onClicked: { Hyprland.dispatch(Hypr.exec("kitty --hold " + Quickshell.env("HOME") + "/.local/bin/jarvis spotify connect")); LauncherState.closeAll(); }
                            }
                        }
                    }
                    Stepper {
                        width: parent.width; label: "DJ CHATTER"
                        hint: ({ off: "DJ mode never talks between tracks", rare: "A short line every 4–5 tracks, music ducked under it", normal: "A short line every 2–3 tracks" })[Theme.cfg.jarvisDjChatter] || ""
                        valueText: Theme.cfg.jarvisDjChatter.toUpperCase()
                        onDec: Theme.cfg.jarvisDjChatter = jarvisPage.cycle(["off", "rare", "normal"], Theme.cfg.jarvisDjChatter, -1)
                        onInc: Theme.cfg.jarvisDjChatter = jarvisPage.cycle(["off", "rare", "normal"], Theme.cfg.jarvisDjChatter, 1)
                    }
                    FileView {
                        path: Quickshell.env("HOME") + "/.config/jarvis/dj_moods.json"
                        watchChanges: true; onFileChanged: reload()
                        onLoaded: { try { jarvisPage.djMoods = Object.keys(JSON.parse(text()).moods || {}); } catch (e) {} }
                    }
                    FileView {
                        id: savedMoods
                        property var names: []
                        path: Quickshell.env("HOME") + "/.local/share/jarvis/dj/moods.json"
                        watchChanges: true; onFileChanged: reload(); printErrors: false
                        onLoaded: { try { names = Object.keys(JSON.parse(text())); } catch (e) {} }
                    }
                    Text {
                        width: parent.width; wrapMode: Text.Wrap
                        text: "MOODS · " + jarvisPage.djMoods.concat(savedMoods.names).join(" · ").toUpperCase()
                              + "\nSay \"DJ for me\", \"play something for studying\", \"more / less like this\", \"save this vibe as …\""
                        color: Theme.dim; font.family: st.mono; font.pixelSize: 11; lineHeight: 1.3
                    }
                    Text {
                        width: parent.width; wrapMode: Text.Wrap
                        text: "CROSSFADE · Spotify's API can't set it: Spotify → Settings → Playback → Crossfade songs (6–8 s suits DJ mode)"
                        color: Theme.faint; font.family: st.mono; font.pixelSize: 11
                    }
                    Text { text: "WINDOW READING"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Stepper { width: parent.width; label: "Watch every"; hint: "How often a watcher looks at its window · compared on this machine, Claude only looks when enough changed"; valueText: Theme.cfg.jarvisWatchInterval + " S"; onDec: Theme.cfg.jarvisWatchInterval = Math.max(3, Theme.cfg.jarvisWatchInterval - (Theme.cfg.jarvisWatchInterval > 30 ? 10 : Theme.cfg.jarvisWatchInterval > 10 ? 5 : 1)); onInc: Theme.cfg.jarvisWatchInterval = Math.min(300, Theme.cfg.jarvisWatchInterval + (Theme.cfg.jarvisWatchInterval >= 30 ? 10 : Theme.cfg.jarvisWatchInterval >= 10 ? 5 : 1)) }
                    Column {
                        width: parent.width; spacing: 4
                        Text { text: "Never read or watch (window titles / apps, comma-separated · Enter to save)"; color: Theme.textSoft; font.family: st.mono; font.pixelSize: 12 }
                        Rectangle {
                            width: parent.width; height: Math.max(32, blockIn.contentHeight + 14)
                            color: Theme.d(0.9)
                            border.color: blockIn.activeFocus ? Theme.primary : Theme.p(0.4)
                            TextEdit {
                                id: blockIn
                                anchors.fill: parent; anchors.margins: 7
                                wrapMode: TextEdit.Wrap
                                color: Theme.text; selectByMouse: true
                                font.family: st.mono; font.pixelSize: 12
                                text: (Theme.cfg.jarvisCaptureBlocklist || []).join(", ")
                                function save() {
                                    const terms = text.split(/[,\n]/).map(t => t.trim().toLowerCase()).filter(t => t !== "");
                                    Theme.cfg.jarvisCaptureBlocklist = terms.filter((t, i) => terms.indexOf(t) === i);
                                    text = Theme.cfg.jarvisCaptureBlocklist.join(", ");
                                }
                                Keys.onReturnPressed: { save(); focus = false; }
                                Keys.onEnterPressed: { save(); focus = false; }
                                onActiveFocusChanged: if (!activeFocus) save()
                            }
                        }
                        Text { width: parent.width; wrapMode: Text.Wrap; text: "Always refused, whatever this says: the lock screen, password / permission / keyring prompts and password managers. Jarvis only reads a window you name; captures stay in memory, never on disk, and what's on screen is data, never an instruction."; color: Theme.faint; font.family: st.mono; font.pixelSize: 11 }
                    }
                    Text { width: parent.width; wrapMode: Text.Wrap; text: "Read-only by default. Sending, creating, deleting or editing anything needs your spoken yes. Email, calendar and document text is treated as data, never as commands. Setup: ~/.config/jarvis/docs"; color: Theme.faint; font.family: st.mono; font.pixelSize: 11 }
                    Row {
                        spacing: 10
                        SmallButton { text: "TEST VOICE"; onClicked: Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/jarvis", "--say", "At your service, sir."]) }
                        SmallButton { text: "MISSED COMMANDS"; onClicked: { Hyprland.dispatch(Hypr.exec("kitty --hold " + Quickshell.env("HOME") + "/.local/bin/jarvis --misses")); LauncherState.closeAll(); } }
                        SmallButton { text: "EDIT JARVIS"; onClicked: { Hyprland.dispatch(Hypr.exec("kate ~/.config/jarvis")); LauncherState.closeAll(); } }
                    }
                    Text { width: parent.width; wrapMode: Text.Wrap; text: "Claude runs on your Pro login (no API key). Memory: ~/.local/share/jarvis/jarvis.db"; color: Theme.faint; font.family: st.mono; font.pixelSize: 11 }
                }

                // ════════ LAUNCHER ════════
                LauncherPage {
                    visible: LauncherState.settingsTab === "LAUNCHER" && st.visible
                    width: parent.width
                    onReleaseFocus: focusCatcher.forceActiveFocus()
                }

                // ════════ SYSTEM ════════
                Column {
                    visible: LauncherState.settingsTab === "SYSTEM"
                    width: parent.width
                    spacing: 14

                    HudFrame {
                        width: parent.width; height: 130
                        title: "ABOUT"
                        Column {
                            spacing: 6
                            Text { text: "STARK OS  ·  " + sys.distro; color: Theme.text; font.family: st.mono; font.pixelSize: 14 }
                            Text { text: "Kernel " + sys.kernel + "   ·   " + sys.hypr; color: Theme.dim; font.family: st.mono; font.pixelSize: 12 }
                            Text { text: "Uptime " + SysStats.fmtUptime(SysStats.uptimeS) + "   ·   " + SysStats.ramTotalGb.toFixed(0) + " GB RAM   ·   " + Math.round(SysStats.diskTotalGb) + " GB disk"; color: Theme.dim; font.family: st.mono; font.pixelSize: 12 }
                        }
                    }

                    Column {
                        visible: sys.power !== ""
                        spacing: 8
                        Text { text: "POWER MODE"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                        Row {
                            spacing: 10
                            Repeater {
                                model: [["power-saver", "SAVER"], ["balanced", "BALANCED"], ["performance", "PERFORMANCE"]]
                                delegate: SmallButton {
                                    required property var modelData
                                    text: modelData[1]
                                    active: sys.power === modelData[0]
                                    onClicked: st.act(["powerprofilesctl", "set", modelData[0]], "Power: " + modelData[1].toLowerCase())
                                }
                            }
                        }
                    }

                    Text { text: "FINGERPRINT"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Text { text: "Unlock the lock screen with your finger (your password always works too)."; color: Theme.textSoft; font.family: st.mono; font.pixelSize: 12 }
                    Row {
                        spacing: 10
                        SmallButton { text: "ENROLL A FINGER"; onClicked: { Hyprland.dispatch(Hypr.exec("kitty -e sh -c 'fprintd-enroll; echo; read -p \"Press Enter to close\"'")); LauncherState.closeAll(); } }
                        SmallButton { text: "TEST"; onClicked: { Hyprland.dispatch(Hypr.exec("kitty -e sh -c 'fprintd-verify; echo; read -p \"Press Enter to close\"'")); LauncherState.closeAll(); } }
                        ConfirmButton { label: "REMOVE ALL"; onConfirmed: st.act(["fprintd-delete", Quickshell.env("USER")], "Removing fingerprints") }
                    }

                    Text { text: "SLEEP & SCREEN"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Stepper { width: parent.width; label: "Dim the screen after"; valueText: Idle.label(Theme.cfg.idleDim); onDec: Theme.cfg.idleDim = Idle.step(Theme.cfg.idleDim, -1); onInc: Theme.cfg.idleDim = Idle.step(Theme.cfg.idleDim, 1) }
                    Stepper { width: parent.width; label: "Lock after"; valueText: Idle.label(Theme.cfg.idleLock); onDec: Theme.cfg.idleLock = Idle.step(Theme.cfg.idleLock, -1); onInc: Theme.cfg.idleLock = Idle.step(Theme.cfg.idleLock, 1) }
                    Stepper { width: parent.width; label: "Turn screens off after"; valueText: Idle.label(Theme.cfg.idleScreenOff); onDec: Theme.cfg.idleScreenOff = Idle.step(Theme.cfg.idleScreenOff, -1); onInc: Theme.cfg.idleScreenOff = Idle.step(Theme.cfg.idleScreenOff, 1) }
                    Stepper { width: parent.width; label: "Sleep after"; hint: "Closing the lid always sleeps (unless docked)"; valueText: Idle.label(Theme.cfg.idleSleep); onDec: Theme.cfg.idleSleep = Idle.step(Theme.cfg.idleSleep, -1); onInc: Theme.cfg.idleSleep = Idle.step(Theme.cfg.idleSleep, 1) }

                    Text { text: "BATTERY"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Text {
                        text: PowerMode.onBattery
                              ? (PowerMode.saver ? "On battery — saver active" : "On battery — saver off")
                              : (SysStats.charging ? "Plugged in — charging" : "Plugged in")
                        color: PowerMode.saver ? Theme.secondary : Theme.textSoft
                        font.family: st.mono; font.pixelSize: 13
                    }
                    Toggle { width: parent.width; label: "Battery saver when unplugged"; hint: "Applies everything below automatically, undone when you plug in"; checked: Theme.cfg.autoSaver; onToggled: Theme.cfg.autoSaver = !Theme.cfg.autoSaver }
                    Toggle { width: parent.width; label: "Turn off blur and shadows"; hint: "Biggest GPU saving"; checked: Theme.cfg.saverNoBlur; onToggled: Theme.cfg.saverNoBlur = !Theme.cfg.saverNoBlur }
                    Toggle { width: parent.width; label: "Laptop screen at 48 Hz"; hint: "Instead of 60 Hz"; checked: Theme.cfg.saverLowRefresh; onToggled: Theme.cfg.saverLowRefresh = !Theme.cfg.saverLowRefresh }
                    Toggle { width: parent.width; label: "Pause Jarvis"; hint: "Wake-word listening uses a little CPU all the time"; checked: Theme.cfg.saverStopJarvis; onToggled: Theme.cfg.saverStopJarvis = !Theme.cfg.saverStopJarvis }
                    Column {
                        spacing: 8
                        Text { text: "EFFECTS ON BATTERY"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                        Row {
                            spacing: 10
                            Repeater {
                                model: [[0, "STATIC"], [12, "ECO · 12"], [24, "BALANCED · 24"]]
                                delegate: SmallButton {
                                    required property var modelData
                                    text: modelData[1]
                                    active: Theme.cfg.batteryFps === modelData[0]
                                    onClicked: Theme.cfg.batteryFps = modelData[0]
                                }
                            }
                        }
                    }

                    Text { text: "COMBAT MODE"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Item {
                        width: parent.width; height: 34
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: GameMode.batteryWarn ? "Engaged — on battery, balanced profile"
                                : GameMode.active ? "Engaged — " + (GameMode.manual ? "manual" : (GameMode.games.join(", ") || "gamemode"))
                                : "Standing by"
                            color: GameMode.batteryWarn ? "#ff5f5f" : GameMode.active ? Theme.secondary : Theme.textSoft
                            font.family: st.mono; font.pixelSize: 13
                        }
                        SmallButton {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            text: GameMode.active ? "DISENGAGE" : "ENGAGE"
                            active: GameMode.active
                            onClicked: GameMode.toggle()
                        }
                    }
                    Toggle { width: parent.width; label: "Auto-detect games"; hint: "Steam / gamescope / games.conf windows, or gamemoderun"; checked: Theme.cfg.gameAuto; onToggled: Theme.cfg.gameAuto = !Theme.cfg.gameAuto }
                    Toggle { width: parent.width; label: "Hyprland effects off"; hint: "Blur, shadows, animations off · tearing allowed for the game"; checked: Theme.cfg.gameHypr; onToggled: Theme.cfg.gameHypr = !Theme.cfg.gameHypr }
                    Toggle { width: parent.width; label: "Also turn off VFR"; hint: "Renders every frame — more iGPU load; Hyprland advises against it"; checked: Theme.cfg.gameNoVfr; onToggled: Theme.cfg.gameNoVfr = !Theme.cfg.gameNoVfr }
                    Toggle { width: parent.width; label: "Performance power profile"; hint: "On AC · balanced (and a warning) on battery"; checked: Theme.cfg.gamePower; onToggled: Theme.cfg.gamePower = !Theme.cfg.gamePower }
                    Toggle { width: parent.width; label: "Pause HUD animations"; hint: "Effects and visualizer stop, panels hide on the game screen · bar every 10 s"; checked: Theme.cfg.gameHud; onToggled: Theme.cfg.gameHud = !Theme.cfg.gameHud }
                    Toggle { width: parent.width; label: "Keep panels on other screens"; hint: "Hide them only where the game is · the rest run without animations"; checked: Theme.cfg.gameKeepPanels; onToggled: Theme.cfg.gameKeepPanels = !Theme.cfg.gameKeepPanels }
                    Toggle { width: parent.width; label: "Keep music panel"; hint: "Track, art and controls · visualizer frozen, cava off"; checked: Theme.cfg.gameKeepMedia; enabled: Theme.cfg.gameKeepPanels; opacity: enabled ? 1 : 0.4; onToggled: Theme.cfg.gameKeepMedia = !Theme.cfg.gameKeepMedia }
                    Toggle { width: parent.width; label: "Keep stats panel"; hint: "CPU, GPU, RAM, network · refreshes every 2.5 s"; checked: Theme.cfg.gameKeepDiag; enabled: Theme.cfg.gameKeepPanels; opacity: enabled ? 1 : 0.4; onToggled: Theme.cfg.gameKeepDiag = !Theme.cfg.gameKeepDiag }
                    Toggle { width: parent.width; label: "Combat telemetry layout"; hint: "Per-core CPU, clocks, temps, iGPU, fans, power, game disk · main screen if the game is on the stats one"; checked: Theme.cfg.gameTelemetry; enabled: Theme.cfg.gameKeepPanels && Theme.cfg.gameKeepDiag; opacity: enabled ? 1 : 0.4; onToggled: Theme.cfg.gameTelemetry = !Theme.cfg.gameTelemetry }
                    Toggle { width: parent.width; label: "Keep telemetry with windows open"; hint: "Discord etc. on that screen tile beside it instead of hiding it"; checked: Theme.cfg.gameTelemetryBeside; enabled: Theme.cfg.gameKeepPanels && Theme.cfg.gameKeepDiag && Theme.cfg.gameTelemetry; opacity: enabled ? 1 : 0.4; onToggled: Theme.cfg.gameTelemetryBeside = !Theme.cfg.gameTelemetryBeside }
                    Toggle { width: parent.width; label: "Pause Jarvis"; hint: "Frees the mic · comes back afterwards if it was on"; checked: Theme.cfg.gameJarvis; onToggled: Theme.cfg.gameJarvis = !Theme.cfg.gameJarvis }
                    Toggle { width: parent.width; label: "Mute notifications"; hint: "Do-not-disturb on mako, swaync or dunst, if one is running"; checked: Theme.cfg.gameNotify; onToggled: Theme.cfg.gameNotify = !Theme.cfg.gameNotify }
                    Text { text: "Effects, power and notification changes apply the next time it engages."; color: Theme.faint; font.family: st.mono; font.pixelSize: 11 }
                    Row {
                        spacing: 10
                        SmallButton { text: "EDIT GAMES LIST"; onClicked: { Hyprland.dispatch(Hypr.exec("kate ~/.config/stark-game/games.conf")); LauncherState.closeAll(); } }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: "~/.config/stark-game/games.conf"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11 }
                    }

                    Text { text: "CONFIG"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Row {
                        spacing: 10
                        SmallButton { text: "HYPRLAND CONFIG"; onClicked: { Hyprland.dispatch(Hypr.exec("kate ~/.config/hypr/hyprland.lua ~/.config/hypr/stark/*.lua")); LauncherState.closeAll(); } }
                        SmallButton { text: "IDLE / SLEEP"; onClicked: { Hyprland.dispatch(Hypr.exec("kate ~/.config/hypr/hypridle.conf")); LauncherState.closeAll(); } }
                        SmallButton { text: "FULL KDE SETTINGS"; onClicked: { Hyprland.dispatch(Hypr.exec("systemsettings")); LauncherState.closeAll(); } }
                    }

                    Text { text: "SESSION"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Row {
                        spacing: 10
                        SmallButton { text: "LOCK"; onClicked: LockState.requestLock() }
                        SmallButton { text: "SLEEP"; onClicked: { LauncherState.closeAll(); Quickshell.execDetached(["stark-govee", "suspend"]); } }
                        ConfirmButton { label: "LOG OUT"; onConfirmed: LockState.power("logout") }
                        ConfirmButton { label: "RESTART"; onConfirmed: LockState.power("reboot") }
                        ConfirmButton { label: "SHUT DOWN"; onConfirmed: LockState.power("shutdown") }
                    }
                }
            }
        }

        Text {
            id: statusLine
            anchors.left: nav.right; anchors.leftMargin: 28
            anchors.bottom: parent.bottom
            text: st.status
            color: st.status.startsWith("✕") ? "#ff6b6b" : Theme.secondary
            font.family: st.mono; font.pixelSize: 12
        }
    }

    // ══════════ Data sources ══════════

    // Wi-Fi
    QtObject {
        id: wifi
        property bool on: false
        property string current: ""
        property var networks: []
    }
    function splitTerse(line) {
        // nmcli -t output: fields split by ":" with literal colons escaped as "\:"
        const out = []; let cur = "";
        for (let i = 0; i < line.length; i++) {
            const c = line[i];
            if (c === "\\" && i + 1 < line.length) { cur += line[++i]; continue; }
            if (c === ":") { out.push(cur); cur = ""; continue; }
            cur += c;
        }
        out.push(cur);
        return out;
    }
    Process {
        id: wifiPoll
        command: ["sh", "-c", "echo \"RADIO $(nmcli radio wifi)\"; nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY dev wifi list 2>/dev/null; echo '---SAVED---'; nmcli -t -f NAME,TYPE connection show 2>/dev/null"]
        stdout: StdioCollector {
            onStreamFinished: {
                const lines = text.split("\n");
                const saved = new Set();
                const seen = {};
                let inSaved = false, current = "";
                const nets = [];
                for (const l of lines) {
                    if (l.startsWith("RADIO ")) { wifi.on = l.slice(6).trim() === "enabled"; continue; }
                    if (l === "---SAVED---") { inSaved = true; continue; }
                    if (!l.trim()) continue;
                    const f = st.splitTerse(l);
                    if (inSaved) { if ((f[1] || "").includes("wireless")) saved.add(f[0]); continue; }
                    const ssid = f[1] || "";
                    if (!ssid) continue;
                    const n = { ssid: ssid, inUse: f[0] === "*", signal: Number(f[2]) || 0, secure: (f[3] || "") !== "" && f[3] !== "--" };
                    if (n.inUse) current = ssid;
                    if (!seen[ssid] || n.inUse || n.signal > seen[ssid].signal) seen[ssid] = n;
                }
                for (const k in seen) { seen[k].saved = saved.has(k); nets.push(seen[k]); }
                nets.sort((a, b) => (b.inUse - a.inUse) || (b.saved - a.saved) || (b.signal - a.signal));
                wifi.current = current;
                wifi.networks = nets.slice(0, 14);
            }
        }
    }

    // Bluetooth
    QtObject {
        id: bt
        property bool on: false
        property var devices: []
    }
    Process {
        id: btPoll
        command: ["sh", "-c", "bluetoothctl show 2>/dev/null | awk '/Powered:/ {print \"POWER\", $2; exit}'; echo '---ALL---'; bluetoothctl devices 2>/dev/null; echo '---PAIRED---'; bluetoothctl devices Paired 2>/dev/null; echo '---CONNECTED---'; bluetoothctl devices Connected 2>/dev/null"]
        stdout: StdioCollector {
            onStreamFinished: {
                let section = "", all = [], paired = new Set(), conn = new Set();
                for (const l of text.split("\n")) {
                    if (l.startsWith("POWER ")) { bt.on = l.slice(6).trim() === "yes"; continue; }
                    if (l.startsWith("---")) { section = l; continue; }
                    const m = l.match(/^Device ([0-9A-F:]{17}) (.*)$/i);
                    if (!m) continue;
                    if (section === "---ALL---") all.push({ mac: m[1], name: m[2] });
                    else if (section === "---PAIRED---") paired.add(m[1]);
                    else if (section === "---CONNECTED---") conn.add(m[1]);
                }
                const list = all
                    .filter(d => !/^([0-9A-F]{2}-){5}[0-9A-F]{2}$/i.test(d.name))   // hide unnamed devices
                    .map(d => ({ mac: d.mac, name: d.name, paired: paired.has(d.mac), connected: conn.has(d.mac) }));
                list.sort((a, b) => (b.connected - a.connected) || (b.paired - a.paired) || a.name.localeCompare(b.name));
                bt.devices = list;
            }
        }
    }
    Process {
        id: btScan
        command: ["bluetoothctl", "--timeout", "12", "scan", "on"]
        onExited: btPoll.running = true
    }

    // System info
    QtObject {
        id: sys
        property string kernel: ""
        property string hypr: ""
        property string distro: ""
        property string power: ""
    }
    Process {
        id: sysPoll
        command: ["sh", "-c", "echo \"K $(uname -r)\"; echo \"H $(hyprctl version 2>/dev/null | head -1 | awk '{print $1, $2}')\"; echo \"D $(. /etc/os-release; echo $PRETTY_NAME)\"; echo \"P $(powerprofilesctl get 2>/dev/null)\""]
        stdout: StdioCollector {
            onStreamFinished: {
                for (const l of text.split("\n")) {
                    const v = l.slice(2).trim();
                    if (l.startsWith("K ")) sys.kernel = v;
                    else if (l.startsWith("H ")) sys.hypr = v;
                    else if (l.startsWith("D ")) sys.distro = v;
                    else if (l.startsWith("P ")) sys.power = v;
                }
            }
        }
    }

    // Keep lists fresh while open
    Timer {
        interval: 4000; repeat: true
        running: st.visible
        onTriggered: {
            if (LauncherState.settingsTab === "NETWORK") wifiPoll.running = true;
            if (LauncherState.settingsTab === "BLUETOOTH") btPoll.running = true;
        }
    }
}
