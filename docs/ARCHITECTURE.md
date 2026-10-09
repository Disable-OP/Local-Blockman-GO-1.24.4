# ARCHITECTURE.md — Network layer of Blockman GO 1.24.4 (custom build)

Package: `com.disabngo.blockynexus` · Launcher: `com.disabngo.blockynexus.view.activity.start.StartActivity` · target platform 29 (Android 10) · `versionCode 4003`

## 1. Bootstrap flow (where every server URL is decided)

`smali/com/disabngo/blockynexus/App.smali` (Application entry) runs the network bootstrap:

```
BaseApplication.getApp()
  .setBaseUrl("https://d32gv25kv9q34j.cloudfront.net")     <- PRIMARY API host (patched by custom build)
  .setBackupBaseUrl("https://[tunnel-host]")                <- BACKUP API host (custom build's tunnel)
  .setVersionCode(4003)
  .setRootPath("SandboxOL")                                 <- app data root dir name
```

`smali/com/sandboxol/common/base/app/BaseApplication.smali` stores these values and exposes them:

- `getMetaDataBaseUrl()` — returns the primary base URL; **hardcoded fallback** to the tunnel host if null
- `getMetaDataBackupBaseUrl()` — returns the backup base URL; **hardcoded fallback** to the tunnel host if null
- `getMetaDataAppVersion()`, `getMetaDataRootPath()`, `getUserId()` (from SharedPreferences key `userId`)

## 2. HTTP client stack

`smali_classes3/com/sandboxol/common/retrofit/RetrofitFactory.smali`:

- `httpsCreate(String baseUrl, Class apiInterface)` builds a Retrofit instance with:
  - `RxJavaCallAdapterFactory` (reactive call layer)
  - `GsonConverterFactory` (JSON serialization)
  - OkHttpClient with:
    - `BaseUrlInterceptor(server = baseUrl, newServer = BaseApplication.getMetaDataBackupBaseUrl())`
    - retry on connection failure = true
    - connect/read/write timeouts = 10 s each
- Every API implementation class (e.g. `center/web/UserApi.smali`) obtains its Retrofit client through:
  `httpsCreate(BaseApplication.getMetaDataBaseUrl(), IUserApi.class)`

## 3. Failover interceptor

`smali_classes3/com/sandboxol/common/retrofit/BaseUrlInterceptor.smali`:

- Fields: `server` (primary), `newServer` (backup), package suffix + app version
- `switchServer(String url)` — runtime URL rewriting:
  - URL contains `server` and `server != newServer` → replace `server` with `newServer`
  - URL contains `newServer` → replace back to `server`
- Injects request headers (observed constants): `Access-Token`, `userId`, `appVersion`, `packageName`, `androidVersion`, `OS: android`
- Tracks an HTTPS failure counter in SharedPreferences key `token.https.count` used to decide failover to the backup host

**Key property for the local patch:** if `server == newServer == http://127.0.0.1:PORT`, failover becomes a no-op and *all* 213 endpoints land on the loopback server.

## 4. TLS / cleartext posture

- `AndroidManifest.xml`: `android:usesCleartextTraffic="true"`
- `res/xml/network_security_config.xml`: `<base-config cleartextTrafficPermitted="true">` with system trust anchors only
- **Consequence:** plain `http://127.0.0.1` requests are allowed for every connection in the app. No HTTPS interception, no custom CA, no network hack needed.

## 5. API surface

18 Retrofit interfaces / 213 endpoints — full listing in [ENDPOINTS.md](ENDPOINTS.md). Main groups:

| Interface | Endpoints | Domain |
|---|---|---|
| `center/web/IUserApi` | 80 | login/register/profile/friends/wallet |
| `center/web/IGameApi` | 41 | game catalog, records, turntable events |
| `center/web/IScrapApi` | 16 | currency ("scrap") ledger |
| `decorate/web/IDecorationApi` | 17 | avatar/room decoration |
| `decorate/web/IShopApi` | 14 | store items |
| `googlepay/billing/IPayApi` | 16 | payment signatures/orders |
| `gameblocky/web/IBlockyGameApi` | 5 | blocky game runtime |
| `halloween/web/IHalloweenApi` | 6 | seasonal event |
| `videosubmit/web/IVideoSubmitApi` | 6 | video uploads |
| others (16 more) | 12 | report/ping/chat/party/VIP/friends |

