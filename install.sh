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
#   --yes                 accept every default without asking (a Hugging Face token is then read from HF_TOKEN)
#   --uninstall           remove the device folder, the server environment and the settings
#
# Environment: MIDIGPT_LIVE_REPO (owner/repo of the releases), MIDIGPT_VERSION (midigpt package version),
# HF_TOKEN (a Hugging Face token to save for the server, with --yes).

set -euo pipefail

REPO="${MIDIGPT_LIVE_REPO:-Metacreation-Lab/midigpt-LIVE}"
MIDIGPT_VERSION="${MIDIGPT_VERSION:-0.4.2}"
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

# Hugging Face access to the model (the checkpoints are gated: an account that accepted the license, and a token).
# Sets HF_ACCESS: cached (already downloaded), ok, nologin (no token saved), gated (the token's account has no
# access), offline (Hugging Face couldn't be reached). HF_TOKEN is left out: what counts is the saved token, the one
# the launcher's server will use.
HF_REPO="Metacreation/MIDI-GPT"
hf_check() {
    HF_ACCESS="$(env -u HF_TOKEN "$VENV/bin/python" - "$HF_REPO" "$MODEL" <<'PY' 2>/dev/null || echo offline
import glob, os, sys
from huggingface_hub import constants, get_hf_file_metadata, get_token, hf_hub_url
from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError
repo, model = sys.argv[1:]
snapshots = os.path.join(constants.HF_HUB_CACHE, "models--" + repo.replace("/", "--"), "snapshots")
if glob.glob(os.path.join(snapshots, "*", model + "-*.safetensors")):
    print("cached"); sys.exit()
try:
    from midigpt.inference.engine import _resolve_checkpoint_filename
    get_hf_file_metadata(hf_hub_url(repo, _resolve_checkpoint_filename(repo, model)))
    print("ok")
except (GatedRepoError, RepositoryNotFoundError):
    print("gated" if get_token() else "nologin")
PY
)"
}

# save a Hugging Face token where midigpt-http finds it (~/.cache/huggingface/token); the token is passed in the
# environment, not on a command line
hf_login() {
    MIDIGPT_HF_TOKEN="$1" env -u HF_TOKEN "$VENV/bin/python" -c '
import os, sys
from huggingface_hub import login
try:
    login(token=os.environ["MIDIGPT_HF_TOKEN"], add_to_git_credential=False)
except Exception as e:
    sys.exit(f"    {e}")' >/dev/null
}

hf_access() {
    hf_check
    case "$HF_ACCESS" in
        cached) ok "the $MODEL model is already downloaded"; return ;;
        ok) ok "Hugging Face: access to $HF_REPO"; return ;;
        offline) warn "Couldn't reach Hugging Face; the server downloads the model on its first start."; return ;;
    esac
    # --yes, or no terminal: use HF_TOKEN if it is set
    if [ "$YES" = 1 ] || [ ! -t 0 ]; then
        if [ -n "${HF_TOKEN:-}" ] && hf_login "$HF_TOKEN"; then hf_check; fi
        [ "$HF_ACCESS" = ok ] && { ok "Hugging Face: access to $HF_REPO (HF_TOKEN saved)"; return; }
        warn "No access to $HF_REPO: accept its license at https://huggingface.co/$HF_REPO, then run"
        warn "'$VENV/bin/hf auth login' (or install again with HF_TOKEN set)."
        return
    fi
    echo
    echo "    The MIDI-GPT models are on Hugging Face and need a free account to download:"
    echo "      1. Sign in at https://huggingface.co and accept the license at https://huggingface.co/$HF_REPO"
    echo "      2. Create an access token at https://huggingface.co/settings/tokens (type \"Read\" is enough)"
    [ "$HF_ACCESS" = gated ] && echo "    (A token is saved, but its account has no access yet: accept the license, or paste another token.)"
    local tok
    while true; do
        read -r -s -p "    Paste the token (hidden), or press Enter to skip: " tok; echo
        if [ -z "$tok" ]; then
            [ "$HF_ACCESS" = gated ] && hf_check
            [ "$HF_ACCESS" = ok ] && { ok "Hugging Face: access to $HF_REPO"; return; }
            warn "Skipped. The server will say what is missing when it starts; run '$VENV/bin/hf auth login' later."
            return
        fi
        hf_login "$tok" || { warn "That token was refused; try again."; continue; }
        hf_check
        case "$HF_ACCESS" in
            ok) ok "token saved; access to $HF_REPO"; return ;;
            gated) warn "Token saved, but this account has no access yet: accept the license at https://huggingface.co/$HF_REPO, then press Enter." ;;
            *) warn "Token saved; Hugging Face couldn't be reached to check it."; return ;;
        esac
    done
}

USER_LIB="${USER_LIB:-$(find_user_library)}"
DEVICE_DIR="$USER_LIB/MIDI-GPT"

