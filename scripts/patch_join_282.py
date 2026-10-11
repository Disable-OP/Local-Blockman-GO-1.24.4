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

    # ------------------------------------------------------------------
    # THE LIVE GATES (2.8.2 call-graph sweep, later session):
    # StartMc.startGame has EXACTLY THREE callers in the whole 2.8.2 app:
    #   1. view/activity/join/v (EnterGameViewModel) - patched above, but
    #      its activity (EnterGameActivity) is @Deprecated with ZERO live
    #      references outside its own package = DEAD CODE on 2.8.2.
    #   2. utils/B (EnterGameHelperV2) - the LIVE facade the home hall +
    #      game detail use (IntentUtils instantiates it; the token
    #      callback y.onSuccess -> a(token,0) -> a(token,i,j,of) ->
    #      e==null plain join -> a(token,i) = THE LOCAL GATE
    #      (setGameAddr("") + setRequestId("")).
    #   3. utils/x (EnterGameHelper) - the v1 helper (lately/rejoin paths;
    #      its g1046 "is.bedwarhall.displayed" write proves it serves the
    #      Bedwars hall too). Local gate = inner class x$a's
    #      a(MiniGameToken, ObservableField).
    # BOTH live gates get the same rename+bridge treatment: the takeover
    # runs FIRST (hosted-only g1046/g1008 inside JoinBridge; every other
    # game falls through to the original local boot), failures fall back
    # to a_local, and a bridge throw can never crash the join.
    patched += patch_gate(
        APKTOOL_DIR,
        rel="smali_classes3/com/sandboxol/blockymods/utils/B.smali",
        cls="Lcom/sandboxol/blockymods/utils/B;",
        sig="Lcom/sandboxol/center/entity/MiniGameToken;I)V",
        sig_re=r"\(Lcom/sandboxol/center/entity/MiniGameToken;I\)V",
        ctx_expr=("iget-object v0, p0, Lcom/sandboxol/blockymods/utils/B;"
                  "->a:Landroid/app/Activity;"),
        game_expr=("iget-object v1, p0, Lcom/sandboxol/blockymods/utils/B;"
                  "->b:Lcom/sandboxol/greendao/entity/Game;"),
        tag="B")
    patched += patch_gate(
        APKTOOL_DIR,
        rel="smali_classes3/com/sandboxol/blockymods/utils/x$a.smali",
        cls="Lcom/sandboxol/blockymods/utils/x$a;",
        sig=("Lcom/sandboxol/center/entity/MiniGameToken;"
             "Landroidx/databinding/ObservableField;)V"),
        sig_re=(r"\(Lcom/sandboxol/center/entity/MiniGameToken;"
                r"Landroidx/databinding/ObservableField;\)V"),
        ctx_expr=("iget-object v0, p0, Lcom/sandboxol/blockymods/utils/x$a;"
                  "->a:Lcom/sandboxol/blockymods/utils/x;\n"
                  "    iget-object v0, v0, Lcom/sandboxol/blockymods/utils/x;"
                  "->a:Landroid/content/Context;"),
        game_expr=("iget-object v1, p0, Lcom/sandboxol/blockymods/utils/x$a;"
                  "->a:Lcom/sandboxol/blockymods/utils/x;\n"
                  "    iget-object v1, v1, Lcom/sandboxol/blockymods/utils/x;"
                  "->d:Lcom/sandboxol/greendao/entity/Game;"),
        tag="x$a")
    print(f"patch_join_282: done ({patched} file(s))")


def patch_gate(apktool_dir, rel, cls, sig, sig_re, ctx_expr, game_expr, tag):
    """Rename ONE private local-gate method to a_local and append the
    same-name bridge that runs JoinBridge.takeOverJoin first. Mirrors the
    v-class patch byte-for-byte in spirit; returns 1 when patched.
    <sig> carries the FULL param list with the closing ')V' (the smali
    tail the header AND the invoke-direct both need); <sig_re> is its
    regex-escaped form for the header match."""
    path = apktool_dir / rel
    if not path.is_file():
        print(f"WARNING: patch_join_282: {rel} missing - skipped")
        return 0
    data = path.read_bytes().decode("latin-1")
    if "a_local" in data or "JoinBridge" in data:
        print(f"patch_join_282: {path.name} already patched, skipping")
        return 0
    header_re = re.compile(
        r"^(\.method private a)" + sig_re + r"(\s*)$", re.M)
    params = sig[:-2]  # strip the trailing ')V' -> 'Lcom/...;I'
    data, n = header_re.subn("\\1_local(" + params + r")V\2", data)
    if n != 1:
        sys.exit(f"FATAL: {path}: {n} matching private gate headers "
                 f"({sig}) - refusing to guess")
    if not data.endswith("\n"):
        data += "\n"
    # param registers: p0=this, p1=token, p2=<the gate's 2nd arg>
    data += f""".method private a({params})V
    .locals 3

    :try_start_bridge
{ctx_expr}
{game_expr}
    invoke-static {{v0, v1}}, Lcom/localapi/JoinBridge;->takeOverJoin(Landroid/content/Context;Ljava/lang/Object;)Z
    move-result v2
    if-eqz v2, :cond_join_local
    return-void
    :try_end_bridge
    .catch Ljava/lang/Throwable; {{:try_start_bridge .. :try_end_bridge}} :catch_bridge

    :catch_bridge
    move-exception v2
    invoke-virtual {{v2}}, Ljava/lang/Throwable;->toString()Ljava/lang/String;
    move-result-object v1
    const-string v2, "JoinBridge: smali bridge({tag}) threw -> local fallback: "
    invoke-virtual {{v2, v1}}, Ljava/lang/String;->concat(Ljava/lang/String;)Ljava/lang/String;
    move-result-object v1
    const-string v2, "LocalAPI"
    invoke-static {{v2, v1}}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I
    goto :cond_join_local

    :cond_join_local
    invoke-direct {{p0, p1, p2}}, {cls}->a_local({sig}
    return-void
.end method
"""
    path.write_bytes(data.encode("latin-1"))
    print(f"patch_join_282: {rel} patched ({tag} gate -> JoinBridge "
          f"takeover)")
    return 1


if __name__ == "__main__":
    main()
