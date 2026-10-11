#!/usr/bin/env python3
"""patch_bootstrap_282.py — insert the LocalServer bootstrap hook into the
2.8.2 client's BaseApplication.onCreate (idempotent).

The 2.8.2 Application chain is com.sandboxol.blockymods.App
  extends com.sandboxol.common.base.app.BaseApplication
    extends com.tencent.tpshell.TPShellApplication (libtprt.so runtime).

BaseApplication.onCreate is the earliest shared hook:

    .method public onCreate()V
        .locals 0
        invoke-super {p0}, Lcom/tencent/tpshell/TPShellApplication;->onCreate()V
    +   invoke-static {p0}, Lcom/localapi/LocalServer;->startIfNeeded(Landroid/content/Context;)V
        sput-object p0, ...->context:Landroid/content/Context;
        ...

`.locals 0` is safe: the hook consumes no extra register (p0 is an incoming
register and IS a Context — BaseApplication extends Application).

The hook starts the embedded loopback API server before the appstartfaster
task chain (InitMetaDataTask & friends) can fire any network request.
Multi-process races are handled inside LocalServer (bind watchdog) — the
1.24.4 line runs the identical hook from its App.smali.
"""
import sys
from pathlib import Path

APKTOOL_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/home/z/bg282/apktool_out")
TARGET = APKTOOL_DIR / "smali" / "com" / "sandboxol" / "common" / "base" / \
    "app" / "BaseApplication.smali"

HOOK = ("    invoke-static {p0}, Lcom/localapi/LocalServer;"
        "->startIfNeeded(Landroid/content/Context;)V\n")
SUPER = ("invoke-super {p0}, Lcom/tencent/tpshell/TPShellApplication;"
         "->onCreate()V")


def main():
    if not TARGET.is_file():
        sys.exit(f"error: {TARGET} not found")
    text = TARGET.read_text(encoding="utf-8")
    if "LocalServer;->startIfNeeded" in text:
        print("hook already present — nothing to do")
        return
    if SUPER not in text:
        sys.exit("ERROR: tpshell super.onCreate anchor not found")
    patched = text.replace(SUPER + "\n", SUPER + "\n\n" + HOOK, 1)
    TARGET.write_text(patched, encoding="utf-8")
    print("hook inserted into", TARGET)


if __name__ == "__main__":
    main()
