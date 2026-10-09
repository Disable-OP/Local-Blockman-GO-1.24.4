package com.localapi;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.GZIPInputStream;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Skin (dress) catalog + device-side icon streaming for the local API.
 *
 * CATALOG: seeded ONCE from the APK asset localapi/skins.json — a genuine
 * 1.24.4 backend capture with 1165 real skins (id/typeId/name/price/
 * occupyPosition/camera/... as the client models expect them). The seed is
 * copied by LocalServer.startIfNeeded into <files>/localapi/skins_seed.json;
 * Skins parses it into its OWN store file (<files>/localapi/skins/
 * catalog.json) so the big list never bloats or slows the shared
 * state.json save path. After seeding it is ordinary editable server state
 * (reseeded only when the APK ships a different seed).
 *
 * ICONS: no icon bytes ship inside the APK. Every catalog iconUrl is
 * rewritten per-request to http://127.0.0.1:18080/localapi/skins/icons/<id>
 * .png, and the icon bytes are streamed from:
 *   1. the extracted icon cache (<files>/localapi/skins/img/<id>.png),
 *      filled on first boot from the icon-pack archive downloaded once
 *      from the project's GitHub Releases (skins.tar.gz; the canonical
 *      archive on the release is skins.tar.xz — the runtime fetches the
 *      gzip twin because the Android platform already has a gzip
 *      inflater, keeping the server dex dependency-free), or
 *   2. on a cache miss, the ORIGINAL CDN url stored per item — a
 *      transparent fetch-and-cache proxy so icons appear instantly on
 *      online devices even before the pack lands.
 * Everything is best-effort: a failed download or proxy never breaks the
 * API — the client simply renders its placeholder for that icon.
 */
final class Skins {

    private static final String ICON_PACK_URL = System.getProperty(
            "localapi.iconPackUrl",
            "https://github.com/Disable-OP/Local-Blockman-GO-1.24.4"
                    + "/releases/download/localapi-assets/skins.tar.gz");
    /** Asset-pack fetch budgets — fail fast, retry on a later boot. */
    private static final int PACK_ATTEMPTS = 3;
    private static final int PACK_CONNECT_TIMEOUT_MS = 10000;
    private static final int PACK_READ_TIMEOUT_MS = 30000;
    /** CDN proxy budgets (per icon). */
    private static final int PROXY_TIMEOUT_MS = 6000;

    private static final Object LOCK = new Object();
    private static boolean loaded;
    private static boolean packThreadStarted;
    /** id -> catalog item (JSONObject, contains the original cdn iconUrl). */
    private static Map<Long, JSONObject> byId = new HashMap<Long, JSONObject>();
    /** typeId -> items in catalog order. */
    private static Map<Long, JSONArray> byType = new HashMap<Long, JSONArray>();

    private Skins() {}

    // ------------------------------------------------------------ lifecycle

    /**
     * Load the catalog (seed on first run). Safe to call from every boot:
     * idempotent, and the heavy work happens at most once per process.
     */
    static void ensure(final StateStore store) {
        try {
            loadOrSeed(store);
        } catch (Throwable t) {
            L.e("skins: catalog load failed: " + t);
        }
        startPackThread(store);
    }

    private static void loadOrSeed(StateStore store) throws Exception {
        synchronized (LOCK) {
            if (loaded) return;
            File catalog = catalogFile(store);
            File seed = seedFile(store);
            String stamp = seedStamp(seed);
            if (catalog.exists()) {
                try {
                    JSONObject root = new JSONObject(slurp(catalog));
                    if (stamp == null || stamp.equals(root.optString("seedStamp"))) {
                        parseCatalog(root.optJSONArray("items"));
                        loaded = true;
                        L.i("skins: catalog loaded (" + byId.size() + " skins, "
                                + byType.size() + " type groups)");
                        return;
                    }
                    L.i("skins: seed changed (" + root.optString("seedStamp")
                            + " -> " + stamp + ") — reseeding");
                } catch (Throwable t) {
                    L.e("skins: catalog parse failed, reseeding: " + t);
                }
            }
            if (stamp == null) {
                // No seed visible (host rig without a fixture): leave the
                // catalog empty — handlers fall back to the legacy generated
                // dresses until a seed appears.
                loaded = true;
                L.i("skins: no seed present — catalog empty (legacy fallback)");
                return;
            }
            seedFromAsset(store, seed, stamp);
            loaded = true;
        }
    }

