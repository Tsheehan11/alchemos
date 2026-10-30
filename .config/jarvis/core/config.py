"""
Jarvis settings. The HUD owns them (Settings → JARVIS writes the jarvis* keys
into quickshell/settings.json); this reads that file again whenever it changes.
"""
import json
import os
from pathlib import Path

HOME = Path.home()
JARVIS_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = HOME / ".local/share/jarvis"
VOICES_DIR = DATA_DIR / "voices"
HUD_SETTINGS = HOME / ".config/quickshell/settings.json"
SERVERS_FILE = JARVIS_DIR / "servers.json"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
GAME_STATE = RUNTIME / "stark-game/state.json"

# Model aliases the claude CLI resolves to the latest of each family
# (`claude --help`: "Provide an alias for the latest model"), so nothing here
# goes stale when new versions ship.
FAST_MODEL = "haiku"
STRONG_MODEL = "sonnet"
MODELS = ["auto", "haiku", "sonnet", "opus"]

DEFAULTS = {
    "jarvisModel": "auto",              # auto = haiku, sonnet for harder requests
    "jarvisVoice": "bm_george",         # Kokoro voice, or a piper model[:speaker] in ~/.local/share/jarvis/voices
    "jarvisSpeed": 1.0,                 # speech rate multiplier
    "jarvisVoiceVolume": 60,            # VOICE VOLUME, 0-100 %: Jarvis's voice + chime only, a gain after the effects (core/voice.py)
    "jarvisSpeakerVolume": -1,          # own level on the Bluetooth speaker, 0-100 %; -1 = same as VOICE VOLUME
    "jarvisPitch": 0.0,                 # semitones, on top of the effect preset's
    "jarvisEffect": "AUTO",             # AUTO (SUIT on headphones, else HOLOGRAM) | CLEAN | HOLOGRAM | SUIT
    "jarvisSpeak": True,                # spoken replies (HUD text either way)
    "jarvisDuck": True,                 # lower music while speaking
    "jarvisFollowup": 8,                # seconds to listen for a follow-up (0 = off)
    "gameJarvis": True,                 # pause the wake word in combat mode
    "jarvisSpeaker": "",                # Bluetooth MAC of a speaker to use when not on headphones; "" = off
    "jarvisMic": "",                    # PipeWire source node.name; "" = system default input
    "jarvisPlace": "Waterloo, Ontario", # home town for the weather (read by stark_actions.weather)
    "jarvisAutoAddAssignments": False,  # LEARN sync may write to the dedicated assignments calendar without asking
    "jarvisAssignmentsAccount": "google",   # where "STARK – Assignments" lives: google | microsoft
    "jarvisAutoUpdateTracker": False,   # tracker events (grades, new LEARN work, moved deadlines) write to the SE tracker without asking
    "jarvisDecisions": "local",         # local = regex fast path, then the local router (core/router_local.py), then Claude | claude
    "jarvisRouterThreshold": 0.70,      # cosine similarity the local router needs to act (tools/eval_router.py to tune)
}

TIMEOUT_S = 30
MAX_TOOLS = 8
CONTEXT_IDLE_S = 180


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
        self.values = {k: data.get(k, v) for k, v in DEFAULTS.items()}

    def __getitem__(self, k):
        self.reload()
        return self.values[k]

    def model_for(self, strong):
        m = self["jarvisModel"]
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
    """MCP servers Jarvis may use (servers.json). Phase-2 integrations are new entries here.

    Each entry: {"command", "args", "env"?, "enabled"?, "policy"?, "auto_allow"?}
      policy "stark"       → stark_actions decides which calls need a spoken yes
      policy "integration" → off unless enabled; read_tools run freely, every other tool is a
                             write: refused if read_only (the default), else needs a spoken yes
                             unless auto_write maps it to a settings key that's on
      otherwise            → every tool needs a yes except those listed in auto_allow
    """
    raw = read_servers()
    subs = {"{jarvis}": str(JARVIS_DIR), "{venv}": str(JARVIS_DIR / ".venv/bin"), "~": str(HOME)}

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
            env["STARK_DRY_RUN"] = "1"
        servers[name] = {"type": "stdio", "command": expand(s["command"]),
                         "args": [expand(a) for a in s.get("args", [])], "env": env}
        policies[name] = {"policy": s.get("policy", "confirm"), "auto_allow": set(s.get("auto_allow", [])),
                          "name": s.get("name", name), "read_only": s.get("read_only", True),
                          "read_tools": set(s.get("read_tools", [])), "auto_write": dict(s.get("auto_write", {}))}
    return servers, policies
