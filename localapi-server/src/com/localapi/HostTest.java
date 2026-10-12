package com.localapi;

import java.io.File;

/**
 * Host-JVM test rig ONLY (never shipped in the dex): boots the daemon with a
 * plain directory as the state root so scripts/test_server_host.py can drive
 * every endpoint with real HTTP before we ever touch an APK.
 */
public final class HostTest {

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("usage: HostTest <stateDir> <port>");
            System.exit(2);
        }
        // MULTI-GAME selftest (scripts/test_server_host.py): with
        // -Dlocalapi.gsSelftest=1, exercise GameServerManager's hosted-room
        // table / staged probe / per-game config / selectGame fallbacks
        // BEFORE the HTTP server boots; the suite greps the boot log for
        // GS-SELFTEST OK. Inert on device (the property is never set).
        if (System.getProperty("localapi.gsSelftest") != null) {
            GameServerManager.hostSelfTest(new File(args[0],
                    "gs-selftest-bundle"));
        }
        StateStore store = new StateStore(new File(args[0]));
        GameCatalog.ensure(store);
        GameCatalog.drift(store);
        Skins.ensure(store);
        MapAssets.ensure(store);   // gated by -Dlocalapi.mapPackUrl (hermetic
        DressRes.ensure(store);    // suites block it; REAL_PACK e2e allows it)
        LocalHttpd httpd = new LocalHttpd(Integer.parseInt(args[1]), store);
        httpd.start(5000, false);
        System.out.println("HOSTTEST READY");
    }

    private HostTest() {}
}
