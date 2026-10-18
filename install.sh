#!/usr/bin/env bash
# MIDI-GPT for Ableton Live: installer (macOS, Linux).
#
#   1. the device: downloads the release zip and copies the MIDI-GPT folder into Live's User Library
#   2. the server (optional, asked): a Python environment with midigpt, a launcher, and the model
#
#   curl -fsSL https://metacreation.net/midigpt-live/bootstrap.sh | bash
#   ./install.sh [options]
#
# Options
#   --zip PATH            install the device from a local release zip (default: latest GitHub release)
#   --version X.Y.Z       install that release instead of the latest
#   --user-library DIR    Live's User Library (default: read from Live's preferences)
#   --server | --no-server   set up the local server, or skip it (default: ask)
#   --server-dir DIR      where the server's Python environment goes
#   --model NAME          yellow_medium (default, 350 MB) or yellow_small (83 MB, faster)
#   --yes                 accept every default without asking
#   --uninstall           remove the device folder, the server environment and the settings
#
# Environment: MIDIGPT_LIVE_REPO (owner/repo of the releases), MIDIGPT_VERSION (midigpt package version).

set -euo pipefail

REPO="${MIDIGPT_LIVE_REPO:-Metacreation-Lab/midigpt-LIVE}"
MIDIGPT_VERSION="${MIDIGPT_VERSION:-0.3.4}"
PORT=3456
ZIP="" VERSION="" USER_LIB="" SERVER="ask" SERVER_DIR="" MODEL="" YES=0 UNINSTALL=0 LAUNCH=""
LAUNCHERS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --zip) ZIP="$2"; shift ;;
        --zip=*) ZIP="${1#*=}" ;;
        --version) VERSION="$2"; shift ;;
        --version=*) VERSION="${1#*=}" ;;
        --user-library) USER_LIB="$2"; shift ;;
        --user-library=*) USER_LIB="${1#*=}" ;;
        --server) SERVER=1 ;;
        --no-server) SERVER=0 ;;
        --server-dir) SERVER_DIR="$2"; shift ;;
        --server-dir=*) SERVER_DIR="${1#*=}" ;;
        --model) MODEL="$2"; shift ;;
        --model=*) MODEL="${1#*=}" ;;
        --yes|-y) YES=1 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1 (see --help)"; exit 1 ;;
    esac
    shift
done

# ------------------------------------------------------------------ helpers
bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# ask "question" default(y|n) -> 0 for yes. --yes, or no terminal, takes the default.
ask() {
    local q="$1" def="$2" ans hint="[Y/n]"
    [ "$def" = n ] && hint="[y/N]"
    if [ "$YES" = 1 ] || [ ! -t 0 ]; then ans="$def"
    else read -r -p "    $q $hint " ans; ans="${ans:-$def}"; fi
    case "$ans" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

OS="$(uname -s)"
case "$OS" in
    Darwin) CONFIG_DIR="$HOME/Library/Application Support/MIDI-GPT" ;;
    Linux)  CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/MIDI-GPT" ;;
    *) die "This installer is for macOS and Linux." ;;
esac
SERVER_DIR="${SERVER_DIR:-$CONFIG_DIR/server}"
CONFIG="$CONFIG_DIR/live.json"

