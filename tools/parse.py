"""Parse the Crystal data tables that Crystal Legacy changes.

Every parser takes a pokecrystal-layout checkout and returns plain Python
values keyed by the same constant names gen1recomp uses for its imported
Crystal data (species, move, item, map and trainer constants).
"""

import os
import re

from asm import evaluate, statements, species_order, read_lines

GENDER = {
    "GENDER_F0": 0, "GENDER_F12_5": 31, "GENDER_F25": 63, "GENDER_F50": 127,
    "GENDER_F75": 191, "GENDER_F100": 254, "GENDER_UNKNOWN": 255,
}
TIME = {"TR_ANYTIME": "ANYTIME", "TR_MORNDAY": "MORNDAY", "TR_NITE": "NITE"}


def p(root, rel):
    return os.path.join(root, rel)


def label_to_species(root):
    """CamelCase label prefix -> SPECIES constant, via the pointer tables."""
    order = species_order(root)
    out = {}
    labels = [a[0] for op, a in statements(p(root, "data/pokemon/evos_attacks_pointers.asm"))
              if op == "dw"]
    for species, label in zip(order, labels):
        out[label] = species
    return order, out


# --------------------------------------------------------------- Pokémon
def base_stats(root):
    order = species_order(root)
    files = {}
    for op, args in statements(p(root, "data/pokemon/base_stats.asm")):
        if op == "INCLUDE":
            path = args[0].strip('"')
            files[len(files)] = path
    out = {}
    for i, rel in files.items():
        if i >= len(order):
            break
        rows = [(op, a) for op, a in statements(p(root, rel))
                if op in ("db", "dn", "tmhm", "dw", "INCBIN")]
        db = [a for op, a in rows if op == "db"]
        species = db[0][0]
        stats = [int(x) for x in db[1]]
        rec = {
            "baseStats": dict(zip(
                ["hp", "attack", "defense", "speed", "specialAttack", "specialDefense"], stats)),
            "types": db[2][:2],
            "catchRate": evaluate(db[3][0]),
            "baseExp": evaluate(db[4][0]),
            "items": db[5][:2],
            "genderRatio": GENDER.get(db[6][0], None),
            "eggSteps": evaluate(db[8][0]),
            "growthRate": db[10][0],
        }
        egg = [a for op, a in rows if op == "dn"][0]
        rec["eggGroups"] = egg[:2]
        tm = [a for op, a in rows if op == "tmhm"]
        rec["tmhmAll"] = tm[0] if tm and tm[0] != [""] else []
        out[species] = rec
    return out


def evos_attacks(root):
    order, label_species = label_to_species(root)
    out, cur, phase = {}, None, None
    for op, args in statements(p(root, "data/pokemon/evos_attacks.asm")):
        if op == "label":
            name = args
            if name in label_species:
                cur = label_species[name]
                out[cur] = {"evolutions": [], "levelMoves": []}
                phase = "evo"
            continue
        if cur is None or op != "db":
            continue
        if phase == "evo":
            if args[0] == "0":
                phase = "moves"
                continue
            m = args[0]
            if m == "EVOLVE_LEVEL":
                row = {"method": m, "level": int(args[1]), "into": args[2]}
            elif m == "EVOLVE_ITEM":
                row = {"method": m, "item": args[1], "into": args[2]}
            elif m == "EVOLVE_TRADE":
                row = {"method": m, "into": args[2]}
                if args[1] not in ("-1", "$ff"):
                    row["item"] = args[1]
            elif m == "EVOLVE_HAPPINESS":
                row = {"method": m, "time": TIME[args[1]], "into": args[2]}
            elif m == "EVOLVE_STAT":
                row = {"method": m, "level": int(args[1]),
                       "comparison": args[2], "into": args[3]}
            else:
                raise ValueError("unknown evolution %r" % args)
            out[cur]["evolutions"].append(row)
        elif phase == "moves":
            if args[0] == "0":
                phase = None
                continue
            out[cur]["levelMoves"].append({"level": int(args[0]), "move": args[1]})
    return out


def egg_moves(root):
    order = species_order(root)
    labels = [a[0] for op, a in statements(p(root, "data/pokemon/egg_move_pointers.asm"))
              if op == "dw"]
    lists, cur = {}, None
    for op, args in statements(p(root, "data/pokemon/egg_moves.asm")):
        if op == "label":
            cur = args
            lists.setdefault(cur, [])
        elif op == "db" and cur is not None:
            for a in args:
                if a in ("-1", "$ff"):
                    cur = None
                    break
                lists[cur].append(a)
    return {sp: list(lists.get(lbl, [])) for sp, lbl in zip(order, labels)}


