#!/usr/bin/env bash
# Training environment for a custom openWakeWord model ("hey friday"), CPU only.
# Everything big lives in ~/.local/share/jarvis/wake-train (untracked): its own venv
# (torch etc. stay out of Jarvis's venv), piper-sample-generator + its LibriTTS-R model,
# room impulse responses, background audio, and the precomputed negative features.
#
#   tools/wakeword/setup.sh          # idempotent; re-run to resume a broken download
#   tools/wakeword/train.sh          # then train (see there)
#
# Negative features: openWakeWord's ACAV100M set is 17 GB (2000 h). Only the first
# NEG_GB of it is fetched with an HTTP range request and the .npy header is rewritten
# for the shorter array: ~2 GB ≈ 650k windows ≈ 230 h of speech, music and noise.
set -euo pipefail
W=${WAKE_TRAIN_DIR:-$HOME/.local/share/jarvis/wake-train}
NEG_GB=${NEG_GB:-2}
HF=https://huggingface.co/datasets
mkdir -p "$W"/{data,models}
cd "$W"

if [ ! -x .venv/bin/python ]; then
    uv venv --python 3.11 .venv
fi
PY=.venv/bin/python
if ! $PY -c "import torch, openwakeword, piper_phonemize, audiomentations, torch_audiomentations" 2>/dev/null; then
    uv pip install --python $PY --index-url https://download.pytorch.org/whl/cpu torch torchaudio
    uv pip install --python $PY "openwakeword==0.6.0" piper-phonemize-cross onnxruntime \
        audiomentations torch-audiomentations acoustics mutagen torchinfo torchmetrics \
        "speechbrain<1" pronouncing deep-phonemizer webrtcvad-wheels "scipy<1.15" pyyaml tqdm \
        "numpy<2" soundfile datasets
fi

# piper-sample-generator (generates the synthetic "hey friday" clips) + its multi-speaker model
if [ ! -d piper-sample-generator ]; then
    # v2.0.0: the layout openWakeWord 0.6.0's train.py imports (generate_samples.py at the top)
    git clone --depth 1 --branch v2.0.0 https://github.com/rhasspy/piper-sample-generator
fi
PSG_MODEL=piper-sample-generator/models/en_US-libritts_r-medium.pt
if [ ! -s "$PSG_MODEL" ]; then
    curl -L --fail -o "$PSG_MODEL" \
        https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt
fi

# piper's LibriTTS-R voice as plain ONNX (904 speakers): gen_clips.py renders the synthetic clips with it.
# (piper-sample-generator's own .pt is a pickled module that torch >= 2.6 won't load with weights_only.)
mkdir -p data/piper
for f in en_US-libritts_r-medium.onnx en_US-libritts_r-medium.onnx.json; do
    [ -s data/piper/$f ] || curl -L --fail -o data/piper/$f \
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/$f"
done

# room impulse responses (MIT survey, 16 kHz)
if [ ! -d data/rir ] || [ -z "$(ls data/rir 2>/dev/null)" ]; then
    mkdir -p data/rir
    $PY - <<'EOF'
import json, urllib.request, os
api = "https://huggingface.co/api/datasets/davidscripka/MIT_environmental_impulse_responses/tree/main/16khz"
for f in json.load(urllib.request.urlopen(api)):
    name = os.path.basename(f["path"])
    out = os.path.join("data/rir", name)
    if not os.path.exists(out):
        urllib.request.urlretrieve("https://huggingface.co/datasets/davidscripka/MIT_environmental_impulse_responses/resolve/main/" + f["path"], out)
print("rir files:", len(os.listdir("data/rir")))
EOF
fi

# validation features (~11 h of mixed audio): the false-positive check during training
VAL=data/validation_set_features.npy
if [ ! -s "$VAL" ] || [ "$(stat -c %s "$VAL")" -lt 184836608 ]; then
    curl -L --fail -C - -o "$VAL" "$HF/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy"
fi

# negative training features: first NEG_GB of ACAV100M
NEG=data/acav100m_part.npy
if [ ! -s "$NEG" ]; then
    BYTES=$(( NEG_GB * 1024 * 1024 * 1024 ))
    curl -L --fail -r 0-$((BYTES - 1)) -o "$NEG.raw" \
        "$HF/davidscripka/openwakeword_features/resolve/main/openwakeword_features_ACAV100M_2000_hrs_16bit.npy"
    $PY - "$NEG.raw" "$NEG" <<'EOF'
import sys, numpy as np, numpy.lib.format as F
src, dst = sys.argv[1:]
with open(src, "rb") as f:
    ver = F.read_magic(f)
    shape, fortran, dtype = F._read_array_header(f, ver)
    off = f.tell()
import os
n = (os.path.getsize(src) - off) // (int(np.prod(shape[1:])) * dtype.itemsize)
a = np.memmap(src, dtype=dtype, mode="r", offset=off, shape=(n,) + tuple(shape[1:]))
out = F.open_memmap(dst, mode="w+", dtype=dtype, shape=a.shape)
for i in range(0, n, 100000):
    out[i:i + 100000] = a[i:i + 100000]
out.flush()
print("negative windows:", n, "of", shape[0])
EOF
    rm -f "$NEG.raw"
fi

# background audio for augmentation: ESC-50 (2000 five-second environmental clips: fans, keyboards,
# rain, voices in a crowd...), resampled to 16 kHz. Music and speech negatives come from the ACAV features.
BG=data/background
if [ ! -d "$BG" ] || [ "$(ls "$BG" | wc -l)" -lt 1000 ]; then
    mkdir -p "$BG"
    [ -s data/esc50.zip ] || curl -L --fail -o data/esc50.zip https://github.com/karolpiczak/ESC-50/archive/refs/heads/master.zip
    $PY - <<'EOF2'
import io, os, zipfile, numpy as np, soundfile as sf
from scipy.signal import resample_poly
z = zipfile.ZipFile("data/esc50.zip")
n = 0
for name in z.namelist():
    if name.endswith(".wav") and "/audio/" in name:
        a, sr = sf.read(io.BytesIO(z.read(name)), dtype="float32")
        if a.ndim > 1:
            a = a.mean(axis=1)
        a = resample_poly(a, 160, sr // 100)
        sf.write(os.path.join("data/background", os.path.basename(name)), (np.clip(a, -1, 1) * 32767).astype(np.int16), 16000)
        n += 1
print("background clips:", n)
EOF2
    rm -f data/esc50.zip
fi
echo "setup done in $W"
