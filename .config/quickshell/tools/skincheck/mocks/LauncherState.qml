pragma Singleton
import QtQuick
import Quickshell
Singleton {
    property bool open: false; property bool searchOpen: false; property bool controlOpen: false
    property bool settingsOpen: false; property bool overviewOpen: false; property bool powerOpen: false
    property real cx: 800; property real cy: 470
    function toggle() {} function openSearch(q) {} function toggleControl() {} function openSettings(t) {}
    function togglePower() {} function closeAll() {} function toggleOverview() {}
}
