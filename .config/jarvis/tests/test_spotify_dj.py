#!/usr/bin/env python3
"""Spotify + DJ mode: spoken names → tracks / devices (mcp/spotify_api.py), the token refresh and the 403 → MPRIS
fallback, the set build / queue / chatter / retire / take-over logic (core/dj.py), the DJ line gate in the voice
loop (jarvis.py check_dj: combat, Discord call, ducking, Spotify's sink), the call and stream detection
(mcp/audio_devices.py) and the fast-path rules. Fake Spotify, fake keyring, fake pactl, temp dirs: no network,
no audio, no Claude, nothing written to the real settings or ~/.local/share/jarvis.
Run: python tests/test_spotify_dj.py"""
import importlib.util
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
TMP = Path(tempfile.mkdtemp(prefix="jarvis-spotify-test-"))
os.environ["XDG_RUNTIME_DIR"] = str(TMP)
os.environ["JARVIS_DB"] = str(TMP / "test.db")

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


# ── fake keyring ──
from core import secrets  # noqa: E402
VAULT = {}
secrets.get = lambda s, a: VAULT.get((s, a))
secrets.store = lambda s, a, v=None: VAULT.__setitem__((s, a), v)
secrets.delete = lambda s, a: VAULT.pop((s, a), None)
secrets.has = lambda s, a: bool(VAULT.get((s, a)))

import spotify_api as S  # noqa: E402
S.LOCK_FILE = str(TMP / "spotify.lock")

# ── query parsing ──
check("parse by", S.parse_query("discovery by daft punk"), ("track", "discovery", "daft punk"))
check("parse album", S.parse_query("the album random access memories"), ("album", "random access memories", ""))
check("parse playlist suffix", S.parse_query("my chill playlist"), ("playlist", "chill", ""))
check("parse some", S.parse_query("some daft punk"), ("any", "daft punk", ""))
check("parse on spotify", S.parse_query("tame impala on spotify"), ("any", "tame impala", ""))


# ── resolve against a fake search ──
def fake_search(q, types=("track",), limit=10):
    art = {"name": "Daft Punk"}
    return {"artists": {"items": [{"name": "Daft Punk", "uri": "spotify:artist:dp"}]},
            "tracks": {"items": [{"name": "One More Time", "uri": "spotify:track:omt", "artists": [art]},
                                 {"name": "Discovery Channel", "uri": "spotify:track:dc", "artists": [{"name": "Other"}]}]},
            "albums": {"items": [{"name": "Discovery", "uri": "spotify:album:disc", "artists": [art]}]},
            "playlists": {"items": [{"name": "Daft Punk Mix", "uri": "spotify:playlist:x", "owner": {"display_name": "Spotify"}}]}}


S.search = fake_search
S.my_playlists = lambda: [{"name": "Study Beats", "uri": "spotify:playlist:study", "owner": "trevor"}]
check("artist wins for a bare name", S.resolve("daft punk")["uri"], "spotify:artist:dp")
check("album by artist", S.resolve("the album discovery by daft punk")["uri"], "spotify:album:disc")
check("track by artist", S.resolve("one more time by daft punk")["uri"], "spotify:track:omt")
check("own playlist", S.resolve("my study beats playlist")["uri"], "spotify:playlist:study")
VAULT[("spotify", "account")] = json.dumps({"id": "trev", "name": "Trevor"})
check("liked songs", S.resolve("liked songs")["uri"], "spotify:user:trev:collection")
try:
    S.resolve("zzqx vrrp")
    check("no match raises", False, True)
except S.SpotifyError as e:
    check("no match say", "couldn't find" in e.say, True)

# ── devices ──
DEVS = [{"id": "a", "name": "Dell-Linux", "type": "Computer", "is_active": True},
        {"id": "b", "name": "Trevor's Room speaker", "type": "CastAudio"},
        {"id": "c", "name": "Pixel 8", "type": "Smartphone"}]
