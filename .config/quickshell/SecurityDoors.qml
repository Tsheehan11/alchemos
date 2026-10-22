// Blast doors that close over every screen when locking / shutting down and
// slide open onto the desktop after unlocking. Driven by LockState.
// Always click-through, so it can never trap you.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: dw
    required property var modelData
    screen: modelData

    visible: LockState.doors !== "open"

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "stark-doors"
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }
    mask: Region {}
    color: "transparent"

    readonly property bool isMain: Roles.role(modelData) === "main"

    // Everything that makes up the closed-doors picture (captured for the lock screen)
    DoorScene {
        id: scene
        anchors.fill: parent
        isMain: dw.isMain
        doorP: Math.min(1.05, LockState.doorPos)
        emblemOpacity: Math.max(0, Math.min(1, (LockState.doorPos - 0.85) / 0.15)) * (1 - LockState.crt)
        message: LockState.message
        submessage: LockState.submessage
        msgP: LockState.msgP
        spin: LockState.spin
    }

    // On the main screen, save a picture of the shut doors → becomes the lock screen's background,
    // so the lock screen lines up exactly with the doors.
    Connections {
        target: LockState
        enabled: dw.isMain
        function onCaptureRequested(path) {
            scene.grabToImage(function(result) {
                LockState.saveBg(result, dw.bgKey, false);
                LockState.captureDone();
            });
        }
    }

    // Theme or screen size changed (or the picture is stale at startup): redraw the shut doors
    // offscreen, without showing them. The window is 1×1 and the scene sits just outside it, so
    // nothing reaches the screen; grabToImage renders the whole scene regardless.
    // (the window itself is unmapped while the doors are open, so size comes from the screen)
    readonly property int screenW: dw.modelData.width
    readonly property int screenH: dw.modelData.height
    readonly property string bgKey: LockState.bgKey(screenW + "x" + screenH)
    function checkBg() {
        if (dw.isMain && dw.screenW > 0 && Theme.loaded && dw.bgKey !== LockState.savedBgKey) bgCheck.restart();
    }
    onBgKeyChanged: checkBg()
    onIsMainChanged: checkBg()
    Connections { target: Theme; function onLoadedChanged() { dw.checkBg(); } }
    Component.onCompleted: checkBg()
    Timer {
        id: bgCheck
        interval: 800     // let a burst of colour changes settle
        onTriggered: if (dw.isMain && dw.bgKey !== LockState.savedBgKey) bgRender.active = true
    }
    LazyLoader {
        id: bgRender
        active: false
        PanelWindow {
            screen: dw.modelData
            WlrLayershell.layer: WlrLayer.Background
            WlrLayershell.namespace: "stark-lock-render"
            exclusionMode: ExclusionMode.Ignore
            anchors { top: true; left: true }
            implicitWidth: 1; implicitHeight: 1
            mask: Region {}
            color: "transparent"

            DoorScene {
                id: still
                x: 1     // outside the 1×1 window
                width: dw.screenW; height: dw.screenH
                isMain: true
            }
            Timer {
                interval: 150; running: still.painted   // a few frames after the canvases paint
                onTriggered: {
                    const key = dw.bgKey;
                    still.grabToImage(function(result) {
                        LockState.saveBg(result, key, true);
                        bgRender.active = false;
                        dw.checkBg();     // colours changed mid-render? go again
                    });
                }
            }
        }
    }

    // Power-off "CRT collapse": the picture squeezes to a line, then a dot, then black
    Rectangle {
        anchors.fill: parent
        visible: LockState.crt > 0
        color: "black"
        opacity: Math.min(1, LockState.crt * 3)
    }
    Rectangle {
        visible: LockState.crt > 0 && LockState.crt < 1
        anchors.centerIn: parent
        readonly property real c: LockState.crt
        width: c < 0.55 ? dw.width : Math.max(4, dw.width * (1 - (c - 0.55) / 0.35))
        height: c < 0.55 ? Math.max(3, dw.height * (1 - c / 0.55)) : 3
        radius: c > 0.85 ? 2 : 0
        color: Theme.text
        opacity: c > 0.9 ? (1 - c) * 10 : 0.95
    }
}
