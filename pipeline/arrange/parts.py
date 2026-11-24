#!/usr/bin/env python3
"""parts.py — write one instrument part per clip, re-voiced onto the shared progression.

Each column of the app plays one instrument (INSTRUMENTS). For a clip, this takes the
track of the clip's song MIDI (the clip's `source` in manifest.json) that plays the
column's role, re-voices it onto HARMONY, and writes it as the clip's `part`,
midi/parts/<slug>--<instrument>.mid: one track named after the instrument, carrying
its GM program, at the library tempo, 8 bars. rerender.py renders it to the clip's WAV.

Roles, by track name in the song MIDI:
  melody  = melody | clarinet           notes unchanged
  bass    = bass | tuba                  re-voiced
  harmony = guitar | pad | oud | accordion | piano   re-voiced
  drums   = drums                        on the drum channel, in the clip's kit (KITS); no re-voicing, no range
A missing or ambiguous role is an error; nothing is guessed.

Re-voicing (bass and harmony): every note keeps its start, end and velocity.
  * a C# whose onset falls inside a V window keeps its pitch
  * a bass note on a bar line or a chord change takes the nearest root, at any distance
  * a note already in the chord stays where it is
  * otherwise it moves to the nearest chord tone (at most 4 semitones; ties go down)
A re-voiced part that contains C# is first rotated by whole bars so the most C# onsets
fall in V windows; the rotation is pinned per clip in ROTATION so re-runs never change
it silently. Where two notes land on one pitch and overlap, the earlier one ends where
the later one starts (MIDI cannot hold both). A part that leaves its instrument's range (RANGES) moves whole by octaves.

usage (repo root, venv active): python pipeline/arrange/parts.py [clip ids ...]
       no ids: every clip in the manifest
"""
import argparse, copy, json, os, sys

import pretty_midi

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from render_midi import manifest_defaults  # noqa: E402

OUT_DIR = "midi/parts"

# The shared progression, D minor, one chord per half bar (beats 1-2, beats 3-4), 8 bars.
HARMONY = "i i  i i  i i  i V  iv iv  i i  i V  i i".split()
CHORDS = {"i": (2, frozenset({2, 5, 9})),       # Dm: D F A
          "iv": (7, frozenset({7, 10, 2})),     # Gm: G Bb D
          "V": (9, frozenset({9, 1, 4}))}       # A:  A C# E
CSHARP = 1

# asset id -> (instrument id, GM program, bank, source role); asset order
INSTRUMENTS = {
    "hebrew":    ("clarinet", 71, 0, "melody"),
    "israel":    ("drums", None, 128, "drums"),    # program: the clip's kit, from KITS
    "values":    ("bass", 33, 0, "bass"),
    "culture":   ("guitar", 25, 0, "harmony"),
    "memory":    ("violin", 40, 0, "melody"),
    "lifestyle": ("piano", 0, 0, "harmony"),
}
ROLE_TRACKS = {"melody": ("melody", "clarinet"),
               "bass": ("bass", "tuba"),
               "harmony": ("guitar", "pad", "oud", "accordion", "piano"),
               "drums": ("drums",)}
# Drum kit per clip: a bank 128 program of Merlin.sf2 (0 Standard, 16 Power, 25 TR 808, 32 Jazz, 48 Orchestra).
# The song's drums track carries the same kit; a mismatch is an error.
KITS = {
    "israel-02": 48,    # התקווה: Orchestra (timpani, orchestral snare, cymbal)
    "israel-03": 32,    # שלום לך ארץ נהדרת: Jazz
    "israel-04": 0,     # קריה יפיפיה: Standard
}
RANGES = {"clarinet": ("D3", "A6"), "violin": ("G3", "A6"), "bass": ("E1", "G3"),
          "guitar": ("E2", "B5"), "piano": ("A0", "C8")}

# Whole-bar rotation per clip, pinned (computed once by best_rotation). Parts without C# use 0.
ROTATION = {
    "values-03": 3,     # צדיק כתמר יפרח, bass: 2 C# onsets in V
    "culture-02": 1,    # ניגון ריקוד לשבת, accordion: 4 C# onsets in V
    "lifestyle-02": 3,  # אשת חיל, piano: 4 C# onsets in V
}

# Clips with no source part for their column yet; they get one in B3.
SKIP = {}

MAX_MOVE = 4        # semitones a non-root note may move
GRACE = 0.03        # s: a note a hair early belongs to the next half bar

BPM, BARS, BPB = manifest_defaults(ROOT)
BAR = BPB * 60.0 / BPM
HALF = BAR / 2
LOOP = BARS * BAR
assert len(HARMONY) == 2 * BARS, "HARMONY must have one chord per half bar"


