#!/usr/bin/env python3
"""Manage the clip library: list and remove. Every change bumps manifest.json's version so phones drop
their saved clip choices.

Clips are rendered instrument parts (one per clip, no stems): a clip is added or replaced by writing its song
(pipeline/arrange/songs.py and manual.py) and running pipeline/arrange/convert.py <slug> --apply, and the
whole library is rendered again by pipeline/arrange/rerender.py. add and replace only say so.

usage:
  library.py list
  library.py remove <clip-id>
      removes the clip's WAV, its part and its manifest entry; refuses to remove an asset's last clip.
All subcommands accept --root DIR (default: this repo).
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prepare_clip import load_manifest, save_manifest, ROOT  # noqa: E402


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
    print(f"{'asset':10s} {'instrument':10s} {'#':>2s} {'clip id':14s} {'bars':>4s} {'title':28s} {'part':52s} file")
    for asset in m["assets"]:
        for i, c in enumerate(asset["clips"]):
            marker = "*" if i == 0 else " "
            print(f"{asset['id']:10s} {asset['instrument']['id']:10s} {i+1:2d}{marker}{c['id']:14s} {c.get('bars', m['bars']):4d} "
                  f"{c['title'][:28]:28s} {c['part'][:52]:52s} {c['file']}")
    print("\n* = default (first) clip of the asset")


def cmd_add(a):
    die("clips are rendered instrument parts now: write the song in pipeline/arrange/songs.py and manual.py, then run\n"
        "pipeline/arrange/convert.py <slug> --apply (it adds the clip, writes its part and renders it)")


cmd_replace = cmd_add


def cmd_remove(a):
    m = load_manifest(a.root)
    asset, idx, old = find_clip(m, a.clip_id)
    if len(asset["clips"]) == 1:
        die(f"'{old['id']}' is the only clip of '{asset['id']}'; replace it instead (every asset needs one clip)")
    asset["clips"].pop(idx)
    gone = remove_file(a.root, old["file"])
    remove_file(a.root, old.get("part", ""))
    v = bump_and_save(m, a.root)
    print(f"removed {old['id']} ('{old['title']}'){' and ' + old['file'] if gone else ''}; "
          f"'{asset['id']}' now has {len(asset['clips'])} clip(s), default {asset['clips'][0]['id']}; manifest version {v}")


def main():
    ap = argparse.ArgumentParser(description="Manage the clip library.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="table of assets and clips"); p.add_argument("--root", default=ROOT)
    sub.add_parser("add", help="retired: use pipeline/arrange/convert.py <slug> --apply")
    sub.add_parser("replace", help="retired: use pipeline/arrange/convert.py <slug> --apply")
    p = sub.add_parser("remove", help="delete a clip's file and manifest entry"); p.add_argument("clip_id"); p.add_argument("--root", default=ROOT)
    a = ap.parse_args()
    {"list": cmd_list, "add": cmd_add, "replace": cmd_replace, "remove": cmd_remove}[a.cmd](a)


if __name__ == "__main__":
    main()
