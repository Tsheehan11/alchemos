// Ambient lights — the Govee strip driven by ~/.local/bin/stark-govee (daemon
// started from hypr/stark/autostart.lua). The mode lives in ~/.config/govee/config.json.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property string mode: "auto"          // auto | music | theme | off (| manual, set from the CLI)
    readonly property var modes: ["auto", "music", "theme", "off"]
    property real animSpeed: 1.0          // segment animation speed multiplier (0.5 - 2.0)

    function setMode(m) {
        root.mode = m;                    // show it right away; the file watch confirms
        Quickshell.execDetached(["stark-govee", "mode", m]);
    }
    function setSpeed(v) {
        root.animSpeed = v;
        Quickshell.execDetached(["stark-govee", "speed", String(v)]);
    }
    function event(name) { Quickshell.execDetached(["stark-govee", "event", name]); }

    FileView {
        id: cfgFile
        path: Quickshell.env("HOME") + "/.config/govee/config.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            try {
                const c = JSON.parse(text());
                if (c.mode) root.mode = c.mode;
                if (c.anim_speed) root.animSpeed = c.anim_speed;
            } catch (e) {}
        }
    }
}
