#!/usr/bin/env python3
"""convert.py — turn recordings in sources/ into 8-bar MIDI arrangements, and put them into the library.

Run from anywhere with the project environment:

  .venv/bin/python pipeline/arrange/convert.py <slug> [<slug> ...]
      transcribe only: writes pipeline/arrange/out/<slug>.mid and prints the bars
  .venv/bin/python pipeline/arrange/convert.py <slug> --start 44.6
      same, but the loop starts 44.6 s into the recording (remembered in picks.json)
  .venv/bin/python pipeline/arrange/convert.py <slug> --apply
      also writes midi/<slug>.mid, then (rerender.apply_song) the clip's instrument part in
      midi/parts/ and its render in clips/<clip id>.wav; a new song is added to manifest.json
      at the end of its asset (bumps its version)
  no slug = every song in songs.py.   --keep-audio keeps the separated audio.

A new song: put the recording in its column folder under sources/, add one line
to songs.py (slug, column id, path, title), then run with --apply. A song in a
6-beat metre also needs a line in NBEATS and GROUP in pick.py.

Steps per song
  1. sep.py     Demucs splits the recording into vocals / bass / other
                (runs with ~/.venvs/demucs/bin/python, or $DEMUCS_PYTHON)
  2. vox.py     pitch track of the vocal and the bass; arr.py: chroma of the backing
  3. sect.py    beat grid of the whole recording
  4. pick2.py   section start (a bar line where a sung phrase begins), unless
                picks.json or --start names one
  5. arr.py     melody (line.py: the line exactly as sung, as MIDI notes with
                pitch-bend for the sung pitch and CC11 for the level), one
                chord per half bar (chroma of the backing + the bass player's
                notes), moved to D minor / F major, written as melody + bass +
                harmony. The song's key is remembered in keys.json.
  6. rerender.apply_song (--apply) the clip's part (parts.py) and its render

Only the small analysis caches stay on disk (sect/, sep/<slug>/*.npz, git-ignored). After
--apply run pipeline/check_library.py. To render the library again from the
committed MIDI (no recordings, no caches), use rerender.py instead.

Songs written by hand (manual.py; since 2026-11-19 all fifteen)
  A song with an entry in manual.py takes its melody, chords, and optionally its
  bass line, strumming pattern, metre and lead instrument from there; steps 2-4
  only supply the section and the key. To write or correct one:
    prep.sh <slug>        separate the audio again and keep it (done.sh <slug> removes it)
    sheet.py / trace.py   the sung pitch bar by bar / step by step (trace.py is the one to trust)
    notes.py / syll.py    every sung note with its level / every syllable attack
    study.py / acc.py     what the band plays: chords and bass per window / the chord notes without the bass
    groove.py             where in the bar the band, the bass and the drums attack (for the patterns)
    peaks.py              the partials of a track in a beat span (octaves, who sings)
    convert.py <slug> --keep-audio      dry run into out/
    judge.py <slug>       the dry run against the recording: written notes vs the singer, chords vs the band,
                          and the rendered clip vs the recording
    convert.py <slug> --apply ; fit.py   (does the part fit every other column's parts?)
  Bar positions in notes.py count from 1: the beat of a note is (bar - 1) * beats per bar + beat - 1.

Checks (left in sources/transcribe/, not in Git; both need a sung-line song, and all fifteen are now hand-written)
  verify.py   (sung-line songs only) renders each melody on its own, measures the pitch of that audio
              again and compares it with the singer, moment by moment
  audit.py    checks the pitch track against the spectrum of the separated
              voice (octave slips, wrong notes); needs sep/<slug>/vocals.wav
Helpers: score.py scores a MIDI melody against the sung voice (judge.py uses it); sources/transcribe/v1/
holds the first version of the fifteen arrangements.
"""
import argparse, json, os, subprocess, sys

W = os.path.dirname(os.path.abspath(__file__))
R = os.path.dirname(os.path.dirname(W))
sys.path.insert(0, W)
from songs import SONGS  # noqa: E402

DEMUCS_PY = os.environ.get("DEMUCS_PYTHON", os.path.expanduser("~/.venvs/demucs/bin/python"))
PICKS = f"{W}/picks.json"          # slug -> section start in seconds of the recording


def features(slug, keep_audio):
    from sect import analyse
    from vox import tracks
    from arr import chroma_stems
    d = f"{W}/sep/{slug}"
    if not (os.path.exists(f"{d}/f0b.npz") and os.path.exists(f"{d}/chroma2.npz")):
        if not os.path.exists(f"{d}/vocals.wav"):
            if not os.path.exists(DEMUCS_PY):
                sys.exit(f"error: no Demucs environment at {DEMUCS_PY} (set DEMUCS_PYTHON)")
            subprocess.run([DEMUCS_PY, f"{W}/sep.py", slug], check=True)
        tracks(slug); chroma_stems(slug)
    analyse(slug)
    if not keep_audio:
        for f in [f"{d}/{n}.wav" for n in ("vocals", "bass", "other", "drums")] + [f"{W}/wav/{slug}.wav"]:
            if os.path.exists(f): os.remove(f)


def section(slug, picks, start=None):
    import numpy as np
    from sect import analyse
    from pick import NBEATS
    beats = analyse(slug)["beats"]; n = NBEATS.get(slug, 32)
    if start is None: start = picks.get(slug)
    if start is None:
        from pick2 import choose2
        start = choose2(slug)["start"]
    b = min(int(np.argmin(np.abs(beats - start))), len(beats) - n - 1)
    pick = dict(N=n, start=round(float(beats[b]), 3), dur=round(float(beats[b + n] - beats[b]), 3))
    picks[slug] = pick["start"]
    return pick


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slugs", nargs="*", help="songs from songs.py (default: all)")
    ap.add_argument("--start", type=float, help="section start in seconds of the recording (one slug only)")
    ap.add_argument("--apply", action="store_true", help="put the result into the library (midi/, clips/, manifest.json)")
    ap.add_argument("--keep-audio", action="store_true", help="keep the separated audio in sep/<slug>/")
    a = ap.parse_args()
    slugs = a.slugs or list(SONGS)
    bad = [s for s in slugs if s not in SONGS]
    if bad: sys.exit(f"error: not in songs.py: {', '.join(bad)}")
    if a.start is not None and len(slugs) != 1: sys.exit("error: --start needs exactly one slug")
    picks = json.load(open(PICKS)) if os.path.exists(PICKS) else {}
    from arr import build
    for slug in slugs:
        features(slug, a.keep_audio)
        pick = section(slug, picks, a.start)
        json.dump(picks, open(PICKS, "w"), indent=1)
        build(slug, pick, out_dir=None if a.apply else f"{W}/out")
        if a.apply:
            from rerender import apply_song
            apply_song(slug)


if __name__ == "__main__":
    main()
