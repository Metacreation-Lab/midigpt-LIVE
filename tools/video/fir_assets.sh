#!/bin/bash
# The panel's device assets on a cluster GPU node (tools/video/blender_panel_assets.py): fir_assets.sh [fields dir]
# renders the fields pushed to $SCRATCH/midigpt-assets/<fields dir> (default fields) into .../raw_<fields dir>
# (raw for the default). Fetches Blender like fir_render.sh.
set -euo pipefail
BV=4.5.14; BDIR=$SCRATCH/opt/blender-$BV-linux-x64
DATA=$SCRATCH/midigpt-assets
mkdir -p "$SCRATCH/opt"
(   flock 9
    if [ ! -x "$BDIR/blender" ]; then
        curl -sSfL "https://download.blender.org/release/Blender${BV%.*}/blender-$BV-linux-x64.tar.xz" | tar xJ -C "$SCRATCH/opt"
    fi
) 9>"$SCRATCH/opt/.blender.lock"
SRC=${1:-fields}
OUT=$DATA/raw; [ "$SRC" != fields ] && OUT=$DATA/raw_$SRC
"$BDIR/blender" -b -P tools/video/blender_panel_assets.py -- --fields "$DATA/$SRC" --out "$OUT" --samples 256 --device GPU
