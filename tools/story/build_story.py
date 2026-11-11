#!/usr/bin/env python3
"""Build mods/crystal_legacy_story from Crystal Legacy's map scripts.

    python3 tools/story/build_story.py --base <pokecrystal@82e315e48, built> \
        --legacy <Crystal Legacy> --rgbds <dir> --engine <gen1recomp checkout> \
        --work <scratch dir>

Pipeline (everything ROM-derived stays in --work):
  1. assemble.py: Legacy's map files, assembled against vanilla numbering.
  2. patch_rom.py: a scratch vanilla ROM with those banks and the maps
     repointed at them.
  3. extract_story.lua: gen1recomp's own importer decodes it; only the Legacy
     banks' scripts, text and movements and the maps' event records are kept.
  4. This script adds the new trainer classes, their teams and art, and
     writes the mod.
--base must contain pokecrystal.gbc / pokecrystal.sym (run `make` there).
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import assemble  # noqa: E402
import sprites as SP  # noqa: E402
import legacy_diff as D  # noqa: E402
import build as B  # noqa: E402

MOD_ID = "crystal_legacy_story"

# Every map Crystal Legacy changed is ported, except the ones whose scripts
# another mod already rewrites (porting both would double up rematch offers
# and badge switches), and the Move Deleter's house, whose Move Reminder is
# new engine code gen1recomp has no counterpart for.
EXCLUDE = {
    # Rematches / Trainer Changes / Hard Mode (Johto gyms, Elite Four)
    "VioletGym", "AzaleaGym", "GoldenrodGym", "EcruteakGym", "MahoganyGym",
    "OlivineGym", "CianwoodGym", "BlackthornGym1F",
    "WillsRoom", "KogasRoom", "BrunosRoom", "KarensRoom", "LancesRoom",
    # Shop Changes
    "CeladonDeptStore3F", "CeladonDeptStore5F",
}

# Legacy's Move Reminder is engine code (engine/events/move_reminder.asm),
# reached by `special MoveReminder`. The special gets a sentinel id here, and
# the decoded row is swapped for a mod command that runs the same flow on
# gen1recomp's own party menu and learn-move prompt.
REMINDER_SPECIALS = {"MoveReminderSpecial": 900 * 3, "EggMoveReminderSpecial": 901 * 3}
REMINDER_VERBS = {900: "crystal_legacy_story:move_reminder",
                  901: "crystal_legacy_story:egg_move_reminder"}
REMINDER_TEXTS = ["_MoveReminderIntro", "_EggMoveReminderIntro", "_MoveReminderWhichMon",
                  "_MoveReminderWhichMove", "_MoveReminderCancel", "_MoveReminderEgg",
                  "_MoveReminderNoMon", "_MoveReminderNoMoves"]
EVENT_IDS = os.path.join(HERE, "event_ids.json")
SPRITE_IDS = os.path.join(HERE, "sprite_ids.json")


def gen1recomp_map_ids(base, engine):
    """pokecrystal map constant -> gen1recomp map id, matched by (group, number).

    gen1recomp names maps after a newer pokecrystal (DANCE_THEATER, not
    DANCE_THEATRE), so names are matched through the numbers both share.
    """
    import re as _re
    by_num, group, num = {}, 0, 0
    for line in open(os.path.join(base, "constants/map_constants.asm")):
        line = line.split(";")[0]
        if "MACRO" in line:
            continue
        if _re.match(r"\s*newgroup\b", line):
            group, num = group + 1, 0
        m = _re.match(r"\s*map_const\s+(\w+)", line)
        if m:
            num += 1
            by_num[m.group(1)] = (group, num)
    manifest = json.load(open(os.path.join(engine, "tools/rom_manifest_crystal.json")))
    names = {(g["group"], g["map"]): g["name"] for g in manifest["constants"]["mapGroups"]}
    return {const: names[gm] for const, gm in by_num.items() if gm in names}


def story_maps(base, legacy, engine):
    """{Legacy map file: gen1recomp map id} for every changed, non-excluded map."""
    consts = B._legacy_map_constants(base)
    rename = gen1recomp_map_ids(base, engine)
    ids = {f: rename[c] for f, c in consts.items() if c in rename}
    out = {}
    for f in sorted(os.listdir(os.path.join(legacy, "maps"))):
        if not f.endswith(".asm") or f[:-4] in EXCLUDE:
            continue
        a, b = os.path.join(base, "maps", f), os.path.join(legacy, "maps", f)
        if os.path.exists(a) and open(a, "rb").read() != open(b, "rb").read():
            out[f[:-4]] = ids[f[:-4]]
    return out

# New trainer classes: index (as assemble.LEGACY_ONLY), display name, the
# Legacy art, and the vanilla class whose music / AI / prize money they borrow.
NEW_CLASSES = [
    {"id": "BOSS", "name": "BOSS", "pic": "boss", "like": "EXECUTIVEM"},
    {"id": "ROCKET_LEADER", "name": "ROCKET", "pic": "archer", "like": "EXECUTIVEM"},
    {"id": "PKMNTRAINERF", "name": "PKMN TRAINER", "pic": "pkmntrainerf",
     "palette_from": "cal", "like": "CAL"},
]

# Legacy's fossils take vanilla's unused item slots $93-$95 (ITEM_93..95 in
# gen1recomp), as they do in Legacy. data/items/{names,descriptions,attributes}.asm.
FOSSILS = {
    "ITEM_93": {"name": "OLD AMBER", "description": "Fossilized resin<NEXT>containing DNA."},
    "ITEM_94": {"name": "DOME FOSSIL", "description": "A fossilized<NEXT>POKéMON shell."},
    "ITEM_95": {"name": "HELIX FOSSIL", "description": "A fossilized<NEXT>POKéMON shell."},
}
for _f in FOSSILS.values():
    _f.update({"price": 0, "pocket": "KEY_ITEM", "pocketId": 2, "canToss": False,
               "canSelect": False})

# Parties the Story maps load from existing classes, by Legacy member index.
EXTRA_PARTIES = [("CAL", 3), ("CAL", 4), ("RED", 2)]


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("%s failed:\n%s%s" % (cmd[0], r.stdout[-3000:], r.stderr[-3000:]))
    return r.stdout


def colour_pic(src, out, palette_src=None):
    """Legacy's 4-shade trainer art -> a true-colour PNG with its own palette."""
    from PIL import Image
    im = Image.open(src)
    pal_im = Image.open(palette_src) if palette_src else im
    pal = pal_im.getpalette()[:12]
    colours = [tuple(pal[i:i + 3]) for i in range(0, 12, 3)]
    grey = im.convert("L")
    shades = sorted(set(grey.tobytes()), reverse=True)  # white .. black
    rgb = Image.new("RGB", im.size)
    rgb.putdata([colours[min(shades.index(v), 3)] for v in grey.tobytes()])
    rgb.save(out)


