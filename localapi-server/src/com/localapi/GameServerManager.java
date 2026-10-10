package com.localapi;

import android.content.Context;
import android.os.Environment;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.util.zip.GZIPInputStream;

import org.json.JSONObject;

/**
 * Stages and runs the on-device GameServer (arm64 C++ binary, engine 10068).
 *
 * Layout on the device:
 *   filesDir/gameserver-bundle/          — runtime bundle (tar.gz from the
 *                                          localapi-assets release): resource.cfg,
 *                                          engineVersion.json, ScriptSetting.csv,
 *                                          GameSetting/, Setting/, recipe/, bt/,
 *                                          scripts/BedWar/ (merged plugin tree),
 *                                          maps/g1008/m1008_2/
 *   nativeLibraryDir/libgameserver.so    — the binary, packaged as jniLibs so it
 *                                          lands in an executable app dir
 *   /storage/emulated/<runtime-id>/SandBoxOL/BlockMan/config/  — the client's own
 *                                          config dir (client.log lives here);
 *                                          the GameServer's logdir is set there
 *                                          too, so the engine writes server.log
 *                                          right next to it. The storage id is
 *                                          resolved at RUNTIME (never hardcoded).
 *
 * The server reads its RoomGameConfig from ./serverConfig.json in its CWD
 * (dev/server/src/main.cpp: argc==1 -> getTestRGConfig("serverConfig.json")).
 */
public final class GameServerManager {
    /** RakNet listen port the engine will be pointed at via Dispatch.gaddr. */
    public static final int GAME_PORT = 31108;

    private static final String BUNDLE_DIR = "gameserver-bundle";
    private static final String STAGE_VERSION_FILE = "stage-version";
    private static final String STAGE_VERSION = "g1008-b2"; // bump to restage

    /** Engine-faithful runtime layout: the server CWD is <bundle>/server
     *  (resource.cfg reads ../client/), while GameServerManager's staging
     *  dir stays the bundle root. The staged tarball is itself rooted at
     *  bundle/ (build_runtime_bundle.py layout), so the real root may be
     *  <staging>/bundle — detect instead of assuming (run 210 lesson: the
     *  server never found resource.cfg one level short). */
    private static File bundleRoot() {
        File nested = new File(sBundleDir, "bundle");
        return new File(nested, "server").isDirectory() ? nested : sBundleDir;
    }

    private static File serverDir() {
        return new File(bundleRoot(), "server");
    }

    private static final Object LOCK = new Object();
    private static Process sProcess;
    private static File sBundleDir;
    private static File sLogDir;
    private static boolean sAttempted;

    private GameServerManager() {}

    /** Release base — same release the map/dress packs ride. */
    private static final String RELEASE_BASE = System.getProperty(
            "localapi.gsReleaseBase",
            "https://github.com/Disable-OP/Local-Blockman-GO-1.24.4"
                    + "/releases/download/localapi-assets");

    private static String releaseBase() {
        return RELEASE_BASE;
    }

    private static String bundleUrl() {
        return releaseBase() + "/gameserver-runtime-g1008.tar.gz";
    }

    private static String serverUrl() {
        return releaseBase() + "/libgameserver-arm64.so";
    }

    /**
     * Stage the runtime bundle + fetch the server binary into the bundle dir.
     * Best effort: any failure leaves the previous stage intact and only means
     * "no gameplay server this boot" — the map-phase behavior is untouched.
     */
    public static void ensure(Context context) {
        synchronized (LOCK) {
            if (sAttempted) return;
            sAttempted = true;
            try {
                File files = context.getFilesDir();
                sBundleDir = new File(files, BUNDLE_DIR);
                File marker = new File(sBundleDir, STAGE_VERSION_FILE);
                boolean needStage = !marker.exists()
                        || !STAGE_VERSION.equals(readText(marker));
                if (needStage) {
                    L.i("gs: staging runtime bundle ...");
                    File tar = download(bundleUrl(), "gameserver-runtime.tar.gz",
                            64 * 1024 * 1024);
                    untarGz(tar, sBundleDir);
                    writeText(marker, STAGE_VERSION);
                    L.i("gs: bundle staged at " + sBundleDir);
                }
                // The binary rides the APK as jniLibs (nativeLibraryDir). When
                // the APK does not carry it yet (older build), fall back to a
                // release download into the bundle dir.
                if (findBinary(context) == null) {
                    File dl = download(serverUrl(), "libgameserver.so",
                            80 * 1024 * 1024);
                    File dst = new File(sBundleDir, "libgameserver.so");
                    if (!dl.renameTo(dst)) {
                        copy(dl, dst);
                    }
                    // filesDir exec: allowed for legacy targetSdk apps only;
                    // chmod +x for good measure.
                    try {
                        Runtime.getRuntime().exec(
                                new String[]{"chmod", "755", dst.getAbsolutePath()})
                                .waitFor();
                    } catch (Throwable ignored) {}
                }
            } catch (Throwable t) {
                L.e("gs: ensure failed: " + t);
            }
        }
    }

