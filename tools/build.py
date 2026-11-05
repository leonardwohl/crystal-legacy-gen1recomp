#!/usr/bin/env python3
"""Generate every mod under mods/ from a Crystal Legacy checkout.

    python3 tools/build.py --base <pokecrystal@82e315e48> --legacy <Crystal Legacy>

Each mod is self-contained (gen1recomp mods cannot load each other's files),
so the small Lua runtime below is written into every generated main.lua.
Hand-written mods (no `data` builder here) are left alone.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legacy_diff as D  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "0.2.0"
GAME_VERSION = ">=0.4.0 <0.5.0"
GITHUB = "leonardwohl/crystal-legacy-gen1recomp"

PRELUDE = r'''
-- Patch one record, logging instead of aborting when gen1recomp refuses it,
-- so a single bad record never takes the rest of the mod down with it.
local function patch(mod, registry, id, fields, stats)
  local reg = mod.content[registry]
  if not reg then
    mod.log:warn("registry %s is not available; skipped %s", registry, tostring(id))
    stats.failed = stats.failed + 1
    return
  end
  local ok, result, reason = pcall(reg.patch, reg, id, fields)
  if not ok or (result == nil and reason ~= nil) then
    mod.log:warn("%s %s: %s", registry, tostring(id), tostring(ok and reason or result))
    stats.failed = stats.failed + 1
  else
    stats.applied = stats.applied + 1
  end
end

-- Deterministic iteration, so load order (and any warnings) is reproducible.
local function each(map, fn)
  local keys = {}
  for k in pairs(map) do keys[#keys + 1] = k end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  for _, k in ipairs(keys) do fn(k, map[k]) end
end

-- Write custom DVs / stat exp / happiness onto a built trainer party.
-- gen1recomp gives trainer mons the vanilla fixed DVs; this hook runs before
-- the battle computes stats, so the values here are what the battle uses.
local function wrapTrainerExtras(mod, extras, memberIndex)
  if next(extras) == nil then return end
  mod.hooks:wrap("trainer.party", function(nextFn, class, member, party)
    party = nextFn(class, member, party)
    local index = type(member) == "string" and memberIndex[member] or member
    local slots = extras[class] and extras[class][index]
    if slots and type(party) == "table" then
      for slot, extra in pairs(slots) do
        local mon = party[slot]
        if mon then
          if extra.dvs then mon.dvs = extra.dvs end
          if extra.statExp then mon.statExp = extra.statExp end
          if extra.happiness then mon.happiness = extra.happiness end
        end
      end
    end
    return party
  end)
end
'''


# ----------------------------------------------------------- mod builders
# Each returns (data table, Lua apply body, summary lines for the README).

def build_pokemon(ctx):
    pk = {sp: {k: v for k, v in p.items() if k != "eggSteps"}
          for sp, p in ctx["pokemon"].items()}
    pk = {sp: p for sp, p in pk.items() if p}
    data = {"pokemon": pk, "moves": ctx["moves"]}
    body = '''
  each(DATA.pokemon, function(id, fields)
    if mod.content.pokemon:get(id) then patch(mod, "pokemon", id, fields, stats) end
  end)
  each(DATA.moves, function(id, fields)
    if mod.content.moves:get(id) then patch(mod, "moves", id, fields, stats) end
  end)'''
    fields = {}
    for p in pk.values():
        for k in p:
            fields[k] = fields.get(k, 0) + 1
    names = {"baseStats": "base stats", "levelMoves": "level-up learnsets",
             "tmhm": "TM/HM compatibility", "tutorMoves": "move tutor compatibility",
             "evolutions": "evolutions", "eggMoves": "egg moves", "types": "types",
             "catchRate": "catch rates", "baseExp": "base experience",
             "growthRate": "growth rates", "genderRatio": "gender ratios",
             "eggGroups": "egg groups", "items": "wild held items"}
    lines = ["%d Pokémon changed:" % len(pk)]
    lines += ["  - %s: %d species" % (names.get(k, k), n) for k, n in sorted(fields.items())]
    lines.append("%d moves changed (power, accuracy, PP, type or effect)" % len(ctx["moves"]))
    return data, body, lines


def build_trainers(ctx):
    rows, extras = ctx["trainersVanilla"], ctx["extrasVanilla"]
    data = {"trainers": rows, "extras": extras,
            "memberIndex": {r["id"]: r["index"] for rs in rows.values() for r in rs}}
    body = '''
  each(DATA.trainers, function(class, rows)
    patch(mod, "trainers", class, { trainers = rows }, stats)
  end)
  wrapTrainerExtras(mod, DATA.extras, DATA.memberIndex)'''
    n = sum(len(r) for r in rows.values())
    return data, body, ["%d trainer classes, %d parties rewritten to Crystal Legacy's teams" % (
        len(rows), n), "Held items and movesets included; custom DVs/stat exp where Legacy sets them"]


def build_encounters(ctx):
    enc = ctx["encounters"]
    data = {"encounters": enc}
    body = '''
  each(DATA.encounters, function(kind, value)
    if kind == "bugContest" then
      local reg = mod.content.encounters
      local ok, err = pcall(reg.override, reg, kind, value)
      if ok then stats.applied = stats.applied + 1 else
        stats.failed = stats.failed + 1
        mod.log:warn("encounters bugContest: %s", tostring(err))
      end
    else
      patch(mod, "encounters", kind, value, stats)
    end
  end)'''
    return data, body, [
        "%d grass encounter tables (morning, day and night)" % len(enc.get("grass", {})),
        "%d water encounter tables" % len(enc.get("water", {})),
        "Bug-Catching Contest: %s" % ("changed" if "bugContest" in enc else "unchanged in Crystal Legacy"),
        "Headbutt trees and Rock Smash: unchanged in Crystal Legacy, so nothing to apply"]


def build_fast_eggs(ctx):
    steps = {sp: p["eggSteps"] for sp, p in ctx["pokemon"].items() if "eggSteps" in p}
    data = {"eggSteps": steps}
    body = '''
  each(DATA.eggSteps, function(id, steps)
    if mod.content.pokemon:get(id) then
      patch(mod, "pokemon", id, { eggSteps = steps }, stats)
    end
  end)'''
    return data, body, ["Egg hatch cycles cut to about a quarter for all %d species, using "
                        "Crystal Legacy's exact values" % len(steps)]


def build_ghost_dark(ctx):
    data = {"categories": {"GHOST": "special", "DARK": "physical"}}
    body = '''
  each(DATA.categories, function(id, category)
    patch(mod, "type_chart", id, { category = category }, stats)
  end)'''
    return data, body, ["Ghost-type moves use Special Attack / Special Defense",
                        "Dark-type moves use Attack / Defense"]


def build_shops(ctx):
    data = {"marts": ctx["marts"], "items": ctx["items"]}
    body = '''
  each(DATA.items, function(id, fields)
    if mod.content.items:get(id) then patch(mod, "items", id, fields, stats) end
  end)
  each(DATA.marts, function(id, items) patch(mod, "marts", id, items, stats) end)'''
    return data, body, ["%d shops restocked" % len(ctx["marts"]),
                        "%d item prices changed" % len(ctx["items"]),
                        "Crystal Legacy's 5 new shops are not in yet (they need clerk scripts)"]


MODS = [
    {"id": "crystal_legacy_pokemon", "name": "Crystal Legacy: Pokémon Changes",
     "category": "BALANCE", "games": ["crystal"], "build": build_pokemon,
     "summary": "Crystal Legacy's base stats, learnsets, TM/HM and egg moves, "
                "evolutions and move changes."},
    {"id": "crystal_legacy_trainers", "name": "Crystal Legacy: Trainer Changes",
     "category": "BALANCE", "games": ["crystal"], "build": build_trainers,
     "summary": "Every trainer, gym leader and Elite Four team rebuilt as in Crystal Legacy."},
    {"id": "crystal_legacy_encounters", "name": "Crystal Legacy: Encounter Changes",
     "category": "CONTENT", "games": ["crystal"], "build": build_encounters,
     "summary": "Crystal Legacy's wild Pokémon: grass, surfing and the Bug-Catching Contest."},
    {"id": "fast_eggs", "name": "Fast Eggs", "category": "QOL", "games": ["gen2"],
     "build": build_fast_eggs,
     "summary": "Eggs hatch in about a quarter of the steps, as in Crystal Legacy."},
    {"id": "crystal_legacy_ghost_dark", "name": "Crystal Legacy: Ghost/Dark Switch",
     "category": "BALANCE", "games": ["gen2"], "build": build_ghost_dark,
     "summary": "Ghost moves become special and Dark moves physical, as in Crystal Legacy."},
    {"id": "crystal_legacy_shops", "name": "Crystal Legacy: Shop Changes",
     "category": "BALANCE", "games": ["crystal"], "build": build_shops,
     "summary": "Crystal Legacy's shop stock and item prices."},
]


def context(base, leg):
    report = {"notes": []}
    ctx = {"report": report,
           "pokemon": D.diff_pokemon(base, leg, report),
           "moves": D.diff_moves(base, leg, report),
           "items": D.diff_items(base, leg, report)}
    ctx["marts"] = {k: v["items"] for k, v in D.diff_marts(base, leg, report).items()}
    rows, extras = D.diff_trainers(base, leg, report)
    vanilla_counts = {c: len(v["parties"]) for c, v in D.parse.trainer_parties(base).items()}
    ctx["trainersAll"], ctx["extrasAll"] = rows, extras
    ctx["trainersVanilla"] = {}
    for c, rs in rows.items():
        keep = [r for r in rs if r["index"] <= vanilla_counts.get(c, 0)]
        b_rows = D.parse.trainer_parties(base)[c]["parties"]
        if any(r["party"] != _plain(b_rows[r["index"] - 1]["party"]) or
               r["name"] != b_rows[r["index"] - 1]["name"] for r in keep):
            ctx["trainersVanilla"][c] = keep
    ctx["extrasVanilla"] = {c: {i: s for i, s in v.items() if i <= vanilla_counts.get(c, 0)}
                            for c, v in extras.items()}
    ctx["extrasVanilla"] = {c: v for c, v in ctx["extrasVanilla"].items() if v}
    ctx["encounters"] = D.diff_encounters(base, leg, report)
    return ctx


def _plain(party):
    return [{k: m[k] for k in ("level", "species", "item", "moves") if k in m} for m in party]


def write_mod(spec, ctx):
    data, body, lines = spec["build"](ctx)
    d = os.path.join(ROOT, "mods", spec["id"])
    os.makedirs(d, exist_ok=True)
    manifest = {
        "id": spec["id"], "name": spec["name"], "version": VERSION, "api": 2,
        "games": spec["games"], "entry": "main.lua", "profile": "content",
        "category": spec["category"], "game_version": GAME_VERSION, "priority": 100,
        "dependencies": [], "optional_dependencies": [], "conflicts": [],
        "description": spec["summary"] + " Unofficial port of Pokémon Crystal Legacy.",
        "github": GITHUB,
    }
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(os.path.join(d, "main.lua"), "w", encoding="utf-8") as fh:
        fh.write("-- GENERATED by tools/build.py -- edit the builder, not this file.\n")
        fh.write("-- %s: %s\n" % (spec["name"], spec["summary"]))
        fh.write("\nlocal DATA = " + D.lua(data) + "\n" + PRELUDE)
        fh.write("\nreturn function(mod)\n  local stats = { applied = 0, failed = 0 }\n")
        fh.write(body + "\n")
        fh.write('  mod.log:info("%s: %%d patches applied, %%d refused", stats.applied, stats.failed)\n'
                 % spec["name"])
        fh.write("end\n")
    with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# %s\n\n%s\n\n## What it changes\n\n" % (spec["name"], spec["summary"]))
        fh.write("\n".join("- " + l if not l.startswith("  ") else l for l in lines))
        fh.write("\n\nGames: %s. Needs gen1recomp %s.\n\n" % (", ".join(spec["games"]), GAME_VERSION))
        fh.write("Generated from [Pokémon Crystal Legacy](https://github.com/cRz-Shadows/"
                 "Pokemon_Crystal_Legacy) by `tools/build.py`. All design credit to the "
                 "Crystal Legacy team. See the [repository README](../../README.md).\n")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    ctx = context(a.base, a.legacy)
    for spec in MODS:
        if a.only and spec["id"] not in a.only:
            continue
        lines = write_mod(spec, ctx)
        print("%-28s %s" % (spec["id"], lines[0]))
    for note in ctx["report"]["notes"]:
        print("note:", note)


if __name__ == "__main__":
    main()
