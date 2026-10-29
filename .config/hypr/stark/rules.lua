-- ── Window and layer rules ───────────────────
-- Apps can't maximize themselves (the tiling layout decides sizes)
hl.window_rule({
    name  = "suppress-maximize",
    match = { class = ".*" },
    suppress_event = "maximize",
})

-- Spotify lives on special:music (Super + M shows / hides it)
hl.window_rule({
    name  = "spotify-music",
    match = { class = "^(Spotify)$" },
    workspace = "special:music silent",
})

-- Security doors: no fade-in. When they shut under the lock screen (lid, idle), Hyprland
-- holds a layer's fade-in until the session unlocks, so hyprlock faded out onto the bare
-- desktop while the doors were still fading in: a black flash before the reveal.
hl.layer_rule({
    name  = "stark-doors-no-anim",
    match = { namespace = "stark-doors" },
    no_anim = true,
})
