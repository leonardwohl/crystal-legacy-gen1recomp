# Legacy: Bug Fixes

The vanilla Crystal bugs Crystal Legacy fixes and gen1recomp still reproduces: Poké Ball catch bonuses, the trainer AI and the Glacier Badge.

## What it changes

- Poké Balls: burned, poisoned and paralysed Pokémon are easier to catch (vanilla only counted sleep and freeze)
- Fast Ball works on every Pokémon that tends to run, Moon Ball on Moon Stone evolvers, and Love Ball on the opposite gender
- The catch formula's high-HP rounding quirk is kept, as in Crystal Legacy
- Trainer AI: Mean Look is favoured when *your* Pokémon is badly poisoned (vanilla checked its own)
- Trainer AI: Full Heal and Full Restore also end Nightmare
- Magikarp lengths (Lake of Rage contest) are worked out on the full number, as intended; vanilla compared only half of it
- Wild Magikarp sizes follow Crystal Legacy's rules: Magikarp over 5'3" are rare, and Lake of Rage's are usually 3' or longer (gen1recomp had no size filter at all). Toggle: MAGIKARP SIZES
- Light Ball and Thick Club can't push Attack past 999
- Hurting itself in confusion ignores held type-boosting items (vanilla boosted the hit when the chosen move's type matched the item)
- The Glacier Badge always boosts Special Defense as well as Special Attack (vanilla's check depended on the boosted Special Attack's value)
- Already correct in gen1recomp, so nothing to change: Counter / Mirror Coat after a non-damaging turn, PP Ups in the 'has PP' check, a Transformed Pokémon caught as Ditto, and Full Heal leaving the AI confused

Games: crystal. Needs gen1recomp >=0.4.0 <0.5.0.

Generated from [Pokémon Crystal Legacy](https://github.com/cRz-Shadows/Pokemon_Crystal_Legacy) by `tools/build.py`. All design credit to the Crystal Legacy team. See the [repository README](../../README.md).
