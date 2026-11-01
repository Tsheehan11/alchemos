// Shared state for the radial launcher and the app search.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property bool open: false          // radial wheel
    property bool searchOpen: false    // app search
    property bool controlOpen: false   // control center
    property bool settingsOpen: false  // settings screen
    property bool overviewOpen: false  // workspace overview
    property bool powerOpen: false     // power menu
    property string settingsTab: "NETWORK"
    property string initialQuery: ""
    property real cx: 0                // cursor position (global layout coords)
    property real cy: 0

    // Radial: grab the cursor position first, then open around it
    function toggle() {
        if (root.open) { root.open = false; return; }
        root.searchOpen = false;
        cursorProc.running = true;
    }

    function openSearch(q) {
        root.open = false;
        root.initialQuery = q || "";
        root.searchOpen = true;
    }

    function toggleSearch() {
        if (root.searchOpen) root.searchOpen = false;
        else root.openSearch("");
    }

    function openControl() {
        root.open = false;
        root.searchOpen = false;
        root.controlOpen = true;
    }

    function toggleControl() {
        if (root.controlOpen) root.controlOpen = false;
        else root.openControl();
    }

    function openSettings(tab) {
        root.open = false;
        root.searchOpen = false;
        root.controlOpen = false;
        if (tab) root.settingsTab = tab;
        root.settingsOpen = true;
    }

    function toggleSettings() {
        if (root.settingsOpen) root.settingsOpen = false;
        else root.openSettings("");
    }

    function toggleOverview() {
        if (root.overviewOpen) { root.overviewOpen = false; return; }
        root.open = false; root.searchOpen = false; root.controlOpen = false; root.settingsOpen = false;
        OverviewData.refresh(true);  // also logs the opening (journal, stark-hud)
        overviewDelay.restart();     // give the window snapshot a moment to arrive
    }
    Timer { id: overviewDelay; interval: 60; onTriggered: root.overviewOpen = true }

    function togglePower() {
        if (root.powerOpen) { root.powerOpen = false; return; }
        root.open = false; root.searchOpen = false; root.controlOpen = false; root.settingsOpen = false; root.overviewOpen = false;
        root.powerOpen = true;
    }

    function closeAll() {
        root.powerOpen = false;
        root.overviewOpen = false;
        root.open = false;
        root.searchOpen = false;
        root.controlOpen = false;
        root.settingsOpen = false;
    }

    Process {
        id: cursorProc
        command: ["hyprctl", "cursorpos", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const p = JSON.parse(text);
                    root.cx = p.x;
                    root.cy = p.y;
                } catch (e) {}
                root.open = true;
            }
        }
    }
}
