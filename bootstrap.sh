#!/usr/bin/env bash
# One-line install of MIDI-GPT for Ableton Live (macOS, Linux):
#
#   curl -fsSL https://raw.githubusercontent.com/DaoTwenty/midigpt-LIVE/HEAD/bootstrap.sh | bash
#
# Downloads install.sh and runs it; arguments go to install.sh, e.g.
#   curl -fsSL .../bootstrap.sh | bash -s -- --no-server
set -euo pipefail
REPO="${MIDIGPT_LIVE_REPO:-DaoTwenty/midigpt-LIVE}"
BRANCH="${MIDIGPT_LIVE_BRANCH:-HEAD}"   # HEAD = the default branch
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
curl -fsSL "https://raw.githubusercontent.com/$REPO/$BRANCH/install.sh" -o "$tmp/install.sh" \
    || { echo "Could not download install.sh from $REPO ($BRANCH)." >&2; exit 1; }
# the installer asks questions: read the answers from the terminal, not from the curl pipe
if [ -r /dev/tty ]; then bash "$tmp/install.sh" "$@" < /dev/tty; else bash "$tmp/install.sh" "$@"; fi
