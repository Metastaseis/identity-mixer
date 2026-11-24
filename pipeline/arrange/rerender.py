#!/usr/bin/env python3
"""rerender.py — render every MIDI clip of the library again (after a change to the renderer or its sound).

Everything comes from committed files, so a fresh clone can run it (it needs only the pinned SoundFont,
Merlin.sf2: see pipeline/README.md). The fifteen songs of songs.py are rendered from their committed
midi/<slug>.mid by finish.py: clip, stems and stems_gain, no recordings or caches. (To change one of them,
edit manual.py and run convert.py <slug> --apply instead.) Every other MIDI clip is rendered again from the MIDI files the manifest already names: the clip from its
`source`, each stem from its own `midi`, and `stems_gain` is measured again. Then run pipeline/check_library.py.
"""
import json, os, subprocess, sys
import numpy as np, soundfile as sf, pyloudnorm as pyln
W = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(os.path.dirname(W))
sys.path.insert(0, W); sys.path.insert(0, f"{R}/pipeline")
from songs import SONGS
from prepare_clip import load_manifest, save_manifest
from render_midi import render, manifest_defaults
from analyze import limit_peaks
import sf2

try:
    sf2.find(R)                     # stop before touching anything if the SoundFont is missing or different
except sf2.SoundFontError as e:
    sys.exit(f"error: {e}")

py = f"{R}/.venv/bin/python"
ours = {f"midi/{slug}.mid": slug for slug in SONGS}
only = set(sys.argv[1:])            # clip ids; none = all
for a in load_manifest(R)["assets"]:
    for c in a["clips"]:
        src = c.get("source", "")
        if not src.startswith("midi/") or (only and c["id"] not in only): continue
        if src in ours:
            r = subprocess.run([py, f"{W}/finish.py", ours[src]], capture_output=True, text=True, cwd=R)
            print(f"{c['id']:13s} {c['title']}: " + ("rebuilt" if r.returncode == 0 else "FAILED " + (r.stderr or r.stdout)[-300:]), flush=True)
            continue
        stems, gain_note = c.get("stems"), ""
        r = subprocess.run([py, f"{R}/pipeline/library.py", "replace", c["id"], "--midi", src], capture_output=True, text=True, cwd=R)
        if r.returncode: print(f"{c['id']}: FAILED {(r.stderr or r.stdout)[-300:]}"); continue
        if stems:
            bpm, bars, bpb = manifest_defaults(R); total = None
            for s in stems:
                quiet = any(k in s["id"] for k in ("darbuka", "drum", "perc"))      # sparse hits: same loudness would mean huge peaks
                y, _ = render(f"{R}/{s['midi']}", f"{R}/{s['file']}", bpm, c.get("bars", bars), bpb, lufs=-21.0 if quiet else -16.0, log=lambda *_: None)
                total = y if total is None else total + y
            meter = pyln.Meter(44100)
            for _ in range(3):          # plucks and drum hits that land together: shave the stems' peaks a little so the sum fits at -16 LUFS
                gain = 10 ** ((-16.0 - meter.integrated_loudness(total)) / 20)
                if float(np.abs(total).max()) * gain <= 0.97: break
                ys = [sf.read(f"{R}/{s['file']}", dtype="float64")[0] for s in stems]
                ceiling = 0.88 * max(float(np.abs(y).max()) for y in ys); total = None
                for s, y in zip(stems, ys):
                    y, _ = limit_peaks(y, 44100, ceiling); sf.write(f"{R}/{s['file']}", y, 44100, subtype="PCM_16")
                    total = y if total is None else total + y
            pk = float(np.abs(total).max()) * gain
            if pk > 0.98: gain *= 0.98 / pk
            m = load_manifest(R)
            for a2 in m["assets"]:
                for c2 in a2["clips"]:
                    if c2["id"] == c["id"]: c2["stems"] = stems; c2["stems_gain"] = round(float(gain), 3)
            save_manifest(m, f"{R}/manifest.json"); gain_note = f", {len(stems)} stems, stems_gain {gain:.3f}"
        print(f"{c['id']:13s} {c['title']}: rendered again{gain_note}", flush=True)
