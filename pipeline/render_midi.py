#!/usr/bin/env python3
"""render_midi.py — render a .mid into an exact whole-bar loop at the library tempo.

usage: render_midi.py <midi> <out.wav> [--bpm N] [--bars N] [--beats-per-bar N]
                      [--transpose ST] [--lufs L] [--root DIR]

Tempo, bars and beats per bar default to manifest.json in the repo root
(--root, default: this repo). The flags override them. The MIDI is expected to
be written in the library key already; --transpose shifts every pitched note
by whole semitones if it is not.

Track names (or GM programs) pick a voice: melody/lead/clarinet -> lead,
bass/tuba -> pluck, guitar/accordion -> strum, pad -> pad, a drum track ->
dum/tak. Note starts are re-timed from the MIDI tempo to the library tempo.
Loop length = bars * beats_per_bar beats at that tempo; the tail that spills
past the loop is wrapped to the start so the seam is clean. Output is mono
44.1 kHz at --lufs (default -16) with peaks held under 0.95.

Importable: render(midi, out, bpm, bars, beats_per_bar) does the work and
returns the float signal; prepare_clip.prepare(midi=...) uses it for
library.py add/replace --midi.
Requires: pretty_midi numpy soundfile pyloudnorm  (pipeline/requirements.txt)
"""
import argparse, json, os, sys

import numpy as np
import pretty_midi
import pyloudnorm as pyln
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 44100
PEAK = 0.95


def freq(m):
    return 440 * 2 ** ((m - 69) / 12)


def env_ar(n, a, r):
    e = np.ones(n)
    a = max(1, min(int(a * SR), n // 2))
    r = max(1, min(int(r * SR), n // 2))
    e[:a] = np.linspace(0, 1, a)
    e[-r:] *= np.linspace(1, 0, r)
    return e


def lead(f, dur, amp):
    n = int(dur * SR); t = np.arange(n) / SR
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1, t / 0.3)
    ph = 2 * np.pi * np.cumsum(f * vib) / SR
    return amp * env_ar(n, 0.015, min(0.06, dur / 4)) * (np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph) + 0.08 * np.sin(4 * ph))


def pluck(f, dur, amp):
    n = int(max(dur, 1.0) * SR); t = np.arange(n) / SR
    e = np.exp(-t * 2.8) * (1 - np.exp(-t * 800))
    return amp * e * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) * np.exp(-t * 5))


def strum(f, dur, amp):
    n = int(max(dur, 0.4) * SR); t = np.arange(n) / SR
    e = np.exp(-t * 4) * (1 - np.exp(-t * 900))
    return amp * e * (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(4 * np.pi * f * t) + 0.25 * np.sin(6 * np.pi * f * t) + 0.1 * np.sin(8 * np.pi * f * t))


def pad(f, dur, amp):
    n = int(dur * SR); t = np.arange(n) / SR
    return amp * env_ar(n, 0.2, 0.2) * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * t * 2.003) + 0.1 * np.sin(2 * np.pi * f * t * 3))


def drum(pitch, amp, rng):
    if pitch in (35, 36):  # kick / dum
        n = int(0.25 * SR); t = np.arange(n) / SR
        f = 60 * np.exp(-t * 12) + 45
        return amp * np.exp(-t * 14) * np.sin(2 * np.pi * np.cumsum(f) / SR)
    n = int(0.08 * SR); t = np.arange(n) / SR   # anything else: tak
    return amp * np.exp(-t * 60) * (rng.standard_normal(n) * 0.6 + 0.4 * np.sin(2 * np.pi * 1800 * t))


VOICES = {"lead": (lead, 0.22), "pluck": (pluck, 0.8), "strum": (strum, 0.06), "pad": (pad, 0.08)}


def pick_voice(inst):
    name = inst.name.lower(); p = inst.program
    if any(k in name for k in ("melody", "lead", "clarinet", "voice")) or 64 <= p <= 79 or p == 25:
        return "lead"
    if any(k in name for k in ("bass", "tuba")) or 32 <= p <= 39 or p == 58:
        return "pluck"
    if any(k in name for k in ("guitar", "accordion", "oud", "strum")) or 21 <= p <= 31:
        return "strum"
    return "pad"


