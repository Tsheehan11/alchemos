#!/bin/sh
# Screens on / off: stark-dpms.sh on|off (hypridle, lid.sh, stark-rescue).
# Hyprland with the Lua config only takes Lua dispatchers; the hyprland.conf backup
# (recovery boot) only takes the old syntax, so try Lua first and fall back.
case "$1" in
    on)  action=enable ;;
    off) action=disable ;;
    *)   echo "usage: $0 on|off" >&2; exit 2 ;;
esac
[ "$(hyprctl dispatch "hl.dsp.dpms({ action = \"$action\" })" 2>&1)" = ok ] || hyprctl dispatch dpms "$1"
