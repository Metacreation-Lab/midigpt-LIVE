# Troubleshooting

## Messages on the stats screen

| Message | Fix |
|---|---|
| **NO LINK** (red light in SETUP) | the server isn't running or the address is wrong: start it, or check the address in [SETUP](guide/setup.md) |
| **LINK LOST** | the server stopped answering mid-request; nothing was written. Retry. |
| **NO REPLY** | the server didn't answer in time: check it's still running, or try a smaller request |
| **SRV BUSY** | the server's queue is full; the device retries by itself |
| **NO TARGET** | nothing to generate: paint some bars or turn on **AR** |
| **TIME SIG** | the scene's clips use different time signatures |
| **TOO FEW BARS** | the scene is shorter than **CONTEXT**: lower it in [ENGINE](guide/engine.md), or lengthen the clips |
| **REJECTED** | the server refused a setting, and the screen says which (for example, density on a melodic track) |
| **MODEL GONE** | the chosen model isn't on the server any more: pick one in [ENGINE](guide/engine.md) |
| **CHECKS FAIL** | every attempt was rejected by NOVELTY or SILENCE: raise **ATTEMPTS** or **ESC**, or turn a check off |
| **CTX OVERFLOW** | the scene is too long for the model: ignore some tracks or lower **CONTEXT** |
| **CTX LIMIT** | the takes may be cut short: lower **CONTEXT** or generate fewer bars |
| **TAKES LOST** | some takes failed the checks; the others are ready |
| **TAG FAILED** | Live didn't load the tag device: drag **MIDI-GPT Instrument** from the MIDI-GPT folder onto the track |
| **SRV FAULT** · **BAD REQUEST** | something broke on the server or in the device: retry, and if it repeats, [report it](https://github.com/DaoTwenty/midigpt-LIVE/issues) with `midigpt.log` |

## Other problems

| Symptom | Fix |
|---|---|
| Port 3456 already in use | another MIDI-GPT server is running (MIDI-GPT for REAPER uses the same port): use it, or start this one with `--port 3457` and change the address |
| The device won't load after a download | clear the macOS quarantine flag (see [Install](install.md#macos-quarantine)) |
| The first generation is slow | the server loads the model on the first request; later ones are faster |
| Generation is slow overall | try `yellow_small`, or run the server on a faster machine |

## Model limits

- **DENSITY** only works on drum tracks; **POLY** and **LENGTH** only on melodic tracks.
- **REGISTER** only applies with **SCALE** on.
- **REMIX** replaces the rhythm settings on the same track.
- Writing a long track with **AR** can come back empty with the current models. Generate 8 bars at a time if that
  happens.

## Files

| | |
|---|---|
| Settings | `~/Library/Application Support/MIDI-GPT/live.json` |
| Server | `~/Library/Application Support/MIDI-GPT/server` (its window shows the log) |
| Models | `~/.cache/huggingface` |

Still stuck? [Open an issue](https://github.com/DaoTwenty/midigpt-LIVE/issues) with what you did and what the
stats screen said.
