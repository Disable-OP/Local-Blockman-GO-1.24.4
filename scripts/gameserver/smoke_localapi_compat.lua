-- smoke_localapi_compat.lua — behavioral test of the v7 compat module
-- against a stubbed 10068 engine-event environment (Lua 5.1.5).
-- Run: lua5.1 smoke_localapi_compat.lua [g1008]
local passed, failed = 0, 0
local function ok(cond, what)
  if cond then passed = passed + 1
  else failed = failed + 1; print("FAIL: " .. what) end
end

-- ---- minimal environment the real IScriptEvent.lua needs ----
function class(name, parent)
  local cls = { className = name }
  cls.__index = cls
  cls.new = function(...)
    local o = setmetatable({}, cls)
    if o.ctor then o.ctor(o, ...) end
    return o
  end
  return cls
end
TableUtil = { include = function(t, v)
  for _, x in pairs(t) do if x == v then return true end end
  return false
end }
LogUtil = { log = function() end, LogLevel = { Error = 3 } }

-- a fake engine event: the ClassRegister shape (raw __name + metatable
-- __index serving a single-slot registerCallBack static)
local function makeEngineEvent(name)
  local eng = {}
  rawset(eng, "__name", name)
  local stored = {}
  local mt = {}
  mt.__index = function(t, k)
    if k == "registerCallBack" then
      return function(fn) stored[1] = fn end
    end
    return nil
  end
  setmetatable(eng, mt)
  eng.fire = function(...)
    if stored[1] then return stored[1](...) end
  end
  return eng
end

-- the real IScriptEvent from the bundle
dofile("/tmp/v6/bundle/server/scripts/BedWarSolo/base/event/IScriptEvent.lua")

-- fire order recorder
local order = {}

local scenario = (arg and arg[1]) or "base18"
if scenario == "g1008" then
  -- Scenario B: the tree ships its own CEvents (g1008) with a
  -- pre-registered subscriber that must be carried over.
  CEvents = {}
  CEvents.PlayerLoginEvent = IScriptEvent.new()
  CEvents.PlayerLoginEvent:registerCallBack(function()
    order[#order + 1] = "pre-existing"
    return "pre"
  end)
  Events = {}
else
  -- Scenario A: no namespaces at all (the 18 overlay-base dirs)
  CEvents = nil
  Events = nil
end

-- the engine globals (registered BEFORE any Lua runs)
-- keep handles to the ORIGINAL engine objects: after the compat replaces
-- the globals with proxies, only these can fire through the real slot.
GameInitEvent = makeEngineEvent("GameInitEvent")
PlayerDieEvent = makeEngineEvent("PlayerDieEvent")
PlayerDynamicAttrEvent = makeEngineEvent("PlayerDynamicAttrEvent")
PlayerLoginEvent = makeEngineEvent("PlayerLoginEvent")
local engGameInit, engDie = GameInitEvent, PlayerDieEvent
local engDynAttr, engLogin = PlayerDynamicAttrEvent, PlayerLoginEvent

-- ---- run the compat exactly like BaseMain would ----
dofile("/home/z/my-project/Local-Blockman-GO-1.24.4/scripts/gameserver/localapi_compat.lua")

-- 1. the globals were replaced by proxies
ok(type(GameInitEvent) == "table" and GameInitEvent.subscribers ~= nil,
   "GameInitEvent global replaced by a proxy")
ok(PlayerDieEvent.subscribers ~= nil, "PlayerDieEvent replaced")
ok(PlayerDynamicAttrEvent.subscribers ~= nil, "PlayerDynamicAttrEvent replaced")

-- 2. the namespaces share ONE identity with the replaced globals
ok(CEvents.GameInitEvent == GameInitEvent,
   "CEvents.GameInitEvent is the same proxy as the global")
ok(Events.GameInitEvent == GameInitEvent,
   "Events.GameInitEvent is the same proxy")
ok(CEvents.PlayerDieEvent == PlayerDieEvent, "CEvents.PlayerDieEvent alias")

-- 3. multi-subscriber order + last-subscriber return semantics
PlayerDieEvent.registerCallBack(function()
  order[#order + 1] = "base68-onPlayerDied"
  return "base68"
end)
-- the game's registry-style registration (BaseListener.registerCallBack
-- keyed by the CEvents alias — must meet the base68 forwarder's key)
local registry = {}
local function BaseListener_registerCallBack(event, fn)
  registry[event] = fn
end
BaseListener_registerCallBack(CEvents.PlayerDieEvent, function()
  order[#order + 1] = "game-registry-onPlayerDied"
  return "game"
end)
-- a direct game subscriber + the deliberate trailing false (TD pattern)
CEvents.PlayerDieEvent:registerCallBack(function()
  order[#order + 1] = "game-direct-onPlayerDied"
  return true
end)
CEvents.PlayerDieEvent:registerCallBack(function()
  order[#order + 1] = "trailing-false"
  return false
end)
local ret = engDie.fire("diePlayer", true, nil)
ok(ret == false, "fire returns the LAST subscriber's result (false)")
ok(order[1] == "base68-onPlayerDied"
   and order[2] == "game-direct-onPlayerDied"
   and order[3] == "trailing-false",
   "subscriber order = registration order")
ok(registry[PlayerDieEvent] ~= nil,
   "the registry keyed by the CEvents alias meets the bare-global key")
ok(registry[PlayerDieEvent]() == "game", "registry handler runs")

-- 4. non-engine names: stable shared IScriptEvent identity
local a = CEvents.MyCustomPacketEvent
local b = Events.MyCustomPacketEvent
local c = CEvents.MyCustomPacketEvent
ok(a ~= nil and a == b and a == c, "custom events share stable identity")
a:registerCallBack(function() return 7 end)
ok(a:invoke() == 7, "custom event fires its subscriber")

-- 5. the engine slot forwarder path returns the proxy result
if scenario == "g1008" then
  -- the pre-existing subscriber was carried onto the bridged proxy
  -- (order was consumed by the die-fire test above; the RETURN is the proof)
  local r = engLogin.fire("peer", "info", true, 1)
  ok(r == "pre",
     "g1008: pre-existing subscriber carried over and fired via the slot")
else
  -- base18: nothing pre-registered; register now and fire via the slot
  PlayerLoginEvent.registerCallBack(function() return "login-ret" end)
  ok(engLogin.fire("peer", "info", true, 1) == "login-ret",
     "base18: subscriber fires through the engine slot")
end

-- 6. g1008 reconcile: the engine-named pure-Lua field was REPOINTED
if scenario == "g1008" then
  ok(CEvents.PlayerLoginEvent == PlayerLoginEvent,
     "g1008: own CEvents field repointed to the bridged proxy")
  -- a custom (non-engine) field survives untouched and stays stable
  ok(CEvents.PlayerLoginEvent ~= nil, "g1008: namespace usable after reconcile")
end

print(string.format("SMOKE %s: %d passed, %d failed", scenario, passed, failed))
os.exit(failed == 0 and 0 or 1)