# Live's User Library: <ProjectPath>/User Library from the newest Live's Library.cfg
find_user_library() {
    local cfg path
    if [ "$OS" = Darwin ]; then
        cfg="$(ls -t "$HOME/Library/Preferences/Ableton"/Live*/Library.cfg 2>/dev/null | head -1 || true)"
        if [ -n "$cfg" ]; then
            path="$(sed -n '/<UserLibrary>/,/<\/UserLibrary>/s/.*<ProjectPath Value="\([^"]*\)".*/\1/p' "$cfg" | head -1)"
            [ -n "$path" ] && [ -d "$path/User Library" ] && { echo "$path/User Library"; return; }
        fi
        echo "$HOME/Music/Ableton/User Library"
    else
        echo "$HOME/Ableton/User Library"
    fi
}

# write one key into live.json (the device's settings file), keeping the others
config_set() {
    mkdir -p "$CONFIG_DIR"
    python3 - "$CONFIG" "$1" "$2" <<'PY' 2>/dev/null || printf '{\n  "%s": "%s"\n}\n' "$1" "$2" > "$CONFIG"
import json, sys
path, key, value = sys.argv[1:]
try: cfg = json.load(open(path))
except Exception: cfg = {}
cfg[key] = value
json.dump(cfg, open(path, "w"), indent=2); open(path, "a").write("\n")
PY
}

config_get() {
    python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' "$CONFIG" "$1" 2>/dev/null || true
}

USER_LIB="${USER_LIB:-$(find_user_library)}"
DEVICE_DIR="$USER_LIB/MIDI-GPT"

# ------------------------------------------------------------------ uninstall
if [ "$UNINSTALL" = 1 ]; then
    bold "Uninstall MIDI-GPT for Live"
    installed="$(config_get install_dir)"; installed="${installed:-$DEVICE_DIR}"
    [ -d "$installed" ] && ask "Remove the devices in $installed?" y && rm -rf "$installed" && ok "removed $installed"
    [ -d "$SERVER_DIR" ] && ask "Remove the server environment in $SERVER_DIR?" y && rm -rf "$SERVER_DIR" && ok "removed $SERVER_DIR"
    [ -f "$HOME/Desktop/Start MIDI-GPT Server.command" ] && rm -f "$HOME/Desktop/Start MIDI-GPT Server.command" && ok "removed the Desktop launcher"
    [ -f "$CONFIG" ] && ask "Remove the saved settings ($CONFIG)?" y && rm -f "$CONFIG" && ok "removed settings"
    echo; echo "    Downloaded models stay in ~/.cache/huggingface (delete Metacreation--MIDI-GPT there to free the space)."
    exit 0
fi

bold "MIDI-GPT for Ableton Live"
echo "    device  -> $DEVICE_DIR"

# ------------------------------------------------------------------ 1. device
step "1/2  Installing the device"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [ -z "$ZIP" ]; then
    command -v curl >/dev/null || die "curl is needed to download the device."
    if [ -n "$VERSION" ]; then api="https://api.github.com/repos/$REPO/releases/tags/v$VERSION"
    else api="https://api.github.com/repos/$REPO/releases/latest"; fi
    url="$(curl -fsSL "$api" | sed -n 's/.*"browser_download_url": *"\([^"]*MIDI-GPT-for-Live-[^"]*\.zip\)".*/\1/p' | head -1)" \
        || die "Could not reach GitHub ($api)."
    [ -n "$url" ] || die "No MIDI-GPT-for-Live zip found in the release at $api."
    echo "    downloading $(basename "$url")"
    curl -fL --progress-bar -o "$TMP/device.zip" "$url" || die "Download failed: $url"
    ZIP="$TMP/device.zip"
fi
[ -f "$ZIP" ] || die "Not found: $ZIP"
unzip -q -o "$ZIP" -d "$TMP/unzipped" || die "Could not unzip $ZIP"
[ -f "$TMP/unzipped/MIDI-GPT/MIDI-GPT.amxd" ] || die "$ZIP does not contain MIDI-GPT/MIDI-GPT.amxd"

if [ ! -d "$USER_LIB" ]; then
    warn "Live's User Library was not found at $USER_LIB"
    ask "Create it there anyway? (or re-run with --user-library DIR)" y || die "Cancelled."
fi
mkdir -p "$DEVICE_DIR"
# replace the devices, keep anything else the user put in the folder
cp -f "$TMP/unzipped/MIDI-GPT/"* "$DEVICE_DIR/"
[ "$OS" = Darwin ] && xattr -dr com.apple.quarantine "$DEVICE_DIR" 2>/dev/null || true
config_set install_dir "$DEVICE_DIR"
ok "MIDI-GPT.amxd and MIDI-GPT Instrument.amxd are in the User Library (Live browser: User Library > MIDI-GPT)"

# ------------------------------------------------------------------ 2. server
step "2/2  MIDI-GPT server"
if [ "$SERVER" = ask ]; then
    echo "    The device needs a MIDI-GPT server. Set one up on this computer now? Skip this if you"
    echo "    use a server on another machine (enter its address in the device's SETUP page)."
    if ask "Set up a local server?" y; then SERVER=1; else SERVER=0; fi
fi

if [ "$SERVER" = 0 ]; then
    ok "skipped (re-run with --server to set it up later)"
else
    # Python 3.10-3.12: midigpt has prebuilt wheels for those (newer Pythons would compile it from source)
    PY="" UV=""
    if command -v uv >/dev/null; then UV="$(command -v uv)"
    elif [ -x "$HOME/.local/bin/uv" ]; then UV="$HOME/.local/bin/uv"
    else
        for c in python3.12 python3.11 python3.10 python3; do
            if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(not ((3,10) <= sys.version_info[:2] <= (3,12)))' 2>/dev/null; then
                PY="$(command -v "$c")"; break
            fi
        done
        if [ -z "$PY" ]; then
            echo "    No Python 3.10-3.12 found. uv (https://docs.astral.sh/uv) can install one just for MIDI-GPT."
            ask "Install uv?" y || die "Install Python 3.12 (python.org or Homebrew: brew install python@3.12) and re-run."
            curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null || die "uv install failed."
            UV="$HOME/.local/bin/uv"
        fi
    fi

    VENV="$SERVER_DIR/.venv"
    mkdir -p "$SERVER_DIR"
    if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import sys; sys.exit(not ((3,10) <= sys.version_info[:2] <= (3,12)))' 2>/dev/null; then
        ok "using the existing environment in $VENV"
    else
        rm -rf "$VENV"
        if [ -n "$UV" ]; then "$UV" venv -q --python 3.12 "$VENV" || die "Could not create the environment."
        else "$PY" -m venv "$VENV" || die "Could not create the environment ($PY -m venv)."; fi
        ok "created $VENV ($("$VENV/bin/python" -V))"
    fi

    pkgs=("midigpt[http,inference]==$MIDIGPT_VERSION")
    # Intel Macs: the last torch built for them is 2.2, which needs numpy 1.x
    if [ "$OS" = Darwin ] && [ "$(uname -m)" = x86_64 ]; then pkgs+=("torch<2.3" "numpy<2"); fi
    # Linux: the CPU build of torch (the default one bundles CUDA, several GB)
    extra=()
    [ "$OS" = Linux ] && ! command -v nvidia-smi >/dev/null && extra=(--extra-index-url https://download.pytorch.org/whl/cpu)
    echo "    installing midigpt $MIDIGPT_VERSION and torch (a few minutes the first time)"
    if [ -n "$UV" ]; then "$UV" pip install -q --python "$VENV/bin/python" ${extra[@]+"${extra[@]}"} "${pkgs[@]}" || die "Installing midigpt failed."
    else
        "$VENV/bin/python" -m pip install -q --upgrade pip
        "$VENV/bin/python" -m pip install -q ${extra[@]+"${extra[@]}"} "${pkgs[@]}" || die "Installing midigpt failed."
    fi
    "$VENV/bin/python" -c 'import midigpt.http.server, midigpt.inference.engine' || die "midigpt installed but does not import."
    ok "midigpt $("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("midigpt"))') installed"

    if [ -z "$MODEL" ]; then
        MODEL=yellow_medium
        if [ "$YES" = 0 ] && [ -t 0 ]; then
            echo "    Model: 1) yellow_medium  350 MB, best results (default)"
            echo "           2) yellow_small    83 MB, faster on older computers"
            read -r -p "    Choose [1/2] " m
            [ "$m" = 2 ] && MODEL=yellow_small
        fi
    fi

    LAUNCH="$SERVER_DIR/start-server.sh"
    cat > "$LAUNCH" <<EOF
#!/usr/bin/env bash
# Starts the MIDI-GPT server for the Live device (http://127.0.0.1:$PORT). Close the window or press Ctrl+C to stop it.
# Extra arguments go to midigpt-http, e.g. --host 0.0.0.0 to reach it from other computers.
cd "\$(dirname "\$0")"
echo "MIDI-GPT server on http://127.0.0.1:$PORT (model $MODEL). Press Ctrl+C to stop."
exec "$VENV/bin/midigpt-http" --pretrained $MODEL --host 127.0.0.1 --port $PORT "\$@"
EOF
    chmod +x "$LAUNCH"
    LAUNCHERS=()
    if [ "$OS" = Darwin ]; then
        printf '#!/usr/bin/env bash\nexec "%s"\n' "$LAUNCH" > "$DEVICE_DIR/Start MIDI-GPT Server.command"
        chmod +x "$DEVICE_DIR/Start MIDI-GPT Server.command"
        LAUNCHERS+=("$DEVICE_DIR/Start MIDI-GPT Server.command")
        if ask "Put a 'Start MIDI-GPT Server' launcher on the Desktop?" y; then
            cp "$DEVICE_DIR/Start MIDI-GPT Server.command" "$HOME/Desktop/"
            LAUNCHERS+=("$HOME/Desktop/Start MIDI-GPT Server.command")
        fi
    fi
    ok "launcher: $LAUNCH"

    if ask "Download the $MODEL model now? (otherwise on the server's first start)" y; then
        "$VENV/bin/python" - "$MODEL" <<'PY' || warn "Download failed; the server will try again when it starts."
import sys
from huggingface_hub import hf_hub_download
from midigpt.inference.engine import _resolve_checkpoint_filename
repo = "Metacreation/MIDI-GPT"
print("    " + hf_hub_download(repo_id=repo, filename=_resolve_checkpoint_filename(repo, sys.argv[1])))
PY
    fi
fi

# ------------------------------------------------------------------ done
step "Done"
first="${LAUNCH:-your MIDI-GPT server}"
[ ${#LAUNCHERS[@]} -gt 0 ] && first="${LAUNCHERS[${#LAUNCHERS[@]}-1]}"
echo "    1. Start the server: $first"
echo "    2. In Live: User Library > MIDI-GPT > drag MIDI-GPT onto a track, then open its window."
echo "    3. The server address is in SETUP (default http://127.0.0.1:$PORT)."
if [ "$SERVER" = 1 ] && [ -t 0 ] && [ "$YES" = 0 ] && ask "Start the server now?" n; then exec "$LAUNCH"; fi
