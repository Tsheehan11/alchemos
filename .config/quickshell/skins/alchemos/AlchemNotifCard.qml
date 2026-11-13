// ALCHEMOS notification card (skin.json components.notifCard; the contract is in HoloNotifCard.qml).
// An engraved plate (Engraving.qml) in the urgency's metal:
//   low       quicksilver: a muted silver, no rim glow
//   normal    the preset's metal (Aurum's gold, Iron's red…) with a faint ember at the rim
//   critical  molten: a red-orange heat that breathes at the rim and never times out
// A medallion on the left holds the app icon (or the engraved bell); ORRIN's and SELENE's own
// messages carry their sun / moon sign. Summary in the display face (Cinzel), body in prose (Marcellus).
// In: the medallion's ring inscribes itself and flares, the plate rises in behind it (ignite).
// Out: solve. The plate dissolves into grains (assets/dissolve.png as a threshold mask) and drifts up.
// Battery saver (calm): no glow or flare, a plain fade in and out.
import QtQuick
import QtQuick.Effects
import Quickshell
import "../.."

Item {
    id: card
    property var n: ({})
    property var ctl: null
    property bool closing: false
    property bool calm: false
    property int exitMs: calm ? 140 : 560
    property bool animated: true           // false: the settled look at once (the skin check)

    readonly property string urgency: n.urgency || "normal"
    readonly property color silver: Theme.mix("#b4bac6", Theme.primary, 0.12)
    readonly property color molten: "#ff5a24"
    readonly property color metal: urgency === "critical" ? molten : urgency === "low" ? silver : Theme.primary
    readonly property color ink: urgency === "low" ? Theme.mix(silver, "#ffffff", 0.55) : Theme.mix(metal, "#ffffff", 0.82)
    readonly property string sign: n.persona === "orrin" ? (Skin.persona("orrin").glyph || "☉")
                                 : n.persona === "selene" ? (Skin.persona("selene").glyph || "☽") : ""
    readonly property string iconSource: {
        const i = n.image || n.icon || "";
        if (!i) return "";
        if (i.startsWith("/")) return "file://" + i;
        if (i.indexOf("://") >= 0) return i;
        return Quickshell.iconPath(i, true);
    }

    implicitHeight: Math.max(76, text.implicitHeight + 28) + (acts.visible ? acts.height + 10 : 0)

    // ── ignite: 0 → 1 as it arrives; dissolve: 0 → 1 as it leaves ──
    property real ignite: calm || !animated ? 1 : 0
    property real dissolve: 0
    property real breathe: 0
    Component.onCompleted: if (!calm && animated) igniteAnim.start()
    NumberAnimation { id: igniteAnim; target: card; property: "ignite"; from: 0; to: 1; duration: 620; easing.type: Easing.OutCubic }
    onClosingChanged: if (closing) { if (calm) fadeOut.start(); else solveAnim.start(); }
    NumberAnimation { id: solveAnim; target: card; property: "dissolve"; from: 0; to: 1; duration: card.exitMs; easing.type: Easing.InQuad }
    NumberAnimation { id: fadeOut; target: plate; property: "opacity"; to: 0; duration: card.exitMs }
    SequentialAnimation on breathe {        // critical: the rim heat swells and settles
        running: card.urgency === "critical" && !card.calm && !card.closing && card.animated
        loops: Animation.Infinite
        NumberAnimation { from: 0; to: 1; duration: 900; easing.type: Easing.InOutSine }
        NumberAnimation { from: 1; to: 0; duration: 900; easing.type: Easing.InOutSine }
    }

    // flash of the ignition behind the medallion, gone by the time the text has settled
    readonly property real flare: calm ? 0 : Math.max(0, 1 - Math.abs(ignite - 0.55) / 0.25) * Style.glow

    Item {
        id: plate
        width: card.width; height: card.height
        // rises in under the medallion's ring, drifts up as it dissolves
        opacity: card.calm ? 1 : Math.min(1, card.ignite * 1.6)
        y: card.calm ? 0 : (1 - card.ignite) * 8 - card.dissolve * 10
        visible: !solveFx.visible
        layer.enabled: solveFx.visible
        Behavior on opacity { enabled: card.calm; NumberAnimation { duration: 140 } }

        Engraving {
            fillAlpha: 0.95
            notch: 12
            emberColor: card.metal
            ember: card.calm ? 0 : card.urgency === "critical" ? (0.22 + 0.2 * card.breathe) * Style.glow
                                 : card.urgency === "low" ? 0 : 0.1 * Style.glow
        }

        // medallion: an engraved ring, inscribed on arrival, holding the sign / icon / bell
        Item {
            id: medal
            x: 14; y: 14
            width: 48; height: 48
            Canvas {
                id: ring
                anchors.fill: parent
                readonly property real draw: card.ignite
                onDrawChanged: requestPaint()
                readonly property color c: card.metal
                onCChanged: requestPaint()
                onPaint: {
                    const ctx = getContext("2d");
                    ctx.reset();
                    const r = width / 2 - 2, cx = width / 2, cy = height / 2;
                    ctx.strokeStyle = Qt.rgba(c.r, c.g, c.b, 0.9);
                    ctx.lineWidth = 1.4;
                    ctx.beginPath();
                    ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, draw / 0.6), false);
                    ctx.stroke();
                    // inner circle and four ticks follow the outer ring
                    const k = Math.max(0, Math.min(1, (draw - 0.4) / 0.4));
                    if (k > 0) {
                        ctx.strokeStyle = Qt.rgba(c.r, c.g, c.b, 0.45 * k);
                        ctx.lineWidth = 1;
                        ctx.beginPath(); ctx.arc(cx, cy, r - 5, 0, Math.PI * 2); ctx.stroke();
                        for (let i = 0; i < 4; i++) {
                            const a = i * Math.PI / 2 + Math.PI / 4;
                            ctx.beginPath();
                            ctx.moveTo(cx + Math.cos(a) * (r - 5), cy + Math.sin(a) * (r - 5));
                            ctx.lineTo(cx + Math.cos(a) * (r + 1), cy + Math.sin(a) * (r + 1));
                            ctx.stroke();
                        }
                    }
                }
            }
            Rectangle {                     // the flare as the ring closes
                anchors.centerIn: parent
                width: parent.width * 1.5; height: width; radius: width / 2
                color: "transparent"
                border.width: 10
                border.color: Qt.rgba(card.metal.r, card.metal.g, card.metal.b, 0.35 * card.flare)
                visible: card.flare > 0.01
            }
            SigilText {
                visible: card.sign !== ""
                anchors.centerIn: parent
                text: card.sign
                color: card.metal
                font.pixelSize: 24
                glow: card.calm ? 0 : 0.5 * Style.glow
                opacity: Math.min(1, card.ignite * 1.4)
            }
            Image {
                id: appIcon
                visible: card.sign === "" && card.iconSource !== "" && status !== Image.Error
                anchors.centerIn: parent
                width: 28; height: 28
                sourceSize: Qt.size(56, 56)
                fillMode: Image.PreserveAspectFit
                source: card.iconSource
                asynchronous: true
                opacity: Math.min(1, card.ignite * 1.4)
            }
            SkinIcon {
                visible: card.sign === "" && !appIcon.visible
                anchors.centerIn: parent
                name: "bell"; size: 22; color: card.metal
                opacity: Math.min(1, card.ignite * 1.4)
            }
        }

        Column {
            id: text
            x: medal.x + medal.width + 14; y: 13
            width: card.width - x - 34
            spacing: 3
            opacity: card.calm ? 1 : Math.max(0, Math.min(1, (card.ignite - 0.3) / 0.5))
            Row {
                spacing: 8
                width: parent.width
                Text {
                    text: (card.n.app || "").toUpperCase()
                    color: Theme.mix(card.metal, Theme.bg, 0.25)
                    font.family: Style.fonts.label; font.pixelSize: 10; font.letterSpacing: 2
                    elide: Text.ElideRight
                    width: Math.min(implicitWidth, parent.width - countText.width - 8)
                }
                Text {
                    id: countText
                    visible: (card.n.count || 1) > 1
                    text: "×" + Style.numeral(card.n.count || 1)
                    color: card.metal
                    font.family: Style.fonts.label; font.pixelSize: 10; font.letterSpacing: 1
                }
            }
            Text {
                width: parent.width
                text: card.n.summary || card.n.app || ""
                color: card.ink
                font.family: Style.fonts.display; font.pixelSize: 15
                wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                textFormat: Text.PlainText
            }
            Text {
                visible: text !== ""
                width: parent.width
                text: card.n.body || ""
                color: Theme.mix(card.ink, Theme.bg, 0.22)
                font.family: Style.fonts.prose; font.pixelSize: 14
                wrapMode: Text.Wrap; maximumLineCount: 6; elide: Text.ElideRight
                textFormat: Text.StyledText
                linkColor: card.metal
            }
        }

        Text {                              // close
            id: closeBtn
            x: card.width - 24; y: 9
            text: "✕"
            color: closeHover.hovered ? card.ink : Theme.mix(card.metal, Theme.bg, 0.4)
            font.family: Style.fonts.glyph; font.pixelSize: 12
            HoverHandler { id: closeHover }
            TapHandler { onTapped: if (card.ctl) card.ctl.dismiss(card.n.nid) }
        }

        Row {
            id: acts
            visible: (card.n.actions || []).length > 0
            x: text.x; y: card.height - height - 12
            spacing: 8
            Repeater {
                model: card.n.actions || []
                delegate: SmallButton {
                    required property var modelData
                    text: String(modelData.text).toUpperCase()
                    onClicked: if (card.ctl) card.ctl.invoke(card.n.nid, modelData.id)
                }
            }
        }
    }

    // ── solve: the plate falls apart into grains, densest last ──
    Item {
        id: noise
        width: card.width; height: card.height
        visible: false
        layer.enabled: true
        Image { anchors.fill: parent; source: Qt.resolvedUrl("../../assets/dissolve.png"); fillMode: Image.Tile }
    }
    MultiEffect {
        id: solveFx
        visible: card.dissolve > 0 && !card.calm
        x: plate.x; y: plate.y
        width: plate.width; height: plate.height
        source: plate
        maskEnabled: true
        maskSource: noise
        maskThresholdMin: card.dissolve
        maskSpreadAtMin: 0.25
        colorization: card.dissolve * 0.6          // cooling to ash as it goes
        colorizationColor: Theme.mix(card.metal, "#3a3632", 0.6)
    }

    // clicks: the default action (else dismiss), not over the buttons or the ✕; right click dismisses
    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: (ev, btn) => {
            if (!card.ctl) return;
            if (acts.visible && ev.position.y >= acts.y - 4) return;
            if (ev.position.x >= closeBtn.x - 6 && ev.position.y <= closeBtn.y + 20) return;
            card.ctl.activate(card.n.nid);
        }
    }
    TapHandler { acceptedButtons: Qt.RightButton; onTapped: if (card.ctl) card.ctl.dismiss(card.n.nid) }
}
