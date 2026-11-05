#!/usr/bin/env python3
"""Build mods/crystal_legacy_story from Crystal Legacy's map scripts.

    python3 tools/story/build_story.py --base <pokecrystal@82e315e48, built> \
        --legacy <Crystal Legacy> --rgbds <dir> --engine <gen1recomp checkout> \
        --work <scratch dir>

Pipeline (everything ROM-derived stays in --work):
  1. assemble.py: Legacy's map files, assembled against vanilla numbering.
  2. patch_rom.py: a scratch vanilla ROM with those banks and the maps
     repointed at them.
  3. extract_story.lua: gen1recomp's own importer decodes it; only the Legacy
     banks' scripts, text and movements and the maps' event records are kept.
  4. This script adds the new trainer classes, their teams and art, and
     writes the mod.
--base must contain pokecrystal.gbc / pokecrystal.sym (run `make` there).
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import assemble  # noqa: E402
import sprites as SP  # noqa: E402
import legacy_diff as D  # noqa: E402
import build as B  # noqa: E402

MOD_ID = "crystal_legacy_story"

# Every map Crystal Legacy changed is ported, except the ones whose scripts
# another mod already rewrites (porting both would double up rematch offers
# and badge switches), and the Move Deleter's house, whose Move Reminder is
# new engine code gen1recomp has no counterpart for.
EXCLUDE = {
    # Rematches / Trainer Changes / Hard Mode (Johto gyms, Elite Four)
    "VioletGym", "AzaleaGym", "GoldenrodGym", "EcruteakGym", "MahoganyGym",
    "OlivineGym", "CianwoodGym", "BlackthornGym1F",
    "WillsRoom", "KogasRoom", "BrunosRoom", "KarensRoom", "LancesRoom",
    # Shop Changes
    "CeladonDeptStore3F", "CeladonDeptStore5F",
    # Move Reminder (no gen1recomp counterpart yet)
    "MoveDeletersHouse",
}
EVENT_IDS = os.path.join(HERE, "event_ids.json")
SPRITE_IDS = os.path.join(HERE, "sprite_ids.json")


def gen1recomp_map_ids(base, engine):
    """pokecrystal map constant -> gen1recomp map id, matched by (group, number).

    gen1recomp names maps after a newer pokecrystal (DANCE_THEATER, not
    DANCE_THEATRE), so names are matched through the numbers both share.
    """
    import re as _re
    by_num, group, num = {}, 0, 0
    for line in open(os.path.join(base, "constants/map_constants.asm")):
        line = line.split(";")[0]
        if "MACRO" in line:
            continue
        if _re.match(r"\s*newgroup\b", line):
            group, num = group + 1, 0
        m = _re.match(r"\s*map_const\s+(\w+)", line)
        if m:
            num += 1
            by_num[m.group(1)] = (group, num)
    manifest = json.load(open(os.path.join(engine, "tools/rom_manifest_crystal.json")))
    names = {(g["group"], g["map"]): g["name"] for g in manifest["constants"]["mapGroups"]}
    return {const: names[gm] for const, gm in by_num.items() if gm in names}


def story_maps(base, legacy, engine):
    """{Legacy map file: gen1recomp map id} for every changed, non-excluded map."""
    consts = B._legacy_map_constants(base)
    rename = gen1recomp_map_ids(base, engine)
    ids = {f: rename[c] for f, c in consts.items() if c in rename}
    out = {}
    for f in sorted(os.listdir(os.path.join(legacy, "maps"))):
        if not f.endswith(".asm") or f[:-4] in EXCLUDE:
            continue
        a, b = os.path.join(base, "maps", f), os.path.join(legacy, "maps", f)
        if os.path.exists(a) and open(a, "rb").read() != open(b, "rb").read():
            out[f[:-4]] = ids[f[:-4]]
    return out

# New trainer classes: index (as assemble.LEGACY_ONLY), display name, the
# Legacy art, and the vanilla class whose music / AI / prize money they borrow.
NEW_CLASSES = [
    {"id": "BOSS", "name": "BOSS", "pic": "boss", "like": "EXECUTIVEM"},
    {"id": "ROCKET_LEADER", "name": "ROCKET", "pic": "archer", "like": "EXECUTIVEM"},
    {"id": "PKMNTRAINERF", "name": "PKMN TRAINER", "pic": "pkmntrainerf",
     "palette_from": "cal", "like": "CAL"},
]

# Legacy's fossils take vanilla's unused item slots $93-$95 (ITEM_93..95 in
# gen1recomp), as they do in Legacy. data/items/{names,descriptions,attributes}.asm.
FOSSILS = {
    "ITEM_93": {"name": "OLD AMBER", "description": "Fossilized resin<NEXT>containing DNA."},
    "ITEM_94": {"name": "DOME FOSSIL", "description": "A fossilized<NEXT>POKéMON shell."},
    "ITEM_95": {"name": "HELIX FOSSIL", "description": "A fossilized<NEXT>POKéMON shell."},
}
for _f in FOSSILS.values():
    _f.update({"price": 0, "pocket": "KEY_ITEM", "pocketId": 2, "canToss": False,
               "canSelect": False})

# Parties the Story maps load from existing classes, by Legacy member index.
EXTRA_PARTIES = [("CAL", 3), ("CAL", 4), ("RED", 2)]


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("%s failed:\n%s%s" % (cmd[0], r.stdout[-3000:], r.stderr[-3000:]))
    return r.stdout


def colour_pic(src, out, palette_src=None):
    """Legacy's 4-shade trainer art -> a true-colour PNG with its own palette."""
    from PIL import Image
    im = Image.open(src)
    pal_im = Image.open(palette_src) if palette_src else im
    pal = pal_im.getpalette()[:12]
    colours = [tuple(pal[i:i + 3]) for i in range(0, 12, 3)]
    grey = im.convert("L")
    shades = sorted(set(grey.tobytes()), reverse=True)  # white .. black
    rgb = Image.new("RGB", im.size)
    rgb.putdata([colours[min(shades.index(v), 3)] for v in grey.tobytes()])
    rgb.save(out)


