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
