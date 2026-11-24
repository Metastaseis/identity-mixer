#!/bin/sh
# done.sh <slug> — remove the separated audio and the working copy of a song (the small caches stay).
cd "$(dirname "$0")" || exit 1
rm -f "sep/$1"/*.wav "wav/$1.wav"; ls "sep/$1"
