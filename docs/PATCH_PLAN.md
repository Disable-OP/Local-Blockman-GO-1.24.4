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

### Session 12 FINAL (verified green): the registered profile-edit chain

v0.5.19-clientfix + the clean_relaunch hardening: test-redroid PASS with the
FULL chain on-device — guest gate evidence (B) -> auth-token + set-password
upgrade -> login with the new credentials (findByAccount fix verified) ->
restart onto the registered session -> Me tab shows the new account ->
registered rename PUT (newName= contract fix verified) -> nickname/exist
flips to taken (server-state proof). 63 unique endpoints served, zero
crashes, zero unmapped.

Deliberate behavior documented (not a bug): the guest rename confirm fires
the native kick (the client's guest gate) — the automation records it and
recovers via D's clean relaunch. am-start of the non-exported
LoginActivity/RegisterActivity is denied; the registered session is
produced through the real set-password upgrade instead.

Coverage: 335 discovered / 281 implemented (84%) / 54 default (all
documented-deliberate) / 217 host-tested / 109 client-asserted.
Host rig 337/337.

### Session 12 surface wave (final): Personal Info editor fully exercised

Run 37220314081 (v0.5.19-clientfix APK + local-api scripts): PASS with the
whole registered-session editor surface verified end-to-end:
- Nickname rename: PUT /user/api/v2/user/nickName + record read-back
  matches (nickName='qaD35034').
- Personal Profile (details): the detail editor template drive types a
  per-run intro, saves through changeInfo, and the re-login record shows
  details='localqa intro 35302' — UI -> server -> read-back all green.
- Gender row: CLIENT STUB (jadx onClickSex = toast only; no picker, no
  network) — documented deliberate behavior, nothing to implement.
- Birthday (wheel picker) and Profile Photo (gallery intent): deliberately
  not driven (low value, high flake risk); handlers are host-tested.

### Wave 5j (session 13): category-tab probe + relaunch hardening

- clean_relaunch (test-redroid automation): after the hardened pid-retry,
  a full second force-stop+launch cycle now runs when the main screen
  never appears. Evidence: run 37216002760 (pre-hardening script) showed
  a swallowed am start (START logged, no am_proc_start) and Gallery3D in
  foreground after the app's own image PICK during the kick self-relaunch.
- Deep-drive extension: rb_2 (game categories) gets a discovery node dump
  ("ab2]" lines) plus ONE best-effort row tap; engine-action words
  (play/start/quick/join/enter/go) are denylisted so automation can never
  trigger the engine connect (deferred GameServer phase). If the row
  opens a game list, one card is opened (same band heuristic as Home).
  rb_3/rb_4 get discovery-only dumps ("tab3]/tab4]" lines).
- Server surface unchanged (no dex change, no tag): this wave is pure
  automation + observability, riding the local-api checkout pin.

### Session 15 (wave 5s): Phase F — registered OWN-CLAN surfaces through the UI

Session 14 FINAL proved the guest gate (visitor create submit is silently
swallowed; the registered session POSTs /clan/api/v2/clan/tribe). The
Phase E clan persists (Phase C dissolves its own API-level clan BEFORE
Phase E), so the registered session OWNS a clan at that point in the run.

Wave 5s adds Phase F after Phase E, driving the OWNER-state clan surfaces
through the real UI:
- `ui_create_clan` now returns (posted, uname) so Phase F knows the
  created clan name.
- Phase F re-enters tab3 as a clan owner, dumps the tab3 layout
  ("F-tab3]" evidence — does the owner state change the tab?), then
  re-enters the clan screen (rlSearchClan), dumps it ("F-clanscreen]"),
  searches for the EXACT created name through the hint-text input picker
  (wave 5n pattern; one IME-aware BACK after key(66) — 5n/5p evidence:
  the first BACK only closes the keyboard), and taps the own-clan row.
- The screen that opens is dumped ("F-clanhome]") and every NEW /clan/
  endpoint is reported. Discovery-first: node dumps + endpoint evidence
  are the deliverable; the hard requirement is only that the app stays
  alive. Expected client fetches for an owner (all real handlers):
  GET /clan/api/v1/clan/tribe/base, /tribe/member, /tribe/currency,
  /tribe/bulletin.
- If the own clan is NOT surfaced, the dumps name the real entry for the
  next wave (honest recorder — no forced taps).

Server surface unchanged (no dex change, no tag): this wave is pure
automation, riding the local-api checkout pin.

## Phase 7 — client-verified error codes + evidence-quality fixes (Session 16)

### 7a. The Session 14 "guest gate" conclusion was a FALSE POSITIVE

Run 37259412423 (wave 5s v4) re-analysis, from the diagnostics artifact:

- The UI clan-create POST line ("REQ POST /clan/api/v2/clan/tribe") is
  ABSENT from the server traffic in the 03:43-03:45 window where Phase E
  submitted; both recommendation responses around it are byte-identical
  (1658b) — no clan was created server-side, registered or not.
- The E-clanui "[ok] UI clan creation hit POST ..." matched PHASE C's
  API-level create of the same route still sitting in the unbounded
  `logcat -d -s LocalAPI` buffer (Phase C ran ~5 min earlier).
- Therefore GET /clan/api/v1/clan/tribe/id returning "0" after the app
  restart was CORRECT — the own clan never existed.

THE REAL GATE (decompiled, classes2.dex com/disabngo/blockynexus/e/b/la):

- TribeCreateViewModel (n.java h()): name sensitive-word check -> no
  spaces/newlines -> if golds >= 8000 use the golds path (currency 2),
  else a TribeCreateDialog ("Inadequate coins, cost 60 to create a
  clan?", tribe_sure_pay_60_diamond) switches to the diamonds path.
- TribeCreateModel (l.java a(List,String,String,int)): validation, then
  the CREATE form REQUIRES the clan icon: `g()/h()` are ONLY set by the
  gallery+crop onActivityResult (TribeCreateFragment). Null icon ->
  toast tribe_icon_empty ("Clan Profile Photo cannot be empty") and
  RETURN — no network call. This is the silence, for ANY session state.
- When an icon exists the chain is uploadIcon (POST /user/api/v1/file)
  FIRST, then clanRequest in the upload callback; headPic = the upload
  response string (our absolute loopback /files/<id> URL — correct).
- Automation fix (ui_create_clan): posted-detection now snapshots the
  LocalAPI log BEFORE the submit tap and requires the match count to
  GROW + the typed clan name to appear (grew/typed printed honestly).

### 7b. Error codes (the authoritative table)

Evidence: OnError mappers decompiled from classes3.dex + toast strings
decoded from resources.arsc via apktool. Dispatch contract in
ARCHITECTURE.md section 9. Server mapping: ErrorCodes.java +
Handlers.failTribe/failFriend/failGroup.

ALL DOMAINS (requireUser failures):
- 7 = not_login / visitor_must_login ("Please log in" / "It only
  supports signed-in users")

USER (UserOnError):
- 101 base_account_exists (register dup) | 102 account_not_exist (login
  by unknown uid) | 7012 sign_in_has_get (daily sign-in double claim,
  was silent-success before) | 7020 has_illegal_character (rename /
  changeInfo nickName against the local sensitive-word config)

TRIBE (TribeOnError):
- 5006 tribe_not_enough_diamond ("Insufficient Bcubes") | 5007
  gold_not_enough ("Coin not enough") | 7001 tribe_joined ("Already
  joined") | 7002 tribe_name_exist | 7003 tribe_not_chief | 7004
  tribe_not_elder (elder-gated "no permission" family) | 7005
  tribe_full | 7006 tribe_not_joined ("not in a clan") | 7008
  tribe_low_level (clan shop level gate) | 7011
  tribe_exceed_max_diamond_or_gold (daily donation caps — the caps
  themselves predate this phase: 20000 golds / 2000 diamonds / 10/day,
  client-visible via donationInfo) | 7012 tribe_task_get_reward
  ("Reward has been claimed") | 7014 tribe_no_enough_24_hour ("You can
  join after 24 hours") | 7020 has_illegal_character (clan create/
  update name)

FRIEND (FriendOnError):
- 3001 is_friend_already | 3002 exceed_max_friend_number | 3003
  no_friend (alias on a stranger — setAlias errors get a "(alias)"
  suffix so only the alias path maps here) | 3004 not_valid_user

GROUP CHAT (GroupOnError):
- 8102 group_no_exist_tip | 8103 new_group_error_8103 ("No permissions
  now", incl. owner-only gates) | 8104 new_group_error_8014 ("The
  player is not in the group chat")

GAME (GameOnError):
- 2002 game_not_exist (game detail / warmup / appreciation of an unknown
  id — detail used to return code 0) | 2005 repeat_like (per-user
  appreciated[] state; the like total only grows on the first like)
  | 7 like-after-login (appreciation is requireUser now)

Deliberately NOT emitted (client-verified but no server-enforced rule):
7005-vs-elder-cap 7010, task refresh limits 7016/7017, join level 7008
emission (our clans carry no level requirement), donation-count cap is
enforced (10/day) and maps to 7011, game 2008 not-played (recordPlay
has no caller until the join/telemetry phase).

### 7c. Client-visible create pricing correction

Tribe.create fees were 20000 golds / 200 diamonds; the client visibly
promises 8000 golds (the golds-path threshold in TribeCreateViewModel)
and 60 diamonds (TribeCreateDialog text). Server now charges
CREATE_FEE_GOLDS=8000 / CREATE_FEE_DIAMONDS=60 — never more than the
client told the user.

### 7d. 24h rejoin cooldown (new real state rule)

exit/kick/dissolve now stamp `clanQuitAt` on the affected users;
requestJoin / agreeJoin / agreeInvitation reject with 7014 within 24h.
Evidence: dedicated client string tribe_no_enough_24_hour.

Host rig: 349/349 (was 337) — the 12 new Phase 7 assertions live in the
"== Phase 7: client-verified error codes ==" block; every prior code-0
error assertion was upgraded to its client-verified code.

## Phase F2 (Session 17): the clan-UPDATE form driven through the real UI

Session 16's top candidate executed: give the registered session a
PERSISTENT clan via the API, then drive the owner surfaces. This makes
Phase F's premise true for the first time (the UI create is icon-gated,
Phase 7a — it never posts, so the "own clan" never existed before).

### The client evidence chain (jadx classes2 + apktool resources)

- `TribeHasFragment` (layout `fragment_tribe_has`, binding Kf): the
  own-clan homepage. Its settings entry is the top-RIGHT toolbar
  ImageButton — NO android:id, `android:src=@mipmap/ic_more`, data-binding
  tag `binding_2` -> TribeHasViewModel command `o` -> `H()` opens a
  BottomDialog.
- `H()` items (strings resolved from resources.arsc): Clan Settings
  (2131823614, chief-only) | **Edit Profile** (2131823533 = `tribe_data_edit`)
  | Manage Members (2131823568) | Cancel (2131821064). "Edit Profile" ->
  `b(dialog)`: starts the CREATE template (`e.b.la.h` = TribeCreateFragment)
  with `tribe.is.create=false` + bundle pre-fill (ico.url / name /
  introduction / labels) — title 2131823544 = "Edit Clan".
- `TribeCreateViewModel.i()` (event "clan_more_edit_data_click") is the
  EDIT submit: `l.a(tags, name(e), details(f), icoUrl(d), clanId)` ->
  validation -> (no NEW icon picked) -> **`TribeApi.clanUpdate`** directly.
  The 8000-golds gate and the icon requirement are BOTH create-path only —
  the edit form needs neither.
- Validation on the edit path: name non-empty (tribe_name_empty), details
  non-empty (tribe_introduction_empty), **1..4 tags required** — our
  persistent clan ships tags=[], so the drive adds one through the same
  Add Tag dialog as the create flow (et_msg / btn_confirm, digit tag).
- Submit control: the "Modify" Button (`tribe_create_modify`, binding_7 =
  command `o` = `i()`) — NOT the "Create a clan" row (binding_8 = `h()`,
  the create submit; a stray tap there 7001s harmlessly).
- One-time `TribeSettingGuideDialog` (Ta): shown on the first owner
  homepage open per install (SharedUtils is_tribe_setting_guide, fresh
  every redroid run). BACK is swallowed while it is up; its top-right
  label ("...join clan") tap opens the SAME settings sheet and dismisses.

### The server contract fix the decode exposed

`PUT /clan/api/v1/clan/tribe` (clanUpdate) had NO uniqueness gate — the
client's edit form has none either, so the server owns the rule:
renaming onto another clan's name now returns **7002** (tribe_name_exist),
matching create. Non-member PUT now returns **7006** (was generic 0).
`Tribe.nameTaken(store, name, excludeClanId)` is shared by create and
update (update excludes the caller's own clan). Chief-only stays 7003
(the handler resolves the CALLER's clan; the body clanId is advisory).

### The drive (scripts/ui_automation_test.py, Phase F/F2)

1. Phase F setup: API-create `PersClan<uniq>` for the live session
   (Phase-D auth-token; golds path, diamonds fallback), assert tribe/id
   != 0, restart the client so the boot re-fetches the clan.
2. Owner drive (existing wave-5s body, now with a real clan): tab3 dump,
   ivTribe/ivClanMsg0 entries, clan screen, exact-name search, row tap,
   homepage dump + NEW /clan/ endpoint report.
3. F2: guide-overlay detection -> ic_more -> "Edit Profile" -> title check
   ("Edit Clan") -> clear+retype etTribeName (EditClan<uniq>, verified,
   retype fallback) -> Add Tag "QA2" -> bounded PUT detection (snapshot
   REQ PUT count before, require growth, member-route excluded) ->
   server read-back `GET /clan/api/v1/clan/tribe/base` name == typed name.

Host rig 361/361 (8 new assertions: chief update+persist, 7002, 7006,
rename-restore, cleanup). No dex-shape change; classes6.dex rebuilt
(214728 bytes) — ship by tag if the on-device run is green.

### Phase F2 run evidence (Session 17 — the guide saga, 5t v1..v9)

Each wave landed with the run PASS (F2 checks fire only when the form is
reached), so the loop stayed green while the evidence accumulated:

| Run | Decode |
|---|---|
| 37335622091 | persistent-clan premise TRUE: owner tab3 IS the clan dashboard (tvClanName / Chief / 1-22 / rl_donate / rlEnterClan); owner surfaces hit through the real client |
| 37338438610 | rlEnterClan opens the homepage under a 'Notice Board' dialog (the empty bulletin; btnSure CLOSE) |
| 37342075770 | CLOSE works; single post-close name-find misses (evidence dump added) |
| 37344788918 | the one-time guide overlay appears at entry; the Notice Board replaces it as the active window (misread as self-clear) |
| 37348093722 | 100s settle budget: after the NB close the guide re-appears and persists — no self-dismiss |
| 37351059115 | same at 100s+ |
| 37354556790 | label-tap escape opens the sheet BUT f() re-shows a fresh guide (a() -> messenger -> H()+Ta(true).show()); sheet never visible |
| 37358087903 | the layout's bottom 'Clan Settings' bar (b()) never appears in either variant's dump |
| 37361712499 | two-tap dance refuted: the a=true guide has no bar either |

CONCLUSION: the guide overlay has NO drivable dismissal. It is pure UX
(one analytics event + a SharedUtils one-shot flag), so the build pipeline
now stubs `Ta.show()` (scripts/patch_tribeguide.py, killlog-patcher
precedent). With the overlay gone the entry chain is: rlEnterClan ->
Notice Board CLOSE -> clean homepage -> ic_more -> sheet -> Edit Profile
-> rename + Add Tag -> Modify -> PUT /clan/api/v1/clan/tribe -> server
read-back. Shipped by tag v0.6.1-guidefix.

## Phase G (Session 18): member management + clan settings driven through the real UI

Client decode (jadx oa.TribeMemberManage / TribeHasItemViewModel J /
sa.TribeSettingFragment + string resources): the manage screen hint is
"Long press to edit member" — the member sheet is the LONG-CLICK
command. The chief's sheet for a member: [Hand over Chief | Set as
Elder | Remove Member | Cancel]; for an elder: [Hand over Chief | Set
as Member | Remove Member | Cancel]; elders only get Remove on plain
members. Sheet items feed TwoButtonDialog (base_dialog_two_button,
btnSure confirms). Clan Settings is the auto-enter CheckBox
(tribe_auto_enter) whose ViewModel hardcodes TRUE and re-binds after
every response.

SERVER CONTRACT FIXES (each verified by the real client on-device):
1. setIdentity type codes: the client sends {1=Set as Elder, 2=Set as
   Member, 3=Hand over Chief}; the server only accepted {0,10} — every
   real role-change failed with generic code 0. Now: type 1 -> role 10,
   type 2 -> role 0, type 3 -> chief handover (target 20, old chief
   steps down to member, chiefId follows).
2. kick guard: the chief's sheet offers Remove for ELDERS - the old
   guard rejected elders. Now: elders remove plain members, the chief
   removes anyone but the chief.
3. Wire notes: the client sends both PUTs with params as a FORM body
   (NanoHTTPD merges them into getParameters; the URI carries no query
   — the REQ log prints the path only). freeVerify worked all along;
   setIdentity needed the type-code fix.

THE DRIVE (Phase G, after F2): second member joined via the local API
(register + requestJoin + chief agreement) -> ic_more -> Manage
Members -> long-press the member row -> Set as Elder -> btnSure ->
bounded PUT + tribe/member read-back (role 10) -> long-press -> Remove
Member -> btnSure -> member-gone read-back -> ic_more -> Clan Settings
-> auto-enter CheckBox taps -> freeVerify state sequence [1,0,1] with
bounded PUTs -> restore to 0.

Run 37391929418 (wip-40) PASS: setIdentity client-asserted (role=10),
removeMember client-asserted (member gone), freeVerify client-asserted
([1,0,1]), plus the F2 clan-UPDATE (name read-back). Host rig 370/370.

## Wave 5v (Session 19): campaign sign-in + datareport sink + turntable status

Phase 8 — the activity/analytics layer. Client contracts decoded from
jadx classes1-4 (ICampaignApi/IVIPApi/IUserApi/IReportInfoApi/
IPingReportApi + the view/dialog/a sign-in family + b/b.java activity
gates), then implemented as real state-backed handlers:

1. campaignSignInList (GET /activity/api/v1/signIn): monthly 8-day cycle
   per user; 8 cells (the client dialog hard-requires 8), status
   0/1, isSpecial on days 7/8, day 8 carries 4 reward cards; signInStatus
   0 = claimable today; remainingTime = cycle end epoch ms.
2. campaignSignIn (POST): claims the first unclaimed day, credits the
   wallet (+200..8000 golds by day), returns {"signInId": N}; double
   claim -> 7012 (CampaignOnError family, same as the daily sign-in).
3. turntableStatus x2 (lucky/turntable + slot draw): TurntableStatus
   {isFree: 1} — the free draw is unused (no draw endpoint locally yet).
4. eventReport/funnelReport/pingReport: the three /datareport routes now
   persist every report body verbatim to
   localapi/datareport/<kind>-<yyyymmdd>.jsonl — a real analytics store
   (also improves observability: the server can now answer "what did the
   client report today").
5. appConfig: isShowUniversalActivity/universalActivityVersionCode added
   explicitly (b/b.java reads them; missing keys Gson-default silently).

Routing pipeline verified end-to-end this session: httpsCreate uses the
inline CloudFront literal as primary + the patched backup as fallback
(fail fast -> switchServer -> loopback), while the datareport APIs point
at the patched PRIMARY directly. All decoded routes land locally.

The remaining 47 default routes are now classified with call-site
evidence in docs/ENDPOINTS.md ("Wave 5v" table): dead code (IVIPApi,
worldCup family, ugc/status, email/phone reset paths), gated-off for
local accounts (videostars — empty starCode), event-gated (halloween,
bgtube), or honest empty-state configs (banner/editor/moregame). None of
them is reachable by the live client request graph of 1.24.4 as
configured; lighting each is a deliberate future decision, not a gap.

Host rig: 390/390 (18 new Wave 5v checks incl. persistence across
restart + the on-disk datareport store assertion). NO GameServer work.

## Wave 5w (Session 19 cont.): turntable draw chain + jackpot surface lit

1. turntableInfo (GET turntable): 8 prize slots (AdsTurntableInfo) — the
   client's dialog bails on an empty list, so the default [] was a dead
   surface, not a working one.
2. turntableProps (GET turntable/props): real daily-state tip string.
3. turntableDraw (PUT turntable): one free draw per UTC day; RNG prize
   (id 1..8 -> +50..2000 golds); the drawn id is what the wheel spins to.
4. turntableStatus x2 now read the real state: isFree 1 -> 0 after the
   daily draw (the red-point icon goes gray) — a genuine state machine.
5. appConfig isShowUniversalActivity=true + universalActivityVersionCode
   0: the slot_machine jackpot icon is now LIT on the hall (b/b.java
   gate + App's activityId="slot_machine"), so the client polls the draw
   status on its own — the first activity surface the 1.24.4 client
   reaches by itself on this build.

Host rig 397/397 (7 new draw-chain checks). Automation: Phase A gained
the defensive campaign-sign-dialog handler (claim-or-dismiss, non-fatal)
and the jackpot poll probe.
