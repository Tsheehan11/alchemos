#!/bin/sh
# STARK OS lock: plays the lock sound, shows hyprlock, then the unlock animation + sound.
# Used by Super+L, the launcher's LOCK, and hypridle (idle + before sleep).

# Already locked (or a lock is starting right now, e.g. lid.sh + hypridle)? Do nothing.
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/stark-lock.lock"
flock -n 9 || exit 0
pidof hyprlock >/dev/null && exit 0

# Snap the HUD doors shut in parallel; hyprlock must not wait on Quickshell.
qs ipc call stark locked >/dev/null 2>&1 &
hyprlock
qs ipc call stark unlocked >/dev/null 2>&1
