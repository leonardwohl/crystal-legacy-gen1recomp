# Crystal Legacy: Story Changes

Crystal Legacy's story and event changes for gen1recomp's Crystal, ported map
by map. Uses Crystal Legacy's own scripts and dialogue.

## What's in so far

- **Trainer House:** the opponent rotates by weekday: Smith (Mon/Thu/Sat),
  Craig (Tue/Fri) and Weebra (Wed/Sun), each with their Legacy team, dialogue
  and art.
- **Archer:** Team Rocket's leader, with his own class and art, in the Radio
  Tower (5F) and Rocket Hideout (B3F).
- **Silver Cave:** after you beat Red, Mewtwo appears; after the Mewtwo
  encounter, Red can be fought again with his level-93 rematch team.

Archer, Giovanni, Mewtwo and Murkrow use Crystal Legacy's own overworld
sprites and battle art. New sprites go on sprite numbers vanilla Crystal
leaves free ($67+ for people, $a3+ for Pokémon), named through the
`constants` registry so objects and variable sprites both find them.

## Not in yet

- The rest of Crystal Legacy's story maps: Ruins of Alph, Mt. Mortar, Lake of
  Rage, Kurt, the Mahogany Mart, the Goldenrod Flower Shop's Squirtbottle and
  Gold Berry flow, the Rocket trigger after the middle gyms, and Giovanni.
- Dialogue tweaks on maps whose scripts are otherwise unchanged.

## How it works

`tools/story/build_story.py` assembles Crystal Legacy's map files with RGBDS
against vanilla pokecrystal's constants. That gives every vanilla constant
its vanilla number, and links every vanilla label to its vanilla address. It
then lets gen1recomp's own importer decode the result, so the scripts, text
and movements are in exactly gen1recomp's format. They live under keys in
banks `$80` and up, which no vanilla script uses. At load time the mod
registers them and points the maps' events at them. Crystal Legacy's new
event flags reuse event ids that vanilla leaves unused (22, 59, 60).

Games: Crystal (1.0 and 1.1). Needs gen1recomp >=0.4.0 <0.5.0. Works with or
without the other Crystal Legacy mods; Hard Mode's level caps also count the
Red rematch.
