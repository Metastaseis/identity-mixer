#!/usr/bin/env python3
"""Turn a source recording into a library clip: an exact whole-bar loop at the
manifest tempo, in the manifest key, at -16 LUFS. Appends the clip to manifest.json.

usage: prepare_clip.py <source> --asset <id> --title <t>
                       [--bpm N] [--key K] [--start seconds] [--bars N]
                       [--note TEXT] [--credit TEXT] [--fade MS] [--root DIR]

Steps: load (resampled to 44.1 kHz) -> detect BPM / key / downbeat (or use flags)
-> cut N bars from the downbeat at the source tempo -> one rubberband R3 pass:
time-stretch to the manifest tempo and pitch-shift to the manifest key
(relative-major-aware, smallest signed shift in -6..+5) -> fix the exact loop
length -> keep a stereo 24-bit master in sources/prepared/ (git-ignored) ->
mix to mono, normalise to -16 LUFS with edge fades (5 ms default), write
clips/<asset>-NN.wav as mono 44.1 kHz 16-bit WAV (exact sample count; MP3
cannot hold an exact loop length) -> append to manifest.json -> print a summary.

Importable: prepare(...) does the work and returns the manifest entry;
library.py builds add / replace on top of it.
"""
import argparse, json, os, re, sys, warnings

import numpy as np
import soundfile as sf
import librosa
import pyrubberband as pyrb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import (load_audio, analysis_signal, to_mono, detect_tempo, detect_key, first_strong_onset,  # noqa: E402
                     refine_onset, integrated_loudness, peak_dbfs, normalize_loop, parse_key, format_key,
                     semitone_shift)

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIP_SR = 44100
TARGET_LUFS = -16.0
LENGTH_TOL_S = 0.010        # rubberband may land a few samples off; trim/pad up to this
PEAK_CEILING = 0.99         # limiter ceiling; check_library flags anything at or above 0.999
DOWNBEAT_SNAP_S = 0.15      # snap the first strong onset to the nearest tracked beat if this close


class PrepareError(Exception):
    pass


def fmt_key(k):
    return format_key(*parse_key(k))


def loop_samples(m, bars, sr):
    """Exact sample count of `bars` bars at the library tempo, or raise if not whole."""
    x = bars * m["beats_per_bar"] * 60.0 / m["tempo"] * sr
    n = int(round(x))
    if abs(x - n) > 1e-6:
        raise PrepareError(f"{bars} bars at {m['tempo']} BPM is not a whole number of samples at {sr} Hz")
    return n


def to_clip_sr(y, sr):
    if sr == CLIP_SR:
        return y
    out = librosa.resample(np.ascontiguousarray(y.T), orig_sr=sr, target_sr=CLIP_SR, res_type="soxr_hq").T
    return np.ascontiguousarray(out, dtype="float32")


def fit_length(y, n, tol_samples, what):
    delta = len(y) - n
    if abs(delta) > tol_samples:
        raise PrepareError(f"{what}: length off by {delta} samples ({delta/CLIP_SR*1000:.1f} ms), more than the {tol_samples/CLIP_SR*1000:.0f} ms tolerance")
    if delta > 0:
        return y[:n], delta
    return np.vstack([y, np.zeros((-delta, y.shape[1]), y.dtype)]), delta


def finalize(master, n, fade_ms):
    """Stereo master at CLIP_SR -> mono (n, 1) normalised to -16 LUFS, limited, faded.
    Returns (mono, lufs_before, lufs_after, limiter_db)."""
    mono = to_mono(master).astype("float32")[:, None]
    before = integrated_loudness(mono, CLIP_SR)
    mono, after, reduction = normalize_loop(mono, CLIP_SR, TARGET_LUFS, PEAK_CEILING)
    nf = int(fade_ms / 1000 * CLIP_SR)
    ramp = np.linspace(0, 1, nf, dtype=mono.dtype)[:, None]
    mono[:nf] *= ramp
    mono[-nf:] *= ramp[::-1]
    assert len(mono) == n
    return mono, before, after, reduction


def write_clip(path, mono):
    """Mono 16-bit WAV with TPDF dither. Returns the sample count read back."""
    rng = np.random.default_rng(0)
    dither = (rng.random(mono.shape) - rng.random(mono.shape)) / 32768.0
    pcm = np.clip(np.round((mono + dither) * 32767.0), -32768, 32767).astype("<i2")
    sf.write(path, pcm, CLIP_SR, subtype="PCM_16")
    info = sf.info(path)
    return info.frames


