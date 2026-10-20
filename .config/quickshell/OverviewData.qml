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

    // Which workspaces this screen's carousel shows
    function workspacesFor(screen) {
        const existing = root.workspaces.filter(w => w.id > 0 && w.id <= 9);
        let ids;
        if (!Roles.docked) {
            ids = [1, 2, 3, 4, 5].concat(existing.map(w => w.id));      // laptop: everything
        } else {
            ids = Roles.baseWorkspaces(screen).concat(existing.filter(w => w.monitor === screen.name).map(w => w.id));
        }
        return Array.from(new Set(ids)).sort((a, b) => a - b);
    }

    function clientsOn(wsId) {
        return root.clients.filter(c => c.workspace && c.workspace.id === wsId && c.mapped !== false && !c.hidden);
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
