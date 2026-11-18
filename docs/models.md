# Models

The server can load several models at once. Each one shows up on the device's [ENGINE](guide/engine.md) page, under
**Models**, where you pick the one to generate with. Which models the server loads is set in one file,
**models.yaml**, in the server folder. You change it with a text editor: no commands needed.

## The models

| Model | Download | |
|---|---|---|
| `yellow_medium` | 350 MB | the default: best results |
| `yellow_small` | 83 MB | faster on older computers |
| `prism_medium` | 360 MB | adds **KEY**, **RANGE**, **GENRE** and per-bar controls ([TRACK](guide/track.md)) |
| `expressive_medium` | 360 MB | as prism, plus velocity and timing (**EXPRESSIVENESS**, **VELOCITY**, **MICRO**) |

Each model the server loads stays in memory while it runs: switch on the ones you use.

## Open models.yaml

The installer puts it in the server folder:

| OS | file |
|---|---|
| macOS | `~/Library/Application Support/MIDI-GPT/server/models.yaml` |
| Linux | `~/.config/MIDI-GPT/server/models.yaml` |
| Windows | `%APPDATA%\MIDI-GPT\server\models.yaml` |

- **macOS:** in Finder, choose **Go › Go to Folder…**, paste `~/Library/Application Support/MIDI-GPT/server`, and
  open `models.yaml` with TextEdit (if TextEdit shows formatting tools, choose **Format › Make Plain Text**).
- **Windows:** paste `%APPDATA%\MIDI-GPT\server` in File Explorer's address bar and open `models.yaml` with Notepad.

The installer writes this file once and never replaces it: your changes survive updates. The server window says which
models it loaded when it starts.

## Add a model

The models from [Metacreation/MIDI-GPT](https://huggingface.co/Metacreation/MIDI-GPT) are already in the file, one per
line. The ones starting with `#` are switched off:

```yaml
models:
  # MIDI-GPT models from huggingface.co/Metacreation/MIDI-GPT
  - {id: yellow_medium, pretrained: yellow_medium}            # 350 MB, the default: best results
  # - {id: yellow_small, pretrained: yellow_small}            # 83 MB, faster on older computers
  # - {id: prism_medium, pretrained: prism_medium}            # 360 MB, adds key, pitch range, genre and per-bar controls
  # - {id: expressive_medium, pretrained: expressive_medium}  # 360 MB, as prism, plus velocity and timing (EXPRESSIVENESS)
```

1. Delete the `# ` (the hash and the space after it) at the start of the model's line, so it lines up with the
   `yellow_medium` line above it.
2. Save the file.
3. Restart the server: close its window (or press Ctrl+C in it) and open **Start MIDI-GPT Server** again. A new model
   downloads on this first start, so it takes a little longer.
4. In the device, open **ENGINE** and pick the model under **Models**.

To switch a model off, put the `# ` back. The device starts with the model named on the `default_model:` line; change
it to any model that is switched on.

!!! note "Spaces matter"
    Keep each model line indented by two spaces, exactly like the others. If the server window says it can't read
    models.yaml, check the line you changed against the ones around it.

## A model from another Hugging Face repository

A model shared on Hugging Face as a `.safetensors` file loads the same way. Add a line under `models:` with:

- `id`: the name the device shows, your choice (letters, digits, `_` and `-`)
- `pretrained`: the start of the file name, before `-final.safetensors` or `-step….safetensors` (for
  `my_model-final.safetensors`, `my_model`). The file must be named that way; with no `-final` file, the highest step
  is used.
- `hf_repo`: the repository, as `account/repository` in its Hugging Face address

```yaml
  - {id: my_model, pretrained: my_model, hf_repo: my-account/my-repo}
```

If the repository is gated (it asks you to accept a license), accept it with the account whose token the server uses
(see [Hugging Face account](install.md#hugging-face-account)).

## A model file on this computer

For a checkpoint you trained or downloaded yourself, give the full path to its `.safetensors` file with `ckpt`:

```yaml
  - {id: my_local_model, ckpt: /Users/me/Models/my_model-final.safetensors}
```

On Windows, use forward slashes: `ckpt: C:/Users/me/Models/my_model-final.safetensors`. Write the path out in full:
`~` doesn't work here. The model must be a MIDI-GPT checkpoint, such as one trained with the
[midigpt](https://github.com/Metacreation-Lab/MIDI-GPT) package.

## GPU or CPU

The `device:` line sets where the models run: `auto` (the GPU when there is one, the default) or `cpu`. On a Mac the
GPU can be slower than the CPU for these models: if generations are slow, change it to `device: cpu` and restart the
server.

## Without models.yaml

If you delete models.yaml, the server loads a single model again: the one in `MODEL=` in `server.conf`, in the same
folder. Running the installer again writes a fresh models.yaml. To try a model once without editing anything, start
the server from a terminal with `start-server.sh --pretrained yellow_small` (`Start MIDI-GPT Server.bat --pretrained
yellow_small` on Windows): it ignores models.yaml.
