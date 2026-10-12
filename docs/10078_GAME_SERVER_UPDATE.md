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

## 7. Addendum (same session): map-dir rebuilt from the CDN + multi-game inventory

- The bundle's `maps/g1008/m1008_2` was REBUILT from the LATEST CDN map zip
  (`m1008_2.1625226508247.zip`, 2021-07-02 — full 21-csv set + dynamic schematics +
  common/lang/GameTip/setting + map.yml) with re-applied: tuned `config.yml`
  (short waits), tuned `AIConfig.csv`/`AiPlayerConfig.csv` (friendly v4 values —
  csv formats are identical between the tuned May-2020 set and July-2021 set),
  10078 `id_mappings.ini`, the 20 10078 mca, regenerated checksums (251 files).
  Bundle repacked (42.5 MB) and re-uploaded to localapi-assets.
- The `plugins/g1046.<ts>.zip` family (60 zips, June 2021) contains the FULL script
  tree as SOURCE (`lua/{engine_base,engine_client,engine_server,plugins,base,client,server}`)
  — a pre-restructure snapshot; useful as readable reference for the 10078-era logic
  without decompiling.
- Multi-game inventory (engine1 = our 100xx family): appres exists for
  g1046 (10065–10078), g1048 (10056–10063), g1055 (10060), g1042 (10073).
  plugins zips: g1008 ×93, g1061/g1062 ×60, g1046 ×60, g1001 ×16, g1047/g1048/g1050/… ×9-10.
  maps zips: 432 unique map names (g1046 ×230, g1008 ×197, g1061/g1062, m1046_2 ×80,
  m1008_2 ×76, named maps: BlockCity/TowerDefense/SkyRoyale/Bird/DUST/…).
  Engine2 games (g2020–g2044 on 200xx engines) need libBlockManv2-family server
  binaries we do not have — out of scope for the 10068 libgameserver.
- Realistic next games for THIS server: g1048, g1055, g1042 — each needs
  (1) its appres `Scripts/Game/<gid>/` (bytecode → unluac) or its plugins zip
  (source), (2) its latest map zip(s) from `sandbox/games/maps/`, (3) a
  ScriptSetting.csv row + hall/map wiring in the bundle — exactly the g10078 recipe.

## 8. Addendum 2: the launch-path contract + the overlay clobber risk (Java)

- The on-device launch passes `scriptdir = <serverDir>/scripts/BedWar` EXPLICITLY in the
  argv[1] config JSON (`GameServerManager.writeServerConfig`, "scriptdir" key) — the
  `Media/Scripts/ServerGame/...` tree in the bundle is legacy/unused on device. The
  engine contract (documented in the Java comments) is exactly:
  `<scriptdir>/base/BaseMain.lua` + `<scriptdir>/ScriptMain.lua` (+ optional
  `<scriptdir>/Loader.lua`), with `addScriptDir(<scriptdir>)` = `package.path` append.
  The g10078 bundle layout satisfies it unchanged.
- **RISK for the 2.8.2 build**: `GameServerManager.ensureScriptOverlay()` (~line 226)
  unconditionally untars `servergame-bedwar-full.tar.gz` (the 10068-scripts overlay v5)
  over `serverDir()` — it would CLOBBER the g10078 bundle's 10078 scripts
  (same paths `scripts/BedWar/{base,common,game,hall,ScriptMain.lua}`).
  FIX for the 2.8.2 line: the overlay must be engine-version aware — either skip it
  (the g10078 bundle already carries the tuned csvs + 10078 id_mappings + mca inline)
  or ship a `servergame-bedwar-full-10078.tar.gz` map-only overlay. The marker file is
  `<staging>/overlay-version` (per-install), so a differing OVERLAY_VERSION constant in
  the 2.8.2 build is also required to avoid marker collisions on shared storage.
- STAGE_VERSION ("g1008-b2") must also be bumped per line so a device that stages both
  builds (not expected — one APK per device) restages cleanly.

## 9. Addendum 3 (cron session): the 2.8.2 API surface — ROUTED + TESTED

- The 2.8.2 Retrofit surface was extracted from the per-dex jadx output
  (23,479 files, 42 interfaces): **409 unique method+path endpoints**. Diff vs the
  1.24.4 RoutingTable: **322 already routed** (79%), 65 new game-relevant (plus 22
  third-party SDK routes — Twitter/Facebook — intentionally NOT routed).