def main():
    ap = argparse.ArgumentParser()
    for k in ("base", "legacy", "rgbds", "engine", "work"):
        ap.add_argument("--" + k, required=True)
    a = ap.parse_args()
    MAPS = story_maps(a.base, a.legacy, a.engine)
    files = list(MAPS)
    mod_dir = os.path.join(ROOT, "mods", MOD_ID)
    # Sprite numbers are stored in saves (variable sprite slots): pinned too.
    pinned_sprites = json.load(open(SPRITE_IDS)) if os.path.exists(SPRITE_IDS) else {}
    sprite_defs, sprite_records, sprite_order = SP.port(
        a.base, a.legacy, files, os.path.join(mod_dir, "assets"), pinned_sprites)
    with open(SPRITE_IDS, "w") as fh:
        json.dump(dict(pinned_sprites, **sprite_defs), fh, indent=2, sort_keys=True)
        fh.write("\n")
    # Event ids are stored in saves, so once given out they never change.
    pinned = json.load(open(EVENT_IDS)) if os.path.exists(EVENT_IDS) else {}
    r = assemble.build(a.base, a.legacy, a.rgbds, a.work, files,
                       dict(sprite_defs, **pinned, **REMINDER_SPECIALS))
    events = dict(pinned, **r["newEvents"])
    with open(EVENT_IDS, "w") as fh:
        json.dump(events, fh, indent=2, sort_keys=True)
        fh.write("\n")
    r["newEvents"] = events
    patched = os.path.join(a.work, "patched.gbc")
    run([sys.executable, "-I", os.path.join(HERE, "patch_rom.py"), "--base", a.base,
         "--work", a.work, "--rom", "pokecrystal.gbc", "--out", patched] + files)
    sha = run(["sha1sum", os.path.join(a.base, "pokecrystal.gbc")]).split()[0]
    story_lua = os.path.join(a.work, "story.lua")
    os.environ["CL_SPRITE_ORDER"] = ",".join("%d=%s" % kv for kv in sorted(sprite_order.items()))
    print(run(["luajit", os.path.join(HERE, "extract_story.lua"), patched, sha, story_lua]
              + list(MAPS.values()), cwd=a.engine).strip())
    dump = run(["luajit", "-e", 'package.path="./?.lua;"..package.path '
                'local Json=require("src.link.Json") '
                # A table with a [0] key (sceneScripts: scene 0 is the "first
                # visit" cutscene) would be encoded as a 1-based array and
                # lose that entry, so such tables get string keys here;
                # numberKeys() turns them back into numbers at load time.
                'local function fix(t) if type(t)~="table" then return t end '
                'local zero=rawget(t,0)~=nil local out={} '
                'for k,v in pairs(t) do out[zero and tostring(k) or k]=fix(v) end return out end '
                'io.write(Json.encode(fix(dofile(%s))))' % json.dumps(story_lua)], cwd=a.engine)
    story = json.loads(dump)
    swapped = 0
    for rows in story["scripts"].values():
        for i, row in enumerate(rows):
            if row.get("op") == "special" and row.get("id") in REMINDER_VERBS:
                rows[i] = {"op": "modcommand", "verb": REMINDER_VERBS[row["id"]]}
                swapped += 1
    print("move reminder rows:", swapped)
    print("fade-ins added:", add_missing_fade_ins(a.base, story["scripts"]))
    import textc
    common = textc.text_blocks(os.path.join(a.legacy, "data/text/common_3.asm"))
    reminder_text = {k.lstrip("_"): common[k] for k in REMINDER_TEXTS}

    # Trainer data from Legacy's parties.asm (same parser as Trainer Changes).
    report = {"notes": []}
    rows, extras = D.diff_trainers(a.base, a.legacy, report)
    classes, parties = [], []
    legacy_parties = D.parse.trainer_parties(a.legacy)
    D.resolve_moves(a.legacy, legacy_parties, report)

    def party_rows(cls):
        out = []
        for i, pt in enumerate(legacy_parties[cls]["parties"], 1):
            party = [{k: m[k] for k in ("level", "species", "item", "moves") if k in m}
                     for m in pt["party"]]
            out.append({"index": i, "name": pt["name"], "party": party,
                        "trainerType": D.TRAINERTYPE[("item" in pt["flags"], "moves" in pt["flags"])]})
        return out

    extra_fields = {}
    for c in NEW_CLASSES:
        pic = "%s.png" % c["pic"]
        pal = os.path.join(a.base, "gfx/trainers/%s.png" % c["palette_from"]) \
            if c.get("palette_from") else None
        colour_pic(SP.gfx_path(a.legacy, "gfx/trainers/" + pic),
                   os.path.join(mod_dir, "assets", pic), pal)
        trs = party_rows(c["id"])
        for t in trs:
            t["id"] = "%s%d" % (c["id"], t["index"])
        classes.append({"id": c["id"], "index": assemble.LEGACY_ONLY[c["id"]],
                        "name": c["name"], "pic": "assets/" + pic, "like": c["like"],
                        "trainers": trs})
    for cls, idx in EXTRA_PARTIES:
        row = next(t for t in party_rows(cls) if t["index"] == idx)
        row["id"] = legacy_parties[cls]["members"][idx - 1] \
            if idx <= len(legacy_parties[cls]["members"]) else "%s_STORY%d" % (cls, idx)
        parties.append({"class": cls, "row": row})
    for cls, by in extras.items():
        for idx, slots in by.items():
            if any(c["id"] == cls for c in NEW_CLASSES) or (cls, idx) in EXTRA_PARTIES:
                extra_fields.setdefault(cls, {})[idx] = slots

    EVENT_FIELDS = ("objects", "bgEvents", "coordEvents", "sceneScripts", "callbacks", "warps")
    data = {
        "scripts": story["scripts"], "movements": story["movements"], "text": story["text"],
        "maps": {mid: {k: story["maps"][mid][k] for k in EVENT_FIELDS if k in story["maps"][mid]}
                 for mid in MAPS.values()},
        "classes": classes, "parties": parties, "extras": extra_fields,
        "newEvents": r["newEvents"],
        "items": FOSSILS,
        "reminderText": reminder_text,
        "sprites": sprite_records,
        "spriteOrder": {str(k): v for k, v in sprite_order.items()},
        "trades": changed_trades(a.base, a.legacy),
    }
    write_mod(mod_dir, data)
    print("events reused:", r["newEvents"])
    print("sprites:", {v: hex(k) for k, v in sprite_order.items()})
    for n in report["notes"]:
        print("note:", n)


