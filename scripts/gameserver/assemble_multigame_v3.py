#!/usr/bin/env python3
"""Assemble the g10078 bundle v3 ADDITIONS into /home/z/build_g10078/bundle/server
(docs/10078_GAME_SERVER_UPDATE.md section 14: the BedWar family + four more games).

v2 (assemble_multigame.py) staged SkyBlock x3 + PixelGunHall from 10076-era appres.
v3 adds SEVEN games, two wirings:

  A. THE BEDWAR FAMILY (plugins SOURCE trees, June 2021 — pre-restructure, bare
     require, the same generation the v2 games use). The g1046/g1061/g1062
     plugins zips carry the FULL BedWar tree (base/client/engine_*/plugins/server)
     and their server trees are byte-identical — ScriptMain branches on GameType:
     g1046 -> hall.BedWarServer (the HALL: map/mode selection), else ->
     game.BedWarServer (the room). The engine picks scripts/<ScriptSetting.Name>,
     so each game gets its OWN scriptdir (BedWarHall/BedWarSolo/BedWarDuo) wired
     from its own plugins tree, while the proven g1008 room keeps scripts/BedWar
     (the tuned 2020 tree) untouched.
     LAYOUT LESSON (the require-graph gate caught it): the plugins tree keeps the
     game-level base SEPARATED (lua/base/{EventDefine,Loader,common,game,hall})
     while the engine contract is the FLATTENED tree — the 2020 overlay ships
     hall/BaseHeader.lua etc. merged at scriptdir root. So the scriptdir =
     engine base (overlay) + game-level base/* MERGED AT ROOT + the server tree
     (server files win collisions). Without the merge, hall/game BaseHeader,
     base.common.config.CommonActivityConfig and game.config.SkillConfig fail
     to resolve (12 unresolved requires across the family).
     Game-setting dirs: the g1046-10078 appres carries the 10078-era BedWar
     settings (id_mappings.ini + GeneralProbability*.csv under
     Scripts/Game/g1008/setting/) — the ONLY 10078-exact game settings on the CDN.

  B. APPRES GAMES (10076-era appres, SOURCE Lua, Scripts/Game/<gid>/lua/server):
     g1051 WalkingDead, g1041 BirdSimulator, g1025 Tycoon, g1018 EggWar.
     g1025/g1018 ship no setting csvs (their game-setting dir is created empty).

Maps: the map zips extract verbatim into maps/<gid>/<mapId>/ (they ship their
own checksums.md5 — none of them carries id_mappings.ini, the engine default
mapping applies; the BedWar family gets the 10078 one at game-setting level).

ScriptSetting rows: Enable=1 + EngineVersion=10078 on every served row (the
C2SLogin gate is EXACT equality vs the client-reported engineVersion — §7.1),
plus the BedWar-family Name retarget (BedWarHall/BedWarSolo/BedWarDuo).

Idempotent: wipes and rebuilds only the per-game dirs it owns. Fails loudly on
any missing source tree.
"""
import os, shutil, subprocess, sys

DL   = "/home/z/dl_games"                      # downloaded zips + their extracts
BND  = "/home/z/build_g10078/bundle/server"
BASE68 = "/tmp/ovl/scripts/BedWar/base"        # the overlay tarball's 10068 engine base

# ---------------------------------------------------------------- BedWar family
# gid -> (scriptdir Name, plugins extract dir, map zip stem, ScriptSetting mapname)
BEDWAR = {
    "g1046": ("BedWarHall", f"{DL}/p1046", "m1046_2.1625226493856", "maps/g1046/m1046_2"),
    "g1061": ("BedWarSolo", f"{DL}/p1061", "g1061.1620913134160",   "maps/g1061/m1061_1"),
    "g1062": ("BedWarDuo",  f"{DL}/p1062", "g1062.1620913155084",   "maps/g1062/m1062_1"),
}
# The 10078-era BedWar game settings (shared by the family), from the g1046-10078 appres.
BEDWAR_SETTING = f"{DL}/x1046/Scripts/Game/g1008/setting"
BEDWAR_SETTING_FILES = ["id_mappings.ini", "GeneralProbability.csv",
                        "GeneralProbabilityItem.csv"]
