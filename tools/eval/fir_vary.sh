#!/bin/bash
# One shard of the Vary comparison (tools/eval/vary_eval.py) on a cluster GPU node: fir_vary.sh <shard>.
# Uses the venv fir_eval.sh builds.
set -euo pipefail
E=$SCRATCH/midigpt-eval; V=$SCRATCH/.venvs/midigpt-eval
module load StdEnv/2023 gcc python/3.12 cuda/12.6 arrow
. "$V/bin/activate"
export HF_HOME=$E/hf PYTHONUNBUFFERED=1
cd tools/eval
python vary_eval.py --model yellow_medium --data "$SCRATCH/MIDI-GPT/data/v2.0.0/test" --out "$E/vary" --pieces 40 --seeds 2 --shard "$1" --shards 4
