#!/usr/bin/env python3
"""Write a vanilla-Crystal dataset fixture shaped like gen1recomp's import.

    python3 tools/make_fixture.py --base <pokecrystal@base> --out tests/fixture_crystal.lua

The fixture stands in for the data gen1recomp extracts from a Crystal ROM, so
tests/load_test.lua can push every generated patch through gen1recomp's real
mod loader and schemas without a ROM. It is built from the disassembly, never
from a ROM, and holds only the tables the mod writes to.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse  # noqa: E402
from legacy_diff import lua  # noqa: E402

TYPES = ["NORMAL", "FIGHTING", "FLYING", "POISON", "GROUND", "ROCK", "BIRD", "BUG",
         "GHOST", "STEEL"] + ["UNUSED_TYPE_%d" % i for i in range(10, 19)] + [
         "CURSE_TYPE", "FIRE", "WATER", "GRASS", "ELECTRIC", "PSYCHIC_TYPE", "ICE",
         "DRAGON", "DARK"]


def build(base):
    stats, evo, egg = parse.base_stats(base), parse.evos_attacks(base), parse.egg_moves(base)
    machines, tutors = parse.tmhm_moves(base)
    pokemon = {}
    for dex, (sp, s) in enumerate(stats.items(), 1):
        pokemon[sp] = {
            "id": sp, "index": dex, "dex": dex, "name": sp,
            "baseStats": s["baseStats"], "types": s["types"],
            "catchRate": s["catchRate"], "baseExp": s["baseExp"],
            "items": [i if i != "NO_ITEM" else None for i in s["items"]],
            "genderRatio": s["genderRatio"],
            "eggSteps": s["eggSteps"], "growthRate": s["growthRate"],
            "eggGroups": s["eggGroups"], "picSize": 7,
            "tmhm": [m for m in s["tmhmAll"] if m in machines],
            "evolutions": evo[sp]["evolutions"], "levelMoves": evo[sp]["levelMoves"],
            "eggMoves": egg[sp],
            "spriteFront": "assets/generated/battle/front/%s.png" % sp.lower(),
            "spriteBack": "assets/generated/battle/back/%s.png" % sp.lower(),
        }
    # The import keeps growth curves and the machine list beside the species.
    pokemon["growthRates"] = {
        g: {"id": g, "index": i, "numerator": 1, "denominator": 1, "squared": 0,
            "linear": 0, "constant": 0}
        for i, g in enumerate(["GROWTH_MEDIUM_FAST", "GROWTH_SLIGHTLY_FAST",
                               "GROWTH_SLIGHTLY_SLOW", "GROWTH_MEDIUM_SLOW",
                               "GROWTH_FAST", "GROWTH_SLOW"])}
    pokemon["tmhmMoves"] = machines + tutors
    moves = {}
    for i, (mv, m) in enumerate(parse.moves(base).items(), 1):
        rec = dict(m, id=mv, index=i, name=mv)
        rec["accuracyRaw"] = rec["accuracy"] * 255 // 100
        rec["effectChanceRaw"] = rec["effectChance"] * 255 // 100
        moves[mv] = rec
    items = {it: {"id": it, "index": i, "name": it, "price": pr}
             for i, (it, pr) in enumerate(parse.item_prices(base).items(), 1)}
    types = {}
    for i, t in enumerate(TYPES):
        if t.startswith("UNUSED") or t == "BIRD":
            continue
        types[t] = {"id": t, "index": i, "name": t,
                    "category": "physical" if i < 20 else "special"}
    marts = parse.marts(base)
    lists = {i + 1: items_ for i, items_ in enumerate(marts.values())}
    classes = {}
    for ci, (cls, ent) in enumerate(parse.trainer_parties(base).items(), 1):
        rows = []
        for i, pt in enumerate(ent["parties"], 1):
            party = [{k: v for k, v in m.items() if k in ("level", "species", "item", "moves")}
                     for m in pt["party"]]
            rows.append({"id": ent["members"][i - 1] if i <= len(ent["members"]) else "%s%d" % (cls, i),
                         "index": i, "name": pt["name"], "party": party,
                         "trainerType": "TRAINERTYPE_NORMAL"})
        classes[cls] = {"id": cls, "index": ci, "name": cls, "baseMoney": 10,
                        "items": [], "trainers": rows}
    grass = {m: dict(v, map=m) for m, v in parse.grass(base).items()}
    water = {m: dict(v, map=m) for m, v in parse.water(base).items()}
    contest = parse.contest(base)
    for row in contest:
        if row["chance"] < 0:
            row["chance"] = 255
    eff = {"SUPER_EFFECTIVE": 20, "EFFECTIVE": 10, "NOT_VERY_EFFECTIVE": 5, "NO_EFFECT": 0}
    matchups = []
    from asm import statements
    for op, args in statements(os.path.join(base, "data/types/type_matchups.asm")):
        if op == "db" and len(args) == 3 and args[2] in eff:
            matchups.append({"attacker": args[0], "defender": args[1],
                             "multiplier": eff[args[2]]})
    # Synthetic stand-ins for the gym and Elite Four scripts gen1recomp
    # decodes from the ROM, shaped like the real rows (op names and fields
    # from RomExtractorGen2's decoder). Keys are made up; content is ours.
    events = __import__("asm").const_values(os.path.join(base, "constants/event_flags.asm"))
    maps, scripts, texts = {}, {"generation": 2}, {"generation": 2}
    gyms = {"FALKNER": "VIOLET_GYM", "BUGSY": "AZALEA_GYM", "WHITNEY": "GOLDENROD_GYM",
            "MORTY": "ECRUTEAK_GYM", "PRYCE": "MAHOGANY_GYM", "JASMINE": "OLIVINE_GYM",
            "CHUCK": "CIANWOOD_GYM", "CLAIR": "BLACKTHORN_GYM_1F"}
    for cls, mid in gyms.items():
        key = "fx:%s" % cls
        maps[mid] = {"id": mid, "name": mid, "objects": [
            {"index": 1, "sprite": "SPRITE_GYM_GUIDE", "scriptKey": "fx:guide"},
            {"index": 2, "sprite": "SPRITE_" + cls, "scriptKey": key}]}
        texts[key] = "%s vanilla{DONE}" % cls
        scripts[key] = [{"op": "faceplayer"}, {"op": "opentext"},
                        {"op": "writetext", "text": key}, {"op": "waitbutton"},
                        {"op": "closetext"}, {"op": "end"}]
    scripts["fx:guide"] = [{"op": "end"}]
    for cls, member_event in (("WILL", "EVENT_BEAT_ELITE_4_WILL"), ("KOGA", "EVENT_BEAT_ELITE_4_KOGA"),
                              ("BRUNO", "EVENT_BEAT_ELITE_4_BRUNO"), ("KAREN", "EVENT_BEAT_ELITE_4_KAREN"),
                              ("CHAMPION", "EVENT_BEAT_CHAMPION_LANCE")):
        cidx = classes[cls]["index"]
        intro, key = "fx:%s:intro" % cls, "fx:%s" % cls
        texts[intro] = "%s vanilla intro{DONE}" % cls
        battle = [{"op": "writetext", "text": intro}, {"op": "waitbutton"}, {"op": "closetext"},
                  {"op": "winlosstext", "winText": intro},
                  {"op": "loadtrainer", "class": cidx, "member": 1},
                  {"op": "startbattle"}, {"op": "reloadmapafterbattle"},
                  {"op": "setevent", "event": events[member_event]}, {"op": "end"}]
        scripts[key] = [{"op": "faceplayer"}, {"op": "opentext"}] + battle
        scripts[key + ":mid"] = [dict(r) for r in battle]  # a label inside the same script
    return {
        "gen2Maps": maps, "gen2Scripts": scripts, "gen2Text": texts,
        "pokemon": pokemon, "moves": moves, "items": items,
        "type_chart": {"types": types, "matchups": matchups},
        "gen2Marts": {"generation": 2, "source": "fixture", "lists": lists},
        "gen2Trainers": {"generation": 2, "source": "fixture", "classes": classes},
        "gen2Encounters": {"generation": 2, "source": "fixture", "grass": grass,
                           "water": water, "bugContest": contest},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write("-- GENERATED by tools/make_fixture.py from the pokecrystal disassembly.\n")
        fh.write("return " + lua(build(a.base)) + "\n")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
