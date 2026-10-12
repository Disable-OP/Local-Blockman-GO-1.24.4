#!/usr/bin/env python3
"""Assemble the g10078 bundle v6 ADDITIONS into an existing v5 bundle server
tree (docs/10078_GAME_SERVER_UPDATE.md section 19: the 2019 config pass).

v6 adds TWO rooms — the 2019-era "config-less" games, now complete because
the 1.24.4-era OFFICIAL SERVER-SIDE SIDECARS were found in the maps.tar.gz
pack (per-map config.yml / *.yml / AppProps.csv published beside the world
zips on the CDN; the pack carries them under sandbox/games/maps/<mapid>):

  g1014 JailBreak   警匪大战  room  (open-world police/criminal sandbox)
  g1001 HungryGame  饥饿游戏  room  (time-gated battle royale)

THE MAP SOURCES (no blind reconstruction — everything is OFFICIAL data):
- g1014 -> maps/g1014/m1401 = maps_pack/m1401.1621495028871.zip, the
  COMPLETE 2021-05-20 official publish: world chunks + config.yml + ALL
  THIRTEEN game ymls (criminal/police/chest/merchant/produce/block/
  location/vehicle/door/damage/strongbox/rankNpc/transferGate) + AppProps
  + lang + minimap. Extracted as-is; nothing synthesized.
- g1001 -> maps/g1001/m1001_1 = the world zip g1001_1.1571834017333.zip
  (chunks + lang + minimap, 2019-10-23) + the official sidecar bundle
  maps_pack/m1001_1.1571834020240.zip (config.yml 16 KB + AppProps.csv)
  extracted OVER it. The sidecar config is the same-publish official data
  (507 ms apart on the CDN; its 16-point spawn circle at y=22 matches the
  dome arena).

THE SCRIPTS (g1014.1622268570616.zip / g1001.1622268463813.zip, the
2021-05 plugin re-publishes): old-style bare requires (like the PixelGun
family) — the v3 recipe applies: the 10068 overlay engine base goes to
<scriptdir>/base/ (the engine's ScriptManager HARD-LOADS
<scriptdir>/base/BaseMain.lua on Linux before ScriptMain.lua — verified
in the 10068 engine source, Script/ScriptManager.h), the server tree
merges at root. The trees' own engine_base/engine_client/engine_server
dirs are NOT wired (dead weight, same as every v2-v5 game).
GameConfig:init(config) reads the map's config.yml (BaseListener re-reads
it via FileUtil.getConfigFromYml("config") after the engine passes the
map path) — both official configs carry every key the 2019 scripts read
(g1001: waitingPlayerTime 150 / ffPos / inventory[1] loot pools /
respawn goods; g1014: initPos / shop / weapon / score + the 13 ymls).

THE START GATES (from the games' own code):
- g1001: WaitingPlayerTask is TIME-gated (starts on the FIRST login,
  expires after waitingPlayerTime 150 s -> DisableMove -> prepare ->
  startMatch; isPlayerFull short-circuits). No player-count gate — but
  the 2019 scripts are NOT AI-aware (PlayerListener builds GamePlayer
  per RakNet login; engine-spawned GamePlayerAI would hit nil fields on
  the scripts' per-tick player loops) -> wave 0 (on-device tunes).
- g1014: NO match gate at all (open world; initMatch just starts
  GameTimeTask) — wave 0 like Tycoon.
- Teams: 4 (the proven cycle) — no map team data in either game.

THE PixelGunGame REWIRE (the v4 latent-bug fix, found while wiring v6):
bundle v4 merged the overlay base68 AT ROOT (assemble_multigame_v4.py
"base68 at root") — but the Linux engine hard-loads
<scriptdir>/base/BaseMain.lua FIRST, and v4's PixelGunGame has NO base/:
the base load MISSES, and the game tree's BaseListener/BaseMain globals
(defined only by the base68 chain) never come into existence ->
GameListener:init() would die on BaseListener nil at the first boot on
device. The require-graph gate could not catch it (nothing REQUIRES
"base.BaseMain"; the engine loads it by PATH). v6 rebuilds
scripts/PixelGunGame to the same contract as every other room: base68 ->
base/, game tree (dl/p1043) -> root. All TWENTY-ONE rooms now satisfy
the engine contract.

Idempotent: wipes and rebuilds only the dirs it owns; re-extracts the
plugin zips itself. Fails loudly on any missing source or an incomplete
map (config.yml must exist after the merge).

Usage: assemble_multigame_v6.py <bundle-server-dir> <dl-dir> <overlay-base-dir>
"""
import os
import shutil
import subprocess
import sys

# gid -> (scriptdir Name, mapname, world zip, sidecar zip|None, plugin zip)
GAMES = {
    "g1001": ("HungryGame", "maps/g1001/m1001_1",
              "g1001_1.1571834017333.zip",
              "maps_pack/m1001_1.1571834020240.zip",
              "g1001.1622268463813.zip"),
    "g1014": ("JailBreak", "maps/g1014/m1401",
              "maps_pack/m1401.1621495028871.zip",
              None,
              "g1014.1622268570616.zip"),
}

# the v4 latent-bug fix: rebuild the shared PixelGun scriptdir onto the
# engine contract (base68 at base/, game tree at root)
PIXELGUN = ("PixelGunGame", "p1043", "g1043.1622268753875.zip")


