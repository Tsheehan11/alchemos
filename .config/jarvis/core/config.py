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
    "jarvisVoice": "en_GB-alan-medium",  # piper voice in ~/.local/share/jarvis/voices
    "jarvisSpeed": 1.0,                 # speech rate multiplier
    "jarvisSpeak": True,                # spoken replies (HUD text either way)
    "jarvisDuck": True,                 # lower music while speaking
    "jarvisFollowup": 8,                # seconds to listen for a follow-up (0 = off)
    "gameJarvis": True,                 # pause the wake word in combat mode
    "jarvisMic": "",                    # PipeWire source node.name; "" = system default input
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


def load_servers(dry_run=False):
    """MCP servers Jarvis may use (servers.json). Phase-2 integrations are new entries here.

    Each entry: {"command", "args", "env"?, "enabled"?, "policy"?, "auto_allow"?}
      policy "stark" → stark_actions decides which calls need a spoken yes
      otherwise      → every tool needs a yes except those listed in auto_allow
    """
    raw = json.loads(SERVERS_FILE.read_text())
    subs = {"{jarvis}": str(JARVIS_DIR), "{venv}": str(JARVIS_DIR / ".venv/bin"), "~": str(HOME)}

    def expand(s):
        for k, v in subs.items():
            s = s.replace(k, v)
        return s

    servers, policies = {}, {}
    for name, s in raw.items():
        if name.startswith("_") or not s.get("enabled", True):
            continue
        env = {k: expand(v) for k, v in s.get("env", {}).items()}
        if dry_run:
            env["STARK_DRY_RUN"] = "1"
        servers[name] = {"type": "stdio", "command": expand(s["command"]),
                         "args": [expand(a) for a in s.get("args", [])], "env": env}
        policies[name] = {"policy": s.get("policy", "confirm"), "auto_allow": set(s.get("auto_allow", []))}
    return servers, policies
