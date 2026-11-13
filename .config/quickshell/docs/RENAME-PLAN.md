# AlchemOS rename + notifications + screenshot reskin: plan

Status: **Stage 2 (rename) done 2026-11-13** (commits C0–C7 below); Stage 3 (notifications) and Stage 4
(screenshot effect) follow in their own commits. Written 2026-11-13 as the Stage 1 plan; see
**Outcome** at the end for what changed from the plan and what is left for you.

Goals: (A) rename everything at the file / service / path level from STARK OS to AlchemOS, and the Jarvis
internals to Orrin; (B) reskin desktop notifications for ALCHEMOS; (C) give the screenshot effect an
ALCHEMOS look. All three go through the skin layer, so LEGACY keeps its STARK look pixel for pixel
(`check_skins.sh` is the gate).

## 0. Preflight (done)

| | |
| --- | --- |
| git tag | `pre-rename` → `5d530d6`, pushed to origin (annotated tag `b41d847`) |
| data backup | `~/Backups/jarvis-pre-rename-2026-11-13.tar.zst` (29.2 GiB, 411,688 entries, mode 600; `~/.local/share/jarvis` + `~/.config/jarvis`, including tokens, wake models, learned intents, tts-lab and wake-train). Local only, never committed |
| running state | `~/Backups/running-before-2026-11-13.txt` |
| raw audit lists | `~/Backups/tokens.txt` (453 distinct name tokens), `~/Backups/tracked-hits.txt` (244 tracked files, 2,852 matching lines) |
| snapper | **not done: needs root** (see §6, first line). Note that the `root` config covers `/` (`@`) only. `/home` is the separate `@home` subvolume, so the snapshot protects `/etc`, `/usr/local/bin` and the sleep hooks, not the dotfiles. The dotfiles are covered by the tag and the tarball |

What was running before the change:

- **User services:** `stark-jarvis.service` (active). `jarvis-wake-train.service` exists, inactive. Enabled: only stock units plus `arch-update.timer`
- **System:** `stark-govee-power.service` (enabled, active/exited)
- **Sleep hooks:** `/usr/lib/systemd/system-sleep/stark-fprintd`, `stark-thaw`, `stark-govee`
- **logind:** `/etc/systemd/logind.conf.d/stark.conf`
- **`/usr/local/bin`:** `stark-fprint-reset` (a root-owned copy)
- **Started at login (`autostart.lua`):** hypridle, polkit-kde, `stark-hud.sh` (qs), **mako** (uncommitted line), spotify-launcher, dbus env, `stark-audio-auto.sh`, `stark-govee daemon`, `stark-game daemon`
- **Started by the HUD:** `stark-vpn watch`, `journalctl -f … SYSLOG_IDENTIFIER=stark-fprint-reset`, `jarvis.py usage --watch`, `jarvis.py feed`, cava

## 1. Blocker: uncommitted work from another session

`stark status` shows nine modified files. Only some match the list you expected:

| file | what it is | expected? |
| --- | --- | --- |
| `.config/Code/User/settings.json` | VS Code | yes |
| `.config/quickshell/settings.json` | settings (PINKY preset etc.) | yes |
| `.config/hypr/hypridle.conf` | idle timeouts 600/900/1200/1800 → 900/1800/1800/2700 | yes |
| `.config/hypr/stark/autostart.lua` | `+ hl.exec_cmd("mako")` | **no** |
| `.config/quickshell/PowerMode.qml`, `ControlCenter.qml`, `Settings.qml` | battery saver: picking BALANCED / PERFORMANCE by hand on battery turns the saver off until the next plug-in | **no** |
| `.config/stark-game/stark-game` | the XWayland primary output follows the focused monitor | **no** |
| `.config/heroic/GamesConfig/Peppermint.json` | Chivalry 2 Proton settings | **no** |

Untracked: `.config/hypr/hyprland.conf` (the stub), `.local/bin/stark-wake`, `.local/bin/govee`,
the symlinks `stark-jarvis` and `stark-fprint-reset`, `.local/bin/__pycache__/`.
(`servers.json` and the wake-word files show no changes, so they are already committed.)

