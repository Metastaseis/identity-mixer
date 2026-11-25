# Identity Mixer — Architecture

## Product summary

Identity Mixer is a phone-first, Hebrew (RTL) static web app for מכינה workshops. Six mixer channels stand for six assets of Jewish identity: עברית, ישראל, עולם ערכים, תרבות, זכרון הסטורי, אורח חיים. Each channel plays one instrument (עברית a clarinet, ישראל drums, עולם ערכים a bass, תרבות a guitar, זכרון הסטורי a violin, אורח חיים a piano). A participant picks a song per asset, and the channel plays that instrument's part of the song; sets each fader to how strongly that asset lives in them; and hears all six loop together in sync, in key and on one shared chord progression. The fader positions become a six-axis "profile" shape the participant can share with the facilitator.

## Design invariants

1. **One tempo, one key, one progression.** The whole library shares a single tempo and key, fixed in `manifest.json`, and a single chord progression (`HARMONY` in `pipeline/arrange/parts.py`) that every bass and harmony part is re-voiced onto, so any part of one column fits any part of another (`fit.py` checks every combination). All synchronisation and harmonisation work happens in the preparation pipeline, never at runtime. The player's audio jobs: start all loops together on one shared grid, swap a channel in place on that grid when a song changes, and keep them running.
2. **Every clip is one instrument part, rendered as an exact whole-bar loop.** Default length is 8 bars at the shared tempo, stored as WAV (mono, 44.1 kHz, 16-bit) so the sample count is exact. MP3 cannot hold an exact loop length: encoders pad the stream and decoders trim differently, so an MP3 loop drifts against the others. Every clip is at −16 LUFS so faders mean the same thing across assets. There are no stems: a clip is one file. The player loops each source over its grid length (`loopEnd`), never over the decoded buffer length.
3. **No build step, no framework.** The app is `index.html` + `app.js` + `profile.js` + `styles.css` + `manifest.json` + `clips/`. It deploys as plain static files to any host.
4. **Hebrew, RTL, phone-first, iOS Safari compatible.** The `AudioContext` is created and resumed only inside the play tap, because iOS refuses audio that is not user-initiated.
5. **One copy of every file, versioned with Git.** No `*_v2` files, no duplicate folders, no "backup" copies. History lives in Git.

## Repository layout

```
index.html            Single page: mixer UI, profile view, share
profile.js            SVG radar profile, shared with facilitator/ later
app.js                Manifest loading, Web Audio scheduling, faders, profile
styles.css            RTL, phone-first layout
manifest.json         Shared tempo/key/bars + assets (each with its instrument) + clips
clips/                Rendered parts, one per clip (WAV mono 44.1 kHz 16-bit, committed)
midi/                 Song MIDI, one per clip (its "source"): the source of truth (committed)
  parts/              One instrument part per clip, re-voiced onto the shared progression (committed)
  alternates/         Alternate feels, not in the library
sources/              Original recordings and SoundFonts (git-ignored, never committed)
pipeline/
  prepare_clip.py     Manifest reading and writing; its recording CLI is retired (clips are rendered parts)
  library.py          list / remove clips; every change bumps the manifest version
  render_midi.py      .mid -> exact loop at the manifest tempo; rerender.py uses it
  sf2.py              SoundFont sample player; render_midi.py plays sampled instruments through it
  analyze.py          Report BPM / key / downbeat of a source file
  check_library.py    Verify every clip, its part and its source; exact loops, loudness, no unreferenced files; runs fit.py
  requirements.txt    Python dependencies
  README.md           The pipeline tools and how to run them
  arrange/            Hand-written arrangements (manual.py) -> midi/, and the tools to write them; caches git-ignored
    parts.py          Song MIDI -> each clip's instrument part (midi/parts/), re-voiced onto HARMONY
    fit.py            Clash score of every combination of parts across columns
    rerender.py       parts.py, then one render per clip: rebuilds the library from committed MIDI
    convert.py        A recording -> midi/<slug>.mid (--apply: then its part and its clip)
facilitator/          Planned (Phase 4), not yet present
  index.html          Room view: overlay of participant profiles
README.md             How to run, how to add a clip, how to deploy
CLAUDE.md             Project rules for every working session
ARCHITECTURE.md       This document
```

## `manifest.json` schema

Top level:

| Field   | Type   | Meaning                                              |
|---------|--------|------------------------------------------------------|
| `version` | integer | Bump whenever clip order or defaults change. The app then drops saved clip choices (fader levels survive) |
| `tempo` | number | Shared BPM for the whole library                     |
| `key`   | string | Shared key, e.g. `"D minor"`                         |
| `bars`  | number | Default loop length in bars (clips may override)     |
| `beats_per_bar` | number | Must be 4; the app and `check_library.py` refuse anything else. A loop lasts bars × beats_per_bar × 60 / tempo seconds |
| `assets`| array  | Exactly six entries, in the canonical order          |

Each asset:

| Field         | Type   | Meaning                                         |
|---------------|--------|-------------------------------------------------|
| `id`          | string | Stable ASCII slug used in filenames and URLs    |
| `name`        | string | Hebrew display name                             |
| `instrument`  | object | `{ id, name }`: the instrument this channel plays; `id` as in `INSTRUMENTS` in `parts.py` (clarinet, drums, bass, guitar, violin, piano), `name` in Hebrew |
| `color`       | string | CSS colour for the channel and the profile axis |
| `description` | string | One Hebrew sentence shown under the channel     |
| `clips`       | array  | The rendered parts available for this asset, one per song |

