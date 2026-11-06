#!/usr/bin/env python3
"""Zip each mod for gen1recomp's MODS -> Import mod .zip.

    python3 tools/package.py [--out dist] [--version 0.2.0] [mod id ...]

Writes dist/<id>-<version>.zip with manifest.json at the zip root, which is
the layout gen1recomp imports and the asset name its updater looks for.
With --version, every manifest must already carry that version (CI passes
the release tag, so a tag and the manifests can never disagree). With --dev N
the zips are stamped <next patch>-dev.N instead, for the rolling dev channel.
"""

import argparse
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # reproducible zips


def package(mod_id, out_dir, want_version=None, set_version=None):
    src = os.path.join(ROOT, "mods", mod_id)
    with open(os.path.join(src, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    version = manifest["version"]
    if set_version:
        # Dev builds: stamp the zip's manifest (and name) with a build version.
        version = manifest["version"] = set_version
    elif want_version and version != want_version:
        sys.exit("%s: manifest version %s does not match %s" % (mod_id, version, want_version))
    path = os.path.join(out_dir, "%s-%s.zip" % (mod_id, version))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, src).replace(os.sep, "/")
                info = zipfile.ZipInfo(rel, FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                if rel == "manifest.json" and set_version:
                    zf.writestr(info, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
                    continue
                with open(full, "rb") as fh:
                    zf.writestr(info, fh.read())
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--version")
    ap.add_argument("--dev", type=int, metavar="BUILD",
                    help="dev build: version becomes <next patch>-dev.BUILD")
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args()
    ids = a.ids or sorted(d for d in os.listdir(os.path.join(ROOT, "mods"))
                          if os.path.isfile(os.path.join(ROOT, "mods", d, "manifest.json")))
    os.makedirs(a.out, exist_ok=True)
    for mod_id in ids:
        dev = None
        if a.dev is not None:
            with open(os.path.join(ROOT, "mods", mod_id, "manifest.json"), encoding="utf-8") as fh:
                major, minor, patch = (int(x) for x in json.load(fh)["version"].split("-")[0].split("."))
            # semver: 0.2.2-dev.N sorts after the 0.2.1 release, before 0.2.2.
            dev = "%d.%d.%d-dev.%d" % (major, minor, patch + 1, a.dev)
        print(package(mod_id, a.out, a.version.lstrip("v") if a.version else None, dev))


if __name__ == "__main__":
    main()
