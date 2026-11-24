# Pipeline

Tools that turn a song into library clips: one instrument part per clip, rendered.
Everything that makes clips play in sync, in key and on one progression happens here,
never in the app.

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
| `prepare_clip.py`  | Manifest reading and writing (`load_manifest`, `save_manifest`). Its recording CLI is retired |
| `library.py`       | `list` and `remove` clips (remove also deletes the clip's part). Every change bumps the manifest version |
| `render_midi.py`   | `.mid` → exact loop at the manifest tempo/bars/beats. `arrange/rerender.py` renders every part with it |
| `sf2.py`           | SoundFont sample player used by `render_midi.py` for the instrument sounds |
| `check_library.py` | Verify the manifest (six assets, each with its instrument), every clip (its part and source exist; exact length, −16 ± 1 LUFS, never full scale), no unreferenced file in `clips/`, `midi/parts/` or `midi/` (`midi/alternates/` is exempt), no stems, and `arrange/fit.py`. Exit 0 = green |
| `arrange/`         | The 16 hand-written songs (`songs.py`, `manual.py` → `midi/` via `convert.py`), `parts.py` (song MIDI → each clip's part), `fit.py` (do the parts fit together), `rerender.py` (parts, then one render per clip), plus the study tools; see `convert.py`'s docstring. Writing a song needs the recordings in `sources/` or the caches in `arrange/sect/` and `arrange/sep/`; `rerender.py` needs neither |

## Managing the library

```sh
source .venv/bin/activate
python pipeline/library.py list
python pipeline/arrange/convert.py <slug> --apply     # a song in songs.py + manual.py -> midi/<slug>.mid, its part, its clip
python pipeline/arrange/rerender.py [clip ids]        # every part and every clip again, from committed MIDI
python pipeline/arrange/fit.py                        # do the parts of all columns fit together (exit 0)
python pipeline/check_library.py
python pipeline/library.py remove <clip-id>
```

A clip is one part: `parts.py` writes `midi/parts/<slug>--<instrument>.mid` from the song's
MIDI (`source`), and `rerender.py` renders it to `clips/<clip id>.wav` (mono, 44.1 kHz,
16-bit, exact sample count, −16 LUFS, peaks limited to 0.95). Clips are WAV because MP3
cannot hold an exact loop length. Only 4 beats per bar is supported.

A melody track that carries pitch-bend or expression (CC11) is rendered as a
sung line: notes that touch are tied, the pitch follows note + bend (bend range
from RPN 0, else 2 semitones) and the level follows CC11.

Sound. `render_midi.py` plays sampled instruments from the pinned SoundFont:
the file named by `$MIXER_SOUNDFONT`, else `sources/soundfonts/Merlin.sf2`.
`sf2.py` is the player (numpy
and scipy, nothing else to install); each track uses the instrument of its General MIDI
program (a track named melody always gets a held instrument, the flute), the
tracks are balanced with the melody in front, and a short room reverb is added.
After a change to the renderer or to `parts.py`, `pipeline/arrange/rerender.py`
writes every part and renders every clip again from committed files only (the song
MIDI in `midi/` as committed). A fresh clone rebuilds the whole library this way,
given Merlin.sf2 (`sources/` is not in Git, so put it
there or point `MIXER_SOUNDFONT` at it). Run `check_library.py` afterwards.

SoundFont. Library renders use **Merlin.sf2** (11,583,258 bytes, sha256
`a3ebced39a1264849616f160bd135d77efd19ddb2be129aa9b9d964ba391f979`), bundled with
the SCAMP Python package 0.9.0 (https://pypi.org/project/scamp/0.9.0/, source
https://sr.ht/~marcevanstein/scamp/). It is pinned by name and checksum in
`sf2.py` (`PINNED`): no other `.sf2` is ever used, and a render stops with an
error if the file is missing or its sha256 differs. `MIXER_SOUNDFONT` may point
at the same file elsewhere (it is checked the same way). `MIXER_SOUNDFONT=builtin`
is the explicit opt-in to the built-in synth, which no library clip uses.

Demucs. `arrange/sep.py` separates a recording into vocals, bass, other and drums
in its own venv (`torch` 2.15.0, `demucs` 4.1.0), by default
`~/.venvs/demucs/bin/python`, or the interpreter named by `$DEMUCS_PYTHON`.
It is needed only for a new song or when the caches are missing.

`remove` refuses to delete an asset's last clip and bumps `version` in `manifest.json`,
which makes phones drop their saved clip choices (fader levels survive). Run
`check_library.py` afterwards.
