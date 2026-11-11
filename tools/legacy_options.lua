-- BEGIN legacy_options (shared; edit tools/legacy_options.lua, not a copy)
-- One "CRYSTAL LEGACY" row in the pause OPTIONS menu, opening a page with the
-- settings of every installed Legacy mod. Each mod still defines its settings
-- with mod.options:define, so the MODS menu keeps showing them per mod; both
-- views save through ManagerState:setOption, the same storage, so they agree.
--
-- Mods cannot load each other's files, so every Legacy mod with settings
-- carries this block and registers into a table on the ManagerState module.
-- Whichever loads first installs the row and the page; later ones only add
-- their settings to the table.
local function legacyOptionsPage(mod, schema, label)
  local okM, ManagerState = pcall(require, "src.mods.ManagerState")
  if not (okM and type(ManagerState) == "table") then return end
  local reg = rawget(ManagerState, "__crystalLegacyOptions")
  -- A mod registering twice means the mods were reloaded: start over, so the
  -- row and the page are installed into the new load.
  if not reg or reg.mods[mod.id] then
    reg = { mods = {}, installed = false }
    ManagerState.__crystalLegacyOptions = reg
  end
  reg.mods[mod.id] = { label = label, schema = schema, mod = mod }
  if reg.installed then return end
  reg.installed = true

  local SCREEN = "CrystalLegacyOptions"

  local function current(entry, row)
    local v = entry.mod.options:get(row.key)
    if v == nil then v = row.default end
    return v
  end

  local function save(game, modId, key, value)
    -- ManagerState's own setter, so the MODS menu sees the same value.
    local proxy = setmetatable({ game = game }, { __index = ManagerState })
    local ok = pcall(ManagerState.setOption, proxy, modId, key, value)
    return ok
  end

  local function buildRows()
    local ids = {}
    for id in pairs(reg.mods) do ids[#ids + 1] = id end
    table.sort(ids, function(a, b) return reg.mods[a].label < reg.mods[b].label end)
    local rows = {}
    for _, id in ipairs(ids) do
      local entry = reg.mods[id]
      rows[#rows + 1] = { header = true, label = entry.label,
        value = function() return "" end }
      for _, row in ipairs(entry.schema) do
        if row.type == "toggle" then
          rows[#rows + 1] = {
            label = row.label,
            value = function() return current(entry, row) and "ON" or "OFF" end,
            step = function(game) save(game, id, row.key, not current(entry, row)) end,
          }
        end
      end
    end
    return rows
  end

  local function selectable(rows, i) return rows[i] and not rows[i].header end

  local function newScreen(game)
    local OptionRows = require("src.ui.OptionRows")
    local rows = buildRows()
    local screen = { game = game, rows = rows, index = 1, scroll = 0, isOpaque = true }
    while screen.index < #rows and not selectable(rows, screen.index) do
      screen.index = screen.index + 1
    end
    local function move(self, dir)
      local n = #self.rows
      for _ = 1, n do
        self.index = (self.index - 1 + dir) % n + 1
        if selectable(self.rows, self.index) then return end
      end
    end
    function screen:update()
      local input = self.game.input
      if input:wasPressed("up") then
        move(self, -1)
      elseif input:wasPressed("down") then
        move(self, 1)
      elseif input:wasPressed("left") or input:wasPressed("right") or input:wasPressed("a") then
        local row = self.rows[self.index]
        if row and row.step then row.step(self.game) end
      elseif input:wasPressed("b") then
        self.game.stack:pop()
        return
      end
      self.scroll = OptionRows.clampScroll(self.index, self.scroll, #self.rows, nil)
    end
    function screen:draw()
      OptionRows.draw(self.game, self.rows, self.index, self.scroll, "A/<>:CHANGE B:DONE")
    end
    return screen
  end

  pcall(mod.content.screens.register, mod.content.screens, SCREEN, { new = newScreen })
  reg.newScreen = newScreen -- for tests

  mod.hooks:wrap("ui.options.rows", function(nextFn, game, rows)
    local out = nextFn(game, rows)
    if type(out) ~= "table" then return out end
    local row = {
      id = "crystal_legacy:options",
      label = "CRYSTAL LEGACY",
      value = function() return "OPEN" end,
      activate = function(g) require("src.ui.Screens").push(g, SCREEN) end,
    }
    if mod.ui and type(mod.ui.insertBefore) == "function" then
      return mod.ui.insertBefore(out, "MODS", row)
    end
    out[#out + 1] = row
    return out
  end)
end
-- END legacy_options
