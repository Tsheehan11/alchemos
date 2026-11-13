#!/bin/sh
# STARK HUD launcher (autostart.lua): Quickshell with its log kept small.
#
# Quickshell logs every instance to $XDG_RUNTIME_DIR/quickshell/by-id/<id>/, which is
# tmpfs (RAM). On 2026-11-01 a QTimer warning repeated every millisecond from the DST
# fall-back on and log.log reached 700 MB.
#
# 1. --log-rules "default.warning=false": drops Qt's / Quickshell's *uncategorised*
#    warnings only: "QTimer::start: negative intervals…", "attempted to use dangling
#    screen object", "Layershell screen does not correspond to a real screen". QML
#    console.* (qml), QML errors (scene), Quickshell's own categories and every critical
#    stay. The rules apply to the log files as well as stdout.
# 2. Cap: every 5 min, any instance's log.log over 32 MiB keeps only its last 8 MiB.
#    Quickshell keeps the file open without O_APPEND, so it can't be truncated or
#    replaced; punching a hole frees the RAM and leaves the tail readable (grep -a).
#    log.qslog is binary (qs log), so it's left alone; it grows ~60× slower.
#    Dead instances' folders older than 7 days are removed.
# The cap loop runs for the whole Hyprland session, so it also covers a qs started by
# hand. Restart the HUD with this script, not a bare `qs`, to keep the log rules.

rules="default.warning=false"
dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/quickshell/by-id"
max=$((32 * 1024 * 1024))
keep=$((8 * 1024 * 1024))

cap() {
    for f in "$dir"/*/log.log; do
        [ -f "$f" ] || continue
        size=$(stat -c %s "$f" 2>/dev/null) || continue
        used=$(( $(stat -c %b "$f") * $(stat -c %B "$f") ))
        [ "$used" -gt "$max" ] || continue
        len=$(( (size - keep) / 4096 * 4096 ))
        [ "$len" -gt 0 ] && fallocate -p -o 0 -l "$len" "$f" 2>/dev/null \
            && logger -t alchemos-hud "log cap: ${f#"$dir"/} kept the last $((keep / 1048576)) MiB of $((size / 1048576)) MiB"
    done
    # Instances are live while a by-pid/<pid> link to their folder has a running pid
    bypid="${dir%/by-id}/by-pid"
    find "$dir" -mindepth 1 -maxdepth 1 -type d -mtime +7 2>/dev/null | while read -r d; do
        live=""
        for l in "$bypid"/*; do
            [ "$(readlink "$l")" = "$d" ] || continue
            kill -0 "${l##*/}" 2>/dev/null && live=1 || rm -f "$l"
        done
        [ -n "$live" ] || rm -rf "$d"
    done
}

# One cap loop per session
sock="${XDG_RUNTIME_DIR}/hypr/${HYPRLAND_INSTANCE_SIGNATURE}/.socket.sock"
loop_lock="${XDG_RUNTIME_DIR}/alchemos-hud-logcap.lock"
(
    flock -n 9 || exit 0
    while [ -S "$sock" ]; do cap; sleep 300; done
) 9>"$loop_lock" &

exec qs --log-rules "$rules" "$@"
