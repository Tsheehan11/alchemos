// Display profiles: the pure decisions (no Quickshell), so they can be tested on their own.
// Profiles.qml does the I/O. A "monitor" is an entry of `hyprctl monitors all -j`.
.pragma library
.import "Hypr.js" as Hypr

var LAPTOP = "eDP-1";

// Home desk: the USB-C dock plus both Acers (by the serial in their description).
var DESK_MAIN = "16220214A4B00";   // left, main
var DESK_DIAG = "1622022294B00";   // middle, diagnostics
// The dock shows up as USB devices, not Thunderbolt. Any of these = docked at the desk:
// its card reader (by serial), or its Realtek LAN adapter.
var DOCK_USB = ["0bda:5350:202503061002", "0bda:8153:001000001"];

function externals(mons) {
    return mons.filter(function (m) { return m.name !== LAPTOP; });
}

function hasSerial(mons, serial) {
    return mons.some(function (m) {
        return (m.serial || "") === serial || (m.description || "").indexOf(serial) >= 0;
    });
}

// usb: list of "vid:pid:serial" strings for the connected USB devices
function dockPresent(usb) {
    return usb.some(function (u) { return DOCK_USB.indexOf(u) >= 0; });
}

function acersPresent(mons) {
    return hasSerial(mons, DESK_MAIN) && hasSerial(mons, DESK_DIAG);
}

// Profiles are keyed by what's connected: "laptop", "desk", or the external monitors'
// descriptions (sorted, so plug order doesn't matter).
function keyFor(mons, usb) {
    var ext = externals(mons);
    if (ext.length === 0) return "laptop";
    if (acersPresent(mons) && dockPresent(usb)) return "desk";
    return "ext:" + ext.map(function (m) { return m.description || m.name; }).sort().join("|");
}

function nameFor(key) {
    if (key === "desk") return "HOME DESK";
    if (key === "laptop") return "LAPTOP ONLY";
    return key.slice(4).split("|").map(function (d) {
        // "Make Model Serial" → "Make Model"; keep it short
        var w = d.split(" ");
        return (w.length > 2 ? w.slice(0, w.length - 1) : w).join(" ");
    }).join(" + ").toUpperCase();
}

function monKey(m) {
    return m.name === LAPTOP ? m.name : "desc:" + m.description;
}

// A profile: { rules: [hyprland monitor rules], layout, orrin, govee, saver }
function defaults(key, mons, goveeMode) {
    if (key === "desk") return {
        rules: [
            "desc:Acer Technologies MGB270U P2 " + DESK_MAIN + ",2560x1440@144.00,0x0,1,transform,0",
            "desc:Acer Technologies MGB270U P2 " + DESK_DIAG + ",2560x1440@59.95,2560x0,1,transform,0",
            LAPTOP + ",1920x1200@60.00,5120x120,1,transform,0"
        ],
        layout: "extend", orrin: true,
        govee: goveeMode && goveeMode !== "off" ? goveeMode : "theme",
        saver: true
    };
    if (key === "laptop") return {
        rules: [LAPTOP + ",preferred,0x0,1,transform,0"],
        layout: "extend", orrin: false, govee: "off", saver: true
    };
    // Anything else (a TV, a projector, someone's monitor): laptop on the left, the rest
    // to its right, best mode. Mirror etc. is whatever you save for it.
    var rules = [LAPTOP + ",preferred,0x0,1"];
    externals(mons).forEach(function (m) { rules.push(monKey(m) + ",preferred,auto-right,1"); });
    return { rules: rules, layout: "extend", orrin: false, govee: "off", saver: true };
}

function mirrored(m) {
    var v = m.mirrorOf;
    return v !== undefined && v !== null && String(v) !== "none" && String(v) !== "";
}

// The current arrangement as rules (for "save current"). Mirroring and "one screen only"
// are the layout mode, applied on top by Displays, so they're not baked into the rules.
function rulesFromMonitors(mons, layout) {
    return mons.slice().sort(function (a, b) { return a.x - b.x; }).map(function (m) {
        var k = monKey(m);
        if (mirrored(m)) return k + ",preferred,auto,1";
        if (m.disabled) {
            // switched off by the layout mode → keep it in the arrangement
            if (layout === "laptop" || layout === "external") return k + ",preferred,auto,1";
            return k + ",disable";
        }
        return k + "," + m.width + "x" + m.height + "@" + Number(m.refreshRate).toFixed(2)
             + "," + m.x + "x" + m.y + "," + m.scale + ",transform," + m.transform;
    });
}

// ~/.config/hypr/alchemos/display-profile.lua: the rules as hl.monitor specs, read by
// alchemos/monitors.lua after its own monitor rules (so these win)
function confText(key, rules) {
    var s = "-- STARK OS — screen arrangement for the \"" + nameFor(key) + "\" display profile.\n";
    s += "-- Written by the HUD (Profiles.qml) from ~/.config/quickshell/display-profiles.json;\n";
    s += "-- edit it in Settings → Display. Applied by alchemos/monitors.lua, after its own rules.\n";
    s += "return {\n";
    rules.forEach(function (r) { s += "    " + Hypr.lua(Hypr.monitorSpec(r)) + ",\n"; });
    return s + "}\n";
}
