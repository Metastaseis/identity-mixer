#!/bin/sh
# prep.sh <slug> — separate a song's audio again for study.py / audit.py, keeping its analysis caches. done.sh <slug> removes the audio.
cd "$(dirname "$0")" || exit 1
s="$1"; [ -d "sep/$s" ] || { echo "no caches for $s: run convert.py $s first"; exit 1; }
mv "sep/$s" "sep/$s.cache" && "${DEMUCS_PYTHON:-$HOME/.venvs/demucs/bin/python}" sep.py "$s" 2>&1 | grep -v HF_TOKEN
mkdir -p "sep/$s"; mv "sep/$s.cache"/*.npz "sep/$s/" && rmdir "sep/$s.cache"; ls "sep/$s"
