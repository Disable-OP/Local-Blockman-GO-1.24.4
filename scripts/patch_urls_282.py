#!/usr/bin/env python3
"""patch_urls_282.py — rewire the OFFICIAL Blockman GO 2.8.2 client's API
hosts to the embedded loopback server (http://127.0.0.1:18080).

THE 2.8.2 DECODE (cron session, apktool_out at /home/z/bg282):
- The MAIN API base is METADATA-DRIVEN, not hardcoded: every Retrofit
  interface is built through RetrofitFactory.httpsCreate(BaseApplication
  .getMetaDataBaseUrl(), apiClass) — UserApi/GameApi/FriendPublicApi/... all
  read the same getter, and BaseUrlInterceptor's failover host is
  getMetaDataBackupBaseUrl(). setBaseUrl/setBackupBaseUrl are called EXACTLY
  once each, from InitMetaDataTask.baseMetaData():
      setBaseUrl("https://d32gv25kv9q34j.cloudfront.net")   (cloudfront)
      setBackupBaseUrl("http://mods.sandboxol.com")
  and the getters' null-fallbacks in BaseApplication repeat
  "http://mods.sandboxol.com". Patching those four spots routes the ENTIRE
  2.8.2 API surface to the embedded LocalAPI — no separate metadata JSON
  endpoint is needed (there is no metadata FETCH whose payload carries the
  API base; the getters ARE the base).
- InitMetaDataTask.configMetadata() also pins:
      setPayUrl("http://mods.sandboxol.com/web/public/pay/api/v2/public/
                pay/signature")            -> loopback prefix rewrite
      setEngineResBaseUrl("http://d401m01aifavw.cloudfront.net/files/
                          upload/")        -> loopback prefix rewrite
      setEditorUrl("https://d32gv25kv9q34j.cloudfront.net") -> loopback
- LEFT ALONE (by design):
      static.sandboxol.com/...           — real CDN, images still served
      staticgs.sandboxol.com/...         — real CDN, appres/maps/plugins
      team.game.sandboxol.com:9921       — organize-team socket (unused here)
      www.blockmango.net/recharge.html   — third-party pay page (unused)
      mailto: / generic https strings    — not API hosts

Idempotent, latin-1-safe (repo lesson: scripts write latin-1).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The 2.8.2 apktool tree (default /home/z/bg282/apktool_out).
APKTOOL_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/home/z/bg282/apktool_out")

LOOPBACK = "http://127.0.0.1:18080"

# Prefix rewrites: every const-string that STARTS with the key gets the key
# replaced (path suffix preserved). Order-independent.
PREFIX_REWRITES = [
    # the metadata/API base (setBaseUrl + setEditorUrl share the const)
    "https://d32gv25kv9q34j.cloudfront.net",
    # the backup base + the pay-signature URL (both mods.sandboxol.com)
    "http://mods.sandboxol.com",
    # the engine-resource update base
    "http://d401m01aifavw.cloudfront.net",
]

# Files whose fallbacks repeat the hosts (getters in BaseApplication).
TARGET_FILES = ["BaseApplication.smali", "InitMetaDataTask.smali"]


def main():
    if not APKTOOL_DIR.is_dir():
        sys.exit(f"error: {APKTOOL_DIR} not found — run apktool d first")
    total = 0
    # 1. the named targets (BaseApplication getters + the init task)
    for name in TARGET_FILES:
        matches = list(APKTOOL_DIR.rglob(name))
        for path in matches:
            data = path.read_bytes().decode("latin-1")
            count = 0
            for host in PREFIX_REWRITES:
                needle = '"' + host
                repl = '"' + LOOPBACK
                count += data.count(needle)
                data = data.replace(needle, repl)
            if count:
                path.write_bytes(data.encode("latin-1"))
                total += count
                print(f"patched {count} const-string(s) in "
                      f"{path.relative_to(APKTOOL_DIR)}")
    if not matches:
        pass
    # 2. sweep EVERY smali for leftover hosts (the pay URL prefix inside
    #    other classes, stray hardcodes). Same prefix rule.
    for path in APKTOOL_DIR.rglob("*.smali"):
        raw = path.read_bytes()
        if (b"mods.sandboxol.com" not in raw
                and b"d32gv25kv9q34j" not in raw
                and b"d401m01aifavw" not in raw):
            continue
        text = raw.decode("latin-1")
        count = 0
        for host in PREFIX_REWRITES:
            needle = '"' + host
            repl = '"' + LOOPBACK
            count += text.count(needle)
            text = text.replace(needle, repl)
        if count:
            path.write_bytes(text.encode("latin-1"))
            total += count
            print(f"sweep: {count} host(s) -> loopback in "
                  f"{path.relative_to(APKTOOL_DIR)}")
    if total == 0:
        print("warning: nothing patched (already patched or pattern drift)")
    else:
        print(f"OK — {total} URL(s) now point at {LOOPBACK}")
    # 3. integrity: no unpatched API host may remain anywhere
    leftovers = []
    for path in APKTOOL_DIR.rglob("*.smali"):
        text = path.read_bytes().decode("latin-1", "ignore")
        for host in PREFIX_REWRITES:
            if '"' + host in text:
                leftovers.append(str(path))
                break
    if leftovers:
        print("FATAL: unpatched API hosts remain:")
        for p in leftovers[:10]:
            print("  ", p)
        sys.exit(1)


if __name__ == "__main__":
    main()
