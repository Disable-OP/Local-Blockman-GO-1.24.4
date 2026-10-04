# PATCH_PLAN.md — Turning the APK into its own server (single-APK, zero external deps)

Goal: one APK that runs the game AND serves its entire REST API from a loopback HTTP server inside the same process. No PC, no tunnel, no internet.

## 1. Server implementation decision

**Choice: embedded NanoHTTPD (MIT, ~100 KB jar) + a custom Java router compiled to an extra dex.**

Rationale (speed + compatibility, per project goals):

| Option | Speed | HTTP correctness | Integration cost |
|---|---|---|---|
| NanoHTTPD embedded | high (thread-pooled, HTTP/1.1 keep-alive, localhost RTT ≈ 0) | battle-tested (chunked, keep-alive, mime, ranges) | low: `d8` jar → `classes6.dex` |
| Hand-rolled smali `ServerSocket` | medium | risky (hand-written HTTP parsing = subtle client bugs) | very high (smali-only dev) |
| Loopback proxy to nothing (URL-kill only) | n/a | n/a | trivial but fails "nothing stubbed" |

NanoHTTPD on 127.0.0.1 with a fixed thread pool outperforms any remote host by orders of magnitude; correctness edge cases are already solved.

## 2. URL rewiring (single point of truth)

Patch 5 const-strings (2 files), replace any `https://host` with `http://127.0.0.1:18080` (keep path suffixes):

- `App.smali` — bootstrap `setBaseUrl(...)`, `setBackupBaseUrl(...)`, pay-signature URL
- `BaseApplication.smali` — `getMetaDataBaseUrl()` + `getMetaDataBackupBaseUrl()` hardcoded fallbacks

`BaseUrlInterceptor.switchServer()` then becomes a no-op (server == newServer). Failover can never leave the device.

Automated by `scripts/patch_urls.py` (idempotent, matches `const-string` lines with `https://` scheme in the two files only).

## 3. Server embedding

1. `javac` the router (Java 8 source/target) + NanoHTTPD jar → `d8 --release --min-api 21` → `classes6.dex`
2. Drop `classes6.dex` into `apktool_out/` root (native multidex loads it automatically on API 21+)
3. Bootstrap hook in `App.smali` (or `BaseApplication.onCreate`): `invoke-static {} → Lcom/localapi/LocalServer;->startIfNeeded(Landroid/content/Context;)V` — starts NanoHTTPD on `127.0.0.1:18080` in a daemon thread pool before any activity can fire a request
4. Data store: JSON files under the app's private dir (`/data/data/com.disabngo.blockynexus/files/localapi/*.json`) seeded on first run from assets — user progress, currencies, game catalog survive restarts (no hardcoding: state is editable and persistent)

## 4. Response contract

Retrofit + Gson expect JSON bodies; errors follow the app's `BaseResponse` shape (code/message/data — confirm exact field names from `IUserApi` call-site models during phase 1 implementation). Every endpoint in ENDPOINTS.md must return a schema-true object. The router keys on `METHOD path` with `{placeholders}` parsed from Retrofit `@Path` segments.

## 5. Phases

- **Phase 0 — pipeline (this session):** URL rewiring + empty-boot server + rebuild/sign + Redroid CI proving the app boots against loopback
- **Phase 1 — auth & shell (DONE, session 4):** `/user/api/v1/login`, `/app/login`, `/register`, `/app/auth-token`, profile, wallet → app reaches main menu with a real local account
- **Phase 2 — economy & catalog:** IGameApi (41), IScrapApi, IShopApi, IDecorationApi, IPayApi — catalog browsing, purchases, decorations fully local
- **Phase 3 — social:** friends/party endpoints + RongCloud replacement (self-hosted IM emulation on loopback or RongCloud-offline shim)
- **Phase 4 — game runtime:** join flow hands out game-server addresses via API responses → return loopback addresses; bridge the in-game socket protocol (reverse-engineer `com.sandboxol.*` game socket layer)
- **Phase 5 — polish:** analytics/ads hosts answered locally, event APIs (Halloween/turntable), resource CDN served from local assets

## 6. Build & sign pipeline (CI-identical)

`scripts/build_signed_apk.sh`: patch_urls → App.smali bootstrap hook (patch_bootstrap.py) → build_server_dex.sh (ecj+d8 → classes6.dex) → apktool b → zip-inject classes6.dex → uber-apk-signer (auto zipalign + debug keystore sign) → `dist/BlockyNexus-localapi-<sha>.apk`. Release workflow attaches every artifact to GitHub Releases (tags `v*` or manual dispatch).

