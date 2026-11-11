#!/usr/bin/env python3
"""Generate every mod under mods/ from a Crystal Legacy checkout.

    python3 tools/build.py --base <pokecrystal@82e315e48> --legacy <Crystal Legacy>

Each mod is self-contained (gen1recomp mods cannot load each other's files),
so the small Lua runtime below is written into every generated main.lua.
Hand-written mods (no `data` builder here) are left alone.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legacy_diff as D  # noqa: E402
import textc  # noqa: E402
from asm import const_values, statements  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "0.3.0"
GAME_VERSION = ">=0.4.0 <0.5.0"
GITHUB = "leonardwohl/crystal-legacy-gen1recomp"

PRELUDE = r'''
-- Patch one record, logging instead of aborting when gen1recomp refuses it,
-- so a single bad record never takes the rest of the mod down with it.
local function patch(mod, registry, id, fields, stats)
  local reg = mod.content[registry]
  if not reg then
    mod.log:warn("registry %s is not available; skipped %s", registry, tostring(id))
    stats.failed = stats.failed + 1
    return
  end
  local ok, result, reason = pcall(reg.patch, reg, id, fields)
  if not ok or (result == nil and reason ~= nil) then
    mod.log:warn("%s %s: %s", registry, tostring(id), tostring(ok and reason or result))
    stats.failed = stats.failed + 1
  else
    stats.applied = stats.applied + 1
  end
end

-- Deterministic iteration, so load order (and any warnings) is reproducible.
local function each(map, fn)
  local keys = {}
  for k in pairs(map) do keys[#keys + 1] = k end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  for _, k in ipairs(keys) do fn(k, map[k]) end
end

-- Write custom DVs / stat exp / happiness onto a built trainer party.
-- gen1recomp gives trainer mons the vanilla fixed DVs; this hook runs before
-- the battle computes stats, so the values here are what the battle uses.
local function wrapTrainerExtras(mod, extras, memberIndex)
  if next(extras) == nil then return end
  mod.hooks:wrap("trainer.party", function(nextFn, class, member, party)
    party = nextFn(class, member, party)
    local index = type(member) == "string" and memberIndex[member] or member
    local slots = extras[class] and extras[class][index]
    if slots and type(party) == "table" then
      for slot, extra in pairs(slots) do
        local mon = party[slot]
        if mon then
          if extra.dvs then mon.dvs = extra.dvs end
          if extra.statExp then mon.statExp = extra.statExp end
          if extra.happiness then mon.happiness = extra.happiness end
        end
      end
    end
    return party
  end)
end
'''


# ----------------------------------------------------------- mod builders
# Each returns (data table, Lua apply body, summary lines for the README).

def build_pokemon(ctx):
    pk = {sp: {k: v for k, v in p.items() if k != "eggSteps"}
          for sp, p in ctx["pokemon"].items()}
    pk = {sp: p for sp, p in pk.items() if p}
    base, leg = ctx["base"], ctx["legacy"]
    data = {"pokemon": pk, "moves": ctx["moves"],
            # engine/items/item_effects.asm: these become EvoStoneEffect, and
            # data/items/attributes.asm makes them usable on a party Pokémon.
            "evoItems": ["KINGS_ROCK", "METAL_COAT", "DRAGON_SCALE", "UP_GRADE", "BRICK_PIECE"],
            "happiness": D.parse.happiness_changes(leg),
            "metronomeAdd": sorted(set(D.parse.metronome_exceptions(leg))
                                   - set(D.parse.metronome_exceptions(base))),
            "critAdd": sorted(set(D.parse.crit_moves(leg)) - set(D.parse.crit_moves(base)))}
    body = '''
  each(DATA.pokemon, function(id, fields)
    if mod.content.pokemon:get(id) then patch(mod, "pokemon", id, fields, stats) end
  end)
  each(DATA.moves, function(id, fields)
    if mod.content.moves:get(id) then patch(mod, "moves", id, fields, stats) end
  end)
  legacyEvolutionItems(mod, stats)
  legacyEngineTables(mod, stats)'''
    fields = {}
    for p in pk.values():
        for k in p:
            fields[k] = fields.get(k, 0) + 1
    names = {"baseStats": "base stats", "levelMoves": "level-up learnsets",
             "tmhm": "TM/HM compatibility", "tutorMoves": "move tutor compatibility",
             "evolutions": "evolutions", "eggMoves": "egg moves", "types": "types",
             "catchRate": "catch rates", "baseExp": "base experience",
             "growthRate": "growth rates", "genderRatio": "gender ratios",
             "eggGroups": "egg groups", "items": "wild held items"}
    lines = ["%d Pokémon changed:" % len(pk)]
    lines += ["  - %s: %d species" % (names.get(k, k), n) for k, n in sorted(fields.items())]
    lines.append("%d moves changed (power, accuracy, PP, type or effect)" % len(ctx["moves"]))
    lines += ["King's Rock, Metal Coat, Dragon Scale, Up-Grade and Brick Piece are used "
              "from the PACK like evolution stones (Politoed, Slowking, Steelix, Scizor, "
              "Kingdra, Porygon2, Hitmontop)",
              "Happiness rises faster (levelling, gym leaders, haircuts)",
              "Cut has a high critical-hit ratio; Metronome can't call Explosion or Selfdestruct",
              "The Zephyr Badge makes traded Pokémon up to level 16 obey"]
    return data, body, lines


def build_trainers(ctx):
    rows, extras = ctx["trainersVanilla"], ctx["extrasVanilla"]
    scaling = []
    # maps/{Mahogany,Olivine,Cianwood}Gym.asm: ifequal 5 -> team 2, 6 -> team 3.
    for cls in ("PRYCE", "JASMINE", "CHUCK"):
        tiers = []
        for badges, legacy_index in ((5, 2), (6, 3)):
            row = next(r for r in ctx["trainersAll"][cls] if r["index"] == legacy_index)
            party = {k: v for k, v in row.items() if k != "index"}
            party["id"] = "%s_%dBADGES" % (cls, badges)
            tiers.append({"badges": badges, "party": party})
        scaling.append({"class": cls, "tiers": tiers})
    base, leg = ctx["base"], ctx["legacy"]
    b_items, l_items = D.parse.class_items(base), D.parse.class_items(leg)
    vanilla_classes = set(b_items)
    data = {"trainers": rows, "extras": extras, "scaling": scaling, "varBadges": 7,
            # data/trainers/attributes.asm: Legacy takes the healing items
            # (Hyper Potions, Full Heals...) away from these classes.
            "classItems": {c: v for c, v in l_items.items()
                           if c in vanilla_classes and b_items.get(c) != v},
            # data/trainers/dvs.asm: every trainer Pokémon gets its class's DVs.
            "classDvs": D.parse.class_dvs(leg),
            "memberIndex": {r["id"]: r["index"] for rs in rows.values() for r in rs}}
    body = '''
  each(DATA.trainers, function(class, rows)
    patch(mod, "trainers", class, { trainers = rows }, stats)
  end)
  for _, S in ipairs(DATA.scaling) do scaleLeader(mod, S, stats) end
  each(DATA.classItems, function(class, items)
    if mod.content.trainers:get(class) then
      -- an empty {} patch is a no-op in gen1recomp's merge, so clear explicitly
      patch(mod, "trainers", class, { items = next(items) and items or mod.DELETE }, stats)
    end
  end)
  wrapTrainerExtras(mod, DATA.extras, DATA.memberIndex)
  -- Class DVs replace gen1recomp's flat 9/8/8/8 only, so a team's own custom
  -- DVs (here, Rematches, Story) always win whichever hook runs first.
  mod.hooks:wrap("trainer.party", function(nextFn, class, member, party)
    party = nextFn(class, member, party)
    local dvs = DATA.classDvs[class]
    if dvs and type(party) == "table" then
      for _, mon in ipairs(party) do
        local d = mon.dvs
        if d and d.attack == 9 and d.defense == 8 and d.speed == 8 and d.special == 8 then
          mon.dvs = { attack = dvs.attack, defense = dvs.defense,
                      speed = dvs.speed, special = dvs.special }
        end
      end
    end
    return party
  end)'''
    n = sum(len(r) for r in rows.values())
    return data, body, ["%d trainer classes, %d parties rewritten to Crystal Legacy's teams" % (
        len(rows), n), "Held items and movesets included; custom DVs/stat exp where Legacy sets them",
        "Pryce, Jasmine and Chuck bring a stronger team if you face them with 5 or 6 badges "
        "(Crystal Legacy lets you take those three gyms in any order)",
        "Trainer classes use Crystal Legacy's DVs (stronger gym leaders), and leaders no "
        "longer carry healing items"]


def build_encounters(ctx):
    enc = ctx["encounters"]
    data = {"encounters": enc, "flee": D.parse.flee_lists(ctx["legacy"])}
    body = '''
  each(DATA.encounters, function(kind, value)
    if kind == "bugContest" then
      local reg = mod.content.encounters
      local ok, err = pcall(reg.override, reg, kind, value)
      if ok then stats.applied = stats.applied + 1 else
        stats.failed = stats.failed + 1
        mod.log:warn("encounters bugContest: %s", tostring(err))
      end
    else
      patch(mod, "encounters", kind, value, stats)
    end
  end)
  -- data/wild/flee_mons.asm: far fewer wild Pokémon run away.
  local okR, Roamers = pcall(require, "src.core.gen2.Roamers")
  if okR and Roamers and Roamers.SOMETIMES_FLEE and Roamers.OFTEN_FLEE then
    for _, t in ipairs({ { Roamers.SOMETIMES_FLEE, DATA.flee.sometimes },
                         { Roamers.OFTEN_FLEE, DATA.flee.often } }) do
      for k in pairs(t[1]) do t[1][k] = nil end
      for _, sp in ipairs(t[2]) do t[1][sp] = true end
    end
  else
    mod.log:warn("flee tables not found; flee changes skipped")
  end'''
    return data, body, [
        "%d grass encounter tables (morning, day and night)" % len(enc.get("grass", {})),
        "%d water encounter tables" % len(enc.get("water", {})),
        "Bug-Catching Contest: %s" % ("changed" if "bugContest" in enc else "unchanged in Crystal Legacy"),
        "Headbutt trees and Rock Smash: unchanged in Crystal Legacy, so nothing to apply",
        "Far fewer wild Pokémon flee: only Umbreon and Togetic (plus Raikou and Entei)"]


def build_fast_eggs(ctx):
    steps = {sp: p["eggSteps"] for sp, p in ctx["pokemon"].items() if "eggSteps" in p}
    data = {"eggSteps": steps}
    body = '''
  each(DATA.eggSteps, function(id, steps)
    if mod.content.pokemon:get(id) then
      patch(mod, "pokemon", id, { eggSteps = steps }, stats)
    end
  end)'''
    return data, body, ["Egg hatch cycles cut to about a quarter for all %d species, using "
                        "Crystal Legacy's exact values" % len(steps)]


def build_ghost_dark(ctx):
    data = {"categories": {"GHOST": "special", "DARK": "physical"}}
    body = '''
  each(DATA.categories, function(id, category)
    patch(mod, "type_chart", id, { category = category }, stats)
  end)'''
    return data, body, ["Ghost-type moves use Special Attack / Special Defense",
                        "Dark-type moves use Attack / Defense"]


SHOPS_RUNTIME = r"""
local function copy(v)
  if type(v) ~= "table" then return v end
  local out = {}
  for k, x in pairs(v) do out[k] = copy(x) end
  return out
