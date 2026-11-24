#!/usr/bin/env python3
"""judge.py — check a hand-written arrangement (manual.py) against its recording, with numbers instead of ears.

usage: judge.py <slug> [--dir midi-folder]        (default folder: out/, the last dry run of convert.py)

1. melody against the singer (score.py): pitch = share of the held singing where the written note is the sung
   pitch (any octave), starts = share of the singer's syllable starts that have a written note start within 90 ms.
2. bar by bar: the chords and the melody notes; a note held 0.3 s or longer that is not in its chord and sits a
   semitone from one of the chord's notes is marked "rub".
3. chords against the band: per chord, the share of the backing's sound (study.py's measurement, needs the
   separated audio or its cache sep/<slug>/study.npz) that falls on the chord's notes, and a better-fitting
   chord when there is one.
4. the whole clip against the whole recording: the MIDI is rendered, and its notes are compared beat by beat with
   the notes of the recording section (cosine similarity of the twelve pitch classes, 1 = the same notes).
"""
import json, os, sys, tempfile, warnings
import numpy as np, librosa, pretty_midi, soundfile as sf
warnings.filterwarnings("ignore")
W = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(os.path.dirname(W))
sys.path.insert(0, W); sys.path.insert(0, f"{R}/pipeline")
import manual, score
from sect import analyse, ensure_wav
from pick import NBEATS
from vox import NAMES
LOOP = 19.2; SR = 22050; HOP = 512


def section(slug):
    picks = json.load(open(f"{W}/picks.json")); beats = analyse(slug)["beats"]; n = NBEATS.get(slug, 32)
    b0 = int(np.argmin(np.abs(beats - picks[slug]))); return beats[b0:b0 + n + 1], picks


