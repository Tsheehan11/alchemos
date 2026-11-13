"""
Spotify for Orrin: the Web API on Trevor's own Spotify developer app (Development Mode), with
MPRIS (playerctl) as the fallback for play / pause / next / previous.

Sign-in: PKCE (no client secret) through a loopback redirect, http://127.0.0.1:8898/callback, open
only while `orrin spotify connect` waits for the browser (Spotify rejects "localhost" redirects).
Everything stored goes to the system keyring next to the Google entries (core/secrets.py):

  orrin:spotify / client_id   the app's Client ID (not secret with PKCE, kept there anyway)
  orrin:spotify / token       {"access_token", "refresh_token", "expires_at", "scope"}
  orrin:spotify / account     {"id", "name", "premium": true | false | null}

The access token lasts an hour and is refreshed on demand. Several processes use it (the voice
loop's DJ, the alchemos MCP server, the CLI) and Spotify may rotate the refresh token, so a refresh
holds a file lock and re-reads the keyring first: only one process refreshes, the rest pick up
its token.

Development Mode rules this follows (developer.spotify.com, Feb 2026 changes): the app owner needs
Premium, player endpoints need Premium, search returns at most 10 per call, saving uses
PUT /me/library, and recommendations / audio-features / related artists are not available, so
nothing here calls them. A 403 PREMIUM_REQUIRED is remembered (account.premium = false) and the
player falls back to MPRIS, saying so.

Results are dicts like alchemos_actions: {"ok": True, ...} or {"ok": False, "error", "say"}.
"""
import base64
import fcntl
import hashlib
import json
import os
import re
import secrets as _rand
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ORRIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ORRIN_DIR not in sys.path:
    sys.path.append(ORRIN_DIR)   # appended: ~/.config/orrin/mcp must not shadow the mcp package
from core import secrets  # noqa: E402

API = "https://api.spotify.com/v1"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
PORT = 8898
REDIRECT_URI = f"http://127.0.0.1:{PORT}/callback"
SCOPES = ["user-read-playback-state", "user-modify-playback-state", "user-read-currently-playing",
          "user-read-recently-played", "user-top-read", "user-library-read", "user-library-modify",
          "playlist-read-private", "playlist-read-collaborative"]
RUNTIME = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
LOCK_FILE = os.path.join(RUNTIME, "orrin", "spotify.lock")
TIMEOUT = 8
NOT_CONNECTED_SAY = "Spotify isn't connected yet, sir. Run orrin spotify connect, or use Settings, under Orrin."
PREMIUM_SAY = "That needs Spotify Premium, sir. I can only play, pause and skip on this account."

_cache = {"token": None}
_mem_lock = threading.Lock()


class SpotifyError(Exception):
    def __init__(self, msg, status=0, reason="", say=""):
        super().__init__(msg)
        self.status, self.reason, self.say = status, reason, say or f"Spotify said no, sir: {msg}."


class NotConnected(SpotifyError):
    def __init__(self):
        super().__init__("Spotify is not connected", say=NOT_CONNECTED_SAY)


class PremiumRequired(SpotifyError):
    def __init__(self):
        super().__init__("Spotify Premium is required for that", 403, "PREMIUM_REQUIRED", PREMIUM_SAY)


class NoDevice(SpotifyError):
    def __init__(self, msg="no active Spotify device"):
        super().__init__(msg, 404, "NO_ACTIVE_DEVICE", "Spotify isn't open anywhere I can reach, sir.")


# ── stored state ──
def client_id():
    return (secrets.get("spotify", "client_id") or "").strip()


def connected():
    return secrets.has("spotify", "token")


def account():
    try:
        return json.loads(secrets.get("spotify", "account") or "{}")
    except ValueError:
        return {}


def _set_account(**kw):
    a = account()
    if all(a.get(k) == v for k, v in kw.items()):
        return
    a.update(kw)
    try:
        secrets.store("spotify", "account", json.dumps(a))
    except Exception:
        pass


