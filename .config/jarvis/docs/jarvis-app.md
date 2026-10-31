# Jarvis upgrade: tracker, app, window reading, window control

Four stages, built and committed one at a time. Every existing rule still holds: other people's
content goes back to the model fenced by `integration_common.untrusted()`, the gate in
`core/brain.py` asks for a spoken yes after any integration read, combat mode pauses Jarvis,
and the voice loop only runs docked.

## Stage 1: SE academic tracker (Google Sheet)

**The sheet.** "SE Academic Tracker - Trevor" (`1EZU-cPfQZ4UflUBUXrFVN2egPgQJUlmd9ZKqE_C6u2s`, his
own; the "- Public" copy is someone else's template and is never used). The ID lives in the keyring
(`jarvis:google` / `tracker_sheet`), set by `jarvis tracker find`.

| tab | role | Jarvis |
|---|---|---|
| Assignment Tracker | header row 3: Course, Assignment, Due Date, Days, Difficulty, Type, Status, Grade; data from row 4, sorted by due date, rows without a date last. Validation lists on Course / Type / Status. Rows 1-2 are COUNTIFS summaries. | reads and writes plain values in data rows only |
| Grades Tracker | per-course columns spilled by FILTER/VSTACK from Assignment Tracker's Grade column + Weights | read only (never written: it is formulas) |
| Weights | course weights, "TYPE EXAM MARKS HERE" column, auto bucket grade | read only |

So the one place a grade goes is Assignment Tracker column H (a number out of 100; the
conditional formats colour it at 90/80/70).

**Access.** New scope `spreadsheets` (Google has no per-file Sheets scope that covers an existing
file). It is held to that one file in code: `google_api.service("sheets")` builds the client with a
request builder that refuses any request whose URL names another spreadsheet, so no caller (and no
model argument) can reach a different sheet. `jarvis connect google` and Settings report the
missing scope and say to reconnect. The Sheets API also has to be enabled in the Cloud project.

**Writes** (`mcp/tracker.py`, one choke point):
- only `valueInputOption=RAW` values (a string starting with `=` stays text; dates are serial
  numbers so the cell keeps its own date format), only into data rows, only into Course,
  Assignment, Due Date, Type, Status, Grade;
- the target cell is read with `FORMULA` rendering first and the write is refused if it holds a
  formula; the row's course + assignment are re-read just before writing, so a row he moved or
  edited meanwhile is never overwritten by position;
- new rows are inserted at their due-date position with `inheritFromBefore`, which carries the
  row's formatting, validation and conditional formats; nothing else structural, never Apps Script;
- every write is logged in jarvis_db `tracker_log` (cell, old → new, source, batch);
  `jarvis tracker undo` reverts the last batch if the cells still hold what Jarvis wrote.

**Events** (`academic_sync.tracker_pass`, no model involved):
- grade notice (existing header-only recogniser) → Status Complete, and Grade if Gmail's snippet
  states a score ("18/20", "85%"); the body is still never fetched;
- LEARN feed assignment with no matching row → new row (Course, Assignment, Due Date, Type
  Assignment, Status Not Started); course email whose subject announces a new assignment from a
  course / LEARN sender → same;
- LEARN due change, or a course email subject announcing an extension → Due Date.

Matching a LEARN item to a row: same course, then the same assignment number + kind ("A5",
"W3", "Tutorial 4"), else close title words. Anything ambiguous is offered, never applied.

**AUTO-UPDATE TRACKER** (Settings → JARVIS, `jarvisAutoUpdateTracker`): off = each event becomes an
offer the voice loop asks out loud + on the HUD when idle; on = applied and announced. Voice edits
("mark CS 137 A5 done") are integration writes, so the gate always asks. Reads: `tracker_pending`
("what haven't I finished this week?"), `tracker_grade` ("what did I get on MATH 135 A6?").
With the tracker configured, "STARK – Assignments" is no longer written (his sheet already syncs to
Google Calendar); it stays as the fallback when the tracker isn't set up.

## Stage 2: JARVIS app (Quickshell)

- `JarvisApp.qml`: a holographic console (Theme colours, HudFrame), Super+J toggles it on the
  focused monitor (bind in `hypr/stark/binds.lua`, IPC `jarvis app`).
- Conversations: `threads` + `messages` tables in jarvis_db. Every turn (voice or typed) lands in
  the current thread; a request that runs tools or more than one turn starts its own thread,
  titled by the fast model. FTS search; resuming a thread replays a short summary into Claude.
- Typed input goes through the same `Jarvis.handle()` path (fast path → local router → Claude), via
  a Unix socket the voice process owns (`$XDG_RUNTIME_DIR/jarvis.sock`, mode 0600, same user
  only; it is a local IPC socket, not a network listener). Replies show text + tool actions.
- Tasks: background Agent SDK sessions (`core/tasks.py`) with the same MCP servers and the same
  gate (confirmations go to the HUD + voice). `tasks` table holds status, steps and log; max 2
  running; cancel from the panel. On start, running tasks are marked interrupted and offered
  for resume. Completion: voice + toast, linked to its thread. A Claude-turns-today counter
  (from `action_log` + tasks) sits in the header.

**Built (stage 2):** Super+J was free (no hyprland.conf any more; nothing in stark/binds.lua bound J).
The socket is `$XDG_RUNTIME_DIR/jarvis/app.sock` (0600 in a 0700 dir, peer uid checked). Thread titles
come from the first request (no extra Claude turn). Typed requests answer confirmations in the app
only; task confirmations show in the app and are asked aloud when idle, first answer wins, 10 min
timeout = no. While Jarvis is off, the app reads history through `jarvis app-data`. Combat mode:
no new task starts and nothing is asked aloud; running tasks continue.

**UI polish (after stage 2):**
- Pop-up (JarvisToast): projected text on a blurred glass plate (no hard border), glowing text, faint
  scanlines, an occasional flicker, a projector line; fades in and out. The whole reply, always:
  `core/hud.py` no longer cuts arguments at 600 characters, and a long reply scrolls inside (max 40 % of
  the screen). Karaoke: `Utterance` reports each sentence as it starts playing (`hud.speak(start, end,
  total, ms)`, `speechDone`), the pop-up lights the sentence being said, marks its line and keeps it in
  view; the mouse wheel scrolls by hand and pauses that. Unspoken replies scroll at reading pace. It
  stays while he speaks or the pointer is on it, then 3.5-12 s by length; hidden while the console is
  open on that monitor. A click opens the console on the active thread, on that monitor.
- Threads: a thread lasts 30 min of quiet (`THREAD_IDLE_S`); Claude's own context still drops after
  3 min, and carrying on replays the thread's last turns. "new topic" / "new chat" / NEW THREAD start a
  new one. After a restart the live thread is picked up again. A background task's messages never make
  its thread current. The console marks the active thread (lit edge, "● ACTIVE", header badge).
- Tasks: each card shows its state (RUNNING / QUEUED / NEEDS YOUR YES / DONE …), a progress bar
  (steps of the 40-step budget), the current step in plain words, elapsed time, and YES / NO inline when
  it's waiting. HELP (always shown with no tasks) explains what a task is and how to start one.
- Console: fades in/out, stays on the monitor it opened on, focus in the input on open and after
  thread / NEW / RESUME clicks; the message list follows new messages only while at the bottom
  ("▼ LATEST" otherwise) and shows a scroll bar.

## Between stages 2 and 3: calendar editing

**How his sheet syncs** (his Apps Script, confirmed): an installable "From spreadsheet – On edit"
trigger runs `handleEdit`, which on a Status (column G) edit looks on the row's due date
(`getEventsForDay`) for `[COURSE] Title` / `✓ [COURSE] Title` and sets title, colour (Complete green 10,
In progress yellow 5, else Assessment mauve 3 / red 11) and description (`Course / Type / Status`, the
status lower-cased with the first letter capitalised). The "📅 Calendar Sync → Sync All" menu does the
same for every row. It never creates, moves or deletes an event, and edit triggers never fire for API
writes, so Jarvis keeps the events in step itself (`mcp/sheet_calendar.py`), in exactly that format.

**Scope.** `calendar.events` (`calendar_scopes` in servers.json); `jarvis connect google` and Settings
report it missing. Writes go through `google_api.CalendarWriter` only: main calendar (plus Jarvis's own
STARK – Assignments, for cleanup), subscribed / view-only calendars refused with a spoken reason,
every write logged in jarvis_db `calendar_log`, `jarvis calendar log | undo`.

**Tools** (google server, no longer read-only; mail and Drive still have no write tools):
`calendar_find` (read: events with a `ref`, editable or why not), `calendar_create_event`,
`calendar_update_event`, `calendar_delete_event`. `core/brain.ALWAYS_ASK` makes these, `tracker_update`,
`tracker_add` and `tracker_remove` ask every time, whatever auto_write and the AUTO settings say.

**Tracker → calendar.** `Tracker.apply(..., calendar=True)` (the tools and accepted offers) brings each
touched row's event in line: matched by title, never by date, so a moved row's event moves; a new row
gets one; a removed row's event is deleted; a second copy is only reported. Colour and status text follow the
script's rules; a new event takes the reminders the existing ones use. AUTO-UPDATE TRACKER still writes only
the sheet, then offers "Shall I bring its calendar event in line too?". `jarvis tracker undo` also
reverts the calendar batch linked to it. `tracker_remove` deletes one row (never one holding a formula).

**LEARN merge fix.** `academic.dedupe`: an "… – Available" entry never overrides a real deadline with the
same key (it had put CHE 102 A3–A6 at the next morning's review time).

**Console.** Clicking the JARVIS pop-up (JarvisToast) opens the console on that monitor.

## Stage 3: Window reading + watchers

- Capture a named window only: resolve "this window" (focused), "the Discord window" (class /
  title), "monitor 2" through `hyprctl clients/monitors -j`, then capture with Hyprland's
  `hyprland_toplevel_export_v1` (works for hidden windows), falling back to wlr-screencopy of the
  window's geometry (grim). Both via a small pure-Python Wayland client like `memory/vptr.py`;
  frames stay in memory, never on disk.
- Text first: kitty's own text (`kitty @ get-text`, if remote control is on), then AT-SPI, then
  the image to Claude (fenced as untrusted screen content).
- Watchers (`core/watch.py`): every N s (default 10) capture → perceptual hash + changed-region
  area, ignore regions (clock, cursor) → only over threshold does Claude judge "does this match
  what he asked for?". Max 3, 2 h expiry, paused in combat mode, listed in the app with
  pause/stop.
- Hard exclusions: hyprlock / lock screen, polkit and password dialogs, and a title blocklist
  (`jarvisCaptureBlocklist`: bank, password manager, …). Screen text can't trigger an action.
- Setup: `grim` is not installed (`sudo pacman -S grim`); Hyprland's screencopy permission
  settings may need an allow rule for Jarvis's python.

## Stage 4: Interacting with windows

- Keyboard: `zwp_virtual_keyboard_v1` (wtype, `sudo pacman -S wtype`). Pointer:
  `zwlr_virtual_pointer_v1`, the pure-Python client already proven on this Hyprland
  (`memory/vptr.py`). Neither needs the uinput group or a root daemon (ydotool would).
- Only the window named in that request; the plan is shown on the HUD and needs a yes; "allow
  this task" covers that one task. A glowing border (Quickshell overlay on the window's geometry)
  while Jarvis has control; a kill bind (Super+Shift+Escape, free in binds.lua) and "stop" end it.
- Refused with a spoken reason: password fields (AT-SPI role), blocklisted windows, payments,
  sending messages or email, deleting files, system settings, anything an on-screen text asks for.
- After every action: re-capture and compare against the expected result; stop and ask if not.
- Tested only against a throwaway kitty / test page.
