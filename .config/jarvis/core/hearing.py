"""
Hearing: where a command starts and ends, and what it says. Tuned on recordings
of Trevor at the desk (`jarvis --record`, 2026-10-25):

- The wake word fires 0.3-0.6 s after "Jarvis", so in one breath ("hey Jarvis
  dim the lights") the first command word has already gone by. The command
  therefore starts from the audio *before* the wake word fired (PRE_ROLL_S);
  whisper hears "Hey Jarvis, dim the lights" and strip_wake() drops the greeting.
- Silero VAD keeps state between calls: it's reset and primed on that pre-roll,
  and fed whole 40 ms frames (480-sample frames left a ragged remainder and
  scored real speech under the old 0.5 threshold).
- whisper retried low-confidence audio at higher temperatures (1.1-1.7 s instead of
  0.3 s); temperature 0 only, plus a vocabulary prompt, is faster and more accurate.
"""
import re
import time

import numpy as np

RATE = 16000
CHUNK = 1280                # 80 ms, what pw-record delivers per read
PRE_ROLL_S = 1.6            # audio before the wake word that the command keeps
VAD_FRAME = 640             # 40 ms; two per chunk
VAD_THRESHOLD = 0.45        # Silero speech probability
SILENCE_END_S = 0.56        # pause that ends a command (longest mid-command pause measured: 0.40 s;
                            # replaying every recording, 0.56 s cut nothing that 1.0 s kept)
SPECULATE_S = 0.24          # start transcribing after this much silence; used if the command did end
LIVE_TAIL_S = 0.32          # speech this close to the wake word = the command is already under way
MAX_COMMAND_S = 10.0

VOCAB = ("Hey Jarvis. Hey Friday. Orrin, Selene, AURUM, ARGENT, VERDIGRIS, STARK, MARK III, VIBRANIUM, Govee, Proton VPN, UW CS, workspace, monitor, Spotify, Claude, brighten, "
         "timer, lights, theme.")

# "Hey Jarvis" as whisper hears it from across the desk: "Hey Joris", "Hey Joe, visit",
# "Hey, Jockfuss", "A Jarvis", "Oh Jarvis", "Jarvis,".
_GREET = r"(?:hey|hay|hi|a|oh|ok|okay|yo|hello)"
_NAME = r"(?:jarvis|jarvi|jervis|javis|jarvus|joris|jarv\w*)"                          # alone
_FUZZY = rf"(?:{_NAME}|j\w{{2,6}}s|joe\W{{0,2}}(?:vis|fuss)\w*|john)"                 # after a greeting
# "Hey Friday" (FRIDAY's wake word): only after a real greeting, or alone with a comma ("Friday, switch to
# Jarvis"), because Friday is also a day he says all the time ("what's due on a Friday", "oh Friday's busy").
_FGREET = r"(?:hey|hay|hi|okay|ok|yo|hello)"
_FRIDAY = r"(?:friday|fri day|fryday|frida|fridey)"
WAKE_PREFIX = re.compile(rf"^\W*(?:(?:{_GREET}\W+)+{_FUZZY}|{_NAME}|(?:{_FGREET}\W+)+{_FRIDAY}|{_FRIDAY}(?=\s*,))\b\W*", re.I)


WAKE_INSIDE = re.compile(rf"\b(?:(?:{_GREET}\W+)+{_FUZZY}|(?:{_FGREET}\W+)+{_FRIDAY})\b\W*", re.I)


def strip_wake(text, anywhere=False):
    """'Hey Joe, visit volume up.' → 'volume up.'; just 'Hey Jarvis' → ''.
    Also cuts whatever came before a "hey Jarvis" in the first few words (the pre-roll
    can catch the end of something else); anywhere=True cuts up to the last one at all,
    for an interruption, whose pre-roll holds Jarvis's own voice."""
    t = text.strip()
    hits = list(WAKE_INSIDE.finditer(t))
    if hits:
        last = hits[-1] if anywhere else next((h for h in hits if len(t[:h.start()].split()) <= 6), None)
        if last:
            t = t[last.end():]
    for _ in range(3):              # "Hey Jarvis. Hey Jarvis, pause."
        m = WAKE_PREFIX.match(t)
        if not m:
            break
        t = t[m.end():]
    return t.strip()


_VOCAB_WORDS = [w for w in re.findall(r"[a-z]+", VOCAB.lower()) if w not in ("hey", "jarvis", "friday")]


def _echoes_prompt(text):
    """On noise, whisper can recite its prompt. Three prompt words in prompt order = an echo."""
    words = re.findall(r"[a-z]+", text.lower())
    pairs = set(zip(_VOCAB_WORDS, _VOCAB_WORDS[1:], _VOCAB_WORDS[2:]))
    if len(words) >= 3 and all(w in _VOCAB_WORDS for w in words):
        return True
    return any(t in pairs for t in zip(words, words[1:], words[2:])) or (
        len(words) == 1 and words[0] in _VOCAB_WORDS and words[0] not in ("timer", "lights", "theme", "spotify", "monitor", "claude", "brighten"))


