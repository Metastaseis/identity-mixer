"""Pitch tracks from separated stems: vocals (pyin, plus the onset envelope of the voice) and bass (pyin),
cached in sep/<slug>/f0b.npz. Frame hop 512 @ 22050."""
import sys, os, warnings
import numpy as np, librosa, soundfile as sf
warnings.filterwarnings("ignore")
W = os.path.dirname(os.path.abspath(__file__)); SR = 22050; HOP = 512
sys.path.insert(0, W)
from songs import SONGS
from sect import analyse
NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]; MAJ = [0,2,4,5,7,9,11]

FMIN = {"culture-hallelujah": 50}     # lowest sung pitch to look for, Hz (default 82 = E2); a bass voice needs less

def retrack(slug):
    """Redo only the vocal pitch track of an existing cache (after changing FMIN). Needs sep/<slug>/vocals.wav."""
    cache = f"{W}/sep/{slug}/f0b.npz"; out = dict(np.load(cache))
    y, sr = sf.read(f"{W}/sep/{slug}/vocals.wav", dtype="float32"); y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    f0, vf, vp = librosa.pyin(y, fmin=FMIN.get(slug, 82), fmax=1000, sr=SR, frame_length=2048, hop_length=HOP, fill_na=np.nan)
    n = len(out["vocals_rms"]); out["vocals_f0"] = f0[:n]; out["vocals_vp"] = vp[:n]
    np.savez(cache, **out)

def tracks(slug):
    cache = f"{W}/sep/{slug}/f0b.npz"
    if os.path.exists(cache): return dict(np.load(cache))
    out = {}
    for name, fmin, fmax in (("vocals", FMIN.get(slug, 82), 1000), ("bass", 33, 260)):
        y, sr = sf.read(f"{W}/sep/{slug}/{name}.wav", dtype="float32")
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
        f0, vf, vp = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=SR, frame_length=2048 if name == "vocals" else 4096, hop_length=HOP, fill_na=np.nan)
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP)[0]
        n = min(len(f0), len(rms))
        out[name + "_f0"] = f0[:n]; out[name + "_vp"] = vp[:n]; out[name + "_rms"] = rms[:n]
        if name == "vocals": out["vocals_onset"] = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)[:n]
    np.savez(cache, **out)
    return out

def slots(beats, sub):
    out = []
    for a, b in zip(beats[:-1], beats[1:]): out.extend(a + (b - a) * np.arange(sub) / sub)
    out.append(beats[-1]); return np.array(out)

def slot_notes(f0, rms, bounds, tune=0.0, minv=0.4, rthr=None):
    t = np.arange(len(f0)) * HOP / SR; midi = librosa.hz_to_midi(f0) - tune
    if rthr is None: rthr = 0.08 * np.percentile(rms, 95)
    ok = ~np.isnan(midi) & (rms > rthr)
    out = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        sel = (t >= a) & (t < b)
        if sel.sum() == 0 or ok[sel].mean() < minv: out.append(None); continue
        out.append(int(np.round(np.median(midi[sel][ok[sel]]))))
    return out

def tuning(f0, rms):
    ok = ~np.isnan(f0) & (rms > 0.1 * np.percentile(rms, 95)); m = librosa.hz_to_midi(f0[ok]); dev = m - np.round(m)
    return float(np.angle(np.mean(np.exp(2j * np.pi * dev))) / (2 * np.pi))

def scale_tonic(notes):
    pcs = np.bincount([p % 12 for p in notes if p is not None], minlength=12)
    cov = [sum(pcs[(t + s) % 12] for s in MAJ) for t in range(12)]
    return int(np.argmax(cov)), cov

def deg(p, tonic):
    if p is None: return " ."
    return {0:"1",1:"b2",2:"2",3:"b3",4:"3",5:"4",6:"#4",7:"5",8:"b6",9:"6",10:"b7",11:"7"}[(p - tonic) % 12].rjust(2)

def show(slug, start_beat, nbeats=32, bpb=4, sub=2, tonic=None, which="vocals"):
    d = analyse(slug); beats = d["beats"][start_beat:start_beat + nbeats + 1]; tr = tracks(slug)
    f0, rms = tr[which + "_f0"], tr[which + "_rms"]; tune = tuning(f0, rms)
    sp = slot_notes(f0, rms, slots(beats, sub), tune)
    if tonic is None: tonic = scale_tonic(slot_notes(f0, rms, slots(d["beats"], 2), tune))[0]
    print(f"{slug} [{which}] major-tonic {NAMES[tonic]} tune {tune:+.2f} beat {start_beat} = {beats[0]:.1f}s")
    per = bpb * sub
    for k in range(0, len(sp), per):
        print(f"  bar {k//per:2d} {beats[min(k//sub, len(beats)-1)]:6.1f}s | " + " ".join(f"{deg(p, tonic)}{'' if p is None else p//12-1}" for p in sp[k:k + per]))
    return sp

if __name__ == "__main__":
    a = sys.argv
    show(a[1], int(a[2]), int(a[3]) if len(a) > 3 else 32, int(a[4]) if len(a) > 4 else 4, int(a[5]) if len(a) > 5 else 2,
         NAMES.index(a[6]) if len(a) > 6 and a[6] != "-" else None, a[7] if len(a) > 7 else "vocals")
