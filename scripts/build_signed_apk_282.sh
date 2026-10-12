#!/usr/bin/env bash
# build_signed_apk_282.sh — build the OFFICIAL Blockman GO 2.8.2 client
# (blockymods, engine 10078) into the local-holding APK.
#
# Strategy (resumable, no apktool b): the patched tree touches ONLY dexes
# + seed assets — resources/lib are byte-identical to the original. So:
#   1. assemble each patched smali_classesN dir with smali 2.5.2 (fast:
#      ~15 s per folder; apktool b would resmale all 7 in one 20+ min
#      non-resumable step and gets killed by the sandbox here)
#   2. start from the ORIGINAL bg282.apk and swap the dexes + add
#      classes8.dex (LocalAPI) + add the 3 seed assets
#   3. zipalign + sign (uber-apk-signer)
#
# Preconditions (idempotent smali patches, rerun after any fresh apktool d):
#   scripts/patch_urls_282.py / patch_bootstrap_282.py / patch_join_282.py
#   scripts/patch_rsa_key.py /home/z/bg282/apktool_out
#
# Usage: bash scripts/build_signed_apk_282.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TREE="${TREE_282:-/home/z/bg282/apktool_out}"
ORIG_APK="${ORIG_APK_282:-/home/z/bg282/bg282.apk}"
DEXOUT="${DEXOUT_282:-/home/z/bg282/dexout}"
BUILD="$REPO/build-282"
TOOLS="$REPO/build/tools"
SLIB="/home/z/tools/smali_lib"
OUT_DIR="${OUT_DIR_282:-$REPO/dist}"
SERVER_DEX="$REPO/localapi-server/build/classes6.dex"
mkdir -p "$DEXOUT" "$BUILD" "$OUT_DIR" "$TOOLS"

if [ ! -f "$TOOLS/uber-apk-signer.jar" ]; then
  curl -sSfL -o "$TOOLS/uber-apk-signer.jar" \
    https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar
fi

# --- sanity: the patched tree must carry the localapi hooks ---
grep -q "LocalServer;->startIfNeeded" "$TREE/smali/com/sandboxol/common/base/app/BaseApplication.smali" \
  || { echo "FATAL: bootstrap hook missing — run scripts/patch_bootstrap_282.py"; exit 1; }
# ALL THREE StartMc.startGame callers must be bridged: v (deprecated join
# dialog), utils/B (EnterGameHelperV2) and utils/x$a (EnterGameHelper) -
# the v-only bridge sat on DEAD CODE (zero live refs to EnterGameActivity),
# the 2.8.2 UI join booted local worlds through B/x$a.
for gate in \
  "smali_classes3/com/sandboxol/blockymods/view/activity/join/v.smali" \
  "smali_classes3/com/sandboxol/blockymods/utils/B.smali" \
  "smali_classes3/com/sandboxol/blockymods/utils/x\$a.smali"; do
  grep -q "JoinBridge;->takeOverJoin" "$TREE/$gate" \
    || { echo "FATAL: join bridge missing in $gate — run scripts/patch_join_282.py"; exit 1; }
done
if grep -rq '"https://d32gv25kv9q34j.cloudfront.net' "$TREE/smali" "$TREE"/smali_classes*/ 2>/dev/null; then
  echo "FATAL: unpatched cloudfront host — run scripts/patch_urls_282.py"; exit 1
fi
# v12: the seccomp guard must arm at the engine-load site (NOT at
# Application.onCreate — the TSS ctor detects an early filter and SIGILLs).
grep -q "armEngineGuardNow" "$TREE/smali/com/sandboxol/center/router/moduleInfo/game/AbstractEngineEnv.smali" \
  || { echo "FATAL: engine-load guard hook missing — run scripts/patch_seccomp_arm_282.py"; exit 1; }
grep -q "armEngineGuardNow" "$TREE/smali/com/sandboxol/blockmango/EchoesRenderer.smali" \
  || { echo "FATAL: renderer nativePreInit guard hook missing — run scripts/patch_seccomp_arm_282.py"; exit 1; }
[ -f "$SERVER_DEX" ] || { echo "FATAL: run scripts/build_server_dex.sh first"; exit 1; }