def tmhm_moves(root):
    """(TM/HM moves in machine order, tutor moves)."""
    machines, tutors = [], []
    for op, args in statements(p(root, "constants/item_constants.asm")):
        if op in ("add_tm", "add_hm") and args:
            machines.append(args[0])
        elif op == "add_mt" and args:
            tutors.append(args[0])
    return machines, tutors


# ----------------------------------------------------------------- moves
def moves(root):
    out = {}
    for op, args in statements(p(root, "data/moves/moves.asm")):
        if op == "move":
            name, effect, power, mtype, acc, pp, chance = args
            out[name] = {
                "effect": effect, "power": evaluate(power), "type": mtype,
                "accuracy": evaluate(acc), "pp": evaluate(pp),
                "effectChance": evaluate(chance),
            }
    return out


def text_block(lines):
    parts = []
    for op, args in lines:
        if op in ("db", "next", "text", "line", "cont", "para") and args:
            s = args[0]
            if s.startswith('"'):
                parts.append(s.strip('"').rstrip("@"))
    return parts


def move_descriptions(root):
    """Move id -> description lines (two lines, as shown in the move menu)."""
    path = p(root, "data/moves/descriptions.asm")
    order = []
    labels = {}
    cur = None
    ptr_names = []
    stmts = list(statements(path))
    for op, args in stmts:
        if op == "dw" and args:
            ptr_names.append(args[0])
    # Labels may stack (several moves share text): collect text per label run.
    text, pending = {}, []
    for op, args in stmts:
        if op == "label":
            pending.append(args)
            continue
        if op in ("db", "next") and pending and args and args[0].startswith('"'):
            for lbl in pending:
                text.setdefault(lbl, [])
            for lbl in pending:
                text[lbl].append(args[0].strip('"').rstrip("@"))
            if args[0].endswith('@"'):
                pending = []
    return ptr_names, text


# ----------------------------------------------------------------- items
def item_order(root):
    """Item ids from MASTER_BALL (id 1) on, including TM_*/HM_* items."""
    out = []
    for op, args in statements(p(root, "constants/item_constants.asm")):
        if op == "const" and args and not args[0].startswith("TM_") and args[0] != "\\1":
            out.append(args[0])
        elif op == "add_tm" and args:
            out.append("TM_" + args[0])
        elif op == "add_hm" and args:
            out.append("HM_" + args[0])
        elif op == "add_mt":
            break
    return [x for x in out if x != "NO_ITEM"]


def item_prices(root):
    order = item_order(root)
    prices = []
    for op, args in statements(p(root, "data/items/attributes.asm")):
        if op == "item_attribute":
            prices.append(evaluate(args[0]))
    return dict(zip(order, prices))


def marts(root):
    """MART_* constant -> item list."""
    consts = [a[0] for op, a in statements(p(root, "constants/mart_constants.asm"))
              if op == "const" and a and a[0].startswith("MART_")]
    stmts = list(statements(p(root, "data/items/marts.asm")))
    ptrs, lists, cur = [], {}, None
    in_table = False
    for op, args in stmts:
        if op == "label":
            in_table = args == "Marts"
            cur = args
            lists.setdefault(cur, [])
            continue
        if op == "dw" and in_table:
            ptrs.append(args[0])
        elif op == "db" and cur and not in_table:
            vals = [a for a in args if a]
            lists[cur].extend(vals)
    out = {}
    for const, label in zip(consts, ptrs):
        items = lists.get(label, [])
        # First byte is the count, the list ends at -1.
        body = items[1:]
        body = body[:body.index("-1")] if "-1" in body else body
        out[const] = body
    return out


# --------------------------------------------------------------- trainers
def trainer_classes(root):
    """Ordered [(CLASS, [member constants])] from trainer_constants.asm."""
    classes, cur = [], None
    for op, args in statements(p(root, "constants/trainer_constants.asm")):
        if op == "trainerclass" and args and args[0] == "TRAINER_NONE":
            cur = ("TRAINER_NONE", [])
            continue
        if op == "trainerclass":
            cur = (args[0], [])
            classes.append(cur)
        elif op == "const" and cur is not None and args:
            cur[1].append(args[0])
    return classes


