"""Transcribe one song section from separated stems and write a library MIDI arrangement.
melody: pyin on the vocal stem -> the line as sung: notes + pitch-bend + expression (line.py)
chords: chroma of other+bass stems per half bar, diatonic triads; bass root from the bass stem
output: midi/<slug>.mid at 100 BPM, 8 bars 4/4, tracks melody / bass / guitar|pad|oud, written in F major / D minor."""
import sys, os, json, warnings
import numpy as np, librosa, soundfile as sf, pretty_midi
warnings.filterwarnings("ignore")
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
from songs import SONGS
from sect import analyse
from vox import tracks, slots, NAMES, MAJ, SR, HOP
import mel, line, manual
R = os.path.dirname(os.path.dirname(W))
BPM = 100.0; BEAT = 60 / BPM; LOOP = 32 * BEAT
STYLE = {"lifestyle-shabbat-baboker": "arp", "lifestyle-leitzan-katan": "strum", "memory-rivers-of-babylon": "offbeat", "memory-chai": "strum",
         "israel-shalom-lach-eretz": "arp", "israel-kirya-yefefiya": "oud", "hebrew-durme-durme": "arp", "hebrew-eliezer-ben-yehuda": "pad",
         "hebrew-adon-olam": "strum", "values-shir-lashalom": "strum", "values-tzadik-katamar": "pad", "values-kichlot-hakol": "pad",
         "values-haya-li-chaver": "arp", "culture-hallelujah": "arp", "culture-shevet-achim": "offbeat"}

# harmony patterns written as (sixteenth of the bar, velocity); the other styles (arp, strum, offbeat, oud, pad, waltz, beats) are in backing()
STRUMS = {"bossa": [(0, 64), (3, 54), (6, 58), (9, 54), (12, 58)],
          "eighths": [(0, 64), (2, 50), (4, 60), (6, 50), (8, 62), (10, 50), (12, 60), (14, 50)],
          "folk": [(0, 50), (4, 64), (6, 52), (8, 50), (12, 64), (14, 52)]}        # boom-chicka: the strum answers the bass on 2 and 4

def frames_t(n): return np.arange(n) * HOP / SR

def melody(slug, beats, sub, tonic=None):
    """Returns (notes [(slot, nslots, midi_float)], tune)."""
    tr = tracks(slug); f0 = tr["vocals_f0"]; rms = tr["vocals_rms"]; vp = tr["vocals_vp"]
    t = frames_t(len(f0)); midi = librosa.hz_to_midi(f0)
    ok = ~np.isnan(midi) & (rms > 0.06 * np.percentile(rms, 95))
    bounds = slots(beats, sub); vals = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        sel = (t >= a) & (t < b)
        if sel.sum() == 0 or ok[sel].mean() < 0.5: vals.append(np.nan); continue
        vals.append(float(np.median(midi[sel][ok[sel]])))
    vals = np.array(vals)
    # octave outliers: fold slots more than 8 st from the running median
    med = np.nanmedian(vals)
    for i, v in enumerate(vals):
        if np.isnan(v): continue
        while v - med > 9: v -= 12
        while med - v > 9: v += 12
        vals[i] = v
    # segment into notes: consecutive voiced slots within 0.6 st of the running note mean
    notes = []; cur = None
    for i, v in enumerate(vals):
        if np.isnan(v):
            cur = None; continue
        if cur is not None and abs(v - np.mean(cur[2])) < 0.6:
            cur[1] += 1; cur[2].append(v)
        else:
            cur = [i, 1, [v]]; notes.append(cur)
    notes = [(s, n, float(np.median(p))) for s, n, p in notes]
    return notes, vals

KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

def acc_keys(slug, a, b):
    """Relative-major tonic -> best Krumhansl score, from the accompaniment stems between a and b seconds."""
    acc, _ = chroma_stems(slug); t = frames_t(acc.shape[1]); prof = acc[:, (t >= a) & (t < b)].mean(axis=1)
    out = {}
    for tonic in range(12):
        for rel, k in ((tonic, KS_MAJOR), ((tonic + 3) % 12, KS_MINOR)):
            r = float(np.corrcoef(prof, np.roll(k, tonic))[0, 1]); out[rel] = max(out.get(rel, -1), r)
    return out

