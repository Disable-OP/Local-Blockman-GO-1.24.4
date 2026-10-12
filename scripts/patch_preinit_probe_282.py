#!/usr/bin/env python3
"""patch_preinit_probe_282.py — instrument the 2.8.2 engine-join Java
surface (EchoesRenderer) with logcat probes.

The engine-integration stall (cron sessions 2026-10-12, delta 8): the
10078 engine process survives the whole drive (the out-of-process USER_NOTIF
supervisor defeats every TSS layer) but initGame to 127.0.0.1:31108 never
fires, no client.log is ever created and the native thread farm never
appears. The client-side chain markers stop at "BlockManEchoesActivity is
up" — whether handlePreInit is even REACHED, with WHICH paths, and whether
the join attrs (gameAddr) reach the engine is UNPROVEN.

This patch drops Log.i probes (tag "EchoesProbe") at the exact chain
points inside com/sandboxol/blockmango/EchoesRenderer.smali:

  1. handlePreInit ENTER      — the 4 string args + the boolean (p0..p4).
  2. handlePreInit env dump   — language + the AbstractEngineEnv paths the
                                native side is about to receive: resRoot,
                                resCache, config, mapRoot, mapTemp,
                                engineResBaseUrl. A wrong/missing dir here
                                IS the stall.
  3. nativePreInit CALL x2    — which branch (old-engine vs new-engine)
                                actually invokes the native pre-init.
  4. handleInitGame entry     — gameAddr (p6, the "ip:port" string the
                                wrapper splits; EMPTY = the local-world
                                boot) + p2/p15 for the join-attr shape.
  5. handleInitGame offline   — the isGLValid()==false early exit (a
                                redroid guest-GPU failure would land here).
  6. handleInitGame empty-addr — the p6=="" branch marker.

Registers are audited against the method bodies: every probe register is
dead/scratch at its insertion point (v0/v2/v8/v10 before the handlePreInit
branch; v0..v31 written-before-read at the handleInitGame entry; v0 at the
two inner markers). Param registers p>=6 in handleInitGame are copied into
low registers with move-object/from16 before use (4-bit invoke limit).

Idempotent: re-runs detect the existing probes. The build script
sanity-checks for the "EchoesProbe" tag.
"""
import sys

TREE = sys.argv[1] if len(sys.argv) > 1 else "/home/z/bg282/apktool_out"
PATH = TREE + "/smali/com/sandboxol/blockmango/EchoesRenderer.smali"

src = open(PATH).read()
if "EchoesProbe" in src:
    print("patch_preinit_probe_282: probes already present")
    sys.exit(0)

def replace_once(s, old, new, what):
    if s.count(old) != 1:
        print("FATAL: anchor %r matches %d times (expected 1)"
              % (what, s.count(old)))
        sys.exit(1)
    return s.replace(old, new, 1)

# ---------------------------------------------------------------- probe 1
# handlePreInit ENTER: p0..p4. At entry v0/v1/v2 are unwritten (the first
# real assignments come after). v0=builder, v1=const/toString scratch.
PREINIT_HEAD = """.method public static handlePreInit(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Z)V
    .locals 11

    .line 1
    invoke-static {}, Lcom/sandboxol/center/router/moduleInfo/game/EngineEnv;->getCurUseEngineTypeInGame()I"""
PREINIT_HEAD_NEW = """.method public static handlePreInit(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Z)V
    .locals 11

    # JBPROBE: handlePreInit reached - dump the raw args
    new-instance v0, Ljava/lang/StringBuilder;
    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V
    const-string v1, "preInit ENTER p0="
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v0, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v1, " p1="
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v0, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v1, " p2="
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v0, p2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v1, " p3="
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v0, p3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v1, " p4="
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v0, p4}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v1
    const-string v0, "EchoesProbe"
    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 1
    invoke-static {}, Lcom/sandboxol/center/router/moduleInfo/game/EngineEnv;->getCurUseEngineTypeInGame()I"""
src = replace_once(src, PREINIT_HEAD, PREINIT_HEAD_NEW, "handlePreInit head")

# ---------------------------------------------------------------- probe 2
# env dump after v9 (engineResBaseUrl) is computed, BEFORE isOldEngine.
# Live then: v0(env) v1(lang) v3..v7 v9. Dead: v2 v8 v10.
# v10 = builder, v2 = const scratch, v8 = toString result.
ENV_ANCHOR = """    invoke-virtual {v0}, Lcom/sandboxol/center/router/moduleInfo/game/AbstractEngineEnv;->getEngineResBaseUrl()Ljava/lang/String;

    move-result-object v9

    .line 9
    invoke-virtual {v0}, Lcom/sandboxol/center/router/moduleInfo/game/AbstractEngineEnv;->isOldEngine()Z"""
