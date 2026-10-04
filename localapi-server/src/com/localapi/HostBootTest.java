package com.localapi;

import java.io.File;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;

/**
 * Host-JVM test rig ONLY (never shipped in the dex): drives the
 * LocalServer boot-resilience path (fast-path + watchdog takeover) that
 * HostTest bypasses (it boots LocalHttpd directly).
 *
 * Modes:
 *   blocked — binds the port with a junk holder socket (accepts, speaks no
 *             HTTP, closes immediately) for 9 seconds, starts LocalServer
 *             beside it, then releases the holder. The watchdog must take
 *             the port over; scripts/test_server_host.py polls HTTP to prove it.
 *   standby — starts LocalServer against an ALREADY-SERVING real instance
 *             (the rig's main HostTest server). The fast path must fail
 *             quietly, the watchdog must detect genuine HTTP and stand by
 *             without disturbing the holder.
 */
public final class HostBootTest {

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            System.err.println("usage: HostBootTest <stateDir> <port> <blocked|standby>");
            System.exit(2);
        }
        final File dir = new File(args[0]);
        final int port = Integer.parseInt(args[1]);
        final String mode = args[2];

        if ("blocked".equals(mode)) {
            final ServerSocket holder = new ServerSocket();
            holder.bind(new InetSocketAddress("127.0.0.1", port), 64);
            holder.setSoTimeout(200);
            System.out.println("HOLDER UP");
            Thread booter = new Thread(new Runnable() {
                @Override public void run() { LocalServer.start(dir, port); }
            }, "booter");
            booter.setDaemon(true);
            booter.start();
            long end = System.currentTimeMillis() + 9000;
            while (System.currentTimeMillis() < end) {
                try {
                    Socket junk = holder.accept();
                    junk.close(); // junk holder: accepts, speaks no HTTP
                } catch (SocketTimeoutException ste) {
                    // keep holding
                }
            }
            holder.close();
            System.out.println("HOLDER RELEASED");
            // Watchdog must take over within a few cycles; stay alive for the rig.
            Thread.sleep(120000);
        } else if ("standby".equals(mode)) {
            System.out.println("STANDBY START");
            LocalServer.start(dir, port); // fast path fails (holder); watchdog stands by
            System.out.println("STANDBY WATCHDOG RUNNING");
            Thread.sleep(30000);
        } else {
            System.err.println("unknown mode: " + mode);
            System.exit(2);
        }
    }

    private HostBootTest() {}
}
