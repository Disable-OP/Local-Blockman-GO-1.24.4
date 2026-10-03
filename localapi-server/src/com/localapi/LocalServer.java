package com.localapi;

import android.content.Context;

/**
 * Entry point for the embedded loopback API server.
 * Called once from App.onCreate (smali hook) before any activity can fire a request.
 * The server binds 127.0.0.1:18080 only — no traffic ever leaves the device.
 * Every failure is swallowed and logged: the game must boot even if the server fails.
 */
public final class LocalServer {

    public static final int PORT = 18080;
    private static LocalHttpd httpd;

    private LocalServer() {}

    public static void startIfNeeded(Context context) {
        if (httpd != null && httpd.isUp()) {
            return;
        }
        try {
            L.i("boot: starting local api on 127.0.0.1:" + PORT);
            StateStore store = new StateStore(context.getApplicationContext().getFilesDir());
            LocalHttpd server = new LocalHttpd(PORT, store);
            server.start(15000, true);
            httpd = server;
            L.i("boot: local api is UP on http://127.0.0.1:" + PORT
                    + " (users=" + store.userCount() + ")");
        } catch (Throwable t) {
            L.e("boot FAILED: " + t);
        }
    }

    public static boolean isRunning() {
        return httpd != null && httpd.wasStarted();
    }
}
