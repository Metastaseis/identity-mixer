# CLAUDE.md — Identity Mixer

Project rules for every session. Read `ARCHITECTURE.md` for the full design. When this file and `ARCHITECTURE.md` disagree, this file wins; say so and propose the fix.

## What this is

A phone-first Hebrew web app for educational workshops. Six faders, one per "identity asset", each driving a curated musical loop. Participants balance the faders and the app shows the result both as music (the mix) and as a radar profile. It runs in a room full of phones from a QR code, so it must load fast, start on the first tap, and stay in sync.

Live at https://metastaseis.github.io/identity-mixer/ (GitHub Pages, `main` root).

## Vocabulary

Use these words and only these words, in code, commits and conversation:

- **asset** — one of the six identity dimensions. Each asset owns one channel.
- **channel** — the runtime unit: one fader, one `GainNode`, one or more running sources.
- **clip** — one song part rendered as an exact whole-bar loop at the library tempo and key. An asset has several clips; one clip per asset is loaded at a time, chosen from the song menu under its column.
- **stem** — a sub-part of a clip (e.g. bass, guitar, melody). Toggled on/off instantly inside a channel.
- **library** — everything `manifest.json` registers: tempo, key, clips, stems.
- **profile** — the six fader values as a vector, drawn as the SVG radar.

Don't introduce synonyms (track, layer, voice, sample, loop, dimension, category).

## Invariants (never break these)

1. One tempo and one key for the whole library, fixed in `manifest.json`. Sync and harmony are solved in `pipeline/`, never at runtime. The player only starts loops on one shared grid (together on play, or in place on a song change).
2. Every clip and every stem is an exact whole-bar loop (default 8 bars) at the shared tempo. Every clip is normalised to −16 LUFS; a clip's stems, summed at its `stems_gain`, reach −16 LUFS (see Audio library rules).
3. No build step, no framework, no package manager. `index.html` + `app.js` + `profile.js` + `styles.css` + `manifest.json` + `clips/`, deployable as static files. Plain `<script>` tags, as `index.html` already does.
4. Hebrew, RTL, phone-first, iOS Safari compatible. Create and resume the `AudioContext` only inside the play tap handler.
5. One copy of every file, versioned with Git. Never create `*_v2`, `*_old`, `*_backup`, `*_new` files or duplicate folders. Edit in place and commit.
6. MIDI is the source of truth for audio; WAV is a build product. Fix a clip by editing the MIDI and re-rendering, never by editing a WAV.

## The six assets

In this exact order and spelling, everywhere (manifest, UI, profile axes, docs). The spelling is the one in `manifest.json` and in `CANON` in `pipeline/check_library.py`:

1. עברית
2. ישראל
3. עולם ערכים
4. תרבות
5. זכרון הסטורי
6. אורח חיים

Ids, same order: `hebrew`, `israel`, `values`, `culture`, `memory`, `lifestyle`.

The order is semantic, not alphabetical. Arrays of channels, faders, radar axes and manifest entries all follow it. Never sort them. To change a name, change `manifest.json`, `CANON` and this list in one commit.

## Repository map

```
~/Projects/Assets/            the repo (NOT on Desktop — Desktop is a synced folder and hangs the venv)
├── index.html                shell, viewport meta, dir="rtl" lang="he"
├── app.js                    audio engine, faders, song menus, stem chips, transport
├── profile.js                six-axis vector → SVG radar
├── styles.css                phone layout, RTL, touch targets
├── manifest.json             the library registry: version, tempo, key, bars, clips, stems
├── clips/                    rendered WAV clips (build products)
│   └── stems/                rendered WAV stems (build products)
├── midi/                     MIDI sources, one per clip (source of truth)
│   └── stems/                MIDI sources, one per stem
├── pipeline/                 Python: render, normalise, check
│   ├── README.md
│   ├── requirements.txt
│   ├── analyze.py            BPM, key, loudness, peak; audio loading
│   ├── prepare_clip.py
│   ├── render_midi.py        MIDI → WAV at the library grid
│   ├── sf2.py                SoundFont 2 sample player used by render_midi.py
│   ├── library.py            add, replace, remove, list clips (bumps manifest version)
│   ├── check_library.py
│   └── arrange/              hand-written arrangements (manual.py) → midi/, and the tools to write them; caches git-ignored
├── sources/                  git-ignored: recordings, SoundFonts, transcription work
├── README.md
├── qr.png                    QR code for the public URL
├── .nojekyll                 Pages serves files as-is
├── ARCHITECTURE.md
├── CLAUDE.md                 this file
└── .venv/                    Python 3.13, git-ignored
```

