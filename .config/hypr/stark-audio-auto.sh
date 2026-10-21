#!/usr/bin/env bash
# STARK OS — auto audio routing.
# When a display with audio (TV/monitor over HDMI or DisplayPort) is plugged in,
# make it the default output and move playing apps to it. When it's unplugged,
# fall back to the laptop speakers. Only acts when what's plugged in changes,
# so picking an output by hand in Settings → AUDIO still sticks until the next plug/unplug.

exec 9>"${XDG_RUNTIME_DIR:-/tmp}/stark-audio-auto.lock"
flock -n 9 || exit 0   # already running

command -v jq >/dev/null || { notify-send "STARK audio" "jq missing: sudo pacman -S --needed jq"; exit 1; }

hdmi_live() {   # names of HDMI/DP sinks whose active port is actually plugged in
  pactl -f json list sinks 2>/dev/null | jq -r '
    .[] | select(.name|test("hdmi";"i")) | . as $s
    | select([.ports[]? | select(.name==$s.active_port and .availability!="not available")] | length > 0)
    | .name'
}

fallback() {    # laptop speakers (first non-HDMI hardware sink)
  pactl -f json list sinks 2>/dev/null | jq -r '
    [.[] | select(.name|test("^alsa_output";"i")) | select(.name|test("hdmi";"i")|not) | .name] | first // empty'
}

apply() {
  local live target
  live=$(hdmi_live)
  [[ "$live" == "$last" ]] && return
  last=$live
  if [[ -n "$live" ]]; then target=$(head -n1 <<<"$live"); else target=$(fallback); fi
  [[ -z "$target" ]] && return
  pactl set-default-sink "$target"
  for i in $(pactl list short sink-inputs | cut -f1); do pactl move-sink-input "$i" "$target"; done
}

last="__init__"
sleep 2   # let PipeWire settle at login
apply
pactl subscribe | while read -r line; do
  case "$line" in
    *"on card"*|*"'new' on sink"*|*"'remove' on sink"*|*"on server"*)
      sleep 0.5; apply ;;
  esac
done
