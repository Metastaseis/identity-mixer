"""Pick an N-beat section per song: beats on the full track, bar phase from chord-change novelty,
vocal-band centre energy per beat, structural novelty. Prints candidates; caches to sect/<slug>.npz."""
import sys, os, subprocess, warnings
import numpy as np, librosa, soundfile as sf, scipy.signal as ss
warnings.filterwarnings("ignore")
W = os.path.dirname(os.path.abspath(__file__)); HOP = 512
R = os.path.dirname(os.path.dirname(W))
sys.path.insert(0, W)
from songs import SONGS

def ensure_wav(slug):
    """Working copy of the recording: stereo 22050 Hz in wav/<slug>.wav."""
    out = f"{W}/wav/{slug}.wav"
    if not os.path.exists(out):
        os.makedirs(f"{W}/wav", exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(R, SONGS[slug][1]), "-ar", "22050", "-ac", "2", out], check=True)
    return out

def analyse(slug):
    cache = f"{W}/sect/{slug}.npz"
    if os.path.exists(cache): return dict(np.load(cache))
    y, sr = sf.read(ensure_wav(slug), always_2d=True, dtype="float32")
    L, R = y[:, 0], y[:, 1]; mono = (L + R) / 2
    onset = librosa.onset.onset_strength(y=mono, sr=sr, hop_length=HOP)
    tempo, bf = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=HOP)
    beats = librosa.frames_to_time(bf, sr=sr, hop_length=HOP)
    # vocal-band centre energy
    SL = librosa.stft(L, n_fft=2048, hop_length=HOP); SR_ = librosa.stft(R, n_fft=2048, hop_length=HOP)
    sim = 2 * np.real(SL * np.conj(SR_)) / (np.abs(SL) ** 2 + np.abs(SR_) ** 2 + 1e-9)
    C = np.clip(sim, 0, 1) ** 4 * np.abs(SL + SR_) / 2
    H, P = librosa.decompose.hpss(C, margin=(2.0, 2.0))
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    vb = (f >= 300) & (f <= 3400)
    venv = np.sqrt((H[vb] ** 2).sum(axis=0)); tot = np.sqrt((np.abs(SL + SR_)[vb] ** 2).sum(axis=0) / 4)
    chroma = librosa.feature.chroma_cqt(y=librosa.effects.harmonic(mono, margin=2.0), sr=sr, hop_length=HOP)
    mfcc = librosa.feature.mfcc(y=mono, sr=sr, hop_length=HOP, n_mfcc=13)
    n = min(len(onset), chroma.shape[1], len(venv))
    bfr = bf[bf < n]
    cb = librosa.util.sync(chroma[:, :n], bfr, aggregate=np.median)[:, 1:len(bfr)]     # per beat interval
    mb = librosa.util.sync(mfcc[:, :n], bfr, aggregate=np.mean)[:, 1:len(bfr)]
    vbeat = librosa.util.sync(venv[None, :n], bfr, aggregate=np.mean)[0, 1:len(bfr)]
    tbeat = librosa.util.sync(tot[None, :n], bfr, aggregate=np.mean)[0, 1:len(bfr)]
    ob = np.array([onset[max(0, b - 2):b + 3].max() for b in bfr])
    d = dict(beats=beats[:len(bfr)], tempo=float(np.atleast_1d(tempo)[0]), cb=cb, mb=mb, vbeat=vbeat, tbeat=tbeat, ob=ob, dur=len(mono) / sr, sim=float(np.mean(np.abs(sim))))
    os.makedirs(f"{W}/sect", exist_ok=True); np.savez(cache, **d)
    return d

def acf(x, lag):
    x = x - x.mean(); return float(np.sum(x[lag:] * x[:-lag]) / (np.sum(x * x) + 1e-9))

def report(slug):
    d = analyse(slug); beats = d["beats"]; cb = d["cb"]
    c = cb / (np.linalg.norm(cb, axis=0, keepdims=True) + 1e-9)
    nov = np.r_[0, 1 - np.sum(c[:, 1:] * c[:, :-1], axis=0)]       # chord change entering beat i
    ob = d["ob"][:len(nov)]
    ibi = np.diff(beats)
    print(f"== {slug}: {float(d['dur']):.0f}s, {len(beats)} beats, median tempo {60/np.median(ibi):.1f}, stereo {float(d['sim']):.2f}")
    print("   acf chord-nov  " + " ".join(f"{l}:{acf(nov, l):+.2f}" for l in (2, 3, 4, 6, 8, 12)) + "   acf onset " + " ".join(f"{l}:{acf(ob, l):+.2f}" for l in (2, 3, 4, 6)))
    print("   phase4 nov " + str([round(float(nov[p::4].mean()), 3) for p in range(4)]) + " onset " + str([round(float(ob[p::4].mean()), 2) for p in range(4)])
          + " | phase3 nov " + str([round(float(nov[p::3].mean()), 3) for p in range(3)]) + " onset " + str([round(float(ob[p::3].mean()), 2) for p in range(3)]))
    v = d["vbeat"]; v = v / (np.percentile(v, 95) + 1e-9)
    print("   vocal-band/8 beats: " + "".join(str(min(9, int(v[i:i + 8].mean() * 10))) for i in range(0, len(v) - 8, 8)))
    print("   time at 8-beat marks (s): " + " ".join(f"{beats[i]:.0f}" for i in range(0, len(beats), 32)))

if __name__ == "__main__":
    for s in (sys.argv[1:] or SONGS): report(s)
