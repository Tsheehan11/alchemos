#!/usr/bin/env bash
# STARK OS cursor theme.
#   build.sh <rrggbb> [animated|static] [24|32|48]
# Renders src/*.svg in that accent, builds an XCursor theme (rsvg-convert + xcursorgen)
# and a hyprcursor theme (hyprcursor-util, SVG) into ~/.local/share/icons/STARK-OS,
# points GTK / Qt / KDE / XWayland at it, and applies it live with `hyprctl setcursor`.
# Called by quickshell/Theme.qml whenever the accent, cursor size or busy animation
# changes. Builds are cached per colour (~/.cache/stark-cursor), so switching back to a
# theme seen before is a copy and a setcursor.
set -euo pipefail

THEME=STARK-OS
SIZES=(24 32 48)
SPIN_FRAMES=12          # busy cursors: the 1/3 arc turns 30° a frame
SPIN_MS=60

here=$(cd "$(dirname "$0")" && pwd)
src=$here/src
hex=${1:-}; hex=${hex#\#}; hex=${hex,,}
mode=${2:-animated}
size=${3:-24}
if [[ ! $hex =~ ^[0-9a-f]{6}$ || ! $mode =~ ^(animated|static)$ || ! $size =~ ^(24|32|48)$ ]]; then
    echo "usage: build.sh <rrggbb> [animated|static] [24|32|48]" >&2
    exit 2
fi

icons=${XDG_DATA_HOME:-$HOME/.local/share}/icons
cache=${XDG_CACHE_HOME:-$HOME/.cache}/stark-cursor
mkdir -p "$icons" "$cache"

# One build at a time; a queued call just runs after (Theme.qml already debounces)
exec 9>"$cache/.lock"
flock 9

# Any edit to the templates or this script invalidates the cache
ver=$(cat "$src"/* "$0" "$here/xcursorgen.py" | md5sum | cut -c1-8)
key=$hex-$mode-$ver
out=$cache/$key

make_xcursor() {
    if command -v xcursorgen >/dev/null; then command xcursorgen "$@"
    else python3 -I "$here/xcursorgen.py" "$@"; fi
}

# ── Build one cursor: XCursor file + hyprcursor source dir ──
# name template hot-x hot-y rotation aliases...
build_one() {
    local name=$1 tpl=$2 hx=$3 hy=$4 rot=$5; shift 5
    local w=$work/$name hc=$work/hc/hyprcursors/$name
    mkdir -p "$w" "$hc"
    [[ $rot == - ]] && rot=0
    local spins=(0)
    if [[ $mode == animated ]] && grep -q '{{SPIN}}' "$src/$tpl"; then
        spins=(); for ((i = 0; i < SPIN_FRAMES; i++)); do spins+=($((i * 360 / SPIN_FRAMES))); done
    fi
    local delay=$(( ${#spins[@]} > 1 ? SPIN_MS : 0 ))
    {
        echo "resize_algorithm = bilinear"
        awk -v x="$hx" -v y="$hy" 'BEGIN { printf "hotspot_x = %.4f\nhotspot_y = %.4f\n", x / 32, y / 32 }'
        for a in "$@"; do echo "define_override = $a"; done
    } > "$hc/meta.hl"
    : > "$w/conf"
    local i=0 s px
    for s in "${spins[@]}"; do
        sed -e "s/{{ACCENT}}/#$hex/g" -e "s/{{ROT}}/$rot/g" -e "s/{{SPIN}}/$s/g" "$src/$tpl" > "$hc/$name-$i.svg"
        if ((delay)); then echo "define_size = 0, $name-$i.svg, $delay"; else echo "define_size = 0, $name-$i.svg"; fi >> "$hc/meta.hl"
        for px in "${SIZES[@]}"; do
            rsvg-convert -w "$px" -h "$px" -o "$w/$px-$i.png" "$hc/$name-$i.svg"
            awk -v p="$px" -v x="$hx" -v y="$hy" -v f="$px-$i.png" -v d="$delay" \
                'BEGIN { printf "%d %d %d %s %d\n", p, int(x * p / 32 + 0.5), int(y * p / 32 + 0.5), f, d }' >> "$w/conf"
        done
        i=$((i + 1))
    done
    sort -n -s -k1,1 -o "$w/conf" "$w/conf"     # xcursorgen groups frames per size
    make_xcursor "$w/conf" "$work/theme/cursors/$name"
    for a in "$@"; do ln -sf "$name" "$work/theme/cursors/$a"; done
}

if [[ ! -f $out/.stark-build ]]; then
    work=$(mktemp -d "$cache/.work.XXXXXX")
    trap 'rm -rf "$work"' EXIT
    mkdir -p "$work/theme/cursors" "$work/hc"
    pids=()
    while read -r name tpl hx hy rot aliases; do
        [[ -z $name || $name == \#* ]] && continue
        # shellcheck disable=SC2086
        build_one "$name" "$tpl" "$hx" "$hy" "$rot" $aliases &
        pids+=($!)
    done < "$src/cursors.txt"
    for p in "${pids[@]}"; do wait "$p"; done     # fail the build if any cursor failed

    cat > "$work/hc/manifest.hl" <<EOF
name = $THEME
description = STARK OS holographic HUD cursors (#$hex)
version = 1
cursors_directory = hyprcursors
EOF
    hyprcursor-util --create "$work/hc" --output "$work" >/dev/null
    cp -r "$work/theme_$THEME/." "$work/theme/"
    cat > "$work/theme/index.theme" <<EOF
[Icon Theme]
Name=$THEME
Comment=STARK OS holographic HUD cursors (#$hex, $mode)
Inherits=Adwaita
EOF
    echo "$key" > "$work/theme/.stark-build"
    rm -rf "$out"
    mv "$work/theme" "$out"
    # Keep the dozen most recent colours
    ls -1dt "$cache"/*/ 2>/dev/null | tail -n +13 | xargs -r rm -rf
fi

# ── Install (swap the whole directory so a running app never sees half a theme) ──
dest=$icons/$THEME
changed=0
if [[ $(cat "$dest/.stark-build" 2>/dev/null) != "$key" ]]; then
    changed=1
    rm -rf "$icons/.$THEME.new" "$icons/.$THEME.old"
    cp -r "$out" "$icons/.$THEME.new"
    [[ -e $dest ]] && mv "$dest" "$icons/.$THEME.old"
    mv "$icons/.$THEME.new" "$dest"
    rm -rf "$icons/.$THEME.old"
fi
touch "$out"

# ── Point everything at it (files are only rewritten when a value changes) ──
# set_line <file> <regex matching the line> <replacement line> [line to insert after]
set_line() {
    local f=$1 re=$2 line=$3 after=${4:-}
    [[ -f $f ]] || return 0
    grep -qxF -- "$line" "$f" && return 0
    if grep -qE -- "$re" "$f"; then
        sed -i -E "s|$re.*|$line|" "$f"
    elif [[ -n $after ]] && grep -qE -- "$after" "$f"; then
        sed -i -E "\|$after|a $line" "$f"
    else
        printf '%s\n' "$line" >> "$f"
    fi
}

hypr=$HOME/.config/hypr/hyprland.conf
for v in XCURSOR_SIZE HYPRCURSOR_SIZE XCURSOR_THEME HYPRCURSOR_THEME; do
    val=$size; [[ $v == *THEME ]] && val=$THEME
    set_line "$hypr" "^env = $v," "env = $v,$val" "^# ── Environment"
done

for f in "$HOME/.config/gtk-3.0/settings.ini" "$HOME/.config/gtk-4.0/settings.ini"; do
    set_line "$f" "^gtk-cursor-theme-name=" "gtk-cursor-theme-name=$THEME"
    set_line "$f" "^gtk-cursor-theme-size=" "gtk-cursor-theme-size=$size"
done
xs=$HOME/.config/xsettingsd/xsettingsd.conf
set_line "$xs" "^Gtk/CursorThemeName " "Gtk/CursorThemeName \"$THEME\""
set_line "$xs" "^Gtk/CursorThemeSize " "Gtk/CursorThemeSize $size"
pkill -HUP -x xsettingsd 2>/dev/null || true

mkdir -p "$HOME/.icons/default"
printf '[Icon Theme]\nName=Default\nInherits=%s\n' "$THEME" > "$HOME/.icons/default/.index.tmp"
cmp -s "$HOME/.icons/default/.index.tmp" "$HOME/.icons/default/index.theme" \
    && rm "$HOME/.icons/default/.index.tmp" \
    || mv "$HOME/.icons/default/.index.tmp" "$HOME/.icons/default/index.theme"

# GTK apps (Zen, …) draw their own cursor and only reload it when the theme *name*
# changes, so a recolour goes STARK-OS → STARK-OS-reload (same cursors, via
# Inherits) → STARK-OS. Half a second apart, or the apps only see the last value.
reload=$icons/$THEME-reload
[[ -f $reload/index.theme ]] || { mkdir -p "$reload"; printf '[Icon Theme]\nName=%s-reload\nComment=Lets build.sh make GTK apps reload %s\nInherits=%s\nHidden=true\n' "$THEME" "$THEME" "$THEME" > "$reload/index.theme"; }
if command -v gsettings >/dev/null; then
    gtk=org.gnome.desktop.interface
    [[ $(gsettings get $gtk cursor-size) == "$size" ]] || changed=1
    if ((changed)) || [[ $(gsettings get $gtk cursor-theme) != "'$THEME'" ]]; then
        (gsettings set $gtk cursor-size "$size"; sleep 0.5
         gsettings set $gtk cursor-theme "$THEME-reload"; sleep 0.5
         gsettings set $gtk cursor-theme "$THEME") >/dev/null 2>&1 9>&- &
    fi
fi
if command -v kwriteconfig6 >/dev/null; then     # Dolphin and other KDE apps
    kwriteconfig6 --file kcminputrc --group Mouse --key cursorTheme "$THEME"
    kwriteconfig6 --file kcminputrc --group Mouse --key cursorSize "$size"
fi
if [[ -n ${DISPLAY:-} ]] && command -v xrdb >/dev/null; then   # XWayland: Steam, older Electron
    printf 'Xcursor.theme: %s\nXcursor.size: %s\n' "$THEME" "$size" | xrdb -merge 2>/dev/null || true
fi
# Apps started by systemd / D-Bus activation (and anything they spawn)
dbus-update-activation-environment --systemd XCURSOR_THEME="$THEME" XCURSOR_SIZE="$size" \
    HYPRCURSOR_THEME="$THEME" HYPRCURSOR_SIZE="$size" 2>/dev/null || true

# ── Live ──
if [[ -n ${HYPRLAND_INSTANCE_SIGNATURE:-} ]]; then
    hyprctl setcursor "$THEME" "$size" >/dev/null
fi
echo "$THEME #$hex $mode $size"
