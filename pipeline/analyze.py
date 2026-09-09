#!/usr/bin/env python3
"""Report BPM, key (with confidence), integrated loudness, duration and the first
strong onset of an audio file. Also hosts the analysis helpers shared by
prepare_clip.py and check_library.py.

usage: analyze.py <file> [--json]
"""
import argparse, json, os, sys, warnings

import numpy as np
import soundfile as sf
import librosa
import pyloudnorm as pyln

warnings.filterwarnings("ignore")

ANALYSIS_SR = 22050
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Cb": "B", "Fb": "E"}
# Krumhansl–Schmuckler key profiles (Krumhansl 1990), index 0 = tonic.
KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


# ---------- loading ----------
def load_audio(path):
    """Return (samples, sr) with samples shaped (n, channels), float32 in -1..1.
    libsndfile decodes WAV/FLAC/OGG/MP3; anything else falls back to librosa/ffmpeg."""
    try:
        y, sr = sf.read(path, always_2d=True, dtype="float32")
    except Exception:
        y, sr = librosa.load(path, sr=None, mono=False)
        y = np.atleast_2d(y).T.astype("float32")
    return y, int(sr)


def to_mono(y):
    return y.mean(axis=1) if y.ndim == 2 else y


def analysis_signal(y, sr):
    """Mono signal at ANALYSIS_SR for tempo / key / onset work."""
    m = to_mono(y)
    return m if sr == ANALYSIS_SR else librosa.resample(m, orig_sr=sr, target_sr=ANALYSIS_SR)


# ---------- measurements ----------
def integrated_loudness(y, sr):
    """LUFS (BS.1770) on the native-rate signal; nan for material shorter than 400 ms."""
    if len(y) < int(0.4 * sr) + 1:
        return float("nan")
    return float(pyln.Meter(sr).integrated_loudness(y))


def peak_dbfs(y):
    p = float(np.max(np.abs(y))) if len(y) else 0.0
    return 20 * np.log10(p) if p > 0 else float("-inf"), p


def detect_tempo(m, sr=ANALYSIS_SR):
    """(bpm, tracker_bpm, beat_times). bpm is fitted across all tracked beats,
    which is far more precise than the tracker's own coarse estimate."""
    tempo, beats = librosa.beat.beat_track(y=m, sr=sr, units="time")
    tracker_bpm = float(np.atleast_1d(tempo)[0])
    if len(beats) >= 8:
        # beat times are quantised to the analysis hop (~23 ms); a straight-line fit of
        # time against beat index averages that out and gives the period to ~0.1%
        period = np.polyfit(np.arange(len(beats)), beats, 1)[0]
        bpm = 60.0 / float(period)
    else:
        bpm = tracker_bpm
    return bpm, tracker_bpm, beats


def detect_key(m, sr=ANALYSIS_SR, beats=None):
    """Krumhansl–Schmuckler matching on beat-synchronous chroma."""
    chroma = librosa.feature.chroma_cqt(y=m, sr=sr)
    if beats is not None and len(beats) > 2:
        frames = np.unique(np.clip(librosa.time_to_frames(beats, sr=sr), 0, chroma.shape[1] - 1))
        if len(frames) > 1:
            chroma = librosa.util.sync(chroma, frames, aggregate=np.median)
    profile = chroma.mean(axis=1)
    if not np.any(profile):
        return {"key": None, "confidence": 0.0, "runner_up": None, "margin": 0.0}
    scores = []
    for tonic in range(12):
        for mode, ks in (("major", KS_MAJOR), ("minor", KS_MINOR)):
            r = float(np.corrcoef(profile, np.roll(ks, tonic))[0, 1])
            scores.append((r, f"{NOTE_NAMES[tonic]} {mode}"))
    scores.sort(reverse=True)
    (r1, k1), (r2, k2) = scores[0], scores[1]
    return {"key": k1, "confidence": round(r1, 3), "runner_up": k2, "margin": round(r1 - r2, 3)}


def first_strong_onset(m, sr=ANALYSIS_SR):
    """(first_strong, first_any) in seconds. 'Strong' = at least half the strength of the
    strongest onset. The strong onset is backtracked to the start of its attack."""
    env = librosa.onset.onset_strength(y=m, sr=sr)
    frames = librosa.onset.onset_detect(onset_envelope=env, sr=sr)
    if len(frames) == 0:
        return 0.0, 0.0
    strengths = env[frames]
    strong = frames[strengths >= 0.5 * strengths.max()][0]
    strong = librosa.onset.onset_backtrack(np.array([strong]), env)[0]
    return float(librosa.frames_to_time(strong, sr=sr)), float(librosa.frames_to_time(frames[0], sr=sr))


def refine_onset(mono, sr, t_approx, window_s=0.04, threshold=0.1):
    """Sample-accurate attack start near t_approx (which is only hop-accurate):
    inside ±window_s, find the envelope peak, then walk back to where the envelope
    first rose above `threshold` of that peak. Starting a loop there keeps the
    transient at the head of the loop instead of chopping it at the tail."""
    lo, hi = max(0, int((t_approx - window_s) * sr)), min(len(mono), int((t_approx + window_s) * sr))
    if hi - lo < 8:
        return t_approx
    k = max(1, int(0.001 * sr))
    env = np.convolve(np.abs(mono[lo:hi]), np.ones(k) / k, mode="same")
    p = int(np.argmax(env))
    if env[p] <= 0:
        return t_approx
    i = p
    while i > 0 and env[i - 1] >= threshold * env[p]:
        i -= 1
    return (lo + i) / sr