# --- seed assets (data-only) into the tree the packer reads from ---
echo "== seed assets =="
SEEDS="$TREE/assets/localapi"
mkdir -p "$SEEDS"
for pair in "skin.json:skins.json" "ScriptSetting.csv:ScriptSetting.csv"; do
  src="${pair%%:*}"; dst="${pair##*:}"
  if [ -f "$REPO/$src" ]; then cp -f "$REPO/$src" "$SEEDS/$dst";
  else echo "WARNING: seed $REPO/$src missing — ${dst} not shipped" >&2; fi
done
# THE ENGINE LINE: 2.8.2 client = engine 10078, g10078 bundle, no overlay.
cat > "$SEEDS/gs-line.json" <<'EOF'
{
  "line": "g10078",
  "clientEngineVersion": 10078,
  "stageVersion": "g10078-b1",
  "applyOverlay": false
}
EOF
echo "gs-line.json: g10078 / engine 10078 / overlay off"

# --- assemble dexes (per-folder, resumable) ---
echo "== smali assemble =="
CP="$SLIB/smali-2.5.2.jar:$SLIB/dexlib2-2.5.2.jar:$SLIB/util-2.5.2.jar:$SLIB/baksmali-2.5.2.jar:$SLIB/jcommander-1.64.jar:$SLIB/stringtemplate-3.2.1.jar:$SLIB/guava-14.0.1.jar:$SLIB/jsr305-1.3.9.jar:$SLIB/antlr-runtime-3.5.2.jar"
declare -A DIRS=( [smali]="classes.dex" [smali_classes2]="classes2.dex" \
  [smali_classes3]="classes3.dex" [smali_classes4]="classes4.dex" \
  [smali_classes5]="classes5.dex" [smali_classes6]="classes6.dex" \
  [smali_classes7]="classes7.dex" )
for d in smali smali_classes2 smali_classes3 smali_classes4 smali_classes5 smali_classes6 smali_classes7; do
  out="$DEXOUT/${DIRS[$d]}"
  # rebuild when the newest smali file is newer than the dex (idempotent)
  newest=$(find "$TREE/$d" -name '*.smali' -newer "$out" 2>/dev/null | head -1 || true)
  if [ -f "$out" ] && [ -z "$newest" ]; then
    echo "  skip ${DIRS[$d]} (up to date)"
    continue
  fi
  echo "  smaling $d -> ${DIRS[$d]}"
  java -Xmx1500m -cp "$CP" org.jf.smali.Main a -j 4 --api 29 -o "$out" "$TREE/$d"
done

# --- pack: original APK + swapped dexes + seeds + classes8 ---
echo "== pack APK =="
python3 - "$ORIG_APK" "$BUILD/patched-unsigned.apk" "$DEXOUT" "$SERVER_DEX" "$SEEDS" <<'EOF'
import sys, zipfile, os
orig, dst, dexdir, server_dex, seeds = sys.argv[1:6]
DEXES = {"classes.dex", "classes2.dex", "classes3.dex", "classes4.dex",
         "classes5.dex", "classes6.dex", "classes7.dex", "classes8.dex"}
SEED_FILES = ["skins.json", "ScriptSetting.csv", "gs-line.json"]
tmp = dst + ".tmp"
with open(server_dex, "rb") as f:
    server_payload = f.read()
with zipfile.ZipFile(orig) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        name = item.filename
        if name.startswith("META-INF/"):
            continue  # old signatures die here
        if name in DEXES:
            continue  # swapped below
        zout.writestr(item, zin.read(item.filename))
    # fresh dexes (assembled from the patched tree) — classes.dex..classes7.dex
    # + the server dex joins as classes8.dex (ART loads every classesN.dex)
    for name in ["classes.dex", "classes2.dex", "classes3.dex",
                 "classes4.dex", "classes5.dex", "classes6.dex",
                 "classes7.dex"]:
        with open(os.path.join(dexdir, name), "rb") as f:
            payload = f.read()
        zi = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
        zi.external_attr = 0o644 << 16
        zout.writestr(zi, payload, zipfile.ZIP_DEFLATED)
    zi = zipfile.ZipInfo("classes8.dex", (2026, 1, 1, 0, 0, 0))
    zi.external_attr = 0o644 << 16
    zout.writestr(zi, server_payload, zipfile.ZIP_DEFLATED)
    for name in SEED_FILES:
        p = os.path.join(seeds, name)
        if not os.path.isfile(p):
            continue
        zi = zipfile.ZipInfo(f"assets/localapi/{name}", (2026, 1, 1, 0, 0, 0))
        zi.external_attr = 0o644 << 16
        zout.writestr(zi, open(p, "rb").read(), zipfile.ZIP_DEFLATED)
