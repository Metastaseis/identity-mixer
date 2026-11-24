#!/usr/bin/env python3
"""Verify manifest.json, every clip it references, and that the parts fit together. Exit 0 means green.

The library is one instrument part per clip: each asset's channel plays one instrument, and each of its
clips is that instrument's part of a song, rendered.

Checks:
  * manifest shape: version, tempo, key, bars, beats_per_bar (must be 4); exactly six assets in the
    canonical order with the canonical ids and names, each with its instrument {id, name}, the id as in
    INSTRUMENTS of pipeline/arrange/parts.py
  * every clip: its fields; id, file and part named by convention (clips/<id>.wav,
    midi/parts/<source slug>--<instrument>.mid); no stems
  * its part (.mid) and its source (.mid) exist; its WAV exists and decodes
  * loop length: samples == bars * beats_per_bar * 60 / tempo * sr, exactly. Only WAV is accepted: MP3
    cannot hold an exact sample count (encoder padding, decoder-dependent trimming), so an MP3 loop drifts
  * loudness: integrated LUFS within -16 ± 1; never touching full scale (no sample at or above 0.999)
  * nothing unreferenced: every file in clips/ is a clip's file, every file in midi/parts/ a clip's part,
    every .mid directly in midi/ a clip's source (midi/alternates/ holds alternate feels and is exempt);
    clips/stems/ and midi/stems/ must not exist
  * fit: pipeline/arrange/fit.py over midi/parts/; any combination above TOLERANT fails the check

usage: check_library.py [--root DIR]
"""
import argparse, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "arrange"))
from analyze import load_audio, integrated_loudness, peak_dbfs  # noqa: E402

CANON = [("hebrew", "עברית"), ("israel", "ישראל"), ("values", "עולם ערכים"),
         ("culture", "תרבות"), ("memory", "זכרון הסטורי"), ("lifestyle", "אורח חיים")]
CLIP_FIELDS = ["id", "title", "note", "file", "source", "part", "credit"]
ASSET_FIELDS = ["id", "name", "instrument", "color", "description", "clips"]
TARGET_LUFS, LUFS_TOL = -16.0, 1.0
CLIP_LEVEL = 0.999


def check_manifest(m, errors):
    from parts import INSTRUMENTS
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
        inst = a.get("instrument")
        want = INSTRUMENTS.get(cid, (None,))[0]
        if not isinstance(inst, dict) or not inst.get("name") or inst.get("id") != want:
            errors.append(f"asset {cid}: instrument must be {{\"id\": \"{want}\", \"name\": <Hebrew>}} (parts.py INSTRUMENTS), got {inst!r}")
        if not a.get("clips"):
            errors.append(f"asset {cid}: no clips")


def check_clip(m, a, c, root, errors):
    cid = c.get("id", "?")
    for k in CLIP_FIELDS:
        if k not in c:
            errors.append(f"clip {cid}: missing '{k}'")
    for k in ("stems", "stems_gain"):
        if k in c:
            errors.append(f"clip {cid}: '{k}' belongs to the old model; a clip is one rendered part")
    if not cid.startswith(a.get("id", "") + "-"):
        errors.append(f"clip {cid}: id must start with '{a.get('id')}-'")
    path, src, part = c.get("file", ""), c.get("source", ""), c.get("part", "")
    if path != f"clips/{cid}.wav":
        errors.append(f"clip {cid}: file must be clips/{cid}.wav (WAV only: exact loop length), got {path!r}")
    inst = (a.get("instrument") or {}).get("id")
    slug = os.path.splitext(os.path.basename(src))[0]
    if part != f"midi/parts/{slug}--{inst}.mid":
        errors.append(f"clip {cid}: part must be midi/parts/{slug}--{inst}.mid, got {part!r}")
    for what, p in (("source", src), ("part", part)):
        if not (p.endswith(".mid") and os.path.isfile(os.path.join(root, p))):
            errors.append(f"clip {cid}: {what} not found: {p}")
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
        problems.append(f"touches full scale: {clipped} sample(s) at or above {CLIP_LEVEL} FS")
    for p in problems:
        errors.append(f"clip {cid}: {p}")
    return {"path": path, "inst": inst, "sr": sr, "ch": y.shape[1], "n": n, "delta": n - exp,
            "lufs": lufs, "peak_db": pk_db, "ok": not problems}


def check_files(m, root, errors):
    """Nothing unreferenced, and nothing of the old stem model."""
    clips = [c for a in m["assets"] for c in a.get("clips", [])]
    for folder in ("clips/stems", "midi/stems"):
        if os.path.exists(os.path.join(root, folder)):
            errors.append(f"{folder}/ exists: stems belong to the old model; remove it")
    for folder, key, ext in (("clips", "file", None), ("midi/parts", "part", None), ("midi", "source", ".mid")):
        used = {c.get(key, "") for c in clips}
        full = os.path.join(root, folder)
        if not os.path.isdir(full):
            continue
        for name in sorted(os.listdir(full)):
            path = f"{folder}/{name}"
            if name.startswith(".") or not os.path.isfile(os.path.join(full, name)) or (ext and not name.lower().endswith(ext)):
                continue
            if path not in used:
                errors.append(f"unreferenced: {path} is no clip's {key} (move alternate MIDI to midi/alternates/, or register it)")


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
    W = 24
    print(f"{'clip':{W}s} {'instrument':10s} {'sr':>6s} {'ch':>2s} {'samples':>8s} {'Δ':>4s} {'LUFS':>7s} {'peak':>7s}  status")
    rows = []
    for asset in m["assets"]:
        for c in asset.get("clips", []):
            r = check_clip(m, asset, c, root, errors)
            if r:
                rows.append(r)
                print(f"{r['path']:{W}s} {r['inst']:10s} {r['sr']:6d} {r['ch']:2d} {r['n']:8d} {r['delta']:+4d} "
                      f"{r['lufs']:7.2f} {r['peak_db']:7.2f}  {'ok' if r['ok'] else 'FAIL'}")
    check_files(m, root, errors)
    try:
        import fit
        f = fit.evaluate(root)
        print(f"\nfit: {f['n']} combinations, {f['strict'] * 100:.1f}% within STRICT {fit.STRICT}, "
              f"{f['tolerant'] * 100:.1f}% within TOLERANT {fit.TOLERANT}, worst {f['worst'][0]:.3f}")
        if f["over"]:
            s, (x, y), _ = f["worst"]
            errors.append(f"fit: {f['over']} combination(s) of parts above TOLERANT {fit.TOLERANT}; worst {s:.3f} ({x} + {y}). Run pipeline/arrange/fit.py")
    except Exception as e:
        errors.append(f"fit: cannot evaluate midi/parts/: {e}")
    if errors:
        print()
        print("\n".join(errors))
        print(f"\n{len(errors)} problem(s)")
        sys.exit(1)
    print(f"\ngreen: {len(rows)} clip(s), one part each")


if __name__ == "__main__":
    main()
