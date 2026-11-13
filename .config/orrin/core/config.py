"""
Orrin settings. The HUD owns them (Settings → ORRIN writes the orrin* keys
into quickshell/settings.json); this reads that file again whenever it changes.
"""
import json
import os
from pathlib import Path

HOME = Path.home()
ORRIN_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = HOME / ".local/share/orrin"
VOICES_DIR = DATA_DIR / "voices"
HUD_SETTINGS = HOME / ".config/quickshell/settings.json"
SERVERS_FILE = ORRIN_DIR / "servers.json"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
GAME_STATE = RUNTIME / "alchemos-game/state.json"

# Model aliases the claude CLI resolves to the latest of each family
# (`claude --help`: "Provide an alias for the latest model"), so nothing here
# goes stale when new versions ship.
FAST_MODEL = "haiku"
# Undocked and switched on by hand (quickshell OrrinState.laptopOn): lighter on the battery. No academic sync,
# no window watchers, no Bluetooth room speaker (headphones or the laptop's own speakers).
LAPTOP = os.environ.get("ORRIN_LAPTOP") == "1"
STRONG_MODEL = "sonnet"
MODELS = ["auto", "haiku", "sonnet", "opus"]

DEFAULTS = {
    "orrinModel": "auto",              # auto = haiku, sonnet for harder requests
    "orrinVoice": "bm_george",         # Kokoro voice, or a piper model[:speaker] in ~/.local/share/orrin/voices
    "orrinSpeed": 1.0,                 # speech rate multiplier
    "skin": "alchemos",                 # the HUD's skin (quickshell/Skin.qml): names the personas (core/persona.py)
    "orrinPersona": "orrin",          # orrin | selene: who answers by default (core/persona.py); same brain,
                                        # tools, memory and threads, different name, voice and manner
    "seleneEffect": "",                 # SELENE's own effect preset; "" = the same as orrinEffect
    "seleneVoice": "bf_emma",          # SELENE's Kokoro voice (orrin-voices --selene to audition)
    "seleneSpeed": 1.15,                # SELENE's own speech rate (ORRIN keeps orrinSpeed / orrinPitch)
    "selenePitch": 0.0,
    "orrinVoiceVolume": 60,            # VOICE VOLUME, 0-100 %: Orrin's voice + chime only, a gain after the effects (core/voice.py)
    "orrinSpeakerVolume": -1,          # own level on the Bluetooth speaker, 0-100 %; -1 = same as VOICE VOLUME
    "orrinPitch": 0.0,                 # semitones, on top of the effect preset's
    "orrinEffect": "AUTO",             # AUTO (SUIT on headphones, else HOLOGRAM) | CLEAN | HOLOGRAM | SUIT
    "orrinSpeak": True,                # spoken replies (HUD text either way)
    "orrinDuck": True,                 # lower music while speaking
    "orrinFollowup": 8,                # seconds to listen for a follow-up (0 = off)
    "gameOrrin": True,                 # pause the wake word in combat mode
    "orrinSpeaker": "",                # Bluetooth MAC of a speaker to use when not on headphones; "" = off
    "orrinMic": "auto",                # auto = headset mic while one is plugged in, else the laptop DMIC |
                                        # "default" (or "") = system default input | a PipeWire source node.name
    "orrinMicBluetooth": False,        # AUTO may use a Bluetooth headset mic (switches it to call quality)
    "orrinPlace": "Waterloo, Ontario", # home town for the weather (read by alchemos_actions.weather)
    "orrinAutoAddAssignments": False,  # LEARN sync may write to the dedicated assignments calendar without asking
    "orrinAssignmentsAccount": "google",   # where "STARK – Assignments" lives: google | microsoft
    "orrinAutoUpdateTracker": False,   # tracker events (grades, new LEARN work, moved deadlines) write to the SE tracker without asking
    "orrinDecisions": "local",         # local = regex fast path, then the local router (core/router_local.py), then Claude | claude
    "orrinRouterThreshold": 0.70,
    "orrinRouterAsk": True,            # near misses get "Did you mean …?" instead of going straight to Claude (core/router_local.py)
    "orrinWatchInterval": 10,
    "orrinDjChatter": "rare",          # DJ mode lines between tracks: off | rare (every 4-5) | normal (every 2-3) (core/dj.py)          # seconds between a watcher's captures (core/watch.py)
    "orrinCaptureBlocklist": ["bank", "banking", "rbc royal", "td canada", "scotiabank", "cibc", "bmo", "tangerine",
                               "wealthsimple", "paypal", "interac", "password", "1password", "bitwarden", "keepass",
                               "lastpass", "proton pass", "authenticator", "2fa", "credit card"],
                                        # window titles / apps never read or watched (core/screen.py; lock screen and
                                        # password / permission prompts are refused whatever this says)      # cosine similarity the local router needs to act (tools/eval_router.py to tune)
}