def premium():
    """True / False / None (not known yet: nothing has failed with PREMIUM_REQUIRED)."""
    return account().get("premium")


# ── HTTP ──
def _http(method, url, data=None, headers=None, timeout=TIMEOUT):
    """→ (status, headers, parsed JSON or None). Never raises on HTTP errors."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            status, hdrs = r.status, r.headers
    except urllib.error.HTTPError as e:
        body, status, hdrs = e.read(), e.code, e.headers
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise SpotifyError(f"network: {getattr(e, 'reason', e)}", say="I can't reach Spotify right now, sir.")
    try:
        parsed = json.loads(body) if body else None
    except ValueError:
        parsed = None
    return status, hdrs, parsed


def _post_form(url, fields):
    return _http("POST", url, urllib.parse.urlencode(fields).encode(),
                 {"Content-Type": "application/x-www-form-urlencoded"})


# ── tokens ──
def _store_token(tok, old_refresh=None):
    data = {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token") or old_refresh,
            "expires_at": time.time() + int(tok.get("expires_in", 3600)) - 60, "scope": tok.get("scope", "")}
    secrets.store("spotify", "token", json.dumps(data))
    _cache["token"] = data
    return data


def _load_token():
    raw = secrets.get("spotify", "token")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _refresh(force=False):
    """Refresh under a cross-process lock; another process may already have done it."""
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    with open(LOCK_FILE, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            tok = _load_token()
            if not tok:
                raise NotConnected()
            if not force and tok.get("expires_at", 0) > time.time() + 30:
                _cache["token"] = tok          # someone else refreshed it
                return tok
            if force and _cache["token"] and tok["access_token"] != _cache["token"]["access_token"]:
                _cache["token"] = tok          # rejected token was stale: use the newer stored one
                return tok
            cid = client_id()
            if not cid or not tok.get("refresh_token"):
                raise NotConnected()
            status, _, body = _post_form(TOKEN_URL, {"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                                     "client_id": cid})
            if status != 200 or not body or "access_token" not in body:
                err = (body or {}).get("error", status)
                if err == "invalid_grant":     # revoked or expired: sign in again
                    secrets.delete("spotify", "token")
                    raise NotConnected()
                raise SpotifyError(f"token refresh failed ({err})", status, say="Spotify's sign-in needs a refresh, sir.")
            return _store_token(body, tok["refresh_token"])
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def access_token():
    with _mem_lock:
        tok = _cache["token"]
        if not tok or tok.get("expires_at", 0) <= time.time():
            tok = _load_token()
            if not tok:
                raise NotConnected()
            if tok.get("expires_at", 0) <= time.time():
                tok = _refresh()
            _cache["token"] = tok
        return tok["access_token"]


def api(method, path, params=None, body=None, _retry=True):
    """One Web API call → parsed JSON (None for 204). Raises SpotifyError subclasses."""
    url = API + path + ("?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}) if params else "")
    headers = {"Authorization": f"Bearer {access_token()}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif method in ("PUT", "POST"):
        data = b""
    status, hdrs, parsed = _http(method, url, data, headers)
    if status in (200, 201, 202):
        return parsed
    if status == 204:
        return None
    err = (parsed or {}).get("error") or {}
    msg = err.get("message", "") if isinstance(err, dict) else str(err)
    reason = err.get("reason", "") if isinstance(err, dict) else ""
    if status == 401 and _retry:
        with _mem_lock:
            _cache["token"] = _refresh(force=True)
        return api(method, path, params, body, _retry=False)
    if status == 429 and _retry:
        wait = min(5, int((hdrs or {}).get("Retry-After", "1") or 1))
        time.sleep(wait)
        return api(method, path, params, body, _retry=False)
    if status == 403 and (reason == "PREMIUM_REQUIRED" or "premium" in msg.lower()):
        _set_account(premium=False)
        raise PremiumRequired()
    if status == 404 and (reason == "NO_ACTIVE_DEVICE" or "device" in msg.lower()):
        raise NoDevice(msg or "no active device")
    if status == 403 and "user may not be registered" in msg.lower():
        raise SpotifyError(msg, status, reason, "Your account isn't on the app's user list, sir. Add it in the Spotify dashboard, under User Management.")
    raise SpotifyError(f"{status} {msg or reason}".strip(), status, reason)


def _premium_ok():
    if premium() is not True:
        _set_account(premium=True)


# ── sign-in (PKCE) ──
def _pkce():
    verifier = base64.urlsafe_b64encode(_rand.token_bytes(64)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def auth_url(cid, challenge, state):
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "response_type": "code", "redirect_uri": REDIRECT_URI, "code_challenge_method": "S256",
        "code_challenge": challenge, "scope": " ".join(SCOPES), "state": state})


def _wait_for_code(state, timeout=300):
    """A one-shot HTTP listener on 127.0.0.1:PORT, only while signing in. → code."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    got = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if urllib.parse.urlparse(self.path).path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            if q.get("state", [""])[0] != state:
                got["error"] = "state mismatch"
            elif "error" in q:
                got["error"] = q["error"][0]
            else:
                got["code"] = q.get("code", [""])[0]
            ok = "code" in got
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(("<html><body style='background:#05080c;color:#7fe7ff;font-family:monospace;padding:40px'>"
                              + ("Orrin is connected to Spotify. You can close this tab." if ok else
                                 f"Spotify sign-in failed: {got.get('error')}") + "</body></html>").encode())

        def log_message(self, *a):
            pass

    try:
        srv = HTTPServer(("127.0.0.1", PORT), H)
    except OSError as e:
        raise SpotifyError(f"port {PORT} is busy ({e})", say=f"Port {PORT} is in use.")
    srv.timeout = 2
    end = time.time() + timeout
    try:
        while not got and time.time() < end:
            srv.handle_request()
    finally:
        srv.server_close()
    if "code" not in got:
        raise SpotifyError(got.get("error", "timed out waiting for the browser"))
    return got["code"]


