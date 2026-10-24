// STARK OS — Quickshell entry point
import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    // Animated hologram background, on every screen
    Variants {
        model: Quickshell.screens
        GridBackground {}
    }

    // Top bar on every screen
    Variants {
        model: Quickshell.screens
        Bar {}
    }

    // Left monitor: arc-reactor clock
    Variants {
        model: Quickshell.screens
        HudWindow {}
    }

    // Middle monitor: diagnostics wall
    Variants {
        model: Quickshell.screens
        DiagPanel {}
    }

    // Laptop screen: audio deck
    Variants {
        model: Quickshell.screens
        MediaPanel {}
    }

    // Overlays: radial launcher, app search, Jarvis pop-up
    Variants {
        model: Quickshell.screens
        Launcher {}
    }
    Variants {
        model: Quickshell.screens
        AppSearch {}
    }
    Variants {
        model: Quickshell.screens
        JarvisToast {}
    }
    Variants {
        model: Quickshell.screens
        DisplayConfirm {}
    }
    Variants {
        model: Quickshell.screens
        Osd {}
    }
    Variants {
        model: Quickshell.screens
        GameToast {}
    }

    Variants {
        model: Quickshell.screens
        ControlCenter {}
    }
    Variants {
        model: Quickshell.screens
        Settings {}
    }
    Variants {
        model: Quickshell.screens
        Overview {}
    }
    Variants {
        model: Quickshell.screens
        PowerMenu {}
    }
    Variants {
        model: Quickshell.screens
        SecurityDoors {}
    }

    //   qs ipc call launcher toggle
    IpcHandler {
        target: "launcher"
        function toggle(): void { LauncherState.toggle() }
        function close(): void { LauncherState.closeAll() }
    }

    //   qs ipc call search toggle
    IpcHandler {
        target: "search"
        function toggle(): void { LauncherState.toggleSearch() }
    }

    //   qs ipc call control toggle
    IpcHandler {
        target: "control"
        function toggle(): void { LauncherState.toggleControl() }
    }

    //   qs ipc call overview toggle   (Super + Tab)
    IpcHandler {
        target: "overview"
        function toggle(): void { LauncherState.toggleOverview() }
    }

    //   qs ipc call osd brightness   (brightness keys)
    IpcHandler {
        target: "osd"
        function brightness(): void { OsdState.brightness() }
    }

    //   qs ipc call settings toggle
    IpcHandler {
        target: "settings"
        function toggle(): void { LauncherState.toggleSettings() }
        //   qs ipc call settings display   (Super+P)
        function display(): void { LauncherState.openSettings("DISPLAY") }
        //   qs ipc call settings open appearance
        function open(tab: string): void { LauncherState.openSettings(tab.toUpperCase()) }
    }

    //   used by ~/.config/hypr/stark-lock.sh
    IpcHandler {
        target: "stark"
        function lock(): void { LockState.requestLock() }            // Super + L
        function locked(): void { LockState.locked() }
        function unlocked(): void { LockState.unlocked() }
        function power(action: string): void { LockState.power(action) }   // shutdown | reboot | logout
        function menu(): void { LauncherState.togglePower() }        // power button / Super + Esc
    }

    //   used by ~/.local/bin/stark-game after each state change
    IpcHandler {
        target: "game"
        function refresh(): void { GameMode.refresh() }
        function toggle(): void { GameMode.toggle() }
    }

    //   used by ~/.config/jarvis/jarvis.py (core/hud.py)
    IpcHandler {
        target: "jarvis"
        function online(): void { JarvisState.beat() }
        function offline(): void { JarvisState.online = false }
        function listening(): void { JarvisState.startListening() }
        function transcript(text: string): void { JarvisState.setTranscript(text) }
        function thinking(): void { JarvisState.thinking() }
        function tool(label: string): void { JarvisState.tool(label) }       // "THEME → MARK III"
        function reply(text: string): void { JarvisState.setReply(text) }
        function confirm(text: string): void { JarvisState.confirm(text) }
        function followup(): void { JarvisState.followup() }
        function idle(): void { JarvisState.idle() }
        function toast(title: string, text: string): void { JarvisState.alert(title, text) }   // timers / reminders
        function paused(on: string): void { JarvisState.paused = on === "true" }
        function heard(msg: string): void { JarvisState.heard(msg) }
        function status(msg: string): void { JarvisState.status(msg) }
    }

    //   qs ipc call vpn toggle proton | connect school | disconnect | status   (VPN.qml)
    IpcHandler {
        target: "vpn"
        function toggle(provider: string): void { VPN.toggle(provider) }
        function connect(provider: string): void { VPN.connect(provider) }
        function disconnect(): void { VPN.disconnect() }
        function killswitch(on: string): void { VPN.setKillSwitch(on === "on" || on === "true") }
        function status(): string {
            return JSON.stringify({ active: VPN.active, selected: VPN.selected, state: VPN.state,
                                    providers: VPN.providers.map(p => ({ id: p.id, state: p.state, server: p.server || "", country: p.country || "" })) })
        }
    }

    //   qs ipc call profiles status | recheck   (display profiles, see Profiles.qml)
    IpcHandler {
        target: "profiles"
        function status(): string { return Profiles.key + " · " + Profiles.name + " · " + Theme.cfg.displayLayout }
        function recheck(): void { Profiles.recheck(true) }
    }
    // Saved preferences from the shell: `qs ipc call theme set panelOpacity 0.9`
    IpcHandler {
        target: "theme"
        function get(key: string): string { return JSON.stringify(Theme.cfg[key]) }
        function set(key: string, value: string): string {
            const cur = Theme.cfg[key];
            if (cur === undefined || typeof cur === "object") return "unknown key " + key;
            Theme.cfg[key] = typeof cur === "number" ? Number(value) : typeof cur === "boolean" ? value === "true" : value;
            return key + " = " + JSON.stringify(Theme.cfg[key]);
        }
        //   qs ipc call theme presets   → ["STARK","MARK III",…] (built-in + custom; Jarvis validates against it)
        function presets(): string { return JSON.stringify(Theme.allPresets.map(p => p.name)) }
        function preset(name: string): string {
            const p = Theme.allPresets.find(x => x.name === name.toUpperCase());
            if (!p) return "no preset " + name;
            Theme.applyPreset(p);
            return "preset " + p.name;
        }
    }
}
