#!/usr/bin/env python3
"""acc.py — the notes of the backing without the bass (the guitar / keyboard chords), per window, in the library key.
usage: acc.py <slug> [--start S] [--bars N] [--win BEATS (default 2)]      Needs prep.sh <slug> (or its study.npz cache)."""
import json, os, sys
import numpy as np
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
from study import fine_chroma, HOP, SR
from sect import analyse
from pick import NBEATS
from vox import NAMES

def main(slug, start=None, bars=8, win=2.0):
    picks = json.load(open(f"{W}/picks.json")); keys = json.load(open(f"{W}/keys.json")); beats = analyse(slug)["beats"]; per = NBEATS.get(slug, 32) // 8
    b0 = int(np.argmin(abs(beats - (picks[slug] if start is None else start)))); shift = (5 - NAMES.index(keys[slug])) % 12
    acc, bass, _ = fine_chroma(slug); t = np.arange(acc.shape[1]) * HOP / SR; bt = lambda x: np.interp(x, np.arange(len(beats)), beats)
    for w in range(int(round(bars * per / win))):
        sel = (t >= bt(b0 + w * win)) & (t < bt(b0 + (w + 1) * win)); c = np.roll(acc[:, sel].mean(axis=1), shift); c = c / (c.max() + 1e-9)
        bb = np.roll(bass[:, sel].mean(axis=1), shift); pos = w * win
        print(f"  bar {int(pos // per) + 1:2d} beat {pos % per + 1:3g}  " + " ".join(f"{NAMES[i]}{c[i]:.2f}" for i in np.argsort(c)[::-1][:6]).ljust(48) + f" | bass {NAMES[int(np.argmax(bb))]}")

if __name__ == "__main__":
    argv = sys.argv[1:]; opt = {}
    for nm in ("--start", "--bars", "--win"):
        if nm in argv: i = argv.index(nm); opt[nm] = argv[i + 1]; del argv[i:i + 2]
    main(argv[0], float(opt["--start"]) if "--start" in opt else None, int(opt.get("--bars", 8)), float(opt.get("--win", 2)))
