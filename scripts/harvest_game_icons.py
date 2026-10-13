#!/usr/bin/env python3
"""harvest_game_icons.py — pull the REAL game icons for the hosted 10078 rooms
from the Blockman GO CDN (staticgs.sandboxol.com) and pack them as the
localapi gameicons seed.

THE SOURCE (user-provided CDN dump, 2026-10-13):
  A URL list of the `sandboxPATHS(RARE).7z` bucket dump (bmg-region, Tencent
  COS) — see README_CDN_ms_timestamp_urls.txt next to it. The icon family is
  `sandbox/games/images/g<gid>-<millis>.<ext>`; the July-2020 sequential
  upload batch (ts ~1595505224203..1595508609926, g1001..g1058 ascending) is
  the OFFICIAL game-icon catalog art — one icon per game, uploaded game by
  game. Every hosted room id g1001..g1058 has its batch entry; g1061/g1062
  (added 2020-08) carry their own later .png uploads.

WHAT THE SCRIPT DOES
  1. parses the URL list, keeps the icon family per hosted game id;
  2. prefers the official batch window, downloads up to --max candidates
     per game (spread across the timestamp range);
  3. picks the most icon-like image (closest to square via PIL, tie ->
     newest), converts to PNG;
  4. packs ALL icons as assets/localapi/gameicons.tar.gz (deterministic:
     sorted entries, fixed mtime, ustar) + writes scripts/gameicons_manifest.json
     (per game: source key/url, bytes, sha256, w, h, chosen from N).

The APK ships the tar as assets/localapi/gameicons.tar.gz (build_signed_apk_282.sh);
LocalServer extracts it into <files>/localapi/gameicons/ and GameCatalog
rewrites every hosted game's gameCoverPic to the local streaming route
GET /localapi/games/icons/<gid>.png (LocalHttpd, GAMEICON log tag).

Usage:
  python3 scripts/harvest_game_icons.py <urls-file> [--max 6] [--offline-manifest]
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import time
import urllib.request

from PIL import Image

CDN = "https://staticgs.sandboxol.com/"
ICON_RE = re.compile(r"^sandbox/games/images/(g\d{4})-(\d{13})\.(png|webp|jpg|jpeg)$")

# The hosted 10078 rooms (bundle v7 / docs/10078_GAME_SERVER_UPDATE.md §19
# + the assemble_multigame v2..v6 recipes). gid -> display name.
HOSTED = {
    "g1001": "HungryGame",
    "g1008": "BedWar",
    "g1014": "JailBreak",
    "g1018": "EggWar",
    "g1025": "Tycoon",
    "g1041": "BirdSimulator",
    "g1042": "PixelGunHall",
    "g1043": "PixelGunGame (team)",
    "g1044": "PixelGunGame (solo)",
    "g1045": "PixelGunGame (duel)",
    "g1046": "BedWarHall",
    "g1048": "SkyBlock",
    "g1049": "SkyBlockMiningArea",
    "g1050": "SkyBlockProduct",
    "g1051": "WalkingDead",
    "g1054": "SkyWarLuckyBlock",
    "g1056": "TowerDefense",
    "g1057": "TowerDefenseHall",
    "g1058": "SkyWarLuckyBlockHall",
    "g1061": "BedWarSolo",
    "g1062": "BedWarDuo",
}

# The official July-2020 icon-catalog batch (sequential per-game uploads).
BATCH_LO, BATCH_HI = 1595500000000, 1595599999999


def collect(urlfile):
    per_game = {g: [] for g in HOSTED}
    with open(urlfile, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = ICON_RE.match(line.strip())
            if not m:
                continue
            gid, ts, ext = m.group(1), int(m.group(2)), m.group(3)
            if gid in per_game:
                per_game[gid].append((ts, ext, line.strip()))
    return per_game


def pick_candidates(entries, maxn):
    """Spread across the timeline: batch-window entries first (the official
    art), then the rest; newest and oldest always included."""
    if not entries:
        return []
    entries = sorted(set(entries))
    batch = [e for e in entries if BATCH_LO <= e[0] <= BATCH_HI]
    pool = batch if batch else entries
    if len(pool) <= maxn:
        return pool
    step = len(pool) / float(maxn)
    return [pool[int(i * step)] for i in range(maxn)]


def download(key):
    url = CDN + key
    req = urllib.request.Request(url, headers={"User-Agent": "localapi-icon-harvest/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def image_size(data):
    try:
        im = Image.open(io.BytesIO(data))
        return im.size, im
    except Exception:
        return None, None


def squareness(w, h):
    # 0 = perfect square; grows with the aspect delta
    return abs(w - h) / float(max(w, h))


def to_png(im):
    out = io.BytesIO()
    im.convert("RGBA").save(out, "PNG")
    return out.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urlfile")
    ap.add_argument("--max", type=int, default=6)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    args = ap.parse_args()

    per_game = collect(args.urlfile)
    out_dir = os.path.join(args.repo, "localapi-server", "assets", "localapi",
                           "gameicons")
    os.makedirs(out_dir, exist_ok=True)

    manifest = {"generated": int(time.time()), "cdn": CDN,
                "source": os.path.basename(args.urlfile), "games": {}}
    packed = {}
    misses = []

    for gid, name in sorted(HOSTED.items()):
        entries = per_game[gid]
        if not entries:
            misses.append((gid, name, "no icon keys in dump"))
            continue
        cands = pick_candidates(entries, args.max)
        best = None  # (sq, ts, data, w, h, key)
        tried = 0
        for ts, ext, key in cands:
            tried += 1
            try:
                data = download(key)
            except Exception as e:
                print(f"  ! {gid} {key}: {e}", file=sys.stderr)
                continue
            size, im = image_size(data)
            if not size:
                continue
            w, h = size
            sq = squareness(w, h)
            if best is None or sq < best[0] - 1e-9 or (
                    abs(sq - best[0]) <= 1e-9 and ts > best[1]):
                best = (sq, ts, to_png(im) if ext != "png" or True else data,
                        w, h, key)
            # a perfect square from the official batch wins outright
            if sq < 1e-9 and BATCH_LO <= ts <= BATCH_HI:
                break
        if best is None:
            misses.append((gid, name, "all candidates failed to download/parse"))
            continue
        sq, ts, png, w, h, key = best
        packed[gid] = (png, name)
        manifest["games"][gid] = {
            "name": name, "sourceKey": key, "url": CDN + key,
            "bytes": len(png), "sha256": hashlib.sha256(png).hexdigest(),
            "width": w, "height": h, "squareness": round(sq, 4),
            "sourceTs": ts, "candidatesTried": tried,
        }
        print(f"  {gid} {name}: {w}x{h} sq={sq:.3f} <- {key}")

    # deterministic tar.gz (ustar, sorted, fixed mtime) — the Skins pack recipe
    tar_path = os.path.join(args.repo, "localapi-server", "assets", "localapi",
                            "gameicons.tar.gz")
    with tarfile.open(tar_path, "w:gz", format=tarfile.USTAR_FORMAT) as tf:
        for gid in sorted(packed):
            png, name = packed[gid]
            info = tarfile.TarInfo(f"{gid}.png")
            info.size = len(png)
            info.mtime = 1577836800  # 2020-01-01, deterministic
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(png))
    size = os.path.getsize(tar_path)
    print(f"packed {len(packed)}/{len(HOSTED)} icons -> {tar_path} ({size} B)")

    man_path = os.path.join(args.repo, "scripts", "gameicons_manifest.json")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"manifest -> {man_path}")

    if misses:
        for gid, name, why in misses:
            print(f"MISS {gid} {name}: {why}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
