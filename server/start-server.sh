#!/usr/bin/env bash
# MIDI-GPT server for the Live device (macOS / Linux): http://127.0.0.1:3456 by default.
# Keep the window open while you use MIDI-GPT in Live; Ctrl+C stops the server.
#
# The installer (install.sh) sets up the server's Python environment and writes server.conf (model, port) next to
# it: ~/Library/Application Support/MIDI-GPT/server on macOS, ~/.config/MIDI-GPT/server on Linux, or the folder
# in MIDIGPT_SERVER_DIR.
#
#   ./start-server.sh                                 # the installed model on port 3456
#   ./start-server.sh --pretrained yellow_small       # another model
#   ./start-server.sh --host 0.0.0.0                  # reachable from other computers
#
# Arguments go to midigpt-http after the defaults, so they override them. The server runs on the GPU when there is
# one (--device auto: CUDA, or the Mac's GPU through MPS), else on the CPU.
#
# On a Mac, MPS can be slower than the CPU for a model this size (twice as slow on an Intel Mac's Radeon GPU):
# ./start-server.sh --device cpu to compare.

# the server folder: MIDIGPT_SERVER_DIR, else the one the installer recorded in live.json, else the default
case "$(uname -s)" in
    Darwin) CONFIG_DIR="$HOME/Library/Application Support/MIDI-GPT" ;;
    *)      CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/MIDI-GPT" ;;
esac
SERVER_DIR="${MIDIGPT_SERVER_DIR:-}"
[ -z "$SERVER_DIR" ] && [ -f "$CONFIG_DIR/live.json" ] \
    && SERVER_DIR="$(sed -n 's/.*"server_dir": *"\([^"]*\)".*/\1/p' "$CONFIG_DIR/live.json" | head -1)"
SERVER_DIR="${SERVER_DIR:-$CONFIG_DIR/server}"
VENV="$SERVER_DIR/.venv"

MODEL=yellow_medium
PORT=3456
# shellcheck disable=SC1091
[ -f "$SERVER_DIR/server.conf" ] && . "$SERVER_DIR/server.conf"

pause() { [ -t 0 ] && read -r -p "Press Enter to close. "; }

# the model and port the arguments override, for the message below
prev=""
for a in "$@"; do
    case "$prev" in --port) PORT="$a" ;; --pretrained) MODEL="$a" ;; esac
    case "$a" in --port=*) PORT="${a#*=}" ;; --pretrained=*) MODEL="${a#*=}" ;; esac
    prev="$a"
done

if [ ! -x "$VENV/bin/midigpt-http" ]; then
    echo "The MIDI-GPT server isn't installed (no environment in $VENV)."
    echo "Install it with:"
    echo "  curl -fsSL https://metacreation.net/midigpt-LIVE/bootstrap.sh | bash -s -- --server"
    echo
    pause
    exit 1
fi

echo
echo "  MIDI-GPT server on http://127.0.0.1:$PORT (model $MODEL)"
echo "  Keep this window open while you use MIDI-GPT in Live. Press Ctrl+C to stop the server."
[ "$(uname -s)" = Darwin ] && echo "  On a Mac the GPU (MPS) can be slower than the CPU: if generations are slow, try start-server.sh --device cpu."
echo

# a failed generation's request is saved here, to attach to a bug report (docs/reporting-bugs.md)
export MIDIGPT_FAILED_REQUESTS_LOG="${MIDIGPT_FAILED_REQUESTS_LOG:-$SERVER_DIR/failed_requests.jsonl}"
"$VENV/bin/midigpt-http" --pretrained "$MODEL" --device auto --host 127.0.0.1 --port "$PORT" "$@"
status=$?

# 130 = Ctrl+C. Keep the window open otherwise, so the message above can be read.
if [ $status -ne 0 ] && [ $status -ne 130 ]; then
    echo
    echo "The server stopped (exit $status)."
    echo "If the message above mentions a gated repo, 401 or 403: accept the license at"
    echo "https://huggingface.co/Metacreation/MIDI-GPT, then save a token with:"
    echo "  \"$VENV/bin/hf\" auth login"
    echo
    pause
fi
exit $status
