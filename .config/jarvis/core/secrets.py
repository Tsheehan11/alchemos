"""
Secrets (OAuth tokens, client IDs, the LEARN feed URL) live in the system keyring
(python keyring → libsecret / gnome-keyring), never in files tracked by `stark`.
Claude itself needs none: it authenticates through the claude CLI login.

    store("google", "token", json_text)
    get("google", "token")              # → str | None
    delete("google", "token")

Keyring entries are named "jarvis:<service>" / <account>, so they're easy to find
(and wipe) in Seahorse. The MCP servers import this too (see mcp/integration_common.py).
"""
import getpass

PREFIX = "jarvis:"


def _kr():
    import keyring       # imported late: only integrations need it, not every Jarvis start
    return keyring


def get(service, account):
    try:
        return _kr().get_password(PREFIX + service, account)
    except Exception:    # keyring locked / no Secret Service: treat as "not stored"
        return None


def store(service, account, value=None):
    value = value if value is not None else getpass.getpass(f"{service} {account}: ")
    _kr().set_password(PREFIX + service, account, value)


def delete(service, account):
    try:
        _kr().delete_password(PREFIX + service, account)
    except Exception:
        pass


def has(service, account):
    return bool(get(service, account))
