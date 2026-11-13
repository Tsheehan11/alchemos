# Skins

A skin changes how the HUD looks, never what it does. Every feature, keybind, IPC call, setting and
assistant tool lives in the main tree and works in every skin. A skin is a folder:

```
~/.config/quickshell/skins/<id>/
    skin.json          everything the skin says (all keys optional)
    *.qml              optional component overrides named in skin.json
    cursor/            optional busy-cursor templates
    baseline/          optional reference renders the skin check compares against
```

Anything a skin leaves out comes from the **base**: today's hologram look (`Skin.qml` `base`,
`Style.qml`) with neutral wording. So a skin that ships only `skin.json` is still a complete, working
desktop, and a feature added to the main tree shows up in every skin without touching any skin.

Installed now:

| id | where | |
| --- | --- | --- |
| `alchemos` | this repo | the default: metals, ORRIN / SELENE, engraved look |
| `legacy` | private repo `Tsheehan11/alchemos-legacy`, cloned into `skins/legacy` (ignored here) | STARK OS. `"hidden": true` |
| `_template` | this repo | never listed (a leading `_`); copy it to start a skin |

## Make a skin

1. `cp -r ~/.config/quickshell/skins/_template ~/.config/quickshell/skins/nebula` and set `"id"` and `"label"`.
2. Fill in what you want to change. `_template/skin.json` lists every key with a note (`"//…"` keys are notes).
3. Switch to it: `qs ipc call skin set nebula`, or Settings → APPEARANCE → SKIN (shown once there is a choice).
4. Run the check: `~/.config/quickshell/tools/skincheck/check_skins.sh` (also part of `check_all.sh`
   and the pre-commit hook). It renders the skin's clock, lock scene, transition, the shared
   primitives and the HUD's own windows (background still and live, bar, launcher in two presets,
   carousel, OSD, control center) offscreen and fails on any QML error or a missing file.
   `SKINCHECK_KEEP=<dir>` keeps the PNGs. The windows render as plain Items with fixed state:
   `tools/skincheck/pin.py` rewrites them in the check's temp copy (`PanelWindow` → `WinStub`,
   Hyprland and the state singletons → `mocks/`, `Math.random()` → a fixed value per call site,
   endless spins stopped), so a baseline only changes when the look does.

## What a skin provides

| key | what | read by |
| --- | --- | --- |
| `label`, `hidden` | name on the SKIN row; listed only after unlocking | `Skin.listed` |
| `osName` | what the assistant calls the desktop ("AlchemOS") | `orrin/core/persona.py` |
| `presets`, `aliases` | built-in colour presets (`name`, `glyph`, `primary`, `secondary`, `background`) and other names for them | `Theme`, Orrin `set_theme` |
| `personas` | display `name` / `call` / `dotted` / `glyph` / `idle` / `starting` / `accent` for `orrin` and `selene` (ids, wake words and voices stay; a skin keyed by the pre-AlchemOS ids `jarvis` / `friday` reads the same, here and in `voices` / `voiceRouting`) | `OrrinState`, `persona.py` |
| `text` | the HUD's wording (`host`: the diagnostics wall's user@host name; the bar's corner sign shows the active preset's sign, else `mark`, and its name): bar, panel titles, lock / unlock / power-down messages (`{name}` = the greeting name), power menu title, hyprlock title, denied text, placeholder (`lockPrompt`) and fingerprint lines (`fprintReady`, `fprintPresent`), lock glyph, bar mark, transition title | everywhere via `Skin.text` |
| `glyphs` | `ring`: signs round the clock, lock seal and transition (any count, `[]` = bare); `sun`: the seal's centre. The clock's ring (the preset wheel) also carries the custom presets' signs (`Theme.customSigns`: the 6 most recently saved + the one in use) | default clock / scene / transition |
| `style` | tokens for the shared components (below) | `Style.qml` |
| `components` | `clock`, `scene`, `transition`, `backdrop`, `launcherLook`, `carouselStage`, `carouselPanel`, `notifCard`, `shotEffect`: QML files in the skin folder replacing the defaults | `Skin.component(name)` |
| `cursor` | a folder with `wait.svg` / `progress.svg` templates (placeholders as in `alchemos-cursor/src`) | `alchemos-cursor/build.sh` |
| `namer` | how SAVE AS PRESET suggests a name and glyph for new colours | Settings |
| `voices` | default voice / speed / pitch / effect per persona | Theme, Settings |
| `voiceRouting` | what the AUTO effect picks per persona and output: `{ orrin: { headphones, speaker, btSpeaker }, selene: {…} }` (base: SUIT on headphones, HOLOGRAM on any speaker; ALCHEMOS: ORRIN CHAMBER / ALEMBIC / RESONANT, SELENE RESONANT / ALEMBIC / RESONANT) | `orrin/core/effects.py` routing(), Settings hint |

