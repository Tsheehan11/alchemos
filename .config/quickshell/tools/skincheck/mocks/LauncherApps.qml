pragma Singleton
import QtQuick
import Quickshell
// nine apps in pairs (the last one alone), one not installed; no icons (the icon theme isn't fixed)
Singleton {
    readonly property var list: [
        ["ZEN", "WEB"], ["FIREFOX", "WEB"], ["CODE", "DEV"], ["KITTY", "DEV"], ["SPOTIFY", "MEDIA"], ["VLC", "MEDIA"],
        ["STEAM", "PLAY"], ["HEROIC", "PLAY"], ["FILES", "HOME"]
    ].map((a, i) => ({ id: "a" + i, name: a[0], group: a[1], icon: "", available: i !== 5 }))
    function launch(a) { return false; }
}
