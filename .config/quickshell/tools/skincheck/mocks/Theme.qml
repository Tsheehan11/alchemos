pragma Singleton
// skincheck mock: the real Theme's colour API with fixed values and no side effects (no settings
// file, no pushes). cfg.skin comes from SKINCHECK_SKIN; colours from that skin's first preset.
import QtQuick
import Quickshell
Singleton {
    id: root
    property bool loaded: true
    property var cfg: ({ skin: Quickshell.env("SKINCHECK_SKIN") || "alchemos", preset: "", reactorScale: 1.0, clock24: true,
                         greetName: "TREVOR", panelOpacity: 0.85, skinUnlocked: true, customPresets: [], jarvisPersona: "jarvis", showGrid: true })
    property int presetIndex: 0         // the gallery picks another preset for a render or two
    readonly property var preset: presetIndex < 0 ? customs[0] : (Skin.presets && Skin.presets.length > presetIndex) ? Skin.presets[presetIndex] : ({ primary: "#4fd8ff", secondary: "#ffb347", background: "#05090f" })
    readonly property color primary: preset.primary
    readonly property color secondary: preset.secondary
    readonly property color bg: preset.background
    function mix(a, b, t) { a = Qt.darker(a, 1.0); b = Qt.darker(b, 1.0); return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, 1); }
    readonly property color text: mix(primary, "#ffffff", 0.88)
    readonly property color textSoft: mix(primary, "#ffffff", 0.7)
    readonly property color dim: Qt.hsla(primary.hslHue, Math.min(1, primary.hslSaturation) * 0.38, 0.68, 1)
    readonly property color faint: Qt.hsla(primary.hslHue, Math.min(1, primary.hslSaturation) * 0.25, 0.42, 1)
    readonly property color deep: mix(bg, primary, 0.09)
    readonly property real panelAlpha: 0.85
    function p(a)  { return Qt.rgba(primary.r, primary.g, primary.b, a); }
    function s(a)  { return Qt.rgba(secondary.r, secondary.g, secondary.b, a); }
    function d(a)  { return Qt.rgba(deep.r, deep.g, deep.b, a); }
    function back(a) { return Qt.rgba(bg.r, bg.g, bg.b, a); }
    function css(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")"; }
    function pc(a)  { return css(primary, a); }
    function sc(a)  { return css(secondary, a); }
    function lc(a)  { return css(mix(primary, "#ffffff", 0.6), a); }
    function slc(a) { return css(mix(secondary, "#ffffff", 0.5), a); }
    function luma(c) {
        const f = v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
    }
    function hex(c) { return c.toString().replace("#", "").slice(-6); }
    // one saved custom preset with a sign, in use in the "custom" render (presetIndex -1)
    readonly property var customs: [{ name: "BISMUTH", glyph: "🜾", primary: "#ff6bd6", secondary: "#7fe0ff", background: "#06080b", custom: true }]
    readonly property var customSigns: (Skin.glyphs.ring || []).length ? ["🜾"] : []
    readonly property string activeName: preset.name || "CUSTOM"
    readonly property string activeSign: presetIndex < 0 ? "🜾" : (preset.glyph || "")
    function signFor(n) { return n === "BISMUTH" ? "🜾" : Skin.glyphFor(n); }
    function switchSkin(from, to) {}
    signal presetApplied(var preset)
}
