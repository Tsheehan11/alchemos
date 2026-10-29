// Talking to Hyprland's Lua config (0.56+). `hyprctl keyword` and the old
// `dispatch exec …` syntax are gone; runtime changes are Lua instead:
//   options    hyprctl eval 'hl.config({ decoration = { blur = { enabled = false } } })'
//   monitors   hyprctl eval 'hl.monitor({ output = "eDP-1", mode = "1920x1200@48", … })'
//   dispatch   Hyprland.dispatch("hl.dsp.focus({ workspace = 3 })")   (= hl.dispatch(…))
// A reload (`hyprctl reload`) still throws runtime changes away and sends `configreloaded`.
.pragma library

// Any JS value → Lua source. Objects become tables; keys that aren't plain names are quoted.
function lua(v) {
    if (v === null || v === undefined) return "nil";
    if (typeof v === "boolean") return v ? "true" : "false";
    if (typeof v === "number") return isFinite(v) ? String(v) : "nil";
    if (typeof v === "string") return str(v);
    if (Array.isArray(v)) return "{ " + v.map(lua).join(", ") + " }";
    return "{ " + Object.keys(v).filter(function (k) { return v[k] !== undefined; }).map(function (k) {
        return (/^[A-Za-z_][A-Za-z0-9_]*$/.test(k) ? k : "[" + str(k) + "]") + " = " + lua(v[k]);
    }).join(", ") + " }";
}

function str(s) {
    return "\"" + String(s).replace(/\\/g, "\\\\").replace(/"/g, "\\\"")
                           .replace(/\n/g, "\\n").replace(/\r/g, "\\r") + "\"";
}

// argv for Quickshell.execDetached / Process
function config(obj) { return ["hyprctl", "eval", "hl.config(" + lua(obj) + ")"]; }
function monitors(specs) { return ["hyprctl", "eval", specs.map(function (s) { return "hl.monitor(" + lua(s) + ")"; }).join(" ")]; }

// Dispatchers, for Hyprland.dispatch(…)
function exec(cmd) { return "hl.dsp.exec_cmd(" + str(cmd) + ")"; }
function workspace(n) { return "hl.dsp.focus({ workspace = " + lua(Number(n)) + " })"; }
function workspaceTo(ws, monitor) { return "hl.dsp.workspace.move({ workspace = " + lua(Number(ws)) + ", monitor = " + str(monitor) + " })"; }
function exit() { return "hl.dsp.exit()"; }

// A Settings → Display rule ("desc:…,2560x1440@144.00,0x0,1,transform,0", "eDP-1,disable",
// "…,preferred,auto,1,mirror,DP-5"; the format kept in display-profiles.json) → hl.monitor spec
function monitorSpec(rule) {
    var p = String(rule).split(",").map(function (s) { return s.trim(); });
    var spec = { output: p[0] };
    if (p[1] === "disable" || p[1] === "disabled") { spec.disabled = true; return spec; }
    if (p[1]) spec.mode = p[1];
    if (p[2]) spec.position = p[2];
    if (p[3]) spec.scale = isNaN(Number(p[3])) ? p[3] : Number(p[3]);
    for (var i = 4; i + 1 < p.length; i += 2) {
        var v = p[i + 1];
        spec[p[i]] = p[i] === "mirror" || isNaN(Number(v)) ? v : Number(v);
    }
    return spec;
}
