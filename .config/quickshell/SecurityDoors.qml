// Blast doors that close over every screen when locking / shutting down and
// slide open onto the desktop after unlocking. Driven by LockState.
// Always click-through, so it can never trap you.
import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Io

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
    SkinScene {
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

    // ── This screen's lock screen background ──
    // A picture of these doors, shut (LockState.bgPath). The stamp next to it records the key it
    // was drawn with; when the theme, size or role changes (or it's stale at startup) the doors
    // are redrawn offscreen, without showing them. (The window is unmapped while the doors are
    // open, so the size comes from the screen.)
    readonly property int screenW: dw.modelData.width
    readonly property int screenH: dw.modelData.height
    readonly property string bgPath: LockState.bgPath(dw.modelData.name)
    readonly property string bgKey: LockState.bgKey(screenW + "x" + screenH, dw.isMain)
    readonly property string savedKey: savedKeyOverride !== "" ? savedKeyOverride : stamp.text().trim()
    property string savedKeyOverride: ""
    FileView { id: stamp; path: dw.bgPath + ".key"; blockLoading: true; printErrors: false }
    onBgPathChanged: savedKeyOverride = ""

    // Live captures write straight to the file (hyprlock starts right after);
    // offscreen renders go through a temp file so a lock never reads half a PNG.
    function saveBg(result, key, atomic) {
        const target = atomic ? dw.bgPath + ".tmp.png" : dw.bgPath;
        if (!result.saveToFile(target)) { console.warn("lock bg: could not save " + target); return; }
        dw.savedKeyOverride = key;
        Quickshell.execDetached(["sh", "-c", (atomic ? 'mv -f "$1" "$2" && ' : "") + 'printf "%s\\n" "$3" > "$2.key"',
            "sh", target, dw.bgPath, key]);
    }

    // Super+L: the doors are shut on every screen right now. A picture that's still stale
    // (e.g. the theme changed a moment ago) is captured from them as they are; current ones
    // are left alone, since rewriting a picture just before hyprlock starts made it show
    // the lock screen's widgets on a blank background for a few frames.
    Connections {
        target: LockState
        function onCaptureRequested() {
            const key = dw.bgKey;
            if (key === dw.savedKey) { LockState.captureDone(); return; }
            if (!scene.grabToImage(function(result) { dw.saveBg(result, key, false); LockState.captureDone(); }))
                LockState.captureDone();
        }
    }

    function checkBg() {
        if (dw.screenW > 0 && Theme.loaded && dw.bgKey !== dw.savedKey) bgCheck.restart();
    }
    onBgKeyChanged: checkBg()
    onSavedKeyChanged: checkBg()
    Connections { target: Theme; function onLoadedChanged() { dw.checkBg(); } }
    Component.onCompleted: checkBg()
    Timer {
        id: bgCheck
        interval: 800     // let a burst of colour / monitor changes settle
        onTriggered: if (dw.bgKey !== dw.savedKey) bgRender.active = true
    }
    // The window is 1×1 and the scene sits just outside it, so nothing reaches the screen;
    // grabToImage renders the whole scene regardless.
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

            SkinScene {
                id: still
                x: 1     // outside the 1×1 window
                width: dw.screenW; height: dw.screenH
                isMain: dw.isMain
            }
            Timer {
                interval: 150; running: still.painted   // a few frames after the canvases paint
                onTriggered: {
                    const key = dw.bgKey;
                    still.grabToImage(function(result) {
                        dw.saveBg(result, key, true);
                        bgRender.active = false;
                        dw.checkBg();     // changed mid-render? go again
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