    /** Parse the captured backend response ({code,message,data:[skins]}). */
    private static void seedFromAsset(StateStore store, File seed, String stamp)
            throws Exception {
        JSONObject doc = new JSONObject(slurp(seed));
        JSONArray data = doc.optJSONArray("data");
        if (data == null || data.length() == 0) {
            L.e("skins: seed has no data array — catalog stays empty");
            return;
        }
        // normalize: keep the item verbatim (iconUrl = original CDN url)
        JSONObject root = new JSONObject();
        root.put("seedStamp", stamp);
        root.put("items", data);
        File catalog = catalogFile(store);
        catalog.getParentFile().mkdirs();
        atomicallyWrite(catalog, root.toString().getBytes("UTF-8"));
        parseCatalog(data);
        L.i("skins: catalog seeded from asset (" + data.length() + " skins) -> "
                + catalog.getName());
    }

    private static void parseCatalog(JSONArray items) {
        byId = new HashMap<Long, JSONObject>();
        byType = new HashMap<Long, JSONArray>();
        for (int i = 0; i < items.length(); i++) {
            JSONObject it = items.optJSONObject(i);
            if (it == null) continue;
            long id = it.optLong("id", -1);
            if (id < 0) continue;
            byId.put(id, it);
            long t = it.optLong("typeId", 0);
            JSONArray list = byType.get(t);
            if (list == null) {
                list = new JSONArray();
                byType.put(t, list);
            }
            list.put(it);
        }
    }

    // ------------------------------------------------------------- queries

    static boolean hasCatalog() {
        synchronized (LOCK) {
            return loaded && !byId.isEmpty();
        }
    }

    static JSONObject byId(long id) {
        synchronized (LOCK) {
            return loaded ? byId.get(id) : null;
        }
    }

    static JSONArray byType(long typeId) {
        synchronized (LOCK) {
            return loaded ? byType.get(typeId) : null;
        }
    }

    /** Loopback icon url for one skin id (the ONLY icon url we ever emit). */
    static String iconUrl(long id) {
        return Handlers.LOCAL_BASE_URL + "/localapi/skins/icons/" + id + ".png";
    }

    // ----------------------------------------------------------- icon bytes

    /**
     * Icon bytes for one skin id: extracted cache first, then the original
     * CDN (fetch-and-cache proxy). Returns null when both are unavailable.
     */
    static byte[] iconBytes(StateStore store, long id) {
        File f = iconFile(store, id);
        if (f != null && f.exists() && f.length() > 0) {
            try {
                return slurpBin(f);
            } catch (Throwable t) {
                L.e("skins: icon read failed id=" + id + ": " + t);
            }
        }
        // proxy fallback — the catalog item carries the original url
        JSONObject it = byId(id);
        if (it == null) return null;
        String cdn = it.optString("iconUrl", "");
        if (cdn == null || !cdn.startsWith("http")) return null;
        try {
            byte[] data = httpGet(cdn, PROXY_TIMEOUT_MS, PROXY_TIMEOUT_MS);
            if (data == null || data.length < 64) return null;
            if (f != null) {
                try {
                    f.getParentFile().mkdirs();
                    atomicallyWrite(f, data);
                } catch (Throwable t) {
                    L.e("skins: icon cache write failed id=" + id + ": " + t);
                }
            }
            return data;
        } catch (Throwable t) {
            L.i("skins: cdn proxy miss id=" + id + ": " + t.getClass().getSimpleName());
            return null;
        }
    }

    /** Content-type sniffing for icon bytes (png/jpeg/webp/gif). */
    static String sniffMime(byte[] d) {
        if (d == null || d.length < 12) return "application/octet-stream";
        if ((d[0] & 0xFF) == 0x89 && d[1] == 'P' && d[2] == 'N' && d[3] == 'G') {
            return "image/png";
        }
        if ((d[0] & 0xFF) == 0xFF && (d[1] & 0xFF) == 0xD8) return "image/jpeg";
        if (d[0] == 'G' && d[1] == 'I' && d[2] == 'F') return "image/gif";
        if (d[0] == 'R' && d[1] == 'I' && d[2] == 'F' && d[3] == 'F'
                && d[8] == 'W' && d[9] == 'E' && d[10] == 'B' && d[11] == 'P') {
            return "image/webp";
        }
        return "application/octet-stream";
    }

