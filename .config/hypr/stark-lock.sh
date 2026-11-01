#!/bin/sh
# STARK OS lock: plays the lock sound, shows hyprlock, then the unlock animation + sound.
# Used by Super+L, the launcher's LOCK, and hypridle (idle + before sleep).

log="${XDG_STATE_HOME:-$HOME/.local/state}/stark/hyprlock.log"

# Not locking after all. Super+L shut the doors before calling us, so open them again unless
# a lock is up or on its way (another run, e.g. lid.sh + hypridle, may be about to start
# hyprlock): never leave the doors shut on an unlocked desktop.
give_up() {
    sleep 2
    [ "$(hyprctl locked 2>/dev/null)" = true ] || pidof hyprlock >/dev/null \
        || qs ipc call stark unlocked >/dev/null 2>&1
    exit 0
}

# Already locked (or a lock is starting right now, e.g. lid.sh + hypridle)? Do nothing.
# Except: after an unlock hyprlock can linger ~25 s while it waits on fprintd (a wedged
# reader never answers its release), and that run of this script still holds the lock file.
# That hyprlock isn't a lock any more (its log says it unlocked and the session is
# unlocked): end it and lock again.
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/stark-lock.lock"
if ! flock -n 9 || pidof hyprlock >/dev/null; then
    grep -qs 'Unlocked, exiting!' "$log" && [ "$(hyprctl locked 2>/dev/null)" = false ] || give_up
    pkill -x hyprlock
    flock -w 3 9 || give_up
    pidof hyprlock >/dev/null && { pkill -KILL -x hyprlock; sleep 0.2; }
fi

# Screens still coming or going (a TV just unplugged; the HUD's settle gate, Hotplug.qml)?
# Wait for them, about 2 s at most, so hyprlock never starts on outputs that are changing (it
# crashes on an output change mid-lock). A flag older than 10 s is stale (a crashed HUD).
# logind gives a lid / before-sleep lock 5 s (InhibitDelayMaxSec), so this still fits.
settle="${XDG_RUNTIME_DIR:-/tmp}/stark-hotplug-settling"
for _ in $(seq 40); do      # ~2.2 s with the date/stat calls
    [ -f "$settle" ] && [ $(( $(date +%s) - $(stat -c %Y "$settle" 2>/dev/null || echo 0) )) -lt 10 ] || break
    sleep 0.05
done

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
mkdir -p "${log%/*}" && { [ -f "$log" ] && mv -f "$log" "$log.1"; }
# Start the reveal the moment authentication succeeds (password, fingerprint, SIGUSR1),
# i.e. when hyprlock begins its fade-out, not when it exits. After the screens were off
# or the system slept, Quickshell's windows show nothing until they draw again, and
# hyprlock faded onto black; this way the doors redraw during the fade. (hyprlock also
# lingers ~2 s after a fingerprint unlock while PAM's fail delay ends the aborted
# password prompt.) "Unlocked" and hyprlock's exit stay as fallbacks.
#
# No suspend while fprintd opens the reader. hyprlock claims the fingerprint reader as it
# starts, and if a suspend begins while fprintd is still opening it (lock, then the lid
# shut within a second), the Elan MOC sensor (libfprint elanmoc) wedges until a power-off.
# fprintd reacts to logind's PrepareForSleep, which goes out before delay locks are waited
# on, so only a block lock helps: "handle-lid-switch" (honoured even with logind's
# LidSwitchIgnoreInhibited=yes, unlike "sleep") plus "sleep" for an explicit suspend.
# Held only until hyprlock says the scan is running, 3 s at most. A lid shut meanwhile
# isn't lost: logind keeps rechecking a closed lid and suspends the moment this ends.
systemd-inhibit --what=handle-lid-switch:sleep --mode=block --who="STARK lock" \
    --why="fingerprint reader opening" sleep 3 &
guard=$!
stdbuf -oL hyprlock 2>&1 | {
    opened=""
    while IFS= read -r line; do
        printf '%s\n' "$line" >>"$log"
        case "$line" in
            *"fprint: started verifying"*|*"fprint: "*[Ee]rror*|*"fprint: could not"*)
                [ -n "$guard" ] && { kill "$guard" 2>/dev/null; guard=""; } ;;
            *"auth: authenticated"*|*"status verify-match"*|*"Unlocking with a SIGUSR1"*|*"Unlocked, exiting!"*)
                [ -z "$opened" ] && { qs ipc call stark unlocked >/dev/null 2>&1 & opened=1; } ;;
        esac
    done
    [ -n "$guard" ] && kill "$guard" 2>/dev/null
    [ -n "$opened" ] || qs ipc call stark unlocked >/dev/null 2>&1
}
