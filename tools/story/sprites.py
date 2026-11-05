"""Port Crystal Legacy's new overworld sprites to gen1recomp.

Each new Legacy sprite a Story map uses gets a sprite number vanilla Crystal
leaves free, and a gen1recomp sprite record with Legacy's art:

  * walking / standing sprites: numbers $67-$7f (vanilla's spriteOrder marks
    them UNUSED); art from gfx/sprites/<name>.png.
  * Pokemon overworld sprites: numbers from $a3 up (past vanilla's last
    Pokemon sprite, below the $e0 day-care block); art is the species' menu
    icon, which Legacy draws per species (gfx/icons/<species>.png).

Images are written the way gen1recomp's importer writes sprites
(ImageWriter.decode2bpp): four greys, white transparent.
"""

import os
import re

from PIL import Image

FIRST_WALKING, LAST_WALKING = 0x67, 0x7F
FIRST_POKEMON, LAST_POKEMON = 0xA3, 0xDF  # vanilla Pokemon sprites end at $a2

SHADES = [(255, 255, 255, 0), (170, 170, 170, 255), (85, 85, 85, 255), (0, 0, 0, 255)]
PALETTE_IDS = {"PAL_OW_RED": 0, "PAL_OW_BLUE": 1, "PAL_OW_GREEN": 2, "PAL_OW_BROWN": 3,
               "PAL_OW_PINK": 4, "PAL_OW_EMOTE": 5, "PAL_OW_TREE": 6, "PAL_OW_ROCK": 7}
SPRITE_TYPES = {"WALKING_SPRITE", "STANDING_SPRITE", "STILL_SPRITE"}


def _consts(path):
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from asm import const_values
    return const_values(path)


def _overworld_rows(legacy):
    """Legacy's OverworldSprites table: [(gfx label, tiles, type, palette)]."""
    rows = []
    for line in open(os.path.join(legacy, "data/sprites/sprites.asm")):
        m = re.match(r"\s*overworld_sprite\s+(\w+),\s*(\d+),\s*(\w+),\s*(\w+)", line)
        if m:
            rows.append((m.group(1), int(m.group(2)), m.group(3), m.group(4)))
    return rows


def _gfx_files(legacy):
    out = {}
    for line in open(os.path.join(legacy, "gfx/sprites.asm")):
        m = re.match(r'\s*(\w+)::\s*INCBIN\s+"([^"]+)\.2bpp"', line)
        if m:
            out[m.group(1)] = m.group(2) + ".png"
    return out


def _sprite_mons(legacy):
    mons = []
    for line in open(os.path.join(legacy, "data/sprites/sprite_mons.asm")):
        m = re.match(r"\s*db\s+(\w+)", line.split(";")[0])
        if m:
            mons.append(m.group(1))
    return mons


def _species_icon_files(legacy):
    """SPECIES -> icon png, via menu_icons.asm, IconPointers and gfx/icons.asm."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from asm import species_order
    icons = []
    for line in open(os.path.join(legacy, "data/pokemon/menu_icons.asm")):
        m = re.match(r"\s*db\s+(ICON_\w+)", line)
        if m:
            icons.append(m.group(1))
    by_species = dict(zip(species_order(legacy), icons))
    consts = _consts(os.path.join(legacy, "constants/icon_constants.asm"))
    labels = []
    for line in open(os.path.join(legacy, "data/icon_pointers.asm")):
        m = re.match(r"\s*dw\s+(\w+)", line)
        if m:
            labels.append(m.group(1))
    files = {}
    for line in open(os.path.join(legacy, "gfx/icons.asm")):
        m = re.match(r'\s*(\w+):+\s*INCBIN\s+"([^"]+)\.2bpp"', line)
        if m:
            files[m.group(1)] = m.group(2) + ".png"
    return {sp: os.path.join(legacy, files[labels[consts[ic]]])
            for sp, ic in by_species.items() if ic in consts and consts[ic] < len(labels)
            and labels[consts[ic]] in files}


def convert(src, dst):
    """Any 4-shade PNG -> RGBA greys with white transparent."""
    im = Image.open(src)
    grey = im.convert("L")
    levels = sorted(set(grey.tobytes()), reverse=True)  # lightest first
    out = Image.new("RGBA", im.size)
    out.putdata([SHADES[min(levels.index(v), 3)] for v in grey.tobytes()])
    out.save(dst)


def used_sprites(legacy, map_files):
    names = set()
    for f in map_files:
        text = open(os.path.join(legacy, "maps", f + ".asm"), encoding="utf-8",
                    errors="replace").read()
        names |= set(re.findall(r"\bSPRITE_\w+", text))
    return names


def port(base, legacy, map_files, asset_dir, pinned=None):
    """Return (constant defs for assemble.py, sprite records, spriteOrder additions).

    `pinned` holds numbers given out by earlier builds ({name: number}); they
    are kept, because saves store variable-sprite slots by number.
    """
    pinned = dict(pinned or {})
    vanilla = _consts(os.path.join(base, "constants/sprite_constants.asm"))
    lvals = _consts(os.path.join(legacy, "constants/sprite_constants.asm"))
    lpoke = lvals["SPRITE_POKEMON"] if "SPRITE_POKEMON" in lvals else 0x80
    rows, gfx, mons = _overworld_rows(legacy), _gfx_files(legacy), _sprite_mons(legacy)
    icon_files = _species_icon_files(legacy)
    new = sorted(n for n in used_sprites(legacy, map_files)
                 if n not in vanilla and n in lvals and lvals[n] < 0xE0)
    defs, records, order = {}, [], {}
    taken = set(pinned.values())

    def alloc(lo, hi):
        for n in range(lo, hi + 1):
            if n not in taken:
                taken.add(n)
                return n
        raise AssertionError("out of free sprite numbers in $%x-$%x" % (lo, hi))
    os.makedirs(os.path.join(asset_dir, "sprites"), exist_ok=True)
    for name in new:
        value = lvals[name]
        base_name = name.lower().replace("sprite_", "", 1)
        if value >= lpoke:
            species = mons[value - lpoke]
            src = icon_files[species]
            num = pinned.get(name) or alloc(FIRST_POKEMON, LAST_POKEMON)
            rec = {"frames": 2, "walker": False, "spriteType": "POKEMON_SPRITE",
                   "palette": "PAL_OW_RED", "paletteId": 0, "species": species}
        else:
            label, tiles, kind, pal = rows[value - 1]
            src = os.path.join(legacy, gfx[label])
            num = pinned.get(name) or alloc(FIRST_WALKING, LAST_WALKING)
            frames = Image.open(src).size[1] // 16
            rec = {"frames": frames, "walker": kind == "WALKING_SPRITE" or frames >= 6,
                   "spriteType": kind if kind in SPRITE_TYPES else "WALKING_SPRITE",
                   "palette": pal, "paletteId": PALETTE_IDS.get(pal, 0)}
        png = "sprites/%s.png" % base_name
        convert(src, os.path.join(asset_dir, png))
        rec.update({"id": name, "image": "assets/" + png, "source": "Crystal Legacy"})
        defs[name] = num
        records.append(rec)
        order[num] = name
    return defs, records, order
