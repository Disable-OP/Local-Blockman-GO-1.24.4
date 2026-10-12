#!/system/bin/sh
# ondrive_collect.sh — RUN ON THE DEVICE (root not strictly required, more with it)
# Usage: sh /sdcard/drive/ondrive_collect.sh [step-label]
# Snapshots everything a session report needs into /sdcard/drive/evidence-<label>.tar.gz

LABEL=${1:-step}
OUT="/sdcard/drive/evidence-$LABEL"
HARNESS_PKG="com.disabngo.blockynexus"
FILES_DIR="/data/data/$HARNESS_PKG/files"

rm -rf "$OUT"; mkdir -p "$OUT" || { echo "[collect] cannot mkdir $OUT"; exit 1; }
say() { echo "[collect] $*"; }

# device identity + network rules
getprop > "$OUT/props.txt" 2>/dev/null
cat /etc/hosts > "$OUT/hosts.txt" 2>/dev/null
iptables -t nat -S > "$OUT/iptables-nat.txt" 2>/dev/null
ls -la /system/etc/security/cacerts/ > "$OUT/cacerts.txt" 2>/dev/null

# holder live probes (http + the TLS hop through the redirected host)
curl -s -m 5 "http://127.0.0.1:18080/health" > "$OUT/health-http.json" 2>/dev/null
CA0=$(ls /sdcard/drive/*.0 2>/dev/null | head -n 1)
[ -n "$CA0" ] && curl -s -m 8 --cacert "$CA0" \
  "https://d32gv25kv9q34j.cloudfront.net/health" > "$OUT/health-tls.json" 2>/dev/null

# harness state (root)
if [ -d "$FILES_DIR" ]; then
  mkdir -p "$OUT/files"
  cp "$FILES_DIR/localapi/gs_line.json" "$OUT/files/" 2>/dev/null
  cp "$FILES_DIR/localapi/state.json" "$OUT/files/" 2>/dev/null
  ls -la "$FILES_DIR/drive/" > "$OUT/files/drive-ls.txt" 2>/dev/null
  cat "$FILES_DIR/drive/tls.active" > "$OUT/files/tls.active" 2>/dev/null
  cp "$FILES_DIR"/seccomp_guard.log "$OUT/files/" 2>/dev/null
fi

# logcat: the filterable tags + a full safety net
logcat -d -s LocalAPI:V GS:V BLOCK:V > "$OUT/logcat-holder.txt" 2>/dev/null
logcat -d > "$OUT/logcat-full.txt" 2>/dev/null

# GameServer monitor/state dumps are inside filesDir (root).
# Staged bundle: GameServerManager.BUNDLE_DIR = filesDir/gameserver-bundle
# (NOT localapi/gameserver-runtime-* — that path never existed).
BUNDLE="$FILES_DIR/gameserver-bundle"
ls -la "$BUNDLE" > "$OUT/files/bundle-ls.txt" 2>/dev/null
cat "$BUNDLE/stage-version" > "$OUT/files/stage-version" 2>/dev/null
ls -la "$BUNDLE/logs" > "$OUT/files/bundle-logs-ls.txt" 2>/dev/null
cp "$BUNDLE"/logs/*.log "$OUT/files/" 2>/dev/null

# The engine's monitor log (server.log) + the client's client.log live in the
# CLIENT config dir (GameServerManager.resolveLogDir order): the external
# storage root first, the harness's own external dir as fallback, the staged
# bundle's logs/ as last resort. Capture every candidate that exists.
for CFG in "/storage/emulated/0/SandBoxOL/BlockMan/config" \
           "/sdcard/SandBoxOL/BlockMan/config" \
           "/sdcard/Android/data/$HARNESS_PKG/files/SandBoxOL/config"; do
  [ -d "$CFG" ] || continue
  { echo "logdir-candidate: $CFG"; ls -la "$CFG" 2>/dev/null; } \
    >> "$OUT/files/logdir.txt"
  cp "$CFG/server.log" "$OUT/files/server.log" 2>/dev/null
  cp "$CFG/client.log" "$OUT/files/client.log" 2>/dev/null
done

TAR="/sdcard/drive/evidence-$LABEL.tar.gz"
tar -czf "$TAR" -C "$(dirname "$OUT")" "$(basename "$OUT")" 2>/dev/null
say "evidence: $TAR ($(du -k "$TAR" 2>/dev/null | cut -f1) KB) — adb pull it"
