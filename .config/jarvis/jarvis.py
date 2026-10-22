#!/usr/bin/env python3
"""
JARVIS — voice assistant for STARK OS. Runs fully offline.

  "Hey Jarvis"                          → chime + LISTENING… on the HUD
  "…open Spotify" / "launch Discord"    → opens that app (any installed app)
  "…what's the derivative of x squared" → opens Claude with your question filled in
  (say nothing after the wake word)     → just opens Claude

Wake word: openWakeWord.  Speech-to-text: faster-whisper (on the CPU).
Test:  ~/.config/jarvis/.venv/bin/python ~/.config/jarvis/jarvis.py
"""
import atexit
import configparser
import difflib
import glob
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.parse

import numpy as np
import openwakeword
from openwakeword.model import Model

# ── Settings ─────────────────────────────────────
WAKEWORD = "hey_jarvis"
THRESHOLD = 0.5            # raise to ~0.7 if it triggers by accident, lower if it misses you
COOLDOWN_S = 2.0
WHISPER_MODEL = "base.en"  # "small.en" = more accurate but slower; "tiny.en" = fastest

MAX_COMMAND_S = 8.0        # longest command it will listen for
SILENCE_END_S = 1.0        # stop listening after this much silence
NO_SPEECH_TIMEOUT_S = 3.5  # if you say nothing at all → just open Claude

CLAUDE_URL = "https://claude.ai/new"
RATE = 16000
CHUNK = 1280               # 80 ms

# Friendly names → commands (checked before installed apps)
ALIASES = {
    "claude": f"zen-browser --new-window {CLAUDE_URL}",
    "claude code": "kitty -e claude",
    "code": "code", "vs code": "code", "vscode": "code", "v s code": "code",
    "visual studio code": "code", "visual studio": "code",
    "browser": "zen-browser", "zen": "zen-browser", "web": "zen-browser", "internet": "zen-browser",
    "terminal": "kitty", "kitty": "kitty", "console": "kitty",
    "files": "dolphin", "file manager": "dolphin", "dolphin": "dolphin",
    "spotify": "spotify-launcher", "music": "spotify-launcher",
    "steam": "steam", "games": "steam",
    "discord": "discord",
    "settings": "systemsettings", "system settings": "systemsettings",
}

OPEN_RE = re.compile(
    r"^(?:hey jarvis\s+)?(?:can you\s+|could you\s+|please\s+)*"
    r"(?:open|launch|start|run|show|bring up|pull up|fire up|load)\s+(?:up\s+)?(?:the\s+|my\s+)?(.+?)(?:\s+(?:app|application|please))*$"
)

CHIMES = [
    "/usr/share/sounds/ocean/stereo/message-new-instant.oga",
    "/usr/share/sounds/freedesktop/stereo/message.oga",
]