def next_clip_index(asset, clips_dir):
    used = set()
    for c in asset.get("clips", []):
        mm = re.fullmatch(rf"{re.escape(asset['id'])}-(\d+)", c.get("id", ""))
        if mm:
            used.add(int(mm.group(1)))
    if os.path.isdir(clips_dir):
        for f in os.listdir(clips_dir):
            mm = re.fullmatch(rf"{re.escape(asset['id'])}-(\d+)\.\w+", f)
            if mm:
                used.add(int(mm.group(1)))
    return max(used, default=0) + 1


def load_manifest(root=ROOT):
    with open(os.path.join(root, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def save_manifest(m, path):
    """Two-space indent, one clip per line, matching the hand-written style."""
    out = ["{"]
    for k in ("version", "tempo", "key", "bars", "beats_per_bar"):
        out.append(f'  "{k}": {json.dumps(m[k], ensure_ascii=False)},')
    out.append('  "assets": [')
    for ai, a in enumerate(m["assets"]):
        out.append("    {")
        for k in ("id", "name", "color", "description"):
            out.append(f'      "{k}": {json.dumps(a[k], ensure_ascii=False)},')
        out.append('      "clips": [')
        for ci, c in enumerate(a["clips"]):
            comma = "," if ci < len(a["clips"]) - 1 else ""
            out.append(f"        {{ {json.dumps(c, ensure_ascii=False)[1:-1]} }}{comma}")
        out.append("      ]")
        out.append("    }" + ("," if ai < len(m["assets"]) - 1 else ""))
    out.append("  ]")
    out.append("}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def prepare(source, asset_id, title, *, bpm=None, key=None, start=None, bars=None, note="", credit="",
            fade=5.0, root=ROOT, manifest=None, clip_id=None, log=print):
    """Prepare one clip. Returns (entry, manifest). Writes clips/<id>.wav and the
    master in sources/prepared/, but does NOT save the manifest: the caller decides
    where the entry goes and bumps the version."""
    m = manifest if manifest is not None else load_manifest(root)
    clips_dir = os.path.join(root, "clips")
    prepared_dir = os.path.join(root, "sources", "prepared")
    if not os.path.isfile(source):
        raise PrepareError(f"source not found: {source}")
    if m.get("beats_per_bar") != 4:
        raise PrepareError(f"beats_per_bar={m.get('beats_per_bar')} is unsupported (only 4 for now)")
    asset = next((x for x in m["assets"] if x["id"] == asset_id), None)
    if asset is None:
        raise PrepareError(f"unknown asset '{asset_id}'; choose one of {[x['id'] for x in m['assets']]}")
    bars = bars or m["bars"]
    beats = bars * m["beats_per_bar"]
    lib_bpm, lib_key = float(m["tempo"]), fmt_key(m["key"])
    n_target = loop_samples(m, bars, CLIP_SR)

    # 1. load at the clip rate
    y, src_sr = load_audio(source)
    y = to_clip_sr(y, src_sr)
    sr = CLIP_SR
    mono = analysis_signal(y, sr)
    log(f"source        {source}  ({len(y)/sr:.2f} s, {y.shape[1]} ch, {src_sr} Hz{' -> 44100' if src_sr != sr else ''})")

    # 2. detect (or take flags)
    det_bpm, tracker_bpm, beat_times = detect_tempo(mono)
    det_key = detect_key(mono, beats=beat_times)
    onset_strong, _ = first_strong_onset(mono)
    src_bpm = bpm or det_bpm
    src_key = fmt_key(key) if key else det_key["key"]
    if src_key is None:
        raise PrepareError("could not detect a key; pass --key")
    if start is not None:
        start_s, start_how = start, "--start"
    else:
        near = [b for b in beat_times if abs(b - onset_strong) <= DOWNBEAT_SNAP_S]
        approx = float(min(near, key=lambda b: abs(b - onset_strong))) if near else onset_strong
        start_s = refine_onset(to_mono(y), sr, approx)
        start_how = "first strong onset" + (" on a tracked beat" if near else "") + f", attack refined from {approx:.3f} s"
    log(f"BPM           detected {det_bpm:.2f} (tracker {tracker_bpm:.2f})  ->  using {src_bpm:.2f}{'  [--bpm]' if bpm else ''}")
    log(f"key           detected {det_key['key']} (confidence {det_key['confidence']:.3f}, margin {det_key['margin']:.3f})  ->  using {src_key}{'  [--key]' if key else ''}")
    log(f"downbeat      {start_s:.3f} s  ({start_how})")

    # 3. cut N bars from the downbeat at the source tempo
    n_src = int(round(beats * 60.0 / src_bpm * sr))
    s0 = int(round(start_s * sr))
    if s0 + n_src > len(y):
        raise PrepareError(f"source too short: need {n_src/sr:.2f} s from {start_s:.3f} s, have {(len(y)-s0)/sr:.2f} s. Try --start or fewer --bars.")
    cut = y[s0:s0 + n_src]

    # 4. one rubberband pass
    rate = n_src / n_target
    shift = semitone_shift(src_key, lib_key)
    rbargs = {"--fine": ""}
    if shift:
        rbargs["--pitch"] = shift
    if abs(rate - 1.0) < 1e-9:
        out = pyrb.pitch_shift(cut, sr, shift, rbargs={"--fine": ""}) if shift else cut.copy()
    else:
        out = pyrb.time_stretch(cut, sr, rate, rbargs=rbargs)
    out = out[:, None] if out.ndim == 1 else out
    log(f"stretch       ratio {lib_bpm/src_bpm:.5f}  ({src_bpm:.2f} -> {lib_bpm:.2f} BPM)")
    log(f"pitch         {shift:+d} semitones  ({src_key} -> {lib_key}, relative-major-aware)")

    # 5. exact length, master, mono clip
    master, delta = fit_length(out, n_target, int(LENGTH_TOL_S * sr), "stretched audio")
    clip_id = clip_id or f"{asset['id']}-{next_clip_index(asset, clips_dir):02d}"
    os.makedirs(clips_dir, exist_ok=True)
    os.makedirs(prepared_dir, exist_ok=True)
    master_path = os.path.join(prepared_dir, f"{clip_id}.wav")
    sf.write(master_path, master, sr, subtype="PCM_24")
    clip, before, after, reduction = finalize(master, n_target, fade)
    pk_db, _ = peak_dbfs(clip)
    rel = f"clips/{clip_id}.wav"
    frames = write_clip(os.path.join(root, rel), clip)
    if frames != n_target:
        raise PrepareError(f"written clip has {frames} samples, expected {n_target}")
    log(f"length        {n_target} samples = {bars} bars @ {lib_bpm:.2f} BPM, {sr} Hz  (adjusted {delta:+d} samples)")
    log(f"loudness      {before:.2f} -> {after:.2f} LUFS (mono), peak {pk_db:.2f} dBFS, limiter max {reduction:.1f} dB, fade {fade:g} ms")
    log(f"export        {rel}  (WAV mono 44.1 kHz 16-bit, {frames} samples exact)")
    log(f"              {os.path.relpath(master_path, root)}  (stereo 24-bit master, git-ignored)")

    entry = {"id": clip_id, "title": title, "note": note, "file": rel,
             "source": os.path.basename(source), "credit": credit}
    if bars != m["bars"]:
        entry["bars"] = bars
    log(f"\nsummary  {clip_id}: {src_bpm:.2f} BPM {src_key} -> {lib_bpm:.0f} BPM {lib_key}, "
        f"stretch {lib_bpm/src_bpm:.4f}, shift {shift:+d} st, {after:.2f} LUFS, {rel}")
    return entry, m


def add_args(ap):
    ap.add_argument("--bpm", type=float, help="override detected source BPM")
    ap.add_argument("--key", help="override detected source key, e.g. 'F# minor'")
    ap.add_argument("--start", type=float, help="override detected downbeat (seconds into the source)")
    ap.add_argument("--bars", type=int, help="override manifest default loop length")
    ap.add_argument("--note", default="", help="one short line shown under the title in the picker")
    ap.add_argument("--credit", default="", help="performer / origin / licence")
    ap.add_argument("--fade", type=float, default=5.0, help="edge fade in ms (default 5; use ~30 for speech)")
    ap.add_argument("--root", default=ROOT, help="repo root (default: this repo)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source")
    ap.add_argument("--asset", required=True)
    ap.add_argument("--title", required=True)
    add_args(ap)
    a = ap.parse_args()
    try:
        entry, m = prepare(a.source, a.asset, a.title, bpm=a.bpm, key=a.key, start=a.start, bars=a.bars,
                           note=a.note, credit=a.credit, fade=a.fade, root=a.root)
    except PrepareError as e:
        sys.exit(f"error: {e}")
    asset = next(x for x in m["assets"] if x["id"] == a.asset)
    asset["clips"].append(entry)
    m["version"] += 1
    save_manifest(m, os.path.join(a.root, "manifest.json"))
    print(f"manifest      appended {entry['id']} to asset '{a.asset}' ({len(asset['clips'])} clip(s)), version {m['version']}")


if __name__ == "__main__":
    main()
