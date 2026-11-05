#!/usr/bin/env python3
"""Zip each mod for gen1recomp's MODS -> Import mod .zip.

    python3 tools/package.py [--out dist] [--version 0.2.0] [mod id ...]

Writes dist/<id>-<version>.zip with manifest.json at the zip root, which is
the layout gen1recomp imports and the asset name its updater looks for.
With --version, every manifest must already carry that version (CI passes
the release tag, so a tag and the manifests can never disagree).
"""

import argparse
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # reproducible zips


def package(mod_id, out_dir, want_version=None):
    src = os.path.join(ROOT, "mods", mod_id)
    with open(os.path.join(src, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    version = manifest["version"]
    if want_version and version != want_version:
        sys.exit("%s: manifest version %s does not match %s" % (mod_id, version, want_version))
    path = os.path.join(out_dir, "%s-%s.zip" % (mod_id, version))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                full = os.path.join(dirpath, name)
                info = zipfile.ZipInfo(os.path.relpath(full, src).replace(os.sep, "/"), FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(full, "rb") as fh:
                    zf.writestr(info, fh.read())
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--version")
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args()
    ids = a.ids or sorted(d for d in os.listdir(os.path.join(ROOT, "mods"))
                          if os.path.isfile(os.path.join(ROOT, "mods", d, "manifest.json")))
    os.makedirs(a.out, exist_ok=True)
    for mod_id in ids:
        print(package(mod_id, a.out, a.version.lstrip("v") if a.version else None))


if __name__ == "__main__":
    main()
