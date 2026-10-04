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
 * Boot resilience (v0.5.9, evidence: v0.5.8 redroid diagnostics): a second
 * app process booted while the first was alive, failed 5 binds (EADDRINUSE)
 * and gave up forever. Loopback traffic was still served by the first
 * process — but had it died later, the second would have had NO server and
 * every API call would black-hole. Fix: a persistent daemon watchdog that
 * runs for the process's whole life and keeps the state machine healthy:
 *   UP        — this process serves the port (quiet)
 *   EXTERNAL  — a genuine LocalAPI holder answers HTTP — stand by
 *   NO SERVER — nothing answers: full takeover boot
 * State is JSON on disk in the shared app files dir, so a takeover serves
 * the exact same state — accounts, wallets, tokens all survive the handover.
 */
public final class LocalServer {

    public static final int PORT = 18080;
    private static volatile LocalHttpd httpd;
    /** Test hook: the host rig disables the watchdog to keep tests deterministic. */
    static volatile boolean watchdogEnabled = true;
    /** One watchdog per process, no matter how often start() is called. */
    private static volatile boolean watchdogRunning = false;
    /** Watchdog retry cadence (ms). */
    static final long WATCHDOG_INTERVAL_MS = 5000L;

    private LocalServer() {}

    public static void startIfNeeded(Context context) {
        start(context.getApplicationContext().getFilesDir(), PORT);
    }

    /**
     * Shared boot core (Context-free so the host JVM rig can drive it).
     * Fast path: a synchronous bind for the common cold-start case (skipped
     * entirely when a genuine holder already answers — secondary app
     * processes start instantly instead of failing 5 binds). The persistent
     * watchdog takes over from there.
     */
    static void start(final File filesDir, final int port) {
        if (probeServing(port)) {
            L.i("boot: another LocalAPI instance already serving 127.0.0.1:" + port);
            startWatchdog(filesDir, port);
            return;
        }
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
        startWatchdog(filesDir, port);
    }

    private static void startWatchdog(final File filesDir, final int port) {
        if (!watchdogEnabled || watchdogRunning) {
            return;
        }
        watchdogRunning = true;
        Thread wd = new Thread(new Runnable() {
            @Override public void run() {
                // Persistent self-healing loop (never exits while enabled).
                // Covers the v0.5.8 evidence (lost bind race) AND the rarer
                // in-process server death while the app process stays alive.
                final int UP = 0, EXTERNAL = 1, NOSERVER = 2;
                int state = -1;
                while (watchdogEnabled && !Thread.currentThread().isInterrupted()) {
                    int s;
                    if (isUp()) {
                        s = UP;
                    } else if (probeServing(port)) {
                        s = EXTERNAL;
                    } else {
                        s = NOSERVER;
                    }
                    if (s != state) {
                        if (s == EXTERNAL) {
                            L.i("watchdog: another LocalAPI instance is serving 127.0.0.1:"
                                    + port + " — standing by");
                        } else if (s == NOSERVER) {
                            L.i("watchdog: no server answering on 127.0.0.1:" + port
                                    + " — booting");
                        }
                        state = s;
                    }
                    if (s == NOSERVER) {
                        bootOnce(filesDir, port, " (watchdog)");
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

    /** Host-rig only: reach the live server so a test can stop it beneath us. */
    static LocalHttpd currentServer() {
        return httpd;
    }

    public static boolean isRunning() {
        return httpd != null && httpd.isUp();
    }

    private static boolean isUp() {
        LocalHttpd h = httpd;
        return h != null && h.isUp();
    }
}
