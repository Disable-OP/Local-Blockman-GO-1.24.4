#!/bin/sh
# run_smoke_localapi_compat.sh — one-command runner for the v7 compat
# behavioral gate (scripts/gameserver/smoke_localapi_compat.lua).
#
# The smoke needs a REAL Lua 5.1.5 interpreter. That interpreter used to
# live only in the ephemeral /tmp/lua_build — a sandbox restart killed the
# gate. This runner self-heals: if the interpreter is missing it rebuilds
# it offline from the repo-vendored sources via scripts/build_lua_515.sh
# (no network), then runs BOTH scenarios and asserts the 28/28 total:
#   scenario base18 : 13 checks
#   scenario g1008  : 15 checks
#
# Usage: sh scripts/run_smoke_localapi_compat.sh
set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEST="${LUA515_DEST:-/tmp/lua_build}"
LUA="$DEST/lua-5.1.5/src/lua"
SMOKE="$REPO/scripts/gameserver/smoke_localapi_compat.lua"

# self-heal the interpreter (build_lua_515.sh is idempotent)
if ! [ -x "$LUA" ] && ! "$LUA" -v >/dev/null 2>&1; then
    echo "smoke: interpreter missing — rebuilding offline..."
    sh "$REPO/scripts/build_lua_515.sh"
fi
"$LUA" -v >&2

total_passed=0
total_failed=0
run_scenario() {
    label="$1"; shift
    out=$("$LUA" "$SMOKE" "$@")
    echo "$out"
    p=$(printf '%s\n' "$out" | sed -n 's/.*: \([0-9]*\) passed, \([0-9]*\) failed/\1/p')
    f=$(printf '%s\n' "$out" | sed -n 's/.*: \([0-9]*\) passed, \([0-9]*\) failed/\2/p')
    [ -n "$p" ] || { echo "smoke: FATAL: no result line for scenario $label" >&2; exit 1; }
    total_passed=$((total_passed + p))
    total_failed=$((total_failed + f))
}

run_scenario base18
run_scenario g1008 g1008

echo "SMOKE TOTAL: $total_passed passed, $total_failed failed (expect 28/0)"
if [ "$total_passed" -ne 28 ] || [ "$total_failed" -ne 0 ]; then
    echo "smoke: GATE RED" >&2
    exit 1
fi
echo "smoke: GATE GREEN (28/28)"
