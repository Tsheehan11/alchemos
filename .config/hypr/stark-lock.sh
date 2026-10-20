#!/bin/sh
# STARK OS lock: plays the lock sound, shows hyprlock, then the unlock animation + sound.
# Used by Super+L, the launcher's LOCK, and hypridle (idle + before sleep).

# Already locked? Do nothing.
pidof hyprlock >/dev/null && exit 0

qs ipc call stark locked >/dev/null 2>&1
hyprlock
qs ipc call stark unlocked >/dev/null 2>&1
