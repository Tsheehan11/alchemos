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
| **Jarvis** | "Hey Jarvis, open Spotify" / "Hey Jarvis, what's…" (offline wake word + Whisper) |
| **Docking aware** | Laptop alone: everything on one screen. Docked: clock / diagnostics / audio deck across 3 screens |
| **Battery saver** | Unplugged → static effects, no blur, 48 Hz, power-saver profile |
| **Themes** | Stark, Mark III, Vibranium, Matrix, Arctic, Solar, or custom colors |

## Layout

```
~/.config/hypr/         Hyprland, hyprlock (template), hypridle, lock + lid scripts
~/.config/hypr/system/  Files installed outside $HOME (hyprlock PAM stack, suspend hooks)
~/.config/quickshell/   The whole HUD (shell.qml is the entry point)
~/.config/jarvis/       Voice assistant (jarvis.py; its .venv is not tracked)
```

## Requirements

```
hyprland quickshell hyprlock hypridle cava kitty fuzzel brightnessctl playerctl
ttf-jetbrains-mono-nerd networkmanager bluez-utils uv
```

Jarvis: `cd ~/.config/jarvis && uv venv --python 3.11 && uv pip install --python .venv openwakeword faster-whisper`

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
then they open. Four things keep that seamless:
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

## Notes

- Monitors are matched by model + serial in `hyprland.conf` — change those two lines for your own screens.
- Sounds in `quickshell/sounds/` are synthesized from scratch (no samples).
- Built with help from Claude.
