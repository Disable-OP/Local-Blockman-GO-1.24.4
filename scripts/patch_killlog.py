#!/usr/bin/env python3
"""Insert stack-trace logging at every in-app Process.killProcess call site.

Evidence (sessions 11, v0.5.9+): the app pair is SIGKILLed between test
phases with no AM kill, no ANR, no lmkd entry, no crash, no tombstone.
Everything points at a self-kill; the only surviving code path is the
native engine's JNI callback into EchoesHelper.killAppProcess(). This
patch makes every kill site LOG a full Java stack (tag "LocalAPI") before
the kill executes, so the next incident names its caller.

Sites (verified in the jadx 1.24.4 sources):
  classes2/com/sandboxol/blockmango/EchoesHelper.smali   killAppProcess()V
  classes2/com/sandboxol/blockmango/EchoesHelper.smali   terminateProcess()V
  classes2/com/sandboxol/blockmango/GameFailedDialog.smali onClick(...)V
  classes3/com/sandboxol/common/base/app/CrashAppManager.smali exitProcess()V

Idempotent: a site is skipped if the marker string is already present.
The injected registers extend .locals by 4 (registers N..N+3 right after
.prologue, where N was the original locals count — always free).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
OUT = os.path.join(ROOT, "build", "apktool_out")

MARKER = "killAppProcess stack-log"

SITES = [
    ("smali_classes2/com/sandboxol/blockmango/EchoesHelper.smali",
     ".method public static killAppProcess()V"),
    ("smali_classes2/com/sandboxol/blockmango/EchoesHelper.smali",
     ".method public static terminateProcess()V"),
    ("smali_classes2/com/sandboxol/blockmango/GameFailedDialog.smali",
     ".method public onClick(Landroid/view/View;)V"),
    ("smali_classes3/com/sandboxol/common/base/app/CrashAppManager.smali",
     ".method public exitProcess()V"),
]

# vN/vN+1/vN+2/vN+3 must be substituted with real register numbers.
LOG_TMPL = """    new-instance v{n}, Ljava/lang/Throwable;
    invoke-direct {{v{n}}}, Ljava/lang/Throwable;-><init>()V
    invoke-static {{v{n}}}, Landroid/util/Log;->getStackTraceString(Ljava/lang/Throwable;)Ljava/lang/String;
    move-result-object v{n}
    new-instance v{n1}, Ljava/lang/StringBuilder;
    invoke-direct {{v{n1}}}, Ljava/lang/StringBuilder;-><init>()V
    const-string v{n2}, "killAppProcess CALLED from:\\n"
    invoke-virtual {{v{n1}, v{n2}}}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {{v{n1}, v{n}}}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {{v{n1}}}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v{n}
    const-string v{n2}, "LocalAPI"
    invoke-static {{v{n2}, v{n}}}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I
"""


def patch_method(text, method_sig):
    """Insert the stack-log right after the method's .locals directive.

    apktool omits .prologue when the method carries no debug info, so the
    only reliable anchor is the .locals line itself (inserting between
    directives is valid smali; pX parameter mapping follows .locals).
    """
    start = text.find(method_sig)
    if start < 0:
        return None, "method not found"
    body_end = text.find(".end method", start)
    if body_end < 0:
        return None, "unterminated method"
    if MARKER in text[start:body_end]:
        return text, "already patched"

    m = re.search(r"\.locals\s+(\d+)", text[start:body_end])
    if not m:
        return None, "no .locals directive (refusing .registers method)"
    n = int(m.group(1))
    locals_start = start + m.start()
    locals_line_end = text.find("\n", locals_start)
    # bump .locals by 4 (new registers n..n+3 live above the old range)
    bumped = text[locals_start:locals_line_end].replace(
        ".locals %d" % n, ".locals %d" % (n + 4), 1)
    block = "\n    # %s\n" % MARKER + LOG_TMPL.format(n=n, n1=n + 1, n2=n + 2)
    text = text[:locals_start] + bumped + block + text[locals_line_end:]
    return text, "patched (locals %d -> %d)" % (n, n + 4)


def main():
    changed = 0
    for rel, sig in SITES:
        path = os.path.join(OUT, rel)
        if not os.path.exists(path):
            print("WARN missing smali: %s" % rel)
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        new_text, status = patch_method(text, sig)
        if new_text is None:
            print("FAIL %s %s: %s" % (rel, sig, status))
            sys.exit(1)
        if status != "already patched":
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
            changed += 1
        print("%s %s :: %s" % (rel.rsplit("/", 1)[-1], sig.split(" ")[-1], status))
    print("killlog patch: %d site(s) changed" % changed)


if __name__ == "__main__":
    main()