TIMEOUT_S = 30
MAX_TOOLS = 8
CONTEXT_IDLE_S = 180          # Claude's own context drops after this much quiet (core/brain.py)
THREAD_IDLE_S = 1800          # a conversation thread lasts this long (core/conversations.py); its last
                              # turns are replayed into a fresh Claude context when he carries on


def old_key(k):
    """The pre-AlchemOS name of a settings key (orrinVoice → jarvisVoice, seleneVoice → fridayVoice), read
    until the HUD's one-time rename (quickshell/Theme.qml migrateNames) has rewritten settings.json."""
    if k == "saverStopOrrin":
        return "saverStopJarvis"
    if k == "gameOrrin":
        return "gameJarvis"
    if k.startswith("orrin") and k[5:6].isupper():
        return "jarvis" + k[5:]
    if k.startswith("selene") and k[6:7].isupper():
        return "friday" + k[6:]
    return k


class Config:
    def __init__(self):
        self._mtime = None
        self.values = dict(DEFAULTS)
        self.reload()

    def reload(self):
        try:
            m = HUD_SETTINGS.stat().st_mtime
        except OSError:
            return
        if m == self._mtime:
            return
        self._mtime = m
        try:
            data = json.loads(HUD_SETTINGS.read_text())
        except (OSError, ValueError):
            return  # mid-write; keep the last good values
        self.values = {k: data.get(k, data.get(old_key(k), v)) for k, v in DEFAULTS.items()}
        self.values["orrinPersona"] = {"jarvis": "orrin", "friday": "selene"}.get(self.values["orrinPersona"],
                                                                                 self.values["orrinPersona"])

    def __getitem__(self, k):
        self.reload()
        return self.values[k]

    def model_for(self, strong):
        m = self["orrinModel"]
        if m in ("haiku", "sonnet", "opus"):
            return m
        return STRONG_MODEL if strong else FAST_MODEL


def read_servers():
    return json.loads(SERVERS_FILE.read_text())


def write_servers(raw):
    """Same layout read_servers() reads (json.dumps, indent 4), so a rewrite only shows the change."""
    tmp = SERVERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, indent=4, ensure_ascii=False) + "\n")
    tmp.replace(SERVERS_FILE)


def integrations(raw=None):
    """Phase-2 entries (policy "integration"), enabled or not: {key: entry}."""
    raw = raw or read_servers()
    return {k: v for k, v in raw.items() if not k.startswith("_") and v.get("policy") == "integration"}


def load_servers(dry_run=False):
    """MCP servers Orrin may use (servers.json). Phase-2 integrations are new entries here.

    Each entry: {"command", "args", "env"?, "enabled"?, "policy"?, "auto_allow"?}
      policy "alchemos"    → alchemos_actions decides which calls need a spoken yes
      policy "integration" → off unless enabled; read_tools run freely, every other tool is a
                             write: refused if read_only (the default), else needs a spoken yes
                             unless auto_write maps it to a settings key that's on
      otherwise            → every tool needs a yes except those listed in auto_allow
    """
    raw = read_servers()
    subs = {"{orrin}": str(ORRIN_DIR), "{venv}": str(ORRIN_DIR / ".venv/bin"), "~": str(HOME)}

    def expand(s):
        for k, v in subs.items():
            s = s.replace(k, v)
        return s

    servers, policies = {}, {}
    for name, s in raw.items():
        if name.startswith("_") or "command" not in s:      # status-only entries (e.g. outlook) start no server
            continue
        integ = s.get("policy") == "integration"
        if not s.get("enabled", not integ):
            continue
        env = {k: expand(v) for k, v in s.get("env", {}).items()}
        if dry_run:
            env["ALCHEMOS_DRY_RUN"] = "1"
        servers[name] = {"type": "stdio", "command": expand(s["command"]),
                         "args": [expand(a) for a in s.get("args", [])], "env": env}
        policies[name] = {"policy": s.get("policy", "confirm"), "auto_allow": set(s.get("auto_allow", [])),
                          "name": s.get("name", name), "read_only": s.get("read_only", True),
                          "read_tools": set(s.get("read_tools", [])), "auto_write": dict(s.get("auto_write", {}))}
    return servers, policies
