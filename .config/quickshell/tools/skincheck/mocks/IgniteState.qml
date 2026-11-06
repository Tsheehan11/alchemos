pragma Singleton
import QtQuick
import Quickshell
Singleton { property bool playing: true; property bool busy: false; property bool moving: true; property string mode: "transmute"
            property real p: 0.5; property color color: Theme.primary; property string glyph: "☉"; property bool lite: false
            property string title: "TRANSITION"; property string sub: "SKINCHECK" }
