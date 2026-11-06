pragma Singleton
import QtQuick
import Quickshell
Singleton { property real time: 0; property int fps: 24; property bool lite: false; property bool locked: false
            function live(s) { return false; } function hidden(s, p) { return false; } function keeps(p) { return true; } }
