#!/bin/sh
# STARK OS lid handler (Hyprland calls this when the lid closes).
# logind suspends on lid close by itself, and hypridle's before_sleep_cmd locks with an
# inhibitor so sleep waits until hyprlock is really up. This script makes the screen go
# dark at once, starts the lock without waiting for logind, and is the backup for when
# logind ignores the lid (for a few seconds after waking, while the lock screen is up).

# Docked (external monitors connected)? Then closing the lid shouldn't sleep.
[ "$(hyprctl monitors -j | grep -c '"name"')" -gt 1 ] && exit 0

hyprctl dispatch dpms off >/dev/null
pidof hyprlock >/dev/null || loginctl lock-session

# Is logind already on its way to sleep? Then we're done.
sleeping() {
    busctl get-property org.freedesktop.login1 /org/freedesktop/login1 \
        org.freedesktop.login1.Manager PreparingForSleep 2>/dev/null | grep -q true
}
for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleeping && exit 0
    sleep 0.2
done
# logind ignored the lid: suspend ourselves if it's still closed.
grep -qs closed /proc/acpi/button/lid/*/state && systemctl suspend
