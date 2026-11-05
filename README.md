# Crystal Legacy for gen1recomp

Unofficial mods that port [Pokémon Crystal Legacy](https://github.com/cRz-Shadows/Pokemon_Crystal_Legacy)
to [gen1recomp](https://github.com/bryanthaboi/gen1recomp)'s Crystal mode, split
by theme so you can install only the parts you want.

Crystal Legacy is a ROM hack by TheSmithPlays and cRz Shadows. All of its design
credit belongs to them and the people listed in its README. This repository
only translates their work into gen1recomp's mod format.

> **Status:** early. These mods pass automated checks against gen1recomp's
> real mod loader, but **have not been play-tested yet**. Reports welcome.

## The mods

| Mod | What it does | Status |
|---|---|---|
| [Pokémon Changes](mods/crystal_legacy_pokemon) | Base stats, learnsets, TM/HM and egg moves, evolutions, move changes | ✅ ready to try |
| [Trainer Changes](mods/crystal_legacy_trainers) | Every trainer and leader team, with items, moves, DVs | ✅ ready to try |
| [Encounter Changes](mods/crystal_legacy_encounters) | Wild grass and surfing Pokémon | ✅ ready to try |
| [Fast Eggs](mods/fast_eggs) | Eggs hatch in about a quarter of the steps (Gold, Silver, Crystal) | ✅ ready to try |
| [Ghost/Dark Switch](mods/crystal_legacy_ghost_dark) | Ghost moves special, Dark moves physical (Gold, Silver, Crystal) | ✅ ready to try |
| [Shop Changes](mods/crystal_legacy_shops) | Shop stock and prices | ✅ existing shops; 🚧 new shops |
| Rematches | Gym leader, Elite Four and Red rematches | 🚧 in progress |
| Legacy Hard Mode | Level caps, Set mode, no items in trainer battles | 🚧 in progress |
| Story Changes | Team Rocket and rival story, new trainer classes, scaling leaders | 🚧 planned |

Every mod works on its own, and they can be combined freely. Trainer Changes
and Rematches are written so that either can be installed without the other.

The headbutt tree and Rock Smash tables are identical in Crystal Legacy and
vanilla, so there is nothing to port there. Exp. Share and Pokédex changes are
left to existing gen1recomp mods.

## Install

1. Use gen1recomp **0.4.x** with a US Pokémon Crystal ROM (1.0 or 1.1) imported.
2. Download the `.zip` for each mod you want from
   [Releases](https://github.com/leonardwohl/crystal-legacy-gen1recomp/releases),
   or from the artifacts of the latest **Package mods** workflow run.
3. In gen1recomp, open **MODS → Import mod .zip** and pick each zip.
4. Enable them for Crystal. A new game is recommended.

## Repository layout

```
mods/<id>/        one folder per mod: manifest.json, main.lua, README.md
tools/parse.py    reads pokecrystal-style data tables
tools/legacy_diff.py  diffs Crystal Legacy against its fork point
tools/build.py    generates the data mods under mods/
tools/package.py  zips each mod as <id>-<version>.zip
tools/test.sh     modkit checks + load tests, each mod alone and all together
tests/            the load test (fixture is generated, not committed)
```

The `main.lua` files of generated mods are build output, so change
`tools/build.py` or the parsers instead of editing them by hand.

## Building and testing

You need Python 3, plus LuaJIT and a gen1recomp checkout for the tests.

```bash
git clone https://github.com/cRz-Shadows/Pokemon_Crystal_Legacy legacy
git clone https://github.com/pret/pokecrystal pokecrystal
git -C pokecrystal worktree add ../base 82e315e48
python3 tools/build.py --base base --legacy legacy
tools/test.sh path/to/gen1recomp base
```

`82e315e48` is the pokecrystal commit Crystal Legacy was forked from: 1,850 of
its 2,477 `.asm` files match that commit byte for byte, more than any other
commit. Diffing against it keeps pokecrystal's own later refactors out of the
mods.

## Releasing

All mods share one version. To release, bump `VERSION` in `tools/build.py`,
rebuild, then push a matching tag (e.g. `v0.2.0`). The **Package mods** workflow
attaches every `<id>-<version>.zip` to a GitHub release. gen1recomp's updater
reads the version from the tag, then picks each mod's own zip from that release.

## License

Crystal Legacy's repository has no license file, so these mods are
**unlicensed for now** (all rights reserved by the respective authors). Please
don't redistribute builds until permission from the Crystal Legacy team is
sorted out. Pokémon is © Nintendo / Creatures Inc. / GAME FREAK inc. This is a
fan project with no affiliation, and it contains no ROM data.