    /** Launch the GameServer if the bundle + binary are ready. */
    public static void startIfPossible(Context context) {
        synchronized (LOCK) {
            try {
                if (isAlive()) return;
                File bin = findBinary(context);
                File cwd = serverDir();
                // NOTE: serverConfig.json is OWNED by this manager and is
                // (re)written below on every start — it must NOT be a
                // precondition (run 210: the old check required the file to
                // already exist, but only this method creates it -> the
                // server could never start). Only the binary and the
                // engine-faithful resource.cfg are real preconditions.
                File cfg = new File(cwd, "serverConfig.json");
                if (bin == null
                        || !new File(cwd, "resource.cfg").exists()) {
                    L.i("gs: not started (binary=" + (bin != null)
                            + " resource.cfg="
                            + new File(cwd, "resource.cfg").exists() + " cwd="
                            + cwd + ")");
                    return;
                }
                MonitorServer.start();
                sLogDir = resolveLogDir();
                writeServerConfig(cfg);
                ProcessBuilder pb = new ProcessBuilder(bin.getAbsolutePath());
                pb.directory(cwd);          // CWD: resource.cfg lives here
                pb.redirectErrorStream(true);
                sProcess = pb.start();
                final Process p = sProcess;
                Thread pump = new Thread(() -> {
                    try {
                        java.io.BufferedReader r = new java.io.BufferedReader(
                                new java.io.InputStreamReader(p.getInputStream()));
                        String line;
                        while ((line = r.readLine()) != null) {
                            L.gs(line);
                        }
                    } catch (Throwable ignored) {}
                }, "LocalApiGsPump");
                pump.setDaemon(true);
                pump.start();
                L.i("gs: launched pid=" + pid() + " logdir=" + sLogDir
                        + " port=" + GAME_PORT);
            } catch (Throwable t) {
                L.e("gs: start failed: " + t);
            }
        }
    }

    public static boolean isAlive() {
        Process p = sProcess;
        return p != null && p.isAlive();
    }

    /** Dispatch.gaddr target while the gameplay server runs. */
    public static String gameAddr() {
        return isAlive() ? ("127.0.0.1:" + GAME_PORT) : null;
    }

    /** Push this user's room attributes after a dispatch was served. */
    public static void notifyDispatch(long uid, String requestId, int sex,
                                      String name, int vip, String country) {
        if (isAlive() && MonitorServer.gameConnected()) {
            MonitorServer.pushUserAttr(uid, requestId, sex, name, vip, country);
        }
    }

    // ------------------------------------------------------------------

    /**
     * The client writes client.log into SandBoxOL/BlockMan/config on the
     * FIRST emulated storage root. The <id> differs per device/profile, so it
     * is resolved from the OS at runtime — never hardcoded.
     */
    private static File resolveLogDir() {
        try {
            File ext = Environment.getExternalStorageDirectory();
            if (ext != null) {
                File dir = new File(new File(new File(ext, "SandBoxOL"), "BlockMan"), "config");
                if (dir.mkdirs() || dir.isDirectory()) {
                    if (dir.canWrite()) return dir;
                }
            }
        } catch (Throwable t) {
            L.e("gs: external storage resolve failed: " + t);
        }
        // Fallback: the app's own external files dir (same filesystem family,
        // still beside nothing — but keeps the server runnable on locked-down
        // storage). The user-visible placement rule prefers the SandBoxOL path
        // above and only lands here on permission failures.
        try {
            File[] outs = ContextCompatExternalFiles();
            if (outs != null) {
                for (File o : outs) {
                    if (o == null) continue;
                    File dir = new File(new File(o, "SandBoxOL"), "config");
                    if (dir.mkdirs() || dir.isDirectory()) return dir;
                }
            }
        } catch (Throwable ignored) {}
        return new File(String.valueOf(sBundleDir), "logs");
    }

