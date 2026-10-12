#!/usr/bin/env python3
"""patch_event_bridge_v7.py — bundle v7 event-layer repair (docs
10078_GAME_SERVER_UPDATE.md section 20).

Bundle v6 shipped THREE latent event-layer defects, all invisible to the
static gates (parse / require-graph / C++ sweep — none models runtime
globals or dispatch):

1. THE EVENT-DEAD BUNDLE. The 10068 libgameserver dispatches script
   events ONLY to the single Lua callback stored on each engine event
   object (the shipped binary contains zero "onScriptEvent" strings).
   The 10078-generation trees register on CEvents.*/Events.* (pure-Lua
   IScriptEvent lists dispatched by the 10078 engine's by-name path —
   absent here). With the stock wiring NO engine event ever reaches ANY
   room: GameInit never runs, logins are never handled.
2. THE NAMESPACE GAP. 18 of 19 scriptdirs never ship CEvents/Events
   (their plugin engine_base trees are unwired by design); the v3
   family's ScriptMain.lua dereferences CEvents.GameInitEvent at LOAD
   time -> nil-index death. TowerDefense additionally indexes
   Events.ReceiveSumRechargeEvent at init.
3. THE g1008 DECOMPILE DROPOUTS. The 10078-exact appres tree was
   recovered by bytecode decompile; TWO files silently came out EMPTY
   and are required+init'ed by BedWarServer.lua:
     game/listener/PlayerAIListener.lua  (the robot wave chain: attr ->
       AITeamManager:newAi -> GamePlayerAI — without it the 15-bot wave
       is inert on the 2.8.2 line; the 1.24.4 line never noticed because
       its runtime overlay supplies the file at boot)
     game/listener/BlockListener.lua     (the block-policy layer: bed
       break rules, team-area protection, TNT explosion tuning, prop
       blocks, sponge)
   Both restored verbatim from the June-2021 plugin sources (p1046,
   sha256-pinned copies under scripts/gameserver/p1046_sources/) —
   semantically identical to the x1046 appres bytecode (string-inventory
   verified); every global they touch exists in the staged tree with
   identical values (AITeamManager/AIManager differ only in whitespace).

THE FIX (this script, idempotent, per scriptdir):
  * copies scripts/gameserver/localapi_compat.lua to
    <dir>/base/localapi_compat.lua and inserts
    `require "base.localapi_compat"` into <dir>/base/BaseMain.lua right
    before its FIRST `BaseListener:init()` (append at EOF as fallback).
    The compat bridges every engine event into an IScriptEvent proxy,
    replaces the event globals with those proxies, and provides/
    reconciles CEvents + Events — see the module header.
  * for every dir whose base/listener/BaseListener.lua is byte-identical
    to the pristine overlay original (sha256-pinned below), adds the
    [ai-presence] fallback to the PlayerDynamicAttr forwarder: a robot
    attr no game handler claims is materialized as a REAL counted player
    (addEntityPlayerAI + sendLogin + sendReady) — this is what makes the
    g1043/44/45 + g1054 waves (and any future wave) effective in
    AI-unaware rooms; AI-aware rooms (the BedWar family via
    PlayerAIListener) never reach it. g1008 is AI-aware after repair 3
    -> skipped (and its base is a different generation without this
    file anyway).
  * repairs the two g1008 dropouts (only when the target is absent or
    0 bytes — never overwrites a non-empty file).

Usage: patch_event_bridge_v7.py <bundle-server-dir> [--overlay-src DIR]
"""
import hashlib
import os
import shutil
import subprocess
import sys

# The pristine overlay base listener (servergame-bedwar-full.tar.gz ->
# scripts/BedWar/base/listener/BaseListener.lua, CRLF line endings).
OVERLAY_LISTENER_SHA256 = (
    "77699521d5e375315053293caddc40b14426e047fbe4522caa8ff3e5332c3e12"
)
# The June-2021 plugin sources restoring the two g1008 dropouts.
PLAYER_AI_LISTENER_SHA256 = (
    "db71b7cb6dccf61b425ae7c19c7d176b7b8d26830fea449fe6a7e3b5b0640262"
)
BLOCK_LISTENER_SHA256 = (
    "d7d6fc0aef521aecf4d80e7edd2be1e20f70275167407fd2e0c284d21c0a70f1"
)

