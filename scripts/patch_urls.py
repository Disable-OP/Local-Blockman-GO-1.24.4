#!/usr/bin/env python3
"""patch_urls.py — rewire Blockman GO custom build API hosts to the embedded
loopback server (http://127.0.0.1:18080).

Idempotent: running twice is a no-op. Only touches const-string values with
the https:// scheme inside App.smali and BaseApplication.smali, preserving
any path suffix. Tunnel host is matched by TLD regex (never spelled out);
CloudFront host by exact string.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APKTOOL_DIR = REPO / "build" / "apktool_out"
TARGETS = ["App.smali", "BaseApplication.smali"]

LOOPBACK = "http://127.0.0.1:18080"
PRIMARY_EXACT = "https://d32gv25kv9q34j.cloudfront.net"
# any https host on a two-label dynamic-DNS style domain ending .dev
TUNNEL_RE = re.compile(r"https://[A-Za-z0-9-]+\.[A-Za-z0-9-]+\.dev")

CONST_STRING = re.compile(r'(const-string\s+\S+,\s*")([^"]+)(")')


def rewrite(value: str) -> str:
    if value.startswith("http://127.0.0.1"):
        return value  # already patched
    new = TUNNEL_RE.sub(LOOPBACK, value)
    if new.startswith(PRIMARY_EXACT):
        new = LOOPBACK + new[len(PRIMARY_EXACT):]
    return new


def main():
    if not APKTOOL_DIR.exists():
        sys.exit(f"error: {APKTOOL_DIR} not found — run apktool d first")
    total = 0
    for name in TARGETS:
        matches = list(APKTOOL_DIR.rglob(name))
        if not matches:
            sys.exit(f"error: {name} not found under {APKTOOL_DIR}")
        path = matches[0]
        text = path.read_text()
        count = 0

        def sub(m):
            nonlocal count
            new_val = rewrite(m.group(2))
            if new_val != m.group(2):
                count += 1
            return m.group(1) + new_val + m.group(3)

        text = CONST_STRING.sub(sub, text)
        path.write_text(text)
        total += count
        print(f"patched {count} const-string(s) in {path.relative_to(APKTOOL_DIR)}")
    if total == 0:
        print("warning: nothing patched (already patched or pattern drift)")
    else:
        print(f"OK — {total} URL(s) now point at {LOOPBACK}")


if __name__ == "__main__":
    main()
