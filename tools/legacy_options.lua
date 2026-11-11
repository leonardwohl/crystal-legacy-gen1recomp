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
        elseif row.type == "choice" and type(row.choices) == "table" and #row.choices > 0 then
          local function at()
            local v = current(entry, row)
            for i, c in ipairs(row.choices) do if c[2] == v then return i end end
            return 1
          end
          rows[#rows + 1] = {
            label = row.label,
            value = function() return tostring(row.choices[at()][1]) end,
            step = function(game, dir)
              local n = #row.choices
              save(game, id, row.key, row.choices[(at() - 1 + (dir or 1)) % n + 1][2])
            end,
          }
        end
      end
    end
    return rows
  end

  local function selectable(rows, i) return rows[i] and not rows[i].header end

  -- Drawn the way Crystal's own OPTIONS screen is (src/ui/gen2/OptionsMenu.lua
  -- drawPanel): one textbox frame, each setting a label line with ":VALUE"
  -- under it, each mod's name as a plain heading line.
  local FIRST_LINE, VISIBLE, ARROW_LINE = 2, 7, 16

  local function newScreen(game)
    local Chrome = require("src.ui.gen2.Chrome")
    local Marquee = require("src.ui.Marquee")
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
    local function keepVisible(self)
      -- A setting at the top of the view keeps its heading above it.
      local top = self.index
      if self.rows[top - 1] and self.rows[top - 1].header then top = top - 1 end
      if top <= self.scroll then self.scroll = top - 1 end
      if self.index > self.scroll + VISIBLE then self.scroll = self.index - VISIBLE end
      self.scroll = math.max(0, math.min(self.scroll, math.max(0, #self.rows - VISIBLE)))
    end
    keepVisible(screen)
    function screen:update()
      local input = self.game.input
      if input:wasPressed("up") then
        move(self, -1)
      elseif input:wasPressed("down") then
        move(self, 1)
      elseif input:wasPressed("left") or input:wasPressed("right") or input:wasPressed("a") then
        local row = self.rows[self.index]
        local dir = input:wasPressed("left") and -1 or 1
        if row and row.step then row.step(self.game, dir) end
      elseif input:wasPressed("b") then
        self.game.stack:pop()
        return
      end
      keepVisible(self)
    end
    local function fit(text, col, hot, key)
      local room = 19 - col
      if hot then return Marquee.scroll(text, room, key) end
      return Marquee.clip(text, room)
    end
    function screen:drawPanel()
      Chrome.clear()
      Chrome.textbox(0, 0, Chrome.SCREEN_W - 2, Chrome.SCREEN_H - 2)
      local y, cursorY = FIRST_LINE, nil
      for i = self.scroll + 1, math.min(#self.rows, self.scroll + VISIBLE) do
        local row = self.rows[i]
        local hot = i == self.index
        if row.header then
          Chrome.print(fit(row.label, 1, false, row.label), 1, y)
        else
          if hot then cursorY = y end
          Chrome.print(fit(row.label, 2, hot, row.label), 2, y)
          local ok, text = pcall(row.value, self.game)
          Chrome.print(":", 10, y + 1)
          Chrome.print(fit(ok and tostring(text) or "?", 11, hot, row.label), 11, y + 1)
        end
        y = y + 2
      end
      if cursorY then Chrome.cursor(1, cursorY) end
      if self.scroll + VISIBLE < #self.rows then
        love.graphics.setColor(0, 0, 0, 1)
        require("src.render.Font").drawCode(Chrome.DOWN_ARROW, 8, ARROW_LINE * 8)
      end
    end
    function screen:draw() self:drawPanel() end
    function screen:wantsFillScale() return true end
    function screen:drawsWidescreen() return true end
    function screen:drawWidescreen(winW, winH)
      local G = love.graphics
      Chrome.letterbox(winW, winH, 1, 1, 1)
      local scale = Chrome.fitScale(winW, winH)
      G.push()
      G.translate(Chrome.fitOrigin(winW, winH, scale))
      G.scale(scale, scale)
      self:drawPanel()
      G.pop()
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
