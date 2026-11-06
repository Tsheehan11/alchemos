"""
DJ mode: Jarvis builds a set from Trevor's own Spotify listening, queues it a few tracks at a time,
and now and then says a short line as a track starts, with the music ducked under it.

Runs inside the voice process (jarvis.py VoiceLoop starts DJ()), because the lines need the voice,
the ducker and the combat / call checks. Everything else talks to it over a local socket:

  $XDG_RUNTIME_DIR/jarvis/dj.sock    one JSON line in, one JSON line out (stark_actions.dj_* →
                                     the stark MCP tools and the fast path)
  $XDG_RUNTIME_DIR/jarvis/dj.json    what the HUD shows (MediaPanel, the "dj" widget): set name,
                                     mood, now playing, the next three
  ~/.local/share/jarvis/dj/          state.json (survives a Jarvis restart), history.json (what DJ
                                     played when: no repeats within REPEAT_HOURS), pool.json (cached
                                     library), moods.json (vibes he saved)

Claude is asked once per set (and once per "more / less like this"), never per track:
  pool     top tracks (4 weeks + 6 months), recently played, liked songs: Web API, no Claude
  build    one Haiku call with the pool as numbered lines + the vibe → an ordered set of 20-30
           tracks, up to 4 Spotify searches to slot in (search is capped at 10 results in
           Development Mode), and DJ lines for about one track in three
  refill   when the set runs low, another build that carries on from the last tracks
Recommendations / audio-features are not available to Development Mode apps, so flow (energy,
genre, era) comes from what the model knows about the tracks plus the release year.

Queueing: Spotify's queue can't be edited or cleared through the API, so DJ keeps only BATCH tracks
ahead in it. When the set changes ("less of this"), what's already queued is retired and skipped
the moment it starts. If two tracks in a row are ones DJ didn't pick (he put something else on),
DJ mode bows out quietly.

Track changes come from the desktop app's MPRIS (playerctl, no network, every second); when Spotify
plays on another Connect device, from GET /me/player every few seconds.

Chatter: Settings → JARVIS → SPOTIFY → DJ CHATTER off | rare (every 4-5 tracks) | normal (every 2-3).
Lines are cut to LINE_MAX_WORDS (under ten seconds). The voice loop says them only when it's idle,
not in combat mode and not while a Discord call has the mic (mcp/audio_devices.voice_call).
"""
import asyncio
import json
import random
import re
import socket
import threading
import time
from collections import deque

from . import config as C

import jarvis_db as db  # noqa: E402  (mcp/ is on sys.path; see jarvis.py)
import spotify_api as S  # noqa: E402

DJ_DIR = C.DATA_DIR / "dj"
STATE_FILE = DJ_DIR / "state.json"
HISTORY_FILE = DJ_DIR / "history.json"
POOL_FILE = DJ_DIR / "pool.json"
USER_MOODS = DJ_DIR / "moods.json"
MOODS_FILE = C.JARVIS_DIR / "dj_moods.json"
HUD_FILE = C.RUNTIME / "jarvis" / "dj.json"
SOCK = C.RUNTIME / "jarvis" / "dj.sock"

BATCH = 3                # tracks kept queued ahead in Spotify
REFILL_LEFT = 6          # build the next set when this few are left
SET_MIN, SET_MAX = 20, 30
POOL_MAX = 320           # library lines in the prompt (~6-8k tokens)
POOL_TTL = 1800
REPEAT_HOURS = 48
CHATTER = {"off": None, "rare": (4, 5), "normal": (2, 3)}
LINE_MAX_WORDS = 20      # ~8 s at Jarvis's speed
LINE_STALE_S = 20        # a line not said by then (he was talking to Jarvis) is dropped
POLL_LOCAL, POLL_REMOTE, POLL_IDLE = 1.0, 5.0, 30.0
RESUME_S = 1800          # a restarted Jarvis carries on a set this recent
IDLE_STOP_S = 1800       # paused this long → DJ mode ends
FOREIGN_STOP = 2
BUILD_TIMEOUT_S = 120
TEMPLATES = ["{title}, by {artist}.", "Next up, sir: {title}.", "This one's {artist}.", "Keeping it going with {artist}.",
             "{artist} now, sir. {title}.", "Here's {title}."]