Auth entry points: `POST /user/api/v1/login`, `POST /user/api/v1/app/login`, `POST /user/api/v1/register`, `GET /user/api/v1/app/auth-token`.

## 6. Out-of-band systems (not Retrofit)

| System | Transport | Notes |
|---|---|---|
| Chat / IM | RongCloud SDK (`io.rong.*`) | connects to RongCloud nav (`nav.cn.ronghub.com`, `nav2-cn.ronghub.com`) — separate cloud service with its own app credentials |
| Resource CDN | `http://static.sandboxol.com` | game resource packs (`assets/resources*`) |
| Analytics | Umeng (`pslog.umeng.com` etc.), TalkingData (`cloud.xdrig.com`), Firebase/Crashlytics | telemetry; can be pointed anywhere or dropped |
| Ads | Google ads, Facebook ads, Supersonic | SDK-managed hosts |
| Payment verify | `App.smali` builds `.../web/public/pay/api/v2/public/pay/signature` from the tunnel host | part of IPayApi flow |

## 7. Patch points (summary — details in PATCH_PLAN.md)

1. `App.smali` bootstrap: `setBaseUrl` + `setBackupBaseUrl` → `http://127.0.0.1:18080`
2. `BaseApplication.smali` fallbacks (2 const-strings) → same
3. Embedded HTTP server started in `App.smali`/`BaseApplication.onCreate` before any network use
4. RongCloud: phase 2 (needs IM server emulation or graceful offline)
5. Game runtime sockets: phase 3 (join flow hands out server addresses via API responses)

## 8. Embedded server internals (Phase 1+2)

Files (localapi-server/src/com/localapi/):
- `LocalServer` — bootstrap hook (App.smali → startIfNeeded), bind-retry across app multi-process races
- `LocalHttpd` — NanoHTTPD router; raw body reader (keep-alive safe); logs REQ/RES under tag LocalAPI
- `RoutingTable` — generated 321-route table; `match()` returns kind + {path} captures
- `Handlers` — Phase 1 auth/profile/config + Phase 2 catalog/economy/social handlers
- `GameCatalog` — generates + serves the persistent game catalog, citizens, prop shops, rank boards
- `StateStore` — JSON persistence (files/localapi/state.json): users, tokens, wallets, per-user economy state, catalog

Request graph the client actually drives (verified from decompiled call sites):
boot config (checkVersion, appConfig) → auth (tourist/visitor/login) → auth-token
→ main screen: recently-played + announcements + daily sign-in + VIP + mail
→ discover: revision/list/by/condition (TypePageData, local DB cache + network refresh)
→ game detail: v2/games/{id} + warmup + prop shop + rank
→ join: dispatch/token (Phase 4)

## 9. Response contract (Phase 7 — client-verified error codes)

Every handler answers `{"code":N,"message":"...","data":...}`. The client's
dispatcher (BaseSubscriber.onNext -> OnResponseAdapter) is exact:

- `code == 1` -> `onSuccess(data)`
- `code 4 / 5 / 429 / 504` -> `onServerError(code)` (server-level toasts)
- HTTP 401 -> forced re-login message (TOKEN_REPEAT_LOGIN)
- **any other code** -> `onError(code, message)` -> the DOMAIN error mapper
  (TribeOnError / UserOnError / FriendOnError / GroupOnError / GameOnError /
  ScrapOnError / ...) translates the code into the proper client toast;
  unknown codes fall back to a generic ServerOnError toast.

The mapper tables were decompiled from the 1.24.4 APK (classes3.dex) and the
toast texts resolved from resources.arsc. The server emits these codes via
`Handlers.failTribe/failFriend/failGroup` + `failCode` (constants in
`ErrorCodes.java`); the authoritative table lives in PATCH_PLAN.md "Phase 7".

## 10. The RSA password contract (Wave 11)

