-- Load the mod through gen1recomp's real mod loader against a vanilla-Crystal
-- fixture and check that every patch lands. No ROM and no display needed.
--
--   cd <gen1recomp checkout> && luajit <this repo>/tests/load_test.lua <this repo>
--
-- The fixture comes from tools/make_fixture.py (built from the pokecrystal
-- disassembly); run tools/test.sh to do all of it in one go.

package.path = "./?.lua;./?/init.lua;" .. package.path

local repo = assert(arg[1], "usage: load_test.lua <repo root>")
local function read(path)
  local fh = assert(io.open(path, "rb"))
  local s = fh:read("*a")
  fh:close()
  return s
end

local Logger = require("src.core.Logger")
local warnings = {}
local realWarn, realError = Logger.warn, Logger.error
Logger.warn = function(fmt, ...)
  warnings[#warnings + 1] = string.format(fmt, ...)
end
Logger.error = function(fmt, ...)
  warnings[#warnings + 1] = "ERROR " .. string.format(fmt, ...)
end

local T = require("tests.modkit")
local Loader = require("src.mods.Loader")
local Runtime = require("src.mods.Runtime")

local data = dofile(repo .. "/tests/fixture_crystal.lua")
local vanillaMatchups = #data.type_chart.matchups

T.sdk.captureRuntime()
local files = {
  ["mods/crystal_legacy/manifest.json"] = read(repo .. "/mod/manifest.json"),
  ["mods/crystal_legacy/main.lua"] = read(repo .. "/mod/main.lua"),
}
local loader = Loader.new({ fs = T.sdk.memfs(files), generation = 2,
  version = "crystal", dev = true })
loader:load(data)

local mod = loader.mods.crystal_legacy
T.eq(mod ~= nil, true, "mod discovered")
T.eq(mod and mod.failed, nil, "mod loads without failing")
for _, e in ipairs(loader.errors) do print("loader error: " .. tostring(e)) end
T.eq(#loader.errors, 0, "loader reports no errors")
local refused = {}
for _, w in ipairs(warnings) do
  if w:find("crystal_legacy", 1, true) then refused[#refused + 1] = w end
end
for _, w in ipairs(refused) do print("refused: " .. w) end
T.eq(#refused, 0, "no patch refused")

-- Spot checks against values read straight from Crystal Legacy's source.
local p = data.pokemon
T.eq(p.CHIKORITA.eggSteps, 5, "egg cycles quartered (Chikorita 20 -> 5)")
T.eq(p.DRAGONITE.eggSteps, 10, "egg cycles quartered (Dragonite 40 -> 10)")
T.eq(data.type_chart.types.GHOST.category, "special", "Ghost is special")
T.eq(data.type_chart.types.DARK.category, "physical", "Dark is physical")
T.eq(data.type_chart.types.FIRE.category, "special", "Fire unchanged")
T.eq(#data.type_chart.matchups, vanillaMatchups, "type matchups kept")

local falkner = data.gen2Trainers.classes.FALKNER.trainers
T.eq(falkner[1].party[1].level, 8, "Falkner's Pidgey is level 8")
T.eq(falkner[1].party[2].species, "NOCTOWL", "Falkner leads with Noctowl second")
T.eq(#falkner, 2, "Falkner rematch roster added")
T.eq(data.gen2Encounters.grass.SPROUT_TOWER_2F.rates.MORN, 5, "grass rate stays raw byte")

-- The trainer.party hook writes Legacy's custom DVs / stat exp.
local party = { {}, {}, {}, {}, {}, {} }
local out = Runtime.call("trainer.party", function(_, _, pt) return pt end,
  "KAREN", "KAREN2", party)
T.eq(out[1].dvs and out[1].dvs.attack, 15, "Karen rematch Umbreon gets DVs")
T.eq(out[1].statExp and out[1].statExp.hp, 0xFE01, "and max-useful stat exp")
local plain = Runtime.call("trainer.party", function(_, _, pt) return pt end,
  "FALKNER", "FALKNER1", { {} })
T.eq(plain[1].dvs, nil, "other trainers untouched")

T.sdk.restoreRuntime()
Logger.warn, Logger.error = realWarn, realError
T.finish("Crystal Legacy mod load")
