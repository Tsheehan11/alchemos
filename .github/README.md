# STARK OS

A holographic, Iron-Man-inspired desktop for **Hyprland** on Arch / CachyOS, built with **Quickshell**.

Arc-reactor clock · spinning holographic workspace overview · flow-cloud app launcher ·
security-door lock / unlock / shutdown animations · Jarvis voice assistant · live system HUD ·
audio deck with visualizer · full themeable settings — all reacting to how many screens are plugged in.

---

## Features

| | |
| --- | --- |
| **Arc-reactor clock** | CPU / RAM / GPU / battery rings around the time |
| **Flow-cloud launcher** | `Super + Space` — apps spin out of the cursor in branches (AI, NET, MEDIA, SYS, CTRL) |
| **App search** | `Super + R`, or start typing in the launcher |
| **Workspace overview** | `Super + Tab` — workspaces as hologram panels on a 3D ring, with live window previews |
| **Control center** | `Super + C` or click the stats in the top-right |
| **Settings** | `Super + ,` — Wi-Fi, Bluetooth, themes, HUD, sleep timings, battery saver |
| **Lock** | `Super + L` — security doors slam shut, lock screen lines up with them, doors open on unlock |
| **Power menu** | Power button or `Super + Escape` — shutdown plays a CRT power-off animation |
| **Jarvis** | Claude-powered voice assistant: "Hey Jarvis, set the theme to Mark III and dim the lights". Local wake word, speech-to-text and voice; Claude only for the thinking (see [Jarvis](#jarvis)) |
| **Docking aware** | Laptop alone: everything on one screen. Docked: clock / diagnostics / audio deck across 3 screens. Display profiles per setup (desk / laptop / TV), switched on plug-in |
| **Battery saver** | Unplugged → static effects, no blur, 48 Hz, power-saver profile |
| **Themes** | Stark, Mark III, Vibranium, Matrix, Arctic, Solar, or custom colors |
| **Cursor** | Holographic STARK-OS cursor theme, rebuilt in the accent colour on every theme change; arc-reactor busy cursor |

## Layout

```
~/.config/hypr/         Hyprland, hyprlock (template), hypridle, lock + lid scripts
~/.config/hypr/system/  Files installed outside $HOME (hyprlock PAM stack, suspend hooks)
~/.config/quickshell/   The whole HUD (shell.qml is the entry point)
~/.config/jarvis/       Voice assistant (jarvis.py; its .venv is not tracked); data in ~/.local/share/jarvis
~/.config/stark-cursor/ Cursor theme: SVG templates (src/) and build.sh
```

## Requirements

```
hyprland quickshell hyprlock hypridle cava kitty fuzzel brightnessctl playerctl
ttf-jetbrains-mono-nerd networkmanager bluez-utils uv librsvg hyprcursor python-pillow
```

`xorg-xcursorgen` is optional: without it the cursor build uses its own `xcursorgen.py`.

Jarvis: `cd ~/.config/jarvis && uv venv --python 3.11 && uv pip install --python .venv openwakeword faster-whisper claude-agent-sdk mcp piper-tts kokoro-onnx pedalboard`,
then put `kokoro-v1.0.int8.onnx` and `voices-v1.0.bin` (kokoro-onnx GitHub releases, `model-files-v1.0`) in
`~/.local/share/jarvis/kokoro/`. Claude uses your `claude` login (Pro/Max); no API key.

## Jarvis

"Hey Jarvis" (openWakeWord) → faster-whisper `base.en` → a regex fast path for everyday commands
(media, lights, workspaces, VPN, themes, timers, weather, CPU temp: 5–40 ms, no AI) → otherwise Claude
through the Agent SDK on the `claude` login: Haiku by default, Sonnet for longer or "explain / plan"
requests, its reply spoken sentence by sentence as it streams. About 0.6–1 s from the end of your
sentence to Jarvis's voice on the fast path, about 2–3 s on Claude.
Runs only while docked (Settings → JARVIS), started by the HUD under `setpriv --no-new-privs`.

- **Tools, not a shell.** Claude gets no built-in tools, only the STARK MCP server
  (`mcp/stark_tools.py`, 22 validated tools: apps, windows, workspaces, themes, lights, media, VPN,
  UW CS servers, timers / reminders, memory, power, weather via Open-Meteo for `jarvisPlace`). Jarvis enforces the rules itself in the SDK's
  permission callback: at most 8 tool calls per request, a 30 s timeout, the browser only when asked,
  and a spoken "yes" before power actions, closing windows, deleting, the kill switch, or anything
  that sends a message. Tool output is treated as data. No network listeners; works with Proton VPN on.
- **Phase 2** integrations (calendar, mail, smart home…) are extra MCP servers in `servers.json`; every
  tool of a new server needs a spoken yes unless listed in `auto_allow`.
- **Voice.** Kokoro (`bm_lewis` by default) with piper as fallback, then an effect chain (pedalboard):
  presets CLEAN / HOLOGRAM / SUIT in `effects.json`; AUTO uses SUIT on headphones and HOLOGRAM on
  speakers. Text is normalized first (`core/speech.py`: "16:07" → "four oh seven PM", dates, units,
  symbols; `python tests/test_speech.py`). The first sentence plays while the rest render; short
  stock lines are cached.
  `jarvis-voices` auditions every British male voice. Without headphones, Jarvis can talk through a
  paired Bluetooth speaker (Settings → JARVIS → Speaker), connecting when it hears the wake word; if
  it isn't up within 1.5 s, that reply plays on the laptop.
- **Hearing** (`core/hearing.py`, tuned on recordings). `jarvisMic` picks the PipeWire source (the
  laptop mic at the desk). The command starts from just before the wake word, so "hey Jarvis dim the
  lights" in one breath keeps every word; Silero VAD ends it after 0.56 s of silence; whisper gets a
  vocabulary prompt. Music is turned down while it listens. Barge in with "Hey Jarvis" while it talks or
  thinks; follow-ups need no wake word for 8 s. It never goes quiet after the chime: anything that
  fails gets a short spoken line and the reason on the toast.
- **CLI.** `jarvis --text "…"` (add `--dry-run` to only show what it would do), `--misses` (requests
  the fast path missed), `--log`, `--facts`, `--reminders`, `--say "…"`. Log: `~/.local/share/jarvis/jarvis.log`.
  `jarvis --trace` follows every exchange stage by stage (wake score, VAD, transcript, route, latency);
  `jarvis --record [MIN]` keeps WAVs of each exchange in `~/.local/state/jarvis/rec` for tuning.
- Secrets, if a phase-2 service ever needs one, go in gnome-keyring (`core/secrets.py`), never in tracked files.

## Lock screen, fingerprint and faillock

hyprlock takes the password or the fingerprint, whichever comes first. It runs the password
through PAM (`/etc/pam.d/hyprlock`) and the fingerprint through fprintd over D-Bus, so a
fingerprint error or timeout never counts as a failed login.

**Why the account used to lock itself.** While the lock screen is up, hyprlock always has a
PAM password prompt open. When the fingerprint (or `SIGUSR1`) unlocks it, hyprlock aborts that
prompt, and the stock stack (`login` -> `system-auth`) recorded the abort as a failed login
(`pam_unix(hyprlock:auth): conversation failed`). The success path never runs, so nothing
cleared those records. Three fingerprint unlocks within 15 minutes locked the account
(`pam_faillock ... temporarily locked`), and from then on the correct password failed too, in
hyprlock and on the TTY, until `unlock_time` ran out.

`~/.config/hypr/system/hyprlock.pam` is the same stack as login with one change: an aborted
prompt (`authtok_err` / `conv_err`: no password was checked) ends it without a faillock record.
Wrong passwords are still counted and still lock the account. Check the tally with
`faillock --user $USER`.

**faillock settings.** `/etc/security/faillock.conf` sets `deny = 5`: five wrong passwords
within 15 minutes (`fail_interval`, default) lock the account for 10 minutes (`unlock_time`,
default), for every PAM service: hyprlock, the TTY, sudo. Stock Arch is `deny = 3`. No PAM
file passes its own `deny=`/`unlock_time=`, so this one file is the only place to change it.
The installer keeps the original as `faillock.conf.orig`.

**Fingerprint across suspend.** The Elan reader (`04f3:0c88`) sometimes wedges across suspend:
fprintd logs `fpi_ssm_mark_failed: assertion 'machine != NULL' failed` (or
`Cannot run while suspended` after wake), and only a USB reset brings it back. hyprlock claims
the reader once when it starts and keeps that claim through suspend, so fprintd must never be
killed or restarted under it. If it is, hyprlock gets `Device was not claimed before use` and
has no fingerprint until the next lock. So the `stark-fprintd` hook leaves fprintd alone before
sleep. After wake, a background unit watches fprintd for a few seconds and, if the sensor
wedged, resets it once no hyprlock is running. The password works the whole time. If a wake
leaves the fingerprint dead, unlock with the password and the reader is fixed for the next lock.

If the sensor wedges for real, `usbreset` may not clear it. A full shutdown (not a reboot)
does.

| Installed file | Source in this repo |
| --- | --- |
| `/etc/pam.d/hyprlock` | `~/.config/hypr/system/hyprlock.pam` |
| `/etc/security/faillock.conf` (`deny = 5`) | edited in place by the installer |
| `/usr/lib/systemd/system-sleep/stark-fprintd` | `~/.config/hypr/system/stark-fprintd-sleep` |
| `/usr/lib/systemd/system-sleep/stark-thaw` | `~/.config/hypr/system/stark-thaw-sleep` |
| `/etc/systemd/logind.conf.d/stark.conf` | `~/.config/hypr/system/logind-stark.conf` |

Install (keeps the old PAM file as `/etc/pam.d/hyprlock.orig`, unwedges a stuck reader and
asks for a test scan; run it while unlocked):

```
fish ~/.config/hypr/fprint-install.fish
```

Manual equivalent:

```
sudo install -m 644 ~/.config/hypr/system/hyprlock.pam /etc/pam.d/hyprlock
sudo install -m 755 ~/.config/hypr/system/stark-fprintd-sleep /usr/lib/systemd/system-sleep/stark-fprintd
sudo install -m 755 ~/.config/hypr/system/stark-thaw-sleep /usr/lib/systemd/system-sleep/stark-thaw
sudo install -D -m 644 ~/.config/hypr/system/logind-stark.conf /etc/systemd/logind.conf.d/stark.conf
sudo cp -n /etc/security/faillock.conf /etc/security/faillock.conf.orig
sudo sed -i -E '/^[[:space:]]*deny[[:space:]]*=/d; s/^# deny = 3$/&\ndeny = 5/' /etc/security/faillock.conf
sudo systemctl unmask --runtime fprintd; faillock --user $USER --reset
```

If it breaks again: `journalctl -b | grep -E 'hyprlock|faillock'`, hyprlock's own log of the
last two locks in `~/.local/state/stark/hyprlock.log{,.1}`,
`journalctl -u fprintd -b | grep -E 'claimed|machine != NULL'` and
`journalctl -u stark-fprintd-wake -u stark-thaw-wake -b`.

## Locked out? `stark-rescue`

From a TTY (Ctrl+Alt+F3, log in), run `stark-rescue` (`~/.config/hypr/stark-rescue`, linked
into `~/.local/bin`; if the link is missing: `sh ~/.config/hypr/stark-rescue`). It:

1. clears faillock for your user (no sudo needed, and it has to come first because sudo goes
   through faillock too);
2. thaws `user.slice` if suspend left it frozen (only then asks for sudo);
3. turns the screens back on (`dpms on`);
4. unlocks hyprlock with `SIGUSR1`. If hyprlock is gone, or hung and ignores the signal, it
   kills it and puts a fresh lock back (`misc:allow_session_lock_restore`, set in
   `hyprland.conf`), so the session is never left open or stuck on the "lock screen died"
   page.

Then switch back with Ctrl+Alt+F2 and, if a fresh lock came up, type your password.

## Lid close / suspend

Closing the lid runs `~/.config/hypr/lid.sh`. Docked (more than one monitor in
`hyprctl monitors -j`) it does nothing, and logind doesn't suspend either
(`HandleLidSwitchDocked=ignore`). Undocked, it shuts the doors, waits until hyprlock has the
session locked (at most ~1.5 s), and only then turns the screen off (`dpms off`): locking with
the screen already off left the HUD undrawn under the lock, which flashed at unlock. logind
suspends on its own; hypridle's `before_sleep_cmd` holds a sleep inhibitor until hyprlock is up,
so the session is never asleep unlocked. For 5 s after waking logind ignores the lid
(`HoldoffTimeoutSec=5s` in `/etc/systemd/logind.conf.d/stark.conf`); if logind isn't preparing
to sleep within 2 s and the lid is still closed, `lid.sh` suspends itself. Opening the lid turns
the screen back on with hyprlock already drawn.
The lid lock skips the security-door animation, and the HUD's animations pause while locked.
Unlocking cuts straight from the lock screen (a picture of the shut doors) to the real doors,
then they open. Five things keep that seamless:
- every monitor has its own picture (`stark-lock-bg-<NAME>.png`: its size, and the emblem on
  the main screen or ◈ on the others) and its own `background` block in `hyprlock.conf`; the
  clock and password sit on the main screen only. The HUD redraws a picture offscreen whenever
  the theme, the screen's size or its role changes (dock / undock / TV); a stamp next to it
  (`.png.key`) records what it was drawn with, so a stale one is redrawn at startup too. Super+L
  captures only a picture that's still stale (re-writing current ones just before hyprlock
  started left it showing a blank background for a few frames). The emblem always rests at 0°
  when the doors are shut, so the pictures match the real doors pixel for pixel;
- while the session is locked, Hyprland draws only black under hyprlock, so hyprlock has no
  fade-out (`fadeOut, 0` in `hyprlock.template.conf`), which would show that black;
- `stark-lock.sh` shuts the doors and waits (at most ~0.6 s) until they're on screen before
  starting hyprlock: a lid lock is followed at once by the freeze for suspend, and doors that
  weren't drawn by then showed as black or the bare desktop at unlock;
- the `stark-doors` layer has no fade-in (`layerrule ... no_anim`), since Hyprland holds a
  layer's fade-in until the session unlocks;
- the reveal starts when hyprlock logs a successful unlock, not when it exits (after a
  fingerprint unlock it lingers ~2 s while PAM's fail delay ends the aborted password prompt).

The system-sleep hooks (`stark-fprintd`, `stark-govee`, `stark-thaw`) run while systemd has the
whole user session frozen, and the screen stays frozen until they finish, before sleep and after
wake. So they must never wait on anything in the session: the Govee hook doesn't talk to its
(frozen) daemon before sleep, and all of them hand their wake work to a background unit that
runs once the suspend is over. `stark-thaw`'s unit is the backstop: if anything under
`user.slice` is still frozen by then, it thaws it. To check timings: `journalctl -b -o short-precise | grep -E 'Lid|systemd-sleep|froze|thawed'`.

## Cursor

`~/.config/stark-cursor/build.sh <rrggbb> [animated|static] [24|32|48] [20-90]` renders the SVG
templates in `src/` (`{{ACCENT}}` is the theme colour, `{{FILL_ALPHA}}` the body fill opacity
in %) into one theme directory,
`~/.local/share/icons/STARK-OS`, holding both an XCursor theme (all three sizes) and a
hyprcursor theme (SVG). It then applies the theme with `hyprctl setcursor`. `src/cursors.txt`
lists every cursor with its hotspot and aliases (X11, CSS and Qt-hash names), so no app falls
back to Adwaita. Builds are cached per colour in `~/.cache/stark-cursor` (about 1 s cold,
0.15 s cached).

Theme.qml runs it whenever the accent, Settings → APPEARANCE → CURSOR (size, CURSOR OPACITY,
ANIMATED BUSY CURSOR) or battery saver changes, 600 ms after the last change and one build at a time.
Battery saver always uses the still busy cursor. build.sh also keeps everything else pointed
at the theme, rewriting a file only when a value changes: the `env =` lines in `hyprland.conf`, gsettings, GTK 3/4
`settings.ini`, xsettingsd, `~/.icons/default`, `kcminputrc` (KDE / Dolphin), Xresources and
the systemd / D-Bus environment.

Hyprland draws the cursor for Qt 6, Electron and the HUD itself, so those recolour at once.
GTK apps like Zen draw their own cursor and reload it only when the theme *name* changes,
so build.sh briefly switches GTK to `STARK-OS-reload` (an alias of the same theme) and back.
That reliably recolours Zen, but a size change may only show in Zen after a restart.
XWayland apps (Steam, Spotify) read the theme when they start, so they need a restart to
pick up a new colour or size.

## Panel opacity

Settings → APPEARANCE → PANEL OPACITY (50–100 %, default 85 %) sets the background of the
HUD's pop-up panels: Settings, the control center and app search (`Theme.panelAlpha`, used by
`HudFrame.qml` and `AppSearch.qml`). The diagnostics wall keeps its own 55 % so the desktop
still looks like a hologram. The HUD layers are never blurred, so battery saver doesn't change
how the panels look.

Preferences can also be set from a shell: `qs ipc call theme set panelOpacity 0.9`,
`qs ipc call theme get cursorOpacity`, `qs ipc call theme preset matrix`, and
`qs ipc call settings open appearance` opens a Settings tab.

## Display profiles

What's plugged in picks a display profile, and switching applies it at once (no 15 s
keep-or-revert prompt):

