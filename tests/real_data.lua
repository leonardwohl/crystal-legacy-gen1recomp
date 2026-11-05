-- Turn a dump of gen1recomp's Crystal importer output into the `game.data`
-- table src/core/Game2.lua builds at boot, for tests/load_test.lua.
--
-- The dump itself is ROM-derived, so it is never committed: make it locally
-- with tools/extract_real.lua from a ROM you own (or one built from the
-- pokecrystal disassembly) and point CL_FIXTURE at its output directory.
return function(dir)
  local d = setmetatable({}, { __index = function(t, name)
    local ok, v = pcall(dofile, dir .. "/" .. name .. ".lua")
    rawset(t, name, ok and v or false)
    return rawget(t, name) or nil
  end })
  -- Songs are decoded by a separate audio stage; the mods only need their
  -- ids to resolve, so name every Music_* the import's constants list.
  local songs = {}
  for _, name in ipairs((d.constants or {}).musicOrder or {}) do
    songs[name] = { bank = 0, address = 0 }
  end
  return {
    audio = { songs = songs }, gen2Tilesets = d.tilesets,
    pokemon = d.pokemon, moves = d.moves, items = d.items, type_chart = d.type_chart,
    gen2Maps = d.maps, gen2Scripts = d.scripts, gen2StdScripts = d.std_scripts,
    gen2Text = d.text, text = d.rom_text or {}, gen2Trainers = d.trainers,
    gen2Encounters = d.encounters, gen2Marts = d.marts, gen2Constants = d.constants,
    gen2Roofs = d.roofs, gen2Sprites = d.sprites or {},
  }
end