The rename moves most of these files (`git mv`). Uncommitted edits would then be carried into commits
named after the rename. **Proposal:** before Stage 2, commit each finished feature as its own commit
(mako autostart, saver override, XWayland primary, Peppermint, hypridle timeouts). Leave both
`settings.json` files uncommitted as usual. Their key renames are staged hunk by hunk.

## 2. Naming map

### (a) STARK → AlchemOS

| now | after | notes |
| --- | --- | --- |
| `~/.stark-os` (bare repo) | `~/.alchemos` | `mv` + `core.hooksPath`, `info/exclude`, `info/attributes` |
| fish `stark` | fish **`alc`** | `stark` stays as a shim: one stderr line `stark: renamed to alc` then runs git. README gives bash/zsh aliases |
| GitHub `Tsheehan11/stark-os` | `Tsheehan11/alchemos` | `gh repo rename alchemos`, `alc remote set-url`, test push. GitHub redirects the old URL |
| `~/.config/stark-hooks/` | `~/.config/alchemos-hooks/` | moved in the same commit as `core.hooksPath`. The hook's `^\.config/jarvis/` check becomes `^\.config/orrin/` |
| git filter `stark-code-theme` | `alchemos-code-theme` | `.git/config` + `info/attributes`. Re-run the clean filter once (`alc add --renormalize` on that file) |
| `hypr/stark/*.lua` | `hypr/alchemos/*.lua` | `hyprland.lua` loader edited in place (no zip), plus `govee/install.fish`. `display-profile.lua` is generated, so the HUD writes the new path |
| `hypr/stark-{audio-auto,dpms,hud,lock,music,share-picker}.sh` | `hypr/alchemos-*.sh` | callers: `autostart.lua`, `hypridle.conf` (lock_cmd, dpms ×3, govee), `lid.sh`, `binds.lua`, QML |
| `hypr/stark-hypr-check`, `.local/bin/stark-hypr-check` | `alchemos-hypr-check` | |
| `hypr/stark-rescue`, `.local/bin/stark-rescue` | `alchemos-rescue` | **`.local/bin/stark-rescue` stays as a permanent symlink**. Test from a real TTY (Ctrl+Alt+F3), including the lock-screen rescue |
| `.local/bin/stark-{govee,vpn,game,shot,uwcs-proxy,code-theme,code-settings-clean}` | `alchemos-*` | the `uwcs.fish` function calls the proxy. Temporary `stark-govee` symlink until the sudo block has run (the root sleep hook and system unit still call it); removed afterwards |
| `govee/stark-govee.py`, `govee/system/stark-govee-power.service` | `alchemos-govee.py`, `alchemos-govee-power.service` | unit Description `AlchemOS …` |
| sleep hook `stark-govee` (not tracked!) | `govee/system/alchemos-govee-sleep` → `/usr/lib/systemd/system-sleep/alchemos-govee` | `install.fish` currently *deletes* this hook, but it is installed and newer than the installer. Question in §8 |
| `.config/stark-{vpn,game,cursor}/` | `.config/alchemos-{vpn,game,cursor}/` | `STARK_VPN_DIR`, `STARK_GAME_DIR`, `STARK_GOVEE_DIR`, `STARK_GOVEE_TRACE` → `ALCHEMOS_*` |
| icon themes `STARK-OS`, `STARK-OS-reload` | `ALCHEMOS`, `ALCHEMOS-reload` | `build.sh` rewrites gsettings / GTK / xsettingsd / KDE / Xresources / Hyprland env. The name change itself makes Zen reload (see the cursor memory). Old dirs deleted after |
| `kitty/stark-theme.conf` | `kitty/alchemos-theme.conf` | `kitty.conf include`. Generated, in `info/exclude` |
| `hypr/stark-lock-bg-<MON>.png(.key)` | `alchemos-lock-bg-<MON>.png` | `hyprlock.template.conf`, Theme. Regenerated, so the old files can just be deleted |
| `hypr/system/logind-stark.conf` | `logind-alchemos.conf` → `/etc/systemd/logind.conf.d/alchemos.conf` | sudo |
| `hypr/system/stark-{fprintd,thaw}-sleep` | `alchemos-{fprintd,thaw}-sleep` → `system-sleep/alchemos-{fprintd,thaw}` | sudo. The units they create via `systemd-run` (`stark-fprintd-wake`, `stark-thaw-wake`) are renamed too |
| `hypr/system/stark-fprint-reset` → `/usr/local/bin/stark-fprint-reset` | `alchemos-fprint-reset` | sudo. Journal tag → `alchemos-fprint-reset`. `FprintWatch.qml` follows both tags until the sudo block has run, then only the new one |
| `hypr/system/hyprlock.pam` | comment only: `STARK OS` → `AlchemOS` | sudo `install`; the diff is a single comment line. Then test password + fingerprint |
| `~/.local/state/stark/` (hyprlock.log) | `~/.local/state/alchemos/` | `stark-lock.sh`, `lid.sh`, README |
| runtime: `stark-power/`, `stark-govee.sock`, `stark-hotplug-settling`, `stark-audio-auto.lock`, `stark-hud-logcap.lock`, `.stark-theme.lock`, `stark-lock.lock` | `alchemos-*` | transient; a reboot clears the old ones |
| layer namespaces `stark-*` (23) | `alchemos-*` | updated in the same commit: `rules.lua` (doors, shot-flash), `stark-lock.sh` (`hyprctl layers \| grep`), `core/control.py` |
| journal tag `stark-hud` | `alchemos-hud` | `stark-hud.sh`, `Hotplug.qml`, `core/screen.py` |
| screenshots `stark-YYYYMMDD-…png` | `alchemos-…png` | existing files keep their names |
| Heroic `themes/stark.css` | `alchemos.css` | plus the theme name in Heroic `config.json` |
| `STARK_DRY_RUN`, `User-Agent: stark-os-usage` | `ALCHEMOS_DRY_RUN`, `alchemos-usage` | |
| QML IPC `stark` (lock, locked, unlocked, fingerprint, power, menu) | `alchemos` | callers: `binds.lua` (L, Escape, power key), `stark-lock.sh` (×5), `alchemos_actions.py` (lock, power) |
| MCP server `stark` (`policy: "stark"`), `stark_tools.py`, `stark_actions.py` | `alchemos`, `alchemos_tools.py`, `alchemos_actions.py` | tool names become `mcp__alchemos__*` (the permission gate and tests too). No stored tool names were found in `jarvis.db` or `learned_intents.json` that need rewriting; checked again during the move |
| README, docs, comments, `fstab` / `pam` comments | AlchemOS | `fstab` comment: optional (§6) |

