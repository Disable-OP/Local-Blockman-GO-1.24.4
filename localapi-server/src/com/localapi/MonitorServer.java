package com.localapi;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

import org.json.JSONObject;

/**
 * Loopback stand-in for the production ROOM MONITOR service.
 *
 * The real GameServer is spawned by the deployer and talks to a monitor over
 * TCP with a tiny framed-JSON protocol (framing: [i32 len][i32 type][json],
 * where len = 4 + payload size). Message ids (from dev/server/src/Network/
 * RoomClient.cpp):
 *
 *   G2R_CONNECT 1, G2R_DISCONNECT 3, G2R_HEARTBEAT 4, G2R_GAME_STATUS 150,
 *   G2R_USER_IN 151, G2R_USER_OUT 152, G2R_SYNC_USERS 155,
 *   G2R_USER_MANOR_SOLD 156, G2R_REPORT_FRAME_TIME 161
 *   R2G_CONNECT_REPLY 2, R2G_USER_ATTR 154, R2G_USER_MANOR_RELEASE 157,
 *   R2G_BROADCAST_MESSAGE 158, R2G_SELECTABLE_ACTION_INFO 159,
 *   R2G_KICK_USER_OUT 160
 *
 * Local lifecycle: the GameServer connects at boot and sends G2R_CONNECT;
 * we answer R2G_CONNECT_REPLY. When the client's engine asks the localapi
 * for a dispatch, the dispatch handler calls pushUserAttr(...) with the SAME
 * requestId the client received — that satisfies the login gate in
 * C2SInitPacketHandles (attrInfo.requestId == m_dispatchRequestId).
 */
public final class MonitorServer {
    public static final int PORT = 18081;

    // G2R (game server -> room/monitor)
    private static final int G2R_CONNECT = 1;
    private static final int G2R_HEARTBEAT = 4;
    private static final int G2R_GAME_STATUS = 150;
    private static final int G2R_USER_IN = 151;
    private static final int G2R_USER_OUT = 152;
    // R2G (room/monitor -> game server)
    private static final int R2G_CONNECT_REPLY = 2;
    private static final int R2G_USER_ATTR = 154;

    /** Synthetic robot platform uids start here; real users (10001+) live
     *  far below. Doubles as the real-human filter for G2R_USER_IN. */
    private static final long ROBOT_UID_BASE = 900000000L;

    private static final Object LOCK = new Object();
    private static ServerSocket sListener;
    private static volatile Socket sGame;
    private static volatile DataOutputStream sOut;
    private static Thread sAcceptThread;
    private static Thread sReadThread;
    private static int sBoundPort;
    /** One robot wave per engine link; reset in acceptLoop on every new
     *  engine socket (a swept/respawned engine is a FRESH world). */
    private static boolean sRobotsPushed;

    private MonitorServer() {}

    /**
     * Bind + accept loop. Idempotent; failures are logged, never fatal.
     *
     * PORT SCAN (run 38101060514): a fixed 18081 can be held FOREVER by an
     * fd an orphaned engine inherited from a dead holder (fork/exec does
     * not close-on-exec the listener) - the kernel keeps that socket bound
     * with a dead backlog behind it, every rebind fails with EADDRINUSE and
     * the fresh engines' connects end refused. So: scan 18081..18120 and
     * bind the FIRST port that actually accepts a bind. serverConfig.json
     * is (re)written by the CURRENT holder with ITS bound port, so the
     * engine it spawns connects to a LIVE listener by construction. The
     * legacy PORT stays first in the scan.
     */
    public static void start() {
        synchronized (LOCK) {
            if (sListener != null && !sListener.isClosed()) return;
            Throwable last = null;
            for (int port = PORT; port <= PORT + 39; port++) {
                try {
                    ServerSocket ss = new ServerSocket();
                    // EXPLICIT IPv4 loopback (run 38104976182: the self-test
                    // showed EVERY port 'bound but NOT connectable' -
                    // getLoopbackAddress() resolves to ::1 in this Android
                    // env, so the listener was IPv6-only while the engine
                    // (and the probe) dial IPv4 127.0.0.1 -> ECONNREFUSED).
                    // The engine's monitorAddr is always the literal
                    // "127.0.0.1" - bind exactly that.
                    ss.bind(new java.net.InetSocketAddress(
                            java.net.InetAddress.getByName("127.0.0.1"), port), 2);
                    // SELF-TEST: bind success is not enough (run 38102569171:
                    // the engine's connect was refused 1s after a successful
                    // bind). Verify a real loopback connect completes and is
                    // accepted; on failure close and try the next port.
                    boolean ok = false;
                    try {
                        java.net.Socket probe = new java.net.Socket();
                        probe.connect(new java.net.InetSocketAddress(
                                java.net.InetAddress.getByName("127.0.0.1"),
                                port), 800);
                        ok = probe.isConnected();
                        probe.close(); // the accept loop sees EOF, cleans up
                    } catch (Throwable t) {
                        ok = false;
                    }
                    if (!ok) {
                        L.e("monitor: port " + port
                                + " bound but NOT connectable - skipping");
                        try { ss.close(); } catch (Throwable ignored) {}
                        continue;
                    }
                    sListener = ss;
                    sBoundPort = port;
                    L.i("monitor: listening on 127.0.0.1:" + port);
                    Thread t = new Thread(() -> acceptLoop(), "LocalApiMonitor");
                    t.setDaemon(true);
                    t.start();
                    sAcceptThread = t;
                    return;
                } catch (Throwable t) {
                    last = t;
                }
            }
            L.e("monitor bind failed on all ports "
                    + PORT + ".." + (PORT + 39) + ": " + last);
            sListener = null;
        }
    }