- **Shipped: the localapi 2.8.2 supplement** — RoutingTable +63 routes (397 total),
  new domain file `Mods282.java`, dispatcher wiring in `Handlers.java`:
  - REAL state: `/user/api/v1/simple/info` (PayUserInfo shape: avatarFrame,
    colorfulNickName, language, name, picUrl, userId, vip), `/user/api/v2/user/details/info`
    (User + v2 extras), `user/api/{version}/user/avatar/frame` GET/PUT,
    `user/api/{version}/user/colorful/nickName` GET/PUT,
    `/pay/pay/api/v1/pay/gdiamond/gold/exchange` + `/rate` (GoldExchangeRate{rate:String},
    REAL wallet conversion, default rate 10000 golds/gDiamond, persisted),
    `/game/api/v2/party/auth/test` (PartyAuthInfo shape, dispUrl→holder),
    `/game/api/v1/game/info/search` + `keyword/associational/word` (REAL catalog search),
    `/game/api/v1/games/like` (persisted counter), `/msg/api/v1/game/chat/room`
    POST/DELETE (persisted rooms), `/config/files/blockymods-bannerv2` (config envelope).
  - Schema-true defaults: the 26 activity/event routes (box/wish/newYear/onePurchase/
    rechargeCount/commonAct/limitSuit/shortActivity), clan mute/members/v3 (5),
    pay advance-order/third-payment/product (5), editorproxy (5), decoration home,
    game comment/revision/mode-config/appreciation.
- **HOST SUITE: 673/673 PASS** (was 655) — new "Wave 282" pins the PayUserInfo shape,
  the frame/nickname state roundtrip mirrored through simple/info, the v2 details
  shape, the exchange rate + honest insufficient failure, the banner envelope, the
  PartyAuthInfo shape, catalog search, likes and chat-room state. Route sweep covers
  all 397 routes. classes6.dex 323,272 B.
- BUG LESSON (encoded): an EMPTY `{}` placeholder in a RoutingTable template
  compiles to an illegal regex repetition and used to ABORT the whole route scan
  for every request that reached it (all later routes silently fell back to the
  default envelope). `RoutingTable.matches()` now catches PatternSyntaxException
  per-template and Logs the bad template instead.
- Wave-282 also encodes: the visitor response carries `data.id` (not `userId`);
  the seeded wallet grants 5000 gDiamonds (the exchange test asserts the honest
  insufficient path with an over-balance amount); anonymous reads answer the ghost
  shape per the documented lenient-resolve convention.

## 10. Addendum 4 (cron session): the 2.8.2 CLIENT BUILD — SHIPPED (APK on the release)

