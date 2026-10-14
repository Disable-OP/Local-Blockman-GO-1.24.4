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
# RUN-24 DECODE (38536039296): /etc/hosts alone is NOT what the app
# processes resolve against on this redroid — bionic reads
# /system/etc/hosts, and the docker-style /etc/hosts bind-mount the
# image ships is invisible to the engine's own HTTP stack (its fetches
# of d401m01aifavw.cloudfront.net NEVER reached the holder: "HTTP
# status code: 0", zero /files/upload REQ lines in the LocalAPI log —
# the shell's ping check passed because the SHELL resolver reads
# /etc/hosts). Mirror the entries into /system/etc/hosts.
if ! grep -q "d32gv25kv9q34j.cloudfront.net" /system/etc/hosts 2>/dev/null; then
  mount -o rw,remount / 2>/dev/null || mount -o rw,remount /system 2>/dev/null || true
  {
    echo "# blockynexus drive (ondrive_setup.sh system hosts)"
    for h in $HOSTS_DROP; do echo "127.0.0.1 $h"; done
  } >> /system/etc/hosts 2>/dev/null || fail "cannot write /system/etc/hosts"
  say "system hosts: 3 lines appended"
else
  say "system hosts: already present"
fi
# The DNAT fallback (any :80 -> 127.0.0.1:18080) is a no-op without
# route_localnet: the kernel drops the martian 127.0.0.1-destined
# packet from a non-loopback interface and the fetcher sees status 0.
sysctl -w net.ipv4.conf.all.route_localnet=1 >/dev/null 2>&1 || true
sysctl -w net.ipv4.conf.default.route_localnet=1 >/dev/null 2>&1 || true
for IF in $(ls /proc/sys/net/ipv4/conf/ 2>/dev/null); do
  sysctl -w "net.ipv4.conf.$IF.route_localnet=1" >/dev/null 2>&1 || true
done
say "route_localnet: enabled (the DNAT fallback now works)"
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

# --- 3. iptables :80 -> 18080 REDIRECT (BEST EFFORT, session 86) --------------
# The holder ALSO answers :80 natively when the unprivileged-port sysctl is
# set (LocalServer's drive :80 listener), so a missing REDIRECT target is no
# longer fatal: the redroid's iptables 1.8.7-legacy ships WITHOUT the REDIRECT
# extension (run-4: "unknown option --to-ports") and some devices ship nft-only.
# Order: open the port range FIRST so the harness (booting after this script)
# can bind :80 without root.
if ! cat /proc/sys/net/ipv4/ip_unprivileged_port_start 2>/dev/null | grep -q '^0$'; then
  sysctl -w net.ipv4.ip_unprivileged_port_start=0 2>/dev/null \
    && say "sysctl: unprivileged port start -> 0 (:80 bindable by the holder)" \
    || say "WARN: cannot set ip_unprivileged_port_start (the :80 listener may fail)"
else
  say "sysctl: unprivileged port start already 0"
fi
if iptables -t nat -S OUTPUT 2>/dev/null | grep -q -- "--dport 80"; then
  say "iptables: dport 80 -> 18080 already present"
elif iptables -t nat -A OUTPUT -p tcp -d 127.0.0.1 --dport 80 \
    -j REDIRECT --to-ports 18080 2>/dev/null \
  || iptables -t nat -A OUTPUT -p tcp --dport 80 -j REDIRECT --to-ports 18080 2>/dev/null \
  || iptables -t nat -A OUTPUT -p tcp --dport 80 -j DNAT --to-destination 127.0.0.1:18080 2>/dev/null; then
  say "iptables: dport 80 -> 18080 added"
else
  say "WARN: no iptables REDIRECT/DNAT (the holder's native :80 listener covers the http hop)"
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
