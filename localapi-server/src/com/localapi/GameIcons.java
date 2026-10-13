package com.localapi;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.zip.GZIPInputStream;

/**
 * GAME ICONS: the REAL official game art for the hosted 10078 rooms, packed
 * as one seed archive inside the APK.
 *
 * SOURCE (session 86): the user-supplied CDN dump (sandboxPATHS bucket list)
 * exposes the official July-2020 icon-catalog batch — sequential per-game
 * uploads `sandbox/games/images/g<gid>-<millis>.webp` (g1001..g1058, each a
 * 326x326 square) plus g1061/g1062's own 700x700 .png uploads. Harvested
 * from https://staticgs.sandboxol.com by scripts/harvest_game_icons.py
 * (provenance: scripts/gameicons_manifest.json — source key, sha256, size
 * per game).
 *
 * PIPELINE:
 *   assets/localapi/gameicons.tar.gz (the APK seed, 21 PNGs)
 *     -> LocalServer.startIfNeeded copies it to <files>/localapi/
 *     -> GameIcons.ensureExtracted unpacks it to <files>/localapi/gameicons/<gid>.png
 *     -> GameCatalog.ensure rewrites every hosted game's gameCoverPic to
 *        http://127.0.0.1:18080/localapi/games/icons/<gid>.png (idempotent,
 *        only when the icon file actually exists)
 *     -> LocalHttpd streams the bytes (GET /localapi/games/icons/<gid>.png,
 *        GAMEICON log tag) — served BEFORE the Retrofit routing, same layer
 *        as the skin icons.
 *
 * The 2.8.2 hall renders gameCoverPic on its game cards; without this every
 * card falls back to the client's gray placeholder.
 */
public final class GameIcons {

    private static final Object LOCK = new Object();
    private static boolean extracted;

    private GameIcons() {}

    // ------------------------------------------------------------- install

    /**
     * Device boot path (LocalServer.startIfNeeded): copy the APK seed asset
     * into the files dir (refresh when the asset size changes — a newer APK
     * ships a newer pack), then extract. Best effort: a missing asset only
     * means the catalog keeps empty cover pics.
     */
    static void install(android.content.Context app, File filesDir) {
        try {
            File localapi = new File(filesDir, "localapi");
            localapi.mkdirs();
            File dst = new File(localapi, packName());
            java.io.InputStream in = app.getAssets().open(assetPath());
            try {
                java.io.ByteArrayOutputStream bos =
                        new java.io.ByteArrayOutputStream();
                byte[] buf = new byte[65536];
                int n;
                while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
                byte[] data = bos.toByteArray();
                // refresh when the APK's pack differs (size is the stamp the
                // seed assets use; the pack is deterministic so size+content
                // move together)
                if (!dst.exists() || dst.length() != data.length) {
                    atomicallyWrite(dst, data);
                    L.i("gameicons: seed pack staged (" + data.length + " B)");
                }
            } finally {
                in.close();
            }
        } catch (Throwable t) {
            L.i("gameicons: no seed asset in this APK (" + t + ")");
        }
        ensureExtracted(filesDir);
    }

    /**
     * Extract <filesDir>/localapi/gameicons.tar.gz -> <filesDir>/localapi/
     * gameicons/<gid>.png. Idempotent (size-match skip per entry); safe on
     * the host rig (the suite drops the pack file in place — no Context).
     */
    public static void ensureExtracted(File filesDir) {
        synchronized (LOCK) {
            if (extracted) return;
            File pack = new File(new File(filesDir, "localapi"), packName());
            if (!pack.exists() || pack.length() < 1024) return;
            File dir = iconDir(filesDir);
            dir.mkdirs();
            try {
                int n = extractPack(pack, dir);
                extracted = n > 0;
                L.i("gameicons: pack extracted (" + n + " icons, "
                        + dir.list().length + " files)");
            } catch (Throwable t) {
                L.e("gameicons: pack extract failed: " + t);
            }
        }
    }

    // -------------------------------------------------------------- queries

    /** The icon dir under a files dir (suite + route + catalog share it). */
    public static File iconDir(File filesDir) {
        return new File(new File(filesDir, "localapi"), "gameicons");
    }

    private static String packName() {
        return "gameicons.tar.gz";
    }

    private static String assetPath() {
        return "localapi/" + packName();
    }

    /** Icon bytes for one game id ("g1008" or "1008"), or null. */
    public static byte[] bytes(StateStore store, String gid) {
        File f = iconFile(store, gid);
        if (f == null || !f.exists()) return null;
        try {
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
        } catch (Throwable t) {
            return null;
        }
    }

    /** True when the local icon exists for this game id. */
    public static boolean has(StateStore store, String gid) {
        File f = iconFile(store, gid);
        return f != null && f.exists();
    }

    /**
     * The local streaming URL for one game's icon — the value GameCatalog
     * writes into gameCoverPic. Callers guard with has() first.
     */
    public static String localUrl(String gid) {
        return Handlers.LOCAL_BASE_URL + "/localapi/games/icons/" + gid + ".png";
    }

    /** Resolve the icon file for "g1008" / "1008" / "g1008.png" forms. */
    static File iconFile(StateStore store, String gid) {
        if (gid == null || gid.isEmpty()) return null;
        String norm = gid.replaceAll("\\.[a-zA-Z]+$", "");
        if (!norm.startsWith("g") && norm.matches("[0-9]+")) norm = "g" + norm;
        if (!norm.matches("g[0-9]+")) return null;
        // store.baseDir() IS the <files>/localapi directory (the same dir
        // LocalServer copies the seed pack into) — gameicons hangs under it.
        return new File(new File(store.baseDir(), "gameicons"), norm + ".png");
    }

    // ----------------------------------------------------------- tar reader

    /**
     * Minimal USTAR reader (the Skins.extractPack recipe): walks 512-byte
     * headers, copies regular-file payloads into <dir>/<name>. Returns the
     * number of entries (re)extracted.
     */
    private static int extractPack(File pack, File dir) throws Exception {
        int count = 0;
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
                File out = new File(dir, new File(name).getName());
                boolean regular = type == '0' || type == 0;
                boolean need = regular
                        && (!out.exists() || out.length() != size);
                if (need) {
                    FileOutputStream fos = new FileOutputStream(out);
                    copyExactly(gz, fos, size);
                    fos.close();
                    count++;
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
        return count;
    }

    // ------------------------------------------------------------- plumbing

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
