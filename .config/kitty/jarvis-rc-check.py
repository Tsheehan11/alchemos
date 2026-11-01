# Remote control checker for the password Jarvis uses (kitty.conf → jarvis-rc-password.sh).
# kitty calls is_cmd_allowed for every request made with that password: only reading a window's text
# (get-text) is allowed, and only over the socket, never as an escape code written to a terminal, so
# nothing running inside a kitty window (or a remote host over ssh) can use it. Everything else
# (send-text, launch, close, set-*, ls, …) is refused.


def is_cmd_allowed(pcmd, window, from_socket, extra_data):
    return bool(from_socket) and pcmd.get('cmd') == 'get-text'
