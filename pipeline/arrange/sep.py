"""Separate each song into vocals / bass / other / drums with htdemucs. Writes sep/<slug>/<stem>.wav (mono 44100).
Run with the Demucs environment: ~/.venvs/demucs/bin/python sep.py <slug> [...]"""
import sys, os, random, subprocess, time
import numpy as np, torch, soundfile as sf
from demucs.pretrained import get_model
from demucs.apply import apply_model
W = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(os.path.dirname(W))
sys.path.insert(0, W); from songs import SONGS
dev = "mps" if torch.backends.mps.is_available() and os.environ.get("SEP_CPU") != "1" else "cpu"
model = get_model("htdemucs"); model.eval()
for slug in (sys.argv[1:] or SONGS):
    out = f"{W}/sep/{slug}"
    only = os.environ.get("SEP_ONLY")                # e.g. SEP_ONLY=vocals: write just that stem, even if the caches exist
    if os.path.exists(f"{out}/vocals.wav") or (not only and os.path.exists(f"{out}/f0b.npz") and os.path.exists(f"{out}/chroma2.npz")): continue
    os.makedirs(out, exist_ok=True); t0 = time.time()
    torch.manual_seed(0); random.seed(0)          # same split every run
    tmp = f"{out}/full44.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(R, SONGS[slug][1]), "-ar", "44100", "-ac", "2", tmp], check=True)
    y, sr = sf.read(tmp, always_2d=True, dtype="float32")
    x = torch.from_numpy(y.T.copy())[None]
    ref = x.mean(1); x = (x - ref.mean()) / (ref.std() + 1e-8)
    with torch.no_grad():
        try: s = apply_model(model, x, device=dev, split=True, overlap=0.25, progress=False)[0]
        except Exception as e:
            print("fallback to cpu:", str(e)[:120], flush=True); s = apply_model(model, x, device="cpu", split=True, overlap=0.25, progress=False)[0]
    s = s * ref.std() + ref.mean()
    for name, stem in zip(model.sources, s):
        if only and name != only: continue
        m = stem.mean(0).cpu().numpy()
        sf.write(f"{out}/{name}.wav", m, sr, subtype="PCM_16")
    os.remove(tmp)
    print(f"{slug}: {len(y)/sr:.0f}s separated in {time.time()-t0:.0f}s on {dev}", flush=True)
