# gen1recomp Gen 2 modding notes (handoff)

Technical notes from building the Crystal Legacy mods in this repo. They are
written for someone starting a new gen1recomp mod for Gold/Silver/Crystal.
Everything here was checked against gen1recomp's source (checkout from
early November 2026, commit `5bf900e`). The engine moves quickly, so check
again before relying on any internal.

## Getting set up

- Clone gen1recomp and read its source. It is the only real documentation.
  The useful places:
  - `src/mods/` holds the loader, `Runtime`, `ManagerState`, `Gen2Compat`
    and `UnifiedCallbacks`.
  - `src/ui/gen2/`, `src/battle/gen2/`, `src/world/gen2/`,
    `src/core/gen2/` and `src/script/gen2/` hold the Gen 2 engine.
  - `src/import/RomExtractorGen2.lua` shows how ROM data becomes Lua
    tables: field names, colour scales and which assets are generated.
  - `tools/modkit.py` is the mod checker:
    `python3 tools/modkit.py --repo <engine> {validate,lint,gen2check} <moddir>`.
- Keep a pret checkout (`pokecrystal`, plus `pokegold` if you need Gold or
  Silver) next to it. The engine's comments cite `file.asm:line` all the
  time, so the disassembly is how you work out what a function is meant to
  do.
- Tests: LuaJIT can load mods through the real loader, with no LÖVE window.
  Copy the harness in `tests/load_test.lua` and `tools/test.sh`. It runs
  modkit checks, then loads each mod alone and all of them together, using
  either a synthetic data fixture or a real importer dump
  (`tools/extract_real.lua`, run against a ROM you own; keep the dump out
  of the repo).
  - The synthetic fixture has no ROM text, no accuracy tables and no menu
    graphics. Code that needs any of those can only be tested on a real
    dump, or with stand-ins made in the test.
  - `love.graphics` is stubbed, so draw calls "run" but nothing is
    rendered. Draw tests only prove that the code doesn't raise errors.
    Look at the screens in game yourself.

## Mod layout and API (api 2)

```
mods/<id>/manifest.json   id, name, version, api 2, games ["crystal"] or ["gen2"],
                          category, permissions (e.g. ["engine_internals"]),
                          optional_dependencies
mods/<id>/main.lua        return function(mod) ... end  (see existing mods)
```

- **Content registries** live in `mod.content.<registry>`, with
  `:get`, `:patch`, `:register` and `:override`, and `mod.DELETE` to
  remove a field. Examples: `trainers`, `item_effects`, `screens`.
  Patch one record at a time and log each refusal; the `patch()` helper in
  `tools/build.py` shows how.
- **Hooks** use `mod.hooks:wrap(name, function(nextFn, ...) ... end)`.
  Ones used here:
  - `trainer.party(nextFn, class, member, party)`: `party` is the list of
    already-built Mon tables. Setting `mon.nickname`, `mon.dvs` or
    `mon.statExp` works, because stats are refreshed afterwards.
  - `exp.gain(nextFn, ctx)`: ctx has `mon`, `participants`, `halved`,
    `luckyEgg`, `battle`, `defeatedDef` and `level`.
  - `movement.speed` and `pokemon.icon(nextFn, path, ctx)`: set
    `ctx.trueColor` to draw an icon in its own colours.
  - `ui.options.rows(nextFn, game, rows)`: the pause OPTIONS rows. Use
    `mod.ui.insertBefore(rows, "MODS", row)`.
- **Events** use `mod.events:on(...)` with `game.ready`, `map.entered`,
  `battle.started` / `battle.ended`, `world.blacked_out` and
  `mod.options_changed`.
- **Options** use `mod.options:define{...}` (types `toggle`, `choice`,
  `number`, `text`) and `mod.options:get(key)`. The MODS menu draws them
  automatically, with one box per row.
  `ManagerState.setOption(proxy, modId, key, value)` saves the same value
  from your own screens. `tools/legacy_options.lua` shows a shared options
  page done this way.
- **Other API pieces:**
  - `mod.save` stores per-save data.
  - `mod.exports` exposes things to tests (`loader.exports[id]`).
  - `mod:find(id)` returns only `id`, `version` and `exports`.
  - `mod:info(relpath)` checks your own files.
  - `mod.path .. "/file.png"` can be passed to `Assets.image` and
    `Assets.imageData`.
- **Sandbox:** `love.filesystem` is blocked. Reading or recolouring your
  own images goes through
  `Assets.compose(key, function() local img = Assets.imageData(path) ... return img end)`,
  after which the key works as an image path.
- **`engine_internals`** permission allows `require("src....")`. Most
  real mods need it.

## Changing engine behaviour

Most Gen 2 behaviour can't be reached through hooks. The approach that
works is to require the engine module and replace its functions, keeping
the originals:

```lua
local ok, Battle = pcall(require, "src.battle.gen2.Battle")
if ok and Battle.giveExperiencePass then
  local orig = Battle.giveExperiencePass
  Battle.giveExperiencePass = function(self, ...) ... return orig(self, ...) end
end
```

- Instances use `setmetatable(..., {__index = Module})`, so replacing a
  module function also changes every existing instance.
- Always `pcall(require)`, check that the function exists, and log a
  warning if it doesn't. Function names change between engine versions.
- Some "methods" are installed onto `Battle` when the module loads, by
  `CrystalRules.install` and `MoveRules.install`. They exist once you
  require `Battle`, and you wrap them the same way.
