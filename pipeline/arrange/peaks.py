#!/usr/bin/env python3
"""peaks.py — the strongest partials of a separated track in given beat spans (for settling octaves and who sings what).
usage: peaks.py <slug> <track: vocals|other|bass> <start seconds> <from beat>-<to beat> [...]   (beats counted from the start)"""
import os, sys
import numpy as np, librosa, soundfile as sf
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
from sect import analyse
N = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
slug, track, start = sys.argv[1], sys.argv[2], float(sys.argv[3])
y, sr = sf.read(f"{W}/sep/{slug}/{track}.wav", dtype="float32"); beats = analyse(slug)["beats"]; b0 = int(np.argmin(abs(beats - start)))
for span in sys.argv[4:]:
    a, b = (float(v) for v in span.split("-")); t0, t1 = np.interp([b0 + a, b0 + b], np.arange(len(beats)), beats); seg = y[int(t0 * sr):int(t1 * sr)]
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))); f = np.fft.rfftfreq(len(seg), 1 / sr); sel = (f > 60) & (f < 1300); S, f = S[sel], f[sel]; idx = []
    for i in np.argsort(S)[::-1]:
        if all(abs(f[i] - f[j]) > 0.04 * f[i] for j in idx): idx.append(i)
        if len(idx) >= 7: break
    out = []
    for i in sorted(idx, key=lambda i: f[i]):
        m = librosa.hz_to_midi(f[i]); k = int(round(m)); out.append(f"{N[k % 12]}{k // 12 - 1}{int(round((m - k) * 100)):+d}({S[i] / S.max():.1f})")
    print(f"  beats {span}: " + " ".join(out))
