#!/usr/bin/env bash
# MIDI-GPT server for the Live device (macOS / Linux): http://127.0.0.1:3456 by default.
# Keep the window open while you use MIDI-GPT in Live; Ctrl+C stops the server.
#
# The installer (install.sh) sets up the server's Python environment and writes models.yaml (the models to load)
# and server.conf (port) next to it: ~/Library/Application Support/MIDI-GPT/server on macOS,
# ~/.config/MIDI-GPT/server on Linux, or the folder in MIDIGPT_SERVER_DIR.
#
#   ./start-server.sh                                 # the models in models.yaml, on port 3456
#   ./start-server.sh --pretrained yellow_small       # just this model, ignoring models.yaml
#   ./start-server.sh --host 0.0.0.0                  # reachable from other computers
#
# Arguments go to midigpt-http after the defaults, so they override them. Without models.yaml the server loads
# MODEL from server.conf. The device (GPU or CPU) is set in models.yaml; without it, --device auto: CUDA, or the
# Mac's GPU through MPS, else the CPU.
#
# On a Mac, MPS can be slower than the CPU for a model this size (twice as slow on an Intel Mac's Radeon GPU):
# set device: cpu in models.yaml to compare.

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
MODELS="$SERVER_DIR/models.yaml"

MODEL=yellow_medium
PORT=3456
# shellcheck disable=SC1091
[ -f "$SERVER_DIR/server.conf" ] && . "$SERVER_DIR/server.conf"

pause() { [ -t 0 ] && read -r -p "Press Enter to close. "; }

# what to load: models.yaml (config), else MODEL (single); a model in the arguments wins over both (own)
MODE=single
[ -f "$MODELS" ] && MODE=config
DEVICE_ARG=0
# the model and port the arguments override, for the message below
prev=""
for a in "$@"; do
    case "$prev" in --port) PORT="$a" ;; --pretrained) MODEL="$a"; MODE=single ;; esac
    case "$a" in
        --port=*) PORT="${a#*=}" ;;
        --pretrained=*) MODEL="${a#*=}"; MODE=single ;;
        --ckpt|--ckpt=*|--config|--config=*) MODE=own ;;
        --device|--device=*) DEVICE_ARG=1 ;;
    esac
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

# a mistake in models.yaml, said in plain words instead of the server's traceback
if [ "$MODE" = config ] && [ -f "$(dirname "$0")/check_models.py" ] \
    && ! "$VENV/bin/python" "$(dirname "$0")/check_models.py" "$MODELS"; then
    echo
    pause
    exit 1
fi

echo
case "$MODE" in
    config)
        # the ids of the models listed (not commented out) in models.yaml
        ids="$(sed -n 's/^[[:space:]]*-[[:space:]]*{\{0,1\}[[:space:]]*id:[[:space:]]*\([^,}[:space:]]*\).*/\1/p' "$MODELS" | paste -sd ' ' -)"
        echo "  MIDI-GPT server on http://127.0.0.1:$PORT (models: ${ids:-see models.yaml})"
        echo "  Models are set in $MODELS" ;;
    single) echo "  MIDI-GPT server on http://127.0.0.1:$PORT (model $MODEL)" ;;
    own)    echo "  MIDI-GPT server on http://127.0.0.1:$PORT" ;;
esac
echo "  Keep this window open while you use MIDI-GPT in Live. Press Ctrl+C to stop the server."
if [ "$MODE" = config ] && [ "$DEVICE_ARG" = 1 ]; then
    echo "  --device has no effect with models.yaml: set device: in that file instead."
elif [ "$(uname -s)" = Darwin ] && [ "$MODE" = config ]; then
    echo "  On a Mac the GPU (MPS) can be slower than the CPU: if generations are slow, set device: cpu in models.yaml."
elif [ "$(uname -s)" = Darwin ]; then
    echo "  On a Mac the GPU (MPS) can be slower than the CPU: if generations are slow, try start-server.sh --device cpu."
fi
echo

# a failed generation's request is saved here, to attach to a bug report (docs/reporting-bugs.md)
export MIDIGPT_FAILED_REQUESTS_LOG="${MIDIGPT_FAILED_REQUESTS_LOG:-$SERVER_DIR/failed_requests.jsonl}"
case "$MODE" in
    config) "$VENV/bin/midigpt-http" --config "$MODELS" --host 127.0.0.1 --port "$PORT" "$@" ;;
    single) "$VENV/bin/midigpt-http" --pretrained "$MODEL" --device auto --host 127.0.0.1 --port "$PORT" "$@" ;;
    own)    "$VENV/bin/midigpt-http" --device auto --host 127.0.0.1 --port "$PORT" "$@" ;;
esac
status=$?

# 130 = Ctrl+C. Keep the window open otherwise, so the message above can be read.
if [ $status -ne 0 ] && [ $status -ne 130 ]; then
    echo
    echo "The server stopped (exit $status)."
    echo "If the message above mentions a gated repo, 401 or 403: accept the license at"
    echo "https://huggingface.co/Metacreation/MIDI-GPT, then save a token with:"
    echo "  \"$VENV/bin/hf\" auth login"
    [ "$MODE" = config ] && echo "If it mentions models.yaml or a model entry, check that file: $MODELS"
    echo
    pause
fi
exit $status