S.LOCAL_NAMES = {"dell-linux"}
check("laptop device", S.resolve_device("the laptop", DEVS)[0]["id"], "a")
check("google home device", S.resolve_device("google home", DEVS)[0]["id"], "b")
check("phone device", S.resolve_device("my phone", DEVS)[0]["id"], "c")
check("by name", S.resolve_device("room speaker", DEVS)[0]["id"], "b")
two = DEVS + [{"id": "d", "name": "Kitchen", "type": "Speaker"}]
d, say = S.resolve_device("speaker", two)
check("two speakers ask", (d, say.startswith("Which one")), (None, True))

# ── tokens: refresh when expired, keep the old refresh token if Spotify doesn't rotate it ──
VAULT[("spotify", "client_id")] = "cid1234567890abcdef"
VAULT[("spotify", "token")] = json.dumps({"access_token": "old", "refresh_token": "r1", "expires_at": time.time() - 5, "scope": ""})
calls = []


def fake_http(method, url, data=None, headers=None, timeout=8):
    calls.append((method, url, headers.get("Authorization") if headers else None))
    if url == S.TOKEN_URL:
        return 200, {}, {"access_token": "new", "expires_in": 3600, "scope": "user-top-read"}
    if headers and headers.get("Authorization") == "Bearer new":
        return 200, {}, {"ok": 1}
    return 401, {}, {"error": {"message": "expired"}}


S._http = fake_http
S._cache["token"] = None
check("api after refresh", S.api("GET", "/me"), {"ok": 1})
check("refresh kept r1", json.loads(VAULT[("spotify", "token")])["refresh_token"], "r1")
check("one refresh", sum(1 for c in calls if c[1] == S.TOKEN_URL), 1)

# ── 403 PREMIUM_REQUIRED → remembered, MPRIS fallback in the action ──
S._http = lambda *a, **k: (403, {}, {"error": {"message": "Player command failed: Premium required", "reason": "PREMIUM_REQUIRED"}})
import stark_actions as A  # noqa: E402
mpris_calls = []
S.mpris = lambda action: mpris_calls.append(action) or {"ok": True, "via": "mpris"}
S.ensure_device = lambda device_id=None: "a"
r = A.spotify_player("next")
check("premium fallback ok", (r["ok"], r.get("via")), (True, "mpris"))
check("premium remembered", S.premium(), False)
r = A.spotify_player("shuffle_on")
check("shuffle needs premium", (r["ok"], "Premium" in r.get("say", "")), (False, True))
check("next goes straight to mpris now", (A.spotify_player("pause")["ok"], mpris_calls), (True, ["next", "pause"]))
VAULT[("spotify", "account")] = json.dumps({"id": "trev", "name": "Trevor", "premium": True})

# ── play() checks it really started: a freshly launched desktop app takes the 204 and plays nothing ──
real_time, clock = S.time, [0.0]
S.time = types.SimpleNamespace(time=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0] + s))
saved_fns = {k: getattr(S, k) for k in ("ensure_device", "state", "api", "local_device", "mpris_open", "mpris_track")}
PLAYER = {"st": None, "opened": [], "api_works": True}


def fake_api(method, path, params=None, body=None, _retry=True):
    if path == "/me/player/play" and PLAYER["api_works"]:
        PLAYER["st"] = {"is_playing": True, "item": {"uri": body["uris"][0]}}


def fake_open(uri):
    PLAYER["opened"].append(uri)
    if PLAYER.get("mpris_works"):
        PLAYER["st"] = {"is_playing": True, "item": {"uri": uri}}
    return True


S.ensure_device = lambda device_id=None: "a"
S.state = lambda: PLAYER["st"]
S.api = fake_api
S.local_device = lambda devs=None: {"id": "a", "name": "Dell-Linux"}
S.mpris_open = fake_open
S.mpris_track = lambda: (None, None)
check("play via api", (S.play(uris=["spotify:track:x1"]), PLAYER["opened"]), ("a", []))
PLAYER.update(st=None, api_works=False, mpris_works=True)
check("ignored 204 → mpris open", (S.play(uris=["spotify:track:x2"]), PLAYER["opened"]), ("a", ["spotify:track:x2"]))
PLAYER.update(st=None, opened=[], mpris_works=False)
try:
    S.play(uris=["spotify:track:x3"])
    check("nothing started raises", False, True)
