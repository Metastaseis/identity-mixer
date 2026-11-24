#!/usr/bin/env python3
"""sheet.py — print the sung melody of a recording bar by bar, as scale degrees on the 16th grid,
to choose where a loop should start.   usage: sheet.py <slug> [from-seconds [to-seconds]]
Bars are counted from the section start in picks.json, so the bar lines are the ones the loop uses."""
import json, os, sys
import numpy as np
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
from sect import analyse
from pick import NBEATS, GROUP
from vox import NAMES, MAJ
from arr import acc_tuning
import mel
DEG = {0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4", 6: "#4", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7"}

def sheet(slug, t0=0.0, t1=1e9):
    picks = json.load(open(f"{W}/picks.json")); keys = json.load(open(f"{W}/keys.json"))
    beats = analyse(slug)["beats"]; tonic = NAMES.index(keys[slug]); n = NBEATS.get(slug, 32); per = n // 8; sub = 2 if n == 48 else 4
    b0 = int(np.argmin(np.abs(beats - picks[slug])))
    first = b0 - per * (b0 // per)                                     # earliest bar line with the same phase
    scale = [(tonic + s) % 12 for s in MAJ]; tune = acc_tuning(slug)
    print(f"{slug}: key {NAMES[tonic]} major / relative minor, {per} tracked beats per bar, loop now starts at {beats[b0]:.1f}s (marked >)")
    for b in range(first, len(beats) - n - 1, n):
        if beats[b + n] < t0 or beats[b] > t1: continue
        seg = beats[b:b + n + 1]; ns, _ = mel.notes(slug, seg, sub, tune, scale, loop=n * 0.6)
        grid = ["."] * (n * sub)
        for s, k, p in ns:
            if s >= n * sub: continue
            grid[s] = DEG[(p - tonic) % 12] + ("'" if p >= 60 + tonic + (12 if tonic < 6 else 0) else "")
            for j in range(1, k):
                if s + j < len(grid): grid[s + j] = "-"
        w = per * sub
        for bar in range(8):
            bb = b + bar * per
            if beats[bb + per] < t0 or beats[bb] > t1: continue
            print(f" {'>' if bb == b0 else ' '}{beats[bb]:6.1f}s |" + " ".join(f"{g:>2s}" for g in grid[bar * w:(bar + 1) * w]))

if __name__ == "__main__":
    sheet(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.0, float(sys.argv[3]) if len(sys.argv) > 3 else 1e9)
