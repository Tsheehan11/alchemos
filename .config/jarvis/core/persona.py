"""
Personas: JARVIS and FRIDAY. One assistant (same brain, tools, memory, threads, router and
learned intents) with two names, voices and manners.

  active   the default persona: Settings → JARVIS → PERSONA ("jarvisPersona" in quickshell/settings.json),
           switched by voice ("Jarvis, switch to Friday"), the HUD, or `qs ipc call jarvis persona friday`.
           Timers, DJ lines, task announcements and typed questions use it.
  current  who is talking right now: the persona the wake word named, for the whole exchange
           ("hey Friday …" is answered by FRIDAY even while JARVIS is the default), else active.

JARVIS is exactly what it always was: its text is never touched here. FRIDAY gets
  - her own voice / speed / pitch (fridayVoice, fridaySpeed, fridayPitch; the effect preset is shared),
  - a paragraph in Claude's system prompt and a "[FRIDAY]" tag on her turns (core/brain.py), so the
    persona costs no extra Claude call and doesn't break the prompt cache,
  - style(): her versions of the stock lines (fast path, errors, confirmations, DJ, alerts) and a
    "sir" → "boss" pass over anything else that reaches the speaker or the HUD.

Names follow the HUD's skin (quickshell/skins/<id>/skin.json: personas, osName; the same fallback as
quickshell/Skin.qml: the asked skin, else alchemos, else the base names). ALCHEMOS calls them ORRIN and
SELENE on AlchemOS, the legacy skin JARVIS and FRIDAY on STARK OS. The ids (jarvis / friday), wake words
and manner are the same in every skin, and "Orrin" / "Selene" work wherever "jarvis" / "friday" do.
Claude learns the names per turn from a tag like "[AlchemOS · ORRIN · SELENE]" (tag()), so a skin
switch applies at once and the system prompt stays cached; the legacy names need no tag.
"""
import json
import re
import threading

from . import config as C

NAMES = ("jarvis", "friday")
ALIASES = {"orrin": "jarvis", "selene": "friday"}
SKINS_DIR = C.HOME / ".config/quickshell/skins"
DEFAULT_SKIN = "alchemos"
# what a skin leaves out (quickshell/Skin.qml BASE); name: labels, call: in a sentence
BASE = {"osName": "the desktop", "personas": {"jarvis": {"name": "JARVIS", "call": "Jarvis"},
                                              "friday": {"name": "FRIDAY", "call": "Friday"}}}
UNTAGGED = ("STARK OS", "JARVIS", "FRIDAY")      # the names the system prompt itself uses: no tag needed
_skin_cache = {}                                 # path → (mtime, data)

_lock = threading.Lock()
_override = None        # persona of the exchange in progress (named by its wake word)
_seen = None            # the active persona this process last announced / switched to


def norm(name):
    n = str(name or "").strip().lower()
    n = ALIASES.get(n, n)
    return n if n in NAMES else None


def _read(sid):
    """A skin's skin.json (cached by mtime), None if it isn't installed or doesn't parse."""
    if not sid or sid.startswith("_"):
        return None
    path = SKINS_DIR / sid / "skin.json"
    try:
        m = path.stat().st_mtime
    except OSError:
        return None
    hit = _skin_cache.get(path)
    if hit and hit[0] == m:
        return hit[1]
    try:
        data = json.loads(path.read_text())
        data = data if isinstance(data, dict) else None
    except (OSError, ValueError):
        data = None
    _skin_cache[path] = (m, data)
    return data


def skin(cfg=None):
    """The skin the HUD shows: the asked one if installed, else alchemos, else "base"."""
    try:
        asked = str((cfg or C.Config())["skin"] or DEFAULT_SKIN)
    except Exception:
        asked = DEFAULT_SKIN
    if _read(asked):
        return asked
    return DEFAULT_SKIN if _read(DEFAULT_SKIN) else "base"


def skin_data(cfg=None):
    return _read(skin(cfg)) or {}


def os_name_of(sid):
    """A skin's desktop name by id (the incoming skin during a switch, before settings.json says so)."""
    return (_read(sid) or {}).get("osName") or BASE["osName"]


def os_name(cfg=None):
    """The desktop's name as the skin shows it: 'AlchemOS' (legacy 'STARK OS')."""
    return skin_data(cfg).get("osName") or BASE["osName"]


def _persona(who, key, cfg):
    who = norm(who) or current(cfg)
    p = (skin_data(cfg).get("personas") or {}).get(who) or {}
    return p.get(key) or BASE["personas"][who][key]


def label(who=None, cfg=None):
    """'ORRIN' / 'SELENE' (legacy 'JARVIS' / 'FRIDAY') for who (default: who's talking)."""
    return _persona(who, "name", cfg)


def call(who=None, cfg=None):
    """The name in a sentence: 'Orrin' / 'Selene' (legacy 'Jarvis' / 'FRIDAY')."""
    return _persona(who, "call", cfg)


