#!/bin/bash
# One model of the checkpoint comparison (tools/eval/model_eval.py) on a cluster GPU node: fir_eval.sh <model>
# (fir_eval.sh build only builds the venv, on a CPU node).
# Builds the MIDI-GPT source pushed to $SCRATCH/midigpt-eval/src into a venv once (shared by the matrix jobs).
set -euo pipefail
MODEL=$1
E=$SCRATCH/midigpt-eval; V=$SCRATCH/.venvs/midigpt-eval
module load StdEnv/2023 gcc python/3.12 cuda/12.6 cmake arrow
mkdir -p "$SCRATCH/.venvs" "$E/out"
(   flock 9
    if [ ! -f "$V/.ok" ]; then
        rm -rf "$V"; python -m venv "$V"; . "$V/bin/activate"
        pip install --upgrade pip
        pip install torch numpy tqdm huggingface_hub safetensors symusic
        pip install --no-build-isolation scikit-build-core pybind11 2>/dev/null || pip install scikit-build-core pybind11
        pip install "$E/src"
        touch "$V/.ok"
    fi
) 9>"$SCRATCH/.venvs/.midigpt-eval.lock"
[ "$MODEL" = build ] && exit 0
. "$V/bin/activate"
export HF_HOME=$E/hf PYTHONUNBUFFERED=1
python -c "import torch, midigpt; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), midigpt.__file__)"
case "$MODEL" in                     # the Nibi checkpoints, pushed to $E/checkpoints
    prism_medium_final)     MODEL="$MODEL=$E/checkpoints/prism_medium-final.safetensors" ;;
    prism_medium_final_grammarfix) MODEL="$MODEL=$E/checkpoints/prism_medium-final.safetensors" ;;
    expressive_medium_272k) MODEL="$MODEL=$E/checkpoints/expressive_medium-step272000.safetensors" ;;
    expressive_medium_272k_fix) MODEL="$MODEL=$E/checkpoints/expressive_medium-step272000.safetensors" ;;
    yellow_large)           MODEL="$MODEL=$E/checkpoints/yellow_large-final.safetensors" ;;
esac
python tools/eval/model_eval.py --model "$MODEL" --data "$SCRATCH/MIDI-GPT/data/v2.0.0/test" --out "$E/out" --pieces 64