- **The 2.8.2 local-holding client EXISTS**: `BlockyNexus-localapi-282.apk`
  (166.5 MB, v1+v2+v3 signed) on the localapi-assets release. It is the OFFICIAL
  blockymods 2.8.2 (armeabi-v7a, 7 dexes, tpshell runtime base, bundled 154 MB
  v1 appres at `assets/resources/`) with:
  - **patch_urls_282.py** — 17 API hosts -> 127.0.0.1:18080. THE API BASE IS THE
    METADATA BASE: every Retrofit interface builds via
    `RetrofitFactory.httpsCreate(getMetaDataBaseUrl(), ...)`, `setBaseUrl` is
    called exactly once (InitMetaDataTask.baseMetaData, cloudfront
    d32gv25kv9q34j — DEAD as of this session), and BaseUrlInterceptor's
    failover is `getMetaDataBackupBaseUrl()`. No separate metadata JSON
    endpoint is needed. The sweep also caught 10 API classes hardcoding
    `http://mods.sandboxol.com` directly (RankingApi/VideoApi/FriendApi/
    VIPApi/TribeApi/CampaignApi/MailBoxApi/GeoApi/GroupChatApi/BaseModuleApp).
    Left alone: static.sandboxol.com + staticgs.sandboxol.com (CDNs alive),
    team.game.sandboxol.com:9921 (unused), blockmango.net recharge (pay).
  - **patch_bootstrap_282.py** — `LocalServer.startIfNeeded` hook inserted
    after `TPShellApplication.onCreate` in BaseApplication.onCreate (the
    earliest shared hook; `.locals 0` is safe, p0 IS a Context).
  - **patch_join_282.py** — `com/sandboxol/blockymods/view/activity/join/v.smali`
    private `a(MiniGameToken)V` is THE 2.8.2 local join gate (the va$b
    equivalent; gameAddr="" boot). Renamed to `a_local` + a new private
    `a(MiniGameToken)V` bridge -> `JoinBridge.takeOverJoin(ctx, gameEntity)`
    with try/catch -> a_local fallback. Exactly ONE in-class caller (v's
    b(MiniGameToken,I,J) at invoke-direct) so the rename reroutes it through
    the bridge automatically.
  - **patch_rsa_key.py** — the 1.24.4 login RSA key IS present in 2.8.2
    (com/sandboxol/login/e/d.smali) and is swapped the same way.
  - **classes8.dex** — the SAME server dex as the 1.24.4 line (325,100 B);
    ART loads every classesN.dex natively, no manifest change.
  - **libgameserver.so in lib/armeabi-v7a/** — CRITICAL: the 2.8.2 APK is
    armeabi-v7a-only; adding an arm64-v8a jniLib dir would make arm64
    devices select arm64-v8a as primary ABI and SKIP the v7a engine libs.
    The arm64 ELF inside the v7a dir is extracted-but-never-JNI-loaded and
    exec()s fine on arm64 kernels.
- **ENGINE LINE = DATA**: `GameServerManager` now reads
  `filesDir/localapi/gs_line.json` (seeded by LocalServer from
  `assets/localapi/gs-line.json` — only the 2.8.2 APK ships it):
  `{"line":"g10078","clientEngineVersion":10078,"stageVersion":"g10078-b1",
  "applyOverlay":false}`. No seed = the proven g1008/10068 defaults, so the
  1.24.4 line is byte-identical (HOST SUITE 673/673 re-run after the change).
  The g10078 line: same room (g1008 BedWar / m1008_2 / scripts/BedWar), 42.5 MB
  `gameserver-runtime-g10078.tar.gz` (on the release), NO script overlay (the
  10078-era WebService.lua is already config-driven — no :8080 bug), engine
  gate 10078 (ensureEngineVersionFile now overwrites on mismatch).
- **JoinBridge line-awareness**: `StartMc.startGame` differs per line —
  2.8.2 is a STATIC 2-arg method (putExtra("gameInfo") -> StartMcActivity),
  1.24.4 is an INSTANCE 4-arg via newInstance(). JoinBridge resolves both.
  All other reflection targets exist unchanged in 2.8.2 (EnterRealmsResult
  setters, AccountCenter ObservableFields, greendao Game).
- **2.8.2 engine selection confirmed**: `EngineEnv.getEngine(isNewEngine,
  isUgc)` — isNewEngine=0 -> v1 = libBlockMan.so = engine 10078 =
  `app_resources/Media`. The catalog's isNewEngine=0 pins are CORRECT for
  both lines. The client bundles its v1 appres in the APK (6,891 files);
  `getGameResource` (check-update) returning `[]` is CORRECT.
- **Build tooling**: `scripts/build_signed_apk_282.sh` — per-folder smali
  assembly (smali 2.5.2 from Maven Central, ~15 s/folder, resumable;
  apktool b is a non-resumable 20+ min single step that the sandbox kills),
  then repack the ORIGINAL APK (only dexes + seeds differ), uber-apk-signer.
  2.8.2 smoke CI: `.github/workflows/test-redroid-282.yml` (install -> boot
  -> 18080 holder probe -> gs engine-line log -> crash scan).
- **Decoded facts for the record**: dead hosts d32gv25kv9q34j +
  d401m01aifavw.cloudfront.net (redirecting them was also the honest choice);
  the 2.8.2 hall flow is getMiniGameToken (`/game/api/v2/game/auth`, routed)
  -> getResInfo (`/v1/game-res`, routed) -> local gate a(token) -> bridge;
  the tpshell base loads libtprt.so but the dexes are NOT packed.

## 11. Addendum 5 (cron session): v15 — the USER_NOTIF status-scrub supervisor (SHIPPED, host-proven)

The TSS war's final mechanism. libbgscomp.so is now built from
`scripts/exithook/bgscomp.c` (C, -nostdlib, armhf cross-gcc; the hand-asm
bgscomp.S built v10-v14 is retired).

Chain: ctor pre-opens /proc/self/status + /proc/self/mem + the guardlog →
prctl(NNP) → raw-clone spawns the supervisor → seccomp(SET_MODE_FILTER,
TSYNC|NEW_LISTENER|TSYNC_ESRCH=1|8|16, bpf15). bpf15 = v14's
exit(25|30)->ERRNO(ENOSYS) block + v11's PR_GET_SECCOMP/GET_NNP fakes +
USER_NOTIF on open/openat/openat2. The supervisor replies a scrubbed memfd
("Seccomp: 0", "NoNewPrivs: 0") for /proc/<x>/status opens and
SECCOMP_USER_NOTIF_FLAG_CONTINUE for everything else — the TSS ctor's
detection read returns clean values, so the verdict (and its SIGILL
fallback) should never fire. No ADDFD: same process, same fd table.

Kernel-law learned on the way (each one a proven failure mode):
TSYNC_ESRCH is REQUIRED for TSYNC|NEW_LISTENER (5.9+); NNP is per-task and
inherited at clone (set before spawning the supervisor); NOTIF_RECV needs a
ZEROED buffer per call; the listener fd global must be volatile;
AUDIT_ARCH_ARM=0x40000028; notif struct = 80 B on 6.1+ kernels; a
USER_NOTIF filter without a listener blocks its syscalls FOREVER (the
fallback chain uses only ALLOW/ERRNO rets); CONTINUE requires val==0 and
error==0.

Proof: a per-ABI x86_64 build of the same C ran the full cycle on kernel
5.10 (install → scrub read-back "Seccomp: 0"/"NoNewPrivs: 0" → CONTINUE
passthrough → openat2 scrub → clean exit). sim_bpf_bgscomp.py validates the
filters (kernel checker semantics + scenarios) and byte-verifies the
committed .so against the source; both wired into build_signed_apk_282.sh.

Layer 2 (independent): CI bind-mounts a scrubbed status over every
:BlockmanGo /proc/<pid>/status (fsloop.sh daemon) — the ctor reads clean
values even if the in-process install fails on-device.

apk wip-89 md5 e0a72fd09b8cdcd290517732be001c5c.

## 12. Addendum 6 (cron session): THE TSS WAR IS WON — the out-of-process USER_NOTIF supervisor serves on-device

Across 10 CI runs (wip-95..wip-104) the seccomp guard evolved from a
thread to a SEPARATE PROCESS and defeated every TSS layer:
- the ctor's status check (exit(25) verdict) — the status scrub;
- the ctor's SIGILL self-abort — the scrub satisfied it (no SIGILL
  since v15);
- the watchdog (fork -> PTRACE_ATTACH all threads -> verify -> release;
  kill = hold stopped + force exit_group(25)) — the v15-v17 'freeze' was
  the deadlock of that protocol against our exit block, and the FINAL
  fix is architectural: the supervisor is NOT a thread of the engine —
  the watchdog cannot attach it (it enumerates /proc/<engine>/task);
- kill(SIGSTOP) — denied (-EPERM); process_vm_readv — denied;
  io_uring — ERRNO(ENOSYS); the umbrella protocol itself — respected
  in full (denying or faking the supervisor's attach aborts the TSS
  init: v18/v22/v23).

The engine now survives the whole 5-minute drive (echoes=True x21,
healthy process, 1431 ptrace notifications served by the child).

The remaining failure is the ENGINE-INTEGRATION stall: initGame to
127.0.0.1:31108 never fires, no client.log is ever created, the
engine's native thread farm never appears. Next: the engine-side log
harvest (logcat for the engine pid, the SandBoxOL/BlockMan tree, the
10078 engine's own log paths) — the TSS is no longer the suspect.

Full mechanics + the debugging minefield (division helpers, zeroed
RECV buffers, volatile listener, AUDIT_ARCH_ARM, notif sizes,
TSYNC_ESRCH, NNP-per-task, arm32 getpid=20, /data/local/tmp
permissions, the phantom process killer) in
scripts/exithook/bgscomp.c comments and NEXT_SESSION_README delta 8.
