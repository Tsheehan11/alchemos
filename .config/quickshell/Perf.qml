// Performance governor for the ambient effects.
//
// 1. One shared clock (time) ticks at a capped frame rate (Settings → Appearance →
//    Effects), instead of every animation redrawing at the monitors' full 144 Hz.
// 2. Effects on a screen pause while that screen's workspace has windows on it
//    (you can't see the background then anyway), and resume when it's empty.
// 3. Everything stops while the session is locked (hyprlock covers it all), so the
//    lock screen and fingerprint prompt get the CPU/GPU right after a wake.
// 4. Combat mode hides the panels only on the screen(s) the game is on; the others
//    keep them in a lightweight form (lite: no animations, cava off, slow stats).
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root

    property real time: 0                  // seconds, advances at `fps`
    readonly property bool locked: LockState.doors === "closed"
    readonly property int fps: GameMode.quiet || locked ? 0 : PowerMode.saver ? Theme.cfg.batteryFps : Theme.cfg.effectsFps
    readonly property double t0: Date.now()

    Timer {
        interval: Math.max(16, Math.round(1000 / Math.max(1, root.fps)))
        running: root.fps > 0
        repeat: true
        onTriggered: root.time = (Date.now() - root.t0) / 1000
    }

    // Monitor name → true if its visible workspace has windows
    property var busy: ({})

    // Should ambient effects animate on this screen right now?
    function live(screen) {
        if (!screen || root.fps <= 0 || !Theme.cfg.animatedBg) return false;
        if (Theme.cfg.pauseBehindWindows && root.busy[screen.name] === true) return false;
        return true;
    }

    // Monitor name → true if a game window (GameMode.games) is on it
    property var gameScreens: ({})

    // Combat mode, panels kept on the other screens: they run without animations
    readonly property bool lite: GameMode.quiet && Theme.cfg.gameKeepPanels

    // Is this panel ("media" | "diag" | anything else) kept on non-game screens in combat mode?
    function keeps(panel) {
        if (!Theme.cfg.gameKeepPanels) return false;
        if (panel === "media") return Theme.cfg.gameKeepMedia;
        if (panel === "diag" || panel === "telemetry") return Theme.cfg.gameKeepDiag;
        return true;
    }

    // Combat telemetry (DiagPanel's combat layout) goes on the diagnostics screen, or on the
    // main screen when the game is on the diagnostics one; nowhere if both have the game
    readonly property string telemetryScreen: {
        if (!GameMode.quiet || !Theme.cfg.gameTelemetry || !root.keeps("diag") || !Roles.docked) return "";
        for (const role of ["diag", "main"]) {
            const s = Quickshell.screens.find(x => Roles.role(x) === role);
            if (s && root.gameScreens[s.name] !== true) return s.name;
        }
        return "";
    }

    // Combat telemetry stays up with windows (Discord…) open on its screen; it reserves its strip
    // so they tile beside it instead of covering it (DiagPanel)
    readonly property bool telemetryBeside: Theme.cfg.gameTelemetryBeside

    // Should the clock / diagnostics / audio deck hide on this screen right now?
    // (They peek through the gaps between tiled windows otherwise.)
    function hidden(screen, panel) {
        if (!screen) return false;
        if (GameMode.quiet && (!root.keeps(panel) || root.gameScreens[screen.name] === true)) return true;
        if (panel === "telemetry" && root.telemetryBeside) return false;
        return Theme.cfg.hideHudBehindWindows && root.busy[screen.name] === true;
    }

    Process {
        id: poll
        command: ["sh", "-c", "hyprctl monitors -j; echo '@@@'; hyprctl workspaces -j; echo '@@@'; hyprctl clients -j"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const parts = text.split("@@@");
                    const mons = JSON.parse(parts[0]);
                    const wss = JSON.parse(parts[1]);
                    const clients = JSON.parse(parts[2]);
                    const count = {};
                    for (const w of wss) count[w.id] = w.windows;
                    const b = {}, names = {}, g = {};
                    for (const m of mons) {
                        b[m.name] = (count[m.activeWorkspace.id] || 0) > 0;
                        names[m.id] = m.name;
                    }
                    for (const c of clients)
                        if (GameMode.games.indexOf(c.class) >= 0 && names[c.monitor]) g[names[c.monitor]] = true;
                    root.busy = b;
                    root.gameScreens = g;
                } catch (e) {}
            }
        }
    }
    Timer { id: debounce; interval: 150; onTriggered: poll.running = true }
    Timer { interval: 5000; running: !GameMode.quiet && !root.locked; repeat: true; triggeredOnStart: true; onTriggered: poll.running = true }

    // The daemon's game list changes before / after the window events
    Connections {
        target: GameMode
        function onGamesChanged() { debounce.restart(); }
        function onActiveChanged() { debounce.restart(); }
    }

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            const n = event.name;
            if (n.startsWith("openwindow") || n.startsWith("closewindow") || n.startsWith("movewindow")
                || n.startsWith("workspace") || n.startsWith("focusedmon") || n.startsWith("monitor"))
                debounce.restart();
        }
    }
}
