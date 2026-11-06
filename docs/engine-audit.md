# Crystal Legacy engine audit

Every change Crystal Legacy makes outside the data tables the converters
already port, read from a diff of `engine/`, `home/` and the behaviour tables
under `data/` against pokecrystal `82e315e48`. Pokédex and other purely
presentational changes are listed at the end without detail.

Status: ✅ ported · 🔜 portable, planned · ⛔ not portable yet (no hook in
gen1recomp; the reason is given) · ➖ not needed in gen1recomp.

## Gameplay changes

| Change | Legacy source | Status | Mod |
|---|---|---|---|
| Ghost moves special, Dark moves physical | `engine/battle/effect_commands.asm` | ✅ | Ghost/Dark Switch |
| AI follows the Ghost/Dark split (Counter, Mirror Coat, screens) | `engine/battle/ai/scoring.asm` | ✅ gen1recomp's AI reads the same type categories | Ghost/Dark Switch |
| Hard Mode: level caps, Set style, no items vs trainers | many | ✅ | Legacy Hard Mode |
| Hardcore Mode: no healing fainted mons (Center, items, Day-Care), release from PC, reset on whiteout | `engine/pokemon/health.asm`, `engine/events/{daycare,whiteout}.asm`, `engine/pokemon/bills_pc.asm`, `engine/items/item_effects.asm` | 🔜 | Legacy Hard Mode |
| Trainer custom DVs, stat exp, happiness, nicknames | `engine/battle/read_trainer_party.asm`, `core.asm` | ✅ DVs / stat exp; nicknames skipped (cosmetic) | Trainer Changes, Rematches |
| Trainer **class** DVs (gym leaders and others get better DVs) | `data/trainers/dvs.asm` | ✅ applied where a team has no DVs of its own | Trainer Changes |
| Trainer classes no longer carry healing items | `data/trainers/attributes.asm` | ✅ | Trainer Changes |
| King's Rock, Metal Coat, Dragon Scale, Up-Grade, Brick Piece are used like evolution stones | `engine/items/item_effects.asm`, `data/items/attributes.asm` | ✅ | Pokémon Changes |
| Happiness: double from levelling, +9 from gym leaders, better haircuts and grooming | `data/events/happiness_{changes,probabilities}.asm` | ✅ changes; haircut odds 🔜 | Pokémon Changes |
| Cut has a high critical-hit ratio | `data/moves/critical_hit_moves.asm` | ✅ | Pokémon Changes |
| Metronome cannot call Explosion / Selfdestruct | `data/moves/metronome_exception_moves.asm` | ✅ | Pokémon Changes |
| Obedience: the Zephyr Badge raises the obedience level to 16 | `engine/battle/effect_commands.asm` | ✅ | Pokémon Changes |
| Fewer wild Pokémon flee (Magnemite, Eevee, Dratini, the birds…) | `data/wild/flee_mons.asm` | ✅ only Umbreon and Togetic (plus Raikou, Entei) | Encounter Changes |
| In-game trades: different Pokémon and held items | `data/events/npc_trades.asm` | ✅ Onix, Voltorb, Mr. Mime, Haunter trades | Story Changes |
| Goldenrod rooftop sale prices | `data/items/rooftop_sale.asm` | ⛔ gen1recomp has no rooftop sale yet | Shop Changes |
| Running (hold B), faster surfing (hold B) | `engine/overworld/player_movement.asm` | 🔜 | new: Quality of Life |
| "Use another Repel?" when one wears off | `engine/events/repel.asm` | 🔜 | Quality of Life |
| Pack: START sorts items | `engine/items/{pack,switch_items}.asm` | 🔜 | Quality of Life |
| Pokémon Center nurse skips her speech after the first visit | `engine/events/std_scripts.asm` | 🔜 | Quality of Life |
| Day-Care returns Pokémon fully healed | `engine/pokemon/{move_mon,health}.asm` | 🔜 | Quality of Life |
| Move Reminder | `engine/events/move_reminder.asm` | ✅ | Story Changes |
| Exp. Share and Pokédex rework | various | ➖ left to other gen1recomp mods (by request) | – |

## Vanilla bug fixes

Crystal Legacy fixes many of the bugs pret documents. Whether each needs a
port depends on whether gen1recomp reproduces the bug; to be checked one by one.

| Fix | Legacy source | Status |
|---|---|---|
| Both Pokémon fainting at once is handled for both | `engine/battle/core.asm` | 🔜 check |
| "Has PP" check masks PP Ups (`and PP_MASK`) | `core.asm` | 🔜 check |
| Wild Pokémon's status lowers its stats on send-out | `core.asm` | 🔜 check |
| Magikarp length thresholds | `core.asm`, `engine/events/magikarp.asm` | 🔜 check |
| Confusion self-damage ignores held-item boosts | `effect_commands.asm` | 🔜 check |
| Boosted stats capped at 999 (Light Ball etc.) | `effect_commands.asm` | 🔜 check |
| Psywave never deals 0, range 1-1.5x level | `effect_commands.asm` | 🔜 check |
| Status moves fail correctly on already-statused targets | `effect_commands.asm` | 🔜 check |
| Beat Up multi-hit handling | `effect_commands.asm` | 🔜 check |
| Rage / AncientPower effect order | `data/moves/effects.asm` | 🔜 check |
| AI type matchup, Leech Seed / Encore checks, X items clear confusion / Nightmare | `engine/battle/ai/*.asm` | 🔜 check |
| Poké Balls: status bonus, held catch chance, Transform-as-Ditto, Heavy / Moon / Love Ball | `engine/items/item_effects.asm` | 🔜 check |
| Level 1 has 0 exp (Medium-Slow underflow) | `engine/pokemon/experience.asm` | 🔜 check |
| Breeding uses the party mon's DVs | `engine/pokemon/breeding.asm` | 🔜 check |
| Can't surf into an object; edge-warp bump sound | `engine/events/overworld.asm`, `player_movement.asm` | 🔜 check |

## Presentation only (not ported)

Pokédex area / moves / evolution / stats pages and colours, per-species menu
icons and their palettes (used here only for overworld Pokémon sprites),
stats screen layout, trainer card, battle weather icon, hidden-TM move names,
naming screen and map sign graphics, title and credits, text engine tweaks.
