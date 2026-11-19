#!/usr/bin/env python3
"""sf2.py — a small SoundFont 2 sample player, so render_midi.py can use real sampled instruments.

Pure numpy/scipy, no synthesiser to install. It reads the presets, instruments and sample headers of
an .sf2 file and plays one note at a time: the right sample zones for the key and velocity, pitched by
resampling (with the loop), shaped by the zone's volume envelope, attenuation and low-pass filter.
Stereo pairs are summed to mono. Modulators, LFOs, the modulation envelope and effects are ignored.

    sf = SoundFont(path)
    y = sf.voice(bank, program, key, velocity, n_on)                 # n_on samples held, then the release
    y = sf.voice(bank, program, key, velocity, n_on, pitch=curve)    # pitch (MIDI numbers) per output sample
    python pipeline/sf2.py <file.sf2>                                # list the presets

find() returns the soundfont to use: $MIXER_SOUNDFONT, else the first .sf2 in sources/soundfonts/ (by name)
that is really on disk.
"""
import glob, os, struct, sys

import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# generator numbers used here
G_FILTER, G_ATTACK, G_HOLD, G_DECAY, G_SUSTAIN, G_RELEASE, G_DELAY = 8, 34, 35, 36, 37, 38, 33
G_INSTRUMENT, G_KEYRANGE, G_VELRANGE, G_ATTEN, G_COARSE, G_FINE, G_SAMPLE, G_MODES, G_SCALE, G_ROOT = 41, 43, 44, 48, 51, 52, 53, 54, 56, 58
G_START, G_END, G_LOOPSTART, G_LOOPEND, G_STARTC, G_ENDC, G_LOOPSTARTC, G_LOOPENDC = 0, 1, 2, 3, 4, 12, 45, 50
DEFAULT = {G_FILTER: 13500, G_ATTACK: -12000, G_HOLD: -12000, G_DECAY: -12000, G_SUSTAIN: 0, G_RELEASE: -12000, G_DELAY: -12000,
           G_ATTEN: 0, G_COARSE: 0, G_FINE: 0, G_MODES: 0, G_SCALE: 100, G_ROOT: -1}
ADDITIVE = (G_FILTER, G_ATTACK, G_HOLD, G_DECAY, G_SUSTAIN, G_RELEASE, G_DELAY, G_ATTEN, G_COARSE, G_FINE, G_SCALE)   # preset level adds to these
MAX_RELEASE = 1.0      # s: longest tail after a note ends


def find(root=ROOT):
    p = os.environ.get("MIXER_SOUNDFONT")
    if p and os.path.isfile(p):
        return p
    for hit in sorted(glob.glob(os.path.join(root, "sources", "soundfonts", "*.sf2"))):
        st = os.stat(hit)
        if st.st_size > 0 and st.st_blocks > 0:          # skip cloud placeholders: reading one would stall
            return hit
    return None


def secs(timecents):
    return float(2.0 ** (timecents / 1200.0))


