#!/bin/sh
# STARK OS lid handler (Hyprland calls this when the lid closes).
# logind suspends on lid close by itself (hypridle's before_sleep_cmd locks first, holding
# an inhibitor until hyprlock is up). This script gets the lock and a dark screen in the
# right order without waiting for logind, and suspends itself when logind ignores the lid:
# for HoldoffTimeoutSec (5 s, logind.conf.d/stark.conf) after waking.

# Docked (an external monitor connected)? Closing the lid shouldn't sleep (logind's
# HandleLidSwitchDocked=ignore agrees).
[ "$(hyprctl monitors -j | jq length)" -gt 1 ] && exit 0

lid_closed() { grep -qs closed /proc/acpi/button/lid/*/state; }
sleeping() {
    busctl get-property org.freedesktop.login1 /org/freedesktop/login1 \
        org.freedesktop.login1.Manager PreparingForSleep 2>/dev/null | grep -q true
}

# 1. Doors and hyprlock first, screen off second. If the session locks while the screen
# is off, the HUD never gets drawn under the lock and unlocking flashes black or the
# desktop. stark-lock.sh (via hypridle's lock_cmd) shuts the doors before hyprlock starts;
# wait (at most ~1.5 s) until hyprlock reports the session locked.
if ! pidof hyprlock >/dev/null; then
    loginctl lock-session
    log="${XDG_STATE_HOME:-$HOME/.local/state}/stark/hyprlock.log"
    for _ in $(seq 30); do
        # stark-lock.sh rotates the log before it starts hyprlock, so with hyprlock
        # running this is the new lock's log.
        pidof hyprlock >/dev/null && grep -qs onLockLocked "$log" && break
        sleep 0.05
    done
fi

# 2. Dark. If logind already suspended while we waited, this runs after the wake, with
# the lid open again: then leave the screen on.
lid_closed || exit 0
hyprctl dispatch dpms off >/dev/null

# 3. logind on its way to sleep? Then we're done. Otherwise it ignored the lid (holdoff
# after waking): suspend ourselves, if the lid is still closed.
for _ in $(seq 10); do
    sleeping && exit 0
    sleep 0.2
done
lid_closed && systemctl suspend
