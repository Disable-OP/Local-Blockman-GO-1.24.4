package com.localapi;

import android.content.Context;
import java.io.File;
import java.net.InetSocketAddress;
import java.net.Socket;

/**
 * Entry point for the embedded loopback API server.
 * Called once from App.onCreate (smali hook) before any activity can fire a request.
 * The server binds 127.0.0.1:18080 only — no traffic ever leaves the device.
 * Every failure is swallowed and logged: the game must boot even if the server fails.
 *
 * Boot resilience (v0.5.9, evidence: v0.5.8 redroid diagnostics): the app was
 * relaunched while a first instance was still alive and the second process
 * failed 5 bind attempts (EADDRINUSE) then gave up forever. Loopback traffic
 * was still served by the first process — but had that process died later,
 * the second would have had NO server and every API call would black-hole.
 * Fix: a lightweight daemon watchdog. While this process has no server:
 *   - probe 127.0.0.1:18080 with a real HTTP request; if a genuine LocalAPI
 *     server answers, stand by quietly (another process of ours is serving);
 *   - if nothing answers (holder died, or a junk socket holds the port),
 *     attempt a full boot so this process takes the port over.
 * State is JSON on disk in the shared app files dir, so a takeover serves the
 * exact same state — accounts, wallets, tokens all survive the handover.
 */
public final class LocalServer {

    public static final int PORT = 18080;
    private static volatile LocalHttpd httpd;
    /** Test hook: the host rig disables the watchdog to keep tests deterministic. */
    static volatile boolean watchdogEnabled = true;
    /** Watchdog retry cadence (ms). */
    static final long WATCHDOG_INTERVAL_MS = 5000L;

    private LocalServer() {}

    public static void startIfNeeded(Context context) {
        start(context.getApplicationContext().getFilesDir(), PORT);
    }

    /**
     * Shared boot core (Context-free so the host JVM rig can drive it).
     * Fast path: a few quick bind attempts for the common cold-start case.
     * Then the daemon watchdog takes over (unless disabled by the test rig).
     */
    static void start(final File filesDir, final int port) {
        for (int attempt = 0; attempt < 5 && !isUp(); attempt++) {
            bootOnce(filesDir, port, attempt > 0 ? " (retry " + attempt + ")" : "");
            if (!isUp()) {
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
        if (isUp() || !watchdogEnabled) {
            return;
        }
        Thread wd = new Thread(new Runnable() {
            @Override public void run() {
                int quiet = 0;
                boolean announced = false;
                while (watchdogEnabled && !isUp()) {
                    boolean served = probeServing(port);
                    if (served) {
                        // A genuine LocalAPI instance owns the port right now.
                        // Stand by silently; take over the moment it disappears.
                        if (!announced) {
                            L.i("watchdog: another LocalAPI instance is serving 127.0.0.1:"
                                    + port + " — standing by");
                            announced = true;
                        }
                        quiet++;
                    } else {
                        if (announced || quiet > 0) {
                            L.i("watchdog: no server answering on 127.0.0.1:" + port
                                    + " — attempting takeover boot");
                        }
                        announced = false;
                        bootOnce(filesDir, port, " (watchdog)");
                        quiet = 0;
                    }
                    try {
                        Thread.sleep(WATCHDOG_INTERVAL_MS);
                    } catch (InterruptedException ie) {
                        return;
                    }
                }
            }
        }, "LocalApiWatchdog");
        wd.setDaemon(true);
        wd.start();
    }

    /** One boot attempt: build state, bind, start serving. Returns when up (or failed). */
    private static void bootOnce(File filesDir, int port, String tag) {
        try {
            L.i("boot: starting local api on 127.0.0.1:" + port + tag);
            StateStore store = new StateStore(filesDir);
            GameCatalog.ensure(store);   // generate catalog once, then it's plain state
            GameCatalog.drift(store);    // evolve online counts across boots
            LocalHttpd server = new LocalHttpd(port, store);
            server.start(15000, true);
            httpd = server;
            L.i("boot: local api is UP on http://127.0.0.1:" + port
                    + " (users=" + store.userCount() + ")");
        } catch (Throwable t) {
            L.e("boot" + tag + " failed: " + t);
        }
    }

    /**
     * True only if a real HTTP server answers on the port. A bare TCP connect is
     * NOT enough: a foreign/junk socket that never speaks HTTP must not be
     * mistaken for a healthy instance (and would block our bind anyway).
     */
    static boolean probeServing(int port) {
        Socket s = new Socket();
        try {
            s.connect(new InetSocketAddress("127.0.0.1", port), 500);
            s.setSoTimeout(500);
            java.io.OutputStream out = s.getOutputStream();
            out.write("GET /health HTTP/1.0\r\n\r\n".getBytes("UTF-8"));
            out.flush();
            byte[] buf = new byte[16];
            int n = s.getInputStream().read(buf);
            return n > 0 && new String(buf, 0, n, "UTF-8").startsWith("HTTP/");
        } catch (Throwable t) {
            return false;
        } finally {
            try { s.close(); } catch (Throwable ignore) {}
        }
    }

    public static boolean isRunning() {
        return httpd != null && httpd.isUp();
    }

    private static boolean isUp() {
        LocalHttpd h = httpd;
        return h != null && h.isUp();
    }
}
