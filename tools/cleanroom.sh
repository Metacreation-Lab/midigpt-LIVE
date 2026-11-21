#!/bin/bash
# Make this Mac look like a first-time user's, for testing a release, then put it back.
#
#   tools/cleanroom.sh status    what a fresh user would not have, and which Max Live uses
#   tools/cleanroom.sh on        stash it all in ~/.midigpt-cleanroom/
#   tools/cleanroom.sh off       remove the test install and restore the stash
#
# What is stashed (each one hides a fresh-install bug on a dev machine):
#   ~/Documents/Max */Library/MIDI-GPT*    links to a checkout's javascript/ and media/: Max always
#                                          searches its Library folder, so every MIDI-GPT device finds
#                                          midigpt_node.js there and never extracts its own copy
#   <User Library>/MIDI-GPT                the installed release
#   ~/Library/Application Support/MIDI-GPT/live.json   remembered server URL, tag path, install dir
# The server venv (server/, server.conf, models.yaml) is left alone.
#
# In between, install the way a user does, with no server step:
#   ./install.sh --version 0.2.4 --no-server --yes                          # before the fix
#   python3 tools/build_release.py && ./install.sh --zip dist/MIDI-GPT-for-Live-$(cat VERSION).zip --no-server --yes
set -u
STASH="$HOME/.midigpt-cleanroom"
CONF_DIR="$HOME/Library/Application Support/MIDI-GPT"

user_lib() {
    local cfg
    cfg="$(ls -t "$HOME/Library/Preferences/Ableton"/Live*/Library.cfg 2>/dev/null | head -1)"
    local p
    p="$(grep -o '<ProjectPath Value="[^"]*"' "$cfg" 2>/dev/null | head -1 | sed 's/.*Value="//; s/"$//')"
    echo "${p:-$HOME/Music/Ableton}/User Library"
}

# the things a fresh user does not have: "<label>|<path>"
targets() {
    local d
    for d in "$HOME/Documents"/Max\ */Library/MIDI-GPT*; do
        [ -e "$d" ] || [ -L "$d" ] && echo "maxlib-$(basename "$(dirname "$(dirname "$d")")" | tr ' ' _)-$(basename "$d")|$d"
    done
    echo "userlib-MIDI-GPT|$(user_lib)/MIDI-GPT"
    echo "live.json|$CONF_DIR/live.json"
}

live_max() {
    local prefs
    prefs="$(ls -td "$HOME/Library/Preferences/Ableton"/Live*/ 2>/dev/null | head -1)"
    [ -n "$prefs" ] || { echo "  no Live preferences found"; return; }
    echo "  $(basename "$prefs"):"
    grep -h "info: Max: Version" "$prefs/Log.txt" 2>/dev/null | tail -1 | sed 's/.*info: /    last run used:  /'
    for app in /Applications/Ableton\ Live*.app; do
        local plist="$app/Contents/App-Resources/Max/Max.app/Contents/Info.plist"
        [ -f "$plist" ] && echo "    bundled with $(basename "$app" .app): Max $(defaults read "$plist" CFBundleShortVersionString | cut -d' ' -f1)"
    done
    [ -f /Applications/Max.app/Contents/Info.plist ] && \
        echo "    /Applications/Max.app:     Max $(defaults read /Applications/Max.app/Contents/Info.plist CFBundleShortVersionString | cut -d' ' -f1)"
    echo "    (switch in Live: Settings > File & Folder > Max Application / Use Max for Live bundled with Live; restart Live)"
}

case "${1:-status}" in
status)
    echo "fresh-user differences (present = NOT clean):"
    targets | while IFS='|' read -r label path; do
        if [ -L "$path" ]; then echo "  present  $path -> $(readlink "$path")"
        elif [ -e "$path" ]; then
            v=""; [ -f "$path/README.txt" ] && v="  ($(grep -o -m1 '[0-9]\+\.[0-9]\+\.[0-9]\+' "$path/README.txt"))"
            [ -f "$path/midigpt_node.js" ] && v="$v  [midigpt_node.js loose]"
            echo "  present  $path$v"
        else echo "  absent   $path"; fi
    done
    [ -d "$STASH" ] && echo "stash: $STASH ($(ls "$STASH" | tr '\n' ' '))"
    echo "Max for Live:"; live_max
    ;;
on)
    if [ -d "$STASH" ]; then echo "already stashed in $STASH (run 'off' first)"; exit 1; fi
    mkdir -p "$STASH"
    targets | while IFS='|' read -r label path; do
        if [ -e "$path" ] || [ -L "$path" ]; then
            printf '%s\n' "$path" > "$STASH/$label.path"
            mv "$path" "$STASH/$label" && echo "stashed  $path"
        fi
    done
    echo "clean. Quit and reopen Live before testing (Max caches search paths and loaded scripts)."
    ;;
off)
    [ -d "$STASH" ] || { echo "nothing stashed"; exit 1; }
    test_install="$(user_lib)/MIDI-GPT"
    if [ -e "$test_install" ] && [ ! -e "$STASH/userlib-MIDI-GPT" ]; then :   # nothing to restore over it: keep it
    elif [ -e "$test_install" ]; then rm -rf "$test_install" && echo "removed test install $test_install"; fi
    [ -f "$CONF_DIR/live.json" ] && [ -e "$STASH/live.json" ] && rm -f "$CONF_DIR/live.json"
    for f in "$STASH"/*.path; do
        [ -e "$f" ] || continue
        label="$(basename "$f" .path)"; path="$(cat "$f")"
        mkdir -p "$(dirname "$path")"
        mv "$STASH/$label" "$path" && rm -f "$f" && echo "restored $path"
    done
    rmdir "$STASH" 2>/dev/null || echo "left over in $STASH: $(ls "$STASH")"
    echo "Quit and reopen Live."
    ;;
*) sed -n 2,6p "$0"; exit 1 ;;
esac