class SoundFont:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            head = f.read(12)
            if head[:4] != b"RIFF" or head[8:12] != b"sfbk":
                raise ValueError(f"not a SoundFont 2 file: {path}")
            size = struct.unpack("<I", head[4:8])[0]
            chunks = {}
            self._walk(f, 12, 8 + size, chunks)
        off, n = chunks["smpl"]
        self.smpl = np.memmap(path, dtype="<i2", mode="r", offset=off, shape=(n // 2,))
        with open(path, "rb") as f:
            def table(name, fmt):
                o, ln = chunks[name]; f.seek(o); raw = f.read(ln); sz = struct.calcsize(fmt)
                return [struct.unpack_from(fmt, raw, i) for i in range(0, ln - sz + 1, sz)]
            self.phdr = table("phdr", "<20sHHHIII"); self.pbag = table("pbag", "<HH"); self.pgen = table("pgen", "<HH")
            self.inst = table("inst", "<20sH"); self.ibag = table("ibag", "<HH"); self.igen = table("igen", "<HH")
            self.shdr = table("shdr", "<20sIIIIIBbHH")
        self._zones = {}; self._data = {}

    def _walk(self, f, pos, end, out):
        while pos + 8 <= end:
            f.seek(pos); cid, size = struct.unpack("<4sI", f.read(8))
            if cid == b"LIST":
                self._walk(f, pos + 12, pos + 8 + size, out)
            else:
                out[cid.decode("latin1")] = (pos + 8, size)
            pos += 8 + size + (size & 1)

    @staticmethod
    def _gens(bags, gens, b):
        """{generator: value} of bag b; ranges become (lo, hi), the rest signed 16-bit."""
        d = {}
        for op, amt in gens[bags[b][0]:bags[b + 1][0]]:
            d[op] = (amt & 0xFF, amt >> 8) if op in (G_KEYRANGE, G_VELRANGE) else (amt - 65536 if amt >= 32768 else amt)
        return d

    def _split(self, bags, gens, first, last, terminal):
        """Zones of one preset or instrument: its global zone folded into each of the others."""
        glob_, zones = {}, []
        for b in range(first, last):
            d = self._gens(bags, gens, b)
            if terminal in d: zones.append({**glob_, **d})
            elif b == first: glob_ = d
        return zones

    def presets(self):
        return sorted((bank, prog, name.split(b"\0")[0].decode("latin1")) for name, prog, bank, *_ in self.phdr[:-1])

    def zones(self, bank, program):
        """Every (preset zone, instrument zone) pair of a preset, with the generators already combined."""
        key = (bank, program)
        if key in self._zones:
            return self._zones[key]
        idx = next((i for i, p in enumerate(self.phdr[:-1]) if p[2] == bank and p[1] == program), None)
        if idx is None:
            raise KeyError(f"no preset bank {bank} program {program} in {os.path.basename(self.path)}")
        out = []
        for pz in self._split(self.pbag, self.pgen, self.phdr[idx][3], self.phdr[idx + 1][3], G_INSTRUMENT):
            ii = pz[G_INSTRUMENT]
            for iz in self._split(self.ibag, self.igen, self.inst[ii][1], self.inst[ii + 1][1], G_SAMPLE):
                g = {k: iz.get(k, v) for k, v in DEFAULT.items()}
                for k in ADDITIVE:
                    g[k] += pz.get(k, 0)
                for k in (G_START, G_END, G_LOOPSTART, G_LOOPEND, G_STARTC, G_ENDC, G_LOOPSTARTC, G_LOOPENDC):
                    g[k] = iz.get(k, 0)
                lo = lambda z, k: z.get(k, (0, 127))
                g["key"] = (max(lo(pz, G_KEYRANGE)[0], lo(iz, G_KEYRANGE)[0]), min(lo(pz, G_KEYRANGE)[1], lo(iz, G_KEYRANGE)[1]))
                g["vel"] = (max(lo(pz, G_VELRANGE)[0], lo(iz, G_VELRANGE)[0]), min(lo(pz, G_VELRANGE)[1], lo(iz, G_VELRANGE)[1]))
                g["sample"] = iz[G_SAMPLE]
                out.append(g)
        self._zones[key] = out
        return out

    def _sample(self, g):
        """(float samples, loop start, loop end, sample rate, root key, pitch correction) of a zone."""
        name, start, end, ls, le, rate, root, corr, link, typ = self.shdr[g["sample"]]
        start += g[G_START] + 32768 * g[G_STARTC]; end += g[G_END] + 32768 * g[G_ENDC]
        ls += g[G_LOOPSTART] + 32768 * g[G_LOOPSTARTC]; le += g[G_LOOPEND] + 32768 * g[G_LOOPENDC]
        k = (start, end)
        if k not in self._data:
            self._data[k] = np.asarray(self.smpl[start:end], dtype=np.float32) / 32768.0
        return self._data[k], ls - start, le - start, rate, (g[G_ROOT] if g[G_ROOT] >= 0 else root), corr

    def voice(self, bank, program, key, vel, n_on, pitch=None, level=None, release=None):
        """One note as a mono float array: n_on samples held, then the release (at most MAX_RELEASE,
        or `release` seconds when given: a sung line wants its notes to end when the singer's do).
        pitch: MIDI pitch per output sample (for bends and ties; padded with its last value); the zone is chosen
        by `key`. level: gain per output sample (expression), padded the same way."""
        zs = [g for g in self.zones(bank, program) if g["key"][0] <= key <= g["key"][1] and g["vel"][0] <= vel <= g["vel"][1]]
        if not zs:
            return np.zeros(max(1, n_on))
        tail = MAX_RELEASE if release is None else release
        n = n_on + int(tail * SR); t = np.arange(n) / SR; t_off = n_on / SR
        def padded(c, fill):
            if c is None: return fill
            c = np.asarray(c, dtype=float)
            return c[:n] if len(c) >= n else np.concatenate([c, np.full(n - len(c), c[-1])])
        pitch = padded(pitch, float(key)); level = padded(level, 1.0)
        out = np.zeros(n)
        for g in zs:
            data, ls, le, rate, root, corr = self._sample(g)
            cents = (pitch - root) * g[G_SCALE] + 100 * g[G_COARSE] + g[G_FINE] + corr
            step = 2.0 ** (cents / 1200.0) * rate / SR
            pos = np.cumsum(np.broadcast_to(step, (n,))) - (step if np.isscalar(step) else step[0])
            looped = g[G_MODES] in (1, 3) and le - ls > 8 and le <= len(data)
            if looped:
                wrap = lambda i: np.where(i >= le, ls + np.mod(i - ls, le - ls), i)
                pos = np.where(pos >= le, ls + np.mod(pos - ls, le - ls), pos); live = np.ones(n, bool)
            else:
                wrap = lambda i: i
                live = pos < len(data) - 2
            i = np.floor(pos).astype(np.int64); f = pos - i
            tap = lambda k: data[np.clip(wrap(i + k), 0, len(data) - 1)]
            y0, y1, y2, y3 = tap(-1), tap(0), tap(1), tap(2)                       # Catmull-Rom
            y = y1 + 0.5 * f * (y2 - y0 + f * (2 * y0 - 5 * y1 + 4 * y2 - y3 + f * (3 * (y1 - y2) + y3 - y0)))
            # volume envelope: delay, attack (linear), hold, decay to sustain (linear in dB), release from wherever it is
            dl, at, ho, de, re = (secs(g[k]) for k in (G_DELAY, G_ATTACK, G_HOLD, G_DECAY, G_RELEASE))
            sus = float(np.clip(g[G_SUSTAIN] / 10.0, 0, 100))
            def att_on(tt):                                                         # attenuation in dB while the key is down
                a = np.where(tt < dl + at, -20 * np.log10(np.clip((tt - dl) / max(at, 1e-4), 1e-5, 1)), 0.0)
                return np.where(tt > dl + at + ho, np.minimum(sus, (tt - dl - at - ho) * 100.0 / max(de, 1e-3)), a)
            a0 = float(att_on(np.array([t_off]))[0])
            att = np.where(t < t_off, att_on(t), a0 + (t - t_off) * 100.0 / max(min(re, tail), 0.02))
            amp = np.where(att < 96, 10.0 ** (-att / 20.0), 0.0) * live
            gain = 10.0 ** (-0.4 * max(g[G_ATTEN], 0) / 200.0) * (vel / 127.0) ** 2
            y = y * amp * gain
            fc = 8.176 * 2.0 ** (g[G_FILTER] / 1200.0)
            if fc < 0.4 * SR and g[G_FILTER] < 13000:
                y = sosfilt(butter(2, fc, btype="low", fs=SR, output="sos"), y)
            out += y * (0.7071 if len(zs) > 1 else 1.0)
        return out * level


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else find()
    if not path:
        sys.exit("no soundfont: pass a path, set MIXER_SOUNDFONT or put one in sources/soundfonts/")
    for bank, prog, name in SoundFont(path).presets():
        print(f"{bank:3d} {prog:3d}  {name}")
