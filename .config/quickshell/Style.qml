pragma Singleton
// Style tokens: how shared components look, from the skin (skin.json "style"). Every token here has a
// base value that is today's hologram look, so a skin that sets none looks exactly like that.
// Components read Style.x; nothing outside this file and skins/ names a skin. See docs/SKINS.md.
import QtQuick
import Quickshell

Singleton {
    id: root
    readonly property var t: Skin.style || ({})
    function pick(key, base) { return t[key] !== undefined && t[key] !== null ? t[key] : base; }

    // ── Type ──
    readonly property string mono: pick("mono", "JetBrainsMono Nerd Font")       // data, labels, body text
    readonly property string display: pick("display", mono)                        // panel / section headings
    readonly property bool displayCaps: pick("displayCaps", false)                 // headings in small caps (as typed) vs as is
    readonly property real displayScale: pick("displayScale", 1)                   // heading size multiplier

    // ── Surfaces ──
    readonly property string frame: pick("frame", "holo")           // holo: corner brackets | engraved: double line, notched corners
    readonly property string texture: pick("texture", "holo")       // holo: scanlines / grid | grain | none
    readonly property real grain: pick("grain", 0)                  // grain strength 0..1 (texture "grain")
    readonly property real grainDark: pick("grainDark", grain)      // …on very dark backgrounds (it shows more there)
    readonly property real glow: pick("glow", 1)                    // halo / glow multiplier
    readonly property var corners: pick("corners", [])              // glyphs in the four corner notches (TL, TR, BL, BR); [] = plain notches
    readonly property string divider: pick("divider", "")           // glyph at a section divider's centre ("" = a plain rule)
    readonly property string gauge: pick("gauge", "ring")           // ring | astrolabe
    readonly property bool metalRule: pick("metalRule", false)      // a brushed-metal rule beside headings
    readonly property real surface: pick("surface", 0)              // 0 = hologram glass, 1 = stone / ink plate (opacity unchanged)

    // the background's darkness decides which grain strength applies
    readonly property real grainNow: Theme.luma(Theme.bg) < 0.004 ? grainDark : grain
    readonly property bool engraved: frame === "engraved"
}
