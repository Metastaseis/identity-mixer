#!/usr/bin/env python3
"""Verify manifest.json and every clip it references. Exit 0 means green.

Checks:
  * manifest shape: version, tempo, key, bars, beats_per_bar (must be 4), exactly six assets
    in the canonical order with the canonical ids and names
  * every clip: required fields, id matches filename, file exists and decodes
  * loop length: samples == round(bars * beats_per_bar * 60 / tempo * sr)
      WAV/FLAC: exact.  MP3: within one MP3 frame (~26 ms), because MP3 encoders
      pad the stream and decoders differ in how much of that padding they strip.
  * loudness: integrated LUFS within -16 ± 1
  * clipping: any sample at or above 0.999 full scale

usage: check_library.py [--root DIR]
"""
import argparse, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import load_audio, integrated_loudness, peak_dbfs  # noqa: E402

CANON = [("hebrew", "השפה העברית"), ("israel", "ישראל"), ("values", "עולם ערכים"),
         ("culture", "תרבות"), ("memory", "זיכרון היסטורי"), ("lifestyle", "אורח חיים")]
CLIP_FIELDS = ["id", "title", "note", "file", "source", "credit"]
ASSET_FIELDS = ["id", "name", "color", "description", "clips"]
TARGET_LUFS, LUFS_TOL = -16.0, 1.0
MP3_TOL_S = 0.026
CLIP_LEVEL = 0.999

LOSSY = {".mp3", ".m4a", ".aac", ".ogg", ".opus"}


def check_manifest(m, errors):
    for k in ("version", "tempo", "key", "bars", "beats_per_bar", "assets"):
        if k not in m:
            errors.append(f"manifest: missing top-level '{k}'")
    if errors:
        return
    if not isinstance(m["version"], int) or m["version"] < 1:
        errors.append(f"manifest: version must be a positive integer, got {m['version']!r}")
    if m["beats_per_bar"] != 4:
        errors.append(f"manifest: beats_per_bar={m['beats_per_bar']} is unsupported (only 4 for now)")
    assets = m["assets"]
    if len(assets) != 6:
        errors.append(f"manifest: expected 6 assets, found {len(assets)}")
    for i, (cid, cname) in enumerate(CANON):
        if i >= len(assets):
            break
        a = assets[i]
        for k in ASSET_FIELDS:
            if k not in a:
                errors.append(f"asset #{i+1}: missing '{k}'")
        if a.get("id") != cid:
            errors.append(f"asset #{i+1}: id '{a.get('id')}' should be '{cid}'")
        if a.get("name") != cname:
            errors.append(f"asset #{i+1}: name '{a.get('name')}' should be '{cname}'")
        if not a.get("clips"):
            errors.append(f"asset {cid}: no clips")


def expected_samples(m, bars, sr):
    x = bars * m["beats_per_bar"] * 60.0 / m["tempo"] * sr
    return int(round(x)), x


def check_clip(m, a, c, root, errors):
    cid, path = c.get("id", "?"), c.get("file", "")
    for k in CLIP_FIELDS:
        if k not in c:
            errors.append(f"clip {cid}: missing '{k}'")
    if not cid.startswith(a.get("id", "") + "-"):
        errors.append(f"clip {cid}: id must start with '{a.get('id')}-'")
    if os.path.splitext(os.path.basename(path))[0] != cid:
        errors.append(f"clip {cid}: file '{path}' does not match id")
    full = os.path.join(root, path)
    if not os.path.isfile(full):
        errors.append(f"clip {cid}: file not found: {path}")
        return None
    try:
        y, sr = load_audio(full)
    except Exception as e:
        errors.append(f"clip {cid}: cannot decode {path}: {e}")
        return None
    n = len(y)
    ext = os.path.splitext(path)[1].lower()
    bars = c.get("bars", m["bars"])
    exp, exact = expected_samples(m, bars, sr)
    tol = int(round(MP3_TOL_S * sr)) if ext in LOSSY else 0
    delta = n - exp
    problems = []
    if abs(delta) > tol:
        problems.append(f"length {n} samples, expected {exp} ({bars} bars @ {m['tempo']} BPM, {sr} Hz), Δ {delta:+d} > tol {tol}")
    lufs = integrated_loudness(y, sr)
    if np.isnan(lufs) or abs(lufs - TARGET_LUFS) > LUFS_TOL:
        problems.append(f"loudness {lufs:.2f} LUFS outside {TARGET_LUFS} ± {LUFS_TOL}")
    pk_db, pk = peak_dbfs(y)
    clipped = int(np.sum(np.abs(y) >= CLIP_LEVEL))
    if clipped:
        problems.append(f"clipping: {clipped} sample(s) at or above {CLIP_LEVEL} FS")
    for p in problems:
        errors.append(f"clip {cid}: {p}")
    return {"path": path, "ext": ext, "sr": sr, "ch": y.shape[1], "n": n, "exp": exp, "delta": delta,
            "tol": tol, "lufs": lufs, "peak_db": pk_db, "clipped": clipped, "ok": not problems,
            "sub_sample": exact - exp}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="repo root holding manifest.json and clips/ (default: this repo)")
    a = ap.parse_args()
    root = a.root
    errors = []
    with open(os.path.join(root, "manifest.json"), encoding="utf-8") as f:
        m = json.load(f)
    check_manifest(m, errors)
    if errors:
        print("\n".join(errors)); sys.exit(1)

    print(f"library: tempo {m['tempo']} BPM, key {m['key']}, {m['bars']} bars, {m['beats_per_bar']}/4")
    print(f"{'clip':22s} {'fmt':4s} {'sr':>6s} {'ch':>2s} {'samples':>8s} {'Δ':>6s} {'tol':>4s} {'LUFS':>7s} {'peak':>7s}  status")
    rows = []
    for asset in m["assets"]:
        for c in asset.get("clips", []):
            r = check_clip(m, asset, c, root, errors)
            if r:
                rows.append(r)
                status = "ok" if r["ok"] else "FAIL"
                note = " (mp3: ±1 frame tolerance)" if r["ext"] in LOSSY and r["ok"] else ""
                print(f"{r['path']:22s} {r['ext'][1:]:4s} {r['sr']:6d} {r['ch']:2d} {r['n']:8d} {r['delta']:+6d} {r['tol']:4d} "
                      f"{r['lufs']:7.2f} {r['peak_db']:7.2f}  {status}{note}")
    if errors:
        print()
        print("\n".join(errors))
        print(f"\n{len(errors)} problem(s)")
        sys.exit(1)
    print(f"\ngreen: {len(rows)} clip(s)")


if __name__ == "__main__":
    main()
