# Pipeline

Tools that turn a recording into a library clip. Everything that makes clips play in
sync and in key happens here, never in the app.

## Install (once)

```sh
brew install ffmpeg rubberband
python3 -m venv .venv && source .venv/bin/activate
pip install -r pipeline/requirements.txt
```

## Tools

| Script             | Purpose                                                                 |
|--------------------|-------------------------------------------------------------------------|
| `analyze.py`       | BPM, key + confidence, LUFS, duration, first strong onset. `--json` too |
| `prepare_clip.py`  | Source → exact-loop clip at the manifest tempo/key/loudness + manifest entry |
| `check_library.py` | Verify every clip: length, loudness, clipping, manifest shape. Exit 0 = green |

## Example

```sh
source .venv/bin/activate
python pipeline/analyze.py "sources/ריקוד חסידי.mp3"
python pipeline/prepare_clip.py "sources/ריקוד חסידי.mp3" --asset culture --title "ריקוד חסידי" \
    --credit "הקלטה ביתית" --bars 8
python pipeline/check_library.py
```

`prepare_clip.py` writes `clips/<asset>-NN.mp3` (committed) and a lossless copy in
`sources/prepared/<asset>-NN.wav` (git-ignored). Override detection with `--bpm`,
`--key` and `--start` when the analysis is wrong; `--bars` overrides the manifest default.
Only 4 beats per bar is supported.
