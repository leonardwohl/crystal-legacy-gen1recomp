# Generated change list

Written by `tools/convert.py`. Counts are what the converter found
different between pokecrystal (base) and Crystal Legacy.

## Ported

| Area | Changed records |
|---|---|
| Pokémon (any field) | 251 |
| &nbsp;&nbsp;`baseStats` | 48 |
| &nbsp;&nbsp;`eggSteps` | 251 |
| &nbsp;&nbsp;`evolutions` | 15 |
| &nbsp;&nbsp;`levelMoves` | 228 |
| &nbsp;&nbsp;`tmhm` | 95 |
| Moves | 90 |
| Item prices | 38 |
| Shops (existing) | 13 |
| Trainer classes rewritten | 66 |
| Trainer parties with custom DVs/stat exp | 8 |
| Grass encounter tables | 54 |
| Water encounter tables | 5 |
| Bug-Catching Contest table | unchanged |
| Ghost special / Dark physical | yes |

## Found but not ported yet

- New shops (need map scripts to open them): MART_CELADON_3F_2, MART_CELADON_5F_1_2, MART_CELADON_5F_2_2, MART_BERRYS, MART_BERRYS_2
- New trainer classes (need pics, names and scripts): BOSS, ROCKET_LEADER, PKMNTRAINERF
- Added trainer parties, e.g. rematches (data is in, but nothing in vanilla map scripts starts these battles yet): 22
- New items: DOME_FOSSIL, HELIX_FOSSIL, OLD_AMBER
- COOLTRAINERF party 21 SEADRA: move slot reads `SUPER_NERD` in Crystal Legacy's source (a trainer class); the ROM assembles it as TWINEEDLE, so that is used.
