#!/usr/bin/env python3
"""Write a gen1recomp mod index feed (index.json) for the mods in this repo.

    python3 tools/make_index.py --repo owner/name --tag v0.2.1 --dist dist \
        --out site/data/index.json [--prerelease] [--channel stable|dev]

The feed is what gen1recomp's MODS -> Find mods tab reads (schema_version 1,
src/mods/ModIndex.lua): one entry per mod with its manifest metadata and a
`latest` release whose zip is the asset tools/package.py built in --dist.
Add the source in the app as `owner/name` (stable feed, site/data/index.json
on main) or as the dev feed's raw URL (site/dev/data/index.json).
"""

import argparse
import datetime
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDIT = "TheSmithPlays & cRz Shadows (Crystal Legacy); port by leonardwohl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", required=True, help="release tag the zips are attached to")
    ap.add_argument("--dist", required=True, help="folder holding <id>-<version>.zip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--prerelease", action="store_true")
    ap.add_argument("--channel", default="stable")
    a = ap.parse_args()
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw = "https://raw.githubusercontent.com/%s/main/" % a.repo
    mods, categories, games = [], set(), set()
    for mdir in sorted(glob.glob(os.path.join(ROOT, "mods", "*", "manifest.json"))):
        man = json.load(open(mdir, encoding="utf-8"))
        mod_id = man["id"]
        zips = glob.glob(os.path.join(a.dist, "%s-*.zip" % mod_id))
        if len(zips) != 1:
            raise SystemExit("%s: expected one zip in %s, found %d" % (mod_id, a.dist, len(zips)))
        zip_path = zips[0]
        zip_name = os.path.basename(zip_path)
        version = zip_name[len(mod_id) + 1:-len(".zip")]
        title = man["name"] + (" (dev)" if a.channel == "dev" else "")
        entry = {
            "folder": "%s@%s" % (a.repo.split("/")[0], mod_id),
            "id": mod_id,
            "title": title,
            "author": CREDIT,
            "version": version,
            "summary": man.get("description", ""),
            "categories": [man["category"]] if man.get("category") else [],
            "games": man.get("games", []),
            "repo": "https://github.com/%s" % a.repo,
            "github": a.repo,
            "api": man.get("api"),
            "game_version": man.get("game_version"),
            "profile": man.get("profile"),
            "permissions": man.get("permissions", []),
            "dependencies": man.get("dependencies", []),
            "conflicts": man.get("conflicts", []),
            "description_url": raw + "mods/%s/README.md" % mod_id,
            "latest": {
                "version": version, "tag": a.tag, "name": a.tag,
                "prerelease": a.prerelease, "published_at": now,
                "zip": {
                    "name": zip_name,
                    "url": "https://github.com/%s/releases/download/%s/%s"
                           % (a.repo, a.tag, zip_name),
                    "size": os.path.getsize(zip_path),
                },
            },
            "update_check": "ok",
        }
        mods.append(entry)
        categories.update(entry["categories"])
        games.update(entry["games"])
    feed = {
        "schema_version": 1, "generated_at": now, "count": len(mods),
        "categories": sorted(categories), "base_games": sorted(games), "mods": mods,
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(feed, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print("wrote %s: %d mods at %s" % (a.out, len(mods), a.tag))


if __name__ == "__main__":
    main()
