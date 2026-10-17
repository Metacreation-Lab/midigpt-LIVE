#!/bin/bash
# Screenshot / click helper for checking the device UI from a terminal.
# Needs Screen Recording (screenshots) and Accessibility (clicks) permission
# for the terminal app, plus cliclick (brew install cliclick).
#
#   tools/screen.sh windows                     list windows: app | title | x y w h
#   tools/screen.sh shot <out.png> [app] [title-substring]
#                                               capture one window (or the whole screen)
#   tools/screen.sh click <x> <y>               click at screen coordinates
#   tools/screen.sh front <app>                 bring an app to the front
#
# Window coordinates from "windows" are in screen points, the same space
# cliclick uses, so a widget at (wx, wy) inside a window at (x, y) is
# clicked at (x + wx, y + wy).

set -euo pipefail
cmd=${1:-}

list_windows() {
    osascript <<'APPLESCRIPT'
set out to ""
tell application "System Events"
    repeat with p in (every process whose background only is false)
        set pname to name of p
        repeat with w in (every window of p)
            try
                set {x, y} to position of w
                set {ww, hh} to size of w
                set out to out & pname & " | " & (name of w) & " | " & x & " " & y & " " & ww & " " & hh & linefeed
            end try
        end repeat
    end repeat
end tell
return out
APPLESCRIPT
}

case "$cmd" in
    windows)
        list_windows
        ;;
    shot)
        out=$2; app=${3:-}; title=${4:-}
        if [ -z "$app" ]; then
            screencapture -x "$out"
        else
            line=$(list_windows | grep -F "$app |" | grep -F -- "$title" | head -1)
            [ -z "$line" ] && { echo "no window for '$app' '$title'"; exit 1; }
            read -r x y w h <<<"$(echo "$line" | awk -F' \\| ' '{print $3}')"
            screencapture -x -R"$x,$y,$w,$h" "$out"
            echo "$line"
        fi
        ;;
    click)
        cliclick "c:$2,$3"
        ;;
    front)
        osascript -e "tell application \"$2\" to activate"
        ;;
    *)
        sed -n '2,14p' "$0"
        exit 2
        ;;
esac
