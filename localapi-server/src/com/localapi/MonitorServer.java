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

    private static final Object LOCK = new Object();
    private static ServerSocket sListener;
    private static volatile Socket sGame;
    private static volatile DataOutputStream sOut;
    private static Thread sAcceptThread;
    private static Thread sReadThread;

    private MonitorServer() {}

    /** Bind + accept loop. Idempotent; failures are logged, never fatal. */
    public static void start() {
        synchronized (LOCK) {
            if (sListener != null && !sListener.isClosed()) return;
            try {
                sListener = new ServerSocket();
                sListener.bind(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(), PORT), 2);
                L.i("monitor: listening on 127.0.0.1:" + PORT);
            } catch (Throwable t) {
                L.e("monitor bind failed: " + t);
                sListener = null;
                return;
            }
            Thread t = new Thread(() -> acceptLoop(), "LocalApiMonitor");
            t.setDaemon(true);
            t.start();
            sAcceptThread = t;
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
                break;
            case G2R_HEARTBEAT:
                break; // steady state, too noisy to log
            case G2R_GAME_STATUS:
            case G2R_USER_IN:
            case G2R_USER_OUT:
                L.i("monitor: g2r type=" + type + " " + abbreviate(json));
                break;
            default:
                L.i("monitor: g2r type=" + type + " " + abbreviate(json));
                break;
        }
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
