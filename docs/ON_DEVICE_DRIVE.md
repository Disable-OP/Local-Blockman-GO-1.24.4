# ON_DEVICE_DRIVE.md — the pristine 2.8.2 client drive (delta-13 architecture)

The endgame: the **OFFICIAL** Blockman GO 2.8.2 (`com.sandboxol.blockymods`,
md5 `59d9946d341ec1550337aaaba9465cd6`, engine 10078) runs UNMODIFIED on a
rooted armeabi-v7a device and is driven into games by our holder — no APK
patching, nothing for the TSS to detect. This runbook is everything a device
session needs; the sandbox already host-proves the contract (**suite 701/701**
incl. the drive-TLS wave).

## 1. What runs where

```
+--------------------------------------------------------------+
| v7a DEVICE (root)                                            |
|                                                              |
|  com.disabngo.blockynexus   (the PATCHED b7 harness APK)     |
|    holder   127.0.0.1:18080  http  (397+ routes, 21 games)   |
|    driveTLS 127.0.0.1:443    https (DriveTls, drive/server.p12)
|    GameServer libgameserver.so (g10078 bundle v6 staged)     |
|                                                              |
|  com.sandboxol.blockymods   (the OFFICIAL 2.8.2 APK)         |
|    API base  https://d32gv25kv9q34j.cloudfront.net --+        |
|    failover  http://mods.sandboxol.com               |        |
|    engineRes http://d401m01aifavw.cloudfront.net ... |        |
|                                                      v        |
|  /etc/hosts: all three -> 127.0.0.1                          |
|  iptables NAT: OUTPUT dport 80 -> REDIRECT 18080             |
|  (443 hits DriveTls directly; the CA is in the SYSTEM store) |
|                                                              |
|  static.sandboxol.com / staticgs.sandboxol.com stay REAL     |
|  (the CDN still serves images/appres/maps — by design)       |
+--------------------------------------------------------------+
```

Why this works: the 2.8.2 API base is metadata-DRIVEN —
`InitMetaDataTask.baseMetaData()` pins the cloudfront pair, and
`BaseUrlInterceptor` fails over between them; the redirect + TLS terminator
covers both. `patch_urls_282.py`'s header documents the full decode.

## 2. Prerequisites

- Rooted armeabi-v7a device (or v7a redroid), `adb` on the PC, `su` working.
- APKs (from the `localapi-assets` release, `scripts/fetch_release_asset.py`):
  - `official-bg-2.8.2-v7a-4151.apk` — the PRISTINE client.
  - `BlockyNexus-localapi-282.apk` — the b7 harness (stageVersion g10078-b7;
    12-game bundle v3 rides the staging thread).
- On the PC: `openssl` (any modern build) and Python 3.

## 3. PC side — generate the drive material

```bash
python3 scripts/gen_drive_ca.py            # -> repo drive/ (gitignored)
adb push drive /sdcard/drive
```

Artifacts: `ca.pem` (PC-kept CA + `ca.key` OFF the device), `server.p12` +
`tls.port` (staged into the harness), `<subject_hash_old>.0` (the Android
system-store file). Leaf SANs cover the three cloudfront/sandboxol API hosts
(+ static + loopback); the suite proves the exact chain end-to-end.

## 4. Device side — network + store + staging

```bash
adb push scripts/ondrive_setup.sh /sdcard/drive/
adb shell su -c "sh /sdcard/drive/ondrive_setup.sh"
```

`ondrive_setup.sh` does, idempotently:
1. `/etc/hosts`: d32gv25kv9q34j.cloudfront.net, d401m01aifavw.cloudfront.net,
   mods.sandboxol.com -> 127.0.0.1 (static hosts intentionally untouched).
2. System CA: `<hash>.0` -> `/system/etc/security/cacerts/` (mode 644;
   Magisk-friendly: copies through the bind if /system is read-only).
3. iptables NAT: `OUTPUT tcp dport 80 -> REDIRECT 18080` (mods/engineRes are
   plain http on :80; the holder binds 18080).
4. Stage `server.p12` + `tls.port` into
   `/data/data/com.disabngo.blockynexus/files/drive/` (the harness reads the
   keystore on next boot — `DriveTls.maybeStart`).
5. Verify: http `127.0.0.1:18080/health`, TLS `127.0.0.1:443` SNI
   d32gv25kv9q34j.cloudfront.net (`openssl s_client` against the new CA),
   and the :80 REDIRECT hop. Any failure prints the exact broken hop.

Reboot (or restart netd) if the hosts file is shadowed by a caching daemon.

## 5. Install + boot

