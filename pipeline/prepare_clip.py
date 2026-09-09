#!/usr/bin/env python3
"""Turn a source recording into a library clip: an exact whole-bar loop at the
manifest tempo, in the manifest key, at -16 LUFS. Appends the clip to manifest.json.

usage: prepare_clip.py <source> --asset <id> --title <t>
                       [--bpm N] [--key K] [--start seconds] [--bars N]
                       [--note TEXT] [--credit TEXT] [--root DIR]

Steps: load -> detect BPM / key / downbeat (or use flags) -> cut N bars from the
downbeat at the source tempo -> time-stretch to the manifest tempo and pitch-shift
to the manifest key (relative-major-aware, smallest signed shift in -6..+5, one
rubberband pass) -> normalise to -16 LUFS with 5 ms fades and verify the exact loop
length -> export MP3 192k to clips/<asset>-NN.mp3 and a lossless WAV to
sources/prepared/ (MP3 via ffmpeg/libmp3lame) -> append to manifest.json -> print a summary.
"""
import argparse, json, os, re, subprocess, sys, warnings

import numpy as np
import soundfile as sf
import pyrubberband as pyrb
import pyloudnorm as pyln

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import (load_audio, analysis_signal, to_mono, detect_tempo, detect_key, first_strong_onset, refine_onset,  # noqa: E402
                     integrated_loudness, peak_dbfs, normalize_loop, parse_key, format_key, semitone_shift)

warnings.filterwarnings("ignore")

TARGET_LUFS = -16.0
FADE_S = 0.005
LENGTH_TOL_S = 0.010        # rubberband may land a few samples off; trim/pad up to this
PEAK_CEILING = 0.99         # limiter ceiling; check_library flags anything at or above 0.999
MP3_TOL_S = 0.026
DOWNBEAT_SNAP_S = 0.15      # snap the first strong onset to the nearest tracked beat if this close


def die(msg):
    sys.exit(f"error: {msg}")


def fmt_key(k):
    return format_key(*parse_key(k))


def next_clip_index(asset, clips_dir):
    used = set()
    for c in asset.get("clips", []):
        m = re.fullmatch(rf"{re.escape(asset['id'])}-(\d+)", c.get("id", ""))
        if m:
            used.add(int(m.group(1)))
    if os.path.isdir(clips_dir):
        for f in os.listdir(clips_dir):
            m = re.fullmatch(rf"{re.escape(asset['id'])}-(\d+)\.\w+", f)
            if m:
                used.add(int(m.group(1)))
    return max(used, default=0) + 1