TT_FLAGS = {
    "TRAINERTYPE_NORMAL": set(), "TRAINERTYPE_MOVES": {"moves"},
    "TRAINERTYPE_ITEM": {"item"}, "TRAINERTYPE_ITEM_MOVES": {"item", "moves"},
    "TRAINERTYPE_NICKNAME": {"nickname"}, "TRAINERTYPE_DVS": {"dvs"},
    "TRAINERTYPE_STAT_EXP": {"statExp"}, "TRAINERTYPE_HAPPINESS": {"happiness"},
    "TRAINERTYPE_VARIABLE": {"variable"},
}


def _dv_byte(tok):
    if tok == "PERFECT_DV":
        return 0xFF
    return evaluate(tok)


def _stat_exp(tok):
    # Legacy writes each value as a little-endian `dw` that the loader copies
    # byte for byte into the big-endian stat exp field, so $01FE means $FE01.
    if tok == "PERFECT_STAT_EXP":
        return 0xFFFF
    v = evaluate(tok)
    return ((v & 0xFF) << 8) | (v >> 8)


def trainer_parties(root):
    """CLASS -> {members, parties: [ {name, flags, party:[mon]} ]}."""
    classes = trainer_classes(root)
    groups = [a[0] for op, a in statements(p(root, "data/trainers/party_pointers.asm"))
              if op in ("dw", "dba")]
    # Flatten every group into a token stream; dw rows (stat exp) stay tagged.
    streams, cur = {}, None
    for op, args in statements(p(root, "data/trainers/parties.asm")):
        if op == "label":
            if not args.startswith("."):
                cur = args
                streams.setdefault(cur, [])
            continue
        if cur and op in ("db", "dw"):
            for a in args:
                if a != "":
                    streams[cur].append((op, a))
    out = {}
    for (cls, members), label in zip(classes, groups):
        toks, i, parties = streams.get(label, []), 0, []

        def take(kind="db"):
            nonlocal i
            op, val = toks[i]
            if op != kind:
                raise ValueError("%s: expected %s, got %s %s" % (label, kind, op, val))
            i += 1
            return val

        while i < len(toks):
            name = take()
            if not name.startswith('"'):
                raise ValueError("%s: expected trainer name, got %s" % (label, name))
            flags = set()
            for part in take().replace(" ", "").split("|"):
                flags |= TT_FLAGS[part]
            party = []
            while toks[i][1] != "-1":
                mon = {"level": evaluate(take()), "species": take()}
                if "nickname" in flags:
                    # Legacy writes "@NAME@": its reader drops the first byte
                    # (read_trainer_party.asm), so the name is what follows.
                    nick = take().strip('"')
                    nick = nick[1:] if nick.startswith("@") else nick
                    mon["nickname"] = nick.split("@")[0]
                if "dvs" in flags:
                    a, b = _dv_byte(take()), _dv_byte(take())
                    mon["dvs"] = {"attack": a >> 4, "defense": a & 15,
                                  "speed": b >> 4, "special": b & 15}
                if "statExp" in flags:
                    vals = [_stat_exp(take("dw")) for _ in range(5)]
                    mon["statExp"] = dict(zip(
                        ["hp", "attack", "defense", "speed", "special"], vals))
                if "happiness" in flags:
                    t = take()
                    mon["happiness"] = 255 if t == "MAX_HAPPINESS" else evaluate(t)
                if "item" in flags:
                    t = take()
                    if t != "NO_ITEM":
                        mon["item"] = t
                if "moves" in flags:
                    mon["moves"] = [m for m in (take() for _ in range(4)) if m != "NO_MOVE"]
                party.append(mon)
            i += 1  # -1 ends the party
            parties.append({"name": name.strip('"').rstrip("@"),
                            "flags": sorted(flags), "party": party})
        out[cls] = {"members": members, "parties": parties}
    return out


# ------------------------------------------------------------- encounters
def _map_rows(path, kind):
    out, cur = {}, None
    for op, args in statements(path):
        if op == "def_grass_wildmons" or op == "def_water_wildmons":
            cur = {"map": args[0], "rows": []}
            out[args[0]] = cur
        elif op in ("end_grass_wildmons", "end_water_wildmons"):
            cur = None
        elif op == "db" and cur is not None:
            cur["rows"].append(args)
    return out


