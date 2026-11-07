// A number in the numeric face whose box doesn't jitter as it changes. With Style.tabular (the skin's
// numeric face has proportional figures, ALCHEMOS' Marcellus) the box is as wide as the text would be
// with every digit at its widest, and the text sits in it at `align` (natural spacing, nothing gapped);
// otherwise it is exactly one plain Text, so a mono face renders as before.
//   NumText { text: "10:08"; font.family: Style.fonts.numeric; font.pixelSize: 56; align: Text.AlignHCenter }
import QtQuick

Item {
    id: n
    property string text: ""
    property color color: Theme.text
    property font font: Qt.font({ family: Style.fonts.numeric, pixelSize: 13 })
    property int align: Text.AlignLeft
    FontMetrics { id: fm; font: n.font }
    readonly property string widest: {
        if (!Style.tabular) return "";
        let best = "0", w = 0;
        for (const d of "0123456789") { const a = fm.advanceWidth(d); if (a > w) { w = a; best = d; } }
        return best;
    }
    implicitWidth: Style.tabular ? Math.ceil(fm.advanceWidth(n.text.replace(/[0-9]/g, n.widest)) + n.text.length * n.font.letterSpacing) : t.implicitWidth
    implicitHeight: t.implicitHeight
    Text {
        id: t
        x: !Style.tabular || n.align === Text.AlignLeft ? 0 : n.align === Text.AlignRight ? n.width - implicitWidth : Math.round((n.width - implicitWidth) / 2)
        text: n.text; color: n.color; font: n.font
    }
}