def sign_in(cid, open_browser=True, log=print):
    verifier, challenge = _pkce()
    state = _rand.token_urlsafe(16)
    url = auth_url(cid, challenge, state)
    log("Opening Spotify sign-in in the browser… If it doesn't open, paste this link:\n  " + url)
    if open_browser:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    code = _wait_for_code(state)
    status, _, body = _post_form(TOKEN_URL, {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
                                             "client_id": cid, "code_verifier": verifier})
    if status != 200 or not body or "access_token" not in body:
        raise SpotifyError(f"token exchange failed: {(body or {}).get('error_description') or (body or {}).get('error') or status}")
    secrets.store("spotify", "client_id", cid)
    tok = _store_token(body)
    me = api("GET", "/me") or {}
    _set_account(id=me.get("id", ""), name=me.get("display_name") or me.get("id", ""), premium=account().get("premium"))
    return tok, me


def disconnect():
    for a in ("token", "account", "client_id"):
        secrets.delete("spotify", a)
    _cache["token"] = None


def granted_scopes():
    tok = _load_token() or {}
    return set((tok.get("scope") or "").split())


# ── MPRIS fallback ──
def mpris(action):
    """playerctl on Spotify's own MPRIS player (works without the Web API and without Premium)."""
    cmd = {"play": "play", "pause": "pause", "play_pause": "play-pause", "next": "next", "previous": "previous"}[action]
    try:
        r = subprocess.run(["playerctl", "-p", "spotify", cmd], capture_output=True, text=True, timeout=4)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": str(e)}
    if r.returncode != 0:
        return {"ok": False, "error": "Spotify isn't running" if "No players" in (r.stderr or "") else (r.stderr or "").strip()[:200]}
    return {"ok": True, "via": "mpris"}


