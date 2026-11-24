#!/usr/bin/env python3
"""score.py — how closely a MIDI melody follows the sung voice of its recording section.

usage: score.py [--dir midi-folder] [slug ...]      (default folder: the library's midi/)

pitch   of the held sung frames that have a MIDI note within 90 ms, the share where that note is the sung
        pitch (within half a semitone, any octave): wrong notes lower it, small timing shifts do not
cover   share of sung frames that have a MIDI note at all
starts  share of the voice's syllable starts that have a MIDI note start within 90 ms
extra   share of MIDI note starts with no syllable start of the voice within 90 ms
"""
import argparse, json, os, sys
import numpy as np, pretty_midi
W = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(os.path.dirname(W)); sys.path.insert(0, W)
from songs import SONGS
from sect import analyse
from pick import NBEATS
from mel import voice, settled, FR
LOOP = 19.2

def score(slug, path, picks):
    beats = analyse(slug)["beats"]; n = NBEATS.get(slug, 32)
    b0 = int(np.argmin(np.abs(beats - picks[slug]))); bs = beats[b0:b0 + n + 1]
    m, ok, rms, on = voice(slug); t = np.arange(len(m)) * FR
    i0, i1 = np.searchsorted(t, bs[0]), np.searchsorted(t, bs[-1])
    tau = np.interp(t[i0:i1], bs, np.arange(n + 1) * LOOP / n); x = m[i0:i1]; v = ok[i0:i1]; o = on[i0:i1]
    mel = [i for i in pretty_midi.PrettyMIDI(path).instruments if i.name == "melody"][0]
    roll = np.full(len(tau), np.nan)
    for q in mel.notes: roll[(tau >= q.start) & (tau < q.end + 0.03)] = q.pitch
    both = v & ~np.isnan(roll)
    off = np.median(((x[both] - roll[both] + 6) % 12) - 6) if both.any() else 0.0
    err = np.abs(((x - roll - off + 6) % 12) - 6)
    held = settled(m, ok)[i0:i1]; near = np.full(len(x), np.inf)
    for k in range(-4, 5):                                   # +-90 ms
        r = np.roll(roll, k); e = np.abs(((x - r - off + 6) % 12) - 6); near = np.fmin(near, np.where(np.isnan(e), np.inf, e))
    # syllable starts of the voice: start of a sung stretch after >= 70 ms of silence, or an onset peak inside one
    truth = []
    for f in range(1, len(v) - 1):
        if v[f] and not v[max(0, f - 3):f].any(): truth.append(tau[f])
        elif v[f] and o[f] > 0.5 and o[f] >= o[f - 1] and o[f] >= o[f + 1] and (not truth or tau[f] - truth[-1] > 0.09): truth.append(tau[f])
    truth = np.array(truth); starts = np.array([q.start for q in mel.notes])
    hit = np.mean([np.abs(starts - s).min() <= 0.09 for s in truth]) if len(truth) and len(starts) else 0.0
    extra = np.mean([np.abs(truth - s).min() > 0.09 for s in starts]) if len(truth) and len(starts) else 0.0
    got = held & np.isfinite(near)
    return dict(pitch=float(np.mean(near[got] < 0.5)) if got.any() else 0.0, cover=float(np.mean(~np.isnan(roll[v]))) if v.any() else 0.0,
                starts=float(hit), extra=float(extra), notes=len(mel.notes))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("slugs", nargs="*"); ap.add_argument("--dir", default=f"{R}/midi")
    a = ap.parse_args(); picks = json.load(open(f"{W}/picks.json")); tot = []
    print(f"{'song':28s} pitch cover starts extra notes")
    for s in (a.slugs or SONGS):
        p = f"{a.dir}/{s}.mid"
        if not os.path.exists(p) or not os.path.exists(f"{W}/sep/{s}/f0b.npz"): continue
        r = score(s, p, picks); tot.append(r)
        print(f"{s:28s} {r['pitch']*100:4.0f}% {r['cover']*100:4.0f}% {r['starts']*100:5.0f}% {r['extra']*100:4.0f}% {r['notes']:5d}")
    if tot: print(f"{'average':28s} " + " ".join(f"{np.mean([r[k] for r in tot])*100:4.0f}%" for k in ("pitch", "cover", "starts", "extra")))
