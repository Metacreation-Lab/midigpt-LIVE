# For developers

MIDI-GPT for Live is built from the sources in [the repository](https://github.com/Metacreation-Lab/midigpt-LIVE).
[CLAUDE.md](https://github.com/Metacreation-Lab/midigpt-LIVE/blob/master/CLAUDE.md) has the full architecture notes, the
pitfalls met along the way, and the tools.

## How it works

```
 Live set ─── clips in the selected scene ───▶ MIDI-GPT.amxd ─── HTTP ───▶ midigpt-http (127.0.0.1:3456)
    ▲                                               │                           │  the MIDI-GPT model
    └─────────── generated bars, as takes ◀─────────┘ ◀──────── score ──────────┘
```

The device sends the scene to the server as a score, with what to generate and how; the server runs MIDI-GPT and
returns the result, which the device writes into only the bars you asked for. The server is the HTTP server from the
`midigpt` Python package ([API reference](https://metacreation-lab.github.io/MIDI-GPT/)).

## Layout

```
patchers/        MIDI-GPT.amxd and MIDI-GPT Instrument.amxd (built by the scripts below)
javascript/      midigpt.js (Live API, state, HTTP client), the panel, strip, tag and Node helper scripts
media/panel/     the panel's images (rendered in Blender)
tools/           build, release, freezing, asset, video and dev scripts
docs/            this site (MkDocs)
install.sh       the installer (bootstrap.sh downloads and runs it)
server/          the server launchers, shipped as MIDI-GPT/Server: start-server.sh, Start MIDI-GPT Server.command / .bat
```

## Build

```bash
python3 tools/build_device.py           # patchers/MIDI-GPT.amxd: panel window, strip key, dependencies (in place)
python3 tools/build_tag_device.py       # patchers/MIDI-GPT Instrument.amxd
python3 tools/build_release.py          # dist/MIDI-GPT-for-Live-<VERSION>.zip, both devices frozen
python3 tools/maxtool.py validate patchers/*.amxd
```

`build_release.py` freezes the devices itself (`tools/amxd_freeze.py`, the same format as Max's **Freeze Device**), so
a release needs no Max. Attach the zip to a GitHub release tagged `v<VERSION>`; the installer downloads the newest one.
Device conventions follow Ableton's
[Max for Live production guidelines](https://github.com/Ableton/maxdevtools/blob/main/m4l-production-guidelines/m4l-production-guidelines.md).

## The dev bridge

`touch .midigpt_dev` in the repository, reload the device, and drive it from the terminal:

```bash
python3 tools/bridge.py state                 # selection, server, current track
python3 tools/bridge.py ui                    # every named widget
python3 tools/bridge.py msg panel generate    # what the panel sends
python3 tools/bridge.py reload                # recompile midigpt.js from disk
python3 tools/bridge.py log 50                # tail midigpt.log
```

## This site

```bash
pip install mkdocs-material
mkdocs serve                                  # http://127.0.0.1:8000
```

The panel images come from the device's own panel code, rendered offline; the clips are cut from the trailer.

## Contributing

Issues and pull requests are welcome. Known gaps: a Windows installer, a MIDI-mappable Generate control, and testing
on Linux.
