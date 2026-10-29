-- ── Session environment ──────────────────────
-- (cursor variables are in theme.lua)
hl.env("QT_QPA_PLATFORM", "wayland")

-- ── Autostart ────────────────────────────────
-- Runs once at login, not on reloads (the old exec-once).
hl.on("hyprland.start", function()
    hl.exec_cmd("hypridle")
    hl.exec_cmd("/usr/lib/polkit-kde-authentication-agent-1")
    hl.exec_cmd("qs")
    hl.exec_cmd("spotify-launcher")   -- rules.lua parks it on special:music
    -- Portals (xdg-desktop-portal-hyprland, screen sharing) need the session's Wayland env
    hl.exec_cmd("dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP HYPRLAND_INSTANCE_SIGNATURE")
    hl.exec_cmd("~/.config/hypr/stark-audio-auto.sh")
    hl.exec_cmd("~/.local/bin/stark-govee daemon")   -- STARK OS ambient lights
    hl.exec_cmd("~/.local/bin/stark-game daemon")    -- combat mode: watches for game windows
end)