def rm(p):
    if os.path.isdir(p):
        shutil.rmtree(p)
    elif os.path.exists(p):
        os.remove(p)


def merge_tree(src, dst):
    """Recursively merge src into dst WITHOUT clobbering sibling dirs
    (files overwrite)."""
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        tgt = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(tgt, exist_ok=True)
        for d in dirs:
            os.makedirs(os.path.join(tgt, d), exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(tgt, f))


def unzip(z, d):
    subprocess.run(["unzip", "-q", "-o", z, "-d", d], check=True)


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    bnd = os.path.abspath(sys.argv[1])
    dl = os.path.abspath(sys.argv[2])
    base68 = os.path.abspath(sys.argv[3])
    if not os.path.isdir(bnd):
        print("FATAL: no bundle server dir at %s" % bnd)
        sys.exit(1)
    if not os.path.isfile(os.path.join(base68, "BaseMain.lua")):
        print("FATAL: no engine base (BaseMain.lua) at %s" % base68)
        sys.exit(1)

    # 0. the PixelGunGame rewire (v4 latent-bug fix)
    name, pext, pzip = PIXELGUN
    ext = os.path.join(dl, pext)
    if not os.path.isdir(os.path.join(ext, "lua", "server")):
        z = os.path.join(dl, pzip)
        if not os.path.isfile(z):
            print("FATAL: missing plugin zip %s" % z)
            sys.exit(1)
        rm(ext)
        os.makedirs(ext)
        unzip(z, ext)
    sd = os.path.join(bnd, "scripts", name)
    rm(sd)
    os.makedirs(sd)
    merge_tree(base68, os.path.join(sd, "base"))
    merge_tree(os.path.join(ext, "lua", "server"), sd)
    if not os.path.isfile(os.path.join(sd, "base", "BaseMain.lua")):
        print("FATAL: PixelGunGame rewire produced no base/BaseMain.lua")
        sys.exit(1)
    n = sum(1 for r, _, fs in os.walk(sd) for f in fs if f.endswith(".lua"))
    print("== scripts/%s REWIRED (v4 fix): %d lua files, base/ contract OK"
          % (name, n))

    # 1. the two new rooms
    for gid, (name, mapname, worldzip, sidecarzip, plugzip) in sorted(GAMES.items()):
        z = os.path.join(dl, plugzip)
        if not os.path.isfile(z):
            print("FATAL: missing plugin zip %s" % z)
            sys.exit(1)
        ext = os.path.join(dl, "pg" + gid)
        rm(ext)
        os.makedirs(ext)
        unzip(z, ext)
        srv = os.path.join(ext, "lua", "server")
        if not os.path.isdir(srv):
            print("FATAL: %s has no lua/server" % plugzip)
            sys.exit(1)
        sd = os.path.join(bnd, "scripts", name)
        rm(sd)
        os.makedirs(sd)
        # v3 recipe: overlay base at <scriptdir>/base/ (the engine's
        # hardcoded first load), the old-style server tree at root.
        merge_tree(base68, os.path.join(sd, "base"))
        merge_tree(srv, sd)
        n_lua = sum(1 for r, _, fs in os.walk(sd)
                    for f in fs if f.endswith(".lua"))
        print("== scripts/%s (%s): %d lua files" % (name, gid, n_lua))

        # the map dir: world zip (+ the official sidecar bundle over it)
        wz = os.path.join(dl, worldzip)
        if not os.path.isfile(wz):
            print("FATAL: missing world zip %s" % wz)
            sys.exit(1)
        md = os.path.join(bnd, mapname)
        rm(os.path.dirname(md))
        os.makedirs(md)
        unzip(wz, md)
        if sidecarzip:
            sz = os.path.join(dl, sidecarzip)
            if not os.path.isfile(sz):
                print("FATAL: missing sidecar zip %s" % sz)
                sys.exit(1)
            unzip(sz, md)
        ok = os.path.isfile(os.path.join(md, "config.yml"))
        has_world = any(f.endswith(".mca") for f in os.listdir(md))
        has_props = os.path.isfile(os.path.join(md, "AppProps.csv"))
        n = sum(len(f) for _, _, f in os.walk(md))
        print("== %s: %d files, config.yml %s, world %s, AppProps %s" % (
            mapname, n, "OK" if ok else "MISSING",
            "OK" if has_world else "MISSING",
            "OK" if has_props else "MISSING"))
        if not (ok and has_world and has_props):
            sys.exit(1)

    # 2. ScriptSetting: Enable=1 + EngineVersion=10078 (no Name retarget —
    #    the rows already carry Name HungryGame / JailBreak)
    csvp = os.path.join(bnd, "ScriptSetting.csv")
    rows = open(csvp, encoding="utf-8", errors="replace").read().splitlines()
    out, flipped = [], []
    for r in rows:
        cols = r.split("\t")
        if len(cols) > 7 and cols[0] in GAMES:
            notes = []
            if cols[3] != "1":
                notes.append("enable")
                cols[3] = "1"
            if cols[7] != "10078":
                notes.append("ev %s->10078" % cols[7])
                cols[7] = "10078"
            if notes:
                flipped.append("%s: %s" % (cols[0], ", ".join(notes)))
                r = "\t".join(cols)
        out.append(r)
    open(csvp, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print("== ScriptSetting updates: %s" % (flipped or "none (already set)"))
    sys.exit(0)


if __name__ == "__main__":
    main()
