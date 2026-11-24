"""Choose the loop section per song. N tracked beats -> 8 library bars."""
import sys, os, json, numpy as np, scipy.ndimage as ndi
from sect import analyse, SONGS, W
NBEATS = {"hebrew-durme-durme": 48, "culture-hallelujah": 48,      # 6-beat metres: 3 tracked beats per 2 library beats
          "hebrew-banai-bed": 64}                                  # beats tracked as eighths: 8 per bar, 8 bars of the song
GROUP = {"hebrew-durme-durme": 6, "culture-hallelujah": 6, "hebrew-banai-bed": 8}

def choose(slug, verbose=True):
    d = analyse(slug); beats = d["beats"]; cb = d["cb"]; mb = d["mb"]
    N = NBEATS.get(slug, 32); G = GROUP.get(slug, 4)
    c = cb / (np.linalg.norm(cb, axis=0, keepdims=True) + 1e-9)
    nov = np.r_[0, 1 - np.sum(c[:, 1:] * c[:, :-1], axis=0)]
    ph = [float(nov[p::G].mean()) for p in range(G)]
    phase = int(np.argmax(ph)); srt = sorted(ph, reverse=True); pmargin = (srt[0] - srt[1]) / (srt[0] + 1e-9)
    # timbre novelty (checkerboard on beat-synchronous MFCC self-similarity)
    m = (mb - mb.mean(axis=1, keepdims=True)) / (mb.std(axis=1, keepdims=True) + 1e-9)
    S = m.T @ m / m.shape[0]
    K = 8; k = np.kron(np.array([[1, -1], [-1, 1]]), np.ones((K, K)))
    tn = np.zeros(S.shape[0])
    for i in range(K, S.shape[0] - K): tn[i] = np.sum(S[i - K:i + K, i - K:i + K] * k)
    tn = np.maximum(tn, 0); tn /= tn.max() + 1e-9
    v = d["vbeat"]; v = v / (np.percentile(v, 95) + 1e-9); vmed = np.median(v)
    nb = len(beats) - 1
    ibi = np.diff(beats)
    cands = []
    for b in range(phase, nb - N - 1, G):
        if beats[b] > 0.6 * float(d["dur"]): break
        w = v[b:b + N]
        if len(w) < N: break
        act = float((w > 0.8 * vmed).mean())                  # share of the window with vocal-band energy
        lead = float(v[max(0, b - 8):b].mean()) if b >= 8 else 0.0
        local = ibi[b:b + N]; jit = float(local.std() / local.mean())
        bound = float(tn[max(0, b - 2):b + 3].max())           # near a timbre boundary
        rise = float(w[:8].mean() - lead)
        score = act + 0.6 * bound + 0.5 * max(0, rise) - 3 * max(0, jit - 0.05) - 0.004 * b   # mild preference for earlier
        cands.append((score, b, act, bound, jit))
    cands.sort(reverse=True)
    best = cands[0]; b = best[1]
    start = float(beats[b]); end = float(beats[b + N]); dur = end - start
    res = dict(slug=slug, N=N, start=round(start, 3), dur=round(dur, 3), tracked_bpm=round(N * 60 / dur, 2), fake_bpm=round(32 * 60 / dur, 3),
               stretch=round(dur / 19.2, 3), phase=phase, phase_margin=round(pmargin, 2), jitter=round(best[4], 3), vocal=round(best[2], 2))
    if verbose:
        print(f"{slug:28s} start {start:6.1f}s len {dur:5.1f}s ({N} beats @ {res['tracked_bpm']:.1f}) speed x{19.2/dur:.2f} phase {phase} (margin {pmargin:.2f}) jitter {best[4]:.3f} vocal {best[2]:.2f} | next: "
              + ", ".join(f"{beats[c[1]]:.0f}s({c[0]:.2f})" for c in cands[1:5]))
    return res

if __name__ == "__main__":
    out = {s: choose(s) for s in (sys.argv[1:] or SONGS)}
    pass