def acc_tuning(slug):
    cache = f"{W}/sep/{slug}/chroma2.npz"
    if os.path.exists(cache):
        z = np.load(cache)
        if "tune" in z: return float(z["tune"])
    o, sr = sf.read(f"{W}/sep/{slug}/other.wav", dtype="float32", frames=44100 * 120)
    return float(librosa.estimate_tuning(y=o, sr=sr))

def fit_scale(pitches, weights, cands=None, off0=0.0):
    """(major tonic pc, tuning offset, cost) that puts the most note-weight closest to a major scale.
    cands: {tonic: accompaniment key score}; only those tonics are tried and a higher score lowers the cost."""
    best = None
    for off in np.arange(off0 - 0.3, off0 + 0.301, 0.05):
        for t in (range(12) if cands is None else cands):
            sc = [(t + s) % 12 for s in MAJ]; cost = 0
            for p, w in zip(pitches, weights):
                q = p - off; d = min(abs(((q - s + 6) % 12) - 6) for s in sc)
                cost += w * min(d, 1.0) ** 2
            cost = cost / (sum(weights) + 1e-9) - (0.25 * cands[t] if cands is not None else 0)
            if best is None or cost < best[0]: best = (cost, t, float(off))
    return best[1], best[2], best[0]

def snap(p, tonic, off):
    q = p - off
    cands = [m for m in range(int(q) - 2, int(q) + 4) if (m - tonic) % 12 in MAJ]
    c = min(cands, key=lambda m: abs(m - q))
    return c if abs(c - q) <= 0.8 else int(round(q))

def chroma_stems(slug):
    cache = f"{W}/sep/{slug}/chroma2.npz"
    if os.path.exists(cache): z = np.load(cache); return z["acc"], z["bass"]
    o, sr = sf.read(f"{W}/sep/{slug}/other.wav", dtype="float32"); b, _ = sf.read(f"{W}/sep/{slug}/bass.wav", dtype="float32")
    o = librosa.resample(o, orig_sr=sr, target_sr=SR); b = librosa.resample(b, orig_sr=sr, target_sr=SR)
    tune = acc_tuning(slug)
    acc = librosa.feature.chroma_cqt(y=o + 0.7 * b, sr=SR, hop_length=HOP, bins_per_octave=36, tuning=tune)
    bass = librosa.feature.chroma_cqt(y=b, sr=SR, hop_length=HOP, fmin=librosa.note_to_hz("C1"), n_octaves=3, bins_per_octave=36, tuning=tune)
    np.savez(cache, acc=acc, bass=bass, tune=tune); return acc, bass

