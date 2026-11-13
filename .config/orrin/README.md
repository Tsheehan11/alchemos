# Orrin (Orrin / Selene)

The AlchemOS / AlchemOS voice assistant: wake word → speech-to-text → local router or Claude → text-to-speech.
`orrin.py` is the entry point; the voice loop runs as `orrin.service`. Module overviews live in each
file's docstring (start with `core/voice.py` for speech, `core/tts/` for the engines). Tests: `tools/check_all.sh`.

## Voices

- **Pocket TTS** (`core/tts/pocket.py`): Orrin and Selene, in voices designed once and cloned
  (`~/.local/share/orrin/voices/pocket/`). Runs on the CPU in its own venv; setup in the module docstring.
- **Kokoro** (`core/tts/kokoro.py`) and **piper** (`core/tts/piper.py`): the other engines; piper is the fallback.
- Effects: `effects.json` (presets) and the skin's `voiceRouting`. Pronunciation fixes: `pronunciations.json`.

## Credits

- Pocket TTS by Kyutai: model weights licensed under CC-BY-4.0, <https://huggingface.co/kyutai/pocket-tts>
  (the `pocket-tts` Python package is MIT). Orrin's and Selene's voices are generated with it.
- Kokoro-82M by hexgrad (Apache-2.0), run through kokoro-onnx (MIT).
- piper by the Rhasspy / Open Home Foundation contributors (MIT); each voice model carries its own licence in its model card.
