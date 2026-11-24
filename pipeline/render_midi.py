#!/usr/bin/env python3
"""render_midi.py — render a .mid into an exact whole-bar loop at the library tempo.

usage: render_midi.py <midi> <out.wav> [--bpm N] [--bars N] [--beats-per-bar N]
                      [--transpose ST] [--lufs L] [--root DIR]

Tempo, bars and beats per bar default to manifest.json in the repo root
(--root, default: this repo). The flags override them. The MIDI is expected to
be written in the library key already; --transpose shifts every pitched note
by whole semitones if it is not.

Sound: every track is played with the sampled instrument of its General MIDI
program by pipeline/sf2.py from the pinned SoundFont (sf2.find(): Merlin.sf2,
checked by sha256, from $MIXER_SOUNDFONT or sources/soundfonts/), the tracks
are balanced (melody in front), and a short room reverb is added. A missing or
different SoundFont stops the render. Only with MIXER_SOUNDFONT=builtin is the
built-in synth below used: track names (or GM programs) pick a voice:
melody/lead/clarinet -> lead, bass/tuba -> pluck, guitar/accordion -> strum,
pad -> pad, a drum track -> dum/tak. A drum track plays the SoundFont's drum kit (bank 128) named by its
program: 0 Standard, 16 Power, 25 TR 808, 32 Jazz, 48 Orchestra in Merlin.sf2.
Note starts are re-timed from the MIDI tempo to the library tempo.
A lead track that carries pitch-bend or expression (CC11) is played as a sung
line: notes that touch are tied, the pitch follows note + bend (bend range from
RPN 0, else 2 semitones) and the level follows CC11.
Loop length = bars * beats_per_bar beats at that tempo; the tail that spills
past the loop is wrapped to the start so the seam is clean. Output is mono
44.1 kHz at --lufs (default -16) with peaks held under 0.95.

Importable: render(midi, out, bpm, bars, beats_per_bar) does the work and
returns the float signal; pipeline/arrange/rerender.py uses it to render each clip's part.
Requires: pretty_midi numpy soundfile pyloudnorm scipy  (pipeline/requirements.txt)
"""
import argparse, json, os, sys

import numpy as np
import pretty_midi
import pyloudnorm as pyln
import soundfile as sf
from scipy.signal import butter, fftconvolve, sosfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sf2  # noqa: E402

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
GLIDE = 0.010      # s: smoothing of the pitch and level curves of a sung line
TIE = 0.004        # s: a note starting this close to the end of the one before is tied to it


def bend_range(inst):
    """Pitch-bend range in semitones from an RPN 0 message (CC101=0, CC100=0, then CC6); 2 if there is none."""
    rng, msb, lsb = 2.0, None, None
    for c in sorted(inst.control_changes, key=lambda c: c.time):
        if c.number == 101: msb = c.value
        elif c.number == 100: lsb = c.value
        elif c.number == 6 and msb == 0 and lsb == 0: rng = float(c.value)
    return rng


def held(events, t, default):
    """Sample-and-hold value at times t of (time, value) events sorted by time; `default` before the first."""
    if not events:
        return np.full(len(t), default)
    et = np.array([e[0] for e in events]); ev = np.array([e[1] for e in events], dtype=float)
    i = np.searchsorted(et, t, side="right") - 1
    return np.where(i >= 0, ev[np.maximum(i, 0)], default)


def smooth(x, n):
    if n < 2 or len(x) < 2:
        return x
    k = np.ones(n) / n
    return np.convolve(np.concatenate([np.full(n, x[0]), x, np.full(n, x[-1])]), k, mode="same")[n:-n]


def sung_curves(inst, scale, loop, transpose):
    """[(start, pitch curve, level curve, velocity)] per chain of tied notes of a track with pitch-bend / expression."""
    notes = sorted(inst.notes, key=lambda n: n.start)
    rng = bend_range(inst)
    bends = sorted((b.time * scale, b.pitch / 8192.0 * rng) for b in inst.pitch_bends)
    expr = sorted((c.time * scale, c.value / 127.0) for c in inst.control_changes if c.number == 11)
    chains = []
    for n in notes:
        if n.start * scale >= loop:
            continue
        if chains and n.start * scale <= chains[-1][-1].end * scale + TIE: chains[-1].append(n)
        else: chains.append([n])
    out = []
    for ch in chains:
        t0, t1 = ch[0].start * scale, max(n.end for n in ch) * scale
        m = max(8, int((t1 - t0) * SR)); t = t0 + np.arange(m) / SR; k = int(GLIDE * SR)
        pitch = smooth(held([(n.start * scale, n.pitch) for n in ch], t, ch[0].pitch) + held(bends, t, 0.0) + transpose, k)
        out.append((t0, pitch, smooth(held(expr, t, 1.0), k), ch[0].velocity))
    return out


