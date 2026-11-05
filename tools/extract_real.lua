-- Run gen1recomp's real Crystal importer on a ROM you own and dump the tables
-- the mods write to, as a local test fixture. The output is ROM-derived:
-- keep it out of the repository.
--   cd <gen1recomp> && luajit <repo>/tools/extract_real.lua <rom.gbc> <out dir> <rom sha1>
package.path = "./?.lua;./?/init.lua;" .. package.path
love = love or require("tests.love_stub")
local Json = require("src.link.Json")
local LuaWriter = require("src.import.LuaWriter")
local Extractor = require("src.import.RomExtractorGen2")
local romPath, outPath = arg[1], arg[2]
local function read(p) local f = assert(io.open(p, "rb")) local s = f:read("*a") f:close() return s end
local manifest = Json.decode(read("tools/rom_manifest_crystal.json"))
local rom = read(romPath)
local sha1 = arg[3]
local e = Extractor.new(rom, manifest, nil, sha1)
local out = {}
e.write = function(_, name, value) out[name] = value end
e.save = function() end
e.writeCompressedPic = function() return nil end
e.write2bpp = function() end
e:extractConstants()
e:extractTilesets()
local maps = e:extractMaps()
e:extractSprites()
local std = e:extractStdScripts()
e:extractScriptsAndText(maps, std)
e:extractText()
e:extractPokemon()
e:extractMoves()
e:extractItems()
e:extractMarts()
e:extractEncounters()
e:extractTrainers()
local keep = {}
for k, v in pairs(out) do keep[k] = v end
local names = {} for k in pairs(keep) do names[#names + 1] = k end
table.sort(names)
print("datasets: " .. table.concat(names, ", "))
-- One file per dataset (as data/generated/ holds them): a single chunk would
-- exceed LuaJIT's per-function constant limit.
for name, value in pairs(keep) do
  local fh = assert(io.open(outPath .. "/" .. name .. ".lua", "wb"))
  fh:write(LuaWriter.encode(value))
  fh:close()
end
