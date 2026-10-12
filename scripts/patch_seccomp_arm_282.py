#!/usr/bin/env python3
"""patch_seccomp_arm_282.py — insert the seccomp-guard arm call at the
engine-load site of the 2.8.2 client.

The engine lib (libBlockMan.so for engine1; libBlockManv2/v3 for the other
lines) is loaded by com.getkeepsafe.relinker.b.a(Context, name) inside
AbstractEngineEnv. libBlockMan.so (10078) embeds the Tencent TSS native:
its constructor self-checks run INSIDE that load, and the TSS verdict's
exit_group(25|30) fires ~2.8s later.

v10/v11 taught (runs 38181791036 / 38183140775 / 38179978542):
- arming the filter EARLY (Application.onCreate) => the TSS ctor detects the
  foreign seccomp filter and aborts with SIGILL in its packed code;
- the correct moment is IMMEDIATELY AFTER the load returns: the ctor checks
  are done (no filter yet) and the verdict has not fired yet.

This patch inserts, right after the relinker invoke in
AbstractEngineEnv.smali:
    invoke-static {}, Lcom/localapi/LocalServer;->armEngineGuardNow()V

Idempotent: re-runs detect the existing hook. The build script sanity-checks
for the inserted line.
"""
import re
import sys

TREE = sys.argv[1] if len(sys.argv) > 1 else "/home/z/bg282/apktool_out"
PATH = TREE + "/smali/com/sandboxol/center/router/moduleInfo/game/AbstractEngineEnv.smali"

HOOK = "invoke-static {}, Lcom/localapi/LocalServer;->armEngineGuardNow()V"
PROBE = "invoke-static {}, Lcom/localapi/LocalServer;->probeEngineLoadSite()V"
METHOD_HEAD = ".method public loadSO(Landroid/content/Context;)V"
RELINK = "invoke-static {p1, v0}, Lcom/getkeepsafe/relinker/b;->a(Landroid/content/Context;Ljava/lang/String;)V"

src = open(PATH).read()
if "armEngineGuardNow" in src:
    print("patch_seccomp_arm_282: hook already present")
    sys.exit(0)

lines = src.split("\n")
out = []
inserted = 0
for i, line in enumerate(lines):
    if line.strip() == METHOD_HEAD and "probeEngineLoadSite" not in src:
        out.append(line)
        out.append("")
        out.append("    # probe: prove whether this load site runs at all")
        out.append("    " + PROBE)
        continue
    out.append(line)
    if line.strip() == RELINK:
        out.append("")
        out.append("    # seccomp engine guard: arm AFTER the engine lib load"
                   " returns (the embedded TSS ctor checks are done; the"
                   " verdict's exit_group(25|30) comes later and gets no-oped)")
        out.append("    " + HOOK)
        inserted += 1

if inserted != 1:
    print(f"FATAL: expected exactly 1 relinker call site, found {inserted}")
    sys.exit(1)

open(PATH, "w").write("\n".join(out))
print(f"patch_seccomp_arm_282: hook inserted into {PATH}")

# ---------------------------------------------------------------------------
# v12.2: the REAL engine load path is EchoesRenderer.handlePreInit ->
# nativePreInit (a NATIVE method that dlopens libBlockMan from C++) —
# AbstractEngineEnv.loadSO is NOT on the join path (probe-proven in run
# 38187611609). The arm hook goes at handlePreInit's convergence point.
RENDERER = TREE + "/smali/com/sandboxol/blockmango/EchoesRenderer.smali"
RENDER_OLD = """    :goto_0
    return-void
.end method

.method private static native nativeBuyActionResult(II)V"""
RENDER_NEW = """    :goto_0
    # seccomp engine guard: arm after the NATIVE pre-init returns — libBlockMan
    # was dlopened inside nativePreInit (the embedded TSS ctor checks already
    # ran there); the verdict's exit_group(25|30) fires ~2.8s later and the
    # filter no-ops it.
    invoke-static {}, Lcom/localapi/LocalServer;->armEngineGuardNow()V

    return-void
.end method

.method private static native nativeBuyActionResult(II)V"""
rs = open(RENDERER).read()
if "armEngineGuardNow" not in rs:
    assert RENDER_OLD in rs, "EchoesRenderer convergence point not found"
    open(RENDERER, "w").write(rs.replace(RENDER_OLD, RENDER_NEW, 1))
    print("patch_seccomp_arm_282: renderer hook inserted")
else:
    print("patch_seccomp_arm_282: renderer hook already present")