```bash
adb install -r BlockyNexus-localapi-282.apk    # harness first
adb shell monkey -p com.disabngo.blockynexus 1 # boot holder + GameServer
sh scripts/ondrive_collect.sh                  # baseline evidence
# verify: tls.active exists, logcat -s LocalAPI shows
#   "drive-tls: serving https://127.0.0.1:443" and the b7 bundle stage line
adb install -r official-bg-2.8.2-v7a-4151.apk  # the pristine client
```

## 6. THE DRIVE (in order — one step per app run, evidence after each)

| # | action | pass gate |
|---|--------|-----------|
| 1 | pristine app: login/register lands on OUR holder (the app creates a fresh account; uid appears in holder state) | `/health` + logcat shows the register/login routes hit 18080; no cloudfront DNS errors |
| 2 | BedWar **g1008** (the proven room): enter the 15-bot room | engine boots; `logcat -s GS` shows the room wave; client renders in-game |
| 3 | **g1046 BedWarHall** join (first LIVE exercise of the 2021 family wiring + the lazy CommonActivityConfig require) | hall map m1046_2 loads; monitor log shows `hall.BedWarServer`; no `base.common.config.CommonActivityConfig` require failure |
| 4 | solo **g1061** join via the hall (first selectGame switch through the family) | `game.BedWarServer` on m1061_1; map loads |
| 5 | duo **g1062** join | same, m1062_1 |
| 6 | WalkingDead / BirdSimulator / Tycoon / EggWar joins | each: first-boot + join + monitor-log review |
| 7 | **g1043/g1044/g1045 PixelGun** rooms (the shared-scriptdir family, waves 5/5/1) | each room loads its own mapdir under the ONE PixelGunGame scriptdir |
| 8 | **g1054 SkyWarLuckyBlock** join (FIRST of the new-style base.* wiring class — 94 base.* requires resolve under scripts/SkyWarLuckyBlock/base/); wave 2 fires (startPlayers 3) | `base.Base` loads from scriptdir/base/; monitor log shows Match.lua start after the human joins |
| 9 | **g1058 SkyWarLuckyBlockHall** + **g1056/g1057 TowerDefense** pair (wave 0 rooms — observe the teammateNum gate from the logs before ever adding bots) | halls idle clean; g1056 starts a process as soon as the human enters (teammateNum 1) |
| 10 | **g1001 HungryGame** join (FIRST time-gated start: the official config's WaitingPlayerTask runs a 150 s countdown from the human's login — wait it out or bump waitingPlayerTime in the map's config.yml); wave 0 by design (2019 scripts not AI-aware) | map m1001_1 loads (dome arena, spawn circle y=22); countdown messages; startMatch after the gate; chest loot fills from the official config pools |
| 10 | **g1014 JailBreak** join (FIRST open-world room: no gate at all — roles police/criminal, shops, vehicles, chests, strongboxes from the 13 official ymls); wave 0 by design | map m1401 loads (initPos 148/116/319); GameTimeTask ticks; role-select UI driven by police.yml/criminal.yml data rows; no `getConfigFromYml not file` errors |
| 11 | (if blocks misrender) per-game `id_mappings.ini` from the g1046-10078 appres pattern (docs §14) | render correct |

After EVERY step: `sh scripts/ondrive_collect.sh <step-N>` — it snapshots
logcat (`LocalAPI`, `GS`, `BLOCK`, engine tags), the holder state dir, the
gs-line/stage markers, the drive dir, and net rules into
`/sdcard/drive/evidence-step-N.tar.gz` (pull with `adb pull`).

## 7. Troubleshooting

| symptom | first check |
|---------|-------------|
| app fails metadata fetch | hosts applied? `ping -c1 d32gv25kv9q34j.cloudfront.net` must answer from 127.0.0.1; TLS: `openssl s_client -connect 127.0.0.1:443 -servername d32gv25kv9q34j.cloudfront.net -CAfile /sdcard/drive/<hash>.0` |
| TLS handshake ok, app still distrusts | CA in SYSTEM store (not user store!) — user store is ignored by default since Nougat; check `ls /system/etc/security/cacerts/<hash>.0` |
| mods.sandboxol.com hangs | iptables REDIRECT present? `iptables -t nat -L OUTPUT -n -v` |
| drive-tls never boots | harness filesDir/drive/server.p12 staged? owner = the app uid; `logcat -s LocalAPI` for `drive-tls` lines |
| TSS kills the pristine app | it must NOT — nothing is patched; if it ever does, stop and capture the full logcat immediately (that is a fresh finding, run 38252063346 proved the baseline survives) |
| hall join: CommonActivityConfig require error | the bundle is pre-b3 — check stageVersion, restage |
