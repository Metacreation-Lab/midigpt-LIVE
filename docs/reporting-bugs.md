# Reporting bugs

MIDI-GPT for Live is in **beta**: it works, but it hasn't been used on many machines or sets yet, and some
combinations of settings will still go wrong. Reports are how those get found and fixed, so please send them,
including small ones (a control that does nothing, a confusing message, a window that doesn't update).

[Report a bug](https://github.com/Metacreation-Lab/midigpt-LIVE/issues/new?template=bug_report.yml){ .md-button .md-button--primary }
[See open issues](https://github.com/Metacreation-Lab/midigpt-LIVE/issues){ .md-button }

You need a free GitHub account. Search the open issues first: if yours is there, add what you saw to it.

## What to include

The form asks for these. The more of them you can give, the faster a bug can be reproduced.

1. **What you did and what happened**, step by step, and what you expected instead. "I painted bars 3 and 5 on the
   bass, turned on REMIX, pressed GENERATE, and the readout said SRV FAULT" is far more useful than "remix is
   broken".
2. **What the device showed**: the code and message on the **OUTPUT** screen (for example **CHECKS FAIL**,
   **SRV FAULT**, **CTX LIMIT**), and the stats screen if it says something unusual. A screenshot of the window is
   ideal.
3. **The settings involved**: the model, CONTEXT, BARS/STEP, TRK/STEP, PROB, TAKES, and the TRACK and MASKS
   controls on the tracks you generated (REMIX, SCALE, RHYTHM, AR...). A screenshot of each bay works too.
4. **The server window**: copy the lines around the error, from the request that failed to the end. Messages
   starting with `Traceback` or `ERROR` are the important ones.
5. **Versions**:
    - MIDI-GPT for Live: the first line of `README.txt` in the MIDI-GPT folder of your User Library.
    - Ableton Live (Live › About Live), and whether Max is the one bundled with Live or a separate install.
    - Your system (macOS 14.5, Windows 11, Ubuntu 24.04...), and Intel or Apple silicon on a Mac.
    - The server: where it runs (this computer or another one) and the midigpt version, which this prints:

        ```bash
        # macOS
        "$HOME/Library/Application Support/MIDI-GPT/server/.venv/bin/python" -c "import midigpt; print(midigpt.__version__)"
        # Linux
        ~/.config/MIDI-GPT/server/.venv/bin/python -c "import midigpt; print(midigpt.__version__)"
        ```

        ```powershell
        # Windows (PowerShell)
        & "$env:APPDATA\MIDI-GPT\server\.venv\Scripts\python.exe" -c "import midigpt; print(midigpt.__version__)"
        ```

## The failed-request file

When a generation fails on the server, the server saves the request it got, including the notes of the clips it
was sent, to `failed_requests.jsonl` in the server folder:

| System | File |
|---|---|
| macOS | `~/Library/Application Support/MIDI-GPT/server/failed_requests.jsonl` |
| Linux | `~/.config/MIDI-GPT/server/failed_requests.jsonl` |
| Windows | `%APPDATA%\MIDI-GPT\server\failed_requests.jsonl` |

This file lets a failure be replayed exactly, so it is the most useful thing you can attach. **It contains the MIDI
of your clips**: only attach it if you're happy to share that music. Each line is one failed request; the last line
is the most recent. To send just that one:

```bash
tail -n 1 "$HOME/Library/Application Support/MIDI-GPT/server/failed_requests.jsonl" > last_failed_request.json
```

GitHub doesn't take `.json` or `.jsonl` attachments: zip the file, or rename it to `.txt`, before dragging it into
the issue.

## Ideas and questions

Suggestions are welcome as issues too: choose **Feature request** instead of **Bug report**. For questions about
the MIDI-GPT model itself (training, checkpoints, the paper), see
[MIDI-GPT on GitHub](https://github.com/Metacreation-Lab/MIDI-GPT).
