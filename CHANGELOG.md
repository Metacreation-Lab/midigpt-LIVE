# Changelog

All notable changes to MIDI-GPT for Live are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.5]

### Added
- **SETTINGS**: click the MIDI-GPT mark, top-left, for a larger font size (three steps) and hover hints on a few
  controls (RE-PITCH, RHYTHM, CONTEXT, POLY LIM, DENS LIM, PROB so far: more as they're written). Both are saved
  per-user, the same way as the remembered server URL.

### Changed
- **REMIX** is now **RE-PITCH** everywhere in the device and the docs. Nothing to update: the setting and its value
  carry over, since only the on-screen name changed.

### Fixed
- The device could fail to connect to the server, with `node.script: couldn't generate path` or
  `midigpt_node.js: No such file or directory` in the Max Console (reported on Max 9.1.5 / macOS 26.3, reproduced on
  Live 11 with Max 8.5.8): Max extracting the Node helper from inside the frozen device is unreliable. It now ships
  as a loose file next to the two devices, and the device starts it by its full path.
- Knobs, keys, toggles, the strip key and the Instrument tag's face were missing in a fresh install (only the page
  backgrounds and text drew): Max does not hand those images out of a frozen device. They now ship loose next to
  the devices as well, and are loaded from there.
- A `patcher: doesn't understand "scrollto"` line in the Max Console whenever the window opened.

  Existing installs get these fixes the next time they run the installer or re-download the release zip.

## [0.2.4]

### Added
- **models.yaml**: the models the server loads, in one file in the server folder, edited with a text editor. The
  installer writes it with the chosen model switched on and the other MIDI-GPT models (`yellow_small`, `prism_medium`,
  `expressive_medium`) one `# ` away; a model from another Hugging Face repository or a local `.safetensors` file goes
  in the same list. Every model it loads shows up under **Models** on the ENGINE page. The installer never replaces
  it. See [Models](docs/models.md).

### Changed
- The server launchers start the models in models.yaml (and say which); without the file they start `MODEL` from
  `server.conf` as before, and `--pretrained NAME` still serves just that model. Where the models run (GPU or CPU) is
  `device:` in models.yaml.

### Fixed
- `start-server.sh --ckpt FILE` works: the launchers no longer add `--pretrained` next to it.
- The one-line installer runs without a terminal (scripts, CI): it no longer fails with `/dev/tty: Device not
  configured`.

## [0.2.3]

### Fixed
- **REMIX** without **P+D** keeps each note's duration again, not only its onset: the server is midigpt 0.4.2. Run the
  installer again to update the server.

## [0.2.2]

### Added
- Marked as beta in the README, the documentation and the release's README.txt.
- [Reporting bugs](docs/reporting-bugs.md): what to include and where to find it, with GitHub forms for bug reports
  and feature requests.

### Changed
- **REMIX AMOUNT** is the share of the notes that change, from 5% to 100%: at least one note always changes. At 0%
  remix changed nothing; a set saved at 0% asks for a higher **AMOUNT** before generating (**REMIX AT 0%**).
- The documentation of **POLY LIM** (notes starting together), **MASK P** and **MASK K** (skip the model's likeliest
  note choices) now says what they do, and that the limits win over **REMIX** and **EXACT** rhythm.
- Troubleshooting lists the messages **GENERATE** shows before sending a request.
- The server launchers keep the requests that failed on the server in `failed_requests.jsonl` in the server folder
  (it went to whichever folder the server was started from), so it can be attached to a bug report.
- The server is midigpt 0.4.1: long generations are several times faster, and remix, exact rhythm, the
  polyphony and density limits, the masks and odd meters (5/8, 7/8, 9/8) are more reliable.

### Fixed
- Takes stay available when you click elsewhere in Live (another track, scene or clip): switching takes still
  writes into the clips they were generated for. They go on the next generation or **KEEP**.
- Adding or deleting a clip in the selected scene updates the window right away, without clicking the track.

## [0.2.1]

### Added
- Hugging Face access for the gated models: the installer checks it before downloading, explains the license and
  token steps, and saves a pasted token where the server reads it (`--yes` uses `HF_TOKEN`). The README and the
  install docs have a Hugging Face account step.
- Server launchers for each system in the release's `Server` folder (`server/` in the repo): `start-server.sh`,
  **Start MIDI-GPT Server.command** (macOS) and **.bat** (Windows), and a Linux menu entry. The installer uses them
  instead of writing its own, and keeps the model and port in `server.conf`.
- Windows installer: `irm https://metacreation.net/midigpt-LIVE/bootstrap.ps1 | iex` (`install.ps1`) installs the
  devices and the server like the macOS / Linux one, with the Visual C++ runtime PyTorch needs, the CUDA build of
  PyTorch when there is an NVIDIA GPU, and Desktop and Start menu shortcuts.

### Changed
- The **Start MIDI-GPT Server** window stays open when the server stops on an error, so its message can be read.
- **NO LINK** points to the server window, which says why a server stopped.
- The server runs on the GPU when there is one (`--device auto`; midigpt-http used the CPU without it). On a Mac,
  MPS can be slower than the CPU: `start-server.sh --device cpu`.
- The server is midigpt 0.4.0: it says plainly when the model is gated, and a model downloaded before keeps
  working when Hugging Face refuses or can't be reached.
- The server runs on Python 3.10–3.14 (3.10–3.12 on Intel Macs, where PyTorch stops at 3.12).

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
  `curl -fsSL https://metacreation.net/midigpt-LIVE/bootstrap.sh | bash`.

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
