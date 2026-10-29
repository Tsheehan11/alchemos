#!/usr/bin/env bash
# Super+M: show/hide Spotify on special:music, relaunching it if it was closed.

spotify_window() { hyprctl clients -j | jq -r 'first(.[] | select(.class == "Spotify") | .workspace.name) // empty'; }
music_shown() { [ "$(hyprctl monitors -j | jq -r '.[] | select(.focused) | .specialWorkspace.name')" = special:music ]; }

ws=$(spotify_window)
if [ -z "$ws" ]; then
    # Closed (or still starting): launch once, wait up to ~8 s for the window.
    pgrep -x spotify >/dev/null || setsid -f spotify-launcher >/dev/null 2>&1
    for _ in $(seq 40); do
        ws=$(spotify_window)
        [ -n "$ws" ] && break
        sleep 0.2
    done
    [ -z "$ws" ] && exit 1
    # The windowrule sends it to special:music; make sure it is visible here.
    [ "$ws" != special:music ] && hyprctl dispatch 'hl.dsp.window.move({ window = "class:^(Spotify)$", workspace = "special:music", follow = false })' >/dev/null
    music_shown || hyprctl dispatch 'hl.dsp.workspace.toggle_special("music")' >/dev/null
    exit 0
fi

# Running but dragged onto a normal workspace: pull it back before toggling,
# otherwise the toggle opens an empty scratchpad.
[ "$ws" != special:music ] && hyprctl dispatch 'hl.dsp.window.move({ window = "class:^(Spotify)$", workspace = "special:music", follow = false })' >/dev/null
hyprctl dispatch 'hl.dsp.workspace.toggle_special("music")' >/dev/null
