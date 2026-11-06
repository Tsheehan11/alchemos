// skincheck: renders the skin's components and the shared primitives offscreen, one PNG each, then
// quits. Run by check_skins.sh in a temp copy of the HUD with mocks/ over the state singletons.
//   SKINCHECK_SKIN  the skin to load      SKINCHECK_OUT  where the PNGs go
import QtQuick
import Quickshell
import Quickshell.Wayland

ShellRoot {
    id: root
    readonly property string out: Quickshell.env("SKINCHECK_OUT")
    function comp(name) {
        if (typeof Skin.component === "function") return Skin.component(name);
        return name === "clock" ? Skin.clockUrl : name === "scene" ? Skin.sceneUrl : null;     // before skins had component()
    }
    // [name, w, h, component url or inline Component, props]
    readonly property var gallery: [
        ["clock", 480, 560, root.comp("clock"), { t: 0, animated: false }],
        ["scene-shut", 1280, 800, root.comp("scene"), { doorP: 1, isMain: true }],
        ["scene-other", 1280, 800, root.comp("scene"), { doorP: 1, isMain: false }],
        ["scene-opening", 1280, 800, root.comp("scene"), { doorP: 0.6, msgP: 1, message: "WELCOME", submessage: "SKINCHECK", spin: 30, ignite: 0.5 }],
        ["transition", 900, 700, root.comp("transition"), { p: 0.5 }],
        ["primitives", 760, 560, primitives, {}]
    ]
    property int i: -1
    property string loading: ""
    function next() {
        i++;
        if (i >= gallery.length) { console.log("SKINCHECK done"); Qt.quit(); return; }
        const g = gallery[i];
        if (!g[3] || (Quickshell.env("SKINCHECK_SKIP") || "").split(",").indexOf(g[0]) >= 0) { console.log("SKINCHECK skip " + g[0]); next(); return; }
        stage.width = g[1]; stage.height = g[2];
        root.loading = g[0];
        ld.props = g[4];
        if (typeof g[3].createObject === "function") { ld.source = ""; ld.sourceComponent = g[3]; }
        else { ld.sourceComponent = undefined; ld.source = g[3]; }
        settle.restart();
    }
    Timer { interval: 400; running: true; onTriggered: root.next() }      // let the skin list settle first
    Timer {
        id: settle; interval: 700
        onTriggered: {
            if (ld.status === Loader.Error || !ld.item) { console.log("SKINCHECK FAIL " + root.loading + ": did not load"); root.next(); return; }
            stage.grabToImage(r => { r.saveToFile(root.out + "/" + root.loading + ".png"); console.log("SKINCHECK ok " + root.loading); root.next(); });
        }
    }

    Component {
        id: primitives
        Item {
            Column {
                x: 20; y: 20; width: 340; spacing: 10
                HudFrame { width: 340; height: 120; title: "FRAME"; detail: "detail" }
                SmallButton { text: "BUTTON" }
                SmallButton { text: "ACTIVE"; active: true }
                Toggle { width: 340; label: "Toggle on"; hint: "a hint"; checked: true }
                Toggle { width: 340; label: "Toggle off"; hint: "a hint"; checked: false }
                Stepper { width: 340; label: "Stepper"; valueText: "VALUE" }
                Slider { width: 340; label: "Slider"; value: 0.6 }
            }
            Column {
                x: 390; y: 20; width: 340; spacing: 12
                HoloFrame { width: 340; height: 140; still: true; t: 0 }
                HoloBar { width: 340; height: 14; value: 0.6 }
                HoloButton { text: "HOLO BUTTON" }
                ConfirmButton { label: "CONFIRM" }
                Graph { width: 340; height: 80; values: [0.1, 0.3, 0.2, 0.6, 0.4, 0.8, 0.5, 0.7, 0.3, 0.9] }
                Ring { radius: 40; thickness: 6; value: 0.65; gauge: true }
            }
        }
    }

    PanelWindow {
        WlrLayershell.layer: WlrLayer.Background
        WlrLayershell.namespace: "skincheck"
        exclusionMode: ExclusionMode.Ignore
        anchors { top: true; left: true }
        implicitWidth: 1; implicitHeight: 1
        mask: Region {}
        color: "transparent"
        Rectangle {
            id: stage
            x: 1
            color: Theme.bg
            Loader {
                id: ld
                anchors.fill: parent
                property var props: ({})
                onLoaded: { for (const k in props) if (k in item) item[k] = props[k]; }
            }
        }
    }
}
