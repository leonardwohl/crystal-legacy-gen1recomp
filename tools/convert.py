#!/usr/bin/env python3
"""Build the gen1recomp mod from a Crystal Legacy checkout.

    python3 tools/convert.py --base <pokecrystal@base> --legacy <Crystal Legacy> \
        [--out mod/main.lua] [--report docs/generated-changes.md]

`--base` must be the pokecrystal commit Crystal Legacy forked from (see
README: 82e315e48). Only values that differ between the two trees are
written, so the mod patches exactly what Crystal Legacy changed and leaves
everything else to gen1recomp's own import of the player's Crystal ROM.
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse  # noqa: E402

TRAINERTYPE = {
    (False, False): "TRAINERTYPE_NORMAL", (False, True): "TRAINERTYPE_MOVES",
    (True, False): "TRAINERTYPE_ITEM", (True, True): "TRAINERTYPE_ITEM_MOVES",
}

# Crystal Legacy reuses unused item slots for these. gen1recomp's import of a
# vanilla ROM has no records for them, and adding items needs names, effects
# and scripts that give them out, so they are reported and skipped for now.
SKIPPED_NEW_ITEMS = {"OLD_AMBER", "DOME_FOSSIL", "HELIX_FOSSIL"}


# ------------------------------------------------------------------ Lua out
def lua(value, indent=0):
    pad = "  " * indent
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        if not value:
            return "{}"
        inner = [lua(v, indent + 1) for v in value]
        one = "{ " + ", ".join(inner) + " }"
        if len(one) + len(pad) < 100 and "\n" not in one:
            return one
        return "{\n" + ",\n".join(pad + "  " + v for v in inner) + ",\n" + pad + "}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        parts = []
        for k in sorted(value, key=lambda k: (not isinstance(k, int), str(k).zfill(4)
                                              if isinstance(k, int) else str(k))):
            key = "[%d]" % k if isinstance(k, int) else (
                k if k.isidentifier() else "[%s]" % json.dumps(k))
            parts.append("%s = %s" % (key, lua(value[k], indent + 1)))
        one = "{ " + ", ".join(parts) + " }"
        if len(one) + len(pad) < 100 and "\n" not in one:
            return one
        return "{\n" + ",\n".join(pad + "  " + v for v in parts) + ",\n" + pad + "}"
    raise TypeError(type(value))


# ------------------------------------------------------------------ diffing
def diff_pokemon(base, leg, report):
    b_stats, l_stats = parse.base_stats(base), parse.base_stats(leg)
    b_evo, l_evo = parse.evos_attacks(base), parse.evos_attacks(leg)
    b_egg, l_egg = parse.egg_moves(base), parse.egg_moves(leg)
    l_machines, l_tutors = parse.tmhm_moves(leg)
    b_machines, b_tutors = parse.tmhm_moves(base)
    if (l_machines, l_tutors) != (b_machines, b_tutors):
        report["notes"].append("TM/HM/tutor move assignments differ; not ported yet.")
    out = {}
    for sp in l_stats:
        b, l, patch = b_stats[sp], l_stats[sp], {}
        for key in ("baseStats", "types", "catchRate", "baseExp", "items",
                    "genderRatio", "eggSteps", "growthRate", "eggGroups"):
            if b[key] != l[key]:
                patch[key] = l[key]
        if b["tmhmAll"] != l["tmhmAll"]:
            machines = [m for m in l["tmhmAll"] if m in l_machines]
            tutors = [m for m in l["tmhmAll"] if m in l_tutors]
            if set(machines) != {m for m in b["tmhmAll"] if m in b_machines}:
                patch["tmhm"] = machines
            if set(tutors) != {m for m in b["tmhmAll"] if m in b_tutors}:
                patch["tutorMoves"] = tutors
        for key in ("evolutions", "levelMoves"):
            if b_evo[sp][key] != l_evo[sp][key]:
                patch[key] = l_evo[sp][key]
        if b_egg[sp] != l_egg[sp]:
            patch["eggMoves"] = l_egg[sp]
        if patch:
            out[sp] = patch
    report["pokemon"] = out
    return out


def diff_moves(base, leg, report):
    b, l = parse.moves(base), parse.moves(leg)
    out = {}
    for mv, rec in l.items():
        patch = {k: v for k, v in rec.items() if b[mv][k] != v}
        if patch:
            out[mv] = patch
    report["moves"] = out
    return out


def diff_items(base, leg, report):
    b, l = parse.item_prices(base), parse.item_prices(leg)
    out, skipped = {}, []
    for item, price in l.items():
        if item in SKIPPED_NEW_ITEMS or item not in b:
            skipped.append(item)
            continue
        if b[item] != price:
            out[item] = {"price": price}
    report["items"] = out
    report["skippedItems"] = sorted(set(skipped) & SKIPPED_NEW_ITEMS)
    return out


def diff_marts(base, leg, report):
    b, l = parse.marts(base), parse.marts(leg)
    order = list(b)  # vanilla MART_* order == the script mart numbers
    out, new = {}, []
    for const, items in l.items():
        if const not in b:
            new.append(const)
            continue
        if b[const] != items:
            out[str(order.index(const))] = {"mart": const, "items": items}
    report["marts"] = out
    report["newMarts"] = new
    return out


def resolve_moves(leg, l, report):
    """Map non-move tokens in trainer move lists to the move the ROM gets.

    Crystal Legacy has at least one typo where a trainer class constant sits
    in a move slot. RGBDS assembles it to that class's number, which the game
    then reads as a move id, so the faithful port is the move at that id.
    """
    move_ids = list(parse.moves(leg))  # move id 1 = first entry
    class_ids = {cls: i for i, (cls, _) in enumerate(parse.trainer_classes(leg), 1)}
    for cls, ent in l.items():
        for pi, pt in enumerate(ent["parties"]):
            for mon in pt["party"]:
                fixed = []
                for mv in mon.get("moves", []):
                    if mv not in move_ids and mv in class_ids:
                        real = move_ids[class_ids[mv] - 1]
                        report["notes"].append(
                            "%s party %d %s: move slot reads `%s` in Crystal Legacy's source "
                            "(a trainer class); the ROM assembles it as %s, so that is used."
                            % (cls, pi + 1, mon["species"], mv, real))
                        mv = real
                    fixed.append(mv)
                if "moves" in mon:
                    mon["moves"] = fixed


def diff_trainers(base, leg, report):
    b, l = parse.trainer_parties(base), parse.trainer_parties(leg)
    resolve_moves(leg, l, report)
    out, extras, new_classes, added = {}, {}, [], []
    for cls, ent in l.items():
        if cls not in b:
            new_classes.append(cls)
            continue
        b_parties = b[cls]["parties"]
        members = b[cls]["members"]
        rows, changed = [], False
        for i, pt in enumerate(ent["parties"]):
            party = []
            for slot, mon in enumerate(pt["party"], 1):
                row = {"level": mon["level"], "species": mon["species"]}
                if "item" in mon:
                    row["item"] = mon["item"]
                if "moves" in mon:
                    row["moves"] = mon["moves"]
                party.append(row)
                ex = {k: mon[k] for k in ("dvs", "statExp", "happiness") if k in mon}
                if ex:
                    extras.setdefault(cls, {}).setdefault(i + 1, {})[slot] = ex
            has_item = "item" in pt["flags"]
            has_moves = "moves" in pt["flags"]
            member = members[i] if i < len(members) else "%s%d" % (cls, i + 1)
            if i >= len(members):
                added.append(member)
            rows.append({"id": member, "index": i + 1, "name": pt["name"],
                         "trainerType": TRAINERTYPE[(has_item, has_moves)],
                         "party": party})
            if i >= len(b_parties) or b_parties[i]["party"] != pt["party"] \
                    or b_parties[i]["name"] != pt["name"]:
                changed = True
        if len(ent["parties"]) != len(b_parties):
            changed = True
        if changed:
            out[cls] = rows
    report["trainers"] = out
    report["trainerExtras"] = extras
    report["newTrainerClasses"] = new_classes
    report["addedTrainers"] = added
    return out, extras


def diff_encounters(base, leg, report):
    out = {}
    for kind, fn in (("grass", parse.grass), ("water", parse.water)):
        b, l = fn(base), fn(leg)
        changed = {m: v for m, v in l.items() if b.get(m) != v}
        if changed:
            out[kind] = changed
    b, l = parse.contest(base), parse.contest(leg)
    if b != l:
        for row in l:
            if row["chance"] < 0:
                row["chance"] = 255
        out["bugContest"] = l
    report["encounters"] = out
    return out


# ------------------------------------------------------------------ main.lua
LUA_BODY = r'''
-- Apply one patch, logging rather than aborting when gen1recomp refuses it,
-- so one bad record never takes the rest of the conversion down with it.
local function patch(mod, registry, id, fields, stats)
  local reg = mod.content[registry]
  if not reg then
    mod.log:warn("registry %s is not available; skipped %s", registry, id)
    stats.failed = stats.failed + 1
    return
  end
  local ok, result, reason = pcall(reg.patch, reg, id, fields)
  if not ok or result == nil and reason ~= nil then
    mod.log:warn("%s %s: %s", registry, id, tostring(ok and reason or result))
    stats.failed = stats.failed + 1
  else
    stats.applied = stats.applied + 1
  end
end

local function each(map, fn)
  local keys = {}
  for k in pairs(map) do keys[#keys + 1] = k end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  for _, k in ipairs(keys) do fn(k, map[k]) end
end

return function(mod)
  local stats = { applied = 0, failed = 0 }

  each(DATA.pokemon, function(id, fields)
    if mod.content.pokemon:get(id) then patch(mod, "pokemon", id, fields, stats) end
  end)
  each(DATA.moves, function(id, fields)
    if mod.content.moves:get(id) then patch(mod, "moves", id, fields, stats) end
  end)
  each(DATA.items, function(id, fields)
    if mod.content.items:get(id) then patch(mod, "items", id, fields, stats) end
  end)
  -- Crystal Legacy's battle engine treats Ghost as special and Dark as
  -- physical; gen1recomp decides this per type, so it is a type_chart patch.
  each(DATA.typeCategories, function(id, category)
    patch(mod, "type_chart", id, { category = category }, stats)
  end)
  each(DATA.marts, function(id, items) patch(mod, "marts", id, items, stats) end)
  each(DATA.trainers, function(class, rows)
    patch(mod, "trainers", class, { trainers = rows }, stats)
  end)
  for kind, maps in pairs(DATA.encounters) do
    if kind == "bugContest" then
      local reg = mod.content.encounters
      local ok, err = pcall(reg.override, reg, kind, maps)
      if not ok then mod.log:warn("encounters bugContest: %s", tostring(err)) end
    else
      patch(mod, "encounters", kind, maps, stats)
    end
  end

  -- Custom DVs and stat exp on a handful of rematch / Elite Four parties.
  -- gen1recomp builds trainer mons with the vanilla fixed DVs, so these are
  -- applied to the built party just before the battle computes its stats.
  mod.hooks:wrap("trainer.party", function(nextFn, class, member, party)
    party = nextFn(class, member, party)
    local byClass = DATA.trainerExtras[class]
    local index = type(member) == "string" and DATA.memberIndex[member] or member
    local slots = byClass and byClass[index]
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

  mod.log:info("Crystal Legacy data: %d patches applied, %d refused",
    stats.applied, stats.failed)
end
'''


def build(base, leg, out_path, report_path):
    report = {"notes": []}
    data = {
        "pokemon": diff_pokemon(base, leg, report),
        "moves": diff_moves(base, leg, report),
        "items": diff_items(base, leg, report),
        "typeCategories": {"GHOST": "special", "DARK": "physical"},
    }
    marts = diff_marts(base, leg, report)
    data["marts"] = {k: v["items"] for k, v in marts.items()}
    trainers, extras = diff_trainers(base, leg, report)
    data["trainers"] = trainers
    data["trainerExtras"] = extras
    data["memberIndex"] = {row["id"]: row["index"]
                           for rows in trainers.values() for row in rows}
    data["encounters"] = diff_encounters(base, leg, report)

    header = (
        "-- GENERATED by tools/convert.py -- do not edit by hand.\n"
        "-- Crystal Legacy (cRz-Shadows/Pokemon_Crystal_Legacy) data changes,\n"
        "-- diffed against pokecrystal %s and written as gen1recomp patches.\n"
        % parse_base_label(base)
    )
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(header + "\nlocal DATA = " + lua(data) + "\n" + LUA_BODY)
    write_report(report, report_path)
    return report


def parse_base_label(base):
    head = os.path.join(base, ".git")
    try:
        if os.path.isfile(head):  # worktree
            return "base checkout"
    except OSError:
        pass
    return "base checkout"


def write_report(r, path):
    lines = ["# Generated change list", "",
             "Written by `tools/convert.py`. Counts are what the converter found",
             "different between pokecrystal (base) and Crystal Legacy.", ""]
    pk = r["pokemon"]
    fields = {}
    for p in pk.values():
        for k in p:
            fields[k] = fields.get(k, 0) + 1
    lines += ["## Ported", "",
              "| Area | Changed records |", "|---|---|",
              "| Pokémon (any field) | %d |" % len(pk)]
    for k in sorted(fields):
        lines.append("| &nbsp;&nbsp;`%s` | %d |" % (k, fields[k]))
    lines += [
        "| Moves | %d |" % len(r["moves"]),
        "| Item prices | %d |" % len(r["items"]),
        "| Shops (existing) | %d |" % len(r["marts"]),
        "| Trainer classes rewritten | %d |" % len(r["trainers"]),
        "| Trainer parties with custom DVs/stat exp | %d |" % sum(
            len(v) for v in r["trainerExtras"].values()),
        "| Grass encounter tables | %d |" % len(r["encounters"].get("grass", {})),
        "| Water encounter tables | %d |" % len(r["encounters"].get("water", {})),
        "| Bug-Catching Contest table | %s |" % ("yes" if "bugContest" in r["encounters"] else "unchanged"),
        "| Ghost special / Dark physical | yes |", "",
        "## Found but not ported yet", "",
        "- New shops (need map scripts to open them): %s" % (", ".join(r["newMarts"]) or "none"),
        "- New trainer classes (need pics, names and scripts): %s" % (
            ", ".join(r["newTrainerClasses"]) or "none"),
        "- Added trainer parties, e.g. rematches (data is in, but nothing in vanilla "
        "map scripts starts these battles yet): %d" % len(r["addedTrainers"]),
        "- New items: %s" % (", ".join(r["skippedItems"]) or "none"),
    ]
    for n in r["notes"]:
        lines.append("- " + n)
    lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--legacy", required=True)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", default=os.path.join(here, "mod", "main.lua"))
    ap.add_argument("--report", default=os.path.join(here, "docs", "generated-changes.md"))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    os.makedirs(os.path.dirname(a.report), exist_ok=True)
    build(a.base, a.legacy, a.out, a.report)
    print("wrote", a.out, "and", a.report)


if __name__ == "__main__":
    main()