    private static File[] ContextCompatExternalFiles() {
        // no androidx dependency here: query through the environment
        File ext = Environment.getExternalStorageDirectory();
        if (ext != null) {
            File alt = new File(ext, "Android/data/com.sandboxol.blockmango/files");
            File dir = new File(new File(alt, "SandBoxOL"), "config");
            if (dir.mkdirs() || dir.isDirectory()) return new File[]{alt};
        }
        return null;
    }

    /**
     * RoomGameConfig JSON — keys exactly as getRGConfigFromCmdline/getTestRGConfig
     * reads them (dev/server/src/main.cpp).
     */
    private static void writeServerConfig(File cfg) throws Exception {
        JSONObject o = new JSONObject();
        o.put("ip", "127.0.0.1");
        o.put("port", GAME_PORT);
        o.put("logdir", sLogDir.getAbsolutePath() + "/");
        o.put("scriptdir", new File(new File(serverDir(), "scripts"), "BedWar")
                .getAbsolutePath());
        o.put("mapdir", new File(new File(new File(serverDir(), "maps"), "g1008"),
                "m1008_2").getAbsolutePath() + "/");
        o.put("id", "g1008");
        o.put("mapid", "m1008_2");
        o.put("name", "BedWar");
        o.put("gtype", "g1008");
        o.put("monitoraddr", "127.0.0.1:" + MonitorServer.PORT);
        o.put("maxplayer", 8);
        o.put("isDebug", false);
        o.put("secret", "pq0194mxoqfh48L362G6R09T737E273X");
        o.put("isChina", false);
        o.put("heartbeatInterval", 5);
        o.put("userConf", "");
        o.put("propAddr", "");
        o.put("rankAddr", "");
        o.put("rewardAddr", "");
        o.put("blockymodsUrl", "");
        o.put("blockymodsRewardAddr", "");
        o.put("blockmanUrl", "");
        o.put("gameRankParams", "");
        o.put("isGameParty", false);
        o.put("private", false);
        o.put("maxWatch", 0);
        JSONObject db = new JSONObject();
        db.put("addr", ""); db.put("user", ""); db.put("password", "");
        db.put("dbname", "");
        o.put("dbconfig", db);
        JSONObject redis = new JSONObject();
        redis.put("ip", ""); redis.put("password", ""); redis.put("port", 0);
        o.put("redisConfig", redis);
        o.put("gameDataServiceAddr", "");
        o.put("gameDataServiceSecondAddr", "");
        FileOutputStream out = new FileOutputStream(cfg);
        out.write(o.toString().getBytes("UTF-8"));
        out.close();
        L.i("gs: config written -> " + cfg);
    }

    private static File findBinary(Context context) {
        try {
            String nd = context.getApplicationInfo().nativeLibraryDir;
            if (nd != null) {
                File f = new File(nd, "libgameserver.so");
                if (f.exists() && f.canExecute()) return f;
                if (f.exists()) return f;
            }
        } catch (Throwable t) {
            L.e("gs: nativeLibraryDir probe failed: " + t);
        }
        File f = new File(sBundleDir, "libgameserver.so");
        return f.exists() ? f : null;
    }

