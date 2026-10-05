#!/usr/bin/env python3
"""patch_tribeguide.py — neutralize TribeSettingGuideDialog.show().

The one-time clan-settings guide overlay (Ta, shown by
TribeHasViewModel.I() on the first owner clan-homepage open per
install) blocks the clan homepage UI on-device. Its own dismissal
paths cannot be driven: the top-right label tap (a()) opens the
settings sheet but ALSO f()-shows a fresh guide that never
self-dismisses (runs 37348093722 / 37351059115 / 37354556790 /
37358087903 / 37361712499), and the layout's bottom 'Clan Settings'
bar never appears in the uiautomator dump of either variant. The guide
is pure UX (a ReportDataAdapter event + a SharedUtils one-shot flag)
with no server contract, so making show() a no-op removes the overlay
for every future session while leaving I()'s flag bookkeeping and the
BottomDialog settings sheet fully intact.

Idempotent: an already-stubbed show() is detected and left alone.
Non-fatal when the class is absent (defensive)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MARKER_SHOW_EVENT = "clan_guide_time"
MARKER_CLASS = "clan_setup_time"
MARKER_SUPER = "Lcom/sandboxol/common/dialog/FullScreenDialog;"
STUB = (".method public show()V\n"
        "    .locals 0\n"
        "\n"
        "    return-void\n"
        ".end method\n")


def find_target(smali_root):
    """Locate the Ta.smali that IS the TribeSettingGuideDialog."""
    for dirpath, _dirnames, filenames in os.walk(smali_root):
        if not dirpath.replace(os.sep, "/").endswith("view/dialog"):
            continue
        for fn in filenames:
            if not fn.endswith(".smali"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            if MARKER_CLASS in text and MARKER_SUPER in text \
                    and ".method public show()V" in text:
                return path, text
    return None, None


def main():
    build_apktool = os.environ.get("APKTOOL_OUT") or os.path.join(
        ROOT, "build", "apktool_out")
    candidates = [p for p in (build_apktool,) if os.path.isdir(p)]
    if not candidates:
        print("patch_tribeguide: no apktool_out found (nothing to do)")
        sys.exit(0)
    for smali_root in candidates:
        path, text = find_target(smali_root)
        if not path:
            print("patch_tribeguide: no TribeSettingGuideDialog smali found "
                  "under %s (nothing to do)" % smali_root)
            continue
        start = text.index(".method public show()V")
        end = text.index(".end method", start) + len(".end method")
        body = text[start:end]
        if body.count("return-void") == 1 and "invoke" not in body \
                and len(body) < 200:
            print("patch_tribeguide: %s already stubbed" % path)
            return
        stub = STUB.rstrip("\n")
        patched = text[:start] + stub + text[end:]
        with open(path, "w", encoding="utf-8") as f:
            f.write(patched)
        print("patch_tribeguide: neutralized show() in %s" % path)
        return
    print("patch_tribeguide: no apktool_out found (nothing to do)")
    sys.exit(0)


if __name__ == "__main__":
    main()
