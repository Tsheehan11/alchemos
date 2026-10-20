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
~/.config/quickshell/   The whole HUD (shell.qml is the entry point)
~/.config/jarvis/       Voice assistant (jarvis.py; its .venv is not tracked)
```

## Requirements

```
hyprland quickshell hyprlock hypridle cava kitty fuzzel brightnessctl playerctl
ttf-jetbrains-mono-nerd networkmanager bluez-utils uv
```

Jarvis: `cd ~/.config/jarvis && uv venv --python 3.11 && uv pip install --python .venv openwakeword faster-whisper`

## Notes

- Monitors are matched by model + serial in `hyprland.conf` — change those two lines for your own screens.
- Sounds in `quickshell/sounds/` are synthesized from scratch (no samples).
- Built with help from Claude.