def main():
    ap = argparse.ArgumentParser()
    for k in ("base", "legacy", "rgbds", "engine", "work"):
        ap.add_argument("--" + k, required=True)
    a = ap.parse_args()
    MAPS = story_maps(a.base, a.legacy, a.engine)
    files = list(MAPS)
    mod_dir = os.path.join(ROOT, "mods", MOD_ID)
    # Sprite numbers are stored in saves (variable sprite slots): pinned too.
    pinned_sprites = json.load(open(SPRITE_IDS)) if os.path.exists(SPRITE_IDS) else {}
    sprite_defs, sprite_records, sprite_order = SP.port(
        a.base, a.legacy, files, os.path.join(mod_dir, "assets"), pinned_sprites)
    with open(SPRITE_IDS, "w") as fh:
        json.dump(dict(pinned_sprites, **sprite_defs), fh, indent=2, sort_keys=True)
        fh.write("\n")
    # Event ids are stored in saves, so once given out they never change.
    pinned = json.load(open(EVENT_IDS)) if os.path.exists(EVENT_IDS) else {}
    r = assemble.build(a.base, a.legacy, a.rgbds, a.work, files,
                       dict(sprite_defs, **pinned))
    events = dict(pinned, **r["newEvents"])
    with open(EVENT_IDS, "w") as fh:
        json.dump(events, fh, indent=2, sort_keys=True)
        fh.write("\n")
    r["newEvents"] = events
    patched = os.path.join(a.work, "patched.gbc")
    run([sys.executable, "-I", os.path.join(HERE, "patch_rom.py"), "--base", a.base,
         "--work", a.work, "--rom", "pokecrystal.gbc", "--out", patched] + files)
    sha = run(["sha1sum", os.path.join(a.base, "pokecrystal.gbc")]).split()[0]
    story_lua = os.path.join(a.work, "story.lua")
    os.environ["CL_SPRITE_ORDER"] = ",".join("%d=%s" % kv for kv in sorted(sprite_order.items()))
    print(run(["luajit", os.path.join(HERE, "extract_story.lua"), patched, sha, story_lua]
              + list(MAPS.values()), cwd=a.engine).strip())
    dump = run(["luajit", "-e", 'package.path="./?.lua;"..package.path '
                'local Json=require("src.link.Json") '
                'io.write(Json.encode(dofile(%s)))' % json.dumps(story_lua)], cwd=a.engine)
    story = json.loads(dump)

    # Trainer data from Legacy's parties.asm (same parser as Trainer Changes).
    report = {"notes": []}
    rows, extras = D.diff_trainers(a.base, a.legacy, report)
    classes, parties = [], []
    legacy_parties = D.parse.trainer_parties(a.legacy)
    D.resolve_moves(a.legacy, legacy_parties, report)

    def party_rows(cls):
        out = []
        for i, pt in enumerate(legacy_parties[cls]["parties"], 1):
            party = [{k: m[k] for k in ("level", "species", "item", "moves") if k in m}
                     for m in pt["party"]]
            out.append({"index": i, "name": pt["name"], "party": party,
                        "trainerType": D.TRAINERTYPE[("item" in pt["flags"], "moves" in pt["flags"])]})
        return out

    extra_fields = {}
    for c in NEW_CLASSES:
        pic = "%s.png" % c["pic"]
        pal = os.path.join(a.base, "gfx/trainers/%s.png" % c["palette_from"]) \
            if c.get("palette_from") else None
        colour_pic(os.path.join(a.legacy, "gfx/trainers", pic),
                   os.path.join(mod_dir, "assets", pic), pal)
        trs = party_rows(c["id"])
        for t in trs:
            t["id"] = "%s%d" % (c["id"], t["index"])
        classes.append({"id": c["id"], "index": assemble.LEGACY_ONLY[c["id"]],
                        "name": c["name"], "pic": "assets/" + pic, "like": c["like"],
                        "trainers": trs})
    for cls, idx in EXTRA_PARTIES:
        row = next(t for t in party_rows(cls) if t["index"] == idx)
        row["id"] = legacy_parties[cls]["members"][idx - 1] \
            if idx <= len(legacy_parties[cls]["members"]) else "%s_STORY%d" % (cls, idx)
        parties.append({"class": cls, "row": row})
    for cls, by in extras.items():
        for idx, slots in by.items():
            if any(c["id"] == cls for c in NEW_CLASSES) or (cls, idx) in EXTRA_PARTIES:
                extra_fields.setdefault(cls, {})[idx] = slots

    EVENT_FIELDS = ("objects", "bgEvents", "coordEvents", "sceneScripts", "callbacks", "warps")
    data = {
        "scripts": story["scripts"], "movements": story["movements"], "text": story["text"],
        "maps": {mid: {k: story["maps"][mid][k] for k in EVENT_FIELDS if k in story["maps"][mid]}
                 for mid in MAPS.values()},
        "classes": classes, "parties": parties, "extras": extra_fields,
        "newEvents": r["newEvents"],
        "items": FOSSILS,
        "sprites": sprite_records,
        "spriteOrder": {str(k): v for k, v in sprite_order.items()},
    }
    write_mod(mod_dir, data)
    print("events reused:", r["newEvents"])
    print("sprites:", {v: hex(k) for k, v in sprite_order.items()})
    for n in report["notes"]:
        print("note:", n)