## 7. Testing (Redroid, arm64-native)

`.github/workflows/test-redroid.yml`: `ubuntu-24.04-arm` runner → `modprobe binder_linux` → `redroid/redroid:12.0.0-latest` (arm64 variant matches arm64-v8a-only APK — no translation) → adb wait-for-boot → install APK → launch `StartActivity` → assert process alive + collect logcat artifacts on failure.

## Phase status (updated this session)

- Phase 0 pipeline: DONE (URL rewiring + CI build/release/redroid)
- Phase 1 auth & shell: DONE (session 4; 21 state-backed handlers)
- Phase 2 economy & catalog: DONE this session — 45+ state-backed handlers
  (game catalog pages/detail/warmup/categories/rank boards/prop shop/chat
  rooms/appreciation, daily sign-in + ad rewards crediting real wallets,
  friend recommendations from persistent citizens pool, VIP/mail).
  Host rig 70/70 PASS incl. 321-route sweep + restart persistence.
- Phase 3 social/dress/scrap/pay: DONE (sessions 5) — dress shop/wardrobe,
  scrap exchange, rankings, mailbox, local wallet/pay layer (strict auth).
- Phase 3.6/3.7: DONE (profile extras + complete IPayApi local wallet).
- Phase 4 tribe/clan: DONE (session 6) — all 35 /clan/api routes
  state-backed (see the Phase 4 section below).
- Phase 5 game runtime API shape: DONE (this session) — token/dispatch
  bridge fully state-backed (see the Phase 5 section below). The engine
  connection target is the loopback API endpoint until the Engine 10068
  GameServer phase; the contract itself is final and nothing is faked.
- Decoration suits: DONE (this session) — see the Phase 5 section below.
- File upload: DONE (this session) — multipart upload + local file serving.

## Phase 3 addendum (same session)

- Dress catalog + wardrobe + purchases + wearing are DONE and state-backed
  (see docs/ENDPOINTS.md Phase 3 table). Remaining defaults: suits (empty),
  VIP dress lists, clan decorations, gameblocky IShopApi, IPayApi.
- Scrap collect-exchange loop is DONE: backpack/value/cards/combine/history.
- CI fixes this session: build_signed_apk.sh exit-2 bug (uber-apk-signer
  output glob never matched -> signed APK was never renamed; ALL previous
  build-release runs failed on this and release APKs were built manually);
  workflows now pin checkout to local-api (main has diverged with archive
  uploads and carries an older UI test that hard-fails Phase B).

## Phase 3.5 (same session)

- World rankings: all 12 /ranking/api/v1/{board}/rank endpoints return real
  PageData boards derived from actual user wallets + citizens pool.
- Mailbox: list/operation return real empty states; mail/new=false.
- Tribe: no-clan states (detail -> code 0 "not in a clan", id -> "0").
- docs/COVERAGE.json: machine-readable coverage (scripts/gen_coverage.py;
  regenerate after route changes). Snapshot: 321 discovered / 122
  implemented / 199 default / 121 host-tested.
- Dormant areas kept as schema-true defaults ON PURPOSE (gated by appConfig
  flags isShowActivity/isShowCampaign/isShowAds=false): worldCup, halloween,
  slot machine, bgtube, lucky turntable, activity tasks. Revisit if the client
  is observed calling them (error-driven development).

## Phase 4 — tribe (clan) real state (session 6, DONE)

All 35 /clan/api routes are now state-backed handlers (was 33 defaults + 2
stubs). New domain module: `localapi-server/src/com/localapi/Tribe.java`.

- **Model shapes** verified from the decompiled client (TribeDetail,
  TribeClanMembersBean, TribeMember greendao entity, TribeDonationInfo/
  History/Response, TribeNoticeGet/Post, TribeTask(List), TribeMessage,
  TribeRank/RankInfo, TribeRecommendation, RequestJoinTribe, ClanResponse,
  TribeShopPageList/Detail) and call-sites (TribeHasFragment/TribeNoFragment,
  MakeFriendModel, TribeMessageItemViewModel, TribeContributionViewModel).
- **Lifecycle**: create (wallet fee: 20000 golds or 200 diamonds, name
  uniqueness, chief role 20) → update (chief) → invite/join-request flows
  (joinRequests + invitations with pending/agreed/rejected statuses;
  auto-join when freeVerify=1) → agree/reject by otherId (requests) or
  message id (invitations) → roles (elder 10 / member 0, chief-protected) →
  kick → exit (chief blocked) → dissolve (chief only, clears all members).
