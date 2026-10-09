#!/usr/bin/env bash
# Reassemble the GameServer source tree from the repo-root archives.
# Idempotent: safe to re-run; wipes and rebuilds the target dir.
# Usage: assemble_sources.sh <workdir>
set -euo pipefail

WORK="${1:?usage: assemble_sources.sh <workdir>}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

rm -rf "$WORK"
mkdir -p "$WORK/extract"

cd "$WORK"

# --- res archive: 6 parts. parts 1-5 are split into 24MiB chunks (concatenate),
#     each part is an independent xz'd batch tar; part 6 ships inside a 7z. ---
for i in 1 2 3 4 5; do
  chunks=$(ls "$REPO"/res_archive_part$i.tar.xz.chunk_* | sort)
  n=$(echo "$chunks" | wc -l)
  if [ "$n" -gt 1 ]; then
    cat $chunks > part$i.tar.xz
  else
    cp $chunks part$i.tar.xz
  fi
done
cp "$REPO/res_archive_part6.tar.xz.7z" part6.7z
python3 - <<'PY'
import py7zr
with py7zr.SevenZipFile('part6.7z') as z:
    z.extractall('.')
PY
mv res_archive_part6.tar.xz part6.tar.xz
for i in 1 2 3 4 5 6; do
  tar -xJf part$i.tar.xz -C extract
done

# --- project archive: dev tree (server/logic/deploy) ---
cat "$REPO"/project_archive_part1.tar.xz.aa \
    "$REPO"/project_archive_part1.tar.xz.ab \
    "$REPO"/project_archive_part1.tar.xz.ac > proj1.tar.xz
tar -xJf proj1.tar.xz -C extract
tar -xJf "$REPO/project_archive_part2.tar.xz" -C extract

# sanity
test -d extract/dev/server/src
test -d extract/engine-core/dev/engine/Src/Core
test -d extract/res/client/Media/Scripts/ServerGame
N=$(find extract/res -path '*ServerGame*' -name '*.lua' | wc -l)
echo "ServerGame lua files: $N"
test "$N" -gt 2000

# --- behaviac (BT engine; only headers ship in the tree, source on GitHub) ---
if [ ! -d behaviac-src ]; then
  git clone --depth 1 https://github.com/Tencent/behaviac.git behaviac-src
fi
test -d behaviac-src/src

# --- curl 7.55.1 (the bundled src/android/curl is 7.55-era code with 7.52
#     headers; the client used a prebuilt libcurl.a. We build a real tree.) ---
if [ ! -f curl-7.55.1/lib/curl_config.h ]; then
  if [ ! -d curl-7.55.1 ]; then
    curl -sL --retry 3 -o curl-7.55.1.tar.xz \
      https://github.com/curl/curl/releases/download/curl-7_55_1/curl-7.55.1.tar.xz
    tar -xJf curl-7.55.1.tar.xz && rm -f curl-7.55.1.tar.xz
  fi
  test -n "${NDK:-}" || { echo "NDK env must point at android-ndk-r17c" >&2; exit 1; }
  WRAP="$WORK/gswrap"; mkdir -p "$WRAP"
  for t in gcc g++; do
    printf '#!/bin/sh\nexec "%s/toolchains/aarch64-linux-android-4.9/prebuilt/linux-x86_64/bin/aarch64-linux-android-%s" --sysroot=%s/platforms/android-21/arch-arm64 -isystem %s/sysroot/usr/include -isystem %s/sysroot/usr/include/aarch64-linux-android "$@"\n' \
      "$NDK" "$t" "$NDK" "$NDK" "$NDK" > "$WRAP/aarch64-linux-android-$t"
    chmod +x "$WRAP/aarch64-linux-android-$t"
  done
  ( cd curl-7.55.1 \
    && PATH="$WRAP:$PATH" CC=aarch64-linux-android-gcc \
       CPP="aarch64-linux-android-gcc -E" cross_compiling=yes \
       ./configure --build=x86_64-pc-linux-gnu --host=aarch64-linux-android \
         --disable-shared --enable-static --without-ssl --without-zlib \
         --without-libidn2 --without-libssh2 --without-nghttp2 --without-libpsl \
         --without-brotli --disable-ldap --disable-ldaps --disable-rtsp \
         --disable-ftp --disable-file --disable-dict --disable-telnet \
         --disable-tftp --disable-pop3 --disable-imap --disable-smtp \
         --disable-gopher --disable-manual > configure.log 2>&1 )
  test -f curl-7.55.1/lib/curl_config.h || { tail -30 curl-7.55.1/configure.log >&2; exit 1; }
  echo "curl 7.55.1 configured (http-only static)"
fi

echo "sources assembled at $WORK"