| Profile | When | Gets |
| --- | --- | --- |
| HOME DESK | the USB-C dock (its card reader `0bda:5350` serial `202503061002`, or its LAN adapter `0bda:8153`) **and** both Acers (serials `16220214A4B00` left/main, `1622022294B00` middle/diag) | extend, left Acer / middle Acer / laptop, workspaces 1–3 / 4–6 / 7–9, Jarvis on, Govee strip on in the mode you last used at the desk |
| LAPTOP ONLY | no external monitor | Jarvis off, strip off, battery saver |
| anything else | keyed by the connected monitors' descriptions, e.g. the TV over HDMI | starts as extend with Jarvis and the strip off; keeps whatever you save for it |

Each profile remembers its own arrangement and layout mode, so mirroring the TV is saved
for the TV only and never reaches the desk. Settings → DISPLAY shows the active profile;
APPLY + KEEP saves into it, **SAVE CURRENT AS THIS PROFILE** stores what's on screen now
(plus the current Jarvis / strip / battery-saver settings), and **RESET PROFILE** forgets
it and puts the defaults back.

Switches happen on Hyprland's `monitoradded` / `monitorremoved` (debounced 2.5 s, as the dock
brings its monitors up one at a time) and after a resume. While a switch settles, the old
layout mode isn't re-applied to the new screens. The profile's reload still goes through the
Displays loop guard (at most one `hyprctl reload` per 20 s), deferred rather than dropped.

Files: `~/.config/quickshell/Profiles.qml` (switching), `ProfileLogic.js` (detection and
defaults), `display-profiles.json` (saved profiles). `~/.config/hypr/monitors.conf` is
generated from the active profile and not tracked. By hand: `qs ipc call profiles status`,
and `qs ipc call profiles recheck` re-detects and re-applies the profile.

## Notes

- Monitors are matched by model + serial in `hyprland.conf` — change those two lines for your own screens.
- Sounds in `quickshell/sounds/` are synthesized from scratch (no samples).
- Files the HUD writes from its theme aren't tracked: `hypr/hyprlock.conf`, `hypr/stark-lock-bg-*`,
  `hypr/monitors.conf`, `kitty/stark-theme.conf`, `govee/theme.json` (listed in the repo's
  `info/exclude`). VS Code's `settings.json` is tracked without the three theme keys
  `stark-code-theme` merges in, via a clean filter. After cloning, set both up:
  ```sh
  stark config filter.stark-code-theme.clean '$HOME/.local/bin/stark-code-settings-clean'
  stark config filter.stark-code-theme.smudge cat
  echo '.config/Code/User/settings.json filter=stark-code-theme' >> ~/.stark-os/info/attributes
  ```
- Built with help from Claude.