# ---------- loudness normalisation ----------
def limit_peaks(y, sr, ceiling=0.99, lookahead_s=0.002, release_s=0.05):
    """Transparent brickwall limiter. Returns (y, max_reduction_db).
    Gain = rolling minimum of the required gain over the next lookahead window,
    smoothed causally over the same window (so the ramp finishes before the peak),
    then released exponentially toward unity."""
    a = np.max(np.abs(y), axis=1) if y.ndim == 2 else np.abs(y)
    req = np.minimum(1.0, ceiling / np.maximum(a, 1e-9))
    if req.min() >= 1.0:
        return y, 0.0
    la = max(2, int(lookahead_s * sr))
    padded = np.concatenate([req, np.ones(la - 1)])
    look = np.lib.stride_tricks.sliding_window_view(padded, la).min(axis=1)
    kernel = np.ones(la) / la
    smooth = np.convolve(np.concatenate([np.full(la - 1, look[0]), look]), kernel, mode="valid")
    rel = np.exp(-1.0 / (release_s * sr))
    g = np.empty_like(smooth)
    prev = 1.0
    for i in range(len(g)):
        prev = min(smooth[i], 1.0 - (1.0 - prev) * rel)
        g[i] = prev
    out = y * (g[:, None] if y.ndim == 2 else g)
    return out.astype(y.dtype, copy=False), float(-20 * np.log10(g.min()))


def normalize_loop(y, sr, target_lufs=-16.0, ceiling=0.99, passes=12):
    """Bring y to target_lufs integrated. Limits peaks to ceiling, re-measures and
    repeats until it converges, so percussive material lands on target without
    clipping. Returns (y, final_lufs, max_limiter_reduction_db)."""
    reduction = 0.0
    for _ in range(passes):
        l = integrated_loudness(y, sr)
        if not np.isfinite(l) or abs(l - target_lufs) < 0.05:
            break
        y = y * 10 ** ((target_lufs - l) / 20)
        y, r = limit_peaks(y, sr, ceiling)
        reduction = max(reduction, r)
    return y, integrated_loudness(y, sr), reduction


# ---------- keys ----------
def parse_key(s):
    """'A minor' / 'Bb major' / 'F#m' -> (pitch_class, 'major'|'minor')."""
    s = s.strip()
    parts = s.replace("-", " ").split()
    if len(parts) == 1 and s.endswith("m") and len(s) > 1:
        parts = [s[:-1], "minor"]
    if len(parts) != 2:
        raise ValueError(f"cannot parse key '{s}' (expected e.g. 'A minor' or 'F# major')")
    root, mode = parts[0], parts[1].lower()
    root = root[0].upper() + root[1:]
    root = FLATS.get(root, root)
    if root not in NOTE_NAMES:
        raise ValueError(f"unknown root '{parts[0]}' in key '{s}'")
    if mode.startswith("maj"):
        mode = "major"
    elif mode.startswith("min"):
        mode = "minor"
    else:
        raise ValueError(f"unknown mode '{parts[1]}' in key '{s}'")
    return NOTE_NAMES.index(root), mode


def relative_major_root(pc, mode):
    return pc if mode == "major" else (pc + 3) % 12


def semitone_shift(src_key, dst_key):
    """Smallest signed shift in -6..+5 that brings src's relative major onto dst's."""
    d = relative_major_root(*parse_key(dst_key)) - relative_major_root(*parse_key(src_key))
    d %= 12
    return d - 12 if d > 5 else d


def format_key(pc, mode):
    return f"{NOTE_NAMES[pc % 12]} {mode}"


# ---------- full report ----------
def analyze_file(path):
    y, sr = load_audio(path)
    m = analysis_signal(y, sr)
    bpm, tracker_bpm, beats = detect_tempo(m)
    key = detect_key(m, beats=beats)
    onset_strong, onset_first = first_strong_onset(m)
    lufs = integrated_loudness(y, sr)
    pk_db, pk = peak_dbfs(y)
    return {
        "file": path,
        "sample_rate": sr,
        "channels": int(y.shape[1]),
        "duration_s": round(len(y) / sr, 3),
        "bpm": round(bpm, 2),
        "bpm_tracker": round(tracker_bpm, 2),
        "bpm_alternatives": [round(bpm / 2, 2), round(bpm * 2, 2)],
        "beats_detected": int(len(beats)),
        "key": key["key"],
        "key_confidence": key["confidence"],
        "key_runner_up": key["runner_up"],
        "key_margin": key["margin"],
        "lufs": None if np.isnan(lufs) else round(lufs, 2),
        "peak_dbfs": round(pk_db, 2) if np.isfinite(pk_db) else None,
        "first_strong_onset_s": round(onset_strong, 3),
        "first_onset_s": round(onset_first, 3),
    }


def print_report(r):
    print(f"{os.path.basename(r['file'])}")
    print(f"  duration      {r['duration_s']:.3f} s   ({r['channels']} ch, {r['sample_rate']} Hz)")
    print(f"  BPM           {r['bpm']:.2f}   (tracker {r['bpm_tracker']:.2f}; half/double {r['bpm_alternatives'][0]:.2f} / {r['bpm_alternatives'][1]:.2f}; {r['beats_detected']} beats)")
    print(f"  key           {r['key']}   confidence {r['key_confidence']:.3f}  (runner-up {r['key_runner_up']}, margin {r['key_margin']:.3f})")
    print(f"  loudness      {r['lufs']} LUFS   peak {r['peak_dbfs']} dBFS")
    print(f"  first onset   strong at {r['first_strong_onset_s']:.3f} s   (any at {r['first_onset_s']:.3f} s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    a = ap.parse_args()
    if not os.path.isfile(a.file):
        sys.exit(f"not found: {a.file}")
    r = analyze_file(a.file)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print_report(r)


if __name__ == "__main__":
    main()
