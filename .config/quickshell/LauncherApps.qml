pragma Singleton
// The radial launcher's apps. Saved in settings.json as Theme.cfg.launcherApps
// and edited from Settings → LAUNCHER.
//
// Each app: { id, name, icon, exec, desktopId?, group? }
//   desktopId  → launched with the desktop entry's execute(); icon "" uses the entry's icon
//   exec       → shell command run through Hyprland (survives a qs restart);
//                "@control" / "@lock" are built-in actions
//   icon       → theme icon name or file path ("" = none)
//   group      → branch label, shown when the app sits on the inner ring
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

Singleton {
    id: root

    // 16 apps = 8 branches. A 9th branch squeezes the inner ring until
    // neighbouring nodes touch (94 px nodes on a 172 px radius).
    readonly property int maxApps: 16
    readonly property string home: Quickshell.env("HOME")

    // ── Defaults (also the first-run seed) ──────
    readonly property string codeId: "com.microsoft.VSCode"
    function defaults() {
        const list = [
            { id: "seed-claude",  name: "CLAUDE",  icon: "", exec: "zen-browser --new-window https://claude.ai", group: "AI" },
            { id: "seed-cc",      name: "CODE",    icon: "", exec: "kitty -e claude" },
            { id: "seed-web",     name: "WEB",     icon: "", exec: "zen-browser", group: "NET" },
            { id: "seed-discord", name: "DISCORD", icon: "", exec: "discord" },
            { id: "seed-music",   name: "MUSIC",   icon: "", exec: "spotify-launcher", group: "MEDIA" },
            { id: "seed-games",   name: "GAMES",   icon: "", exec: "steam" }
        ];
        if (DesktopEntries.byId(codeId))
            list.push({ id: "seed-vscode", name: "VS CODE", icon: "", exec: "code", group: "DEV" },
                      { id: "seed-hud",    name: "HUD",     icon: "", exec: "code ~/.config/quickshell" });
        list.push({ id: "seed-term",    name: "TERM",    icon: "", exec: "kitty", group: "SYS" },
                  { id: "seed-files",   name: "FILES",   icon: "", exec: "dolphin" },
                  { id: "seed-control", name: "CONTROL", icon: "", exec: "@control", group: "CTRL" },
                  { id: "seed-lock",    name: "LOCK",    icon: "", exec: "@lock" });
        return list;
    }

    // First run: once settings.json is read and the app list is known, save the defaults.
    // An empty list never happens otherwise — Settings won't remove the last app.
    readonly property bool ready: Theme.loaded && DesktopEntries.applications.values.length > 0
    onReadyChanged: seedIfNeeded()
    Connections {
        target: Theme
        function onLoadedChanged() { root.seedIfNeeded(); }
    }
    function seedIfNeeded() {
        if (ready && !(Theme.cfg.launcherApps && Theme.cfg.launcherApps.length)) Theme.cfg.launcherApps = defaults();
    }

    // ── Resolved list (what the launcher draws) ─
    readonly property var raw: (Theme.cfg.launcherApps && Theme.cfg.launcherApps.length) ? Theme.cfg.launcherApps : defaults()
    readonly property var list: {
        DesktopEntries.applications.values;      // re-resolve when apps are installed / removed
        const ok = execOk;
        return raw.slice(0, maxApps).map(a => resolve(a, ok));
    }

    function iconSource(name) {
        if (!name) return "";
        if (name.startsWith("~/")) name = home + name.slice(1);
        if (name.startsWith("/")) return "file://" + name;
        return Quickshell.iconPath(name, true);
    }
    function exeOf(cmd) {
        const words = (cmd || "").trim().split(/\s+/).filter(w => !/^\w+=/.test(w));   // skip FOO=bar
        const w = words[0] || "";
        return w.startsWith("~/") ? home + w.slice(1) : w;
    }
    function kindOf(a) {
        if (a.desktopId) return "desktop";
        return (a.exec || "").startsWith("@") ? "action" : "command";
    }
    function resolve(a, ok) {
        const kind = kindOf(a);
        const entry = kind === "desktop" ? DesktopEntries.byId(a.desktopId) : null;
        return {
            id: a.id, name: a.name || "?", group: a.group || "", exec: a.exec || "", desktopId: a.desktopId || "",
            iconName: a.icon || "", kind: kind, entry: entry,
            icon: iconSource(a.icon || (entry ? entry.icon : "")),
            available: kind === "desktop" ? entry !== null
                     : kind === "action" ? (a.exec === "@control" || a.exec === "@lock")
                     : ok[exeOf(a.exec)] !== false            // unknown until checked → assume fine
        };
    }

    // ── Launching ───────────────────────────────
    // Returns true when the launcher should close.
    function launch(app) {
        if (!app || !app.available) return false;
        if (app.exec === "@control") { LauncherState.openControl(); return false; }
        if (app.exec === "@lock") { LockState.requestLock(); return false; }
        if (app.entry) app.entry.execute();
        else Hyprland.dispatch("exec " + app.exec);
        return true;
    }

    // ── Is each command installed? ──────────────
    // execOk: executable → true / false. Re-checked when the list changes
    // and each time the launcher opens.
    property var execOk: ({})
    function checkCommands() {
        const exes = [...new Set(raw.filter(a => kindOf(a) === "command").map(a => exeOf(a.exec)).filter(e => e))];
        if (exes.length === 0) return;
        if (check.running) { check.again = true; return; }
        check.exes = exes;
        check.command = ["sh", "-c", 'for c; do command -v -- "$c" >/dev/null 2>&1 && printf 1 || printf 0; done', "sh"].concat(exes);
        check.running = true;
    }
    onRawChanged: checkCommands()
    Connections {
        target: LauncherState
        function onOpenChanged() { if (LauncherState.open) root.checkCommands(); }
    }
    Process {
        id: check
        property var exes: []
        property bool again: false
        stdout: StdioCollector {
            onStreamFinished: {
                const ok = {};
                check.exes.forEach((e, i) => ok[e] = text.charAt(i) === "1");
                root.execOk = ok;
            }
        }
        onExited: if (again) { again = false; root.checkCommands(); }
    }
    Component.onCompleted: checkCommands()

    // ── Editing (Settings → LAUNCHER) ───────────
    // Every change saves a fresh array, so JsonAdapter writes settings.json
    // and the launcher redraws immediately.
    function save(list) { Theme.cfg.launcherApps = list; }
    function copy() { return raw.map(a => Object.assign({}, a)); }
    function newId() { return "app-" + Date.now().toString(36) + Math.floor(Math.random() * 1e4).toString(36); }
    readonly property bool full: raw.length >= maxApps

    function addDesktop(entry) {
        if (full || !entry) return;
        const name = (entry.name || entry.id).toUpperCase();
        save(copy().concat([{ id: newId(), name: name.length > 12 ? name.slice(0, 12) : name, icon: "", exec: "", desktopId: entry.id }]));
    }
    function addCommand(name, exec, icon) {
        if (full || !exec.trim()) return;
        save(copy().concat([{ id: newId(), name: (name.trim() || exeOf(exec).split("/").pop()).toUpperCase(), icon: icon.trim(), exec: exec.trim() }]));
    }
    function update(id, fields) {
        save(copy().map(a => a.id === id ? Object.assign(a, fields) : a));
    }
    function remove(id) {
        if (raw.length <= 1) return;
        save(copy().filter(a => a.id !== id));
    }
    function move(id, delta) {
        const l = copy();
        const i = l.findIndex(a => a.id === id), j = i + delta;
        if (i < 0 || j < 0 || j >= l.length) return;
        const t = l[i]; l[i] = l[j]; l[j] = t;
        save(l);
    }
    function reset() { save(defaults()); }
}
