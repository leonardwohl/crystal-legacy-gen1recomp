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
| Hardcore Mode: no healing fainted mons (Center, items, Day-Care), release from PC, reset on whiteout | `engine/pokemon/health.asm`, `engine/events/{daycare,whiteout}.asm`, `engine/pokemon/bills_pc.asm`, `engine/items/item_effects.asm` | ✅ opt-in toggle; the Cherrygrove rival fight stays "can lose" | Legacy Hard Mode |
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
| Goldenrod rooftop sale prices | `data/items/rooftop_sale.asm` | ✅ gen1recomp opened the rooftop clerk as a plain mart 0 (its mart screen knows types 0–3); the wrapper serves the sale lists at Legacy's prices. Buy/Sell menu shown where the cart goes straight to Buy | Shop Changes |
| Running (hold B), faster surfing (hold B) | `engine/overworld/player_movement.asm` | ✅ (no running sprite) | Quality of Life |
| "Use another Repel?" when one wears off | `engine/events/repel.asm` | ✅ | Quality of Life |
| Pack: START sorts items | `engine/items/{pack,switch_items}.asm` | ✅ sorts silently (no "Sorting items!" box) | Quality of Life |
| Pokémon Center nurse skips her speech after the first visit | `engine/events/std_scripts.asm` | ✅ | Quality of Life |
| Day-Care keeps the experience earned (vanilla already heals; it reset exp to the level's minimum) | `engine/pokemon/move_mon.asm` | ✅ | Quality of Life |
| Move Reminder | `engine/events/move_reminder.asm` | ✅ | Story Changes |
| Exp. Share and Pokédex rework | various | ➖ left to other gen1recomp mods (by request) | – |

## Vanilla bug fixes

Crystal Legacy fixes many of the bugs pret documents. gen1recomp reproduces
some on purpose and simply doesn't have others, so each was checked against
its source. Ported fixes live in **Crystal Legacy: Bug Fixes**.

✅ ported · ➖ gen1recomp already behaves correctly · 🔜 still to check

| Fix | Legacy source | Status |
|---|---|---|
| Poké Balls: burn / poison / paralysis give a catch bonus | `engine/items/item_effects.asm` | ✅ |
| Fast Ball (all flee-prone mons), Moon Ball (Moon Stone), Love Ball (opposite gender) | `item_effects.asm` | ✅ via gen1recomp's own `fixBugs` arms; the high-HP rounding quirk Legacy keeps is left alone |
| Heavy Ball reads the wrong dex bank for three species | `item_effects.asm` | ➖ gen1recomp reads weights straight from the Pokédex |
| A Transformed wild Pokémon is caught as Ditto | `item_effects.asm` | ➖ gen1recomp restores the species it was sent out as |
| Held-item catch bonus never applied | `item_effects.asm` | 🔜 check whether any item carries it |
| AI: Mean Look checks the AI's own toxic instead of the player's | `engine/battle/ai/scoring.asm` | ✅ |
| AI: Full Heal / Full Restore leave Nightmare | `engine/battle/ai/items.asm` | ✅ |
| AI: Full Heal / Full Restore leave confusion | `ai/items.asm` | ➖ gen1recomp already clears it |
| Counter / Mirror Coat answer stale damage after a non-damaging turn | `move_effects/{counter,mirror_coat}.asm` | ➖ gen1recomp only counts damage taken this turn |
| "Has PP" check confused by PP Ups | `engine/battle/core.asm` | ➖ gen1recomp stores PP and PP Ups separately |
| Redundant Fly / Dig check after the hit check (Lock-On, Mind Reader) | `effect_commands.asm` | 🔜 no such check found by name in gen1recomp; needs a behaviour test |
| Day-Care resets exp to the level's minimum | `engine/pokemon/move_mon.asm` | ✅ in Quality of Life |
| Magikarp length thresholds | `engine/events/magikarp.asm` | 🔜 gen1recomp keeps the bug (`Specials.lua`) |
| Both Pokémon fainting at once | `engine/battle/core.asm` | 🔜 check |
| Wild Pokémon's status lowers its stats on send-out | `core.asm` | 🔜 check |
| Confusion self-damage ignores held-item boosts | `effect_commands.asm` | 🔜 check |
| Boosted stats capped at 999 (Light Ball etc.) | `effect_commands.asm` | 🔜 check |
| Psywave never deals 0 | `effect_commands.asm` | 🔜 check |
| Beat Up, Rage / AncientPower effect order | `effect_commands.asm`, `data/moves/effects.asm` | 🔜 check |
| Level 1 has 0 exp (Medium-Slow underflow) | `engine/pokemon/experience.asm` | 🔜 check |
| Breeding uses the party mon's DVs | `engine/pokemon/breeding.asm` | 🔜 check |
| Can't surf into an object; edge-warp bump sound | `engine/events/overworld.asm`, `player_movement.asm` | 🔜 check |

## Presentation only (not ported)

Pokédex area / moves / evolution / stats pages and colours, per-species menu
icons and their palettes (used here only for overworld Pokémon sprites),
stats screen layout, trainer card, battle weather icon, hidden-TM move names,
naming screen and map sign graphics, title and credits, text engine tweaks.
