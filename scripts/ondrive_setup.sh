#!/system/bin/sh
# ondrive_setup.sh — RUN ON THE DEVICE AS ROOT (sh /sdcard/drive/ondrive_setup.sh)
# Idempotent network/store/staging setup for the pristine 2.8.2 drive.
# See docs/ON_DEVICE_DRIVE.md §4. Exits non-zero on the first broken check.

HARNESS_PKG="com.disabngo.blockynexus"
HOSTS_DROP="d32gv25kv9q34j.cloudfront.net d401m01aifavw.cloudfront.net mods.sandboxol.com"
DRIVE_SRC="/sdcard/drive"
FILES_DIR="/data/data/$HARNESS_PKG/files"
TLS_PORT_EXPECT=$(cat "$DRIVE_SRC/tls.port" 2>/dev/null || echo 443)
HASH0=$(ls "$DRIVE_SRC"/*.0 2>/dev/null | head -n 1)
CA_FILE="${HASH0:-$DRIVE_SRC/ca.pem}"
CA_NAME=$(basename "$CA_FILE" 2>/dev/null)

say() { echo "[ondrive] $*"; }
fail() { echo "[ondrive] FAIL: $*"; exit 1; }

[ -d "$DRIVE_SRC" ] || fail "$DRIVE_SRC missing (adb push drive /sdcard/drive first)"
[ -f "$DRIVE_SRC/server.p12" ] || fail "server.p12 missing in $DRIVE_SRC (run gen_drive_ca.py on the PC)"
[ -n "$CA_NAME" ] || fail "no <hash>.0 CA file in $DRIVE_SRC"

# --- 1. /etc/hosts -----------------------------------------------------------
if ! grep -q "d32gv25kv9q34j.cloudfront.net" /etc/hosts 2>/dev/null; then
  mount -o rw,remount / 2>/dev/null || mount -o rw,remount /system 2>/dev/null || true
  {
    echo "# blockynexus drive (ondrive_setup.sh)"
    for h in $HOSTS_DROP; do echo "127.0.0.1 $h"; done
  } >> /etc/hosts
  say "hosts: 3 lines appended"
else
  say "hosts: already present"
fi
ping -c 1 -W 1 d32gv25kv9q34j.cloudfront.net 2>/dev/null | head -n 1 | \
  grep -q "127.0.0.1" || fail "hosts redirect not effective (netd cache? reboot)"

# --- 2. SYSTEM CA store ------------------------------------------------------
CACERTS="/system/etc/security/cacerts"
if [ ! -f "$CACERTS/$CA_NAME" ]; then
  mount -o rw,remount / 2>/dev/null || mount -o rw,remount /system 2>/dev/null || true
  cp "$CA_FILE" "$CACERTS/$CA_NAME" || fail "cannot write $CACERTS (magisk module alternative: use the bind-copy recipe in docs)"
  chmod 644 "$CACERTS/$CA_NAME"
  chown root:root "$CACERTS/$CA_NAME" 2>/dev/null || true
  say "cacerts: $CA_NAME installed"
else
  say "cacerts: $CA_NAME already installed"
fi

# --- 3. iptables :80 -> 18080 REDIRECT ---------------------------------------
if ! iptables -t nat -S OUTPUT 2>/dev/null | grep -q -- "--dport 80"; then
  iptables -t nat -A OUTPUT -p tcp -d 127.0.0.1 --dport 80 \
    -j REDIRECT --to-ports 18080 2>/dev/null \
  || iptables -t nat -A OUTPUT -p tcp --dport 80 -j REDIRECT --to-ports 18080 \
  || fail "iptables REDIRECT failed"
  say "iptables: dport 80 -> 18080 added"
else
  say "iptables: already present"
fi

# --- 4. stage drive/ into the harness filesDir --------------------------------
DEST="$FILES_DIR/drive"
mkdir -p "$DEST" || fail "cannot mkdir $DEST (is the harness installed?)"
cp "$DRIVE_SRC/server.p12" "$DEST/server.p12" || fail "staging server.p12"
cp "$DRIVE_SRC/tls.port" "$DEST/tls.port" 2>/dev/null || true
OWNER=$(stat -c "%u.%g" "$FILES_DIR" 2>/dev/null || stat -f "%u.%g" "$FILES_DIR")
chown -R "$OWNER" "$DEST" 2>/dev/null || true
chmod 600 "$DEST/server.p12"
say "staged: $DEST/server.p12 (owner $OWNER, tls.port $TLS_PORT_EXPECT)"

# --- 5. verify (holder must be running for 5/6) -------------------------------
say "verify: http holder"
curl -s -m 5 "http://127.0.0.1:18080/health" | grep -q '"code":1' \
  || say "WARN holder not answering yet (boot the harness, then re-run this script)"
say "verify: TLS drive listener"
if curl -s -m 8 --cacert "$CA_FILE" \
     "https://d32gv25kv9q34j.cloudfront.net/health" | grep -q '"code":1'; then
  say "verify: TLS OK (SAN + chain + redirect all good)"
else
  say "WARN TLS not answering yet (stage the keystore BEFORE booting the harness; re-run after boot)"
fi
say "done — next: docs/ON_DEVICE_DRIVE.md §5"
