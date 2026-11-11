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
| [Pokémon Changes](../mods/crystal_legacy_pokemon) | Base stats, learnsets, TM/HM and egg moves, evolutions, move changes | ✅ ready to try |
| [Trainer Changes](../mods/crystal_legacy_trainers) | Every trainer and leader team, with items, moves, DVs; Pryce, Jasmine and Chuck scale to your badges | ✅ ready to try |
| [Encounter Changes](../mods/crystal_legacy_encounters) | Wild grass and surfing Pokémon | ✅ ready to try |
| [Fast Eggs](../mods/fast_eggs) | Eggs hatch in about a quarter of the steps (Gold, Silver, Crystal) | ✅ ready to try |
| [Ghost/Dark Switch](../mods/crystal_legacy_ghost_dark) | Ghost moves special, Dark moves physical (Gold, Silver, Crystal) | ✅ ready to try |
| [Shop Changes](../mods/crystal_legacy_shops) | Shop stock and prices, Celadon TM upgrades, the Flower Shop berry clerk | ✅ ready to try |
| [Rematches](../mods/crystal_legacy_rematches) | Gym leaders after the Elite Four; Elite Four and Lance with 16 badges | ✅ ready to try (Red: see Story) |
| [Legacy Hard Mode](../mods/legacy_hard_mode) | Level caps, Set mode and no items in trainer battles (Crystal) | ✅ ready to try; Hardcore is an opt-in toggle; Gen 1/3 later |
| [Quality of Life](../mods/crystal_legacy_qol) | Run with B, reuse Repels, START sorts the PACK, quick nurse, Day-Care keeps exp (Crystal) | 🧪 new; each part can be toggled |
| [Bug Fixes](../mods/crystal_legacy_fixes) | Legacy's fixes for vanilla bugs gen1recomp reproduces: catch bonuses, Fast / Moon / Love Ball, trainer AI (Crystal) | 🧪 new; more after the remaining checks |
| [Menu Icons](../mods/crystal_legacy_icons) | Legacy's per-species party icons and colours; bring your own icons (copy Crystal Legacy's `gfx/icons` in as `icons/`) | 🧪 new |
| [Pokédex](../mods/crystal_legacy_pokedex) | Crystal Legacy's extra Pokédex pages (after Nayru62's Pokédex): SELECT on an entry for Stats, Level-up / TM/HM / Egg moves, Evolution and Area; START for shiny colours; a POKéDEX COLOR setting | 🧪 new |
| [Screens](../mods/crystal_legacy_screens) | Crystal Legacy's fourth stats page (met location, time and level; DVs; Hidden Power once every Unown is caught) and happiness on the stats screen | 🧪 new |
| [Story Changes](../mods/crystal_legacy_story) | 131 changed maps: Rocket story, Trainer House, fossils, legendaries, Red rematch, new sprites, dialogue | ✅ ready to try |

Every mod works on its own, and they can be combined freely. Trainer Changes
and Rematches are written so that either can be installed without the other.

The headbutt tree and Rock Smash tables are identical in Crystal Legacy and
vanilla, so there is nothing to port there. Crystal Legacy leaves the Exp. Share
itself as it is in vanilla.

## Install

### From inside gen1recomp (recommended)

1. Use gen1recomp **0.4.x** with a US Pokémon Crystal ROM (1.0 or 1.1) imported.
2. Open **MODS → Find mods**, add a source, and enter one of these feeds:
   - **Stable** (releases): `leonardwohl/crystal-legacy-gen1recomp`
   - **Dev** (a build of every push to `main`, for testing):
     `https://raw.githubusercontent.com/leonardwohl/crystal-legacy-gen1recomp/main/site/dev/data/index.json`
3. Install the mods you want from the list, and enable them for Crystal. A new
   game is recommended.

Add **only one** of the two. When two sources list the same mod, gen1recomp
keeps the one from the source added first and hides the other, so a stable
source added before the dev one keeps every card on the stable version. To
switch channels, remove the old source first.

Dev builds are versioned `<next patch>-dev.<build>` (e.g. `0.2.2-dev.17`), so
each new one shows up as an update in Find mods, and the next release
supersedes them. A mod's own update check (its GitHub releases) skips dev
builds, so update dev builds from Find mods.

### By hand

Download the `.zip` for each mod from
[Releases](https://github.com/leonardwohl/crystal-legacy-gen1recomp/releases)
and use **MODS → Import mod .zip**.

## Repository layout

```
mods/<id>/        one folder per mod: manifest.json, main.lua, README.md
tools/parse.py    reads pokecrystal-style data tables
tools/legacy_diff.py  diffs Crystal Legacy against its fork point
tools/build.py    generates the data mods under mods/
tools/package.py  zips each mod as <id>-<version>.zip (--dev N for dev builds)
tools/make_index.py  writes the gen1recomp mod feed (site/data, site/dev/data)
tools/story/      Story Changes: assemble Legacy maps with RGBDS, decode with gen1recomp
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

For a stronger check, dump gen1recomp's real import of a Crystal ROM you own
(1.0 and/or 1.1) and run the same tests against it. The dump is ROM-derived,
so keep it outside the repo:

```bash
cd path/to/gen1recomp
luajit path/to/repo/tools/extract_real.lua crystal.gbc /tmp/dumps/crystal10 "$(sha1sum crystal.gbc | cut -d' ' -f1)"
```

```bash
CL_REAL="/tmp/dumps/crystal10" tools/test.sh path/to/gen1recomp base
```

`82e315e48` is the pokecrystal commit Crystal Legacy was forked from: 1,850 of
its 2,477 `.asm` files match that commit byte for byte, more than any other
commit. Diffing against it keeps pokecrystal's own later refactors out of the
mods.

### Rebuilding Story Changes

Story Changes is built separately, because it needs RGBDS 0.5.2 and a built
vanilla pokecrystal (for its symbol file):

```bash
PATH=path/to/rgbds:$PATH make -C base crystal
python3 tools/story/build_story.py --base base --legacy legacy --rgbds path/to/rgbds --engine path/to/gen1recomp --work /tmp/story-work
```

Sprite art the builds read (Story's overworld and trainer sprites, Quality of
Life's running sprite) comes from this repository's `gfx/` folder when a file is
there, and from the `--legacy` checkout otherwise.

Everything ROM-derived (the built ROM, the patched scratch ROM, the decoded
output) stays in `--work`. Only Crystal Legacy's own scripts and text end up
in the mod.

## Releasing

All mods share one version. To release, bump `VERSION` in `tools/build.py`
(and `legacy_hard_mode`'s manifest), rebuild, push, then either:

- **Actions → Package mods → Run workflow**, with the version (e.g. `v0.2.0`).
  It creates the tag and the release on the chosen commit.
- Or create a release for a new `v…` tag in GitHub's Releases page, or push
  such a tag; the workflow attaches the zips to it.

Every `<id>-<version>.zip` is attached to the release. gen1recomp's updater
reads the version from the tag, then picks each mod's own zip from that
release.

## License

Crystal Legacy's repository has no license file, so these mods are
**unlicensed for now** (all rights reserved by the respective authors). Please
don't redistribute builds until permission from the Crystal Legacy team is
sorted out. Pokémon is © Nintendo / Creatures Inc. / GAME FREAK inc. This is a
fan project with no affiliation, and it contains no ROM data.