RUNTIME = r'''
-- ------------------------------------------------------------ Move Reminder
-- Crystal Legacy's engine/events/move_reminder.asm (after Polished Crystal and
-- TPP Anniversary Crystal), on gen1recomp's own party menu and learn-move
-- prompt: pick a Pokemon, then any level-up move it could have learned by now
-- and does not know (or, for the Egg-move tutor, any of its egg moves).

local TYPE_ABBR = {
  NORMAL = "NRM", FIGHTING = "FGT", FLYING = "FLY", POISON = "PSN", GROUND = "GRD",
  ROCK = "RCK", BIRD = "BRD", BUG = "BUG", GHOST = "GHT", STEEL = "STL", FIRE = "FIR",
  WATER = "WTR", GRASS = "GRS", ELECTRIC = "ELC", PSYCHIC_TYPE = "PSY", ICE = "ICE",
  DRAGON = "DRG", DARK = "DRK", CURSE_TYPE = "???",
}

-- GetRemindableMoves / GetEggRemindableMoves: in learnset order, no repeats,
-- none the Pokemon already knows.
local function remindable(def, mon, egg)
  local known, out, seen = {}, {}, {}
  for _, m in ipairs(mon.moves or {}) do known[m.id] = true end
  local function add(id)
    if id and not known[id] and not seen[id] then
      seen[id] = true
      out[#out + 1] = id
    end
  end
  if egg then
    for _, id in ipairs(def and def.eggMoves or {}) do add(id) end
  else
    for _, row in ipairs(def and def.levelMoves or {}) do
      if (row.level or 0) <= (mon.level or 0) then add(row.move) end
    end
  end
  return out
end

-- ChooseMoveToLearn: a scrolling list with type and PP, and the highlighted
-- move's description underneath.
local MoveList = {}
MoveList.__index = MoveList
MoveList.isOpaque = true
local VISIBLE = 5

function MoveList.new(game, moves, onDone)
  return setmetatable({ game = game, moves = moves, onDone = onDone, index = 1,
    scroll = 0, data = (game and game.data) or {} }, MoveList)
end
function MoveList:wantsFillScale() return true end
function MoveList:finish(move)
  if self.done then return end
  self.done = true
  -- Close before answering: the overworld (and so the script that is
  -- waiting on this) only runs again once this screen is off the stack.
  if self.game and self.game.stack then self.game.stack:pop() end
  self.onDone(move)
end
function MoveList:update()
  if self.done then return end
  local input = self.game and self.game.input
  if not input then return end
  if input:wasPressed("up") and self.index > 1 then
    self.index = self.index - 1
  elseif input:wasPressed("down") and self.index < #self.moves then
    self.index = self.index + 1
  elseif input:wasPressed("b") then
    return self:finish(nil)
  elseif input:wasPressed("a") then
    return self:finish(self.moves[self.index])
  end
  if self.index - 1 < self.scroll then self.scroll = self.index - 1 end
  if self.index > self.scroll + VISIBLE then self.scroll = self.index - VISIBLE end
end
function MoveList:drawPanel()
  local Chrome = require("src.ui.gen2.Chrome")
  local moves = self.data.moves or {}
  Chrome.textbox(0, 0, 18, 10)
  for slot = 1, VISIBLE do
    local id = self.moves[self.scroll + slot]
    if id then
      local def = moves[id] or {}
      local y = slot * 2
      Chrome.print(def.name or id, 2, y)
      Chrome.print(("%s %2d"):format(TYPE_ABBR[def.type] or "???", def.pp or 0), 13, y)
      if self.scroll + slot == self.index then Chrome.cursor(1, y) end
    end
  end
  Chrome.textbox(0, 12, 18, 4)
  local def = moves[self.moves[self.index]] or {}
  local line = 0
  for part in ((def.description or ""):gsub("<NEXT>", "\n") .. "\n"):gmatch("([^\n]*)\n") do
    Chrome.print(part, 1, 14 + line * 2)
    line = line + 1
    if line >= 2 then break end
  end
  love.graphics.setColor(1, 1, 1, 1)
end
function MoveList:draw() self:drawPanel() end
function MoveList:drawWidescreen(winW, winH)
  local Chrome = require("src.ui.gen2.Chrome")
  local G = love.graphics
  Chrome.letterbox(winW, winH, 1, 1, 1)
  local scale = Chrome.fitScale(winW, winH)
  G.push()
  G.translate(Chrome.fitOrigin(winW, winH, scale))
  G.scale(scale, scale)
  self:drawPanel()
  G.pop()
end

-- Wait inside the script for a screen's callback; the screen closes itself
-- first, so the overworld (and this script) can run again.
local function await(vm, isDone)
  while not isDone() do vm:waitFrames(1) end
end

local function moveReminder(mod, ctx, egg)
  local vm, game = ctx.vm, mod.game
  local function say(id) vm:showText("crystal_legacy_story:" .. id) end
  if not (game and game.stack and vm) then return end
  say(egg and "EggMoveReminderIntro" or "MoveReminderIntro")
  if not coroutine.yield({ kind = "yesorno" }) then
    return say("MoveReminderCancel")
  end
  say("MoveReminderWhichMon")
  local PartyMenu = require("src.ui.gen2.PartyMenu")
  local picked, done = nil, false
  game.stack:push(PartyMenu.new(game, { prompt = "which",
    onChoose = function(_, mon) game.stack:pop() picked, done = mon, true end,
    onCancel = function() game.stack:pop() done = true end }))
  await(vm, function() return done end)
  if not picked then return say("MoveReminderCancel") end
  if picked.isEgg then return say("MoveReminderEgg") end
  local def = game.data and game.data.pokemon and game.data.pokemon[picked.species]
  local moves = remindable(def, picked, egg)
  if #moves == 0 then return say("MoveReminderNoMoves") end
  say("MoveReminderWhichMove")
  local chosen
  done = false
  game.stack:push(MoveList.new(game, moves, function(m) chosen, done = m, true end))
  await(vm, function() return done end)
  if chosen and game.learnMoveOn then
    done = false
    game:learnMoveOn(picked, chosen, function() done = true end)
    await(vm, function() return done end)
  end
  say("MoveReminderCancel")
end

local function copy(v)
  if type(v) ~= "table" then return v end
  local out = {}
  for k, x in pairs(v) do out[k] = copy(x) end
  return out
end

local function register(mod, reg, id, value, stats)
  local r = mod.content[reg]
  local ok, err = pcall(r.has and r:has(id) and r.override or r.register, r, id, value)
  if ok then stats.applied = stats.applied + 1 else
    stats.failed = stats.failed + 1
    mod.log:warn("%s %s: %s", reg, tostring(id), tostring(err))
  end
end

-- Lua's JSON round trip turns sparse integer maps into string keys; give
-- scene ids, trainer indices and DV slots their numbers back.
local function numberKeys(t)
  if type(t) ~= "table" then return t end
  local out = {}
  for k, v in pairs(t) do out[tonumber(k) or k] = numberKeys(v) end
  return out
end
'''


