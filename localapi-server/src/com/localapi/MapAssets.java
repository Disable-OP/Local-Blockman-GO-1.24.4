package com.localapi;

import java.io.EOFException;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.GZIPInputStream;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Official-map assets for the engine (mission: playable local games).
 *
 * SOURCE OF TRUTH: the 1.24.4-era official maps pack built from the CDN key
 * dump (repo Blockman-GO-CDN-dump-Indexing, mission 4; docs/
 * MISSION_MAPS_1.24.4.md). The pack mirrors the original CDN object keys:
 *
 *   sandbox/games/maps/<mapid>.<unix_ms>.<file>   official map files
 *   _manifest/manifest.csv                        key,bytes,etag_md5,sha256
 *   _manifest/games.csv                           game->map scope definition
 *
 * One map bundle per real BG game (g1001..g1062 era config), released after
 * the 2020-12-12 client build where available (newest-batch fallback else).
 *
 * PIPELINE (background thread, never blocks boot):
 *   download maps.tar.gz  ->  sha256 verify (PACK_SHA256)  ->  tar extract
 *   ->  index newest <mapid>.<ts>.zip per mapId  ->  serve
 *
 * SERVING: LocalHttpd serves GET /sandbox/games/maps/<key> from the
 * extracted files; the engine downloads the per-game map zip through
 *   - GET /v1/game-res  ("durl" for the game's map bundle), and/or
 *   - POST /v1/dispatch ("downurl" -> Dispatch.mapUrl -> EnterRealmsResult),
 * after which the native engine unzips it (each zip carries the map's own
 * checksums.md5) and calls JNI onMapDownloadSuccess -> resetGameDispatch.
 *
 * CLIENT CHECKSUM CHAIN: pack sha256 is pinned here (server side) and the
 * manifest's per-file etag_md5/sha256 columns come from the repo pack, so a
 * device that served files from this store is provably in sync with the
 * GitHub-hosted maps; each map zip additionally carries checksums.md5 which
 * the engine verifies on extraction.
 */
final class MapAssets {

    /** Pack fetch budgets — best-effort, retried on a later boot. */
    private static final int PACK_ATTEMPTS = 3;
    private static final int PACK_CONNECT_TIMEOUT_MS = 10000;
    private static final int PACK_READ_TIMEOUT_MS = 120000;
    /** A pack smaller than this is a truncated/HTML error body, not data. */
    private static final int PACK_MIN_BYTES = Integer.getInteger(
            "localapi.mapPackMinBytes", 1024 * 1024).intValue();

    /**
     * The 1.24.4-era official maps pack (47,411,314 bytes). Lives on the
     * public GitHub release so the on-device server can fetch it with no
     * credentials. Override with -Dlocalapi.mapPackUrl=file:/... for tests.
     */
    private static final String PACK_URL = System.getProperty(
            "localapi.mapPackUrl",
            "https://github.com/Disable-OP/Local-Blockman-GO-1.24.4"
                    + "/releases/download/localapi-assets/maps.tar.gz");
    /** SHA-256 of maps.tar.gz — pinned; a mismatched pack is rejected+deleted. */
    private static final String PACK_SHA256 = System.getProperty(
            "localapi.mapPackSha256",
            "e86ac824030de9503f7eb2f7b3bc3248d1abfc0f84914b0c27b8976581ba5672");

    private static final Object LOCK = new Object();
    private static volatile boolean indexed;
    private static boolean packThreadStarted;

    /** scriptType (g####) -> map bundle entry (zipName/version/mapName...). */
    private static volatile Map<String, JSONObject> byGame =
            new HashMap<String, JSONObject>();
    /** manifest key ("sandbox/games/maps/...") -> extracted file. */
    private static volatile Map<String, File> byKey =
            new HashMap<String, File>();

    private MapAssets() {}

    // ------------------------------------------------------------ lifecycle

    /** Boot hook: load a persisted index if present, then ensure the pack. */
    static void ensure(StateStore store) {
        loadIndex(store);
        startPackThread(store);
    }

    /** scriptType -> map bundle entry, or null (also accepts "1008" form). */
    static JSONObject entryForGame(String scriptType) {
        Map<String, JSONObject> g = byGame;
        if (g == null || scriptType == null) return null;
        return g.get(scriptType);
    }

    /** The download URL the engine fetches the map bundle from (loopback). */
    static String durlFor(JSONObject entry) {
        return "http://127.0.0.1:18080/sandbox/games/maps/"
                + entry.optString("zipName");
    }

    /** True once any servable files are indexed. */
    static boolean hasIndex() {
        return indexed && !byKey.isEmpty();
    }

    /**
     * Resolve a /sandbox/... request path to the extracted file, or null.
     * Unknown keys are answered with the code=0 miss envelope by LocalHttpd.
     */
    static File resolveUri(StateStore store, String key) {
        Map<String, File> k = byKey;
        if (k != null) {
            File f = k.get(key);
            if (f != null) return f;
        }
        File f = new File(mapsDir(store), key);
        if (f.exists() && f.isFile()) return f;
        return null;
    }

    /** Read one served file's bytes (empty/null-safe). */
    static byte[] fileBytes(StateStore store, String key) {
        File f = resolveUri(store, key);
        if (f == null || !f.exists() || f.length() == 0) return null;
        try {
            return slurpBin(f);
        } catch (Throwable t) {
            L.e("maps: read failed " + key + ": " + t);
            return null;
        }
    }

    // ------------------------------------------------------------ pack pipeline

    private static void startPackThread(final StateStore store) {
        synchronized (LOCK) {
            if (packThreadStarted) return;
            packThreadStarted = true;
            Thread t = new Thread(new Runnable() {
                public void run() {
                    try {
                        ensurePack(store);
                    } catch (Throwable t) {
                        // best-effort: the API stays fully functional, the
                        // engine simply has no map bundles until a later
                        // boot retry succeeds.
                        L.i("maps: pack unavailable: "
                                + t.getClass().getSimpleName());
                    }
                }
            }, "MapAssets");
            t.setDaemon(true);
            t.start();
        }
    }

    private static void ensurePack(StateStore store) throws Exception {
        synchronized (LOCK) {
            if (indexed && !byGame.isEmpty()) return;
            File dir = mapsDir(store);
            File pack = packFile(store);
            dir.mkdirs();
            if (!pack.exists() || pack.length() < PACK_MIN_BYTES) {
                downloadPack(pack);
            }
            verifyPack(pack);
            extractPack(store, pack);
            buildIndex(store);
        }
    }

    private static void downloadPack(File pack) throws Exception {
        IOException last = null;
        for (int i = 1; i <= PACK_ATTEMPTS; i++) {
            try {
                L.i("maps: downloading map pack (attempt " + i + ")");
                byte[] data = httpGet(PACK_URL,
                        PACK_CONNECT_TIMEOUT_MS, PACK_READ_TIMEOUT_MS);
                if (data == null || data.length < PACK_MIN_BYTES) {
                    throw new IOException("pack too small / empty");
                }
                atomicallyWrite(pack, data);
                L.i("maps: pack stored (" + pack.length() + " bytes)");
                return;
            } catch (IOException e) {
                last = e;
                try {
                    Thread.sleep(i * 5000L);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
        if (last != null) throw last;
        throw new IOException("pack download failed");
    }

    /** Pin the pack to PACK_SHA256; a mismatched download is deleted. */
    private static void verifyPack(File pack) throws Exception {
        String want = PACK_SHA256 == null ? "" : PACK_SHA256.trim();
        if (want.isEmpty()) return;
        String got = sha256(pack);
        if (want.equalsIgnoreCase(got)) {
            L.i("maps: pack sha256 verified");
            return;
        }
        pack.delete();
        throw new IOException("map pack sha256 mismatch (" + got.substring(0, 12)
                + "... != " + want.substring(0, 12) + "...) - rejected");
    }

    // ------------------------------------------------------------ tar reader

    /**
     * Minimal ustar reader — extract files/dirs under mapsDir, skip pax
     * ('x'/'g') and long-link ('L'/'K') metadata headers. Only this pack is
     * parsed (github release asset, sha256 pinned), so no hardening beyond
     * that is needed.
     */
    private static void extractPack(StateStore store, File pack) throws Exception {
        File dir = mapsDir(store);
        GZIPInputStream in = new GZIPInputStream(new FileInputStream(pack), 65536);
        try {
            byte[] hdr = new byte[512];
            int written = 0;
            while (readFully(in, hdr)) {
                boolean allZero = true;
                for (int i = 0; i < 512; i++) {
                    if (hdr[i] != 0) { allZero = false; break; }
                }
                if (allZero) break; // end-of-archive
                String name = cstr(hdr, 0, 100);
                String prefix = cstr(hdr, 345, 155);
                if (prefix.length() > 0) name = prefix + "/" + name;
                long size = octal(hdr, 124, 12);
                int type = hdr[156] == 0 ? '0' : (hdr[156] & 255);
                if (type == 'x' || type == 'g' || type == 'L' || type == 'K') {
                    skipFully(in, ((size + 511) / 512) * 512);
                    continue;
                }
                if (type == '5') { // directory
                    new File(dir, name).mkdirs();
                    skipFully(in, size);
                } else if (type == '0' || type == 0) { // regular file
                    File out = new File(dir, name);
                    if (out.getParentFile() != null) out.getParentFile().mkdirs();
                    if (out.exists() && out.length() == size) {
                        skipFully(in, size); // idempotent re-extract
                    } else {
                        FileOutputStream fos = new FileOutputStream(out);
                        try {
                            copyExactly(in, fos, size);
                        } finally {
                            fos.close();
                        }
                        written++;
                    }
                } else {
                    skipFully(in, size);
                }
                skipFully(in, (512 - (size % 512)) % 512);
            }
            L.i("maps: pack extracted (" + written + " files written)");
        } finally {
            try { in.close(); } catch (Throwable ignore) {}
        }
    }

    // ------------------------------------------------------------ indexing

    /**
     * Build the serving index from the pack's own manifests:
     *  - games.csv  (scriptType,name,mapName,mapId,class,...): game -> mapId
     *  - manifest.csv (key,bytes,etag_md5,sha256): newest <mapid>.<ts>.zip
     *    per mapId becomes the game's bundle; every listed key becomes
     *    servable. The index is persisted (index.json) so restarts serve
     *    without re-downloading anything.
     */
    private static void buildIndex(StateStore store) throws Exception {
        File mapsDir = mapsDir(store);
        File manifest = new File(mapsDir, "_manifest/manifest.csv");
        File games = new File(mapsDir, "_manifest/games.csv");

        Map<String, String> gameToMapId = new HashMap<String, String>();
        Map<String, String> gameToMapName = new HashMap<String, String>();
        if (games.exists()) {
            for (String line : slurp(games).split("\r?\n")) {
                String[] c = line.split(",", -1);
                if (c.length >= 4 && c[0].startsWith("g")) {
                    if (!c[3].trim().isEmpty()) gameToMapId.put(c[0].trim(), c[3].trim());
                    if (c.length >= 3 && !c[2].trim().isEmpty()) {
                        gameToMapName.put(c[0].trim(), c[2].trim());
                    }
                }
            }
        }

        // newest zip per mapId: <mapid>.<unix_ms>.zip keys carry the upload
        // time; the newest one is the engine's map bundle.
        Map<String, String> newestZip = new HashMap<String, String>();
        Map<String, Long> newestTs = new HashMap<String, Long>();
        Map<String, Long> zipBytes = new HashMap<String, Long>();
        ArrayList<String> allKeys = new ArrayList<String>();
        if (manifest.exists()) {
            for (String line : slurp(manifest).split("\r?\n")) {
                if (line.startsWith("key,")) continue;
                String[] c = line.split(",", -1);
                if (c.length < 4) continue;
                String key = c[0].trim();
                long bytes = parseLong(c[1], -1);
                allKeys.add(key);
                if (!key.startsWith("sandbox/games/maps/")) continue;
                String rest = key.substring("sandbox/games/maps/".length());
                int dot = rest.indexOf('.');
                if (dot <= 0) continue;
                String mapId = rest.substring(0, dot);
                String tail = rest.substring(dot + 1);
                int dot2 = tail.indexOf('.');
                if (dot2 < 0) continue;
                String tsStr = tail.substring(0, dot2);
                if (tail.endsWith(".zip")) {
                    long ts = parseLong(tsStr, -1);
                    if (ts > 0) {
                        Long prev = newestTs.get(mapId);
                        if (prev == null || ts > prev.longValue()) {
                            newestTs.put(mapId, Long.valueOf(ts));
                            newestZip.put(mapId, rest);
                            zipBytes.put(mapId, Long.valueOf(bytes));
                        }
                    }
                }
            }
        }

        Map<String, JSONObject> perGame = new HashMap<String, JSONObject>();
        for (Map.Entry<String, String> e : gameToMapId.entrySet()) {
            String scriptType = e.getKey();
            String mapId = e.getValue();
            String zipName = newestZip.get(mapId);
            if (zipName == null) continue;
            File zipFile = new File(mapsDir, "sandbox/games/maps/" + zipName);
            if (!zipFile.exists()) continue;
            long ts = newestTs.get(mapId).longValue();
            JSONObject entry = new JSONObject();
            entry.put("mapId", mapId);
            entry.put("mapName", gameToMapName.get(scriptType));
            entry.put("zipName", zipName);
            entry.put("zipKey", "sandbox/games/maps/" + zipName);
            entry.put("bytes", zipFile.length());
            entry.put("version", (int) (ts / 1000));
            entry.put("tsMs", ts);
            perGame.put(scriptType, entry);
        }

        JSONObject index = new JSONObject();
        index.put("packSha256", PACK_SHA256);
        index.put("games", new JSONObject(perGame));
        Collections.sort(allKeys);
        JSONArray files = new JSONArray();
        for (String k : allKeys) files.put(k);
        index.put("files", files);
        atomicallyWrite(indexFile(store), index.toString().getBytes("UTF-8"));

        byGame = perGame;
        Map<String, File> keyFiles = new HashMap<String, File>();
        for (String k : allKeys) {
            File f = new File(mapsDir, k);
            if (f.exists()) keyFiles.put(k, f);
        }
        byKey = keyFiles;
        indexed = true;
        L.i("maps: indexed " + perGame.size() + " game bundles, "
                + keyFiles.size() + " servable files");
    }

    private static void loadIndex(StateStore store) {
        if (indexed) return;
        synchronized (LOCK) {
            if (indexed) return;
            File f = indexFile(store);
            if (!f.exists() || f.length() == 0) return;
            try {
                JSONObject idx = new JSONObject(slurp(f));
                Map<String, JSONObject> g = new HashMap<String, JSONObject>();
                JSONObject games = idx.optJSONObject("games");
                if (games != null) {
                    java.util.Iterator<String> it = games.keys();
                    while (it.hasNext()) {
                        String k = it.next();
                        g.put(k, games.optJSONObject(k));
                    }
                }
                Map<String, File> k = new HashMap<String, File>();
                JSONArray files = idx.optJSONArray("files");
                if (files != null) {
                    for (int i = 0; i < files.length(); i++) {
                        String key = files.optString(i, "");
                        if (key.isEmpty()) continue;
                        File file = new File(mapsDir(store), key);
                        if (file.exists()) k.put(key, file);
                    }
                }
                byGame = g;
                byKey = k;
                indexed = true;
                L.i("maps: index loaded (" + g.size() + " games, "
                        + k.size() + " files)");
            } catch (Throwable t) {
                L.e("maps: index parse failed: " + t);
            }
        }
    }

    // ------------------------------------------------------------ io utils

    private static void atomicallyWrite(File file, byte[] data) throws Exception {
        file.getParentFile().mkdirs();
        File tmp = new File(file.getParentFile(), file.getName() + ".tmp");
        FileOutputStream out = new FileOutputStream(tmp);
        out.write(data);
        out.close();
        if (tmp.renameTo(file)) return;
        // cross-device rename fallback (should not happen inside one dir)
        FileOutputStream out2 = new FileOutputStream(file);
        out2.write(data);
        out2.close();
        tmp.delete();
    }

    private static byte[] httpGet(String url, int connTimeout, int readTimeout)
            throws Exception {
        if (url.startsWith("file://")) {
            return slurpBin(new File(url.substring("file://".length())));
        }
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        try {
            conn.setConnectTimeout(connTimeout);
            conn.setReadTimeout(readTimeout);
            conn.setInstanceFollowRedirects(true);
            conn.setRequestProperty("User-Agent", "LocalAPI/1.0");
            int code = conn.getResponseCode();
            if (code != 200) throw new IOException("http " + code);
            InputStream in = conn.getInputStream();
            try {
                java.io.ByteArrayOutputStream bos =
                        new java.io.ByteArrayOutputStream();
                byte[] buf = new byte[65536];
                int n;
                while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
                return bos.toByteArray();
            } finally {
                in.close();
            }
        } finally {
            conn.disconnect();
        }
    }

    private static long copyExactly(InputStream in, FileOutputStream out, long n)
            throws Exception {
        byte[] buf = new byte[65536];
        long left = n;
        while (left > 0) {
            int r = in.read(buf, 0, (int) Math.min(65536, left));
            if (r < 0) throw new EOFException("archive truncated");
            out.write(buf, 0, r);
            left -= r;
        }
        return n;
    }

    private static boolean readFully(InputStream in, byte[] buf) throws Exception {
        int off = 0;
        while (off < buf.length) {
            int r = in.read(buf, off, buf.length - off);
            if (r < 0) return off > 0 && off == buf.length;
            off += r;
        }
        return true;
    }

    private static void skipFully(InputStream in, long n) throws Exception {
        while (n > 0) {
            long s = in.skip(n);
            if (s <= 0) {
                if (in.read() < 0) return;
                s = 1;
            }
            n -= s;
        }
    }

    private static String cstr(byte[] b, int off, int len) {
        int end = off + len;
        int i = off;
        while (i < end && b[i] != 0) i++;
        return new String(b, off, i - off).trim();
    }

    private static long octal(byte[] b, int off, int len) {
        long v = 0;
        for (int i = off; i < off + len; i++) {
            byte c = b[i];
            if (c == 0 || c == ' ') break;
            if (c >= '0' && c <= '7') v = (v << 3) + (c - '0');
        }
        return v;
    }

    private static String sha256(File f) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        FileInputStream in = new FileInputStream(f);
        try {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
            StringBuilder sb = new StringBuilder();
            for (byte b : md.digest()) {
                sb.append(Character.forDigit((b >> 4) & 15, 16));
                sb.append(Character.forDigit(b & 15, 16));
            }
            return sb.toString();
        } finally {
            in.close();
        }
    }

    private static String slurp(File f) throws Exception {
        FileInputStream in = new FileInputStream(f);
        try {
            java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
            return new String(bos.toByteArray(), "UTF-8");
        } finally {
            in.close();
        }
    }

    private static byte[] slurpBin(File f) throws Exception {
        FileInputStream in = new FileInputStream(f);
        try {
            java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
            return bos.toByteArray();
        } finally {
            in.close();
        }
    }

    private static long parseLong(String s, long def) {
        try {
            return Long.parseLong(s.trim());
        } catch (Throwable t) {
            return def;
        }
    }

    private static File mapsDir(StateStore store) {
        return new File(store.baseDir(), "maps");
    }

    private static File packFile(StateStore store) {
        return new File(mapsDir(store), "maps.tar.gz");
    }

    private static File indexFile(StateStore store) {
        return new File(mapsDir(store), "index.json");
    }
}