def sung_line(inst, scale, loop, transpose, base):
    """[(start, signal)] for a lead track with pitch-bend / expression: one signal per chain of tied notes."""
    notes = sorted(inst.notes, key=lambda n: n.start)
    rng = bend_range(inst)
    bends = sorted((b.time * scale, b.pitch / 8192.0 * rng) for b in inst.pitch_bends)
    expr = sorted((c.time * scale, c.value / 127.0) for c in inst.control_changes if c.number == 11)
    chains = []
    for n in notes:
        if n.start * scale >= loop:
            continue
        if chains and n.start * scale <= chains[-1][-1].end * scale + TIE: chains[-1].append(n)
        else: chains.append([n])
    out = []
    for ch in chains:
        t0, t1 = ch[0].start * scale, max(n.end for n in ch) * scale
        m = max(8, int((t1 - t0) * SR)); t = t0 + np.arange(m) / SR
        pitch = held([(n.start * scale, n.pitch) for n in ch], t, ch[0].pitch) + held(bends, t, 0.0) + transpose
        k = int(GLIDE * SR)
        f = freq(smooth(pitch, k))
        ph = 2 * np.pi * np.cumsum(f) / SR
        vel = held([(n.start * scale, n.velocity / 100.0) for n in ch], t, ch[0].velocity / 100.0)
        level = smooth(vel * held(expr, t, 1.0), k)
        sig = base * level * env_ar(m, 0.012, min(0.04, (t1 - t0) / 4)) * (np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph) + 0.08 * np.sin(4 * ph))
        out.append((t0, sig))
    return out


def pick_voice(inst):
    name = inst.name.lower(); p = inst.program
    if any(k in name for k in ("melody", "lead", "clarinet", "voice")) or 64 <= p <= 79 or p == 25:
        return "lead"
    if any(k in name for k in ("bass", "tuba")) or 32 <= p <= 39 or p == 58:
        return "pluck"
    if any(k in name for k in ("guitar", "accordion", "oud", "strum")) or 21 <= p <= 31:
        return "strum"
    return "pad"


# ---------- sampled instruments ----------
# role -> (level against the melody in dB, share of room reverb)
ROLES = {"lead": (0.0, 0.12), "bass": (-2.0, 0.04), "chords": (-6.0, 0.15), "drums": (-5.0, 0.10)}
SUNG_RELEASE = 0.12      # s: a sung line's notes end with the singer's
SUNG_LEAD_IN = 0.02      # s: sampled wind instruments speak late; a sung line starts this much early to land on time
HAND_DRUMS = {35: 64, 36: 64, 42: 60, 38: 62}     # a darbuka written on kick / hat keys -> low conga (dum), high bongo (tak)
_FONT = {}


def soundfont():
    """The pinned SoundFont player, or None with MIXER_SOUNDFONT=builtin (then the built-in synth plays).
    A missing or different SoundFont stops the process with sf2's message."""
    try:
        path = sf2.find(ROOT)
    except sf2.SoundFontError as e:
        sys.exit(f"error: {e}")
    if path not in _FONT:
        _FONT[path] = sf2.SoundFont(path) if path else None
    return _FONT[path]


def role_of(inst):
    name = inst.name.lower(); p = inst.program
    if inst.is_drum: return "drums"
    if any(k in name for k in ("melody", "lead", "clarinet", "voice")): return "lead"
    if any(k in name for k in ("bass", "tuba")) or 32 <= p <= 39 or p == 58: return "bass"
    if 64 <= p <= 79 or 40 <= p <= 42: return "lead"
    return "chords"


def program_of(inst):
    name = inst.name.lower(); p = int(inst.program)
    if "oud" in name: return 24                                          # no oud in General MIDI: nylon guitar
    if any(k in name for k in ("melody", "lead", "voice")) and (p <= 31 or 104 <= p <= 119): return 73   # a melody is held, not plucked: flute
    return p


def room():
    """A small synthetic room: 15 ms pre-delay, a few early reflections, a 1.1 s tail that darkens as it fades."""
    n = int(1.3 * SR); t = np.arange(n) / SR; rng = np.random.default_rng(7)
    tail = 0.6 * rng.standard_normal(n) * np.exp(-t / 0.15) + sosfilt(butter(2, 1800, btype="low", fs=SR, output="sos"), rng.standard_normal(n)) * np.exp(-t / 0.26) * 3.0
    tail *= np.minimum(1.0, t / 0.03)
    ir = np.zeros(n + int(0.015 * SR)); ir[int(0.015 * SR):] = tail * 0.05
    for ms, g in ((11, 0.5), (17, -0.4), (23, 0.35), (31, -0.3), (41, 0.25), (53, 0.2)):
        ir[int(ms * SR / 1000)] += g
    ir = sosfilt(butter(2, 160, btype="high", fs=SR, output="sos"), ir)
    return ir / np.sqrt(np.sum(ir ** 2))