    private static File download(String url, String name, long maxBytes) throws Exception {
        File dst = new File(String.valueOf(sBundleDir), name);
        File tmp = new File(String.valueOf(sBundleDir), name + ".tmp");
        sBundleDir.mkdirs();
        L.i("gs: downloading " + url);
        java.net.HttpURLConnection c = (java.net.HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(60000);
        c.setInstanceFollowRedirects(true);
        InputStream in = new BufferedInputStream(c.getInputStream());
        OutputStream out = new FileOutputStream(tmp);
        long total = 0;
        byte[] buf = new byte[65536];
        int n;
        while ((n = in.read(buf)) > 0) {
            total += n;
            if (total > maxBytes) throw new Exception("download too large: " + url);
            out.write(buf, 0, n);
        }
        out.close();
        in.close();
        if (!tmp.renameTo(dst)) copy(tmp, dst);
        L.i("gs: downloaded " + dst.getName() + " (" + dst.length() + " bytes)");
        return dst;
    }

    /**
     * Minimal ustar reader (same approach as MapAssets.extractPack): extracts
     * regular files + dirs, skips pax/long-link metadata headers. The bundle
     * is a sha-pinned release asset so this is sufficient.
     */
    private static void untarGz(File tarGz, File dstDir) throws Exception {
        dstDir.mkdirs();
        GZIPInputStream in = new GZIPInputStream(new BufferedInputStream(
                new FileInputStream(tarGz)), 65536);
        byte[] hdr = new byte[512];
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
                new File(dstDir, name).mkdirs();
                skipFully(in, size);
            } else if (type == '0' || type == 0) { // regular file
                File out = new File(dstDir, name);
                if (!out.getCanonicalPath().startsWith(dstDir.getCanonicalPath())) {
                    skipFully(in, ((size + 511) / 512) * 512);
                    continue; // tar path traversal guard
                }
                if (out.getParentFile() != null) out.getParentFile().mkdirs();
                FileOutputStream fos = new FileOutputStream(out);
                long left = size;
                byte[] buf = new byte[65536];
                while (left > 0) {
                    int n = in.read(buf, 0, (int) Math.min(buf.length, left));
                    if (n < 0) throw new java.io.EOFException("truncated tar");
                    fos.write(buf, 0, n);
                    left -= n;
                }
                fos.close();
                long pad = (512 - (size % 512)) % 512;
                skipFully(in, pad);
            } else {
                skipFully(in, ((size + 511) / 512) * 512);
            }
        }
        in.close();
    }

    private static boolean readFully(InputStream in, byte[] b) throws Exception {
        int off = 0;
        while (off < b.length) {
            int n = in.read(b, off, b.length - off);
            if (n < 0) return off > 0;
            off += n;
        }
        return true;
    }

    private static void skipFully(InputStream in, long n) throws Exception {
        while (n > 0) {
            long skipped = in.skip(n);
            if (skipped <= 0) {
                if (in.read() < 0) return;
                skipped = 1;
            }
            n -= skipped;
        }
    }

    private static String cstr(byte[] b, int off, int len) {
        int end = off;
        while (end < off + len && end < b.length && b[end] != 0) end++;
        return new String(b, off, end - off).trim();
    }

    private static long octal(byte[] b, int off, int len) {
        long v = 0;
        boolean started = false;
        for (int i = off; i < off + len && i < b.length; i++) {
            byte c = b[i];
            if (c == ' ' || c == 0) {
                if (started) break;
                continue;
            }
            started = true;
            if (c >= '0' && c <= '7') v = (v << 3) + (c - '0');
            else break;
        }
        return v;
    }

    private static void copy(File src, File dst) throws Exception {
        FileInputStream in = new FileInputStream(src);
        FileOutputStream out = new FileOutputStream(dst);
        byte[] buf = new byte[65536];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        out.close();
        in.close();
    }

    private static String readText(File f) {
        try {
            byte[] b = new byte[(int) Math.min(f.length(), 4096)];
            FileInputStream in = new FileInputStream(f);
            int n = in.read(b);
            in.close();
            return new String(b, 0, Math.max(0, n), "UTF-8").trim();
        } catch (Exception e) {
            return "";
        }
    }

    private static void writeText(File f, String s) {
        try {
            f.getParentFile().mkdirs();
            FileOutputStream out = new FileOutputStream(f);
            out.write(s.getBytes("UTF-8"));
            out.close();
        } catch (Exception ignored) {}
    }

    private static long pid() {
        try {
            java.lang.reflect.Field f = Process.class.getDeclaredField("pid");
            f.setAccessible(true);
            return f.getInt(sProcess);
        } catch (Throwable t) {
            return -1;
        }
    }
}