# ── moods ──
def load_moods():
    """Presets from dj_moods.json (tracked) + the ones he saved (moods.json, untracked)."""
    out = {}
    for f in (MOODS_FILE, USER_MOODS):
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        for k, v in (data.get("moods", data) if isinstance(data, dict) else {}).items():
            if not k.startswith("_") and isinstance(v, dict) and v.get("desc"):
                out[k.lower()] = v
    return out


def match_mood(text):
    """'studying' / 'for the gym' / 'some chill stuff' → (key, preset) or (None, {"desc": text})."""
    t = re.sub(r"^(?:for |to |while |when )?(?:me )?(?:to )?(?:the |my |some |a )?", "", str(text or "").strip().lower())
    t = re.sub(r"\s+(?:music|songs|tracks|stuff|vibes?|mood|set|mix)$", "", t).strip()
    t = re.sub(r"\s+(?:to|with|by|for)$", "", t).strip()                # "something to code to"
    moods = load_moods()
    if not t:
        return None, {}
    for k, v in moods.items():
        words = [k] + [a.lower() for a in v.get("aliases", [])]
        if t in words or any(re.fullmatch(rf"{re.escape(w)}(?:ing|s)?", t) for w in words):
            return k, v
    return None, {"desc": str(text).strip()}


def save_mood(name, mood):
    name = re.sub(r"[^\w\s-]", "", str(name or "")).strip().lower()[:30]
    if not name or not mood.get("desc"):
        return None
    try:
        data = json.loads(USER_MOODS.read_text())
    except (OSError, ValueError):
        data = {}
    data[name] = {"desc": mood["desc"] + ("; " + "; ".join(mood.get("notes", [])) if mood.get("notes") else ""),
                  "saved": time.strftime("%Y-%m-%d")}
    DJ_DIR.mkdir(parents=True, exist_ok=True)
    USER_MOODS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return name


# ── library pool (Web API, no Claude) ──
def gather(force=False):
    try:
        cached = json.loads(POOL_FILE.read_text())
        if not force and time.time() - cached.get("at", 0) < POOL_TTL and cached.get("tracks"):
            return cached
    except (OSError, ValueError):
        pass
    by_id = {}

    def add(items, src):
        for t in items:
            if t and t.get("id") and t.get("uri", "").startswith("spotify:track:"):
                e = by_id.setdefault(t["id"], {k: t.get(k) for k in ("id", "uri", "title", "artist", "album", "year", "ms")} | {"src": []})
                if src not in e["src"]:
                    e["src"].append(src)
    recent = S.recently_played(50)
    add(S.top_tracks("short_term"), "top")
    add(S.top_tracks("medium_term"), "top6m")
    add(recent, "recent")
    add(S.saved_tracks(200), "liked")
    pool = {"at": time.time(), "tracks": list(by_id.values()), "recent_ids": [t["id"] for t in recent if t.get("id")]}
    DJ_DIR.mkdir(parents=True, exist_ok=True)
    POOL_FILE.write_text(json.dumps(pool, ensure_ascii=False))
    return pool


def load_history():
    try:
        h = json.loads(HISTORY_FILE.read_text())
    except (OSError, ValueError):
        return {}
    cut = time.time() - 7 * 86400
    return {k: v for k, v in h.items() if v > cut}


def candidates(pool, history, exclude=()):
    """Pool minus recent repeats: DJ's own plays in the last REPEAT_HOURS and Spotify's last 50 plays.
    A thin library relaxes it to 12 h / the last 20."""
    now = time.time()
    ex = set(exclude)

    def pick(hours, recent_n):
        bad = ex | {k for k, v in history.items() if now - v < hours * 3600} | set(pool.get("recent_ids", [])[:recent_n])
        return [t for t in pool["tracks"] if t["id"] not in bad]
    c = pick(REPEAT_HOURS, 50)
    if len(c) < 60:
        c = pick(12, 20)
    order = {"top": 0, "top6m": 1, "recent": 2, "liked": 3}
    c.sort(key=lambda t: min(order.get(s, 4) for s in t["src"]))
    head, tail = c[:120], c[120:]
    random.shuffle(tail)              # liked songs beyond the favourites: a different slice each set
    return head + tail[:POOL_MAX - len(head)]