except S.SpotifyError as e:
    check("nothing started say", "didn't start" in e.say, True)
S.local_device = lambda devs=None: {"id": "other"}
PLAYER.update(st=None, opened=[], mpris_works=True)
try:
    S.play(uris=["spotify:track:x4"])
except S.SpotifyError:
    pass
check("remote device: no mpris", PLAYER["opened"], [])
for k, v in saved_fns.items():
    setattr(S, k, v)
S.time = real_time
S.ensure_device = lambda device_id=None: "a"
S._http = lambda *a, **k: (403, {}, {"error": {"message": "Player command failed: Premium required", "reason": "PREMIUM_REQUIRED"}})

# ── not connected ──
tok = VAULT.pop(("spotify", "token"))
r = A.spotify_play("daft punk")
check("not connected say", (r["ok"], "isn't connected" in r.get("say", "")), (False, True))
check("not connected next uses mpris", A.spotify_player("next")["via"], "mpris")
VAULT[("spotify", "token")] = tok

# ── audio_devices: calls and Spotify's stream ──
import audio_devices as AD  # noqa: E402


def so(app, binary="", media="RecordStream"):
    return {"properties": {"application.name": app, "application.process.binary": binary, "media.name": media}}


check("discord call", AD.voice_call([so("WEBRTC VoiceEngine", "Discord")]), True)
check("vesktop call", AD.voice_call([so("vesktop")]), True)
check("jarvis mic isn't a call", AD.voice_call([so("pw-record", media="Jarvis wake word")]), False)
check("no call", AD.voice_call([so("OBS")]), False)
AD._json = lambda *a: [{"index": 7, "name": "bluez_output.X"}] if a[-1] == "sinks" else []
SI = [{"index": 41, "sink": 7, "corked": False, "properties": {"application.name": "spotify", "media.name": "Spotify"}}]
check("spotify stream", AD.music_stream(SI), (41, "bluez_output.X"))
check("corked spotify", AD.music_stream([dict(SI[0], corked=True)]), (None, None))

# ── DJ: moods, plan parsing, candidates ──
from core import dj as D  # noqa: E402
for name in ("DJ_DIR",):
    setattr(D, name, TMP / "dj")
D.STATE_FILE, D.HISTORY_FILE, D.POOL_FILE, D.USER_MOODS = (TMP / "dj" / f for f in ("state.json", "history.json", "pool.json", "moods.json"))
D.HUD_FILE, D.SOCK = TMP / "jarvis" / "dj.json", TMP / "jarvis" / "dj.sock"
check("mood gym", D.match_mood("for the gym")[0], "gym")
check("mood code to", D.match_mood("code to")[0], "focus")
check("mood study music", D.match_mood("some study music")[0], "studying")
check("mood free text", D.match_mood("dark synthwave")[1].get("desc"), "dark synthwave")
check("line cap", len(D.clean_line(" ".join(["word"] * 40)).split()), D.LINE_MAX_WORDS)
check("line strips markup", D.clean_line("**Up next** <b>sir</b> https://x.y"), "Up next bsir/b")

TRACKS = [{"id": f"t{i:02d}", "uri": f"spotify:track:t{i:02d}", "title": f"Song {i}", "artist": f"Artist {i % 9}",
           "album": "", "year": "2015", "ms": 200000, "src": ["liked"] if i > 10 else ["top"]} for i in range(80)]
POOL = {"at": time.time(), "tracks": TRACKS, "recent_ids": ["t00", "t01"]}
name, plan, searches = D.parse_plan('Sure! {"name": "Night Shift", "order": [3, 3, 5, 999, "x", 7, 8, 9, 10, 11, 12, 13],'
                                     ' "search": [{"q": "genre:lo-fi", "after": 2}], "lines": {"1": "Easing in, sir.", "40": "nope"}}', TRACKS)
check("plan name", name, "Night Shift")
check("plan dedupes + drops bad", [t["id"] for t in plan][:4], ["t02", "t04", "t06", "t07"])
check("plan line", plan[0].get("line"), "Easing in, sir.")
check("plan searches", searches, [{"q": "genre:lo-fi", "after": 2}])
c = D.candidates(POOL, {"t05": time.time() - 3600})
ids = {t["id"] for t in c}
check("recent excluded", ("t00" in ids, "t01" in ids, "t05" in ids), (False, False, False))
check("thin library relaxes", len(D.candidates({"tracks": TRACKS[:30], "recent_ids": [t["id"] for t in TRACKS[:25]]}, {})) >= 10, True)