If a file or folder you need isn't here, it probably shouldn't exist. Ask.

## Files by concern

| Changing… | Touch | Don't touch |
|---|---|---|
| Fader behaviour, playback, stem toggles, song swap | `app.js` | `manifest.json`, `pipeline/` |
| Radar drawing | `profile.js`, `styles.css` | `app.js` beyond the call site |
| Layout, copy, colours | `index.html`, `styles.css` | `app.js` |
| Adding or replacing a clip or stem | `midi/`, run `pipeline/`, then `manifest.json` | `app.js` |
| Writing or changing a hand-written arrangement | `pipeline/arrange/manual.py`, then `convert.py --apply` | `app.js` |
| Tempo or key of the library | **Don't.** This re-renders everything. Ask first. | |

## manifest.json

- The only registry. Every file in `clips/` and `clips/stems/` is listed in it, and every listed file exists. `pipeline/check_library.py` checks that every listed file exists; nothing checks for unlisted files, so remove a file and its entry together.
- `version` is an integer that every library change bumps (`library.py` does it). Phones drop saved clip choices when it changes; fader levels survive.
- Shared `tempo`, `key`, `bars` and `beats_per_bar` (only 4 is supported) live at the top level once. No per-clip tempo, key or offset fields. A clip may override `bars`. The one per-clip level field is `stems_gain`, written by the pipeline (see Audio library rules); if a clip needs any other correction, the clip is wrong, not the manifest.
- Clips sit in their asset's `clips` list; assets are listed in asset order. A clip's position in its asset's list is what phones save, so add new clips at the end and use `library.py replace` to keep a clip's place.
- Paths are relative to the repo root, forward slashes, no leading `/` (GitHub Pages serves from a subpath).
- Edit it by hand or from `pipeline/`, never from `app.js`. The player reads it and never writes it.
- Every field is read by the player or by `check_library.py`. If you need a new field, add its reader in the same commit.

## Audio library rules (`pipeline/`)

