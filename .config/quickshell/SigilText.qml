// A glyph (☉ ☽ ♂ ♀ ☿ ♄ …): the HUD's mono font has none of them, so a symbol face first.
// Noto Sans Symbols has ☽♂♀☿♄, Noto Sans Symbols 2 has ☉ (left to Qt, ☉ came from a CJK face).
// (No font.families in this Qt, so the face is picked from the text; other letters fall back as usual.)
// glow: 0..1, a soft halo in the text colour.
import QtQuick
import QtQuick.Effects

Text {
    id: t
    property real glow: 0
    font.family: text.indexOf("☉") >= 0 ? "Noto Sans Symbols 2" : "Noto Sans Symbols"
    renderType: Text.QtRendering
    layer.enabled: glow > 0.02
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: t.color
        shadowOpacity: Math.min(1, t.glow)
        shadowBlur: 0.8
        blurMax: 24
        shadowHorizontalOffset: 0
        shadowVerticalOffset: 0
        autoPaddingEnabled: true
    }
}