class PartError(Exception):
    pass


def name(p):
    return pretty_midi.note_number_to_name(p)


def chord_at(t):
    return HARMONY[int((t + GRACE) // HALF) % len(HARMONY)]


def chord_change(t):
    """True when t is on a bar line, or on a mid-bar point where the chord changes."""
    h = int(round(t / HALF))
    if abs(t - h * HALF) >= GRACE:
        return False
    return h % 2 == 0 or HARMONY[h % len(HARMONY)] != HARMONY[(h - 1) % len(HARMONY)]


def nearest(p, pcs):
    """Nearest pitch to p whose pitch class is in pcs (ties go down)."""
    return min((q for q in range(p - 6, p + 7) if q % 12 in pcs), key=lambda q: (abs(q - p), q))


def rotated(inst, r):
    out = copy.deepcopy(inst)
    for n in out.notes:
        d = n.end - n.start
        n.start = (n.start + r * BAR) % LOOP
        n.end = n.start + d
    out.notes.sort(key=lambda n: (n.start, n.pitch))
    return out


def v_hits(inst):
    return sum(1 for n in inst.notes if n.pitch % 12 == CSHARP and chord_at(n.start) == "V")


def best_rotation(inst):
    """The whole-bar rotation (0..BARS-1) that puts the most C# onsets in V windows; ties go to the smallest."""
    return max(range(BARS), key=lambda r: (v_hits(rotated(inst, r)), -r))


def revoice(inst, role):
    """Re-voice onto HARMONY in place. Returns (notes moved, C#s kept)."""
    moved = kept = 0
    for n in inst.notes:
        c = chord_at(n.start)
        root, pcs = CHORDS[c]
        if n.pitch % 12 == CSHARP and c == "V":
            q = n.pitch
            kept += 1
        elif role == "bass" and chord_change(n.start):
            q = nearest(n.pitch, {root})
        elif n.pitch % 12 in pcs:
            q = n.pitch
        else:
            q = nearest(n.pitch, pcs)
            if abs(q - n.pitch) > MAX_MOVE:
                raise PartError(f"note {name(n.pitch)} at {n.start:.3f}s would move {q - n.pitch:+d} semitones")
        moved += q != n.pitch
        n.pitch = q
    return moved, kept


def untangle(inst):
    """MIDI cannot hold two overlapping notes of one pitch (re-voicing can land two notes on one
    pitch): end the earlier one where the later one starts. Returns how many notes were shortened."""
    last, cut = {}, 0
    for n in sorted(inst.notes, key=lambda n: (n.start, n.pitch)):
        p = last.get(n.pitch)
        if p is not None and p.end > n.start:
            p.end = n.start
            cut += 1
        last[n.pitch] = n
    return cut


def fit_range(inst, instrument):
    """Move the whole part by octaves into the instrument's range. Returns the shift in octaves."""
    lo, hi = (pretty_midi.note_name_to_number(x) for x in RANGES[instrument])
    a, b = min(n.pitch for n in inst.notes), max(n.pitch for n in inst.notes)
    for k in sorted(range(-5, 6), key=lambda k: (abs(k), k)):
        if lo <= a + 12 * k and b + 12 * k <= hi:
            for n in inst.notes:
                n.pitch += 12 * k
            return k
    raise PartError(f"spans {name(a)}-{name(b)}, which no octave shift fits into {instrument} {RANGES[instrument][0]}-{RANGES[instrument][1]}")


def source_track(pm, role):
    names = [i.name for i in pm.instruments]
    hits = [i for i in pm.instruments if i.name.strip().lower() in ROLE_TRACKS[role]]
    if not hits:
        raise PartError(f"no {role} track ({' | '.join(ROLE_TRACKS[role])}) among {names}")
    if len(hits) > 1:
        raise PartError(f"ambiguous {role} role: {[i.name for i in hits]} among {names}")
    return hits[0]


def clips(manifest):
    """{clip id: (asset id, clip)} in manifest order."""
    return {c["id"]: (a["id"], c) for a in manifest["assets"] for c in a["clips"]}


def build(asset, clip):
    """Write the clip's part. Returns a report row, or raises PartError."""
    cid = clip["id"]
    instrument, program, bank, role = INSTRUMENTS[asset]
    if role == "drums":
        if cid not in KITS:
            raise PartError(f"no drum kit for {cid} in KITS")
        program = KITS[cid]
    pm = pretty_midi.PrettyMIDI(os.path.join(ROOT, clip["source"]))
    if abs(pm.get_tempo_changes()[1][0] - BPM) > 1e-6:
        raise PartError(f"{clip['source']} is not at the library tempo {BPM:g}")
    src = source_track(pm, role)
    part = copy.deepcopy(src)
    row = {"clip": cid, "instrument": instrument, "track": src.name, "moved": "-", "rotation": 0,
           "octaves": 0, "csharp": "-", "notes": len(part.notes)}
    if role == "drums":
        if not src.is_drum:
            raise PartError(f"track {src.name!r} is not on the drum channel")
        if src.program != program:
            raise PartError(f"track {src.name!r} plays kit {src.program}, but KITS has {program}")
    elif role == "melody":
        row["melody_cs_outside_v"] = sum(1 for n in part.notes if n.pitch % 12 == CSHARP and chord_at(n.start) != "V")
    else:
        has_cs = any(n.pitch % 12 == CSHARP for n in part.notes)
        best = best_rotation(part) if has_cs else 0
        if has_cs and cid not in ROTATION:
            raise PartError(f"contains C# but has no pinned rotation; best is {best} "
                            f"({v_hits(rotated(part, best))} C# onsets in V): add \"{cid}\": {best} to ROTATION")
        if not has_cs and cid in ROTATION:
            raise PartError(f"has no C# but ROTATION pins {ROTATION[cid]}; remove the entry")
        r = ROTATION.get(cid, 0)
        if r != best:
            print(f"  warning: {cid}: pinned rotation {r}, but {best} now puts more C#s in V windows")
        if r:
            if part.pitch_bends or part.control_changes:
                raise PartError("a rotated part must not carry pitch bends or controllers")
            part = rotated(part, r)
        cs_in = sum(1 for n in part.notes if n.pitch % 12 == CSHARP)
        moved, kept = revoice(part, role)
        row.update(moved=f"{moved}/{len(part.notes)}", rotation=r, csharp=f"{kept}/{cs_in}" if cs_in else "-")
    row["shortened"] = untangle(part)
    row["octaves"] = 0 if role == "drums" else fit_range(part, instrument)
    part.name, part.program, part.is_drum = instrument, program, bank == 128
    out = pretty_midi.PrettyMIDI(initial_tempo=BPM, resolution=960)
    out.instruments.append(part)
    slug = os.path.splitext(os.path.basename(clip["source"]))[0]
    row["file"] = f"{OUT_DIR}/{slug}--{instrument}.mid"
    if clip.get("part") != row["file"]:
        raise PartError(f"manifest part is {clip.get('part')!r}, but the part is {row['file']}")
    os.makedirs(os.path.join(ROOT, OUT_DIR), exist_ok=True)
    out.write(os.path.join(ROOT, row["file"]))
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ids", nargs="*", help="clip ids (default: every clip)")
    a = ap.parse_args()
    with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as f:
        every = clips(json.load(f))
    unknown = [i for i in a.ids if i not in every]
    if unknown:
        sys.exit(f"error: unknown clip id(s): {', '.join(unknown)}")
    rows, skipped, failed = [], [], []
    for cid in a.ids or every:
        asset, clip = every[cid]
        pm = pretty_midi.PrettyMIDI(os.path.join(ROOT, clip["source"]))
        print(f"{cid:13s} {clip['source']}: tracks {[i.name for i in pm.instruments]}")
        role = INSTRUMENTS[asset][3]
        if cid in SKIP:
            try:
                source_track(pm, role)
            except PartError:
                skipped.append((cid, SKIP[cid]))
                continue
            failed.append((cid, f"listed in SKIP, but it has a {role} track now; remove it from SKIP"))
            continue
        try:
            rows.append(build(asset, clip))
        except PartError as e:
            failed.append((cid, str(e)))
    if rows:
        print(f"\n{'clip':13s} {'instrument':10s} {'source track':12s} {'moved':>7s} {'rot':>3s} {'oct':>3s} {'C# kept':>7s}  file")
        for r in rows:
            print(f"{r['clip']:13s} {r['instrument']:10s} {r['track']:12s} {r['moved']:>7s} {r['rotation']:3d} "
                  f"{r['octaves']:+3d} {r['csharp']:>7s}  {r['file']}")
        for r in rows:
            if r["octaves"]:
                print(f"  moved {r['clip']} {r['octaves']:+d} octave(s) to fit the {r['instrument']} range")
            if r["shortened"]:
                print(f"  {r['clip']}: shortened {r['shortened']} note(s) that overlapped a later note of the same pitch")
            if r.get("melody_cs_outside_v"):
                print(f"  note: {r['clip']} melody has {r['melody_cs_outside_v']} C# onset(s) outside V windows (left as written)")
    for cid, why in skipped:
        print(f"skipped {cid}: {why}")
    for cid, why in failed:
        print(f"FAILED  {cid}: {why}")
    print(f"\n{len(rows)} written, {len(skipped)} skipped, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