The client encrypts every modern password payload before it leaves the app
(com.sandbox.login.web.b -> LoginHelper.b -> RSAUtils, classes2.dex):
`RSA/ECB/PKCS1Padding`, a hardcoded 1024-bit X509 public key, 117-byte
chunks, Base64 NO_WRAP. Encrypted flows: POST /user/api/v2/app/login,
POST /user/api/v2/app/set-password (password + confirmPassword), POST
/user/api/v2/user/password/modify (old + new + confirm), POST
/user/api/v1/user/password/check (@Query password). The v1 login wrapper
and v1/register send plaintext.

The original production keypair is unrecoverable (the private half lived on
the real backend), so the local world mints a fixed pair:
- `RsaCipher.java` (server) decrypts for real — Base64 -> 128-byte blocks ->
  PKCS1 chunked decrypt; any mismatch returns the raw value, which keeps
  plaintext v1 flows and host-rig fcalls working (the client's own
  LoginHelper.b has the same lenient fallback when its cipher throws).
- `scripts/patch_rsa_key.py` (build_signed_apk.sh) swaps the client's
  public-key constant in the smali tree for the local server's public key.
  Idempotent; fails the build if the original key survives anywhere.

The stored password is always the plaintext the flow set. RES log lines
carry the envelope code ("code=1") for UI-assertable acceptance checks.

## Session 50 addendum — seeded catalogs + icon streaming

Boot data flow (two layers: APK-embedded SEEDS, device-downloaded ICONS):

```
APK assets (data only, ~1.6 MB)
  assets/localapi/skins.json        ← real 1165-skin backend capture
  assets/localapi/ScriptSetting.csv ← the client's own game list (59 real games)
        │ LocalServer.startIfNeeded (copies once, refresh on size change)
        ▼
<files>/localapi/skins_seed.json  +  games_seed.csv
        │ bootOnce: Skins.ensure + GameCatalog.ensure (seed → own store, then plain state)
        ▼
skins/catalog.json (1165 items)    state.json games[] (real ids, isNewEngine=0)

Icon bytes (NEVER in the APK):
  GitHub release localapi-assets/skins.tar.gz   ← canonical skins.tar.xz also on the release
        │ SkinsAssets daemon thread (download once, 3 attempts)
        ▼
<files>/localapi/skins/img/<id>.png   (USTAR extraction, idempotent)
        │
GET /localapi/skins/icons/<id>.png
        ├─ cache hit  → stream bytes (mime sniffed)
        ├─ cache miss → CDN proxy (item's original iconUrl), fetch-and-cache
        └─ both fail  → code=0 miss envelope (client placeholder)
```

Map + dress asset packs (wip-67 mission, same pattern as the icon pack):
  GitHub release localapi-assets: maps.tar.gz (sha256-pinned, 707 files)
                                   + 10-19_decorate.1607431823179.zip (md5)
        │ MapAssets / DressRes daemon threads (download once, 3 attempts)
        ▼
<files>/localapi/maps/... (ustar extract + index.json: newest
                          <mapid>.<ts>.zip per game via _manifest/games.csv)
<files>/localapi/dress/10-19_decorate...zip
        │
GET /sandbox/games/maps/<key>     → byte-exact bundle/file serving
GET /sandbox/dresses/dress-resources/<key> → decorate pack bytes
        │
Client join: /v1/game-res durl + /v1/dispatch downurl (Dispatch.mapUrl)
Skin flow: checkDressResource → DecorationResourcesResponse (v19, md5)

Halls (catalog v4): g1046 Bedwars→g1008, g1042 Pixel Hall→g1043/44/45/53,
g1058 Lucky Block Hall→g1054 — isLobby=1 + realPlayGameList on the catalog
rows (client Game entity fields); all other games isLobby=0.

Invariants:
- `isNewEngine=0` on every game in every response (engine-1 only runtime).
- `iconUrl` in every dress response points at the loopback streaming route;
  the original CDN url never leaves the server.
- Seeds are data, not code paths: catalogs are editable server state after
  the first seed (skin reseed only when the APK ships a different seed file).

- Packs are data with pinned checksums: a pack whose sha256/md5 does not
  match the release manifest is deleted and re-downloaded; served bytes are
  byte-exact with the GitHub-hosted pack (suite proves byte equality).
- Map/dress pack threads are best-effort and never block boot or the API;
  until a pack lands the routes answer truthful "not available" envelopes
  (needUpdate=false, durl="") and the client keeps its placeholder state.