BEDWAR_GROUP = "g1001_g1030"

# ------------------------------------------------------------------- appres games
# gid -> (scriptdir Name, appres extract dir, map zip stem, ScriptSetting mapname, group)
APPRES = {
    "g1051": ("WalkingDead",    f"{DL}/x1051", "g1051.1571816766296",   "maps/g1051/m1051_1", "g1031_g1060"),
    "g1041": ("BirdSimulator",  f"{DL}/x1041", "m1041_2.1608544678374", "maps/g1041/m1041_2", "g1031_g1060"),
    "g1025": ("Tycoon",         f"{DL}/x1025", "g1025.1603281440181",   "maps/g1025/m1025_1", "g1001_g1030"),
    "g1018": ("EggWar",         f"{DL}/x1018", "m1018_1.1625218383894", "maps/g1018/m1018_1", "g1001_g1030"),
}

# The ScriptSetting Name each row must carry (v3 retargets the BedWar family).
ROW_NAME = {"g1046": "BedWarHall", "g1061": "BedWarSolo", "g1062": "BedWarDuo"}


def merge_tree(src, dst):
    """Recursively merge src into dst WITHOUT clobbering sibling dirs
    (shutil.copytree dirs_exist_ok semantics; files overwrite)."""
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        tgt = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(tgt, exist_ok=True)
        for d in dirs:
            os.makedirs(os.path.join(tgt, d), exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(tgt, f))


def rm(p):
    if os.path.isdir(p):
        shutil.rmtree(p)
    elif os.path.exists(p):
        os.remove(p)