os.replace(tmp, dst)
print("packed", dst, os.path.getsize(dst), "bytes")
EOF

# --- libgameserver.so into lib/armeabi-v7a/ (NEVER arm64-v8a here) ---
echo "== inject libgameserver.so (armeabi-v7a dir) =="
GSSO="$REPO/build/libgameserver.so"
if [ ! -f "$GSSO" ]; then
  GH_TOKEN="$(git -C "$REPO" config --get remote.origin.url | sed -n 's|https://x-access-token:\([^@]*\)@.*|\1|p')" \
    python3 "$REPO/scripts/fetch_release_asset.py" libgameserver-arm64.so "$GSSO"
fi
mkdir -p "$BUILD/libtmp/lib/armeabi-v7a"
cp -f "$GSSO" "$BUILD/libtmp/lib/armeabi-v7a/libgameserver.so"
# v10: the in-process seccomp engine guard (armv7, .init_array ctor) —
# loaded by LocalServer in the :BlockmanGo process; neutralizes the TSS
# verdict (exit/exit_group 25|30 -> ERRNO(ENOSYS)) regardless of the
# unreliable Zygote wrap property.
# v15: the guard is now the USER_NOTIF status-scrub supervisor
# (scripts/exithook/bgscomp.c — C source of truth, cross-compiled with
# arm-linux-gnueabihf-gcc; bgscomp.S is the retired v14 hand-asm build).
# The .so is committed; re-verify its embedded BPF against the C source:
python3 "$REPO/scripts/exithook/sim_bpf_bgscomp.py" "$REPO/scripts/exithook/bgscomp.c" \
  || { echo "FATAL: bgscomp BPF simulator mismatch"; exit 1; }
python3 "$REPO/scripts/exithook/sim_bpf_bgscomp.py" "$REPO/scripts/exithook/bgscomp.c" \
  --verify-so "$REPO/scripts/exithook/libbgscomp.so" \
  || { echo "FATAL: libbgscomp.so BPF bytes do not match bgscomp.c"; exit 1; }
cp -f "$REPO/scripts/exithook/libbgscomp.so" "$BUILD/libtmp/lib/armeabi-v7a/libbgscomp.so"
( cd "$BUILD/libtmp" && zip -q "$BUILD/patched-unsigned.apk" lib/armeabi-v7a/libgameserver.so lib/armeabi-v7a/libbgscomp.so )
unzip -l "$BUILD/patched-unsigned.apk" | grep -q 'lib/armeabi-v7a/libgameserver.so' \
  || { echo "FATAL: libgameserver.so missing from APK"; exit 1; }
unzip -l "$BUILD/patched-unsigned.apk" | grep -q 'lib/armeabi-v7a/libbgscomp.so' \
  || { echo "FATAL: libbgscomp.so missing from APK"; exit 1; }
echo "libgameserver.so injected into armeabi-v7a ($(stat -c%s "$GSSO") bytes)"
echo "libbgscomp.so injected into armeabi-v7a ($(stat -c%s "$REPO/scripts/exithook/libbgscomp.so") bytes)"

# --- zipalign + sign ---
echo "== sign =="
rm -f "$OUT_DIR"/patched-*igned*.apk
java -jar "$TOOLS/uber-apk-signer.jar" \
  --apks "$BUILD/patched-unsigned.apk" \
  --out "$OUT_DIR" ${KEYSTORE:+--ks "$KEYSTORE"} ${KS_PASS:+--ks-pass "$KS_PASS"} ${KS_ALIAS:+--ks-key-alias "$KS_ALIAS"}

APK_PATH=$(ls "$OUT_DIR"/patched-*igned*.apk 2>/dev/null | head -1 || true)
if [ -z "$APK_PATH" ]; then
  echo "FATAL: no signed APK found in $OUT_DIR" >&2
  exit 1
fi
mv -f "$APK_PATH" "$OUT_DIR/BlockyNexus-localapi-282.apk"
echo "SIGNED APK: $OUT_DIR/BlockyNexus-localapi-282.apk"