COMPAT_REQUIRE = 'require "base.localapi_compat"'
COMPAT_MARKER = "localapi-compat"
AI_MARKER = "[ai-presence]"

# CRLF-exact anchors from the overlay original.
ANCHOR = (
    "    local callback = BaseListener.callbacks[PlayerDynamicAttrEvent]\r\n"
    "    if callback then\r\n"
    "        callback(attr)\r\n"
    "    end\r\n"
)
ANCHOR_REPLACEMENT = (
    "    local callback = BaseListener.callbacks[PlayerDynamicAttrEvent]\r\n"
    "    if callback then\r\n"
    "        callback(attr)\r\n"
    "    elseif attr.isRobot then\r\n"
    "        -- [ai-presence] no game handler for this robot attr: materialize\r\n"
    "        -- it as a REAL, counted player (engine AI entity + the synthetic\r\n"
    "        -- login/ready -> the room's own PlayerListener builds the\r\n"
    "        -- GamePlayer), so the room's startPlayers gate sees it. AI-aware\r\n"
    "        -- rooms register a handler and never land here.\r\n"
    "        BaseListener.materializeRobot(attr)\r\n"
    "    end\r\n"
)
TAIL_ANCHOR = "return BaseListener"
MATERIALIZE = (
    "\r\n"
    "-- [ai-presence] (bundle v7): turn one robot attr into a real, counted\r\n"
    "-- player for rooms whose game tree registers no PlayerDynamicAttr\r\n"
    "-- handler. Mirrors GamePlayerControl:ctor's engine calls\r\n"
    "-- (addEntityPlayerAI + sendLogin + sendReady); the game's own\r\n"
    "-- PlayerListener then builds the GamePlayer exactly like a human's.\r\n"
    "local aiPresenceSeq = 0\r\n"
    "local aiPresenceSeen = {}\r\n"
    "function BaseListener.materializeRobot(attr)\r\n"
    "    local userId = attr.userId\r\n"
    "    if not userId or aiPresenceSeen[userId] then\r\n"
    "        return\r\n"
    "    end\r\n"
    "    aiPresenceSeen[userId] = true\r\n"
    "    aiPresenceSeq = aiPresenceSeq + 1\r\n"
    "    local botName = tostring(attr.name or (\"Bot\" .. tostring(aiPresenceSeq)))\r\n"
    "    local seq = aiPresenceSeq\r\n"
    "    local ok, err = pcall(function()\r\n"
    "        EngineWorld:addEntityPlayerAI(VectorUtil.ZERO, botName, seq, function(entity)\r\n"
    "            entity:sendLogin(userId)\r\n"
    "            entity:sendReady()\r\n"
    "        end)\r\n"
    "    end)\r\n"
    "    if not ok then\r\n"
    "        aiPresenceSeen[userId] = nil\r\n"
    "        pcall(function() HostApi.log(\"[ai-presence] materialize failed: \" .. tostring(err)) end)\r\n"
    "    end\r\n"
    "end\r\n"
    "\r\n"
    "return BaseListener"
)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8", "surrogateescape")


def write_text(path, text):
    with open(path, "wb") as f:
        f.write(text.encode("utf-8", "surrogateescape"))


