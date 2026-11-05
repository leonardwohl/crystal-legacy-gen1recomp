# Porting notes

## How the conversion works

1. `tools/parse.py` reads the data tables both trees share: base stats,
   evolutions and learnsets, egg moves, moves, item prices, shops, trainer
   parties and wild encounters.
2. `tools/legacy_diff.py` diffs Crystal Legacy against pokecrystal `82e315e48`
   (its fork point), and `tools/build.py` writes only the changed values into each mod's `main.lua`
   as gen1recomp patches, using gen1recomp's native Crystal record shapes
   (`"api": 2`, `"games": ["crystal"]`). The portable API 3 shapes would drop
   Crystal-only detail such as separate morning, day and night encounter slots.
3. At load time, each `main.lua` patches each record and logs anything gen1recomp
   refuses instead of aborting.

## Engine details worth knowing

- **Physical/special:** gen1recomp decides this per type, through the
  `type_chart` type records' `category`. That is how Crystal Legacy's Ghost
  special / Dark physical change is applied. The vanilla type records and
  matchups are seeded into the registry before mods run, and the load test
  checks that the matchup table survives.
- **Trainer DVs and stat exp:** gen1recomp gives every trainer Pokémon the
  vanilla fixed DVs. Crystal Legacy's extended trainer format (custom DVs,
  stat exp, happiness, nicknames) is applied through the `trainer.party`
  hook, which runs before battle stats are calculated. Nicknames are skipped
  because they are cosmetic.
- **Stat exp byte order:** Crystal Legacy writes stat exp as little-endian `dw`
  values that its loader copies straight into the big-endian field, so
  `dw $01FE` in the source means 65025 in game.
- **Shops:** gen1recomp's shop ids are the vanilla script mart numbers.
  Crystal Legacy inserts new shops into the middle of the table, so shops are
  matched by `MART_*` name. The five new shops are skipped until scripts can
  open them.
- **Typo in Crystal Legacy's source:** one Cooltrainer's Seadra has
  `SUPER_NERD` (a trainer class) in a move slot. The converter uses the move
  that the assembled ROM actually contains, and lists it in
  the build output.

## How scripts are changed without ROM addresses

Crystal scripts in gen1recomp are decoded bytecode rows keyed by ROM address
(`"55:4e2e"`). The mods never hard-code those addresses. Instead, at load time:

- **Gym leaders and clerks** are found through their map object: the leader by
  sprite (`SPRITE_FALKNER`), a shop clerk by the vanilla mart its script opens.
  Their script is replaced by a small wrapper that falls through to a copy of
  the vanilla rows.
- **Battle scripts** (Elite Four, Lance, the scaling leaders) are found by
  their `loadtrainer CLASS, 1` row, in every script list that contains it.
  Crystal Legacy's own `readvar VAR_BADGES` branch is spliced in front of it.
- **New text** is compiled from Crystal Legacy's source by `tools/textc.py`
  into gen1recomp's text format and registered under mod-owned ids.

This works for Crystal 1.0 and 1.1 alike, and ships no vanilla script or text
data. Building vanilla pokecrystal for a symbol file would give exact
addresses, but the RGBDS toolchain could not be built in this environment.

## Story Changes: scope

Crystal Legacy changes 146 map files. About 30 are Hard Mode hooks and 15 are
gym or Elite Four edits, both handled by Hard Mode, Rematches and Trainer
Changes. 66 are mostly dialogue tweaks. That leaves roughly 15-20 maps with
real story rewrites: Radio Tower 5F (Archer), Ruins of Alph, the Trainer
House (Smith, Craig, Weebra), Silver Cave (Mewtwo and the Red rematch),
Mt. Mortar, Mahogany Mart, Lake of Rage, Kurt's house, the Goldenrod Flower
Shop's Squirtbottle/Gold Berry flow, and the Rocket trigger after the last of
the three middle gyms.

These are ported by `tools/story/`, which has no hand-written script
compiler:

1. `assemble.py` assembles Legacy's map files with RGBDS against vanilla
   pokecrystal's constants and macros, so every constant gets vanilla's
   number by name. Labels outside the file are pinned at their vanilla
   addresses (from a vanilla build's symbol file), and Legacy-only names come
   from an explicit table: new trainer classes 68-70, new events on unused
   vanilla event ids, new variable sprite slots $fd/$fe, and stand-ins for
   new overworld sprites. Each map goes in its own bank from $80 up.
2. `patch_rom.py` appends those banks to a scratch vanilla ROM and repoints
   the maps' headers at them.
3. `extract_story.lua` runs gen1recomp's own importer on that ROM and keeps
   only the Legacy banks and the maps' event records, so the output is
   exactly what gen1recomp would have decoded.
4. `build_story.py` adds the new trainer classes (with Legacy's art
   coloured from its palettes) and writes the mod.

The tests check that every script, text and movement a Story row or map
event points at exists, and run the Trainer House, Archer and Red flows in
gen1recomp's script VM against real imported data.

## Next steps, roughly by value

1. **More Story Changes maps**, by adding them to `MAPS` in
   `tools/story/build_story.py`, and porting Legacy's overworld sprites.
2. **Hardcore Mode** for Legacy Hard Mode, and Gen 1 caps from Yellow Legacy.
3. **New items:** register the fossils with fresh item indices and add the
   scripts that hand them out.
4. **Map script changes:** gift Pokémon, item placements and story beats.
   About 150 map files changed in Crystal Legacy.
5. **Text:** move descriptions, and dialogue through the `text` registry
   (Crystal's text ids are ROM pointers).
