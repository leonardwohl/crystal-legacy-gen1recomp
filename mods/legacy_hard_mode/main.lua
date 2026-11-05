-- Legacy Hard Mode: Crystal Legacy's optional Hard Mode for gen1recomp.
--
--   * Level caps that rise with story progress. Pokémon at the cap gain no
--     experience and Rare Candy has no effect on them.
--   * Trainer battles are fought in SET style (no free switch when the foe's
--     Pokémon faints) and the PACK cannot be used in them.
--
-- Crystal Legacy writes its cap into RAM from about thirty map scripts. A mod
-- cannot run those scripts, so the cap is recomputed from what the save
-- already records (badges and vanilla event flags), plus two wins vanilla does
-- not record, which this mod notes in its own save data. The schedule below is
-- Crystal Legacy's (maps/*Gym.asm, the Elite Four rooms, DragonShrine.asm,
-- KantoLevelCapUpdateScript in engine/events/std_scripts.asm).
--
-- Event ids are vanilla Crystal's (pokecrystal constants/event_flags.asm),
-- matching src/core/gen2/FlagNames.lua in gen1recomp.

local START_CAP = 10

-- Johto badge count -> cap. Badges 5-7 can be earned in any order, so the
-- cap follows the count rather than which leader was beaten.
local JOHTO = { 16, 21, 25, 31, 36, 38, 45, 50 }
-- Total badge count 9-16 (Kanto gyms, any order) -> cap.
local KANTO = { [9] = 62, [10] = 63, [11] = 64, [12] = 66,
                [13] = 66, [14] = 67, [15] = 69, [16] = 69 }
local EVENTS = {
  { id = 1464, cap = 52 }, -- EVENT_BEAT_ELITE_4_WILL
  { id = 1465, cap = 54 }, -- EVENT_BEAT_ELITE_4_KOGA
  { id = 1466, cap = 55 }, -- EVENT_BEAT_ELITE_4_BRUNO
  { id = 1468, cap = 60 }, -- EVENT_BEAT_CHAMPION_LANCE
}
-- Wins this mod records itself (vanilla sets no event for them).
local E4_REMATCH_CAP = 77 -- Lance beaten again with all 16 badges
local RED_CAP = 100

local ITEMS_REFUSED = "Items can't be\nused here."

local function badgeCount(store, names)
  if type(store) ~= "table" then return 0 end
  local n = 0
  for i, name in ipairs(names) do
    if store[name] or store[i] then n = n + 1 end
  end
  return n
end

local JOHTO_NAMES = { "ZEPHYR", "HIVE", "PLAIN", "FOG", "MINERAL", "STORM", "GLACIER", "RISING" }
local KANTO_NAMES = { "BOULDER", "CASCADE", "THUNDER", "RAINBOW", "SOUL", "MARSH", "VOLCANO", "EARTH" }