def lua_parse(lpgate, path):
    if not lpgate:
        return True, "lpgate-missing"
    r = subprocess.run([lpgate, path], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()[:200]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    server = os.path.abspath(sys.argv[1])
    scripts = os.path.join(server, "scripts")
    if not os.path.isdir(scripts):
        print("FATAL: no scripts dir under %s" % server)
        sys.exit(1)
    here = os.path.dirname(os.path.abspath(__file__))
    compat_src = os.path.join(here, "localapi_compat.lua")
    if not os.path.isfile(compat_src):
        print("FATAL: %s missing" % compat_src)
        sys.exit(1)
    lpgate = "/tmp/lua_build/lpgate"
    if not os.path.isfile(lpgate):
        lpgate = None

    # optional overlay source dir for pin re-verification
    if "--overlay-src" in sys.argv:
        overlay_src = os.path.abspath(
            sys.argv[sys.argv.index("--overlay-src") + 1])
        ref = os.path.join(overlay_src, "BedWar", "base", "listener",
                           "BaseListener.lua")
        if os.path.isfile(ref):
            got = sha256(ref)
            if got != OVERLAY_LISTENER_SHA256:
                print("FATAL: overlay listener pin mismatch: %s" % got)
                sys.exit(1)

    touched = []       # (relpath) lua files added/modified for the parse gate
    bridged = []
    ai_rooms = []
    repaired = []
    failures = []

    dirs = sorted(
        d for d in os.listdir(scripts)
        if os.path.isdir(os.path.join(scripts, d)))

    for d in dirs:
        sdir = os.path.join(scripts, d)

        # --- 1. the compat bridge into base/ ---
        base_dir = os.path.join(sdir, "base")
        base_main = os.path.join(base_dir, "BaseMain.lua")
        if not os.path.isfile(base_main):
            failures.append("%s: no base/BaseMain.lua" % d)
            continue
        compat_dst = os.path.join(base_dir, "localapi_compat.lua")
        shutil.copyfile(compat_src, compat_dst)
        touched.append(os.path.join(d, "base", "localapi_compat.lua"))

        text = read_text(base_main)
        if COMPAT_REQUIRE in text:
            pass  # already inserted (the require line is the idempotence mark)
        else:
            marker_line = "BaseListener:init()"
            idx = text.find(marker_line)
            if idx >= 0:
                text = text[:idx] + COMPAT_REQUIRE + "\n" + text[idx:]
            else:
                text = text + "\n" + COMPAT_REQUIRE + "\n"
            write_text(base_main, text)
            touched.append(os.path.join(d, "base", "BaseMain.lua"))
        bridged.append(d)

        # --- 2. the ai-presence fallback (overlay-base dirs only) ---
        listener = os.path.join(base_dir, "listener", "BaseListener.lua")
        if os.path.isfile(listener):
            got = sha256(listener)
            lt = read_text(listener)
            if AI_MARKER in lt:
                ai_rooms.append(d + " (already)")
            elif got == OVERLAY_LISTENER_SHA256:
                if ANCHOR in lt and TAIL_ANCHOR in lt:
                    lt = lt.replace(ANCHOR, ANCHOR_REPLACEMENT, 1)
                    lt = lt.replace(TAIL_ANCHOR, MATERIALIZE, 1)
                    write_text(listener, lt)
                    touched.append(os.path.join(
                        d, "base", "listener", "BaseListener.lua"))
                    ai_rooms.append(d)
                else:
                    failures.append("%s: listener anchor not found" % d)
            else:
                failures.append(
                    "%s: base listener pin mismatch (%s)" % (d, got[:12]))

        # --- 3. the g1008 decompile dropouts ---
        if d == "BedWar":
            for rel, want in (
                ("game/listener/PlayerAIListener.lua",
                 PLAYER_AI_LISTENER_SHA256),
                ("game/listener/BlockListener.lua",
                 BLOCK_LISTENER_SHA256),
            ):
                target = os.path.join(sdir, rel)
                cur = sha256(target) if os.path.isfile(target) else None
                if cur == want:
                    repaired.append("%s/%s (already)" % (d, rel))
                    continue
                if cur is not None and os.path.getsize(target) > 0:
                    failures.append(
                        "%s/%s: non-empty but unknown content" % (d, rel))
                    continue
                src = os.path.join(here, "p1046_sources",
                                   os.path.basename(rel))
                if not os.path.isfile(src) or sha256(src) != want:
                    failures.append("%s/%s: pinned source missing" % (d, rel))
                    continue
                shutil.copyfile(src, target)
                touched.append(os.path.join(d, rel))
                repaired.append("%s/%s" % (d, rel))

    # --- 4. parse gate over every file we touched ---
    bad = []
    for rel in touched:
        ok, msg = lua_parse(lpgate, os.path.join(scripts, rel))
        if not ok:
            bad.append("%s: %s" % (rel, msg))

    print("compat bridged: %d dirs (%s)" % (len(bridged), ", ".join(bridged)))
    print("ai-presence: %s" % (", ".join(ai_rooms) if ai_rooms else "NONE"))
    print("repaired: %s" % (repaired if repaired else "none"))
    print("parse gate: %d files%s" % (len(touched),
                                      "" if lpgate else " (lpgate MISSING)"))
    if bad:
        print("PARSE FAILURES:")
        for b in bad:
            print("  ! %s" % b)
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  ! %s" % f)
        sys.exit(1)
    if bad:
        sys.exit(1)
    print("PATCH OK")


if __name__ == "__main__":
    main()