# ── the one Claude call per set ──
PROMPT = """You are {name}, DJ for Trevor. Plan a set.
VIBE: {vibe}
{adjust}{carry}
Pick {lo}-{hi} tracks from LIBRARY by number and order them for flow: ease in, shape the energy to the vibe, keep neighbours compatible in genre, energy and era, and never the same artist twice within 4 tracks. Use what you know about each artist and track. Fit to the vibe beats familiarity.
You may ask for up to 4 Spotify track searches for fitting music not in the library (search syntax like "genre:lo-fi", "artist:Nujabes", "year:2012-2016 genre:house"), each placed after a position of your order.
Write DJ lines {voice}, at most 18 words, no emojis, no hype clichés) for about one track in three, keyed by position; each is said as that track starts and may mention the track or artist.
Answer with only JSON: {{"name": "2-4 word set name", "order": [numbers], "search": [{{"q": "...", "after": position}}], "lines": {{"position": "line"}}}}
LIBRARY (number | title | artist | year | from):
{library}"""


def library_lines(tracks):
    return "\n".join(f"{i} | {t['title'][:60]} | {t['artist'][:40]} | {t.get('year') or '?'} | {','.join(t['src'])}"
                     for i, t in enumerate(tracks, 1))


def ask_claude(prompt, log=print):
    """One Haiku call, no tools. → reply text ('' on failure)."""
    async def run():
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

        async def deny(*a, **k):
            from claude_agent_sdk import PermissionResultDeny
            return PermissionResultDeny(message="no tools")
        opts = ClaudeAgentOptions(model=C.FAST_MODEL, system_prompt="You answer only with the JSON asked for.",
                                  tools=[], allowed_tools=[], mcp_servers={}, strict_mcp_config=True, setting_sources=[],
                                  can_use_tool=deny, max_turns=1, cwd=str(C.DATA_DIR),
                                  env={"CLAUDE_AGENT_SDK_CLIENT_APP": "stark-jarvis/2"}, stderr=lambda line: None)
        text = ""
        async for m in query(prompt=prompt, options=opts):
            if isinstance(m, AssistantMessage):
                text += " ".join(b.text for b in m.content if isinstance(b, TextBlock))
            elif isinstance(m, ResultMessage):
                db.add_usage("dj", m)
        return text
    try:
        return asyncio.run(asyncio.wait_for(run(), BUILD_TIMEOUT_S))
    except Exception as e:
        log(f"JARVIS: DJ set build failed: {type(e).__name__}: {e}")
        return ""