def skin_tag(cfg=None):
    """The turn's names tag, "" when they're the prompt's own (STARK OS, JARVIS, FRIDAY)."""
    names = (os_name(cfg), label("jarvis", cfg), label("friday", cfg))
    return "" if names == UNTAGGED else "[" + " · ".join(names) + "] "


def active(cfg=None):
    try:
        return norm((cfg or C.Config())["jarvisPersona"]) or "jarvis"
    except Exception:
        return "jarvis"


def current(cfg=None):
    return _override or active(cfg)


def begin(name):
    """An exchange starts, answered by `name` (None → the active persona)."""
    global _override
    _override = norm(name)


def end():
    global _override
    _override = None


def set_active(name, cfg=None):
    """Make `name` the default persona: written to quickshell/settings.json (the HUD reloads it, Config
    re-reads it by mtime). The exchange in progress switches too, so the confirmation is in the new
    voice. → True if it changed."""
    global _seen, _override
    n = norm(name)
    if not n:
        raise ValueError(f"unknown persona {name!r} (jarvis | friday)")
    with _lock:
        try:
            data = json.loads(C.HUD_SETTINGS.read_text())
        except (OSError, ValueError):
            data = {}
        changed = data.get("jarvisPersona", "jarvis") != n
        if changed:
            data["jarvisPersona"] = n
            tmp = C.HUD_SETTINGS.with_suffix(".persona.tmp")
            tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n")
            tmp.replace(C.HUD_SETTINGS)
        _seen = n
        if _override:
            _override = n
    return changed


def switched(cfg):
    """The voice loop polls this: the active persona changed from outside this process (Settings,
    IPC) since we last looked → the new name (to announce), else None. The first call only records."""
    global _seen
    a = active(cfg)
    if _seen is None:
        _seen = a
        return None
    if a != _seen:
        _seen = a
        return a
    return None


def voice_params(cfg, who=None):
    """(voice, speed, pitch) settings for who's talking; JARVIS's are the jarvis* keys."""
    if (who or current(cfg)) == "friday":
        return cfg["fridayVoice"], cfg["fridaySpeed"], cfg["fridayPitch"]
    return cfg["jarvisVoice"], cfg["jarvisSpeed"], cfg["jarvisPitch"]


def announce_line(who, cfg=None):
    n = {"jarvis": label("jarvis", cfg), "friday": label("friday", cfg)}
    return {"jarvis": f"{n['jarvis']} here, sir. {n['friday']}'s on standby.",
            "friday": f"Hey boss, {n['friday']} here. {n['jarvis']} is taking five."}[who]


def switch_reply(who, changed):
    if not changed:
        return {"jarvis": "Still me, sir.", "friday": "Already here, boss."}[who]
    return announce_line(who)


# ── FRIDAY's manner ─────────────────────────────────────────────────────────────
# Brain: appended to JARVIS's system prompt (which stays as it is); her turns start with "[FRIDAY]".
PROMPT = """
You have a second persona, FRIDAY, with the same tools, memory and rules. A message tagged [FRIDAY] is answered as FRIDAY; every other message is answered as JARVIS, exactly as described above. FRIDAY is warmer, quicker and more casual than JARVIS: friendly, a little playful, plain words and contractions, short punchy sentences, no butler formality. She calls him "boss" (sparingly), never "sir", and she is FRIDAY, not JARVIS. Same speech rules: written for the ear, 1-2 short sentences, no lists or symbols. Never write the [FRIDAY] tag yourself.
A message may also start with a names tag such as [AlchemOS · ORRIN · SELENE]: the desktop is wearing a skin that renames things. The first name is what the desktop is called (say that, never STARK OS), the second is JARVIS's name and the third FRIDAY's. Same two of you, same manner; only the names change. In those exchanges call yourselves, each other and the desktop only by the tag's names (he may still say "Jarvis" or "Friday", or wake you with "hey Jarvis": that means you). For example, with [AlchemOS · ORRIN · SELENE] the desktop is AlchemOS, JARVIS is ORRIN and FRIDAY is SELENE. Never write a names tag yourself."""

TAG = "[FRIDAY] "


def tag(text, who=None, cfg=None):
    """The user turn as Claude sees it: FRIDAY's turns carry [FRIDAY], and every turn under a skin that renames
    things starts with its names tag ("[AlchemOS · ORRIN · SELENE] "). Legacy JARVIS turns are unchanged."""
    t = TAG + text if (who or current()) == "friday" else text
    return skin_tag(cfg) + t


