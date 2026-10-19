# Quick start

From an empty device to your first take in five steps.

1. **Start the server.** Open **Start MIDI-GPT Server** (on the Desktop, or in the MIDI-GPT folder), or run
   `midigpt-http` as in [Install](install.md); the first start downloads the model with your Hugging Face token. On the device's **SETUP** page, the light next to the address turns
   green when the server answers.
2. **Add the device.** In Live's browser, open **User Library › MIDI-GPT** and drag **MIDI-GPT** onto any track. Click
   the key on the device to open its window.
3. **Tell it your instruments.** Run **SETUP › SETUP ALL** once per set. MIDI-GPT guesses each track's instrument from
   its device and name, lets you confirm each guess, and saves it on the track. See [Setup](guide/setup.md).
4. **Choose what to write.** Select a scene with some MIDI clips. In the roll at the top of the window, paint the bars
   to generate on a track, or turn on **AR** to write the whole track.
5. **Generate.** Press **GENERATE**. When it is done, the result is already playing in your clips: step through the
   takes, then press **KEEP**.

<video src="assets/video/generate.mp4" poster="assets/video/generate.jpg" autoplay muted loop playsinline></video>

!!! tip "Where to go next"
    The [interface guide](guide/roll.md) explains every control, and [Workflows](workflows.md) shows the common ways
    to use them together.
