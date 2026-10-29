# Identity Mixer

Phone web app for מכינה workshops — six assets of Jewish identity as a six-channel mixer.

## Run locally and test on a phone

The app is static files, no build step. Serve the repo root and open it on a phone
on the same Wi-Fi network. The server must bind IPv4 explicitly, or the phone
cannot reach it:

```sh
python3 -m http.server 8000 --bind 0.0.0.0
```

Open on the phone the address of the Mac's `en0` interface:

```sh
echo "http://$(ipconfig getifaddr en0):8000"
```

On iOS Safari, audio only starts after a tap on the play button. If nothing plays,
make sure the phone is not on silent mode (the side switch) and the volume is up.

## Layout

See `ARCHITECTURE.md` for the full design and `CLAUDE.md` for project rules.

```
index.html      mixer UI
app.js          manifest loading, Web Audio scheduling, faders, persistence
profile.js      SVG radar profile (shared later with the facilitator page)
styles.css      RTL, phone-first layout
manifest.json   shared tempo / key / bars + six assets + their clips
clips/          prepared loops: WAV, mono, 44.1 kHz, 16-bit, exact whole-bar length.
                WAV, not MP3, on purpose: MP3 cannot hold an exact loop length
                (encoder padding, decoder trimming) and the loops would drift apart.
midi/           the MIDI behind every MIDI-rendered clip (source of truth, committed)
pipeline/       Python tools that prepare clips (Phase 2)
```

## MIDI clips

The current six clips are rendered from MIDI, not cut from recordings. For them
`midi/` is the source of truth and `clips/` is the build product:

- `midi/<name>.mid` is the thing you edit: one file per clip, separate tracks for
  melody, bass, guitar or pad, and drums, written in the library key. Change it in
  a DAW, then re-render. Never edit a rendered WAV by hand.
- `clips/<asset>-NN.wav` is what `pipeline/render_midi.py` makes from it, through
  `library.py --midi`: an exact whole-bar loop at the manifest tempo, −16 LUFS,
  committed like any other clip.
- `manifest.json` points `source` at the MIDI (for example
  `midi/israel-hatikva-full.mid`) and carries `credit: "עיבוד MIDI"`.

Re-render one clip after editing its MIDI (the clip keeps its id and picker position):

```sh
python pipeline/library.py replace israel-02 --midi midi/israel-hatikva-full.mid
python pipeline/check_library.py
```

Add a new MIDI clip:

```sh
python pipeline/library.py add --midi midi/<name>.mid --asset <id> --title "<title>" \
    --note "מעובד מ-MIDI, 8 תיבות ב-100 BPM, רה מינור" --credit "עיבוד MIDI"
```

Stems: a MIDI clip can also list per-instrument loops (`"stems"` in the manifest,
WAVs under `clips/stems/`, MIDI under `midi/stems/`). The player then plays the stems
instead of the full file, all started together, and each chip under the channel
switches one of them on or off without touching the others. `render_midi.py
midi/<name>.mid sources/stems --stems` writes one `.mid` and `.wav` per track; the
manifest's `stems_gain` (computed by the pipeline, checked by `check_library.py`)
trims them so that all stems together are as loud as a plain clip.

`render_midi.py` reads tempo, bars and beats per bar from `manifest.json`, so after a
tempo or loop-length change re-render every MIDI clip with `replace --midi` and the
library stays in sync. The renderer does not shift pitch: after a key change,
transpose the MIDI files in the DAW first (or render once by hand with
`render_midi.py --transpose N` to audition).

## Deploy

The site is served by GitHub Pages from the `main` branch root of
https://github.com/Metastaseis/identity-mixer. Public URL:

https://metastaseis.github.io/identity-mixer/

To publish an update: make the change, run `python pipeline/check_library.py`,
test on the phone, commit, then

```sh
git push origin main
```

Pages rebuilds automatically; the change is live within about a minute.
`qr.png` in the repo root encodes the public URL for the workshop room.
Only `clips/` is committed; `sources/` never leaves this machine.

## Adding a clip

```sh
brew install ffmpeg rubberband
python -m venv .venv && source .venv/bin/activate
pip install -r pipeline/requirements.txt
python pipeline/prepare_clip.py sources/<file> --asset <id> --title "<title>"
python pipeline/check_library.py
```