- Rendered, not stretched. Earlier stretched/shifted real recordings never locked to the beat; the library is MIDI-rendered on purpose. Do not reintroduce time-stretching or pitch-shifting of recordings into the library.
- Every render goes through `pipeline/`: exact bar length at the library tempo, written to `clips/` or `clips/stems/`. A clip is normalised to −16 LUFS integrated.
- Sound: `render_midi.py` plays sampled instruments through `pipeline/sf2.py`, from the SoundFont named by `$MIXER_SOUNDFONT`, else the first `.sf2` in `sources/soundfonts/`. `sources/` is git-ignored, so a fresh clone has no SoundFont and falls back to the built-in synth; the render log says which one played. Never commit a SoundFont.
- Stems: same length, tempo, key and start as their clip. Stems are not each −16 LUFS. Their levels are a balance: the stems of the first six clips sit at −16 each (the אשת חיל darbuka at −21, so its hits don't clip); in the fifteen later songs the melody sits at −14 and the accompaniment at −20. What is enforced is the sum: a clip's stems played together at the clip's `stems_gain` reach −16 ± 1 LUFS without touching full scale. The player plays the stems at that gain instead of the full-mix file.
- Clips and stems are mono 44.1 kHz 16-bit WAV, as the pipeline writes them (846 720 samples per 8-bar loop). WAV only: `check_library.py` rejects anything else, because MP3 can't hold an exact loop length.
- Keep the total size of `clips/` in mind before adding anything: phones on a classroom Wi-Fi download each channel's selected clip before it can sound. Report the size delta in the session summary whenever `clips/` changes.
- Always run from the venv: `source ~/Projects/Assets/.venv/bin/activate`. Never `pip install` outside it and never without asking.

## Audio scheduling (`app.js`)

- One `AudioContext`, created lazily inside the play tap handler, `resume()`d there every time (iOS suspends it on every backgrounding).
- Fetch and decode in the background from page load, without an `AudioContext`. Play is enabled at once; a tap waits for the selected clips' buffers and shows a loading state. Never start a channel whose buffers aren't decoded.
- Loop length comes from the manifest grid, never from a decoded buffer: `L = bars × beats_per_bar × 60 / tempo`. Every `AudioBufferSourceNode` has `loop = true`, `loopStart = 0`, `loopEnd = L`. A buffer a few samples off would otherwise drift a little every loop.
- All channels start sample-accurately with the same `AudioContext` time, computed once as `const t0 = ctx.currentTime + START_LEAD` (`START_LEAD` = 0.15 s), after every source has been built.
- Never start channels one after another with separate `currentTime` reads. Never `start()` without the shared time.
- Song change: the new clip's sources start in place on the shared grid at `t = ctx.currentTime + SWAP_LEAD` (0.05 s) with offset `((t − startTime) mod L)`, and the old sources stop at the same `t`. Nothing else restarts.
- Faders drive `GainNode.gain` only, through a perceptual curve (gain = level²). Use `setTargetAtTime` with `RAMP` = 0.03; never set `.value` directly while playing — it clicks.
- Stem chips are gain switches on sources that are already running (`STEM_RAMP` = 0.02). Toggling a stem never creates or stops a source. All of a clip's stems start together.
- Stems start off: when the app opens, and after every song change, all of the clip's stems are off; the participant turns on the voices they want. Stem state is not saved.
- A clip's full-mix file is only a fallback for when its stems fail to load.
- No per-channel tempo, pitch, playbackRate or detune in the player. If someone asks for one, the answer is in `pipeline/`. The only offset is the grid offset of a song change.
- Stop stops all sources together. Rebuild sources on the next play; `AudioBufferSourceNode`s are one-shot.
- The graph is `source → stemGain → channelGain → master → destination`. Keep it that flat.
- Don't add effects, analysers or compressors to the runtime graph without asking. Loudness is solved in the pipeline.
- `?debug=1` turns on the sync self-test in the console and the status line.

## UI rules

- Hebrew only. Sentence case. Active voice. Short lines that fit a phone screen. No English strings reach the DOM, including `aria-label`s and `alt`s.
- `<html dir="rtl" lang="he">`. Logical CSS properties (`margin-inline-start`, `inset-inline-end`), not left/right.
- Phone first, portrait first. One screen per task; no scrolling to find the play button.
- Touch targets ≥ 44 × 44 px. No hover-only states. No double-tap gestures (iOS zooms).
- `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">` and respect `env(safe-area-inset-*)`.
- Faders are the existing custom control (`role="slider"`); don't swap it for a native range without asking.
- Song menus are native `<select>` elements under each column, so the phone opens its own menu.
- The radar always shows all six axes in asset order, even at zero.
- No web fonts, no icon libraries, no CDN. System font stack; inline SVG.
- `styles.css` owns colours and spacing; no inline styles, no CSS-in-JS. (Exceptions already in `app.js`: the fader fill height and the `--c` asset colour variable.)

## Environment

- Repo: `~/Projects/Assets`. Don't move it. Don't create a copy on Desktop or in any synced folder.
- Python: `.venv` (3.13) in the repo root; activate it before any `python` or `pip` command.
- Node is not part of this project. Don't `npm init`, don't add `package.json`.
- Dev server is Python's stdlib, see below. No live-reload tooling.
- The phone and the Mac must be on the same Wi-Fi for local testing. If not, test on the public URL after pushing.

## After any change to audio scheduling or `manifest.json`

1. Run `python pipeline/check_library.py` and make it green.
2. Start the dev server bound to IPv4, always exactly `python3 -m http.server 8000 --bind 0.0.0.0` (without `--bind` the phone cannot reach it).
3. Print the phone URL as `http://<en0 address>:8000`, with the address from `ipconfig getifaddr en0`. It changes between networks, so read it every time.
4. Tell the user exactly what to test on the phone: which screen, which taps, what they should hear and see.

## Testing order

1. Desktop Chrome at `http://localhost:8000` — fast loop for layout and logic. Check the console is empty.
2. iPhone, Safari, on the LAN URL — the real target. Sound on, silent switch off, screen not locked.
3. After push, the public URL on the same phone — confirms paths and caching on Pages.

What "passes" means: the first tap on play starts every channel on the shared grid (silently, since stems start off); turning on any stem chip is heard at once and in time with the others, with no flam on the downbeat and no click; moving any fader changes only that channel; choosing another song in a column lands on the beat, with its stems off; stop is silent; play again restarts together; the radar matches the faders.

iOS-specific things to check whenever `app.js` changes: first tap after a cold load, play after backgrounding and returning, play with the phone's silent switch on (should still sound — Web Audio ignores it only if the context is resumed inside a user gesture), rotate to landscape and back.

## Build and deploy

There is no build. GitHub Pages serves the `main` branch root directly, so every commit pushed to `main` is live at https://metastaseis.github.io/identity-mixer/ within about a minute. Push only what has passed the phone test.

- Pages serves from a subpath, so every URL in HTML, CSS, JS and the manifest is relative. Never `/clips/...`.
- Browsers cache aggressively on Pages. After changing a clip, tell the user to hard-reload. Don't rename the file and don't add a query string to its manifest path: `check_library.py` rejects both.
- `.venv/`, `__pycache__/`, `.DS_Store`, `sources/` stay out of Git. Rendered WAVs are committed (Pages needs them). MIDI sources are committed (they're the source of truth).

## Git

- One task, one commit, after the phone test. Don't commit "WIP".
- Message: imperative, present tense, one line under 72 chars, optionally a body explaining why. Prefix by concern: `player:`, `ui:`, `library:`, `pipeline:`, `docs:`.
- Commit the MIDI, the rendered WAV and the manifest change for a clip together.
- Never force-push `main`. Never rewrite history that's been pushed.
- Don't commit anything you haven't run. Don't push anything you haven't phone-tested.
- This file is the Identity Mixer rules only. Documents about other projects never go in this repo.

## Process

- One task per session. Finish it, test on the phone, commit when it passes.
- Ask before adding any dependency, system or Python or JavaScript.
- Do not scaffold or refactor beyond the task at hand. Leave adjacent ugliness alone and mention it in the summary instead.
- Read the relevant file in full before editing it. Don't guess at function names from memory.
- If the task is unclear, ask one precise question and stop. Don't build two versions.
- If you discover the task would break an invariant, stop and say which one. Don't quietly work around it.

### Session start

1. `git status` must be clean. If it isn't, report it and ask before touching anything.
2. `git log --oneline -5` to see where things stand.
3. Restate the task in one sentence and list the files you expect to touch. If the list crosses more than one row of the "Files by concern" table, say so before starting.

### Session end — always print this

```
Changed:   <files>
Why:       <one line>
Verify:    <exact terminal commands, in order, starting with cd ~/Projects/Assets>
Phone:     <screen → taps → expected sound and sight>
Not done:  <anything deferred, or "nothing">
```

Every pastable block says where it goes: **Terminal**, **Claude Code prompt**, or **Finder**.

## Things that have already gone wrong (don't repeat them)

- Stretched and shifted real recordings never locked together. That's why the library is MIDI-rendered.
- The venv on Desktop hung reading numpy's files because Desktop syncs. The repo lives in `~/Projects/Assets` for that reason.
- `http.server` without `--bind 0.0.0.0` listens on IPv6 only and the phone can't reach it.
- The en0 address changes between networks; print it, don't remember it.
- Creating the `AudioContext` outside a tap handler leaves it suspended on iOS forever.
- Starting sources with separate `ctx.currentTime` reads drifts by a few ms per channel — audible as flam on the downbeat.
- Setting `gain.value` directly while playing clicks.
- On 4 Nov a business document from another project was committed over this file, and sessions ran without these rules until 24 Nov. Check that this file starts with "CLAUDE.md — Identity Mixer" at session start.
