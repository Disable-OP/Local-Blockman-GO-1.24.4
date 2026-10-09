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

echo "sources assembled at $WORK"
