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
~/.config/hypr/system/  Files installed outside $HOME (fingerprint suspend hook)
~/.config/quickshell/   The whole HUD (shell.qml is the entry point)
~/.config/jarvis/       Voice assistant (jarvis.py; its .venv is not tracked)
```

## Requirements

```
hyprland quickshell hyprlock hypridle cava kitty fuzzel brightnessctl playerctl
ttf-jetbrains-mono-nerd networkmanager bluez-utils uv
```

Jarvis: `cd ~/.config/jarvis && uv venv --python 3.11 && uv pip install --python .venv openwakeword faster-whisper`

## Fingerprint (Elan MOC sensor)

The Elan reader (`04f3:0c88`) wedges if it's mid-scan when the laptop suspends: fprintd logs
`Cannot run while suspended`, then `fpi_ssm_mark_failed: assertion 'machine != NULL' failed`,
and every Claim after that fails with `Device was already claimed`. Fingerprint then vanishes
from hyprlock and sudo, and restarting fprintd alone doesn't help.

The fix is a system-sleep hook. Before suspend it masks fprintd (so nothing re-activates it)
and SIGKILLs it at once, so no scan can be running when the laptop sleeps and suspend isn't held
up. On resume it unmasks fprintd first, then a background unit restarts it after the wake and
watches its log for a few seconds; only if the sensor really wedged does it USB-reset it.
hyprlock releases the device on sleep and re-claims it on wake, so the lock screen gets its
fingerprint prompt back by itself.

If the sensor wedges for real, `usbreset` may not clear it. A full shutdown (not a reboot)
does.

| Installed file | Source in this repo |
| --- | --- |
| `/usr/lib/systemd/system-sleep/stark-fprintd` | `~/.config/hypr/system/stark-fprintd-sleep` |

Install (also unwedges a stuck reader and asks for a test scan):

```
fish ~/.config/hypr/fprint-install.fish
```

Manual equivalent:

```
sudo install -m 755 ~/.config/hypr/system/stark-fprintd-sleep /usr/lib/systemd/system-sleep/stark-fprintd
sudo systemctl kill -s KILL fprintd; sudo systemctl reset-failed fprintd
sudo usbreset 04f3:0c88 && sudo systemctl start fprintd && fprintd-verify
```

If it breaks again: `journalctl -u fprintd -b | grep -E 'claimed|in use|machine != NULL'`
(and `journalctl -u stark-fprintd-wake -b` to see whether the resume check reset the sensor).

## Lid close / suspend

Closing the lid (undocked) runs `~/.config/hypr/lid.sh`: the screen goes dark at once
(`dpms off`), the lock starts, and logind suspends. hypridle's `before_sleep_cmd` holds a sleep
inhibitor until hyprlock is really up, so the session is never asleep unlocked, and nothing
waits on fixed sleeps. Opening the lid turns the screen back on with hyprlock already drawn.
The lid lock skips the security-door animation, and the HUD's animations pause while locked.

The system-sleep hooks (`stark-fprintd`, `stark-govee`) run while systemd has the whole user
session frozen, and the screen stays frozen until they finish, before sleep and after wake. So
they must never wait on anything in the session: the Govee hook doesn't talk to its (frozen)
daemon before sleep, and both hooks hand their wake work to a background unit that runs once
the session thaws. To check timings: `journalctl -b -o short-precise | grep -E 'Lid|systemd-sleep|froze|thawed'`.

## Notes

- Monitors are matched by model + serial in `hyprland.conf` — change those two lines for your own screens.
- Sounds in `quickshell/sounds/` are synthesized from scratch (no samples).
- Built with help from Claude.
