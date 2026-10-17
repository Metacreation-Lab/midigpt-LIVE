#!/bin/bash
# Quit Max cleanly and reopen the device standalone, then wait for the dev
# bridge to answer. Quitting with "saving no" (instead of killing Max) avoids
# the "Recover edits?" prompt on the next launch.
#
#   tools/max_reload.sh [patch]      default: patchers/MIDI-GPT.amxd

set -uo pipefail
cd "$(dirname "$0")/.."
patch=${1:-patchers/MIDI-GPT.amxd}

if pgrep -x Max >/dev/null; then
    osascript -e 'tell application "Max" to quit saving no' >/dev/null 2>&1
    for _ in $(seq 1 20); do pgrep -x Max >/dev/null || break; sleep 0.5; done
    pgrep -x Max >/dev/null && { echo "Max did not quit (a dialog may be open)"; exit 1; }
fi

open -a /Applications/Max.app "$patch"
for _ in $(seq 1 30); do
    python3 tools/bridge.py eval 'initialized' 2>/dev/null | grep -q true && { echo "device up"; exit 0; }
    sleep 2
done
echo "no bridge reply (is .midigpt_dev present? is a dialog open in Max?)"
exit 1
