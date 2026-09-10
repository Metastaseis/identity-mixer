# Identity Mixer

Phone web app for מכינה workshops — six assets of Jewish identity as a six-channel mixer.

## Run locally and test on a phone

The app is static files, no build step. Serve the repo root and open it on a phone
on the same Wi-Fi network. The server must bind IPv4 explicitly, or the phone
cannot reach it:

```sh
python3 -m http.server 8000 --bind 0.0.0.0
```

Open on the phone the address of the Mac's `en0` interface:

```sh
echo "http://$(ipconfig getifaddr en0):8000"
```

On iOS Safari, audio only starts after a tap on the play button. If nothing plays,
make sure the phone is not on silent mode (the side switch) and the volume is up.

## Layout

See `ARCHITECTURE.md` for the full design and `CLAUDE.md` for project rules.

```
index.html      mixer UI
app.js          manifest loading, Web Audio scheduling, faders, persistence
profile.js      SVG radar profile (shared later with the facilitator page)
styles.css      RTL, phone-first layout
manifest.json   shared tempo / key / bars + six assets + their clips
clips/          prepared loops (exact whole-bar loops at the shared tempo)
                Phase 1: six synthesized placeholder WAVs, 4 bars at 100 BPM, A minor
pipeline/       Python tools that prepare clips (Phase 2)
```

## Adding a clip (Phase 2)

```sh
brew install ffmpeg rubberband
python -m venv .venv && source .venv/bin/activate
pip install -r pipeline/requirements.txt
python pipeline/prepare_clip.py sources/<file> --asset <id> --title "<title>"
python pipeline/check_library.py
```
