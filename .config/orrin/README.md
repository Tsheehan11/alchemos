# Orrin (Orrin / Selene)

The AlchemOS voice assistant: wake word → speech-to-text → fast path → local router → local model → Claude →
text-to-speech.
`orrin.py` is the entry point; the voice loop runs as `orrin.service`. Module overviews live in each
file's docstring (start with `core/voice.py` for speech, `core/tts/` for the engines). Tests: `tools/check_all.sh`.

## Thinking

- **Fast path** (`core/fastpath.py`) and **local router** (`core/router_local.py`, learning in `core/router_learn.py`):
  no AI service, act only when sure.
- **Local model** (`core/local_llm.py`, `orrin-llm.service`): Qwen3.5-9B in llama.cpp on the Arc iGPU, for what the
  router wasn't sure of. Starts in shadow mode (it proposes, Claude acts, agreement is logged per intent); intents it
  earns run locally once shadow mode is off. Email, calendar, docs, assignments and anything that sends stay Claude
  only. `orrin brain status | shadow on|off|report | bench`; model files in `~/.local/share/llama.cpp/models`,
  benchmark in `~/.local/share/orrin/bench`.
- **Claude** (`core/brain.py`): everything else, through the Agent SDK on the Pro login.

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
