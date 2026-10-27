"""
Phase-2 integrations from the CLI side: status for Settings → JARVIS → INTEGRATIONS,
and the sign-in flows.

  jarvis integrations [--json]
  jarvis connect google [CLIENT_SECRET.json]     OAuth desktop flow (docs/phase2-google.md)
  jarvis connect microsoft [CLIENT_ID [TENANT]]  MSAL device code flow (docs/phase2-microsoft.md)
  jarvis connect learn-ical [URL]                LEARN's private calendar feed
  jarvis disconnect google|microsoft|learn-ical

Everything secret goes to the system keyring (core/secrets.py). A successful connect sets
"enabled": true on the servers.json entry and restarts the voice loop so it loads the new
MCP server; disconnect wipes the keyring entries and disables it again.
"""
import json
import os
import signal
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from . import config as C
from . import secrets

import academic  # noqa: E402  (mcp/ is on sys.path; see jarvis.py)

DOCS = C.JARVIS_DIR / "docs"
PIP = f"uv pip install --python {C.JARVIS_DIR}/.venv/bin/python"
# Entra ID errors that mean "the tenant won't let you consent to this app yourself"
CONSENT_BLOCKED = {65001, 90094, 90095, 50105, 530032}
MSAL_RESERVED = {"offline_access", "openid", "profile"}   # MSAL adds these itself and rejects them in scopes


def _entry_for(auth):
    for key, e in C.integrations().items():
        if e.get("auth") == auth:
            return key, e
    raise SystemExit(f"no integration in servers.json uses auth '{auth}'")


def _state(key, e):
    """(connected, detail)"""
    if key == "google":
        if secrets.has("google", "token"):
            return True, "Read-only · token in the system keyring"
        return False, "Needs an OAuth client · docs/phase2-google.md" if not secrets.has("google", "client") else "Client saved · sign in"
    if key == "microsoft":
        if secrets.has("microsoft", "token"):
            return True, "Read-only · token in the system keyring"
        if secrets.has("microsoft", "blocked"):
            return False, "UWaterloo needs admin consent · using the LEARN feed instead"
        return False, "May need university admin consent · docs/phase2-microsoft.md"
    if key == "academic":
        feed = secrets.has("learn", "ical_url")
        inbox = secrets.has("google", "token") or secrets.has("microsoft", "token")
        if feed:
            return True, "LEARN feed" + (" · grade notices from your inbox" if inbox else " · connect an inbox for grade notices")
        return False, "Paste your LEARN calendar feed URL"
    return False, ""


def status():
    out = []
    for key, e in C.integrations().items():
        connected, detail = _state(key, e)
        out.append({"key": key, "name": e.get("name", key), "label": e.get("label", ""), "auth": e.get("auth", key),
                    "enabled": bool(e.get("enabled")), "connected": connected,
                    "state": "CONNECTED" if connected else "NOT CONNECTED", "detail": detail})
    return out


def print_status(as_json=False):
    rows = status()
    if as_json:
        print(json.dumps(rows, ensure_ascii=False))
        return
    for r in rows:
        print(f"{r['name']:<15} {r['state']:<14} {'on ' if r['enabled'] else 'off'}  {r['detail']}")


def _set_enabled(key, on):
    raw = C.read_servers()
    if raw[key].get("enabled") != on:
        raw[key]["enabled"] = on
        C.write_servers(raw)


