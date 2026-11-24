"""Section choice using the separated vocal: start on a bar line where a sung phrase begins."""
import sys, os, json, numpy as np
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
from sect import analyse, SONGS
from vox import tracks, SR, HOP
from pick import NBEATS, GROUP

def choose2(slug, verbose=True):
    d = analyse(slug); beats = d["beats"]; cb = d["cb"]; tr = tracks(slug)
    N = NBEATS.get(slug, 32); G = GROUP.get(slug, 4)
    c = cb / (np.linalg.norm(cb, axis=0, keepdims=True) + 1e-9)
    nov = np.r_[0, 1 - np.sum(c[:, 1:] * c[:, :-1], axis=0)]
    ph = [float(nov[p::G].mean()) for p in range(G)]; phase = int(np.argmax(ph))
    f0 = tr["vocals_f0"]; rms = tr["vocals_rms"]; t = np.arange(len(f0)) * HOP / SR
    act = (~np.isnan(f0)) & (rms > 0.06 * np.percentile(rms, 95))
    idx = np.searchsorted(t, beats)
    vact = np.array([act[i:j].mean() if j > i else 0.0 for i, j in zip(idx[:-1], idx[1:])])
    ibi = np.diff(beats); nb = len(vact); cands = []
    for b in range(phase, nb - N - 1, G):
        if beats[b] > 0.62 * float(d["dur"]): break
        w = vact[b:b + N]; a = float(w.mean())
        pre = float(vact[max(0, b - 2):b].mean()) if b >= 2 else 0.0
        first = float(vact[b:b + 2].mean()); tail = float(vact[b + N - 2:b + N].mean())
        local = ibi[b:b + N]; jit = float(local.std() / local.mean())
        opening = float(vact[b:b + 4].mean())
        score = (-0.5 if opening < 0.25 else 0.0) + min(a, 0.8) + 0.4 * (1 - pre) + 0.3 * first + 0.15 * (1 - tail) - 3 * max(0, jit - 0.05) - 0.0015 * b
        cands.append((score, b, a, pre, first, jit))
    cands.sort(reverse=True); best = cands[0]; b = best[1]
    start = float(beats[b]); dur = float(beats[b + N] - beats[b])
    res = dict(slug=slug, N=N, start=round(start, 3), dur=round(dur, 3), fake_bpm=round(32 * 60 / dur, 3), phase=phase, jitter=round(best[5], 3), vocal=round(best[2], 2))
    if verbose:
        print(f"{slug:28s} start {start:6.1f}s len {dur:5.1f}s vocal {best[2]:.2f} pre {best[3]:.2f} first {best[4]:.2f} jitter {best[5]:.3f} | next: " + ", ".join(f"{beats[c[1]]:.0f}s({c[0]:.2f})" for c in cands[1:4]))
    return res

if __name__ == "__main__":
    for s in (sys.argv[1:] or SONGS):
        if os.path.exists(f"{W}/sep/{s}/f0b.npz"): choose2(s)