### (b) Jarvis → Orrin (and FRIDAY → Selene)

| now | after | notes |
| --- | --- | --- |
| `~/.config/jarvis/` | `~/.config/orrin/` | `mv` (same subvolume, instant). `.venv`: rewrite the 27 shebangs plus `activate*` `VIRTUAL_ENV` (`pyvenv.cfg` points at uv's python, so nothing else changes). Verified with `check_all.sh` |
| `~/.local/share/jarvis/` | `~/.local/share/orrin/` | `mv` with the service stopped. `jarvis.db(-wal,-shm)` → `orrin.db` after a WAL checkpoint. `jarvis.log` → `orrin.log`. `pocket-venv`: rewrite its 17 shebangs. Absolute paths in `wake-train/` and `tts-lab/` configs are rewritten with sed (generated audio is left alone) |
| `~/.local/state/jarvis/` | `~/.local/state/orrin/` | trace, recordings |
| `$XDG_RUNTIME_DIR/jarvis/` (sockets, status.json, dj.json, voice.lock), `jarvis-control-stop` | `…/orrin/`, `orrin-control-stop` | Shift+Super+Escape bind + `core/control.py` in the same commit |
| `jarvis.py` / `.local/bin/jarvis` | `orrin.py` / `orrin` | **`jarvis` stays as a shim** (one stderr line, then `exec orrin "$@"`) |
| `jarvis-voices` | `orrin-voices` | no shim |
| `stark-jarvis` (start/stop/status/log/restart) | **`orrinctl`** | the HUD (`OrrinState`) and `alchemos-rescue status` call it. No shim (tell me if you want one) |
| `stark-jarvis.service` (`SyslogIdentifier=jarvis`) | `orrin.service` (`SyslogIdentifier=orrin`) | stop, `disable`, remove the old unit, `daemon-reload`, start the new one. Not enabled (the HUD starts it), same as now |
| `jarvis-wake-train.service`, `stark-wake` | `orrin-wake-train.service`, `orrin-wake` | |
| `mcp/jarvis_db.py`, `JARVIS_DIR` / `JARVIS_DB` / `JARVIS_PY` / `JARVIS_STREAM(S)`, `STARK_JARVIS_LAPTOP` | `orrin_db.py`, `ORRIN_*`, `ORRIN_LAPTOP` | |
| keyring `jarvis:<service>` (Google, Spotify, Outlook, LEARN, kitty rc) | `orrin:<service>` | **no re-auth:** `secrets.get` reads `orrin:` first, then falls back to `jarvis:` and copies the entry over. `orrin secrets migrate` (run once, with the keyring unlocked) copies every entry, reads each back and lists them. The old entries are deleted only by a later `orrin secrets migrate --prune`, after you confirm everything works. `jarvis-rc-password.sh` (→ `orrin-rc-password.sh`, with `timeout 2` kept) looks up both |
| persona ids `jarvis` / `friday` | `orrin` / `selene` | `persona.norm()` already maps orrin/selene; it is flipped so old ids map to new. That covers stored `messages.persona` rows, IPC args, intents and **legacy `skin.json` `personas` keys, which stay `jarvis` / `friday`** (`Skin.qml` normalizes them at load; the legacy repo is untouched) |
| settings keys `jarvis*` (29), `friday*` (4), `saverStopJarvis`, `gameJarvis` | `orrin*`, `selene*`, `saverStopOrrin`, `gameOrrin` | **one-time migration in `Theme.qml`** (a `cfgVersion` bump: copy each old key → new, then delete the old one), done before anything is pushed. The Python readers (`core/config.py`, `alchemos-shot`) read new keys with an old-key fallback, for the moment between the agent starting and the HUD migrating. That fallback is removed in the last commit |
| IPC `jarvis`, `jarvisapp`, `jarviscontrol` | `orrin`, `orrinapp`, `orrincontrol` | callers: `core/hud.py`, `control.py`, `binds.lua` (Super+J, Shift+Esc), comments and docs. The HUD and agent change in one commit, and the agent is restarted with it |
| QML `JarvisState`, `JarvisToast`, `JarvisApp`, `JarvisControl(State)`, `JarvisFeed`, `JarvisLink`, `JarvisPage`, `widgets/Jarvis.qml`, skincheck `mocks/JarvisState.qml` | `Orrin*` | the legacy QML uses none of them (checked) |
| widget type `jarvis` (in `widgets.json`) | `orrin` | `Widgets.qml` `migrate()` aliases it. The `widget_add` Literal accepts both |
| `kitty/jarvis-rc-{check.py,password.sh}` | `orrin-rc-*` | `kitty.conf geninclude` |
| system prompt base names (JARVIS / FRIDAY / STARK OS + names tag) | ORRIN / SELENE / AlchemOS as the base | LEGACY's names tag (`[STARK OS · JARVIS · FRIDAY]`) still gives it the old names |
| tests: `dev.stark.jtest`, `mcp__stark__set_theme` fixtures | `dev.alchemos.jtest`, `mcp__alchemos__…` | |

### (c) KEEP, with the reason for each

| hit | why it stays |
| --- | --- |
| everything in `skins/legacy/` (`alchemos-legacy` repo): `STARK`, `JARVIS`, `FRIDAY`, `personas.jarvis/friday` keys, `osName: "STARK OS"` | it *is* the STARK look. The main tree reads its old keys through the alias instead |
| openWakeWord built-in `hey_jarvis` (the fallback wake model), "hey Jarvis" in fallback docs | the model name and the phrase it hears |
| `hey_friday` in `core/wake.py` `DEFAULT_PERSONA`, `tools/wakeword/hey_friday.yml` | a spoken phrase / model name, not a brand. `hey_friday.yml` → `words/` is fine as is |
| Google Calendar `extendedProperties.private.starkKey` | stored on every assignment event already in your calendar. Renaming it would make the sync miss them and add duplicates. Kept as a named constant `CAL_KEY = "starkKey"` with this note |
| history: `messages`, `action_log`, `router_log`, `calendar_log` text rows that mention Jarvis / STARK | history. Persona ids are read through `norm()` |
| git history, tag `pre-rename`, old commit messages | never rewrite history |
| `~/.config/hypr.conf-backup/` (pre-Lua rescue config, untracked, with its own `stark-*.sh` copies) | a frozen emergency config that only calls its own copies. Touching it risks the one thing it is for |
| existing `~/Pictures/Screenshots/stark-*.png`, `heroic/config.json.bak-pre-stark` | your files / backups |
| `/etc/ananicy.d/…LOSTARK.exe`, "Friday" in `/etc/security/{time,group}.conf` | third party |
| `.local/bin/stark-rescue` (symlink), `stark` fish shim, `jarvis` shim | as requested |
| `~/.claude/settings.json` (two lines mention `.config/jarvis`), memory files | not mine to change without asking: I'll show you the edit for `settings.json` (§8). Memory files: per your instruction |

### (d) Needs sudo: §6.

## 3. Stage B audit: notifications

- **What shows desktop notifications:** **mako 1.11** (started from `autostart.lua`, an uncommitted line). Its config `~/.config/mako/config` is **untracked**, hard-codes the STARK cyan (`#4fd8ff`), and is not skinned at all. There is no Quickshell `NotificationServer`. `fr.emersion.mako.service` and `org.kde.plasma.Notifications.service` are D-Bus-activatable.
- **DND:** mako mode `do-not-disturb`. Set by `stark-game` (combat mode, `gameNotify`) and read by `Indicators.qml` (the bar's bell icon, polled with `makoctl mode`).
- **History:** only mako's own (`makoctl restore`); there is none in the control center.
- **Who sends:** apps (Discord etc.), `stark-shot` when the HUD isn't running (`notify-send -a STARK`). Jarvis sends none.
- **HUD toasts (not D-Bus):** `JarvisToast` (the persona panel, which also shows `JarvisState.alert`: timers, reminders, **the fingerprint-stuck alert from `FprintWatch`**), `GameToast` (combat banner), `ShotToast` (capture saved), `Osd`.

**Proposal:** a `Notifications.qml` singleton with Quickshell's `NotificationServer` (QS 0.3.2 has it):
actions, app icon, image, body markup, replace-id, grouping by app (newest on top, "+N"), per-urgency
timeout (critical stays), DND (`notifications dnd on|off|toggle` IPC; `alchemos-game` and `Indicators`
switch over from `makoctl`), and an in-memory history for `notifications restore` / Super+Shift+N.
The card is a skin component `notifCard`. The base `HoloNotifCard.qml` draws today's mako look 1:1
(dark glass, 1 px primary border, red for critical), so LEGACY looks as it does now. ALCHEMOS gets
`AlchemNotifCard.qml`: an engraved frame (Style tokens), a sigil drawn on entry ("ignite"), a dissolve
on exit (solve), urgency mapped to metals (low silver, normal gold/brass, critical molten red glow),
a ☉ / ☽ sigil when the app name is the active persona's, and `Style.fonts` roles. Shown on the
main-role screen (`Roles`), never while `LockState.doors !== "open"` (held, then shown after unlock).
Battery saver / `Perf`: no blur or glow, a fade instead of the dissolve.

mako is no longer started at login, but it stays installed. `alchemos-hud.sh` stops a running mako
before starting qs. If qs is down, D-Bus activation brings up mako as the fallback, so Discord never
hangs. qs takes the name back on its next start. I'll test this during Stage 3: Quickshell may not
replace an existing owner; if it can't, the hud script hands over first.

## 4. Stage C audit: screenshot effect

How it works today:

1. `Shot.take()` makes the overlays transparent (opacity binding, not unmapping).
2. 50 ms later it closes the pop-ups; 70 ms after that it runs `stark-shot <mode> --json` (grim / slurp; annotate detaches satty after saving).
3. When the JSON comes back, it plays `shutter.wav`, then `serial++` triggers:
   - `ShotFlash.qml`: one overlay per covered monitor, 700 ms. A flash, then four brackets snap in from 22 px, a 2 px outline, a scan line with an 80 px trail sweeping down, and a `CAPTURED · W×H` readout. No Hyprland fade (`rules.lua` no_anim). Battery saver: none of it.
   - `ShotToast.qml`: the toast.

The capture is already finished before anything draws, so the effect can't end up in the picture or
delay it.

**Proposal:** the effect becomes a skin component `shotEffect`, driven by the same `t`, `box`, `calm`, `last`.
The current code moves to `HoloShotEffect.qml` unchanged, so LEGACY stays the same (a new baseline is
rendered from today's code before the move, then compared). ALCHEMOS gets `AlchemShotEffect.qml`,
about 1.1 s:

1. **Frozen frame:** the saved PNG, cropped to this monitor, sits under the effect. It plays on the captured image even if the screen changes beneath.
2. A transmutation-circle rim traces the region's border clockwise, with corner sigils (`Style.corners`).
3. A molten-gold (Aurum / warm presets) or quicksilver (cool presets: colour from `Theme.primary`) front sweeps diagonally and "fixes" the image (*coagula*): a heat shimmer ahead of it, cooled metal behind.
4. A seal stamps in the centre: the active preset's sign in an engraved ring, `COAGULATUM · W×H` in the label font.
5. Everything dissolves.

Region, window, screen and annotate all work the same way, across all three monitors (one overlay
per screen, each showing its crop). Battery saver: only the seal stamp (250 ms, no glow or shimmer).
The skin check renders it at fixed `t` values.

## 5. Commit order (Stage 2)

Each commit then has to pass: `qs` starts with no warnings or errors in the log, `check_skins.sh`
passes, `hyprctl configerrors` is empty, the services are active, and `journalctl --user -t alchemos-hud`
(or `stark-hud` before C4) is clean. Any commit that touches `.config/orrin` also runs
`tools/check_all.sh` (the hook). `--no-verify` is never used.

| # | commit | contents |
| --- | --- | --- |
| C0 | (your pending work) | per §1 |
| — | stop services | `stark-jarvis stop`, `pkill -f 'stark-govee daemon'` (the strip goes dark briefly) |
| C1 | **Repo: AlchemOS** | `mv ~/.stark-os ~/.alchemos`, `alc` function + `stark` shim, hooks dir + `core.hooksPath`, filter rename, `info/*` paths. `gh repo rename alchemos` + `remote set-url`, test push |
| C2 | **Scripts and binaries** | `hypr/stark-*.sh` → `alchemos-*`, `.local/bin/stark-*` → `alchemos-*`, config dirs (vpn, game, cursor), govee, env vars, layer namespaces + `rules.lua`, journal tag, runtime/state paths, icon theme, kitty theme, lock backgrounds. Every caller (`hypridle.conf`, `lid.sh`, `binds.lua`, `autostart.lua`, `uwcs.fish`, QML) in the same commit. `stark-rescue` symlink; temporary `stark-govee` symlink |
| C3 | **Hyprland modules** | `hypr/stark/` → `hypr/alchemos/`, loader, `install.fish`, `display-profile.lua` path in QML. `hyprctl reload` + `configerrors` |
| C4 | **Quickshell + IPC** | `stark` → `alchemos` IPC with all callers (`binds.lua`, the lock script, actions). QML file renames (`Jarvis*` → `Orrin*`), skin persona-key aliasing, `Theme.qml` settings migration, widget type alias, skincheck mock + `pin.py` |
| C5 | **Agent: Orrin** | `mv` config + data + state dirs, venv shebangs, `orrin.py` / CLI / `jarvis` shim / `orrinctl`, `orrin.service` (remove the old unit, `daemon-reload`), `jarvis`/`jarvisapp`/`jarviscontrol` IPC → `orrin*` (lands with C4's QML: **C4 and C5 are one commit** if the gate can't pass between them), MCP `alchemos` server, `orrin_db`, keyring fallback + `orrin secrets migrate`, persona ids, prompt base names, tests. `check_all.sh` must pass |
| C6 | **System files** | renamed `hypr/system/*` sources, `install.fish` / `fprint-install.fish` paths. Then **you run the §6 sudo block**; verify; drop the temporary symlinks and the old fprint tag |
| C7 | **README + docs** | new README (AlchemOS, sun/moon, solve et coagula; LEGACY exists, no unlock; no secrets, IPs or emails; MIT-ready wording), `.config/orrin/README.md`, `SKINS.md`, this plan marked done. Drop the Python old-key fallbacks |
| — | leftover grep | every remaining hit must be on the KEEP list |
| C8+ | Stage 3 notifications, Stage 4 screenshot | own commits, same gate. `SKINS.md` updated |

## 6. Sudo block (one block, for you to run or approve)

```fish
# now, before Stage 2
sudo snapper -c root create -d pre-alchemos-rename

# after C6 (reversible: the old files' sources are in tag pre-rename; pam keeps a .pre-alchemos copy)
set h ~/.config/hypr/system
sudo install -m 755 $h/alchemos-fprintd-sleep /usr/lib/systemd/system-sleep/alchemos-fprintd
sudo install -m 755 $h/alchemos-thaw-sleep    /usr/lib/systemd/system-sleep/alchemos-thaw
sudo rm /usr/lib/systemd/system-sleep/stark-{fprintd,thaw,govee}    # stark-govee: redundant, see Outcome
sudo install -m 755 $h/alchemos-fprint-reset /usr/local/bin/alchemos-fprint-reset
sudo rm /usr/local/bin/stark-fprint-reset
sudo install -D -m 644 $h/logind-alchemos.conf /etc/systemd/logind.conf.d/alchemos.conf
sudo rm /etc/systemd/logind.conf.d/stark.conf
sudo cp /etc/pam.d/hyprlock /etc/pam.d/hyprlock.pre-alchemos
sudo install -m 644 $h/hyprlock.pam /etc/pam.d/hyprlock      # comment-only change; diff shown first
sudo systemctl disable stark-govee-power.service
sed -e "s|@USER@|$USER|g" -e "s|@HOME@|$HOME|g" ~/.config/govee/system/alchemos-govee-power.service | sudo tee /etc/systemd/system/alchemos-govee-power.service >/dev/null
sudo rm /etc/systemd/system/stark-govee-power.service
sudo systemctl daemon-reload
sudo systemctl enable --now alchemos-govee-power.service      # --now plays the boot animation once
# optional: sudo sed -i 's/# Windows C: (STARK OS gaming/# Windows C: (AlchemOS gaming/' /etc/fstab
```

logind reads `logind.conf.d` on restart. Rather than restart logind in a live session, the change
(same contents, new name) takes effect at the reboot in the test checklist. The sleep hooks and
`/usr/local/bin` work at once. The PAM file is read on every auth, so test the lock straight after.
fprintd is never touched here (never kill it under hyprlock).

## 7. Rollback

- **One commit:** `alc revert <sha>` (forward only, history untouched), plus the matching `mv` back for any moved data dir.
- **Everything:** `alc checkout pre-rename -- .` then commit as "Revert AlchemOS rename". Then:
  - `mv ~/.alchemos ~/.stark-os` (or keep the name, the shim covers it)
  - `mv ~/.config/orrin ~/.config/jarvis` and `~/.local/share/orrin ~/.local/share/jarvis` (shebangs rewritten back), or extract the tarball
  - `gh repo rename stark-os`
- **Keyring:** the old `jarvis:` entries stay until `--prune`, so the pre-rename code still finds its tokens.
- **System:** reverse the sudo block (`.orig` / `.pre-alchemos` copies, old unit from the tag) or `snapper undochange` on the `pre-alchemos-rename` snapshot for `/etc` and `/usr`.
- **Settings:** `settings.json.alchemos-bak` is written by the migration before its first write.

## 8. Questions before "go"

1. **Uncommitted work (§1):** commit those five items as separate commits first? Or should I leave some of them out?
2. **Govee sleep hook:** `/usr/lib/systemd/system-sleep/stark-govee` is live but untracked, and `install.fish` deletes it. Keep it (track it + fix the installer) or drop it?
3. **Names:** `alc` (git), `orrinctl` (service), `orrin` (+ `jarvis` shim), persona ids `orrin`/`selene`, MCP server `alchemos`. Any changes?
4. **`~/.claude/settings.json`:** two lines in the permissions text mention `.config/jarvis`. Update them to `.config/orrin`?

## 9. Test checklist (after the finish)

- [ ] reboot + login: no Hyprland error bar, HUD up, `orrin.service` active, strip boot animation
- [ ] lock / unlock: fingerprint, then password; `faillock --user $USER` stays clean
- [ ] lid close docked (nothing happens) and undocked (doors → lock → screen off → suspend → wake → fingerprint)
- [ ] `stark-rescue` and `alchemos-rescue status` from a TTY (Ctrl+Alt+F3), and the rescue while locked
- [ ] "hey Orrin" + a voice command; "hey Selene"; `jarvis --text "what time is it"` (shim)
- [ ] Spotify `orrin spotify status`, Google agenda widget, Outlook feed: all without re-auth
- [ ] Govee: boot, lock, unlock, sleep/wake animations
- [ ] VPN toggle (control center + `alchemos-vpn status`)
- [ ] screenshots: region / screen / window / annotate on all three monitors, in both skins, plus battery saver
- [ ] `notify-send -u low|normal|critical` in both skins, with an action (`notify-send -A ok=OK`), DND in combat mode, while locked (held until unlock), undocked (laptop screen)
- [ ] Super+Shift+K skin swap both ways: LEGACY looks exactly as before
- [ ] `alc status`, `alc push`, `stark status` (prints the notice)


## Outcome (2026-11-13)

Decisions after "go": the pending work was committed first (C0); the names in §8 were approved as
proposed; `~/.claude/settings.json` now points at `.config/orrin`.

Changes from the plan:

- **Govee sleep hook dropped, not renamed.** `/usr/lib/systemd/system-sleep/stark-govee` was redundant:
  the running daemon holds a logind sleep *delay* inhibitor and sets the dim glow in `before_sleep()`
  (journal: `suspend: dim glow held`). The hook's `pre` always logged "strip not reachable" (Wi-Fi is
  already down by then), and the daemon ignores its `post` "wake" ("resume is handled via logind now").
  `install.fish` deletes it; the sudo block removes it.
- **C4 / C5 split** as planned: C4 only renamed the HUD side (stark IPC, `Orrin*` QML); everything shared
  with the agent (keys, ids, `jarvis*` IPC, widget type) landed in C5 together.
- **Persona ids** are `orrin` / `selene` everywhere; LEGACY's `skin.json` keeps `jarvis` / `friday` and
  both sides normalize it (`Skin.qml` `normPersonas`, `persona.py` `norm_skin`). The system prompt is
  ORRIN / SELENE on AlchemOS, and LEGACY turns get the `[STARK OS · JARVIS · FRIDAY]` names tag.
- **Diagnostics wall host name** (`user@stark`) became the skin text key `host`: base "stark" (so LEGACY
  is unchanged), ALCHEMOS "alchemos".
- **Data migrations** (all automatic, values kept): settings keys (`Theme.qml` `migrateNames`, backup
  `settings.json.alchemos-bak`), `orrin.db` roles / personas, the usage store's source key, the
  `widgets.json` type, the wake-model metadata, the keyring (copied; old entries kept until
  `orrin secrets migrate --prune`).
- All 8 venvs (agent, pocket, 5 tts-lab, wake-train) had their shebangs / `pyvenv.cfg` rewritten.

Left for you:

1. The sudo block in §6 (from `set h ~/.config/hypr/system` on; the snapper line is done).
2. After it: tell me (or do it yourself) to drop the transition fallbacks: `FprintWatch.qml` and
   `alchemos-rescue` read the `stark-fprint-reset` journal tag too, and `alchemos-fprint-reset`
   falls back to `/usr/local/bin/stark-fprint-reset`; plus remove the untracked `~/.local/bin/stark-govee`
   symlink.
3. Once everything has worked for a while: `orrin secrets migrate --prune`.
4. Heroic keeps its theme choice in its own storage: pick "alchemos" once in Heroic → Settings.

Leftover grep (tracked files, LEGACY excluded): every remaining stark / jarvis / friday hit is one of:
the spoken / wake-word names (`hey_jarvis`, `hey_friday`, "hey Jarvis", whisper spellings, router
example phrases, FILLER / TRAILER regexes), the weekday Friday, the migration code that reads the old
names (settings keys, keyring prefix, DB rows, persona aliases, widget type, the `stark` / `jarvis`
shims), LEGACY's names (`[STARK OS · JARVIS · FRIDAY]`, base persona / host text, STARK OS preset
aliases like MARK III → IRON, "switch to the stark theme"), the Google Calendar `starkKey` property and
the existing "STARK – Assignments" calendar, the installers' clean-up of the pre-AlchemOS files and
the temporary fprint fallbacks above, and test labels.
