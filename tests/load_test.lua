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

-- CL_FIXTURE=<dump> runs against real importer output (tests/real_data.lua);
-- otherwise the synthetic fixture built from the disassembly is used.
local real = os.getenv("CL_FIXTURE")
local data = real and dofile(repo .. "/tests/real_data.lua")(real)
  or dofile(repo .. "/tests/fixture_crystal.lua")

-- Find the vanilla scripts the checks drive BEFORE the mods change anything,
-- by structure rather than by key, so the same checks run on either fixture.
local function classIndex(name)
  local c = data.gen2Trainers.classes[name]
  return c and c.index
end
local battleKeys = {}   -- class -> { keys whose rows load its first team }
local martKeys = {}     -- vanilla mart id -> clerk script key
for key, rows in pairs(data.gen2Scripts) do
  if type(rows) == "table" and type(key) == "string" then
    for _, row in ipairs(rows) do
      if type(row) == "table" and row.op == "loadtrainer" and (row.member or (row.args and row.args[2])) == 1 then
        local cls = row.class or (row.args and row.args[1])
        battleKeys[cls] = battleKeys[cls] or {}
        table.insert(battleKeys[cls], key)
      end
    end
  end
end
for _, c in pairs(battleKeys) do table.sort(c) end
local function objectKey(mapId, sprite)
  for _, obj in ipairs((data.gen2Maps[mapId] or {}).objects or {}) do
    if obj.sprite == sprite and obj.scriptKey then return obj.scriptKey end
  end
end
for _, mapId in ipairs({ "CELADON_DEPT_STORE_3F", "CELADON_DEPT_STORE_5F" }) do
  for _, obj in ipairs((data.gen2Maps[mapId] or {}).objects or {}) do
    for _, row in ipairs(obj.scriptKey and data.gen2Scripts[obj.scriptKey] or {}) do
      if type(row) == "table" and row.op == "pokemart" then
        local a = row.args or {}
        martKeys[row.mart or ((a[2] or 0) + (a[3] or 0) * 256)] = obj.scriptKey
      end
    end
  end
end
local falknerKey = objectKey("VIOLET_GYM", "SPRITE_FALKNER")
local function firstBattleKey(name)
  local list = battleKeys[classIndex(name)]
  return list and list[1], list