def main(slug, folder):
    man = manual.SONGS[slug]; path = f"{folder}/{slug}.mid"; bs, picks = section(slug)
    keys = json.load(open(f"{W}/keys.json")); shift = (5 - NAMES.index(keys[slug])) % 12
    r = score.score(slug, path, picks)
    print(f"{slug}: melody against the singer: pitch {r['pitch'] * 100:.0f}%, starts {r['starts'] * 100:.0f}%, written notes with no syllable start {r['extra'] * 100:.0f}%, sung time with a note {r['cover'] * 100:.0f}%")
    if "--starts" in sys.argv:                                     # where the singer starts syllables / changes note, in grid steps
        import mel, line as ln_
        m, ok, rms, on = mel.voice(slug); t = np.arange(len(m)) * mel.FR; i0, i1 = np.searchsorted(t, bs[0]), np.searchsorted(t, bs[-1])
        tau = np.interp(t[i0:i1], bs, np.arange(len(bs)) * LOOP / (len(bs) - 1)); v = ok[i0:i1]; o = on[i0:i1]; x = m[i0:i1]; uu = LOOP / man["units"]
        written = np.array([s_ for s_, _, _ in man["melody"]], dtype=float); out = []
        for f in range(1, len(v) - 1):
            new = v[f] and not v[max(0, f - 3):f].any(); peak = v[f] and o[f] > 0.5 and o[f] >= o[f - 1] and o[f] >= o[f + 1]
            if new or (peak and (not out or tau[f] / uu - out[-1][0] > 0.45)):
                st = tau[f] / uu; d = written - st; j = int(np.argmin(np.abs(d))); out.append((st, "breath" if new else "onset", d[j], x[f + 2] if f + 2 < len(x) else x[f]))
        print("   singer's starts (step: kind, nearest written start is this many steps away):")
        print("     " + "  ".join(f"{st:.1f}:{k[0]}{d:+.1f}" + ("!" if abs(d) * uu > 0.09 else "") for st, k, d, _ in out))
    # where the held singing and the written notes disagree (runs of 70 ms and longer), in grid steps
    import mel
    m_, ok_, _, _ = mel.voice(slug); t_ = np.arange(len(m_)) * mel.FR; i0, i1 = np.searchsorted(t_, bs[0]), np.searchsorted(t_, bs[-1])
    tau = np.interp(t_[i0:i1], bs, np.arange(len(bs)) * LOOP / (len(bs) - 1)); x = m_[i0:i1]; held = mel.settled(m_, ok_)[i0:i1]; uu = LOOP / man["units"]
    roll = np.full(len(tau), np.nan)
    for s_, k_, p_ in man["melody"]: roll[(tau >= s_ * uu) & (tau < (s_ + k_) * uu + 0.03)] = pretty_midi.note_name_to_number(p_)
    both = held & ~np.isnan(roll); off = np.median(((x[both] - roll[both] + 6) % 12) - 6) if both.any() else 0.0
    near = np.full(len(x), np.inf)
    for k_ in range(-4, 5):
        e = np.abs(((x - np.roll(roll, k_) - off + 6) % 12) - 6); near = np.fmin(near, np.where(np.isnan(e), np.inf, e))
    bad = held & (near >= 0.5); runs = []; f = 0
    while f < len(bad):
        if not bad[f]: f += 1; continue
        g = f
        while g < len(bad) and bad[g]: g += 1
        if g - f >= 3:
            q = float(np.median(x[f:g])) - off; wr = roll[f:g][~np.isnan(roll[f:g])]
            name = pretty_midi.note_number_to_name(int(round(q)) % 12 + 60)[:-1]
            runs.append(f"{tau[f] / uu:.1f}-{tau[g - 1] / uu:.1f}: sung {name}{int(round((q - round(q)) * 100)):+d}c, written " + (pretty_midi.note_number_to_name(int(wr[0])) if len(wr) else "nothing"))
        f = g
    if runs: print("   singer and written note differ at steps:  " + ";  ".join(runs))
    # 2. notes and chords, bar by bar
    ch = manual.chord_list(man["chords"]); names = man["chords"]; n = len(ch); span = LOOP / n; u = LOOP / man["units"]; per = man["units"] // 8
    rubs = 0
    for bar in range(8):
        cpb = n // 8; line = []
        for s, k, p in man["melody"]:
            if not bar * per <= s < (bar + 1) * per: continue
            pc = pretty_midi.note_name_to_number(p) % 12; t0, t1 = s * u, (s + k) * u; flag = ""
            for w in range(int(t0 / span), min(n - 1, int((t1 - 1e-6) / span)) + 1):
                tones = {(ch[w][0] + i) % 12 for i in ch[w][1]}; inside = min(t1, (w + 1) * span) - max(t0, w * span)
                if inside >= 0.3 and pc not in tones and ({(pc + 1) % 12, (pc - 1) % 12} & tones): flag = f"(rub on {names[w]})"; rubs += 1
            line.append(f"{p}@{s - bar * per:g}{flag}")
        print(f"   bar {bar + 1} [{' '.join(names[bar * cpb:(bar + 1) * cpb])}]  " + " ".join(line))
    # 3. chords against the band
    try:
        from study import fine_chroma
        acc, bass, _ = fine_chroma(slug); t = np.arange(acc.shape[1]) * HOP / SR; fine = True
    except Exception:
        z = np.load(f"{W}/sep/{slug}/chroma2.npz"); acc, bass = z["acc"], z["bass"]; t = np.arange(acc.shape[1]) * HOP / SR; fine = False
    bt = lambda x: np.interp(x, np.arange(len(bs)), bs); nb = len(bs) - 1
    print(f"   chords against the band ({'fine measurement' if fine else 'chroma cache'}): share of the backing on the chord's notes" + ("" if fine else "  (rough)"))
    low = []
    for w in range(n):
        sel = (t >= bt(w * nb / n)) & (t < bt((w + 1) * nb / n)); c = acc[:, sel].mean(axis=1) + 0.5 * bass[:, sel].mean(axis=1); c = np.roll(c, shift); c = c / (c.sum() + 1e-9)
        tones = sorted({(ch[w][0] + i) % 12 for i in ch[w][1]}); on = float(c[tones].sum())
        best = max(((c[[(q + i) % 12 for i in iv]].sum(), NAMES[q] + nm) for q in range(12) for nm, iv in (("", (0, 4, 7)), ("m", (0, 3, 7)))))
        low.append((on, w, best))
    print("     " + "  ".join(f"{names[w]}:{on * 100:.0f}" for on, w, _ in low))
    for on, w, best in low:
        if best[0] > on + 0.12 and len({(ch[w][0] + i) % 12 for i in ch[w][1]}) <= 3 or best[0] > on + 0.2:
            print(f"     chord {w + 1} of {n} ({names[w]}, bar {w * 8 // n + 1}): {on * 100:.0f}% on its notes; {best[1]} would have {best[0] * 100:.0f}%")
    # 4. render and compare with the recording
    from render_midi import render, manifest_defaults
    bpm, bars, bpb = manifest_defaults(R)
    with tempfile.TemporaryDirectory() as d:
        y, _ = render(path, f"{d}/x.wav", bpm, bars, bpb, log=lambda *a: None, reverb=False)
    y = librosa.resample(y.astype(np.float32), orig_sr=44100, target_sr=SR)
    cr = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP); tr = np.arange(cr.shape[1]) * HOP / SR
    o, sr = sf.read(ensure_wav(slug), always_2d=True, dtype="float32"); o = o.mean(axis=1)
    a, b = int(bs[0] * sr), int(bs[-1] * sr); seg = o[a:b]
    co = librosa.feature.chroma_cqt(y=seg, sr=sr, hop_length=HOP, tuning=librosa.estimate_tuning(y=seg, sr=sr)); to = bs[0] + np.arange(co.shape[1]) * HOP / sr
    co = np.roll(co, shift, axis=0); sims = []
    for k in range(nb):
        x = co[:, (to >= bs[k]) & (to < bs[k + 1])].mean(axis=1); z = cr[:, (tr >= k * LOOP / nb) & (tr < (k + 1) * LOOP / nb)].mean(axis=1)
        sims.append(float(x @ z / (np.linalg.norm(x) * np.linalg.norm(z) + 1e-9)))
    per_bar = [np.mean(sims[i * nb // 8:(i + 1) * nb // 8]) for i in range(8)]
    print(f"   clip against the recording, same notes sounding (1 = identical): {np.mean(sims):.2f} overall; per bar " + " ".join(f"{v:.2f}" for v in per_bar))
    return dict(r, rubs=rubs, sim=float(np.mean(sims)))


if __name__ == "__main__":
    argv = sys.argv[1:]; folder = f"{W}/out"
    if "--dir" in argv: i = argv.index("--dir"); folder = argv[i + 1]; del argv[i:i + 2]
    for s in [a for a in argv if not a.startswith("--")]: main(s, folder)
