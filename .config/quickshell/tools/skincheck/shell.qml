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
        ["primitives", 760, 560, primitives, {}],
        // the HUD's own windows (pin.py makes them Items): [.., props at creation, { arm, settle }]
        ["background", 1600, 1000, "GridBackground.qml", { modelData: root.screenOf(1600, 1000) }, {}],
        ["background-live", 1600, 1000, "GridBackground.qml", { modelData: root.screenOf(1600, 1000) },
            { arm: () => { Perf.time = 13.7; Perf.liveAll = true; }, settle: 1100 }],
        ["bar", 1600, 34, "Bar.qml", { modelData: root.screenOf(1600, 34) }, {}],
        ["launcher", 1600, 940, "Launcher.qml", { modelData: root.screenOf(1600, 940) }, { arm: () => LauncherState.open = true, settle: 1500 }],
        ["launcher-alt", 1600, 940, "Launcher.qml", { modelData: root.screenOf(1600, 940) },
            { arm: () => { Theme.presetIndex = Math.min(5, Skin.presets.length - 1); LauncherState.open = true; }, settle: 1500 }],
        ["carousel", 1600, 1000, "Overview.qml", { modelData: root.screenOf(1600, 1000) }, { arm: () => LauncherState.overviewOpen = true, settle: 1200 }],
        ["osd", 420, 96, "Osd.qml", { modelData: root.screenOf(420, 96) }, {}],
        ["control", 900, 1000, "ControlCenter.qml", { modelData: root.screenOf(900, 1000), wifiOn: true, ssid: "HOME-5G", btOn: true, brightness: 0.7, powerProfile: "balanced" }, { arm: () => LauncherState.controlOpen = true }]
    ]
    function screenOf(w, h) { return { name: "DP-1", x: 0, y: 0, width: w, height: h }; }
    // put back what an entry's arm() changed
    function disarm() {
        Perf.liveAll = false; Perf.time = 0; Theme.presetIndex = 0;
        LauncherState.open = false; LauncherState.overviewOpen = false; LauncherState.controlOpen = false;
    }
    property int i: -1
    property string loading: ""
    function next() {
        i++;
        if (i >= gallery.length) { root.checkNamer(); console.log("SKINCHECK done"); Qt.quit(); return; }
        const g = gallery[i];
        if (!g[3] || (Quickshell.env("SKINCHECK_SKIP") || "").split(",").indexOf(g[0]) >= 0) { console.log("SKINCHECK skip " + g[0]); next(); return; }
        root.disarm();
        stage.width = g[1]; stage.height = g[2];
        root.loading = g[0];
        const opt = g[5];
        settle.interval = opt && opt.settle ? opt.settle : 700;
        if (opt) {                    // a window: its required properties at creation, then arm() opens it
            ld.props = ({});
            ld.sourceComponent = undefined; ld.source = "";
            ld.setSource(Qt.resolvedUrl(g[3]), g[4]);
            if (opt.arm) Qt.callLater(opt.arm);
        } else {
            ld.props = g[4];
            if (typeof g[3].createObject === "function") { ld.source = ""; ld.sourceComponent = g[3]; }
            else { ld.sourceComponent = undefined; ld.source = g[3]; }
        }
        settle.restart();
    }
    Timer { interval: 400; running: true; onTriggered: root.next() }
    // the skin's preset namer: a suggestion for every colour, ≤ 14 characters, never a taken name
    function checkNamer() {
        if (typeof Namer === "undefined") return;
        const taken = Skin.presets.map(p => p.name).concat(Object.keys(Skin.aliases));
        for (const c of ["#d23a2a", "#2f6fd8", "#3fbf6a", "#ff6b8a", "#c8ccd2", "#9a5cff", "#ffc04a", "#1a1c22"]) {
            const s = Namer.suggest(c, "#ffb000", taken);
            const bad = !s.length ? "no suggestion" : s.find(x => x.name.length > 14 || taken.indexOf(x.name) >= 0);
            if (bad) { console.log("SKINCHECK FAIL namer " + c + ": " + JSON.stringify(bad)); return; }
        }
        console.log("SKINCHECK ok namer");
    }      // let the skin list settle first
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
        WlrLayershell.layer: WlrLayer.Overlay       // Background gets no frames under a fullscreen window
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
