#!/bin/sh
# AlchemOS screen-share picker (used by xdg-desktop-portal-hyprland whenever an
# app like Discord asks to share your screen). Pick a monitor from a quick menu;
# the one you're on is listed first, so Enter = share the screen you're using.

focused=$(hyprctl activeworkspace -j | sed -n 's/.*"monitor": *"\([^"]*\)".*/\1/p' | head -1)
all=$(hyprctl monitors | awk '/^Monitor/ {print $2}')

list=$( { [ -n "$focused" ] && echo "$focused"; echo "$all"; } | awk 'NF && !seen[$0]++')

choice=$(printf '%s\n' "$list" | fuzzel --dmenu --prompt "SHARE SCREEN › " --lines 4)
[ -z "$choice" ] && exit 1

echo "[SELECTION]/screen:$choice"
