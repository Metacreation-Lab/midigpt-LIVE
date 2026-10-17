#!/bin/bash
# Reload the device inside Live after patch changes: the running device
# deletes itself from its track (via the dev bridge), then Live re-inserts
# patchers/MIDI-GPT.amxd on that (now selected) track. Waits for the bridge and
# opens the device window.
#
#   tools/live_reload.sh                   device on track 0
#   tools/live_reload.sh <track>           device on another track (first device on it)
#   tools/live_reload.sh <track> <file>    load a different device file

set -uo pipefail
cd "$(dirname "$0")/.."
t=${1:-0}
device=${2:-patchers/MIDI-GPT.amxd}

# Close the old instance's window first: Live keeps a deleted device alive
# for Undo, and its window would otherwise stay open.
python3 tools/bridge.py eval "this.patcher.apply(function(o){ if(o.maxclass=='pcontrol') o.message('close'); return true;}); 1" >/dev/null || exit 1
python3 tools/bridge.py eval "var tr=new LiveAPI('live_set tracks $t'); new LiveAPI('live_set view').set('selected_track','id '+tr.id); var k=new Task(function(){ new LiveAPI('live_set tracks $t').call('delete_device',0); }); k.schedule(200); 1" >/dev/null || exit 1
sleep 2
open -a "Ableton Live 11 Suite" "$device"
for _ in $(seq 1 30); do
    if python3 tools/bridge.py eval 'initialized' 2>/dev/null | grep -q true; then
        python3 tools/bridge.py eval 'this.patcher.apply(function(o){ if(o.maxclass=="pcontrol") o.message("open"); return true;}); 1' >/dev/null
        # A device deleted earlier can keep reopening its old-size window
        # (Live holds it for Undo); close any device window ([main_window] or MIDI-GPT) that isn't 960 wide.
        osascript -e 'tell application "System Events" to tell process "Live"' \
                  -e 'repeat with w in (every window whose name is "[main_window]" or name is "MIDI-GPT")' \
                  -e 'if (item 1 of (get size of w)) is not 960 then click (first button of w whose subrole is "AXCloseButton")' \
                  -e 'end repeat' -e 'end tell' >/dev/null 2>&1
        echo "device up"
        exit 0
    fi
    sleep 2
done
echo "no bridge reply"
exit 1
