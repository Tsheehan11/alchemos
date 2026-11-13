-- ── Theme: hologram cyan ─────────────────────
-- These are the colours Hyprland starts with. The HUD (Theme.qml) repaints them in the
-- active theme a moment later and after every reload, with `hyprctl eval 'hl.config(…)'`.

-- ── Cursor ── (alchemos-cursor/build.sh rewrites these four lines)
hl.env("HYPRCURSOR_THEME", "ALCHEMOS")
hl.env("XCURSOR_THEME", "ALCHEMOS")
hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")

hl.config({
    general = {
        col = {
            active_border   = { colors = { "rgba(4fd8ffee)", "rgba(4fd8ff55)" }, angle = 45 },
            inactive_border = "rgba(4fd8ff22)",
        },
    },
    decoration = {
        shadow = {
            color          = "rgba(4fd8ff40)",
            color_inactive = "rgba(00000000)",
        },
    },
    misc = {
        background_color = "rgb(05090f)",
    },
})
