#!/usr/bin/env python3
"""build_pack_124.py — pack the 1.24.4 harness APK WITHOUT apktool b
(session 86; the sandbox reaps >10-minute background jobs and apktool's
resource pass is the >10-minute step — but the manual pack never needed
it: resources/lib stay the ORIGINAL bytes, only dexes + seed assets +
libgameserver.so change, exactly the 282 build's proven zipfile recipe).

Inputs (defaults in brackets):
  <original base APK>            [build/../bg-base.apk -> /home/z/bg-base.apk]
  build/dexout/classes{,2..5}.dex   the smali-assembled patched dexes
  localapi-server/build/classes6.dex the server dex
  build/apktool_out/assets/localapi/{skins.json,ScriptSetting.csv,
                                     gs-line.json,gameicons.tar.gz}
  build/libtmp/lib/arm64-v8a/libgameserver.so

Output: build/patched-unsigned.apk
"""
import os
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(REPO, "build")
ORIG = sys.argv[1] if len(sys.argv) > 1 else "/home/z/bg-base.apk"
DST = os.path.join(BUILD, "patched-unsigned.apk")

DEXES = ["classes.dex", "classes2.dex", "classes3.dex",
         "classes4.dex", "classes5.dex", "classes6.dex"]
SEEDS = ["skins.json", "ScriptSetting.csv", "gs-line.json", "gameicons.tar.gz"]
GS_SO = os.path.join(BUILD, "libtmp", "lib", "arm64-v8a", "libgameserver.so")


def main():
    for d in DEXES:
        p = os.path.join(BUILD, "dexout" if d != "classes6.dex" else
                         os.path.join(REPO, "localapi-server", "build"), d)
        if not os.path.isfile(p):
            sys.exit(f"FATAL: {p} missing")
    server_payload = open(os.path.join(REPO, "localapi-server", "build",
                                       "classes6.dex"), "rb").read()
    tmp = DST + ".tmp"
    with zipfile.ZipFile(ORIG) as zin, \
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            name = item.filename
            if name.startswith("META-INF/"):
                continue  # old signatures die here
            if name in DEXES:
                continue  # swapped below
            zout.writestr(item, zin.read(name))
        for name in DEXES[:-1]:
            payload = open(os.path.join(BUILD, "dexout", name), "rb").read()
            zi = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            zi.external_attr = 0o644 << 16
            zout.writestr(zi, payload, zipfile.ZIP_DEFLATED)
        zi = zipfile.ZipInfo("classes6.dex", (2026, 1, 1, 0, 0, 0))
        zi.external_attr = 0o644 << 16
        zout.writestr(zi, server_payload, zipfile.ZIP_DEFLATED)
        seeds = os.path.join(BUILD, "apktool_out", "assets", "localapi")
        for name in SEEDS:
            p = os.path.join(seeds, name)
            if not os.path.isfile(p):
                print(f"WARNING: seed {p} missing — not shipped")
                continue
            zi = zipfile.ZipInfo(f"assets/localapi/{name}", (2026, 1, 1, 0, 0, 0))
            zi.external_attr = 0o644 << 16
            zout.writestr(zi, open(p, "rb").read(), zipfile.ZIP_DEFLATED)
        if os.path.isfile(GS_SO):
            zi = zipfile.ZipInfo("lib/arm64-v8a/libgameserver.so",
                                 (2026, 1, 1, 0, 0, 0))
            zi.external_attr = 0o644 << 16
            zout.writestr(zi, open(GS_SO, "rb").read(), zipfile.ZIP_DEFLATED)
        else:
            print("WARNING: libgameserver.so missing — shipping without the "
                  "gameplay server")
    os.replace(tmp, DST)
    print("packed", DST, os.path.getsize(DST), "bytes")


if __name__ == "__main__":
    main()