# What base.en keeps getting wrong at the desk (jarvis.log, 2026-10-25), fixed after the
# fact: only in contexts where the misheard word can't be meant ("cloudy" weather is safe).
CORRECTIONS = [
    (r"\b(?:cloud|clouds|cloud's|clogged|clawed|claw|clod|clot|clawd|claud|clyde)\b(?=\s+(?:usage|use|limits?|plan|code|model|sonnet|haiku|opus)\b)", "Claude"),
    (r"\b(?:ask|tell|open|use)\s+(?:cloud|clogged|clawed|claw|clod)\b", lambda m: m.group(0).split()[0] + " Claude"),
    (r"\bhow much (?:more )?(?:cloud|clod|claw)\b", lambda m: m.group(0).rsplit(" ", 1)[0] + " Claude"),
    (r"\b(?:break|brake|bright|brite)(?:en|in|ing)?(?: in| up)? (?=(?:the |my )?(?:lights?|strip|leds?)\b)", "brighten "),
    (r"\bmake (it|them|the lights?|the strip) (?:break|brake|bright|brite)(?:er)?\b", r"make \1 brighter"),
    (r"^(?:bright|brighter|brite|break|brake)[.!]?$", "brighten the lights"),
    (r"\b(?:cmeo|cmo|cpo|cpu's|see pee you|c p u)\b(?=\s+(?:temp|temperature|usage|load))", "CPU"),
    (r"\bmy attempts\b", "my temps"),
]


def correct(text):
    """'how much cloud usage' → 'how much Claude usage'; 'break in the lights' → 'brighten the lights'."""
    t = text
    for pat, rep in CORRECTIONS:
        t = re.sub(pat, rep, t, flags=re.I)
    return t


class Endpointer:
    """Feed 80 ms chunks; tells when the command has ended.

    pre: chunks from just before the wake word. They prime the VAD and are kept
    (they hold the start of a one-breath command); speech right at the end of them
    means the command is already under way."""

    def __init__(self, vad, no_speech_s, pre=(), threshold=VAD_THRESHOLD, silence_s=SILENCE_END_S):
        self.vad = vad
        self.threshold = threshold
        self.silence_s = silence_s
        self.no_speech_s = no_speech_s
        self.frames, self.probs = [], []
        self.speech = False
        self.silent = 0.0
        self.elapsed = 0.0           # since the wake word
        self.first = self.last = None
        self.step = CHUNK / RATE
        vad.reset_states()
        pre = list(pre)[-int(PRE_ROLL_S * RATE / CHUNK):]
        tail = int(LIVE_TAIL_S * RATE / CHUNK)
        for i, c in enumerate(pre):
            p = self.prob(c)
            self.frames.append(c)
            if p > threshold and i >= len(pre) - tail:
                self.speech, self.first, self.last = True, len(self.frames) - 1, len(self.frames)
        self.n_pre = len(pre)

    def prob(self, chunk):
        return float(max(self.vad.predict(chunk[i:i + VAD_FRAME], VAD_FRAME)
                         for i in range(0, len(chunk) - VAD_FRAME + 1, VAD_FRAME)))

    def feed(self, chunk):
        """→ None while listening, else why it stopped: silence | no-speech | max-length."""
        self.frames.append(chunk)
        self.elapsed += self.step
        p = self.prob(chunk)
        self.probs.append(p)
        if p > self.threshold:
            if not self.speech:
                self.first = len(self.frames) - 1
            self.speech, self.silent, self.last = True, 0.0, len(self.frames)
            self.speech_end = time.monotonic()
        else:
            self.silent += self.step
        if self.speech and self.silent >= self.silence_s:
            return "silence"
        if not self.speech and self.elapsed >= self.no_speech_s:
            return "no-speech"
        if self.elapsed >= MAX_COMMAND_S + (0 if self.speech else self.no_speech_s):
            return "max-length"
        return None

    def audio(self):
        return np.concatenate(self.frames) if self.frames else np.zeros(0, np.int16)


class STT:
    """faster-whisper with Trevor's vocabulary. transcribe(float32 audio) → (text, info dict).

    speculate(audio) starts a transcription in the background while the endpointer is
    still waiting out the silence; if no more speech comes, that result is used
    (it differs only by trailing silence), which takes whisper's ~0.3 s off the wait."""

    def __init__(self, model):
        from concurrent.futures import ThreadPoolExecutor
        from faster_whisper import WhisperModel
        self.name = model
        self.model = WhisperModel(model, device="cpu", compute_type="int8")
        self.pool = ThreadPoolExecutor(max_workers=1)

    def speculate(self, audio):
        return self.pool.submit(self.transcribe, audio)

    def transcribe(self, audio):
        t0 = time.monotonic()
        segments, _ = self.model.transcribe(audio, language="en", beam_size=1, temperature=0,
                                            initial_prompt=VOCAB, without_timestamps=True,
                                            condition_on_previous_text=False, max_new_tokens=60)
        segments = list(segments)
        text = " ".join(s.text for s in segments).strip()
        info = {"ms": int((time.monotonic() - t0) * 1000),
                "logprob": round(min((s.avg_logprob for s in segments), default=0), 2),
                "no_speech": round(max((s.no_speech_prob for s in segments), default=0), 2)}
        # music / noise: whisper invents a line ("and we'll be right back") with low confidence
        if text and info["no_speech"] > 0.6 and info["logprob"] < -0.9:
            info["dropped"] = text
            text = ""
        if _echoes_prompt(text):
            info["dropped"] = text      # echoed the prompt back ("STARK, VIBRANIUM, Govee, …")
            text = ""
        return text, info
