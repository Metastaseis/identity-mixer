"""Melody from the separated vocal, note by note.

The sung pitch track is decoded frame by frame into notes (a Viterbi pass over
semitone states and silence), long notes are split where the singer starts a new
syllable, and note starts are placed on the 16th-note grid of the tracked beats.
Pitches are rounded to the nearest semitone; the scale only breaks ties.

notes(slug, beats, sub, tune, scale) -> [[slot, nslots, pitch], ...] in the song's own key.
"""
import os
import numpy as np, librosa
from vox import tracks, SR, HOP

SIGMA = 0.5        # semitones: spread of a sung pitch around its note
MINF = 3           # frames (70 ms): anything shorter is an ornament, not a note
FR = HOP / SR
PULL = float(os.environ.get('MEL_PULL', 0.8))     # how strongly an unclear pitch is pulled onto the scale (0 = nearest semitone)
LEVEL = float(os.environ.get('MEL_LEVEL', 0.05))   # sung = louder than this share of the section's loud singing


def voice(slug):
    """(pitch in MIDI numbers, sung?, level, onset strength) per frame for the whole recording."""
    tr = tracks(slug); f0 = tr["vocals_f0"]; rms = tr["vocals_rms"]
    ok = ~np.isnan(f0) & (rms > 0.06 * np.percentile(rms, 95))
    m = np.where(ok, librosa.hz_to_midi(np.where(np.isnan(f0), 440.0, f0)), 0.0)
    on = tr["vocals_onset"]; on = on / (np.percentile(on, 99) + 1e-9)
    return m, ok, rms, on


def settled(m, ok):
    """Frames where the pitch is holding still (not sliding between notes)."""
    d = np.abs(np.diff(m)); st = ok.copy()
    st[1:] &= d < 0.3; st[:-1] &= d < 0.3
    st[1:] &= ok[:-1]; st[:-1] &= ok[1:]
    return st


def dist_to(q, pcs):
    return np.min(np.abs(((q[:, None] - np.asarray(pcs)[None, :] + 6) % 12) - 6), axis=1)


def vocal_tuning(m, st, ref, scale):
    """Offset (within 0.35 st of the backing's tuning) that puts the held pitches closest to the scale."""
    v = m[st]
    if len(v) < 30: return ref
    offs = np.arange(ref - 0.35, ref + 0.351, 0.05)
    cost = [np.mean(np.minimum(dist_to(v - o, scale), 0.5) ** 2) for o in offs]
    return float(offs[int(np.argmin(cost))])


def pc_hist(v):
    """Share of held frames per tenth of a semitone around the octave (120 bins, bin 10*pc = that pitch class, centred)."""
    h, _ = np.histogram((v + 0.05) % 12, bins=120, range=(0, 12))
    return h / max(1, h.sum())


def mass(h, lo, hi):
    """Histogram mass between lo and hi semitones (pitch-class axis, wraps)."""
    return float(sum(h[k % 120] for k in range(int(round(lo * 10)), int(round(hi * 10)))))


def sung_scale(x, st, scale):
    """The scale plus any other pitch class the singer clearly centres on (raised 7th, flat 2nd, ...):
    it needs 4% of the held singing and a peak of its own, not the edge of a neighbour sung flat or sharp."""
    v = x[st]; out = list(scale)
    if len(v) < 60: return out
    h = pc_hist(v)
    for pc in range(12):
        if pc in scale: continue
        mid = mass(h, pc - 0.25, pc + 0.25)
        if mid >= 0.04 and mid >= 1.5 * mass(h, pc + 0.25, pc + 0.75) and mid >= 1.5 * mass(h, pc - 0.75, pc - 0.25): out.append(pc)
    return out


def scale_fit(m, st, ref, tonic):
    """Share of the held singing that sits on the major scale of `tonic` (within 0.3 st), at the best tuning offset."""
    sc = [(tonic + k) % 12 for k in (0, 2, 4, 5, 7, 9, 11)]; v = m[st]
    if len(v) < 30: return 0.0
    return max(float(np.mean(dist_to(v - o, sc) < 0.3)) for o in np.arange(ref - 0.35, ref + 0.351, 0.05))


