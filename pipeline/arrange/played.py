#!/usr/bin/env python3
"""played.py — does the melody stem the app plays sound the notes written in manual.py?
The pitch of clips/stems/<slug>--melody.wav is measured from scratch and compared with the written notes, step by step.
   right  share of the written note time where the stem sounds that note (within half a semitone)
   silent share of it where the stem has no pitch at all      extra  share of the stem's sounding time with no written note
usage: played.py [slug ...]   (default: every song in manual.py)"""
import os, sys, warnings
import numpy as np, librosa, pretty_midi, soundfile as sf
warnings.filterwarnings("ignore")
W = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(os.path.dirname(W)); sys.path.insert(0, W)
import manual
SR = 22050; HOP = 256; LOOP = 19.2
print(f"{'song':28s} right silent extra")
for slug in (sys.argv[1:] or manual.SONGS):
    man = manual.SONGS[slug]; y, sr = sf.read(f"{R}/clips/stems/{slug}--melody.wav", dtype="float32"); y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    f0, _, _ = librosa.pyin(y, fmin=180, fmax=1400, sr=SR, frame_length=1024, hop_length=HOP, fill_na=np.nan); t = np.arange(len(f0)) * HOP / SR; p = librosa.hz_to_midi(f0)
    u = LOOP / man["units"]; roll = np.full(len(t), np.nan)
    for s, n, name in man["melody"]:
        a, b = s * u + 0.06, (s + n) * u - 0.06                      # leave the attack and the release out
        if b <= a: continue
        for lo, hi in ((a, b), (a - LOOP, b - LOOP)): roll[(t >= lo) & (t < hi)] = pretty_midi.note_name_to_number(name)
    w = ~np.isnan(roll); right = np.mean(np.abs(p[w] - roll[w]) < 0.5); silent = np.mean(np.isnan(p[w]))
    far = np.array([np.isnan(roll[max(0, i - 8):i + 9]).all() for i in range(len(t))])
    extra = np.mean(far[~np.isnan(p)])
    print(f"{slug:28s} {right * 100:4.0f}% {silent * 100:5.0f}% {extra * 100:4.0f}%")
