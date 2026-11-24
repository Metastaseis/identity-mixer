#!/usr/bin/env python3
"""groove.py — when the band plays inside the bar: the attack strength of the backing and of the bass, folded onto the
steps of one bar (sixteenths, or twelfths for a 3/4 or 6/8 song) and averaged over the section. For choosing a
strumming / bass pattern.   usage: groove.py <slug> [--start S] [--bars N] [--per BEATS] [--sub STEPS_PER_BEAT]
Needs the separated audio (prep.sh)."""
import json, os, sys, warnings
import numpy as np, librosa, soundfile as sf
warnings.filterwarnings("ignore")
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
from sect import analyse
from pick import NBEATS

def main(slug, start=None, bars=8, per=None, sub=4):
    picks = json.load(open(f"{W}/picks.json")); beats = analyse(slug)["beats"]; per = per or NBEATS.get(slug, 32) // 8
    b0 = int(np.argmin(abs(beats - (picks[slug] if start is None else start)))); n = bars * per
    for name in ("other", "bass", "drums"):
        p = f"{W}/sep/{slug}/{name}.wav"
        if not os.path.exists(p): continue
        y, sr = sf.read(p, dtype="float32"); a, b = int(beats[b0] * sr) - sr, int(beats[b0 + n] * sr) + sr; y = y[max(0, a):b]
        on = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256); t = max(0, a) / sr + np.arange(len(on)) * 256 / sr
        pos = np.interp(t, beats[b0:b0 + n + 1], np.arange(n + 1), left=-1, right=-1); acc = np.zeros(per * sub)
        for k in range(n * sub):
            sel = np.abs(pos - k / sub) < 0.5 / sub * 0.8
            if sel.any(): acc[k % (per * sub)] += on[sel].max()
        acc /= acc.max() + 1e-9
        print(f"{name:6s} " + " ".join(("|" if k % sub == 0 else " ") + f"{int(round(v * 9))}" for k, v in enumerate(acc)))

if __name__ == "__main__":
    argv = sys.argv[1:]; opt = {}
    for nm in ("--start", "--bars", "--per", "--sub"):
        if nm in argv: i = argv.index(nm); opt[nm] = argv[i + 1]; del argv[i:i + 2]
    main(argv[0], float(opt["--start"]) if "--start" in opt else None, int(opt.get("--bars", 8)), int(opt["--per"]) if "--per" in opt else None, int(opt.get("--sub", 4)))
