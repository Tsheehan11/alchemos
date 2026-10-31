-- ── Keybinds ─────────────────────────────────
-- New binds go here (e.g. the planned Super + D Peek), one hl.bind per line.
local terminal = "kitty"
local files    = "dolphin"
local browser  = "zen-browser"
local menu     = "fuzzel"   -- old plain launcher, still on Super + Shift + R

local mod  = "SUPER"
local exec = hl.dsp.exec_cmd
local function bind(keys, dsp, opts) hl.bind(mod .. " + " .. keys, dsp, opts) end

bind("Return", exec(terminal))
bind("Space",  exec("qs ipc call launcher toggle"))   -- molecule launcher
bind("R",      exec("qs ipc call search toggle"))     -- app search
bind("C",      exec("qs ipc call control toggle"))    -- control center
bind("comma",  exec("qs ipc call settings toggle"))   -- settings
bind("P",      exec("qs ipc call settings display"))  -- Settings → Display
bind("M",      exec("~/.config/hypr/stark-music.sh")) -- show/hide Spotify (relaunches if closed)
bind("SHIFT + R", exec(menu))
bind("E",      exec(files))
bind("B",      exec(browser))
bind("Q",      hl.dsp.window.close())
bind("F",      hl.dsp.window.fullscreen({ mode = "fullscreen" }))
bind("V",      hl.dsp.window.float({ action = "toggle" }))
bind("SHIFT + V", exec("qs ipc call roles cycle"))    -- what this screen's HUD shows: AUTO → CLOCK → STATS → MUSIC → NONE
bind("L",      exec("qs ipc call stark lock || ~/.config/hypr/stark-lock.sh"))
bind("Tab",    exec("qs ipc call overview toggle"))
bind("Escape", exec("qs ipc call stark menu"))
bind("J",      exec("qs ipc call jarvisapp toggle"))  -- JARVIS console (conversations, typed requests, tasks)
bind("SHIFT + M", hl.dsp.exit())
-- Peek: hide / bring back every window on this workspace (stark/peek.lua). Loaded on its
-- own, so a mistake in it costs only this bind.
local peekOk, peek = pcall(require, "stark.peek")
if peekOk then bind("D", peek.toggle) end

-- Move focus / windows with arrows
for _, dir in ipairs({ "left", "right", "up", "down" }) do
    bind(dir,             hl.dsp.focus({ direction = dir }))
    bind("SHIFT + " .. dir, hl.dsp.window.move({ direction = dir }))
end

-- Workspaces 1–9 (go to / send window to)
for ws = 1, 9 do
    bind(tostring(ws),           hl.dsp.focus({ workspace = ws }))
    bind("SHIFT + " .. ws,       hl.dsp.window.move({ workspace = ws, follow = true }))
end

-- Mouse: Super + drag to move/resize. 0.56 ignores `mouse` (drag() / resize() wait for the
-- button release themselves); newer Hyprland needs it, so it stays.
bind("mouse:272", hl.dsp.window.drag(),   { mouse = true })
bind("mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Volume, brightness, media keys (work on the lock screen too)
local held   = { locked = true, repeating = true }
local locked = { locked = true }
hl.bind("XF86AudioRaiseVolume",  exec("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"), held)
hl.bind("XF86AudioLowerVolume",  exec("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"), held)
hl.bind("XF86AudioMute",         exec("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"), held)
hl.bind("XF86MonBrightnessUp",   exec("brightnessctl -q set 5%+ && qs ipc call osd brightness"), held)
hl.bind("XF86MonBrightnessDown", exec("brightnessctl -q set 5%- && qs ipc call osd brightness"), held)
hl.bind("XF86AudioPlay", exec("playerctl play-pause"), locked)
hl.bind("XF86AudioNext", exec("playerctl next"), locked)
hl.bind("XF86AudioPrev", exec("playerctl previous"), locked)
hl.bind("XF86PowerOff",  exec("qs ipc call stark menu"), locked)

-- Lid: closing it (laptop only) locks + turns the screen off; opening turns it back on
hl.bind("switch:on:Lid Switch",  exec("~/.config/hypr/lid.sh"), locked)
hl.bind("switch:off:Lid Switch", exec("~/.config/hypr/stark-dpms.sh on"), locked)
