#!/usr/bin/env python3
"""Verify manifest.json and every clip it references. Exit 0 means green.

Checks:
  * manifest shape: version, tempo, key, bars, beats_per_bar (must be 4), exactly six
    assets in the canonical order with the canonical ids and names
  * every clip: required fields, id matches filename, file is WAV, exists, decodes
  * loop length: samples == bars * beats_per_bar * 60 / tempo * sr, exactly.
    Only WAV is accepted: MP3 cannot hold an exact sample count (encoder padding,
    decoder-dependent trimming), so an MP3 loop drifts against the others.
  * loudness: integrated LUFS within -16 ± 1
  * clipping: any sample at or above 0.999 full scale
  * stems (optional per clip): fields, unique ids, WAV exists and has exactly the
    clip's loop length, the .mid exists, and the stems summed at the clip's
    stems_gain sit within -16 ± 1 LUFS without touching full scale (the player
    plays the stems at that gain instead of the full file)

usage: check_library.py [--root DIR]
"""
import argparse, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import load_audio, integrated_loudness, peak_dbfs  # noqa: E402

CANON = [("hebrew", "השפה העברית"), ("israel", "ישראל"), ("values", "עולם ערכים"),
         ("culture", "תרבות"), ("memory", "זיכרון היסטורי"), ("lifestyle", "אורח חיים")]
CLIP_FIELDS = ["id", "title", "note", "file", "source", "credit"]
STEM_FIELDS = ["id", "name", "file", "midi"]
ASSET_FIELDS = ["id", "name", "color", "description", "clips"]
TARGET_LUFS, LUFS_TOL = -16.0, 1.0
CLIP_LEVEL = 0.999


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


def check_clip(m, a, c, root, errors):
    cid, path = c.get("id", "?"), c.get("file", "")
    for k in CLIP_FIELDS:
        if k not in c:
            errors.append(f"clip {cid}: missing '{k}'")
    if not cid.startswith(a.get("id", "") + "-"):
        errors.append(f"clip {cid}: id must start with '{a.get('id')}-'")
    if os.path.splitext(os.path.basename(path))[0] != cid:
        errors.append(f"clip {cid}: file '{path}' does not match id")
    if os.path.splitext(path)[1].lower() != ".wav":
        errors.append(f"clip {cid}: only WAV clips are allowed (exact loop length); got {path}")
        return None
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
    bars = c.get("bars", m["bars"])
    exact = bars * m["beats_per_bar"] * 60.0 / m["tempo"] * sr
    exp = int(round(exact))
    problems = []
    if abs(exact - exp) > 1e-6:
        problems.append(f"{bars} bars at {m['tempo']} BPM is not a whole number of samples at {sr} Hz")
    elif n != exp:
        problems.append(f"length {n} samples, expected exactly {exp} ({bars} bars @ {m['tempo']} BPM, {sr} Hz), Δ {n-exp:+d}")
    lufs = integrated_loudness(y, sr)
    if np.isnan(lufs) or abs(lufs - TARGET_LUFS) > LUFS_TOL:
        problems.append(f"loudness {lufs:.2f} LUFS outside {TARGET_LUFS} ± {LUFS_TOL}")
    pk_db, _ = peak_dbfs(y)
    clipped = int(np.sum(np.abs(y) >= CLIP_LEVEL))
    if clipped:
        problems.append(f"clipping: {clipped} sample(s) at or above {CLIP_LEVEL} FS")
    for p in problems:
        errors.append(f"clip {cid}: {p}")
    return {"path": path, "sr": sr, "ch": y.shape[1], "n": n, "exp": exp, "delta": n - exp,
            "lufs": lufs, "peak_db": pk_db, "ok": not problems}


