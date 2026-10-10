package com.localapi;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;

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
                L.i(TAG + ": no live GameServer gaddr - local fallback");
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
            final String signature = Long.toHexString(
                    Double.doubleToLongBits(Math.random()));
            final long timestamp = System.currentTimeMillis();

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
            new Thread(new Runnable() {
                @Override public void run() {
                    // Pre-place the map bundle where MapManager::n expects
                    // it - the engine's own downloader cannot create the
                    // emulated-storage dir chain (run 38089237461: CreateDir
                    // error 17 -> onDownloadMapFailure x2 -> no connect).
                    GameServerManager.ensureEngineMap();
                    boolean pushed = false;
                    for (int i = 0; i < ATTR_PUSH_TRIES; i++) {
                        GameServerManager.notifyDispatch(fUid, requestId, 1,
                                fNick, 0, "Oversea");
                        if (MonitorServer.gameConnected()) { pushed = true; break; }
                        try { Thread.sleep(1000L); } catch (InterruptedException ie) { return; }
                    }
                    L.i(TAG + ": attrs " + (pushed ? "pushed" : "PUSH-UNVERIFIED")
                            + " uid=" + fUid + " requestId=" + requestId
                            + " gaddr=" + GameServerManager.gameAddr());
                    new Handler(Looper.getMainLooper()).post(new Runnable() {
                        @Override public void run() {
                            try {
                                startOnlineGame(ctx, gameEntity, gaddr, mapId,
                                        mapUrl, resVersion, requestId, signature,
                                        timestamp, fNick, fUid);
                            } catch (Throwable t) {
                                L.e(TAG + ": startOnlineGame failed: " + t);
                            }
                        }
                    });
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
