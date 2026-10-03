#!/usr/bin/env bash
# build_server_dex.sh — compile localapi-server Java sources into classes6.dex.
# Toolchain (pinned, downloaded on demand into .javatools/):
#   ecj        — Eclipse batch compiler (no JDK needed, runs on JRE 17+)
#   nanohttpd  — embedded HTTP server (single jar, no deps)
#   r8/D8      — dexer from Google Maven
#   android-stubs — compile-time framework stubs (org.json/Context/Log APIs)
# Output: localapi-server/build/classes6.dex
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/localapi-server/src"
OUT="$ROOT/localapi-server/build"
TOOLS="${LOCALAPI_TOOLS:-$ROOT/.javatools}"
mkdir -p "$TOOLS" "$OUT"

ECJ="$TOOLS/ecj.jar"
NANO="$TOOLS/nanohttpd.jar"
R8="$TOOLS/r8.jar"
STUBS="$TOOLS/android-stubs.jar"
JSON="$TOOLS/json.jar"

fetch() { # url dest
  [ -s "$2" ] && return 0
  echo "downloading $(basename "$2")..."
  curl -sSfL -o "$2" "$1"
}

fetch https://repo1.maven.org/maven2/org/eclipse/jdt/ecj/3.33.0/ecj-3.33.0.jar "$ECJ"
fetch https://repo1.maven.org/maven2/org/nanohttpd/nanohttpd/2.3.1/nanohttpd-2.3.1.jar "$NANO"
fetch https://dl.google.com/dl/android/maven2/com/android/tools/r8/8.3.37/r8-8.3.37.jar "$R8"
fetch https://repo1.maven.org/maven2/com/google/android/android/4.1.1.4/android-4.1.1.4.jar "$STUBS"
fetch https://repo1.maven.org/maven2/org/json/json/20231013/json-20231013.jar "$JSON"

echo "[1/3] compiling java sources (ecj)"
rm -rf "$OUT/classes" "$OUT/host" "$OUT/dex"
mkdir -p "$OUT/classes" "$OUT/host" "$OUT/dex"
java -Xmx900m -jar "$ECJ" -nowarn -source 8 -target 8 \
  -cp "$NANO:$STUBS:$JSON" \
  -d "$OUT/classes" \
  "$SRC/com/localapi/LocalServer.java" \
  "$SRC/com/localapi/LocalHttpd.java" \
  "$SRC/com/localapi/Handlers.java" \
  "$SRC/com/localapi/StateStore.java" \
  "$SRC/com/localapi/RoutingTable.java" \
  "$SRC/com/localapi/L.java" \
  "$SRC/com/localapi/HostTest.java" 1>&2

# host test classes get the real org.json on the runtime classpath (device has
# org.json in the framework; the JVM does not)
java -Xmx900m -jar "$ECJ" -nowarn -source 8 -target 8 \
  -cp "$NANO:$STUBS:$JSON:$OUT/classes" \
  -d "$OUT/host" \
  "$SRC/com/localapi/HostTest.java" 1>&2

echo "[2/3] dexing (d8: server + nanohttpd, HostTest excluded)"
java -Xmx1400m -cp "$R8" com.android.tools.r8.D8 \
  --release --min-api 21 --lib "$STUBS" \
  --output "$OUT/dex" \
  $(find "$OUT/classes/com/localapi" -name '*.class' ! -name 'HostTest*') \
  "$NANO" 1>&2

mv "$OUT/dex/classes.dex" "$OUT/classes6.dex"
echo "[3/3] done: $OUT/classes6.dex ($(stat -c%s "$OUT/classes6.dex") bytes)"
