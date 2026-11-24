"""line.py — the melody exactly as it is sung.

The vocal pitch track of the section is cleaned (tracking slips only), cut into MIDI notes, and the
difference between each note and the pitch actually sung is written as pitch-bend, frame by frame.
The level of the voice is written as expression (CC11). Notes inside one breath of singing are tied;
a new syllable starts a new attack. Time follows the tracked beats after smoothing them (a straight
line plus their slow drift), so the singer's own rhythm is kept and a beat-tracking wobble cannot bend it.

build(slug, beats, tune, scale, loop) -> dict(notes, bends, expr, ...) in the song's own key.
pipeline/render_midi.py plays such a track as a sung line.
"""
import numpy as np
import mel
from mel import FR

BEND_RANGE = 2.0      # semitones: the General MIDI default, so any synth plays the bends right
ATTACK_GAP = 0.01     # s of silence before a new syllable inside one breath


def stretches(ok):
    out = []; i = 0; n = len(ok)
    while i < n:
        if not ok[i]: i += 1; continue
        j = i
        while j < n and ok[j]: j += 1
        out.append((i, j)); i = j
    return out


def clean(x, ok):
    """Repair pitch-tracking slips; never changes what is sung. Returns (x, ok, changed frames)."""
    x = x.copy(); ok = ok.copy(); raw = x.copy(); raw_ok = ok.copy()
    # 1. a dropout of up to 2 frames inside a held sound: bridge it
    for (a, b), (c, d) in zip(stretches(ok)[:-1], stretches(ok)[1:]):
        if c - b <= 2 and abs(x[c] - x[b - 1]) < 2.0:
            x[b:c] = np.interp(np.arange(b, c), [b - 1, c], [x[b - 1], x[c]]); ok[b:c] = True
    # 2. octave slips: a jump of about an octave that comes back within 0.3 s, or sits at the edge of a breath
    for a, b in stretches(ok):
        i = a + 1
        while i < b:
            d = x[i] - x[i - 1]
            if 9.5 <= abs(d) <= 14.5:
                j = i + 1
                while j < b and j - i <= 12 and not (9.5 <= abs(x[j] - x[j - 1]) <= 14.5 and (x[j] - x[j - 1]) * d < 0): j += 1
                if j < b and j - i <= 12: x[i:j] -= 12 * np.sign(d); i = j + 1; continue
                if b - i <= 6: x[i:b] -= 12 * np.sign(d); break
                if i - a <= 6: x[a:i] += 12 * np.sign(d)
            i += 1
    # 3. one- or two-frame spikes
    for a, b in stretches(ok):
        if b - a < 5: continue
        med = np.array([np.median(x[max(a, i - 2):min(b, i + 3)]) for i in range(a, b)])
        bad = np.abs(x[a:b] - med) > 0.8                              # (a slide is left alone: on a slide the middle value is the median)
        x[a:b][bad] = med[bad]
    # 4. a short sound an octave away from the singing on both sides of it
    runs = stretches(ok); meds = [float(np.median(x[a:b])) for a, b in runs]
    for k in range(1, len(runs) - 1):
        a, b = runs[k]; d0, d1 = meds[k] - meds[k - 1], meds[k] - meds[k + 1]
        if b - a < 14 and abs(d0) >= 10 and abs(d1) >= 10 and d0 * d1 > 0: x[a:b] -= 12 * np.sign(d0)
    # 5. blips shorter than 70 ms are not notes
    for a, b in stretches(ok):
        if b - a < 3: ok[a:b] = False
    changed = (raw_ok != ok) | (ok & (np.abs(x - raw) > 0.5))
    return x, ok, changed


def pulled(q, scale):
    k0 = int(np.floor(q))
    return min((k0, k0 + 1), key=lambda k: (q - k) ** 2 + (0.0 if k % 12 in scale else mel.PULL))


def segment(x, ok, rms, on, scale):
    """[(first frame, end frame, pitch, attack?)]: the notes of the line. Every sung frame is in a note."""
    st = mel.settled(x, ok)
    q = mel.decode(x, ok, st, scale).astype(int)
    q[~ok] = 0
    for i in np.where(ok & (q == 0))[0]: q[i] = pulled(x[i], scale)
    notes = []
    for a, b in stretches(ok):
        # level runs inside this breath; very short ones join the note they lead into (or the one before)
        runs = []; i = a
        while i < b:
            j = i
            while j < b and q[j] == q[i]: j += 1
            runs.append([i, j, int(q[i])]); i = j
        k = 0
        while k < len(runs) and len(runs) > 1:
            if runs[k][1] - runs[k][0] <= 3:
                if k + 1 < len(runs): runs[k + 1][0] = runs[k][0]
                else: runs[k - 1][1] = runs[k][1]
                del runs[k]; continue
            k += 1
        for i, j, p in runs: q[i:j] = p
        far = np.abs(x[a:b] - q[a:b]) > 1.8                          # keep every bend inside the bend range
        q[a:b][far] = np.round(x[a:b][far]).astype(int)
        i = a
        while i < b:
            j = i
            while j < b and q[j] == q[i]: j += 1
            cuts = [i]
            for f in range(i + 4, j - 3):                            # a new syllable on the same pitch
                if on[f] < 0.35 or on[f] < on[f - 1] or on[f] < on[f + 1] or f - cuts[-1] < 4: continue
                if rms[max(i, f - 4):f + 1].min() < 0.7 * rms[f + 1:min(j, f + 5)].max(): cuts.append(f)
            cuts.append(j)
            for n, (s, e) in enumerate(zip(cuts[:-1], cuts[1:])):
                attack = s == a or n > 0
                if not attack:                                        # a new syllable that also changes pitch
                    w = on[max(a, s - 2):s + 3]
                    after = rms[s + 1:min(b, s + 5)]
                    attack = bool(len(after) and w.max() >= 0.35 and rms[max(a, s - 4):s + 1].min() < 0.7 * after.max())
                notes.append((s, e, int(q[s]), attack))
            i = j
    return notes


