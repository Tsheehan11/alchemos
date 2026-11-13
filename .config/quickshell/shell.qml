// AlchemOS — Quickshell entry point
import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    // started here so it watches from login (FprintWatch.qml)
    readonly property bool fprintWatching: FprintWatch.watching

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

    // What each screen shows (Roles.shows: Settings → Display, Super+Shift+V). A panel only
    // exists on the screens showing it, so a NONE screen runs no timers / cava / stats for itself.
    Variants {
        model: Quickshell.screens
        Scope {
            id: slot
            required property var modelData
            readonly property string shows: Roles.shows(modelData)
            LazyLoader { active: slot.shows === "clock"; HudWindow { modelData: slot.modelData } }       // the skin's clock (Skin.clockUrl)
            LazyLoader {                                                                                  // diagnostics wall / combat telemetry
                active: slot.shows === "stats" || Perf.telemetryScreen === slot.modelData.name
                DiagPanel { modelData: slot.modelData }
            }
            LazyLoader { active: slot.shows === "music"; MediaPanel { modelData: slot.modelData } }       // audio deck
        }
    }

    // Desktop widgets: clocks, timers, now playing, stats, notes (Widgets.qml)
    Variants {
        model: Quickshell.screens
        WidgetLayer {}
    }
    Variants {                  // right-click the empty desktop → pick a widget
        model: Quickshell.screens
        WidgetMaker {}
    }

    // Overlays: radial launcher, app search, Orrin pop-up
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
        OrrinToast {}
    }
    Variants {                  // ORRIN console (Super + J): conversations, typed requests, tasks
        model: Quickshell.screens
        OrrinApp {}
    }
    Variants {                  // the glow around a window Orrin is working (stage 4, core/control.py)
        model: Quickshell.screens
        OrrinControl {}
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
    Variants {                  // screenshot shutter + "CAPTURE SAVED" toast (Shot.qml)
        model: Quickshell.screens
        ShotFlash {}
    }
    Variants {
        model: Quickshell.screens
        ShotToast {}
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
    Variants {                  // skin transitions and the preset ignite (IgniteState.qml)
        model: Quickshell.screens
        Ignite {}
    }

    //   qs ipc call widgets add clock diag top-right '{"tz":"America/New_York","label":"New York"}'
    //   qs ipc call widgets add timer current - '{"minutes":10,"label":"tea"}'
    //   qs ipc call widgets remove clock3 | clock | clock:diag
    //   qs ipc call widgets move weather "monitor 2" top-right -  |  move weather laptop 0.5 0.5  |  move clock - 1200 300
    //   qs ipc call widgets list | clear diag | clear all | pin clock true | resize stats huge | reset | types
    // Screens: main | diag | media / laptop | monitor N | a port or description | current; "-" keeps it.
    // move x y: a named position (y "-"), fractions 0–1 of the room on that screen, or pixels.
    IpcHandler {
        target: "widgets"
        function add(type: string, screen: string, position: string, params: string): string {
            let p = {};
            if (params && params !== "-") { try { p = JSON.parse(params); } catch (e) { return JSON.stringify({ ok: false, error: "params must be JSON" }); } }
            return JSON.stringify(Widgets.add(type, screen, position, p));
        }
        function remove(query: string): string { return JSON.stringify(Widgets.remove(query)) }
        function move(query: string, screen: string, x: string, y: string): string { return JSON.stringify(Widgets.move(query, screen, x, y)) }
        function reset(): string { return JSON.stringify(Widgets.reset()) }
        function pin(query: string, on: string): string { return JSON.stringify(Widgets.pin(query, on === "true" || on === "on" || on === "1")) }
        function resize(query: string, size: string): string { return JSON.stringify(Widgets.resize(query, size)) }   // small | normal | large | huge | bigger | smaller | 1.3
        function clear(screen: string): string { return JSON.stringify(Widgets.clear(screen)) }
        function list(): string { return JSON.stringify({ ok: true, docked: Roles.docked, current: Widgets.currentRole(), widgets: Widgets.list() }) }
        function types(): string { return JSON.stringify({ types: Widgets.types, positions: Widgets.positions, screens: Widgets.roles }) }
    }

    //   qs ipc call roles set tv music | set DP-6 clock | set "monitor 2" none | set laptop auto
    //   qs ipc call roles get | cycle   (cycle = the focused monitor, Super+Shift+V)
    IpcHandler {
        target: "roles"
        function set(screen: string, role: string): string { return JSON.stringify(Roles.setFor(screen, role)) }
        function get(): string { return JSON.stringify(Roles.status()) }
        function cycle(): string { return JSON.stringify(Roles.cycle()) }
    }

    //   qs ipc call shot region | screen | window | annotate   (Print, Shift+Print, Super+Shift+S; Shot.qml)
    //   qs ipc call shot output DP-6   (a given monitor)      status   (last shot as JSON)
    IpcHandler {
        target: "shot"
        function region(): string { return Shot.take("region") }
        function screen(): string { return Shot.take("screen") }
        function window(): string { return Shot.take("window") }
        function annotate(): string { return Shot.take("annotate") }
        function output(name: string): string { return Shot.take("screen", name) }
        function status(): string { return JSON.stringify({ busy: Shot.busy, last: Shot.last }) }
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

    //   used by ~/.config/hypr/alchemos-lock.sh
    IpcHandler {
        target: "alchemos"
        function lock(): void { LockState.requestLock() }            // Super + L
        function locked(): void { LockState.locked() }
        function unlocked(): void { LockState.unlocked() }
        function fingerprint(): void { LockState.fingerprint() }      // just before unlocked(): the finger matched
        function power(action: string): void { LockState.power(action) }   // shutdown | reboot | logout
        function menu(): void { LauncherState.togglePower() }        // power button / Super + Esc
    }

    //   Peek (Super + D is bound in hypr/alchemos/binds.lua; this is for scripts / Orrin)
    IpcHandler {
        target: "peek"
        function toggle(): void { Peek.toggle() }
        function restore(): void { Peek.restoreAll() }
        function status(): string { return JSON.stringify({ active: Peek.active, workspaces: Peek.peeked }) }
    }

    //   used by ~/.local/bin/alchemos-game after each state change
    IpcHandler {
        target: "game"
        function refresh(): void { GameMode.refresh() }
        function toggle(): void { GameMode.toggle() }
    }

    //   qs ipc call orrinapp toggle   (Super + J, hypr/alchemos/binds.lua)
    IpcHandler {
        target: "orrinapp"
        function toggle(): void { OrrinLink.toggle() }
        function open(): void { OrrinLink.show() }
        function close(): void { OrrinLink.open = false }
    }

    //   used by ~/.config/orrin/core/control.py while Orrin works a window; stop = the kill switch
    IpcHandler {
        target: "orrincontrol"
        function frame(scr: string, x: int, y: int, w: int, h: int, label: string): void { OrrinControlState.show(scr, x, y, w, h, label) }
        function hide(): void { OrrinControlState.hide() }
        function stop(): void { OrrinControlState.stop() }
    }

    //   used by ~/.config/orrin/orrin.py (core/hud.py)
    IpcHandler {
        target: "orrin"
        function online(): string { return OrrinState.beat() }          // heartbeat; "resync" → Orrin sends restore
        function offline(): void { OrrinState.goOffline() }
        function restore(state: string): void { OrrinState.restore(state) }   // JSON from core/hud.py after a qs restart
        function listening(): void { OrrinState.startListening() }
        function transcript(text: string): void { OrrinState.setTranscript(text) }
        function thinking(): void { OrrinState.thinking() }
        function tool(label: string): void { OrrinState.tool(label) }       // "THEME → MARK III"
        function reply(text: string): void { OrrinState.setReply(text) }
        function confirm(text: string): void { OrrinState.confirm(text) }
        function followup(): void { OrrinState.followup() }
        function idle(): void { OrrinState.idle() }
        function toast(title: string, text: string): void { OrrinState.alert(title, text) }   // timers / reminders
        function error(reason: string, text: string): void { OrrinState.fail(reason, text) }  // "NO NETWORK", spoken line
        function note(label: string): void { OrrinState.note(label) }
        function speak(start: int, end: int, total: int, ms: int): void { OrrinState.speak(start, end, total, ms) }
        function speechDone(): void { OrrinState.speechDone() }
        function paused(on: string): void { OrrinState.paused = on === "true" }
        function heard(msg: string): void { OrrinState.heard(msg) }
        function status(msg: string): void { OrrinState.status(msg) }
        // persona: `qs ipc call orrin persona friday` switches the default (Orrin announces it in the new
        // voice); `qs ipc call orrin whois` → the active one. answering: sent by Orrin per exchange ("" = default)
        function persona(name: string): string { return OrrinState.setPersona(name) }
        function whois(): string { return OrrinState.persona }
        function answering(who: string): void { OrrinState.answering = who }
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
        //   qs ipc call theme presets   → ["AURUM","ARGENT",…] (the skin's built-ins + custom; Orrin validates against it)
        //   preset: the other skin's names work too (MARK III → IRON in ALCHEMOS, Skin.aliases)
        function presets(): string { return JSON.stringify(Theme.allPresets.map(p => p.name)) }
        function preset(name: string): string {
            const p = Theme.findPreset(name);
            if (!p) return "no preset " + name;
            Theme.applyPreset(p);
            return "preset " + p.name;
        }
    }
}
