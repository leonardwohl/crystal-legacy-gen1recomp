#!/usr/bin/env python3
"""Make a scratch ROM in which the Story maps run Crystal Legacy's scripts.

    python3 tools/story/patch_rom.py --base <built pokecrystal> --work <dir> \
        --rom pokecrystal.gbc --out <dir>/patched.gbc MapName [...]

Copies a vanilla ROM, appends the banks tools/story/assemble.py produced
($80 up), and repoints each map's MapAttributes (scripts bank, MapScripts,
MapEvents) at the Legacy versions. gen1recomp's own importer then decodes the
result, so the Story mod's rows come out in exactly gen1recomp's format.
The patched ROM is a build intermediate: it stays in the scratch directory.
"""

import argparse
import os
import shutil

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assemble import load_sym, FIRST_BANK  # noqa: E402

BANK = 0x4000


def offset(bank, addr):
    return addr if bank == 0 else bank * BANK + (addr - BANK)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--rom", required=True, help="vanilla ROM file name inside --base")
    ap.add_argument("--out", required=True)
    ap.add_argument("maps", nargs="+")
    a = ap.parse_args()
    vsym = load_sym(os.path.join(a.base, a.rom.replace(".gbc", ".sym")))
    ssym = load_sym(os.path.join(a.work, "story.sym"))
    rom = bytearray(open(os.path.join(a.base, a.rom), "rb").read())
    story = open(os.path.join(a.work, "story.gbc"), "rb").read()
    last = max(bank for bank, _ in ssym.values())
    size = (last + 1) * BANK
    rom.extend(b"\xff" * (size - len(rom)))
    rom[FIRST_BANK * BANK:size] = story[FIRST_BANK * BANK:size]
    for m in a.maps:
        bank, attrs = vsym[m + "_MapAttributes"]
        sb, sa = ssym[m + "_MapScripts"]
        eb, ea = ssym[m + "_MapEvents"]
        assert sb == eb, "%s: scripts and events must share a bank" % m
        o = offset(bank, attrs)
        rom[o + 6] = sb
        rom[o + 7:o + 9] = bytes([sa & 0xFF, sa >> 8])
        rom[o + 9:o + 11] = bytes([ea & 0xFF, ea >> 8])
    with open(a.out, "wb") as fh:
        fh.write(rom)
    print("patched %d maps -> %s (%d KB)" % (len(a.maps), a.out, len(rom) // 1024))


if __name__ == "__main__":
    main()