# ── DJ engine with fake Spotify ──
D.gather = lambda force=False: POOL
LOG = []
played, queued, posted = [], [], []
S.play = lambda uris=None, context_uri=None, offset=None, device_id=None, position_ms=None: played.append(uris[0]) or "a"
S.queue_add = lambda uri, device_id=None: queued.append(uri)
S.api = lambda method, path, params=None, body=None, _retry=True: posted.append(path)
S.search = lambda q, types=("track",), limit=10: {"tracks": {"items": [{"id": "s1", "uri": "spotify:track:s1", "name": "Found",
                                                                        "artists": [{"name": "Searched"}], "album": {}}]}}
MPRIS = {"id": None, "status": "Playing"}
S.mpris_track = lambda: (MPRIS["id"], MPRIS["status"])
CLAUDE_CALLS = []


def fake_claude(prompt, log=print):
    CLAUDE_CALLS.append(prompt)
    lib = [line for line in prompt.split("LIBRARY (number")[1].splitlines()[1:] if line.strip()]
    order = list(range(1, min(len(lib), 24) + 1))
    return json.dumps({"name": "Test Set", "order": order, "search": [{"q": "genre:test", "after": 3}],
                       "lines": {"5": "A line from Claude, sir."}})


class Cfg(dict):
    def __getitem__(self, k):
        return dict.get(self, k)


cfg = Cfg(jarvisDjChatter="rare", jarvisSpeak=True)
dj = D.DJ(cfg, log=LOG.append, claude=fake_claude, serve=False)


def wait_build():
    for _ in range(200):
        if not dj.building:
            time.sleep(0.05)       # the state / HUD files are written just after building clears
            return
        time.sleep(0.02)


r = dj.start("studying")
check("start reply", (r["ok"], r["say"]), (True, "Putting a studying set together, sir."))
wait_build()
check("one claude call", len(CLAUDE_CALLS), 1)
check("vibe in prompt", "music for studying" in CLAUDE_CALLS[0], True)
check("recent not offered", "| Song 0 |" in CLAUDE_CALLS[0] or "| Song 1 |" in CLAUDE_CALLS[0], False)
check("active", (dj.s["active"], dj.s["set"]), (True, "Test Set"))
check("search slotted after 3", dj.s["tracks"][3]["id"], "s1")
check("first track played", played, [dj.s["tracks"][0]["uri"]])
check("batch queued", queued, [t["uri"] for t in dj.s["tracks"][1:1 + D.BATCH]])
first = dj.pop_line()
check("intro line", first and first["text"].startswith("Here's Test Set, sir."), True)
hud = json.loads(D.HUD_FILE.read_text())
check("hud next three", [n["title"] for n in hud["next"]], [t["title"] for t in dj.s["tracks"][1:4]])

# playback follows the set: each new track tops the queue back up; a rare line every 4-5 tracks
MPRIS["id"] = dj.s["tracks"][0]["id"]
dj.tick()
lines = []
for i in range(1, 12):
    MPRIS["id"] = dj.s["tracks"][i]["id"]
    dj.tick()
    item = dj.pop_line()
    if item:
        lines.append(i)
check("pos follows", dj.s["pos"], 11)
check("queue kept ahead", dj.s["queued_upto"] - dj.s["pos"], D.BATCH)
check("rare cadence", 1 <= len(lines) <= 3 and lines[0] >= 4 and all(b - a >= 4 for a, b in zip(lines, lines[1:])), True)

