# CLAUDE.md — Identity Mixer

Project rules for every session. Read `ARCHITECTURE.md` for the full design.

## Invariants (never break these)

1. One tempo and one key for the whole library, fixed in `manifest.json`. Sync and harmony are solved in `pipeline/`, never at runtime. The player only starts loops together.
2. Every clip is an exact whole-bar loop (default 8 bars) at the shared tempo, normalised to −16 LUFS.
3. No build step, no framework. `index.html` + `app.js` + `styles.css` + `manifest.json` + `clips/`, deployable as static files.
4. Hebrew, RTL, phone-first, iOS Safari compatible. Create and resume the `AudioContext` only inside the play tap handler.
5. One copy of every file, versioned with Git. Never create `*_v2`, `*_old`, `*_backup` files or duplicate folders. Edit in place and commit.

## The six assets

In this exact order and spelling, everywhere (manifest, UI, profile axes, docs):

1. השפה העברית
2. ישראל
3. עולם ערכים
4. תרבות
5. זיכרון היסטורי
6. אורח חיים

Ids, same order: `hebrew`, `israel`, `values`, `culture`, `memory`, `lifestyle`.

## UI copy

Hebrew only. Sentence case. Active voice. Short lines that fit a phone screen.

## Audio scheduling

- All channels start sample-accurately: every `AudioBufferSourceNode` has `loop = true` and is started with the same `AudioContext` time value, computed once as `ctx.currentTime + small lead`.
- Never start channels one after another with separate `currentTime` reads.
- Faders drive `GainNode.gain` only. No per-channel tempo, pitch, or offset in the player.
- Stop tears down all sources together.

## After any change to audio scheduling or `manifest.json`

1. Run `python pipeline/check_library.py` and make it green.
2. Start the dev server bound to IPv4, always exactly `python3 -m http.server 8000 --bind 0.0.0.0` (without `--bind` the phone cannot reach it).
3. Print the phone URL as `http://<en0 address>:8000`, with the address from `ipconfig getifaddr en0`. It changes between networks, so read it every time.
4. Tell the user exactly what to test on the phone: which screen, which taps, what they should hear and see.

## Process

- One task per session. Finish it, test on the phone, commit when it passes.
- Ask before adding any dependency, system or Python or JavaScript.
- Do not scaffold or refactor beyond the task at hand.