# ── Helpers ──────────────────────────────────────
def qs(*args):
    """Talk to the Quickshell HUD; silently ignored if it isn't running."""
    subprocess.run(["qs", "ipc", "call", "jarvis", *args],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def heartbeat():
    while True:
        qs("online")
        time.sleep(5)


def chime():
    for path in CHIMES:
        if os.path.exists(path):
            subprocess.Popen(["pw-play", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return


def launch(cmd):
    """Start through Hyprland so the app isn't tied to this script."""
    subprocess.Popen(["hyprctl", "dispatch", "exec", cmd],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def normalize(s):
    s = s.lower().strip()
    s = re.sub(r"[^\w\s']", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_apps():
    """name → command for every installed app (.desktop files)."""
    apps = {}
    dirs = ["/usr/share/applications",
            os.path.expanduser("~/.local/share/applications"),
            "/var/lib/flatpak/exports/share/applications"]
    for d in dirs:
        for path in glob.glob(os.path.join(d, "*.desktop")):
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(path, encoding="utf-8")
                e = cp["Desktop Entry"]
            except Exception:
                continue
            if e.get("Type", "") != "Application" or e.get("NoDisplay", "false").lower() == "true":
                continue
            name, exe = e.get("Name"), e.get("Exec")
            if not name or not exe:
                continue
            exe = re.sub(r"\s*%[a-zA-Z]", "", exe).strip()
            apps.setdefault(normalize(name), exe)
            if e.get("GenericName"):
                apps.setdefault(normalize(e.get("GenericName")), exe)
    return apps


APPS = {}


def find_app(target):
    t = normalize(target)
    if not t:
        return None, None
    if t in ALIASES:
        return ALIASES[t], t
    if t in APPS:
        return APPS[t], t
    for n, cmd in APPS.items():
        if n.startswith(t) or t in n.split():
            return cmd, n
    names = list(ALIASES) + list(APPS)
    m = difflib.get_close_matches(t, names, n=1, cutoff=0.6)
    if m:
        return ALIASES.get(m[0]) or APPS[m[0]], m[0]
    return None, None


def ask_claude(question):
    url = f"{CLAUDE_URL}?q={urllib.parse.quote(question)}"
    launch(f"zen-browser --new-window {shlex.quote(url)}")


def handle(text):
    raw = text.strip()
    t = normalize(raw)
    print(f'JARVIS: heard "{raw}"', flush=True)

    if not t:
        qs("heard", "Opening Claude")
        launch(ALIASES["claude"])
        return

    m = OPEN_RE.match(t)
    if m:
        cmd, name = find_app(m.group(1))
        if cmd:
            qs("heard", f"Opening {name.title()}")
            launch(cmd)
        else:
            qs("heard", f"Couldn't find \"{m.group(1)}\"")
        return

    # Just an app name on its own ("Spotify")
    if len(t.split()) <= 2:
        cmd, name = find_app(t)
        if cmd:
            qs("heard", f"Opening {name.title()}")
            launch(cmd)
            return

    # Anything else → it's a question for Claude
    qs("heard", "Asking Claude")
    ask_claude(raw)


# ── Audio ────────────────────────────────────────
class Mic:
    def __init__(self):
        self.proc = subprocess.Popen(
            ["pw-record", "--rate", str(RATE), "--channels", "1", "--format", "s16", "-"],
            stdout=subprocess.PIPE)
        atexit.register(self.proc.terminate)
        self.noise = 300.0

    def read(self):
        n = CHUNK * 2
        data = self.proc.stdout.read(n)
        if not data or len(data) < n:
            print("JARVIS: microphone stream ended", file=sys.stderr)
            sys.exit(1)
        return np.frombuffer(data, dtype=np.int16)

    @staticmethod
    def rms(a):
        return float(np.sqrt(np.mean(a.astype(np.float32) ** 2)))

    def track_noise(self, a):
        self.noise = 0.97 * self.noise + 0.03 * self.rms(a)

    def record_command(self):
        frames, speech, silent = [], False, 0.0
        elapsed = 0.0
        step = CHUNK / RATE
        while True:
            a = self.read()
            frames.append(a)
            elapsed += step
            if self.rms(a) > max(450.0, self.noise * 2.5):
                speech, silent = True, 0.0
            else:
                silent += step
            if speech and silent >= SILENCE_END_S:
                break
            if not speech and elapsed >= NO_SPEECH_TIMEOUT_S:
                return None
            if elapsed >= MAX_COMMAND_S:
                break
        return np.concatenate(frames).astype(np.float32) / 32768.0


# ── Main loop ────────────────────────────────────
def main():
    global APPS
    print("JARVIS: loading models…", flush=True)
    openwakeword.utils.download_models([WAKEWORD])
    wake = Model(wakeword_models=[WAKEWORD], inference_framework="onnx")

    from faster_whisper import WhisperModel
    stt = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    APPS = load_apps()
    print(f"JARVIS: indexed {len(APPS)} apps", flush=True)

    mic = Mic()
    atexit.register(lambda: qs("offline"))
    threading.Thread(target=heartbeat, daemon=True).start()
    print('JARVIS: online — say "Hey Jarvis"', flush=True)

    last = 0.0
    while True:
        a = mic.read()
        score = max(wake.predict(a).values())
        if score < THRESHOLD or time.time() - last < COOLDOWN_S:
            mic.track_noise(a)
            continue

        print(f"JARVIS: wake word (score {score:.2f})", flush=True)
        chime()
        qs("status", "Listening…")

        audio = mic.record_command()
        if audio is None:
            handle("")
        else:
            qs("status", "Thinking…")
            segments, _ = stt.transcribe(audio, language="en", beam_size=1)
            handle(" ".join(s.text for s in segments))

        wake.reset()
        last = time.time()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