def decode(x, ok, st, scale):
    """Viterbi over [silence, lo..hi]. Returns one state per frame: 0 = silence, else the MIDI pitch.
    Sliding frames say "a note is sounding" but not which, so a slide never becomes notes of its own."""
    lo, hi = int(np.floor(x[ok].min())) - 1, int(np.ceil(x[ok].max())) + 1
    P = np.arange(lo, hi + 1); K = len(P) + 1; T = len(x)
    d = x[:, None] - P[None, :]
    em = np.maximum(-0.5 * (d / SIGMA) ** 2, -8.0) + np.where(np.isin(P % 12, scale), 0.0, -2 * PULL)[None, :]
    em = np.where(st[:, None], em, -0.8)
    E = np.empty((T, K)); E[:, 1:] = np.where(ok[:, None], em, -1.6); E[:, 0] = np.where(ok, -3.0, 0.0)
    A = -(4.0 + 0.15 * np.abs(P[:, None] - P[None, :])); np.fill_diagonal(A, 0.0)
    full = np.full((K, K), -1.6); full[1:, 1:] = A; full[0, 0] = 0.0
    score = E[0].copy(); back = np.zeros((T, K), dtype=np.int32)
    for i in range(1, T):
        c = score[:, None] + full; back[i] = np.argmax(c, axis=0); score = c[back[i], np.arange(K)] + E[i]
    s = np.empty(T, dtype=np.int32); s[-1] = int(np.argmax(score))
    for i in range(T - 1, 0, -1): s[i - 1] = back[i, s[i]]
    return np.where(s == 0, 0, P[np.maximum(s - 1, 0)])


def runs(states):
    out = []; i = 0
    while i < len(states):
        j = i
        while j < len(states) and states[j] == states[i]: j += 1
        if states[i] != 0: out.append([i, j, int(states[i])])
        i = j
    return out


def label(x, ok, st, a, b, scale, fallback):
    """Semitone for frames a..b: median of the held part; a note of the sung scale unless the pitch sits right on another."""
    v = x[a:b][st[a:b]]
    if len(v) == 0: v = x[a:b][ok[a:b]]
    if len(v) == 0: return fallback
    q = float(np.median(v)); k0 = int(np.floor(q))
    return min((k0, k0 + 1), key=lambda k: (q - k) ** 2 + (0.0 if k % 12 in scale else PULL))


def raw_notes(x, ok, st, rms, on, scale):
    """[[first frame, end frame, pitch], ...] from the frame-level track."""
    ns = runs(decode(x, ok, st, scale))
    # ornaments: a very short run joins the note it slides into, else the one it left, else it goes
    changed = True
    while changed:
        changed = False
        for i, (a, b, p) in enumerate(ns):
            if b - a > MINF: continue
            nxt = i + 1 < len(ns) and ns[i + 1][0] == b; prv = i > 0 and ns[i - 1][1] == a
            if nxt: ns[i + 1][0] = a
            elif prv: ns[i - 1][1] = b
            del ns[i]; changed = True; break
    for n in ns: n[2] = label(x, ok, st, n[0], n[1], scale, n[2])
    # a short step that keeps sliding into the next note is the singer reaching for it; a short fading step after a note is its tail
    i = 0
    while i < len(ns):
        a, b, p = ns[i]; v = x[a:b][ok[a:b]]
        if b - a <= 8 and len(v) >= 2:
            nxt = i + 1 < len(ns) and ns[i + 1][0] == b and 0 < abs(ns[i + 1][2] - p) <= 2
            prv = i > 0 and ns[i - 1][1] == a and 0 < abs(ns[i - 1][2] - p) <= 2
            if nxt and (v[-1] - v[0]) * (ns[i + 1][2] - p) > 0 and abs(v[-1] - v[0]) >= (0.5 if b - a <= 6 else 1.0):
                ns[i + 1][0] = a; del ns[i]; continue
            if b - a <= 6 and prv and not nxt and rms[b - 1] < 0.5 * rms[a] and (v[-1] - v[0]) * (p - ns[i - 1][2]) > 0:
                ns[i - 1][1] = b; del ns[i]; continue
        i += 1
    merged = []
    for a, b, p in ns:
        if merged and merged[-1][1] == a and merged[-1][2] == p: merged[-1][1] = b
        else: merged.append([a, b, p])
    # a new syllable on the same pitch: an onset peak of the voice well inside a note, after a dip in level
    out = []
    for a, b, p in merged:
        cuts = []
        for f in range(a + 4, b - 3):
            if on[f] < 0.35 or on[f] < on[f - 1] or on[f] < on[f + 1]: continue
            dip = rms[max(a, f - 4):f + 1].min(); after = rms[f + 1:min(b, f + 5)].max()
            if dip < 0.7 * after and (not cuts or f - cuts[-1] >= 4): cuts.append(f)
        edges = [a] + cuts + [b]
        out += [[s, e, p] for s, e in zip(edges[:-1], edges[1:])]
    # a short note an octave away from both neighbours is a tracking slip
    for i in range(1, len(out) - 1):
        d0, d1 = out[i][2] - out[i - 1][2], out[i][2] - out[i + 1][2]
        if abs(d0) >= 10 and abs(d1) >= 10 and d0 * d1 > 0 and out[i][1] - out[i][0] < 14:
            out[i][2] -= 12 * int(np.sign(d0))
    return out


