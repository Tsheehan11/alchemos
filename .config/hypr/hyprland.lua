-- ─────────────────────────────────────────────
--  AlchemOS — Hyprland config (Lua, Hyprland 0.56+)
--  Trevor's Inspiron 16 7640 + 2x 1440p monitors
-- ─────────────────────────────────────────────
--
-- Everything lives in ~/.config/hypr/alchemos/*.lua; this file only loads them in order.
-- Edit the modules in place: Hyprland reloads by itself when one of them is saved.
--
--   monitors.lua   screens (matched by desc:), workspace homes, the HUD's display profile
--   theme.lua      cursor + the border / shadow / background colours (the HUD repaints these live)
--   looks.lua      gaps, blur, shadows, animations, layout, input, misc
--   binds.lua      every keybind
--   rules.lua      window and layer rules
--   autostart.lua  session env + what starts once at login
--
-- If this config ever fails to load, see "Recovery" in ~/.github/README.md
-- (start-hyprland -- --config ~/.config/hypr.conf-backup/hyprland.conf, or alchemos-rescue).
-- Lua API stubs: /usr/share/hypr/stubs (wired into VS Code by .luarc.json here).

-- Each module loads on its own, so a typo in one (shown in the red error bar) can't take
-- the binds or the screens down with it.
for _, name in ipairs({ "monitors", "theme", "looks", "binds", "rules", "autostart" }) do
    pcall(require, "alchemos." .. name)
end
