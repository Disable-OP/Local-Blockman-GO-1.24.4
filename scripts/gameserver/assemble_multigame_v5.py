#!/usr/bin/env python3
"""Assemble the g10078 bundle v5 ADDITIONS into an existing v4 bundle server
tree (docs/10078_GAME_SERVER_UPDATE.md section 18: the SkyWarLuckyBlock +
TowerDefense families).

v5 adds FOUR rooms in TWO families (the hall+room pattern again):

  g1054 SkyWarLuckyBlock       幸运方块(空岛)      room  (skywar + dragons)
  g1058 SkyWarLuckyBlockHall   幸运方块(空岛)大厅  hall
  g1056 TowerDefense           塔防                room  (tower defense)
  g1057 TowerDefenseHall       塔防大厅            hall

THE WIRING FACTS (all verified against the zips before assembly):
- Each gid has its OWN ScriptSetting Name -> its OWN scriptdir (unlike the
  PixelGun family's shared scriptdir). Maps ship COMPLETE room data
  (config.yml + setting/ + game csvs, g1054 even ships GameTeam.csv +
  mca chunks) — the v4-era completeness rule holds; the assembler still
  refuses any map without config.yml (the g1014/g1001 lesson, kept).
- WIRING = the v3 (BedWar-family) recipe, required by the require-graph
  gate: these trees are NEW-STYLE — 94 distinct `base.*` requires per
  tree (base.Base, base.DBManager, base.util.*, ...) — so the 10068
  overlay base goes to <scriptdir>/base/ (resolves ALL 94; the
  engine_base/engine_server trees inside the plugins resolve 55/38 of
  them — the overlay is the complete one), the plugins' own `lua/base/`
  (g1054 config/MountConfig.lua; g1056/g1057 BaseHeader.lua + its
  data/entity/manager/util deps — REQUIRED by their ScriptMain
  `require "BaseHeader"`) merges AT ROOT, the server tree merges at
  root (server files win collisions). Verified ZERO file collisions
  (base68 vs lua/base, lua/base vs lua/server) for all four plugins.
  No engine_server.*/engine_base.* requires anywhere (cleaner than the
  2021 BedWar hall — no 2-file engine_server wiring needed).
- Start gates:
  * g1054: Match.lua `getReadyPlayerCount() >= GameConfig.startPlayers`
    (map config.yml startPlayers 3) — the PROVEN BedWar-family gate:
    wave 2 bots can never satisfy it alone (2 < 3), one human joins ->
    3 -> starts. (The map ships GameTeam.csv; teams cycle the proven
    1..4, GameDef.teams=4.)
  * g1056: NO startPlayers — WaitPlayerStatus starts a process when
    `#playerList >= teammateNum` (teammateNum comes from the HALL queue
    and DEFAULTS TO 1). Any bot in the queue would auto-start a game
    with no human -> wave 0 (on-device observation tunes it later).
  * g1057/g1058: halls (no gate at all) — wave 0, like every hall.
- ScriptSetting rows need Enable=1 + EngineVersion 90900->10078 only
  (Name and MapName are already correct in the shipped csv).

Idempotent: wipes and rebuilds only the dirs it owns; re-extracts the
plugin zips itself (no pre-extraction step). Fails loudly on any missing
source or an incomplete map.

Usage: assemble_multigame_v5.py <bundle-server-dir> <dl-dir> <overlay-base-dir>
"""
import os
import shutil
import subprocess
import sys

# gid -> (scriptdir Name, mapname, map zip, plugin zip, merge lua/base?)
GAMES = {
    "g1054": ("SkyWarLuckyBlock", "maps/g1054/m1054_1",
              "g1054.1607690392415.zip", "g1054.1622268825079.zip", True),
    "g1056": ("TowerDefense", "maps/g1056/m1056_1",
              "TowerDefense.1584671960692.zip", "g1056.1622268839627.zip", True),
    "g1057": ("TowerDefenseHall", "maps/g1057/m1057_1",
              "TowerDefenseHall.1584085062106.zip", "g1057.1622268846040.zip", True),
    "g1058": ("SkyWarLuckyBlockHall", "maps/g1058/m1058_1",
              "m1058_1.1625218714165.zip", "g1058.1622268852365.zip", False),
}


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

    for gid, (name, mapname, mapzip, plugzip, merge_base) in sorted(GAMES.items()):
        z = os.path.join(dl, plugzip)
        if not os.path.isfile(z):
            print("FATAL: missing plugin zip %s" % z)
            sys.exit(1)

        # 1. the scriptdir: re-extract the plugin zip fresh (idempotent)
        ext = os.path.join(dl, "pg" + gid)
        rm(ext)
        os.makedirs(ext)
        subprocess.run(["unzip", "-q", "-o", z, "-d", ext], check=True)
        srv = os.path.join(ext, "lua", "server")
        if not os.path.isdir(srv):
            print("FATAL: %s has no lua/server" % plugzip)
            sys.exit(1)
        sd = os.path.join(bnd, "scripts", name)
        rm(sd)
        os.makedirs(sd)
        # v3 recipe: the 10068 overlay engine base at <scriptdir>/base/
        # (the trees' 94 base.* requires resolve there), the game-level
        # lua/base at ROOT, the server tree at root (server files win).
        merge_tree(base68, os.path.join(sd, "base"))
        if merge_base:
            lb = os.path.join(ext, "lua", "base")
            if os.path.isdir(lb):
                merge_tree(lb, sd)   # BaseHeader + deps (0 collisions, verified)
        merge_tree(srv, sd)          # server files win collisions
        n_lua = sum(1 for r, _, fs in os.walk(sd) for f in fs if f.endswith(".lua"))
        print("== scripts/%s (%s): %d lua files" % (name, gid, n_lua))

        # 2. the map dir (must ship config.yml + setting/)
        mz = os.path.join(dl, mapzip)
        if not os.path.isfile(mz):
            print("FATAL: missing map zip %s" % mz)
            sys.exit(1)
        md = os.path.join(bnd, mapname)
        rm(os.path.dirname(md))      # wipe the whole maps/g<gid>/ we own
        os.makedirs(md)
        subprocess.run(["unzip", "-q", "-o", mz, "-d", md], check=True)
        ok = os.path.isfile(os.path.join(md, "config.yml"))
        has_setting = os.path.isdir(os.path.join(md, "setting"))
        n = sum(len(f) for _, _, f in os.walk(md))
        print("== %s: %d files, config.yml %s, setting/ %s" % (
            mapname, n, "OK" if ok else "MISSING",
            "OK" if has_setting else "MISSING"))
        if not (ok and has_setting):
            sys.exit(1)

    # 3. ScriptSetting: Enable=1 + EngineVersion=10078 (no Name retarget)
    csvp = os.path.join(bnd, "ScriptSetting.csv")
    rows = open(csvp, encoding="utf-8", errors="replace").read().splitlines()
    out, flipped = [], []
    for r in rows:
        cols = r.split("\t")
        if len(cols) > 7 and cols[0] in GAMES:
            # columns: 0=GameType 1=GroupDirectory 2=Name 3=Enable 4=MapName
            #          5=ServerIP 6=ServerPort 7=EngineVersion 8=Remark
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