def notes(slug, beats, sub, tune, scale, loop=19.2, lead=None):
    """Melody of the section between beats[0] and beats[-1] on a grid of `sub` slots per tracked beat.
    scale: pitch classes of the song's scale (in the song's own key). lead: the tracked beats just before the
    section; a pick-up sung there (after a rest, running into bar 1) is placed at the end of the loop if that
    is free, so the phrase is whole when the loop comes round. Returns ([[slot, nslots, pitch]], info)."""
    m, ok, rms, on = voice(slug)
    n = len(beats) - 1; nslots = n * sub; slot = loop / nslots
    t = np.arange(len(m)) * FR
    pre = beats[0] - lead[0] if lead is not None and len(lead) else 0.12
    i0, i1 = np.searchsorted(t, beats[0] - pre), np.searchsorted(t, beats[-1])
    w0, w1 = np.searchsorted(t, beats[0] - 45), np.searchsorted(t, beats[-1] + 45)      # wider window: more evidence
    if ok[i0:i1].sum() < 10: return [], dict(off=tune, shift_ms=0, raw=0, extra=[])
    ok = ok & (rms > LEVEL * np.percentile(rms[i0:i1][ok[i0:i1]], 90))                 # drop breaths and tails
    st = settled(m, ok)
    off = vocal_tuning(m[w0:w1], st[w0:w1], tune, scale)
    full = sung_scale(m[w0:w1] - off, st[w0:w1], scale)
    x = m[i0:i1] - off; okk = ok[i0:i1]
    if okk.sum() < 10: return [], dict(off=off, shift_ms=0, raw=0, extra=[])
    raw = raw_notes(x, okk, st[i0:i1], rms[i0:i1], on[i0:i1], full)
    bl = loop / n; tt = t[i0:i1]
    if lead is not None and len(lead): tau = np.interp(tt, np.r_[lead, beats], np.r_[(np.arange(len(lead)) - len(lead)) * bl, np.arange(n + 1) * bl])
    else: tau = np.where(tt < beats[0], (tt - beats[0]) * bl / (beats[1] - beats[0]), np.interp(tt, beats, np.arange(n + 1) * bl))
    st = np.array([tau[a] for a, _, _ in raw]); en = np.array([tau[b - 1] + FR for _, b, _ in raw])
    # the singer (or the beat tracker) may sit a little early or late on the whole: take that out before rounding
    z = np.mean(np.exp(2j * np.pi * st / slot)); lag = float(np.angle(z) / (2 * np.pi)) * slot if abs(z) > 0.25 else 0.0
    lag = float(np.clip(lag, -0.35 * slot, 0.35 * slot))
    grid = {}; pickup = []
    for (a, b, p), s, e in zip(raw, st - lag, en - lag):
        k = int(round(s / slot))
        if k < 0:
            if a == 0 or e > 0.5 * slot:                # already sounding before the window, or held across the bar line
                if e < 0.5 * slot: continue
                k = 0; s = 0.0
            else: pickup.append((k, e - s, min(e, 0.0), p)); continue
        if k >= nslots: continue
        if k in grid:                                   # two notes on one slot: the longer keeps it, the other moves aside if it can
            if grid[k][0] >= e - s:
                k2 = k + 1
                if k2 >= nslots or k2 in grid or e / slot < k2 + 0.3: continue
                k = k2
            elif k - 1 >= 0 and k - 1 not in grid: grid[k - 1] = grid[k]      # the earlier, shorter one steps back
        grid[k] = (e - s, e, p)
    # pick-up: only the notes that run unbroken into bar 1, and only onto free slots at the end of the loop
    keep = []; edge = 0.0
    for k, d, e, p in reversed(pickup):
        if edge - e > 1.2 * slot: break
        keep.append((k, d, e, p)); edge = e - d
    last = max(grid) if grid else -1; last_end = last + max(1, int(round(grid[last][0] / slot))) if grid else 0
    if keep and min(k for k, *_ in keep) + nslots >= last_end + 1:
        for k, d, e, p in keep:
            if k + nslots not in grid: grid[k + nslots] = (d, e + loop, p)
    ks = sorted(grid); out = []
    for i, k in enumerate(ks):
        _, e, p = grid[k]; nxt = ks[i + 1] if i + 1 < len(ks) else nslots
        end = min(max(k + 1, int(round(e / slot))), nxt)
        if nxt - end == 1 and nxt * slot - e < 0.6 * slot: end = nxt          # no audible hole before the next note
        out.append([k, end - k, int(p)])
    info = dict(off=round(off, 2), shift_ms=round(lag * 1000), raw=len(raw), extra=[p for p in full if p not in scale])
    return out, info
