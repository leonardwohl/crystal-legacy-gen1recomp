-- Load mods through gen1recomp's real mod loader against a vanilla-Crystal
-- fixture and check that every patch lands. No ROM and no display needed.
--
--   cd <gen1recomp checkout>
--   luajit <repo>/tests/load_test.lua <repo> <mod id> [<mod id> ...]
--
-- With several ids the mods load together, which is how conflicts between
-- them would show up. tools/test.sh runs every mod alone and then all of them.

package.path = "./?.lua;./?/init.lua;" .. package.path

local repo = assert(arg[1], "usage: load_test.lua <repo root> <mod id>...")
local ids = {}
for i = 2, #arg do ids[#ids + 1] = arg[i] end
assert(#ids > 0, "name at least one mod")

local function read(path)
  local fh = assert(io.open(path, "rb"))
  local s = fh:read("*a")
  fh:close()
  return s
end

local Logger = require("src.core.Logger")
local warnings = {}
local realWarn, realError = Logger.warn, Logger.error
Logger.warn = function(fmt, ...) warnings[#warnings + 1] = string.format(fmt, ...) end
Logger.error = function(fmt, ...) warnings[#warnings + 1] = "ERROR " .. string.format(fmt, ...) end

local T = require("tests.modkit")
local Loader = require("src.mods.Loader")
local Runtime = require("src.mods.Runtime")

local data = dofile(repo .. "/tests/fixture_crystal.lua")
local vanillaMatchups = #data.type_chart.matchups
local vanillaFalkner = #data.gen2Trainers.classes.FALKNER.trainers

T.sdk.captureRuntime()
local files = {}
for _, id in ipairs(ids) do
  files["mods/" .. id .. "/manifest.json"] = read(repo .. "/mods/" .. id .. "/manifest.json")
  files["mods/" .. id .. "/main.lua"] = read(repo .. "/mods/" .. id .. "/main.lua")
end
local loader = Loader.new({ fs = T.sdk.memfs(files), generation = 2,
  version = "crystal", dev = true })
loader:load(data)

local label = table.concat(ids, "+")
for _, id in ipairs(ids) do
  local mod = loader.mods[id]
  T.eq(mod ~= nil, true, id .. ": discovered")
  T.eq(mod and mod.failed, nil, id .. ": loads without failing")
end
for _, e in ipairs(loader.errors) do print("loader error: " .. tostring(e)) end
T.eq(#loader.errors, 0, label .. ": loader reports no errors")
local refused = {}
for _, w in ipairs(warnings) do
  for _, id in ipairs(ids) do
    if w:find(id, 1, true) then refused[#refused + 1] = w break end
  end
end
for _, w in ipairs(refused) do print("refused: " .. w) end
T.eq(#refused, 0, label .. ": no patch refused")

-- Spot checks per mod, against values read straight from Crystal Legacy's
-- source. Each runs only when its mod is in this load.
local p, enc = data.pokemon, data.gen2Encounters
local trainers = data.gen2Trainers.classes
local CHECKS = {
  crystal_legacy_pokemon = function()
    if not loader.mods.fast_eggs then
      T.eq(p.CHIKORITA.eggSteps, 20, "pokemon: leaves egg steps to Fast Eggs")
    end
    T.eq(data.moves.SHADOW_BALL ~= nil, true, "pokemon: moves present")
  end,
  fast_eggs = function()
    T.eq(p.CHIKORITA.eggSteps, 5, "fast eggs: Chikorita 20 -> 5")
    T.eq(p.DRAGONITE.eggSteps, 10, "fast eggs: Dragonite 40 -> 10")
  end,
  crystal_legacy_ghost_dark = function()
    T.eq(data.type_chart.types.GHOST.category, "special", "ghost/dark: Ghost special")
    T.eq(data.type_chart.types.DARK.category, "physical", "ghost/dark: Dark physical")
    T.eq(data.type_chart.types.FIRE.category, "special", "ghost/dark: Fire unchanged")
    T.eq(#data.type_chart.matchups, vanillaMatchups, "ghost/dark: matchups kept")
  end,
  crystal_legacy_trainers = function()
    local f = trainers.FALKNER.trainers
    T.eq(f[1].party[1].level, 8, "trainers: Falkner's Pidgey is level 8")
    T.eq(f[1].party[2].species, "NOCTOWL", "trainers: Falkner has Noctowl")
    T.eq(#f, vanillaFalkner, "trainers: no rematch rows added here")
    T.eq(trainers.CAL.trainers[3].name, "SMITH", "trainers: Trainer House Cal 3 -> Smith")
    local out = Runtime.call("trainer.party", function(_, _, pt) return pt end,
      "CAL", "CAL3", { {} })
    T.eq(out[1].statExp and out[1].statExp.hp, 0xFE01, "trainers: Smith's Raikou stat exp")
  end,
  crystal_legacy_encounters = function()
    T.eq(enc.grass.SPROUT_TOWER_2F.rates.MORN, 5, "encounters: rates stay raw bytes")
    T.eq(#enc.grass.SPROUT_TOWER_2F.slots.NITE, 7, "encounters: 7 night slots")
  end,
  legacy_hard_mode = function()
    local Mon = require("src.battle.gen2.Mon")
    local base = function() return 5000 end
    local ctxFor = function(level, exp)
      return { mon = { species = "CHIKORITA", level = level, experience = exp },
               battle = { data = data } }
    end
    T.eq(Runtime.call("exp.gain", base, ctxFor(10, 1000)), 0, "hard mode: no exp at cap 10")
    local growth = Mon.growthFor(data, p.CHIKORITA.growthRate)
    local at10 = Mon.experienceForLevel(growth, 10)
    local got = Runtime.call("exp.gain", base, ctxFor(9, at10 - 50))
    T.eq(got, 50, "hard mode: exp stops exactly at the cap")
    T.eq(type(data.screens and data.screens.Gen2PackMenu), "table", "hard mode: PACK wrapper registered")
    local candy = data.gen2ItemEffects and data.gen2ItemEffects.RARE_CANDY
    local r = candy and candy.use({ mon = { species = "CHIKORITA", level = 10 }, data = data })
    T.eq(r and r.used, false, "hard mode: Rare Candy refused at cap")
    -- Simulate a trainer battle: the PACK must refuse, then work again after.
    local refusedText, closed = nil, false
    local ui = { refuseMenu = function(_, text) refusedText = text end }
    Runtime.emit("battle.started", { kind = "trainer", battle = ui })
    local inst = data.screens.Gen2PackMenu.new(nil, { battle = true,
      onClose = function() closed = true end })
    inst:update(0)
    T.eq(closed, true, "hard mode: PACK closes in a trainer battle")
    T.eq(refusedText ~= nil, true, "hard mode: refusal message shown")
    Runtime.emit("battle.ended", { battle = ui, result = "win" })
    Runtime.emit("battle.started", { kind = "wild", battle = ui })
    local ok, wildInst = pcall(data.screens.Gen2PackMenu.new, nil, { battle = true })
    T.eq(ok and wildInst and wildInst.update ~= nil and closed, true,
      "hard mode: wild battles get the normal PACK")
  end,
  crystal_legacy_shops = function()
    T.eq(data.gen2Marts.lists ~= nil, true, "shops: mart table present")
  end,
}
for _, id in ipairs(ids) do
  if CHECKS[id] then CHECKS[id]() end
end

T.sdk.restoreRuntime()
Logger.warn, Logger.error = realWarn, realError
T.finish(label)
