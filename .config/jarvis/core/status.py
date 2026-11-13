"""
Jarvis's state for the HUD's desktop widgets: $XDG_RUNTIME_DIR/jarvis/status.json.

The voice process keeps it current; quickshell OrrinFeed.qml reads it with a FileView that
watches the file (inotify), so nothing polls. Written only when something changed, coalesced
(at most one write per 0.4 s), atomically (tmp + rename).

  {"pid", "started", "updated",
   "mic":   {"setting", "node", "label"},                     the wake-word microphone (jarvis.py Mic)
   "last":  {"text", "reply", "tier", "source", "ts"},        the last command
   "tasks": [{"id", "title", "status", "steps", "max_steps", "now", "waiting", "started", "finished"}],
   "usage": {"session": usage_since(started), "today": usage_since(midnight),
             "plan": {"five_hour": {"pct", "resets_at"}, "seven_day": {…}, "at"}}}   (plan only if Claude reported it)

Listening / thinking / speaking aren't in here: the HUD already has them (OrrinState, IPC).
"""
import datetime as _dt
import json
import os
import threading
import time

import jarvis_db as db

from . import config as C

PATH = C.RUNTIME / "jarvis" / "status.json"
DELAY = 0.4


class Status:
    def __init__(self, log=print):
        self.log = log
        self.started = time.time()
        self.data = {"pid": os.getpid(), "started": self.started, "mic": {}, "last": {}, "tasks": [], "usage": {}}
        self._lock = threading.Lock()
        self._dirty = threading.Event()
        threading.Thread(target=self._writer, daemon=True).start()

    def set(self, key, value):
        with self._lock:
            if self.data.get(key) == value:
                return
            self.data[key] = value
        self._dirty.set()

    # ── pieces ──
    def mic(self, setting, node, label):
        self.set("mic", {"setting": setting, "node": node, "label": label})

    def last(self, text, reply, tier, source):
        self.set("last", {"text": str(text or "")[:200], "reply": str(reply or "")[:300], "tier": tier or "",
                          "source": source or "", "ts": time.time()})

    def tasks(self, items):
        keep = ("id", "title", "status", "steps", "max_steps", "now", "waiting", "started", "finished", "created")
        live = [t for t in items if t.get("status") in ("running", "queued")]
        done = [t for t in items if t.get("status") not in ("running", "queued")][:3]
        self.set("tasks", [{k: t.get(k) for k in keep} for t in live + done])

    def usage(self, brain=None):
        midnight = _dt.datetime.combine(_dt.date.today(), _dt.time()).timestamp()
        u = {"session": db.usage_since(self.started), "today": db.usage_since(midnight)}
        windows = getattr(brain, "usage", None) or {}
        plan = {}
        for k in ("five_hour", "seven_day"):
            w = windows.get(k) or {}
            if w.get("utilization") is not None:
                plan[k] = {"pct": round(float(w["utilization"]) * 100, 1), "resets_at": w.get("resetsAt")}
        if plan:
            plan["at"] = getattr(brain, "usage_at", 0) or 0
            u["plan"] = plan
        self.set("usage", u)

    # ── file ──
    def _writer(self):
        while True:
            self._dirty.wait()
            time.sleep(DELAY)
            self._dirty.clear()
            with self._lock:
                self.data["updated"] = time.time()
                text = json.dumps(self.data, ensure_ascii=False)
            try:
                PATH.parent.mkdir(parents=True, exist_ok=True)
                tmp = PATH.with_suffix(".tmp")
                tmp.write_text(text)
                tmp.replace(PATH)
            except OSError as e:
                self.log(f"JARVIS: status file: {e}")

    def close(self):
        try:
            PATH.unlink()
        except OSError:
            pass