def chords(slug, beats, nwin, tonic):
    """One chord (root pc, 'maj'|'min') per window; windows split the section evenly in beats."""
    acc, bass = chroma_stems(slug); t = frames_t(acc.shape[1])
    per = (len(beats) - 1) // nwin
    # the bass player's own notes (pitch track of the bass stem): the strongest hint for the root
    tr = tracks(slug); bf, br = tr["bass_f0"], tr["bass_rms"]; bt = frames_t(len(bf))
    bok = ~np.isnan(bf) & (br > 0.1 * np.percentile(br, 95))
    bpc = np.round(librosa.hz_to_midi(np.where(bok, bf, 440.0)) - acc_tuning(slug)).astype(int) % 12
    cands = [((tonic + 0) % 12, "maj"), ((tonic + 2) % 12, "min"), ((tonic + 4) % 12, "min"), ((tonic + 5) % 12, "maj"),
             ((tonic + 7) % 12, "maj"), ((tonic + 9) % 12, "min"), ((tonic + 4) % 12, "maj"), ((tonic + 2) % 12, "maj"), ((tonic + 10) % 12, "maj")]
    prior = [0.06, 0.02, 0.0, 0.05, 0.05, 0.06, -0.03, -0.06, -0.06]
    out = []; scores = []
    for w in range(nwin):
        a, b = beats[w * per], beats[(w + 1) * per]; sel = (t >= a) & (t < b)
        c = acc[:, sel].mean(axis=1); c = c / (np.linalg.norm(c) + 1e-9)
        bb = bass[:, sel].mean(axis=1); bb = bb / (bb.max() + 1e-9)
        bs = (bt >= a) & (bt < b) & bok; bh = np.zeros(12)
        if bs.sum() >= 4: bh = np.bincount(bpc[bs], weights=br[bs], minlength=12); bh = bh / bh.sum()
        sc = []
        for (r, q), pr in zip(cands, prior):
            third = (r + (4 if q == "maj" else 3)) % 12; other3 = (r + (3 if q == "maj" else 4)) % 12
            sc.append(c[r] + 0.9 * c[third] + 0.8 * c[(r + 7) % 12] - 0.5 * c[other3] + 0.45 * bb[r] + pr
                      + 0.5 * bh[r] + 0.15 * (bh[third] + bh[(r + 7) % 12]))
        scores.append(sc); out.append(cands[int(np.argmax(sc))])
    # tidy: a half-bar that differs from both neighbours by a small margin takes the bar partner's chord
    scores = np.array(scores)
    for w in range(0, nwin - 1, 2):
        if out[w] != out[w + 1]:
            i0, i1 = cands.index(out[w]), cands.index(out[w + 1])
            tot0 = scores[w, i0] + scores[w + 1, i0]; tot1 = scores[w, i1] + scores[w + 1, i1]; split = scores[w, i0] + scores[w + 1, i1]
            if split - max(tot0, tot1) < 0.12:
                out[w] = out[w + 1] = cands[i0] if tot0 >= tot1 else cands[i1]
    return out