def mpris_open(uri):
    """Spotify's MPRIS OpenUri: plays a spotify: URI in the desktop app (the non-Premium fallback for play X)."""
    try:
        r = subprocess.run(["playerctl", "-p", "spotify", "open", uri], capture_output=True, text=True, timeout=4)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def mpris_track():
    """(track id, status) from the desktop app's MPRIS, or (None, None). No network."""
    try:
        r = subprocess.run(["playerctl", "-p", "spotify", "metadata", "--format", "{{mpris:trackid}}\t{{status}}"],
                           capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if r.returncode != 0 or "\t" not in r.stdout:
        return None, None
    tid, status = r.stdout.strip().split("\t", 1)
    m = re.search(r"track[:/]([A-Za-z0-9]{22})", tid)
    return (m.group(1) if m else None), status


# ── shapes ──
def track_info(t):
    if not t:
        return None
    alb = t.get("album") or {}
    return {"id": t.get("id"), "uri": t.get("uri"), "title": t.get("name", ""),
            "artist": ", ".join(a.get("name", "") for a in t.get("artists") or [] if a.get("name")),
            "album": alb.get("name", ""), "year": (alb.get("release_date") or "")[:4],
            "ms": t.get("duration_ms", 0), "art": ((alb.get("images") or [{}])[0] or {}).get("url", "")}


# ── player ──
def state():
    """GET /me/player → dict or None (nothing active)."""
    return api("GET", "/me/player", {"additional_types": "episode"})


def devices():
    return (api("GET", "/me/player/devices") or {}).get("devices", [])


LOCAL_NAMES = {socket.gethostname().lower()}
DEVICE_WORDS = {
    "computer": r"laptop|computer|pc|desktop|this (?:computer|machine|pc|laptop)|here|my (?:laptop|computer)",
    "speaker": r"google home|room speaker|speaker|nest|home speaker|the speaker|cast",
    "phone": r"phone|mobile|iphone|android",
    "tv": r"tv|television|chromecast",
}


def resolve_device(spoken, devs=None):
    """Spoken name → (device | None, say | None). Two candidates → a question, never a guess."""
    devs = devs if devs is not None else devices()
    s = re.sub(r"^(?:the|my|our)\s+", "", str(spoken or "").strip().lower())
    if not devs:
        return None, "I can't see any Spotify devices, sir. Is Spotify open?"
    exact = [d for d in devs if d.get("name", "").lower() == s]
    if exact:
        return exact[0], None
    for kind, pat in DEVICE_WORDS.items():
        if re.fullmatch(rf"(?:{pat})", s):
            types = {"computer": {"computer"}, "speaker": {"speaker", "castaudio", "avr"}, "phone": {"smartphone"},
                     "tv": {"tv", "castvideo"}}[kind]
            cands = [d for d in devs if (d.get("type") or "").lower() in types]
            if kind == "computer":
                local = [d for d in cands if d.get("name", "").lower() in LOCAL_NAMES]
                cands = local or cands
            if len(cands) == 1:
                return cands[0], None
            if len(cands) > 1:
                return None, "Which one, sir: " + " or ".join(d["name"] for d in cands[:3]) + "?"
            return None, f"I don't see a {kind} in Spotify's device list, sir."
    from rapidfuzz import fuzz
    scored = sorted(((fuzz.token_set_ratio(s, d.get("name", "").lower()), d) for d in devs), key=lambda x: -x[0])
    good = [d for sc, d in scored if sc >= 75]
    if len(good) == 1 or (good and scored[0][0] - scored[1][0] >= 15):
        return good[0], None
    if len(good) > 1:
        return None, "Which one, sir: " + " or ".join(d["name"] for d in good[:3]) + "?"
    return None, f"I can't find {spoken} in Spotify, sir."


def local_device(devs=None):
    devs = devs if devs is not None else devices()
    comp = [d for d in devs if (d.get("type") or "").lower() == "computer"]
    return next((d for d in comp if d.get("name", "").lower() in LOCAL_NAMES), comp[0] if comp else None)


def launch_desktop(wait=12):
    """Start the desktop app (rules.lua parks it on special:music, silent) and wait for its Connect device."""
    try:
        subprocess.Popen(["spotify-launcher"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return None
    end = time.time() + wait
    while time.time() < end:
        time.sleep(1)
        try:
            d = local_device()
        except SpotifyError:
            d = None
        if d:
            return d
    return None


def ensure_device(device_id=None):
    """A device to play on: the given one, the active one, else this computer (starting Spotify if needed)."""
    if device_id:
        return device_id
    devs = devices()
    active = next((d for d in devs if d.get("is_active")), None)
    if active:
        return active["id"]
    d = local_device(devs) or launch_desktop()
    if not d:
        raise NoDevice()
    return d["id"]


def _playing(want_uri=None, want_context=None, before=None, timeout=3.5):
    """Wait until Spotify reports the wanted track / context playing (or at least a new track). → bool.
    Needed because a 204 from PUT /me/player/play doesn't mean anything plays: see play()."""
    end = time.time() + timeout
    while time.time() < end:
        time.sleep(0.5)
        try:
            st = state() or {}
        except SpotifyError:
            continue
        item = (st.get("item") or {}).get("uri")
        ctx = (st.get("context") or {}).get("uri")
        if st.get("is_playing") and item and (item == want_uri or (want_context and ctx == want_context)
                                              or (item != before and not want_uri)):
            return True
        tid, status = mpris_track()               # the desktop app may know before the Web API does
        if status == "Playing" and tid and want_uri and want_uri.endswith(tid):
            return True
    return False


def play(uris=None, context_uri=None, offset=None, device_id=None, position_ms=None):
    """Start playback and make sure it started. The desktop app, freshly launched with nothing loaded,
    answers PUT /me/player/play with 204 and then ignores it (seen 2026-11-03: "active" device, no item,
    queue adds dropped too). Once a track is loaded, Web API commands work. So: check it plays; if not and
    the device is this computer, open the URI through the app's own MPRIS (OpenUri) and check again.
    Raises SpotifyError if nothing started."""
    dev = ensure_device(device_id)
    try:
        before = ((state() or {}).get("item") or {}).get("uri")
    except SpotifyError:
        before = None
    body = {}
    if uris:
        body["uris"] = list(uris)
    if context_uri:
        body["context_uri"] = context_uri
    if offset is not None:
        body["offset"] = {"position": offset} if isinstance(offset, int) else {"uri": offset}
    if position_ms is not None:
        body["position_ms"] = int(position_ms)
    api("PUT", "/me/player/play", {"device_id": dev}, body or None)
    _premium_ok()
    want = uris[0] if uris and offset in (None, 0) else (offset if isinstance(offset, str) else None)
    if not body or _playing(want, context_uri, before):
        return dev
    local = local_device()
    target = (uris or [None])[0] if not context_uri else context_uri
    if local and local["id"] == dev and target and mpris_open(target):
        if _playing(want, context_uri, before, timeout=4):
            return dev
    raise SpotifyError("playback didn't start", say="Spotify took the request but didn't start playing, sir. Try opening it once with Super M.")


def transfer(device_id, start=True):
    api("PUT", "/me/player", body={"device_ids": [device_id], "play": bool(start)})
    _premium_ok()


def queue_add(uri, device_id=None):
    api("POST", "/me/player/queue", {"uri": uri, "device_id": device_id})


def get_queue():
    q = api("GET", "/me/player/queue") or {}
    return [track_info(t) for t in q.get("queue") or [] if t and t.get("type") == "track"]


def set_volume(pct, device_id=None):
    api("PUT", "/me/player/volume", {"volume_percent": max(0, min(100, int(pct))), "device_id": device_id})


def save_tracks(uris, remove=False):
    """PUT / DELETE /me/library (the Feb 2026 generic library endpoint). The migration guide shows the
    URIs as a list; send them as the query parameter first, then as a JSON body if that's refused."""
    method = "DELETE" if remove else "PUT"
    try:
        api(method, "/me/library", {"uris": ",".join(uris)})
    except SpotifyError as e:
        if e.status != 400:
            raise
        api(method, "/me/library", body={"uris": list(uris)})


def saved(uris):
    r = api("GET", "/me/library/contains", {"uris": ",".join(uris)})
    return list(r) if isinstance(r, list) else [False] * len(uris)


# ── library / search ──
def search(q, types=("track",), limit=10):
    """Dev mode: limit is capped at 10 per call (Feb 2026)."""
    return api("GET", "/search", {"q": q, "type": ",".join(types), "limit": min(10, limit)}) or {}


def paged(path, key=None, limit=50, max_items=200, params=None):
    out, offset = [], 0
    while len(out) < max_items:
        r = api("GET", path, dict(params or {}, limit=limit, offset=offset)) or {}
        items = r.get("items") or []
        out += items
        if len(items) < limit or not r.get("next"):
            break
        offset += limit
    return out[:max_items]


def recently_played(limit=50):
    r = api("GET", "/me/player/recently-played", {"limit": limit}) or {}
    return [dict(track_info(i.get("track")) or {}, played_at=i.get("played_at")) for i in r.get("items") or [] if i.get("track")]


def top_tracks(time_range="short_term", limit=50):
    r = api("GET", "/me/top/tracks", {"time_range": time_range, "limit": limit}) or {}
    return [track_info(t) for t in r.get("items") or [] if t]


def saved_tracks(max_items=200):
    return [track_info(i.get("track")) for i in paged("/me/tracks", max_items=max_items) if i.get("track")]


_pl_cache = {"at": 0.0, "items": []}


def my_playlists():
    if time.time() - _pl_cache["at"] > 600:
        _pl_cache["items"] = [{"name": p.get("name", ""), "uri": p.get("uri"), "owner": (p.get("owner") or {}).get("display_name", "")}
                              for p in paged("/me/playlists", max_items=200) if p]
        _pl_cache["at"] = time.time()
    return _pl_cache["items"]


# ── "play X" ──
KINDS = ("track", "album", "artist", "playlist")
LIKED = re.compile(r"^(?:my )?(?:liked|saved|favou?rite|loved) (?:songs|tracks|music)$|^my (?:library|likes)$")


def _norm(s):
    s = str(s or "").lower()
    s = re.sub(r"\s*[\(\[][^)\]]*(?:remaster|version|edit|mix|live|feat)[^)\]]*[\)\]]", "", s)
    s = re.sub(r"\s+-\s+.*(?:remaster|version|edit|live).*$", "", s)
    return re.sub(r"[^\w\s]", "", s).strip()


def parse_query(text, kind="any"):
    """'the album discovery by daft punk' → (kind, name, artist)."""
    t = re.sub(r"\s+(?:on|from|in) spotify$", "", str(text or "").strip().lower())
    t = re.sub(r"^(?:some|a bit of|a little|the|some of)\s+", "", t)
    m = re.match(r"^(?:the |my )?(song|track|album|record|lp|ep|artist|band|playlist)\s+(?:called\s+)?(.+)$", t)
    if m:
        kind = {"song": "track", "record": "album", "lp": "album", "ep": "album", "band": "artist"}.get(m.group(1), m.group(1))
        t = m.group(2)
    m = re.match(r"^(?:my )?(.+?)\s+(playlist|album)$", t)
    if m and kind == "any":
        kind, t = m.group(2), m.group(1)
    artist = ""
    m = re.match(r"^(.+?)\s+by\s+(.+)$", t)
    if m and kind in ("any", "track", "album"):
        t, artist = m.group(1), m.group(2)
        if kind == "any":
            kind = "track"
    return kind, t.strip(), artist.strip()


def resolve(text, kind="any"):
    """Spoken name → {"kind", "uri", "name", "artist"} or raises SpotifyError with a say line."""
    from rapidfuzz import fuzz
    kind, name, artist = parse_query(text, kind)
    if not name:
        raise SpotifyError("nothing to search for", say="Play what, sir?")
    if LIKED.match(name) or (kind == "playlist" and LIKED.match(name + " songs")):
        uid = account().get("id") or (api("GET", "/me") or {}).get("id", "")
        return {"kind": "collection", "uri": f"spotify:user:{uid}:collection", "name": "your Liked Songs", "artist": ""}
    best = []
    if kind in ("playlist", "any"):
        for p in my_playlists():
            sc = fuzz.token_set_ratio(_norm(name), _norm(p["name"]))
            if sc >= (80 if kind == "playlist" else 92):
                best.append((sc + 3, {"kind": "playlist", "uri": p["uri"], "name": p["name"], "artist": ""}))
    q = name if not artist else (f'track:"{name}" artist:"{artist}"' if kind == "track" else f'album:"{name}" artist:"{artist}"')
    types = KINDS if kind == "any" else (kind,)
    r = search(q, types, 10)
    for k in types:
        for i, it in enumerate(((r.get(k + "s") or {}).get("items") or [])):
            if not it:
                continue
            who = ", ".join(a.get("name", "") for a in it.get("artists") or []) if k in ("track", "album") else \
                ((it.get("owner") or {}).get("display_name", "") if k == "playlist" else "")
            sc = fuzz.token_set_ratio(_norm(name), _norm(it.get("name")))
            if artist:
                sc = 0.6 * sc + 0.4 * fuzz.token_set_ratio(_norm(artist), _norm(who))
            sc -= i * 1.5                       # Spotify's own ranking breaks ties
            if kind == "any":
                sc += {"artist": 4, "track": 2, "album": 0, "playlist": -4}[k]   # "play daft punk" = the artist
            best.append((sc, {"kind": k, "uri": it.get("uri"), "name": it.get("name", ""), "artist": who}))
    best.sort(key=lambda x: -x[0])
    if not best or best[0][0] < 62:
        raise SpotifyError(f"no match for {text}", say=f"I couldn't find {text} on Spotify, sir.")
    return best[0][1]


def play_query(text, kind="any", device=""):
    """Resolve and play. Non-Premium: the desktop app opens the URI over MPRIS instead."""
    hit = resolve(text, kind)
    dev_id = None
    if device:
        d, say = resolve_device(device)
        if not d:
            return {"ok": False, "error": say, "say": say}
        dev_id = d["id"]
    try:
        if hit["kind"] == "track":
            play(uris=[hit["uri"]], device_id=dev_id)
        else:
            play(context_uri=hit["uri"], device_id=dev_id)
    except PremiumRequired:
        if mpris_open(hit["uri"]):
            return {"ok": True, "via": "mpris", **hit}
        raise
    return {"ok": True, **hit}


def describe(hit):
    k, n, a = hit.get("kind"), hit.get("name", ""), hit.get("artist", "")
    if k == "track":
        return f"{n} by {a}" if a else n
    if k == "album":
        return f"the album {n}" + (f" by {a}" if a else "")
    if k == "artist":
        return n
    if k == "playlist":
        return f"your {n} playlist" if not n.lower().endswith("playlist") else n
    return n


def now_playing():
    st = state()
    if not st or not st.get("item"):
        return {"ok": True, "playing": False}
    t = track_info(st["item"]) if st["item"].get("type") == "track" else {"title": st["item"].get("name", ""), "artist": ""}
    dev = st.get("device") or {}
    return {"ok": True, "playing": bool(st.get("is_playing")), **t, "progress_ms": st.get("progress_ms", 0),
            "device": dev.get("name", ""), "device_type": dev.get("type", ""), "volume": dev.get("volume_percent"),
            "shuffle": st.get("shuffle_state"), "repeat": st.get("repeat_state")}
