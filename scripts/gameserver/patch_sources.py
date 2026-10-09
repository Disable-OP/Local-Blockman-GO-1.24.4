#!/usr/bin/env python3
"""Apply surgical patches to the assembled GameServer sources (idempotent).

Patches (all build-environment driven, none change game behaviour):
1. CoreDef.h            — aarch64 recognized as 64-bit; LORD_FORCE_PLATFORM override
                          so the server compiles its LINUX branches under the NDK.
2. curl_config.h        — drop OpenSSL (loopback http only, no TLS dependency).
3. Core/Std/cpp17/string_view.h — skip the backport shim under libc++.
4. ClientPeer.cpp       — getName() returns LORD::String; passing it through
                          printf-style varargs is UB (gcc hard-errors on it).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
ENGINE = os.path.join(ROOT, 'extract', 'engine-core', 'dev', 'engine')
LIBS = os.path.join(ROOT, 'extract', 'engine-core', 'dev', 'libraries')
SERVER = os.path.join(ROOT, 'extract', 'dev', 'server', 'src')


def patch(path, transforms):
    with open(path, encoding='latin-1') as f:
        s = f.read()
    orig = s
    for old, new in transforms:
        if new in s:
            continue  # already applied
        if old not in s:
            raise SystemExit('patch anchor missing in %s: %r' % (path, old[:60]))
        s = s.replace(old, new, 1)
    if s != orig:
        with open(path, 'w', encoding='latin-1') as f:
            f.write(s)
        print('patched', os.path.relpath(path, ROOT))
    else:
        print('ok (already)', os.path.relpath(path, ROOT))


# 1. CoreDef.h
patch(os.path.join(ENGINE, 'Src/Core/CoreDef.h'), [
    ("defined(__s390x__)",
     "defined(__s390x__) || defined(__aarch64__) || defined(_M_ARM64)"),
    ("#if defined(_WIN32) || defined(__WIN32__) || defined(WIN32)\n#\tdefine LORD_PLATFORM    LORD_PLATFORM_WINDOWS",
     "#if defined(LORD_FORCE_PLATFORM)\n#\tdefine LORD_PLATFORM    LORD_FORCE_PLATFORM\n#elif defined(_WIN32) || defined(__WIN32__) || defined(WIN32)\n#\tdefine LORD_PLATFORM    LORD_PLATFORM_WINDOWS"),
])

# 2. curl_config.h — no TLS needed for loopback
patch(os.path.join(LIBS, 'src/android/curl/curl_config.h'), [
    ("#define USE_OPENSSL 1",
     "/* #undef USE_OPENSSL */ /* loopback-only build: TLS not needed */"),
])

# 3. string_view shim vs libc++
patch(os.path.join(ENGINE, 'Src/Core/Std/cpp17/string_view.h'), [
    ("#if __cplusplus < 201703L",
     "#if !defined(_LIBCPP_VERSION) && __cplusplus < 201703L"),
])

# 3b. curl: the bundled sources are 7.53-era (struct Curl_easy) while the
#     bundled headers are 7.52.1-DEV (CURL*). The client used a prebuilt
#     libcurl.a; we build the sources, so align the two escaped-URL
#     prototypes (the only API change that touches this build).
# curl.h treats CURL as void* (no struct Curl_easy forward decl); the 7.53
# sources name the parameter struct Curl_easy*. Without a file-scope forward
# declaration the tag lands in the parameter-list scope and conflicts with
# urldata.h's real struct — so declare it first.
for hdr in ('include/android/curl/64/curl/curl.h',):
    patch(os.path.join(LIBS, hdr), [
        ("CURL_EXTERN char *curl_easy_escape(CURL *handle,",
         "struct Curl_easy;\nCURL_EXTERN char *curl_easy_escape(struct Curl_easy *handle,"),
        ("CURL_EXTERN char *curl_easy_unescape(CURL *handle,",
         "CURL_EXTERN char *curl_easy_unescape(struct Curl_easy *handle,"),
    ])

# 4. ClientPeer varargs UB (LORD::String -> const char*)
peer = os.path.join(SERVER, 'Network/ClientPeer.cpp')
with open(peer, encoding='latin-1') as f:
    s = f.read()
fixed = s.replace('getRakssid(), getName(), hasLogon()',
                  'getRakssid(), getName().c_str(), hasLogon()')
if fixed != s:
    with open(peer, 'w', encoding='latin-1') as f:
        f.write(fixed)
    print('patched dev/server/src/Network/ClientPeer.cpp (varargs)')
else:
    print('ok (already) dev/server/src/Network/ClientPeer.cpp')

print('all patches applied')
