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

-- Screenshots (quickshell/Shot.qml, ~/.local/bin/stark-shot). The region selector (slurp, namespace
-- "selection") and the shutter flash skip the fade: a fading-out selector would land in the capture, and
-- the flash is too short to fade.
hl.layer_rule({
    name  = "stark-shot-no-anim",
    match = { namespace = "^(selection|stark-shot-flash)$" },
    no_anim = true,
})
-- satty (annotate) floats over the desktop instead of tiling
hl.window_rule({
    name  = "stark-shot-satty",
    match = { class = "^(com.gabm.satty|org.satty.satty)$" },   -- app id changed in 0.21
    float = true,
})
