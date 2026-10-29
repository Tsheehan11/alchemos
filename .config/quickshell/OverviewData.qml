// Snapshot of monitors, workspaces and windows for the workspace overview.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root

    property var monitors: []
    property var workspaces: []
    property var clients: []

    function refresh() { proc.running = true; }

    Process {
        id: proc
        command: ["sh", "-c", "hyprctl monitors -j; echo '@@@'; hyprctl workspaces -j; echo '@@@'; hyprctl clients -j"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const p = text.split("@@@");
                    root.monitors = JSON.parse(p[0]);
                    root.workspaces = JSON.parse(p[1]);
                    root.clients = JSON.parse(p[2]);
                } catch (e) {}
            }
        }
    }

    function monitorByName(n) { return root.monitors.find(m => m.name === n) || null; }
    function monitorById(id) { return root.monitors.find(m => m.id === id) || null; }
    function activeOn(name) { const m = monitorByName(name); return m ? m.activeWorkspace.id : -1; }

    // Peek (Super + D) keeps a workspace's windows in special:peek<id>, and Hyprland drops
    // the emptied workspace once you leave it. Here those windows still belong to <id>:
    // its card stays on the ring with them (marked PEEK). Other specials stay out.
    function homeId(ws) { return !ws ? -1 : ws.id > 0 ? ws.id : Peek.homeOf(ws.name); }
    function isPeeked(wsId) { return root.workspaces.some(w => Peek.homeOf(w.name) === wsId); }

    // Which workspaces this screen's carousel shows
    function workspacesFor(screen) {
        const existing = root.workspaces.map(w => ({ id: root.homeId(w), monitor: w.monitor }))
                                        .filter(w => w.id > 0 && w.id <= 9);
        let ids;
        if (!Roles.docked) {
            ids = [1, 2, 3, 4, 5].concat(existing.map(w => w.id));      // laptop: everything
        } else {
            ids = Roles.baseWorkspaces(screen).concat(existing.filter(w => w.monitor === screen.name).map(w => w.id));
        }
        return Array.from(new Set(ids)).sort((a, b) => a - b);
    }

    function clientsOn(wsId) {
        return root.clients.filter(c => root.homeId(c.workspace) === wsId && c.mapped !== false && !c.hidden);
    }

    // Live Wayland handle for a window (used for the preview thumbnails)
    function toplevelFor(address) {
        const a = String(address || "").replace(/^0x/, "");
        const list = Hyprland.toplevels ? Hyprland.toplevels.values : [];
        const t = list.find(t => String(t.address || "").replace(/^0x/, "") === a);
        return t && t.wayland ? t.wayland : null;
    }

    function iconFor(cls) {
        if (!cls) return "";
        let e = null;
        try {
            e = DesktopEntries.heuristicLookup ? DesktopEntries.heuristicLookup(cls) : DesktopEntries.byId(cls);
        } catch (err) {}
        return e ? Quickshell.iconPath(e.icon, true) : Quickshell.iconPath(cls.toLowerCase(), true);
    }
}