# "less of this": one Claude call, queued tracks retired, the next new one plays now
CLAUDE_CALLS.clear()
before_queued = [t["uri"] for t in dj.s["tracks"][dj.s["pos"] + 1:dj.s["queued_upto"] + 1]]
r = dj.adjust("less")
wait_build()
check("less: one call", len(CLAUDE_CALLS), 1)
check("less: anchor in prompt", "less of this" in CLAUDE_CALLS[0] and "Song 11" in CLAUDE_CALLS[0], True)
check("less: retired the queued", all(u in dj.s["retired"] for u in before_queued), True)
check("less: skipped to a new one", played[-1], dj.s["tracks"][dj.s["pos"]]["uri"])
# a retired track starting is skipped at once
posted.clear()
MPRIS["id"] = before_queued[0].split(":")[-1]
dj.tick()
check("retired skipped", posted, ["/me/player/next"])

# refill when the set runs low: appended, still one call
CLAUDE_CALLS.clear()
dj.s["tracks"] = dj.s["tracks"][:dj.s["pos"] + 4]
MPRIS["id"] = dj.s["tracks"][dj.s["pos"] + 1]["id"]
dj.tick()
wait_build()
check("refill one call", len(CLAUDE_CALLS), 1)
check("refill carries on", "Carry on smoothly" in CLAUDE_CALLS[0], True)
check("refill appended", len(dj.s["tracks"]) > dj.s["pos"] + 10, True)

# he puts something else on: two foreign tracks → DJ bows out quietly
MPRIS["id"] = "foreign1"
dj.tick()
check("one foreign keeps going", dj.s["active"], True)
MPRIS["id"] = "foreign2"
dj.tick()
check("two foreign → off", (dj.s["active"], dj.s["note"]), (False, "you took over"))

# stop while building: the finished set is dropped
def slow_claude(prompt, log=print):
    time.sleep(0.3)
    return fake_claude(prompt, log)


dj.claude = slow_claude
played.clear()
dj.start("gym")
time.sleep(0.05)
dj.stop()
time.sleep(0.5)
check("stopped build dropped", (dj.s["active"], played), (False, []))
dj.claude = fake_claude

# chatter off: no chatter lines, only the start notice
cfg["jarvisDjChatter"] = "off"
dj.lines.clear()
dj.start("chill")
wait_build()
check("off: notice only", (dj.pop_line() or {}).get("text"), "Here's Test Set, sir.")
for i in range(1, 10):
    MPRIS["id"] = dj.s["tracks"][i]["id"]
    dj.tick()
check("off: silent", dj.pop_line(), None)
# stale lines are dropped
dj.push_line("old news")
dj.lines[-1]["at"] -= D.LINE_STALE_S + 1
check("stale dropped", dj.pop_line(), None)

# restart resumes a recent set
dj2 = D.DJ(cfg, log=LOG.append, claude=fake_claude, serve=False)
check("resume", (dj2.s["active"], dj2.s["set"]), (True, "Test Set"))

# premium false → DJ refuses plainly
VAULT[("spotify", "account")] = json.dumps({"id": "trev", "premium": False})
r = dj.handle({"op": "start", "mood": "gym"})
check("no premium say", (r["ok"], "needs Spotify Premium" in r.get("say", "")), (False, True))
VAULT[("spotify", "account")] = json.dumps({"id": "trev", "premium": True})

# chatter setting writes the HUD key (patched writer)
wrote = {}
A._write_hud_setting = lambda k, v: wrote.__setitem__(k, v)
r = dj.handle({"op": "chatter", "level": "on"})
check("chatter on = normal", (r["ok"], wrote), (True, {"jarvisDjChatter": "normal"}))

# socket round trip
dj3 = D.DJ(cfg, log=LOG.append, claude=fake_claude, serve=True)
for _ in range(100):               # bound before it listens: retry until it answers
    if D.request("status", timeout=1).get("ok"):
        break
    time.sleep(0.02)
check("socket status", D.request("status").get("ok"), True)
A.DJ_SOCK = D.SOCK
check("action over socket", A.dj_status().get("ok"), True)

# ── the voice loop's DJ gate (jarvis.py check_dj) ──
spec = importlib.util.spec_from_file_location("jarvis_main", os.path.join(ROOT, "jarvis.py"))
JV = importlib.util.module_from_spec(spec)
saved = sys.argv
sys.argv = ["jarvis.py"]
spec.loader.exec_module(JV)
sys.argv = saved


