#!/usr/bin/env python3
"""notes.py — list every sung note of a section (beat position, length, pitch as scale degree and cents,
level), and score all 24 major/minor chords against the backing per half bar. For writing a melody by
hand in manual.py.   usage: notes.py <slug> [bars (default 8)] [--key NAME] [--start SECONDS] [--nochords]"""
import json, os, sys
import numpy as np
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
import mel, line, arr
from sect import analyse
from vox import NAMES, MAJ
from pick import NBEATS
DEG = {0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4", 6: "#4", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7"}

def main(s, bars=8, key=None, start=None, chords=True):
    picks = json.load(open(f"{W}/picks.json")); keys = json.load(open(f"{W}/keys.json"))
    beats = analyse(s)["beats"]; per = NBEATS.get(s, 32) // 8; b0 = int(np.argmin(abs(beats - (picks[s] if start is None else start)))); bs = beats[b0:b0 + bars * per + 1]
    tonic = NAMES.index(key or keys[s]); scale = [(tonic + k) % 12 for k in MAJ]; shift = (5 - tonic) % 12
    m, ok, rms, on = mel.voice(s); t = np.arange(len(m)) * mel.FR
    i0, i1 = np.searchsorted(t, bs[0] - 0.4), np.searchsorted(t, bs[-1])
    ok = ok & (rms > mel.LEVEL * np.percentile(rms[i0:i1][ok[i0:i1]], 90)); st = mel.settled(m, ok)
    w0, w1 = max(0, i0 - 1900), i1 + 1900
    off = mel.vocal_tuning(m[w0:w1], st[w0:w1], arr.acc_tuning(s), scale)
    x, okc, _ = line.clean(m[i0:i1] - off, ok[i0:i1]); r = rms[i0:i1]; ref = np.percentile(r[okc], 90)
    seg = line.segment(x, okc, r, on[i0:i1], scale); stc = mel.settled(x, okc)
    tb = np.interp(t[i0:i1], bs, np.arange(len(bs)), left=-1); fb = (tb[-1] - tb[0]) / max(1, len(tb) - 1)
    h = mel.pc_hist(x[stc]); print(f"{s}: key {NAMES[tonic]} major / relative minor, voice offset {off:+.2f} st, tracked tempo {60 / np.mean(np.diff(bs)):.1f}, {per} beats per bar")
    print("   held singing per scale degree: " + "  ".join(f"{DEG[d]}:{100 * mel.mass(h, (tonic + d) % 12 - 0.5, (tonic + d) % 12 + 0.5):.0f}%" for d in range(12)))
    print(f"   section starts at {bs[0]:.1f}s"); prev = None
    for a, b, p, att in seg:
        if b - a < 3: continue
        held = x[a:b][stc[a:b]]; q = float(np.median(held)) if len(held) else float(np.median(x[a:b])); k = int(round(q))
        pos = tb[a]; dur = (b - a) * fb
        if prev is not None and pos - prev > 0.3: print(f"      (rest {pos - prev:.2f} beats)")
        unit = (pos % per) * 4 if per == 4 else (pos % per) * 2
        print(f"  bar {int(pos // per) + 1:2d} beat {pos % per + 1:4.2f} (step {unit:4.1f})  {dur:4.2f} beats  {'NEW' if att else 'tie'}  {DEG[(k - tonic) % 12]:>2s} {int(round((q - k) * 100)):+4d}c  {arr.pretty_midi.note_number_to_name(k)}  level {r[a:b].mean() / ref:.2f}")
        prev = pos + dur
    if not chords: return
    acc, bass = arr.chroma_stems(s); ta = arr.frames_t(acc.shape[1]); half = per // 2
    print("   chords, library key (transposed %+d): best triads per half bar | strongest notes" % (shift if shift <= 6 else shift - 12))
    for w in range(bars * 2):
        sel = (ta >= bs[w * half]) & (ta < bs[(w + 1) * half]); c = acc[:, sel].mean(axis=1); c = c / (np.linalg.norm(c) + 1e-9); bb = bass[:, sel].mean(axis=1); bb = bb / (bb.max() + 1e-9)
        sc = sorted(((c[q] + 0.9 * c[(q + th) % 12] + 0.8 * c[(q + 7) % 12] - 0.5 * c[(q + ot) % 12] + 0.45 * bb[q], NAMES[(q + shift) % 12] + nm) for q in range(12) for nm, th, ot in (("", 4, 3), ("m", 3, 4))), reverse=True)
        print(f"   bar {w // 2 + 1}.{w % 2 + 1}  " + "  ".join(f"{n}:{v:.2f}" for v, n in sc[:4]) + "   | " + " ".join(f"{NAMES[(i + shift) % 12]}{c[i]:.2f}" for i in np.argsort(c)[::-1][:5]) + f"   low: {NAMES[(int(np.argmax(bb)) + shift) % 12]}")

if __name__ == "__main__":
    argv = sys.argv[1:]; opt = {}
    for name in ("--key", "--start"):
        if name in argv: i = argv.index(name); opt[name] = argv[i + 1]; del argv[i:i + 2]
    chords = "--nochords" not in argv; argv = [v for v in argv if v != "--nochords"]
    main(argv[0], int(argv[1]) if len(argv) > 1 else 8, opt.get("--key"), float(opt["--start"]) if "--start" in opt else None, chords)