RUNTIME = r'''
local function copy(v)
  if type(v) ~= "table" then return v end
  local out = {}
  for k, x in pairs(v) do out[k] = copy(x) end
  return out
end

local function register(mod, reg, id, value, stats)
  local r = mod.content[reg]
  local ok, err = pcall(r.has and r:has(id) and r.override or r.register, r, id, value)
  if ok then stats.applied = stats.applied + 1 else
    stats.failed = stats.failed + 1
    mod.log:warn("%s %s: %s", reg, tostring(id), tostring(err))
  end
end

-- Lua's JSON round trip turns sparse integer maps into string keys; give
-- scene ids, trainer indices and DV slots their numbers back.
local function numberKeys(t)
  if type(t) ~= "table" then return t end
  local out = {}
  for k, v in pairs(t) do out[tonumber(k) or k] = numberKeys(v) end
  return out
end
'''


def write_mod(mod_dir, data):
    manifest = {
        "id": MOD_ID, "name": "Crystal Legacy: Story Changes", "version": B.VERSION, "api": 2,
        "games": ["crystal"], "entry": "main.lua", "profile": "content", "category": "CONTENT",
        "game_version": B.GAME_VERSION, "priority": 100, "dependencies": [],
        "optional_dependencies": ["crystal_legacy_trainers", "crystal_legacy_rematches",
                                  "crystal_legacy_shops"],
        "conflicts": [], "permissions": [],
        "description": "Crystal Legacy's story changes, starting with the Trainer House "
                       "trio, Archer and the Silver Cave Mewtwo / Red rematch. "
                       "Unofficial port of Pokemon Crystal Legacy.",
        "github": B.GITHUB,
    }
    with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    body = r'''
return function(mod)
  local stats = { applied = 0, failed = 0 }
  local scripts, maps = numberKeys(DATA.scripts), numberKeys(DATA.maps)

  -- 0. Legacy's new overworld sprites, on sprite numbers vanilla leaves free.
  for _, rec in ipairs(DATA.sprites) do
    local r = copy(rec)
    r.image = mod.path .. "/" .. rec.image
    register(mod, "sprites", rec.id, r, stats)
  end
  local order = mod.content.constants:get("spriteOrder")
  if order then
    for num, name in pairs(numberKeys(DATA.spriteOrder)) do order[num] = name end
    patch(mod, "constants", "spriteOrder", order, stats)
  end

  -- Legacy's fossils, on vanilla's unused item slots.
  each(DATA.items, function(id, fields)
    if mod.content.items:get(id) then patch(mod, "items", id, fields, stats) end
  end)

  -- 1. Legacy's text, movements and scripts, under their own (bank $80+) keys.
  each(DATA.text, function(id, s) register(mod, "text", id, s, stats) end)
  each(DATA.movements, function(id, bytes)
    register(mod, "map_scripts", "movement:" .. id, bytes, stats)
  end)
  each(scripts, function(id, rows) register(mod, "map_scripts", id, rows, stats) end)

  -- 2. New trainer classes, borrowing music / AI / money from a vanilla one.
  for _, c in ipairs(DATA.classes) do
    local like = mod.content.trainers:get(c.like) or {}
    local rec = { id = c.id, index = c.index, name = c.name,
      pic = mod.path .. "/" .. c.pic, trueColor = true,
      baseMoney = like.baseMoney, attributes = copy(like.attributes),
      items = copy(like.items or {}), encounterMusic = like.encounterMusic,
      trainers = copy(c.trainers) }
    register(mod, "trainers", c.id, rec, stats)
  end

  -- 3. Parties the story loads from existing classes (Trainer House Smith and
  --    Craig, Red's rematch), at the member index Legacy's scripts use.
  for _, p in ipairs(DATA.parties) do
    local rec = mod.content.trainers:get(p.class)
    if rec and rec.trainers then
      local list, row = rec.trainers, copy(p.row)
      if row.index > #list + 1 then
        mod.log:warn("%s: cannot place member %d after %d", p.class, row.index, #list)
        stats.failed = stats.failed + 1
      else
        list[row.index] = row
        patch(mod, "trainers", p.class, { trainers = list }, stats)
      end
    end
  end

  -- 4. The maps' events now point at Legacy's scripts.
  -- (Every map exists in a real Crystal import; a test dataset may hold fewer.)
  each(maps, function(id, fields)
    if mod.content.maps:get(id) then
      patch(mod, "maps", id, fields, stats)
    else
      mod.log:info("map %s not in this dataset; skipped", id)
    end
  end)

  -- Custom DVs / stat exp on story teams (Trainer House, Red).
  local extras = numberKeys(DATA.extras)
  if next(extras) then
    mod.hooks:wrap("trainer.party", function(nextFn, class, member, party)
      party = nextFn(class, member, party)
      local rec = mod.content.trainers:get(class)
      local index
      for i, t in ipairs(rec and rec.trainers or {}) do
        if t.id == member then index = i break end
      end
      local slots = extras[class] and extras[class][index]
      if slots and type(party) == "table" then
        for slot, extra in pairs(slots) do
          local mon = party[slot]
          if mon then
            if extra.dvs then mon.dvs = extra.dvs end
            if extra.statExp then mon.statExp = extra.statExp end
          end
        end
      end
      return party
    end)
  end
  mod.log:info("Crystal Legacy: Story Changes: %d applied, %d refused", stats.applied, stats.failed)
end
'''
    with open(os.path.join(mod_dir, "main.lua"), "w", encoding="utf-8") as fh:
        fh.write("-- GENERATED by tools/story/build_story.py -- edit the builder, not this file.\n")
        fh.write("-- Crystal Legacy's story scripts, decoded by gen1recomp's own importer.\n")
        fh.write("\nlocal DATA = " + D.lua(data) + "\n" + B.PRELUDE + RUNTIME + body)


if __name__ == "__main__":
    main()