end

local function setScript(mod, verb, id, rows, stats)
  local reg = mod.content.map_scripts
  local ok, err = pcall(reg[verb], reg, id, rows)
  if ok then stats.applied = stats.applied + 1 else
    stats.failed = stats.failed + 1
    mod.log:warn("map script %s: %s", id, tostring(err))
  end
end

local function martIdOf(row)
  if row.mart or row.martId then return row.mart or row.martId end
  local a = row.args
  return a and ((a[2] or 0) + (a[3] or 0) * 256) or nil
end

-- gen1recomp's mart ids are a closed set (vanilla's 34), so Legacy's new
-- stock lists get ids from 1000 up, and the mart screen is wrapped to serve
-- them. Vanilla ids pass straight through to the normal screen.
local function wrapMartScreen(mod, stats)
  local ok, MartMenu = pcall(require, "src.ui.gen2.MartMenu")
  if not (ok and MartMenu and MartMenu.new) then
    mod.log:warn("mart screen not found; new shops disabled")
    stats.failed = stats.failed + 1
    return false
  end
  mod.content.screens:register("Gen2MartMenu", {
    new = function(game, opts, ...)
      -- MARTTYPE_ROOFTOP (4): gen1recomp's mart screen knows types 0-3 and
      -- would open the rooftop clerk as a plain mart 0. Serve RooftopSale
      -- instead: list 1, or list 2 once the player is in the Hall of Fame,
      -- each item at the sale's own price.
      local kind = opts and opts.martType
      if (kind == 4 or kind == "ROOFTOP") and DATA.rooftop[1] then
        local o = {}
        for k, v in pairs(opts) do o[k] = v end
        o.martType, o.martId = 0, 0
        local menu = MartMenu.new(game, o, ...)
        local okH, HallOfFame = pcall(require, "src.core.gen2.HallOfFame")
        local entered = okH and HallOfFame.hasEntered(menu.save)
        local list = DATA.rooftop[entered and 2 or 1] or DATA.rooftop[1]
        local entries = {}
        for _, row in ipairs(list) do
          local def = menu.items and menu.items[row.item]
          entries[#entries + 1] = { id = row.item, price = row.price,
            name = (def and def.name) or row.item }
        end
        menu.entries = entries
        return menu
      end
      local list = opts and DATA.customMarts[opts.martId]
      if list then
        -- Shallow: opts.save must stay the live save, or purchases would be
        -- charged to a copy.
        local o = {}
        for k, v in pairs(opts) do o[k] = v end
        opts = o
        opts.marts = { lists = { list } }
        opts.martId = 0
      end
      return MartMenu.new(game, opts, ...)
    end,
  })
  return true
end

-- A clerk whose vanilla script opens `vanillaMart` gets Legacy's badge check:
-- with enough badges they open the upgraded stock instead.
local function upgradeClerk(mod, U, stats)
  local map = mod.content.maps:get(U.map)
  for _, obj in ipairs(map and map.objects or {}) do
    local rows = obj.scriptKey and mod.content.map_scripts:get(obj.scriptKey)
    local sells = false
    for _, row in ipairs(rows or {}) do
      if type(row) == "table" and row.op == "pokemart" and martIdOf(row) == U.vanillaMart then
        sells = true
      end
    end
    if sells then
      local base = ("crystal_legacy_shops:%s:%d"):format(U.map, obj.index or 0)
      setScript(mod, "register", base .. ":vanilla", copy(rows), stats)
      setScript(mod, "register", base .. ":upgraded", {
        { op = "faceplayer" }, { op = "opentext" },
        { op = "pokemart", martType = 0, mart = U.custom },
        { op = "closetext" }, { op = "end" },
      }, stats)
      setScript(mod, "override", obj.scriptKey, {
        { op = "readvar", var = DATA.varBadges },
        { op = "ifgreater", value = U.badges - 1, script = base .. ":upgraded" },
        { op = "sjump", script = base .. ":vanilla" },
      }, stats)
      return
    end
  end
  mod.log:warn("%s: no clerk sells mart %d; upgrade skipped", U.map, U.vanillaMart)
  stats.failed = stats.failed + 1
end

