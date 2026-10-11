package com.localapi;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

import org.json.JSONObject;

/**
 * JoinBridge — turns the hall Quick-in's LOCAL join into the ONLINE join
 * into the on-device GameServer room (BedWar g1008 on map m1008_2).
 *
 * THE DECODE (session 58, androguard on the shipped APK):
 *   StartMc.startGame(Context, EnterRealmsResult, flavor, baseUrl) is the
 *   ONLY engine entry. It gson-serializes the EnterRealmsResult into the
 *   "start.game.info" shared prefs, kills the :BlockmanGo process and
 *   startActivityForResult's StartMcActivity with the BLOCK_MAN enum
 *   extra. StartMcActivity's rx chain (Controller.a(Subscriber)) reads
 *   the prefs back, switches the engine env on game.isNewEngine/isUgc,
 *   loadSO's and setEnterRealmsResult's — the engine then initGame's with
 *   result.gameAddr host:port, requestId, gameType=game.gameId and
 *   downloads result.mapUrl before the RakNet connect.
 *
 *   The hall Quick-in's ONLY local startGame call site in the whole app is
 *   va$b.a(MiniGameToken) — it hard-sets gameAddr=""/requestId=""/resetIp=""
 *   (client.log initGame ip[] port[0] gameType=<tapped>) which is exactly
 *   the local-world boot every redroid run observed.
 *
 *   The ONLINE variant, va$b.a(Dispatch, Z), copies dispatch.gAddr into
 *   the result — the same fields the engine consumes. So the takeover
 *   builds that result directly from GameServerManager's live room and
 *   calls StartMc.startGame — the SAME entry the app itself uses, no
 *   prefs surgery, no am-start serializable problem (the enum extra can
 *   never be passed from adb).
 *
 * Called from the patched va$b smali (scripts/patch_join.py) - the smali
 * invoke descriptor is (Landroid/content/Context;Ljava/lang/Object;)Z
 * (this class compiles against android-stubs alone, so the tapped Game
 * entity rides in as Object; the smali wrapper try/catches the call and
 * falls back to a_local on any Throwable, so a bridge failure can never
 * crash the join):
 *   takeOverJoin(context, tappedGame) == false  -> original local start
 *   true                                        -> online join in flight
 *
 * Everything app-side is reached via reflection so this compiles against
 * the android-stubs classpath alone (build_server_dex.sh -cp has no app
 * classes). Markers: "JoinBridge:" (logcat tag LocalAPI).
 */
public final class JoinBridge {

    private static final String TAG = "JoinBridge";
    /** Room attributes push retry budget (the monitor link must be up
     *  BEFORE the engine's C2S login lands - the login gate matches
     *  requestId against the pushed attrs). 30s: the engine's monitor
     *  link can be mid-reconnect after an app-process churn. */
    private static final int ATTR_PUSH_TRIES = 30;

    private JoinBridge() {}

