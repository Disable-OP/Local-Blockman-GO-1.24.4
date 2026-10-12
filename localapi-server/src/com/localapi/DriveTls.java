package com.localapi;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.security.KeyStore;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLServerSocketFactory;

/**
 * The pristine-client drive TLS listener (delta-13 architecture).
 *
 * <p>The OFFICIAL 2.8.2 client builds its metadata base from
 * {@code https://d32gv25kv9q34j.cloudfront.net} — a dead host that the drive
 * redirects to THIS holder via /etc/hosts. The redirect maps hostname → IP
 * only, NOT the port: the client still speaks TLS on 443. This class boots a
 * second {@link LocalHttpd} (the exact same routing table and state) behind
 * an SSLServerSocket when — and only when — a drive keystore is staged.
 *
 * <p>Contract (all under {@code <filesDir>/drive/}):
 * <ul>
 *   <li>{@code server.p12} — PKCS#12 keystore with the leaf chain built by
 *       scripts/gen_drive_ca.py (leaf SANs cover every redirected host).
 *       Absent → the listener does not boot and the feature is inert (the
 *       1.24.4/282 patched clients never need TLS: they talk http://127.0.0.1
 *       on 18080 directly).</li>
 *   <li>{@code server.pass} — optional keystore password (UTF-8, trimmed);
 *       default "drive".</li>
 *   <li>{@code tls.port} — optional listen port; default 443 (root binds it
 *       on-device; host rigs stage e.g. 25xxx and never need privileges).</li>
 *   <li>{@code tls.active} — written on a successful boot with the port inside;
 *       an existing marker with a live TCP answer makes a re-boot a no-op
 *       (bootOnce runs on every watchdog wake).</li>
 * </ul>
 *
 * <p>Failure policy: ANY problem (bad keystore, bind lost, no JSSE) is logged
 * through L.e and swallowed — the drive degrades to plain http on 18080 and
 * must never destabilise the holder boot path. Plain JVM only (no android.*
 * imports), so HostTest/HostBootTest exercise the identical code path the
 * device runs, and the whole thing ships in classes6.dex harmlessly.
 */
public final class DriveTls {

    /** Sub-directory of the holder state root holding the drive material. */
    public static final String DIR = "drive";
    /** PKCS#12 keystore file name inside {@link #DIR}. */
    public static final String P12 = "server.p12";
    /** Optional keystore password file inside {@link #DIR}. */
    public static final String PASS_FILE = "server.pass";
    /** Optional listen-port file inside {@link #DIR}. */
    public static final String PORT_FILE = "tls.port";
    /** Written on success; presence + live port = already booted. */
    public static final String ACTIVE_FILE = "tls.active";
    /** Listen port when {@link #PORT_FILE} is absent. */
    public static final int DEFAULT_PORT = 443;
    /** Keystore password when {@link #PASS_FILE} is absent. */
    public static final String DEFAULT_PASS = "drive";

    private static volatile boolean bootedHere;

    private DriveTls() {}

    /**
     * Boots the TLS listener when {@code <stateDir>/drive/server.p12} exists.
     * Idempotent; never throws. Call after the plain-http holder is up.
     */
    public static void maybeStart(final File stateDir, final StateStore store) {
        try {
            if (bootedHere) {
                return;
            }
            final File dir = new File(stateDir, DIR);
            final File p12 = new File(dir, P12);
            if (!p12.isFile()) {
                // The normal case for every non-drive boot: stay silent at
                // info level (the 696-test suite and production boots must
                // not grow TLS noise), one debug-ish line is enough.
                L.i("drive-tls: no " + DIR + "/" + P12 + " — TLS listener off");
                return;
            }
            final int port = readPort(dir);
            if (alreadyServing(dir, port)) {
                L.i("drive-tls: already serving 127.0.0.1:" + port
                        + " — skipping");
                bootedHere = true;
                return;
            }
            final SSLServerSocketFactory factory = factory(p12, readPass(dir));
            final LocalHttpd tls = new LocalHttpd(port, store);
            tls.makeSecure(factory, null);
            tls.start(15000, true);
            bootedHere = true;
            final File active = new File(dir, ACTIVE_FILE);
            java.io.FileWriter w = new java.io.FileWriter(active);
            try {
                w.write(String.valueOf(port));
            } finally {
                w.close();
            }
            L.i("drive-tls: serving https://127.0.0.1:" + port
                    + " (pristine-client drive, metadata-base SANs)");
        } catch (Throwable t) {
            bootedHere = false;
            L.e("drive-tls boot failed (drive continues on plain http): " + t);
        }
    }

    /** Listen port: {@code tls.port} when parseable, else {@link #DEFAULT_PORT}. */
    static int readPort(final File dir) {
        final File f = new File(dir, PORT_FILE);
        if (f.isFile()) {
            try {
                final String s = new String(readAll(f), "UTF-8").trim();
                if (!s.isEmpty()) {
                    return Integer.parseInt(s);
                }
            } catch (Exception ignore) {
                // fall through to the default
            }
        }
        return DEFAULT_PORT;
    }

    /** Keystore password: {@code server.pass} when present, else the default. */
    static char[] readPass(final File dir) {
        final File f = new File(dir, PASS_FILE);
        if (f.isFile()) {
            try {
                return new String(readAll(f), "UTF-8").trim().toCharArray();
            } catch (Exception ignore) {
                // fall through to the default
            }
        }
        return DEFAULT_PASS.toCharArray();
    }

    /**
     * Boot idempotence: the {@link #ACTIVE_FILE} marker plus a live TCP answer
     * on the port. The marker alone would lie after a process death; the TCP
     * connect makes the pair honest.
     */
    private static boolean alreadyServing(final File dir, final int port) {
        if (!new File(dir, ACTIVE_FILE).isFile()) {
            return false;
        }
        Socket s = new Socket();
        try {
            s.connect(new InetSocketAddress("127.0.0.1", port), 500);
            return true;
        } catch (Exception e) {
            return false;
        } finally {
            try {
                s.close();
            } catch (Exception ignore) {
                // nothing to salvage
            }
        }
    }

    /** SSLServerSocketFactory from a PKCS#12 keystore (JSSE, plain JVM). */
    private static SSLServerSocketFactory factory(final File p12, final char[] pass)
            throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        InputStream in = new FileInputStream(p12);
        try {
            ks.load(in, pass);
        } finally {
            in.close();
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(ks, pass);
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(kmf.getKeyManagers(), null, null);
        return ctx.getServerSocketFactory();
    }

    private static byte[] readAll(final File f) throws Exception {
        InputStream in = new FileInputStream(f);
        try {
            java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
            return out.toByteArray();
        } finally {
            in.close();
        }
    }
}
