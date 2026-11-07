// An icon from the skin's set (Style.icons): an SVG in the skin's folder, recoloured through
// currentColor, with {{placeholders}} for state. Empty (0×0) when the skin has no such icon: callers
// keep the base's text / glyph then (Style.hasIcon).
//   {{l1}} {{l2}} {{l3}}  1 or dimmed by level (signal arcs, volume)   {{fy}}  a fill's top edge (battery)
//   {{on}} 1 / 0          {{chg}} 1 / 0 while charging
// The SVG is re-rasterised only when its colour, size or state changes.
import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: ic
    property string name
    property color color: Theme.primary
    property real size: 14
    property real level: 1
    property bool on: true
    property bool charging: false
    readonly property bool present: Style.hasIcon(name)
    implicitWidth: present ? size : 0
    implicitHeight: present ? size : 0

    FileView {
        id: file
        path: ic.present ? Quickshell.shellPath("skins/" + Skin.current + "/" + Style.icons[ic.name]) : ""
        printErrors: false; blockLoading: true
    }
    function hex(c) { return "#" + [c.r, c.g, c.b].map(v => Math.round(v * 255).toString(16).padStart(2, "0")).join(""); }
    // levels quantised, so a changing level only redraws when an arc / the fill visibly changes
    readonly property int steps: Math.round(Math.max(0, Math.min(1, level)) * 20)
    readonly property string svg: {
        if (!present || !file.loaded) return "";
        const L = steps / 20, dim = 0.28;
        return file.text()
            .replace(/currentColor/g, hex(color))
            .replace(/\{\{l1\}\}/g, L > 0.05 ? 1 : dim).replace(/\{\{l2\}\}/g, L > 0.4 ? 1 : dim).replace(/\{\{l3\}\}/g, L > 0.75 ? 1 : dim)
            .replace(/\{\{on\}\}/g, on ? 1 : 0).replace(/\{\{chg\}\}/g, charging ? 1 : 0)
            .replace(/\{\{fy\}\}/g, (21 - L * 12.4).toFixed(2));
    }
    Image {
        visible: ic.present
        anchors.centerIn: parent
        width: ic.size; height: ic.size
        sourceSize: Qt.size(Math.ceil(ic.size * 2), Math.ceil(ic.size * 2))
        source: ic.svg ? "data:image/svg+xml;utf8," + encodeURIComponent(ic.svg) : ""
        smooth: true; asynchronous: false
    }
}
