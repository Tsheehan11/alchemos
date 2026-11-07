#!/usr/bin/env bash
# Render every installed skin's components and the shared primitives offscreen (tools/skincheck), fail on
# any QML error or missing render, and compare against a skin's baseline/ if it has one.
#   check_skins.sh [-q]            every skin in ~/.config/quickshell/skins (incl. _template)
#   check_skins.sh --baseline ID   (re)capture skins/ID/baseline/ from the current code
# Needs a Wayland session (the renders use an unmapped-looking 1×1 layer surface; nothing shows).
set -uo pipefail
hud=$(cd "$(dirname "$0")/../.." && pwd)
here=$hud/tools/skincheck
quiet=""; baseline=""
[[ ${1:-} == -q ]] && quiet=1
[[ ${1:-} == --baseline ]] && baseline=${2:?skin id}
work=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/skincheck.XXXXXX")
trap 'rm -rf "$work"' EXIT
# a copy of the HUD with the mocks over the state singletons and the gallery as its shell
rsync -a --exclude '.git' --exclude 'baseline' --exclude 'tools' "$hud/" "$work/hud/"
cp "$here"/mocks/*.qml "$work/hud/"
cp "$here/shell.qml" "$work/hud/shell.qml"
cp "$here/WinStub.qml" "$work/hud/"
# the HUD's windows as plain Items, pinned (pin.py)
python3 -I "$here/pin.py" "$work"/hud/*.qml
# a fixed time, so clocks render the same every run
grep -rl 'SystemClock {' "$work/hud" --include='*.qml' | xargs -r sed -i -E \
    's/SystemClock \{ *id: *([a-zA-Z]+)[^}]*\}/QtObject { id: \1; property date date: new Date(2026, 0, 1, 10, 8, 30) }/' 
fail=()
skins=$(cd "$hud/skins" && ls -d */ 2>/dev/null | tr -d / )
[[ -n ${SKINCHECK_SKINS:-} ]] && skins=$SKINCHECK_SKINS      # e.g. a built-in id that has no folder
[[ -n $baseline ]] && skins=$baseline
for s in $skins; do
    out=$work/out/$s; mkdir -p "$out"
    log=$(SKINCHECK_SKIN=$s SKINCHECK_OUT=$out timeout 60 qs -p "$work/hud" --no-duplicate 2>&1)
    errs=$(echo "$log" | grep -E 'ERROR|caused by|Error:|TypeError|ReferenceError|is not a type|File not found|not found|Cannot assign|SKINCHECK FAIL' \
           | grep -v -E 'textinput|Socket' | head -8)
    echo "$log" | grep -q 'SKINCHECK done' || errs+=$'\n'"never finished"
    [[ -n $baseline ]] || echo "$log" | grep -q 'SKINCHECK ok namer' || errs+=$'\n'"the preset namer didn't run"
    n=$(ls "$out"/*.png 2>/dev/null | wc -l)
    if [[ -n $errs ]]; then fail+=("$s"); echo "FAIL skin $s ($n renders)"; echo "$errs" | sed 's/^/    /'; continue; fi
    if [[ -n $baseline ]]; then
        mkdir -p "$hud/skins/$s/baseline" && cp "$out"/*.png "$hud/skins/$s/baseline/" && echo "baseline $s: $n renders"; continue
    fi
    if [[ -d $hud/skins/$s/baseline ]]; then
        diff=$(python3 -I "$here/compare.py" "$hud/skins/$s/baseline" "$out")
        if [[ -n $diff ]]; then fail+=("$s"); echo "FAIL skin $s differs from its baseline:"; echo "$diff" | sed 's/^/    /'; continue; fi
    fi
    [[ -n $quiet ]] || echo "ok   skin $s ($n renders${baseline:+})$( [[ -d $hud/skins/$s/baseline ]] && echo ', matches baseline')"
done
[[ -n ${SKINCHECK_KEEP:-} ]] && { mkdir -p "$SKINCHECK_KEEP"; cp -r "$work/out/." "$SKINCHECK_KEEP/"; }
((${#fail[@]})) && { echo "RED: skins ${fail[*]}"; exit 1; }
[[ -n $quiet ]] && echo "skins ok"
exit 0
