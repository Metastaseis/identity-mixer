#!/usr/bin/env python3
"""rerender.py — render the library again from committed MIDI: each clip is its instrument part, rendered.

  1. parts.py writes every clip's `part` (midi/parts/<slug>--<instrument>.mid) from its song MIDI (`source`).
  2. Each part is rendered to the clip's `file` (clips/<clip id>.wav) by render_midi.py with the pinned
     SoundFont, as an exact loop of the library grid, then brought to -16 LUFS integrated by the pipeline's
     peak limiter (analyze.normalize_loop, ceiling PEAK), so sparse hits such as drums reach the loudness
     without touching full scale.

Everything comes from committed files: the song MIDI in midi/ is rendered as it is. A fresh clone with
Merlin.sf2 (pipeline/README.md) rebuilds every part and every clip with this script. Regenerating a song's
midi/<slug>.mid from manual.py needs the analysis caches of its recording, so that stays with
convert.py <slug> --apply, which then calls apply_song() here for that clip. The manifest's clips are not
changed here (only apply_song adds a new one); run pipeline/check_library.py afterwards.

usage (repo root, venv active): python pipeline/arrange/rerender.py [clip ids ...]   (none = every clip)
"""
import os, subprocess, sys

import numpy as np
import soundfile as sf

W = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(os.path.dirname(W))
sys.path.insert(0, W); sys.path.insert(0, f"{R}/pipeline")
from prepare_clip import load_manifest, save_manifest  # noqa: E402
from render_midi import render, manifest_defaults, SR  # noqa: E402
from analyze import normalize_loop, integrated_loudness  # noqa: E402
import sf2  # noqa: E402

TARGET = -16.0      # LUFS integrated, every clip
RENDER_LUFS = -20.0 # the render's own level: low enough that its soft clip barely touches the peaks
PEAK = 0.95         # peak ceiling of a clip (check_library.py fails at 0.999)
NOTE = "{instrument}, {bars} תיבות ב-{tempo:g} BPM{key}"
CREDIT = "עיבוד MIDI"


def render_clip(clip, m, log=print):
    """Render the clip's part into its file. Returns (lufs, peak, limiter dB)."""
    bpm, bars, bpb = float(m["tempo"]), int(clip.get("bars", m["bars"])), int(m["beats_per_bar"])
    out = f"{R}/{clip['file']}"
    y, _ = render(f"{R}/{clip['part']}", out, bpm, bars, bpb, lufs=RENDER_LUFS, log=lambda *_: None)
    y, lufs, red = normalize_loop(y, SR, TARGET, ceiling=PEAK)
    sf.write(out, y, SR, subtype="PCM_16")
    z, _ = sf.read(out, dtype="float64")
    lufs, pk = integrated_loudness(z, SR), float(np.abs(z).max())
    log(f"{clip['id']:13s} {clip['part']:52s} -> {clip['file']}  {lufs:6.2f} LUFS, peak {pk:.3f}"
        + (f", limited {red:.1f} dB" if red > 0.05 else ""))
    return lufs, pk, red


def run_parts(ids=()):
    r = subprocess.run([sys.executable, f"{W}/parts.py", *ids], capture_output=True, text=True, cwd=R)
    if r.returncode:
        sys.exit(f"parts.py failed:\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
    print(r.stdout.strip().splitlines()[-1])


def apply_song(slug):
    """After convert.py has written midi/<slug>.mid: its clip (added at the end of its asset if it is new,
    which bumps the manifest version), its part, and its render."""
    from songs import SONGS
    from parts import INSTRUMENTS
    asset_id, _, title = SONGS[slug]
    m = load_manifest(R); asset = next(a for a in m["assets"] if a["id"] == asset_id)
    clip = next((c for c in asset["clips"] if c["source"] == f"midi/{slug}.mid"), None)
    if clip is None:
        inst = INSTRUMENTS[asset_id][0]
        used = {c["id"] for c in asset["clips"]}
        cid = next(f"{asset_id}-{k:02d}" for k in range(1, 100) if f"{asset_id}-{k:02d}" not in used)
        clip = {"id": cid, "title": title,
                "note": NOTE.format(instrument=asset["instrument"]["name"], bars=m["bars"], tempo=m["tempo"],
                                    key="" if inst == "drums" else ", רה מינור"),
                "file": f"clips/{cid}.wav", "source": f"midi/{slug}.mid", "part": f"midi/parts/{slug}--{inst}.mid", "credit": CREDIT}
        asset["clips"].append(clip); m["version"] += 1
        save_manifest(m, f"{R}/manifest.json")
        print(f"added {cid} ({title}) to {asset_id}; manifest version {m['version']}")
    run_parts([clip["id"]])
    render_clip(clip, m)


def main(ids):
    try:
        sf2.find(R)                 # stop before touching anything if the SoundFont is missing or different
    except sf2.SoundFontError as e:
        sys.exit(f"error: {e}")
    m = load_manifest(R)
    clips = [c for a in m["assets"] for c in a["clips"]]
    unknown = set(ids) - {c["id"] for c in clips}
    if unknown:
        sys.exit(f"error: unknown clip id(s): {', '.join(sorted(unknown))}")
    run_parts(ids)
    for c in clips:
        if not ids or c["id"] in ids:
            render_clip(c, m)


if __name__ == "__main__":
    main(sys.argv[1:])
