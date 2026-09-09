# Identity Mixer — Architecture

## Product summary

Identity Mixer is a phone-first, Hebrew (RTL) static web app for מכינה workshops. Six mixer channels stand for six assets of Jewish identity: השפה העברית, ישראל, עולם ערכים, תרבות, זיכרון היסטורי, אורח חיים. A participant picks one clip per asset from a curated audio library, sets each fader to how strongly that asset lives in them, and hears all six loop together in sync and in key. The fader positions become a six-axis "profile" shape the participant can share with the facilitator.

## Design invariants

1. **One tempo, one key, fixed in `manifest.json`.** The whole library shares a single tempo and a single key. All synchronisation and harmonisation work happens in the preparation pipeline, never at runtime. The player does exactly one audio job: start all loops together and keep them running.
2. **Every clip is an exact whole-bar loop.** Default length is 8 bars at the shared tempo. Every clip is loudness-matched so faders mean the same thing across assets.
3. **No build step, no framework.** The app is `index.html` + `app.js` + `styles.css` + `manifest.json` + `clips/`. It deploys as plain static files to any host.
4. **Hebrew, RTL, phone-first, iOS Safari compatible.** The `AudioContext` is created and resumed only inside the play tap, because iOS refuses audio that is not user-initiated.
5. **One copy of every file, versioned with Git.** No `*_v2` files, no duplicate folders, no "backup" copies. History lives in Git.

## Repository layout

```
index.html            Single page: mixer UI, profile view, share
app.js                Manifest loading, Web Audio scheduling, faders, profile
styles.css            RTL, phone-first layout
manifest.json         Shared tempo/key/bars + assets + clips
clips/                Prepared loops (MP3, committed)
sources/              Original recordings (git-ignored, never committed)
pipeline/
  prepare_clip.py     Source recording -> prepared loop + manifest entry
  analyze.py          Report BPM / key / downbeat of a source file
  check_library.py    Verify every manifest clip exists, loops exactly, matches tempo/key/loudness
  requirements.txt    Python dependencies
facilitator/
  index.html          Room view: overlay of participant profiles (later phase)
README.md             How to run, how to add a clip, how to deploy
CLAUDE.md             Project rules for every working session
ARCHITECTURE.md       This document
```

## `manifest.json` schema

Top level:

| Field   | Type   | Meaning                                              |
|---------|--------|------------------------------------------------------|
| `tempo` | number | Shared BPM for the whole library                     |
| `key`   | string | Shared key, e.g. `"D minor"`                         |
| `bars`  | number | Default loop length in bars (clips may override)     |
| `assets`| array  | Exactly six entries, in the canonical order          |

Each asset:

| Field         | Type   | Meaning                                         |
|---------------|--------|-------------------------------------------------|
| `id`          | string | Stable ASCII slug used in filenames and URLs    |
| `name`        | string | Hebrew display name                             |
| `color`       | string | CSS colour for the channel and the profile axis |
| `description` | string | One Hebrew sentence shown under the channel     |
| `clips`       | array  | Prepared loops available for this asset         |

Each clip:

| Field    | Type   | Meaning                                                   |
|----------|--------|-----------------------------------------------------------|
| `id`     | string | `<asset>-NN`, matches the filename                        |
| `title`  | string | Hebrew title shown in the clip picker                     |
| `note`   | string | One short Hebrew line: what this clip is and why it fits  |
| `file`   | string | Path relative to repo root, e.g. `clips/hebrew-01.mp3`    |
| `source` | string | Original filename under `sources/` (for traceability)     |
| `credit` | string | Performer / origin / licence note                         |

Example with one asset:

```json
{
  "tempo": 92,
  "key": "D minor",
  "bars": 8,
  "assets": [
    {
      "id": "hebrew",
      "name": "השפה העברית",
      "color": "#3A7BD5",
      "description": "המילים שבהן אנחנו חושבים, שרים ומתווכחים.",
      "clips": [
        {
          "id": "hebrew-01",
          "title": "שיר ערש",
          "note": "קול אחד, בלי ליווי. עברית כנשימה.",
          "file": "clips/hebrew-01.mp3",
          "source": "hebrew_lullaby_take2.wav",
          "credit": "הקלטה ביתית, 2026, שימוש בהסכמה"
        }
      ]
    }
  ]
}
```

Asset ids and canonical order: `hebrew`, `israel`, `values`, `culture`, `memory`, `lifestyle`.

## Pipeline contract: `pipeline/prepare_clip.py`

### CLI

```
prepare_clip.py <source> --asset <id> --title <t> [--bpm N] [--key K] [--start seconds] [--bars N]
```

- `<source>` is a file under `sources/`.
- `--asset` must be one of the six ids in the manifest.
- `--title` is the Hebrew title written into the manifest.
- `--bpm` and `--key` override detection when analysis is wrong or ambiguous.
- `--start` is a seconds offset that overrides the detected downbeat.
- `--bars` overrides the manifest default loop length.

### Steps

1. **Load** the source with `librosa` at its native sample rate, mixed to mono for analysis, stereo preserved for output.
2. **Detect** BPM, key and first downbeat, or take them from `--bpm`, `--key`, `--start`. Print what was detected and what was used.
3. **Cut** exactly `bars` bars from the downbeat at the *source* tempo. Length in samples is `bars * 4 * (60 / source_bpm) * sr`, rounded to an integer.
4. **Stretch and shift** with `pyrubberband`: time-stretch by `manifest.tempo / source_bpm`, and pitch-shift to the manifest key. The shift is relative-major-aware (a source in F major targeting D minor shifts by 0 semitones) and always uses the smallest signed semitone distance, in the range −6 to +5.
5. **Normalise** to −16 LUFS integrated with `pyloudnorm`, apply 5 ms linear fades at both ends, then verify the sample count equals `bars * 4 * (60 / manifest.tempo) * sr` exactly. Trim or pad by at most a few samples; abort if the difference is larger.
6. **Export** MP3 at 192 kbps via `ffmpeg` (libmp3lame) to `clips/<asset>-NN.mp3`, plus a lossless WAV in `sources/prepared/` (git-ignored), where `NN` is the next free two-digit index for that asset.
7. **Append** the clip entry to `manifest.json` under the matching asset, preserving existing formatting and key order.
8. **Print** a summary: source, detected vs used BPM/key/downbeat, semitone shift, stretch ratio, loudness before/after, final length in samples and bars, output path.

`check_library.py` re-derives step 5 for every clip in the manifest and exits non-zero on any mismatch. `analyze.py` runs step 2 only and prints the result, for auditioning sources before committing to a cut.

### Dependencies

System (Homebrew): `ffmpeg`, `rubberband`.
Python (`pipeline/requirements.txt`): `librosa`, `soundfile`, `pyrubberband`, `pyloudnorm`, `numpy`. (`pydub` was dropped: it needs the `audioop` module that Python 3.13 removed; ffmpeg encodes the MP3 directly.)

## Phases

1. **Bootstrap.** Build the app from the prototype: six channels, faders, play/stop, profile shape. Test on a real phone over the local network.
2. **Pipeline.** Implement `prepare_clip.py`, `analyze.py`, `check_library.py`. Prepare one real clip per asset. `check_library.py` is green.
3. **Deploy.** Publish to GitHub Pages. Generate a QR code for the room.
4. **Sharing.** Encode the profile in the URL (`?p=60,40,90,20,70,50`). Build `facilitator/index.html` to overlay many profiles in one view.
5. **Depth and polish.** Several clips per asset, PWA manifest and offline cache, visual and copy polish.

## Working rhythm

One task per session. Test on the phone after each task. Commit when it passes, and only then.
