// Engraved inscription: a triangle in a circle of `radius`, its incircle, and a square in that.
// draw: 0..1 traces it in that order (the "inscribes itself" animation); 1 = all of it.
// A still sigil paints once; it only repaints when something here changes.
import QtQuick

Canvas {
    id: c
    property real radius: 100
    property real draw: 1
    property color color: Theme.primary
    property real lineWidth: 1.2
    property bool square: true
    width: radius * 2 + 8; height: width

    onDrawChanged: requestPaint()
    onColorChanged: requestPaint()
    onRadiusChanged: requestPaint()
    onVisibleChanged: if (visible) requestPaint()     // a Canvas comes back blank after hide/show

    onPaint: {
        const ctx = getContext("2d");
        ctx.reset();
        if (c.draw <= 0) return;
        const cx = width / 2, cy = height / 2, R = c.radius, r = R / 2;
        const tri = [0, 1, 2, 3].map(i => {
            const a = -Math.PI / 2 + (i % 3) * 2 * Math.PI / 3;
            return [cx + Math.cos(a) * R, cy + Math.sin(a) * R];
        });
        const sq = [0, 1, 2, 3, 4].map(i => {
            const a = -Math.PI / 4 + (i % 4) * Math.PI / 2;
            return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
        });
        // lengths: triangle, incircle, square
        const lt = 3 * Math.sqrt(3) * R, lc = 2 * Math.PI * r, ls = c.square ? 4 * Math.SQRT2 * r : 0;
        let budget = c.draw * (lt + lc + ls);
        ctx.strokeStyle = Theme.css(c.color, c.color.a);
        ctx.lineWidth = c.lineWidth;
        ctx.lineJoin = "round";
        function poly(pts, seg) {
            ctx.moveTo(pts[0][0], pts[0][1]);
            for (let i = 1; i < pts.length && budget > 0; i++) {
                const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
                const k = Math.min(1, budget / seg);
                ctx.lineTo(x0 + (x1 - x0) * k, y0 + (y1 - y0) * k);
                budget -= seg;
            }
        }
        ctx.beginPath();
        poly(tri, Math.sqrt(3) * R);
        ctx.stroke();
        if (budget > 0) {
            ctx.beginPath();
            ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * Math.min(1, budget / lc));
            ctx.stroke();
            budget -= lc;
        }
        if (budget > 0 && c.square) {
            ctx.beginPath();
            poly(sq, Math.SQRT2 * r);
            ctx.stroke();
        }
    }
}
