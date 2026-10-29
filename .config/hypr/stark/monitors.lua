-- ── Monitors ─────────────────────────────────
-- Matched by model + serial number, so it doesn't matter which USB-C port
-- names the dock hands out (DP-5, DP-7, …).
-- If left and middle are ever backwards: swap the two serials below.
local leftMon = "desc:Acer Technologies MGB270U P2 16220214A4B00"
local midMon  = "desc:Acer Technologies MGB270U P2 1622022294B00"

hl.monitor({ output = leftMon, mode = "2560x1440@144", position = "0x0",      scale = 1 })
hl.monitor({ output = midMon,  mode = "2560x1440@144", position = "2560x0",   scale = 1 })
hl.monitor({ output = "eDP-1", mode = "1920x1200@60",  position = "5120x120", scale = 1 })
-- Any other screen (projector, TV): auto-place to the right
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })

-- Workspaces: 1–3 left, 4–6 middle, 7–9 laptop (when docked).
-- Laptop only, the HUD (Roles.qml) keeps 1–5 on the laptop screen.
local homes = { [leftMon] = { 1, 2, 3 }, [midMon] = { 4, 5, 6 }, ["eDP-1"] = { 7, 8, 9 } }
for mon, list in pairs(homes) do
    for i, ws in ipairs(list) do
        hl.workspace_rule({ workspace = tostring(ws), monitor = mon, default = (i == 1) or nil })
    end
end

-- ── Display profile (Settings → Display) ─────
-- The HUD (Profiles.qml) writes the active profile's arrangement to display-profile.lua
-- next to this file: `return { { output = …, mode = …, … }, … }`. Applied last, so its
-- rules win. Loaded with loadfile, so Hyprland doesn't watch it: the HUD decides when to
-- reload (with its reload-loop guard). A missing or broken file just leaves the rules above.
local path = os.getenv("HOME") .. "/.config/hypr/stark/display-profile.lua"
local chunk = loadfile(path)
local ok, rules = pcall(chunk or function() return {} end)
if ok and type(rules) == "table" then
    for _, rule in ipairs(rules) do
        if type(rule) == "table" then pcall(hl.monitor, rule) end
    end
end
