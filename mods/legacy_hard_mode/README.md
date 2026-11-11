# Legacy: Hard Mode

Crystal Legacy's optional Hard Mode for gen1recomp's Crystal. Two switches, in
**OPTIONS → CRYSTAL LEGACY** or the mod's settings in the MODS menu:

- **HARD MODE** (on by default): level caps, Set style and no items against
  trainers, all together.
- **HARDCORE** (off by default): the rules below.

## Rules

- **Level caps.** Pokémon at the cap gain no experience, and Rare Candy has no
  effect on them. Experience also stops exactly at the cap rather than
  overshooting it. The Day-Care follows the same cap: a Pokémon left there
  stops growing at the current cap.
- **Set style against trainers.** No free switch when the foe's Pokémon faints.
  Your own Shift/Set option is restored after each battle.
- **No items against trainers.** The PACK shows "Items can't be used here."
- **Hardcore** (off by default; switch it on in the options):
  - fainted Pokémon stay fainted: the Pokémon Center, Mom and Sacred Ash heal
    only the ones still standing;
  - Revive, Max Revive and Revival Herb can't be used, and Rare Candy and
    vitamins do nothing on a fainted Pokémon;
  - the PC and the Day-Care won't take a fainted Pokémon;
  - whiting out sends you back to the title screen, to carry on from your last save;
  - the first rival fight in Cherrygrove is a real battle: the rival gloats, then
    losing it is a whiteout.

## Cap schedule (from Crystal Legacy)

| Progress | Cap |
|---|---|
| Start | 10 |
| Badges 1–4 | 16, 21, 25, 31 |
| Badges 5–7 (any order) | 36, 38, 45 |
| Rising Badge (8) | 50 |
| Beat Will / Koga / Bruno | 52 / 54 / 55 |
| Beat Lance | 60 |
| 9–16 total badges | 62, 63, 64, 66, 66, 67, 69, 69 |
| Elite Four rematch with 16 badges | 77 |
| Beat Red | 100 |

Crystal Legacy writes the cap from its map scripts. This mod works it out from
the save instead (badges and vanilla event flags), so it also works on an
existing save. It records two wins vanilla does not track: the Elite Four
rematch (which needs the Rematches mod) and Red.

## Not included yet

- **Gen 1 and Gen 3**: the rules would port, but they need cap tables of their
  own (Yellow Legacy has one for Gen 1).

Games: Crystal. Needs gen1recomp >=0.4.0 <0.5.0. It uses the `engine_internals`
permission to wrap the battle PACK screen.
