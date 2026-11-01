#!/usr/bin/python3
"""The visible text of one window through AT-SPI (accessibility), as JSON on stdout.

    /usr/bin/python3 -I atspi_text.py PID TITLE    → {"ok": true, "text": "...", "nodes": N} | {"ok": false, "error": "..."}

Runs under the system python (PyGObject + Atspi live there, not in Jarvis's venv); core/screen.py calls it
with a timeout. Only the application with that pid, only its frame with that title (or its only frame),
only nodes that are showing. Password fields are never read. Nothing is written anywhere.
"""
import json
import sys
import time

MAX_NODES = 4000
MAX_CHARS = 12000
DEADLINE_S = 4.0


def main(pid, title):
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi

    R = Atspi.Role
    skip_roles = {R.PASSWORD_TEXT}
    label_roles = {R.LABEL, R.HEADING, R.PUSH_BUTTON, R.LINK, R.MENU_ITEM, R.PAGE_TAB, R.STATIC, R.LIST_ITEM,
                   R.TABLE_CELL, R.CHECK_BOX, R.RADIO_BUTTON, R.TOGGLE_BUTTON, R.STATUS_BAR}
    end = time.monotonic() + DEADLINE_S
    desk = Atspi.get_desktop(0)
    apps = []
    for i in range(desk.get_child_count()):
        a = desk.get_child_at_index(i)
        try:
            if a is not None and a.get_process_id() == pid:
                apps.append(a)
        except Exception:
            continue
    if not apps:
        return {"ok": False, "error": "this app exposes no accessibility tree"}
    frames = []
    for a in apps:
        for i in range(a.get_child_count()):
            f = a.get_child_at_index(i)
            if f is not None:
                frames.append(f)
    if not frames:
        return {"ok": False, "error": "no windows in its accessibility tree"}
    want = [f for f in frames if (f.get_name() or "").strip() == title.strip()]
    if not want and len(frames) == 1:
        want = frames
    if not want:
        want = [f for f in frames if title and (f.get_name() or "") and (f.get_name() in title or title in f.get_name())]
    if len(want) != 1:
        return {"ok": False, "error": "couldn't tell which of its windows that is"}

    out, seen, n = [], set(), 0
    stack = [want[0]]
    while stack and n < MAX_NODES and time.monotonic() < end and sum(map(len, out)) < MAX_CHARS:
        node = stack.pop()
        n += 1
        try:
            states = node.get_state_set()
            if not states.contains(Atspi.StateType.SHOWING):
                continue
            role = node.get_role()
            if role in skip_roles:
                continue
            text = ""
            iface = node.get_text_iface() if hasattr(node, "get_text_iface") else None
            if iface is not None and role not in label_roles:
                text = Atspi.Text.get_text(node, 0, min(Atspi.Text.get_character_count(node), 4000)) or ""
            elif role in label_roles:
                text = node.get_name() or ""
            text = " ".join(text.replace("\ufffc", " ").split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
            kids = [node.get_child_at_index(i) for i in range(min(node.get_child_count(), 500))]
            stack.extend(k for k in reversed(kids) if k is not None)
        except Exception:
            continue
    return {"ok": True, "text": "\n".join(out)[:MAX_CHARS], "nodes": n}


if __name__ == "__main__":
    try:
        r = main(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "")
    except Exception as e:
        r = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    print(json.dumps(r, ensure_ascii=False))
