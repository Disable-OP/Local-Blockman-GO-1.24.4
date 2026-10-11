# Engine 10078 GameServer update — the 2.8.2 client compat layer

Status: **bundle built, analysis complete** (2026-10-11, session 66).
Goal: make the local GameServer (the 10068 `libgameserver-arm64.so` binary we already
ship) host **Blockman GO 2.8.2 clients whose engine is 10078**, and open the door to
the other games whose maps/plugins/APPRES ride the still-alive CDN.

## 1. Sources used for this phase

| Artifact | Where | What it gave us |
|---|---|---|
| BG 2.8.2 APK (armeabi-v7a, versionCode 4151) | `https://staticgs.sandboxol.com/sandbox/apk/Mtp-app-blockymods-v2.8.2-armeabi-v7a-4151-engine1-10078-engine2-20051-engine3-30023-google.apk` (155.7 MB, md5 `59d9946d341ec1550337aaaba9465cd6`) — the OFFICIAL current download, `sandbox/apk/version.json` still points at it | the 10078 client: `lib/armeabi-v7a/libBlockMan.so` (24 MB, engine1=10078), `libBlockManv2.so` (engine2=20051), `libBlockManv3.so` (engine3=30023), 7 dexes |
| `appres-g1046-10078.1625140813136.zip` (29 MB, CDN **still alive**) | `sandbox/games/app-game-engine-resources/…` | ALL 10078 engine + g1008 scripts — but as **precompiled Lua 5.1 bytecode** (815/815 files, `\x1bLua\x51`), plus 20 fresh `.mca` terrain regions + 10078 `id_mappings.ini` |
| `appres-g1046-10068.1608361944857.zip` (51 MB, CDN) | same | the 10068 appres for comparison (243 source `.lua` files — 10068 shipped SOURCE, 10078 ships BYTECODE) |
| 10068 engine/server C++ source | `project_archive_part1/2.tar.xz` in-repo (`dev/server`, `dev/logic`, `dev/client`, `engine-core`) | the ground truth for the 10068 Lua-C API (`_CLASSREGISTER_*` tables) and the version gate |
| 10068 runtime + bedwar overlay v5 | GitHub release `localapi-assets` | the data files (csvs/Media/bt/recipe) + the tuned AI csvs reused in the new bundle |
| CDN URL dump | `zips_all_sorted_unique.txt` (50,624 zips, "before June 2021") | maps/ (3,282), plugins/ (9,809), appres/ (21,889) — ALL still downloadable (Tencent COS, HTTP 200) |

## 2. What actually changed 10068 → 10078 (server-side)

### 2.1 Distribution format (the headline)
- 10068 appres shipped **plain `.lua` source** (CRLF).
- 10078 appres ships **standard Lua 5.1 bytecode** for ALL 815 files (built on a Jenkins
  pipeline, path strings confirm the same `dev/client/Shells/Android/Blockmango` layout).
- Decompilation: `unluac` (built from `viruscamp/unluac`, JDK21 Temurin downloaded into
  the sandbox) recovers full source. **All 815 files decompile and parse clean**
  (one file, `PlayerListener.lua`, was silently truncated by a parallel-run OOM —
  re-decompiled serially; always check `unluac` output parses when batch-decompiling).

### 2.2 The version gate (how a 10078 client is accepted)
`dev/server/src/Network/C2SPacketHandles/C2SInitPacketHandles.cpp:41`:
```cpp
int curVersion = EngineVersionSetting::getEngineVersion();   // reads engineVersion.json
bool bIsSameVersion = packet->m_engineVersion == curVersion; // client sends its own
if (!bIsSameVersion) { /* S2CPacketCheckCSVersionResult(success=false) + drop */ }
```
`EngineVersionSetting::loadSetting()` reads `bundle/server/engineVersion.json`.
**No binary patch is needed** — the g10078 bundle ships `"engineVersion": 10078` and
the 10068 binary then accepts 10078 login packets (and rejects 10068 ones — the two
bundles coexist per client build, see §5).

