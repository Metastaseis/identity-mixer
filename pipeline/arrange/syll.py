#!/usr/bin/env python3
"""syll.py — where the singer starts syllables: the attack peaks of the vocal track in a section, with the beat
position (counted from the section start), the strength of the attack and the pitch sung just after it. Notes
repeated on one pitch show up here even when notes.py ties them.   usage: syll.py <slug> [--start S] [--bars N] [--min STRENGTH]"""
import json, os, sys
import numpy as np
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
import mel
from sect import analyse
from pick import NBEATS
from vox import NAMES
import pretty_midi

def main(slug, start=None, bars=8, low=0.25):
    picks = json.load(open(f"{W}/picks.json")); keys = json.load(open(f"{W}/keys.json")); beats = analyse(slug)["beats"]; per = NBEATS.get(slug, 32) // 8
    b0 = int(np.argmin(abs(beats - (picks[slug] if start is None else start)))); bs = beats[b0:b0 + bars * per + 1]
    shift = (5 - NAMES.index(keys[slug])) % 12; shift = shift if shift <= 6 else shift - 12
    m, ok, rms, on = mel.voice(slug); t = np.arange(len(m)) * mel.FR; i0, i1 = np.searchsorted(t, bs[0] - 0.5), np.searchsorted(t, bs[-1])
    pos = np.interp(t, bs, np.arange(len(bs)), left=-9); ref = np.percentile(rms[i0:i1][ok[i0:i1]], 90); out = []
    for f in range(i0 + 1, i1 - 1):
        if on[f] >= low and on[f] >= on[f - 1] and on[f] > on[f + 1]:
            w = slice(f + 1, min(i1, f + 7)); v = m[w][ok[w]]
            if len(v) < 2 or rms[w].max() < 0.1 * ref: continue
            q = float(np.median(v)) + shift; k = int(round(q))
            out.append(f"{pos[f] if pos[f] > -9 else (t[f] - bs[0]) / (bs[1] - bs[0]):6.2f} {'#' * int(round(min(1.5, on[f]) * 6)):9s} {pretty_midi.note_number_to_name(k)}{int(round((q - k) * 100)):+d}")
    print(f"{slug}: syllable attacks from {bs[0]:.2f}s (beat, strength, pitch after it in the library key, singer's octave)")
    for i in range(0, len(out), 4): print("   " + "   |   ".join(out[i:i + 4]))

if __name__ == "__main__":
    argv = sys.argv[1:]; opt = {}
    for nm in ("--start", "--bars", "--min"):
        if nm in argv: i = argv.index(nm); opt[nm] = argv[i + 1]; del argv[i:i + 2]
    main(argv[0], float(opt["--start"]) if "--start" in opt else None, int(opt.get("--bars", 8)), float(opt.get("--min", 0.25)))
