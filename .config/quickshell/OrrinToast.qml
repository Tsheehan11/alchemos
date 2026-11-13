// ORRIN pop-up on the focused screen: projected text, not a box. Follows OrrinState.phase:
//   LISTENING (waveform) → transcript → PROCESSING (tool calls appear one by one,
//   "◆ THEME → MARK III") → RESPONSE / AWAITING CONFIRMATION → FOLLOW-UP.
// The whole reply is always there: a long one scrolls inside, following the speech karaoke-style
// (OrrinState.speak: the sentence being spoken is lit, the line under it is marked, and the view
// keeps it in sight). The mouse wheel scrolls it by hand and pauses the following. It stays up while
// Orrin speaks or the pointer is on it, then a few seconds scaled to length. A click opens the
// thread in the ORRIN console on this monitor. Timers and reminders use the same panel (phase "alert").
import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

PanelWindow {
    id: toast
    required property var modelData
    screen: modelData

    // not over the console: it shows the same conversation (and any YES / NO) itself
    readonly property bool on: OrrinState.showing && Hyprland.focusedMonitor?.name === modelData.name
                               && !(OrrinLink.open && OrrinLink.screenName === modelData.name)
    visible: on || holo.opacity > 0.01          // stays mapped while it fades out

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "alchemos-orrin"
    exclusionMode: ExclusionMode.Ignore
    anchors { bottom: true }
    margins { bottom: 44 }
    implicitWidth: Math.min(900, Math.round(modelData.width * 0.52))
    implicitHeight: Math.min(Math.round(modelData.height * 0.4), content.implicitHeight + 2 * pad)
    color: "transparent"
    Binding { target: toast.contentItem; property: "opacity"; value: Shot.hiding ? 0 : 1 }   // out of screenshots (Shot.qml)

    readonly property int pad: 26
    readonly property string phase: OrrinState.phase
    readonly property bool hot: phase === "confirm" || phase === "alert" || phase === "error"     // secondary colour
    readonly property color accent: hot ? Theme.secondary : OrrinState.accent     // the persona's (ALCHEMOS gold / silver) at the edge
    readonly property bool busy: phase === "thinking"
    readonly property string phaseLabel: ({
        listening: "LISTENING", followup: "LISTENING · FOLLOW-UP", thinking: "PROCESSING",
        reply: OrrinState.speaking ? "SPEAKING" : "RESPONSE", confirm: "AWAITING CONFIRMATION",
        alert: OrrinState.alertTitle, error: "⚠ " + OrrinState.errorReason, idle: ""
    })[phase] || ""
    readonly property bool showReply: OrrinState.reply !== "" && ["reply", "confirm", "alert", "followup", "error"].includes(phase)

    // ── speech progress → a position in the reply ──
    property real spoken: 0                      // characters of the spoken text, animated per sentence
    readonly property bool following: OrrinState.speaking && OrrinState.speakTotal > 0
    readonly property int pos: OrrinState.speakTotal > 0
        ? Math.min(OrrinState.reply.length, Math.floor(spoken / OrrinState.speakTotal * OrrinState.reply.length)) : 0
    NumberAnimation { id: spokenAnim; target: toast; property: "spoken" }
    Connections {
        target: OrrinState
        function onSpeakAtChanged() {
            spokenAnim.stop();
            spokenAnim.from = OrrinState.speakStart; spokenAnim.to = OrrinState.speakEnd;
            spokenAnim.duration = Math.max(1, OrrinState.speakMs);
            spokenAnim.start();
        }
        function onSpeakingChanged() { if (!OrrinState.speaking) { spokenAnim.stop(); toast.spoken = OrrinState.speakTotal; } }
        function onReplySerialChanged() { scroller.userScrolled = false; scroller.contentY = 0; readPace.pos = 0; }
    }

    // sentence around a character position: [start, end)
    function sentenceAt(t, p) {
        let s = 0;
        const re = /[.!?…]+["')\]]?(\s+|$)/g;
        let m;
        while ((m = re.exec(t)) !== null) {
            const e = m.index + m[0].length;
            if (e > p) return [s, e];
            s = e;
            if (m[0].length === 0) re.lastIndex++;
        }
        return [s, t.length];
    }
    function esc(t) { return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>"); }
    function hex(c, a) { return Qt.rgba(c.r, c.g, c.b, a === undefined ? 1 : a).toString(); }
    // karaoke: said · being said (lit) · still to come (dim)
    readonly property var span: following ? sentenceAt(OrrinState.reply, pos) : [0, 0]
    readonly property string replyHtml: {
        const t = OrrinState.reply;
        if (!following) return esc(t);
        return "<span style='color:" + hex(Theme.textSoft) + "'>" + esc(t.slice(0, span[0])) + "</span>"
             + "<span style='color:" + hex(Qt.lighter(toast.accent, 1.45)) + "'>" + esc(t.slice(span[0], span[1])) + "</span>"
             + "<span style='color:" + hex(Theme.dim) + "'>" + esc(t.slice(span[1])) + "</span>";
    }

    // ═══ the projection ═══
    Item {
        id: holo
        anchors.fill: parent
        opacity: toast.on ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: toast.on ? 260 : 420; easing.type: Easing.OutCubic } }
        transform: Translate { y: toast.on ? 0 : 16; Behavior on y { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } } }

        HoverHandler { onHoveredChanged: OrrinState.hovered = hovered }
        TapHandler {
            onTapped: {
                OrrinLink.show(toast.modelData.name);
                if (OrrinLink.current !== null) OrrinLink.openThread(OrrinLink.current);
                OrrinState.dismiss();
            }
        }

        // engraved skins: a stone plate, its rim glowing in the persona's accent (dense enough over white windows)
        Engraving {
            visible: Style.engraved
            anchors.fill: parent; anchors.margins: 10
            fillAlpha: 0.96
            corners: []
            emberColor: toast.accent
            ember: (toast.busy ? 0.22 + 0.12 * Math.sin(glowT.t) : 0.2) * Style.glow
        }

        // soft glass: a blurred plate with no hard edge, tinted toward the accent at the rim
        Rectangle {
            id: plate
            anchors.fill: parent; anchors.margins: 10
            radius: 22
            color: Theme.d(0.93)
            visible: false
        }
        MultiEffect {
            visible: !Style.engraved
            source: plate; anchors.fill: plate
            autoPaddingEnabled: true
            blurEnabled: true; blur: 0.45; blurMax: 32
        }
        Rectangle {                                     // denser in the middle, so what's behind can't compete
            visible: !Style.engraved
            anchors.fill: parent; anchors.margins: 30
            radius: 14; color: Theme.d(0.45)
        }
        Rectangle {
            id: rim
            anchors.fill: parent; anchors.margins: 6
            radius: 26; color: "transparent"
            border.width: 6; border.color: Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.22)
            visible: false
        }
        MultiEffect {
            visible: !Style.engraved
            source: rim; anchors.fill: rim
            autoPaddingEnabled: true
            blurEnabled: true; blur: 1.0; blurMax: 48
            opacity: toast.busy ? 0.6 + 0.4 * Math.sin(glowT.t) : 0.9
        }
        QtObject { id: glowT; property real t: 0; NumberAnimation on t { running: toast.visible && toast.busy; from: 0; to: Math.PI * 2; duration: 900; loops: Animation.Infinite } }

        // scanlines + a slow sweep, kept inside the plate
        Item {
            visible: Style.texture === "holo"
            anchors.fill: parent; anchors.margins: 18
            clip: true
            Column {
                anchors.fill: parent; spacing: 3
                Repeater {
                    model: Math.ceil(holo.height / 4)
                    Rectangle { width: holo.width; height: 1; color: Theme.p(0.028) }
                }
            }
            Rectangle {
                width: parent.width; height: 60
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.06) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                NumberAnimation on y { running: toast.visible; from: -60; to: holo.height; duration: toast.busy ? 1500 : 3600; loops: Animation.Infinite }
            }
        }

        // the projector: a bright line along the bottom, light rising from it
        Rectangle {
            visible: !Style.engraved
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - 9
            width: parent.width * 0.78; height: 2; radius: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.5; color: toast.accent }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }
        Rectangle {
            visible: !Style.engraved
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - 9 - height
            width: parent.width * 0.7; height: 46
            gradient: Gradient {
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 1.0; color: Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.08) }
            }
        }

        // ═══ content (flickers now and then, like a projection) ═══
        Column {
            id: content
            x: toast.pad + 4; y: toast.pad - 4
            width: parent.width - 2 * toast.pad - 8
            spacing: 8

            SequentialAnimation on opacity {
                id: flicker
                running: false
                NumberAnimation { to: 0.78; duration: 40 }
                NumberAnimation { to: 1; duration: 70 }
                NumberAnimation { to: 0.9; duration: 30 }
                NumberAnimation { to: 1; duration: 90 }
            }
            Timer {
                running: toast.visible && !Style.engraved; repeat: true      // a projection flickers; engraved metal doesn't
                interval: 2600
                onTriggered: { interval = 1800 + Math.random() * 4200; if (Math.random() < 0.6) flicker.start(); }
            }

            // header: the persona's marker, its name, the phase
            Item {
                width: parent.width; height: 22
                Item {
                    id: reactor
                    width: 22; height: 22
                    Ring {
                        anchors.centerIn: parent
                        radius: 10; thickness: 1.5; value: 1; animated: false
                        dashed: true; dash: [4, 3]
                        color: toast.accent; trackColor: "transparent"
                        RotationAnimation on rotation { running: toast.visible; from: 0; to: 360; duration: toast.busy ? 1100 : 3200; loops: Animation.Infinite }
                    }
                    // ALCHEMOS: the persona's sign (☉ / ☽), breathing
                    SigilText {
                        visible: OrrinState.hasAccent
                        anchors.centerIn: parent
                        text: OrrinState.glyph
                        color: toast.accent
                        font.pixelSize: 12
                        glow: 0.6
                        SequentialAnimation on scale {
                            running: toast.visible && OrrinState.hasAccent; loops: Animation.Infinite
                            NumberAnimation { from: 0.85; to: 1.15; duration: OrrinState.listening || OrrinState.speaking ? 380 : 700; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 1.15; to: 0.85; duration: OrrinState.listening || OrrinState.speaking ? 380 : 700; easing.type: Easing.InOutSine }
                        }
                    }
                    Rectangle {
                        visible: !OrrinState.hasAccent
                        anchors.centerIn: parent
                        // legacy: JARVIS a round core; FRIDAY a diamond
                        width: 8; height: 8; radius: OrrinState.who === "selene" ? 1 : 4
                        rotation: OrrinState.who === "selene" ? 45 : 0
                        color: toast.accent
                        SequentialAnimation on scale {
                            running: toast.visible && !OrrinState.hasAccent; loops: Animation.Infinite
                            NumberAnimation { from: 0.7; to: 1.25; duration: OrrinState.listening || OrrinState.speaking ? 380 : 700; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 1.25; to: 0.7; duration: OrrinState.listening || OrrinState.speaking ? 380 : 700; easing.type: Easing.InOutSine }
                        }
                    }
                }
                Text {
                    anchors.left: reactor.right; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter
                    text: OrrinState.dotted
                    color: OrrinState.hasAccent ? OrrinState.accent : Theme.primary
                    font.family: Style.fonts.display; font.pixelSize: Style.display !== Style.mono ? 13 : 11; font.letterSpacing: 4
                }
                Text {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    text: (scroller.userScrolled && toast.following ? "SCROLLED · " : "") + toast.phaseLabel
                    color: toast.hot ? Theme.secondary : Theme.dim
                    font.family: Style.fonts.label; font.pixelSize: 10; font.letterSpacing: 3
                }
            }

            // skins with a divider glyph: a rule under the header carrying the persona's own sign
            Divider {
                visible: Style.divider !== ""
                width: parent.width
                glyph: OrrinState.glyph
                color: toast.accent
            }

            // waveform while listening with nothing heard yet
            Row {
                visible: OrrinState.listening && OrrinState.transcript === ""
                height: 26; spacing: 4
                Repeater {
                    model: 22
                    Rectangle {
                        required property int index
                        width: 4; radius: 2
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.p(0.75)
                        height: 6
                        SequentialAnimation on height {
                            running: toast.visible && OrrinState.listening
                            loops: Animation.Infinite
                            NumberAnimation { to: 8 + (index * 37 % 17); duration: 180 + (index * 53 % 160); easing.type: Easing.InOutSine }
                            NumberAnimation { to: 4; duration: 180 + (index * 29 % 140); easing.type: Easing.InOutSine }
                        }
                    }
                }
            }

            // what Trevor said
            Text {
                id: said
                visible: OrrinState.transcript !== ""
                width: parent.width
                text: "“" + OrrinState.transcript + "”"
                color: Theme.textSoft
                font.family: Style.fonts.body; font.pixelSize: 13; font.italic: true
                wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
            }

            // tool calls as they run
            Column {
                id: toolCol
                visible: OrrinState.tools.length > 0 && toast.phase !== "alert"
                width: parent.width
                spacing: 3
                Repeater {
                    model: OrrinState.tools
                    Text {
                        id: line
                        required property string modelData
                        text: "◆ " + modelData
                        color: Theme.secondary
                        font.family: Style.fonts.label; font.pixelSize: 12; font.letterSpacing: 2
                        opacity: 0; x: -14
                        Component.onCompleted: appear.start()
                        ParallelAnimation {
                            id: appear
                            NumberAnimation { target: line; property: "opacity"; to: 1; duration: 260 }
                            NumberAnimation { target: line; property: "x"; to: 0; duration: 260; easing.type: Easing.OutCubic }
                        }
                    }
                }
            }

            // thinking dots
            Text {
                visible: toast.busy && OrrinState.reply === ""
                text: "▸ " + "· · ·".slice(0, 1 + 2 * dots.n)
                color: Theme.dim
                font.family: Style.fonts.body; font.pixelSize: 13
                QtObject { id: dots; property int n: 0 }
                Timer { running: parent.visible && toast.visible; interval: 280; repeat: true; onTriggered: dots.n = (dots.n + 1) % 3 }
            }

            // ── the reply: all of it, scrolling with the speech ──
            Item {
                id: replyBox
                visible: toast.showReply
                width: parent.width
                // whatever the half-screen window has left after the header, transcript and tools
                readonly property int maxH: Math.round(toast.modelData.height * 0.4) - 2 * toast.pad - 22 - 8
                                            - (said.visible ? said.height + 8 : 0) - (toolCol.visible ? toolCol.height + 8 : 0) - 8
                height: visible ? Math.min(replyText.implicitHeight, Math.max(80, maxH)) : 0
                clip: true

                Flickable {
                    id: scroller
                    anchors.fill: parent
                    contentWidth: width; contentHeight: replyText.implicitHeight
                    interactive: false                       // the wheel is handled below (and pauses following)
                    property bool userScrolled: false
                    readonly property real maxY: Math.max(0, contentHeight - height)
                    Behavior on contentY { enabled: !wheel.active; NumberAnimation { duration: 420; easing.type: Easing.OutCubic } }

                    // the line being spoken
                    Rectangle {
                        id: lineMark
                        visible: toast.following
                        x: -8; width: replyText.width + 16
                        readonly property rect r: replyText.positionToRectangle(Math.max(0, Math.min(toast.pos, OrrinState.reply.length - 1)))
                        y: r.y - 2; height: r.height + 4
                        Behavior on y { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                        radius: 4
                        color: Qt.rgba(toast.accent.r, toast.accent.g, toast.accent.b, 0.10)
                        Rectangle { width: 2; height: parent.height; color: toast.accent; opacity: 0.8 }
                        onYChanged: if (toast.following && !scroller.userScrolled)
                            scroller.contentY = Math.max(0, Math.min(scroller.maxY, y - scroller.height * 0.35))
                    }

                    TextEdit {                                   // TextEdit: it can say where a character is
                        id: replyText
                        width: scroller.width
                        text: "<div style='line-height:115%'>" + toast.replyHtml + "</div>"
                        textFormat: TextEdit.RichText
                        readOnly: true; enabled: false           // display only: clicks go to the pop-up
                        cursorVisible: false; cursorDelegate: Item {}
                        color: toast.hot ? Qt.lighter(Theme.secondary, 1.15) : Theme.text
                        font.family: Style.fonts.body; font.pixelSize: toast.phase === "alert" ? 19 : 16
                        wrapMode: TextEdit.Wrap
                        layer.enabled: true
                        layer.effect: MultiEffect {
                            shadowEnabled: true; shadowColor: toast.accent
                            shadowBlur: 0.55; shadowOpacity: 0.55
                            shadowHorizontalOffset: 0; shadowVerticalOffset: 0
                        }
                    }
                }
                WheelHandler {
                    id: wheel
                    property bool active: false
                    onWheel: event => {
                        scroller.userScrolled = true;
                        active = true;
                        scroller.contentY = Math.max(0, Math.min(scroller.maxY, scroller.contentY - event.angleDelta.y * 0.6));
                        active = false;
                    }
                }
                // not spoken (voice off, typed): scroll at reading pace instead
                QtObject { id: readPace; property real pos: 0 }
                Timer {
                    running: toast.visible && toast.showReply && !toast.following && !scroller.userScrolled
                             && !OrrinState.hovered && scroller.maxY > 0
                    interval: 60; repeat: true
                    property int waited: 0
                    onRunningChanged: waited = 0
                    onTriggered: {
                        if ((waited += interval) < 2500) return;         // a moment to start reading at the top
                        scroller.contentY = Math.min(scroller.maxY, scroller.contentY + 0.9);
                    }
                }
                // more above / below
                Rectangle {
                    anchors.top: parent.top; width: parent.width; height: 18
                    visible: scroller.contentY > 2
                    gradient: Gradient { GradientStop { position: 0; color: Theme.d(0.7) } GradientStop { position: 1; color: "transparent" } }
                }
                Rectangle {
                    anchors.bottom: parent.bottom; width: parent.width; height: 22
                    visible: scroller.contentY < scroller.maxY - 2
                    gradient: Gradient { GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: Theme.d(0.7) } }
                    Text {
                        anchors.right: parent.right; anchors.bottom: parent.bottom
                        text: "▾"; color: toast.accent; font.family: Style.fonts.glyph; font.pixelSize: 12
                    }
                }
            }
        }
    }
}
