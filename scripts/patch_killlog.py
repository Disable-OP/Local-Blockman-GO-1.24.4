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

LOG_TMPL = """    new-instance v{n}, Ljava/lang/Throwable;
    invoke-direct {{v{n}}}, Ljava/lang/Throwable;-><init>()V
    invoke-static {{v{n}}}, Landroid/util/Log;->getStackTraceString(Ljava/lang/Throwable;)Ljava/lang/String;
    move-result-object v{n}
    const-string v{n1}, "LocalAPI"
    invoke-static {{v{n1}, v{n}}}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I
"""

KILL_INVOKE = "Landroid/os/Process;->killProcess"
SCAN_DIRS = ("smali", "smali_classes2", "smali_classes3",
             "smali_classes4", "smali_classes5")
# Scan EVERYTHING (bundled SDKs included — the v0.5.14 death outlived the
# neutralized MainActivity kills, and a crashsdk/anti-addiction SDK is the
# prime suspect); skip only our own injected package and obvious framework
#/library noise where a killProcess call is legitimate tooling.
SCAN_EXCLUDES = ("com/localapi", "androidx/", "android/support")

# Proven killers (v0.5.12/v0.5.13 evidence): MainActivity hard-exits the
# whole app pair via Process.killProcess from (a) onPause's finishing path
# and (b) the synthetic a(Ljava/lang/Boolean;)V — the guest-kick dialog's
# confirm handler. The guest/login flow finishes MainActivity and the hard
# exit SIGKILLs everything ~5m20s after launch. Real-server session hygiene
# has no meaning in the local world; ALL kill invocations inside
# MainActivity are suppressed (stack logs stay everywhere).
NEUTRALIZE_FILE_SUFFIX = "view/activity/main/MainActivity.smali"


def find_methods_with_kill(text):
    """Yield (method_start, method_sig_line, body_end) for every method whose
    body contains a Process.killProcess invocation."""
    out = []
    for m in re.finditer(r"^\.method[^\n]*$", text, re.M):
        start = m.start()
        body_end = text.find(".end method", start)
        if body_end < 0:
            continue
        if KILL_INVOKE in text[start:body_end]:
            out.append((start, m.group(0), body_end))
    return out


def main():
    changed = skipped = 0
    for d in SCAN_DIRS:
        base = os.path.join(OUT, d)
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            rel = os.path.relpath(root, OUT).replace(os.sep, "/")
            # rel = "smali_classesN/com/sandboxol/..." — scope-check the part
            # AFTER the smali dir component
            parts = rel.split("/")
            pkg_path = "/".join(parts[1:]) if len(parts) > 1 else ""
            if pkg_path.startswith(SCAN_EXCLUDES):
                continue
            for fn in files:
                if not fn.endswith(".smali"):
                    continue
                path = os.path.join(root, fn)
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                if KILL_INVOKE not in text:
                    continue
                # patch methods from LAST to FIRST so earlier offsets survive
                for start, sig, body_end in reversed(
                        find_methods_with_kill(text)):
                    new_text, status = patch_method_at(text, start, body_end)
                    if new_text is None:
                        print("FAIL %s :: %s :: %s" % (fn, sig.strip(), status))
                        sys.exit(1)
                    if status.startswith("patched"):
                        text = new_text
                        changed += 1
                        print("patched %s :: %s" % (
                            os.path.relpath(path, OUT), sig.strip()))
                    else:
                        skipped += 1
                        if status != "already patched":
                            print("SKIPPED %s :: %s :: %s" % (
                                os.path.relpath(path, OUT), sig.strip(),
                                status))
                    # proven-killer suppression (see NEUTRALIZE comment above)
                    if path.endswith(NEUTRALIZE_FILE_SUFFIX):
                        # patch_method_at inserted lines inside the method, so
                        # the original body_end offset is stale — recompute
                        cur_end = text.find(".end method", start)
                        text, nops = neutralize_kills(text, start, cur_end)
                        if nops:
                            print("NEUTRALIZED %d killProcess invoke(s) in %s :: %s"
                                  % (nops, os.path.relpath(path, OUT),
                                     sig.strip()))
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
    print("killlog scan: %d site(s) patched, %d already done" % (changed, skipped))


def neutralize_kills(text, start, body_end):
    """Replace every killProcess invoke inside ONE method's body with nop
    (the stack-log stays). Operates on [start, body_end] so other methods in
    the same file keep their own evidence-only patches. Returns
    (text, number_of_replaced_lines)."""
    head, body, tail = text[:start], text[start:body_end], text[body_end:]
    lines = body.split("\n")
    nops = 0
    for i, line in enumerate(lines):
        if KILL_INVOKE in line and line.strip().startswith("invoke-static"):
            lines[i] = line.replace(line.strip(), "nop")
            nops += 1
    return head + "\n".join(lines) + tail, nops


def param_registers(sig):
    """Register footprint of a method signature's parameters (J/D are wide)."""
    mm = re.search(r"\(([^)]*)\)", sig)
    if not mm:
        return 0
    total = 0
    for t in re.findall(r"\*?(?:[ZBSCIJFD]|L[^;]+;)", mm.group(1)):
        total += 2 if t in ("J", "D") else 1
    return total


def patch_method_at(text, start, body_end):
    """patch_method core, positioned by byte offsets (method already known
    to contain a killProcess call)."""
    sig = text[start:text.find("\n", start)]
    if MARKER in text[start:body_end]:
        return text, "already patched"
    m = re.search(r"\.locals\s+(\d+)", text[start:body_end])
    if not m:
        return None, "no .locals directive (refusing .registers method)"
    n = int(m.group(1))
    pregs = param_registers(sig)
    # Dalvik non-range invokes address v0-v15 only. Bumping .locals shifts
    # parameter registers up (base n+4). This is ONLY a hazard when the
    # original parameters fit inside v15 (n+p-1 <= 15) — such code may legally
    # use non-range {pX} invokes — and the bump pushes them out. Methods whose
    # parameters ALREADY live beyond v15 (e.g. .locals 21) necessarily use
    # range invokes and are safe to patch.
    if n + pregs - 1 <= 15 and n + 4 + pregs - 1 > 15:
        return text, "skipped (register budget: locals=%d params=%d)" % (n, pregs)
    locals_start = start + m.start()
    locals_line_end = text.find("\n", locals_start)
    bumped = text[locals_start:locals_line_end].replace(
        ".locals %d" % n, ".locals %d" % (n + 2), 1)
    block = "\n    # %s\n" % MARKER + LOG_TMPL.format(n=n, n1=n + 1)
    text = text[:locals_start] + bumped + block + text[locals_line_end:]
    return text, "patched (locals %d -> %d)" % (n, n + 2)


if __name__ == "__main__":
    main()
