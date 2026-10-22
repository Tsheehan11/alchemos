// Settings → LAUNCHER: the apps on the Super+Space radial launcher (LauncherApps.qml).
// Changes save straight to settings.json and the launcher redraws live.
import QtQuick
import Quickshell

Column {
    id: lp
    spacing: 14
    readonly property string mono: "JetBrainsMono Nerd Font"
    property string editing: ""        // id of the app whose edit panel is open
    property string adding: ""         // "" | "app" | "custom"
    property string note: ""           // last result, shown under the buttons
    signal releaseFocus()              // hand keyboard focus back to the settings window

    onVisibleChanged: if (!visible) { editing = ""; adding = ""; note = ""; }

    function startAdding(kind) {
        editing = "";
        note = "";
        adding = adding === kind ? "" : kind;
        if (adding === "app") { search.text = ""; search.focusInput(); }
        if (adding === "custom") { cName.text = ""; cExec.text = ""; cIcon.text = ""; cExec.focusInput(); }
        if (adding === "") releaseFocus();
    }
    function finishAdding() { adding = ""; releaseFocus(); }
    function tierText(i) {
        return (i % 2 === 0 ? "INNER" : "OUTER") + " · BRANCH " + (Math.floor(i / 2) + 1) + (i < 10 ? " · KEY " + (i + 1) % 10 : "");
    }
    function detailText(a) {
        if (a.kind === "desktop") return a.entry ? "app · " + a.desktopId : "app not installed · " + a.desktopId;
        if (a.kind === "action") return "built-in · " + (a.exec === "@control" ? "opens the control center" : a.exec === "@lock" ? "locks the screen" : "unknown action");
        return a.available ? a.exec : "command not found · " + a.exec;
    }

    // ── Header ──
    Item {
        width: parent.width; height: 22
        Text { text: "RADIAL LAUNCHER"; color: Theme.dim; font.family: lp.mono; font.pixelSize: 11; font.letterSpacing: 3; anchors.verticalCenter: parent.verticalCenter }
        Text {
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            text: LauncherApps.list.length + " / " + LauncherApps.maxApps + " APPS"
            color: LauncherApps.full ? Theme.secondary : Theme.dim
            font.family: lp.mono; font.pixelSize: 11; font.letterSpacing: 2
        }
    }
    Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: "Super + Space. Apps fill the ring in launch order, in pairs: the first of each pair sits by the core, the second flows out from it. Keys 1–9 and 0 launch the first ten."
        color: Theme.faint; font.family: lp.mono; font.pixelSize: 11
    }

    // ── The ring, in launch order ──
    Column {
        width: parent.width
        spacing: 4
        Repeater {
            model: LauncherApps.list
            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                readonly property bool open: lp.editing === modelData.id
                readonly property bool inner: index % 2 === 0
                width: parent.width
                height: head.height + (open ? editor.height + 12 : 0)
                color: open ? Theme.p(0.1) : (rowMa.containsMouse ? Theme.p(0.05) : "transparent")
                border.color: open ? Theme.p(0.55) : Theme.p(0.14)
                Behavior on height { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                clip: true

                MouseArea { id: rowMa; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }

                Item {
                    id: head
                    width: parent.width; height: 56

                    // Launch number + ring position
                    Column {
                        id: pos
                        x: 12; width: 150
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Text {
                            text: String(row.index + 1).padStart(2, "0")
                            color: row.inner ? Theme.primary : Theme.secondary
                            font.family: lp.mono; font.pixelSize: 13; font.letterSpacing: 1
                        }
                        Text { text: lp.tierText(row.index); color: Theme.faint; font.family: lp.mono; font.pixelSize: 9; font.letterSpacing: 1 }
                    }

                    // Icon (or initial)
                    Item {
                        id: ico
                        anchors.left: pos.right; anchors.verticalCenter: parent.verticalCenter
                        width: 30; height: 30
                        opacity: row.modelData.available ? 1 : 0.4
                        Image {
                            anchors.fill: parent
                            source: row.modelData.icon
                            sourceSize: Qt.size(64, 64)
                            visible: row.modelData.icon !== "" && status === Image.Ready
                            smooth: true
                        }
                        Rectangle {
                            anchors.fill: parent
                            visible: row.modelData.icon === ""
                            color: "transparent"
                            border.color: row.inner ? Theme.p(0.6) : Theme.s(0.6)
                            Text {
                                anchors.centerIn: parent
                                text: (row.modelData.name || "?").charAt(0).toUpperCase()
                                color: row.inner ? Theme.primary : Theme.secondary
                                font.family: lp.mono; font.pixelSize: 14
                            }
                        }
                    }

                    // Name + what it runs
                    Column {
                        anchors.left: ico.right; anchors.leftMargin: 14
                        anchors.right: buttons.left; anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        Row {
                            spacing: 10
                            Text {
                                text: row.modelData.name
                                color: row.modelData.available ? Theme.text : Theme.faint
                                font.family: lp.mono; font.pixelSize: 14; font.letterSpacing: 1
                                font.capitalization: Font.AllUppercase
                            }
                            Text {
                                visible: row.inner && row.modelData.group !== ""
                                text: "◆ " + row.modelData.group
                                color: Theme.dim
                                font.family: lp.mono; font.pixelSize: 10; font.letterSpacing: 2
                                font.capitalization: Font.AllUppercase
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                visible: !row.modelData.available
                                text: "MISSING"
                                color: Theme.secondary
                                font.family: lp.mono; font.pixelSize: 10; font.letterSpacing: 2
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                        Text {
                            width: parent.width
                            elide: Text.ElideRight
                            text: lp.detailText(row.modelData)
                            color: Theme.dim
                            font.family: lp.mono; font.pixelSize: 11
                        }
                    }

                    Row {
                        id: buttons
                        anchors.right: parent.right; anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6
                        SmallButton {
                            text: "▲"
                            opacity: row.index > 0 ? 1 : 0.25
                            onClicked: if (row.index > 0) LauncherApps.move(row.modelData.id, -1)
                        }
                        SmallButton {
                            text: "▼"
                            opacity: row.index < LauncherApps.list.length - 1 ? 1 : 0.25
                            onClicked: if (row.index < LauncherApps.list.length - 1) LauncherApps.move(row.modelData.id, 1)
                        }
                        SmallButton {
                            text: row.open ? "CLOSE" : "EDIT"
                            active: row.open
                            onClicked: {
                                lp.adding = "";
                                lp.note = "";
                                if (row.open) { lp.editing = ""; lp.releaseFocus(); return; }
                                eName.text = row.modelData.name;
                                eExec.text = row.modelData.exec;
                                eIcon.text = row.modelData.iconName;
                                eGroup.text = row.modelData.group;
                                lp.editing = row.modelData.id;
                                eName.focusInput();
                            }
                        }
                        ConfirmButton {
                            label: "REMOVE"
                            width: 96
                            visible: LauncherApps.list.length > 1       // the ring needs at least one app
                            onConfirmed: {
                                if (row.open) lp.editing = "";
                                lp.note = "✓ Removed " + row.modelData.name;
                                LauncherApps.remove(row.modelData.id);
                            }
                        }
                    }
                }

                // ── Edit panel ──
                Column {
                    id: editor
                    anchors.top: head.bottom
                    x: 12 + 150
                    width: parent.width - x - 12
                    spacing: 8
                    visible: row.open
                    function commit() {
                        const f = { name: eName.text.trim() || row.modelData.name, icon: eIcon.text.trim(), group: eGroup.text.trim() };
                        if (row.modelData.kind === "command") {
                            if (eExec.text.trim() === "") { lp.note = "✕ The command can't be empty"; return; }
                            f.exec = eExec.text.trim();
                        }
                        LauncherApps.update(row.modelData.id, f);
                        lp.note = "✓ Saved " + f.name.toUpperCase();
                        lp.editing = "";
                        lp.releaseFocus();
                    }
                    function cancel() { lp.editing = ""; lp.releaseFocus(); }

                    Row {
                        spacing: 10
                        Text { width: 70; text: "NAME"; color: Theme.dim; font.family: lp.mono; font.pixelSize: 11; font.letterSpacing: 2; anchors.verticalCenter: parent.verticalCenter }
                        HudInput { id: eName; width: 220; maximumLength: 16; placeholder: "LABEL"; onAccepted: editor.commit(); onCancelled: editor.cancel() }
                        Text { width: 60; text: "BRANCH"; color: Theme.dim; font.family: lp.mono; font.pixelSize: 11; font.letterSpacing: 2; anchors.verticalCenter: parent.verticalCenter }
                        HudInput { id: eGroup; width: 120; maximumLength: 8; placeholder: "e.g. DEV"; onAccepted: editor.commit(); onCancelled: editor.cancel() }
                    }
                    Row {
                        spacing: 10
                        visible: row.modelData.kind === "command"
                        Text { width: 70; text: "COMMAND"; color: Theme.dim; font.family: lp.mono; font.pixelSize: 11; font.letterSpacing: 2; anchors.verticalCenter: parent.verticalCenter }
                        HudInput { id: eExec; width: editor.width - 80; placeholder: "kitty -e btop"; onAccepted: editor.commit(); onCancelled: editor.cancel() }
                    }
                    Row {
                        spacing: 10
                        Text { width: 70; text: "ICON"; color: Theme.dim; font.family: lp.mono; font.pixelSize: 11; font.letterSpacing: 2; anchors.verticalCenter: parent.verticalCenter }
                        HudInput {
                            id: eIcon; width: 360
                            placeholder: row.modelData.kind === "desktop" ? "blank = the app's own icon" : "theme icon name or file path"
                            onAccepted: editor.commit(); onCancelled: editor.cancel()
                        }
                        Image {
                            width: 28; height: 28; anchors.verticalCenter: parent.verticalCenter
                            sourceSize: Qt.size(64, 64)
                            source: LauncherApps.iconSource(eIcon.text.trim() || (row.modelData.entry ? row.modelData.entry.icon : ""))
                        }
                    }
                    Text {
                        visible: row.inner
                        text: "BRANCH is the label drawn on this app's branch (only apps on the inner ring show one)."
                        color: Theme.faint; font.family: lp.mono; font.pixelSize: 10
                    }
                    Row {
                        spacing: 10
                        SmallButton { text: "SAVE"; onClicked: editor.commit() }
                        SmallButton { text: "CANCEL"; onClicked: editor.cancel() }
                    }
                }
            }
        }
    }

    // ── Add / reset ──
    Row {
        spacing: 10
        SmallButton { text: "+ ADD APP"; active: lp.adding === "app"; opacity: LauncherApps.full ? 0.35 : 1; onClicked: if (!LauncherApps.full) lp.startAdding("app") }
        SmallButton { text: "+ ADD CUSTOM"; active: lp.adding === "custom"; opacity: LauncherApps.full ? 0.35 : 1; onClicked: if (!LauncherApps.full) lp.startAdding("custom") }
        ConfirmButton {
            label: "RESET TO DEFAULTS"
            width: 180
            onConfirmed: { lp.editing = ""; lp.adding = ""; LauncherApps.reset(); lp.note = "✓ Launcher reset to the default apps"; }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            visible: LauncherApps.full
            text: "Ring is full (" + LauncherApps.maxApps + " max) — remove one to add another"
            color: Theme.secondary; font.family: lp.mono; font.pixelSize: 11
        }
    }
    Text {
        visible: lp.note !== ""
        text: lp.note
        color: lp.note.startsWith("✕") ? Theme.secondary : Theme.primary
        font.family: lp.mono; font.pixelSize: 12
    }

    // ── Add app: search installed apps ──
    Column {
        id: picker
        visible: lp.adding === "app"
        width: parent.width
        spacing: 6
        readonly property var added: LauncherApps.list.map(a => a.desktopId).filter(d => d)
        readonly property var results: {
            const q = search.text.toLowerCase().trim();
            const all = DesktopEntries.applications.values.filter(e => !e.noDisplay);
            const score = e => {
                const n = (e.name || "").toLowerCase(), g = (e.genericName || "").toLowerCase();
                if (!q) return 1;
                if (n.startsWith(q)) return 100;
                if (n.split(/[\s\-_.]+/).some(w => w.startsWith(q))) return 80;
                if (n.includes(q)) return 60;
                if (g.includes(q)) return 45;
                if ((e.keywords || []).some(k => k.toLowerCase().startsWith(q))) return 30;
                return 0;
            };
            return all.map(e => ({ e: e, s: score(e) })).filter(x => x.s > 0)
                      .sort((a, b) => (b.s - a.s) || a.e.name.localeCompare(b.e.name))
                      .slice(0, 8).map(x => x.e);
        }
        function pick(e) {
            if (LauncherApps.full) return;
            LauncherApps.addDesktop(e);
            lp.note = "✓ Added " + e.name + " as #" + LauncherApps.list.length;
            lp.finishAdding();
        }

        Row {
            spacing: 10
            HudInput {
                id: search
                width: 360
                placeholder: "Search installed apps…"
                onAccepted: if (picker.results.length) picker.pick(picker.results[0])
                onCancelled: lp.finishAdding()
            }
            SmallButton { text: "CANCEL"; onClicked: lp.finishAdding() }
        }
        Repeater {
            model: picker.results
            delegate: Rectangle {
                id: hit
                required property var modelData
                readonly property bool already: picker.added.indexOf(modelData.id) >= 0
                readonly property string iconSrc: Quickshell.iconPath(modelData.icon, true)
                width: picker.width; height: 42
                color: hitMa.containsMouse ? Theme.p(0.12) : "transparent"
                border.color: hitMa.containsMouse ? Theme.p(0.5) : Theme.p(0.12)
                Row {
                    x: 12; anchors.verticalCenter: parent.verticalCenter
                    spacing: 12
                    Item {
                        width: 26; height: 26
                        Image { anchors.fill: parent; source: hit.iconSrc; sourceSize: Qt.size(64, 64); visible: hit.iconSrc !== "" && status === Image.Ready }
                        Text { anchors.centerIn: parent; visible: hit.iconSrc === ""; text: (hit.modelData.name || "?").charAt(0); color: Theme.primary; font.family: lp.mono; font.pixelSize: 13 }
                    }
                    Text { text: hit.modelData.name; color: Theme.text; font.family: lp.mono; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: hit.modelData.genericName || ""; color: Theme.dim; font.family: lp.mono; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                }
                Text {
                    anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                    text: hit.already ? "ON THE RING" : "ADD"
                    color: hit.already ? Theme.faint : Theme.secondary
                    font.family: lp.mono; font.pixelSize: 10; font.letterSpacing: 2
                }
                MouseArea { id: hitMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: picker.pick(hit.modelData) }
            }
        }
        Text {
            visible: picker.results.length === 0
            text: "No installed app matches “" + search.text + "”"
            color: Theme.faint; font.family: lp.mono; font.pixelSize: 12
        }
    }

    // ── Add custom command ──
    Column {
        id: custom
        visible: lp.adding === "custom"
        width: parent.width
        spacing: 8
        function commit() {
            if (cExec.text.trim() === "") { lp.note = "✕ Enter a command to run"; cExec.focusInput(); return; }
            LauncherApps.addCommand(cName.text, cExec.text, cIcon.text);
            lp.note = "✓ Added " + (LauncherApps.raw[LauncherApps.raw.length - 1] || {}).name + " as #" + LauncherApps.list.length;
            lp.finishAdding();
        }
        Row {
            spacing: 10
            Text { width: 80; text: "COMMAND"; color: Theme.dim; font.family: lp.mono; font.pixelSize: 11; font.letterSpacing: 2; anchors.verticalCenter: parent.verticalCenter }
            HudInput { id: cExec; width: 480; placeholder: "kitty -e btop   ·   code ~/cs137   ·   ~/bin/script.sh"; onAccepted: custom.commit(); onCancelled: lp.finishAdding() }
        }
        Row {
            spacing: 10
            Text { width: 80; text: "NAME"; color: Theme.dim; font.family: lp.mono; font.pixelSize: 11; font.letterSpacing: 2; anchors.verticalCenter: parent.verticalCenter }
            HudInput { id: cName; width: 220; maximumLength: 16; placeholder: "blank = command name"; onAccepted: custom.commit(); onCancelled: lp.finishAdding() }
        }
        Row {
            spacing: 10
            Text { width: 80; text: "ICON"; color: Theme.dim; font.family: lp.mono; font.pixelSize: 11; font.letterSpacing: 2; anchors.verticalCenter: parent.verticalCenter }
            HudInput { id: cIcon; width: 360; placeholder: "theme icon name or file path (optional)"; onAccepted: custom.commit(); onCancelled: lp.finishAdding() }
            Image { width: 28; height: 28; anchors.verticalCenter: parent.verticalCenter; sourceSize: Qt.size(64, 64); source: LauncherApps.iconSource(cIcon.text.trim()) }
        }
        Text {
            text: "Runs through Hyprland, so it keeps running if the HUD restarts. ~ works in paths."
            color: Theme.faint; font.family: lp.mono; font.pixelSize: 10
        }
        Row {
            spacing: 10
            SmallButton { text: "ADD"; onClicked: custom.commit() }
            SmallButton { text: "CANCEL"; onClicked: lp.finishAdding() }
        }
    }
}
