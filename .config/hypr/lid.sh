#!/bin/sh
# STARK OS lid handler (Hyprland calls this when the lid closes).
# Normally the system already locks + sleeps on lid close. This is the backup for
# when it doesn't — e.g. you close the lid again right after waking, while the lock
# screen is up (the system ignores the lid for a few seconds after waking).

# Docked (external monitors connected)? Then closing the lid shouldn't sleep.
[ "$(hyprctl monitors -j | grep -c '"name"')" -gt 1 ] && exit 0

sleep 3
# Still closed after 3 s and still awake → lock (if needed) and sleep
if grep -qs closed /proc/acpi/button/lid/*/state; then
    pidof hyprlock >/dev/null || loginctl lock-session
    sleep 1
    systemctl suspend
fi
