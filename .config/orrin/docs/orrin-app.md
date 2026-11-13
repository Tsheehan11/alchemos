# Orrin upgrade: tracker, app, window reading, window control (all four stages built)

Four stages, built and committed one at a time. Every existing rule still holds: other people's
content goes back to the model fenced by `integration_common.untrusted()`, the gate in
`core/brain.py` asks for a spoken yes after any integration read, combat mode pauses Orrin,
and the voice loop only runs docked.

## Stage 1: SE academic tracker (Google Sheet)

**The sheet.** "SE Academic Tracker - Trevor" (`1EZU-cPfQZ4UflUBUXrFVN2egPgQJUlmd9ZKqE_C6u2s`, his
own; the "- Public" copy is someone else's template and is never used). The ID lives in the keyring
(`orrin:google` / `tracker_sheet`), set by `orrin tracker find`.

| tab | role | Orrin |
|---|---|---|
| Assignment Tracker | header row 3: Course, Assignment, Due Date, Days, Difficulty, Type, Status, Grade; data from row 4, sorted by due date, rows without a date last. Validation lists on Course / Type / Status. Rows 1-2 are COUNTIFS summaries. | reads and writes plain values in data rows only |
| Grades Tracker | per-course columns spilled by FILTER/VSTACK from Assignment Tracker's Grade column + Weights | read only (never written: it is formulas) |
| Weights | course weights, "TYPE EXAM MARKS HERE" column, auto bucket grade | read only |

So the one place a grade goes is Assignment Tracker column H (a number out of 100; the
conditional formats colour it at 90/80/70).

**Access.** New scope `spreadsheets` (Google has no per-file Sheets scope that covers an existing
file). It is held to that one file in code: `google_api.service("sheets")` builds the client with a
request builder that refuses any request whose URL names another spreadsheet, so no caller (and no
model argument) can reach a different sheet. `orrin connect google` and Settings report the
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
- every write is logged in orrin_db `tracker_log` (cell, old → new, source, batch);
  `orrin tracker undo` reverts the last batch if the cells still hold what Orrin wrote.

**Events** (`academic_sync.tracker_pass`, no model involved):
- grade notice (existing header-only recogniser) → Status Complete, and Grade if Gmail's snippet
  states a score ("18/20", "85%"); the body is still never fetched;
- LEARN feed assignment with no matching row → new row (Course, Assignment, Due Date, Type
  Assignment, Status Not Started); course email whose subject announces a new assignment from a
  course / LEARN sender → same;
- LEARN due change, or a course email subject announcing an extension → Due Date.

Matching a LEARN item to a row: same course, then the same assignment number + kind ("A5",
"W3", "Tutorial 4"), else close title words. Anything ambiguous is offered, never applied.

**AUTO-UPDATE TRACKER** (Settings → ORRIN, `orrinAutoUpdateTracker`): off = each event becomes an
offer the voice loop asks out loud + on the HUD when idle; on = applied and announced. Voice edits
("mark CS 137 A5 done") are integration writes, so the gate always asks. Reads: `tracker_pending`
("what haven't I finished this week?"), `tracker_grade` ("what did I get on MATH 135 A6?").
With the tracker configured, "STARK – Assignments" is no longer written (his sheet already syncs to
Google Calendar); it stays as the fallback when the tracker isn't set up.

## Stage 2: ORRIN app (Quickshell)

- `OrrinApp.qml`: a holographic console (Theme colours, HudFrame), Super+J toggles it on the
  focused monitor (bind in `hypr/alchemos/binds.lua`, IPC `orrin app`).
- Conversations: `threads` + `messages` tables in orrin_db. Every turn (voice or typed) lands in
  the current thread; a request that runs tools or more than one turn starts its own thread,
  titled by the fast model. FTS search; resuming a thread replays a short summary into Claude.
- Typed input goes through the same `Orrin.handle()` path (fast path → local router → Claude), via
  a Unix socket the voice process owns (`$XDG_RUNTIME_DIR/orrin.sock`, mode 0600, same user
  only; it is a local IPC socket, not a network listener). Replies show text + tool actions.
- Tasks: background Agent SDK sessions (`core/tasks.py`) with the same MCP servers and the same
  gate (confirmations go to the HUD + voice). `tasks` table holds status, steps and log; max 2
  running; cancel from the panel. On start, running tasks are marked interrupted and offered
  for resume. Completion: voice + toast, linked to its thread. A Claude-turns-today counter
  (from `action_log` + tasks) sits in the header.

**Built (stage 2):** Super+J was free (no hyprland.conf any more; nothing in alchemos/binds.lua bound J).
The socket is `$XDG_RUNTIME_DIR/orrin/app.sock` (0600 in a 0700 dir, peer uid checked). Thread titles
come from the first request (no extra Claude turn). Typed requests answer confirmations in the app
only; task confirmations show in the app and are asked aloud when idle, first answer wins, 10 min
timeout = no. While Orrin is off, the app reads history through `orrin app-data`. Combat mode:
no new task starts and nothing is asked aloud; running tasks continue.

**UI polish (after stage 2):**
- Pop-up (OrrinToast): projected text on a blurred glass plate (no hard border), glowing text, faint
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
writes, so Orrin keeps the events in step itself (`mcp/sheet_calendar.py`), in exactly that format.

**Scope.** `calendar.events` (`calendar_scopes` in servers.json); `orrin connect google` and Settings
report it missing. Writes go through `google_api.CalendarWriter` only: main calendar (plus Orrin's own
STARK – Assignments, for cleanup), subscribed / view-only calendars refused with a spoken reason,
every write logged in orrin_db `calendar_log`, `orrin calendar log | undo`.

**Tools** (google server, no longer read-only; mail and Drive still have no write tools):
`calendar_find` (read: events with a `ref`, editable or why not), `calendar_create_event`,
`calendar_update_event`, `calendar_delete_event`. `core/brain.ALWAYS_ASK` makes these, `tracker_update`,
`tracker_add` and `tracker_remove` ask every time, whatever auto_write and the AUTO settings say.

**Tracker → calendar.** `Tracker.apply(..., calendar=True)` (the tools and accepted offers) brings each
touched row's event in line: matched by title, never by date, so a moved row's event moves; a new row
gets one; a removed row's event is deleted; a second copy is only reported. Colour and status text follow the
script's rules; a new event takes the reminders the existing ones use. AUTO-UPDATE TRACKER still writes only
the sheet, then offers "Shall I bring its calendar event in line too?". `orrin tracker undo` also
reverts the calendar batch linked to it. `tracker_remove` deletes one row (never one holding a formula).

**LEARN merge fix.** `academic.dedupe`: an "… – Available" entry never overrides a real deadline with the
same key (it had put CHE 102 A3–A6 at the next morning's review time).

**Console.** Clicking the ORRIN pop-up (OrrinToast) opens the console on that monitor.

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
  (`orrinCaptureBlocklist`: bank, password manager, …). Screen text can't trigger an action.
- Setup: grim and wtype are installed (2026-10-31).

**Built (stage 3):**
- Capture: `core/wlcap.py` speaks `hyprland_toplevel_export_manager_v1` directly (stdlib socket + memfd
  `wl_shm` buffer, ~50 ms, works on covered windows and special workspaces); the handle is the low 32 bits
  of the hyprctl address. Fallback: `grim -t ppm … -` on the visible geometry (a pipe, never a file).
  Monitors: `grim -o`, with every never-read window on it blacked out. `ecosystem:enforce_permissions` is
  off here, so no permission rule was needed.
- Naming (`core/screen.resolve`): "this window" / "" = focused; app or title words; "monitor N" counts
  left to right; "laptop screen", "left monitor", "this screen", connector names. Two matches → he is asked
  which (the focused one wins if it's among them); never a guess.
- Never read: hyprlock running (nothing at all), polkit / pinentry / keyring / askpass prompts, password
  managers, titles matching "password", and `orrinCaptureBlocklist` (Settings → ORRIN → WINDOW READING,
  whole-word match on class + title). Re-checked on every capture, so a watched tab that turns into a bank
  page is skipped.
- Text first: kitty's own text (see "kitty remote control" below), then AT-SPI through `mcp/atspi_text.py` (system python; showing nodes only, password fields never read),
  else a PNG (≤1568 px) as an MCP image. All results go back fenced by `untrusted()`.
- Tools: `mcp/screen_tools.py` (server "screen", policy "screen" in servers.json): `read_window`,
  `list_windows` (reads: they taint the request, so any later action needs his yes), `watch_window`,
  `watch_list`, `watch_stop`, `watch_pause`. Local router: `claude.screen` (claude-only), and `open_app` /
  `widget.list` refuse reading words ("read the discord window" used to open Discord).
- Watchers (`core/watch.py`, `watchers` table, run by the voice process): thumbnails of 8 px cells,
  changed-cell count vs a baseline (≥6 cells and ≥0.05 %), cells that flicker on their own learned as noise,
  a small change rejected twice in the same place learned as noise (minute clocks); windows with text compare
  new lines instead (no Claude call when only pixels moved). Claude (haiku, no tools, no MCP) is asked only
  once the picture settles (or after 60 s of change), at least 20 s apart, doubling to 5 min while nothing
  matches, at most 40 per watcher; turns count under source "watch" (console header: WATCHERS n). A match
  speaks one cleaned sentence ("Sir, the build finished…") and ends the watcher unless keep_watching. Window
  closed / expired → said once. Paused in combat mode; not running while undocked (voice process). Console:
  WATCHERS cards with state, countdown, Claude looks, PAUSE / STOP.

**kitty remote control (after stage 3).** kitty.conf: `allow_remote_control password`, `listen_on
unix:${XDG_RUNTIME_DIR}/kitty-rc-{kitty_pid}` (a socket file in the 0700 runtime dir; abstract `@` sockets are
never used, anyone could connect to or squat one), `geninclude orrin-rc-password.sh`, which prints
`remote_control_password "<pw>" orrin-rc-check.py` from the keyring (`orrin:kitty` / `rc_password`, via
secret-tool), so the password is in no file. `orrin-rc-check.py` allows `get-text` over the socket only:
send-text, launch, ls, set-* … and anything sent as escape codes through a terminal (a program in the window,
a remote host over ssh) are refused. A request without a password is refused. A request with an unknown
password makes kitty ask in a dialog ("A program wishes to control kitty", default ALLOW REQUEST): that is
kitty's built-in behaviour and can't be configured away; the answer is DENY PASSWORD. kitty encrypts password
requests with the target instance's public key, which it only gives its children, so Orrin reads
KITTY_PUBLIC_KEY from that kitty's child in /proc and passes it and the password in the environment, never
argv. `listen_on` is read only at start: kittys opened before this have no socket (they fall back to a
picture). `orrin kitty-rc status | setup | rotate`.

**Task announcement fix (stage 3 prelude).** The silent run was task 10 (21:30): queued during combat mode
(on since 21:27), so the runner never started it and nothing said why; it was cancelled at 21:31. Tasks 8
and 9 got the generic line because their naming turn returned nothing (the naming turn now works live).
Also found: an announcement waiting out combat mode sat in an in-memory queue and was lost on a restart.
Now the line is stored on the task (`tasks.announce`, `announced`), `core.tasks.Announcer` says it when the
voice loop is free (deferred in combat mode, survives restarts, "While I was away, sir: …" after 2 min,
retried 3× if speech fails, older than 12 h left in the console), wrap-up errors still owe the generic
line, an interrupted task is announced too, and a task queued in combat mode logs why it waits.

**Checked on Hyprland 0.57.0 (2026-11-02, before stage 4).** 70c8f07 + 3d20abb + the hotplug gate (8f5d6a8,
e2c1b4a) on main and pushed; all suites and the router eval (0 wrong at 0.70) pass. Live on dummies: kitty read
through its own text, GTK through AT-SPI, toplevel export from a hidden special workspace, one watcher end to end
(one Claude look, match spoken, SEEN), the console card with PAUSE / STOP and "TURNS TODAY n (WATCHERS n)". Found
and fixed: (1) 0.57 gives special workspaces no id (clients, monitors and workspaces only have address / type /
name), which broke every monitor read while any window sat on a special workspace (Spotify's special:music) and the
grim fallback's visibility check: workspaces are now compared by name (`screen.ws_name` / `shown_on`); (2) with
Orrin off, the console never loaded the turn counts (`app-data usage`), so the header always read 0. The settle
gate still refuses captures while its flag is fresh. Nested repro of the mirror-source unplug on 0.57.0: 6/6 unplugs
re-homed the workspace to the remaining screen (no "monitor -1"), every capture worked, no crash. The gate stays.

## Stage 4: Interacting with windows

- Keyboard: `zwp_virtual_keyboard_v1` (wtype, `sudo pacman -S wtype`). Pointer:
  `zwlr_virtual_pointer_v1`, the pure-Python client already proven on this Hyprland
  (`memory/vptr.py`). Neither needs the uinput group or a root daemon (ydotool would).
- Only the window named in that request; the plan is shown on the HUD and needs a yes; "allow
  this task" covers that one task. A glowing border (Quickshell overlay on the window's geometry)
  while Orrin has control; a kill bind (Super+Shift+Escape, free in binds.lua) and "stop" end it.
- Refused with a spoken reason: password fields (AT-SPI role), blocklisted windows, payments,
  sending messages or email, deleting files, system settings, anything an on-screen text asks for.
- After every action: re-capture and compare against the expected result; stop and ask if not.
- Tested only against a throwaway kitty / test page.

**Built (stage 4):**
- Input. Keyboard: wtype (already installed), one key or ≤12 characters per call so the kill switch is checked
  between chunks; newlines and tabs are sent as Return / Tab keys. Pointer: `core/wlinput.py`, a
  `zwlr_virtual_pointer_v1` client on the same stdlib Wayland code as `core/wlcap.py` (absolute motion over the
  monitors' logical bounding box, buttons, wheel notches with `axis_discrete`); every move is checked with
  `hyprctl cursorpos`. No setup: no uinput group, no daemon, no ydotool. Proven on 0.57.0 at scale 1 and (nested) 1.625.
- Tools (`mcp/control_tools.py`, server "control", policy "control"): `control_look(target)` = the window as a
  picture + its clickable elements by name (AT-SPI `elements` mode in `mcp/atspi_text.py`, boxes in window
  coordinates, since Wayland gives no screen ones) + its text, fenced as untrusted; a read, so the request is tainted.
  `control_run(target, goal, steps, picture_size)`: ≤12 steps of click / double_click / right_click (by element
  name, or x / y in the look's picture), type, key ("ctrl+t"), scroll, wait, each with the screen it expects after.
- Approval (`core/brain.py` `_control_gate`): the target has to be named in this request (`control.named_in`:
  "this window / terminal / tab" needs those words; otherwise every word of the target must be in what he said; never
  an address); the plan is validated and checked against every never-do *before* he's asked (a refused plan is never
  put to him); then the whole plan is shown (console: full text, HUD: full text, voice: only the first line) and he
  says or clicks yes. The gate then writes a random single-use approval (`orrin_db.control_approvals`, 3 min) bound
  to the hash of exactly that window + goal + steps, and fills in `address` / `approval` / `request` itself (the
  model's values are overwritten). `control_run` refuses anything without a matching unused approval. "Allow this
  task" (voice, or ALLOW TASK in the console; offered only for a background task's plan) lets that task's Brain
  approve its later plans for the same window without asking; it lives in that Brain object only (never stored, not
  for voice / typed requests, not for another window or task). Every plan still shows on the border and in the log.
- Never (`core/control.py` `check_plan` before asking, again at run time): lock screen / hyprlock, Stage 3's never-read
  windows (polkit, keyring, password prompts and managers, blocklist); typing while AT-SPI says a password field has
  the focus or a terminal's last line is a password / passphrase / `[sudo]` prompt (checked before every line);
  system settings (settings apps, Super-key and XF86 keys, Ctrl+Alt+Del/F-keys, and in a terminal sudo / systemctl /
  pacman / nmcli / hyprctl / chmod / writes into ~/.config …); messaging and mail apps or pages (only scrolling
  allowed), "send / reply / post / share" steps or buttons; payment pages (only scrolling), pay / buy / order buttons;
  deleting files (Delete in a file manager, Shift+Delete, rm / shred / find -delete …, Delete / Trash buttons, by
  AT-SPI name even for a coordinate click); scripts piped from the internet; and text to type that appears on screen
  but not in his request (a page can't get its instructions typed). Typed text across steps is checked joined.
- Running (`control.Runner`): focus the window once, then before every input event: kill flag, hyprlock, settle gate
  (waits ≤10 s), combat mode (pauses ≤2 min with the border saying so, no input meanwhile, then gives up), window
  still there / same app / not now on the never list / still the focused window (a pop-up or another app taking focus
  stops it), point inside the window and not under a floating, pinned or special-workspace window or an overlay layer.
  After every step it re-captures (Stage 3 `screen.capture_window`, export) and checks: "no visible change" steps
  pass; typed text found in the window's own text (kitty / AT-SPI) passes without Claude; nothing changed (two looks)
  stops; otherwise a one-shot fast-model look with no tools compares BEFORE / NOW with the step's `expect`. Not as
  expected → stops and says what it saw (fenced), and the model asks him. Verification turns count under "control"
  (console header: "(WATCHERS n · CONTROL n)").
- Border: `quickshell/OrrinControl.qml` (+ `OrrinControlState.qml` singleton, IPC `orrincontrol frame | hide | stop`),
  an Overlay layer over the window plus a glow margin, empty input mask (clicks go through), breathing theme-primary
  outline and a tag "J.A.R.V.I.S CONTROL · ACTING · STEP 2/3 · SUPER+SHIFT+ESC / "STOP" TO STOP". The runner beats it
  every 0.5 s; no beat for 2 s → gone. The kill switch flashes it STOPPED in the secondary colour.
- Kill switch: Super+Shift+Escape (`hypr/alchemos/binds.lua`; plain shell `touch $XDG_RUNTIME_DIR/orrin-control-stop`
  + `qs ipc call orrincontrol stop`, so it works with Python or the HUD stuck), "Orrin, stop" (the wake word
  interrupts the request and `Brain.interrupt` sets the flag; then "stop" / "halt" / "hands off" answers "Stopped, sir"
  without reaching the music's "stop"), typed "stop" in the console (handled before the turn lock the running plan
  holds), `orrin control stop`. A plan stops before its next input event; typing stops within one 12-character chunk.
  `orrin control status | log` (`control_log`: every plan, refusal and stop).
- Router: `claude.control` (claude-only) examples; `open_app` refuses click / press / type / scroll / "in this window"
  wording ("press enter in this terminal" used to open a terminal).
- Tests: `tests/test_control.py` (keys, plan shape, window kinds, every never-do, naming, plan text / hash, single-use
  approvals, the runner with fakes for each stop, the gate incl. allow-task scope, control_run without approval).
  Live on dummies only: nested Hyprland (scale 1.625) with a GTK test page and a kitty: element and coordinate clicks,
  typing verified through AT-SPI and kitty, a password field refused after the click, the kill flag mid-typing (one
  chunk typed), focus stolen mid-plan; a typed request end to end (Claude looked, planned one step, the gate asked,
  the executor clicked and Claude verified); `rm -rf` refused at the gate without asking; an unnamed window → "which
  window?"; a note in the GTK page telling Orrin to type a command → declined. Real session, dummies on
  special:jtest: border on screen, real pointer click verified, Super+Shift+Escape through the real bind stopped a plan
  mid-wait, focus and the special workspace restored, real keyboard layouts unchanged.

## After stage 4: Orrin on the laptop (2026-11-02)

When Orrin runs (`quickshell/OrrinState.qml`):
- Docked: unchanged. It runs while the ORRIN toggle (Settings → ORRIN / HUD, control-center tile) is on
  (`orrinDocked`, saved), and battery saver stops it only if `saverStopOrrin` says so.
- Undocked: off by default. The same toggle switches it on for now (`laptopOn`, never saved). Any dock or undock
  clears it, so the next undocked spell starts off again and docking goes back to the docked rule. Docking with it on
  restarts Orrin in docked mode.
- Laptop mode (`ORRIN_LAPTOP=1` → `core/config.LAPTOP`): wake word, voice and the console as usual; no
  academic sync (`_sync_loop` returns), window watchers wait for the dock (the console shows PAUSED · ON LAPTOP and
  `watch_window` says so), no Bluetooth room speaker (`Speaker.wanted()` false: headphones or the laptop speakers).
  It switches itself off under 20 % on battery, with a ORRIN OFF toast saying why; switching it on then is refused
  with a ORRIN STAYS OFF toast. Battery saver doesn't affect laptop mode (autoSaver turns it on whenever he's on
  battery, which would have meant AC only).
- Shown as ON, OFF or "ON (laptop, until dock change)" on the toggles and the bar (◉ listening, ◌ starting, ○ off).
- Tested with a probe Quickshell (the real OrrinState with stub Theme / Roles / PowerMode / SysStats and a dummy
  process logging its mode): undocked off → on (laptop) → dock (restarts in docked mode) → undock (off); docked
  toggle off / on; low battery stops it and refuses it, battery saver doesn't.
