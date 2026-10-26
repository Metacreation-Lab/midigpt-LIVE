# Troubleshooting

## Messages on the stats screen

| Message | Fix |
|---|---|
| **NO LINK** (red light in SETUP) | the server isn't running or the address is wrong: start it, or check the address in [SETUP](guide/setup.md). If it stopped at startup, its window says why |
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
| **SRV FAULT** · **BAD REQUEST** | something broke on the server or in the device: retry, and if it repeats, [report it](reporting-bugs.md) with the server window's lines and its `failed_requests.jsonl` |

## Before generating

**GENERATE** checks the settings first, and instead of sending a request the server would refuse, the **OUTPUT**
screen says what to change:

| Message | Change |
|---|---|
| **BARS/STEP > CONTEXT** | lower **BARS/STEP** |
| **REMIX + RHYTHM** | turn one of them off on that track |
| **REMIX AT 0%** | raise **AMOUNT**: at 0% remix would change nothing |
| **REMIX** / **EXACT RHYTHM NEEDS TRK/STEP 1** | set **TRK/STEP** to 1 (or AUTO) |
| **MASK K ≥ TOP-K** · **MASK P ≥ TOP-P** | lower **MASK K** / **MASK P**: they would skip every choice |

## Other problems

| Symptom | Fix |
|---|---|
| The server window says the model is gated, or no access | accept the license at [huggingface.co/Metacreation/MIDI-GPT](https://huggingface.co/Metacreation/MIDI-GPT) with your Hugging Face account and save a token (see [Install](install.md#hugging-face-account)) |
| Windows: the server stops with a DLL error (`WinError 126`, `c10.dll`) | PyTorch needs Microsoft's Visual C++ runtime: install [vc_redist.x64.exe](https://aka.ms/vc14/vc_redist.x64.exe) |
| Windows: "Windows protected your PC" when starting the server | click **More info › Run anyway**, or right-click the `.bat` › Properties › **Unblock** (the installer unblocks the files itself) |
| Port 3456 already in use | another MIDI-GPT server is running (MIDI-GPT for REAPER uses the same port): use it, or start this one with `--port 3457` and change the address |
| The device won't load after a download | clear the macOS quarantine flag (see [Install](install.md#macos-quarantine)) |
| The first generation is slow | the server loads the model on the first request; later ones are faster |
| Generation is slow overall | on a Mac the GPU (MPS) can be slower than the CPU: start the server with `start-server.sh --device cpu`. Else try `yellow_small`, or run the server on a faster machine |

## Model limits

- **DENSITY** only works on drum tracks; **POLY** and **LENGTH** only on melodic tracks.
- **REGISTER** only applies with **SCALE** on.
- **REMIX** replaces the rhythm settings on the same track. **POLY LIM** and **DENS LIM** win over it: a wider chord
  or a fuller bar comes back with fewer notes.

## Files

| | |
|---|---|
| Settings | `~/Library/Application Support/MIDI-GPT/live.json` |
| Server | `~/Library/Application Support/MIDI-GPT/server` (its window shows the log) |
| Models and the Hugging Face token | `~/.cache/huggingface` |
| Requests that failed on the server | `failed_requests.jsonl` in the server folder |

Still stuck? [Report it](reporting-bugs.md) with what you did and what the
stats screen said.
