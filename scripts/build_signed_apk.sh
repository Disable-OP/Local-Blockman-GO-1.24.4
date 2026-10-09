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

# fetch_tool_jar <repo> <dest> — resolve the latest release jar URL and
# download it. Transient GitHub API hiccups (rate-limit/5xx payloads without
# 'assets') previously killed whole release builds; retry with backoff.
fetch_tool_jar() {
  local repo="$1" dest="$2" tries=0 url
  if [ -s "$dest" ]; then return 0; fi
  while :; do
    url=$(curl -s "${AUTH[@]}" "https://api.github.com/repos/$repo/releases/latest" \
      | python3 -c "import sys,json;d=json.load(sys.stdin);print([a['browser_download_url'] for a in d.get('assets',[]) if a['name'].endswith('.jar')][0]) if d.get('assets') else sys.exit(3)" ) \
      && break
    tries=$((tries + 1))
    if [ "$tries" -ge 5 ]; then
      echo "FATAL: could not resolve latest-release jar for $repo after $tries attempts" >&2
      return 1
    fi
    echo "toolchain resolve attempt $tries for $repo failed; retrying in $((tries * 15))s" >&2
    sleep $((tries * 15))
  done
  echo "downloading $dest"
  curl -sL --retry 3 -o "$dest" "$url"
}

if [ ! -f "$TOOLS/apktool.jar" ]; then
  fetch_tool_jar iBotPeaches/Apktool "$TOOLS/apktool.jar"
fi
if [ ! -f "$TOOLS/uber-apk-signer.jar" ]; then
  fetch_tool_jar patrickfav/uber-apk-signer "$TOOLS/uber-apk-signer.jar"
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

echo "== patch_killlog.py (kill-site stack logs) =="
python3 "$REPO/scripts/patch_killlog.py"

echo "== patch_tribeguide.py (one-time clan guide overlay off) =="
python3 "$REPO/scripts/patch_tribeguide.py"

echo "== patch_rsa_key.py (local RSA login keypair — Wave 11) =="
python3 "$REPO/scripts/patch_rsa_key.py" "$BUILD/apktool_out"

# --- embedded server dex ---
echo "== build_server_dex.sh =="
bash "$REPO/scripts/build_server_dex.sh"
SERVER_DEX="$REPO/localapi-server/build/classes6.dex"

# --- seed assets (data-only, never icon bytes) ---
# localapi/skins.json       — real skin catalog capture (1.6 MB)
# localapi/ScriptSetting.csv — the client's own game list w/ real ids (4 KB)
# The server copies them into its files dir at boot; icons are streamed
# from the downloaded pack, NOT shipped here.
echo "== seed assets =="
SEEDS="$BUILD/apktool_out/assets/localapi"
mkdir -p "$SEEDS"
for pair in "skin.json:skins.json" "ScriptSetting.csv:ScriptSetting.csv"; do
  src="${pair%%:*}"; dst="${pair##*:}"
  if [ -f "$REPO/$src" ]; then
    cp -f "$REPO/$src" "$SEEDS/$dst"
  else
    echo "WARNING: seed $REPO/$src missing — ${dst} not shipped" >&2
  fi
done

# --- rebuild ---
echo "== apktool b =="
java -jar "$TOOLS/apktool.jar" b "$BUILD/apktool_out" -o "$BUILD/patched-unsigned.apk"

# --- inject classes6.dex (server + nanohttpd) into the APK ---
echo "== inject classes6.dex =="
zip -q -j "$BUILD/patched-unsigned.apk" "$SERVER_DEX"
unzip -l "$BUILD/patched-unsigned.apk" | grep -q classes6.dex || { echo "FATAL: classes6.dex missing"; exit 1; }

# --- gameplay server binary (arm64) into nativeLibraryDir ---
# Packaged as lib*.so so PackageManager extracts it into the app's
# nativeLibraryDir — one of the few app-writable dirs an exec() is allowed
# from. Without it the client still works (map-download phase); with it the
# on-device GameServer starts at boot and real matches become reachable.
echo "== inject libgameserver.so (arm64) =="
GSSO="$BUILD/libgameserver.so"
if python3 "$REPO/scripts/fetch_release_asset.py" libgameserver-arm64.so "$GSSO"; then
  mkdir -p "$BUILD/libtmp/arm64-v8a"
  cp -f "$GSSO" "$BUILD/libtmp/arm64-v8a/libgameserver.so"
  ( cd "$BUILD/libtmp" && zip -q "$BUILD/patched-unsigned.apk" lib/arm64-v8a/libgameserver.so )
  unzip -l "$BUILD/patched-unsigned.apk" | grep -q 'libgameserver.so' \
    || { echo "FATAL: libgameserver.so missing from APK"; exit 1; }
  echo "libgameserver.so injected ($(stat -c%s "$GSSO") bytes)"
else
  echo "WARNING: libgameserver-arm64.so unavailable on releases — APK ships without the gameplay server" >&2
fi

# --- zipalign + sign (uber-apk-signer does both; debug keystore by default) ---
echo "== sign =="
java -jar "$TOOLS/uber-apk-signer.jar" \
  --apks "$BUILD/patched-unsigned.apk" \
  --out "$OUT_DIR" ${KEYSTORE:+--ks "$KEYSTORE"} ${KS_PASS:+--ks-pass "$KS_PASS"} ${KS_ALIAS:+--ks-key-alias "$KS_ALIAS"}

# uber-apk-signer renames "<in>-unsigned.apk" to "<base>-aligned-debugSigned.apk"
APK_PATH=$(ls "$OUT_DIR"/patched-*igned*.apk 2>/dev/null | head -1 || true)
if [ -z "$APK_PATH" ]; then
  APK_PATH=$(ls "$OUT_DIR"/*igned*.apk 2>/dev/null | rg -v '\.idsig' | head -1 || true)
fi
if [ -z "$APK_PATH" ]; then
  APK_PATH=$(ls "$OUT_DIR"/patched-unsigned.apk 2>/dev/null | head -1 || true)
fi
if [ -n "$APK_PATH" ]; then
  if [ "$(readlink -f "$APK_PATH" || true)" != "$(readlink -f "$OUT_DIR/BlockyNexus-localapi.apk" || true)" ]; then
    mv -f "$APK_PATH" "$OUT_DIR/BlockyNexus-localapi.apk" || true
  fi
else
  echo "FATAL: no signed APK found in $OUT_DIR" >&2
  ls -la "$OUT_DIR" >&2 || true
  exit 1
fi
echo "SIGNED APK: $OUT_DIR/BlockyNexus-localapi.apk"
[ -f "$OUT_DIR/BlockyNexus-localapi.apk" ]
