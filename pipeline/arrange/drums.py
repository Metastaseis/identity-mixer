#!/usr/bin/env python3
"""drums.py — read a drum pattern off a song's separated drum stem, for a drums entry in manual.py.

The section is the song's loop: N beats (32) from its picks.json start, on the beat grid of sect.py.
Onsets in three bands of sep/<slug>/drums.wav (separate it first: SEP_ONLY=drums sh prep.sh <slug>):
  kick   below 150 Hz
  snare  150 Hz - 2 kHz, counted only when noise (2-5 kHz) rises with it
  hats   above 5 kHz
Per sixteenth of the beat grid, the band's strongest onset within SNAP; a hit is a local peak above
--floor (against the band's 95th percentile). Velocity comes from the onset strength. The simplified
bar keeps the sixteenths that have a hit in at least half the bars. Prints hits per bar per band, the grid, and the hits as manual.py data
(sixteenth step, GM drum key, velocity).

usage (repo root): .venv/bin/python pipeline/arrange/drums.py <slug> [--floor 0.5]
"""
import argparse, json, os, sys
import numpy as np, librosa, soundfile as sf
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
from sect import analyse

BANDS = {"kick": (20, 150), "snare": (150, 2000), "hats": (5000, 16000)}
NOISE = (2000, 5000)
KEYS = {"kick": 36, "snare": 38, "hats": 42}
N_FFT, HOP = 1024, 128
SNAP = 0.03           # s: how far from a sixteenth an onset still counts for it


def flux(S, f, lo, hi):
    """Positive spectral flux of the log magnitude in [lo, hi) Hz, per frame."""
    sel = (f >= lo) & (f < hi)
    L = np.log1p(100 * S[sel])
    d = np.maximum(0, np.diff(L, axis=1)).sum(axis=0)
    return np.r_[0, d]


def detect(slug, floor):
    """{band: 8 x 16 array of onset strength per sixteenth (1 = the band's 95th percentile)}, hits {band: {step: strength}}, beats."""
    pick = json.load(open(f"{W}/picks.json"))[slug]
    beats_all = analyse(slug)["beats"]
    b0 = int(np.argmin(np.abs(beats_all - pick))); beats = beats_all[b0:b0 + 33]
    if len(beats) < 33:
        sys.exit(f"error: fewer than 32 beats after {pick}s")
    grid = np.concatenate([np.linspace(a, b, 4, endpoint=False) for a, b in zip(beats[:-1], beats[1:])])   # 128 sixteenths
    y, sr = sf.read(f"{W}/sep/{slug}/drums.wav", dtype="float32")
    a, b = int(max(0, beats[0] - 1) * sr), int((beats[-1] + 1) * sr)
    S = np.abs(librosa.stft(y[a:b], n_fft=N_FFT, hop_length=HOP))
    f = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    t = a / sr + np.arange(S.shape[1]) * HOP / sr
    def slots(x):
        s = np.array([x[(t >= g - SNAP) & (t <= g + SNAP)].max() for g in grid])
        return s / (np.percentile(s, 95) + 1e-9)
    noise = slots(flux(S, f, *NOISE))
    strength, hits = {}, {}
    for band, (lo, hi) in BANDS.items():
        s = slots(flux(S, f, lo, hi)); strength[band] = s.reshape(8, 16)
        got = {}
        for k in range(128):
            if s[k] < floor or s[k] < s[k - 1] or s[k] < s[(k + 1) % 128]: continue      # a local peak above the floor
            if band == "snare" and noise[k] < 0.3: continue                              # a snare is noisy
            got[k] = float(s[k])
        hits[band] = got
    return strength, hits, beats


def simplify(hits, share=0.5):
    """One bar: a sixteenth keeps a hit when at least `share` of the bars have one there; velocity from the mean strength."""
    out = {}
    for band, got in hits.items():
        for p in range(16):
            v = [got[b * 16 + p] for b in range(8) if b * 16 + p in got]
            if len(v) >= share * 8: out[(p, band)] = float(np.mean(v))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slug"); ap.add_argument("--floor", type=float, default=0.5, help="weakest onset kept, against the band's 98th percentile")
    a = ap.parse_args()
    strength, hits, beats = detect(a.slug, a.floor)
    print(f"{a.slug}: section {beats[0]:.2f}-{beats[-1]:.2f}s, {60 / np.median(np.diff(beats)):.1f} BPM in the recording")
    for band, got in hits.items():
        per = [sum(1 for k in got if k // 16 == bar) for bar in range(8)]
        print(f"  {band:5s} hits per bar {per}")
    for bar in range(8):
        row = []
        for band in ("hats", "snare", "kick"):
            row.append("".join(("X" if hits[band][k] > 0.6 else "x") if k in hits[band] else "." for k in range(bar * 16, bar * 16 + 16)))
        print(f"  bar {bar + 1}  hats {row[0]}  snare {row[1]}  kick {row[2]}")
    data = sorted((k, KEYS[band], int(round(45 + 65 * min(1.0, s)))) for band, got in hits.items() for k, s in got.items())
    print("  hits = " + repr(data))
    for band in BANDS:
        print(f"  {band:5s} mean strength per sixteenth " + " ".join(f"{v:.1f}" for v in strength[band].mean(0)))
    one = simplify(hits)
    print("  simplified bar (in at least half the bars): " + repr(sorted((p, KEYS[band], int(round(45 + 65 * min(1.0, s)))) for (p, band), s in one.items())))


if __name__ == "__main__":
    main()