def manifest_defaults(root=ROOT):
    """(tempo, bars, beats_per_bar) from <root>/manifest.json."""
    with open(os.path.join(root, "manifest.json"), encoding="utf-8") as f:
        m = json.load(f)
    return float(m["tempo"]), int(m["bars"]), int(m["beats_per_bar"])


def render(midi, out, bpm, bars, beats_per_bar, *, transpose=0, lufs=-16.0, subtype="PCM_16", log=print):
    """Render `midi` to `out` (mono WAV at SR) as an exact loop of bars * beats_per_bar
    beats at `bpm`. Deterministic: the same input always gives the same samples.
    Returns (y, info) where y is the float64 signal and info has 'samples',
    'lufs', 'peak', 'midi_bpm'."""
    rng = np.random.default_rng(1)              # fresh per render: same noise every time
    pm = pretty_midi.PrettyMIDI(midi)
    tempi = pm.get_tempo_changes()[1]
    src_bpm = float(tempi[0]) if len(tempi) else 120.0
    scale = src_bpm / bpm                       # re-time note starts to the library tempo
    loop = bars * beats_per_bar * 60.0 / bpm
    N = int(round(loop * SR))
    buf = np.zeros(N + 2 * SR)

    def add(start, sig):
        s = int(start * SR); e = min(len(buf), s + len(sig))
        buf[s:e] += sig[:e - s]

    for inst in pm.instruments:
        if inst.is_drum:
            for n in inst.notes:
                if n.start * scale < loop:
                    add(n.start * scale, drum(n.pitch, 0.5 * n.velocity / 100, rng))
            continue
        fn, base = VOICES[pick_voice(inst)]
        for n in inst.notes:
            st = n.start * scale
            if st >= loop:
                continue
            dur = max(0.05, (n.end - n.start) * scale)
            add(st, fn(freq(n.pitch + transpose), dur, base * n.velocity / 100))

    y = buf[:N].copy()
    y[:2 * SR] += buf[N:N + 2 * SR]             # wrap the tail -> clean seam
    meter = pyln.Meter(SR)
    y = pyln.normalize.loudness(y, meter.integrated_loudness(y), lufs)
    for _ in range(3):                          # soft-clip, re-measure, converge
        y = 0.92 * np.tanh(y / 0.92)
        y = pyln.normalize.loudness(y, meter.integrated_loudness(y), lufs)
    pk = float(np.abs(y).max())
    if pk > PEAK:
        y *= PEAK / pk
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sf.write(out, y, SR, subtype=subtype)
    info = {"samples": len(y), "lufs": float(meter.integrated_loudness(y)), "peak": pk, "midi_bpm": src_bpm}
    log(f"render        {midi}  ({src_bpm:g} BPM in the file -> {bpm:g} BPM)")
    log(f"              {out}: {len(y)} samples = {len(y)/SR:.3f} s ({bars} bars x {beats_per_bar} beats), "
        f"{info['lufs']:.1f} LUFS, peak {pk:.2f}")
    return y, info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("midi")
    ap.add_argument("out")
    ap.add_argument("--bpm", type=float, help="library tempo (default: manifest.json)")
    ap.add_argument("--bars", type=int, help="loop length in bars (default: manifest.json)")
    ap.add_argument("--beats-per-bar", type=int, dest="beats_per_bar", help="default: manifest.json")
    ap.add_argument("--transpose", type=int, default=0, help="semitones added to every pitched note")
    ap.add_argument("--lufs", type=float, default=-16.0)
    ap.add_argument("--root", default=ROOT, help="repo root holding manifest.json (default: this repo)")
    a = ap.parse_args()
    try:
        bpm, bars, bpb = manifest_defaults(a.root)
    except (OSError, KeyError, ValueError) as e:
        if a.bpm is None or a.bars is None or a.beats_per_bar is None:
            sys.exit(f"error: cannot read tempo/bars/beats_per_bar from {os.path.join(a.root, 'manifest.json')} ({e}); "
                     "pass --bpm, --bars and --beats-per-bar")
        bpm = bars = bpb = None
    if a.bpm is not None: bpm = a.bpm
    if a.bars is not None: bars = a.bars
    if a.beats_per_bar is not None: bpb = a.beats_per_bar
    render(a.midi, a.out, bpm, bars, bpb, transpose=a.transpose, lufs=a.lufs)


if __name__ == "__main__":
    main()