def save_manifest(m, path):
    """Two-space indent, one clip per line, matching the hand-written style."""
    out = ["{"]
    for k in ("tempo", "key", "bars", "beats_per_bar"):
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source")
    ap.add_argument("--asset", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--bpm", type=float, help="override detected source BPM")
    ap.add_argument("--key", help="override detected source key, e.g. 'F# minor'")
    ap.add_argument("--start", type=float, help="override detected downbeat (seconds into the source)")
    ap.add_argument("--bars", type=int, help="override manifest default loop length")
    ap.add_argument("--note", default="", help="one short line shown under the title in the picker")
    ap.add_argument("--credit", default="", help="performer / origin / licence")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="repo root (default: this repo)")
    a = ap.parse_args()

    root = a.root
    manifest_path = os.path.join(root, "manifest.json")
    clips_dir = os.path.join(root, "clips")
    prepared_dir = os.path.join(root, "sources", "prepared")
    if not os.path.isfile(a.source):
        die(f"source not found: {a.source}")
    with open(manifest_path, encoding="utf-8") as f:
        m = json.load(f)
    if m.get("beats_per_bar") != 4:
        die(f"beats_per_bar={m.get('beats_per_bar')} is unsupported (only 4 for now)")
    asset = next((x for x in m["assets"] if x["id"] == a.asset), None)
    if asset is None:
        die(f"unknown asset '{a.asset}'; choose one of {[x['id'] for x in m['assets']]}")
    bars = a.bars or m["bars"]
    beats = bars * m["beats_per_bar"]
    lib_bpm, lib_key = float(m["tempo"]), fmt_key(m["key"])

    # 1. load
    y, sr = load_audio(a.source)                    # (n, ch), native rate
    mono = analysis_signal(y, sr)
    print(f"source        {a.source}  ({len(y)/sr:.2f} s, {y.shape[1]} ch, {sr} Hz)")

    # 2. detect (or take flags)
    det_bpm, tracker_bpm, beat_times = detect_tempo(mono)
    det_key = detect_key(mono, beats=beat_times)
    onset_strong, _ = first_strong_onset(mono)
    src_bpm = a.bpm or det_bpm
    src_key = fmt_key(a.key) if a.key else det_key["key"]
    if src_key is None:
        die("could not detect a key; pass --key")
    if a.start is not None:
        start_s, start_how = a.start, "--start"
    else:
        near = [b for b in beat_times if abs(b - onset_strong) <= DOWNBEAT_SNAP_S]
        approx = float(min(near, key=lambda b: abs(b - onset_strong))) if near else onset_strong
        start_s = refine_onset(to_mono(y), sr, approx)
        start_how = "first strong onset" + (" on a tracked beat" if near else "") + f", attack refined from {approx:.3f} s"
    print(f"BPM           detected {det_bpm:.2f} (tracker {tracker_bpm:.2f})  ->  using {src_bpm:.2f}{'  [--bpm]' if a.bpm else ''}")
    print(f"key           detected {det_key['key']} (confidence {det_key['confidence']:.3f}, margin {det_key['margin']:.3f})  ->  using {src_key}{'  [--key]' if a.key else ''}")
    print(f"downbeat      {start_s:.3f} s  ({start_how})")

    # 3. cut N bars from the downbeat at the source tempo
    n_src = int(round(beats * 60.0 / src_bpm * sr))
    s0 = int(round(start_s * sr))
    if s0 + n_src > len(y):
        die(f"source too short: need {n_src/sr:.2f} s from {start_s:.3f} s, have {(len(y)-s0)/sr:.2f} s. Try --start or fewer --bars.")
    cut = y[s0:s0 + n_src]

    # 4. one rubberband pass: stretch to the library tempo, shift to the library key
    n_target = int(round(beats * 60.0 / lib_bpm * sr))
    rate = n_src / n_target                          # >1 speeds up; equals lib_bpm / src_bpm
    shift = semitone_shift(src_key, lib_key)
    rbargs = {"--fine": ""}                          # R3 engine, best quality
    if shift:
        rbargs["--pitch"] = shift
    if abs(rate - 1.0) < 1e-9:
        out = pyrb.pitch_shift(cut, sr, shift, rbargs={"--fine": ""}) if shift else cut.copy()
    else:
        out = pyrb.time_stretch(cut, sr, rate, rbargs=rbargs)
    out = np.atleast_2d(out.T).T if out.ndim == 1 else out
    print(f"stretch       ratio {lib_bpm/src_bpm:.5f}  ({src_bpm:.2f} -> {lib_bpm:.2f} BPM)")
    print(f"pitch         {shift:+d} semitones  ({src_key} -> {lib_key}, relative-major-aware)")

    # 5. exact length, loudness, fades
    delta = len(out) - n_target
    if abs(delta) > int(LENGTH_TOL_S * sr):
        die(f"stretched length off by {delta} samples ({delta/sr*1000:.1f} ms), more than {LENGTH_TOL_S*1000:.0f} ms")
    out = out[:n_target] if delta > 0 else np.vstack([out, np.zeros((-delta, out.shape[1]), out.dtype)])
    lufs_before = integrated_loudness(out, sr)
    out, lufs_final, reduction = normalize_loop(out, sr, TARGET_LUFS, PEAK_CEILING)
    nf = int(FADE_S * sr)
    ramp = np.linspace(0, 1, nf, dtype=out.dtype)[:, None]
    out[:nf] *= ramp
    out[-nf:] *= ramp[::-1]
    lufs_final = integrated_loudness(out, sr)
    pk_db, _ = peak_dbfs(out)
    assert len(out) == n_target, "loop length mismatch after processing"
    print(f"length        {n_target} samples = {bars} bars @ {lib_bpm:.2f} BPM, {sr} Hz  (adjusted {delta:+d} samples)")
    print(f"loudness      {lufs_before:.2f} -> {lufs_final:.2f} LUFS, peak {pk_db:.2f} dBFS, limiter max {reduction:.1f} dB")

    # 6. export
    idx = next_clip_index(asset, clips_dir)
    clip_id = f"{asset['id']}-{idx:02d}"
    os.makedirs(clips_dir, exist_ok=True)
    os.makedirs(prepared_dir, exist_ok=True)
    wav_path = os.path.join(prepared_dir, f"{clip_id}.wav")
    mp3_rel = f"clips/{clip_id}.mp3"
    mp3_path = os.path.join(root, mp3_rel)
    sf.write(wav_path, out, sr, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
                    "-codec:a", "libmp3lame", "-b:a", "192k", mp3_path], check=True)
    back, back_sr = load_audio(mp3_path)
    mp3_delta = len(back) - n_target
    if abs(mp3_delta) > int(MP3_TOL_S * sr):
        die(f"exported MP3 decodes to {len(back)} samples, expected {n_target} (Δ {mp3_delta:+d})")
    print(f"export        {mp3_rel}  (MP3 192k, decodes to {len(back)} samples, Δ {mp3_delta:+d} within one frame)")
    print(f"              {os.path.relpath(wav_path, root)}  (lossless, git-ignored)")

    # 7. manifest
    entry = {"id": clip_id, "title": a.title, "note": a.note, "file": mp3_rel,
             "source": os.path.basename(a.source), "credit": a.credit}
    if bars != m["bars"]:
        entry["bars"] = bars
    asset["clips"].append(entry)
    save_manifest(m, manifest_path)
    print(f"manifest      appended {clip_id} to asset '{asset['id']}' ({len(asset['clips'])} clip(s))")

    # 8. summary line
    print(f"\nsummary  {clip_id}: {src_bpm:.2f} BPM {src_key} -> {lib_bpm:.0f} BPM {lib_key}, "
          f"stretch {lib_bpm/src_bpm:.4f}, shift {shift:+d} st, {lufs_final:.2f} LUFS, {mp3_rel}")


if __name__ == "__main__":
    main()
