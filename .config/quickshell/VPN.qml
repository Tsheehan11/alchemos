pragma Singleton
// VPN — ~/.local/bin/stark-vpn does the work, for every provider listed in
// ~/.config/stark-vpn/providers.json (Proton VPN; a school openconnect slot).
// The HUD keeps `stark-vpn watch` running, which wakes only on NetworkManager
// events and rewrites $XDG_RUNTIME_DIR/stark-vpn/state.json; this follows that
// file, so there's no polling. One VPN at a time: connecting one drops the other.
// Off at login: Proton's NM connection is in-memory only and nothing autoconnects.
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property var providers: []            // [{ id, name, label, enabled, state, server, country, city, killSwitch, hasKillSwitch, error }]
    property string active: ""            // provider connected / connecting / blocked, "" = none
    // Provider the tile / Settings act on: the active one, else the last picked
    readonly property string selected: active !== "" ? active
        : (providers.some(p => p.id === Theme.cfg.vpnProvider) ? Theme.cfg.vpnProvider : (providers[0] ? providers[0].id : ""))
    readonly property var current: providers.find(p => p.id === selected) || ({ id: "", name: "VPN", state: "disabled" })
    readonly property string state: current.state || "disconnected"      // disconnected | connecting | connected | disconnecting | disabled
    readonly property bool connected: state === "connected"
    readonly property bool busy: state === "connecting" || state === "disconnecting"
    // Tunnel dropped with the kill switch on: no internet until toggle / disconnect
    readonly property bool blocked: state === "blocked"
    readonly property bool killSwitch: !!current.killSwitch

    function get(id) { return providers.find(p => p.id === id); }
    function pick(id) { if (get(id)) Theme.cfg.vpnProvider = id; }
    function run(args) {
        // Show the phase straight away; the state file catches up as NM moves
        Quickshell.execDetached(["stark-vpn"].concat(args));
    }
    function toggle(id) { id = id || root.selected; pick(id); run(["toggle", id]); }
    function connect(id) { id = id || root.selected; pick(id); run(["connect", id]); }
    function disconnect() { run(["disconnect"]); }
    function setKillSwitch(on) { run(["killswitch", on ? "on" : "off"]); }
    // "CANADA · CA-FREE#32" for the tile / bar
    function where(p) {
        p = p || root.current;
        return [p.country || "", p.server || ""].filter(x => x).join(" · ");
    }

    FileView {
        id: file
        path: (Quickshell.env("XDG_RUNTIME_DIR") || "/run/user/1000") + "/stark-vpn/state.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: root.read(text())
    }
    function read(t) {
        let s;
        try { s = JSON.parse(t); } catch (e) { return; }
        root.providers = s.providers || [];
        root.active = s.active || "";
    }

    // Event-driven status: blocks on `nmcli monitor`, restarted if it ever exits
    Process {
        id: watcher
        command: ["stark-vpn", "watch"]
        running: true
        // Each line = "state file rewritten"; the file stays the one source of truth,
        // so a line can't land after (and undo) a newer write from a connect / disconnect
        stdout: SplitParser { onRead: file.reload() }
        onExited: restart.start()
    }
    Timer { id: restart; interval: 5000; onTriggered: { watcher.running = true; file.reload(); } }
    // providers.json edits (e.g. enabling the school VPN) show up without a HUD restart
    FileView {
        path: Quickshell.env("HOME") + "/.config/stark-vpn/providers.json"
        watchChanges: true
        onFileChanged: Quickshell.execDetached(["stark-vpn", "status"])
    }
}
