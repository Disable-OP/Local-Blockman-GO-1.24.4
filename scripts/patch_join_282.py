#!/usr/bin/env python3
"""patch_join_282.py — take over the 2.8.2 hall join's LOCAL boot and turn
it into the ONLINE join into the on-device GameServer room.

THE 2.8.2 DECODE (cron session, apktool_out + jadx_out at /home/z/bg282):
- com/sandboxol/blockymods/view/activity/join/v.smali is the join dialog
  view model (the 1.24.4 va$b equivalent). Its PRIVATE
  a(MiniGameToken)V is THE local gate — it builds the EnterRealmsResult
  with setGameAddr(this.f == null ? "" : f.getGameAddr()) (gameAddr="" =
  the local-world boot, client.log `initGame ip[] port[0]`) and calls
  StartMc.startGame(activity, result).
- The ONLINE variant, a(Dispatch, Z), copies dispatch.gAddr into the
  result — the same fields the engine consumes. The takeover bridges the
  local gate to that online shape (JoinBridge builds the result from
  GameServerManager's live room).
- Call graph: the private a(MiniGameToken)V has EXACTLY ONE caller —
  v's own b(MiniGameToken, I, J)V (the res-ready path, smali line ~1349,
  invoke-direct). No synthetic accessors target it. Renaming the original
  to a_local and adding a NEW private a(MiniGameToken)V therefore reroutes
  every caller through the bridge automatically.
- The whole bridge call sits in a try/catch whose handler logs
  "JoinBridge: smali bridge threw -> local fallback: ..." (tag LocalAPI)
  and falls back to a_local — a bridge failure can NEVER crash the join.

THE BRIDGE (classes8.dex in the 2.8.2 build):
  JoinBridge.takeOverJoin(context, gameEntity) — the 2nd param is Object
  (the server dex compiles against android-stubs alone; the smali passes
  the Game ref into an Object slot). JoinBridge does the hosted-only
  check (g1046/g1008), the gaddr gate + honest toast, the attr pushes and
  the reflection startOnlineGame — line-aware since the 2.8.2 dex
  (2-arg static StartMc.startGame; 1.24.4 uses the 4-arg instance form).

Idempotent, pure ASCII, latin-1-safe (repo lesson: scripts write latin-1).
"""
import re
import sys
from pathlib import Path

APKTOOL_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/home/z/bg282/apktool_out")

TARGET_NAME = "v.smali"
TARGET_DIR_PART = "com/sandboxol/blockymods/view/activity/join"
V_CLASS = "Lcom/sandboxol/blockymods/view/activity/join/v;"
M_TOKEN = "Lcom/sandboxol/center/entity/MiniGameToken;"
F_CTX = ("Lcom/sandboxol/blockymods/view/activity/join/EnterGameActivity;")
F_GAME = "Lcom/sandboxol/greendao/entity/Game;"

NEW_METHOD = """.method private a(LOKCOMPAT_TOKEN;)V
    .locals 3

    :try_start_bridge
    iget-object v0, p0, LOKV;->a:LOKCTX;
    iget-object v1, p0, LOKV;->b:LOKGAME;
    invoke-static {v0, v1}, Lcom/localapi/JoinBridge;->takeOverJoin(Landroid/content/Context;Ljava/lang/Object;)Z
    move-result v2
    if-eqz v2, :cond_join_local
    return-void
    :try_end_bridge
    .catch Ljava/lang/Throwable; {:try_start_bridge .. :try_end_bridge} :catch_bridge

    :catch_bridge
    move-exception v2
    invoke-virtual {v2}, Ljava/lang/Throwable;->toString()Ljava/lang/String;
    move-result-object v1
    const-string v2, "JoinBridge: smali bridge threw -> local fallback: "
    invoke-virtual {v2, v1}, Ljava/lang/String;->concat(Ljava/lang/String;)Ljava/lang/String;
    move-result-object v1
    const-string v2, "LocalAPI"
    invoke-static {v2, v1}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I
    goto :cond_join_local

    :cond_join_local
    invoke-direct {p0, p1}, LOKV;->a_local(LOKCOMPAT_TOKEN;)V
    return-void
.end method
""".replace("LOKV;", V_CLASS).replace("LOKCTX;", F_CTX) \
   .replace("LOKGAME;", F_GAME).replace("LOKCOMPAT_TOKEN;", M_TOKEN)


def main():
    if not APKTOOL_DIR.is_dir():
        sys.exit(f"error: {APKTOOL_DIR} not found")
    targets = [p for p in APKTOOL_DIR.rglob(TARGET_NAME)
               if TARGET_DIR_PART in str(p).replace("\\", "/")]
    if not targets:
        sys.exit(f"error: no {TARGET_NAME} under {TARGET_DIR_PART} in "
                 f"{APKTOOL_DIR}")

    patched = 0
    for path in targets:
        data = path.read_bytes().decode("latin-1")
        if "a_local" in data or "JoinBridge" in data:
            print(f"patch_join_282: {path.name} already patched, skipping")
            continue

        # 1. rename the original private a(MiniGameToken) -> a_local
        header_re = re.compile(
            r"^(\.method[^\r\n]*?\sa)\(" + re.escape(M_TOKEN) + r"\)V(\s*)$",
            re.M)
        data, n = header_re.subn(
            r"\1_local(" + M_TOKEN + r")V\2", data)
        if n == 0:
            print(f"WARNING: {path}: a(MiniGameToken) header not found "
                  f"- no patch applied")
            continue
        if n > 1:
            sys.exit(f"FATAL: {path}: {n} matching a(MiniGameToken) headers "
                     f"- refusing to guess")

        # 2. append the takeover method — every existing invoke-direct to
        #    a(MiniGameToken) now resolves to the BRIDGE (same name, still
        #    private), and the bridge falls through to a_local.
        if not data.endswith("\n"):
            data += "\n"
        data += NEW_METHOD

        path.write_bytes(data.encode("latin-1"))
        patched += 1
        print(f"patch_join_282: {path} patched (a->a_local + JoinBridge "
              f"takeover)")
    if patched == 0:
        print("patch_join_282: nothing to do (all targets already patched)")
    print(f"patch_join_282: done ({patched} file(s))")


if __name__ == "__main__":
    main()
