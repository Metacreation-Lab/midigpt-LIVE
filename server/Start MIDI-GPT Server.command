#!/usr/bin/env bash
# Double-click to start the MIDI-GPT server on macOS (runs start-server.sh, next to this file).
# Keep the window open while you use MIDI-GPT in Live.
# The server uses the Mac's GPU (MPS), which can be slower than the CPU; to use the CPU, run in Terminal:
#   bash "<this folder>/start-server.sh" --device cpu
src="$0"
# the installer's Desktop launcher is a link to this file: find the real folder
while [ -L "$src" ]; do
    link="$(readlink "$src")"
    case "$link" in /*) src="$link" ;; *) src="$(dirname "$src")/$link" ;; esac
done
exec bash "$(cd "$(dirname "$src")" && pwd)/start-server.sh" "$@"
