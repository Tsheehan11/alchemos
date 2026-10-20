// A single circular gauge ring. value = 0..1 of a full circle.
import QtQuick
import QtQuick.Shapes

Item {
    id: root

    property real value: 1
    property real radius: 100
    property real thickness: 6
    property color color: Theme.primary
    property color trackColor: Theme.p(0.12)
    property real startAngle: -90
    property bool dashed: false
    property var dash: [2, 6]

    width: radius * 2 + thickness + 4
    height: width

    Behavior on value {
        NumberAnimation { duration: 700; easing.type: Easing.OutCubic }
    }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        // Faint full-circle track
        ShapePath {
            strokeColor: root.trackColor
            strokeWidth: root.thickness
            fillColor: "transparent"
            PathAngleArc {
                centerX: root.width / 2
                centerY: root.height / 2
                radiusX: root.radius
                radiusY: root.radius
                startAngle: 0
                sweepAngle: 360
            }
        }

        // The value arc
        ShapePath {
            strokeColor: root.color
            strokeWidth: root.thickness
            fillColor: "transparent"
            capStyle: root.dashed ? ShapePath.FlatCap : ShapePath.RoundCap
            strokeStyle: root.dashed ? ShapePath.DashLine : ShapePath.SolidLine
            dashPattern: root.dash
            PathAngleArc {
                centerX: root.width / 2
                centerY: root.height / 2
                radiusX: root.radius
                radiusY: root.radius
                startAngle: root.startAngle
                sweepAngle: 360 * Math.max(0.002, Math.min(1, root.value))
            }
        }
    }
}
