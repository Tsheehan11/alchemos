pragma Singleton
import QtQuick
import Quickshell
// liveAll: the gallery's "live" renders (a frozen moment of the animated look, at a fixed time)
Singleton { property real time: 0; property int fps: 24; property bool lite: false; property bool locked: false; property bool liveAll: false
            function live(s) { return liveAll; } function hidden(s, p) { return false; } function keeps(p) { return true; } }
