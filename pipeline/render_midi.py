#!/usr/bin/env python3
"""render_midi.py — render a .mid into an exact whole-bar loop at the library tempo/key.

Usage:
  python3 pipeline/render_midi.py sources/midi/israel-hatikva-full.mid sources/israel-hatikva-full.wav
      [--bpm 100] [--bars 8] [--transpose 0] [--lufs -16]

Track names (or GM programs) pick a voice: melody/lead/clarinet -> lead, bass/tuba -> pluck,
guitar/accordion -> strum, pad -> pad, a drum track -> dum/tak. Loop length = bars * 4 beats at --bpm;
the tail that spills past the loop is wrapped to the start so the seam is clean.
Requires: pretty_midi numpy soundfile pyloudnorm  (pip install ...)
"""
import argparse, numpy as np, pretty_midi, pyloudnorm as pyln, soundfile as sf
SR = 44100
def freq(m): return 440 * 2 ** ((m - 69) / 12)
def env_ar(n, a, r):
    e = np.ones(n); a = max(1, min(int(a * SR), n // 2)); r = max(1, min(int(r * SR), n // 2))
    e[:a] = np.linspace(0, 1, a); e[-r:] *= np.linspace(1, 0, r); return e
def lead(f, dur, amp):
    n = int(dur * SR); t = np.arange(n) / SR
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1, t / 0.3); ph = 2 * np.pi * np.cumsum(f * vib) / SR
    return amp * env_ar(n, 0.015, min(0.06, dur / 4)) * (np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph) + 0.08 * np.sin(4 * ph))
def pluck(f, dur, amp):
    n = int(max(dur, 1.0) * SR); t = np.arange(n) / SR; e = np.exp(-t * 2.8) * (1 - np.exp(-t * 800))
    return amp * e * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) * np.exp(-t * 5))
def strum(f, dur, amp):
    n = int(max(dur, 0.4) * SR); t = np.arange(n) / SR; e = np.exp(-t * 4) * (1 - np.exp(-t * 900))
    return amp * e * (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(4 * np.pi * f * t) + 0.25 * np.sin(6 * np.pi * f * t) + 0.1 * np.sin(8 * np.pi * f * t))
def pad(f, dur, amp):
    n = int(dur * SR); t = np.arange(n) / SR
    return amp * env_ar(n, 0.2, 0.2) * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * t * 2.003) + 0.1 * np.sin(2 * np.pi * f * t * 3))
rng = np.random.default_rng(1)
def drum(pitch, amp):
    if pitch in (35, 36):  # kick / dum
        n = int(0.25 * SR); t = np.arange(n) / SR; f = 60 * np.exp(-t * 12) + 45
        return amp * np.exp(-t * 14) * np.sin(2 * np.pi * np.cumsum(f) / SR)
    n = int(0.08 * SR); t = np.arange(n) / SR   # anything else: tak
    return amp * np.exp(-t * 60) * (rng.standard_normal(n) * 0.6 + 0.4 * np.sin(2 * np.pi * 1800 * t))
VOICES = {'lead': (lead, 0.22), 'pluck': (pluck, 0.8), 'strum': (strum, 0.06), 'pad': (pad, 0.08)}
def pick_voice(inst):
    name = inst.name.lower(); p = inst.program
    if any(k in name for k in ('melody', 'lead', 'clarinet', 'voice')) or 64 <= p <= 79 or p == 25: return 'lead'
    if any(k in name for k in ('bass', 'tuba')) or 32 <= p <= 39 or p == 58: return 'pluck'
    if any(k in name for k in ('guitar', 'accordion', 'oud', 'strum')) or 21 <= p <= 31: return 'strum'
    return 'pad'
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('midi'); ap.add_argument('out')
    ap.add_argument('--bpm', type=float, default=100); ap.add_argument('--bars', type=int, default=8)
    ap.add_argument('--transpose', type=int, default=0); ap.add_argument('--lufs', type=float, default=-16)
    a = ap.parse_args()
    pm = pretty_midi.PrettyMIDI(a.midi); src_bpm = pm.get_tempo_changes()[1][0]
    scale = src_bpm / a.bpm                     # re-time note starts to the library tempo
    loop = a.bars * 4 * 60 / a.bpm; N = int(round(loop * SR)); out = np.zeros(N + 2 * SR)
    def add(start, sig):
        s = int(start * SR); e = min(len(out), s + len(sig)); out[s:e] += sig[:e - s]
    for inst in pm.instruments:
        if inst.is_drum:
            for n in inst.notes:
                if n.start * scale < loop: add(n.start * scale, drum(n.pitch, 0.5 * n.velocity / 100))
            continue
        fn, base = VOICES[pick_voice(inst)]
        for n in inst.notes:
            st = n.start * scale
            if st >= loop: continue
            dur = max(0.05, (n.end - n.start) * scale)
            add(st, fn(freq(n.pitch + a.transpose), dur, base * n.velocity / 100))
    y = out[:N].copy(); y[:2 * SR] += out[N:N + 2 * SR]        # wrap the tail -> clean seam
    meter = pyln.Meter(SR); y = pyln.normalize.loudness(y, meter.integrated_loudness(y), a.lufs)
    for _ in range(3):
        y = 0.92 * np.tanh(y / 0.92); y = pyln.normalize.loudness(y, meter.integrated_loudness(y), a.lufs)
    pk = np.abs(y).max()
    if pk > 0.95: y *= 0.95 / pk
    sf.write(a.out, y, SR, subtype='PCM_16')
    print(f'{a.out}: {len(y)} samples = {len(y)/SR:.3f} s ({a.bars} bars @ {a.bpm} BPM), '
          f'{meter.integrated_loudness(y):.1f} LUFS, peak {pk:.2f}')
if __name__ == '__main__': main()
