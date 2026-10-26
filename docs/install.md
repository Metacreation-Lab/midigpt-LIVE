# Install

## Hugging Face account

The models are downloaded from [Metacreation/MIDI-GPT](https://huggingface.co/Metacreation/MIDI-GPT) on Hugging
Face, which needs a free account. Before installing:

1. Sign in at [huggingface.co](https://huggingface.co) and accept the license on the
   [model page](https://huggingface.co/Metacreation/MIDI-GPT).
2. Create an access token in **Settings › Access Tokens**
   ([huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)); the **Read** type is enough.

The installer asks for the token and saves it in `~/.cache/huggingface/token`, where the server finds it on every
start (or run `hf auth login` in the server's environment, or set `HF_TOKEN`). Only the server uses it, to download
the model; the device never sees it. A model that is already downloaded keeps working without one.

## One-line install

macOS and Linux, in Terminal:

```bash
curl -fsSL https://metacreation.net/midigpt-LIVE/bootstrap.sh | bash
```

Windows, in PowerShell:

```powershell
irm https://metacreation.net/midigpt-LIVE/bootstrap.ps1 | iex
```

This downloads the latest release and copies the **MIDI-GPT** folder into your Live User Library (its location is
read from Live's preferences). It then asks whether to set up a server on this computer: a Python environment with
`midigpt` (in `~/Library/Application Support/MIDI-GPT/server`, `~/.config/MIDI-GPT/server` on Linux,
`%APPDATA%\MIDI-GPT\server` on Windows), a **Start MIDI-GPT Server** launcher (Desktop and Start menu shortcuts on
Windows), and the model. On Windows it also offers Microsoft's Visual C++ runtime, which PyTorch needs, and the CUDA
build of PyTorch when there is an NVIDIA GPU.
If no Hugging Face token is saved yet, it asks for one (see [Hugging Face account](#hugging-face-account)). Skip the
server if yours runs on another machine.

Options go after `bash -s --`, for example `… | bash -s -- --no-server`:

| Flag | |
|---|---|
| `--no-server` / `--server` | install only the devices, or set up the server without asking |
| `--model yellow_small` | the smaller, faster model (default `yellow_medium`) |
| `--user-library DIR` | install the devices into another User Library |
| `--zip FILE` | install from a downloaded release zip |
| `--yes` | accept every default (a Hugging Face token is then read from `HF_TOKEN`) |
| `--uninstall` | remove everything (see below) |

On Windows the options are PowerShell flags, passed through a script block, for example
`& ([scriptblock]::Create((irm https://metacreation.net/midigpt-LIVE/bootstrap.ps1))) -NoServer`: `-NoServer` / `-Server`, `-Model`, `-UserLibrary`, `-Zip`, `-Gpu` / `-Cpu` (the PyTorch build), `-Yes`, `-Uninstall`.

## Manual install

1. **The devices.** Download `MIDI-GPT-for-Live-<version>.zip` from the
   [latest release](https://github.com/Metacreation-Lab/midigpt-LIVE/releases/latest), unzip it, and move the `MIDI-GPT`
   folder into your User Library (by default `~/Music/Ableton/User Library`). Keep its contents together:

    | File | |
    |---|---|
    | `MIDI-GPT.amxd` | the device you use |
    | `MIDI-GPT Instrument.amxd` | a small tag MIDI-GPT adds to each track to remember its instrument; you never add it yourself |
    | `Server/` | the server launchers: **Start MIDI-GPT Server.command** (macOS), **.bat** (Windows), `start-server.sh` (Linux) |

2. **A Python environment** with Python 3.10–3.14 (3.10–3.12 on an Intel Mac), in the server folder the launchers look in:

    | OS | server folder |
    |---|---|
    | macOS | `~/Library/Application Support/MIDI-GPT/server` |
    | Linux | `~/.config/MIDI-GPT/server` |
    | Windows | `%APPDATA%\MIDI-GPT\server` |

    ```bash
    python3.12 -m venv ~/Library/Application\ Support/MIDI-GPT/server/.venv     # Windows: py -3.12 -m venv "%APPDATA%\MIDI-GPT\server\.venv"
    source ~/Library/Application\ Support/MIDI-GPT/server/.venv/bin/activate    # Windows: "%APPDATA%\MIDI-GPT\server\.venv\Scripts\activate"
    ```

3. **MIDI-GPT:**

    ```bash
    pip install "midigpt[http,inference]==0.4.2"
    ```

    On an Intel Mac, add `"torch<2.3" "numpy<2"` (the last PyTorch built for Intel Macs).

4. **Sign in to Hugging Face** with your token (see [Hugging Face account](#hugging-face-account)):

    ```bash
    hf auth login
    ```

5. **Start the server** from the `Server` folder inside `MIDI-GPT`: double-click **Start MIDI-GPT Server.command** (macOS)
    or **Start MIDI-GPT Server.bat** (Windows), or run `start-server.sh` (Linux). The first start downloads the model.
    Leave the window open while you work; Ctrl+C stops the server. To use another model or port, put `MODEL=yellow_small`
    or `PORT=3457` lines in a `server.conf` file in the server folder.

    !!! note "GPU or CPU"
        The server uses the GPU when there is one (CUDA, or MPS on a Mac). **On a Mac, MPS can be slower than the CPU** for a model this size (twice as slow on an Intel Mac with a Radeon GPU): if generations are slow, start it with `start-server.sh --device cpu`.

## The server on another computer

The server can run on a more powerful machine, such as a studio computer. Start it there with `--host 0.0.0.0` (`start-server.sh --host 0.0.0.0`) so
other machines can reach it, then enter its address on the device's [SETUP](guide/setup.md) page. The device
remembers it for every set.

## macOS quarantine

macOS quarantines files downloaded with a browser. If Live won't load the device, or the launcher won't open, clear
the flag (the one-line installer does this for you):

```bash
xattr -dr com.apple.quarantine ~/Music/Ableton/User\ Library/MIDI-GPT
```

## Update or uninstall

Run the one-line install again to update: it replaces the devices and keeps your settings and server. To remove
everything:

```bash
curl -fsSL https://metacreation.net/midigpt-LIVE/bootstrap.sh | bash -s -- --uninstall
```

On Windows, in PowerShell:

```powershell
& ([scriptblock]::Create((irm https://metacreation.net/midigpt-LIVE/bootstrap.ps1))) -Uninstall
```

This removes the MIDI-GPT folder from the User Library, the server environment, the launchers and the settings.
Downloaded models stay in `~/.cache/huggingface`; delete `models--Metacreation--MIDI-GPT` there to free the space.
The Hugging Face token stays there too; `hf auth logout` removes it.
