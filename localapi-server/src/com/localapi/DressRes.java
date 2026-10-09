package com.localapi;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Enumeration;
import java.util.zip.ZipFile;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Skin/dress RESOURCE pack for the client renderer (mission: the client must
 * be able to render the skins the catalog sells — ALL of them, no matter how
 * new, and degrade gracefully for anything unavailable).
 *
 * Session 52 mega-pack: the union of EVERY decorate generation indexed in
 * the sandbox.csv CDN dump (sandbox/dresses/dress-resources/*.zip,
 * 2020-03-03 .. 2021-06-08 — 613 packs, 598 unique contents), merged
 * newest-wins per path. That includes the 1.24.4-era 10-19_decorate bundle
 * (dressVersion 19) and the 7-9_decorate* members the mission calls the
 * "July 9" pack (the X-Y prefix reads as a date). Target version 31 is the
 * newest real decorate generation on the original CDN (June 2021 snapshot —
 * the closest obtainable to the mission's July 2021 request).
 *
 * Coverage: 1,223 shipped files; Decorate_res_config.txt is aligned to the
 * shipped bytes (10 md5s that pointed at versions shipped in no pack were
 * corrected). 292 manifest entries reference the face-merge/newer part set
 * that exists in NO obtainable source (not in any of the 613 packs, not in
 * the 72.9M-key dump, not on the live CDN, not in the APK baseline) — those
 * degrade gracefully: the engine renders the default for the slot instead
 * of failing, which is exactly the "no matter if it's not available" half
 * of the mission. The client applies the zip as an overlay copy
 * (CopyDownloadToResources, verified from the 1.24.4 APK: resources/Media/**
 * over every engine res root, overwrite=true, no deletions), so anything
 * the pack does not carry simply keeps the previous art.
 *
 * CLIENT CONTRACT (verified from the 1.24.4 APK):
 *   GET /decoration/api/v1/new/decorations/check/resource
 *       ?resVersion=<local>&engineVersion=<v>   (IDecorationApi.
 *       checkDressResource) -> DecorationResourcesResponse
 *       {needUpdate, version, url, hash, fileCount, fileSize, cdns[]}.
 *   needUpdate=true -> the client downloads <url> (via cdns fallback) once,
 *   verifies <hash> (md5 of the zip), unzips to app_download, copies
 *   resources/Media over the res roots, stores the new resVersion; until
 *   the local pack is present the server answers needUpdate=false /
 *   version=<client's> so the flow never wedges.
 */
final class DressRes {

    /** Newest real decorate generation obtainable from the original CDN. */
    private static final int DRESS_VERSION = 31;
    /** The merged all-generations pack (see class doc). */
    private static final String PACK_NAME = "decorate_merged_v31.1623125813504.zip";

    private static final int PACK_ATTEMPTS = 3;
    private static final int PACK_CONNECT_TIMEOUT_MS = 10000;
    private static final int PACK_READ_TIMEOUT_MS = 120000;
    private static final int PACK_MIN_BYTES = Integer.getInteger(
            "localapi.dressPackMinBytes", 1024 * 1024).intValue();

    /** Public release asset — no credentials needed on device. */
    private static final String PACK_URL = System.getProperty(
            "localapi.dressPackUrl",
            "https://github.com/Disable-OP/Local-Blockman-GO-1.24.4"
                    + "/releases/download/localapi-assets/" + PACK_NAME);
    /** MD5 of the decorate pack (from the pack manifest; the client's
     * DecorationResourcesResponse.hash carries the same value). */
    private static final String PACK_MD5 = System.getProperty(
            "localapi.dressPackMd5", "ae133c31151484813ee4b605a1859c7c");

    private static final Object LOCK = new Object();
    private static volatile Boolean packOk;
    private static boolean packThreadStarted;

    private DressRes() {}

    // ------------------------------------------------------------ lifecycle

    static void ensure(StateStore store) {
        startPackThread(store);
    }

    /** The loopback path this pack is served under (LocalHttpd /sandbox/). */
    static String packPath() {
        return "/sandbox/dresses/dress-resources/" + PACK_NAME;
    }

    /** The pack's bytes for LocalHttpd serving, or null when unavailable. */
    static byte[] packBytes(StateStore store) {
        File f = packFile(store);
        if (!f.exists() || f.length() == 0) return null;
        try {
            return slurpBin(f);
        } catch (Throwable t) {
            L.e("dress: pack read failed: " + t);
            return null;
        }
    }

    /**
     * DecorationResourcesResponse for the client's resource check. When the
     * pack is unavailable locally the answer is a truthful "no update"
     * (version=max(1, client's)) instead of a URL the client would 404 on.
     */
    static JSONObject checkResponse(StateStore store, long clientVersion)
            throws org.json.JSONException {
        boolean havePack = ensurePack(store);
        File f = packFile(store);
        long bytes = (havePack && f.exists()) ? f.length() : 0L;

        int fileCount = 0;
        if (havePack) {
            try {
                ZipFile zip = new ZipFile(f);
                try {
                    Enumeration<? extends java.util.zip.ZipEntry> es =
                            zip.entries();
                    while (es.hasMoreElements()) {
                        if (!es.nextElement().isDirectory()) fileCount++;
                    }
                } finally {
                    zip.close();
                }
            } catch (Throwable t) {
                L.e("dress: zip listing failed: " + t);
                fileCount = 0;
            }
        }

        boolean needUpdate = havePack && clientVersion < DRESS_VERSION;

        JSONObject out = new JSONObject();
        out.put("needUpdate", needUpdate);
        JSONArray cdns = new JSONArray();
        JSONObject cdn = new JSONObject();
        cdn.put("base", true);
        cdn.put("cdnId", "local");
        cdn.put("cdnUrl", "http://127.0.0.1:18080");
        cdn.put("ratio", 1);
        cdn.put("url", "http://127.0.0.1:18080" + packPath());
        cdns.put(cdn);
        out.put("cdns", cdns);
        out.put("fileCount", fileCount);
        out.put("fileSize", bytes);
        out.put("hash", havePack ? PACK_MD5 : "");
        out.put("url", havePack ? "http://127.0.0.1:18080" + packPath() : "");
        out.put("version", havePack ? DRESS_VERSION
                : Math.max(1, (int) clientVersion));
        return out;
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
                        L.i("dress: pack unavailable: "
                                + t.getClass().getSimpleName());
                    }
                }
            }, "DressAssets");
            t.setDaemon(true);
            t.start();
        }
    }

    /** True once the pack file is present (downloads on first need). */
    static boolean ensurePack(StateStore store) {
        Boolean ok = packOk;
        if (ok != null) return ok.booleanValue();
        synchronized (LOCK) {
            if (packOk != null) return packOk.booleanValue();
            File f = packFile(store);
            if (f.exists() && f.length() >= PACK_MIN_BYTES) {
                packOk = Boolean.TRUE;
                L.i("dress: pack present (" + f.length() + " bytes)");
                return true;
            }
            IOException last = null;
            for (int i = 1; i <= PACK_ATTEMPTS && last == null; i++) {
                try {
                    L.i("dress: downloading decorate pack (attempt " + i + ")");
                    byte[] data = httpGet(PACK_URL,
                            PACK_CONNECT_TIMEOUT_MS, PACK_READ_TIMEOUT_MS);
                    if (data == null || data.length < PACK_MIN_BYTES) {
                        throw new IOException("pack too small / empty");
                    }
                    atomicallyWrite(f, data);
                    packOk = Boolean.TRUE;
                    L.i("dress: decorate pack stored (" + data.length + " B)");
                    return true;
                } catch (IOException e) {
                    last = e;
                    try {
                        Thread.sleep(i * 5000L);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                    }
                } catch (Exception e) {
                    last = new IOException(e.getMessage());
                }
            }
            packOk = Boolean.FALSE;
            return false;
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

    private static File packFile(StateStore store) {
        return new File(dir(store), PACK_NAME);
    }

    private static File dir(StateStore store) {
        return new File(store.baseDir(), "dress");
    }
}
