#!/bin/bash
# One shard of the context-drop comparison (tools/eval/context_drop_eval.py) on a cluster GPU node:
# fir_ctxdrop.sh <model>:<window bars>:<shard>:<shards> (any Alliance cluster). Uses the venv fir_eval.sh builds.
set -euo pipefail
IFS=: read -r MODEL DIM SHARD SHARDS <<< "$1"
E=$SCRATCH/midigpt-eval; V=$SCRATCH/.venvs/midigpt-eval
bash tools/eval/fir_eval.sh build     # builds the venv once (locked), a no-op after that
module load StdEnv/2023 gcc python/3.12 cuda/12.6 arrow
. "$V/bin/activate"
export HF_HOME=$E/hf PYTHONUNBUFFERED=1
case "$MODEL" in
    prism_medium_final)     MODEL="$MODEL=$E/checkpoints/prism_medium-final.safetensors" ;;
    expressive_medium_272k) MODEL="$MODEL=$E/checkpoints/expressive_medium-step272000.safetensors" ;;
esac
python tools/eval/context_drop_eval.py --model "$MODEL" --dim "$DIM" --data "$SCRATCH/MIDI-GPT/data/v2.0.0/test" \
    --out "$E/ctxdrop" --pieces 96 --shard "$SHARD" --shards "$SHARDS"
