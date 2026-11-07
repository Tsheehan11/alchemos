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
    readonly property string mono: pick("mono", "JetBrainsMono Nerd Font")       // the base face (every role's default)
    readonly property string display: pick("display", mono)                        // panel / section headings
    // Font roles: every Text names one (Style.fonts.<role>; tools/fontcheck.py checks), so nothing falls
    // back to whatever face the system picks. A skin sets them under style.fonts; any it leaves out is
    // the base face (display: the display token), so the base look is all one mono face.
    //   display  headings, titles            numeric  clocks, big numbers, percentages
    //   label    short caps labels, buttons   body     running text, names, descriptions
    //   mono     data, code, hex, paths       glyph    a lone mark or arrow (♪ ▾ ◈): the face Qt fell back to
    //   signs    featured signs (☉ ☽ ♂ ♀ ☿ ♄, alchemical 🜁…; SigilText)     signs2  …☉ (Symbols has no ☉)
    //   field    the lock screen's password field (hyprlock's own default: Sans)
    readonly property var fonts: {
        const f = pick("fonts", {});
        return {
            display: f.display || display,
            numeric: f.numeric || mono,
            label: f.label || mono,
            body: f.body || mono,
            mono: f.mono || mono,
            glyph: f.glyph || "Noto Sans",
            signs: f.signs || "Noto Sans Symbols",
            signs2: f.signs2 || "Noto Sans Symbols 2",
            field: f.field || "Sans"
        };
    }
    readonly property string symbols: fonts.signs
    // the numeric face has proportional figures: NumText lays digits in fixed cells so numbers don't jitter
    readonly property bool tabular: pick("tabular", false)
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

    // ── Numerals and icons ──
    readonly property string numerals: pick("numerals", "arabic")    // arabic | roman: workspaces, launcher keys, the carousel
    function numeral(n) {
        n = Math.floor(Number(n));
        if (numerals !== "roman" || !(n > 0) || n > 3999) return String(n);
        const t = [[1000, "M"], [900, "CM"], [500, "D"], [400, "CD"], [100, "C"], [90, "XC"], [50, "L"], [40, "XL"], [10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
        let out = "";
        for (const [v, r] of t) while (n >= v) { out += r; n -= v; }
        return out;
    }
    // name → an SVG in the skin's folder (SkinIcon.qml recolours it). No entry = the base's text / glyph,
    // drawn as it always was. Names: cpu gpu ram temp battery wifi wifi-off bluetooth volume volume-mute
    // mic mic-off vpn bell power
    readonly property var icons: pick("icons", ({}))
    function hasIcon(name) { return typeof icons[name] === "string" && icons[name] !== ""; }
    // extra status icons in the bar's right end, in order (wifi bluetooth volume mic bell); [] = none
    readonly property var barIndicators: pick("barIndicators", [])

    // ── Lock screen ──
    // The default lock scene's great circle (VaultScene) on a screen h px tall; its outermost ring is
    // sealRim px further out. hyprlock's text keeps clear of it through lockLayout.
    function sealRadius(h) { return Math.min(h / 2 * 0.86, 330); }
    readonly property int sealRim: 18
    // Where hyprlock puts its text on the main screen: y offsets from the screen's centre (up = +) for
    // title, clock, date, field (the password box's centre) and prompt (the fingerprint line). A number
    // is fixed; { "outside": n } is n px beyond the seal's outer ring, above (n > 0) or below (n < 0).
    // battery: [x, y] from the bottom-right corner (hyprlock's own sign: x < 0 = in from the right).
    readonly property var lockLayout: Object.assign({ title: 290, clock: 16, date: -34, field: -280, prompt: -335, battery: [-30, 20] },
                                                     pick("lockLayout", {}))
    function lockY(key, h) {
        const v = lockLayout[key];
        if (typeof v === "number") return Math.round(v);
        const rim = sealRadius(h) + sealRim, n = Number(v && v.outside) || 0;
        return Math.round(n >= 0 ? rim + n : -(rim - n));
    }

    // the background's darkness decides which grain strength applies
    readonly property real grainNow: Theme.luma(Theme.bg) < 0.004 ? grainDark : grain
    readonly property bool engraved: frame === "engraved"
}
