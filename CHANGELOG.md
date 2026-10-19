# Changelog

All notable changes to MIDI-GPT for Live are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.1]

### Added
- Hugging Face access for the gated models: the installer checks it before downloading, explains the license and
  token steps, and saves a pasted token where the server reads it (`--yes` uses `HF_TOKEN`). The README and the
  install docs have a Hugging Face account step.

### Changed
- The **Start MIDI-GPT Server** window stays open when the server stops on an error, so its message can be read.
- **NO LINK** points to the server window, which says why a server stopped.

## [0.2.0]

### Added
- Prism and expressive models: **KEY**, **RANGE**, **SILENCE** and **PCS** track controls, shown when the model has
  them, and context windows up to 16 bars.
- **PROB** (SAMPLE): regenerate only a random share of the painted bars; the rest stay as context, and the roll
  dims the bars left out.
- **EXPRESSIVENESS** (TRACK, expressive) and **GENRE** (prism and expressive: a screen in the TRACK bay's top row,
  for the whole request; click it for the list, or step with ◀ ▶ and the wheel).
- Partial AR: click a bar of an AR track to start writing there; the bars before it are its history.
- The roll and the SETUP list scroll with the mouse wheel and the trackpad.
- The track the TRACK and MASKS controls edit is highlighted in the roll and named in the bay titles, with a
  warning when it isn't being generated.
- Single generations stream: NOTES, TOK/S, CTX and the retry attempt update on the stats screen while it runs.
- The seed is a small screen: click to type a seed (digits only, 1–2147483647), **DICE** for a random one, **LOCK**
  to keep the last run's or the selected take's seed.
- Panel images, path-traced in Blender from the same geometry: real shadows, glossy knobs.
- Documentation site (MkDocs): install, a page per panel area, workflows, troubleshooting, developer notes.
- Release trailer (full and short cuts).

### Changed
- **CONTEXT**, **BARS/STEP** and **TRK/STEP** on AUTO are left to the server: windows that follow the painted bars,
  context tracks left out when a step would not fit (struck through in the roll), then smaller steps.
- **VELOCITY** and **MICRO** are on by default and apply to models that can switch them (expressive).
- Track controls are sent under the names each model uses (bar-level density, polyphony and pitch-class set on
  prism and expressive).
- **CTX** shows the model's window per step, and its peak when a generation finishes.
- Lighter panel: one page background in memory, per-track refreshes, repaints only when something changes.
- All HTTP goes through the Node helper: a reply arriving after the device was closed or deleted could crash Live.
- Stats read the server's real fields (TOK/S and CTX were always empty); ATT shows the accepted attempt.
- Long note and state messages to the panel are sent in parts (large scenes showed an empty roll).
- The project now lives at Metacreation-Lab/midigpt-LIVE; the one-line install is
  `curl -fsSL https://metacreation.net/midigpt-live/bootstrap.sh | bash`.

### Fixed
- AR generations always write their result into the target clips.
- **NOTES** counts only the notes written back, not the target tracks' context bars.
- RUNNING and STOPPING overlapped the STATUS label.

## [0.1.0]

First release.

### Added
- **MIDI-GPT** device: a floating panel with the scene's tracks as a roll, per-track controls
  (polyphony, note length, density), scale / rhythm / remix masks, sampling controls, an engine page,
  setup, and takes with revert and keep.
- Multi-track generation: any track with painted bars or AR is generated; the rest of the scene is context.
- **MIDI-GPT Instrument** tag device: stores each track's General MIDI instrument on the track.
- Server address saved per user, in `~/Library/Application Support/MIDI-GPT/live.json`.
- `bootstrap.sh` / `install.sh`: installs the devices into Live's User Library and, optionally,
  a local MIDI-GPT server (midigpt 0.3.4) with a launcher; `--uninstall` removes everything.
- Release build that freezes both devices without Max (`tools/build_release.py`).