def backing(bass, h, ch, style, metre="four"):
    """Write the bass and harmony tracks. ch: (root, intervals, bass) chords evenly spread over the loop.
    metre: 'four' = 4/4, 'six' = two groups of three per half bar (6/8 feel), 'three' = 3/4, three beats to the bar."""
    n = len(ch); span = LOOP / n; half = 2 * BEAT
    at = lambda t: ch[min(n - 1, int((t + 1e-6) / span))]
    def low(c):                                                   # D2..C#3
        return 36 + c[2] if c[2] >= 2 else 48 + c[2]
    def alt(c):                                                   # the fifth, for the second bass note (a chord over another bass note keeps it)
        if c[2] != c[0]: return low(c)
        return low(c) + 7 if low(c) + 7 <= 53 else low(c) - 5
    def tones(c):
        ps = [48 + c[0] + i for i in c[1]]; ps = [p if p >= 50 else p + 12 for p in ps]; return [p if p <= 69 else p - 12 for p in ps]
    def tri(c):                                                   # three notes for broken chords: a seventh takes the place of the fifth
        ps = tones(c); return sorted(ps[:3] if len(ps) == 3 else [ps[0], ps[1], ps[3]])
    def held(t0, t1, vel=50):                                     # pad: each chord for as long as it lasts
        t = t0
        while t < t1 - 1e-6:
            c = at(t); e = t + span
            while e < t1 - 1e-6 and at(e) == c: e += span
            e = min(e, t1)
            for p in sorted(set(tones(c))): h.notes.append(pretty_midi.Note(vel, p, t, t + (e - t) * 0.98))
            t = e
    if metre == "three":
        bar = 4 * BEAT; q = bar / 3; e = q / 2
        for b in range(8):
            for k in range(3):
                t = b * bar + k * q; c = at(t); same = k > 0 and at(t - q) == c
                if k == 0: bass.notes.append(pretty_midi.Note(90, low(c), t, t + (1.9 * q if at(t + q) == c else 0.9 * q)))
                elif not same: bass.notes.append(pretty_midi.Note(84, low(c), t, t + 0.9 * q))
                elif k == 2: bass.notes.append(pretty_midi.Note(75, alt(c), t, t + 0.9 * q))
                if style == "arp":
                    for j in (0, 1):
                        cc = at(t + j * e); p = tri(cc)[[0, 1, 2, 1, 2, 1][2 * k + j]]; h.notes.append(pretty_midi.Note(60 if j == 0 else 54, p, t + j * e, t + j * e + 0.5))
                elif style == "waltz":
                    if k: [h.notes.append(pretty_midi.Note(56, p, t + j * 0.012, t + 0.4)) for j, p in enumerate(sorted(set(tones(c))))]
                elif style == "pad": pass
                else:                                               # strum: every beat, the first the strongest
                    for j, p in enumerate(sorted(set(tones(c)))): h.notes.append(pretty_midi.Note(64 if k == 0 else 52, p, t + j * 0.012, t + 0.45))
            if style == "pad": held(b * bar, (b + 1) * bar)
        return
    if style in STRUMS:                                             # a written strumming pattern: (sixteenth of the bar, velocity)
        for b in range(8):
            for step, vel in STRUMS[style]:
                t = b * 4 * BEAT + step * BEAT / 4
                for j, p in enumerate(sorted(set(tones(at(t))))): h.notes.append(pretty_midi.Note(vel, p, t + j * 0.01, t + 0.3))
    for w in range(16):
        t0 = w * half; c0 = at(t0); c1 = at(t0 + BEAT)
        if metre == "six":      # each window = 2 library beats = 3 triplet-quarters
            q3 = half / 3; t3 = tri(c0)
            bass.notes.append(pretty_midi.Note(90, low(c0), t0, t0 + q3 * 1.9)); bass.notes.append(pretty_midi.Note(75, alt(c0), t0 + 2 * q3, t0 + 2.9 * q3))
            for k, p in enumerate([t3[0], t3[1], t3[2], t3[1], t3[2], t3[1]]):
                h.notes.append(pretty_midi.Note(60, p, t0 + k * q3 / 2, t0 + k * q3 / 2 + 0.3))
            continue
        bass.notes.append(pretty_midi.Note(90, low(c0), t0, t0 + BEAT * 0.9))
        bass.notes.append(pretty_midi.Note(78, low(c1) if c1 != c0 else alt(c0) if w % 2 else low(c0), t0 + BEAT, t0 + BEAT * 1.9))
        e = BEAT / 2
        if style == "pad": held(t0, t0 + half); continue
        if style == "beats":                                        # a slow broken chord, one note to the beat
            for k in (0, 1): h.notes.append(pretty_midi.Note(60 if w % 2 == 0 and k == 0 else 54, tri(at(t0 + k * BEAT))[[0, 1, 2, 1][(2 * w + k) % 4]], t0 + k * BEAT, t0 + k * BEAT + 0.85))
            continue
        for k in range(4):
            c = at(t0 + k * e); t3 = tri(c); full = sorted(set(tones(c)))
            if style == "arp": h.notes.append(pretty_midi.Note(60, [t3[0], t3[2], t3[1], t3[2]][k], t0 + k * e, t0 + k * e + 0.4))
            elif style == "strum":
                if k != 1:
                    for j, p in enumerate(full): h.notes.append(pretty_midi.Note({0: 64, 2: 56, 3: 50}[k], p, t0 + k * e + j * 0.012, t0 + k * e + 0.35))
            elif style == "offbeat":
                if k in (1, 3):
                    for j, p in enumerate(full): h.notes.append(pretty_midi.Note(62, p, t0 + k * e + j * 0.01, t0 + k * e + 0.25))
            elif style == "oud": h.notes.append(pretty_midi.Note(62, [t3[0], t3[0] + 12 if t3[0] + 12 <= 69 else t3[2], t3[1], t3[2]][k], t0 + k * e, t0 + k * e + 0.4))


