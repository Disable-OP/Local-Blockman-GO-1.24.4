#!/usr/bin/env python3
"""Assemble the multi-game bundle additions (SkyBlock family + PixelGunHall)
into the g10078 bundle tree at /home/z/build_g10078/bundle — per
docs/10078_GAME_SERVER_UPDATE.md section 7 (the g1008 recipe), old-style games
(10068 layout): scripts/<Name>/{base = 10068 engine base, <game server tree>},
maps/g<gid>/<map>/, g1031_g1060/<Name>/ game settings, ScriptSetting Enable=1.
Idempotent: wipes and rebuilds only the per-game dirs it owns.
"""
import os, re, shutil, subprocess, sys

DL   = "/home/z/dl282"
BND  = "/home/z/build_g10078/bundle/server"
SRC  = "/home/z/src10078"
BASE68 = "/tmp/ovl/scripts/BedWar/base"   # the overlay tarball's base = the REAL 10068 engine base
# (runtime10068/bundle's base is a trimmed copy missing Base.lua/LuaTimer/uuid/CommonActivity*)

# gid -> (ScriptSetting Name, appres extract dir, map zip stem, ScriptSetting map name)
GAMES = {
    "g1048": ("SkyBlock",           f"{DL}/x1048", "m1048_1.1625218507296", "maps/g1048/m1048_1"),
    "g1049": ("SkyBlockMiningArea", f"{DL}/x1048", "m1049_2.1625218522432", "maps/g1049/m1049_2"),
    "g1050": ("SkyBlockProduct",    f"{DL}/x1048", "m1050_1.1625218530856", "maps/g1050/m1050_1"),
    "g1042": ("PixelGunHall",       f"{DL}/x1042", "m1042_1.1625218423007", "maps/g1042/m1042_1"),
}
GROUP = "g1031_g1060"

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

fail = False
for gid, (name, xdir, mapstem, mapname) in GAMES.items():
    print(f"== {gid} -> {name}")
    lua = f"{xdir}/Scripts/Game/{gid}/lua"
    srv = f"{lua}/server"
    if not os.path.isdir(srv):
        print(f"   FATAL: no server tree at {srv}")
        fail = True
        continue

    # 1. scripts/<Name>/ — base = the 10068 engine base, root = the game server tree
    sd = f"{BND}/scripts/{name}"
    rm(sd)
    os.makedirs(sd)
    cp(BASE68, f"{sd}/base")
    for item in sorted(os.listdir(srv)):
        cp(f"{srv}/{item}", f"{sd}/{item}")

    # 2. maps/g<gid>/<map>/ — the map zip contents
    md = f"{BND}/{mapname}"
    rm(os.path.dirname(md))          # wipe the whole maps/g<gid>/ we own
    os.makedirs(md)
    subprocess.run(["unzip", "-q", "-o", f"{DL}/{mapstem}.zip", "-d", md], check=True)

    # 3. g1031_g1060/<Name>/ — the game-setting tree (appres setting csvs)
    gd = f"{BND}/{GROUP}/{name}"
    rm(gd)
    os.makedirs(gd)
    st = f"{xdir}/Scripts/Game/{gid}/setting"
    if os.path.isdir(st):
        for f in sorted(os.listdir(st)):
            if f.endswith(".csv"):
                cp(f"{st}/{f}", f"{gd}/{f}")
    # game-level id_mappings: reuse the map zip's when it ships one (the 10078-era mapping)
    im = f"{md}/id_mappings.ini"
    if os.path.exists(im):
        cp(im, f"{gd}/id_mappings.ini")
    print(f"   scripts={len(os.listdir(sd))} entries, map files={sum(len(f) for _,_,f in os.walk(md))}, setting={len(os.listdir(gd))}")

# 4. ScriptSetting.csv — Enable 0->1 for our rows (server load is GameType-matched;
#    Enable matters for tooling/consistency only, but flip it for honesty)
# 5. EngineVersion 10078 on every row the 10078 line serves — the C2SLogin gate is
#    EXACT equality vs the client-reported engineVersion (C2SInitPacketHandles.cpp:
#    packet->m_engineVersion == EngineVersionSetting::getEngineVersion()), and the
#    2.8.2 client reports 10078 (assets/resources/Media/engineVersion.json). The row
#    value overwrites the engineVersion.json boot value in loadGameScriptDir, so a
#    90007/90900 row REJECTS every 10078 client. The 10068 line uses the OTHER
#    bundle (gameserver-runtime-g1008.tar.gz, rows at 90007) — mutually exclusive.
csvp = f"{BND}/ScriptSetting.csv"
rows = open(csvp, encoding="utf-8", errors="replace").read().splitlines()
out = []
flipped = []
for r in rows:
    cols = r.split("\t")
    if len(cols) > 7 and cols[0] in GAMES:
        if cols[4] == GAMES[cols[0]][3] and cols[3] == "0":
            cols[3] = "1"
            flipped.append(f"{cols[0]} enable")
            r = "\t".join(cols)
        if cols[7] != "10078":
            flipped.append(f"{cols[0]} ev {cols[7]}->10078")
            cols[7] = "10078"
            r = "\t".join(cols)
    out.append(r)
open(csvp, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"== ScriptSetting updates: {flipped}")
sys.exit(1 if fail else 0)
