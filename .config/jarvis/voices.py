#!/usr/bin/env python3
"""
Voice audition: every British male voice (Kokoro bm_*, then piper) says the same
line, announcing its name first, so you can pick by ear.

  jarvis-voices                  # with your current effect preset (Settings → JARVIS)
  jarvis-voices --effect CLEAN   # raw voices, no effects
  jarvis-voices --only kokoro    # or piper
  jarvis-voices --line "Shall I render the suit, sir?"

Pick one in Settings → JARVIS → Voice, or set "jarvisVoice" in quickshell/settings.json.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import config as C  # noqa: E402
from core.voice import Voice, is_kokoro, kokoro_voices, piper_voices  # noqa: E402

LINE = "Good evening, sir. All systems are online, and the lights are set to MARK III."
BRITISH_MALE_PIPER = ("alan", "northern_english_male", "semaine-medium:spike", "semaine-medium:obadiah")


def spoken_name(v):
    """bm_george → "Kokoro, George"; en_GB-semaine-medium:obadiah → "Piper, Semaine, Obadiah"."""
    if is_kokoro(v):
        return "Kokoro, " + v.split("_", 1)[1].capitalize()
    model, _, spk = v.partition(":")
    words = model.replace("en_GB-", "").rsplit("-", 1)[0].replace("_", " ").title()
    return "Piper, " + words + (", " + spk.capitalize() if spk else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--effect", help="effect preset (default: your setting)")
    ap.add_argument("--only", choices=["kokoro", "piper"])
    ap.add_argument("--line", default=LINE)
    ap.add_argument("--list", action="store_true", help="JSON of voices and effect presets (for Settings)")
    args = ap.parse_args()

    if args.list:
        import json
        from core import effects
        british = [v for v in kokoro_voices() if v.startswith("bm_")] + [v for v in kokoro_voices() if v.startswith("bf_")]
        print(json.dumps({"voices": british + piper_voices(), "effects": list(effects.presets())}))
        return

    voices = []
    if args.only != "piper":
        voices += [v for v in kokoro_voices() if v.startswith("bm_")]
    if args.only != "kokoro":
        voices += [v for v in piper_voices() if any(k in v for k in BRITISH_MALE_PIPER)]
    if not voices:
        sys.exit("no voices found (Kokoro files in ~/.local/share/jarvis/kokoro, piper in …/voices)")

    cfg = C.Config()
    voice = Voice(cfg, log=print)
    preset = args.effect or cfg["jarvisEffect"]
    print(f"{len(voices)} voices · effect {preset} · current: {cfg['jarvisVoice']}\n")
    try:
        for i, v in enumerate(voices, 1):
            print(f"{i:>2}. {v}")
            voice.overrides = {"voice": v, "preset": preset}
            voice.speak(f"{spoken_name(v)}. {args.line}")
    except KeyboardInterrupt:
        voice.stop()
    print('\nSet it in Settings → JARVIS → Voice (or "jarvisVoice" in ~/.config/quickshell/settings.json).')


if __name__ == "__main__":
    main()
