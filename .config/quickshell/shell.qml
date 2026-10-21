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

    //   used by ~/.config/jarvis/jarvis.py
    IpcHandler {
        target: "jarvis"
        function online(): void { JarvisState.beat() }
        function offline(): void { JarvisState.online = false }
        function heard(msg: string): void { JarvisState.heard(msg) }
        function status(msg: string): void { JarvisState.status(msg) }
    }
}
