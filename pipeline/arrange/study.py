#!/usr/bin/env python3
"""study.py — what the band plays under a section: the notes sounding in the backing and in the bass, window by
window, in the library key. For writing chords (and a bass line) by hand in manual.py.

usage: study.py <slug> [--start SECONDS] [--bars N] [--per BEATS] [--win BEATS] [--key NAME]
   --per   tracked beats per bar (default: pick.py NBEATS / 8)
   --win   window length in tracked beats (default: half a bar)

Needs the separated audio: ~/.venvs/demucs/bin/python sep.py <slug>  (convert.py deletes it; keep it while working).
Unlike the chroma cache this measures on a fine grid (five steps per semitone) at the recording's own tuning and
counts only what sits on a note, so a recording a quarter-tone off does not smear into its neighbours.

Per window: the best chords (major, minor, 7, m7, m7b5, dim), the notes sounding (share of the strongest),
and the bass stem's notes.
"""
import json, os, sys, warnings
import numpy as np, librosa, soundfile as sf
warnings.filterwarnings("ignore")
W = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, W)
from sect import analyse
from pick import NBEATS
from vox import NAMES
SR = 22050; HOP = 512; BPO = 60
KINDS = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10), "m7b5": (0, 3, 6, 10), "dim": (0, 3, 6)}


def fine_chroma(slug):
    """(backing chroma 12 x frames, bass chroma 12 x frames, tuning in semitones) on the recording's own tuning."""
    cache = f"{W}/sep/{slug}/study.npz"
    if os.path.exists(cache):
        z = np.load(cache); return z["acc"], z["bass"], float(z["tune"])
    out = {}
    def cq(name, lo, octs):
        y, sr = sf.read(f"{W}/sep/{slug}/{name}.wav", dtype="float32"); y = librosa.resample(y, orig_sr=sr, target_sr=SR)
        return np.abs(librosa.cqt(y, sr=SR, hop_length=HOP, fmin=librosa.note_to_hz(lo), n_bins=BPO * octs, bins_per_octave=BPO))
    C = cq("other", "C2", 5); B = cq("bass", "C1", 3)
    prof = (C ** 2).mean(axis=1) + (B ** 2).mean(axis=1)[:BPO * 5 - BPO * 0].sum() * 0     # tuning from the backing
    k = int(np.argmax([prof[j::5].sum() for j in range(5)])); tune = (k if k < 3 else k - 5) / 5.0
    def fold(M):
        M = np.roll(M, -k, axis=0)                                   # bin 0 now sits on a note
        on = M[0::5] + 0.5 * (np.roll(M, 1, axis=0)[0::5] + M[1::5])  # the note and its two nearest fifths of a semitone
        ch = np.array([on[pc::12].sum(axis=0) for pc in range(12)])
        return np.roll(ch, 1, axis=0) if k >= 3 else ch              # a grid 40 or 20 cents below a note belongs to that note, not the one under it
    acc, bass = fold(C), fold(B)
    n = min(acc.shape[1], bass.shape[1]); acc, bass = acc[:, :n], bass[:, :n]
    c2 = f"{W}/sep/{slug}/chroma2.npz"                               # name the notes as the rest of the tool does (keys.json):
    if os.path.exists(c2):                                           # a recording half a semitone off can be read either way
        d = int(round(tune - float(np.load(c2)["tune"])))
        acc, bass, tune = np.roll(acc, d, axis=0), np.roll(bass, d, axis=0), tune - d
    np.savez(cache, acc=acc, bass=bass, tune=tune)
    return acc, bass, tune


def main(slug, start=None, bars=8, per=None, win=None, key=None):
    picks = json.load(open(f"{W}/picks.json")); keys = json.load(open(f"{W}/keys.json"))
    beats = analyse(slug)["beats"]; per = per or NBEATS.get(slug, 32) // 8; win = win or per / 2
    b0 = int(np.argmin(abs(beats - (picks[slug] if start is None else start))))
    tonic = NAMES.index(key or keys[slug]); shift = (5 - tonic) % 12
    acc, bass, tune = fine_chroma(slug); t = np.arange(acc.shape[1]) * HOP / SR
    # the tuning may put the notes nearer the semitone above: name pitch classes by the nearest one
    bt = lambda x: np.interp(x, np.arange(len(beats)), beats)        # seconds at a (fractional) beat index
    print(f"{slug}: tuning {tune * 100:+.0f} cents, library key = recording {shift if shift <= 6 else shift - 12:+d} semitones, section from {beats[b0]:.2f}s, {per} beats per bar, windows of {win:g} beats")
    nm = lambda pc: NAMES[(pc + shift) % 12]
    nwin = int(round(bars * per / win))
    for w in range(nwin):
        a, b = bt(b0 + w * win), bt(b0 + (w + 1) * win); sel = (t >= a) & (t < b)
        if not sel.any(): break
        c = acc[:, sel].mean(axis=1) + 0.5 * bass[:, sel].mean(axis=1); c = c / (c.max() + 1e-9)
        bb = bass[:, sel].mean(axis=1); bb = bb / (bb.max() + 1e-9)
        sc = []
        for r in range(12):
            for kind, iv in KINDS.items():
                inn = [c[(r + i) % 12] for i in iv]; out = [c[p] for p in range(12) if (p - r) % 12 not in iv]
                sc.append((np.mean(inn) - 0.6 * np.mean(sorted(out)[-3:]) + 0.25 * bb[r] + (0.03 if len(iv) == 3 else 0.0), nm(r) + kind))
        sc.sort(reverse=True)
        pos = w * win; bar = int(pos // per) + 1; beat = pos % per + 1
        notes = " ".join(f"{nm(i)}{c[i]:.2f}" for i in np.argsort(c)[::-1] if c[i] >= 0.3)
        low = " ".join(f"{nm(i)}{bb[i]:.2f}" for i in np.argsort(bb)[::-1][:2] if bb[i] >= 0.4)
        print(f"  bar {bar:2d} beat {beat:3g}  " + "  ".join(f"{n}:{v:.2f}" for v, n in sc[:4]).ljust(46) + f" | {notes.ljust(44)} | bass: {low}")


if __name__ == "__main__":
    argv = sys.argv[1:]; opt = {}
    for name in ("--start", "--bars", "--per", "--win", "--key"):
        if name in argv: i = argv.index(name); opt[name] = argv[i + 1]; del argv[i:i + 2]
    main(argv[0], float(opt["--start"]) if "--start" in opt else None, int(opt.get("--bars", 8)),
         int(opt["--per"]) if "--per" in opt else None, float(opt["--win"]) if "--win" in opt else None, opt.get("--key"))