    // ------------------------------------------------- asset pack (tar.gz)

    private static void startPackThread(final StateStore store) {
        synchronized (LOCK) {
            if (packThreadStarted) return;
            packThreadStarted = true;
        }
        Thread t = new Thread(new Runnable() {
            @Override public void run() {
                try {
                    ensurePack(store);
                } catch (Throwable t) {
                    L.i("skins: icon pack unavailable: "
                            + t.getClass().getSimpleName());
                }
            }
        }, "SkinsAssets");
        t.setDaemon(true);
        t.start();
    }

    /**
     * Make sure every catalog icon exists in the img/ cache: download the
     * pack once if needed, then extract the missing entries. Fully
     * idempotent; every failure is non-fatal (the CDN proxy covers online
     * devices meanwhile).
     */
    private static void ensurePack(StateStore store) throws Exception {
        synchronized (LOCK) {
            if (byId.isEmpty()) return; // nothing to fetch for
        }
        File img = imgDir(store);
        File pack = packFile(store);
        int expected = size();
        int have = img.exists() ? img.listFiles().length : 0;
        if (have >= expected) return; // already complete
        if (!pack.exists() || pack.length() < 1024 * 1024) {
            downloadPack(pack);
        }
        if (pack.exists() && pack.length() >= 1024 * 1024) {
            img.mkdirs();
            int before = img.exists() ? img.listFiles().length : 0;
            extractPack(pack, img);
            int after = img.exists() ? img.listFiles().length : 0;
            L.i("skins: icon pack extracted (" + before + " -> " + after
                    + " / " + expected + " icons)");
        }
    }

