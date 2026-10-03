#!/usr/bin/env bash
# build_signed_apk.sh — decompile (if needed), patch URLs, rebuild, zipalign+sign.
# Usage: BASE_APK=path/to/base.apk [OUT_DIR=dist] ./scripts/build_signed_apk.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_APK="${BASE_APK:?set BASE_APK=/path/to/blockman-custom-1.24.4.apk}"
OUT_DIR="${OUT_DIR:-$REPO/dist}"
BUILD="$REPO/build"
TOOLS="$BUILD/tools"
mkdir -p "$OUT_DIR" "$TOOLS"

# --- toolchain (downloaded once) ---
AUTH=(); [ -n "${GH_TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer $GH_TOKEN")
if [ ! -f "$TOOLS/apktool.jar" ]; then
  APKTOOL_URL=$(curl -s "${AUTH[@]}" "https://api.github.com/repos/iBotPeaches/Apktool/releases/latest" \
    | python3 -c "import sys,json;print([a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if a['name'].endswith('.jar')][0])")
  curl -sL -o "$TOOLS/apktool.jar" "$APKTOOL_URL"
fi
if [ ! -f "$TOOLS/uber-apk-signer.jar" ]; then
  UAS_URL=$(curl -s "${AUTH[@]}" "https://api.github.com/repos/patrickfav/uber-apk-signer/releases/latest" \
    | python3 -c "import sys,json;print([a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if a['name'].endswith('.jar')][0])")
  curl -sL -o "$TOOLS/uber-apk-signer.jar" "$UAS_URL"
fi

# --- decompile ---
if [ ! -d "$BUILD/apktool_out" ]; then
  echo "== apktool d =="
  java -jar "$TOOLS/apktool.jar" d "$BASE_APK" -o "$BUILD/apktool_out" -f
fi

# --- patch ---
echo "== patch_urls.py =="
python3 "$REPO/scripts/patch_urls.py"

echo "== patch_bootstrap.py (LocalServer hook) =="
python3 "$REPO/scripts/patch_bootstrap.py" "$BUILD/apktool_out/smali/com/disabngo/blockynexus/App.smali"

# --- embedded server dex ---
echo "== build_server_dex.sh =="
bash "$REPO/scripts/build_server_dex.sh"
SERVER_DEX="$REPO/localapi-server/build/classes6.dex"

# --- rebuild ---
echo "== apktool b =="
java -jar "$TOOLS/apktool.jar" b "$BUILD/apktool_out" -o "$BUILD/patched-unsigned.apk"

# --- inject classes6.dex (server + nanohttpd) into the APK ---
echo "== inject classes6.dex =="
zip -q -j "$BUILD/patched-unsigned.apk" "$SERVER_DEX"
unzip -l "$BUILD/patched-unsigned.apk" | grep -q classes6.dex || { echo "FATAL: classes6.dex missing"; exit 1; }

# --- zipalign + sign (uber-apk-signer does both; debug keystore by default) ---
echo "== sign =="
java -jar "$TOOLS/uber-apk-signer.jar" \
  --apks "$BUILD/patched-unsigned.apk" \
  --out "$OUT_DIR" ${KEYSTORE:+--ks "$KEYSTORE"} ${KS_PASS:+--ks-pass "$KS_PASS"} ${KS_ALIAS:+--ks-key-alias "$KS_ALIAS"}

APK_PATH=$(ls "$OUT_DIR"/patched-unsigned-*-signed*.apk 2>/dev/null | head -1 || true)
if [ -z "$APK_PATH" ]; then
  # uber-apk-signer names outputs alignedDebugApr2.apk etc under --out; normalize
  APK_PATH=$(ls "$OUT_DIR"/patched-unsigned.apk 2>/dev/null | head -1)
fi
if [ -n "$APK_PATH" ] && [ "$(readlink -f "$APK_PATH")" != "$(readlink -f "$OUT_DIR/BlockyNexus-localapi.apk")" ]; then
  mv -f "$APK_PATH" "$OUT_DIR/BlockyNexus-localapi.apk"
fi
echo "SIGNED APK: $OUT_DIR/BlockyNexus-localapi.apk"
