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
