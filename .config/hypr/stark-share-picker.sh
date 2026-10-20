#!/bin/sh
# STARK OS screen-share picker (used by xdg-desktop-portal-hyprland for casting,
# Discord screen share, etc.). Pick a monitor from a quick menu; the focused
# monitor is listed first, so Enter = share the screen you're on.

focused=$(hyprctl activeworkspace | awk '/monitorID|on monitor/ {for(i=1;i<=NF;i++) if ($i=="monitor") {gsub(":","",$(i+1)); print $(i+1); exit}}')
all=$(hyprctl monitors | awk '/^Monitor/ {print $2}')

list=$( { [ -n "$focused" ] && echo "$focused"; echo "$all"; } | awk 'NF && !seen[$0]++')

choice=$(printf '%s\n' "$list" | fuzzel --dmenu --prompt "CAST SCREEN › " --lines 4)
[ -z "$choice" ] && exit 1

echo "[SELECTION]/screen:$choice"
