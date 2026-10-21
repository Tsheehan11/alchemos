// STARK OS settings — Wi-Fi, Bluetooth, appearance, HUD and system.
// Open with Super + , (comma), the SETTINGS button in the control center,
// or: qs ipc call settings toggle
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland

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
    readonly property var tabs: ["NETWORK", "BLUETOOTH", "DISPLAY", "AUDIO", "APPEARANCE", "HUD", "SYSTEM"]
    property string status: ""            // last action result, shown at the bottom

    onVisibleChanged: if (visible) { focusCatcher.forceActiveFocus(); refreshAll(); }

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
                        SmallButton { text: "ADVANCED (NMTUI)"; onClicked: { Hyprland.dispatch("exec kitty -e nmtui"); LauncherState.closeAll(); } }
                    }

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
                    visible: LauncherState.settingsTab === "APPEARANCE"
                    width: parent.width
                    spacing: 16

                    Text { text: "THEME"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Grid {
                        columns: 3
                        columnSpacing: 12; rowSpacing: 12
                        Repeater {
                            model: Theme.presets
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
                            }
                        }
                    }

                    Text { text: "CUSTOM — MAIN COLOR"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Swatches { selected: Theme.cfg.primary; onPicked: c => { Theme.cfg.primary = c; Theme.cfg.preset = "CUSTOM"; } }
                    Text { text: "CUSTOM — ACCENT COLOR"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Swatches { selected: Theme.cfg.secondary; onPicked: c => { Theme.cfg.secondary = c; Theme.cfg.preset = "CUSTOM"; } }

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

                    Toggle { width: parent.width; label: "Arc-reactor clock"; hint: "Main screen"; checked: Theme.cfg.showReactor; onToggled: Theme.cfg.showReactor = !Theme.cfg.showReactor }
                    Toggle { width: parent.width; label: "Diagnostics wall"; hint: "Second monitor, when docked"; checked: Theme.cfg.showDiag; onToggled: Theme.cfg.showDiag = !Theme.cfg.showDiag }
                    Toggle { width: parent.width; label: "Audio deck"; hint: "Laptop screen, when docked"; checked: Theme.cfg.showMedia; onToggled: Theme.cfg.showMedia = !Theme.cfg.showMedia }
                    Toggle { width: parent.width; label: "Hide panels behind windows"; hint: "Clock, diagnostics and audio deck only show on screens with no windows open"; checked: Theme.cfg.hideHudBehindWindows; onToggled: Theme.cfg.hideHudBehindWindows = !Theme.cfg.hideHudBehindWindows }
                    Toggle { width: parent.width; label: "Volume & brightness pop-up"; hint: "Shows on the screen you're using"; checked: Theme.cfg.osd; onToggled: Theme.cfg.osd = !Theme.cfg.osd }
                    Toggle { width: parent.width; label: "Jarvis"; hint: "Runs while docked, stops on laptop only (same as the control center switch)"; checked: JarvisState.userWantsJarvis; onToggled: JarvisState.setWanted(!JarvisState.userWantsJarvis) }
                    Row {
                        spacing: 10
                        SmallButton { text: "RELOAD HUD"; onClicked: Quickshell.reload(true) }
                        SmallButton { text: "EDIT HUD FILES"; onClicked: { Hyprland.dispatch("exec kate ~/.config/quickshell"); LauncherState.closeAll(); } }
                    }
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
                        SmallButton { text: "ENROLL A FINGER"; onClicked: { Hyprland.dispatch("exec kitty -e sh -c 'fprintd-enroll; echo; read -p \"Press Enter to close\"'"); LauncherState.closeAll(); } }
                        SmallButton { text: "TEST"; onClicked: { Hyprland.dispatch("exec kitty -e sh -c 'fprintd-verify; echo; read -p \"Press Enter to close\"'"); LauncherState.closeAll(); } }
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

                    Text { text: "CONFIG"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Row {
                        spacing: 10
                        SmallButton { text: "HYPRLAND CONFIG"; onClicked: { Hyprland.dispatch("exec kate ~/.config/hypr/hyprland.conf"); LauncherState.closeAll(); } }
                        SmallButton { text: "IDLE / SLEEP"; onClicked: { Hyprland.dispatch("exec kate ~/.config/hypr/hypridle.conf"); LauncherState.closeAll(); } }
                        SmallButton { text: "FULL KDE SETTINGS"; onClicked: { Hyprland.dispatch("exec systemsettings"); LauncherState.closeAll(); } }
                    }

                    Text { text: "SESSION"; color: Theme.dim; font.family: st.mono; font.pixelSize: 11; font.letterSpacing: 3 }
                    Row {
                        spacing: 10
                        SmallButton { text: "LOCK"; onClicked: LockState.requestLock() }
                        SmallButton { text: "SLEEP"; onClicked: { LauncherState.closeAll(); Quickshell.execDetached(["systemctl", "suspend"]); } }
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
