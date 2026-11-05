-- Decode the patched ROM with gen1recomp's own Crystal importer and keep only
-- what the Story mod ships: the patched maps' event records, and every script,
-- text and movement in the Legacy banks ($80 up). Everything else in the
-- output is vanilla and is never written out.
--
--   cd <gen1recomp> && luajit <repo>/tools/story/extract_story.lua \
--       <patched.gbc> <vanilla sha1> <out.lua> MAP_ID [MAP_ID ...]
package.path = "./?.lua;./?/init.lua;" .. package.path
love = love or require("tests.love_stub")
local Json = require("src.link.Json")
local LuaWriter = require("src.import.LuaWriter")
-- The importer rejects banks past $7f, the end of a real cart. The Legacy
-- code lives from $80 up (so its keys cannot collide with vanilla ones), so
-- for this build-time decode only, load the importer with that cap raised.
local src = assert(io.open("src/import/RomExtractorGen2.lua")):read("*a")
local patched, n = src:gsub("bank > 0x7f", "bank > 0xff")
patched = patched:gsub("farBank > 0x7f", "farBank > 0xff")
assert(n >= 1, "importer bank check not found; update extract_story.lua")
local Extractor = assert(loadstring(patched, "@src/import/RomExtractorGen2.lua"))()

local romPath, sha1, outPath = arg[1], arg[2], arg[3]
local mapIds = {}
for i = 4, #arg do mapIds[#mapIds + 1] = arg[i] end

local function read(p) local f = assert(io.open(p, "rb")) local s = f:read("*a") f:close() return s end
local manifest = Json.decode(read("tools/rom_manifest_crystal.json"))
local e = Extractor.new(read(romPath), manifest, nil, sha1)
local out = {}
e.write = function(_, name, value) out[name] = value end
e.save = function() end
e.writeCompressedPic = function() return nil end
e.write2bpp = function() end
e:extractConstants()
e:extractTilesets()
local maps = e:extractMaps()
local std = e:extractStdScripts()
e:extractScriptsAndText(maps, std)

local FIRST_BANK = 0x80
local function ours(key)
  local hex = type(key) == "string" and key:match("^(%x+):%x+$")
  local bank = hex and tonumber(hex, 16)
  return bank ~= nil and bank >= FIRST_BANK
end

local result = { maps = {}, scripts = {}, text = {}, movements = {} }
for _, id in ipairs(mapIds) do
  result.maps[id] = assert(out.maps[id], "map not found: " .. id)
end
for key, rows in pairs(out.scripts) do
  if key ~= "movements" and ours(key) then result.scripts[key] = rows end
end
for key, bytes in pairs(out.scripts.movements or {}) do
  if ours(key) then result.movements[key] = bytes end
end
for key, value in pairs(out.text) do
  if ours(key) then result.text[key] = value end
end
local n = { scripts = 0, text = 0, movements = 0 }
for k in pairs(n) do for _ in pairs(result[k]) do n[k] = n[k] + 1 end end
print(("story: %d maps, %d scripts, %d texts, %d movements"):format(
  #mapIds, n.scripts, n.text, n.movements))
local fh = assert(io.open(outPath, "wb"))
fh:write(LuaWriter.encode(result))
fh:close()