### Style tokens

| token | base | meaning |
| --- | --- | --- |
| `mono` | JetBrainsMono Nerd Font | data, labels, body text |
| `display`, `displayCaps`, `displayScale` | mono, false, 1 | headings: face, small caps, size |
| `fonts` | every role = `mono` (display = `display`) | font roles: `display`, `numeric` (clocks, big numbers), `label` (short caps labels), `body` (running text), `mono` (data), `glyph` (a lone mark; base Noto Sans, the face Qt fell back to), `signs` / `signs2` (featured signs), `field` (hyprlock's password field; base Sans), `prose` (sentences people read: notification bodies; base = `body`). Every Text names one (`tools/fontcheck/fontcheck.py`, part of the skin check); hyprlock's labels take `label` / `numeric` |
| `numerals` | `arabic` | `arabic` · `roman`: workspace seals, launcher keys, carousel numbers (`Style.numeral(n)`); readouts stay Arabic |
| `icons` | `{}` | name → SVG in the skin folder (`SkinIcon.qml`: `currentColor` takes the colour; `{{l1}}`–`{{l3}}` level arcs, `{{fy}}` a fill's top, `{{on}}`, `{{chg}}`). Names: cpu gpu ram temp battery wifi wifi-off bluetooth volume volume-mute mic mic-off vpn bell power. Without one, the base's text / glyph stays |
| `barIndicators` | `[]` | extra status icons at the bar's right end, in order: wifi bluetooth volume mic bell (live state: `Indicators.qml`) |
| `tabular` | false | the numeric face has proportional figures: `NumText` reserves the widest width so numbers don't shift |
| `frame` | `holo` | `holo` corner brackets · `engraved` double line with notched corners |
| `texture` | `holo` | `holo` scanlines / grid · `grain` · `none` |
| `grain`, `grainDark` | 0, 0 | grain strength 0..1; `grainDark` applies on very dark presets |
| `glow` | 1 | halo multiplier |
| `corners` | `[]` | four glyphs for engraved corner notches (TL, TR, BL, BR) |
| `divider` | `""` | glyph at a divider's centre |
| `gauge` | `ring` | `ring` · `astrolabe` |
| `metalRule` | false | a brushed-metal rule beside headings, in the preset's colour |
| `surface` | 0 | 0 glass … 1 stone plate (opacity unchanged) |
| `lockLayout` | `{ title: 290, clock: 16, date: -34, field: -280, prompt: -335, battery: [-30, 20] }` | where hyprlock's words sit on the main screen: y offsets from its centre (up = +); `{ "outside": n }` = n px beyond the lock seal's outer ring (`Style.sealRadius(h) + sealRim`, the default scene's great circle), above (n > 0) or below (n < 0), so they keep clear of it at any screen height. `battery`: [x, y] from the bottom-right corner. Filled into `hyprlock.template.conf`'s `__Y_*__` / `__BATTERY_POS__` by Theme |

Components read `Style.<token>`; nothing outside `Style.qml`, `Skin.qml` and `skins/` names a skin.

### Component overrides

Start from the default (`AlchemCircle.qml`, `VaultScene.qml`, `TransmuteTransition.qml`,
`HoloBackdrop.qml`, `HoloLauncherLook.qml`, `HoloCarouselStage.qml`, `HoloCarouselPanel.qml`, `HoloNotifCard.qml`, `HoloShotEffect.qml`), keep its properties (they're how the HUD drives it), and add `import "../.."` under `import QtQuick` so it can
reach the HUD's singletons. Components are loaded through `Qt.resolvedUrl` inside the shell; never
build a `file://` URL to them (it would load a second copy of every singleton).

**backdrop** (the desktop background, hosted by `GridBackground.qml` in a background-layer window)
gets `modelData` (the screen), `t` (seconds off the shared Perf clock, frozen while it shouldn't
animate: windows over it, locked, combat mode, battery saver), `live`, `res` (1, or 0.5 on the laptop
panel and in battery saver: draw textures at that scale, the iGPU's memory is system RAM) and
`activity` (0..1, the assistant at work, else CPU load). Draw anything heavy once into a texture and
only move it with `t`; never run an animation of its own. ALCHEMOS: `skins/alchemos/AlchemBackdrop.qml`.

**launcherLook** (what the Super+Space launcher draws; `Launcher.qml` keeps the keys, the branch
geometry, the spiral open, launching and the hit areas over the nodes) gets `win` (apps, selected,
current, spread, t, visible, branchOf / tierOf / nodeSize / branchCount) and `core` (cx, cy, nx(i),
ny(i): where app i is now) as required properties, and may set `openMs` / `openEasing` (how the spiral
opens) and `opened()` (called as it opens). ALCHEMOS: `skins/alchemos/AlchemLauncherLook.qml`.

**carouselStage** / **carouselPanel** (the Super+Tab carousel; `Overview.qml` keeps the ring geometry,
keys, clicks and the front panel's glow layer): the stage draws the floor and header under the panels
and gets `ov` (ids, n, pos, step, ringR, ringRy, panelW, cx, cy, appear, focusedHere, modelData = the
screen); a panel draws one workspace inside its placed, turned box and gets `ov` and `panel`
(modelData = workspace id, index, front, current, wins, peeked, mon, k), and may set `glowColor`,
`glowBlur`, `glowOpacity`. Put `CarouselWindows { ov; panel }` inside it for the window previews (it
holds the capture-safety rules). ALCHEMOS: `skins/alchemos/AlchemCarousel*.qml`.

**notifCard** (one desktop notification; `Notifications.qml` owns the D-Bus name, the queue, grouping,
timeouts, do-not-disturb and the lock hold, and `NotifPopups.qml` stacks the cards top-right on the
main-role screen) gets `n` (`nid`, `app`, `summary`, `body` in simple markup, `icon`, `image`, `urgency`
low / normal / critical, `actions` [{ id, text }], `count` for a group, `persona` orrin / selene / ""),
`ctl` (`activate(nid)` for a click, `invoke(nid, id)`, `dismiss(nid)`), `closing` (play the exit; the row
goes after the card's `exitMs`), `calm` (battery saver: no glow or blur, short motion) and `animated`
(false in the skin check: the settled look, no looping motion). It sizes its own `implicitHeight`. The
base is the look mako had (LEGACY). ALCHEMOS: `skins/alchemos/AlchemNotifCard.qml`: an engraved plate in
the urgency's metal (low quicksilver, normal the preset's metal, critical molten and breathing), a
medallion whose ring inscribes itself on arrival with ORRIN's ☉ / SELENE's ☽ for their own messages,
and a dissolve on the way out (`assets/dissolve.png` as a threshold mask). The skin check renders
`notifications` and `notifications-calm`.

**shotEffect** (what plays after a screenshot is saved; `Shot.qml` hides the HUD, `alchemos-shot`
captures, then `ShotFlash.qml` hosts this on every monitor the shot covers) gets `box` (this screen's part
of the shot, in its coordinates), `t` (0 → 1), `last` (the capture's JSON), `frame` (`source` + `clip`: the
saved PNG cropped to this screen, to play on a frozen image), `calm` (battery saver) and `main` (the
screen holding most of the shot), and sets `durationMs` and `calmMs` (0 = nothing in battery saver). The
capture is finished before it starts, so nothing it draws can end up in the shot or delay it. Draw with
GPU items (Rectangle, Shape, Image, gradients): a monitor-sized Canvas repaints on the GUI thread and
stalls. The base (LEGACY) is the hologram scan: flash, brackets, scan line, CAPTURED · W×H. ALCHEMOS:
`skins/alchemos/AlchemShotEffect.qml`: the region dims while a transmutation circle inscribes itself
(rim, corner element signs, inscribed circle), a molten-gold (warm presets) or quicksilver (cool) front
sweeps across and fixes the image (coagula), the preset's sign stamps a COAGULATUM seal, then the frozen
image gives way to the live screen; battery saver: the seal alone. The skin check renders `shot-trace`,
`shot-sweep`, `shot-seal` and `shot-calm`.

## How switching works

`cfg.skin` names the skin; the skin in use is read synchronously at start-up (no flicker), the list of
installed skins in the background. A missing skin falls back to `alchemos`, then to the base.
Switching saves the current look under the old skin (`cfg.skinPresets`), puts back the new skin's last
look, plays the new skin's transition, then pushes the theme to Hyprland, hyprlock (the lock pictures
are redrawn, their key includes the skin), kitty, VS Code, Heroic, the cursor and the Govee strip.
The assistant picks up the names on its next turn (a names tag, so its prompt cache stays warm).

`qs ipc call skin get | set <id> | toggle | swap | list` · Orrin `set_skin`. Once there's a second skin to pick (the hidden one after its first unlock:
`Skin.switchable`, the same rule as Settings' SKIN row): the control center's SKIN tile, the power
menu's SWITCH SKIN and Super+Shift+K (`skin swap`, which never unlocks) toggle too.

The transition plays once the incoming skin has landed (`Skin.current` is the new id), with its own
wording (`Skin.textOf(id)`); the skin check switches skins at the end of each run and fails if the
title isn't the incoming skin's. The assistant's reply names the incoming skin too.
