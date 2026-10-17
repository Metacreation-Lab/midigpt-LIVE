# Changelog

All notable changes to MIDI-GPT for Live are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
