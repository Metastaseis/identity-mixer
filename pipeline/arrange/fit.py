#!/usr/bin/env python3
"""fit.py — check that every combination of parts in midi/parts/ fits together.

A participant picks one part per column, so any part of one instrument can sound with any
part of another. This scores every such combination for semitone clashes.

Profile of a part: its first 8 bars (at the library tempo) cut into one-beat windows; per
window, how long each pitch class sounds, in beats (12 bins).
clash(x, y): the mean, over the windows where both parts sound, of
    sum_p x[p] * (y[p+1] + y[p-1]) / (sum(x) * sum(y))     (pitch classes mod 12),
that is, the share of note pairs a semitone apart, weighted by how long they sound.
A combination takes one part per pitched instrument (drums are skipped); its score is its
worst pair.

Exit 1 if any combination is above TOLERANT, so this guards the library when parts are added.

usage (repo root, venv active): python pipeline/arrange/fit.py
"""
import itertools, os, sys
from collections import defaultdict

import numpy as np
import pretty_midi

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from render_midi import manifest_defaults  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parts import INSTRUMENTS  # noqa: E402

PARTS_DIR = "midi/parts"
BARS = 8
# Thresholds from the same-song analysis of the v126 library on 2026-11-24: clash of the pairs
# of parts written together within one song.
STRICT = 0.069      # 90th percentile of the same-song pairs
TOLERANT = 0.108    # the roughest same-song pair

BPM, _, BPB = manifest_defaults(ROOT)
BEATS = BARS * BPB
BEAT = 60.0 / BPM


def profile(path):
    """BEATS x 12 array: per one-beat window, beats each pitch class sounds (first BARS bars)."""
    pm = pretty_midi.PrettyMIDI(path)
    prof = np.zeros((BEATS, 12))
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for n in inst.notes:
            a, b = n.start / BEAT, min(n.end / BEAT, BEATS)
            w = int(a)
            while w < b and w < BEATS:
                prof[w, n.pitch % 12] += min(b, w + 1) - max(a, w)
                w += 1
    return prof


def clash(x, y):
    sx, sy = x.sum(axis=1), y.sum(axis=1)
    both = (sx > 0) & (sy > 0)
    if not both.any():
        return 0.0
    near = np.roll(y, -1, axis=1) + np.roll(y, 1, axis=1)          # y[p+1] + y[p-1]
    per = (x * near).sum(axis=1)[both] / (sx[both] * sy[both])
    return float(per.mean())


def main():
    groups = defaultdict(dict)
    for name in sorted(os.listdir(os.path.join(ROOT, PARTS_DIR))):
        if not name.endswith(".mid") or "--" not in name:
            continue
        slug, instrument = name[:-4].rsplit("--", 1)
        if instrument == "drums":
            continue
        groups[instrument][slug] = profile(os.path.join(ROOT, PARTS_DIR, name))
    if len(groups) < 2:
        sys.exit("error: need parts of at least two pitched instruments in midi/parts/")
    order = [v[0] for v in INSTRUMENTS.values()]                      # column order
    instruments = sorted(groups, key=lambda i: order.index(i) if i in order else len(order))
    pair = {}
    for i, j in itertools.combinations(instruments, 2):
        for a, pa in groups[i].items():
            for b, pb in groups[j].items():
                pair[(f"{a}--{i}", f"{b}--{j}")] = clash(pa, pb)
    scores = []
    for combo in itertools.product(*[[f"{s}--{i}" for s in groups[i]] for i in instruments]):
        worst = max(itertools.combinations(combo, 2), key=lambda p: pair[p])
        scores.append((pair[worst], worst, combo))
    vals = np.array([s for s, _, _ in scores])
    n = len(scores)
    print("parts: " + ", ".join(f"{i} {len(groups[i])}" for i in instruments))
    print(f"{n} combinations")
    print(f"  worst pair <= STRICT {STRICT}: {np.mean(vals <= STRICT) * 100:.1f}%")
    print(f"  worst pair <= TOLERANT {TOLERANT}: {np.mean(vals <= TOLERANT) * 100:.1f}%")
    s, (a, b), combo = max(scores, key=lambda t: t[0])
    print(f"worst combination {s:.3f}: {', '.join(combo)}")
    print(f"  its worst pair: {a} + {b}")
    print("5 worst pairs:")
    for (a, b), v in sorted(pair.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {v:.3f}  {a} + {b}")
    over = int(np.sum(vals > TOLERANT))
    if over:
        print(f"FAIL: {over} combination(s) above TOLERANT {TOLERANT}")
        sys.exit(1)
    print("ok: every combination is within TOLERANT")


if __name__ == "__main__":
    main()
