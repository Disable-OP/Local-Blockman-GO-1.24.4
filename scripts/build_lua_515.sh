#!/bin/sh
# build_lua_515.sh — offline, idempotent rebuild of the Lua 5.1.5 toolchain
# that the repo's Lua gates depend on:
#   /tmp/lua_build/lua-5.1.5/src/lua  (the behavioral smoke interpreter,
#       scripts/gameserver/smoke_localapi_compat.lua)
#   /tmp/lua_build/lpgate             (the static parse gate binary,
#       used by scripts/gameserver/patch_event_bridge_v7.py)
#
# Both binaries were session-ephemeral (/tmp) — a sandbox restart wiped
# them and silently degraded the gates (the parse gate fell back to
# "lpgate-missing" = pass-through; the smoke became unrunnable). This
# script rebuilds both from the repo-vendored sources, NO network needed:
#   scripts/gameserver/vendor/lua-5.1.5.tar.gz  md5 2e115fe26e435e33b0d5c022e4490567
#       (the official lua.org 5.1.5 tarball)
#   scripts/gameserver/vendor/lpgate.c          md5 802286c5aad13d39c68e0c15e63b1e79
# Build recipe mirrors the original session build: `make generic`
# (ANSI, no readline — the existing binary links only libm/libc, ldd-verified).
#
# Usage: sh scripts/build_lua_515.sh
# Override the destination with LUA515_DEST=<dir> (default /tmp/lua_build).
set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEST="${LUA515_DEST:-/tmp/lua_build}"
VENDOR="$REPO/scripts/gameserver/vendor"
TARBALL="$VENDOR/lua-5.1.5.tar.gz"
GATE_C="$VENDOR/lpgate.c"
LUA="$DEST/lua-5.1.5/src/lua"
LPGATE="$DEST/lpgate"

TARBALL_MD5="2e115fe26e435e33b0d5c022e4490567"
GATE_C_MD5="802286c5aad13d39c68e0c15e63b1e79"

die() { echo "build_lua_515: FATAL: $*" >&2; exit 1; }

# --- 0. vendor pins (fail loudly if the repo copies were corrupted) ---
echo "build_lua_515: verifying vendored source pins..."
echo "$TARBALL_MD5  $TARBALL" | md5sum -c - >/dev/null || die "lua-5.1.5.tar.gz md5 mismatch"
echo "$GATE_C_MD5  $GATE_C"   | md5sum -c - >/dev/null || die "lpgate.c md5 mismatch"

# --- 1. idempotence: already built and ALIVE? ---
GATE_PROBE="$DEST/.gate_probe.lua"
if [ -x "$LUA" ] && [ -x "$LPGATE" ] \
   && "$LUA" -v >/dev/null 2>&1 \
   && printf 'return 1\n' > "$GATE_PROBE" && "$LPGATE" "$GATE_PROBE" >/dev/null 2>&1; then
    echo "build_lua_515: up-to-date ($LUA + $LPGATE)"
    exit 0
fi

# --- 2. build from the vendored tarball ---
command -v make >/dev/null || die "make not found"
command -v cc   >/dev/null || die "cc not found"
mkdir -p "$DEST"
rm -rf "$DEST/lua-5.1.5"
tar -xzf "$TARBALL" -C "$DEST"
echo "build_lua_515: make generic (ANSI, no readline)..."
make -C "$DEST/lua-5.1.5" generic >/dev/null
[ -x "$LUA" ] || die "lua binary missing after make"

echo "build_lua_515: compiling lpgate (the lua_parse gate binary)..."
cc -O2 -I "$DEST/lua-5.1.5/src" -o "$LPGATE" "$GATE_C" "$DEST/lua-5.1.5/src/liblua.a" -lm
[ -x "$LPGATE" ] || die "lpgate binary missing after cc"

# --- 3. prove both work: parse a GOOD file (rc 0) and a BAD one (rc 1) ---
printf 'return 1\n' > "$GATE_PROBE"
"$LUA" -v >&2
"$LPGATE" "$GATE_PROBE" >/dev/null || die "lpgate rejects a valid lua file"
printf 'x =\n' > "$GATE_PROBE"
if "$LPGATE" "$GATE_PROBE" >/dev/null 2>&1; then
    die "lpgate accepts an invalid lua file"
fi
rm -f "$GATE_PROBE"

echo "build_lua_515: DONE"
echo "  lua:    $LUA"
echo "  lpgate: $LPGATE"
