"""
Secrets (OAuth tokens, client IDs, the LEARN feed URL) live in the system keyring
(python keyring → libsecret / gnome-keyring), never in files tracked by `alc`.
Claude itself needs none: it authenticates through the claude CLI login.

    store("google", "token", json_text)
    get("google", "token")              # → str | None
    delete("google", "token")

Keyring entries are named "orrin:<service>" / <account>, so they're easy to find
(and wipe) in Seahorse. The MCP servers import this too (see mcp/integration_common.py).

Before AlchemOS they were "jarvis:<service>". get() still finds those and copies them to
"orrin:" on first read, so nothing needs signing in again; `orrin secrets migrate` copies them
all at once and `orrin secrets migrate --prune` deletes the old ones after checking each copy.
"""
import getpass

PREFIX = "orrin:"
OLD_PREFIX = "jarvis:"


def _kr():
    import keyring       # imported late: only integrations need it, not every Orrin start
    return keyring


def get(service, account):
    try:
        v = _kr().get_password(PREFIX + service, account)
        if v is None:
            v = _kr().get_password(OLD_PREFIX + service, account)
            if v is not None:
                try:
                    _kr().set_password(PREFIX + service, account, v)   # carried over; the old entry stays until --prune
                except Exception:
                    pass
        return v
    except Exception:    # keyring locked / no Secret Service: treat as "not stored"
        return None


def store(service, account, value=None):
    value = value if value is not None else getpass.getpass(f"{service} {account}: ")
    _kr().set_password(PREFIX + service, account, value)


def delete(service, account):
    for prefix in (PREFIX, OLD_PREFIX):
        try:
            _kr().delete_password(prefix + service, account)
        except Exception:
            pass


def has(service, account):
    return bool(get(service, account))


def _old_entries():
    """(service, account) of every pre-AlchemOS "jarvis:" entry (attributes only, no secrets)."""
    import subprocess
    r = subprocess.run(["secret-tool", "search", "--all", "--unlock", "xdg:schema", "org.freedesktop.Secret.Generic"],
                       capture_output=True, text=True, timeout=20)
    out, svc = [], None
    for line in (r.stdout + "\n" + r.stderr).splitlines():
        k, _, v = line.partition(" = ")
        if k == "attribute.service":
            svc = v
        elif k == "attribute.username" and svc and svc.startswith(OLD_PREFIX):
            out.append((svc[len(OLD_PREFIX):], v))
            svc = None
    return sorted(set(out))


def migrate(prune=False):
    """Copy every "jarvis:" entry to "orrin:" (verified by reading it back). With prune, delete the old
    entry only once its copy reads back identical. Returns lines for the CLI."""
    kr, lines = _kr(), []
    for service, account in _old_entries():
        old = kr.get_password(OLD_PREFIX + service, account)
        new = kr.get_password(PREFIX + service, account)
        if new is None and old is not None:
            kr.set_password(PREFIX + service, account, old)
            new = kr.get_password(PREFIX + service, account)
        ok = old is not None and new == old
        state = "copied" if ok else ("already moved" if old is None and new is not None else "MISMATCH, left alone")
        if prune and ok:
            kr.delete_password(OLD_PREFIX + service, account)
            state = "moved, old entry deleted"
        lines.append(f"{service:10s} {account:22s} {state}")
    return lines or ["no jarvis: entries left"]
