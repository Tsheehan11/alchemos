#!/usr/bin/env python3
"""
Voice audition: every British male voice (Kokoro bm_*, then piper) says the same
line, announcing its name first, so you can pick by ear.

  jarvis-voices                  # with your current effect preset (Settings → JARVIS)
  jarvis-voices --effect CLEAN   # raw voices, no effects
  jarvis-voices --only kokoro    # or piper
  jarvis-voices --line "Shall I render the suit, sir?"
  jarvis-voices --friday --out ~/Music/friday-audition --effect HOLOGRAM
                                 # FRIDAY: every English female voice (Kokoro bf_*, then af_*), the same
                                 # three lines each, written as WAVs instead of played

Pick one in Settings → JARVIS → Voice, or set "jarvisVoice" in quickshell/settings.json.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import config as C  # noqa: E402
from core.voice import Voice, is_kokoro, kokoro_voices, piper_voices  # noqa: E402

LINE = "Good evening, sir. All systems are online, and the lights are set to MARK III."
# FRIDAY audition lines: a greeting, a status line with numbers, a quick casual one
FRIDAY_LINES = ["Hey boss. FRIDAY here, all systems are green and the lights are set to MARK III.",
                "Your CPU is at sixty-two degrees and the five-hour Claude window resets at four twenty.",
                "On it. Want me to queue something chill while you work?"]
BRITISH_MALE_PIPER = ("alan", "northern_english_male", "semaine-medium:spike", "semaine-medium:obadiah")


def spoken_name(v):
    """bm_george → "Kokoro, George"; en_GB-semaine-medium:obadiah → "Piper, Semaine, Obadiah"."""
    if is_kokoro(v):
        return "Kokoro, " + v.split("_", 1)[1].capitalize()
    model, _, spk = v.partition(":")
    words = model.replace("en_GB-", "").rsplit("-", 1)[0].replace("_", " ").title()
    return "Piper, " + words + (", " + spk.capitalize() if spk else "")


def bt_speakers():
    """Paired Bluetooth audio sinks that aren't headphones: [{"mac", "name"}]."""
    import subprocess
    out = []
    paired = subprocess.run(["bluetoothctl", "devices", "Paired"], capture_output=True, text=True).stdout
    for line in paired.splitlines():
        parts = line.split(" ", 2)
        if len(parts) < 3:
            continue
        info = subprocess.run(["bluetoothctl", "info", parts[1]], capture_output=True, text=True).stdout
        if "Audio Sink" in info and "Icon: audio-head" not in info:
            out.append({"mac": parts[1], "name": parts[2]})
    return out


def female_voices():
    """English female Kokoro voices, British first. Kokoro's other f voices (ef/ff/hf/if/jf/pf/zf) are
    Spanish, French, Hindi, Italian, Japanese, Portuguese and Mandarin speakers: they mangle English."""
    v = kokoro_voices()
    return [x for x in v if x.startswith("bf_")] + [x for x in v if x.startswith("af_")]


def friday_audition(args):
    import wave
    import numpy as np
    from core import effects
    cfg = C.Config()
    voice = Voice(cfg, log=print)
    preset = args.effect or "HOLOGRAM"
    lines = [args.line] if args.line != LINE else FRIDAY_LINES
    voices = female_voices()
    print(f"{len(voices)} voices · effect {preset}" + (f" · → {args.out}" if args.out else ""))
    if args.out:
        os.makedirs(os.path.expanduser(args.out), exist_ok=True)
    for i, v in enumerate(voices, 1):
        # FRIDAY's own rate and pitch (Settings → JARVIS → PERSONA), not JARVIS's
        voice.overrides = {"voice": v, "preset": preset, "speed": cfg["fridaySpeed"], "pitch": cfg["fridayPitch"]}
        if not args.out:
            print(f"{i:>2}. {v}")
            voice.speak(f"{spoken_name(v)}. " + " ".join(lines))
            continue
        for n, line in enumerate(lines, 1):
            params = voice.params()
            chunks = []
            from core import speech
            from core.voice import RATE, resample
            for sent in speech.sentences(speech.normalize(line)):
                a, sr = voice.render(sent, params)
                chunks.append(resample(a, sr, RATE))
            audio = np.concatenate(chunks) if chunks else np.zeros(1, np.float32)
            path = os.path.join(os.path.expanduser(args.out), f"{i:02d}_{v}_line{n}.wav")
            with wave.open(path, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
                w.writeframes((np.clip(audio * 0.9, -1, 1) * 32767).astype(np.int16).tobytes())
        print(f"{i:>2}. {v}")
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--effect", help="effect preset (default: your setting)")
    ap.add_argument("--only", choices=["kokoro", "piper"])
    ap.add_argument("--line", default=LINE)
    ap.add_argument("--list", action="store_true", help="JSON of voices and effect presets (for Settings)")
    ap.add_argument("--friday", action="store_true", help="audition the English female voices (FRIDAY)")
    ap.add_argument("--out", help="write WAVs to this folder instead of playing (one file per voice and line)")
    args = ap.parse_args()

    if args.list:
        import json
        from core import effects
        british = [v for v in kokoro_voices() if v.startswith("bm_")] + [v for v in kokoro_voices() if v.startswith("bf_")]
        print(json.dumps({"voices": british + piper_voices(), "female": female_voices(), "effects": ["AUTO"] + list(effects.presets()),
                          "speakers": bt_speakers()}))
        return

    if args.friday:
        return friday_audition(args)

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