def check_stems(m, c, root, errors):
    """Rows for each stem of clip c plus one for their trimmed sum; [] if the clip has no stems."""
    cid = c.get("id", "?")
    stems = c.get("stems")
    if stems is None:
        return []
    if not isinstance(stems, list) or not stems:
        errors.append(f"clip {cid}: 'stems' must be a non-empty list")
        return []
    gain = c.get("stems_gain")
    if not isinstance(gain, (int, float)) or gain <= 0:
        errors.append(f"clip {cid}: stems need a positive 'stems_gain' (the trim that brings their sum to {TARGET_LUFS} LUFS)")
        gain = 1.0
    bars = c.get("bars", m["bars"])
    rows, total, total_sr, ids = [], None, None, set()
    for s in stems:
        sid = s.get("id", "?")
        for k in STEM_FIELDS:
            if k not in s:
                errors.append(f"clip {cid} stem {sid}: missing '{k}'")
        if sid in ids:
            errors.append(f"clip {cid}: duplicate stem id '{sid}'")
        ids.add(sid)
        midi = s.get("midi", "")
        if midi and not os.path.isfile(os.path.join(root, midi)):
            errors.append(f"clip {cid} stem {sid}: midi not found: {midi}")
        path = s.get("file", "")
        if os.path.splitext(path)[1].lower() != ".wav":
            errors.append(f"clip {cid} stem {sid}: only WAV stems are allowed; got {path}")
            continue
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            errors.append(f"clip {cid} stem {sid}: file not found: {path}")
            continue
        try:
            y, sr = load_audio(full)
        except Exception as e:
            errors.append(f"clip {cid} stem {sid}: cannot decode {path}: {e}")
            continue
        n, exp = len(y), int(round(bars * m["beats_per_bar"] * 60.0 / m["tempo"] * sr))
        problems = []
        if n != exp:
            problems.append(f"length {n} samples, expected exactly {exp} ({bars} bars @ {m['tempo']} BPM, {sr} Hz), Δ {n-exp:+d}")
        if total_sr not in (None, sr):
            problems.append(f"sample rate {sr} differs from the other stems ({total_sr})")
        for p in problems:
            errors.append(f"clip {cid} stem {sid}: {p}")
        pk_db, _ = peak_dbfs(y)
        rows.append({"path": path, "sr": sr, "ch": y.shape[1], "n": n, "exp": exp, "delta": n - exp,
                     "lufs": integrated_loudness(y, sr), "peak_db": pk_db, "ok": not problems})
        if not problems:
            mono = y.mean(axis=1, keepdims=True) if y.shape[1] > 1 else y
            total = mono if total is None else total + mono
            total_sr = sr
    if total is not None and len(rows) == len(stems):
        mix = total * gain
        lufs = integrated_loudness(mix, total_sr)
        pk_db, _ = peak_dbfs(mix)
        problems = []
        if np.isnan(lufs) or abs(lufs - TARGET_LUFS) > LUFS_TOL:
            problems.append(f"stems summed at stems_gain {gain:g} are {lufs:.2f} LUFS, outside {TARGET_LUFS} ± {LUFS_TOL}")
        clipped = int(np.sum(np.abs(mix) >= CLIP_LEVEL))
        if clipped:
            problems.append(f"stems summed at stems_gain {gain:g} clip: {clipped} sample(s) at or above {CLIP_LEVEL} FS")
        for p in problems:
            errors.append(f"clip {cid}: {p}")
        rows.append({"path": f"  = {len(stems)} stems x {gain:g}", "sr": total_sr, "ch": 1, "n": len(mix), "exp": len(mix),
                     "delta": 0, "lufs": lufs, "peak_db": pk_db, "ok": not problems})
    return rows


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

    print(f"library v{m['version']}: tempo {m['tempo']} BPM, key {m['key']}, {m['bars']} bars, {m['beats_per_bar']}/4")
    W = 50
    print(f"{'clip / stem':{W}s} {'sr':>6s} {'ch':>2s} {'samples':>8s} {'Δ':>4s} {'LUFS':>7s} {'peak':>7s}  status")
    rows, stem_rows = [], 0
    for asset in m["assets"]:
        for c in asset.get("clips", []):
            r = check_clip(m, asset, c, root, errors)
            if r:
                rows.append(r)
                print(f"{r['path']:{W}s} {r['sr']:6d} {r['ch']:2d} {r['n']:8d} {r['delta']:+4d} "
                      f"{r['lufs']:7.2f} {r['peak_db']:7.2f}  {'ok' if r['ok'] else 'FAIL'}")
            for s in check_stems(m, c, root, errors):
                stem_rows += not s["path"].startswith("  =")
                print(f"  {s['path']:{W-2}s} {s['sr']:6d} {s['ch']:2d} {s['n']:8d} {s['delta']:+4d} "
                      f"{s['lufs']:7.2f} {s['peak_db']:7.2f}  {'ok' if s['ok'] else 'FAIL'}")
    if errors:
        print()
        print("\n".join(errors))
        print(f"\n{len(errors)} problem(s)")
        sys.exit(1)
    print(f"\ngreen: {len(rows)} clip(s), {stem_rows} stem(s)")


if __name__ == "__main__":
    main()
