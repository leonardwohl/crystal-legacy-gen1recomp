#!/usr/bin/env python3
"""Assemble Crystal Legacy map scripts against VANILLA Crystal numbering.

    python3 tools/story/assemble.py --base <pokecrystal@82e315e48, built> \
        --legacy <Crystal Legacy> --rgbds <dir with rgbasm/rgblink> \
        --work <scratch dir> MapName [MapName ...]

Each Crystal Legacy map file (maps/<MapName>.asm) is assembled with the real
RGBDS against vanilla pokecrystal's constants and macros, so every constant
an unchanged script uses gets vanilla's number by name: specials, sprites,
events, items. It goes into its own bank from $80 up, past the end of the 2 MB
cart, so none of its addresses can collide with a vanilla script key.

Names the file uses but does not define are resolved in order:
  1. Crystal Legacy-only constants: LEGACY_ONLY below, an explicit table.
  2. Vanilla labels (engine routines, std scripts, shared text, RAM): pinned
     at their address in vanilla's symbol file, so a jump into vanilla code
     decodes to the very key gen1recomp already has for it.
Anything left unresolved is an error, listed by name.

Writes <work>/story.gbc (only banks >= $80 matter) and <work>/story.sym.
"""

import argparse
import os
import re
import subprocess
import sys

FIRST_BANK = 0x80

# Crystal Legacy constants with no vanilla counterpart, and what they become.
# Trainer classes past vanilla's 67 are registered by the Story mod at load
# time with exactly these indices. Variable sprite slots $fd/$fe are unused in
# vanilla ($f0-$fc are taken). Hard Mode flags point at an engine flag nothing
# sets, so Legacy's hard-mode branches fall through to normal play (the Legacy
# Hard Mode mod applies those rules itself).
LEGACY_ONLY = {
    # trainer classes (constants/trainer_constants.asm, appended in Legacy)
    "BOSS": 68, "ROCKET_LEADER": 69, "PKMNTRAINERF": 70,
    # trainer members
    "SMITH": 3, "CRAIG": 4, "GIOVANNI": 1, "ARCHER": 1, "WEEBRA": 1,
    # variable sprite slots
    "SPRITE_TRAINER_HOUSE_PKMN_TRAINER": 0xFD, "SPRITE_RADIOTOWER_GIOVANNI": 0xFE,
    # hard mode: an engine flag id no script sets; any battle type value
    "ENGINE_HARD_MODE": 0x7FF, "ENGINE_HARDCORE_MODE": 0x7FF,
    "BATTLETYPE_SET": 0, "BATTLETYPE_SETNOITEMS": 0, "BATTLETYPE_CANLOSE_SETNOITEMS": 0,
}

# Legacy's new overworld sprites need art gen1recomp does not have yet, so
# for now each uses the closest vanilla sprite (resolved by name below).
SPRITE_STAND_INS = {
    "SPRITE_ARCHER": "SPRITE_ROCKET", "SPRITE_GIOVANNI": "SPRITE_GENTLEMAN",
    "SPRITE_GIOVANNI_DISGUISE": "SPRITE_GENTLEMAN", "SPRITE_MEWTWO": "SPRITE_MONSTER",
    "SPRITE_MURKROW": "SPRITE_BIRD",
}

# RAM only Legacy's Hard Mode branches write (never taken here).
DUMMY_RAM = {"wLevelCap": 0xDFF0}


def load_sym(path):
    out = {}
    with open(path) as fh:
        for line in fh:
            line = line.split(";")[0].strip()
            if not line:
                continue
            addr, name = line.split(None, 1)
            bank, a = addr.split(":")
            out[name] = (int(bank, 16), int(a, 16))
    return out


def const_values(path):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from asm import const_values as cv
    return cv(path)


def free_event_ids(base):
    used = set(const_values(os.path.join(base, "constants/event_flags.asm")).values())
    top = max(used)
    return [i for i in range(1, top) if i not in used]


def specials(base):
    names = []
    for line in open(os.path.join(base, "data/events/special_pointers.asm")):
        m = re.match(r"\s*add_special\s+(\w+)", line)
        if m:
            names.append(m.group(1))
    return names


