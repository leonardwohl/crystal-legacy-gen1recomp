# Legacy: Story Changes

Crystal Legacy's story, event and dialogue changes for gen1recomp's Crystal,
using Crystal Legacy's own scripts and text.

## What's in

Every map Crystal Legacy changed is ported (131 of them), apart from the
exclusions below. That includes:

- **Team Rocket:** Archer (his own class, art and sprite) in the Radio Tower
  and the Rocket Hideout, and Giovanni.
- **Trainer House:** the opponent rotates by weekday: Smith (Mon/Thu/Sat),
  Craig (Tue/Fri) and Weebra (Wed/Sun).
- **Silver Cave:** after you beat Red, Mewtwo appears; after the Mewtwo
  encounter, Red can be fought again with his level-93 rematch team.
- **Fossils:** Old Amber, Dome Fossil and Helix Fossil, revived at the Ruins
  of Alph research centre.
- **Legendaries and events:** the legendary birds and Mew on Route 24,
  Celebi, the Mt. Mortar and Lake of Rage changes, Kurt, the Goldenrod Flower
  Shop's Squirtbottle and Gold Berry, and more.
- **Move Reminder:** the new NPC in Blackthorn's Move Deleter's house, free,
  for any level-up move a Pokémon could have learned by its level.
- **Kanto gyms** and the many smaller dialogue fixes across both regions.
- **Overworld Pokémon and sprites:** about 30 new walking and Pokémon
  sprites, with Crystal Legacy's art.

## Not in, and why

- **Johto gyms and the Elite Four rooms**: Rematches, Trainer Changes and
  Legacy Hard Mode already change those scripts. Porting them here as well
  would double up the rematch offers and badge switches, so their dialogue
  tweaks are not included.
- **Celadon Dept. Store 3F/5F**: handled by Shop Changes.
- **Hard Mode branches** in Crystal Legacy's scripts are left switched off;
  the Legacy Hard Mode mod applies those rules on its own.

The Flower Shop's berry clerk sells through Shop Changes' extra shop lists, so
install Shop Changes too to buy berries there.

## How it works

`tools/story/build_story.py` assembles Crystal Legacy's map files with RGBDS
against vanilla pokecrystal's constants. Every vanilla constant gets its
vanilla number, and every vanilla label links to its vanilla address. It
then lets gen1recomp's own importer decode the result, so the scripts, text
and movements are in exactly gen1recomp's format, under keys in banks `$80`
and up that no vanilla script uses. At load time the mod registers them and
points the maps' events at them.

Crystal Legacy's new event flags, sprites and items need numbers vanilla
doesn't use, and saves store those numbers. So they are pinned in
`tools/story/event_ids.json` and `tools/story/sprite_ids.json`, and never
change between releases:

- **Events:** ids vanilla leaves unused.
- **Sprites:** $67+ for people, $a3+ for Pokémon.
- **Fossils:** item slots $93-$95, as in Crystal Legacy.

Crystal Legacy's Move Reminder is engine code, not a script. Its
`special MoveReminder` row is swapped at build time for a mod command that
runs the same flow on gen1recomp's party menu and learn-move prompt. That
part needs the `engine_internals` permission.

Games: Crystal (1.0 and 1.1). Needs gen1recomp >=0.4.0 <0.5.0. Works with or
without the other Crystal Legacy mods.