- Some tables are local to their module. Where a module exposes them (for
  example `SummaryMenu.PAGE_PALETTES` and `PAGE_TINTS`), you can add
  entries in place.
- A wrapped `Battle.emit(self, event)` sees every battle message
  (`event.kind == "message"`, `event.text`). That is the last place to
  rewrite text the engine builds itself.

### Where things live (Gen 2)

| Area | Module / function |
|---|---|
| Battle flow, moves, text | `src/battle/gen2/Battle.lua`: `useMove`, `accuracyRoll`, `failText`, `moveText`, `romText(label, user, target)`, `primaryStatusRefusal`, `applyStatus`, `giveExperiencePass`, `hiddenPower` |
| Mon data | `src/battle/gen2/Mon.lua`: `Mon.new`, `stats`, `hpDV`, `experienceGain`, `gainStatExp`, `growthFor`, `experienceForLevel`, caught data (`caughtTime` 1-3, `caughtLevel`, `caughtLocation` = landmark byte) |
| Stats screen | `src/ui/gen2/SummaryMenu.lua`: pages are numbered 1-3; there are `*Placements` methods and `draw*Page` methods |
| Trainer card | `src/ui/gen2/TrainerCard.lua`: has `drawBadges`, `colorsAt` and `pages` (page 3 is the Kanto page) |
| Pokédex | `src/ui/gen2/PokedexMenu.lua`: has `update`, `drawPanel` and `drawPic`. There is an older Gen 1 file at `src/ui/PokedexMenu.lua` |
| Options screen | `src/ui/gen2/OptionsMenu.lua`, and `src/ui/OptionRows.lua` (Gen 1 boxes) |
| Text / tiles | `src/ui/gen2/Chrome.lua`: `print`, `printThrough`, `textbox`, `cursor`, `number`, `letterbox`, `fitScale`, `fitOrigin`. `src/ui/gen2/TileSheet.lua` |
| Palettes | `src/world/gen2/Palettes.lua` (`monColors(data, species, shiny)`) and `src/render/GbcPalette.lua`. Colours are 0-255 RGB, converted from 5-bit with `floor(v*255/31+0.5)` |
| Events / flags | `src/world/gen2/Events.lua` (`events:get(id)` with numeric EVENT ids). Script VM is `src/script/gen2/Vm.lua` |
| World | `src/world/gen2/World.lua` (`landmarkName(id)`, `healParty`, `startBattle`, ...) |
| Unown | `src/core/gen2/Unown.lua` (`Unown.dex(save)`, `Unown.index(letter)`) |

### Screens

- A screen is a table with `update(dt)` and `draw()`. Register it with
  `mod.content.screens:register(name, { new = fn })` and open it with
  `require("src.ui.Screens").push(game, name)`. `game.stack:pop()` closes
  it.
- Input is read with `game.input:wasPressed("a"|"b"|"start"|"select"|"up"|...)`.
- To look like Crystal, draw with `Chrome`, one 8x8 tile per cell
  (20x18). Add `wantsFillScale`, `drawsWidescreen` and `drawWidescreen`;
  copy them from any `src/ui/gen2` screen.

## Text and font gotchas

- Crystal's font **has no** `< > = +`. In strings, `#` is a macro that
  prints "POKé". `<LV>`, `<ID>`, `№` and `é` are single tiles.
- When fitting text, count tiles with `Font.split`, not with `#str`.
- Lowercase letters exist.
- `Strings(fmt, ...)` and `Strings.source(...)` are the engine's
  string-building helpers.

## Data shapes worth knowing

- Trainer parties are records under `mod.content.trainers` by class. Each
  has `trainers[i] = { id, name, party, trainerType }`, and party entries
  hold `level`, `species`, `item` and `moves`. DVs, stat exp and
  nicknames are not part of the record. Apply them through the
  `trainer.party` hook.
- Badges: `save.player.badges` (Johto) and `save.player.kantoBadges` are
  keyed by name (`"ZEPHYR"`, `"BOULDER"`, ...).
- ROM text: `battle:romText("DidntAffect1Text", ...)` throws an error if
  the label isn't in the imported text cache.

## Releasing through gen1recomp's mod browser

- gen1recomp's **Find mods** reads an `index.json` feed. Either a GitHub
  `owner/repo` (its releases) or a raw URL to a feed file works.
- If two sources list the same mod id, the source added first wins.
- Listings are cached for 24h.
- The per-mod updater ignores prereleases.
- `tools/package.py`, `tools/make_index.py` and
  `.github/workflows/mods.yml` in this repo are a working setup. Every
  push produces a dev build `<next patch>-dev.N`, plus fixed-name
  `<id>-dev.zip` aliases so stale cached feeds still download. The stable
  release comes from a `workflow_dispatch` with a `vX.Y.Z` tag that must
  match the manifests.

## Things that cost time

- Gen 2 trainer DVs/stat exp/happiness are not in party rows; use
  `trainer.party`.
- The engine's `gen2check` lint flags `require("src.ui.OptionRows")` as
  MK402. That is a false positive: Crystal's own options menu uses it.
- `tools/modkit.py` also enforces manifest fields. Run `validate` early.
- When a pret label differs between pokecrystal commits, check the commit
  your data comes from (Crystal Legacy forked at `82e315e48`).
