-- =====================================================================
-- localapi-compat (bundle g10078 v7) — run the 10078-generation script
-- trees on the 10068 libgameserver. Required by base/BaseMain.lua right
-- BEFORE BaseListener:init() in every scriptdir of the bundle.
--
-- THE TWO GAPS (proven from the engine sources + the shipped binary):
--
-- (1) THE DISPATCH GAP. The 10068 engine fires a script event by calling
--     the ONE Lua callback stored on its C++ event object
--     (ClassRegister::lua_setglobal exposes each event as a global table
--     whose registerCallBack static member stores that callback; the
--     shipped libgameserver contains NO "onScriptEvent" string — the
--     10078 engine's by-name CEvents dispatch does not exist here).
--     The 10078-generation trees register their handlers on
--     CEvents.<Name>/Events.<Name> (pure-Lua IScriptEvent lists, with
--     MULTI-subscriber semantics and last-subscriber return), so with
--     the stock wiring NOTHING ever fires: GameInit never runs, logins
--     are never handled — every room is event-dead.
--
-- (2) THE NAMESPACE GAP. 18 of 19 scriptdirs never ship the CEvents /
--     Events namespaces at all (their plugin engine_base trees are
--     deliberately unwired); only g1008 defines them (its own wired
--     engine_base/event/Events.lua). ScriptMain.lua of the v3 family
--     dereferences CEvents.GameInitEvent at LOAD time -> nil-index death.
--
-- THE FIX (this module):
--   * Scan _G for the engine event objects (signature: a table whose
--     raw "__name" equals its global name and whose registerCallBack
--     resolves to a function through the class metatable).
--   * For each: take the engine's single dispatch slot ONCE with a
--     forwarder into a fresh IScriptEvent PROXY, then REPLACE the global
--     with the proxy. Every later Lua-side registration — the base68
--     BaseListener:init() direct registrations AND the game trees'
--     CEvents.*/Events.* registrations AND bare-global registrations —
--     lands in the proxy's subscriber list, so the proven 1.24.4
--     handlers and the 10078 game handlers run IN REGISTRATION ORDER
--     with the official last-subscriber return semantics (TD's
--     deliberate trailing `return false` on PlayerDieEvent works).
--   * Provide CEvents/Events as lazy namespaces sharing ONE proxy cache:
--     an engine-named field resolves to the same proxy the global was
--     replaced with (so `BaseListener.registerCallBack(CEvents.X, fn)`
--     meets the base68 forwarders' `BaseListener.callbacks[X]` lookups —
--     same table = same key); any other name gets a stable IScriptEvent
--     (custom/packet events fired Lua-side).
--   * For trees that ship their OWN CEvents (g1008): repoint the
--     engine-named fields to the proxies, carrying any pre-registered
--     subscribers over, and add the same lazy __index.
--
-- Everything is pcall-guarded; on any failure the affected piece is left
-- untouched (the module goes inert rather than breaking the boot).
-- =====================================================================

if type(IScriptEvent) ~= "table" then
  local ok1 = pcall(require, "base.event.IScriptEvent")
  if not ok1 or type(IScriptEvent) ~= "table" then
    pcall(require, "engine_base.event.IScriptEvent")
  end
end
if type(IScriptEvent) ~= "table" or type(IScriptEvent.new) ~= "function" then
  -- Cannot build the bridge without the event class; stay inert.
  return
end

-- name -> the proxy every route (global, CEvents, Events) must share.
local proxyCache = {}

local function isEngineEvent(v)
  if type(v) ~= "table" then return false end
  if type(rawget(v, "__name")) ~= "string" then return false end
  local ok, r = pcall(function() return v.registerCallBack end)
  return ok and type(r) == "function"
end

-- 1) scan + bridge + replace (runs FIRST so later registrations —
--    BaseListener:init() included — land in the proxies).
--
-- The proxy is a real IScriptEvent instance with ONE instance-field
-- override: registerCallBack accepts BOTH call conventions — the
-- engine's dot static `Event.registerCallBack(fn)` (every base68 +
-- game-tree registration uses this; a plain IScriptEvent would silently
-- swallow it because the method would see fn as self and callback=nil)
-- and the IScriptEvent method `Event:registerCallBack(fn)`.

local function makeProxy()
  local proxy = IScriptEvent.new()
  local realRegister = proxy.registerCallBack
  local realUnregister = proxy.unregisterCallBack
  proxy.registerCallBack = function(a, b)
    if b ~= nil then return realRegister(proxy, b) end
    return realRegister(proxy, a)
  end
  proxy.unregisterCallBack = function(a, b)
    if b ~= nil then return realUnregister(proxy, b) end
    return realUnregister(proxy, a)
  end
  return proxy
end

do
  local engineEvents = {}
  for name, value in pairs(_G) do
    if type(name) == "string" and isEngineEvent(value) then
      engineEvents[name] = value
    end
  end
  for name, eng in pairs(engineEvents) do
    local proxy = makeProxy()
    local ok = pcall(function()
      eng.registerCallBack(function(...) return proxy:invoke(...) end)
    end)
    if ok then
      proxyCache[name] = proxy
      rawset(_G, name, proxy)
    end
    -- on failure: leave the global alone; the namespace below will then
    -- alias the raw engine object (single-slot — the 1.24.4 behavior).
  end
end

-- 2) the lazy namespace factory (shared proxyCache = shared identity).
local function namespaceIndex(t, k)
  if type(k) ~= "string" then return nil end
  local v = proxyCache[k]
  if v == nil then
    v = IScriptEvent.new()
    proxyCache[k] = v
  end
  rawset(t, k, v)
  return v
end

local function makeNamespace()
  local ns = {}
  setmetatable(ns, { __index = namespaceIndex })
  return ns
end

-- 3) trees with their own CEvents/Events (g1008): repoint engine-named
--    pure-Lua fields to the proxies (carrying subscribers), then add the
--    lazy __index for names the official Events.lua never pre-created.
local function reconcile(ns)
  if type(ns) ~= "table" then return end
  if getmetatable(ns) == nil then
    for k, v in pairs(ns) do
      if type(k) == "string" and proxyCache[k] ~= nil and v ~= proxyCache[k] then
        if type(v) == "table" and type(v.subscribers) == "table" then
          for _, fn in ipairs(v.subscribers) do
            pcall(function() proxyCache[k]:registerCallBack(fn) end)
          end
        end
        rawset(ns, k, proxyCache[k])
      end
    end
    setmetatable(ns, { __index = namespaceIndex })
  end
end

if type(CEvents) ~= "table" then
  CEvents = makeNamespace()
else
  reconcile(CEvents)
end
if type(Events) ~= "table" then
  Events = makeNamespace()
else
  reconcile(Events)
end
