#!/usr/bin/env python3
"""Insert the LocalServer bootstrap hook into App.smali (idempotent).

The hook starts the embedded loopback API server as early as possible in
Application.onCreate, before any activity can fire a network request:

    invoke-super {p0}, ...BaseApplication;->onCreate()V
    invoke-static {p0}, Lcom/localapi/LocalServer;->startIfNeeded(Landroid/content/Context;)V
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
SMALI = os.path.join(ROOT, "build", "apktool_out", "smali", "com", "disabngo", "blockynexus", "App.smali")

HOOK = ("    invoke-static {p0}, Lcom/localapi/LocalServer;"
        "->startIfNeeded(Landroid/content/Context;)V\n")
SUPER = "invoke-super {p0}, Lcom/sandboxol/common/base/app/BaseApplication;->onCreate()V"


def main(smali_path):
    with open(smali_path, "r", encoding="utf-8") as f:
        text = f.read()
    if "LocalServer;->startIfNeeded" in text:
        print("hook already present — nothing to do")
        return
    if SUPER not in text:
        print("ERROR: super.onCreate anchor not found", file=sys.stderr)
        sys.exit(1)
    patched = text.replace(SUPER + "\n", SUPER + "\n\n" + HOOK, 1)
    # apktool keeps the .line debug directive after super call; hook must sit
    # before the next invoke-direct c() call — placing right after super is safe.
    with open(smali_path, "w", encoding="utf-8") as f:
        f.write(patched)
    print("hook inserted into", smali_path)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else SMALI
    main(path)