    /**
     * UI-thread entry, called at the top of the patched va$b.a(MiniGameToken).
     *
     * @param ctx        the dialog's activity context (startGame casts it to
     *                   Activity for startActivityForResult)
     * @param gameEntity the tapped game's greendao Game entity — its
     *                   isNewEngine/isUgc flags select the engine .so (the
     *                   hall already boots the right one); gameId is forced
     *                   to the hosted room's script id.
     * @return true when the online join was started (caller must return
     *         immediately); false → caller falls back to the local start.
     */
    public static boolean takeOverJoin(final Context ctx, final Object gameEntity) {
        try {
            if (ctx == null || gameEntity == null) {
                return false;
            }
            final String gaddr = GameServerManager.gameAddr();
            if (gaddr == null) {
                // v0.6.36-joinhint: the engine exists ONLY after
                // GameServerManager.ensure() stages the runtime bundle
                // (64MB GitHub download + overlay; MapAssets' maps pack
                // rides the same release). Until that lands, EVERY tap
                // used to silently fall through here and the engine
                // booted a local world with ip[]/port[0]/mapId[] and
                // died on the empty-URL map download (HttpDownloader
                // error 5 -> onDownloadMapFailure x2) - the exact
                // physical-phone report of 2026-10-11. Make the
                // fallback HONEST: kick a staging retry (idempotent,
                // single-flight; a no-op when this process is not the
                // 18080 holder - the holder retries via its own
                // dispatch kick at the token request) and tell the
                // user why, instead of a silent dead-end boot.
                boolean kicked = GameServerManager.kick();
                L.i(TAG + ": no live GameServer gaddr - local fallback"
                        + " (kick=" + kicked + ")");
                try {
                    Toast.makeText(ctx,
                            "Game world is still preparing (first run"
                                    + " downloads game files). Please try"
                                    + " again in a few minutes.",
                            Toast.LENGTH_LONG).show();
                } catch (Throwable t2) {
                    L.e(TAG + ": prepare toast failed: " + t2);
                }
                return false;
            }

            // --- account (same source the app's own join paths use) ---
            Class<?> accC = Class.forName("com.sandboxol.center.entity.AccountCenter");
            Object acc = accC.getMethod("newInstance").invoke(null);
            long uid = 0;
            String nick = "";
            Object uidField = accC.getField("userId").get(acc);
            Object nickField = accC.getField("nickName").get(acc);
            Object uidVal = uidField.getClass().getMethod("get").invoke(uidField);
            Object nickVal = nickField.getClass().getMethod("get").invoke(nickField);
            if (uidVal instanceof Number) uid = ((Number) uidVal).longValue();
            if (nickVal != null) nick = String.valueOf(nickVal);
            if (uid <= 0) {
                L.i(TAG + ": no logged-in account (uid=" + uid + ") - local fallback");
                return false;
            }

            final String requestId = Long.toHexString(System.nanoTime())
                    + Long.toHexString(Math.abs(uid));
            final long timestamp = System.currentTimeMillis();
            // The engine's C2S login gate (LORD_PLATFORM_LINUX branch is
            // ACTIVE on the Android build, run 38107604916 'login fail,
            // result code=1' = emErrTokenWrong): the token must equal
            // SHA1_hex_lowercase(WEB_HTTP_SECRET + uid + gameTimestamp)
            // where WEB_HTTP_SECRET is the constant the server binary
            // embeds (Server.cpp: 'pq0194mxoqfh48L362G6R09T737E273X' - the
            // same string serverConfig.json carries as 'secret').
            final String signature = gameToken(uid, timestamp);

            // The engine resolves scripts by the ScriptSetting GameType key
            // (g####): force the hosted room's id so the engine loads the
            // BedWar scripts + m1008_2 map regardless of the tapped card.
            // The entity's isNewEngine/isUgc flags stay as tapped (they
            // already boot the correct engine .so for this client).
            gameEntity.getClass().getMethod("setGameId", String.class)
                    .invoke(gameEntity, GameServerManager.ENGINE_GAME_ID);
            final String mapId = GameServerManager.ENGINE_MAP_ID;

            // Map bundle for the engine: result.mapUrl feeds the native
            // download -> checksums.md5 verify -> onMapDownloadSuccess ->
            // resetGameDispatch -> RakNet connect.
            final String mapUrl;
            final int resVersion;
            JSONObject entry = MapAssets.entryForGame(GameServerManager.ENGINE_GAME_ID);
            if (entry != null) {
                mapUrl = MapAssets.durlFor(entry);
                resVersion = entry.optInt("version", 1);
            } else {
                mapUrl = "";
                resVersion = 1;
            }

            // startGame must run on the UI thread (startActivityForResult);
            // the map pre-placement + attr pushes run off it.
            final long fUid = uid;
            final String fNick = nick;
            final String fReqId = requestId;
            final String fCountry = "Oversea";
            new Thread(new Runnable() {
                @Override public void run() {
                    // Pre-place the map bundle where MapManager::n expects
                    // it - the engine's own downloader cannot create the
                    // emulated-storage dir chain (run 38089237461: CreateDir
                    // error 17 -> onDownloadMapFailure x2 -> no connect).
                    GameServerManager.ensureEngineMap();
                    // Push the join attrs THROUGH THE HOLDER (the /v1/
                    // joinbridge endpoint): the monitor + engine ownership
                    // live in the 18080 holder process - the UI process's
                    // own ensure/push are no-ops when it is not the holder
                    // (run 38092797697: the attrs never landed, the C2S
                    // login timed out).
                    final String preBody = joinBridgeBody(fUid, fReqId, 1,
                            fNick, 0, fCountry, true);
                    // WAIT FOR THE PUSH before startGame (bounded 25s): the
                    // client's C2S login is ONE-SHOT and fires ~10-15s after
                    // startGame - the attrs MUST already be on the engine
                    // (run 38106258661: pushed=true only at +19s, the login
                    // had failed at +12s). The join dialog is a modal rx
                    // callback and stays alive for the bounded wait; the
                    // monitor bring-up (sweep+spawn+boot+link) is ~6-9s.
                    boolean pushed = false;
                    long deadline = System.currentTimeMillis() + 25000L;
                    while (System.currentTimeMillis() < deadline) {
                        String res = httpPost("/v1/joinbridge", preBody);
                        if (res != null && res.contains("\"pushed\":true")) {
                            pushed = true; break;
                        }
                        try { Thread.sleep(1000L); }
                        catch (InterruptedException ie) { return; }
                    }
                    L.i(TAG + ": joinbridge " + (pushed ? "PUSHED" : "deadline")
                            + " req=" + fReqId);
                    L.i(TAG + ": attrs " + (pushed ? "pushed" : "PUSH-UNVERIFIED")
                            + " uid=" + fUid + " requestId=" + requestId
                            + " gaddr=" + GameServerManager.gameAddr());
                    new Handler(Looper.getMainLooper()).post(new Runnable() {
                        @Override public void run() {
                            try {
                                startOnlineGame(ctx, gameEntity, gaddr, mapId,
                                        mapUrl, resVersion, fReqId, signature,
                                        timestamp, fNick, fUid);
                            } catch (Throwable t) {
                                L.e(TAG + ": startOnlineGame failed: " + t);
                            }
                        }
                    });
                    // CONTINUATION: keep guaranteeing + pushing while the
                    // client engine boots (map pre-placed: boot ~8-15s).
                    // ensure=true stays safe until the client's RakNet
                    // connect (+10-20s); after that the RePush phase is
                    // push-only (never sweep).
                    new Thread(new Runnable() {
                        @Override public void run() {
                            long deadline = System.currentTimeMillis() + 30000L;
                            while (System.currentTimeMillis() < deadline) {
                                String r = httpPost("/v1/joinbridge", preBody);
                                if (r != null && r.contains("\"pushed\":true")) {
                                    L.i(TAG + ": joinbridge cont pushed req="
                                            + fReqId);
                                    return;
                                }
                                GameServerManager.notifyDispatch(fUid, fReqId,
                                        1, fNick, 0, fCountry);
                                if (MonitorServer.gameConnected()) return;
                                try { Thread.sleep(1000L); }
                                catch (InterruptedException ie) { return; }
                            }
                        }
                    }, "JoinBridgeCont").start();
                    // Keep the attrs fresh through the login window: re-push
                    // (push-only, ensure=false - NEVER sweep once the client
                    // may be connected) for ~44s after that.
                    final String postBody = joinBridgeBody(fUid, fReqId, 1,
                            fNick, 0, fCountry, false);
                    new Thread(new Runnable() {
                        @Override public void run() {
                            try { Thread.sleep(30000L); }
                            catch (InterruptedException ie) { return; }
                            for (int i = 0; i < 22; i++) {
                                httpPost("/v1/joinbridge", postBody);
                                GameServerManager.notifyDispatch(fUid, fReqId,
                                        1, fNick, 0, fCountry);
                                try { Thread.sleep(2000L); }
                                catch (InterruptedException ie) { return; }
                            }
                        }
                    }, "JoinBridgeRePush").start();
                }
            }, "JoinBridge").start();

            L.i(TAG + ": takeover ONLINE join uid=" + uid + " gaddr=" + gaddr
                    + " game=" + GameServerManager.ENGINE_GAME_ID
                    + " map=" + mapId + " requestId=" + requestId);
            return true;
        } catch (Throwable t) {
            L.e(TAG + ": takeover failed: " + t);
            return false;
        }
    }

