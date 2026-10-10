#!/usr/bin/env python3
"""patch_join.py — take over the hall Quick-in's LOCAL join and turn it into
the ONLINE join into the on-device GameServer room.

THE DECODE (session 58, androguard on the shipped APK, all dexes):
- StartMc.startGame(Context, EnterRealmsResult, flavor, baseUrl) is the only
  engine entry: it gson-writes the result into the "start.game.info" prefs,
  kills the :BlockmanGo process and startActivityForResult's StartMcActivity.
  Controller.a(Subscriber) reads the prefs back, loadSO's the engine and
  setEnterRealmsResult's; the engine initGame's with result.gameAddr
  host:port, requestId, gameType=game.gameId and downloads result.mapUrl.
- The app has exactly FOUR startGame call sites:
    va$b.a(MiniGameToken)         LOCAL  (gameAddr="" — the hall Quick-in)
    va$b.a(Dispatch, Z)           ONLINE (gameAddr=dispatch.gAddr)
    join/s.a(Dispatch, Z)         ONLINE (friend-follow join)
    TeamModel$5.onTeamNext        ONLINE (team join)
  Every "client booted a local world" observation in every redroid run came
  through va$b.a(MiniGameToken) — by elimination, it is THE local gate.
- The instance method va$b.a(MiniGameToken) is PRIVATE (the synthetic
  accessor a(va$b, MiniGameToken) calls it with invoke-direct), so the
  replacement method keeps `private` (a public replacement would turn the
  accessor's invoke-direct into a verifier error and crash the app).

THE PATCH: rename the original method to a_local (body untouched) and add a
new private a(MiniGameToken) that first offers the takeover to
com.localapi.JoinBridge.takeOverJoin(context, tappedGame) (classes6.dex;
the 2nd param is Object because the server dex compiles against
android-stubs alone — the smali passes the Game ref into an Object slot).
The whole bridge call sits in a try/catch whose handler logs
"JoinBridge: smali bridge threw -> local fallback: ..." (tag LocalAPI) and
falls back to a_local — a bridge failure can NEVER crash the join.

Idempotent, pure ASCII, latin-1-safe (repo lesson: scripts write latin-1).
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APKTOOL_DIR = REPO / "build" / "apktool_out"

TARGET_NAME = "va$b.smali"
TARGET_DIR_PART = "com/disabngo/blockynexus/view/dialog"
VA_CLASS = "Lcom/disabngo/blockynexus/view/dialog/va;"
VAB_CLASS = "Lcom/disabngo/blockynexus/view/dialog/va$b;"
M_TOKEN = "Lcom/sandboxol/greendao/entity/MiniGameToken;"

NEW_METHOD = """.method private a(LOKCOMPAT_TOKEN;)V
    .locals 3

    :try_start_bridge
    iget-object v0, p0, LOKVAB;->d:LOKVA;
    invoke-static {v0}, LOKVA;->e(LOKVA;)Landroid/content/Context;
    move-result-object v0
    iget-object v1, p0, LOKVAB;->d:LOKVA;
    invoke-static {v1}, LOKVA;->a(LOKVA;)Lcom/sandboxol/greendao/entity/Game;
    move-result-object v1
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
    invoke-direct {p0, p1}, LOKVAB;->a_local(LOKCOMPAT_TOKEN;)V
    return-void
.end method
""".replace("LOKVAB;", VAB_CLASS).replace("LOKVA;", VA_CLASS) \
   .replace("LOKCOMPAT_TOKEN;", M_TOKEN)


def main():
    if not APKTOOL_DIR.exists():
        sys.exit(f"error: {APKTOOL_DIR} not found - run apktool d first")
    targets = [p for p in APKTOOL_DIR.rglob(TARGET_NAME)
               if TARGET_DIR_PART in str(p).replace("\\", "/")]
    if not targets:
        sys.exit(f"error: no {TARGET_NAME} under {TARGET_DIR_PART} in {APKTOOL_DIR}")

    patched = 0
    for path in targets:
        data = path.read_bytes().decode("latin-1")
        if "a_local" in data or "JoinBridge" in data:
            print(f"patch_join: {path.name} already patched, skipping")
            continue

        # 1. rename the original private a(MiniGameToken) -> a_local
        header_re = re.compile(
            r"^(\.method[^\r\n]*?\sa)\(" + re.escape(M_TOKEN) + r"\)V(\s*)$",
            re.M)
        data, n = header_re.subn(r"\1_local(" + M_TOKEN + r")V\2", data)
        if n == 0:
            if "a_local(" in data:
                print(f"patch_join: {path.name}: a_local present, "
                      f"appending takeover method if missing")
            else:
                print(f"WARNING: {path}: a(MiniGameToken) header not found "
                      f"- no patch applied")
                continue
        if n > 1:
            sys.exit(f"FATAL: {path}: {n} matching a(MiniGameToken) headers "
                     f"- refusing to guess")

        # 2. append the takeover method (order-independent within a class)
        #    (idempotent: a_local present -> the takeover method is too)
        if n == 0:
            continue
        if not data.endswith("\n"):
            data += "\n"
        data += NEW_METHOD

        path.write_bytes(data.encode("latin-1"))
        patched += 1
        print(f"patch_join: {path} patched (a->a_local + JoinBridge takeover)")
    if patched == 0:
        print("patch_join: nothing to do (all targets already patched)")
    print(f"patch_join: done ({patched} file(s))")


if __name__ == "__main__":
    main()
