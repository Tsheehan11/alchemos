pragma Singleton
// Preset auto-namer: suggests a name and glyph for a new custom preset from its colours, using the skin's
// namer (skin.json "namer": { entries: [{ name, glyph, h, s, l }], compound, joiner }; the base one names
// plain colours). Settings → APPEARANCE → SAVE AS PRESET offers the first suggestion, editable; ↻ cycles.
//
//   suggest(primary, secondary, taken) → [{ name, glyph }], best first, none of them in `taken`
// Nearest entry by hue / saturation / lightness (hue counts less as colours grey out). With compound, an
// accent whose own nearest entry is clearly different (another hue, both saturated) makes "A-B" when that
// fits the 14-character limit. Names in use get the next candidate, then a numeral (… II, III).
import QtQuick
import Quickshell

Singleton {
    id: root

    // Base namer: plain colour names (skins/_template uses the same)
    readonly property var baseNamer: ({
        compound: false, joiner: " ",
        entries: [
            { name: "RED", h: 2, s: 0.8, l: 0.52 }, { name: "ORANGE", h: 26, s: 0.85, l: 0.55 },
            { name: "AMBER", h: 40, s: 0.9, l: 0.55 }, { name: "YELLOW", h: 55, s: 0.9, l: 0.6 },
            { name: "LIME", h: 85, s: 0.75, l: 0.55 }, { name: "GREEN", h: 125, s: 0.6, l: 0.48 },
            { name: "TEAL", h: 172, s: 0.6, l: 0.45 }, { name: "CYAN", h: 190, s: 0.75, l: 0.55 },
            { name: "SKY", h: 205, s: 0.7, l: 0.68 }, { name: "BLUE", h: 220, s: 0.75, l: 0.52 },
            { name: "INDIGO", h: 245, s: 0.6, l: 0.45 }, { name: "VIOLET", h: 270, s: 0.6, l: 0.6 },
            { name: "MAGENTA", h: 300, s: 0.75, l: 0.55 }, { name: "PINK", h: 330, s: 0.8, l: 0.68 },
            { name: "ROSE", h: 345, s: 0.7, l: 0.58 }, { name: "SILVER", h: 210, s: 0.1, l: 0.75 },
            { name: "SLATE", h: 215, s: 0.15, l: 0.45 }, { name: "WHITE", h: 0, s: 0, l: 0.95 },
            { name: "PALE GOLD", h: 46, s: 0.5, l: 0.75 }, { name: "CRIMSON", h: 350, s: 0.75, l: 0.38 }
        ]
    })
    readonly property var namer: Skin.data.namer && Array.isArray(Skin.data.namer.entries) && Skin.data.namer.entries.length
                                 ? Skin.data.namer : baseNamer

    function hsl(c) {
        c = Qt.darker(c, 1.0);                       // a "#rrggbb" string → color
        return { h: Math.max(0, c.hslHue) * 360, s: Math.max(0, c.hslSaturation), l: c.hslLightness };
    }
    function dist(a, e) {
        const dh = Math.abs(((a.h - e.h) % 360 + 540) % 360 - 180) / 180;    // 0..1
        const w = Math.min(a.s, e.s) * 8;                                       // hue matters less when grey
        return w * dh * dh + 0.4 * (a.s - e.s) * (a.s - e.s) + 1.6 * (a.l - e.l) * (a.l - e.l);
    }
    function ranked(c) {
        const a = hsl(c);
        return namer.entries.map(e => ({ e: e, d: dist(a, e) })).sort((x, y) => x.d - y.d).map(x => x.e);
    }
    readonly property var numerals: ["II", "III", "IV", "V", "VI", "VII", "VIII", "IX"]

    function suggest(primary, secondary, taken) {
        const used = new Set((taken || []).map(n => String(n).toUpperCase()));
        const out = [];
        const add = (name, glyph) => {
            name = String(name).toUpperCase();
            if (name.length > 14 || used.has(name) || out.some(o => o.name === name)) return;
            out.push({ name: name, glyph: glyph || "" });
        };
        const ps = ranked(primary);
        const p = hsl(primary), s = secondary ? hsl(secondary) : null;
        const distinct = s && namer.compound && p.s > 0.25 && s.s > 0.25
                         && Math.abs(((p.h - s.h) % 360 + 540) % 360 - 180) > 40;
        const ss = distinct ? ranked(secondary) : [];
        for (let i = 0; i < Math.min(4, ps.length); i++) {
            if (distinct) {
                for (let j = 0; j < Math.min(2, ss.length); j++)
                    if (ss[j].name !== ps[i].name) add(ps[i].name + (namer.joiner || "-") + ss[j].name, ps[i].glyph);
            }
            add(ps[i].name, ps[i].glyph);
        }
        for (const n of numerals) {                  // every candidate taken: the nearest with a numeral
            if (out.length >= 4) break;
            add(ps[0].name + " " + n, ps[0].glyph);
        }
        return out;
    }
}