Each clip:

| Field    | Type   | Meaning                                                   |
|----------|--------|-----------------------------------------------------------|
| `id`     | string | `<asset>-NN`, matches the filename; stable, phones save a clip's position |
| `title`  | string | Hebrew song title shown in the song menu                  |
| `note`   | string | One short Hebrew line describing the part, e.g. "קלרינט, 8 תיבות ב-100 BPM, רה מינור" |
| `file`   | string | `clips/<clip id>.wav`: the rendered part                  |
| `source` | string | `midi/<slug>.mid`: the song's MIDI arrangement             |
| `part`   | string | `midi/parts/<slug>--<instrument>.mid`: the instrument's part of the song, what gets rendered |
| `credit` | string | Performer / origin / licence note                         |
| `bars`   | number | Optional. Loop length override for this clip              |

The player plays `file` as the channel's one source, behind its fader (`source → channelGain → master → destination`). Faders start at zero; the column shows the asset's instrument name under the asset name.

Example with one asset:

```json
{
  "version": 1,
  "tempo": 92,
  "key": "D minor",
  "bars": 8,
  "beats_per_bar": 4,
  "assets": [
    {
      "id": "hebrew",
      "name": "עברית",
      "instrument": { "id": "clarinet", "name": "קלרינט" },
      "color": "#3A7BD5",
      "description": "המילים שבהן אנחנו חושבים, שרים ומתווכחים.",
      "clips": [
        {
          "id": "hebrew-01",
          "title": "אל אדון",
          "note": "קלרינט, 8 תיבות ב-100 BPM, רה מינור",
          "file": "clips/hebrew-01.wav",
          "source": "midi/hebrew-banai-bed.mid",
          "part": "midi/parts/hebrew-banai-bed--clarinet.mid",
          "credit": "עיבוד MIDI"
        }
      ]
    }
  ]
}
```

Asset ids and canonical order: `hebrew`, `israel`, `values`, `culture`, `memory`, `lifestyle`.

## Pipeline contract: parts and clips

A song becomes a clip in three steps, all in `pipeline/arrange/`:

1. **Song MIDI.** `convert.py <slug>` writes `midi/<slug>.mid` from the song's entry in `manual.py` (melody, chords, optional bass and drums), at 100 BPM, 8 bars, D minor. Songs that are not in `songs.py` keep a hand-made `midi/<slug>.mid`.
2. **Part.** `parts.py` takes the track of the song MIDI that plays the column's role (melody: `melody`/`clarinet`; bass: `bass`/`tuba`; harmony: `guitar`/`pad`/`oud`/`accordion`/`piano`; drums: `drums`). Melodies and drums keep their notes. Bass and harmony are re-voiced onto `HARMONY`: every note keeps its timing and velocity, a chord tone stays, any other note moves to the nearest chord tone, a bass note on a bar line or chord change takes the root, and a C# inside a V window stays. A part with C# is first rotated by whole bars (pinned in `ROTATION`) so its C#s land in the V windows. A part outside its instrument's range moves by octaves. The result is the clip's `part`.
3. **Clip.** `rerender.py` renders each part with `render_midi.py` (pinned SoundFont, exact loop length, tail wrapped across the seam) and brings it to −16 LUFS integrated with the pipeline's peak limiter (ceiling 0.95), into `clips/<clip id>.wav`.

`convert.py <slug> --apply` runs all three for one song and adds a new song's clip at the end of its asset (bumping `version`). `rerender.py` runs steps 2 and 3 for the whole library from committed MIDI, so a fresh clone with Merlin.sf2 rebuilds every part and clip. `check_library.py` then verifies the manifest, every clip (exact sample count, −16 ± 1 LUFS, no sample at full scale), that nothing in `clips/`, `midi/parts/` or `midi/` is unreferenced, and that `fit.py` finds no combination of parts above its TOLERANT threshold.

### Dependencies

Python (`pipeline/requirements.txt`): `librosa`, `soundfile`, `pyloudnorm`, `numpy`, `scipy`, `pretty_midi`, and `pyrubberband` (with Homebrew `rubberband`), which only the retired recording path in `prepare_clip.py` imports. The recording tools in `arrange/` also use `ffmpeg` (decoding) and a separate Demucs environment (`arrange/sep.py`).

## Phases

1. **Bootstrap.** Build the app from the prototype: six channels, faders, play/stop, profile shape. Test on a real phone over the local network. Done.
2. **Pipeline.** Implement `prepare_clip.py`, `analyze.py`, `check_library.py`. Prepare one real clip per asset. `check_library.py` is green. Done; since then the library moved to MIDI-rendered songs and then to one instrument part per clip.
3. **Deploy.** Publish to GitHub Pages. Generate a QR code for the room. Done.
4. **Sharing.** Encode the profile in the URL (`?p=60,40,90,20,70,50`). Build `facilitator/index.html` to overlay many profiles in one view. Not started.
5. **Depth and polish.** Several clips per asset: done. PWA manifest and offline cache, visual and copy polish: not started.

## Working rhythm

One task per session. Test on the phone after each task. Commit when it passes, and only then.