ENV_NEW = """    invoke-virtual {v0}, Lcom/sandboxol/center/router/moduleInfo/game/AbstractEngineEnv;->getEngineResBaseUrl()Ljava/lang/String;

    move-result-object v9

    # JBPROBE: the env paths the native pre-init is about to receive
    new-instance v10, Ljava/lang/StringBuilder;
    invoke-direct {v10}, Ljava/lang/StringBuilder;-><init>()V
    const-string v2, "preInit env: lang="
    invoke-virtual {v10, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v10, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v2, " p0="
    invoke-virtual {v10, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v10, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v2, " resRoot="
    invoke-virtual {v10, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v10, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v2, " resCache="
    invoke-virtual {v10, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v10, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v2, " cfg="
    invoke-virtual {v10, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v10, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v2, " mapRoot="
    invoke-virtual {v10, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v10, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v2, " mapTemp="
    invoke-virtual {v10, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v10, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v2, " resBase="
    invoke-virtual {v10, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v10, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v10}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v8
    const-string v2, "EchoesProbe"
    invoke-static {v2, v8}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 9
    invoke-virtual {v0}, Lcom/sandboxol/center/router/moduleInfo/game/AbstractEngineEnv;->isOldEngine()Z"""
src = replace_once(src, ENV_ANCHOR, ENV_NEW, "handlePreInit env anchor")

# ---------------------------------------------------------------- probe 3
# the two nativePreInit call sites (v0 is dead inside both branches).
OLD_CALL = """    move-object v7, p2

    move-object v2, p0

    move-object v8, p3

    move v10, p4

    .line 10
    invoke-static/range {v1 .. v10}, Lcom/sandboxol/blockmango/EchoesRenderer;->nativePreInit("""
OLD_CALL_NEW = """    move-object v7, p2

    move-object v2, p0

    move-object v8, p3

    move v10, p4

    const-string v0, "EchoesProbe: nativePreInit CALL (old-engine branch)"
    invoke-static {v0, v0}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 10
    invoke-static/range {v1 .. v10}, Lcom/sandboxol/blockmango/EchoesRenderer;->nativePreInit("""
src = replace_once(src, OLD_CALL, OLD_CALL_NEW, "old-engine call site")

NEW_CALL = """    :cond_1
    move-object v2, p0

    move-object v8, p1

    move v10, p4

    .line 11
    invoke-static/range {v1 .. v10}, Lcom/sandboxol/blockmango/EchoesRenderer;->nativePreInit("""
NEW_CALL_NEW = """    :cond_1
    move-object v2, p0

    move-object v8, p1

    move v10, p4

    const-string v0, "EchoesProbe: nativePreInit CALL (new-engine branch)"
    invoke-static {v0, v0}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 11
    invoke-static/range {v1 .. v10}, Lcom/sandboxol/blockmango/EchoesRenderer;->nativePreInit("""
src = replace_once(src, NEW_CALL, NEW_CALL_NEW, "new-engine call site")

# ---------------------------------------------------------------- probe 4
# handleInitGame entry: gameAddr p6 + p2 + p15. v0..v31 are all
# written-before-read after the entry move, so v0=builder, v2/v3 scratch.
INIT_HEAD = """.method public handleInitGame(FLjava/lang/String;JLjava/lang/String;Ljava/lang/String;JLjava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;IILjava/lang/String;IZZLjava/lang/String;)V
    .locals 32

    move-object/from16 v1, p0

    .line 3
    :try_start_0"""
INIT_HEAD_NEW = """.method public handleInitGame(FLjava/lang/String;JLjava/lang/String;Ljava/lang/String;JLjava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;IILjava/lang/String;IZZLjava/lang/String;)V
    .locals 32

    move-object/from16 v1, p0

    # JBPROBE: the engine was asked to initGame - dump the join attrs
    move-object/from16 v2, p6
    new-instance v0, Ljava/lang/StringBuilder;
    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V
    const-string v3, "initGame: gameAddr(p6)="
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v3, " p2="
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-object/from16 v2, p2
    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v3, " p15="
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-object/from16 v2, p15
    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v2
    const-string v0, "EchoesProbe"
    invoke-static {v0, v2}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 3
    :try_start_0"""
src = replace_once(src, INIT_HEAD, INIT_HEAD_NEW, "handleInitGame head")

# ---------------------------------------------------------------- probe 5
# the offline (GL invalid) early exit - v0 is scratch right there.
OFFLINE = """    if-nez v0, :cond_0

    const-string v0, "offline"

    .line 4
    invoke-static {v0}, Lcom/sandboxol/blockmango/EchoesHelper;->onGameExit(Ljava/lang/String;)V"""
OFFLINE_NEW = """    if-nez v0, :cond_0

    const-string v0, "EchoesProbe: initGame offline-exit (GL invalid)"
    invoke-static {v0, v0}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    const-string v0, "offline"

    .line 4
    invoke-static {v0}, Lcom/sandboxol/blockmango/EchoesHelper;->onGameExit(Ljava/lang/String;)V"""
src = replace_once(src, OFFLINE, OFFLINE_NEW, "offline exit")

# ---------------------------------------------------------------- probe 6
# the EMPTY gameAddr branch (the local-world boot) - v0 holds "" there.
EMPTY = """    :cond_1
    move-object v10, v0

    const/4 v11, 0x0

    .line 9
    :goto_0"""
EMPTY_NEW = """    :cond_1
    move-object v10, v0

    const/4 v11, 0x0

    const-string v0, "EchoesProbe: initGame gameAddr EMPTY (local-world boot)"
    invoke-static {v0, v0}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 9
    :goto_0"""
src = replace_once(src, EMPTY, EMPTY_NEW, "empty gameAddr branch")

open(PATH, "w").write(src)
print("patch_preinit_probe_282: 6 probe sets inserted into %s" % PATH)
