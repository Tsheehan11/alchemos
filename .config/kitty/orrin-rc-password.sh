#!/bin/sh
# geninclude for kitty.conf: the remote control password for Orrin's window reader, read from the keyring
# (orrin:kitty / rc_password, created by `orrin kitty-rc`), so it is never written in a file. Its actions
# are decided by orrin-rc-check.py (get-text over the socket only). No keyring entry → no line, and with
# allow_remote_control password and no password every request is refused.
pw=$(timeout 2 secret-tool lookup service orrin:kitty username rc_password 2>/dev/null || timeout 2 secret-tool lookup service jarvis:kitty username rc_password 2>/dev/null)   # jarvis: = before AlchemOS
case "$pw" in
    ''|*[!A-Za-z0-9_-]*) ;;
    *) printf 'remote_control_password "%s" orrin-rc-check.py\n' "$pw" ;;
esac
exit 0
