-- ── Look and feel ────────────────────────────
-- Colours are in theme.lua. Battery saver (PowerMode.qml) and combat mode (stark-game)
-- switch blur / shadows / animations at runtime and put them back afterwards.
hl.config({
    general = {
        gaps_in  = 6,
        gaps_out = 14,
        border_size = 2,
        layout = "dwindle",
        resize_on_border = true,
    },

    decoration = {
        rounding = 4,
        active_opacity   = 1.0,
        inactive_opacity = 1.0,

        blur = {
            enabled  = true,
            size     = 7,
            passes   = 3,
            vibrancy = 0.2,
            noise    = 0.02,
        },

        shadow = {
            enabled      = true,
            range        = 22,
            render_power = 2,
        },
    },

    animations = {
        enabled = true,
    },

    -- Fullscreen games skip compositing (scanned out directly) → less iGPU work, less lag.
    render = {
        direct_scanout = 2,
    },

    dwindle = {
        preserve_split = true,
    },

    misc = {
        disable_hyprland_logo    = true,
        disable_splash_rendering = true,
        anr_missed_pings = 6,
        -- If hyprlock dies the session stays locked; this lets a new hyprlock take over
        -- (stark-rescue does that from a TTY).
        allow_session_lock_restore = true,
    },

    input = {
        kb_layout = "us",
        follow_mouse = 1,
        touchpad = {
            natural_scroll = true,
            tap_to_click   = true,
        },
    },
})

-- ── Animations ───────────────────────────────
hl.curve("holo",  { type = "bezier", points = { { 0.16, 1 }, { 0.3, 1 } } })
hl.curve("flick", { type = "bezier", points = { { 0.7, 0 },  { 0.3, 1 } } })

hl.animation({ leaf = "windows",     enabled = true, speed = 5,  bezier = "holo",    style = "popin 85%" })
hl.animation({ leaf = "windowsOut",  enabled = true, speed = 4,  bezier = "flick",   style = "popin 70%" })
hl.animation({ leaf = "border",      enabled = true, speed = 8,  bezier = "default" })
hl.animation({ leaf = "borderangle", enabled = true, speed = 60, bezier = "default", style = "loop" })
hl.animation({ leaf = "fade",        enabled = true, speed = 4,  bezier = "default" })
hl.animation({ leaf = "workspaces",  enabled = true, speed = 5,  bezier = "holo",    style = "slidefade 15%" })