def _restart_voice():
    """The voice loop reads servers.json at start; the HUD restarts it when it exits."""
    me = os.getpid()
    for d in Path("/proc").iterdir():
        if not d.name.isdigit() or int(d.name) == me:
            continue
        try:
            argv = (d / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        args = [a for a in argv if a]
        if len(args) >= 2 and args[-1].endswith(b"/jarvis.py"):   # voice mode = jarvis.py with no arguments
            os.kill(int(d.name), signal.SIGTERM)
            print("Restarted Jarvis so it loads the new integration.")


def _ask(prompt, hidden=False):
    if not sys.stdin.isatty():
        return ""
    if hidden:
        import getpass
        return getpass.getpass(prompt).strip()
    return input(prompt).strip()


def _done(key):
    _set_enabled(key, True)
    _restart_voice()
    return 0


# ── Google: OAuth desktop app (a loopback redirect on 127.0.0.1, only while you sign in) ──
def connect_google(args):
    key, e = _entry_for("google")
    if args:
        p = Path(args[0]).expanduser()
        try:
            client = json.loads(p.read_text())
        except (OSError, ValueError) as err:
            print(f"Couldn't read {p}: {err}")
            return 1
        if "installed" not in client:
            print("That isn't a Desktop app client (no \"installed\" section). See docs/phase2-google.md, step 3.")
            return 1
        secrets.store("google", "client", json.dumps(client))
        print(f"Saved the OAuth client to the keyring. You can delete {p} now.")
    client = secrets.get("google", "client")
    if not client:
        path = _ask("Path to the client_secret_….json you downloaded (Enter to stop): ")
        if not path:
            print(f"No OAuth client yet. Follow {DOCS / 'phase2-google.md'} first.")
            return 1
        return connect_google([path])
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(f"Install the Google libraries first:\n  {PIP} google-auth-oauthlib google-api-python-client")
        return 1
    scopes = list(e["scopes"])
    if C.Config()["jarvisAssignmentsAccount"] == "google":
        scopes += e.get("write_scopes", [])
    flow = InstalledAppFlow.from_client_config(json.loads(client), scopes)
    print("Opening Google sign-in in the browser… (read-only access"
          + (", plus calendars Jarvis creates" if len(scopes) > len(e["scopes"]) else "") + ")")
    creds = flow.run_local_server(host="localhost", bind_addr="127.0.0.1", port=0, open_browser=True,
                                  prompt="consent", access_type="offline",
                                  success_message="Jarvis is connected. You can close this tab.")
    secrets.store("google", "token", creds.to_json())
    print("Google connected (read-only). Token stored in the system keyring.")
    return _done(key)


# ── Microsoft 365: MSAL device code flow (no listener, sign in on any device) ──
def connect_microsoft(args):
    key, e = _entry_for("microsoft")
    client_id = args[0] if args else secrets.get("microsoft", "client_id") or _ask("Application (client) ID: ")
    tenant = args[1] if len(args) > 1 else secrets.get("microsoft", "tenant") or "organizations"
    if not client_id:
        print(f"No app registration yet. Follow {DOCS / 'phase2-microsoft.md'} first.")
        return 1
    secrets.store("microsoft", "client_id", client_id)
    secrets.store("microsoft", "tenant", tenant)
    try:
        import msal
    except ImportError:
        print(f"Install MSAL first:\n  {PIP} msal")
        return 1
    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(client_id, authority=f"https://login.microsoftonline.com/{tenant}",
                                       token_cache=cache)
    scopes = [s for s in e["scopes"] if s not in MSAL_RESERVED]
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        print(f"Microsoft refused to start sign-in: {flow.get('error_description') or flow}")
        print("If it mentions public client flows, turn on 'Allow public client flows' (docs/phase2-microsoft.md, step 4).")
        return 1
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        secrets.store("microsoft", "token", cache.serialize())
        secrets.delete("microsoft", "blocked")
        print("Microsoft 365 connected. Token cache stored in the system keyring.")
        return _done(key)
    codes = set(result.get("error_codes") or [])
    desc = result.get("error_description", "") or str(result)
    if codes & CONSENT_BLOCKED or ("admin" in desc.lower() and "consent" in desc.lower()):
        secrets.store("microsoft", "blocked", ",".join(map(str, sorted(codes))) or "consent")
        print("UWaterloo needs an administrator to approve this app, so Outlook stays off.\n"
              "Jarvis falls back to what needs no consent:\n"
              "  jarvis connect learn-ical <your LEARN feed URL>   assignments and due dates\n"
              "  jarvis connect google                             an inbox for LEARN / Crowdmark grade notices\n"
              "  (or forward UW mail to Gmail, see docs/phase2-microsoft.md)")
        return 2
    print(f"Sign-in failed: {desc.splitlines()[0] if desc else result}")
    return 1


# ── LEARN: private iCal feed (no consent needed) ──
def _feed_url(raw):
    u = raw.strip().strip("<>\"'")
    if u.startswith("webcal://"):
        u = "https://" + u[len("webcal://"):]
    p = urllib.parse.urlparse(u)
    if p.scheme != "https" or not p.netloc:
        raise ValueError("expected an https:// (or webcal://) feed URL")
    return u, p.netloc


def sync_learn_feed(url=None):
    """Fetch the feed → deduplicated assignments in academic.json. Returns (total, upcoming)."""
    url = url or secrets.get("learn", "ical_url")
    req = urllib.request.Request(url, headers={"User-Agent": "stark-jarvis/2"})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read(5_000_000).decode("utf-8", "replace")
    items = academic.dedupe(academic.parse_ical(text))
    st = academic.load_state()
    st["assignments"] = {a["key"]: dict(a, due=a["due"].isoformat()) for a in items}
    academic.save_state(st)
    return len(items), len(academic.upcoming(items))


def connect_learn(args):
    key, _ = _entry_for("learn-ical")
    raw = args[0] if args else _ask("LEARN calendar feed URL (Calendar → Subscribe; it's private, so it stays hidden): ", hidden=True)
    if not raw:
        print("No URL. On LEARN: Calendar → Subscribe → copy the feed URL.")
        return 1
    try:
        url, host = _feed_url(raw)
    except ValueError as err:
        print(f"That doesn't look right: {err}.")
        return 1
    if not host.endswith("uwaterloo.ca") and "d2l" not in host:
        print(f"Note: {host} isn't learn.uwaterloo.ca; saving it anyway.")
    secrets.store("learn", "ical_url", url)
    print("Saved the feed URL to the keyring.")
    try:
        total, soon = sync_learn_feed(url)
        print(f"Synced {total} assignments from LEARN ({soon} due in the next two weeks).")
    except Exception as err:
        print(f"Saved, but the first sync failed: {err}")
    print("Calendar writes start once Google or Outlook is connected (and stay behind confirmation"
          " unless Settings → JARVIS → AUTO-ADD ASSIGNMENTS is on).")
    return _done(key)


def disconnect(target):
    wipe = {"google": [("google", "token"), ("google", "client")],
            "microsoft": [("microsoft", "token"), ("microsoft", "blocked"), ("microsoft", "client_id"), ("microsoft", "tenant")],
            "learn-ical": [("learn", "ical_url")]}
    if target not in wipe:
        print(f"usage: jarvis disconnect {'|'.join(wipe)}")
        return 2
    for s, a in wipe[target]:
        secrets.delete(s, a)
    key, _ = _entry_for(target)
    _set_enabled(key, False)
    print(f"{target}: keyring entries removed, integration disabled.")
    _restart_voice()
    return 0


def main(argv):
    """argv after `jarvis`: ["connect", "google", ...] etc."""
    cmd, rest = argv[0], argv[1:]
    if cmd == "integrations":
        print_status("--json" in rest)
        return 0
    if cmd == "disconnect":
        return disconnect(rest[0] if rest else "")
    flows = {"google": connect_google, "microsoft": connect_microsoft, "learn-ical": connect_learn}
    if not rest or rest[0] not in flows:
        print(f"usage: jarvis connect {'|'.join(flows)} [...]   (see {DOCS})")
        return 2
    return flows[rest[0]](rest[1:])