    /** The server's login-gate token: SHA1_hex_lowercase(WEB_HTTP_SECRET +
     *  uid + gameTimestamp) - byte-identical to C2SInitPacketHandles.cpp's
     *  LORD_PLATFORM_LINUX check (Server::WEB_HTTP_SECRET constant, decimal
     *  uid/ts, lowercase hex via std::hex). */
    private static String gameToken(long uid, long timestamp) {
        try {
            java.security.MessageDigest md =
                    java.security.MessageDigest.getInstance("SHA-1");
            byte[] d = md.digest(("pq0194mxoqfh48L362G6R09T737E273X"
                    + uid + timestamp).getBytes("UTF-8"));
            StringBuilder sb = new StringBuilder(d.length * 2);
            for (byte b : d) {
                sb.append(Character.forDigit((b >> 4) & 0xF, 16));
                sb.append(Character.forDigit(b & 0xF, 16));
            }
            return sb.toString();
        } catch (Throwable t) {
            L.e(TAG + ": gameToken failed: " + t);
            return "";
        }
    }

    /** Build the /v1/joinbridge request body. */
    private static String joinBridgeBody(long uid, String reqId, int sex,
            String name, int vip, String country, boolean ensure) {
        try {
            JSONObject o = new JSONObject();
            o.put("id", uid);
            o.put("reqId", reqId);
            o.put("sex", sex);
            o.put("name", name);
            o.put("vip", vip);
            o.put("country", country);
            o.put("ensure", ensure);
            return o.toString();
        } catch (Throwable t) {
            return "{\"id\":" + uid + ",\"reqId\":\"" + reqId
                    + "\",\"ensure\":" + ensure + "}";
        }
    }

