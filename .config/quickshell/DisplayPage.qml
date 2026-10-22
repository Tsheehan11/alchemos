// Settings → Display: layout mode (extend / mirror / one screen), per-screen
// resolution + refresh, scale, rotation, on/off and left-to-right order.
// The work (apply, 15 s keep-or-revert, saving) lives in Displays.qml; which profile
// (home desk, laptop only, the TV, …) the changes are saved to lives in Profiles.qml.
import QtQuick
import Quickshell
import Quickshell.Io

Column {
    id: dp
    spacing: 16

    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property string laptop: "eDP-1"

    property var mons: []          // hyprctl monitors all -j
    property var edits: ({})       // name → { mode, scale, transform, enabled }
    property var order: []         // names, left → right
    property string layout: "extend"
    property string selName: ""
    property string status: ""

    readonly property var sel: mons.find(m => m.name === selName) || null
    readonly property var selEdit: edits[selName] || null
    readonly property bool hasExternal: mons.some(m => m.name !== laptop)

    readonly property var scales: [1, 1.25, 1.5, 1.6, 2]
    readonly property var rotations: ["NORMAL", "90°", "180°", "270°"]
    readonly property var layoutNames: ({ extend: "EXTEND", mirror: "MIRROR", external: "EXTERNAL ONLY", laptop: "LAPTOP ONLY" })

    onVisibleChanged: if (visible) refresh()
    function refresh() { poll.running = true; }

    // Re-read after any change settles (revert, keep, plug/unplug)
    Connections {
        target: Displays
        function onPendingChanged() { if (!Displays.pending) later.restart(); }
    }
    Timer { id: later; interval: 1500; onTriggered: dp.refresh() }
    property alias later: later
    // A profile switch (hotplug) changes the screens under us
    Connections {
        target: Profiles
        function onKeyChanged() { later.restart(); }
    }

    Process {
        id: poll
        command: ["hyprctl", "monitors", "all", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                try { dp.load(JSON.parse(text)); } catch (e) { dp.status = "Couldn't read monitors"; }
            }
        }
    }

    function modeOf(m) { return m.width + "x" + m.height + "@" + Number(m.refreshRate).toFixed(2); }
    function modesOf(m) {
        const out = [];
        for (const s of (m.availableModes || [])) {
            const v = s.replace("Hz", "");
            if (out.indexOf(v) < 0) out.push(v);
        }
        const cur = dp.edits[m.name] ? dp.edits[m.name].mode : modeOf(m);
        if (out.indexOf(cur) < 0) out.unshift(cur);
        return out;
    }
    function keyOf(m) { return m.name === dp.laptop ? m.name : "desc:" + m.description; }
    function prettyMode(mode) {
        const [res, hz] = mode.split("@");
        return res.replace("x", " × ") + "  @ " + Math.round(Number(hz)) + " Hz";
    }
    function aspect(mode) {
        const [w, h] = mode.split("@")[0].split("x").map(Number);
        const r = w / h;
        const known = [[16 / 9, "16:9"], [16 / 10, "16:10"], [4 / 3, "4:3"], [5 / 4, "5:4"], [21 / 9, "21:9"], [32 / 9, "32:9"], [3 / 2, "3:2"]];
        let best = known[0];
        for (const k of known) if (Math.abs(k[0] - r) < Math.abs(best[0] - r)) best = k;
        return Math.abs(best[0] - r) < 0.03 ? best[1] : r.toFixed(2) + ":1";
    }

    function load(list) {
        dp.mons = list;
        const e = {};
        for (const m of list) {
            // A mirrored screen reports the source's geometry; use its own best mode instead
            const mirrored = m.mirrorOf !== undefined && m.mirrorOf !== "none" && m.mirrorOf !== "";
            e[m.name] = {
                mode: mirrored && m.availableModes && m.availableModes.length ? m.availableModes[0].replace("Hz", "") : modeOf(m),
                scale: m.scale, transform: m.transform,
                // Monitors switched off by "laptop only" still count as part of the arrangement
                enabled: m.name === dp.laptop ? true : !(m.disabled && Displays.active !== "laptop")
            };
        }
        dp.edits = e;
        dp.order = list.slice().sort((a, b) => a.x - b.x).map(m => m.name);
        dp.layout = Displays.active;
        if (!dp.sel) dp.selName = dp.order[0] || "";
    }

    function setEdit(name, patch) {
        const e = Object.assign({}, dp.edits);
        e[name] = Object.assign({}, e[name], patch);
        dp.edits = e;
    }
    function move(name, dir) {
        const o = dp.order.slice();
        const i = o.indexOf(name), j = i + dir;
        if (i < 0 || j < 0 || j >= o.length) return;
        o[i] = o[j]; o[j] = name;
        dp.order = o;
    }

    // Effective on-screen size (after scale + rotation)
    function sizeOf(name) {
        const ed = dp.edits[name];
        const [res] = ed.mode.split("@");
        let [w, h] = res.split("x").map(Number);
        if (ed.transform % 2 === 1) [w, h] = [h, w];
        return [Math.round(w / ed.scale), Math.round(h / ed.scale)];
    }
    function inLayout(name) { return !!dp.edits[name] && dp.edits[name].enabled; }
    function isOn(name) {
        if (!dp.edits[name]) return false;
        if (dp.layout === "external") return name !== dp.laptop && dp.edits[name].enabled;
        if (dp.layout === "laptop") return name === dp.laptop;
        return dp.edits[name].enabled;
    }
    // Left → right, vertically centred
    function positions() {
        const on = dp.order.filter(n => inLayout(n));
        const sizes = on.map(n => sizeOf(n));
        const maxH = Math.max(1, ...sizes.map(s => s[1]));
        const pos = {};
        let x = 0;
        on.forEach((n, i) => { pos[n] = [x, Math.round((maxH - sizes[i][1]) / 2)]; x += sizes[i][0]; });
        return pos;
    }
    // The saved arrangement (the layout mode is applied on top by Displays)
    function rules() {
        const pos = positions();
        return dp.order.map(n => {
            const m = dp.mons.find(x => x.name === n), ed = dp.edits[n];
            if (!inLayout(n)) return keyOf(m) + ",disable";
            return keyOf(m) + "," + ed.mode + "," + pos[n][0] + "x" + pos[n][1] + "," + ed.scale + ",transform," + ed.transform;
        });
    }

    function apply() {
        if (!dp.order.some(n => dp.isOn(n))) { dp.status = "At least one screen has to stay on"; return; }
        dp.status = "";
        Displays.apply(dp.rules(), dp.layout);
    }

    // ── Active profile ──
    Text { text: "DISPLAY PROFILE"; color: Theme.dim; font.family: dp.mono; font.pixelSize: 11; font.letterSpacing: 3 }
    Column {
        width: parent.width
        spacing: 6
        Text {
            width: parent.width; elide: Text.ElideRight
            text: Profiles.name + (Profiles.saved ? "" : "  ·  DEFAULTS")
            color: Theme.primary; font.family: dp.mono; font.pixelSize: 15; font.letterSpacing: 2
        }
        Text {
            width: parent.width; wrapMode: Text.WordWrap
            color: Theme.textSoft; font.family: dp.mono; font.pixelSize: 12
            text: {
                const p = Profiles.current;
                if (!p) return "";
                return dp.layoutNames[p.layout] + "  ·  JARVIS " + (p.jarvis ? "ON" : "OFF")
                    + "  ·  STRIP " + String(p.govee).toUpperCase() + "  ·  BATTERY SAVER " + (p.saver ? "ON" : "OFF");
            }
        }
        Text {
            width: parent.width; wrapMode: Text.WordWrap
            color: Theme.faint; font.family: dp.mono; font.pixelSize: 11
            text: "Chosen by what's plugged in, and applied by itself when that changes. APPLY + KEEP below saves into this profile only."
        }
    }
    Row {
        spacing: 10
        SmallButton { text: "SAVE CURRENT AS THIS PROFILE"; onClicked: Profiles.saveCurrent() }
        ConfirmButton { label: "RESET PROFILE"; onConfirmed: { Profiles.reset(); dp.later.restart(); } }
    }
    Text {
        visible: Profiles.status !== ""
        text: Profiles.status
        color: Theme.secondary; font.family: dp.mono; font.pixelSize: 12
    }

    // ── Layout mode ──
    Text { text: "WHAT THE SCREENS SHOW"; color: Theme.dim; font.family: dp.mono; font.pixelSize: 11; font.letterSpacing: 3 }
    Row {
        spacing: 10
        visible: dp.hasExternal
        Repeater {
            model: ["extend", "mirror", "external", "laptop"]
            delegate: SmallButton {
                required property var modelData
                text: dp.layoutNames[modelData]
                active: dp.layout === modelData
                onClicked: dp.layout = modelData
            }
        }
    }
    Text {
        width: parent.width
        wrapMode: Text.WordWrap
        color: Theme.textSoft; font.family: dp.mono; font.pixelSize: 12
        text: !dp.hasExternal ? "Only the laptop screen is connected. Plug in the monitors to get extend / mirror / external-only."
            : dp.layout === "extend" ? "Every screen is its own desktop. MOVE LEFT / RIGHT below sets the order."
            : dp.layout === "mirror" ? "Every screen shows the main monitor (same picture everywhere)."
            : dp.layout === "external" ? "Laptop screen turns off while docked — handy with the lid closed. It comes back the moment you unplug."
            : "Monitors turn off, laptop screen only."
    }

    // ── Arrangement preview (click a screen to edit it) ──
    Item {
        id: preview
        width: parent.width; height: 200
        readonly property var pos: dp.positions()
        readonly property var on: dp.order.filter(n => dp.isOn(n))
        readonly property bool mirror: dp.layout === "mirror"
        readonly property real totalW: Math.max(1, ...on.map(n => (mirror ? 0 : (pos[n] ? pos[n][0] : 0)) + dp.sizeOf(n)[0]))
        readonly property real totalH: Math.max(1, ...on.map(n => (mirror ? 0 : (pos[n] ? pos[n][1] : 0)) + dp.sizeOf(n)[1]))
        readonly property real k: Math.min((width - 40) / totalW, (height - 40) / totalH)

        Rectangle { anchors.fill: parent; color: Theme.d(0.5); border.color: Theme.p(0.15) }

        Repeater {
            model: dp.order
            delegate: Rectangle {
                id: box
                required property var modelData
                readonly property bool on: dp.isOn(modelData)
                readonly property var sz: dp.edits[modelData] ? dp.sizeOf(modelData) : [0, 0]
                readonly property var pp: preview.pos[modelData] || [0, 0]
                readonly property int stack: preview.on.indexOf(modelData)
                visible: on
                x: 20 + (preview.width - 40 - preview.totalW * preview.k) / 2 + (preview.mirror ? stack * 10 : pp[0] * preview.k)
                y: 20 + (preview.height - 40 - preview.totalH * preview.k) / 2 + (preview.mirror ? stack * 10 : pp[1] * preview.k)
                width: Math.max(10, sz[0] * preview.k - 4); height: Math.max(10, sz[1] * preview.k - 4)
                color: dp.selName === modelData ? Theme.p(0.22) : Theme.d(0.92)
                border.color: dp.selName === modelData ? Theme.primary : Theme.p(0.45)
                border.width: dp.selName === modelData ? 2 : 1
                Behavior on x { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                Column {
                    anchors.centerIn: parent
                    spacing: 2
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: box.modelData === dp.laptop ? "LAPTOP" : "MONITOR " + (dp.order.filter(n => n !== dp.laptop).indexOf(box.modelData) + 1); color: Theme.text; font.family: dp.mono; font.pixelSize: 12 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: dp.edits[box.modelData] ? dp.edits[box.modelData].mode.split("@")[0] + " · " + dp.aspect(dp.edits[box.modelData].mode) : ""; color: Theme.dim; font.family: dp.mono; font.pixelSize: 10 }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: dp.selName = box.modelData }
            }
        }
        Text {
            anchors.bottom: parent.bottom; anchors.right: parent.right; anchors.margins: 8
            text: "CLICK A SCREEN TO EDIT IT"; color: Theme.faint; font.family: dp.mono; font.pixelSize: 9; font.letterSpacing: 2
        }
    }

    // ── Selected screen ──
    Column {
        width: parent.width
        spacing: 10
        visible: dp.sel !== null && dp.selEdit !== null

        Text {
            text: dp.sel ? (dp.sel.name === dp.laptop ? "LAPTOP SCREEN" : dp.sel.description.toUpperCase()) + "  ·  " + dp.sel.name : ""
            color: Theme.primary; font.family: dp.mono; font.pixelSize: 13; font.letterSpacing: 2
            width: parent.width; elide: Text.ElideRight
        }
        Toggle {
            width: parent.width
            visible: dp.sel !== null && dp.sel.name !== dp.laptop && dp.layout !== "laptop"
            label: "Use this monitor"
            hint: "Off = this monitor stays dark"
            checked: dp.selEdit ? dp.selEdit.enabled : false
            onToggled: dp.setEdit(dp.selName, { enabled: !dp.selEdit.enabled })
        }
        Stepper {
            width: parent.width
            label: "Resolution & refresh"
            hint: dp.selEdit ? "Aspect ratio " + dp.aspect(dp.selEdit.mode) + " — lower resolution = bigger + softer" : ""
            valueText: dp.selEdit ? dp.prettyMode(dp.selEdit.mode) : ""
            onDec: { const l = dp.modesOf(dp.sel); dp.setEdit(dp.selName, { mode: l[Math.min(l.length - 1, l.indexOf(dp.selEdit.mode) + 1)] }); }
            onInc: { const l = dp.modesOf(dp.sel); dp.setEdit(dp.selName, { mode: l[Math.max(0, l.indexOf(dp.selEdit.mode) - 1)] }); }
        }
        Stepper {
            width: parent.width
            label: "Scale"
            hint: "Bigger = larger text and windows, same sharpness"
            valueText: dp.selEdit ? Math.round(dp.selEdit.scale * 100) + "%" : ""
            onDec: { const i = dp.scales.indexOf(dp.selEdit.scale); dp.setEdit(dp.selName, { scale: dp.scales[Math.max(0, (i < 0 ? 1 : i) - 1)] }); }
            onInc: { const i = dp.scales.indexOf(dp.selEdit.scale); dp.setEdit(dp.selName, { scale: dp.scales[Math.min(dp.scales.length - 1, i + 1)] }); }
        }
        Stepper {
            width: parent.width
            label: "Rotation"
            hint: "90° / 270° for a vertical monitor"
            valueText: dp.selEdit ? dp.rotations[dp.selEdit.transform % 4] : ""
            onDec: dp.setEdit(dp.selName, { transform: (dp.selEdit.transform + 3) % 4 })
            onInc: dp.setEdit(dp.selName, { transform: (dp.selEdit.transform + 1) % 4 })
        }
        Row {
            spacing: 10
            visible: dp.layout === "extend" || dp.layout === "external"
            SmallButton { text: "◀ MOVE LEFT"; onClicked: dp.move(dp.selName, -1) }
            SmallButton { text: "MOVE RIGHT ▶"; onClicked: dp.move(dp.selName, 1) }
        }
    }

    // ── Apply ──
    Row {
        spacing: 10
        SmallButton { text: Displays.pending ? "KEEP (" + Displays.countdown + ")" : "APPLY"; active: true; onClicked: Displays.pending ? Displays.keep() : dp.apply() }
        SmallButton { visible: Displays.pending; text: "REVERT"; onClicked: Displays.revert() }
        SmallButton { visible: !Displays.pending; text: "UNDO EDITS"; onClicked: dp.refresh() }
    }
    Text {
        visible: dp.status !== ""
        text: dp.status
        color: Theme.secondary; font.family: dp.mono; font.pixelSize: 12
    }
}
