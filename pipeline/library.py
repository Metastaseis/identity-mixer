#!/usr/bin/env python3
"""Manage the clip library: list, add, replace, remove. Every change bumps
manifest.json's version so phones drop their saved clip choices.

usage:
  library.py list
  library.py add <source> --asset <id> --title <t> [--bpm N] [--key K] [--start S] [--bars N] [--tempo-ratio R]
                 [--note TEXT] [--credit TEXT] [--fade MS]
  library.py add --midi <file.mid> --asset <id> --title <t> [--bars N] [--note TEXT] [--credit TEXT] [--fade MS]
  library.py replace <clip-id> <source> [--title <t>] [--bpm N] [--key K] [--start S] [--bars N] [--tempo-ratio R]
                 [--note TEXT] [--credit TEXT] [--fade MS]
  library.py replace <clip-id> --midi <file.mid> [--title <t>] [--bars N] [--note TEXT] [--credit TEXT] [--fade MS]
      prepares the source, then removes the old clip's file and manifest entry.
      The clip keeps its id and its position in the picker.
      --midi renders the file with render_midi.py at the manifest tempo instead of
      preparing a recording: no detection, no stretch, no shift; the exact-length,
      loudness and export steps still run. Default fade is 0 ms for MIDI.
  library.py remove <clip-id>
      refuses to remove an asset's last clip (the manifest needs one per asset).
All subcommands accept --root DIR (default: this repo).
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prepare_clip import prepare, load_manifest, save_manifest, add_args, PrepareError, ROOT  # noqa: E402


def die(msg):
    sys.exit(f"error: {msg}")


def find_clip(m, clip_id):
    for a in m["assets"]:
        for i, c in enumerate(a["clips"]):
            if c["id"] == clip_id:
                return a, i, c
    die(f"no clip '{clip_id}' in the manifest")


def remove_file(root, rel):
    full = os.path.join(root, rel)
    if os.path.isfile(full):
        os.remove(full)
        return True
    return False


def bump_and_save(m, root):
    m["version"] += 1
    save_manifest(m, os.path.join(root, "manifest.json"))
    return m["version"]


def cmd_list(a):
    m = load_manifest(a.root)
    print(f"library v{m['version']}: {m['tempo']} BPM, {m['key']}, {m['bars']} bars default, {m['beats_per_bar']}/4\n")
    print(f"{'asset':10s} {'name':16s} {'#':>2s} {'clip id':14s} {'bars':>4s} {'title':28s} {'source':32s} file")
    for asset in m["assets"]:
        for i, c in enumerate(asset["clips"]):
            marker = "*" if i == 0 else " "
            print(f"{asset['id']:10s} {asset['name']:16s} {i+1:2d}{marker}{c['id']:14s} {c.get('bars', m['bars']):4d} "
                  f"{c['title'][:28]:28s} {c['source'][:32]:32s} {c['file']}")
    print("\n* = default (first) clip of the asset")


def prep_kwargs(a):
    return dict(midi=a.midi, bpm=a.bpm, key=a.key, start=a.start, bars=a.bars, tempo_ratio=a.tempo_ratio,
                note=a.note, credit=a.credit, fade=a.fade, root=a.root)


def cmd_add(a):
    m = load_manifest(a.root)
    try:
        entry, m = prepare(a.source, a.asset, a.title, manifest=m, **prep_kwargs(a))
    except PrepareError as e:
        die(str(e))
    asset = next(x for x in m["assets"] if x["id"] == a.asset)
    asset["clips"].append(entry)
    v = bump_and_save(m, a.root)
    print(f"\nadded {entry['id']} to '{a.asset}' as clip #{len(asset['clips'])}; manifest version {v}")


def cmd_replace(a):
    m = load_manifest(a.root)
    asset, idx, old = find_clip(m, a.clip_id)
    title = a.title or old["title"]
    if not a.note and old.get("note"):
        a.note = old["note"]
    if not a.credit and old.get("credit") and old["source"] != "prototype-synth":
        a.credit = old["credit"]
    try:
        entry, m = prepare(a.source, asset["id"], title, manifest=m, clip_id=old["id"], **prep_kwargs(a))
    except PrepareError as e:
        die(str(e))
    if old["file"] != entry["file"]:
        remove_file(a.root, old["file"])
    asset["clips"][idx] = entry
    v = bump_and_save(m, a.root)
    print(f"\nreplaced {old['id']} (was '{old['title']}' from {old['source']}) in place as clip #{idx+1} of '{asset['id']}'; manifest version {v}")


def cmd_remove(a):
    m = load_manifest(a.root)
    asset, idx, old = find_clip(m, a.clip_id)
    if len(asset["clips"]) == 1:
        die(f"'{old['id']}' is the only clip of '{asset['id']}'; replace it instead (every asset needs one clip)")
    asset["clips"].pop(idx)
    gone = remove_file(a.root, old["file"])
    v = bump_and_save(m, a.root)
    print(f"removed {old['id']} ('{old['title']}'){' and ' + old['file'] if gone else ''}; "
          f"'{asset['id']}' now has {len(asset['clips'])} clip(s), default {asset['clips'][0]['id']}; manifest version {v}")


def main():
    ap = argparse.ArgumentParser(description="Manage the clip library.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="table of assets and clips"); p.add_argument("--root", default=ROOT)
    p = sub.add_parser("add", help="prepare a source (or render --midi) and append it to an asset")
    p.add_argument("source", nargs="?", help="source recording (omit with --midi)")
    p.add_argument("--asset", required=True); p.add_argument("--title", required=True); add_args(p)
    p = sub.add_parser("replace", help="prepare a source (or render --midi) into an existing clip id, keeping its position")
    p.add_argument("clip_id"); p.add_argument("source", nargs="?", help="source recording (omit with --midi)")
    p.add_argument("--title"); add_args(p)
    p = sub.add_parser("remove", help="delete a clip's file and manifest entry"); p.add_argument("clip_id"); p.add_argument("--root", default=ROOT)
    a = ap.parse_args()
    {"list": cmd_list, "add": cmd_add, "replace": cmd_replace, "remove": cmd_remove}[a.cmd](a)


if __name__ == "__main__":
    main()
