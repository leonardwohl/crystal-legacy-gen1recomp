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
| Hard Mode: level caps (battles, Rare Candy, Day-Care), Set style, no items vs trainers | many, `engine/events/happiness_egg.asm` | ✅ | Legacy Hard Mode |
| Hardcore Mode: no healing fainted mons (Center, items, Day-Care), release from PC, reset on whiteout | `engine/pokemon/health.asm`, `engine/events/{daycare,whiteout}.asm`, `engine/pokemon/bills_pc.asm`, `engine/items/item_effects.asm` | ✅ opt-in toggle; the Cherrygrove rival fight stays "can lose" | Legacy Hard Mode |
| Trainer custom DVs, stat exp, happiness, nicknames | `engine/battle/read_trainer_party.asm`, `core.asm` | ✅ DVs / stat exp; nicknames skipped (cosmetic) | Trainer Changes, Rematches |
| Trainer **class** DVs (gym leaders and others get better DVs) | `data/trainers/dvs.asm` | ✅ applied where a team has no DVs of its own | Trainer Changes |
| Trainer classes no longer carry healing items | `data/trainers/attributes.asm` | ✅ | Trainer Changes |
| King's Rock, Metal Coat, Dragon Scale, Up-Grade, Brick Piece are used like evolution stones | `engine/items/item_effects.asm`, `data/items/attributes.asm` | ✅ | Pokémon Changes |
| Happiness: double from levelling, +9 from gym leaders, better haircuts and grooming | `data/events/happiness_{changes,probabilities}.asm` | ✅ happiness amounts. The odds table's edits only change which line the barber says (Legacy's new values never match the script's `ifequal 2/3`, so it always says "much happier"), so they're left out | Pokémon Changes |
| Cut has a high critical-hit ratio | `data/moves/critical_hit_moves.asm` | ✅ | Pokémon Changes |
| Metronome cannot call Explosion / Selfdestruct | `data/moves/metronome_exception_moves.asm` | ✅ | Pokémon Changes |
| Obedience: the Zephyr Badge raises the obedience level to 16 | `engine/battle/effect_commands.asm` | ✅ | Pokémon Changes |
| Fewer wild Pokémon flee (Magnemite, Eevee, Dratini, the birds…) | `data/wild/flee_mons.asm` | ✅ only Umbreon and Togetic (plus Raikou, Entei) | Encounter Changes |
| In-game trades: different Pokémon and held items | `data/events/npc_trades.asm` | ✅ Onix, Voltorb, Mr. Mime, Haunter trades | Story Changes |
| Goldenrod rooftop sale prices | `data/items/rooftop_sale.asm` | ✅ gen1recomp opened the rooftop clerk as a plain mart 0 (its mart screen knows types 0–3); the wrapper serves the sale lists at Legacy's prices. Buy/Sell menu shown where the cart goes straight to Buy | Shop Changes |
| Running (hold B), faster surfing (hold B) | `engine/overworld/player_movement.asm` | ✅ including Legacy's running sprite | Quality of Life |
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
| Held-item catch bonus never applied | `item_effects.asm` | ➖ no item in vanilla or Legacy carries `HELD_CATCH_CHANCE` |
| AI: Mean Look checks the AI's own toxic instead of the player's | `engine/battle/ai/scoring.asm` | ✅ |
| AI: Full Heal / Full Restore leave Nightmare | `engine/battle/ai/items.asm` | ✅ |
| AI: Full Heal / Full Restore leave confusion | `ai/items.asm` | ➖ gen1recomp already clears it |
| Counter / Mirror Coat answer stale damage after a non-damaging turn | `move_effects/{counter,mirror_coat}.asm` | ➖ gen1recomp only counts damage taken this turn |
| "Has PP" check confused by PP Ups | `engine/battle/core.asm` | ➖ gen1recomp stores PP and PP Ups separately |
| Redundant Fly / Dig check after the hit check (Lock-On, Mind Reader) | `effect_commands.asm` | ⛔ not ported: gen1recomp reproduces it, but Legacy's fix only fires for Nightmare / Transform / Curse / Mean Look on a locked-on target mid-Fly or Dig, and the effects are dispatched through a records registry a wrapper may not reach |
| Day-Care resets exp to the level's minimum | `engine/pokemon/move_mon.asm` | ✅ in Quality of Life |
| Magikarp length: the size table compared only the high byte | `engine/events/magikarp.asm` | ✅ |
| Magikarp wild-encounter size filter (thresholds, Lake of Rage test) | `engine/battle/core.asm` | ➖ gen1recomp has no such filter at all; adding Legacy's would be new behaviour, possible later through `encounter.*` hooks |
| Faint check repeats until nobody is left fainted | `engine/battle/core.asm` | ⛔ not ported: gen1recomp transcribes vanilla's single pass (`Battle:resolveFaints`); changing the battle loop needs a battle-flow test first |
| Confusion self-damage ignores held-item boosts | `effect_commands.asm` | ✅ |
| Light Ball / Thick Club doubling capped at 999 | `effect_commands.asm` | ✅ |
| Psywave never deals 0 | `effect_commands.asm` | ➖ gen1recomp floors it at 1 for both sides |
| Beat Up's failure path (a link-battle desync in vanilla) | `effect_commands.asm` | ➖ no link battles here |
| Status moves on an already-statused target name the status | `effect_commands.asm` | ➖ message only; the move fails either way |
| Level 1 has 0 exp (Medium-Slow underflow) | `engine/pokemon/experience.asm` | ➖ gen1recomp clamps exp at 0 |
| Egg / hatch picture uses the party mon's DVs | `engine/pokemon/breeding.asm` | ➖ presentation only (which Unown letter is drawn) |
| Can't surf into an object | `engine/events/overworld.asm` | ➖ Crystal has gen1recomp's `surfOntoNpc` fix on |
| Glacier Badge's Special Defense boost depends on the boosted Special Attack | `engine/battle/core.asm` | ✅ |

## Presentation only (not ported)

Pokédex area / moves / evolution / stats pages and colours, per-species menu
icons and their palettes (used here only for overworld Pokémon sprites),
stats screen layout, trainer card, battle weather icon, hidden-TM move names,
naming screen and map sign graphics, title and credits, text engine tweaks.
