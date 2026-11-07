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
| `osName` | what the assistant calls the desktop ("AlchemOS") | `jarvis/core/persona.py` |
| `presets`, `aliases` | built-in colour presets (`name`, `glyph`, `primary`, `secondary`, `background`) and other names for them | `Theme`, Jarvis `set_theme` |
| `personas` | display `name` / `call` / `dotted` / `glyph` / `idle` / `starting` / `accent` for `jarvis` and `friday` (ids, wake word and voices stay) | `JarvisState`, `persona.py` |
| `text` | the HUD's wording: bar, panel titles, lock / unlock messages, hyprlock title and denied text, lock glyph, bar mark, transition title | everywhere via `Skin.text` |
| `glyphs` | `ring`: signs round the clock, lock seal and transition (any count, `[]` = bare); `sun`: the seal's centre | default clock / scene / transition |
| `style` | tokens for the shared components (below) | `Style.qml` |
| `components` | `clock`, `scene`, `transition`, `backdrop`, `launcherLook`, `carouselStage`, `carouselPanel`: QML files in the skin folder replacing the defaults | `Skin.component(name)` |
| `cursor` | a folder with `wait.svg` / `progress.svg` templates (placeholders as in `stark-cursor/src`) | `stark-cursor/build.sh` |
| `namer` | how SAVE AS PRESET suggests a name and glyph for new colours | Settings |
| `voices` | default voice / speed / pitch / effect per persona | Theme, Settings |

### Style tokens

| token | base | meaning |
| --- | --- | --- |
| `mono` | JetBrainsMono Nerd Font | data, labels, body text |
| `display`, `displayCaps`, `displayScale` | mono, false, 1 | headings: face, small caps, size |
| `frame` | `holo` | `holo` corner brackets · `engraved` double line with notched corners |
| `texture` | `holo` | `holo` scanlines / grid · `grain` · `none` |
| `grain`, `grainDark` | 0, 0 | grain strength 0..1; `grainDark` applies on very dark presets |
| `glow` | 1 | halo multiplier |
| `corners` | `[]` | four glyphs for engraved corner notches (TL, TR, BL, BR) |
| `divider` | `""` | glyph at a divider's centre |
| `gauge` | `ring` | `ring` · `astrolabe` |
| `metalRule` | false | a brushed-metal rule beside headings, in the preset's colour |
| `surface` | 0 | 0 glass … 1 stone plate (opacity unchanged) |

Components read `Style.<token>`; nothing outside `Style.qml`, `Skin.qml` and `skins/` names a skin.

### Component overrides

Start from the default (`AlchemCircle.qml`, `VaultScene.qml`, `TransmuteTransition.qml`,
`HoloBackdrop.qml`, `HoloLauncherLook.qml`, `HoloCarouselStage.qml`, `HoloCarouselPanel.qml`), keep its properties (they're how the HUD drives it), and add `import "../.."` under `import QtQuick` so it can
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

## How switching works

`cfg.skin` names the skin; the skin in use is read synchronously at start-up (no flicker), the list of
installed skins in the background. A missing skin falls back to `alchemos`, then to the base.
Switching saves the current look under the old skin (`cfg.skinPresets`), puts back the new skin's last
look, plays the new skin's transition, then pushes the theme to Hyprland, hyprlock (the lock pictures
are redrawn, their key includes the skin), kitty, VS Code, Heroic, the cursor and the Govee strip.
The assistant picks up the names on its next turn (a names tag, so its prompt cache stays warm).

`qs ipc call skin get | set <id> | toggle | list` · Jarvis `set_skin` · the app search's hidden word
toggles the hidden skin.