def build(base, legacy, rgbds, work, maps, extra_consts):
    os.makedirs(os.path.join(work, "maps"), exist_ok=True)
    sym = load_sym(os.path.join(base, "pokecrystal.sym"))
    defs = dict(LEGACY_ONLY)
    defs.update({k: v for k, v in extra_consts.items() if not k.startswith("__")})
    defs["SpecialsPointers"] = 0
    for i, name in enumerate(specials(base)):
        defs[name + "Special"] = i * 3

    stubs = {}  # (bank, addr) -> [names]
    vanilla_sprites = const_values(os.path.join(base, "constants/sprite_constants.asm"))
    legacy_events = const_values(os.path.join(legacy, "constants/event_flags.asm"))
    free_events = free_event_ids(base)
    new_events = extra_consts.setdefault("__new_events__", {})
    for attempt in range(6):
        with open(os.path.join(work, "shim.asm"), "w") as fh:
            for name, value in sorted(defs.items()):
                fh.write("DEF %s EQU %d\n" % (name, value))
        with open(os.path.join(work, "main.asm"), "w") as fh:
            fh.write('INCLUDE "constants.asm"\nINCLUDE "shim.asm"\n')
            for i, m in enumerate(maps):
                src = os.path.join(legacy, "maps", m + ".asm")
                dst = os.path.join(work, "maps", m + ".asm")
                with open(src, encoding="utf-8", errors="replace") as a, \
                        open(dst, "w", encoding="utf-8") as b:
                    b.write(a.read())
                fh.write('SECTION "story_%d", ROMX[$4000], BANK[$%x]\n' % (i, FIRST_BANK + i))
                fh.write('INCLUDE "maps/%s.asm"\n' % m)
            for n, ((bank, addr), names) in enumerate(sorted(stubs.items())):
                if bank == 0 and addr < 0x4000:
                    fh.write('SECTION "ext_%d", ROM0[$%04x]\n' % (n, addr))
                else:
                    fh.write('SECTION "ext_%d", ROMX[$%04x], BANK[$%x]\n' % (n, addr, bank))
                for name in names:
                    fh.write("%s::\n" % name)
        env = dict(os.environ, PATH=rgbds + os.pathsep + os.environ.get("PATH", ""))
        asm = subprocess.run(["rgbasm", "-i", base + "/", "-i", work + "/", "-o", "main.o", "main.asm"],
                             cwd=work, capture_output=True, text=True, env=env)
        if asm.returncode != 0:
            sys.exit("rgbasm failed:\n" + asm.stderr[-4000:])
        link = subprocess.run(["rgblink", "-n", "story.sym", "-o", "story.gbc", "main.o"],
                              cwd=work, capture_output=True, text=True, env=env)
        if link.returncode == 0:
            return {"stubs": sorted(stubs.items()), "newEvents": new_events,
                    "defs": defs}
        unknown = sorted(set(re.findall(r'Unknown symbol "([^"]+)"', link.stderr)))
        if not unknown:
            sys.exit("rgblink failed:\n" + link.stderr[-4000:])
        missing = []
        for name in unknown:
            if name in SPRITE_STAND_INS:
                defs[name] = vanilla_sprites[SPRITE_STAND_INS[name]]
                continue
            if name in DUMMY_RAM:
                defs[name] = DUMMY_RAM[name]
                continue
            if name.startswith("EVENT_") and name in legacy_events:
                # New Legacy event flag: put it on an id vanilla never uses.
                defs[name] = free_events.pop(0)
                new_events[name] = defs[name]
                continue
            if name in sym:
                bank, addr = sym[name]
                if addr >= 0x8000:  # RAM: a plain address is all a script uses
                    defs[name] = addr
                else:
                    stubs.setdefault((bank, addr), []).append(name)
            else:
                missing.append(name)
        if missing:
            sys.exit("unresolved Crystal Legacy names (add them to LEGACY_ONLY): "
                     + ", ".join(missing))
    sys.exit("could not resolve all symbols")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--rgbds", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("maps", nargs="+")
    a = ap.parse_args()
    r = build(a.base, a.legacy, a.rgbds, a.work, a.maps, {})
    print("assembled %d maps; %d vanilla addresses pinned; new events %s"
          % (len(a.maps), len(r["stubs"]), r["newEvents"]))


if __name__ == "__main__":
    main()