def clean_line(s):
    s = re.sub(r"https?://\S+|www\.\S+", "", str(s or ""))
    s = re.sub(r"[`<>{}\[\]|\\*_#]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    words = s.split()
    if len(words) > LINE_MAX_WORDS:
        s = " ".join(words[:LINE_MAX_WORDS]).rstrip(",;:") + "."
    return s


def parse_plan(text, cands):
    """Claude's JSON → (name, [tracks], searches, notes). Bad numbers / duplicates are dropped."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    seen, out = set(), []
    for n in d.get("order") or []:
        try:
            t = cands[int(n) - 1]
        except (ValueError, TypeError, IndexError):
            continue
        if int(n) >= 1 and t["id"] not in seen:
            seen.add(t["id"])
            out.append(dict(t))
    lines = d.get("lines") or {}
    if isinstance(lines, dict):
        for k, v in lines.items():
            try:
                i = int(k) - 1
            except (ValueError, TypeError):
                continue
            if 0 <= i < len(out) and clean_line(v):
                out[i]["line"] = clean_line(v)
    searches = [s for s in (d.get("search") or []) if isinstance(s, dict) and s.get("q")][:4]
    name = re.sub(r"[^\w\s'&-]", "", str(d.get("name") or "")).strip()[:32]
    return name, out, searches


def fallback_order(cands, n=24):
    """No Claude (limit / offline): a shuffled pick with artists spread apart."""
    pool = cands[:]
    random.shuffle(pool)
    out = []
    for t in pool:
        if len(out) >= n:
            break
        if t["artist"] not in [x["artist"] for x in out[-4:]]:
            out.append(dict(t))
    return out


def apply_searches(tracks, searches, exclude, log=print):
    for s in sorted(searches, key=lambda s: -int(s.get("after") or 0) if str(s.get("after", "")).isdigit() else 0):
        try:
            items = (S.search(str(s["q"])[:100], ("track",), 10).get("tracks") or {}).get("items") or []
        except S.SpotifyError as e:
            log(f"JARVIS: DJ search {s['q']!r}: {e}")
            continue
        have = {t["id"] for t in tracks} | set(exclude)
        found = [S.track_info(i) for i in items if i and i.get("id") not in have][:2]
        try:
            at = max(0, min(len(tracks), int(s.get("after") or len(tracks))))
        except (TypeError, ValueError):
            at = len(tracks)
        for j, t in enumerate(found):
            t["src"] = ["search"]
            tracks.insert(at + j, t)
    return tracks


def build_set(vibe, adjust="", carry=(), played=(), log=print, claude=None):
    """→ (name, tracks, used_claude). `claude` is injectable for tests."""
    pool = gather()
    cands = candidates(pool, load_history(), exclude=played)
    if len(cands) < 8:
        raise S.SpotifyError("library too small", say="There isn't enough in your library for a set yet, sir.")
    carry_txt = ("Carry on smoothly from the last tracks played: " + "; ".join(f"{t['title']} by {t['artist']}" for t in carry) + "\n") if carry else ""
    adj_txt = (adjust + "\n") if adjust else ""
    from . import persona
    who = persona.active()           # the set's lines are written once, in the default persona's voice
    prompt = PROMPT.format(name=persona.call(who), voice=persona.dj_voice(who),
                           vibe=vibe, adjust=adj_txt, carry=carry_txt, lo=SET_MIN, hi=SET_MAX, library=library_lines(cands))
    text = (claude or ask_claude)(prompt, log=log)
    name, tracks, searches = parse_plan(text, cands)
    used = len(tracks) >= 8
    if not used:
        tracks, name = fallback_order(cands), ""
    else:
        tracks = apply_searches(tracks, searches, played, log)
    return name, tracks, used


# ── the engine ──
def _blank():
    return {"active": False, "set": "", "mood": {}, "keep": False, "tracks": [], "pos": -1, "queued_upto": -1,
            "retired": [], "played": [], "since_line": 0, "line_due": 4, "current": None, "foreign": 0,
            "remote": False, "device": "", "started": 0, "updated": 0, "paused_since": 0, "note": ""}


class DJ:
    def __init__(self, cfg, log=print, claude=None, serve=True):
        self.cfg, self.log, self.claude = cfg, log, claude
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.lines = deque(maxlen=2)
        self.building = ""
        self.gen = 0             # bumped by stop / start: a build that finishes after a stop is dropped
        self.s = _blank()
        self._load()
        if serve:
            threading.Thread(target=self._loop, daemon=True, name="dj").start()
            threading.Thread(target=self._serve, daemon=True, name="dj-sock").start()
        self._hud()

    # ── persistence ──
    def _load(self):
        try:
            s = json.loads(STATE_FILE.read_text())
        except (OSError, ValueError):
            return
        if s.get("active") and time.time() - s.get("updated", 0) < RESUME_S:
            self.s = _blank() | s
            self.log(f"JARVIS: DJ carrying on with {s.get('set') or 'the set'}")
        else:
            self.s = _blank()

    def _save(self):
        self.s["updated"] = time.time()
        try:
            DJ_DIR.mkdir(parents=True, exist_ok=True)
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.s, ensure_ascii=False))
            tmp.replace(STATE_FILE)
        except OSError as e:
            self.log(f"JARVIS: DJ state: {e}")
        self._hud()

    def _hud(self):
        s = self.s
        pos = s["pos"]
        now = s["tracks"][pos] if 0 <= pos < len(s["tracks"]) else None
        nxt = s["tracks"][pos + 1:pos + 4] if s["active"] else []
        data = {"active": s["active"], "building": self.building, "set": s["set"], "mood": s["mood"].get("key") or s["mood"].get("desc", ""),
                "chatter": self.chatter(), "keep": s["keep"], "remote": s["remote"], "device": s["device"],
                "now": {k: now.get(k, "") for k in ("title", "artist", "year")} if now else None,
                "next": [{k: t.get(k, "") for k in ("title", "artist", "year")} for t in nxt],
                "left": max(0, len(s["tracks"]) - 1 - pos) if s["active"] else 0, "note": s["note"], "updated": time.time()}
        try:
            HUD_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = HUD_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False))
            tmp.replace(HUD_FILE)
        except OSError:
            pass

    def chatter(self):
        try:
            v = str(self.cfg["jarvisDjChatter"]).lower()
        except KeyError:
            v = "rare"
        return v if v in CHATTER else "rare"

    def _next_due(self):
        r = CHATTER.get(self.chatter())
        return random.randint(*r) if r else 0

    # ── lines for the voice loop ──
    def push_line(self, text, kind="chatter"):
        text = clean_line(text)
        if text:
            self.lines.append({"text": text, "kind": kind, "at": time.time()})

    def pop_line(self):
        """Next line to say, or None. Stale ones (he was busy) are dropped."""
        while self.lines:
            item = self.lines.popleft()
            if time.time() - item["at"] < LINE_STALE_S:
                return item
        return None

    def duck_remote(self, level):
        """Spotify playing on another Connect device (no stream here to turn down): lower that device's
        volume through the Web API. → a function that puts it back, or None."""
        try:
            st = S.state() or {}
            dev = st.get("device") or {}
            vol = dev.get("volume_percent")
            if (not st.get("is_playing") or vol is None or not dev.get("id") or dev.get("supports_volume") is False
                    or dev.get("name", "").lower() in S.LOCAL_NAMES):
                return None
            S.set_volume(int(vol * level), dev["id"])
        except S.SpotifyError as e:
            self.log(f"JARVIS: DJ remote duck: {e}")
            return None

        def restore():
            try:
                S.set_volume(vol, dev["id"])
            except S.SpotifyError as e:
                self.log(f"JARVIS: DJ remote volume back: {e}")
        return restore

    # ── commands ──
    def handle(self, req):
        op = req.get("op")
        try:
            fn = {"start": self.start, "stop": self.stop, "adjust": self.adjust, "keep": self.keep, "status": self.status,
                  "chatter": self.set_chatter, "save_mood": self.save_mood, "moods": self.moods}[op]
        except KeyError:
            return {"ok": False, "error": f"unknown op {op}"}
        args = {k: v for k, v in req.items() if k != "op"}
        try:
            return fn(**args)
        except S.SpotifyError as e:
            return {"ok": False, "error": str(e), "say": e.say}

    def _ready(self):
        if not S.connected():
            raise S.NotConnected()
        if S.premium() is False:
            raise S.SpotifyError("Premium required", say="DJ mode needs Spotify Premium, sir. Play, pause and skip still work.")

    def start(self, mood="", seed=None):
        self._ready()
        if self.building:
            return {"ok": False, "error": "busy", "say": "I'm still putting the last set together, sir."}
        key, preset = match_mood(mood)
        if seed:
            preset = {"desc": f"more music like {seed}, the same feel"}
        vibe = preset.get("desc") or "a mix of what Trevor plays most, varied and easy to listen to"
        label = key or (mood.strip() if mood else ("more like this" if seed else "your mix"))
        self._build_async("start", vibe=vibe, mood={"key": key or "", "desc": vibe, "label": label, "notes": []})
        what = f"a {label} set" if label not in ("your mix", "more like this") else ("more like this" if seed else "a set")
        return {"ok": True, "building": True, "say": f"Putting {what} together, sir."}

    def stop(self, quiet=False, why=""):
        with self.lock:
            was = self.s["active"] or bool(self.building)
            self.s = _blank() | {"note": why}
            self.building = ""
            self.gen += 1
            self._save()
        return {"ok": True, "was_active": was, "say": "DJ mode off, sir." if was else "DJ mode wasn't on, sir."}

    def keep(self):
        with self.lock:
            if not self.s["active"]:
                return {"ok": False, "error": "DJ mode is off", "say": "DJ mode isn't on, sir."}
            self.s["keep"] = True
            cur = self._current_track()
            if cur:
                self.s["mood"].setdefault("notes", []).append(f"stay close to the feel of {cur['title']} by {cur['artist']}")
            self._save()
        return {"ok": True, "say": "Keeping this vibe, sir."}

    def adjust(self, direction="more", note=""):
        direction = direction if direction in ("more", "less") else "more"
        with self.lock:
            active = self.s["active"]
            cur = self._current_track()
        if not active:
            np = S.now_playing() if S.connected() else {}
            if direction == "more" and np.get("title"):
                return self.start(seed=f"{np['title']} by {np.get('artist', '')}")
            return {"ok": False, "error": "DJ mode is off", "say": "DJ mode isn't on, sir."}
        self._ready()
        if self.building:
            return {"ok": False, "error": "busy", "say": "One moment, sir, I'm still on the last change."}
        anchor = f"{cur['title']} by {cur['artist']}" if cur else "the current track"
        extra = f" ({note})" if note else ""
        adj = (f"ADJUST: Trevor said 'more like this' about {anchor}{extra}: lean the rest of the set toward its sound."
               if direction == "more" else
               f"ADJUST: Trevor said 'less of this' about {anchor}{extra}: steer the rest of the set away from its sound and genre.")
        with self.lock:
            self.s["mood"].setdefault("notes", []).append(("more like " if direction == "more" else "less like ") + anchor)
        self._build_async(direction, adjust=adj)
        return {"ok": True, "building": True, "say": "More like this, sir." if direction == "more" else "Changing it up, sir."}

    def set_chatter(self, level=""):
        level = str(level or "").lower().strip()
        level = {"on": "normal", "more": "normal", "less": "rare", "none": "off", "quiet": "off"}.get(level, level)
        if level not in CHATTER:
            return {"ok": False, "error": "level must be off, rare or normal"}
        import stark_actions as A
        A._write_hud_setting("jarvisDjChatter", level)
        with self.lock:
            self.s["line_due"] = self._next_due() or 4
            self._hud()
        return {"ok": True, "level": level,
                "say": {"off": "I'll keep quiet between tracks, sir.", "rare": "Only the odd word between tracks, sir.",
                        "normal": "I'll chime in more often, sir."}[level]}

    def save_mood(self, name=""):
        with self.lock:
            mood = dict(self.s["mood"])
        if not mood.get("desc"):
            return {"ok": False, "error": "no vibe to save", "say": "There's no set playing to save, sir."}
        n = save_mood(name or mood.get("label") or "saved", mood)
        return {"ok": bool(n), "name": n, "say": f"Saved as {n}, sir." if n else "I couldn't save that, sir."}

    def moods(self):
        return {"ok": True, "moods": {k: v.get("desc", "") for k, v in load_moods().items()}}

    def status(self):
        with self.lock:
            s = self.s
            cur = self._current_track()
            return {"ok": True, "active": s["active"], "building": self.building, "set": s["set"],
                    "mood": s["mood"].get("label") or s["mood"].get("desc", ""), "chatter": self.chatter(),
                    "now": cur and f"{cur['title']} by {cur['artist']}",
                    "next": [f"{t['title']} by {t['artist']}" for t in s["tracks"][s["pos"] + 1:s["pos"] + 4]] if s["active"] else [],
                    "left": max(0, len(s["tracks"]) - 1 - s["pos"]) if s["active"] else 0, "note": s["note"]}

    # ── building ──
    def _current_track(self):
        p = self.s["pos"]
        return self.s["tracks"][p] if 0 <= p < len(self.s["tracks"]) else None

    def _build_async(self, kind, **kw):
        self.building = kind
        if kind == "start":
            self.gen += 1
        self._hud()
        threading.Thread(target=self._build, args=(kind, self.gen), kwargs=kw, daemon=True, name="dj-build").start()

    def _build(self, kind, gen, vibe=None, mood=None, adjust=""):
        try:
            with self.lock:
                if kind == "start":
                    played, carry = [], []
                else:
                    vibe = self.s["mood"].get("desc", "")
                    if self.s["mood"].get("notes"):
                        vibe += " (" + "; ".join(self.s["mood"]["notes"][-4:]) + ")"
                    played = [t["id"] for t in self.s["tracks"][:self.s["pos"] + 1]]
                    carry = self.s["tracks"][max(0, self.s["pos"] - 2):self.s["pos"] + 1]
            name, tracks, used = build_set(vibe, adjust, carry, played, log=self.log, claude=self.claude)
            self.log(f"JARVIS: DJ {kind}: {len(tracks)} tracks{'' if used else ' (no Claude: shuffled)'}" + (f", {name!r}" if name else ""))
            if gen != self.gen:
                self.log("JARVIS: DJ: stopped while building, set dropped")
                return
            if kind == "start":
                self._begin(name or (mood.get("label", "").title() + " Set").strip(), mood, tracks)
            else:
                self._replace(kind, tracks, name)
        except S.SpotifyError as e:
            self.log(f"JARVIS: DJ: {e}")
            self.push_line(e.say, "notice")
            if kind == "start":
                with self.lock:
                    self.s = _blank() | {"note": str(e)[:80]}
        except Exception as e:
            import traceback
            self.log(f"JARVIS: DJ build crashed: {traceback.format_exc()}")
            self.push_line("I couldn't put that set together, sir.", "notice")
        finally:
            with self.lock:
                if gen == self.gen:
                    self.building = ""
                self._save()
            self.wake.set()

    def _begin(self, name, mood, tracks):
        dev = S.play(uris=[tracks[0]["uri"]])
        with self.lock:
            self.s = _blank() | {"active": True, "set": name, "mood": mood, "tracks": tracks, "pos": 0, "queued_upto": 0,
                                 "current": tracks[0]["id"], "started": time.time(), "line_due": self._next_due() or 4}
            self._mark_played(tracks[0])
            self._queue_ahead(dev)
        t = tracks[0]
        self.push_line(f"Here's {name}, sir. Starting with {t['title']} by {t['artist']}." if self.chatter() != "off"
                       else f"Here's {name}, sir.", "notice")

    def _replace(self, kind, tracks, name):
        with self.lock:
            s = self.s
            if not s["active"]:
                return
            have = {t["id"] for t in s["tracks"][:s["pos"] + 1]}
            if kind in ("more", "less"):
                s["retired"] = (s["retired"] + [t["uri"] for t in s["tracks"][s["pos"] + 1:s["queued_upto"] + 1]])[-30:]
            have |= {u.rsplit(":", 1)[-1] for u in s["retired"]}     # already in Spotify's queue, skipped when they start
            tracks = [t for t in tracks if t["id"] not in have]
            if kind in ("more", "less"):
                s["tracks"] = s["tracks"][:s["pos"] + 1] + tracks
                s["queued_upto"] = s["pos"]
            else:                                   # refill: append
                s["tracks"] = s["tracks"] + tracks
                if name and not s["keep"]:
                    s["set"] = name
            if kind == "less" and len(s["tracks"]) > s["pos"] + 1:
                nxt = s["tracks"][s["pos"] + 1]
                S.play(uris=[nxt["uri"]])
                s["pos"] += 1
                s["queued_upto"] = s["pos"]
                s["current"] = nxt["id"]
                self._mark_played(nxt)
            self._queue_ahead()

    def _queue_ahead(self, device=None):
        s = self.s
        while s["queued_upto"] - s["pos"] < BATCH and s["queued_upto"] + 1 < len(s["tracks"]):
            t = s["tracks"][s["queued_upto"] + 1]
            try:
                S.queue_add(t["uri"], device)
            except S.SpotifyError as e:
                self.log(f"JARVIS: DJ queue: {e}")
                break
            s["queued_upto"] += 1

    def _mark_played(self, t):
        h = load_history()
        h[t["id"]] = time.time()
        try:
            DJ_DIR.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.write_text(json.dumps(h))
        except OSError:
            pass
        self.s["played"] = (self.s["played"] + [t["id"]])[-200:]

    # ── following playback ──
    def _loop(self):
        while True:
            try:
                wait = self.tick()
            except S.NotConnected:
                self.stop(why="Spotify disconnected")
                wait = POLL_IDLE
            except S.SpotifyError as e:
                self.log(f"JARVIS: DJ: {e}")
                wait = POLL_REMOTE * 2
            except Exception as e:
                self.log(f"JARVIS: DJ tick: {type(e).__name__}: {e}")
                wait = POLL_REMOTE * 2
            self.wake.wait(wait)
            self.wake.clear()

    def tick(self, now=None):
        """One look at playback → seconds until the next."""
        now = now or time.time()
        if not self.s["active"] or self.building == "start":
            return POLL_IDLE
        tid, status = S.mpris_track()
        remote = False
        if tid is None:
            st = S.state()
            item = (st or {}).get("item") or {}
            tid = item.get("id")
            status = "Playing" if (st or {}).get("is_playing") else "Paused"
            dev = (st or {}).get("device") or {}
            remote = bool(dev) and dev.get("name", "").lower() not in S.LOCAL_NAMES
            if dev.get("name") != self.s["device"]:
                self.s["device"] = dev.get("name", "")
        with self.lock:
            if remote != self.s["remote"]:
                self.s["remote"] = remote
                self._hud()
            if status != "Playing":
                self.s["paused_since"] = self.s["paused_since"] or now
                if now - self.s["paused_since"] > IDLE_STOP_S:
                    self.stop(why="paused a long while")
                    return POLL_IDLE
            else:
                self.s["paused_since"] = 0
            if tid and tid != self.s["current"]:
                self.on_track(tid)
        return POLL_REMOTE if remote else POLL_LOCAL

    def on_track(self, tid):
        s = self.s
        s["current"] = tid
        ids = [t["id"] for t in s["tracks"]]
        idx = next((i for i in range(s["pos"] + 1, len(ids)) if ids[i] == tid), None)
        if idx is None and tid in ids:
            idx = ids.index(tid)
        if idx is None:
            if f"spotify:track:{tid}" in s["retired"]:
                s["retired"].remove(f"spotify:track:{tid}")
                try:
                    S.api("POST", "/me/player/next")        # stale from before "less of this": skip it
                except S.SpotifyError as e:
                    self.log(f"JARVIS: DJ skip: {e}")
                self._save()
                return
            s["foreign"] += 1
            if s["foreign"] >= FOREIGN_STOP:
                self.log("JARVIS: DJ: he put something else on, bowing out")
                self.stop(quiet=True, why="you took over")
                return
            self._save()
            return
        s["foreign"] = 0
        s["pos"] = idx
        s["queued_upto"] = max(s["queued_upto"], idx)
        t = s["tracks"][idx]
        self._mark_played(t)
        self._maybe_line(idx)
        self._queue_ahead()
        if len(s["tracks"]) - 1 - idx <= REFILL_LEFT and not self.building:
            self._build_async("refill")
        self._save()

    def _maybe_line(self, idx):
        s = self.s
        level = self.chatter()
        if CHATTER.get(level) is None:
            return
        s["since_line"] += 1
        due = s["line_due"] or 4
        t = s["tracks"][idx]
        if s["since_line"] < due:
            return
        if not t.get("line") and s["since_line"] < due + 2:     # wait a track or two for one of Claude's lines
            return
        from . import persona
        line = t.get("line") or random.choice(persona.DJ_TEMPLATES.get(persona.active(self.cfg), TEMPLATES)).format(title=t["title"], artist=t["artist"].split(",")[0])
        self.push_line(line)
        s["since_line"] = 0
        s["line_due"] = self._next_due() or 4

    # ── socket ──
    def _serve(self):
        try:
            SOCK.parent.mkdir(parents=True, exist_ok=True)
            SOCK.unlink(missing_ok=True)
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(SOCK))
            SOCK.chmod(0o600)
            srv.listen(4)
        except OSError as e:
            self.log(f"JARVIS: DJ socket: {e}")
            return
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        with conn:
            conn.settimeout(10)
            buf = b""
            try:
                while not buf.endswith(b"\n") and len(buf) < 8192:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                req = json.loads(buf.decode() or "{}")
                r = self.handle(req)
            except (OSError, ValueError) as e:
                r = {"ok": False, "error": str(e)}
            try:
                conn.sendall((json.dumps(r, ensure_ascii=False) + "\n").encode())
            except OSError:
                pass


def request(op, timeout=15, **kw):
    """Client side (stark_actions): one op to the voice process's DJ."""
    try:
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.settimeout(timeout)
        c.connect(str(SOCK))
        c.sendall((json.dumps({"op": op, **kw}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = c.recv(65536)
            if not chunk:
                break
            buf += chunk
        c.close()
        return json.loads(buf.decode() or "{}")
    except (OSError, ValueError):
        return {"ok": False, "error": "Jarvis's voice loop isn't running",
                "say": "DJ mode needs me running, sir. Switch me on in Settings, under Jarvis."}
