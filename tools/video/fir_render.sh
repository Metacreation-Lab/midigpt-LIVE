#!/bin/bash
# Trailer plates on a cluster GPU node: fir_render.sh <cut>:<A-B>   (plan frames A..B, e.g. full:0-59)
# Fetches Blender (same LTS as the Mac) into $SCRATCH on first use; frames go to
# $SCRATCH/prism-data/midigpt-trailer/plates_v2/<cut>/ and existing frames are skipped.
set -euo pipefail
CUT=${1%%:*}; FRAMES=${1##*:}
BV=4.5.14; BDIR=$SCRATCH/opt/blender-$BV-linux-x64
DATA=$SCRATCH/prism-data/midigpt-trailer
mkdir -p "$SCRATCH/opt"
(   flock 9                                        # the sections start together: one of them downloads
    if [ ! -x "$BDIR/blender" ]; then
        curl -sSfL "https://download.blender.org/release/Blender${BV%.*}/blender-$BV-linux-x64.tar.xz" | tar xJ -C "$SCRATCH/opt"
    fi
) 9>"$SCRATCH/opt/.blender.lock"
"$BDIR/blender" -b -P tools/video/blender_trailer.py -- \
    --plan "$DATA/plan_$CUT.json" --tex "$DATA/ui3_hd" --out "$DATA/plates_v2/$CUT" \
    --frames "$FRAMES" --res 2560x1440 --samples 128 --device GPU
