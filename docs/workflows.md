# Workflows

The common ways to put the controls together. Each one starts with a scene selected and the device window open.

## Write a new track

A new part that fits the rest of the scene: a lead over a groove, a bass under chords.

1. Add an empty MIDI track with the instrument you want, and run **SETUP SEL** on it so MIDI-GPT knows what it is.
2. Turn on its **AR** button in the roll.
3. Shape it with [TRACK](guide/track.md): **POLY 1–1** for a monophonic line, for example.
4. Set **TAKES** to 4 and press **GENERATE**, then pick the take you like and press **KEEP**.

<video src="assets/video/generate.mp4" poster="assets/video/generate.jpg" autoplay muted loop playsinline></video>

## Rewrite part of a track

Keep what works and replace the rest: a better ending, a variation for the second half.

1. Paint the bars to rewrite on that track. The bars on either side are kept and the new notes join them.
2. Press **GENERATE**. Switch between the take and the original with the take keys and **↩**.

<video src="assets/video/rewrite.mp4" poster="assets/video/rewrite.jpg" autoplay muted loop playsinline></video>

## Explore with takes

Ask for several options and choose by ear.

1. Set **TAKES** between 2 and 16.
2. Generate, then click through the takes while the music plays: each is written into the clip as you select it.
3. **KEEP** the one you like, or **↩** to go back. To hear more like a take, select it and press **LOCK** under the
   seed before generating again.

<video src="assets/video/takes.mp4" poster="assets/video/takes.jpg" autoplay muted loop playsinline></video>

## Keep a groove, change the notes

1. On the target track, turn on **RHYTHM** and choose **EXACT** to keep onsets where you draw them, or **GRID** for
   a looser feel.
2. Or turn on **REMIX** to keep the rhythm of the existing notes and vary their pitches (and durations with **P+D**).
3. Lock the key with **SCALE**, **ROOT** and **MODE**.

<video src="assets/video/masks.mp4" poster="assets/video/masks.jpg" autoplay muted loop playsinline></video>

## Reproduce a result

Every generation reports its seed on the stats screen. **LOCK** keeps it; with the same scene, targets and settings,
generating again gives the same notes. Type a seed you noted down by clicking the seed screen.
