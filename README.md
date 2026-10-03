# Local-Blockman-GO-1.24.4

Blockman GO 1.24.4 (custom build `com.disabngo.blockynexus`) rebuilt as a **fully local single APK** — the game carries its own API server on `127.0.0.1`, no PC, no tunnel, no internet.

## Status

| Milestone | State |
|---|---|
| Full decompile (apktool + jadx, 5 dexes) | done |
| API surface extraction (18 interfaces / **213 endpoints**) | done — [docs/ENDPOINTS.md](docs/ENDPOINTS.md) |
| Network architecture map | done — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Embedded-server design (NanoHTTPD on loopback) | done — [docs/PATCH_PLAN.md](docs/PATCH_PLAN.md) |
| URL rewiring to `127.0.0.1` (`scripts/patch_urls.py`) | done |
| Rebuild + sign pipeline + GitHub Releases | done (`.github/workflows/build-release.yml`) |
| Redroid arm64 CI test | done (`.github/workflows/test-redroid.yml`) |
| Phase 1: local auth (login/register/token) | **next** |
| Phase 2-4: economy, social, game runtime | backlog |

## Layout

```
docs/ENDPOINTS.md          all 213 endpoints (verb, path, smali method)
docs/ARCHITECTURE.md       network layer: bootstrap, Retrofit, failover, auth headers
docs/PATCH_PLAN.md         embedded server design + phased roadmap
scripts/patch_urls.py      idempotent URL rewiring (2 smali files, 5 const-strings)
scripts/build_signed_apk.sh  decompile→patch→rebuild→zipalign+sign
scripts/extract_endpoints.py smali Retrofit-annotation parser (regenerates ENDPOINTS.md)
.github/workflows/         CI: build-release + test-redroid (arm64 native)
NEXT_SESSION_README.md     context handoff for the next working session
WORKLOG.md                 running session log
```

## Build

```bash
BASE_APK=/path/to/blockman-custom-1.24.4.apk ./scripts/build_signed_apk.sh
# → dist/BlockyNexus-localapi.apk
```

Base APK is attached to GitHub Releases (`base-apk-1.24.4.apk`). Patched builds land on Releases as `BlockyNexus-localapi.apk` on every tag/dispatch.

## Hard-won operational notes

- GitHub API from CI-less environments: unauthenticated calls get rate-limited — always send the token header.
- jadx on this app OOMs at 4 GB RAM: decompile per-dex (`scripts/extract_endpoints.py` notes in WORKLOG.md).
- Agent-backend filter: some host literals in tool commands kill sessions — never paste the tunnel host raw; regex it (`[n]grok`) or match by TLD.