def sampled(pm, font, scale, loop, transpose, length, rng, reverb=True):
    """Mix of all tracks played from the SoundFont: one bus per track, balanced by role, with room reverb."""
    ir = room(); meter = pyln.Meter(SR); mix = np.zeros(length)
    for inst in pm.instruments:
        bus = np.zeros(length); role = role_of(inst); prog = program_of(inst)
        def add(start, sig):
            a = int(start * SR); b = min(length, a + len(sig))
            if b > a: bus[a:b] += sig[:b - a]
        if inst.is_drum:
            for n in inst.notes:
                if n.start * scale < loop:
                    key = HAND_DRUMS.get(n.pitch, n.pitch) if "darbuka" in inst.name.lower() else n.pitch
                    add(n.start * scale, font.voice(128, int(inst.program), key, n.velocity, max(int(0.25 * SR), int((n.end - n.start) * scale * SR))))
        elif inst.pitch_bends or any(c.number == 11 for c in inst.control_changes):
            for t0, pitch, level, vel in sung_curves(inst, scale, loop, transpose):
                k = int(min(SUNG_LEAD_IN, t0) * SR)
                pitch = np.concatenate([np.full(k, pitch[0]), pitch]); level = np.concatenate([np.full(k, level[0]), level])
                add(t0 - k / SR, font.voice(0, prog, int(round(float(np.median(pitch)))), vel, len(pitch), pitch=pitch, level=level, release=SUNG_RELEASE))
        else:
            for n in inst.notes:
                if n.start * scale < loop:
                    add(n.start * scale, font.voice(0, prog, n.pitch + transpose, n.velocity, int(max(0.05, (n.end - n.start) * scale) * SR)))
        gain_db, wet = ROLES[role]
        if reverb: bus = bus + wet * fftconvolve(bus, ir)[:length]
        loud = meter.integrated_loudness(bus) if np.any(bus) else float("-inf")
        if np.isfinite(loud):
            mix += bus * 10 ** ((-20.0 + gain_db - loud) / 20)
    return sosfilt(butter(2, 30, btype="high", fs=SR, output="sos"), mix)


def manifest_defaults(root=ROOT):
    """(tempo, bars, beats_per_bar) from <root>/manifest.json."""
    with open(os.path.join(root, "manifest.json"), encoding="utf-8") as f:
        m = json.load(f)
    return float(m["tempo"]), int(m["bars"]), int(m["beats_per_bar"])


def render(midi, out, bpm, bars, beats_per_bar, *, transpose=0, lufs=-16.0, subtype="PCM_16", log=print, reverb=True):
    """Render `midi` to `out` (mono WAV at SR) as an exact loop of bars * beats_per_bar
    beats at `bpm`. Deterministic: the same input always gives the same samples.
    Returns (y, info) where y is the float64 signal and info has 'samples',
    'lufs', 'peak', 'midi_bpm'. reverb=False leaves the room out (for measuring the notes themselves)."""
    rng = np.random.default_rng(1)              # fresh per render: same noise every time
    pm = pretty_midi.PrettyMIDI(midi)
    tempi = pm.get_tempo_changes()[1]
    src_bpm = float(tempi[0]) if len(tempi) else 120.0
    scale = src_bpm / bpm                       # re-time note starts to the library tempo
    loop = bars * beats_per_bar * 60.0 / bpm
    N = int(round(loop * SR))
    buf = np.zeros(N + 6 * SR)
    font = soundfont()

    def add(start, sig):
        s = int(start * SR); e = min(len(buf), s + len(sig))
        buf[s:e] += sig[:e - s]

    if font is not None:
        buf += sampled(pm, font, scale, loop, transpose, len(buf), rng, reverb)
    for inst in (pm.instruments if font is None else []):
        if inst.is_drum:
            for n in inst.notes:
                if n.start * scale < loop:
                    add(n.start * scale, drum(n.pitch, 0.5 * n.velocity / 100, rng))
            continue
        fn, base = VOICES[pick_voice(inst)]
        if fn is lead and (inst.pitch_bends or any(c.number == 11 for c in inst.control_changes)):
            for start, sig in sung_line(inst, scale, loop, transpose, base):
                add(start, sig)
            continue
        for n in inst.notes:
            st = n.start * scale
            if st >= loop:
                continue
            dur = max(0.05, (n.end - n.start) * scale)
            add(st, fn(freq(n.pitch + transpose), dur, base * n.velocity / 100))

    y = buf[:N].copy()
    for k in range(N, len(buf), N):             # wrap the tail (notes ringing on, reverb) -> clean seam
        part = buf[k:k + N]; y[:len(part)] += part
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
    log(f"render        {midi}  ({src_bpm:g} BPM in the file -> {bpm:g} BPM)  sound: "
        + (os.path.basename(font.path) if font is not None else "built-in synth (MIXER_SOUNDFONT=builtin)"))
    log(f"              {out}: {len(y)} samples = {len(y)/SR:.3f} s ({bars} bars x {beats_per_bar} beats), "
        f"{info['lufs']:.1f} LUFS, peak {pk:.2f}")
    return y, info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("midi")
    ap.add_argument("out", help="output .wav")
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
