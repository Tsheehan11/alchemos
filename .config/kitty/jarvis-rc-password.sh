#!/bin/sh
# geninclude for kitty.conf: the remote control password for Jarvis's window reader, read from the keyring
# (jarvis:kitty / rc_password, created by `jarvis kitty-rc`), so it is never written in a file. Its actions
# are decided by jarvis-rc-check.py (get-text over the socket only). No keyring entry → no line, and with
# allow_remote_control password and no password every request is refused.
pw=$(timeout 2 secret-tool lookup service jarvis:kitty username rc_password 2>/dev/null)
case "$pw" in
    ''|*[!A-Za-z0-9_-]*) ;;
    *) printf 'remote_control_password "%s" jarvis-rc-check.py\n' "$pw" ;;
esac
exit 0