def build(slug, beats, tune, scale, loop=19.2):
    m, ok, rms, on = mel.voice(slug)
    n = len(beats) - 1; t = np.arange(len(m)) * FR
    p, a = np.polyfit(np.arange(n + 1), beats, 1)                    # beat k is at a + p*k seconds
    resid = float(np.max(np.abs(beats - (a + p * np.arange(n + 1)))))
    rate = (loop / n) / p                                             # loop seconds per recording second
    i0, i1 = np.searchsorted(t, a + FR / 2), np.searchsorted(t, a + p * n - FR / 2)
    w0, w1 = np.searchsorted(t, a - 45), np.searchsorted(t, a + p * n + 45)
    empty = dict(notes=[], bends=[], expr=[], frames=None, off=tune, resid=resid, a=float(a), p=float(p), sung=0.0, repaired=0.0, extra=[])
    if ok[i0:i1].sum() < 10: return empty
    ok = ok & (rms > mel.LEVEL * np.percentile(rms[i0:i1][ok[i0:i1]], 90))
    off = mel.vocal_tuning(m[w0:w1], mel.settled(m, ok)[w0:w1], tune, scale)
    full = mel.sung_scale(m[w0:w1] - off, mel.settled(m, ok)[w0:w1], scale)
    lo = max(0, i0 - 20); x, okc, changed = clean(m[lo:i1 + 20] - off, ok[lo:i1 + 20])
    x, okc, changed = x[i0 - lo:i1 - lo], okc[i0 - lo:i1 - lo], changed[i0 - lo:i1 - lo]
    if okc.sum() < 10: return empty
    r, o = rms[i0:i1], on[i0:i1]
    seg = segment(x, okc, r, o, full)
    drift = beats - (a + p * np.arange(n + 1)); pad = np.r_[np.full(4, drift[0]), drift, np.full(4, drift[-1])]
    smooth = a + p * np.arange(n + 1) + np.convolve(pad, np.ones(9) / 9, mode="valid")
    tau = np.interp(t[i0:i1], smooth, np.arange(n + 1) * loop / n)   # loop time of each frame centre
    tau = np.where(t[i0:i1] < smooth[0], (t[i0:i1] - smooth[0]) * rate, tau)
    half = FR * rate / 2
    ref = np.percentile(r[okc], 90)
    notes, bends, expr = [], [], []
    for k, (s, e, pitch, attack) in enumerate(seg):
        start, end = max(0.0, tau[s] - half), min(loop - 0.005, tau[e - 1] + half)
        if end - start < 0.02: continue
        if attack and notes and start - notes[-1][1] < ATTACK_GAP:    # break the tie before a new syllable
            prev = notes[-1]; notes[-1] = (prev[0], max(prev[0] + 0.01, start - ATTACK_GAP), prev[2])
        notes.append((float(start), float(end), pitch))
        for f in range(s, e):
            # four steps per frame, on straight lines through the frame centres, so slides are smooth
            before = x[f - 1] if f > 0 and okc[f - 1] else x[f]; after = x[f + 1] if f + 1 < len(x) and okc[f + 1] else x[f]
            for k, v in enumerate(((before + x[f]) / 2, (before + 3 * x[f]) / 4, x[f], (3 * x[f] + after) / 4)):
                tm = tau[f] - half + k * half / 2
                if 0.0 <= tm < loop: bends.append((float(tm), float(np.clip(v - pitch, -BEND_RANGE, BEND_RANGE))))
            expr.append((float(max(0.0, tau[f] - half)), float(np.clip((r[f] / ref) ** 0.5, 0.3, 1.0))))
    raw_ok = ok[i0:i1]
    frames = dict(tau=tau, sung=okc, pitch=np.where(okc, x, 0.0), raw_sung=raw_ok, raw_pitch=np.where(raw_ok, m[i0:i1] - off, 0.0))
    span = dict(i0=int(i0), i1=int(i1), off=float(off))                 # where these frames sit in the recording (for audit.py)
    return dict(notes=notes, bends=bends, expr=expr, frames=frames, span=span, off=float(off), resid=resid, a=float(a), p=float(p),
                sung=float(okc.mean()), repaired=float(changed.sum() / max(1, okc.sum())), extra=[pc for pc in full if pc not in scale])
