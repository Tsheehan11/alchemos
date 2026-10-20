#!/bin/sh
# STARK OS screen-share picker (used by xdg-desktop-portal-hyprland for casting,
# Discord screen share, etc.).
#
#   ⧉ DUPLICATE, FIT TO TV — makes a TV-shaped (16:9) virtual screen, mirrors it
#                            onto the screen you're on, and sends that to the TV,
#                            so the TV is filled edge to edge.
#   ▭ SEPARATE TV SCREEN   — the TV becomes an extra desktop to the right.
#   ◫ <monitor>            — send that monitor exactly as it is.
#
# TV resolution: Settings → Display → TV / CASTING. The virtual screen is
# removed again when the cast app closes (handled by the HUD, Cast.qml).

TV=STARK-TV
SETTINGS="$HOME/.config/quickshell/settings.json"

res=$(sed -n 's/.*"castRes": *"\([0-9]*x[0-9]*\)".*/\1/p' "$SETTINGS" 2>/dev/null | head -1)
[ -z "$res" ] && res=1920x1080
w=${res%x*}
scale=1
[ "$w" -ge 3840 ] && scale=2
[ "$w" -ge 2560 ] && [ "$w" -lt 3840 ] && scale=1.5

LAST="${XDG_RUNTIME_DIR:-/tmp}/stark-cast-last"

# The TV sometimes reconnects mid-cast, which makes the cast app ask for a
# screen again. Answer that automatically instead of re-running the setup
# (re-running it while the TV screen already existed broke the cast):
#   • TV screen already up → keep sending it
#   • picked a screen in the last 60 s → send the same one again
if hyprctl monitors | grep -q "^Monitor $TV "; then
    echo "[SELECTION]/screen:$TV"
    exit 0
fi
if [ -f "$LAST" ] && [ $(( $(date +%s) - $(stat -c %Y "$LAST") )) -lt 60 ]; then
    prev=$(cat "$LAST")
    if hyprctl monitors | grep -q "^Monitor $prev "; then
        touch "$LAST"
        echo "[SELECTION]/screen:$prev"
        exit 0
    fi
fi

active=$(hyprctl activeworkspace -j)
focused=$(printf '%s' "$active" | sed -n 's/.*"monitor": *"\([^"]*\)".*/\1/p' | head -1)
wsid=$(printf '%s' "$active" | sed -n 's/^ *"id": *\(-\{0,1\}[0-9]*\).*/\1/p' | head -1)
mons=$(hyprctl monitors | awk '/^Monitor/ {print $2}' | grep -v "^$TV$")

DUP="⧉  DUPLICATE, FIT TO TV  ($res)"
EXT="▭  SEPARATE TV SCREEN  ($res)"
list=$( { echo "$DUP"; echo "$EXT"; { [ -n "$focused" ] && echo "$focused"; echo "$mons"; } | awk 'NF && !seen[$0]++ {print "◫  " $0 "  (as is)"}'; } )

choice=$(printf '%s\n' "$list" | fuzzel --dmenu --prompt "CAST › " --lines 6 --width 44)
[ -z "$choice" ] && exit 1

[ -n "$wsid" ] && echo "$wsid" > "${XDG_RUNTIME_DIR:-/tmp}/stark-cast-ws"

make_tv() {
    hyprctl monitors all | grep -q "^Monitor $TV " || hyprctl output create headless "$TV" >/dev/null
    sleep 0.4
    hyprctl keyword monitor "$TV,${res}@60,auto,$scale" >/dev/null
}

case "$choice" in
    "$DUP")
        make_tv
        # Your screen now shows the TV-shaped desktop; bring your current workspace along
        [ "$focused" != "$TV" ] && hyprctl keyword monitor "$focused,preferred,auto,1,mirror,$TV" >/dev/null
        sleep 0.4
        hyprctl dispatch focusmonitor "$TV" >/dev/null
        if [ -n "$wsid" ]; then
            hyprctl dispatch moveworkspacetomonitor "$wsid" "$TV" >/dev/null
            hyprctl dispatch workspace "$wsid" >/dev/null      # show YOUR workspace on the TV, not a new empty one
        fi
        sleep 0.6
        echo "[SELECTION]/screen:$TV"
        ;;
    "$EXT")
        make_tv
        # Hyprland jumps focus (and the mouse) to a new screen — put you back where you were
        sleep 0.3
        [ -n "$focused" ] && hyprctl dispatch focusmonitor "$focused" >/dev/null
        [ -n "$wsid" ] && hyprctl dispatch workspace "$wsid" >/dev/null
        sleep 0.4
        echo "[SELECTION]/screen:$TV"
        ;;
    *)
        name=$(printf '%s' "$choice" | sed 's/^◫  //; s/  (as is)$//')
        echo "$name" > "$LAST"
        echo "[SELECTION]/screen:$name"
        ;;
esac