# Scripts that leave the map clear a fade by loading the next one.
LEAVES_MAP = {"warp", "warpfacing", "warpmod", "reloadmap", "reloadmapafterbattle",
              "newloadmap", "warpcheck"}


def add_missing_fade_ins(base, scripts):
    """A few Legacy scripts fade the screen out and carry on without fading it
    back in (the fossil scientist: FadeBlackQuickly, a sound, a pause, then
    back into his dialogue). The cartridge recovers on its own; gen1recomp
    keeps a fade until a script lifts it, so the screen stayed black. Such a
    script gets the matching fade-in just before it jumps or ends."""
    names = [m.group(1) for m in re.finditer(
        r"^\s*add_special\s+(\w+)",
        open(os.path.join(base, "data/events/special_pointers.asm"), encoding="utf-8").read(),
        re.M)]
    pairs = {names.index("FadeBlackQuickly"): names.index("FadeInQuickly"),
             names.index("FadeOutPalettes"): names.index("FadeInPalettes")}
    fade_ins = set(pairs.values())
    added = 0
    for rows in scripts.values():
        pending = None
        for row in rows:
            op, sid = row.get("op"), row.get("id")
            if op == "special" and sid in pairs:
                pending = pairs[sid]
            elif (op == "special" and sid in fade_ins) or op in LEAVES_MAP:
                pending = None
        if pending is not None and rows and rows[-1].get("op") in ("sjump", "end"):
            rows.insert(len(rows) - 1, {"op": "special", "id": pending})
            added += 1
    return added


