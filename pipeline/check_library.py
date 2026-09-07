#!/usr/bin/env python3
"""Verify manifest.json and every clip it references.

Phase 1 checks (standard library only):
  * manifest shape: tempo, key, bars, beats_per_bar (must be 4), exactly six assets
    in the canonical order with the canonical ids and names
  * every clip: required fields, id matches filename, file exists
  * every WAV clip: sample count equals bars * beats_per_bar * 60 / tempo * sr exactly
Phase 2 adds loudness, key and MP3 checks. Exit code 0 means green.
"""
import json, os, sys, wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANON = [("hebrew", "השפה העברית"), ("israel", "ישראל"), ("values", "עולם ערכים"),
         ("culture", "תרבות"), ("memory", "זיכרון היסטורי"), ("lifestyle", "אורח חיים")]
CLIP_FIELDS = ["id", "title", "note", "file", "source", "credit"]
ASSET_FIELDS = ["id", "name", "color", "description", "clips"]

errors = []
def err(msg): errors.append(msg)

with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as f:
    m = json.load(f)

for k in ("tempo", "key", "bars", "beats_per_bar", "assets"):
    if k not in m: err(f"manifest: missing top-level '{k}'")
if errors:
    print("\n".join(errors)); sys.exit(1)
if m["beats_per_bar"] != 4:
    err(f"manifest: beats_per_bar={m['beats_per_bar']} is unsupported (only 4 for now)")

assets = m["assets"]
if len(assets) != 6: err(f"manifest: expected 6 assets, found {len(assets)}")
for i, (cid, cname) in enumerate(CANON):
    if i >= len(assets): break
    a = assets[i]
    for k in ASSET_FIELDS:
        if k not in a: err(f"asset #{i+1}: missing '{k}'")
    if a.get("id") != cid: err(f"asset #{i+1}: id '{a.get('id')}' should be '{cid}'")
    if a.get("name") != cname: err(f"asset #{i+1}: name '{a.get('name')}' should be '{cname}'")
    if not a.get("clips"): err(f"asset {cid}: no clips")

checked = 0
for a in assets:
    for c in a.get("clips", []):
        for k in CLIP_FIELDS:
            if k not in c: err(f"clip {c.get('id','?')}: missing '{k}'")
        cid, path = c.get("id", ""), c.get("file", "")
        if not cid.startswith(a.get("id", "") + "-"): err(f"clip {cid}: id must start with '{a.get('id')}-'")
        if os.path.splitext(os.path.basename(path))[0] != cid: err(f"clip {cid}: file '{path}' does not match id")
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full): err(f"clip {cid}: file not found: {path}"); continue
        bars = c.get("bars", m["bars"])
        if path.lower().endswith(".wav"):
            with wave.open(full) as w:
                sr, n = w.getframerate(), w.getnframes()
            expected = bars * m["beats_per_bar"] * 60 / m["tempo"] * sr
            if abs(expected - round(expected)) > 1e-9:
                err(f"clip {cid}: {bars} bars at {m['tempo']} BPM is not a whole number of samples at {sr} Hz")
            elif n != round(expected):
                err(f"clip {cid}: {n} samples, expected {round(expected)} ({bars} bars at {m['tempo']} BPM, {sr} Hz)")
            else:
                checked += 1
                print(f"ok  {path}  {n} samples = {bars} bars @ {m['tempo']} BPM, {sr} Hz")
        else:
            err(f"clip {cid}: only WAV can be verified until the Phase 2 pipeline lands ({path})")

if errors:
    print("\n".join(errors)); print(f"\n{len(errors)} problem(s)"); sys.exit(1)
print(f"\ngreen: {checked} clip(s), tempo {m['tempo']}, key {m['key']}, {m['bars']} bars, {m['beats_per_bar']}/4")