- **Economy**: donation currency=1 diamonds / 2 golds (verified from the
  client's clan_gold/cube_donate event names), daily per-currency caps +
  count cap (client error path 5006), wallet deduction → clan experience →
  personal tribeCurrency (1/10 of exp); donation history PageData newest
  first; tasks (clan type 1 / personal type 2) derive progress from real
  state (donations, games played, sign-in) and pay tribeCurrency+experience.
- **Shop**: 12 persisted clan decorations (frames/bubbles typeIds 1/2),
  per-caller hasPurchase, clan-level gates, purchases paid in tribeCurrency.
- **Discovery**: 8 seeded NPC tribes (generated once, persisted) power
  recommendation/search/rank; rank boards sort by experience desc with
  RankInfo{pageInfo,remainTime}; getTribeId returns the caller's clanId as a
  STRING ("0" = none) which is exactly what TribeCenter bootstraps from.
- **Messages**: GET /clan/api/v2/clan/tribe/member/message merges join
  requests (type 1, visible to chief/elder) + invitations (type 2, visible
  to the invitee); status 0/2/3 = pending/agreed/rejected.
- Multi-value query support added to the router ctx (`queryValues`) for
  Retrofit `String[]` params (friendIds, decorationId).
- Host rig: 176/176 PASS (incl. 333-route sweep + tribe persistence across
  restart). Coverage: 335 discovered / 174 implemented / 161 default /
  158 host-tested. CI Phase C now drives a full tribe lifecycle (create →
  base → bulletin → donate → rank → tasks → dissolve) through the embedded
  server on-device.
- Remaining default areas: /user/api account-security block (50),
  /msg/api group chat (21 — RongCloud shim decision), /activity events
  (29, flag-gated), /video (7), misc.

## Phase 4b — friend relationships real state (session 6, DONE)

All 15 /friend/api routes are now state-backed (13 new + friendList/
friendRequestsList upgraded from empty states). New domain module:
`localapi-server/src/com/localapi/Friend.java`.

- **Model shapes** from the decompiled client (Friend greendao entity,
  FriendRequests, FriendStatus, StatusBean, FriendRequestAdd,
  RecommendFriendEntity) and call-sites (FriendModel/FriendViewModel,
  FriendListItemViewModel — DELETE /friends/black verified as ADD TO
  BLACKLIST from the UI context action next to friendDelete).
- **Lifecycle**: add request {friendId,msg} (self/duplicate/blacklisted
  rejected; requests land in the target's incoming list) → accept
  (agreement: both sides become friends) or reject (rejection) → alias
  set/remove (caller-local) → unfriend (both sides) → blacklist
  (unfriends + marks). Citizens (the persistent NPC pool) auto-accept adds
  since nobody else can approve on a purely local server.
- **Presence is real state**: a user is online iff it holds at least one
  un-dropped access token (StateStore.isOnline); citizens are offline.
  GET /friend/api/v2/friends/status returns cur/max counts, currentTime
  (server time used by the client for "last seen"), and StatusBeans for
  online friends; /{friendId}/gaming returns the same StatusBean shape
  (gamingInfo stays null until the GameServer phase).
- **friendList / friendRequestsList** now return real persisted data
  instead of empty pages; friend search (info/{nickName}) scans real users
  + citizens, info/id/{id} and v2 /{friendId} return full Friend JSON with
  caller-relative fields (friend flag, alias).
- GET /friend/api/v1/friend/status/{friendId} → relationship code
  (2 self / 1 friend / 0 other).
- **Host-rig bug found + fixed**: server logs went to an undrained PIPE;
  after ~400 requests the 64KB pipe buffer filled and every L.i() write
  blocked, wedging all handler threads (sweep timeouts). Server output now
  sinks to a file in the state dir. (Logcat has no such backpressure
  on-device — host-rig-only issue, but it was masking real progress.)
- Host rig: 199/199 PASS. Coverage: 335 discovered / 187 implemented /
  148 default / 161 host-tested.

## Phase 4c — group chat management real state (session 6, DONE)

All 21 /msg/api routes are now state-backed. New domain module:
`localapi-server/src/com/localapi/GroupChat.java`.

- Model shapes from the client: GroupInfo (ownerId is a STRING, identity
  2=owner/1=manager/0=member, banStatus derived from banUntil), GroupParam,
  CreateGroupPrice (price==0 is the client's free tier), GroupInviteCount,
  GroupRequest (type 1 join / 2 invitation; status 0/2/3), GroupInviteParam,
  JoinGroupRequest, GroupRemoveParam, GroupAdminsParam, GroupTransferParam,
  GroupInfoParam, GroupOwnerRecall.
- Management is fully real: create (free tier; initial members added),
  modify (name/notice/pic/inviteStatus), apply → accept/reject by
  requestId, invite (direct add for citizens, invitations for real users),
  direct-add (GroupInviteParam), mail invite (ack), ban member N minutes
  (banUntil-derived banStatus), unban, mute-all toggle
  (forbiddenWordsStatus), set/remove managers (owner only), kick,
  transfer ownership, quit (owner quitting transfers to the first
  remaining member; last member quit deletes the group), invite-count
  (daily limit policy), recall (ack — message transport is RongCloud).
- Group lists are per-caller (groups you belong to); request feed merges
  join requests for groups you manage + invitations addressed to you.
- Host rig: 220/220 PASS (20 new group assertions incl. permission
  negatives). Coverage: 335 discovered / 208 implemented / 127 default /
  177 host-tested. Remaining default areas: /user/api security block (50),
  activity events (29, flag-gated), /video (7), config/misc (~30).

## Phase 4d — account security + daily tasks real state (session 6, DONE)

40 /user/api routes converted from defaults to real state-backed handlers
(248 implemented total). Highlights:

- **Password lifecycle**: set-password (guest → password account, x2
  routes), modify (old-password verified, x2), check (UserVerifyInfo
  right=true/false), password reset via secret-question authCode, account
  rename (re-keys the login account; login verified).
- **Nickname availability**: nickname/exist scans real users + citizens
  (case-insensitive); taken → code 0 (the client's exact contract).
- **Phone/email bind**: bind/unbind phone + email store real user fields
  (local policy: verification codes are validated server-side since no
  SMS/email transport exists in a purely local world — documented, no
  fabricated third-party traffic); masked email tip (security/bind/email);
  unbind emails x2; sms/email sender endpoints ack.
- **Secret questions**: GET list / POST auth (saves answers, issues a
  server-stored authCode) / setting (authCode-checked) / reset-password
  (authCode-checked, real password change) / unbind.
- **Login records**: every login/register/visitor/tourist appends a record
  (cap 10); GET login/change/record returns the latest AccountRecordResult.
- **Daily/weekly task strip**: new/daily/tasks (DailyTaskResponse with
  7-slot TaskBase list + UTC-midnight countdown), dairy/tasks/{type}
  (WeekTaskResponse taskMap), PUT users/tasks/{type} claims the day's
  reward into the real wallet and returns RechargeEntity.
- **Rewards**: sharing/reward (+200 golds, once/day, real wallet),
  prefect/info/reward (+500 golds after profile completion, claim-once,
  BuyGameResponse), id-card status (local "unverified" policy string).
- Host rig: 256/256 PASS (36 new assertions incl. full password rename/
  reset logins, authCode negatives, wallet math). Coverage: 335 discovered
  / 248 implemented / 87 default / 189 host-tested.
- Remaining default areas (deliberate): activity events (29, flag-gated
  off in appConfig), /video (7), videostars (5, real-money program), file
  upload + misc (~20).

## Session 7 — error-driven fixes + RongCloud decision (2026-10-04)

### RongCloud decision: OFFLINE SHIM (no local IM transport)

Evidence from the v0.4.3 redroid diagnostics (logcat):
- RongIMClient init succeeds; native lib loads; RongService starts in :ipc.
- ConnectionService: `initConnectToken null` -> ConnectionState UNCONNECTED,
  reconnect interval 10s, retries in background, ZERO crashes/ANRs, app
  fully usable end-to-end.

Decision: do NOT emulate RongCloud's proprietary nav/binary protocol
(disproportionate effort; message transport inside games runs via the game
server in a later phase anyway). The HTTP-side social graph (friends, groups,
tribe chat metadata) is fully implemented; message send endpoints ack; chat
UIs degrade gracefully exactly as observed. `rongToken` keeps returning the
local token. Revisit only if a future phase needs text chat in lobbies.

### Error-driven fixes from the v0.4.3 run's client traffic

Diagnostics artifact (redroid-diagnostics.tgz: logcat + localapi.txt +
crash buffer) analyzed for the whole client session:
- ZERO unmapped requests — every endpoint the real client called was
  matched by the RoutingTable (incl. the {version}-template scrap routes).
- Two client-called defaults upgraded to real handlers:
  * GET /user/api/v2/users/verify/user/security/settings ->
    UserVerifySettingsInfo from real user state (bindEmail/email/
    secretQuestionList/ids/userId).
  * GET /activity/api/v2/activity/title -> ActivityTaskTitleList with an
    empty activityTitleList (activities are appConfig-gated off) and a
    real serverTime.
- Host rig: 259/259 PASS. Coverage: 335 discovered / 250 implemented /
  85 default / 190 host-tested.

### Phase 5 (this session): dispatch bridge API shape + suits + file upload

Client-first evidence (jadx sources, classes3):
- `IBlockyGameApi`: POST /v1/dispatch + POST /v1/follow take a body Map and
  x-shahe-uid/x-shahe-token headers, return Dispatch; GET /v1/game-res
  returns GameResInfo{cdns, durl, resVersion}.
- The dispatch Retrofit is built against `miniGameToken.getDispUrl()` — i.e.
  the SERVER decides where dispatch lands. Empty dispUrl made the client
  abort with onServerError(429) before dispatch (GameApi line ~825).
- Dispatch consumers (EchoesGLSurfaceView line ~902): gAddr.split(":") -> host
  + port for the engine connect; requestIds.get(userId) as connect token;
  chatRoomId feeds the in-game chat room join. The client overwrites
  dispatch.dispUrl/signature/timestamp from the MiniGameToken afterwards.
- Dispatch request body (onGetGameDispatch): clz/name/pioneer/targetId/
  resVersion/ever/picUrl/packageName/appVer/country/lang/rid.

Implementation:
- miniGameToken now issues into root.miniTokens (token, userId, gameType,
  mapName, region, requestId, signature, timestamp; pruned to 40) and returns
  dispUrl = http://127.0.0.1:18080 — the client's follow-up dispatch hits
  THIS server.
- /v1/dispatch + /v1/follow validate the shahe token for real (unknown ->
  code=0) and return the complete Dispatch model with
  gaddr=127.0.0.1:18080 (host:port format, engine-ready) + persistent
  per-game chat room (croomid) + requestIds echo. The Engine 10068 GameServer
  remains a later phase (per project instruction); the bridge contract is
  final and every value is dynamic.
- /v1/game-res returns the loopback CDN as the base source.
- recordAdsGame (PUT /game/api/v1/game/record/ads) credits 100 golds under
  the shared 5/day ad cap and returns the credited amount.
- Suits (Suits.java): 6 suits generated once + persisted (root.suits), each
  bundling real DressShop dress ids with a ~30% set discount; per-user
  ownedSuits + one-time gift claim (giftSuitClaimed); buy via
  dressBuyV2.buySuitList with real wallet deduction; dressSuitList returns
  the owned suits.
- File upload: multipart parser in LocalHttpd (raw-byte safe; body strings
  would corrupt binaries) + storeFile/readFile in StateStore (4 MB cap,
  bytes under localapi/files/<id>, metadata in root.files); uploadFile
  handler returns the loopback URL; GET /files/<id> serves the bytes back
  with the stored mime type.
- name-sensitive-word-config is now real persisted config; nickNameExist
  rejects nicknames containing a listed word.

Host rig 282/282 PASS (Phase 5: dispatch lifecycle incl. bad-token
rejection, suit shop/gift/owned/buy wallet math, upload round-trip incl.
binary integrity, sensitive-name rejection). Coverage: 335 discovered /
261 implemented (78%) / 74 default / 202 host-tested. CI Phase C now drives
the dispatch bridge + suit gift on-device via adb-forward.

### Phase 5b (this session): geoinfo + region ranking + party auth

Client-first evidence (jadx): IGeoApi (UserMapInfo{distance, latitude,
longitude, pic, userId, x, y}; postUserGeoInfo stores TencentLocation fix),
IRankingApi region home (RankHomePageInfoResponse{topRankInfos:
TopRankInfo{quantity/topName/topPic/type/userId}, remainingTime}) + user info
(rankType "week"/"overall", types "gDiamond"/"active"/"clan"/gold),
PartyAuthInfo{partyService host:port consumed with split(":") by the gRPC
QuickIn/PartyList clients, partyQuerierService drives isPartyExist}.

- POST/GET /geoinfo/api/v1/userGeoInfo: real per-user geo state; citizens get
  lazily persisted coordinates; distance is a real haversine computation.
- Career data returns truthful zero counters (no engine sessions exist);
  gameTimeMap keys are the user's real played games.
- Region/user rankings derive from real wallets, played-history length and
  tribeCurrency across users + citizens; weekly variants divide by 7 and
  remainingTime counts to the next Monday 00:00 UTC.
- Party auth returns the PartyAuthInfo shape with loopback service addresses
  so the host:port split never crashes; the gRPC party transport stays
  offline per the RongCloud-shim decision (documented, not fabricated).

Host rig 291/291 PASS. Coverage: 335/268/67/209 (80% implemented).

### Phase 5c (this session): real mailbox + engine telemetry

Error-driven entry point: the v0.5.1 redroid diagnostics showed the client
polling GET /mailbox/api/v1/mail/new every session (static bool until now)
and calling PUT /game/api/v1/games/engine (mapped to `none`). Client-first
evidence from jadx: IMailBoxApi + InboxModel/InboxDetailViewModel define the
exact status machine (0=unread, 2=read, 3=delete), the attachment claim flow
and the MailInfo Gson shape.

- Mail.java domain: per-user mails in user state (status machine implemented
  exactly as the client drives it), global mail id sequence, attachment
  claiming into the real wallet (type 1=diamonds 2=golds — matching the
  donation currency semantics), claim-once guarantee, newest-first list.
- Welcome mail: every new account (register/visitor/tourist) gets one mail
  with a 500-gold attachment; the per-user welcomeMail flag guarantees
  one-time issuance even after deletion.
- PUT /game/api/v1/games/engine (countUploadVersion): records
  engineVersion/newEngineVersion/country into root.engineReports (last 20)
  for observability; ack unchanged.
- Mail reads AND writes are strict-auth (mailbox is personal data; the
  ghost-user lenient resolve does not apply).

Host rig 304/304 PASS (13 new mailbox assertions incl. no-re-credit across a
restart). Coverage: 335 discovered / 271 implemented (81%) / 64 default /
209 host-tested.

### Phase 5d (this session): game-prop purchase + economy currency correction

- Currency mapping CORRECTED across the whole economy. The old dress/suit/
  recharge code inferred 1=golds 2=diamonds; client evidence proves the
  opposite (1=diamonds, 2=golds) from three independent sites: the recharge
  reward dialog icon (googlepay recharge r.java), the game-detail prop buy
  pre-check against AccountCenter.diamonds (gamedetail h.java/Z.java), and
  the dress checkout bucket math (decorate E.java j()/b()). Fixed: dress buy
  (single + v2), suit buy, recharge product catalog + credit, ads reward
  RechargeEntity/AdsSignReward config (200-gold rewards now currency 2).
- PUT /shop/api/v3/shop/game/props/new (buyGameDetailShopGoods) is now real:
  strict auth, per-game prop lookup, wallet deduction, one-time ownership
  (userState.ownedProps), re-buy + unknown-prop rejection.
- PUT /shop/api/v2/pay/game/{gameId} deliberately stays default (no paid
  games exist; isPay=0 everywhere). Turntable deliberately stays default
  (ad-driven spin; ads don't exist locally — documented decision).
- IVIPApi (vipPriceList/buyVip) has no client call sites in 1.24.4 (dead
  code) — left as schema-true defaults.
- Host rig 307/307 PASS (new: prop buy wallet math, no-double-charge,
  unknown prop; suit buy now asserts the corrected currency).
- Coverage: 335 discovered / 272 implemented (81%) / 63 default / 210
  host-tested.

### Phase 5d addendum: share-reward config real

GET /config/files/blockymods-share-reward returns one ShareRewardEntity row
{id, picUrl, count} whose count (200) matches the actual once-per-day share
grant — display config and server behavior can no longer disagree. Host rig
308/308. Coverage 335/273/62/211 (81%).

### Phase 5f (this session): chat-room lifecycle + deep-drive discovery

- DELETE /game/api/v1/game/chat/room?roomId= is real (deleteChatRoom +
  GameCatalog.removeChatRoom): leaving a game chat drops the persisted
  name→roomId binding; re-entering the same room name issues a fresh
  persistent id. Idempotent for unknown ids. Host rig 321/321 (new:
  delete ok, fresh id re-issued, idempotent delete).
- Config-shape pass evaluated and CLOSED as deliberate: every remaining
  /config/files `obj` default parses `data:{}` into the same Gson outcome
  any honest empty value would produce (fields 0/null/empty). No handler
  added; model shapes documented in ENDPOINTS.md Phase 5f for future waves.
- UI automation deep-drive: the redroid run now visits Inbox / Top Up /
  Ranking (Me-tab rows, labels from the real uiautomator dump) and taps a
  Home game card, logging the endpoint paths each newly visited screen
  adds — the discovery channel for the next error-driven pass.
- Coverage: 335 discovered / 274 implemented (82%) / 61 default / 215
  host-tested.

### Phase 5g (this session): video feed crash fix

- Deep-drive probe of the Video row caught a real client crash
  (BaseVideoInfoDbHelper NPE on null List) — the /video list endpoints must
  answer a real flat PageData (data:[] inside), not a bare list. All 7
  /video routes are now real handlers serving honest empty local states.
- Host rig 324/324 (new: video PageData shape, more/list shape, tag map).
- CI infra: build_signed_apk.sh toolchain fetch hardened with retry/backoff
  (a transient GitHub API blip failed the v0.5.6 build with KeyError:assets).
- UI automation harness: adb log reads decode-tolerant (non-UTF-8 bytes in
  logcat killed the crash scan with UnicodeDecodeError before it could
  report; the app itself was fine).
- Coverage: 335/281 implemented (84%) / 54 default / 218 host-tested.

### Phase 5h (this session): boot resilience + probe extension

Evidence first: the v0.5.8 redroid diagnostics showed a second app process
booting while the first was alive; it failed 5 binds (EADDRINUSE) and gave
up forever. Loopback traffic kept working only because the first process
kept serving — had it died, every API call in the second instance would
black-hole. The old design assumed only non-main processes multi-boot; the
device evidence contradicts that.

- LocalServer now separates a Context-free boot core from a daemon watchdog:
  fast path unchanged (5 quick binds); while not up, the watchdog probes the
  port with a real HTTP request. A genuine LocalAPI instance answering ->
  stand by silently (one log line). Nothing answering -> full takeover boot.
  State is shared disk JSON in the app files dir, so a takeover serves the
  same accounts/wallets/tokens with no data loss.
- probeServing() requires an HTTP/ status line — a bare TCP connect or a
  junk socket never counts as "served" (and can't be taken over until it
  releases the port anyway).
- Host rig 329/329 (new HostBootTest main, host-only): (a) junk holder holds
  the port 9s -> watchdog takes over and the visitor flow works afterwards;
  (b) a standby process started against a REAL holder detects HTTP, stands
  by, and the holder keeps serving untouched.
- build_server_dex.sh: both HostTest.java and HostBootTest.java excluded
  from classes6.dex (the old single-name exclusion would have shipped
  HostBootTest in the APK).
- Deep-drive extension (discovery channel only, no behavior change on the
  server): Me-tab Settings row + one account row inside it, and game-detail
  rank/comment sub-tabs; all best-effort taps with BACK recovery, crash on
  any driven screen still fails CI.
- Coverage: unchanged (335/281/54/217) — no new handlers this wave.

### Phase 5i (this session): Phase B rework — profile-edit path through the real UI

Decision taken on the Session 11 open question (native guest-kick): STOP
TRIGGERING it. The old Phase B tapped the Me-tab account row (ll_account),
which opens the guest register-upgrade Tip whose teardown natively kills the
app (Session 11: killer is .so-native, Java exonerated, 10/10 recoveries at
~40s cost per run) — and the UI register never completed once. Account
creation was already deterministic in Phase C through the real server, so
the ll_account flow bought nothing but a death.

New Phase B (deterministic, no guest-kick): Me tab -> profile header
(ll_top) -> ibMore -> "Personal Info" editor -> Nickname row: fill EditText
with a fresh per-run nickname, confirm, assert the local server saw the
profile-edit calls (PUT /user/api/v2/user/nickName or POST
/user/api/v1/user/details/info or POST /user/api/v1/user/nickname/exist),
then best-effort the Gender row. Safety valve: a guest-Tip detector aborts
the editor drive the instant the register-upgrade Tip shows (the killer must
not be fed); remaining alive-checks are skipped and Phase C's preflight
recovers if a death still follows.

- All four profile-edit handlers were already state-backed
  (changeNickName / nickNameExist / changeInfo x2 routes); this wave makes
  them client-asserted through the REAL UI for the first time.
- Coverage: 335 discovered / 281 implemented (84%) / 54 default (all
  documented-deliberate) / 217 host-tested / 109 client-asserted.
- Expected run delta: no more between-phase SIGKILL, no more ~40s recovery
  restart in the happy path; Phase C preflight answers immediately.
- No dex change (scripts only) — automation rides the local-api checkout
  pin; no new tag required to test it.

### Phase 5i addendum (same session): the UI register flow decoded + Phase D

Evidence from two dispatched runs (v0.5.18b/c artifacts):
- A GUEST saving a nickname in the Personal Info editor makes NO API call;
  the process natively self-kills and relaunches with a TemplateActivity on
  top (pid 2208 -> 5140; delayed variant observed: pid change after the
  drive returned). The editor is guest-gated client-side — the same killer
  family as the ll_account Tip.
- am-start of LoginActivity redirects straight to main when a session
  exists — no login UI is reachable that way.

Jadx decode of the REAL register flow (com.sandbox.login):
- RegisterActivity (in the manifest, shell-startable, NO session redirect)
  drives two steps: step 1 `login_register_step_1` (account + password +
  confirm, account regex ^(?!\d+$)[a-zA-Z0-9_]{6,16}$, protocol checkbox)
  submits POST /user/api/v2/app/set-password (H:setPassword — upgrades the
  token's user with account+password, i.e. the designed guest upgrade);
  step 2 `login_fragment_make_role` (nickname + gender) submits POST
  /user/api/v1/user/register (H:userRegister — sets nickName/sex). After
  that the session is a registered user (hasPassword=true -> the kick
  condition in LoginService.a() is false).

New Phase D in the automation: am-start RegisterActivity, drive both steps
from live dumps, assert the app itself fired /user/api/v1/user/register,
then drive the Personal Info editor under the registered session (PUT
/user/api/v2/user/nickName) and prove server state through the forward
(nickname/exist flips to taken). This revives the UI-register requirement
through the real client UI without ever touching the lethal guest paths.

### Phase 5i addendum 2 (same session): rename flow fully decoded; Phase D reworked again

Two more dispatched runs produced the decisive evidence:
- The guest nickname rename is NOT gated: the flow is ChangeNameFragment ->
  GET /user/api/v1/user/nickName/free (H:nickNameFree answers
  {currencyType:1, free:true, quantity:0}) -> ChangeNicknameDialog -> its
  confirm fires PUT /user/api/v2/user/nickName. The earlier "gate" was an
  untapped SECOND confirm; the one-off kick in v0.5.18b was the roaming
  native killer, not a gate.
- am-start of LoginActivity AND RegisterActivity is denied (non-exported;
  the post-launch dump showed the previous screen). In-app UI login is not
  reachable without the lethal ll_account/Tip path — so the registered
  session is produced differently.

New Phase D: read the session user id from the live Me tab (ID row), issue
that user's token via GET /user/api/v1/app/auth-token (real handler),
upgrade the account via POST /user/api/v2/app/set-password (the client's
own guest-upgrade endpoint; H:setPassword sets account+password+hasPassword),
verify by logging in with the new credentials through /user/api/v1/login,
force-stop + relaunch (boot restores the saved session, now registered),
assert the Me tab shows the new account name, and — only if Phase B's PUT
never fired — re-drive the editor under the registered session with the
nickname/exist taken-check as the server-state proof.

### Session 12 win: two REAL server bugs exposed by the on-device client (v0.5.18e run)

The Phase D registered-upgrade run drove the real client into paths the host
rig had only exercised with synthetic params, and caught two contract bugs:

1. PUT /user/api/v2/user/nickName was a SILENT NO-OP for the real client:
   IUserApi.changeNickName sends `newName=` + `oldName=` query params, the
   handler only read `nickName=`. Fixed (newName first, nickName kept as a
   legacy alias) + host regression: rename via newName= must persist and
   nickname/exist must flip to taken.
2. POST /user/api/v1/login could not resolve a guest upgraded through
   /user/api/v2/app/set-password: the upgrade sets `account` on the record
   but the record's storage KEY stays the guest key, so findByKey missed it
   ("account not found, please register"). Fixed with StateStore.findByAccount
   (case-insensitive account-field scan) + host regression: upgrade a guest,
   login with the new credentials, same userId.

Both verified by the host rig: 337/337 PASS. The Phase D registered-editor
drive also proved on-device that with a registered session the rename flow
reaches PUT /user/api/v2/user/nickName (the guest gate blocks exactly that
final step).
