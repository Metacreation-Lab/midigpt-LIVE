# Choosing what to write

![The roll](../assets/panel/roll.png)

The roll at the top of the window shows every MIDI track in the selected scene, bar by bar, with the notes of its
clip. Everything you generate is chosen here.

## Targets and context

A track is a **target** when you paint some of its bars or turn on its **AR** button. Every other track is
**context**: MIDI-GPT reads it to fit the new notes to the music, and leaves it untouched. The line under the roll
lists the current targets (`TGT LEAD (AR)`), or says **PAINT BARS** when there are none.

| Do this | To |
|---|---|
| Click or drag across bars | paint them for rewriting (orange brackets). Drag again from a painted bar to unpaint. |
| **AR** | write the whole track (autoregressive), including a track with no clip in this scene yet; it then gets one |
| **IG** | ignore the track: it is neither written nor used as context |
| Click a track name | select it, for the [TRACK](track.md) and [MASKS](masks.md) controls |

Painting bars on an **AR** or ignored track switches those off: the three modes are exclusive.

!!! note "Scenes"
    MIDI-GPT works on the selected scene. All its clips must share one time signature, and the scene needs at least
    **CONTEXT** bars (see [Engine](engine.md)). The clips' loop lengths set how many bars the roll shows.

## Rewrite a few bars, or a whole track

- **Infill** keeps everything around the painted bars, so the new notes join the existing part at both ends: good for
  fixing a bar or varying the end of a phrase.
- **AR** writes the track from its start. Use it for a new part, or to replace one completely.

<video src="../assets/video/rewrite.mp4" poster="../assets/video/rewrite.jpg" autoplay muted loop playsinline></video>
