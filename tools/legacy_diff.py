"""Diff Crystal Legacy against its pokecrystal fork point.

Each diff_* function returns only what Crystal Legacy changed, in the record
shapes gen1recomp uses for its imported Crystal data. tools/build.py turns
the results into the individual mods.
"""

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
_ESC = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t",
        "\f": "\\f", "\v": "\\v"}


def lua_string(s):
    """A Lua 5.1 string literal (no \\u escapes; UTF-8 passes through)."""
    out = []
    for ch in s:
        if ch in _ESC:
            out.append(_ESC[ch])
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append("\\%03d" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def lua(value, indent=0):
    pad = "  " * indent
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return lua_string(value)
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


def mon_extras(mon):
    """What a trainer Pokémon carries beyond level/species/item/moves."""
    ex = {k: mon[k] for k in ("dvs", "statExp", "happiness") if k in mon}
    # A nickname only when it isn't just the species' name.
    nick = mon.get("nickname")
    if nick and nick.upper() != mon["species"].replace("_", " "):
        ex["nickname"] = nick
    return ex


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
                ex = mon_extras(mon)
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