    /** The port this holder's monitor actually bound (0 = none). */
    public static int boundPort() {
        synchronized (LOCK) {
            return sListener != null && !sListener.isClosed() ? sBoundPort : 0;
        }
    }

    public static boolean gameConnected() {
        Socket s = sGame;
        return s != null && s.isConnected() && !s.isClosed();
    }

    private static void acceptLoop() {
        while (sListener != null && !sListener.isClosed()) {
            try {
                Socket s = sListener.accept();
                L.i("monitor: game server connected from " + s.getRemoteSocketAddress());
                synchronized (LOCK) {
                    Socket old = sGame;
                    if (old != null) try { old.close(); } catch (IOException ignored) {}
                    sGame = s;
                    sOut = new DataOutputStream(new java.io.BufferedOutputStream(
                            s.getOutputStream()));
                    sRobotsPushed = false; // fresh engine link -> fresh wave
                }
                final Socket sock = s;
                Thread r = new Thread(() -> readLoop(sock), "LocalApiMonitorRead");
                r.setDaemon(true);
                r.start();
            } catch (Throwable t) {
                if (sListener == null || sListener.isClosed()) return;
                L.e("monitor accept failed: " + t);
                try { Thread.sleep(300); } catch (InterruptedException ignored) { return; }
            }
        }
    }

    private static void readLoop(Socket sock) {
        try {
            DataInputStream in = new DataInputStream(new java.io.BufferedInputStream(
                    sock.getInputStream()));
            while (true) {
                int len = in.readInt();
                if (len < 4 || len > 8 * 1024 * 1024) throw new IOException("bad frame len " + len);
                int type = in.readInt();
                int payload = len - 4;
                byte[] data = new byte[Math.max(0, payload)];
                in.readFully(data);
                String json = payload > 0 ? new String(data, "UTF-8") : "";
                onGameFrame(type, json);
            }
        } catch (Throwable t) {
            L.i("monitor: game connection closed (" + t + ")");
            synchronized (LOCK) {
                if (sGame == sock) { sGame = null; sOut = null; }
            }
        }
    }

    private static void onGameFrame(int type, String json) {
        switch (type) {
            case G2R_CONNECT:
                L.i("monitor: G2R_CONNECT " + abbreviate(json));
                send(R2G_CONNECT_REPLY, "{}");
                // v0.6.29-joinwave: NO robot wave here anymore. The wave
                // used to fire on every engine connect — a RESPAWNED engine
                // with nobody joining then got 15 bots pinned at waitPos
                // forever (the empty-room force-teleport loop, 233 events
                // in the v0.6.28 evidence) and re-pushed its wave into an
                // already-lost world. Bots are only worth pushing when a
                // REAL player is actually entering the room: the wave now
                // fires from G2R_USER_IN below (once per engine link).
                break;
            case G2R_HEARTBEAT:
                break; // steady state, too noisy to log
            case G2R_GAME_STATUS:
                L.i("monitor: g2r type=" + type + " " + abbreviate(json));
                break;
            case G2R_USER_IN:
                L.i("monitor: g2r type=" + type + " " + abbreviate(json));
                onUserIn(json);
                break;
            case G2R_USER_OUT:
                L.i("monitor: g2r type=" + type + " " + abbreviate(json));
                break;
            default:
                L.i("monitor: g2r type=" + type + " " + abbreviate(json));
                break;
        }
    }

    /** G2R_USER_IN: a user entered the room. v0.6.29-joinwave: the robot
     *  wave fires the FIRST time a REAL human (id < ROBOT_UID_BASE) is seen
     *  on this engine link. Ordering is safe by construction: the human's
     *  attr was already pushed by the dispatch (the login gate demands it),
     *  the login completed, and WaitingPlayerTask only starts its countdown
     *  once isPlayerEnough(startPlayers) passes — which needs the bots — so
     *  the ~2.6s the wave takes to land cannot outrun the match start.
     *  Robots (ids ROBOT_UID_BASE+) never re-trigger the wave.
     *  MULTI-GAME: only games with a player-count gate get a wave — the
     *  g1008 proven room (startPlayers 16), the g1061 solo room (8x1), the
     *  g1062 duo room (8x2, both config.yml-verified) and — since bundle
     *  v7's event bridge + [ai-presence] fallback (§20) — the g1043/44/45
     *  PixelGun rooms (6/6/2) and g1054 SkyWarLuckyBlock (3): their trees
     *  are CEvents-generation + AI-unaware, and the fallback materializes
     *  the wave robots as real, counted players through the rooms' own
     *  PlayerListeners. The size AND the team cycle come from GameDef. */
    private static void onUserIn(String json) {
        try {
            long id = new JSONObject(json).optLong("id", 0);
            if (id > 0 && id < ROBOT_UID_BASE) {
                int wave = GameServerManager.currentBotWave();
                if (wave <= 0) {
                    L.i("monitor: human " + id + " entered the room — game "
                            + GameServerManager.currentGameIdOrDefault()
                            + " needs no robot wave");
                    return;
                }
                L.i("monitor: human " + id + " entered the room — pushing "
                        + "the robot wave (" + wave + ", "
                        + GameServerManager.currentBotWaveTeams() + " teams)");
                pushRobotWave(wave, GameServerManager.currentBotWaveTeams());
            }
        } catch (Throwable t) {
            L.e("monitor: user-in parse failed: " + t);
        }
    }

