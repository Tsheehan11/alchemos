// Small line graph for history arrays (last 60 samples).
import QtQuick

Canvas {
    id: g
    property var values: []
    property real maxValue: 1          // 0 = scale to the data automatically
    property string lineColor: Theme.primary
    property string fillColor: Theme.pc(0.12)
    property int slots: 60

    onValuesChanged: requestPaint()
    onWidthChanged: requestPaint()
    onLineColorChanged: requestPaint()
    onFillColorChanged: requestPaint()

    onPaint: {
        const ctx = getContext("2d");
        ctx.clearRect(0, 0, width, height);
        const v = values || [];
        if (v.length < 2) return;

        const mx = maxValue > 0 ? maxValue : Math.max(1, Math.max.apply(null, v) * 1.15);
        const dx = width / (slots - 1);
        const off = slots - v.length;
        const yOf = val => height - Math.min(1, val / mx) * (height - 2) - 1;

        ctx.beginPath();
        for (let i = 0; i < v.length; i++) {
            const x = (off + i) * dx, y = yOf(v[i]);
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = lineColor;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.lineTo((off + v.length - 1) * dx, height);
        ctx.lineTo(off * dx, height);
        ctx.closePath();
        ctx.fillStyle = fillColor;
        ctx.fill();
    }
}
