"""
`orrin spotify …` and `orrin dj …` (dispatched before orrin.py's heavy imports; Settings polls
`orrin spotify status --json`).

  orrin spotify connect [CLIENT_ID]   walk through the developer app, then PKCE sign-in in the browser
  orrin spotify status [--json]       connected / account / Premium as far as known (keyring only, no network)
  orrin spotify disconnect            wipe the keyring entries
  orrin spotify devices               Spotify Connect devices (needs the network)
  orrin spotify now                   what Spotify reports as playing
  orrin dj start [MOOD…] | stop | status | more | less | keep | chatter off|rare|normal | save NAME | moods
                                       DJ mode in the running voice loop (core/dj.py, over its socket)
"""
import json
import sys

import spotify_api as S

WALKTHROUGH = f"""
Spotify for Orrin: your own developer app (Development Mode, free; the owner needs Premium).

  1. Open https://developer.spotify.com/dashboard and sign in with your Spotify account.
  2. Create app:
       App name         AlchemOS Orrin
       App description  Voice assistant on my own desktop
       Redirect URI     {S.REDIRECT_URI}      (click Add; Spotify refuses "localhost", use 127.0.0.1 exactly)
       APIs used        tick "Web API"
     Agree to the terms and Save.
  3. Open the app's Settings. Check the Redirect URI still reads 127.0.0.1 (one user report says the
     dashboard can rewrite it to localhost; if so, fix it and Save). Copy the Client ID.
     No client secret is needed: Orrin signs in with PKCE.
  4. If sign-in later says your user isn't registered: Settings → User Management → add your
     Spotify name and email.

Orrin asks for these permissions: {", ".join(S.SCOPES)}
Tokens go to the system keyring (orrin:spotify), never to a file.
"""


def status():
    a = S.account()
    connected = S.connected()
    missing = sorted(set(S.SCOPES) - S.granted_scopes()) if connected else []
    if not connected:
        detail = "Client ID saved · sign in" if S.client_id() else "Needs your Spotify developer app · CONNECT walks you through it"
    elif missing:
        detail = "Missing permissions · reconnect"
    elif a.get("premium") is False:
        detail = "Not Premium · play / pause / skip only (MPRIS)"
    else:
        detail = "Playback, queue, library, DJ mode"
    return {"connected": connected, "user": a.get("name", ""), "premium": a.get("premium"), "client": bool(S.client_id()),
            "missing": missing, "detail": detail}


def connect(args):
    cid = args[0].strip() if args else ""
    if not cid:
        print(WALKTHROUGH)
        have = S.client_id()
        if have:
            ans = input(f"Client ID [{have[:6]}…, Enter to keep]: ").strip() if sys.stdin.isatty() else ""
            cid = ans or have
        else:
            cid = input("Client ID: ").strip() if sys.stdin.isatty() else ""
    if not cid or len(cid) < 16:
        print("No Client ID: nothing changed.")
        return 1
    try:
        _, me = S.sign_in(cid)
    except S.SpotifyError as e:
        print(f"Sign-in failed: {e}")
        if "redirect" in str(e).lower() or "INVALID_CLIENT" in str(e):
            print(f"Check the app's Redirect URI is exactly {S.REDIRECT_URI}.")
        return 1
    print(f"Spotify connected as {me.get('display_name') or me.get('id')}. Token stored in the system keyring.")
    try:
        devs = S.devices()
        print("Devices Spotify sees now: " + (", ".join(f"{d['name']} ({d['type']})" for d in devs) or "none (open Spotify)"))
    except S.SpotifyError as e:
        print(f"(Couldn't list devices: {e})")
    print('Try: "Hey Jarvis, play Discovery by Daft Punk" or "DJ for me".')
    return 0


def devices():
    try:
        for d in S.devices():
            print(f"{'▶' if d.get('is_active') else ' '} {d['name']:<30} {d['type']:<12} vol {d.get('volume_percent')}")
    except S.SpotifyError as e:
        print(f"Couldn't list devices: {e}")
        return 1
    return 0


def dj(args):
    from core import dj as D
    op = args[0] if args else "status"
    rest = args[1:]
    req = {"start": lambda: ("start", {"mood": " ".join(rest)}), "stop": lambda: ("stop", {}),
           "status": lambda: ("status", {}), "more": lambda: ("adjust", {"direction": "more"}),
           "less": lambda: ("adjust", {"direction": "less"}), "keep": lambda: ("keep", {}),
           "chatter": lambda: ("chatter", {"level": rest[0] if rest else ""}),
           "save": lambda: ("save_mood", {"name": " ".join(rest)}), "moods": lambda: ("moods", {})}
    if op not in req:
        print(__doc__)
        return 2
    name, kw = req[op]()
    r = D.request(name, **kw)
    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0 if r.get("ok") else 1


def main(argv):
    if argv[0] == "dj":
        return dj(argv[1:])
    cmd, rest = (argv[1] if len(argv) > 1 else "status"), argv[2:]
    if cmd == "connect":
        return connect(rest)
    if cmd == "disconnect":
        S.disconnect()
        print("Spotify: keyring entries removed.")
        return 0
    if cmd == "status":
        st = status()
        if "--json" in rest:
            print(json.dumps(st))
        else:
            print(("CONNECTED" if st["connected"] else "NOT CONNECTED") + (f" as {st['user']}" if st["user"] else "")
                  + f" · {st['detail']}")
        return 0
    if cmd == "devices":
        return devices()
    if cmd == "now":
        try:
            print(json.dumps(S.now_playing(), indent=2, ensure_ascii=False))
        except S.SpotifyError as e:
            print(e.say)
            return 1
        return 0
    print(__doc__)
    return 2