end
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
    if loader.mods.crystal_legacy_rematches then
      T.eq(#f, vanillaFalkner + 1, "trainers+rematches: rematch appended after Legacy teams")
      T.eq(f[#f].party[1].level, 54, "trainers+rematches: appended team is the rematch")
    else
      T.eq(#f, vanillaFalkner, "trainers: no rematch rows added here")
    end
    T.eq(trainers.CAL.trainers[3].name, "SMITH", "trainers: Trainer House Cal 3 -> Smith")
    local out = Runtime.call("trainer.party", function(_, _, pt) return pt end,
      "CAL", "CAL3", { {} })
    T.eq(out[1].statExp and out[1].statExp.hp, 0xFE01, "trainers: Smith's Raikou stat exp")
  end,
  crystal_legacy_trainers_scaling = function()
    local Vm = require("src.script.gen2.Vm")
    local Events = require("src.world.gen2.Events")
    local Trainers = require("src.world.gen2.Trainers")
    local function fight(key, badges)
      local got
      local vm = Vm.new(data.gen2Scripts, data.gen2Text, Events.new(), {
        showText = function(_, onDone) if onDone then onDone() end end,
        readVar = function(id) return id == 7 and badges or 0 end,
        lookupTrainer = function(c, m) return Trainers.lookup(data.gen2Trainers, c, m) end,
        startBattle = function(trainer, _, done) got = trainer done("win") end,
      })
      vm:start(key)
      for _ = 1, 200 do if not vm:running() then break end vm:update() end
      return got
    end
    T.eq(fight(firstBattleKey("PRYCE"), 4).member, 1, "scaling: Pryce with 4 badges -> first team")
    T.eq(fight(firstBattleKey("PRYCE"), 5).id, "PRYCE_5BADGES", "scaling: 5 badges -> second team")
    T.eq(fight(firstBattleKey("PRYCE"), 6).roster[1].level >= 37, true, "scaling: 6 badges -> strongest")
    T.eq(fight(firstBattleKey("CHUCK"), 5).id, "CHUCK_5BADGES", "scaling: Chuck too")
    T.eq(fight(firstBattleKey("JASMINE"), 6).id, "JASMINE_6BADGES", "scaling: Jasmine too")
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
  crystal_legacy_rematches = function()
    -- Run the real gen1recomp Crystal script VM over the merged scripts.
    local Vm = require("src.script.gen2.Vm")
    local Events = require("src.world.gen2.Events")
    local Trainers = require("src.world.gen2.Trainers")
    local function talk(key, opts)
      local events = Events.new()
      for _, id in ipairs(opts.events or {}) do events:set(id, true) end
      local seen, battle = {}, nil
      local vm = Vm.new(data.gen2Scripts, data.gen2Text, events, {
        showText = function(body, onDone) seen[#seen + 1] = tostring(body) if onDone then onDone() end end,
        yesorno = function(onChoose) onChoose(opts.yes) end,
        readVar = function(id) return id == 7 and (opts.badges or 0) or 0 end,
        lookupTrainer = function(class, member)
          return Trainers.lookup(data.gen2Trainers, class, member)
        end,
        startBattle = function(trainer, _, done) battle = trainer done("win") end,
      })
      T.eq(vm:start(key), true, "rematches: " .. key .. " starts")
      for _ = 1, 600 do if not vm:running() then break end vm:update() end
      return table.concat(seen, " | "), battle
    end
    local E4, FALK = 68, 1213
    local text, b1 = talk(falknerKey, { events = {}, yes = true })
    T.eq(text:find("Congratulations", 1, true), nil, "rematches: before E4, no rematch offer")
    if real then T.eq(b1 and b1.member, 1, "rematches: before E4, the normal Falkner fight") end
    local text2, b2 = talk(falknerKey, { events = { E4, FALK }, yes = true })
    T.eq(text2:find("Congratulations", 1, true) ~= nil, true, "rematches: offers Falkner rematch")
    T.eq(b2 and b2.roster and b2.roster[1].level, 54, "rematches: level 54 rematch team")
    local text3, b3 = talk(falknerKey, { events = { E4, FALK }, yes = false })
    T.eq(b3, nil, "rematches: declining starts no battle")
    T.eq(#text3 > #"Congratulations", true, "rematches: declining falls back to vanilla dialogue")
    local willKey, willKeys = firstBattleKey("WILL")
    local w1, wb1 = talk(willKey, { badges = 8 })
    T.eq(wb1 and wb1.member, 1, "rematches: Will with 8 badges uses his first team")
    T.eq(w1:find("welcome back", 1, true), nil, "rematches: and his vanilla intro")
    local w2, wb2 = talk(willKey, { badges = 16 })
    T.eq(wb2 and wb2.roster and wb2.roster[1].level, 66, "rematches: 16 badges -> rematch team")
    T.eq(w2:find("welcome back", 1, true) ~= nil, true, "rematches: and rematch intro")
    for _, k in ipairs(willKeys) do
      local _, wb3 = talk(k, { badges = 16 })
      T.eq(wb3 and wb3.roster and wb3.roster[1].level, 66, "rematches: every Will battle list patched (" .. k .. ")")
    end
    local _, lb = talk(firstBattleKey("CHAMPION"), { badges = 16 })
    T.eq(lb and lb.id, "CHAMPION_REMATCH", "rematches: Lance rematch member id")
  end,
  crystal_legacy_story = function()
    -- Every key a story row or map event points at must exist afterwards.
    local missing = {}
    local function need(kind, key)
      if not key then return end
      -- The synthetic fixture has no vanilla scripts; there, check only the
      -- story's own keys (banks $80 up). Real data checks everything.
      if not real and not tostring(key):match("^8%x:") then return end
      local ok = (kind == "text" and data.gen2Text[key] ~= nil)
        or (kind == "movement" and data.gen2Scripts.movements and data.gen2Scripts.movements[key] ~= nil)
        or (kind == "script" and data.gen2Scripts[key] ~= nil)
      if not ok then missing[#missing + 1] = kind .. " " .. tostring(key) end
    end
    local storyMaps = { "TRAINER_HOUSE_B1F", "RADIO_TOWER_5F", "TEAM_ROCKET_BASE_B3F", "SILVER_CAVE_ROOM_3" }
    for _, id in ipairs(storyMaps) do
      local m = data.gen2Maps[id] or {}
      for _, o in ipairs(m.objects or {}) do
        need("script", o.scriptKey)
        if o.trainer then need("text", o.trainer.seenText) need("text", o.trainer.winText) end
      end
      for _, list in ipairs({ m.bgEvents or {}, m.coordEvents or {}, m.callbacks or {} }) do
        for _, e in ipairs(list) do need("script", e.scriptKey) end
      end
      for _, sc in pairs(m.sceneScripts or {}) do need("script", sc.scriptKey) end
    end
    for key, rows in pairs(data.gen2Scripts) do
      if type(key) == "string" and key:match("^8%x:") then
        for _, r in ipairs(rows) do
          need("script", r.script) need("text", r.text) need("text", r.winText)
          need("text", r.lossText) need("movement", r.movement)
        end
      end
    end
    for _, m in ipairs(missing) do print("missing: " .. m) end
    T.eq(#missing, 0, "story: every referenced script/text/movement exists")
    -- Legacy's new overworld sprites: registered, and their numbers named.
    for _, name in ipairs({ "SPRITE_ARCHER", "SPRITE_GIOVANNI", "SPRITE_MEWTWO", "SPRITE_MURKROW" }) do
      local rec = data.gen2Sprites and data.gen2Sprites[name]
      T.eq(rec ~= nil and type(rec.image) == "string", true, "story: sprite " .. name .. " registered")
    end
    local order = data.gen2Constants and data.gen2Constants.spriteOrder or {}
    T.eq(order[0x68], "SPRITE_GIOVANNI", "story: sprite $68 is Giovanni")
    T.eq(order[0xa3], "SPRITE_MEWTWO", "story: sprite $a3 is Mewtwo")
    if data.items.ITEM_93 then
      T.eq(data.items.ITEM_93.name, "OLD AMBER", "story: Old Amber on item slot $93")
    end
    if not real then return end
    local Vm = require("src.script.gen2.Vm")
    local Events = require("src.world.gen2.Events")
    local Trainers = require("src.world.gen2.Trainers")
    local function run(key, opts)
      local events = Events.new()
      for _, id in ipairs(opts.events or {}) do events:set(id, true) end
      local battle, seen = nil, {}
      local vm = Vm.new(data.gen2Scripts, data.gen2Text, events, {
        showText = function(b, onDone) seen[#seen + 1] = tostring(b) if onDone then onDone() end end,
        yesorno = function(f) f(true) end,
        readVar = function(id) return (opts.vars or {})[id] or 0 end,
        lookupTrainer = function(c, m) return Trainers.lookup(data.gen2Trainers, c, m) end,
        startBattle = function(t, w, done) battle = battle or (t or w) done("win") end,
        -- The real special handlers, so e.g. `special TrainerHouse` answers
        -- as it does in game (no Mystery Gift trainer -> FALSE).
        specialOrder = data.gen2Constants and data.gen2Constants.specialOrder,
        save = function() return {} end,
      })
      vm:start(key)
      for _ = 1, 2000 do if not vm:running() then break end vm:update() end
      return battle, table.concat(seen, " | ")
    end
    -- Smoke test: every entry point on every Story map runs in the VM without
    -- a Lua error (answers "yes" to questions, wins every battle).
    local entries = {}
    for id, m in pairs(data.gen2Maps) do
      local function add(k) if k and tostring(k):match("^%x%x:") and tonumber(k:sub(1, 2), 16) >= 0x80 then entries[#entries + 1] = k end end
      for _, o in ipairs(m.objects or {}) do add(o.scriptKey) end
      for _, e in ipairs(m.bgEvents or {}) do add(e.scriptKey) end
      for _, e in ipairs(m.coordEvents or {}) do add(e.scriptKey) end
      for _, sc in pairs(m.sceneScripts or {}) do add(sc.scriptKey) end
      for _, cb in ipairs(m.callbacks or {}) do add(cb.scriptKey) end
    end
    table.sort(entries)
    local crashed = {}
    for _, key in ipairs(entries) do
      local ok, err = pcall(run, key, { vars = {} })
      if not ok then crashed[#crashed + 1] = key .. ": " .. tostring(err) end
    end
    for i = 1, math.min(#crashed, 10) do print("crash: " .. crashed[i]) end
    T.eq(#entries > 300, true, "story: smoke test found the map entry points (" .. #entries .. ")")
    T.eq(#crashed, 0, "story: every map entry point runs without a Lua error")
    -- Move Reminder: talk to the second NPC in the Move Deleter's house with a
    -- level-20 Chikorita that has forgotten Razor Leaf, and learn it back.
    do
      local house = data.gen2Maps.MOVE_DELETERS_HOUSE
      local key = house and house.objects[2] and house.objects[2].scriptKey
      local stack, pressed = {}, {}
      local mon = { species = "CHIKORITA", level = 20,
        moves = { { id = "TACKLE" }, { id = "GROWL" } } }
      local learnedMove, listShown
      local game = { data = data,
        stack = { push = function(_, s) stack[#stack + 1] = s end,
                  pop = function() stack[#stack] = nil end },
        input = { wasPressed = function(_, b) return pressed[b] end },
        learnMoveOn = function(_, m, move, cb) learnedMove = move cb(true) end }
      package.loaded["src.ui.gen2.PartyMenu"] = { new = function(_, opts)
        return { update = function() opts.onChoose(nil, mon) end }
      end }
      loader.game = game  -- what mod.game resolves to (Loader:_game)
      local seen = {}
      local vm = Vm.new(data.gen2Scripts, data.gen2Text, Events.new(), {
        showText = function(b, onDone) seen[#seen + 1] = tostring(b) if onDone then onDone() end end,
        yesorno = function(f) f(true) end,
        commands = data.commands,
      })
      vm:start(key)
      for _ = 1, 500 do
        local top = stack[#stack]
        if top then
          if top.moves and not listShown then listShown = top.moves end
          pressed = { a = top.moves ~= nil }
          top:update(0)
        elseif vm:running() then vm:update() else break end
      end
      local all = table.concat(seen, " | ")
      local expected
      for _, row in ipairs(data.pokemon.CHIKORITA.levelMoves or {}) do
        if row.level <= 20 and row.move ~= "TACKLE" and row.move ~= "GROWL" then
          expected = row.move break
        end
      end
      T.eq(all:find("MOVE REMINDER", 1, true) ~= nil, true, "story: Move Reminder greets")
      T.eq(listShown and listShown[1], expected, "story: list starts with the first forgotten move")
      local hasKnown = false
      for _, m in ipairs(listShown or {}) do if m == "TACKLE" then hasKnown = true end end
      T.eq(hasKnown, false, "story: known moves are not offered")
      T.eq(learnedMove, expected, "story: the chosen move is learned")
      T.eq(all:find("Come back anytime", 1, true) ~= nil, true, "story: and says goodbye")
      package.loaded["src.ui.gen2.PartyMenu"] = nil
      loader.game = nil
    end
    local th = data.gen2Maps.TRAINER_HOUSE_B1F
    local thKey = th.coordEvents and th.coordEvents[1] and th.coordEvents[1].scriptKey
    local mon = run(thKey, { vars = { [11] = 1 } })
    T.eq(mon and mon.name, "SMITH", "story: Monday's Trainer House opponent is Smith")
    local tue = run(thKey, { vars = { [11] = 2 } })
    T.eq(tue and tue.name, "CRAIG", "story: Tuesday is Craig")
    local wed = run(thKey, { vars = { [11] = 3 } })
    T.eq(wed and wed.className, "PKMN TRAINER", "story: Wednesday is Weebra's class")
    local function scriptLoading(classId)
      for key, rows in pairs(data.gen2Scripts) do
        if type(key) == "string" and key:match("^8%x:") then
          for _, r in ipairs(rows) do
            if r.op == "loadtrainer" and r.class == classId then return key end
          end
        end
      end
    end
    local archer = data.gen2Trainers.classes.ROCKET_LEADER
    T.eq(archer and archer.index, 69, "story: Archer's class registered")
    local b = run(scriptLoading(69), {})
    T.eq(b and b.name, "ARCHER", "story: Radio Tower / Rocket Base battle is Archer")
    T.eq(type(archer.pic) == "string" and archer.pic:find("archer.png", 1, true) ~= nil, true,
      "story: Archer has his Legacy art")
    local red = data.gen2Trainers.classes.RED
    T.eq(red and #red.trainers >= 2, true, "story: Red has a rematch team")
  end,
  crystal_legacy_shops = function()
    T.eq(data.gen2Marts.lists ~= nil, true, "shops: mart table present")
    local Vm = require("src.script.gen2.Vm")
    local Events = require("src.world.gen2.Events")
    local function shop(key, badges)
      local opened
      local vm = Vm.new(data.gen2Scripts, data.gen2Text, Events.new(), {
        showText = function(_, onDone) if onDone then onDone() end end,
        readVar = function(id) return id == 7 and badges or 0 end,
        openMart = function(_, martId, done) opened = martId done() end,
      })
      vm:start(key)
      for _ = 1, 200 do if not vm:running() then break end vm:update() end
      return opened
    end
    T.eq(shop(martKeys[27], 8), 27, "shops: 5F clerk 1 vanilla stock before 16 badges")
    T.eq(shop(martKeys[27], 16), 1001, "shops: 5F clerk 1 upgraded at 16 badges")
    T.eq(shop(martKeys[28], 16), 1002, "shops: 5F clerk 2 upgraded at 16 badges")
    T.eq(shop(martKeys[25], 16), 1000, "shops: 3F clerk upgraded at 16 badges")
    local fs = data.gen2Maps.GOLDENROD_FLOWER_SHOP.objects
    local clerk = fs[#fs]
    T.eq(clerk.sprite, "SPRITE_CLERK", "shops: flower shop clerk added")
    T.eq(clerk.x == 5 and clerk.y == 3, true, "shops: at Legacy's position")
    T.eq(shop(clerk.scriptKey, 3), 1003, "shops: berry clerk basic stock")
    T.eq(shop(clerk.scriptKey, 7), 1004, "shops: berry clerk full stock at 7 badges")
    -- The wrapped mart screen serves the custom list and charges the real save.
    local save = { player = { money = 50000 }, inventory = {} }
    local game = { data = data, save = save }
    local menu = data.screens.Gen2MartMenu.new(game, { martId = 1001, save = save,
      items = data.items })
    T.eq(menu.entries and menu.entries[1] and menu.entries[1].id, "TM_MUD_SLAP",
      "shops: upgraded 5F list served")
    menu.qtyItem, menu.qty = menu.entries[1], 1
    menu:completePurchase(1000)
    T.eq(save.player.money, 49000, "shops: purchase charged to the live save")
  end,
}
for _, id in ipairs(ids) do
  if CHECKS[id] then CHECKS[id]() end
end
if loader.mods.crystal_legacy_trainers then CHECKS.crystal_legacy_trainers_scaling() end

T.sdk.restoreRuntime()
Logger.warn, Logger.error = realWarn, realError
T.finish(label)