    /** One wave of AI player attrs for the hosted room (the size and the
     *  team cycle come from the game's GameDef — g1008: 15 bots over the
     *  4 map teams; g1061 solo: 7 over the 8 teams; g1062 duo: 15 over 8).
     *  robotId=1 selects AI group 1 in the map's AiPlayerConfig.csv
     *  (per-team behavior rows 101+; fix_ai_teams_v3.py extends the
     *  8-team maps to teams 1..8 — without those rows AITeamManager
     *  silently skips the robot). Synthetic platform uids ROBOT_UID_BASE+1..
     *  never collide with real users (10001+) and never log in via RakNet,
     *  so the login requestId gate never sees them. reqId is a placeholder
     *  - RoomClient::_parseUserAttr only requires the FIELD to exist for
     *  robots. */
    private static void pushRobotWave(int count, int teams) {
        synchronized (LOCK) {
            if (sRobotsPushed) return;
            sRobotsPushed = true;
        }
        final int COUNT = count;
        Thread t = new Thread(() -> {
            try { Thread.sleep(800); } catch (InterruptedException ignored) { return; }
            int sent = 0;
            for (int i = 1; i <= COUNT; i++) {
                try {
                    JSONObject o = new JSONObject();
                    o.put("reqId", "bots");
                    o.put("id", ROBOT_UID_BASE + i);
                    o.put("clz", 1);
                    o.put("team", ((i - 1) % teams) + 1);
                    o.put("rid", 1);
                    o.put("sex", 1);
                    o.put("vip", 0);
                    o.put("name", "Bot" + i);
                    o.put("isRobot", true);
                    o.put("robotId", 1);
                    JSONObject skin = new JSONObject();
                    skin.put("skin_color", "255-225-195-255");
                    o.put("skin", skin);
                    send(R2G_USER_ATTR, o.toString());
                    sent++;
                    try { Thread.sleep(120); } catch (InterruptedException ignored) { break; }
                } catch (Throwable t2) {
                    L.e("monitor: robot attr " + i + " failed: " + t2);
                }
            }
            L.i("monitor: pushed " + sent + "/" + COUNT
                    + " robot attrs (isRobot=true, robotId=1, teams 1.."
                    + teams + ")");
        }, "LocalApiMonitorRobots");
        t.setDaemon(true);
        t.start();
    }

    private static String abbreviate(String s) {
        if (s == null) return "";
        return s.length() <= 300 ? s : s.substring(0, 300) + "...";
    }

    private static void send(int type, String json) {
        DataOutputStream out = sOut;
        if (out == null) {
            L.e("monitor: cannot send type " + type + " — no game connection");
            return;
        }
        try {
            byte[] payload = json.getBytes("UTF-8");
            synchronized (LOCK) {
                out.writeInt(payload.length + 4);
                out.writeInt(type);
                out.write(payload);
                out.flush();
            }
        } catch (Throwable t) {
            L.e("monitor send type " + type + " failed: " + t);
        }
    }

    /**
     * Push the user attributes the game server needs before it accepts the
     * player's login (RoomClient::_parseUserAttr requires reqId/id/clz/team/
     * rid/sex/vip; skin is optional — the server falls back to defaults).
     */
    public static void pushUserAttr(long uid, String requestId, int sex,
                                    String name, int vip, String country) {
        try {
            JSONObject o = new JSONObject();
            o.put("reqId", requestId == null ? "" : requestId);
            o.put("id", uid);
            o.put("clz", 1);
            o.put("team", 0);
            o.put("rid", 1);
            o.put("sex", sex == 0 ? 1 : sex);
            o.put("vip", vip);
            if (name != null && !name.isEmpty()) o.put("name", name);
            if (country != null && !country.isEmpty()) o.put("country", country);
            // skin: server-side defaults kick in for zero/absent parts; a
            // neutral skin_color avoids a fully transparent model.
            JSONObject skin = new JSONObject();
            skin.put("skin_color", "255-225-195-255");
            o.put("skin", skin);
            send(R2G_USER_ATTR, o.toString());
            L.i("monitor: pushed user attr uid=" + uid + " reqId=" + requestId);
        } catch (Throwable t) {
            L.e("monitor pushUserAttr failed: " + t);
        }
    }
}
