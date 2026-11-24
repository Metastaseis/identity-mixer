"""Put each song's MIDI arrangement into the library: add it as a clip (or replace the clip it already has),
render one stem per MIDI track, and register the stems in the manifest. Each call bumps the manifest version."""
import sys, os, json, shutil, subprocess
import numpy as np, soundfile as sf, pyloudnorm as pyln
W = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(os.path.dirname(W))
sys.path.insert(0, W); sys.path.insert(0, f"{R}/pipeline")
from songs import SONGS
from prepare_clip import load_manifest, save_manifest
from render_midi import split_stems, manifest_defaults
STEM_NAME = {"melody": "מנגינה", "bass": "בס", "guitar": "גיטרה", "pad": "הרמוניה", "oud": "עוד"}
NOTE = "מעובד מ-MIDI, 8 תיבות ב-100 BPM, רה מינור"
LEAD_DB = {"melody": 2.0}; BACK_DB = -4.0        # the melody stem leads the others by 6 dB

def find_clip(m, slug):
    src = os.path.basename(SONGS[slug][1])
    for a in m["assets"]:
        for c in a["clips"]:
            if c["source"] in (src, f"midi/{slug}.mid"): return c["id"]
    return None

for slug in (sys.argv[1:] or SONGS):
    midi = f"midi/{slug}.mid"
    if not os.path.exists(f"{R}/{midi}"): print("skip (no midi):", slug); continue
    cid = find_clip(load_manifest(R), slug)
    how = ["replace", cid] if cid else ["add", "--asset", SONGS[slug][0], "--title", SONGS[slug][2]]
    r = subprocess.run([f"{R}/.venv/bin/python", f"{R}/pipeline/library.py", *how, "--midi", midi, "--note", NOTE, "--credit", "עיבוד MIDI"], capture_output=True, text=True, cwd=R)
    if r.returncode: raise SystemExit(f"{slug}: {r.stderr[-400:]} {r.stdout[-400:]}")
    cid = cid or find_clip(load_manifest(R), slug)
    bpm, bars, bpb = manifest_defaults(R)
    done = split_stems(f"{R}/{midi}", f"{R}/clips/stems", bpm, bars, bpb, log=lambda *_: None)
    os.makedirs(f"{R}/midi/stems", exist_ok=True)
    stems = []; total = None
    for stem, mid_path, wav_path in done:
        shutil.move(mid_path, f"{R}/midi/stems/{os.path.basename(mid_path)}")
        y, sr = sf.read(wav_path, dtype="float64")
        y = y * 10 ** (LEAD_DB.get(stem, BACK_DB) / 20); pk = float(np.abs(y).max())
        if pk > 0.95: y *= 0.95 / pk
        sf.write(wav_path, y, sr, subtype="PCM_16"); total = y if total is None else total + y
        stems.append({"id": stem, "name": STEM_NAME.get(stem, stem), "file": f"clips/stems/{os.path.basename(wav_path)}", "midi": f"midi/stems/{os.path.basename(mid_path)}"})
    lufs = pyln.Meter(sr).integrated_loudness(total); gain = 10 ** ((-16.0 - lufs) / 20)
    pk = float(np.abs(total).max()) * gain
    if pk > 0.98: gain *= 0.98 / pk
    m = load_manifest(R)
    for a in m["assets"]:
        for c in a["clips"]:
            if c["id"] == cid:
                c["stems_gain"] = round(float(gain), 3); c["stems"] = sorted(stems, key=lambda s: s["id"])
    save_manifest(m, f"{R}/manifest.json")
    print(f"{slug}: {cid} <- {midi}, {len(stems)} stems, stems_gain {gain:.3f} (sum {lufs:.1f} LUFS, peak after gain {min(pk, 0.98):.2f})", flush=True)
