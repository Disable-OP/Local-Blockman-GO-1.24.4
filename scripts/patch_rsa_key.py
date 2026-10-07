#!/usr/bin/env python3
"""patch_rsa_key.py — swap the client's hardcoded RSA login public key for ours.

The 1.24.4 client encrypts login/password payloads with RSA/ECB/PKCS1Padding
against a hardcoded 1024-bit public key (com.sandbox.login.e.e "LoginHelper",
classes2.dex). The matching private half lived on the production backend and
is unrecoverable, so the local world mints its own fixed pair:

  - the server half lives in localapi-server/src/com/localapi/RsaCipher.java
    (real RSA decryption, see Wave 11 in docs/ENDPOINTS.md)
  - THIS script replaces the client's public-key constant in the apktool
    smali tree so the client encrypts against the key the local server
    actually holds.

The client's fallback (LoginHelper.b returns the plaintext when its cipher
throws) is untouched — v1 plaintext flows keep working either way.

Idempotent: replaces the original key and re-replaces a previous swap.
"""
import sys
from pathlib import Path

# The ORIGINAL client key (com.sandbox.login.e.e, classes2.dex).
ORIGINAL_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCLzlsA+3wXCAph80r/xs1bWhVrsJSO"
    "QmSBTA0GaBpVIzXqFBaibDmYA3WJDM9rcQ7KpYSyrJ02iFlsN43RnizrHfS+xPtdwuxB"
    "Q2Clow5cYPZucqQYL9HIlbBLoighH2eGQqGlVadL7r384iKTz9mmckSUa8hhJzS+WwUA"
    "qVO3DwIDAQAB"
)

# Our local server's public key — MUST match RsaCipher.PUBLIC_KEY_B64.
LOCAL_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCp466bkyckAkuVRRPYusDN"
    "yW3urjleyz1ps//rKXI2jPzFAMZ6aI/PbMmFdxv3alnnSeO20vjmge2CwRAI"
    "FaJbp6h/OQvfONThKyfE/Y2StpuBdYTDOcOiVUQuE0YI+ROCHAKleLoJDFE1"
    "H70BByEq07Ha8slWiHxfJUMAi36wwwIDAQAB"
)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "build/apktool_out")
    if not root.is_dir():
        print(f"patch_rsa_key: smali root {root} not found - skip")
        return 0
    hits = 0
    for smali in root.rglob("*.smali"):
        try:
            text = smali.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if ORIGINAL_KEY in text:
            smali.write_text(text.replace(ORIGINAL_KEY, LOCAL_KEY), encoding="utf-8")
            hits += 1
            print(f"patch_rsa_key: swapped key in {smali.relative_to(root)}")
    # integrity: the original key must be gone everywhere
    leftovers = [p for p in root.rglob("*.smali") if ORIGINAL_KEY in p.read_text(encoding="utf-8", errors="ignore")]
    if leftovers:
        print("FATAL: original RSA key still present after patch:")
        for p in leftovers:
            print("  ", p)
        return 1
    print(f"patch_rsa_key: {hits} file(s) patched")
    if hits == 0:
        # not fatal: the key lives in classes2 — a tree without it means the
        # patch already ran (idempotence) or the layout changed.
        print("patch_rsa_key: note - original key not found (already patched or absent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
