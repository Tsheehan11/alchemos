pragma Singleton
import QtQuick
import Quickshell
Singleton {
    readonly property var look: Skin.persona("jarvis")
    property bool online: true; property bool toggleOn: true; property bool laptopMode: false; property bool docked: true
    property bool speaking: false; property bool listening: false; property string phase: "idle"
    readonly property string name: look.name
    readonly property string glyph: look.glyph
    readonly property string glyphIdle: look.idle
    readonly property string glyphStarting: look.starting
    readonly property color accent: look.accent ? look.accent : Theme.primary
    readonly property string assistant: look.name
    readonly property string stateLabel: "ON"
    function toggle() {}
}
