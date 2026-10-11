#!/usr/bin/env python3
"""patch_antitp_282.py — neutralize the Tencent anti-tamper stack in the
2.8.2 client (tersafe2 / tprt / TSS SDK) so the RE-SIGNED APK survives.

THE EVIDENCE (test-redroid-282 runs 38153281566 + 38153769894):
  "Zygote: Process 1949 exited cleanly (30)"  ~60-150s after launch, main
  process + the :ipc (Rong) process, no Java FATAL, no signal, no
  tombstone. A CLEAN exit(30) from a native thread = the TSS anti-cheat
  verdict path (TssSdk 5.0.5 / tersafe2, loaded by App + TssSdk clinit;
  tpshell's tprt loaded from TPShellApplication.<clinit>). The official
  build validates the (Google) signature; our debug re-sign fails it.

THE NEUTRALIZATION (behavior-preserving — every call site keeps working):
  1. TPShellApplication.<clinit>: drop System.loadLibrary("tprt").
  2. TPShellApplication.initialize(native) -> Java stub returning 0
     (attachBaseContext throws on non-zero but CATCHES it; 0 = clean).
  3. TssSdk.<clinit>: drop System.loadLibrary("tersafe2").
  4. TssSdk's 10 static native methods -> Java stubs (V -> return-void,
     I -> return 0). Callers (OneSDK_Tss / TP2Sdk / TouchListenerProxy /
     TssInfoPublisher / r) are unguarded, so stub bodies (not load
     removal alone) are what keep them safe.
  5. App.smali's Relinker chain: "tersafe2" -> "c++_shared" (a real lib
     that is in the APK; the relink keeps succeeding).
  MMKV and every other native surface are untouched.

Idempotent, latin-1-safe.
"""
import re
import sys
from pathlib import Path

APKTOOL_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/home/z/bg282/apktool_out")

TPSHELL = APKTOOL_DIR / "smali" / "com" / "tencent" / "tpshell" / \
    "TPShellApplication.smali"
TSSSDK = APKTOOL_DIR / "smali_classes6" / "com" / "tencent" / "tp" / \
    "TssSdk.smali"
APP = APKTOOL_DIR / "smali" / "com" / "sandboxol" / "blockymods" / "App.smali"


def patch_tpshell(text):
    changed = 0
    # 1. <clinit>: drop the tprt load (const-string + loadLibrary pair)
    clinit_re = re.compile(
        r'(\.method static constructor <clinit>\(\)V\s*\.locals \d+\s*)'
        r'const-string/jumbo v0, "tprt"\s*'
        r'invoke-static \{v0\}, Ljava/lang/System;->loadLibrary'
        r'\(Ljava/lang/String;\)V\s*',
        re.S)
    text, n = clinit_re.subn(r"\1", text)
    if n:
        changed += n
    # 2. initialize native -> stub returning 0
    init_re = re.compile(
        r'\.method private final native initialize\(Ljava/lang/String;'
        r'Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;'
        r'\[Ljava/lang/String;Ljava/lang/String;\)I\s*\.end method')
    stub = (
        ".method private final initialize(Ljava/lang/String;"
        "Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;"
        "[Ljava/lang/String;Ljava/lang/String;)I\n"
        "    .locals 1\n\n"
        "    const/4 v0, 0x0\n\n"
        "    return v0\n"
        ".end method")
    text, n2 = init_re.subn(stub, text)
    changed += n2
    return text, changed


def patch_tsssdk(text):
    changed = 0
    # 3. <clinit>: drop the tersafe2 load
    clinit_re = re.compile(
        r'(\.method static constructor <clinit>\(\)V\s*\.locals \d+\s*)'
        r'const-string v0, "tersafe2"\s*'
        r'invoke-static \{v0\}, Ljava/lang/System;->loadLibrary'
        r'\(Ljava/lang/String;\)V\s*',
        re.S)
    text, n = clinit_re.subn(r"\1", text)
    changed += n
    # 4. every `native` method -> plain stub (V: return-void, I: return 0).
    #    The `native` keyword MUST be stripped — a native declaration with
    #    a body is invalid smali.
    def sub_native(m):
        header = m.group(1).replace(" native ", " ")
        if header.endswith(")I"):
            body = "    .locals 1\n\n    const/4 v0, 0x0\n\n    return v0\n"
        else:
            body = "    .locals 0\n\n    return-void\n"
        return header + "\n" + body + ".end method"
    text, n2 = re.subn(
        r'(\.method public static native [^\n]*\([^)]*\)[VI])\s*\.end method',
        sub_native, text)
    changed += n2
    # REPAIR (idempotent): a previous buggy run could leave native headers
    # WITH stub bodies (invalid smali) — strip any remaining ` native `
    # keyword from static declarations in this class.
    if " public static native " in text:
        n3 = text.count(" public static native ")
        text = text.replace(" public static native ", " public static ")
        changed += n3
    return text, changed


def patch_app(text):
    # 5. the Relinker chain: load c++_shared instead of tersafe2
    if '"tersafe2"' in text:
        text = text.replace('"tersafe2"', '"c++_shared"')
        return text, 1
    return text, 0


def main():
    total = 0
    for path, fn in ((TPSHELL, patch_tpshell),
                     (TSSSDK, patch_tsssdk),
                     (APP, patch_app)):
        if not path.is_file():
            sys.exit(f"error: {path} not found")
        text = path.read_bytes().decode("latin-1")
        text, n = fn(text)
        if n:
            path.write_bytes(text.encode("latin-1"))
        print(f"{path.name}: {n} patch site(s)")
        total += n
    # integrity
    bad = []
    for path in (TPSHELL, TSSSDK):
        t = path.read_bytes().decode("latin-1")
        if " native " in t:
            bad.append(str(path.name) + " still declares natives")
    if bad:
        sys.exit("FATAL: " + "; ".join(bad))
    print(f"OK — anti-tamper neutralized ({total} site(s)); "
          f"MMKV and all other natives untouched")


if __name__ == "__main__":
    main()
