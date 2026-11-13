#!/usr/bin/env python3
"""AlchemOS voice audition: the same three lines from each candidate voice for ORRIN and SELENE, dry and
through each AlchemOS effect chain (effects.json CHAMBER, RESONANT, ALEMBIC), one WAV per voice × effect
with the three lines in a row. Rendered offline through the assistant's own voice path (Kokoro, the
speech normalizer, effects, loudness matching), so they sound exactly as they would live.

  .venv/bin/python tools/alchemos_audition.py [--out ~/Music/alchemos-audition] [--only orrin|selene]
Files: <persona>_<voice>_<effect>.wav, plus README.txt (the table)."""
import argparse
import os
import sys
import wave

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from core import config as C  # noqa: E402
from core import speech  # noqa: E402
from core.voice import RATE, Voice, resample  # noqa: E402

EFFECTS = ["CLEAN", "CHAMBER", "RESONANT", "ALEMBIC"]          # CLEAN = dry
CAST = {
    # warm, measured, older / scholarly
    "orrin": {"speed": 0.94, "pitch": -0.5, "voices": [
        ("bm_george", "British, older, warm baritone"), ("bm_fable", "British, measured, storyteller"),
        ("bm_daniel", "British, calm, lower"), ("am_onyx", "American, deep, slow"), ("am_michael", "American, warm, even")]},
    # calm, cool, clear
    "selene": {"speed": 0.97, "pitch": 0.0, "voices": [
        ("bf_isabella", "British, clear, composed"), ("bf_alice", "British, cool, crisp"), ("bf_lily", "British, soft, light"),
        ("af_nicole", "American, hushed, calm"), ("af_river", "American, cool, even")]},
}
LINES = {
    "orrin": ["Good evening, sir. Orrin here; the work is ready when you are.",
              "The processor is at forty-two percent, and the Iron theme is set on all three screens.",
              "Welcome back to AlchemOS. I've sealed the vault and kept the furnace warm."],
    "selene": ["Hey boss, Selene here. Everything's calm and running.",
               "The processor is at forty-two percent, and the Iron theme is set on all three screens.",
               "Welcome back to AlchemOS. The vault's sealed, and the night is quiet."],
}
EFFECT_NOTES = {"CLEAN": "dry", "CHAMBER": "stone chamber: a small, hard-walled room", "RESONANT": "faint metallic ring (comb)",
                "ALEMBIC": "glass vessel: band-limited, a very short glassy echo"}


def render(voice, text):
    chunks = []
    for sent in speech.sentences(speech.normalize(text)):
        a, sr = voice.render(sent, voice.params())
        chunks.append(resample(a, sr, RATE))
    return np.concatenate(chunks) if chunks else np.zeros(1, np.float32)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="~/Music/alchemos-audition")
    ap.add_argument("--only", choices=list(CAST))
    args = ap.parse_args()
    out = os.path.expanduser(args.out)
    os.makedirs(out, exist_ok=True)
    voice = Voice(C.Config(), log=lambda *a: None)
    gap = np.zeros(int(RATE * 0.7), np.float32)
    rows = []
    for who, cast in CAST.items():
        if args.only and who != args.only:
            continue
        for v, note in cast["voices"]:
            for fx in EFFECTS:
                voice.overrides = {"voice": v, "preset": fx, "speed": cast["speed"], "pitch": cast["pitch"]}
                audio = np.concatenate([x for line in LINES[who] for x in (render(voice, line), gap)])
                name = f"{who}_{v}_{fx.lower()}.wav"
                with wave.open(os.path.join(out, name), "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
                    w.writeframes((np.clip(audio * 0.9, -1, 1) * 32767).astype(np.int16).tobytes())
                rows.append((who.upper(), v, note, fx, name))
                print(f"{who:6} {v:12} {fx:9} → {name}", flush=True)
    with open(os.path.join(out, "README.txt"), "w") as f:
        f.write("AlchemOS voice audition (tools/alchemos_audition.py)\n\n")
        for who in CAST:
            f.write(f"{who.upper()}: speed {CAST[who]['speed']}, pitch {CAST[who]['pitch']}; lines:\n")
            for line in LINES[who]:
                f.write(f"  - {line}\n")
        f.write("\nEffects: " + "; ".join(f"{k} = {v}" for k, v in EFFECT_NOTES.items()) + "\n\n")
        for r in rows:
            f.write("  ".join(f"{c:<28}" if i == 4 else f"{c:<12}" for i, c in enumerate(r)).rstrip() + "\n")


if __name__ == "__main__":
    main()
