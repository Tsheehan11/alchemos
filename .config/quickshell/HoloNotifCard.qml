// The base notification card (Skin.component "notifCard"; LEGACY uses it): the look mako had in STARK
// OS, kept exactly: dark glass #05090f at 90 %, text #cfefff, a 1 px cyan border (red when critical),
// 4 px corners, 10 px padding, the mono face, summary in bold over the body, the app icon on the left,
// "(N)" for a group. No entrance or exit animation (mako had none).
//
// Contract for any skin's notifCard (NotifPopups.qml sets these; width comes from the container,
// the card sets its own implicitHeight):
//   n        { nid, app, summary, body (simple markup), icon (name or path), image, urgency
//              ("low" | "normal" | "critical"), actions [{ id, text }], count, persona ("orrin" |
//              "selene" | ""), time }
//   ctl      Notifications: ctl.activate(nid) (a click: default action or dismiss), ctl.invoke(nid, id),
//            ctl.dismiss(nid)
//   closing  true once it's closing: play the exit; the row goes after exitMs
//   calm     battery saver: no blur / glow, short or no animation
//   exitMs   how long the exit plays
//   animated false: no entrance / looping motion, the settled look at once (the skin check sets it)
import QtQuick
import Quickshell

Item {
    id: card
    property var n: ({})
    property var ctl: null
    property bool closing: false
    property bool calm: false
    property int exitMs: 60
    property bool animated: true
    readonly property bool critical: n.urgency === "critical"
    readonly property string iconSource: {
        const i = n.image || n.icon || "";
        if (!i) return "";
        if (i.startsWith("/") ) return "file://" + i;
        if (i.indexOf("://") >= 0) return i;
        return Quickshell.iconPath(i, true);
    }
    implicitHeight: Math.max(body.implicitHeight, iconBox.visible ? 64 : 0) + 20 + (acts.visible ? acts.height + 8 : 0)
    opacity: closing ? 0 : 1

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: Qt.rgba(0x05 / 255, 0x09 / 255, 0x0f / 255, 0.9)
        border.width: 1
        border.color: card.critical ? Qt.rgba(1, 0x5a / 255, 0x5a / 255, 0.93) : Qt.rgba(0x4f / 255, 0xd8 / 255, 1, 0.93)
    }
    Image {
        id: iconBox
        visible: card.iconSource !== "" && status !== Image.Error
        x: 10; y: 10
        width: 64; height: 64
        sourceSize: Qt.size(64, 64)
        fillMode: Image.PreserveAspectFit
        source: card.iconSource
        asynchronous: true
    }
    Column {
        id: body
        x: iconBox.visible ? 84 : 10; y: 10
        width: card.width - x - 10
        spacing: 2
        Text {
            width: parent.width
            text: (card.n.count > 1 ? "(" + card.n.count + ") " : "") + (card.n.summary || card.n.app || "")
            color: "#cfefff"; font.family: Style.fonts.mono; font.pixelSize: 13; font.bold: true
            wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
            textFormat: Text.PlainText
        }
        Text {
            visible: text !== ""
            width: parent.width
            text: card.n.body || ""
            color: "#cfefff"; font.family: Style.fonts.mono; font.pixelSize: 13
            wrapMode: Text.Wrap; maximumLineCount: 8; elide: Text.ElideRight
            textFormat: Text.StyledText
        }
    }
    Row {
        id: acts
        visible: (card.n.actions || []).length > 0
        x: body.x; y: card.height - height - 10
        spacing: 8
        Repeater {
            model: card.n.actions || []
            delegate: Rectangle {
                required property var modelData
                width: lbl.implicitWidth + 16; height: 22
                radius: 3
                color: actHover.hovered ? Qt.rgba(0x4f / 255, 0xd8 / 255, 1, 0.18) : "transparent"
                border.width: 1; border.color: Qt.rgba(0x4f / 255, 0xd8 / 255, 1, 0.6)
                Text { id: lbl; anchors.centerIn: parent; text: modelData.text; color: "#cfefff"; font.family: Style.fonts.mono; font.pixelSize: 12 }
                HoverHandler { id: actHover }
                TapHandler { onTapped: if (card.ctl) card.ctl.invoke(card.n.nid, modelData.id) }
            }
        }
    }
    // a click anywhere else: the default action, else dismiss; right click dismisses (mako's buttons)
    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: (ev, btn) => { if (card.ctl && !(acts.visible && ev.position.y >= acts.y - 4)) card.ctl.activate(card.n.nid); }
    }
    TapHandler { acceptedButtons: Qt.RightButton; onTapped: if (card.ctl) card.ctl.dismiss(card.n.nid) }
}
