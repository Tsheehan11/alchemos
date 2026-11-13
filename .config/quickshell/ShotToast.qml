// "CAPTURE SAVED" toast (Shot.qml), bottom-right of the monitor holding most of the shot: thumbnail (click
// opens it), OPEN / FOLDER buttons, ✕. Stays 7 s, longer while the pointer is on it. Battery saver: no slide.
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

PanelWindow {
    id: toast
    required property var modelData
    screen: modelData

    readonly property string where: Shot.mainScreen() || (Hyprland.focusedMonitor?.name ?? "")
    readonly property bool here: where === modelData.name
    readonly property bool ok: !!Shot.last.ok
    visible: here && (Shot.toastShowing || panel.opacity > 0.01)

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "alchemos-shot-toast"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { bottom: true; right: true }
    margins { bottom: 28; right: 28 }
    implicitWidth: 430
    implicitHeight: 128
    color: "transparent"

    // Out of the next shot's way (Shot.qml)
    Binding { target: toast.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }

    readonly property color accent: ok ? Theme.primary : "#ff5f5f"

    Rectangle {
        Engraving { visible: Style.engraved; fillAlpha: 0.94; corners: []; notch: 12; emberColor: toast.accent }     // engraved skins: the plate (Engraving.qml)
        id: panel
        width: parent.width; height: parent.height
        color: Style.engraved ? "transparent" : Theme.d(0.92)
        border.color: Style.engraved ? "transparent" : Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.55)
        border.width: 1
        opacity: Shot.toastShowing ? 1 : 0
        x: Shot.toastShowing || Shot.calm ? 0 : 40
        Behavior on opacity { enabled: !Shot.calm; NumberAnimation { duration: Shot.toastShowing ? 160 : 380; easing.type: Easing.OutCubic } }
        Behavior on x { enabled: !Shot.calm; NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }

        HoverHandler { onHoveredChanged: Shot.toastHover = hovered }

        // Corner brackets
        Repeater {
            model: Style.engraved ? 0 : 4
            delegate: Item {
                required property int index
                width: 14; height: 14
                x: index % 2 === 0 ? -1 : panel.width - 13
                y: index < 2 ? -1 : panel.height - 13
                Rectangle { width: 14; height: 2; color: toast.accent; y: index < 2 ? 0 : 12 }
                Rectangle { width: 2; height: 14; color: toast.accent; x: index % 2 === 0 ? 0 : 12 }
            }
        }

        // Thumbnail
        Rectangle {
            id: thumbBox
            x: 12; y: 12
            width: 160; height: parent.height - 24
            color: Theme.d(1)
            border.color: thumbMa.containsMouse ? toast.accent : Theme.p(0.35)
            border.width: 1
            Image {
                id: thumb
                anchors.fill: parent; anchors.margins: 2
                visible: toast.ok
                source: toast.ok && Shot.last.path ? "file://" + Shot.last.path : ""
                sourceSize.width: 320
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                cache: false
                smooth: true
            }
            Text {
                anchors.centerIn: parent
                visible: !toast.ok
                text: String.fromCodePoint(0xF0100)   // camera-off
                color: toast.accent; font.family: Style.fonts.body; font.pixelSize: 34
            }
            MouseArea { id: thumbMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; enabled: toast.ok; onClicked: Shot.openShot() }
        }

        Column {
            anchors.left: thumbBox.right; anchors.leftMargin: 16
            anchors.right: parent.right; anchors.rightMargin: 14
            anchors.top: parent.top; anchors.topMargin: 14
            spacing: 5
            Text {
                text: toast.ok ? (Shot.last.annotating ? "CAPTURE // ANNOTATE" : "CAPTURE SAVED") : "CAPTURE FAILED"
                color: Theme.text; font.family: Style.fonts.label; font.pixelSize: 15; font.bold: true; font.letterSpacing: 3
            }
            Text {
                width: parent.width; elide: Text.ElideMiddle
                text: toast.ok ? Shot.last.name : (Shot.last.error || "")
                color: toast.accent; font.family: Style.fonts.body; font.pixelSize: 11
                wrapMode: toast.ok ? Text.NoWrap : Text.Wrap; maximumLineCount: 2
            }
            Text {
                visible: toast.ok
                text: (Shot.last.width || 0) + "×" + (Shot.last.height || 0) + " · " + String(Shot.last.mode || "").toUpperCase()
                      + (Shot.last.copied ? " · CLIPBOARD" : " · NOT COPIED")
                color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 10; font.letterSpacing: 1
            }
        }

        Row {
            visible: toast.ok
            anchors.left: thumbBox.right; anchors.leftMargin: 16
            anchors.bottom: parent.bottom; anchors.bottomMargin: 12
            spacing: 8
            SmallButton { text: "▸ OPEN"; onClicked: Shot.openShot() }
            SmallButton { text: "▤ FOLDER"; onClicked: Shot.openFolder() }
        }

        Text {
            anchors.right: parent.right; anchors.rightMargin: 12
            anchors.top: parent.top; anchors.topMargin: 8
            text: "✕"
            color: closeMa.containsMouse ? Theme.text : Theme.faint
            font.family: Style.fonts.body; font.pixelSize: 13
            MouseArea { id: closeMa; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Shot.dismiss() }
        }
    }
}
