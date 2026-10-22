#!/bin/sh
# STARK OS lock: plays the lock sound, shows hyprlock, then the unlock animation + sound.
# Used by Super+L, the launcher's LOCK, and hypridle (idle + before sleep).

# Already locked (or a lock is starting right now, e.g. lid.sh + hypridle)? Do nothing.
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/stark-lock.lock"
flock -n 9 || exit 0
pidof hyprlock >/dev/null && exit 0

# Snap the HUD doors shut in parallel; hyprlock must not wait on Quickshell.
qs ipc call stark locked >/dev/null 2>&1 &
# Keep hyprlock's own log (auth, fingerprint, sleep) for the last two locks.
log="${XDG_STATE_HOME:-$HOME/.local/state}/stark/hyprlock.log"
mkdir -p "${log%/*}" && { [ -f "$log" ] && mv -f "$log" "$log.1"; }
# Open the doors the moment hyprlock gives the session back, not when it exits: after a
# fingerprint unlock it lingers ~2 s while PAM's fail delay ends the aborted password
# prompt. Its exit stays the fallback.
stdbuf -oL hyprlock 2>&1 | {
    opened=""
    while IFS= read -r line; do
        printf '%s\n' "$line" >>"$log"
        case "$line" in
            *"Unlocked, exiting!"*)
                [ -z "$opened" ] && { qs ipc call stark unlocked >/dev/null 2>&1 & opened=1; } ;;
        esac
    done
    [ -n "$opened" ] || qs ipc call stark unlocked >/dev/null 2>&1
}
