"""Per-word training settings: words/_common.yml under words/<word>.yml (the word wins), with {W} filled in.
hey_friday (the first run) keeps its own flat hey_friday.yml next to this file."""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
W = Path(os.environ.get("WAKE_TRAIN_DIR", Path.home() / ".local/share/jarvis/wake-train"))
WORDS = ["hey_orrin", "hey_selene"]          # what pipeline.py trains, in order


def load(word):
    import yaml
    if word == "hey_friday":
        cfg = yaml.safe_load((HERE / "hey_friday.yml").read_text())
        cfg.setdefault("persona", "friday")
        cfg.setdefault("positive_texts", ["hey friday", "hey friday", "hey friday", "hey, friday",
                                          "hey friday!", "hey friday?", "hey friday."])
        for k, v in {"n_positive_train": cfg["n_samples"], "n_negative_train": cfg["n_samples"],
                     "n_positive_test": cfg["n_samples_val"], "n_negative_test": cfg["n_samples_val"]}.items():
            cfg.setdefault(k, v)
    else:
        cfg = yaml.safe_load((HERE / "words/_common.yml").read_text())
        cfg.update(yaml.safe_load((HERE / f"words/{word}.yml").read_text()))
    return _fill(cfg)


def _fill(v):
    if isinstance(v, str):
        return v.replace("{W}", str(W))
    if isinstance(v, list):
        return [_fill(x) for x in v]
    if isinstance(v, dict):
        return {k: _fill(x) for k, x in v.items()}
    return v


def write_train_yml(word):
    """The config openWakeWord's train.py reads → $W/out/<word>.yml."""
    import yaml
    out = W / "out" / f"{word}.yml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(load(word), sort_keys=False))
    return out