# ------------------------------------------------------------------ uninstall
if [ "$UNINSTALL" = 1 ]; then
    bold "Uninstall MIDI-GPT for Live"
    installed="$(config_get install_dir)"; installed="${installed:-$DEVICE_DIR}"
    [ -d "$installed" ] && ask "Remove the devices in $installed?" y && rm -rf "$installed" && ok "removed $installed"
    [ -d "$SERVER_DIR" ] && ask "Remove the server environment in $SERVER_DIR?" y && rm -rf "$SERVER_DIR" && ok "removed $SERVER_DIR"
    d="$HOME/Desktop/Start MIDI-GPT Server.command"
    { [ -f "$d" ] || [ -L "$d" ]; } && rm -f "$d" && ok "removed the Desktop launcher"
    d="${XDG_DATA_HOME:-$HOME/.local/share}/applications/midigpt-server.desktop"
    [ -f "$d" ] && rm -f "$d" && ok "removed the menu entry"
    [ -f "$CONFIG" ] && ask "Remove the saved settings ($CONFIG)?" y && rm -f "$CONFIG" && ok "removed settings"
    echo; echo "    Downloaded models stay in ~/.cache/huggingface (delete models--Metacreation--MIDI-GPT there to free the space),"
    echo "    and so does a saved Hugging Face token (hf auth logout removes it)."
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
# replace the devices and the Server folder, keep anything else the user put in the folder
cp -Rf "$TMP/unzipped/MIDI-GPT/." "$DEVICE_DIR/"
# launchers older installers generated (now Server/Start MIDI-GPT Server.command)
rm -f "$DEVICE_DIR/Start MIDI-GPT Server.command"
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
    # Python 3.10-3.14: midigpt has prebuilt wheels for those. Intel Macs stop at 3.12: torch has no Intel Mac
    # builds for newer Pythons.
    PYMAX=14
    [ "$OS" = Darwin ] && [ "$(uname -m)" = x86_64 ] && PYMAX=12
    py_ok() { "$1" -c "import sys; sys.exit(not ((3,10) <= sys.version_info[:2] <= (3,$PYMAX)))" 2>/dev/null; }
    PY="" UV=""
    if command -v uv >/dev/null; then UV="$(command -v uv)"
    elif [ -x "$HOME/.local/bin/uv" ]; then UV="$HOME/.local/bin/uv"
    else
        for c in python3.12 python3.13 python3.14 python3.11 python3.10 python3; do
            if command -v "$c" >/dev/null && py_ok "$c"; then
                PY="$(command -v "$c")"; break
            fi
        done
        if [ -z "$PY" ]; then
            echo "    No Python 3.10-3.$PYMAX found. uv (https://docs.astral.sh/uv) can install one just for MIDI-GPT."
            ask "Install uv?" y || die "Install Python 3.12 (python.org or Homebrew: brew install python@3.12) and re-run."
            curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null || die "uv install failed."
            UV="$HOME/.local/bin/uv"
        fi
    fi

    VENV="$SERVER_DIR/.venv"
    mkdir -p "$SERVER_DIR"
    if [ -x "$VENV/bin/python" ] && py_ok "$VENV/bin/python"; then
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

    # the launchers are in the release's Server folder (server/ in the repo); they read the model and port from
    # server.conf, and the server folder from live.json
    LAUNCH="$DEVICE_DIR/Server/start-server.sh"
    [ -f "$LAUNCH" ] || die "This release has no Server folder with the server launchers: install 0.2.1 or later."
    printf '# written by install.sh: the model and port start-server.sh uses\nMODEL=%s\nPORT=%s\n' "$MODEL" "$PORT" > "$SERVER_DIR/server.conf"
    config_set server_dir "$SERVER_DIR"
    rm -f "$SERVER_DIR/start-server.sh"   # generated by older installers
    LAUNCHERS=()
    if [ "$OS" = Darwin ]; then
        LAUNCHERS+=("$DEVICE_DIR/Server/Start MIDI-GPT Server.command")
        if ask "Put a 'Start MIDI-GPT Server' launcher on the Desktop?" y; then
            rm -f "$HOME/Desktop/Start MIDI-GPT Server.command"
            ln -s "$DEVICE_DIR/Server/Start MIDI-GPT Server.command" "$HOME/Desktop/Start MIDI-GPT Server.command"
            LAUNCHERS+=("$HOME/Desktop/Start MIDI-GPT Server.command")
        fi
    else
        apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
        mkdir -p "$apps"
        sed "s#@START_SERVER@#$LAUNCH#" "$DEVICE_DIR/Server/midigpt-server.desktop" > "$apps/midigpt-server.desktop"
        ok "menu entry: Start MIDI-GPT Server"
        LAUNCHERS+=("$LAUNCH")
    fi
    ok "launcher: ${LAUNCHERS[0]}"

    hf_access
    if { [ "$HF_ACCESS" = ok ] || [ "$HF_ACCESS" = offline ]; } && ask "Download the $MODEL model now? (otherwise on the server's first start)" y; then
        "$VENV/bin/python" - "$MODEL" <<'PY' || warn "Download failed; the server will try again when it starts."
import sys
from huggingface_hub import hf_hub_download
from huggingface_hub.utils import GatedRepoError
from midigpt.inference.engine import _resolve_checkpoint_filename
repo = "Metacreation/MIDI-GPT"
try:
    print("    " + hf_hub_download(repo_id=repo, filename=_resolve_checkpoint_filename(repo, sys.argv[1])))
except GatedRepoError:
    print(f"    No access to {repo} yet: accept its license at https://huggingface.co/{repo}, then run this installer "
          "again or start the server.", file=sys.stderr)
    sys.exit(1)
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
if [ "$SERVER" = 1 ] && [ -t 0 ] && [ "$YES" = 0 ] && ask "Start the server now?" n; then exec bash "$LAUNCH"; fi