-- A brand-new clerk NPC (Legacy's Goldenrod Flower Shop berry seller).
local function addClerk(mod, C, stats)
  local map = mod.content.maps:get(C.map)
  if not (map and map.objects) then
    mod.log:warn("%s not found; clerk skipped", C.map)
    stats.failed = stats.failed + 1
    return
  end
  local key = "crystal_legacy_shops:" .. C.map .. ":clerk"
  local rows = { { op = "faceplayer" }, { op = "opentext" },
                 { op = "readvar", var = DATA.varBadges } }
  for _, tier in ipairs(C.tiers) do
    if tier.minBadges then
      rows[#rows + 1] = { op = "ifgreater", value = tier.minBadges - 1,
                          script = key .. ":" .. tier.mart }
    end
  end
  local fallback = C.tiers[#C.tiers].mart
  for _, tier in ipairs(C.tiers) do
    setScript(mod, "register", key .. ":" .. tier.mart, {
      { op = "pokemart", martType = 0, mart = tier.mart },
      { op = "closetext" }, { op = "end" },
    }, stats)
  end
  rows[#rows + 1] = { op = "sjump", script = key .. ":" .. fallback }
  setScript(mod, "register", key, rows, stats)
  local objects = map.objects
  objects[#objects + 1] = {
    index = #objects + 1, sprite = C.sprite, x = C.x, y = C.y,
    movement = C.movement, radius = { x = 0, y = 0 }, hours = { -1, -1 },
    palette = 0, type = 0, sight = 0, scriptKey = key,
  }
  patch(mod, "maps", C.map, { objects = objects }, stats)
end
"""


def build_shops(ctx):
    base, leg = ctx["base"], ctx["legacy"]
    lmarts = D.parse.marts(leg)
    vmart = const_values(os.path.join(base, "constants/mart_constants.asm"))
    move = const_values(os.path.join(base, "constants/map_object_constants.asm"))
    new = ["MART_CELADON_3F_2", "MART_CELADON_5F_1_2", "MART_CELADON_5F_2_2",
           "MART_BERRYS", "MART_BERRYS_2"]
    custom = {1000 + i: lmarts[m] for i, m in enumerate(new)}
    cid = {m: 1000 + i for i, m in enumerate(new)}
    data = {
        "marts": ctx["marts"], "items": ctx["items"], "customMarts": custom,
        "rooftop": D.parse.rooftop_sale(ctx["legacy"]),
        "varBadges": 7,
        # Celadon Dept. Store: Legacy's clerks switch to these TM lists at 16 badges.
        "upgrades": [
            {"map": "CELADON_DEPT_STORE_3F", "vanillaMart": vmart["MART_CELADON_3F"],
             "custom": cid["MART_CELADON_3F_2"], "badges": 16},
            {"map": "CELADON_DEPT_STORE_5F", "vanillaMart": vmart["MART_CELADON_5F_1"],
             "custom": cid["MART_CELADON_5F_1_2"], "badges": 16},
            {"map": "CELADON_DEPT_STORE_5F", "vanillaMart": vmart["MART_CELADON_5F_2"],
             "custom": cid["MART_CELADON_5F_2_2"], "badges": 16},
        ],
        # maps/GoldenrodFlowerShop.asm: object_event 5, 3, SPRITE_CLERK,
        # SPRITEMOVEDATA_STANDING_DOWN ... BerryMartScript (7+ badges: more berries).
        "clerks": [
            {"map": "GOLDENROD_FLOWER_SHOP", "x": 5, "y": 3, "sprite": "SPRITE_CLERK",
             "movement": move["SPRITEMOVEDATA_STANDING_DOWN"],
             "tiers": [{"minBadges": 7, "mart": cid["MART_BERRYS_2"]},
                       {"mart": cid["MART_BERRYS"]}]},
        ],
    }
    body = '''
  each(DATA.items, function(id, fields)
    if mod.content.items:get(id) then patch(mod, "items", id, fields, stats) end
  end)
  each(DATA.marts, function(id, items) patch(mod, "marts", id, items, stats) end)
  if wrapMartScreen(mod, stats) then
    for _, U in ipairs(DATA.upgrades) do upgradeClerk(mod, U, stats) end
    for _, C in ipairs(DATA.clerks) do addClerk(mod, C, stats) end
  end'''
    return data, body, ["%d shops restocked" % len(ctx["marts"]),
                        "%d item prices changed" % len(ctx["items"]),
                        "Celadon Dept. Store 3F and 5F clerks sell Legacy's extra TMs "
                        "once you have all 16 badges",
                        "New berry clerk in the Goldenrod Flower Shop (more berries from 7 badges)",
                        "Goldenrod rooftop sale: Legacy's cheaper prices, and the sale items "
                        "themselves (gen1recomp otherwise opens a plain mart there)"]

# ----------------------------------------------------------------- rematches
SCRIPT_HELPERS = r"""
local function copy(v)
  if type(v) ~= "table" then return v end
  local out = {}
  for k, x in pairs(v) do out[k] = copy(x) end
  return out
end

local function slice(list, from)
  local out = {}
  for i = from, #list do out[#out + 1] = copy(list[i]) end
  return out
end

-- Append a rematch party to a trainer class; returns (class index, member).
-- Reads the merged list, so it lands after Trainer Changes' teams when that
-- mod is installed (it is an optional dependency, so it always loads first).
local function appendParty(mod, class, row, stats)
  local rec = mod.content.trainers:get(class)
  if not (rec and rec.trainers and rec.index) then
    mod.log:warn("trainer class %s not found; rematch skipped", class)
    stats.failed = stats.failed + 1
    return nil
  end
  local list = rec.trainers
  local member = #list + 1
  local new = copy(row)
  new.index = member
  list[member] = new
  patch(mod, "trainers", class, { trainers = list }, stats)
  return rec.index, member
end

local function addText(mod, id, value, stats)
  local ok, err = pcall(mod.content.text.register, mod.content.text, id, value)
  if ok then stats.applied = stats.applied + 1 else
    stats.failed = stats.failed + 1
    mod.log:warn("text %s: %s", id, tostring(err))
  end
end

local function setScript(mod, verb, id, rows, stats)
  local reg = mod.content.map_scripts
  local ok, err = pcall(reg[verb], reg, id, rows)
  if ok then stats.applied = stats.applied + 1 else
    stats.failed = stats.failed + 1
    mod.log:warn("map script %s: %s", id, tostring(err))
  end
end

"""

REMATCH_RUNTIME = SCRIPT_HELPERS + r"""
-- Gym leaders: the leader's own talk script becomes a small wrapper. After
-- the Elite Four (and once this leader is beaten) it offers the rematch, as
-- Crystal Legacy does; otherwise, or on NO, it runs the vanilla script.
local function leaderRematch(mod, L, stats)
  local map = mod.content.maps:get(L.map)
  local key
  for _, obj in ipairs(map and map.objects or {}) do
    if obj.sprite == L.sprite and obj.scriptKey then key = obj.scriptKey break end
  end
  local vanilla = key and mod.content.map_scripts:get(key)
  if not vanilla then
    mod.log:warn("%s: %s's script not found; rematch skipped", L.map, L.class)
    stats.failed = stats.failed + 1
    return
  end
  local class, member = appendParty(mod, L.class, L.party, stats)
  if not class then return end
  local base = "crystal_legacy_rematches:" .. L.class
  addText(mod, base .. ":ask", L.ask, stats)
  addText(mod, base .. ":beaten", L.beaten, stats)
  setScript(mod, "register", base .. ":vanilla", copy(vanilla), stats)
  setScript(mod, "register", base .. ":battle", {
    { op = "special", id = DATA.healParty },
    { op = "winlosstext", winText = base .. ":beaten" },
    { op = "loadtrainer", class = class, member = member },
    { op = "startbattle" },
    { op = "reloadmapafterbattle" },
    { op = "end" },
  }, stats)
  setScript(mod, "override", key, {
    { op = "checkevent", event = DATA.beatEliteFour },
    { op = "iffalse", script = base .. ":vanilla" },
    { op = "checkevent", event = L.beatEvent },
    { op = "iffalse", script = base .. ":vanilla" },
    { op = "faceplayer" },
    { op = "opentext" },
    { op = "writetext", text = base .. ":ask" },
    { op = "yesorno" },
    { op = "iftrue", script = base .. ":battle" },
    { op = "closetext" },
    { op = "sjump", script = base .. ":vanilla" },
  }, stats)
  return member
end

-- Elite Four and Lance: with all 16 badges, the same battle script uses the
-- rematch text and team (Crystal Legacy's `readvar VAR_BADGES` branch).
-- Their scripts are found by the vanilla `loadtrainer CLASS, 1` row, in every
-- script list that contains it.
local function eliteRematch(mod, E, stats)
  local class, member = appendParty(mod, E.class, E.party, stats)
  if not class then return end
  local base = "crystal_legacy_rematches:" .. E.class
  addText(mod, base .. ":intro", E.intro, stats)
  local found = {}
  for key, rows in mod.content.map_scripts:each() do
    if type(rows) == "table" then
      for i, row in ipairs(rows) do
        if type(row) == "table" and row.op == "loadtrainer"
            and row.class == class and row.member == 1 then
          found[#found + 1] = { key = key, rows = rows, at = i }
          break
        end
      end
    end
  end
  if #found == 0 then
    mod.log:warn("no vanilla %s battle script found; rematch skipped", E.class)
    stats.failed = stats.failed + 1
    return
  end
  for n, f in ipairs(found) do
    local rows, at = copy(f.rows), f.at
    -- 16 badges: a tail that loads the rematch team instead.
    local teamTail = slice(rows, at)
    teamTail[1].member = member
    local teamKey = ("%s:team%d"):format(base, n)
    setScript(mod, "register", teamKey, teamTail, stats)
    table.insert(rows, at, { op = "ifgreater", value = 15, script = teamKey })
    table.insert(rows, at, { op = "readvar", var = DATA.varBadges })
    -- ...and the intro line before it, if this list shows one.
    local textAt
    for i = at - 1, 1, -1 do
      if rows[i].op == "writetext" then textAt = i break end
    end
    if textAt then
      local textTail = slice(rows, textAt)
      textTail[1].text = base .. ":intro"
      local textKey = ("%s:intro%d"):format(base, n)
      setScript(mod, "register", textKey, textTail, stats)
      table.insert(rows, textAt, { op = "ifgreater", value = 15, script = textKey })
      table.insert(rows, textAt, { op = "readvar", var = DATA.varBadges })
    end
    setScript(mod, "override", f.key, rows, stats)
  end
  return member
end
"""


SCALING_RUNTIME = SCRIPT_HELPERS + r"""
-- Pryce, Jasmine and Chuck can be fought in any order in Crystal Legacy, so
-- each brings a team for the badge count you arrive with. Every vanilla script
-- list that loads their first team gets Legacy's `readvar VAR_BADGES /
-- ifequal` switch in front of that row.
local function scaleLeader(mod, S, stats)
  local rec = mod.content.trainers:get(S.class)
  if not rec then return end
  local members = {}
  for _, tier in ipairs(S.tiers) do
    local _, member = appendParty(mod, S.class, tier.party, stats)
    if not member then return end
    members[#members + 1] = { badges = tier.badges, member = member }
  end
  -- Collect first: overriding while iterating the registry is not safe.
  local found = {}
  for key, rows in mod.content.map_scripts:each() do
    for i, row in ipairs(type(rows) == "table" and rows or {}) do
      if type(row) == "table" and row.op == "loadtrainer"
          and row.class == rec.index and row.member == 1 then
        found[#found + 1] = { key = key, rows = rows, at = i }
        break
      end
    end
  end
  local hits = 0
  for _, f in ipairs(found) do
    local key, rows, at = f.key, f.rows, f.at
    do
      hits = hits + 1
      local new = copy(rows)
      local inserts = { { op = "readvar", var = DATA.varBadges } }
      for n, m in ipairs(members) do
        local tail = slice(new, at)
        tail[1].member = m.member
        local tailKey = ("crystal_legacy_trainers:%s:%d:%d"):format(S.class, hits, n)
        setScript(mod, "register", tailKey, tail, stats)
        inserts[#inserts + 1] = { op = "ifequal", value = m.badges, script = tailKey }
      end
      for i = #inserts, 1, -1 do table.insert(new, at, inserts[i]) end
      setScript(mod, "override", key, new, stats)
    end
  end
  if hits == 0 then
    mod.log:warn("no vanilla %s battle script found; team scaling skipped", S.class)
    stats.failed = stats.failed + 1
  end
end
"""


def _legacy_map_constants(leg):
    out = {}
    for op, args in statements(os.path.join(leg, "data/maps/attributes.asm")):
        if op == "map_attributes" and len(args) >= 2:
            out[args[0]] = args[1]
    return out


def _script_blocks(path):
    """[(label, [(op, args)])] including local labels, in file order."""
    blocks, cur = [], None
    for op, args in statements(path):
        if op == "label":
            cur = (args, [])
            blocks.append(cur)
        elif cur is not None:
            cur[1].append((op, args))
    return blocks


def rematch_specs(ctx, base, leg):
    texts_cache, maps = {}, _legacy_map_constants(leg)
    rows_all, extras_all = ctx["trainersAll"], ctx["extrasAll"]
    vanilla_counts = {c: len(v["parties"]) for c, v in D.parse.trainer_parties(base).items()}
    events = const_values(os.path.join(base, "constants/event_flags.asm"))

    def texts(f):
        if f not in texts_cache:
            texts_cache[f] = textc.text_blocks(os.path.join(leg, "maps", f + ".asm"))
        return texts_cache[f]

    def party_for(cls, legacy_index):
        row = next(r for r in rows_all[cls] if r["index"] == legacy_index)
        new = {k: v for k, v in row.items() if k != "index"}
        new["id"] = "%s_REMATCH" % cls
        ext = extras_all.get(cls, {}).get(legacy_index)
        return new, ext

    leaders, elites, extras = [], [], {}
    gyms = {"FALKNER": "VioletGym", "BUGSY": "AzaleaGym", "WHITNEY": "GoldenrodGym",
            "MORTY": "EcruteakGym", "PRYCE": "MahoganyGym", "JASMINE": "OlivineGym",
            "CHUCK": "CianwoodGym", "CLAIR": "BlackthornGym1F"}
    for cls, f in gyms.items():
        blocks = _script_blocks(os.path.join(leg, "maps", f + ".asm"))
        label = ".%sRematch" % cls.capitalize()
        body = dict(blocks)[label]
        beaten = next(a[0] for op, a in body if op == "winlosstext")
        idx = next(int(a[1]) for op, a in body if op == "loadtrainer" and a[0] == cls)
        ask = None
        for _, ops in blocks:
            for i, (op, a) in enumerate(ops):
                if op == "iftrue" and a and a[0] == label:
                    ask = next(x[1][0] for x in reversed(ops[:i]) if x[0] == "writetext")
        party, ext = party_for(cls, idx)
        if ext:
            extras.setdefault(cls, {})[party["id"]] = ext
        leaders.append({"class": cls, "map": maps[f], "sprite": "SPRITE_" + cls,
                        "beatEvent": events["EVENT_BEAT_" + cls],
                        "ask": texts(f)[ask], "beaten": texts(f)[beaten], "party": party})
    rooms = {"WILL": "WillsRoom", "KOGA": "KogasRoom", "BRUNO": "BrunosRoom",
             "KAREN": "KarensRoom", "CHAMPION": "LancesRoom"}
    for cls, f in rooms.items():
        ops = [x for _, b in _script_blocks(os.path.join(leg, "maps", f + ".asm")) for x in b]
        intro = None
        for i, (op, a) in enumerate(ops):
            if op == "if_less_than" and a[0] == "16" and ops[i + 1][0] == "writetext":
                intro = ops[i + 1][1][0]
                break
        party, ext = party_for(cls, 2)
        if ext:
            extras.setdefault(cls, {})[party["id"]] = ext
        elites.append({"class": cls, "intro": texts(f)[intro], "party": party})
    specials = [a[0] for op, a in statements(os.path.join(base, "data/events/special_pointers.asm"))
                if op == "add_special"]
    return {"leaders": leaders, "elites": elites, "extras": extras,
            "healParty": specials.index("HealParty"),
            "beatEliteFour": events["EVENT_BEAT_ELITE_FOUR"], "varBadges": 7}


def build_rematches(ctx):
    data = rematch_specs(ctx, ctx["base"], ctx["legacy"])
    body = """
  for _, L in ipairs(DATA.leaders) do leaderRematch(mod, L, stats) end
  for _, E in ipairs(DATA.elites) do eliteRematch(mod, E, stats) end
  -- Custom DVs / stat exp on the rematch teams, keyed by member id.
  if next(DATA.extras) then
    mod.hooks:wrap("trainer.party", function(nextFn, class, member, party)
      party = nextFn(class, member, party)
      local slots = DATA.extras[class] and DATA.extras[class][member]
      if slots and type(party) == "table" then
        for slot, extra in pairs(slots) do
          local mon = party[slot]
          if mon then
            if extra.dvs then mon.dvs = extra.dvs end
            if extra.statExp then mon.statExp = extra.statExp end
            if extra.happiness then mon.happiness = extra.happiness end
          end
        end
      end
      return party
    end)
  end"""
    return data, body, [
        "Gym leader rematches after the Elite Four: %s" % ", ".join(
            l["class"].capitalize() for l in data["leaders"]),
        "Elite Four and Lance rematch teams once you have all 16 badges",
        "Crystal Legacy's rematch dialogue and teams (levels 53-69)",
        "Red's rematch is part of Story Changes (it follows Crystal Legacy's Mewtwo event)"]


# -------------------------------------------------------------- quality of life
def _db_order(path):
    out = []
    for op, a in statements(path):
        if op == "db" and a and a[0] not in ("NO_ITEM", "-1"):
            out.extend(x for x in a if x)
    return out


def build_qol(ctx):
    leg = ctx["legacy"]
    std = textc.text_blocks(os.path.join(leg, "data/text/std_text.asm"))
    common = textc.text_blocks(os.path.join(leg, "data/text/common_1.asm"))
    # gfx/sprites/{chris,kris}_run.png: Legacy's PLAYER_RUN sheets
    # (data/sprites/player_sprites.asm), converted like Story Changes' sprites.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "story"))
    import sprites as SP
    from PIL import Image
    asset_dir = os.path.join(ROOT, "mods", "crystal_legacy_qol", "assets", "sprites")
    os.makedirs(asset_dir, exist_ok=True)
    run_sprites = []
    for name, src, pal in (("SPRITE_CHRIS_RUN", "chris_run.png", "PAL_OW_RED"),
                           ("SPRITE_KRIS_RUN", "kris_run.png", "PAL_OW_BLUE")):
        path = os.path.join(leg, "gfx", "sprites", src)
        SP.convert(path, os.path.join(asset_dir, src))
        run_sprites.append({"id": name, "image": "assets/sprites/" + src,
                            "frames": Image.open(path).size[1] // 16, "walker": True,
                            "spriteType": "WALKING_SPRITE", "palette": pal,
                            "paletteId": SP.PALETTE_IDS.get(pal, 0),
                            "source": "Crystal Legacy"})
    data = {
        "runSprites": run_sprites,
        # engine/events/std_scripts.asm PokecenterNurseScript, Legacy's short visit
        "nurseScript": "2f:409c",
        "text": {"take": std["NurseTakePokemonText"],
                 "returned": std["NurseReturnPokemonShortText"],
                 "repel": common["_UseAnotherRepelText"]},
        # data/items/sorting_order.asm (ItemNameOrder): START in the PACK
        "sortOrder": _db_order(os.path.join(leg, "data/items/sorting_order.asm")),
    }
    body = '''
  qolOptions(mod)
  qolRunning(mod)
  qolRunSprite(mod, stats)
  qolRepel(mod)
  qolPackSort(mod)
  qolNurse(mod, stats)
  qolDayCare(mod)'''
    lines = [
        "Hold B to run (walking at bike speed), and to surf faster. The player wears "
        "Crystal Legacy's running sprite while running",
        "When a Repel wears off and you have another of the same kind, you're asked "
        "\"Use another?\"",
        "START in the PACK sorts your items into Crystal Legacy's order",
        "After your first visit, the Pokémon Center nurse skips her speech and heals "
        "straight away",
        "The Day-Care keeps the experience your Pokémon earned (vanilla throws away "
        "everything past its current level's minimum)",
        "Each change can be switched off in the mod's options",
    ]
    return data, body, lines


QOL_RUNTIME = r"""
local QOL_OPTIONS = {
  { key = "running", label = "RUN WITH B", type = "toggle", default = true },
  { key = "repel", label = "REUSE REPEL PROMPT", type = "toggle", default = true },
  { key = "packSort", label = "START SORTS PACK", type = "toggle", default = true },
  { key = "nurse", label = "QUICK NURSE", type = "toggle", default = true },
  { key = "dayCareExp", label = "DAY-CARE KEEPS EXP", type = "toggle", default = true },
}
local OPT

local function qolOptions(mod)
  mod.options:define(QOL_OPTIONS)
  OPT = function(key)
    local v = mod.options:get(key)
    if v == nil then return true end
    return v
  end
end

local function engine(mod, name, what)
  local ok, m = pcall(require, name)
  if ok and type(m) == "table" then return m end
  mod.log:warn("%s not found; %s disabled", name, what)
  return nil
end

-- engine/overworld/player_movement.asm .HandleWalkAndRun / .FastSurfCheck:
-- B held on foot or on water takes the bike's step (half the frames).
local function qolRunning(mod)
  mod.hooks:wrap("movement.speed", function(nextFn, frames, ctx)
    frames = nextFn(frames, ctx)
    if not OPT("running") or type(ctx) ~= "table" or ctx.onBike then return frames end
    local input = ctx.input
    if input and input.isDown and input:isDown("b") then
      return math.max(1, math.floor((tonumber(frames) or 16) / 2))
    end
    return frames
  end)
end

-- data/sprites/player_sprites.asm: Legacy's PLAYER_RUN row. Only the sheet
-- is swapped, never wPlayerState, so everything that checks for the walking
-- state (bike, Surf, fishing) still sees it.
local RUN_SPRITE = { male = "SPRITE_CHRIS_RUN", female = "SPRITE_KRIS_RUN" }

local function qolRunSprite(mod, stats)
  for _, rec in ipairs(DATA.runSprites) do
    local r = {}
    for k, v in pairs(rec) do r[k] = v end
    r.image = mod.path .. "/" .. rec.image
    local ok, err = pcall(mod.content.sprites.register, mod.content.sprites, rec.id, r)
    if ok then stats.applied = stats.applied + 1 else
      stats.failed = stats.failed + 1
      mod.log:warn("sprite %s: %s", rec.id, tostring(err))
    end
  end
  local World = engine(mod, "src.world.gen2.World", "the running sprite")
  local FieldMoves = engine(mod, "src.world.gen2.FieldMoves", "the running sprite")
  if not (World and World.stepBody and World.applyPlayerState and FieldMoves) then return end
  local function tick(self)
    local p = self.player
    if p then
      local input = self.game and self.game.input
      local want = OPT("running") and p.moving
        and self.playerState == FieldMoves.PLAYER_NORMAL
        and input and input.isDown and input:isDown("b") or false
      local wearing = self.__qolRunning == p
      if want and not wearing then
        local gender = self.playerGender and self:playerGender()
        local def = self.sprites
          and self.sprites[RUN_SPRITE[FieldMoves.isFemale(gender) and "female" or "male"]]
        if def then
          p:setSprite(def)
          if self.applySpritePalette then self:applySpritePalette(p) end
          self.__qolRunning = p
        end
      elseif not want and wearing then
        self.__qolRunning = nil
        -- Back to whatever the current state wears (walking, bike, Surf).
        self:applyPlayerState(self.playerState)
      end
    end
  end
  mod.exports.runSpriteTick = tick
  local stepBody = World.stepBody
  World.stepBody = function(self, ...)
    local results = { stepBody(self, ...) }
    tick(self)
    return unpack(results)
  end
end

-- engine/overworld/events.asm DoRepelStep + engine/events/repel.asm
-- UseAnotherRepelScript: if the bag still holds the kind just used, ask.
local function qolRepel(mod)
  local World = engine(mod, "src.world.gen2.World", "the Repel prompt")
  if not (World and World.useRepel and World.repelWoreOff) then return end
  local useRepel, woreOff = World.useRepel, World.repelWoreOff
  World.useRepel = function(self, itemId, ...)
    local result = useRepel(self, itemId, ...)
    if result == "repel_used" then mod.save:set("repelType", itemId) end
    return result
  end
  World.repelWoreOff = function(self, ...)
    local save = self.game and self.game.save
    local kind = mod.save:get("repelType", nil)
    local have = save and save.inventory and kind and (save.inventory[kind] or 0) > 0
    if not (OPT("repel") and have and self.askYesNo) then return woreOff(self, ...) end
    local items = self.game.data and self.game.data.items
    local name = (items and items[kind] and items[kind].name) or kind
    local text = DATA.text.repel:gsub("{STRBUF}", function() return name end)
    self:showText(text, function()
      self:askYesNo(function(yes)
        if not yes then return end
        -- RepelEffect / UseRepel, run straight from the field: the counter is
        -- zero by now, so this is a fresh Repel.
        local r = useRepel(self, kind)
        if r ~= "repel_used" then
          -- World:useRepel refuses while a box is up; apply it the same way.
          save.repelSteps = ({ REPEL = 100, SUPER_REPEL = 200, MAX_REPEL = 250 })[kind] or 100
          local left = (save.inventory[kind] or 1) - 1
          save.inventory[kind] = left > 0 and left or nil
        end
      end)
    end, true)
  end
end

-- engine/items/switch_items.asm SortItemsInBag: START puts the bag in
-- ItemNameOrder (each pocket sorts within itself, since a pocket is a view
-- of the one list).
local function sortBag(save)
  local order = save and save.bagOrder
  if type(order) ~= "table" then return false end
  local rank = {}
  for i, id in ipairs(DATA.sortOrder) do rank[id] = rank[id] or i end
  local pos = {}
  for i, id in ipairs(order) do pos[id] = i end
  table.sort(order, function(a, b)
    local ra, rb = rank[a] or math.huge, rank[b] or math.huge
    if ra ~= rb then return ra < rb end
    return pos[a] < pos[b]
  end)
  return true
end

local function qolPackSort(mod)
  local PackMenu = engine(mod, "src.ui.gen2.PackMenu", "Pack sorting")
  if not (PackMenu and PackMenu.update) then return end
  local update = PackMenu.update
  PackMenu.update = function(self, dt, ...)
    local input = self.game and self.game.input
    if OPT("packSort") and input and input.wasPressed and input:wasPressed("start")
        and not (self.qtyState or self.switching or self.message or self.confirm
                 or self.submenu) then
      if self.save and self.save.inventory then
        local Bag = require("src.inventory.Bag")
        Bag.order(self.save, self.bagData)
        if sortBag(self.save) then
          self:rebuild()
          if self.playSfxTwice then self:playSfxTwice("Sfx_SwitchPokemon") end
        end
      end
      return
    end
    return update(self, dt, ...)
  end
end

-- PokecenterNurseScript, Crystal Legacy's way: the full welcome once, then
-- "OK, may I see your POKéMON?", the heal, and a one-line goodbye.
local function qolNurse(mod, stats)
  local key = DATA.nurseScript
  local scripts = mod.content.map_scripts
  local root = scripts:get(key)
  if not root then
    mod.log:info("nurse script %s not in this dataset; quick nurse skipped", key)
    return
  end
  local healKey
  for _, row in ipairs(root or {}) do
    if row.op == "sjump" then healKey = row.script end
  end
  local heal = healKey and scripts:get(healKey)
  -- The yes branch, from the first pause to the turn back to the player.
  local from, to
  for i, row in ipairs(heal or {}) do
    if not from and row.op == "pause" then from = i end
    if from and row.op == "checkphonecall" then to = i - 1 break end
  end
  if not (root and from and to) then
    mod.log:warn("nurse script %s not in the expected shape; quick nurse skipped", key)
    stats.failed = stats.failed + 1
    return
  end
  local NS = "crystal_legacy_qol:nurse"
  local function reg(kind, id, value)
    local ok, err = pcall(mod.content[kind].register, mod.content[kind], id, value)
    if ok then stats.applied = stats.applied + 1 else
      stats.failed = stats.failed + 1
      mod.log:warn("%s %s: %s", kind, id, tostring(err))
    end
  end
  reg("text", NS .. ":take", DATA.text.take)
  reg("text", NS .. ":returned", DATA.text.returned)
  local copy = function(t)
    local out = {}
    for k, v in pairs(t) do out[k] = v end
    return out
  end
  local full = {}
  for i, row in ipairs(root) do full[i] = copy(row) end
  reg("map_scripts", NS .. ":full", full)
  reg("map_scripts", NS .. ":bye", {
    { op = "opentext" }, { op = "writetext", text = NS .. ":returned" },
    { op = "pause", frames = 40 }, { op = "closetext" }, { op = "end" },
  })
  local quick = {
    { op = "opentext" }, { op = "writetext", text = NS .. ":take" },
    { op = "pause", frames = 40 }, { op = "closetext" },
  }
  for i = from, to do quick[#quick + 1] = copy(heal[i]) end
  -- The Pokerus check vanilla runs after healing (and its phone-call guards).
  for i = to + 1, #heal do
    local row = copy(heal[i])
    if row.op == "farwritetext" or row.op == "writetext" then
      quick[#quick + 1] = { op = "sjump", script = NS .. ":bye" }
      break
    end
    if row.op == "iftrue" and row.script ~= nil and heal[i - 1]
        and heal[i - 1].op ~= "special" then
      row.script = NS .. ":bye"
    end
    quick[#quick + 1] = row
  end
  reg("map_scripts", NS .. ":quick", quick)
  mod.content.commands:register(NS .. ":visit", function()
    if OPT("nurse") and mod.save:get("nurseWelcomed", false) then return 3 end
    mod.save:set("nurseWelcomed", true)
    return nil
  end)
  local ok, err = pcall(scripts.override, scripts, key, {
    { op = "modcommand", verb = NS .. ":visit" },
    { op = "sjump", script = NS .. ":full" },
    { op = "sjump", script = NS .. ":quick" },
  })
  if ok then stats.applied = stats.applied + 1 else
    stats.failed = stats.failed + 1
    mod.log:warn("nurse script: %s", tostring(err))
  end
end

-- engine/pokemon/move_mon.asm RetrieveBreedmon: Legacy keeps the stored exp
-- (capped at level 100's) instead of resetting it to the new level's minimum.
local function qolDayCare(mod)
  local Breeding = engine(mod, "src.core.gen2.Breeding", "Day-Care exp")
  if not (Breeding and Breeding.withdraw and Breeding.side) then return end
  local withdraw = Breeding.withdraw
  Breeding.withdraw = function(data, save, which, ...)
    local slot = Breeding.side(save, which)
    local earned = slot and slot.mon and slot.mon.experience
    local ok, mon, price = withdraw(data, save, which, ...)
    if ok and OPT("dayCareExp") and type(mon) == "table" and type(earned) == "number"
        and earned > (mon.experience or 0) then
      local Mon = require("src.battle.gen2.Mon")
      local def = data and data.pokemon and data.pokemon[mon.species]
      local growth = Mon.growthFor(data, def and def.growthRate)
      mon.experience = math.min(earned, Mon.experienceForLevel(growth, Mon.MAX_LEVEL))
    end
    return ok, mon, price
  end
end
"""


# ------------------------------------------------------------------ bug fixes
def build_fixes(ctx):
    body = '''
  mod.options:define({
    { key = "magikarpSizes", label = "MAGIKARP SIZES", type = "toggle", default = true },
  })
  OPT = function(key)
    local v = mod.options:get(key)
    if v == nil then return true end
    return v
  end
  fixCatching(mod)
  fixAi(mod)
  fixMagikarp(mod)
  fixMagikarpWild(mod)'''
    lines = [
        "Poké Balls: burned, poisoned and paralysed Pokémon are easier to catch (vanilla "
        "only counted sleep and freeze)",
        "Fast Ball works on every Pokémon that tends to run, Moon Ball on Moon Stone "
        "evolvers, and Love Ball on the opposite gender",
        "The catch formula's high-HP rounding quirk is kept, as in Crystal Legacy",
        "Trainer AI: Mean Look is favoured when *your* Pokémon is badly poisoned (vanilla "
        "checked its own)",
        "Trainer AI: Full Heal and Full Restore also end Nightmare",
        "Magikarp lengths (Lake of Rage contest) are worked out on the full number, as "
        "intended; vanilla compared only half of it",
        "Wild Magikarp sizes follow Crystal Legacy's rules: Magikarp over 5'3\" are rare, "
        "and Lake of Rage's are usually 3' or longer (gen1recomp had no size filter at "
        "all). Toggle: MAGIKARP SIZES",
        "Light Ball and Thick Club can't push Attack past 999",
        "Hurting itself in confusion ignores held type-boosting items (vanilla boosted "
        "the hit when the chosen move's type matched the item)",
        "The Glacier Badge always boosts Special Defense as well as Special Attack "
        "(vanilla's check depended on the boosted Special Attack's value)",
        "Already correct in gen1recomp, so nothing to change: Counter / Mirror Coat after a "
        "non-damaging turn, PP Ups in the 'has PP' check, a Transformed Pokémon caught "
        "as Ditto, and Full Heal leaving the AI confused",
    ]
    return {}, body, lines


FIXES_RUNTIME = r"""
local OPT = function() return true end

local function engine(mod, name, what)
  local ok, m = pcall(require, name)
  if ok and type(m) == "table" then return m end
  mod.log:warn("%s not found; %s left as vanilla", name, what)
end

-- A view of a table with a few keys replaced, leaving the original alone.
local function with(t, over)
  return setmetatable(over, { __index = t })
end

-- engine/items/item_effects.asm PokeBallEffect, as Crystal Legacy fixes it.
-- gen1recomp keeps the cart's bugs and can flip them with `fixBugs`; that
-- flag also fixes the high-HP rounding, which Legacy keeps, so it is passed
-- only to the status bonus and the ball multipliers.
local function fixCatching(mod)
  local Catching = engine(mod, "src.battle.gen2.Catching", "catching")
  if not (Catching and Catching.statusBonus and Catching.recordFor) then return end
  local statusBonus, recordFor = Catching.statusBonus, Catching.recordFor
  Catching.statusBonus = function(status, opts, ...)
    return statusBonus(status, with(opts or {}, { fixBugs = true }), ...)
  end
  local fixed = setmetatable({}, { __mode = "k" })
  Catching.recordFor = function(ball, opts, ...)
    local record = recordFor(ball, opts, ...)
    if type(record) ~= "table" or type(record.specialty) ~= "function" then return record end
    local out = fixed[record]
    if not out then
      local specialty = record.specialty
      out = with(record, { specialty = function(rate, o, ...)
        return specialty(rate, with(o or {}, { fixBugs = true }), ...)
      end })
      fixed[record] = out
    end
    return out
  end
end

-- engine/events/magikarp.asm CalcMagikarpLength: Legacy fixes .BCLessThanDE
-- (it compared only the high bytes, `ret c / ret nc`), so the length table is
-- walked on the full 16-bit value. Same transcription as gen1recomp's
-- Specials.magikarpLength otherwise.
local function rrc(x) return math.floor(x / 2) + (x % 2) * 128 end
local function xorByte(a, b)
  local out, bit = 0, 1
  for _ = 1, 8 do
    if (a % 2) ~= (b % 2) then out = out + bit end
    a, b, bit = math.floor(a / 2), math.floor(b / 2), bit * 2
  end
  return out
end

local function fixMagikarp(mod)
  local Specials = engine(mod, "src.script.gen2.Specials", "Magikarp lengths")
  if not (Specials and Specials.magikarpLength and Specials.MAGIKARP_LENGTHS) then return end
  Specials.magikarpLength = function(otId, dvWord)
    otId = (otId or 0) % 65536
    dvWord = (dvWord or 0) % 65536
    local b = xorByte(rrc(math.floor(otId / 256)), rrc(rrc(math.floor(dvWord / 256))))
    local c = xorByte(rrc(otId % 256), rrc(rrc(dvWord % 256)))
    local bc = b * 256 + c
    local mm
    if b == 0 and c < 10 then
      mm = bc + 190
    else
      local index, de = 2, 0
      for _, row in ipairs(Specials.MAGIKARP_LENGTHS) do
        de = row[1]
        if bc < de then
          mm = 100 * index + (math.floor(((bc - de) % 65536) / row[2]) % 256)
          break
        end
        index = index + 1
      end
      if not mm then mm = ((bc - de) % 65536) + 1600 end
    end
    mm = mm % 65536
    local inches = math.floor(mm * 10 / 254) % 256
    return math.floor(inches / 12), inches % 12, mm
  end
end

-- engine/battle/core.asm LoadEnemyMon .Magikarp, as Crystal Legacy fixes it
-- (vanilla compared feet/inches against millimetre constants and inverted the
-- Lake of Rage test). gen1recomp has no such filter at all, so this adds it:
-- a wild Magikarp's DVs are re-rolled until its length passes. `byte` is
-- Random (0-255); `percent` thresholds are the cart's own (`5 percent` = 12).
local function magikarpFilter(Specials, otId, atLake, randomDVs, byte)
  for _ = 1, 512 do
    local dvs = randomDVs()
    local feet, inches = Specials.magikarpLength(otId, Specials.dvWord(dvs))
    local reroll = false
    if feet == 5 then
      if byte() < 12 then -- 5%: skip both size checks
      elseif inches >= 4 then reroll = true -- 5'4" and up
      elseif byte() < 50 then -- 20% - 1: skip the next check
      elseif inches >= 3 then reroll = true -- 5'3"
      end
    end
    -- Lake of Rage: 61% of the time, nothing under 3'0"
    if not reroll and atLake and byte() >= 100 and feet < 3 then reroll = true end
    if not reroll then return dvs end
  end
  return randomDVs()
end

local function fixMagikarpWild(mod)
  local Mon = engine(mod, "src.battle.gen2.Mon", "wild Magikarp sizes")
  local Specials = engine(mod, "src.script.gen2.Specials", "wild Magikarp sizes")
  if not (Mon and Mon.new and Mon.randomDVs and Specials and Specials.magikarpLength
          and Specials.dvWord) then return end
  local function byte()
    if love and love.math and love.math.random then return love.math.random(0, 255) end
    return math.random(0, 255)
  end
  mod.exports.magikarpFilter = function(otId, atLake, randomDVs, rng)
    return magikarpFilter(Specials, otId, atLake, randomDVs or Mon.randomDVs, rng or byte)
  end
  local new = Mon.new
  Mon.new = function(data, species, level, opts, ...)
    if species == "MAGIKARP" and type(opts) == "table" and opts.wild and opts.dvs == nil
        and OPT("magikarpSizes") then
      local game = mod.game
      local save = game and game.save
      local world = game and game.world
      if save and save.player and save.player.id == nil and Mon.stampOT then
        Mon.stampOT(save, {}) -- gives the player their trainer ID, as a catch would
      end
      local otId = save and save.player and save.player.id or 0
      local atLake = world and world.map and world.map.id == "LAKE_OF_RAGE" or false
      local o = {}
      for k, v in pairs(opts) do o[k] = v end
      o.dvs = magikarpFilter(Specials, otId, atLake, Mon.randomDVs, byte)
      opts = o
    end
    return new(data, species, level, opts, ...)
  end
end

local function fixAi(mod)
  -- engine/battle/ai/scoring.asm AI_Smart_MeanLook: test the PLAYER's toxic.
  local Ai = engine(mod, "src.battle.gen2.Ai", "AI scoring")
  local smart = Ai and Ai.SMART
  if smart and type(smart.EFFECT_MEAN_LOOK) == "function" then
    local meanLook = smart.EFFECT_MEAN_LOOK
    smart.EFFECT_MEAN_LOOK = function(ctx, st, ...)
      return meanLook(ctx, with(st or {}, { enemyToxic = (st and st.playerToxic) or false }), ...)
    end
  end
  -- engine/battle/ai/items.asm AI_HealStatus: also clear SUBSTATUS_NIGHTMARE.
  local Battle = engine(mod, "src.battle.gen2.Battle", "AI items")
  -- engine/battle/effect_commands.asm HitConfusion: Legacy's
  -- ConfusionDamageCalc leaves held items out; vanilla's DamageCalc boosted
  -- the self-hit when the chosen move's type matched a held type booster.
  if Battle and Battle.confusionSelfHit and Battle.heldEffect then
    local selfHit = Battle.confusionSelfHit
    Battle.confusionSelfHit = function(self, mon, ...)
      local own = rawget(self, "heldEffect")
      local held = own or Battle.heldEffect
      self.heldEffect = function(s, m, kind, ...)
        if m == mon and kind == "damage" then return nil end
        return held(s, m, kind, ...)
      end
      local results = { pcall(selfHit, self, mon, ...) }
      self.heldEffect = own
      if not results[1] then error(results[2], 0) end
      return unpack(results, 2)
    end
  end
  -- engine/battle/effect_commands.asm SpeciesItemBoost: Legacy caps the
  -- Light Ball / Thick Club doubling at MAX_STAT_VALUE before the stats are
  -- truncated; vanilla let it run past 999.
  local Damage = engine(mod, "src.battle.gen2.Damage", "the Light Ball cap")
  if Damage and Damage.calc and Damage.truncateStats then
    local calc, truncate = Damage.calc, Damage.truncateStats
    local capNext = false
    Damage.calc = function(opts, ...)
      local outer = capNext
      capNext = type(opts) == "table" and opts.attackDoubled == true
      local results = { pcall(calc, opts, ...) }
      capNext = outer
      if not results[1] then error(results[2], 0) end
      return unpack(results, 2)
    end
    Damage.truncateStats = function(attack, defense, ...)
      if capNext and type(attack) == "number" then
        attack = math.min(Damage.MAX_STAT_VALUE or 999, attack)
        capNext = false
      end
      return truncate(attack, defense, ...)
    end
  end
  -- engine/battle/core.asm BadgeStatBoosts: Legacy's push/pop af keeps the
  -- badge bits, so the Glacier Badge always boosts Special Defense too.
  if Battle and Battle.glacierBoostsSpDef then
    Battle.glacierBoostsSpDef = function() return true end
  end
  if Battle and Battle.enemyUseItem then
    local enemyUseItem = Battle.enemyUseItem
    Battle.enemyUseItem = function(self, item, ...)
      local used = enemyUseItem(self, item, ...)
      if used and (item == "FULL_HEAL" or item == "FULL_RESTORE") and self.volatile then
        local v = self:volatile(self.enemy)
        if v then v.nightmare = nil end
      end
      return used
    end
  end
end
"""


# ----------------------------------------------------------------- menu icons
def build_icons(ctx):
    """Data only: which icon file and palette each species uses, and the
    palettes' colours. The icon images themselves are never copied into the
    mod; players drop Crystal Legacy's gfx/icons folder in themselves."""
    import re
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "story"))
    import sprites as SP
    from asm import species_order
    leg, base = ctx["legacy"], ctx["base"]
    files = {sp: os.path.basename(path) for sp, path in SP._species_icon_files(leg).items()}
    order = species_order(base)
    pals = []
    for line in open(os.path.join(leg, "data/pokemon/menu_icon_pals.asm"), encoding="utf-8"):
        m = re.match(r"\s*icon_pals\s+(\w+),\s*(\w+)", line)
        if m:
            pals.append((m.group(1), m.group(2)))
    colours = {}
    names = ["RED", "BLUE", "GREEN", "BROWN", "PINK", "GRAY", "TEAL", "PURPLE"]
    rows = [l for l in open(os.path.join(leg, "gfx/stats/party_menu_ob.pal"), encoding="utf-8")
            if l.strip().startswith("RGB")]
    for name, row in zip(names, rows):
        nums = [int(n) for n in re.findall(r"\d+", row.split(";")[0])]
        # GBC RGB, 0-31 per channel (divided down at run time)
        colours[name] = [[nums[i + j] for j in range(3)] for i in range(0, 12, 3)]
    icons = {}
    for i, sp in enumerate(order):
        if sp in files and i < len(pals):
            icons[sp] = {"file": files[sp], "normal": pals[i][0], "shiny": pals[i][1]}
    data = {"icons": icons, "palettes": colours}
    body = '''
  legacyMenuIcons(mod)'''
    lines = [
        "Crystal Legacy's party menu icons: one icon per species, coloured with Legacy's "
        "per-species palette (and its shiny palette)",
        "**The icons are not included.** Copy Crystal Legacy's `gfx/icons` folder into "
        "this mod's folder as `icons/` (so `icons/bulbasaur.png` and so on). Species "
        "without a file keep gen1recomp's normal icon",
        "%d species mapped to Legacy's icon files and palettes" % len(icons),
        "With **Wilds of Kanto** installed, species without a Legacy icon use Wilds' "
        "front-facing follower sprite as their icon (classic Poké Followers / GSC "
        "style; other Sprite Styles keep the normal icon). Toggle: USE WILDS SPRITES",
    ]
    return data, body, lines


ICONS_RUNTIME = r"""
local function iconRgba(palette)
  -- GBC OBJ palette: colour 0 is transparent, then light, dark, black.
  local out = {}
  for i, c in ipairs(palette) do out[i] = { c[1] / 31, c[2] / 31, c[3] / 31, i == 1 and 0 or 1 } end
  return out
end

-- The four Game Boy shades, lightest first, by brightness.
local function shadeOf(r, g, b)
  local v = (r + g + b) / 3
  if v > 0.84 then return 1 elseif v > 0.5 then return 2 elseif v > 0.17 then return 3 end
  return 4
end

local function legacyMenuIcons(mod)
  mod.options:define({
    { key = "useWilds", label = "USE WILDS SPRITES", type = "toggle", default = true },
  })
  local okA, Assets = pcall(require, "src.render.Assets")
  if not (okA and Assets and Assets.compose) then
    mod.log:warn("asset module not found; Legacy menu icons disabled")
    return
  end
  -- The mod's own folder, through the sandbox's mod:info (love.filesystem
  -- is off limits to mods).
  local function present(file)
    local ok, info = pcall(mod.info, mod, "icons/" .. file)
    return ok and type(info) == "table" and info.type == "file"
  end
  local found, missing = 0, 0
  local registered = {}
  -- One composed image per species and palette, built from the player's own
  -- file the first time the party menu asks for it.
  local function composedPath(species, shiny)
    local rec = DATA.icons[species]
    if not rec then return nil end
    if not present(rec.file) then return nil end
    local src = mod.path .. "/icons/" .. rec.file
    local key = "legacy-icons/" .. species .. (shiny and "-shiny" or "") .. ".png"
    if not registered[key] then
      local colours = iconRgba(DATA.palettes[shiny and rec.shiny or rec.normal]
        or DATA.palettes.RED)
      Assets.compose(key, function()
        -- loaded by the engine's asset layer, outside the mod sandbox
        local img = Assets.imageData(src)
        img:mapPixel(function(_, _, r, g, b, a)
          if a == 0 then return 0, 0, 0, 0 end
          local c = colours[shadeOf(r, g, b)]
          return c[1], c[2], c[3], c[4]
        end)
        return img
      end)
      registered[key] = true
    end
    return key
  end
  mod.exports.composedPath = composedPath

  -- Fallback source: Wilds of Kanto (overworld_wild_spawns), when installed.
  -- Its resolveFollowerSprite picks the sheet for the player's chosen Sprite
  -- Style; a classic 16x16 walking sheet (idle_down, idle_up, idle_left,
  -- walk_down, ...) becomes a two-frame icon: idle_down over walk_down.
  local wildsResolver -- tests may set one through mod.exports
  local function wildsSheet(species, shiny)
    local resolve = wildsResolver
    if not resolve then
      local wilds = mod:find("overworld_wild_spawns")
      resolve = wilds and wilds.exports and wilds.exports.resolveFollowerSprite
    end
    if type(resolve) ~= "function" then return nil end
    local ok, def = pcall(resolve, { species = species, shiny = shiny == true,
      surface = "land", game = mod.game })
    if not ok or type(def) ~= "table" or def.fallback or type(def.image) ~= "string" then
      return nil
    end
    if (def.frameWidth or 16) ~= 16 or (def.frameHeight or 16) ~= 16 or (def.frames or 6) < 4 then
      return nil -- HGSS true-size, PMDCollab etc.: not icon-shaped
    end
    return def.image
  end
  local wildsCache_reset -- set below, once the cache exists
  mod.exports.setWildsResolver = function(fn)
    wildsResolver = fn
    if wildsCache_reset then wildsCache_reset() end
  end

  -- The party menu asks every frame; Wilds' answer is cached per species and
  -- shininess (a Sprite Style change in Wilds shows after a restart).
  local wildsCache = {}
  wildsCache_reset = function() wildsCache = {} end
  local function wildsIconPath(species, shiny)
    if mod.options:get("useWilds") == false then return nil end
    local ck = tostring(species) .. (shiny and ":shiny" or ":normal")
    if wildsCache[ck] ~= nil then return wildsCache[ck] or nil end
    local image = wildsSheet(species, shiny)
    if not image then wildsCache[ck] = false return nil end
    if not image then return nil end
    local key = "wilds-icons/" .. image
    if not registered[key] then
      Assets.compose(key, function()
        local src = Assets.imageData(image)
        local out = love.image.newImageData(16, 32)
        out:paste(src, 0, 0, 0, 0, 16, 16)   -- idle_down
        out:paste(src, 0, 16, 0, 48, 16, 16) -- walk_down
        return out
      end)
      registered[key] = true
    end
    wildsCache[ck] = key
    return key
  end
  mod.exports.wildsIconPath = wildsIconPath

  for species, rec in pairs(DATA.icons) do
    if present(rec.file) then found = found + 1 else missing = missing + 1 end
  end
  if found == 0 then
    mod.log:info("no icons in %s/icons yet; copy Crystal Legacy's gfx/icons folder there", mod.path)
  else
    mod.log:info("Legacy menu icons: %d species found, %d missing", found, missing)
  end

  mod.hooks:wrap("pokemon.icon", function(nextFn, path, ctx)
    path = nextFn(path, ctx)
    local mon = ctx and ctx.mon
    local species = (ctx and ctx.species) or (mon and mon.species)
    if not species or (mon and mon.isEgg) then return path end
    local key = composedPath(species, mon and mon.shiny)
      or wildsIconPath(species, mon and mon.shiny)
    if not key then return path end
    ctx.trueColor = true
    return key
  end)
end
"""


POKEMON_RT = r"""
local function copyT(v)
  if type(v) ~= "table" then return v end
  local out = {}
  for k, x in pairs(v) do out[k] = copyT(x) end
  return out
end

-- Item evolutions: the Legacy items take the evolution stones' effect, which
-- evolves whichever EVOLVE_ITEM row names the item used.
local function legacyEvolutionItems(mod, stats)
  local stone = mod.content.item_effects:get("MOON_STONE")
  if not stone then
    mod.log:warn("MOON_STONE effect not found; item evolutions stay unusable")
    stats.failed = stats.failed + 1
    return
  end
  for _, id in ipairs(DATA.evoItems) do
    if mod.content.items:get(id) then
      patch(mod, "items", id, { fieldMenu = "ITEMMENU_PARTY" }, stats)
      local reg = mod.content.item_effects
      local ok, err = pcall(reg:get(id) ~= nil and reg.override or reg.register, reg, id, copyT(stone))
      if ok then stats.applied = stats.applied + 1 else
        stats.failed = stats.failed + 1
        mod.log:warn("item effect %s: %s", id, tostring(err))
      end
    end
  end
end

-- Tables gen1recomp keeps in its engine modules rather than in a registry.
local function legacyEngineTables(mod, stats)
  local okH, Happiness = pcall(require, "src.core.gen2.Happiness")
  if okH and Happiness and Happiness.CHANGES then
    for i, row in ipairs(DATA.happiness) do Happiness.CHANGES[i] = row end
  else
    mod.log:warn("happiness table not found; happiness changes skipped")
  end
  local okE, Effects = pcall(require, "src.battle.gen2.Effects")
  if okE and Effects and Effects.METRONOME_EXCEPTIONS then
    for _, m in ipairs(DATA.metronomeAdd) do Effects.METRONOME_EXCEPTIONS[m] = true end
  end
  -- engine/battle/effect_commands.asm: Legacy adds a Zephyr Badge tier (16).
  local okB, Battle = pcall(require, "src.battle.gen2.Battle")
  if okB and Battle and Battle.obedienceLevel and not Battle.__legacyObedience then
    local vanilla = Battle.obedienceLevel
    Battle.__legacyObedience = vanilla
    Battle.obedienceLevel = function(self, ...)
      local level = vanilla(self, ...)
      if level == 10 and self.hasBadge and self:hasBadge("badges", "ZEPHYR") then return 16 end
      return level
    end
  end
  -- data/moves/critical_hit_moves.asm lives in the imported battle rules.
  mod.events:on("game.ready", function(payload)
    local game = (payload and payload.game) or mod.game
    local data = game and game.data
    local rules = data and data.type_chart and data.type_chart.battleRules
    if rules and rules.highCriticalMoves then
      for _, m in ipairs(DATA.critAdd) do rules.highCriticalMoves[m] = true end
    end
  end)
end
"""

MODS = [
    {"id": "crystal_legacy_pokemon", "name": "Legacy: Pokémon Changes",
     "category": "BALANCE", "games": ["crystal"], "build": build_pokemon,
     "runtime": POKEMON_RT, "permissions": ["engine_internals"],
     "summary": "Crystal Legacy's base stats, learnsets, TM/HM and egg moves, "
                "evolutions and move changes."},
    {"id": "crystal_legacy_trainers", "name": "Legacy: Trainer Changes",
     "category": "BALANCE", "games": ["crystal"], "build": build_trainers,
     "runtime": SCALING_RUNTIME,
     "summary": "Every trainer, gym leader and Elite Four team rebuilt as in Crystal Legacy."},
    {"id": "crystal_legacy_encounters", "name": "Legacy: Encounter Changes",
     "category": "CONTENT", "games": ["crystal"], "build": build_encounters,
     "permissions": ["engine_internals"],
     "summary": "Crystal Legacy's wild Pokémon: grass, surfing and the Bug-Catching Contest."},
    {"id": "fast_eggs", "name": "Fast Eggs", "category": "QOL", "games": ["gen2"],
     "build": build_fast_eggs,
     "summary": "Eggs hatch in about a quarter of the steps, as in Crystal Legacy."},
    {"id": "crystal_legacy_ghost_dark", "name": "Legacy: Ghost/Dark Switch",
     "category": "BALANCE", "games": ["gen2"], "build": build_ghost_dark,
     "summary": "Ghost moves become special and Dark moves physical, as in Crystal Legacy."},
    {"id": "crystal_legacy_shops", "name": "Legacy: Shop Changes",
     "category": "BALANCE", "games": ["crystal"], "build": build_shops,
     "runtime": SHOPS_RUNTIME, "permissions": ["engine_internals"],
     "summary": "Crystal Legacy's shop stock and item prices."},
    {"id": "crystal_legacy_rematches", "name": "Legacy: Rematches",
     "category": "CONTENT", "games": ["crystal"], "build": build_rematches,
     "runtime": REMATCH_RUNTIME, "optional_dependencies": ["crystal_legacy_trainers"],
     "summary": "Rematch every gym leader after the Elite Four, and the Elite Four "
                "themselves once you have all 16 badges."},
    {"id": "crystal_legacy_fixes", "name": "Legacy: Bug Fixes",
     "category": "BALANCE", "games": ["crystal"], "build": build_fixes,
     "runtime": FIXES_RUNTIME, "permissions": ["engine_internals"],
     "summary": "The vanilla Crystal bugs Crystal Legacy fixes and gen1recomp still "
                "reproduces: Poké Ball catch bonuses, the trainer AI and the Glacier Badge."},
    {"id": "crystal_legacy_icons", "name": "Legacy: Menu Icons",
     "category": "QOL", "games": ["crystal"], "build": build_icons,
     "runtime": ICONS_RUNTIME, "permissions": ["engine_internals"],
     "summary": "Crystal Legacy's per-species party menu icons and colours. Bring "
                "your own icons: copy Crystal Legacy's gfx/icons folder into this "
                "mod's folder as icons/. Falls back to Wilds of Kanto's follower "
                "sprites when that mod is installed."},
    {"id": "crystal_legacy_qol", "name": "Legacy: Quality of Life",
     "category": "QOL", "games": ["crystal"], "build": build_qol,
     "runtime": QOL_RUNTIME, "permissions": ["engine_internals"],
     "summary": "Crystal Legacy's quality-of-life touches: run with B, reuse Repels, "
                "sort the PACK with START, a quicker nurse, and a Day-Care that keeps "
                "your Pokémon's experience."},
]


def context(base, leg):
    report = {"notes": []}
    ctx = {"report": report, "base": base, "legacy": leg,
           "pokemon": D.diff_pokemon(base, leg, report),
           "moves": D.diff_moves(base, leg, report),
           "items": D.diff_items(base, leg, report)}
    ctx["marts"] = {k: v["items"] for k, v in D.diff_marts(base, leg, report).items()}
    rows, extras = D.diff_trainers(base, leg, report)
    vanilla_counts = {c: len(v["parties"]) for c, v in D.parse.trainer_parties(base).items()}
    ctx["trainersAll"], ctx["extrasAll"] = rows, extras
    ctx["trainersVanilla"] = {}
    for c, rs in rows.items():
        keep = [r for r in rs if r["index"] <= vanilla_counts.get(c, 0)]
        b_rows = D.parse.trainer_parties(base)[c]["parties"]
        if any(r["party"] != _plain(b_rows[r["index"] - 1]["party"]) or
               r["name"] != b_rows[r["index"] - 1]["name"] for r in keep):
            ctx["trainersVanilla"][c] = keep
    ctx["extrasVanilla"] = {c: {i: s for i, s in v.items() if i <= vanilla_counts.get(c, 0)}
                            for c, v in extras.items()}
    ctx["extrasVanilla"] = {c: v for c, v in ctx["extrasVanilla"].items() if v}
    ctx["encounters"] = D.diff_encounters(base, leg, report)
    return ctx


def _plain(party):
    return [{k: m[k] for k in ("level", "species", "item", "moves") if k in m} for m in party]


def write_mod(spec, ctx):
    data, body, lines = spec["build"](ctx)
    d = os.path.join(ROOT, "mods", spec["id"])
    os.makedirs(d, exist_ok=True)
    manifest = {
        "id": spec["id"], "name": spec["name"], "version": VERSION, "api": 2,
        "games": spec["games"], "entry": "main.lua", "profile": "content",
        "category": spec["category"], "game_version": GAME_VERSION, "priority": 100,
        "dependencies": [], "optional_dependencies": spec.get("optional_dependencies", []),
        "conflicts": [], "permissions": spec.get("permissions", []),
        "description": spec["summary"] + " Unofficial port of Pokémon Crystal Legacy.",
        "github": GITHUB,
    }
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(os.path.join(d, "main.lua"), "w", encoding="utf-8") as fh:
        fh.write("-- GENERATED by tools/build.py -- edit the builder, not this file.\n")
        fh.write("-- %s: %s\n" % (spec["name"], spec["summary"]))
        fh.write("\nlocal DATA = " + D.lua(data) + "\n" + PRELUDE + spec.get("runtime", ""))
        fh.write("\nreturn function(mod)\n  local stats = { applied = 0, failed = 0 }\n")
        fh.write(body + "\n")
        fh.write('  mod.log:info("%s: %%d patches applied, %%d refused", stats.applied, stats.failed)\n'
                 % spec["name"])
        fh.write("end\n")
    with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# %s\n\n%s\n\n## What it changes\n\n" % (spec["name"], spec["summary"]))
        fh.write("\n".join("- " + l if not l.startswith("  ") else l for l in lines))
        fh.write("\n\nGames: %s. Needs gen1recomp %s.\n\n" % (", ".join(spec["games"]), GAME_VERSION))
        fh.write("Generated from [Pokémon Crystal Legacy](https://github.com/cRz-Shadows/"
                 "Pokemon_Crystal_Legacy) by `tools/build.py`. All design credit to the "
                 "Crystal Legacy team. See the [repository README](../../README.md).\n")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    ctx = context(a.base, a.legacy)
    for spec in MODS:
        if a.only and spec["id"] not in a.only:
            continue
        lines = write_mod(spec, ctx)
        print("%-28s %s" % (spec["id"], lines[0]))
    for note in ctx["report"]["notes"]:
        print("note:", note)


if __name__ == "__main__":
    main()
