#!/usr/bin/env bash
# Train the "hey friday" wake word with openWakeWord's own pipeline (CPU), after setup.sh:
# gen_clips.py renders the synthetic clips, then train.py augments (RIRs + background) and trains.
#   tools/wakeword/train.sh            # all stages, timed → $W/out/timing.txt, log → $W/train.log
#   STAGES="--train_model" tools/wakeword/train.sh     # one stage again
# Then eval.py measures recall and false triggers per hour, and install.sh puts the model where
# Jarvis loads it (~/.local/share/orrin/wake/hey_friday.onnx).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
W=${WAKE_TRAIN_DIR:-$HOME/.local/share/orrin/wake-train}
PY=$W/.venv/bin/python
# --generate_clips is replaced by gen_clips.py (same folders; train.py skips generation when they're full)
STAGES=${STAGES:-"gen --augment_clips --train_model"}
mkdir -p "$W/out"
sed "s|{W}|$W|g" "$HERE/hey_friday.yml" > "$W/out/hey_friday.yml"
$PY -c "import openwakeword.utils as u; u.download_models(['hey_jarvis'])"   # melspectrogram + embedding models
cd "$W"
for st in $STAGES; do
    t0=$(date +%s)
    echo "== $st $(date -Is)"
    if [ "$st" = gen ]; then
        nice -n 10 "$HOME/.config/orrin/.venv/bin/python" "$HERE/gen_clips.py" --workers 8
        echo "gen $(( $(date +%s) - t0 )) s" | tee -a out/timing.txt
        continue
    fi
    # torch and onnxruntime each want every core; leave some for the desktop (and Jarvis)
    # augment: --overwrite, or a features file half-written by a crashed run makes it skip silently
    EXTRA=""; [ "$st" = "--augment_clips" ] && EXTRA="--overwrite"
    OMP_NUM_THREADS=12 nice -n 10 $PY -m openwakeword.train --training_config out/hey_friday.yml $st $EXTRA
    echo "$st $(( $(date +%s) - t0 )) s" | tee -a out/timing.txt
done
