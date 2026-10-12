#!/usr/bin/env python3
"""Assemble the g10078 bundle v4 ADDITIONS into an existing v3 bundle server
tree (docs/10078_GAME_SERVER_UPDATE.md section 17: the PixelGun room family).

v4 adds the PIXELGUN ROOM FAMILY — the three rooms behind the already-staged
PixelGunHall (g1042, v2):

  g1043 PixelGunGame 像素射击团队  (team room)
  g1044 PixelGunGame 像素射击个人  (solo room)
  g1045 PixelGunGame 像素射击单挑  (duel room)

THE WIRING FACTS (all verified against the June-2021 plugin zips + the
2020-12 map zips):
- The three plugin trees are BYTE-IDENTICAL (diff -r = empty) and the
  ScriptSetting rows for all three gids share Name "PixelGunGame" — ONE
  scriptdir serves all three rooms; the room selection is the map
  (serverConfig mapdir), exactly how the real system ran it.
- The server tree is OLD-STYLE bare requires (config.*, listener.*, skill.*,
  property.*, process.*, settlement.*, events.*, data.*, task.*, messages.*,
  packet.*) — 143 requires, ZERO missing inside the tree, ZERO
  engine-namespace requires. Wiring = the 10068 overlay engine base under
  base/ (the same recipe as every v2/v3 game) + the server tree at root.
- The map zips are the 2020/2021 generation and ship COMPLETE room data:
  config.yml (startPlayers 6/6/2, maxPlayers 16, gameType, initPos),
  setting/ csvs, GunConfig/TeamConfig/Skill csvs — no config
  reconstruction needed (unlike the 2019-era g1014/g1001 maps, which lack
  config.yml/setting and were REJECTED for v4 on that basis).
- The games carry a startPlayers gate (WaitingPlayerTask reads
  GameConfig.startPlayers): g1043 6 -> wave 5, g1044 6 -> wave 5, g1045
  2 -> wave 1. Teams: the maps ship TeamConfig.csv; the wave cycles the
  proven 1..4 (GameDef.teams=4) — on-device observation tunes it.

ScriptSetting: Enable=1 + EngineVersion=10078 on the three rows (Name and
MapName already correct — no retarget).

Idempotent: wipes and rebuilds only the dirs it owns. Fails loudly on any
missing source tree.

Usage: assemble_multigame_v4.py <bundle-server-dir> <dl-dir> <overlay-base-dir>
"""
import os
import shutil
import subprocess
import sys

# gid -> (map zip stem, ScriptSetting mapname)
ROOMS = {
    "g1043": ("g1043.1607687347157", "maps/g1043/m1043_1"),
    "g1044": ("g1044.1617244814505", "maps/g1044/m1044_1"),
    "g1045": ("g1045.1607687392161", "maps/g1045/m1045_1"),
}
PLUGIN_ZIP = "g1043.1622268753875.zip"  # any of the three; trees identical
SCRIPTDIR = "PixelGunGame"


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

    # 1. the scriptdir (one tree, three rooms)
    plug = os.path.join(dl, "p1043")
    srv = os.path.join(plug, "lua", "server")
    if not os.path.isdir(srv):
        print("FATAL: extract %s to %s first" % (PLUGIN_ZIP, plug))
        sys.exit(1)
    sd = os.path.join(bnd, "scripts", SCRIPTDIR)
    rm(sd)
    os.makedirs(sd)
    merge_tree(base68, sd)      # the 10068 overlay engine base AT ROOT
    merge_tree(srv, sd)         # server files win collisions
    n_lua = sum(1 for r, _, fs in os.walk(sd) for f in fs if f.endswith(".lua"))
    print("== scripts/%s: %d lua files" % (SCRIPTDIR, n_lua))

    # 2. the three map dirs (each zip carries config.yml + setting/ + csvs)
    for gid, (stem, mapname) in sorted(ROOMS.items()):
        z = os.path.join(dl, stem + ".zip")
        md = os.path.join(bnd, mapname)
        rm(os.path.dirname(md))  # wipe the whole maps/g<gid>/ we own
        os.makedirs(md)
        subprocess.run(["unzip", "-q", "-o", z, "-d", md], check=True)
        ok = os.path.isfile(os.path.join(md, "config.yml"))
        n = sum(len(f) for _, _, f in os.walk(md))
        print("== %s: %d files, config.yml %s" % (mapname, n,
                                                  "OK" if ok else "MISSING"))
        if not ok:
            sys.exit(1)

    # 3. ScriptSetting: Enable=1 + EngineVersion=10078 (no Name retarget)
    csvp = os.path.join(bnd, "ScriptSetting.csv")
    rows = open(csvp, encoding="utf-8", errors="replace").read().splitlines()
    out, flipped = [], []
    for r in rows:
        cols = r.split("\t")
        if len(cols) > 7 and cols[0] in ROOMS:
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
