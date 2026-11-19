# Pipeline

Tools that turn a recording into a library clip. Everything that makes clips play in
sync and in key happens here, never in the app.

## Install (once)

```sh
brew install ffmpeg rubberband
python3 -m venv .venv && source .venv/bin/activate
pip install -r pipeline/requirements.txt
```

## Tools

| Script             | Purpose                                                                 |
|--------------------|-------------------------------------------------------------------------|
| `analyze.py`       | BPM, key + confidence, LUFS, duration, first strong onset. `--json` too |
| `prepare_clip.py`  | Source → exact-loop clip at the manifest tempo/key/loudness + manifest entry |
| `library.py`       | `list`, `add`, `replace`, `remove` clips. Every change bumps the manifest version |
| `render_midi.py`   | `.mid` → exact loop at the manifest tempo/bars/beats, −16 LUFS. Used by `--midi`. `--stems` writes one `.mid` + `.wav` per track |
| `sf2.py`           | SoundFont sample player used by `render_midi.py` for the instrument sounds |
| `check_library.py` | Verify every clip and stem: length, loudness, clipping, manifest shape. Exit 0 = green |

## Example

```sh
source .venv/bin/activate
python pipeline/analyze.py "sources/ריקוד חסידי.mp3"
python pipeline/prepare_clip.py "sources/ריקוד חסידי.mp3" --asset culture --title "ריקוד חסידי" \
    --credit "הקלטה ביתית" --bars 8
python pipeline/check_library.py
```

`prepare_clip.py` writes `clips/<asset>-NN.wav` (mono, 44.1 kHz, 16-bit, exact sample
count; committed) and a stereo 24-bit master in `sources/prepared/<asset>-NN.wav`
(git-ignored). Clips are WAV because MP3 cannot hold an exact loop length and
would drift against the other channels. Override detection with `--bpm`,
`--key` and `--start` when the analysis is wrong; `--bars` overrides the manifest default.
`--tempo-ratio 1.5` (or 0.5, 2) stretches to library tempo × ratio and cuts bars × ratio
source bars, for sources far from the library tempo. Only 4 beats per bar is supported.

## Managing the library

```sh
python pipeline/library.py list
python pipeline/library.py add "sources/<file>" --asset values --title "<title>" --credit "<credit>"
python pipeline/library.py replace <clip-id> "sources/<file>" [--title "<title>"] [--start S] [--bpm N] [--key K]
python pipeline/library.py add --midi midi/<name>.mid --asset <id> --title "<title>" --credit "עיבוד MIDI"
python pipeline/library.py replace <clip-id> --midi midi/<name>.mid
python pipeline/library.py remove <clip-id>
```

`--midi` renders the file with `render_midi.py` instead of preparing a recording:
no detection, no stretch, no shift. The render is already at the manifest tempo
(tempo, bars and beats per bar come from `manifest.json`; flags override) and at
−16 LUFS; it becomes the master in `sources/prepared/` and then runs through the
same exact-length, loudness and export steps. The edge fade defaults to 0 ms for
MIDI because the render wraps its tail across the loop seam. `source` in the
manifest records the MIDI path, e.g. `midi/israel-hatikva-full.mid`. See the
"MIDI clips" section of the top-level README for the workflow.

A melody track that carries pitch-bend or expression (CC11) is rendered as a
sung line: notes that touch are tied, the pitch follows note + bend (bend range
from RPN 0, else 2 semitones) and the level follows CC11.

Sound. `render_midi.py` plays sampled instruments when it finds a SoundFont:
the file named by `$MIXER_SOUNDFONT`, else the first `.sf2` (by name) in
`sources/soundfonts/` that is really on disk. `sf2.py` is the player (pure
numpy, nothing to install); each track uses the instrument of its General MIDI
program (a track named melody always gets a held instrument, the flute), the
tracks are balanced with the melody in front, and a short room reverb is added.
`sources/` is not in Git, so a fresh clone has no SoundFont and falls back to
the built-in synth; the render log says which one played. After changing the
SoundFont or the renderer, `sources/transcribe/rerender.py` renders every MIDI
clip and stem again.

`replace` keeps the clip id and its position in the picker, so the participant's
choice stays valid. `remove` refuses to delete an asset's last clip. Every command
bumps `version` in `manifest.json`, which makes phones drop their saved clip
choices (fader levels survive). Run `check_library.py` afterwards.

Replace the placeholder for עברית with a new source:

```sh
python pipeline/library.py replace hebrew-01 "sources/<file>" --title "<title>" --credit "<credit>"
python pipeline/check_library.py
```