def build(slug, pick, verbose=True, out_dir=None):
    d = analyse(slug); allb = d["beats"]; N = pick["N"]
    b0 = int(np.argmin(np.abs(allb - pick["start"]))); beats = allb[b0:b0 + N + 1]
    triplet = N == 48
    sub = 2 if triplet else 4; nslots = N * sub; slot_dur = LOOP / nslots
    notes, vals = melody(slug, beats, sub)
    # scale from the whole song's vocal line (more evidence than one section)
    lo_t, hi_t = max(0.0, pick["start"] - 45), pick["start"] + pick["dur"] + 45
    kb = allb[(allb >= lo_t) & (allb <= hi_t)]; allnotes, _ = melody(slug, kb, 2)
    ks = acc_keys(slug, lo_t, hi_t); top = sorted(ks, key=ks.get, reverse=True)[:3]
    close = [t for t in top if ks[top[0]] - ks[t] < 0.10]
    tonic, off, cost = fit_scale([p for _, _, p in allnotes], [n for _, n, _ in allnotes], {t: ks[t] for t in close}, acc_tuning(slug))
    if verbose: print("   key candidates (rel. major tonic: accompaniment score): " + ", ".join(f"{NAMES[t]}:{ks[t]:.2f}" for t in top))
    keys = json.load(open(f"{W}/keys.json")) if os.path.exists(f"{W}/keys.json") else {}
    if slug in keys: tonic = NAMES.index(keys[slug])            # pinned: the key does not flip between runs
    else: keys[slug] = NAMES[tonic]; json.dump(keys, open(f"{W}/keys.json", "w"), indent=1)
    shift = (5 - tonic) % 12
    if shift > 6: shift -= 12
    # melody: the line exactly as sung (line.py): notes + pitch-bend + expression, moved to the library key
    man = manual.SONGS.get(slug)
    if man:                                                         # a melody written by hand (manual.py), already in the library key
        u = LOOP / man["units"]
        ln = dict(notes=[(s * u, (s + n) * u - min(0.05, 0.12 * n * u), pretty_midi.note_name_to_number(p) - shift) for s, n, p in man["melody"]],
                  bends=[], expr=[], frames=None, off=0.0, resid=0.0, repaired=0.0, extra=[])
        for f in (f"{W}/out/{slug}.line.npz", f"{W}/out/{slug}.frames.json"):
            if os.path.exists(f): os.remove(f)
    else:
        ln = line.build(slug, beats, acc_tuning(slug), [(tonic + s) % 12 for s in MAJ], LOOP)
    octs = 0
    if ln["notes"] and not man:
        med = np.median(np.repeat([p for _, _, p in ln["notes"]], [max(1, int(round((e - s) * 50))) for s, e, _ in ln["notes"]])) + shift
        octs = int(round((69 - med) / 12))                         # register: median near A4
    move = shift + 12 * octs
    clean = [[min(nslots - 1, int(round(s / slot_dur))), max(1, int(round((e - s) / slot_dur))), p + move] for s, e, p in ln["notes"]]   # for the printout
    minfo = dict(off=ln["off"], shift_ms=0, extra=ln["extra"])
    os.makedirs(f"{W}/out", exist_ok=True)
    if ln["frames"]: np.savez(f"{W}/out/{slug}.line.npz", move=move, repaired=ln["repaired"], **ln["frames"])   # what verify.py checks the render against
    if ln["frames"]: json.dump(ln["span"], open(f"{W}/out/{slug}.frames.json", "w"))
    if man: ch = manual.chord_list(man["chords"])
    else:
        ch = chords(slug, beats, 16, tonic)
        ch = [((r + shift) % 12, (0, 4, 7) if q == "maj" else (0, 3, 7), (r + shift) % 12) for r, q in ch]
    pm = pretty_midi.PrettyMIDI(initial_tempo=BPM, resolution=960)
    m = pretty_midi.Instrument(program=(man or {}).get("lead", 73), name="melody")
    if ln["bends"]:
        for num, val in ((101, 0), (100, 0), (6, int(line.BEND_RANGE)), (38, 0)): m.control_changes.append(pretty_midi.ControlChange(num, val, 0.0))
    for st, en, p in ln["notes"]: m.notes.append(pretty_midi.Note(velocity=90, pitch=int(p + move), start=st, end=en))
    for tm, semis in ln["bends"]: m.pitch_bends.append(pretty_midi.PitchBend(int(np.clip(round(8192 * semis / line.BEND_RANGE), -8192, 8191)), tm))
    for tm, lev in ln["expr"]: m.control_changes.append(pretty_midi.ControlChange(11, int(round(127 * lev)), tm))
    bass = pretty_midi.Instrument(program=33, name="bass")
    style = (man or {}).get("style") or STYLE.get(slug, "strum"); hname = {"pad": "pad", "oud": "oud"}.get(style, "guitar")
    h = pretty_midi.Instrument(program={"pad": 89, "oud": 105}.get(style, 24), name=hname)
    three = (man or {}).get("beats", 4) == 3
    backing(bass, h, ch, style, "three" if three else "six" if triplet else "four")
    if man and man.get("bass") == "eighths":                        # the root on every eighth note (a pop bass)
        n8 = len(ch); at = lambda t: ch[min(n8 - 1, int((t + 1e-6) * n8 / LOOP))]
        bass.notes = [pretty_midi.Note(88 if k % 2 == 0 else 76, 36 + at(k * BEAT / 2)[2] if at(k * BEAT / 2)[2] >= 2 else 48 + at(k * BEAT / 2)[2], k * BEAT / 2, k * BEAT / 2 + BEAT * 0.42) for k in range(64)]
    elif man and man.get("bass"):                                   # the bass line written out
        u = LOOP / man["units"]
        bass.notes = [pretty_midi.Note(88, pretty_midi.note_name_to_number(p), s * u, (s + n) * u - min(0.04, 0.1 * n * u)) for s, n, p in man["bass"]]
    pm.instruments += [m, bass, h]
    out = f"{out_dir or R + '/midi'}/{slug}.mid"; os.makedirs(os.path.dirname(out), exist_ok=True); pm.write(out)
    cov = sum(n for _, n, _ in clean) / nslots
    inscale = np.mean([((p - 5) % 12) in MAJ for _, _, p in clean]) if clean else 0
    info = dict(slug=slug, tonic=NAMES[tonic], shift=shift, scale_cost=round(cost, 3), notes=len(clean), coverage=round(cov, 2), inscale=round(float(inscale), 2),
                lo=min(p for _, _, p in clean) if clean else 0, hi=max(p for _, _, p in clean) if clean else 0, harmony=hname)
    if verbose:
        print(f"== {slug}: src scale {NAMES[tonic]} major/rel minor (fit {cost:.3f}, tune {off:+.2f}) shift {shift:+d}; {len(clean)} notes (voice {minfo['off']:+.2f} st, beats off a straight line by up to {ln['resid'] * 1000:.0f} ms, tracking repairs {ln['repaired'] * 100:.1f}% of sung frames), coverage {cov:.2f}, in-scale {inscale:.2f}, range {info['lo']}-{info['hi']}, harmony {hname}/{style}")
        per = nslots // 8; grid = ["."] * nslots
        for s, n, p in clean:
            if grid[s] != ".": continue
            grid[s] = pretty_midi.note_number_to_name(int(p)).replace("#", "s")
            for k in range(1, n):
                if s + k < nslots: grid[s + k] = "-"
        for bar in range(8):
            cpb = len(ch) // 8
            cn = " ".join(man["chords"][bar * cpb:(bar + 1) * cpb]) if man else " ".join(f"{NAMES[r]}{'' if iv[1] == 4 else 'm'}" for r, iv, _ in ch[bar * 2: bar * 2 + 2])
            print(f"   bar {bar + 1} [{cn:8s}] " + " ".join(f"{g:>3s}" for g in grid[bar * per:(bar + 1) * per]))
    return info

if __name__ == "__main__":
    sys.exit("run convert.py instead")
