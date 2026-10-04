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
- Phase 3 social/tribe/scrap/decoration: NEXT (IScrapApi 16, IDecorationApi 17,
  IShopApi dress shop, tribe/mailbox lists)
- Phase 4 game runtime: dispatch/join (Dispatch model, MiniGameToken.dispUrl)
  hands the client a game-server address — needs the Engine 10068 GameServer
  phase; API surface (token/dispatch) already state-backed with real tokens.

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
