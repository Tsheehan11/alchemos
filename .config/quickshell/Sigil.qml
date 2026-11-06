// Engraved inscription, drawn in order: a triangle in a circle of `radius`, its incircle (radius / 2),
// a square in a circle of squareRadius. Each part can be left out.
// draw: 0..1 traces it in that order (the "inscribes itself" animation); 1 = all of it.
// A still sigil paints once and only repaints when something here changes (turn it with rotation).
import QtQuick

Canvas {
    id: c
    property real radius: 100
    property real draw: 1
    property color color: Theme.primary
    property real lineWidth: 1.2
    property bool triangle: true
    property bool incircle: true
    property bool square: true
    property real squareRadius: radius / 2
    readonly property real reach: Math.max(radius, squareRadius)
    width: reach * 2 + 8; height: width

    onDrawChanged: requestPaint()
    onColorChanged: requestPaint()
    onRadiusChanged: requestPaint()
    onSquareRadiusChanged: requestPaint()
    onVisibleChanged: if (visible) requestPaint()     // a Canvas comes back blank after hide/show

    onPaint: {
        const ctx = getContext("2d");
        ctx.reset();
        if (c.draw <= 0) return;
        const cx = width / 2, cy = height / 2, R = c.radius, r = R / 2, S = c.squareRadius;
        const corners = (n, rad, start) => Array.from({ length: n + 1 }, (_, i) => {
            const a = start + (i % n) * 2 * Math.PI / n;
            return [cx + Math.cos(a) * rad, cy + Math.sin(a) * rad];
        });
        const lt = c.triangle ? 3 * Math.sqrt(3) * R : 0;
        const lc = c.incircle ? 2 * Math.PI * r : 0;
        const ls = c.square ? 4 * Math.SQRT2 * S : 0;
        let budget = c.draw * (lt + lc + ls);
        ctx.strokeStyle = Theme.css(c.color, c.color.a);
        ctx.lineWidth = c.lineWidth;
        ctx.lineJoin = "round";
        function poly(pts, side) {
            ctx.beginPath();
            ctx.moveTo(pts[0][0], pts[0][1]);
            for (let i = 1; i < pts.length && budget > 0; i++) {
                const x0 = pts[i - 1][0], y0 = pts[i - 1][1], x1 = pts[i][0], y1 = pts[i][1];
                const k = Math.min(1, budget / side);
                ctx.lineTo(x0 + (x1 - x0) * k, y0 + (y1 - y0) * k);
                budget -= side;
            }
            ctx.stroke();
        }
        if (c.triangle) poly(corners(3, R, -Math.PI / 2), Math.sqrt(3) * R);
        if (c.incircle && budget > 0) {
            ctx.beginPath();
            ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * Math.min(1, budget / lc));
            ctx.stroke();
            budget -= lc;
        }
        if (c.square && budget > 0) poly(corners(4, S, -Math.PI / 4), Math.SQRT2 * S);
    }
}
