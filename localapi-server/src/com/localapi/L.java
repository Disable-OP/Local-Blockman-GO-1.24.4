package com.localapi;

/**
 * Tiny logging facade: android.util.Log on device, stdout on the host JVM test rig.
 */
public final class L {

    private static boolean host;

    static {
        try {
            Class.forName("android.util.Log");
        } catch (Throwable t) {
            host = true;
        }
    }

    private L() {}

    public static void i(String msg) {
        if (host) {
            System.out.println("[LocalAPI] " + msg);
        } else {
            try {
                android.util.Log.i("LocalAPI", msg);
            } catch (Throwable ignore) {
                System.out.println("[LocalAPI] " + msg);
            }
        }
    }

    public static void e(String msg) {
        if (host) {
            System.err.println("[LocalAPI] " + msg);
        } else {
            try {
                android.util.Log.e("LocalAPI", msg);
            } catch (Throwable ignore) {
                System.err.println("[LocalAPI] " + msg);
            }
        }
    }
    /** GameServer stdout/stderr pump — tagged separately so it is filterable. */
    public static void gs(String msg) {
        if (host) {
            System.out.println("[GS] " + msg);
        } else {
            try {
                android.util.Log.i("GS", msg);
            } catch (Throwable ignore) {
                System.out.println("[GS] " + msg);
            }
        }
    }
}