    private static void downloadPack(File pack) throws Exception {
        java.io.IOException last = null;
        for (int attempt = 1; attempt <= PACK_ATTEMPTS; attempt++) {
            try {
                L.i("skins: downloading icon pack (attempt " + attempt + ")");
                byte[] data = httpGet(ICON_PACK_URL,
                        PACK_CONNECT_TIMEOUT_MS, PACK_READ_TIMEOUT_MS);
                if (data == null || data.length < 1024 * 1024) {
                    throw new java.io.IOException("pack too small / empty");
                }
                atomicallyWrite(pack, data);
                L.i("skins: icon pack stored (" + pack.length() + " bytes)");
                return;
            } catch (java.io.IOException e) {
                last = e;
                try {
                    Thread.sleep(attempt * 5000L);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
        throw last == null ? new java.io.IOException("pack download failed")
                : last;
    }

    /**
     * Minimal USTAR reader: walks 512-byte headers, copies regular-file
     * payloads into img/<name>. Skips pax/global headers and directories;
     * re-extracts only entries whose cached size differs.
     */
    private static void extractPack(File pack, File imgDir) throws Exception {
        GZIPInputStream gz = new GZIPInputStream(
                new FileInputStream(pack), 1 << 16);
        try {
            byte[] hdr = new byte[512];
            while (readFully(gz, hdr)) {
                boolean zero = true;
                for (byte b : hdr) {
                    if (b != 0) {
                        zero = false;
                        break;
                    }
                }
                if (zero) break;
                String name = cstr(hdr, 0, 100);
                String prefix = cstr(hdr, 345, 155);
                if (prefix.length() > 0) name = prefix + "/" + name;
                long size = octal(hdr, 124, 12);
                int type = hdr[156] == 0 ? '0' : (hdr[156] & 0xFF);
                if (type == 'x' || type == 'g' || type == 'L' || type == 'K') {
                    skipFully(gz, ((size + 511) / 512) * 512);
                    continue;
                }
                File out = new File(imgDir, new File(name).getName());
                boolean need = !"0".equals(String.valueOf((char) type))
                        && type != 0 ? false : !out.exists()
                        || out.length() != size;
                if (need) {
                    FileOutputStream fos = new FileOutputStream(out);
                    copyExactly(gz, fos, size);
                    fos.close();
                } else {
                    skipFully(gz, size);
                }
                long pad = (512 - (size % 512)) % 512;
                skipFully(gz, pad);
            }
        } finally {
            try {
                gz.close();
            } catch (Throwable ignore) {
            }
        }
    }

    // ------------------------------------------------------------ plumbing

    static int size() {
        synchronized (LOCK) {
            return byId.size();
        }
    }

    private static File baseDir(StateStore store) {
        return store.baseDir();
    }

    private static File catalogFile(StateStore store) {
        return new File(new File(baseDir(store), "skins"), "catalog.json");
    }

    private static File seedFile(StateStore store) {
        return new File(baseDir(store), "skins_seed.json");
    }

    private static File imgDir(StateStore store) {
        return new File(new File(baseDir(store), "skins"), "img");
    }

    private static File packFile(StateStore store) {
        return new File(new File(baseDir(store), "skins"), "skins.tar.gz");
    }

    static File iconFile(StateStore store, long id) {
        return new File(imgDir(store), id + ".png");
    }

    /** Identify a seed by size+mtime so a changed APK re-seeds the catalog. */
    private static String seedStamp(File seed) {
        if (seed == null || !seed.exists() || seed.length() == 0) return null;
        return seed.length() + "-" + seed.lastModified();
    }

    private static String slurp(File f) throws Exception {
        FileInputStream in = new FileInputStream(f);
        try {
            java.io.ByteArrayOutputStream bos =
                    new java.io.ByteArrayOutputStream();
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
            java.io.ByteArrayOutputStream bos =
                    new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
            return bos.toByteArray();
        } finally {
            in.close();
        }
    }

    private static void atomicallyWrite(File dst, byte[] data) throws Exception {
        File tmp = new File(dst.getParentFile(), dst.getName() + ".tmp");
        FileOutputStream out = new FileOutputStream(tmp);
        out.write(data);
        out.close();
        if (!tmp.renameTo(dst)) {
            FileOutputStream out2 = new FileOutputStream(dst);
            out2.write(data);
            out2.close();
            tmp.delete();
        }
    }

    private static byte[] httpGet(String url, int connTimeout, int readTimeout)
            throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        try {
            c.setConnectTimeout(connTimeout);
            c.setReadTimeout(readTimeout);
            c.setInstanceFollowRedirects(true);
            c.setRequestProperty("User-Agent", "LocalAPI/1.0");
            int code = c.getResponseCode();
            if (code != 200) throw new java.io.IOException("http " + code);
            InputStream in = c.getInputStream();
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
            c.disconnect();
        }
    }

    private static boolean readFully(InputStream in, byte[] buf) throws Exception {
        int off = 0;
        while (off < buf.length) {
            int n = in.read(buf, off, buf.length - off);
            if (n < 0) return off > 0 && off == buf.length;
            off += n;
        }
        return true;
    }

    private static void skipFully(InputStream in, long n) throws Exception {
        long left = n;
        while (left > 0) {
            long s = in.skip(left);
            if (s <= 0) {
                if (in.read() < 0) return;
                s = 1;
            }
            left -= s;
        }
    }

    private static void copyExactly(InputStream in, FileOutputStream out,
                                    long n) throws Exception {
        byte[] buf = new byte[65536];
        long left = n;
        while (left > 0) {
            int r = in.read(buf, 0, (int) Math.min(buf.length, left));
            if (r < 0) throw new java.io.EOFException("archive truncated");
            out.write(buf, 0, r);
            left -= r;
        }
    }

    private static String cstr(byte[] hdr, int off, int len) {
        int end = off;
        int max = off + len;
        while (end < max && hdr[end] != 0) end++;
        return new String(hdr, off, end - off).trim();
    }

    private static long octal(byte[] hdr, int off, int len) {
        long v = 0;
        for (int i = off; i < off + len; i++) {
            byte b = hdr[i];
            if (b == 0 || b == ' ') break;
            if (b < '0' || b > '7') continue;
            v = (v << 3) + (b - '0');
        }
        return v;
    }
}