### 2.3 Script layout change (how the bundle is assembled)
- 10068 bundle: `scripts/BedWar/{base/ = the engine server scripts, ScriptMain.lua, common/, game/, hall/}`.
  The 10068 `ScriptManager.h` loads `<scriptDir>/base/BaseMain.lua` then `<scriptDir>/ScriptMain.lua`
  (`addScriptDir` = plain `package.path` append).
- 10078 split: engine scripts moved OUT of the game (`Scripts/Engine/lua/{engine_base,engine_client,engine_server,plugins}`)
  and game scripts became per-game (`Scripts/Game/g1008/lua/{server,base,client}`), with
  absolute requires `engine_server.*` / `engine_base.*` and `CEvents.GameInitEvent`
  (new events namespace in `engine_base/event/Events.lua`).
- The g10078 bundle therefore mounts BOTH layouts under `scripts/BedWar/`:
  - `base/BaseMain.lua` = the 10078 engine entry (C++ still loads that exact path) with the
    **compat shim prepended** (§2.4) and `base/` ALSO holding the 10078 game-base tree
    (`EventDefine.lua`, `common/…` — one game require is `base.common.config.CommonActivityConfig`).
  - `engine_server/`, `engine_base/`, `plugins/` = the 10078 engine trees (absolute requires resolve
    through `addScriptDir`'s `<dir>/?.lua`).
  - `ScriptMain.lua`, `common/`, `game/`, `hall/` = the 10078 g1008 server scripts (unchanged paths).
  - No `engine_client/` needed (client-only scripts never load on the server).

### 2.4 The Lua-C API delta (the complete list, from a full sweep)
Method: extracted every `_BEGIN_REGISTER_CLASS` + `AddMember/StaticMember/Override`
name from `dev/server`, `dev/logic/Src`, `dev/client/Src` (2,707 unique names), then
grepped every engine-class call in the decompiled 10078 server tree. Result — the 10068
binary is nearly API-complete for the 10078 scripts. Missing (all handled by the shim
prepended to `base/BaseMain.lua`):

| Missing API | 10078 caller | Shim |
|---|---|---|
| `HostApi.onSetClipboard` | clipboard helper | no-op |
| `HostApi.reportError` / `reportErrorFile` / `reportErrorResource` | error reporting | no-op |
| `World.getEntitiesWithinAABBExcludingEntityReturnJson` | `DoubleDummy.lua` (summon) | wrapper: calls the 10068 `getEntitiesWithinAABBExcludingEntity`, JSON-encodes the entity ids (engine_base `json` util); degrades to `"[]"` |
| `DynamicCastEntity.dynamicCastFireBall` | `util/DynamicCast.lua` map | alias of 10068 `dynamicCastFireball` (case rename) |
| `DynamicCastEntity.dynamicCastFishhook` | same | alias of `dynamicCastFishHook` |
| `DynamicCastEntity.dynamicCastItemSkill` | same | alias of `dynamicCastSkillThrowable` |
| `DynamicCastEntity.dynamicCastSnowball` | same | identity stub (10068 has no snowball cast; the map falls back to the raw entity anyway) |
| `GunSetting.getGunSetting` | `GMBedWar.lua` (GM path only) | stub → nil |

Non-issues worth recording:
- `Server.Instance():getConfig()` — the 10078 Lua *reads* config from C++ instead of the
  10068 `GameServer:setServerConfig` write-in; the 10068 binary ALREADY registers
  `getConfig`, `getEnableRoom`, `getLuaRoomManager`, `setInitPos` ✓.
- `WorldInfo.*` (AIKiller/AITeam/checkAITeamNum/…) — a **pure Lua class** in 10078
  (`game/bt/WorldInfo.lua`), not the C++ `WorldInfo`; no shim needed.
- `World.setBlock`/`removeEntity(id)`/`EngineWorld:*` — all present in 10068 with the
  same signatures (the 10068 `EngineWorld:removeEntity(entityId)` wrapper is identical).
- The 10078 `WebService.lua` **already** uses `self.ServerHttpHost .. PayOrderApi` — the
  127.0.0.1:8080 hardcode the overlay v5 patched is fixed upstream; no pay patch needed.

### 2.5 Data / terrain deltas
- **Custom block ids were reorganized**: 10068 `id_mappings.ini` has `1445=red_cloth_0`;
  10078 has `1445=cyan_cloth`, `_0` series starts at 1452, plus new plugin blocks
  (1803/1806/1811/1813/1830-1899 = bare numeric `block_plugin:<id>` names with
  `plugins/block_plugin/blocks/<id>/texture.*`).
- The 10078 appres carries **20 fresh `.mca` region files** (`setting/map/r.*.mca`,
  covering r.0.0 … r.10.0 — the islands at x~5087 live in r.9.x ✓). This supersedes
  the 4 stale 10068 sidecars that caused the session-65 "out of map" void-death
  investigation. The g10078 bundle ships all 20 **flat in the mapdir** (the server's
  `AnvilManager` reads `r.%d.%d.mca` flat — session 65 finding).
- Match config (`config.yml`) + the tuned AI csvs (overlay v4 friendly-AI values) are
  carried over unchanged; `checksums.md5` regenerated for the map dir.

### 2.6 Inner API surface (what the 10078 server Lua calls in the holder)
36 endpoints extracted from the decompiled `web/WebService.lua` (+ `PayHelper`).
The localapi-server `gameServerInner()` currently answers ~7 of them (session 65 set:
purchase, user/details, simple-info, props list/consume, settlement, settlement/golds, mails).
The remainder are NEW in 10078 and need real-or-default handlers in `Handlers.java`:

```
/api/v2/game/data                                          /gameaide/api/v1/inner/game/rank
/config/files/{fileName}                                   /gameaide/api/v1/inner/rank/integral/upload/{gameId}
/game/api/v1/inner/games/{gameId}/rank                     /gameaide/api/v1/inner/msg/send
/game/api/v1/inner/games/{gameId}/uses/rank                /gameaide/api/v1/inner/insert/thumbs-up-record
/game/api/v1/inner/region/disp-cluster/{regionCode}        /gameaide/api/v1/inner/get/thumbs-up-record
/game/api/v1/inner/region/connector-cluster/{regionCode}/{gameId}   /gameaide/api/v1/inner/delete/thumbs-up-record
/v1/dispatch-party                                         /gameaide/api/v1/inner/user/segment/info
/game/api/v1/users/inner/games/settlement/list             /gameaide/api/v1/inner/user/segment/integral
/game/api/v2/inner/users/games/reporting/list              /gameaide/api/v1/inner/segment/integral/reward
/activity/api/v1/inner/activity/games/records              /gameaide/api/v1/inner/game/mails/{id}/status
/activity/api/v1/inner/activity/games/settlement/rule      /pay/api/v1/inner/user/game/recharge/sum/gDiamond
/activity/api/v1/inner/activity/games/user/exp             /pay/api/v1/pay/inner/has/user/recharge
/activity/api/v1/inner/collect/exchange/game/notify        /pay/api/v1/pay/inner/user/consume
/activity/api/v1/inner/collect/exchange/game/props         /user/api/v1/inner/user/game/career/time
```
(plus the already-implemented 7). A 10078-mode `gameServerInner()` should answer these
with schema-true empty/rank-shaped objects — the client degrades gracefully on most.

## 3. The g10078 runtime bundle (built and verified)

`gameserver-runtime-g10078.tar.gz` (41.4 MB, 3,381 files) — layout:
```
bundle/
  client/                       ← copied verbatim from the 10068 runtime (engine-bound resources)
  server/
    engineVersion.json          ← {"engineVersion": 10078, "useCmd": "true", "logLevel": "debug"}
    <10068 data files>          ← ScriptSetting.csv, csvs, Media, GameTip, bt, recipe, g1001_g1030
    scripts/BedWar/
      base/BaseMain.lua         ← 10078 engine entry + COMPAT SHIM prepended
      base/<game base tree>     ← 10078 g1008 lua/base (EventDefine, common/, game/, hall/)
      engine_server/            ← 10078 engine server scripts (252 files)
      engine_base/              ← 10078 engine base scripts
      plugins/                  ← 10078 engine plugins (red_dot, trigger_gift)
      ScriptMain.lua            ← 10078 g1008 ScriptMain (requires common.connector.MessageInterceptor)
      common/ game/ hall/       ← 10078 g1008 server scripts (206 files)
    maps/g1008/m1008_2/
      config.yml + tuned AI csvs ← carried from the overlay-v5 map dir (proven values)
      id_mappings.ini           ← 10078 mapping (REQUIRED — block ids reorganized, §2.5)
      r.*.mca ×20               ← fresh 10078 terrain, flat in the mapdir
      checksums.md5             ← regenerated
```
All 403 Lua files in the bundle pass a Lua 5.1 parse (luaparse gate).

## 4. Client-side facts (2.8.2 APK, for the next phase)

- The APK is **armeabi-v7a ONLY** (no arm64 build exists on the CDN; the official
  `version.json` still serves this exact file). The custom 1.24.4 build is arm64 — the
  2.8.2 client line will be a v7a build; the redroid CI runner (ubuntu-24.04-arm,
  arm64-only, no 32-bit compat) CANNOT run it — device/redroid-with-32bit testing only,
  or a CI image change.
- `libBlockMan.so` (engine1 10078) is the client engine; `libBlockManv2/v3.so` are the
  engine2/engine3 runtimes (20051/30023 — different game families, e.g. new-style games).
- Decompile pipeline: apktool 2.9.3 + per-dex jadx 1.5.6 (`-Xmx2400m`, the 4 GB sandbox
  rule) — the 2.8.2 dexes are 7 (9.7/9.6/5.9/3.2/2.5/4.7/6.4 MB).
- The 2.8.2 app-side URL rewiring + embedded localapi (classes.dex count grows to 8)
  follows the same `patch_urls.py` + `build_server_dex.sh` flow; the API surface delta
  (2.8.2 Retrofit interfaces vs the 213 of 1.24.4) is the next analysis step (jadx_out).
- Dispatch/`initGame` on 2.8.2: the Java flow changed (join by game card, region
  connector concepts in the Lua) — `JoinBridge`/`GameServerManager` need the 2.8.2
  equivalents; the dispatch response shape must be re-derived from the 2.8.2 smali.

## 5. Integration plan (how this ships)

1. **Asset**: upload `gameserver-runtime-g10078.tar.gz` to the `localapi-assets` release.
2. **Bundle selection**: `GameServerManager` gains a client-engine constant
   (`10068` for the 1.24.4 line, `10078` for the 2.8.2 line) and stages the matching
   runtime tarball (`gameserver-runtime-g1008.tar.gz` vs `gameserver-runtime-g10078.tar.gz`).
   The two bundles are mutually exclusive per install (one staged serverDir) — the
   version gate is equality, so each client gets its own.
3. **2.8.2 client build** (next phase): apktool decode → `patch_urls.py` for 2.8.2's
   bootstrap URLs → embed localapi classes.dex → JoinBridge/GameServerManager port →
   sign + release. The inner-API handlers from §2.6 land in the same build.
4. **More games**: the CDN `maps/` (3,282) + `plugins/` (9,809) + `appres/` zips cover
   g1001-g1058+ halls; each game = a `scripts/<Name>/` (from the game's appres/plugins
   zips) + a `maps/g<gid>/` dir + a ScriptSetting.csv row — the same bundle layout this
   phase assembled for Bedwars.

## 6. Verification status

- [x] 815/815 bytecode files decompile + parse (Lua 5.1)
- [x] 403/403 bundle scripts parse
- [x] API sweep: every engine-class call in the 10078 server tree resolves against the
      10068 registration table, with the 8 shim entries above
- [x] bundle tarball assembled + checksums regenerated
- [ ] on-device/redroid match run with a 10078 client (blocked on the 2.8.2 client build,
      §5.3 — the 1.24.4 client cannot fake 10078)
- [ ] RakNet packet-struct compatibility 10068-binary ↔ 10078-client (empirically
      verified by the first match run; the Lua layer is version-agnostic, the C2S/C2S
      structs are the residual risk — `C2SPacketLogin` fields are the first thing to
      watch in the server log)
