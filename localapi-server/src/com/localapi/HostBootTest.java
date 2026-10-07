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
 *   race    — (run 37569020063) the holder speaks junk on the FIRST
 *             connection and HTTP afterwards: probe #1 fails, the first
 *             bind loses, the post-loss probe must stand the loser down
 *             immediately (no 5 x 1s main-thread bind burn).
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
        } else if ("resurrect".equals(mode)) {
            // Cold boot succeeds, then the server is stopped UNDERNEATH the
            // process (as if NanoHTTPD died while the app kept running). The
            // persistent watchdog must notice and re-boot within a few cycles.
            LocalServer.start(dir, port);
            System.out.println("RESURRECT STARTED");
            Thread.sleep(2000);
            LocalHttpd h = LocalServer.currentServer();
            if (h != null) {
                h.stop();
                System.out.println("RESURRECT STOPPED");
            } else {
                System.out.println("RESURRECT NO-SERVER");
            }
            Thread.sleep(60000);
        } else if ("race".equals(mode)) {
            // Run 37569020063 bind race (pid 12672): the fast-path probe
            // sees a not-yet-HTTP holder (sibling mid-death), the first
            // bind LOSES, and the holder speaks HTTP by the time the
            // loser re-probes. LocalServer.start must stand down after
            // the FIRST lost bind instead of burning 5 x 1s binds on the
            // main thread. The holder answers junk on connection 1 and
            // real HTTP from connection 2 on — connection 1 is the
            // fast-path probe, connection 2 is the post-bind-loss probe
            // (a failed bind opens no connection), so the sequence is
            // deterministic.
            final ServerSocket holder = new ServerSocket();
            holder.bind(new InetSocketAddress("127.0.0.1", port), 64);
            holder.setSoTimeout(200);
            Thread speaker = new Thread(new Runnable() {
                @Override public void run() {
                    int connections = 0;
                    while (!holder.isClosed()) {
                        try {
                            Socket c = holder.accept();
                            connections++;
                            try {
                                if (connections == 1) {
                                    // probe #1: junk sibling (speaks no HTTP)
                                    c.close();
                                } else {
                                    c.getOutputStream().write(
                                            ("HTTP/1.0 200 OK\r\n"
                                                    + "Content-Length: 2\r\n\r\nok")
                                            .getBytes("UTF-8"));
                                    c.getOutputStream().flush();
                                    c.close();
                                }
                            } catch (Throwable ignore2) {
                                // best-effort canned responder
                            }
                        } catch (Throwable t) {
                            // accept timeout — keep holding
                        }
                    }
                }
            }, "race-holder");
            speaker.setDaemon(true);
            speaker.start();
            System.out.println("RACE HOLDER UP");
            long t0 = System.currentTimeMillis();
            LocalServer.start(dir, port);
            long elapsed = System.currentTimeMillis() - t0;
            System.out.println("RACE START RETURNED in " + elapsed + "ms");
            // The loser must have stood down WITHOUT binding: isRunning()
            // stays false (the canned holder keeps the port).
            System.out.println("RACE BOUND=" + LocalServer.isRunning());
            // Stay alive so the watchdog settles into EXTERNAL standby.
            Thread.sleep(30000);
        } else {
            System.err.println("unknown mode: " + mode);
            System.exit(2);
        }
    }

    private HostBootTest() {}
}