def cp(src, dst):
    dst_parent = os.path.dirname(dst)
    os.makedirs(dst_parent, exist_ok=True)
    if os.path.isdir(src):
        rm(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def wire_map(gid, mapstem, mapname):
    md = f"{BND}/{mapname}"
    rm(os.path.dirname(md))          # wipe the whole maps/g<gid>/ we own
    os.makedirs(md)
    subprocess.run(["unzip", "-q", "-o", f"{DL}/{mapstem}.zip", "-d", md], check=True)
    return md


def wire_setting_dir(group, name, csv_dir, files=None):
    gd = f"{BND}/{group}/{name}"
    rm(gd)
    os.makedirs(gd)
    n = 0
    if csv_dir and os.path.isdir(csv_dir):
        srcs = files if files is not None else sorted(
            f for f in os.listdir(csv_dir) if f.endswith(".csv"))
        for f in srcs:
            if os.path.exists(f"{csv_dir}/{f}"):
                cp(f"{csv_dir}/{f}", f"{gd}/{f}")
                n += 1
    return gd, n


fail = False

for gid, (name, pdir, mapstem, mapname) in BEDWAR.items():
    print(f"== {gid} -> {name} (BedWar family, plugins tree)")
    srv = f"{pdir}/lua/server"
    if not os.path.isdir(srv):
        print(f"   FATAL: no server tree at {srv}")
        fail = True
        continue
    gbase = f"{pdir}/lua/base"
    if not os.path.isdir(gbase):
        print(f"   FATAL: no game-level base tree at {gbase}")
        fail = True
        continue
    sd = f"{BND}/scripts/{name}"
    rm(sd)
    os.makedirs(sd)
    cp(BASE68, f"{sd}/base")
    # the game-level base MERGES AT ROOT first, then the server tree merges
    # over it (server files win collisions; the 2020 overlay proves the
    # flattened contract). merge_tree, NOT cp — cp would clobber the whole
    # base/hall dir when the server tree ships its own hall/.
    merge_tree(gbase, sd)
    merge_tree(srv, sd)
    # Era-wiring (the require-graph gate's findings, minimal and verified):
    # 1. The 2021 hall's lazy require "base.common.config.CommonActivityConfig"
    #    (a restructured-era leftover: in the old layout "base.*" = the ENGINE
    #    base, which has no common/) — satisfy it by placing the game base's
    #    file at base/common/config/. The engine base has NO common/ dir, so
    #    zero collision.
    # 2. The only engine_server.* require in the whole tree is
    #    CommonActivityConfig's server branch (isClient else-branch, fired by
    #    the hall map's CommonActivitySetting.json): engine_server.data.
    #    CommonActivity -> engine_server.util.CommonActivityReportUtil (no
    #    further requires). Two files, zero collisions — wiring the WHOLE
    #    2021 engine_server tree would pull restructured "engine_base.*"
    #    requires that do not resolve in this old-style layout.
    es = f"{sd}/engine_server"
    os.makedirs(f"{es}/data", exist_ok=True)
    os.makedirs(f"{es}/util", exist_ok=True)
    cp(f"{pdir}/lua/engine_server/data/CommonActivity.lua",
       f"{es}/data/CommonActivity.lua")
    cp(f"{pdir}/lua/engine_server/util/CommonActivityReportUtil.lua",
       f"{es}/util/CommonActivityReportUtil.lua")
    os.makedirs(f"{sd}/base/common/config", exist_ok=True)
    cp(f"{gbase}/common/config/CommonActivityConfig.lua",
       f"{sd}/base/common/config/CommonActivityConfig.lua")
    md = wire_map(gid, mapstem, mapname)
    gd, n = wire_setting_dir(BEDWAR_GROUP, name, BEDWAR_SETTING, BEDWAR_SETTING_FILES)
    print(f"   scripts={len(os.listdir(sd))} entries, map files="
          f"{sum(len(f) for _, _, f in os.walk(md))}, setting={n}")

for gid, (name, xdir, mapstem, mapname, group) in APPRES.items():
    print(f"== {gid} -> {name} (appres tree)")
    srv = f"{xdir}/Scripts/Game/{gid}/lua/server"
    if not os.path.isdir(srv):
        print(f"   FATAL: no server tree at {srv}")
        fail = True
        continue
    sd = f"{BND}/scripts/{name}"
    rm(sd)
    os.makedirs(sd)
    cp(BASE68, f"{sd}/base")
    for item in sorted(os.listdir(srv)):
        cp(f"{srv}/{item}", f"{sd}/{item}")
    md = wire_map(gid, mapstem, mapname)
    gd, n = wire_setting_dir(group, name, f"{xdir}/Scripts/Game/{gid}/setting")
    print(f"   scripts={len(os.listdir(sd))} entries, map files="
          f"{sum(len(f) for _, _, f in os.walk(md))}, setting={n}")

# ------------------------------------------------------- ScriptSetting.csv edits
# v2's rule (Enable=1 + EngineVersion=10078 on the served rows) plus the v3
# BedWar-family Name retarget. Row match key: gid + the v3 mapname.
csvp = f"{BND}/ScriptSetting.csv"
rows = open(csvp, encoding="utf-8", errors="replace").read().splitlines()
out = []
flipped = []
want_names = {}
for gid, (name, _, _, mapname) in BEDWAR.items():
    want_names[gid] = (name, mapname)
for gid, (name, _, _, mapname, _) in APPRES.items():
    want_names[gid] = (name, mapname)

for r in rows:
    cols = r.split("\t")
    if len(cols) > 7 and cols[0] in want_names:
        # columns: 0=GameType 1=GroupDirectory 2=Name 3=Enable 4=MapName
        #          5=ServerIP 6=ServerPort 7=EngineVersion 8=Remark
        name, mapname = want_names[cols[0]]
        if cols[2] == name and cols[4] == mapname and cols[3] == "1" \
                and cols[7] == "10078":
            out.append(r)
            continue
        notes = []
        if cols[2] != name:
            notes.append(f"name {cols[2]}->{name}")
            cols[2] = name
        if cols[4] != mapname:
            notes.append(f"map {cols[4]}->{mapname}")
            cols[4] = mapname
        if cols[3] != "1":
            notes.append("enable")
            cols[3] = "1"
        if cols[7] != "10078":
            notes.append(f"ev {cols[7]}->10078")
            cols[7] = "10078"
        flipped.append(f"{cols[0]}: " + ", ".join(notes))
        r = "\t".join(cols)
    out.append(r)
open(csvp, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"== ScriptSetting updates: {flipped}")
sys.exit(1 if fail else 0)
