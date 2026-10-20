// The arc-reactor clock: CPU / RAM / GPU / battery rings around the time.
// Change k to resize the whole thing (1 = original size).
import QtQuick
import Quickshell

Item {
    id: r
    property real k: Theme.cfg.reactorScale
    property real t: 0          // effects clock (seconds), from HudWindow

    width: 480 * k
    height: 560 * k

    readonly property color cyan: Theme.primary
    readonly property color amber: Theme.secondary
    readonly property color dim: Theme.dim
    readonly property string mono: "JetBrainsMono Nerd Font"

    SystemClock { id: clock; precision: SystemClock.Seconds }

    Item {
        id: core
        width: 480 * r.k
        height: 480 * r.k

        // Outer dashed ring, slowly rotating
        Ring {
            anchors.centerIn: parent
            radius: 230 * r.k; thickness: 1; value: 1
            dashed: true; dash: [2, 8]
            color: Theme.p(0.4)
            trackColor: "transparent"
            rotation: r.t * 4
        }

        // Tick dial
        Ring {
            anchors.centerIn: parent
            radius: 216 * r.k; thickness: 8 * r.k; value: 1
            dashed: true; dash: [0.25, 2.2]
            color: Theme.p(0.22)
            trackColor: "transparent"
        }

        // Seconds marker orbiting the outer ring
        Item {
            anchors.fill: parent
            rotation: clock.date.getSeconds() * 6
            Behavior on rotation { RotationAnimation { duration: 300; direction: RotationAnimation.Clockwise } }
            Rectangle {
                width: 8 * r.k; height: width; radius: width / 2
                color: r.cyan
                x: parent.width / 2 - width / 2
                y: parent.height / 2 - 230 * r.k - height / 2
            }
        }

        // CPU / RAM / GPU / battery rings
        Ring { anchors.centerIn: parent; radius: 196 * r.k; thickness: 6 * r.k; value: SysStats.cpu; color: r.cyan }
        Ring { anchors.centerIn: parent; radius: 180 * r.k; thickness: 6 * r.k; value: SysStats.ram; color: r.cyan; opacity: 0.8 }
        Ring { anchors.centerIn: parent; radius: 164 * r.k; thickness: 6 * r.k; value: SysStats.gpu; color: r.amber; opacity: 0.85 }
        Ring { anchors.centerIn: parent; radius: 148 * r.k; thickness: 6 * r.k; value: SysStats.battery; color: SysStats.charging ? "#7cf5c1" : r.cyan; opacity: 0.5 }

        // Thin divider
        Ring { anchors.centerIn: parent; radius: 130 * r.k; thickness: 1; value: 1; color: Theme.p(0.4); trackColor: "transparent" }

        // Amber segmented ring, counter-rotating
        Ring {
            anchors.centerIn: parent
            radius: 117 * r.k; thickness: 4 * r.k; value: 1
            dashed: true; dash: [5, 1.6]
            color: r.amber; opacity: 0.7
            trackColor: "transparent"
            rotation: -r.t * 9
        }

        // Core disc
        Rectangle {
            anchors.centerIn: parent
            width: 204 * r.k; height: width; radius: width / 2
            color: Theme.p(0.06)
            border.color: Theme.p(0.3)
            border.width: 1
        }

        // Time + date
        Column {
            anchors.centerIn: parent
            spacing: 4
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Qt.formatDateTime(clock.date, Theme.cfg.clock24 ? "hh:mm" : "h:mm")
                color: Theme.text
                font.family: r.mono
                font.pixelSize: 56 * r.k
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Qt.formatDateTime(clock.date, "ddd · dd MMM").toUpperCase()
                color: r.dim
                font.family: r.mono
                font.pixelSize: 13 * r.k
                font.letterSpacing: 3
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: ":" + Qt.formatDateTime(clock.date, "ss")
                color: r.amber
                font.family: r.mono
                font.pixelSize: 12 * r.k
                opacity: 0.8
            }
        }
    }

    // Legend
    Row {
        anchors.top: core.bottom
        anchors.topMargin: 16 * r.k
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 26 * r.k
        Text { text: "● CPU " + Math.round(SysStats.cpu * 100) + "%"; color: r.cyan; font.family: r.mono; font.pixelSize: 13 * r.k; font.letterSpacing: 1 }
        Text { text: "● RAM " + Math.round(SysStats.ram * 100) + "%"; color: r.dim; font.family: r.mono; font.pixelSize: 13 * r.k; font.letterSpacing: 1 }
        Text { text: "● GPU " + (SysStats.gpuAvailable ? Math.round(SysStats.gpu * 100) + "%" : "--"); color: r.amber; font.family: r.mono; font.pixelSize: 13 * r.k; font.letterSpacing: 1 }
        Text { text: "● BAT " + Math.round(SysStats.battery * 100) + "%" + (SysStats.charging ? " ⚡" : ""); color: Theme.dim; font.family: r.mono; font.pixelSize: 13 * r.k; font.letterSpacing: 1 }
    }
}