    /** POST a body to the holder's LocalAPI. Short timeouts so the caller's
     *  loop stays responsive. Returns the response body or null. */
    private static String httpPost(String path, String body) {
        java.net.HttpURLConnection c = null;
        try {
            java.net.URL u = new java.net.URL(Handlers.LOCAL_BASE_URL + path);
            c = (java.net.HttpURLConnection) u.openConnection();
            c.setRequestMethod("POST");
            c.setConnectTimeout(3000);
            c.setReadTimeout(9000); // the holder polls up to ~6s inside
            c.setDoOutput(true);
            java.io.OutputStream os = c.getOutputStream();
            os.write(body.getBytes("UTF-8"));
            os.close();
            int code = c.getResponseCode();
            if (code != 200) return null;
            java.io.InputStream in = c.getInputStream();
            java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
            in.close();
            return bo.toString("UTF-8");
        } catch (Throwable t) {
            return null;
        } finally {
            if (c != null) try { c.disconnect(); } catch (Throwable ignored) {}
        }
    }

    /**
     * Build the EnterRealmsResult exactly like the app's online variant
     * (va$b.a(Dispatch, Z)) and call the app's own StartMc.startGame —
     * the same gson->prefs->StartMcActivity chain as every normal join.
     */
    private static void startOnlineGame(Context ctx, Object gameEntity,
            String gaddr, String mapId, String mapUrl, int resVersion,
            String requestId, String signature, long timestamp,
            String nick, long uid) throws Exception {
        Class<?> resC = Class.forName(
                "com.sandboxol.center.router.moduleInfo.game.EnterRealmsResult");
        Object r = resC.newInstance();
        // identity + the join params the engine consumes
        call(resC, r, "setGameAddr", gaddr);
        call(resC, r, "setUserName", nick);
        call(resC, r, "setUserId", uid);
        call(resC, r, "setUserToken", signature);
        call(resC, r, "setDispatchToken", signature);
        call(resC, r, "setDispatchUrl", Handlers.LOCAL_BASE_URL);
        call(resC, r, "setGame", gameEntity);
        call(resC, r, "setTimestamp", timestamp);
        call(resC, r, "setRequestId", requestId);
        call(resC, r, "setMapId", mapId);
        call(resC, r, "setMapName", mapId);
        call(resC, r, "setMapUrl", mapUrl);
        call(resC, r, "setResVersion", resVersion);
        call(resC, r, "setRegion", 0);
        call(resC, r, "setCountry", "Oversea");
        call(resC, r, "setChatRoomId", "");
        call(resC, r, "setResetIp", "");
        call(resC, r, "setTeam", false);
        call(resC, r, "setFollow", false);
        call(resC, r, "setInviter", 0L);
        call(resC, r, "setTargetUserId", uid);
        // gameMode/newStartMadel ride the tapped entity's own values (the
        // hall's entity already selects the working engine env).

        Class<?> smC = Class.forName("com.sandboxol.blocky.router.StartMc");
        Object sm = smC.getMethod("newInstance").invoke(null);
        smC.getMethod("startGame", Context.class,
                Class.forName("com.sandboxol.center.router.moduleInfo.game.EnterRealmsResult"),
                String.class, String.class)
                .invoke(sm, ctx, r, "google", Handlers.LOCAL_BASE_URL);
        L.i(TAG + ": StartMc.startGame dispatched (online) — engine should "
                + "initGame ip=127.0.0.1 port=31108 gameType=g1008 map=" + mapId);
    }

    /** Best-effort setter: match by name, box primitives automatically. */
    private static void call(Class<?> cls, Object receiver, String name,
            Object arg) throws Exception {
        for (java.lang.reflect.Method m : cls.getMethods()) {
            if (!m.getName().equals(name)) continue;
            Class<?>[] ps = m.getParameterTypes();
            if (ps.length != 1) continue;
            Class<?> p = ps[0];
            if (arg == null || p.isInstance(arg)
                    || (p == long.class && arg instanceof Long)
                    || (p == int.class && arg instanceof Integer)
                    || (p == boolean.class && arg instanceof Boolean)
                    || (p == double.class && arg instanceof Double)
                    || (p == float.class && arg instanceof Float)) {
                m.invoke(receiver, arg);
                return;
            }
        }
        throw new NoSuchMethodException(cls.getName() + "." + name
                + " (" + (arg == null ? "null" : arg.getClass().getName()) + ")");
    }
}
