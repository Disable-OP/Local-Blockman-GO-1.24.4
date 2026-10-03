#!/usr/bin/env bash
# release_and_test.sh — create release v0.2.0-localapi with the embedded-server APK, dispatch CI.
# Token is read from git config (never printed).
set -euo pipefail
cd "$(dirname "$0")"  # repo root

URL=$(git config branch.local-api.remote)
TOKEN=$(echo "$URL" | sed -n 's|https://x-access-token:\([^@]*\)@.*|\1|p')
[ -n "$TOKEN" ] || { echo "no token in git config"; exit 1; }
API="https://api.github.com/repos/Disable-OP/Local-Blockman-GO-1.24.4"
UP="https://uploads.github.com/repos/Disable-OP/Local-Blockman-GO-1.24.4"
AUTH="Authorization: Bearer $TOKEN"
TAG="v0.2.0-localapi"

echo "== create release $TAG =="
REL=$(curl -s -X POST -H "$AUTH" "$API/releases" \
  -d "{\"tag_name\":\"$TAG\",\"name\":\"BlockyNexus localapi $TAG\",\"prerelease\":true,\"body\":\"First APK with the embedded local API server (Phase 1):\\n- NanoHTTPD loopback server 127.0.0.1:18080 inside the app\\n- 320 routes from 27 Retrofit interfaces, 21 state-backed handlers (auth/register/visitor/tourist/profile/configs)\\n- persistent JSON state, schema-true defaults for all other routes\\n- CI now runs full UI automation (register, login, navigate all tabs, crash scan)\"}")
RID=$(echo "$REL" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
[ -n "$RID" ] || { echo "release create failed:"; echo "$REL" | head -5; exit 1; }
echo "release id: $RID"

echo "== upload APK (232MB, be patient) =="
CODE=$(curl -s -o /tmp/upload_resp.json -w "%{http_code}" -X POST \
  -H "$AUTH" -H "Content-Type: application/octet-stream" \
  -T dist/BlockyNexus-localapi.apk \
  "$UP/releases/$RID/assets?name=BlockyNexus-localapi.apk")
echo "upload http: $CODE"
[ "$CODE" = "201" ] || { cat /tmp/upload_resp.json | head -5; exit 1; }

echo "== also upload as BlockyNexus-localapi-$TAG.apk? skip — one asset =="
echo "== dispatch test-redroid =="
DCODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$AUTH" \
  -H "Accept: application/vnd.github+json" \
  "$API/actions/workflows/test-redroid.yml/dispatches" -d "{\"ref\":\"local-api\"}")
echo "dispatch http: $DCODE (204 = ok)"
echo "DONE"