class FakeDucker:
    def __init__(self):
        self.log = []

    def duck(self, level, ramp_s=0.0):
        self.log.append(("duck", level))
        return True

    def restore(self, ramp_s=0.0, level=None):
        self.log.append(("restore",))


class FakeVoice:
    def __init__(self):
        self.ducker, self.targets, self.said = FakeDucker(), [], []

    def utterance(self, target=None):
        self.targets.append(target)
        v = self
        return types.SimpleNamespace(add=lambda t: v.said.append(t), finish=lambda: None)


class FakeDJ:
    def __init__(self, text):
        self.items = [{"text": text, "kind": "chatter", "at": time.time()}]
        self.remote_ducked = False

    def pop_line(self):
        return self.items.pop() if self.items else None

    def duck_remote(self, level):
        self.remote_ducked = True
        return lambda: None


def gate(paused=False, combat=False, call=False, stream=(41, "bluez_output.X")):
    vl = types.SimpleNamespace(dj=FakeDJ("Here's one, sir."), paused=paused, cfg=Cfg(jarvisSpeak=True), voice=FakeVoice(),
                               play=lambda u, where="": False)
    A.combat_mode = lambda: combat
    AD.voice_call = lambda outputs=None: call
    AD.music_stream = lambda inputs=None, app="spotify": stream
    JV.hud.reply = lambda t: None
    JV.VoiceLoop.check_dj(vl)
    return vl


vl = gate()
check("dj line said", vl.voice.said, ["Here's one, sir."])
check("dj line on spotify's sink", vl.voice.targets, ["bluez_output.X"])
check("ducked to 30% and back", vl.voice.ducker.log, [("duck", 0.3), ("restore",)])
check("combat silent", gate(combat=True).voice.said, [])
check("paused silent", gate(paused=True).voice.said, [])
check("discord silent", gate(call=True).voice.said, [])
vl = gate(stream=(None, None))
check("remote: api duck, no pactl", (vl.dj.remote_ducked, vl.voice.ducker.log, vl.voice.said), (True, [], ["Here's one, sir."]))

# ── fast path ──
from core import fastpath as F  # noqa: E402


def fp(u):
    st = F.match(u)
    return [(s["tool"], s["args"]) for s in st] if st else None


check("fp dj", fp("DJ for me"), [("dj_start", {"mood": ""})])
check("fp study", fp("play something for studying"), [("dj_start", {"mood": "studying"})])
check("fp gym music", fp("put on some gym music"), [("dj_start", {"mood": "gym"})])
check("fp genre music", fp("play some jazz music"), [("dj_start", {"mood": "jazz music"})])
check("fp like", fp("like this song"), [("spotify_like", {})])
check("fp next unchanged", fp("next song"), [("media", {"action": "next"})])
check("fp pause unchanged", fp("pause music"), [("media", {"action": "pause"})])
check("fp play x", fp("play discovery by daft punk"), [("spotify_play", {"query": "discovery by daft punk", "kind": "any", "device": ""})])
check("fp play on laptop", fp("play daft punk on the laptop"), [("spotify_play", {"query": "daft punk", "kind": "any", "device": "laptop"})])
check("fp audio route kept", fp("play music on the google home"), [("set_audio_output", {"device": "google home"})])
check("fp spotify connect", fp("play spotify on the google home"), [("spotify_transfer", {"device": "google home"})])
check("fp queue", fp("add one more time to the queue"), [("spotify_queue", {"query": "one more time"})])
check("fp more", fp("more like this"), [("dj_adjust", {"direction": "more"})])
check("fp less", fp("less of this"), [("dj_adjust", {"direction": "less"})])
check("fp chatter", fp("dj chatter off"), [("dj_chatter", {"level": "off"})])
check("fp stop dj", fp("stop dj mode"), [("dj_stop", {})])
check("fp what's next is not dj", fp("what's next"), None)
check("fp play video not music", fp("play the next episode"), None)
check("fp widget", fp("show the dj widget")[0][1]["type"], "dj")

print("FAILED: " + ", ".join(FAILS) if FAILS else "all spotify / dj checks passed", flush=True)
os._exit(1 if FAILS else 0)          # daemon threads (DJ loop, socket) would keep a normal exit waiting
