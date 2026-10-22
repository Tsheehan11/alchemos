#!/bin/sh
# STARK OS lock: plays the lock sound, shows hyprlock, then the unlock animation + sound.
# Used by Super+L, the launcher's LOCK, and hypridle (idle + before sleep).

# Already locked (or a lock is starting right now, e.g. lid.sh + hypridle)? Do nothing.
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/stark-lock.lock"
flock -n 9 || exit 0
pidof hyprlock >/dev/null && exit 0

# Snap the HUD doors shut and let them reach the screen before hyprlock starts. Once the
# session is locked, Hyprland draws only black under hyprlock, and a lid lock is followed
# at once by the freeze for suspend, so doors that weren't on screen by then showed as
# black or the bare desktop when hyprlock faded out at unlock. Bounded (~0.6 s at most),
# so a stuck Quickshell can't hold up the lock.
timeout 0.3 qs ipc call stark locked >/dev/null 2>&1
mons=$(hyprctl monitors | grep -c '^Monitor ')
for _ in 1 2 3 4 5; do
    [ "$(hyprctl layers | grep -c 'namespace: stark-doors')" -ge "$mons" ] && break   # on every screen
    sleep 0.05
done
sleep 0.05   # one more frame for the doors to be drawn
# Keep hyprlock's own log (auth, fingerprint, sleep) for the last two locks.
log="${XDG_STATE_HOME:-$HOME/.local/state}/stark/hyprlock.log"
mkdir -p "${log%/*}" && { [ -f "$log" ] && mv -f "$log" "$log.1"; }
# Start the reveal the moment authentication succeeds (password, fingerprint, SIGUSR1),
# i.e. when hyprlock begins its fade-out, not when it exits. After the screens were off
# or the system slept, Quickshell's windows show nothing until they draw again, and
# hyprlock faded onto black; this way the doors redraw during the fade. (hyprlock also
# lingers ~2 s after a fingerprint unlock while PAM's fail delay ends the aborted
# password prompt.) "Unlocked" and hyprlock's exit stay as fallbacks.
stdbuf -oL hyprlock 2>&1 | {
    opened=""
    while IFS= read -r line; do
        printf '%s\n' "$line" >>"$log"
        case "$line" in
            *"auth: authenticated"*|*"status verify-match"*|*"Unlocking with a SIGUSR1"*|*"Unlocked, exiting!"*)
                [ -z "$opened" ] && { qs ipc call stark unlocked >/dev/null 2>&1 & opened=1; } ;;
        esac
    done
    [ -n "$opened" ] || qs ipc call stark unlocked >/dev/null 2>&1
}