def changed_trades(base, legacy):
    """data/events/npc_trades.asm rows Legacy changed, keyed by 1-based row."""
    from asm import species_order
    dex = {sp: i + 1 for i, sp in enumerate(species_order(base))}
    b, l = D.parse.npc_trades(base), D.parse.npc_trades(legacy)
    out = {}
    for i, row in enumerate(l):
        if i < len(b) and row != b[i]:
            r = {k: v for k, v in row.items() if k != "dialog"}
            r["giveIndex"], r["getIndex"] = dex[row["give"]], dex[row["get"]]
            out[str(i + 1)] = r
    return out


def write_mod(mod_dir, data):
    manifest = {
        "id": MOD_ID, "name": "Legacy: Story Changes", "version": B.VERSION, "api": 2,
        "games": ["crystal"], "entry": "main.lua", "profile": "content", "category": "CONTENT",
        "game_version": B.GAME_VERSION, "priority": 100, "dependencies": [],
        "optional_dependencies": ["crystal_legacy_trainers", "crystal_legacy_rematches",
                                  "crystal_legacy_shops"],
        # The Move Reminder opens gen1recomp's party menu and draws its list
        # with the engine's Chrome helpers.
        "conflicts": [], "permissions": ["engine_internals"],
        "description": "Crystal Legacy's story changes, starting with the Trainer House "
                       "trio, Archer and the Silver Cave Mewtwo / Red rematch. "
                       "Unofficial port of Pokemon Crystal Legacy.",
        "github": B.GITHUB,
    }
    with open(os.path.join(mod_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    body = r'''
return function(mod)
  local stats = { applied = 0, failed = 0 }
  local scripts, maps = numberKeys(DATA.scripts), numberKeys(DATA.maps)

  -- 0. Legacy's new overworld sprites, on sprite numbers vanilla leaves free.
  for _, rec in ipairs(DATA.sprites) do
    local r = copy(rec)
    r.image = mod.path .. "/" .. rec.image
    register(mod, "sprites", rec.id, r, stats)
  end
  local order = mod.content.constants:get("spriteOrder")
  if order then
    for num, name in pairs(numberKeys(DATA.spriteOrder)) do order[num] = name end
    patch(mod, "constants", "spriteOrder", order, stats)
  end

  -- Legacy's fossils, on vanilla's unused item slots.
  each(DATA.items, function(id, fields)
    if mod.content.items:get(id) then patch(mod, "items", id, fields, stats) end
  end)

  -- The Move Reminder (Move Deleter's house) and its Egg-move twin.
  each(DATA.reminderText, function(id, s)
    register(mod, "text", "crystal_legacy_story:" .. id, s, stats)
  end)
  register(mod, "commands", "crystal_legacy_story:move_reminder",
    function(ctx) return moveReminder(mod, ctx, false) end, stats)
  register(mod, "commands", "crystal_legacy_story:egg_move_reminder",
    function(ctx) return moveReminder(mod, ctx, true) end, stats)

  -- 1. Legacy's text, movements and scripts, under their own (bank $80+) keys.
  each(DATA.text, function(id, s) register(mod, "text", id, s, stats) end)
  each(DATA.movements, function(id, bytes)
    register(mod, "map_scripts", "movement:" .. id, bytes, stats)
  end)
  each(scripts, function(id, rows) register(mod, "map_scripts", id, rows, stats) end)

  -- 2. New trainer classes, borrowing music / AI / money from a vanilla one.
  for _, c in ipairs(DATA.classes) do
    local like = mod.content.trainers:get(c.like) or {}
    local rec = { id = c.id, index = c.index, name = c.name,
      pic = mod.path .. "/" .. c.pic, trueColor = true,
      baseMoney = like.baseMoney, attributes = copy(like.attributes),
      items = copy(like.items or {}), encounterMusic = like.encounterMusic,
      trainers = copy(c.trainers) }
    register(mod, "trainers", c.id, rec, stats)
  end

  -- 3. Parties the story loads from existing classes (Trainer House Smith and
  --    Craig, Red's rematch), at the member index Legacy's scripts use.
  for _, p in ipairs(DATA.parties) do
    local rec = mod.content.trainers:get(p.class)
    if rec and rec.trainers then
      local list, row = rec.trainers, copy(p.row)
      if row.index > #list + 1 then
        mod.log:warn("%s: cannot place member %d after %d", p.class, row.index, #list)
        stats.failed = stats.failed + 1
      else
        list[row.index] = row
        patch(mod, "trainers", p.class, { trainers = list }, stats)
      end
    end
  end

  -- 4. The maps' events now point at Legacy's scripts.
  -- (Every map exists in a real Crystal import; a test dataset may hold fewer.)
  each(maps, function(id, fields)
    if mod.content.maps:get(id) then
      -- sceneScripts is keyed from 0 (a dictionary, which a patch merges),
      -- so clear vanilla's first: a scene Legacy dropped must not survive.
      if fields.sceneScripts then
        patch(mod, "maps", id, { sceneScripts = mod.DELETE }, stats)
      end
      patch(mod, "maps", id, fields, stats)
    else
      mod.log:info("map %s not in this dataset; skipped", id)
    end
  end)

  -- In-game trades (data/events/npc_trades.asm): World reads the event
  -- tables when it is built, so they are patched as soon as the game exists.
  local trades = numberKeys(DATA.trades)
  if next(trades) then
    mod.events:on("game.ready", function(payload)
      local game = (payload and payload.game) or mod.game
      local tables = game and game.data and game.data.gen2EventTables
      local rows = type(tables) == "table" and tables.trades
      if type(rows) ~= "table" then
        mod.log:warn("trade table not loaded; Legacy's trades skipped")
        return
      end
      for i, fields in pairs(trades) do
        if rows[i] then
          for k, v in pairs(fields) do rows[i][k] = copy(v) end
        end
      end
    end)
  end

  -- Custom DVs / stat exp on story teams (Trainer House, Red).
  local extras = numberKeys(DATA.extras)
  if next(extras) then
    mod.hooks:wrap("trainer.party", function(nextFn, class, member, party)
      party = nextFn(class, member, party)
      local rec = mod.content.trainers:get(class)
      local index
      for i, t in ipairs(rec and rec.trainers or {}) do
        if t.id == member then index = i break end
      end
      local slots = extras[class] and extras[class][index]
      if slots and type(party) == "table" then
        for slot, extra in pairs(slots) do
          local mon = party[slot]
          if mon then
            if extra.dvs then mon.dvs = extra.dvs end
            if extra.statExp then mon.statExp = extra.statExp end
          end
        end
      end
      return party
    end)
  end
  mod.log:info("Legacy: Story Changes: %d applied, %d refused", stats.applied, stats.failed)
end
'''
    with open(os.path.join(mod_dir, "main.lua"), "w", encoding="utf-8") as fh:
        fh.write("-- GENERATED by tools/story/build_story.py -- edit the builder, not this file.\n")
        fh.write("-- Crystal Legacy's story scripts, decoded by gen1recomp's own importer.\n")
        fh.write("\nlocal DATA = " + D.lua(data) + "\n" + B.PRELUDE + RUNTIME + body)


if __name__ == "__main__":
    main()
