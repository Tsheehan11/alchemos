pragma Singleton
import QtQuick
import Quickshell
Singleton {
    property bool connected: true; property bool busy: false; property bool blocked: false
    property string state: "connected"; property string selected: "proton"; property string active: "proton"
    property var current: ({ name: "PROTON", countryCode: "CH", error: "" })
    property var providers: [{ id: "proton", name: "PROTON", enabled: true }, { id: "mullvad", name: "MULLVAD", enabled: true }]
    function where() { return "ZURICH"; } function toggle(p) {} function pick(p) {}
}
