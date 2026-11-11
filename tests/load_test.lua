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
-- Menu Icons: a stand-in for one icon a player copied in (placeholder bytes,
-- never decoded -- the checks only follow which path the hook hands back).
files["mods/crystal_legacy_icons/icons/chikorita.png"] = "stand-in"
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

-- The handshake a running game sends once its data is merged; the engine
-- ports in Pokémon / Story Changes finish their work on it.
Runtime.emit("game.ready", { game = { data = data } })

-- Spot checks per mod, against values read straight from Crystal Legacy's
-- source. Each runs only when its mod is in this load.
local p, enc = data.pokemon, data.gen2Encounters
local trainers = data.gen2Trainers.classes
local CHECKS = {
  crystal_legacy_pokedex = function()
    local ex = loader.exports.crystal_legacy_pokedex
    local function glyphs(str)
      local n = 0
      for i = 1, #str do
        local b = str:byte(i)
        if b < 0x80 or b >= 0xC0 then n = n + 1 end
      end
      return n
    end
    local function join(lines)
      local t = {}
      for _, l in ipairs(lines or {}) do t[#t + 1] = type(l) == "table" and l[3] or l end
      return table.concat(t, " | ")
    end
    local pages = {}
    for _, page in ipairs(ex.pages) do pages[page.title] = page end
    -- Stats, from the live data.
    local stats = join(ex.statsLines(data, "CHIKORITA"))
    T.eq(stats:find("HP   " .. data.pokemon.CHIKORITA.baseStats.hp, 1, true) ~= nil, true,
      "pokedex: base HP from the live data")
    T.eq(stats:find("TOTAL", 1, true) ~= nil, true, "pokedex: stat total")
    -- Moves.
    local level = join(pages["LEVEL-UP MOVES"].list(data, "CHIKORITA"))
    local first = data.pokemon.CHIKORITA.levelMoves[1]
    T.eq(level:find("LV" .. first.level, 1, true) ~= nil and level:find(data.moves[first.move].name, 1, true) ~= nil,
      true, "pokedex: level-up moves with levels")
    T.eq(#pages["TM/HM MOVES"].list(data, "CHIKORITA") >= 1, true, "pokedex: TM/HM page lists moves")
    -- Evolution: the whole family, with methods.
    local eevee = join(pages.EVOLUTION.list(data, "UMBREON"))
    T.eq(eevee:find("EEVEE", 1, true) ~= nil and eevee:find("VAPOREON", 1, true) ~= nil, true,
      "pokedex: evolution shows the family from any member")
    T.eq(eevee:find("NIGHT", 1, true) ~= nil, true, "pokedex: happiness by time of day")
    T.eq(join(pages.EVOLUTION.list(data, "TYROGUE")):find("ATK HIGHER", 1, true) ~= nil, true,
      "pokedex: Tyrogue's stat check in words")
    T.eq(join(pages.EVOLUTION.list(data, "UNOWN")):find("DOES NOT EVOLVE", 1, true) ~= nil, true,
      "pokedex: single-stage Pokemon say so")
    -- Area: every way a species is found, from the live encounter tables.
    if data.gen2Encounters and data.gen2Encounters.fishGroups then
      local area = function(sp) return join(pages.AREA.list(data, sp)) end
      T.eq(area("MAGIKARP"):find(" OLD ", 1, true) ~= nil, true, "pokedex: area lists Old Rod fishing")
      T.eq(area("HOOTHOOT"):find("TREE", 1, true) ~= nil, true, "pokedex: area lists Headbutt trees")
      T.eq(area("PIDGEY"):find("%", 1, true) ~= nil, true, "pokedex: area shows encounter odds")
      T.eq(area("MEW"):find("NOT FOUND IN", 1, true) ~= nil, true, "pokedex: no wild spot says so")
    end
    -- Every page, every species: fits the box and uses only Crystal's font.
    local tooWide, badChar = {}, {}
    for species in pairs(data.pokemon) do
      for _, page in ipairs(ex.pages) do
        local lines = page.stats and page.stats(data, species) or page.list(data, species) or {}
        for _, l in ipairs(lines) do
          local x, text = 1, l
          if type(l) == "table" then x, text = l[1], l[3] end
          if glyphs(text) + x > 19 then tooWide[#tooWide + 1] = species .. ": " .. text end
          if text:find("[<>=+#]") then badChar[#badChar + 1] = species .. ": " .. text end
        end
      end
    end
    for i = 1, math.min(5, #tooWide) do print("too wide: " .. tooWide[i]) end
    T.eq(#tooWide, 0, "pokedex: every line of every page fits the box")
    T.eq(#badChar, 0, "pokedex: no characters Crystal's font lacks")
    -- SELECT opens the pages; left/right switch; down scrolls; B goes back.
    local PokedexMenu = require("src.ui.gen2.PokedexMenu")
    local pressed
    local fake = { view = "entry", page = 1,
      current = function() return { species = "CHIKORITA" } end,
      game = { data = data, input = { wasPressed = function(_, b) return b == pressed end } } }
    pressed = "select" PokedexMenu.update(fake)
    T.eq(fake.view, "legacy", "pokedex: SELECT opens the Legacy pages")
    pressed = "right" PokedexMenu.update(fake)
    T.eq(fake.legacyPage, 2, "pokedex: right moves to the next page")
    local tmFake = fake
    pressed = "right" PokedexMenu.update(tmFake) -- TM/HM: long enough to scroll
    pressed = "down" PokedexMenu.update(tmFake)
    T.eq((tmFake.legacyScroll or 0) <= math.max(0, #pages["TM/HM MOVES"].list(data, "CHIKORITA") - 12), true,
      "pokedex: scrolling stays inside the list")
    pressed = "left" PokedexMenu.update(fake)
    T.eq(fake.legacyPage, 2, "pokedex: left goes back a page")
    pressed = "b" PokedexMenu.update(fake)
    T.eq(fake.view, "entry", "pokedex: B goes back to the entry")
    -- START on an entry flips the picture to shiny colours and back; the
    -- picture asks Palettes.monColors, which then answers with the shiny pair.
    local Palettes = require("src.world.gen2.Palettes")
    local pal = { pokemon = { CHIKORITA = { normal = { { 1, 1, 1 }, { 2, 2, 2 } },
      shiny = { { 9, 9, 9 }, { 8, 8, 8 } } } } }
    local function picColour()
      local got
      local inner = Palettes.monColors
      Palettes.monColors = function(...) got = inner(...) return got end
      pcall(PokedexMenu.drawPic, { palettes = pal, game = fake.game, picFor = function() end },
        { species = "CHIKORITA", seen = true }, 1, 1, true)
      Palettes.monColors = inner
      return got and got[2][1]
    end
    T.eq(picColour(), 1, "pokedex: normal colours to start")
    pressed = "start" PokedexMenu.update(fake)
    T.eq(ex.shinyView(), true, "pokedex: START shows shiny colours")
    T.eq(picColour(), 9, "pokedex: the picture asks for the shiny pair")
    T.eq(Palettes.monColors(pal, "CHIKORITA")[2][1], 1, "pokedex: other screens keep normal colours")
    pressed = "start" PokedexMenu.update(fake)
    T.eq(ex.shinyView(), false, "pokedex: START again goes back")
    -- Pokédex colour: Legacy's nine, from pokecrystal's predef.pal.
    for _, name in ipairs({ "RED", "BLUE", "PURPLE", "BROWN", "GREEN", "PINK", "YELLOW", "CYAN", "GRAY" }) do
      local c = ex.dexPalette(name)
      T.eq(c ~= nil and #c == 4 and #c[1] == 3, true, "pokedex: colour " .. name)
    end
    T.eq(ex.dexPalette("BLUE")[2][3], math.floor(27 * 255 / 31 + 0.5), "pokedex: BLUE from predef.pal")
  end,
  crystal_legacy_icons = function()
    -- Data only: the mod ships Legacy's species -> icon file / palette map.
    local Assets = require("src.render.Assets")
    local function icon(species, mon)
      local ctx = { species = species, mon = mon or { species = species } }
      local path = Runtime.call("pokemon.icon", function(p) return p end, "vanilla.png", ctx)
      return path, ctx.trueColor
    end
    local path, trueColor = icon("CHIKORITA")
    T.eq(path, "legacy-icons/CHIKORITA.png", "icons: a copied-in icon is used")
    T.eq(trueColor, true, "icons: and drawn in its own colours")
    T.eq(Assets.isComposed(path), true, "icons: coloured on demand from the player's file")
    T.eq((icon("CHIKORITA", { species = "CHIKORITA", shiny = true })),
      "legacy-icons/CHIKORITA-shiny.png", "icons: shiny Pokemon get Legacy's shiny palette")
    T.eq((icon("CYNDAQUIL")), "vanilla.png", "icons: no file -> gen1recomp's normal icon")
    T.eq((icon("CHIKORITA", { species = "CHIKORITA", isEgg = true })), "vanilla.png",
      "icons: eggs keep the egg icon")
    -- Palette slots for Legacy's (already coloured) icon files, by colour value.
    local slot = loader.exports.crystal_legacy_icons.slotOf
    local function c(r, g, b) return slot(r / 255, g / 255, b / 255) end
    T.eq(c(255, 255, 255), 1, "icons: white is the transparent slot")
    T.eq(c(255, 156, 82), 2, "icons: the shared peach stays peach")
    T.eq(c(0, 0, 0), 4, "icons: black stays black")
    T.eq(c(82, 74, 255), 3, "icons: Wooper's blue is the species colour")
    T.eq(c(57, 189, 24), 3, "icons: Chikorita's green is the species colour")
    T.eq(c(255, 57, 8), 3, "icons: red is the species colour")
    T.eq(c(247, 82, 90), 3, "icons: pink is not mistaken for the peach")
    T.eq(c(107, 107, 107), 3, "icons: gray is the species colour")
    T.eq(c(170, 170, 170), 2, "icons: a grey file's light grey is the light slot (Ho-Oh)")
    T.eq(c(85, 85, 85), 3, "icons: a grey file's dark grey is the species colour")
    -- Wilds of Kanto fallback, with a stand-in resolver (no image is decoded).
    local ex = loader.exports.crystal_legacy_icons
    ex.setWildsResolver(function(opts)
      if opts.species == "CYNDAQUIL" then
        return { image = "wilds/155-" .. (opts.shiny and "shiny" or "normal") .. ".png",
                 frames = 6, frameWidth = 16, frameHeight = 16 }
      elseif opts.species == "TOTODILE" then
        return { image = "wilds/158-hgss.png", frames = 6, frameWidth = 32, frameHeight = 32 }
      end
      return { image = "wilds/missing.png", fallback = true }
    end)
    local wp = icon("CYNDAQUIL")
    T.eq(wp, "wilds-icons/wilds/155-normal.png", "icons: Wilds' follower sprite fills in")
    T.eq(Assets.isComposed(wp), true, "icons: cut into an icon on demand")
    T.eq((icon("CYNDAQUIL", { species = "CYNDAQUIL", shiny = true })),
      "wilds-icons/wilds/155-shiny.png", "icons: Wilds' shiny sheet for shiny Pokemon")
    T.eq((icon("CHIKORITA")), "legacy-icons/CHIKORITA.png", "icons: a copied-in Legacy icon still wins")
    T.eq((icon("TOTODILE")), "vanilla.png", "icons: non-16x16 Wilds styles keep the normal icon")
    T.eq((icon("PIDGEY")), "vanilla.png", "icons: Wilds' missing-sprite fallback is not used")
    ex.setWildsResolver(nil)
  end,
  crystal_legacy_fixes = function()
    local Catching = require("src.battle.gen2.Catching")
    T.eq(Catching.statusBonus("burn", {}), 5, "fixes: burn gives a catch bonus")
    T.eq(Catching.statusBonus("sleep", {}), 10, "fixes: sleep bonus unchanged")
    local love = { catchRate = 45, maxHp = 30, hp = 30, ball = "LOVE_BALL",
      species = "PIDGEY", playerSpecies = "PIDGEY", gender = "female", playerGender = "male" }
    local plain = { catchRate = 45, maxHp = 30, hp = 30, ball = "POKE_BALL" }
    T.eq(Catching.rate(love) > Catching.rate(plain), true, "fixes: Love Ball boosts opposite genders")
    love.gender = "male"
    T.eq(Catching.rate(love), Catching.rate(plain), "fixes: Love Ball ignores same gender")
    -- Legacy keeps the high-HP rounding quirk: fixBugs must not reach it.
    local big = { catchRate = 45, maxHp = 400, hp = 400, ball = "POKE_BALL" }
    local fixedBig = { catchRate = 45, maxHp = 400, hp = 400, ball = "POKE_BALL", fixBugs = true }
    T.eq(Catching.rate(big) ~= Catching.rate(fixedBig), true, "fixes: HP rounding quirk kept")
    local Ai = require("src.battle.gen2.Ai")
    local never = { random = function() return 99 end }
    local base = { enemyHp = 100, enemyMaxHp = 100 }
    T.eq(Ai.SMART.EFFECT_MEAN_LOOK(never, setmetatable({ enemyToxic = true }, { __index = base })), 1,
      "fixes: AI ignores its own poison for Mean Look")
    T.eq(Ai.SMART.EFFECT_MEAN_LOOK(never, setmetatable({ playerToxic = true }, { __index = base })), -3,
      "fixes: AI favours Mean Look on a badly poisoned player")
    local Battle = require("src.battle.gen2.Battle")
    local vol = { nightmare = true, confuseCount = 2 }
    local fake = { enemy = { status = "sleep" }, trainer = { items = { "FULL_HEAL" } },
      volatile = function() return vol end, itemDef = function() return nil end, emit = function() end }
    Battle.enemyUseItem(fake, "FULL_HEAL")
    T.eq(vol.nightmare, nil, "fixes: AI Full Heal ends Nightmare")
    T.eq(Battle.glacierBoostsSpDef(300), true, "fixes: Glacier Badge always boosts Sp. Def")
    -- OT ID 600, DVs 0 -> bc = $012c (300): the full compare stops at the 310
    -- row (551 mm); vanilla's high-byte compare skips to the 710 row (553 mm).
    local Specials = require("src.script.gen2.Specials")
    local _, _, mm = Specials.magikarpLength(600, 0)
    T.eq(mm, 551, "fixes: Magikarp length compares the full value")
    _, _, mm = Specials.magikarpLength(0, 0)
    T.eq(mm, 190, "fixes: tiny Magikarp special case unchanged")
    -- Wild Magikarp sizes: find DVs for a big, a small and a mid-sized fish
    -- (OT ID 600), then drive Legacy's filter with fixed dice.
    local filter = loader.exports.crystal_legacy_fixes and loader.exports.crystal_legacy_fixes.magikarpFilter
    T.eq(type(filter), "function", "fixes: Magikarp size filter exported")
    if filter then
      local function dvsOf(w)
        return { attack = math.floor(w / 4096) % 16, defense = math.floor(w / 256) % 16,
                 speed = math.floor(w / 16) % 16, special = w % 16 }
      end
      local big, small, mid
      for w = 0, 65535 do
        local ft, inch = Specials.magikarpLength(600, w)
        if not big and ft == 5 and inch >= 4 then big = dvsOf(w) end
        if not small and ft < 3 then small = dvsOf(w) end
        if not mid and ft == 4 then mid = dvsOf(w) end
        if big and small and mid then break end
      end
      local function seq(list)
        local i = 0
        return function() i = i + 1 return list[math.min(i, #list)] end
      end
      local high, low = function() return 255 end, function() return 0 end
      T.eq(filter(600, false, seq({ big, mid }), high), mid, "fixes: a 5'4\" Magikarp is re-rolled")
      T.eq(filter(600, false, seq({ big, mid }), low), big, "fixes: ...except on the 5% skip")
      T.eq(filter(600, true, seq({ small, mid }), high), mid, "fixes: Lake of Rage re-rolls one under 3'")
      T.eq(filter(600, false, seq({ small, mid }), high), small, "fixes: small ones are fine elsewhere")
      T.eq(filter(600, true, seq({ small, mid }), low), small, "fixes: Lake of Rage's 39% pass")
      -- And wild Magikarp really go through it.
      local Mon = require("src.battle.gen2.Mon")
      loader.game = { save = { player = { id = 600 } }, world = { map = { id = "LAKE_OF_RAGE" } } }
      local short = 0
      for _ = 1, 200 do
        local fish = Mon.new(data, "MAGIKARP", 10, { wild = true })
        if fish and Specials.magikarpLength(600, Specials.dvWord(fish.dvs)) < 3 then short = short + 1 end
      end
      loader.game = nil
      -- Unfiltered, about 35% of Magikarp are under 3' (~70 of 200); the
      -- filter lets ~39% of those through (~28 of 200).
      T.eq(short < 50, true, "fixes: wild Lake of Rage Magikarp are mostly 3' or longer (" .. short .. "/200 short)")
    end
    -- Light Ball: 600 doubled is capped to 999, so it hits like a plain 999.
    local Damage = require("src.battle.gen2.Damage")
    local function hit(attack, doubled)
      return Damage.calc({ level = 50, power = 80, moveType = "NORMAL",
        types = data.type_chart.types, matchups = data.type_chart.matchups,
        attacker = { attack = attack, types = { "ELECTRIC" } },
        defender = { defense = 100, types = { "NORMAL" } },
        attackDoubled = doubled, random = function() return 0 end })
    end
    T.eq(hit(600, true), hit(999, false), "fixes: Light Ball doubling capped at 999")
    T.eq(hit(400, true), hit(800, false), "fixes: doubling below the cap unchanged")
    -- Confusion self-hit: a held type booster matching the chosen move no
    -- longer adds to it.
    local function selfHit(item)
      local mon = { level = 50, hp = 500, item = item,
        stats = { attack = 150, defense = 100 } }
      local fake = setmetatable({
        data = data, stages = { player = {} }, screens = { player = {} },
        sideOf = function() return "player" end,
        battleBadgeBoosts = function() return {} end,
        reflectOverflowFixed = function() return nil end,
        moveDef = function() return { type = "FIRE", effect = "EFFECT_NORMAL_HIT" } end,
        heldEffect = function(_, m, kind)
          if m.item == "CHARCOAL" and kind == "damage" then return "HELD_FIRE_BOOST", 10 end
        end,
        emit = function() end,
      }, { __index = Battle })
      return Battle.confusionSelfHit(fake, mon, "EMBER")
    end
    local okText, boosted = pcall(selfHit, "CHARCOAL")
    if okText then  -- needs the ROM's HurtItselfText (absent from the synthetic fixture)
      T.eq(boosted, selfHit(nil), "fixes: confusion self-hit ignores Charcoal")
    end
  end,
  crystal_legacy_qol = function()
    -- Running: B halves the step on foot and on water, never on the bike.
    local holdB = { isDown = function(_, b) return b == "b" end }
    local speed = function(ctx) return Runtime.call("movement.speed", function(f) return f end, 16, ctx) end
    T.eq(speed({ input = holdB }), 8, "qol: B runs at bike speed")
    T.eq(speed({ input = holdB, surfing = true }), 8, "qol: B surfs faster")
    T.eq(speed({ input = holdB, onBike = true }), 16, "qol: bike untouched")
    T.eq(speed({ input = { isDown = function() return false end } }), 16, "qol: walking without B")
    -- The running sheet: registered, worn while B is held mid-step on foot,
    -- and handed back to the state's own sprite afterwards.
    T.eq(type(data.gen2Sprites.SPRITE_CHRIS_RUN), "table", "qol: Chris's running sprite registered")
    T.eq(type(data.gen2Sprites.SPRITE_KRIS_RUN), "table", "qol: Kris's running sprite registered")
    local tick = loader.exports.crystal_legacy_qol and loader.exports.crystal_legacy_qol.runSpriteTick
    T.eq(type(tick), "function", "qol: running sprite tick exported")
    if tick then
      local worn, held = nil, true
      local player = { moving = true, setSprite = function(_, def) worn = def end }
      local world = { player = player, playerState = "normal", sprites = data.gen2Sprites,
        playerGender = function() return "female" end,
        game = { input = { isDown = function(_, b) return b == "b" and held end } },
        applyPlayerState = function(self, st) worn = { id = "STATE:" .. st } end }
      tick(world)
      T.eq(worn and worn.id, "SPRITE_KRIS_RUN", "qol: Kris wears the running sheet with B held")
      held = false
      tick(world)
      T.eq(worn and worn.id, "STATE:normal", "qol: back to walking when B is let go")
      held = true; world.playerState = "bike"; worn = nil
      tick(world)
      T.eq(worn, nil, "qol: no running sheet on the bike")
    end
    -- START in the PACK sorts the one bag list into ItemNameOrder.
    local PackMenu = require("src.ui.gen2.PackMenu")
    local save = { inventory = { POTION = 2, POKE_BALL = 3, REPEL = 1 },
      bagOrder = { "REPEL", "POTION", "POKE_BALL" } }
    local rebuilt = false
    PackMenu.update({ game = { input = { wasPressed = function(_, b) return b == "start" end } },
      save = save, bagData = data, rebuild = function() rebuilt = true end })
    T.eq(save.bagOrder[1], "POKE_BALL", "qol: START sorts the PACK (balls first)")
    T.eq(save.bagOrder[2], "POTION", "qol: then potions")
    T.eq(rebuilt, true, "qol: list redrawn after sorting")
    -- Day-Care: the exp past the new level's threshold survives the withdraw.
    local Mon = require("src.battle.gen2.Mon")
    local Breeding = require("src.core.gen2.Breeding")
    local mon = Mon.new(data, "CHIKORITA", 10, {})
    if mon then
      local growth = Mon.growthFor(data, data.pokemon.CHIKORITA.growthRate)
      mon.experience = Mon.experienceForLevel(growth, 11) + 50
      local dsave = { player = { money = 10000 }, party = {} }
      Breeding.dayCare(dsave).man.mon = mon
      local ok, back = Breeding.withdraw(data, dsave, "man")
      T.eq(ok and back.level, 11, "qol: Day-Care levels the mon up")
      T.eq(ok and back.experience, Mon.experienceForLevel(growth, 11) + 50,
        "qol: Day-Care keeps the extra exp")
    end
    -- Nurse: the full welcome the first time, the short version after.
    if data.gen2Scripts["2f:409c"] then
      local Vm = require("src.script.gen2.Vm")
      local Events = require("src.world.gen2.Events")
      local function visit()
        local seen = {}
        local vm = Vm.new(data.gen2Scripts, data.gen2Text, Events.new(), {
          showText = function(b, onDone) seen[#seen + 1] = tostring(b) if onDone then onDone() end end,
          yesorno = function(f) f(false) end,
          commands = data.commands,
        })
        vm:start("2f:409c")
        for _ = 1, 300 do if vm:running() then vm:update() else break end end
        return table.concat(seen, " | ")
      end
      local first, second = visit(), visit()
      T.eq(first:find("may I see", 1, true), nil, "qol: first visit is vanilla's welcome")
      T.eq(second:find("may I see", 1, true) ~= nil, true, "qol: later visits are quick")
      T.eq(second:find("fully healed", 1, true) ~= nil, true, "qol: quick visit returns the party")
    end
  end,
  crystal_legacy_pokemon = function()
    if not loader.mods.fast_eggs then
      T.eq(p.CHIKORITA.eggSteps, 20, "pokemon: leaves egg steps to Fast Eggs")
    end
    T.eq(data.moves.SHADOW_BALL ~= nil, true, "pokemon: moves present")
    -- engine ports
    T.eq(data.items.KINGS_ROCK.fieldMenu, "ITEMMENU_PARTY", "pokemon: King's Rock used on a party mon")
    local effects = loader.content and loader.content.item_effects
    if effects and effects:get("MOON_STONE") then
      T.eq(effects:get("KINGS_ROCK") ~= nil, true, "pokemon: King's Rock has the stone effect")
      T.eq(effects:get("UP_GRADE") ~= nil, true, "pokemon: Up-Grade has the stone effect")
      local ItemEffects = require("src.core.gen2.ItemEffects")
      T.eq(ItemEffects.partyAction("KINGS_ROCK", data), "stone", "pokemon: Pack runs King's Rock as a stone")
      local entry = require("src.core.gen2.Evolution").checkMon(data,
        { species = "SLOWPOKE", level = 20 }, { force = true, item = "KINGS_ROCK" })
      T.eq(entry and entry.into, "SLOWKING", "pokemon: King's Rock evolves Slowpoke into Slowking")
    end
    local Happiness = require("src.core.gen2.Happiness")
    T.eq(Happiness.CHANGES[1][1], 10, "pokemon: levelling happiness doubled")
    T.eq(Happiness.CHANGES[4][1], 9, "pokemon: gym leader happiness +9")
    local Effects = require("src.battle.gen2.Effects")
    T.eq(Effects.METRONOME_EXCEPTIONS.EXPLOSION, true, "pokemon: Metronome skips Explosion")
    T.eq(Effects.METRONOME_EXCEPTIONS.SELFDESTRUCT, true, "pokemon: Metronome skips Selfdestruct")
    local Battle = require("src.battle.gen2.Battle")
    local function obey(badges)
      local fake = { hasBadge = function(_, _, b) return badges[b] == true end }
      return Battle.obedienceLevel(fake)
    end
    T.eq(obey({}), 10, "pokemon: no badges -> obedience 10")
    T.eq(obey({ ZEPHYR = true }), 16, "pokemon: Zephyr Badge -> obedience 16")
    T.eq(obey({ ZEPHYR = true, HIVE = true }), 30, "pokemon: Hive Badge still 30")
    local rules = data.type_chart.battleRules
    if rules and rules.highCriticalMoves then
      T.eq(rules.highCriticalMoves.CUT, true, "pokemon: Cut has high crit ratio")
      T.eq(rules.highCriticalMoves.SLASH, true, "pokemon: Slash still high crit")
    end
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
    T.eq(trainers.PRYCE.items == nil or #trainers.PRYCE.items == 0, true,
      "trainers: Pryce carries no healing items")
    T.eq(trainers.BLAINE.items == nil or #trainers.BLAINE.items == 0, true,
      "trainers: Blaine carries no healing items")
    local function vanillaDvs() return { attack = 9, defense = 8, speed = 8, special = 8 } end
    local brock = Runtime.call("trainer.party", function(_, _, pt) return pt end,
      "BROCK", 1, { { dvs = vanillaDvs() } })
    T.eq(brock[1].dvs.defense, 14, "trainers: Brock's class DVs (defense 14)")
    local custom = Runtime.call("trainer.party", function(_, _, pt) return pt end,
      "BROCK", 1, { { dvs = { attack = 1, defense = 2, speed = 3, special = 4 } } })
    T.eq(custom[1].dvs.defense, 2, "trainers: a team's own DVs beat class DVs")
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
    local Roamers = require("src.core.gen2.Roamers")
    T.eq(Roamers.SOMETIMES_FLEE.EEVEE, nil, "encounters: Eevee no longer flees")
    T.eq(Roamers.SOMETIMES_FLEE.UMBREON, true, "encounters: Umbreon still flees")
    T.eq(Roamers.OFTEN_FLEE.ARTICUNO, nil, "encounters: Articuno no longer flees")
    T.eq(Roamers.OFTEN_FLEE.TOGETIC, true, "encounters: Togetic flees often")
  end,
  legacy_hard_mode = function()
    local Mon = require("src.battle.gen2.Mon")
    local base = function() return 5000 end
    local ctxFor = function(level, exp)
      return { mon = { species = "CHIKORITA", level = level, experience = exp },
               battle = { data = data } }
    end
    T.eq(Runtime.call("exp.gain", base, ctxFor(10, 1000)), 0, "hard mode: no exp at cap 10")
    loader.modOptions.legacy_hard_mode = { hardMode = false }
    T.eq(Runtime.call("exp.gain", base, ctxFor(10, 1000)), 5000, "hard mode: HARD MODE off lifts the cap")
    loader.modOptions.legacy_hard_mode = nil
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
    Runtime.emit("battle.ended", { battle = ui, result = "win" })

    -- Day-Care: growth stops at the cap (10 with no badges), and a Pokemon
    -- deposited at the cap gains nothing.
    local Breeding = require("src.core.gen2.Breeding")
    local function dayCare(level, exp)
      local dsave = { player = {} }
      Breeding.dayCare(dsave).man.mon = { species = "CHIKORITA", level = level, experience = exp }
      for _ = 1, 200 do Breeding.dayCareStep(data, dsave, function() return 0 end) end
      return Breeding.side(dsave, "man").mon.experience
    end
    local cap10 = Mon.experienceForLevel(growth, 10)
    T.eq(dayCare(9, cap10 - 50), cap10, "hard mode: Day-Care exp stops at the cap")
    T.eq(dayCare(10, cap10 + 5), cap10 + 5, "hard mode: no Day-Care exp at the cap")
    T.eq(dayCare(5, 200), 400, "hard mode: Day-Care growth below the cap unchanged")

    -- Hardcore: off by default, then every rule with it on.
    local World = require("src.world.gen2.World")
    local function party()
      return { { species = "CHIKORITA", level = 5, hp = 0, maxHp = 20, moves = {} },
               { species = "PIDGEY", level = 5, hp = 3, maxHp = 18, moves = {} } }
    end
    local hsave = { party = party() }
    World.healParty({ game = { save = hsave, data = data } })
    T.eq(hsave.party[1].hp, 20, "hardcore: off by default (Center revives)")
    local function rivalType(class)
      local opts = { trainer = { classId = class }, battleType = 1 }
      World.startBattle({ game = {} }, opts, function() end)
      return opts.battleType
    end
    T.eq(rivalType("RIVAL1"), 1, "hardcore off: Cherrygrove rival stays a can-lose battle")
    loader.modOptions.legacy_hard_mode = { hardcore = true }
    T.eq(rivalType("RIVAL1"), 0, "hardcore: Cherrygrove rival is a real battle")
    T.eq(rivalType("YOUNGSTER"), 1, "hardcore: other can-lose battles untouched")
    -- The rival still gloats: LostBattle runs as CANLOSE (printing his
    -- winning line), then the battle turns normal so the whiteout fade plays.
    local Battle = require("src.battle.gen2.Battle")
    local printed
    local fakeBattle = { trainer = { classId = "RIVAL1" }, battleType = 1,
      emit = function() end, endBattle = function() end,
      printWinLossText = function(_, which) printed = which end }
    Battle.lostBattle(fakeBattle)
    T.eq(printed, "lose", "hardcore: the rival's winning line still prints")
    T.eq(fakeBattle.battleType, 0, "hardcore: then the loss is a real whiteout")
    hsave = { party = party() }
    local before = hsave.party
    World.healParty({ game = { save = hsave, data = data } })
    T.eq(hsave.party[1].hp, 0, "hardcore: Center leaves fainted mons fainted")
    T.eq(hsave.party[2].hp, 18, "hardcore: Center still heals the rest")
    T.eq(hsave.party == before and #hsave.party == 2, true, "hardcore: party kept intact")
    local ItemEffects = require("src.core.gen2.ItemEffects")
    T.eq(ItemEffects.useOnMon("REVIVE", hsave.party[1], data).used, false, "hardcore: no Revive")
    T.eq(ItemEffects.useOnMon("RARE_CANDY", hsave.party[1], data).used, false,
      "hardcore: no Rare Candy on a fainted mon")
    local okBox, why = require("src.core.gen2.Boxes").canDeposit(hsave, 1, 1)
    T.eq(okBox == false and why:find("Fainted", 1, true) ~= nil, true, "hardcore: PC refuses a fainted mon")
    local Breeding = require("src.core.gen2.Breeding")
    local okDc, key = Breeding.canDeposit(data, hsave, "man", 1)
    T.eq(okDc == false and key, "legacy_hard_mode:fainted", "hardcore: Day-Care refuses a fainted mon")
    local reset = false
    loader.game = { softReset = function() reset = true end }
    Runtime.emit("world.blacked_out", { save = hsave })
    T.eq(reset, false, "hardcore: reset waits for the warp home")
    Runtime.emit("map.entered", {})
    T.eq(reset, true, "hardcore: whiting out resets the game")
    loader.modOptions.legacy_hard_mode = nil
    loader.game = nil
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
    local tables = data.gen2EventTables
    if tables and tables.trades then
      local t = tables.trades
      T.eq(t[2].get, "ONIX", "story: Kyle trades Onix")
      T.eq(t[2].item, "HARD_STONE", "story: Onix holds Hard Stone")
      T.eq(t[2].getIndex, 95, "story: trade dex index follows the species")
      T.eq(t[4].get, "MR__MIME", "story: Doris trades Mr. Mime")
      T.eq(t[1].get, "MACHOP", "story: Mike's trade unchanged")
    end
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
    -- Scene 0 is each map's first-visit cutscene (Elm's intro, Mr. Pokemon):
    -- it must survive the build and point at Legacy's script.
    for _, id in ipairs({ "ELMS_LAB", "MR_POKEMONS_HOUSE" }) do
      local scenes = data.gen2Maps[id] and data.gen2Maps[id].sceneScripts
      local zero = scenes and scenes[0]
      if data.gen2Maps[id] and data.gen2Maps[id].objects and #data.gen2Maps[id].objects > 0 or real then
        T.eq(zero and tostring(zero.scriptKey):match("^8%x:") ~= nil, true,
          "story: " .. id .. " keeps scene 0 (first-visit cutscene)")
      end
    end
    -- Every scene a story map ends up with points at Legacy's scripts.
    local stale = 0
    for _, id in ipairs({ "ELMS_LAB", "MR_POKEMONS_HOUSE", "AZALEA_TOWN", "POWER_PLANT" }) do
      for _, sc in pairs((data.gen2Maps[id] or {}).sceneScripts or {}) do
        if not tostring(sc.scriptKey):match("^8%x:") then stale = stale + 1 end
      end
    end
    if real then T.eq(stale, 0, "story: no vanilla scene scripts left on story maps") end
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

    -- ---------------------------------------------------------- deep walk
    -- Every Story entry point, three ways: answering YES to questions (first
    -- menu option), answering NO (cancel), and with every event flag set (so
    -- the "already done" arms run too). Each run must finish, must not hit a
    -- command gen1recomp lacks, and every battle must find its trainer.
    -- STORY_WALK=1 prints the full report.
    local verbose = os.getenv("STORY_WALK") == "1"
    local report = { stall = {}, crash = {}, noTrainer = {}, unknownOps = {}, badBytes = {} }
    local function walk(key, variant)
      local events = Events.new()
      if variant == "allEvents" then
        local get = events.get
        events.get = function(self, id) return true end
      end
      -- A player who keeps the variant's answer for three questions, then
      -- gives in: "ask again" loops (Elm won't take no for an answer) finish,
      -- while a real infinite loop still never does.
      local asked = 0
      local function answer()
        asked = asked + 1
        local yes = variant ~= "no"
        if asked > 3 then yes = not yes end
        return yes
      end
      local battleMiss
      local vm = Vm.new(data.gen2Scripts, data.gen2Text, events, {
        showText = function(_, onDone) if onDone then onDone() end end,
        waitButton = function(cb) cb() end,
        holdStayed = function() return false end,
        yesorno = function(f) f(answer()) end,
        applyMovement = function(_, _, cb) if cb then cb() end end,
        startBattle = function(t, w, done)
          if not t and not w then battleMiss = true end
          done("win")
        end,
        catchTutorial = function(_, _, cb) cb() end,
        openMart = function(_, _, cb) cb() end,
        trainerApproach = function(cb) cb() end,
        openMenu = function(_, _, cb) cb(answer() and 1 or 0) end,
        checkPokeMail = function(_, cb) cb(answer() and 1 or 0) end,
        npcTrade = function(_, cb) cb() end,
        elevator = function(_, cb) cb(false) end,
        phoneCall = function(_, cb) cb() end,
        hallOfFame = function(cb) cb() end,
        credits = function(cb) cb() end,
        readVar = function() return 0 end,
        lookupTrainer = function(c, m) return Trainers.lookup(data.gen2Trainers, c, m) end,
        specialOrder = data.gen2Constants and data.gen2Constants.specialOrder,
        commands = data.commands,
        eventTables = data.gen2EventTables,
        save = function() return {} end,
      })
      vm:start(key)
      local steps = 0
      while vm:running() and steps < 5000 do vm:update() steps = steps + 1 end
      local tag = key .. " [" .. variant .. "]"
      if vm:running() then report.stall[#report.stall + 1] = tag end
      if battleMiss then report.noTrainer[#report.noTrainer + 1] = tag end
      for op, n in pairs(vm.unknownOps or {}) do
        report.unknownOps[op] = (report.unknownOps[op] or 0) + n
      end
      for code, n in pairs(vm.badBytes or {}) do
        report.badBytes[tostring(code)] = (report.badBytes[tostring(code)] or 0) + n
      end
    end
    for _, key in ipairs(entries) do
      for _, variant in ipairs({ "yes", "no", "allEvents" }) do
        local ok, err = pcall(walk, key, variant)
        if not ok then report.crash[#report.crash + 1] = key .. " [" .. variant .. "]: " .. tostring(err) end
      end
    end

    -- Static references across every Story row and Story map.
    local refs = {}
    local function bad(what) refs[#refs + 1] = what end
    local classByIndex, itemByIndex, monByIndex = {}, {}, {}
    for id, c in pairs(data.gen2Trainers.classes or {}) do
      if c.index then classByIndex[c.index] = c end
    end
    for id, it in pairs(data.items or {}) do
      if type(it) == "table" and it.index then itemByIndex[it.index] = id end
    end
    for id, mon in pairs(data.pokemon or {}) do
      if type(mon) == "table" and (mon.dexNumber or mon.index) then monByIndex[mon.dexNumber or mon.index] = id end
    end
    local function exists(kind, key)
      if key == nil then return true end
      if kind == "text" then return data.gen2Text[key] ~= nil end
      if kind == "movement" then return data.gen2Scripts.movements and data.gen2Scripts.movements[key] ~= nil end
      return data.gen2Scripts[key] ~= nil
    end
    for key, rows in pairs(data.gen2Scripts) do
      if type(key) == "string" and key:match("^[89a-f]%x:") then
        for i, r in ipairs(rows) do
          local at = key .. "#" .. i .. " " .. tostring(r.op)
          if not exists("script", r.script) then bad(at .. ": script " .. tostring(r.script)) end
          for _, f in ipairs({ "text", "winText", "lossText", "yesText", "noText" }) do
            if type(r[f]) == "string" and not exists("text", r[f]) then bad(at .. ": " .. f .. " " .. r[f]) end
          end
          if type(r.movement) == "string" and not exists("movement", r.movement) then
            bad(at .. ": movement " .. r.movement)
          end
          if r.op == "loadtrainer" and type(r.class) == "number" then
            local c = classByIndex[r.class]
            if not c then bad(at .. ": no trainer class " .. r.class)
            elseif not (c.trainers and c.trainers[r.member or 1]) then
              bad(at .. ": " .. tostring(c.id) .. " has no member " .. tostring(r.member))
            end
          end
          if (r.op == "givepoke" or r.op == "loadwildmon") and type(r.species) == "number"
              and next(monByIndex) and not monByIndex[r.species] then
            bad(at .. ": no species #" .. r.species)
          end
          if (r.op == "verbosegiveitem" or r.op == "giveitem" or r.op == "takeitem" or r.op == "checkitem")
              and type(r.item) == "number" and r.item ~= 0 and not itemByIndex[r.item] then
            bad(at .. ": no item $" .. string.format("%02x", r.item))
          end
        end
      end
    end
    local varSlots = {}
    for _, rows in pairs(data.gen2Scripts) do
      for _, r in ipairs(type(rows) == "table" and rows or {}) do
        if type(r) == "table" and r.op == "variablesprite" then
          local slot = r.slot or (r.args and r.args[1])
          if slot then varSlots[slot] = true end
        end
      end
    end
    for id, m in pairs(data.gen2Maps) do
      local story = false
      for _, o in ipairs(m.objects or {}) do
        if tostring(o.scriptKey):match("^[89a-f]%x:") then story = true end
      end
      if story then
        for _, o in ipairs(m.objects or {}) do
          local sp = o.sprite
          -- $F0 up are variable sprites: fine when some script fills the slot.
          local var = type(sp) == "number" and ((sp >= 0xf0 and varSlots[sp - 0xf0])
            -- $E0 / $E1: GetMonSprite's Day-Care Pokemon (Route 34)
            or sp == 0xe0 or sp == 0xe1)
          if sp and not var and not data.gen2Sprites[sp] then bad(id .. ": object sprite " .. tostring(sp)) end
        end
        for _, w in ipairs(m.warps or {}) do
          if w.destMap and not data.gen2Maps[w.destMap] then bad(id .. ": warp to " .. w.destMap) end
        end
        -- Every event's script, and every trainer NPC's lines and team.
        local function ev(what, key)
          if key and not exists("script", key) then bad(id .. ": " .. what .. " script " .. tostring(key)) end
        end
        for i, o in ipairs(m.objects or {}) do
          ev("object " .. i, o.scriptKey)
          local t = o.trainer
          if t then
            ev("trainer " .. i, t.scriptKey)
            for _, f in ipairs({ "seenText", "winText", "lossText" }) do
              if type(t[f]) == "string" and not exists("text", t[f]) then
                bad(id .. ": trainer " .. i .. " " .. f .. " " .. t[f])
              end
            end
            local c = type(t.class) == "number" and classByIndex[t.class]
            if type(t.class) == "number" and not c then
              bad(id .. ": trainer " .. i .. " class " .. t.class)
            elseif c and not (c.trainers and c.trainers[t.member or 1]) then
              bad(id .. ": trainer " .. i .. " " .. tostring(c.id) .. " has no member " .. tostring(t.member))
            end
          end
        end
        for i, e in ipairs(m.bgEvents or {}) do ev("bg " .. i, e.scriptKey) end
        for i, e in ipairs(m.coordEvents or {}) do ev("coord " .. i, e.scriptKey) end
        for i, e in ipairs(m.callbacks or {}) do ev("callback " .. i, e.scriptKey) end
        for n, sc in pairs(m.sceneScripts or {}) do ev("scene " .. tostring(n), sc.scriptKey) end
      end
    end

    local unknown = {}
    for op, n in pairs(report.unknownOps) do unknown[#unknown + 1] = op .. " x" .. n end
    table.sort(unknown)
    local badB = {}
    for c, n in pairs(report.badBytes) do badB[#badB + 1] = c .. " x" .. n end
    local function dump(label, list, limit)
      for i = 1, math.min(#list, verbose and #list or (limit or 8)) do print(label .. ": " .. list[i]) end
    end
    table.sort(report.stall) table.sort(report.noTrainer) table.sort(refs)
    dump("walk crash", report.crash) dump("walk stall", report.stall)
    dump("walk no trainer", report.noTrainer) dump("unknown op", unknown)
    dump("bad bytes", badB) dump("bad ref", refs)
    print(("story walk: %d entry points x 3; %d stalls, %d crashes, %d battles without a trainer, %d unknown ops, %d bad refs")
      :format(#entries, #report.stall, #report.crash, #report.noTrainer, #unknown, #refs))
    T.eq(#report.crash, 0, "story walk: no Lua errors on any branch")
    T.eq(#report.stall, 0, "story walk: every branch finishes")
    T.eq(#report.noTrainer, 0, "story walk: every battle finds its trainer")
    T.eq(#unknown, 0, "story walk: no command gen1recomp lacks")
    T.eq(#refs, 0, "story walk: every trainer / item / species / sprite / warp exists")
    -- A script that fades the screen out must fade it back in or leave the
    -- map (gen1recomp keeps a fade until something lifts it): the fossil
    -- scientist once left the Research Center black.
    local order = data.gen2Constants and data.gen2Constants.specialOrder or {}
    local special = {}
    for i, name in ipairs(order) do special[name] = i - 1 end
    local outs = { [special.FadeOutToBlack or -1] = true, [special.FadeOutToWhite or -1] = true }
    local ins = { [special.FadeInFromBlack or -1] = true, [special.FadeInFromWhite or -1] = true }
    local leaves = { warp = true, warpfacing = true, warpmod = true, reloadmap = true,
      reloadmapafterbattle = true, newloadmap = true, warpcheck = true }
    local dark = {}
    for key, rows in pairs(data.gen2Scripts) do
      if type(key) == "string" and key:match("^[89a-f]%x:") then
        local pending = false
        for _, r in ipairs(rows) do
          if r.op == "special" and outs[r.id] then pending = true
          elseif (r.op == "special" and ins[r.id]) or leaves[r.op] then pending = false end
        end
        if pending then dark[#dark + 1] = key end
      end
    end
    table.sort(dark)
    for _, k in ipairs(dark) do print("left dark: " .. k) end
    T.eq(#dark, 0, "story walk: every fade-out is faded back in (or leaves the map)")
    -- Std scripts (nurses, signs, bookshelves...): every call resolves to a
    -- real one. The only exception is Legacy's own KantoLevelCapUpdateScript,
    -- which gen1recomp has no equivalent of and which just ends. (A build once
    -- sent every std call there, silencing every nurse on Story maps.)
    local unresolved, legacyOnly = {}, 0
    for key, rows in pairs(data.gen2Scripts) do
      if type(key) == "string" and key:match("^[89a-f]%x:") then
        for i, r in ipairs(rows) do
          if r.op == "jumpstd" or r.op == "callstd" then
            if r.script and data.gen2Scripts[r.script] then
            elseif (r.id or 0) >= 500 then legacyOnly = legacyOnly + 1
            else unresolved[#unresolved + 1] = key .. "#" .. i end
          end
        end
      end
    end
    for _, k in ipairs(unresolved) do print("std unresolved: " .. k) end
    T.eq(#unresolved, 0, "story walk: every std script call resolves")
    T.eq(legacyOnly <= 20, true, "story walk: only Legacy's Kanto level-cap std calls end early (" .. legacyOnly .. ")")
    -- And the bug as reported: the Goldenrod nurse talks.
    local nurseKey
    for _, o in ipairs((data.gen2Maps.GOLDENROD_POKECENTER_1F or {}).objects or {}) do
      if o.sprite == "SPRITE_NURSE" then nurseKey = o.scriptKey end
    end
    local said = 0
    if nurseKey then
      local vm = Vm.new(data.gen2Scripts, data.gen2Text, Events.new(), {
        showText = function(_, cb) said = said + 1 if cb then cb() end end,
        yesorno = function(f) f(false) end, waitButton = function(cb) cb() end,
        specialOrder = data.gen2Constants and data.gen2Constants.specialOrder,
        commands = data.commands, save = function() return {} end,
      })
      vm:start(nurseKey)
      for _ = 1, 3000 do if not vm:running() then break end vm:update() end
    end
    T.eq(said > 0, true, "story walk: the Goldenrod nurse talks")
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
    -- The rooftop clerk (MARTTYPE_ROOFTOP) gets the sale list at sale prices.
    local roof = data.screens.Gen2MartMenu.new(game, { martType = 4, martId = 0,
      save = save, items = data.items })
    T.eq(roof.entries[2].id, "GREAT_BALL", "shops: rooftop sale list 1")
    T.eq(roof.entries[2].price, 350, "shops: rooftop Great Ball at Legacy's 350")
    save.hallOfFame = { count = 1 }
    roof = data.screens.Gen2MartMenu.new(game, { martType = 4, martId = 0,
      save = save, items = data.items })
    T.eq(roof.entries[1].id, "HYPER_POTION", "shops: rooftop list 2 after the Hall of Fame")
    T.eq(roof.entries[1].price, 750, "shops: rooftop Hyper Potion at 750")
  end,
}
for _, id in ipairs(ids) do
  if CHECKS[id] then CHECKS[id]() end
end

-- The shared "CRYSTAL LEGACY" options page, whenever a Legacy mod with
-- settings is loaded.
do
  local withSettings = { legacy_hard_mode = "HARD MODE", crystal_legacy_qol = "QUALITY OF LIFE",
    crystal_legacy_fixes = "BUG FIXES", crystal_legacy_icons = "MENU ICONS",
    crystal_legacy_pokedex = "POKEDEX" }
  local expected = {}
  for _, id in ipairs(ids) do if withSettings[id] then expected[#expected + 1] = id end end
  if #expected > 0 then
    local ManagerState = require("src.mods.ManagerState")
    local reg = rawget(ManagerState, "__crystalLegacyOptions")
    T.eq(reg ~= nil, true, "options: Legacy settings page registered")
    local rows = Runtime.call("ui.options.rows", function(_, r) return r end, {},
      { { label = "TEXT SPEED" }, { label = "MODS" } })
    local at, mods, count = nil, nil, 0
    for i, r in ipairs(rows) do
      if r.label == "CRYSTAL LEGACY" then at = i count = count + 1 end
      if r.label == "MODS" then mods = i end
    end
    T.eq(count, 1, "options: exactly one CRYSTAL LEGACY row")
    T.eq(at and mods and at == mods - 1, true, "options: placed just before MODS")
    local game = { mods = loader, save = { options = {} }, writeOptions = function() end }
    local page = reg and reg.newScreen(game)
    local headers = {}
    for _, r in ipairs(page and page.rows or {}) do if r.header then headers[r.label] = true end end
    for _, id in ipairs(expected) do
      T.eq(headers[withSettings[id]] == true, true, "options: page lists " .. withSettings[id])
    end
    -- Flip the first setting through the page; the MODS menu's store sees it.
    local first = page and page.rows[page.index]
    if first and first.step then
      local before = first.value()
      first.step(game)
      T.eq(first.value() ~= before, true, "options: a setting changes from the page")
      local saved = false
      for _, bucket in pairs(game.save.options.modOptions or {}) do
        for _ in pairs(bucket) do saved = true end
      end
      T.eq(saved, true, "options: saved where the MODS menu reads it")
      first.step(game, -1) -- put it back
    end
    -- Drawn as Crystal's options screen: one frame, no per-row boxes.
    if page then
      local okDraw, err = pcall(page.draw, page)
      if not okDraw then print("options draw: " .. tostring(err)) end
      T.eq(okDraw, true, "options: page draws")
    end
    -- Choice rows cycle both ways.
    for _, r in ipairs(page and page.rows or {}) do
      if r.label == "POKEDEX COLOR" then
        T.eq(r.value(), "RED", "options: dex colour starts RED")
        r.step(game, 1)
        T.eq(r.value(), "BLUE", "options: right picks the next colour")
        r.step(game, -1) r.step(game, -1)
        T.eq(r.value(), "GRAY", "options: left wraps to the last colour")
        r.step(game, 1)
      end
    end
  end
end
if loader.mods.crystal_legacy_trainers then CHECKS.crystal_legacy_trainers_scaling() end

T.sdk.restoreRuntime()
Logger.warn, Logger.error = realWarn, realError
T.finish(label)