# Her versions of JARVIS's stock lines (exact match, after the line is formatted).
FRIDAY_LINES = {
    # core/voice.py COMMON (pre-rendered) + jarvis.py
    "Right away, sir.": "On it, boss.",
    "Done, sir.": "Done.",
    "Very well, sir.": "You got it.",
    "Very good, sir.": "Cool.",
    "You're welcome, sir.": "Anytime, boss.",
    "Goodnight, sir.": "Night, boss.",
    "Your timer is done, sir.": "Timer's up, boss.",
    "Nothing's playing, sir.": "Nothing's playing right now.",
    "Sorry sir, I didn't catch that.": "Sorry boss, didn't catch that.",
    "I'm having trouble reaching the network, sir.": "Can't reach the network, boss.",
    # core/brain.py ERRORS
    "I've hit the Claude usage limit, sir.": "We're out of Claude for now, boss. The limit's maxed.",
    "Claude isn't answering, sir. I'm reconnecting.": "Claude's not answering. Reconnecting, hang on.",
    "That took too long, sir. I've stopped.": "That was dragging, so I stopped it.",
    "My Claude login has lapsed, sir. Run claude to sign in again.": "My Claude login expired, boss. Run claude to sign back in.",
    "Something went wrong on my end, sir.": "Ugh, something broke on my end, boss.",
    "That needed more steps than I'm allowed, sir.": "That needs more steps than I'm allowed, boss.",
    "Claude didn't report my usage just now, sir.": "Claude didn't send usage numbers just now, boss.",
    # core/dj.py
    "DJ mode off, sir.": "DJ mode's off.",
    "DJ mode wasn't on, sir.": "DJ mode wasn't on, boss.",
    "DJ mode isn't on, sir.": "DJ mode isn't on, boss.",
    "Keeping this vibe, sir.": "Keeping this vibe going.",
    "More like this, sir.": "More like this, coming up.",
    "Changing it up, sir.": "Switching it up.",
    "I'll keep quiet between tracks, sir.": "I'll stay quiet between tracks.",
    "Only the odd word between tracks, sir.": "Just the odd word between tracks.",
    "I'll chime in more often, sir.": "I'll chat a bit more between tracks.",
    "There's no set playing to save, sir.": "No set playing to save, boss.",
    "I couldn't save that, sir.": "Couldn't save that one.",
    "I couldn't put that set together, sir.": "Couldn't build that set, boss.",
    "There isn't enough in your library for a set yet, sir.": "Your library's a bit thin for a set yet, boss.",
    "One moment, sir, I'm still on the last change.": "Hang on, still sorting the last change.",
    "I'm still putting the last set together, sir.": "Still building the last set, hang on.",
}

# Anything else: Claude already writes FRIDAY's replies in her manner (PROMPT); the rest of the
# hard-coded lines (tools, confirmations, alerts) get the vocative swapped and the stiffest phrases eased.
_RULES = [
    (r"^Very well, sir\b", "You got it"),
    (r"^Right away, sir\b", "On it, boss"),
    (r"^Very good, sir\b", "Nice"),
    (r"^Certainly, sir\b", "Sure thing"),
    (r"^Good (morning|afternoon|evening), sir\b", lambda m: m.group(1).capitalize() + ", boss"),
    (r"\bShall I\b", "Want me to"),
    (r"\bshall I\b", "want me to"),
    (r"\bSorry,? sir\b", "Sorry boss"),
    (r"\bI'm afraid (?=I |you |that |there |it )", ""),
    (r"^Sir, ", "Boss, "),
    (r"\bsir\b", "boss"),
    (r"\bSir\b", "Boss"),
    (r"\bthat's all, boss\b", "that's it, boss"),
]
_RULES = [(re.compile(p), r) for p, r in _RULES]


def style(text, who=None):
    """Text on its way to the speaker or the HUD, in who's manner. JARVIS: unchanged."""
    if not text or (who or current()) != "friday":
        return text
    s = str(text)
    hit = FRIDAY_LINES.get(s.strip())
    if hit:
        return hit
    for pat, rep in _RULES:
        s = pat.sub(rep, s)
    # "Want me to …?" after the rewrite: sentence case if the rule left a lowercase start
    return s[:1].upper() + s[1:] if s else s


# ── DJ: lines written for each set (core/dj.py) and the stock templates between tracks ──
DJ_VOICE = {"jarvis": 'in {name}\'s voice (dry, British, calls him "sir"',
            "friday": 'in {name}\'s voice (warm, quick, casual, calls him "boss", never "sir"'}


def dj_voice(who, cfg=None):
    return DJ_VOICE[who].format(name=call(who, cfg))
DJ_TEMPLATES = {
    "friday": ["{title}, by {artist}.", "Next up: {title}.", "Ooh, {artist}.", "Keeping it rolling with {artist}.",
               "Here's {artist}. {title}.", "This one's {title}."],
}

# ── the wake-word chime: each persona has its own two notes (JARVIS's are the HUD's unlock E5 / B5) ──
CHIME_NOTES = {"jarvis": [(659.3, 0.0), (987.8, 0.07)],          # E5 → B5, a fifth
               "friday": [(784.0, 0.0), (1174.7, 0.06)]}         # G5 → D6, a fifth higher and quicker
CHIME_SHIMMER = {"jarvis": 1318.5, "friday": 1568.0}             # E6 / G6
