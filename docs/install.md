# Install

## One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/DaoTwenty/midigpt-LIVE/HEAD/bootstrap.sh | bash
```

This downloads the latest release and copies the **MIDI-GPT** folder into your Live User Library (its location is
read from Live's preferences). It then asks whether to set up a server on this computer: a Python environment in
`~/Library/Application Support/MIDI-GPT/server` with `midigpt`, a **Start MIDI-GPT Server** launcher, and the model.
Skip that step if your server runs on another machine.

Options go after `bash -s --`, for example `… | bash -s -- --no-server`:

| Flag | |
|---|---|
| `--no-server` / `--server` | install only the devices, or set up the server without asking |
| `--model yellow_small` | the smaller, faster model (default `yellow_medium`) |
| `--user-library DIR` | install the devices into another User Library |
| `--zip FILE` | install from a downloaded release zip |
| `--yes` | accept every default |
| `--uninstall` | remove everything (see below) |

## Manual install

1. **The devices.** Download `MIDI-GPT-for-Live-<version>.zip` from the
   [latest release](https://github.com/DaoTwenty/midigpt-LIVE/releases/latest), unzip it, and move the `MIDI-GPT`
   folder into your User Library (by default `~/Music/Ableton/User Library`). Keep both devices together:

    | File | |
    |---|---|
    | `MIDI-GPT.amxd` | the device you use |
    | `MIDI-GPT Instrument.amxd` | a small tag MIDI-GPT adds to each track to remember its instrument; you never add it yourself |

2. **A Python environment** (any folder works):

    ```bash
    python3.12 -m venv ~/midigpt-server
    source ~/midigpt-server/bin/activate
    ```

3. **MIDI-GPT:**

    ```bash
    pip install "midigpt[http,inference]==0.3.4"
    ```

    On an Intel Mac, add `"torch<2.3" "numpy<2"` (the last PyTorch built for Intel Macs).

4. **Start the server:**

    ```bash
    midigpt-http --pretrained yellow_medium --host 127.0.0.1 --port 3456
    ```

    The first start downloads the model from Hugging Face. Leave the window open while you work; Ctrl+C stops the
    server.

## The server on another computer

The server can run on a more powerful machine, such as a studio computer. Start it there with `--host 0.0.0.0` so
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
curl -fsSL https://raw.githubusercontent.com/DaoTwenty/midigpt-LIVE/HEAD/bootstrap.sh | bash -s -- --uninstall
```

This removes the MIDI-GPT folder from the User Library, the server environment, the launchers and the settings.
Downloaded models stay in `~/.cache/huggingface`; delete `models--Metacreation--MIDI-GPT` there to free the space.
