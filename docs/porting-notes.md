# Porting notes

## How the conversion works

1. `tools/parse.py` reads the data tables both trees share: base stats,
   evolutions and learnsets, egg moves, moves, item prices, shops, trainer
   parties and wild encounters.
2. `tools/convert.py` diffs Crystal Legacy against pokecrystal `82e315e48`
   (its fork point). It writes only the changed values into `mod/main.lua`
   as gen1recomp patches, using gen1recomp's native Crystal record shapes
   (`"api": 2`, `"games": ["crystal"]`). The portable API 3 shapes would drop
   Crystal-only detail such as separate morning, day and night encounter slots.
3. At load time, `main.lua` patches each record and logs anything gen1recomp
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
  `generated-changes.md`.

## Next steps, roughly by value

1. **Rematches:** port the gym leader and Elite Four rematch scripts through
   `map_scripts`. The rematch teams are already in the trainer data.
2. **Hard Mode / level caps:** there is no rules system on Gen 2 yet, so this
   needs hooks. The `trainer.party` hook can already scale parties.
3. **New items:** register the fossils with fresh item indices and add the
   scripts that hand them out.
4. **Map script changes:** gift Pokémon, item placements and story beats.
   About 150 map files changed in Crystal Legacy.
5. **Text:** move descriptions, and dialogue through the `text` registry
   (Crystal's text ids are ROM pointers).