def grass(root):
    out = {}
    for f in ("data/wild/johto_grass.asm", "data/wild/kanto_grass.asm"):
        for mid, ent in _map_rows(p(root, f), "grass").items():
            rows = ent["rows"]
            rates = [evaluate(x) for x in rows[0]]
            mons = [{"level": evaluate(r[0]), "species": r[1]} for r in rows[1:]]
            out[mid] = {
                "rates": dict(zip(["MORN", "DAY", "NITE"], rates)),
                "slots": {"MORN": mons[0:7], "DAY": mons[7:14], "NITE": mons[14:21]},
            }
    return out


def water(root):
    out = {}
    for f in ("data/wild/johto_water.asm", "data/wild/kanto_water.asm"):
        for mid, ent in _map_rows(p(root, f), "water").items():
            rows = ent["rows"]
            out[mid] = {
                "rate": evaluate(rows[0][0]),
                "slots": [{"level": evaluate(r[0]), "species": r[1]} for r in rows[1:4]],
            }
    return out


def contest(root):
    out = []
    for op, args in statements(p(root, "data/wild/bug_contest_mons.asm")):
        if op == "db" and len(args) == 4:
            out.append({"chance": evaluate(args[0]), "species": args[1],
                        "min": evaluate(args[2]), "max": evaluate(args[3])})
    return out


# ------------------------------------------------------- engine-side tables
def _db_lists(path):
    """{label: [first operand of each db]} for label / db / db -1 lists."""
    out, cur = {}, None
    for op, args in statements(path):
        if op == "label":
            cur = args
            out.setdefault(cur, [])
        elif op == "db" and cur is not None and args:
            if args[0] in ("-1", "$ff"):
                cur = None
            else:
                out[cur].append(args[0])
    return out


def happiness_changes(root):
    """data/events/happiness_changes.asm rows: [[low, mid, high], ...]."""
    return [[evaluate(x) for x in a[:3]]
            for op, a in statements(p(root, "data/events/happiness_changes.asm"))
            if op == "db" and len(a) >= 3]


def flee_lists(root):
    lists = _db_lists(p(root, "data/wild/flee_mons.asm"))
    return {"sometimes": lists.get("SometimesFleeMons", []),
            "often": lists.get("OftenFleeMons", []),
            "always": lists.get("AlwaysFleeMons", [])}


def crit_moves(root):
    return [m for ms in _db_lists(p(root, "data/moves/critical_hit_moves.asm")).values() for m in ms]


def metronome_exceptions(root):
    return [m for ms in _db_lists(p(root, "data/moves/metronome_exception_moves.asm")).values()
            for m in ms]


def npc_trades(root):
    """data/events/npc_trades.asm rows, in NPCTRADE_* order."""
    rows = []
    for op, a in statements(p(root, "data/events/npc_trades.asm")):
        if op == "npctrade":
            atkdef, spdspc = evaluate(a[4]), evaluate(a[5])
            rows.append({"dialog": a[0], "give": a[1], "get": a[2],
                         "nickname": a[3].strip('"').split("@")[0],
                         "dvs": [atkdef, spdspc], "item": a[6], "otId": evaluate(a[7]),
                         "otName": a[8].strip('"').split("@")[0], "gender": a[9]})
    return rows


def class_dvs(root):
    """CLASS -> {attack, defense, speed, special} from data/trainers/dvs.asm."""
    classes = [c for c, _ in trainer_classes(root)]
    rows = [a for op, a in statements(p(root, "data/trainers/dvs.asm")) if op == "dn"]
    return {c: dict(zip(("attack", "defense", "speed", "special"), (evaluate(x) for x in r[:4])))
            for c, r in zip(classes, rows)}


def class_items(root):
    """CLASS -> [item, ...] (the two TRNATTR_ITEM slots) from attributes.asm."""
    classes = [c for c, _ in trainer_classes(root)]
    rows = []
    for op, a in statements(p(root, "data/trainers/attributes.asm")):
        if op == "db" and len(a) == 2 and all(x.isupper() or x.startswith("NO_") for x in a):
            rows.append([x for x in a if x != "NO_ITEM"])
    return dict(zip(classes, rows))


def rooftop_sale(root):
    """data/items/rooftop_sale.asm: [[{item, price}, ...] per list] (1 before HoF, 2 after)."""
    lists, cur = [], None
    for op, a in statements(p(root, "data/items/rooftop_sale.asm")):
        if op == "label":
            cur = []
            lists.append(cur)
        elif op == "dbw" and cur is not None:
            cur.append({"item": a[0], "price": evaluate(a[1])})
    return lists
