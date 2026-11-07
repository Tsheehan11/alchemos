pragma Singleton
import QtQuick
import Quickshell
Singleton { property bool docked: true; function role(s) { return "main"; } function shows(s) { return "clock"; } function baseWorkspaces(s) { return [1, 2, 3]; }
            readonly property string laptopName: "eDP-1" }
