#!/usr/bin/env python3
"""trace.py — the sung pitch step by step: for every grid step of a section the pitch the singer holds there, as a
note of the library key in the singer's octave with the cents off it ('.' = not singing, '~' = sliding).
usage: trace.py <slug> [--start S] [--bars N] [--sub STEPS_PER_BEAT (default 4)]"""
import json, os, sys
import numpy as np, pretty_midi
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
import mel
from sect import analyse
from pick import NBEATS
from vox import NAMES

def main(slug, start=None, bars=8, sub=4):
    picks = json.load(open(f"{W}/picks.json")); keys = json.load(open(f"{W}/keys.json")); beats = analyse(slug)["beats"]; per = NBEATS.get(slug, 32) // 8
    b0 = int(np.argmin(abs(beats - (picks[slug] if start is None else start)))); bs = beats[b0:b0 + bars * per + 1]
    shift = (5 - NAMES.index(keys[slug])) % 12; shift = shift if shift <= 6 else shift - 12
    m, ok, rms, on = mel.voice(slug); t = np.arange(len(m)) * mel.FR; pos = np.interp(t, bs, np.arange(len(bs)), left=-1, right=-1)
    sel = pos >= 0; ok = ok & (rms > mel.LEVEL * np.percentile(rms[sel][ok[sel]], 90))
    for bar in range(bars):
        row = []
        for k in range(per * sub):
            a = bar * per + k / sub; w = (pos >= a) & (pos < a + 1 / sub); v = m[w][ok[w]]
            if len(v) < max(1, w.sum() // 2): row.append("."); continue
            q = float(np.median(v)) + shift; kk = int(round(q)); name = pretty_midi.note_number_to_name(kk).replace("#", "s")
            row.append(("~" if v.max() - v.min() > 1.2 else "") + f"{name}{int(round((q - kk) * 100)):+d}")
        print(f" bar {bar + 1}: " + "".join(("| " if k % sub == 0 else "") + f"{c:9s}" for k, c in enumerate(row)))

if __name__ == "__main__":
    argv = sys.argv[1:]; opt = {}
    for nm in ("--start", "--bars", "--sub"):
        if nm in argv: i = argv.index(nm); opt[nm] = argv[i + 1]; del argv[i:i + 2]
    main(argv[0], float(opt["--start"]) if "--start" in opt else None, int(opt.get("--bars", 8)), int(opt.get("--sub", 4)))
