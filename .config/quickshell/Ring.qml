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
    property bool animated: true
    // A value gauge (stats, network…): with Style.gauge "astrolabe" it gets a graduated limb outside the
    // arc, a needle to the value and a centre rivet. Off (and drawing nothing) otherwise.
    property bool gauge: false
    readonly property bool astro: gauge && Style.gauge === "astrolabe"

    width: radius * 2 + thickness + 4
    height: width

    Behavior on value {
        enabled: root.animated
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

        // Astrolabe limb: fine graduations just outside the arc
        ShapePath {
            strokeColor: root.astro ? Qt.rgba(root.color.r, root.color.g, root.color.b, 0.4) : "transparent"
            strokeWidth: root.astro ? 4 : 0
            fillColor: "transparent"
            capStyle: ShapePath.FlatCap
            strokeStyle: ShapePath.DashLine
            dashPattern: [0.25, 2.4]
            PathAngleArc {
                centerX: root.width / 2
                centerY: root.height / 2
                radiusX: root.radius + root.thickness / 2 + 5
                radiusY: root.radius + root.thickness / 2 + 5
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

    // Astrolabe pointer: a short alidade just inside the arc at the value (gauges keep their centre for text)
    Item {
        visible: root.astro
        anchors.fill: parent
        rotation: root.startAngle + 90 + 360 * Math.max(0.002, Math.min(1, root.value))
        Rectangle {
            width: 2; height: Math.max(4, root.radius * 0.3)
            x: parent.width / 2 - 1; y: parent.height / 2 - root.radius + root.thickness / 2 + 1
            antialiasing: true
            color: Theme.mix(root.color, "#ffffff", 0.45)
        }
        Rectangle {
            width: 5; height: 5; rotation: 45
            x: parent.width / 2 - 2.5; y: parent.height / 2 - root.radius + root.thickness / 2 + Math.max(4, root.radius * 0.3) - 1
            color: Theme.mix(root.color, "#ffffff", 0.45)
        }
    }
}
