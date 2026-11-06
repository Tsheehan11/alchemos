"""
Pluggable TTS engines. Each engine is a module in this folder defining ENGINE = <an Engine subclass>; every
module here is discovered at first use, so a new local model is one file and nothing else in the voice
pipeline changes (speech normalizing, effects, loudness, caching, streaming and the piper fallback all stay
in core/voice.py and work for any engine).

  Voice names → engine: an engine claims plain names it recognises (handles(): Kokoro "bm_george",
  piper "en_GB-alan-medium" / "model:speaker"); any engine also answers to "<id>/<voice>"
  ("f5/narrator"), so new engines never clash with the old names. Settings lists every engine's voices.

Writing one (core/tts/myengine.py):

    from . import Engine

    class MyEngine(Engine):
        id = "myengine"             # also the "<id>/" prefix of its voice names
        priority = 50               # lower is asked first in handles()
        def available(self): ...    # installed / model on disk?
        def voices(self): ...       # names it can speak (without the prefix)
        def synth(self, voice, text, speed): ...   # → (float32 mono numpy array, sample rate)
        def cache_tag(self): ...    # changes when the model changes (it keys the on-disk cache)

    ENGINE = MyEngine

synth() runs on the voice loop's render threads: load the model lazily, once, under a lock.
"""
import importlib
import pkgutil
import threading


class Engine:
    id = ""
    priority = 100
    female = ()                    # names to list under FRIDAY's voices in Settings (the rest go under both)

    def available(self):
        return True

    def handles(self, voice):
        """A plain voice name this engine recognises (without the "<id>/" prefix)."""
        return False

    def voices(self):
        return []

    def synth(self, voice, text, speed):
        raise NotImplementedError

    def cache_tag(self):
        return self.id


_lock = threading.Lock()
_engines = None


def engines():
    """Every engine found in this package, by priority."""
    global _engines
    with _lock:
        if _engines is None:
            found = []
            for m in pkgutil.iter_modules(__path__):
                if m.name.startswith("_"):
                    continue
                try:
                    mod = importlib.import_module(f"{__name__}.{m.name}")
                except Exception:        # a broken engine module must not take the voice down
                    continue
                cls = getattr(mod, "ENGINE", None)
                if isinstance(cls, type) and issubclass(cls, Engine):
                    found.append(cls())
            _engines = sorted(found, key=lambda e: (e.priority, e.id))
        return _engines


def register(engine):
    """Add an engine at run time (tests, experiments); it's asked first."""
    engines()
    with _lock:
        _engines.insert(0, engine)


def unregister(engine_id):
    with _lock:
        if _engines is not None:
            _engines[:] = [e for e in _engines if e.id != engine_id]


def resolve(name):
    """A voice name → (engine, the engine's own voice name), or (None, name)."""
    name = name or ""
    if "/" in name:
        eid, _, voice = name.partition("/")
        for e in engines():
            if e.id == eid:
                return e, voice
    for e in engines():
        if e.handles(name):
            return e, name
    return None, name


def synth(name, text, speed):
    """Speak `text` in voice `name` → (float32 audio, sample rate). LookupError if no engine has it."""
    e, voice = resolve(name)
    if e is None:
        raise LookupError(f"no TTS engine for voice {name!r}")
    return e.synth(voice, text, speed)


def cache_tag(name):
    e, _ = resolve(name)
    return e.cache_tag() if e else ""


def all_voices():
    """{engine id: [full voice names]} for every available engine (prefixless for the built-in ones)."""
    out = {}
    for e in engines():
        try:
            if not e.available():
                continue
            vs = e.voices()
        except Exception:
            continue
        out[e.id] = [v if e.handles(v) else f"{e.id}/{v}" for v in vs]
    return out