return function(mod)
  mod.options:define({
    { key = "levelCaps", label = "LEVEL CAPS", type = "toggle", default = true },
    { key = "setMode", label = "SET MODE VS TRAINERS", type = "toggle", default = true },
    { key = "noItems", label = "NO ITEMS VS TRAINERS", type = "toggle", default = true },
  })

  local function option(key)
    local v = mod.options:get(key)
    if v == nil then return true end
    return v
  end

  -- ------------------------------------------------------------- level cap
  -- Vanilla event flags live in the overworld's event store (wEventFlags).
  local function eventSet(id)
    local game = mod.game
    local world = game and (game.world or (game.overworld and game.overworld.world))
    local events = world and world.events
    if events and events.get then return events:get(id) == true end
    return false
  end

  local function currentCap()
    local game = mod.game
    local save = game and game.save
    local player = save and save.player or {}
    local johto = badgeCount(player.badges, JOHTO_NAMES)
    local total = johto + badgeCount(player.kantoBadges, KANTO_NAMES)
    local cap = START_CAP
    if johto > 0 then cap = math.max(cap, JOHTO[johto]) end
    for _, row in ipairs(EVENTS) do
      if eventSet(row.id) then cap = math.max(cap, row.cap) end
    end
    if KANTO[total] then cap = math.max(cap, KANTO[total]) end
    if mod.save:get("e4Rematch", false) then cap = math.max(cap, E4_REMATCH_CAP) end
    if mod.save:get("beatRed", false) then cap = math.max(cap, RED_CAP) end
    return cap
  end

  mod.exports.currentCap = currentCap

  -- No experience at or above the cap, and never past it.
  mod.hooks:wrap("exp.gain", function(nextFn, ctx)
    local amount = nextFn(ctx)
    if not option("levelCaps") or type(amount) ~= "number" then return amount end
    local mon = ctx and ctx.mon
    if not mon then return amount end
    local cap = currentCap()
    if (mon.level or 1) >= cap then return 0 end
    local data = ctx.battle and ctx.battle.data
    local def = data and data.pokemon and data.pokemon[mon.species]
    local ok, Mon = pcall(require, "src.battle.gen2.Mon")
    if ok and def and mon.experience then
      local growth = Mon.growthFor(data, def.growthRate)
      local limit = Mon.experienceForLevel(growth, cap) - mon.experience
      if limit < amount then return math.max(0, limit) end
    end
    return amount
  end)

  -- Rare Candy has no effect at the cap.
  local candy = mod.content.item_effects:get("RARE_CANDY")
  if candy and type(candy.use) == "function" then
    local vanillaUse = candy.use
    mod.content.item_effects:patch("RARE_CANDY", {
      use = function(ctx, ...)
        if option("levelCaps") and ctx and ctx.mon
            and (ctx.mon.level or 1) >= currentCap() then
          local Strings = require("src.core.Strings")
          local ItemEffects = require("src.core.gen2.ItemEffects")
          return { used = false, text = Strings(ItemEffects.TEXT_NO_EFFECT) }
        end
        return vanillaUse(ctx, ...)
      end,
    })
  else
    mod.log:warn("RARE_CANDY effect not found; Rare Candy is not capped")
  end

  -- -------------------------------------------- trainer battle rules
  local active = nil -- { ui = BattleState, style = saved battleStyle }

  local function trainerOf(payload)
    local b = payload and payload.battle
    local t = b and (b.trainer or (b.battle and b.battle.trainer))
    return t
  end

  mod.events:on("battle.started", function(payload)
    if not payload or payload.kind ~= "trainer" then return end
    active = active or {}
    -- BattleState raises the event with itself as `battle`; it is the one
    -- with refuseMenu, which is how the PACK refusal is shown.
    if payload.battle and payload.battle.refuseMenu then active.ui = payload.battle end
    local game = mod.game
    local options = game and game.options
    if option("setMode") and options and active.style == nil then
      active.style = options.battleStyle or "SHIFT"
      options.battleStyle = "SET"
    end
  end)

  mod.events:on("battle.ended", function(payload)
    local t = trainerOf(payload)
    local won = payload and payload.result == "win"
    if won and t then
      local class, member = t.classId or t.class, t.memberId
      if class == "RED" then mod.save:set("beatRed", true) end
      -- The Elite Four rematch: Lance again, with all 16 badges.
      if class == "CHAMPION" and member ~= "LANCE" and member ~= "CHAMPION1"
          and eventSet(1468) then
        local player = mod.game and mod.game.save and mod.game.save.player or {}
        if badgeCount(player.badges, JOHTO_NAMES)
            + badgeCount(player.kantoBadges, KANTO_NAMES) >= 16 then
          mod.save:set("e4Rematch", true)
        end
      end
    end
    if active then
      local options = mod.game and mod.game.options
      if active.style ~= nil and options then options.battleStyle = active.style end
      active = nil
    end
  end)

  -- The PACK in a trainer battle: refuse it the way the Battle Tower does.
  local okPack, PackMenu = pcall(require, "src.ui.gen2.PackMenu")
  if okPack and PackMenu and PackMenu.new then
    mod.content.screens:register("Gen2PackMenu", {
      new = function(game, opts, ...)
        if opts and opts.battle and active and active.ui and option("noItems") then
          local ui = active.ui
          return {
            enter = function() end, draw = function() end, exit = function() end,
            update = function()
              if opts.onClose then opts.onClose() end
              ui:refuseMenu(require("src.core.Strings").source(ITEMS_REFUSED))
            end,
          }
        end
        return PackMenu.new(game, opts, ...)
      end,
    })
  else
    mod.log:warn("battle PACK module not found; items stay usable vs trainers")
  end

  mod.log:info("Legacy Hard Mode loaded")
end
