#!/bin/sh
# STARK OS lid handler (Hyprland calls this when the lid closes).
# logind suspends on lid close by itself (hypridle's before_sleep_cmd locks first, holding
# an inhibitor until hyprlock is up). This script gets the lock and a dark screen in the
# right order without waiting for logind, and suspends itself when logind ignores the lid:
# for HoldoffTimeoutSec (5 s, logind.conf.d/alchemos.conf) after waking.

# Screens still coming or going (the HUD's settle gate, Hotplug.qml: a TV unplugged a
# moment ago)? Decide "docked" only once they've settled, about 2 s at most. A flag older
# than 10 s is stale (a crashed HUD).
settle="${XDG_RUNTIME_DIR:-/tmp}/alchemos-hotplug-settling"
for _ in $(seq 40); do      # ~2.2 s with the date/stat calls
    [ -f "$settle" ] && [ $(( $(date +%s) - $(stat -c %Y "$settle" 2>/dev/null || echo 0) )) -lt 10 ] || break
    sleep 0.05
done

# Docked (an external monitor connected)? Closing the lid shouldn't sleep (logind's
# HandleLidSwitchDocked=ignore agrees). `monitors all`, enabled ones: plain `monitors`
# leaves out a screen that mirrors another, so the TV mirror profile counted as 1.
[ "$(hyprctl monitors all -j | jq '[.[] | select(.disabled | not)] | length')" -gt 1 ] && exit 0

lid_closed() { grep -qs closed /proc/acpi/button/lid/*/state; }
sleeping() {
    busctl get-property org.freedesktop.login1 /org/freedesktop/login1 \
        org.freedesktop.login1.Manager PreparingForSleep 2>/dev/null | grep -q true
}

# 1. Doors and hyprlock first, screen off second. If the session locks while the screen
# is off, the HUD never gets drawn under the lock and unlocking flashes black or the
# desktop. alchemos-lock.sh (via hypridle's lock_cmd) shuts the doors before hyprlock starts;
# wait (at most ~1.5 s) until hyprlock reports the session locked.
if ! pidof hyprlock >/dev/null; then
    loginctl lock-session
    log="${XDG_STATE_HOME:-$HOME/.local/state}/alchemos/hyprlock.log"
    for _ in $(seq 30); do
        # alchemos-lock.sh rotates the log before it starts hyprlock, so with hyprlock
        # running this is the new lock's log.
        pidof hyprlock >/dev/null && grep -qs onLockLocked "$log" && break
        sleep 0.05
    done
fi

# 2. Dark. If logind already suspended while we waited, this runs after the wake, with
# the lid open again: then leave the screen on.
lid_closed || exit 0
"$HOME/.config/hypr/alchemos-dpms.sh" off >/dev/null

# 3. logind on its way to sleep? Then we're done. Otherwise it ignored the lid (holdoff
# after waking): suspend ourselves, if the lid is still closed. alchemos-lock.sh holds the
# lid off for up to 3 s while the fingerprint reader opens (logind suspends by itself
# when that ends), so wait that out before deciding.
guard_up() { systemd-inhibit --list --no-pager 2>/dev/null | grep -q 'fingerprint reader opening'; }
n=0
while [ $n -lt 10 ] || { guard_up && [ $n -lt 25 ]; }; do
    sleeping && exit 0
    sleep 0.2; n=$((n + 1))
done
lid_closed && systemctl suspend
