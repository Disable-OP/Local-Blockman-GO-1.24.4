package com.localapi;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * State-backed endpoint handlers (Phase 1: auth + boot-critical config).
 * Every handler returns the exact JSON the app's Gson models expect
 * (HttpResponse envelope: {"code":1,"message":...,"data":...}).
 */
final class Handlers {

    private static final String OK = "ok";
    private static final String FAIL = "failed";

    private Handlers() {}

    interface Ctx {
        String query(String name);

        String header(String name);

        String body();

        String pathParam(String name);
    }

    static String handle(String name, Ctx ctx, StateStore store) {
        if ("login".equals(name)) return login(ctx, store);
        if ("register".equals(name)) return register(ctx, store);
        if ("userRegister".equals(name)) return userRegister(ctx, store);
        if ("visitor".equals(name)) return visitor(ctx, store);
        if ("tourist".equals(name)) return tourist(ctx, store);
        if ("authToken".equals(name)) return authToken(ctx, store);
        if ("renew".equals(name)) return renew(ctx, store);
        if ("logout".equals(name)) return logout(ctx, store);
        if ("rongToken".equals(name)) return rongToken(ctx, store);
        if ("checkVersion".equals(name)) return checkVersion(ctx, store);
        if ("appConfig".equals(name)) return appConfig(ctx, store);
        if ("changeNickName".equals(name)) return changeNickName(ctx, store);
        if ("changeInfo".equals(name)) return changeInfo(ctx, store);
        if ("joinSwitch".equals(name)) return bool(true);
        if ("ackPost".equals(name)) return envelope("none", null);
        if ("ackPut".equals(name)) return envelope("none", null);
        // ---- Phase 2: game catalog / detail / shop / daily economy ----
        if ("category".equals(name)) return category(ctx, store);
        if ("gameListByCondition".equals(name)) return gameListByCondition(ctx, store);
        if ("gameListMore".equals(name)) return gameListMore(ctx, store);
        if ("gameListGuessYouLike".equals(name)) return gameListGuessYouLike(ctx, store);
        if ("recentlyPlayList".equals(name)) return recentlyPlayList(ctx, store);
        if ("friendPlayList".equals(name)) return envelope("list", "[]");
        if ("recommendation".equals(name)) return recommendation(ctx, store);
        if ("getGameByType".equals(name)) return getGameByType(ctx, store);
        if ("getUGCGameList".equals(name)) return getUGCGameList(ctx, store);
        if ("miniGameDetail".equals(name)) return miniGameDetail(ctx, store);
        if ("gameDetail".equals(name)) return gameDetail(ctx, store);
        if ("gamePreheat".equals(name)) return gamePreheat(ctx, store);
        if ("getGameTypeList".equals(name)) return getGameTypeList(ctx, store);
        if ("getSystemAnnouncementInfo".equals(name)) return announcement();
        if ("getStopServiceAnnouncementInfo".equals(name)) return announcement();
        if ("getAllGameIdInfo".equals(name)) return getAllGameIdInfo(ctx, store);
        if ("getGameRank".equals(name)) return getGameRank(ctx, store);
        if ("getGameMyRank".equals(name)) return getGameMyRank(ctx, store);
        if ("getGameDetailShop".equals(name)) return getGameDetailShop(ctx, store);
        if ("getGameUpdateContent".equals(name)) return envelope("obj", "{\"content\":\"\",\"count\":0}");
        if ("getGameUpdateContentList".equals(name)) return envelope("obj", "{}");
        if ("getPartyCreateGameConfig".equals(name)) return getPartyCreateGameConfig(ctx, store);
        if ("getChatRoom".equals(name)) return getChatRoom(ctx, store);
        if ("appreciation".equals(name)) return appreciation(ctx, store);
        if ("miniGameToken".equals(name)) return miniGameToken(ctx, store);
        if ("followGameAuth".equals(name)) return miniGameToken(ctx, store);
        if ("miniGameMap".equals(name)) return miniGameToken(ctx, store);
        if ("getResInfo".equals(name)) return envelope("obj", "{\"durl\":\"\",\"resVersion\":1}");
        if ("resCheck".equals(name)) return envelope("obj", "{\"md5\":\"\",\"update\":false,\"url\":\"\"}");
        if ("getUpgradeInfo".equals(name)) return envelope("obj", "{\"needUpgrade\":false,\"downloadUrl\":\"\",\"hash\":\"\",\"resVersion\":1}");
        if ("getGameResource".equals(name)) return envelope("list", "[]");
        if ("countUploadVersion".equals(name)) return envelope("none", null);
        if ("dailySignIn".equals(name)) return dailySignIn(ctx, store);
        if ("clickSignIn".equals(name)) return clickSignIn(ctx, store);
        if ("getAdsReward".equals(name)) return getAdsReward(ctx, store);
        if ("getAdsRewardInfo".equals(name)) return envelope("obj", "{\"currency\":1,\"quantity\":200,\"remainTime\":0}");
        if ("getSignAdsReward".equals(name)) return getSignAdsReward(ctx, store);
        if ("friendList".equals(name)) return emptyPage(10);
        if ("friendRequestsList".equals(name)) return emptyPage(10);
        if ("followFriendsList".equals(name)) return emptyPage(10);
        if ("friendRecommendation".equals(name)) return friendRecommendation(ctx, store);
        if ("getVipInfo".equals(name)) return getVipInfo(ctx, store);
        if ("getSubscribeInfo".equals(name)) return getSubscribeInfo(ctx, store);
        L.e("unknown handler name: " + name);
        return envelope("none", null);
    }

    // ---------------------------------------------------------------- auth

    /** POST /user/api/v1/login, /user/api/v1/app/login, /user/api/v2/app/login */
    private static String login(Ctx ctx, StateStore store) {
        JSONObject form = body(ctx);
        String uid = form.optString("uid");
        String password = form.optString("password");
        String imei = form.optString("imei");
        L.i("login attempt: uid=" + uid + " imei=" + imei);

        if (uid != null && !uid.isEmpty()) {
            JSONObject u = store.findByKey(uid);
            if (u == null) {
                return fail("account not found, please register");
            }
            String saved = u.optString("password");
            if (saved != null && !saved.isEmpty() && !saved.equals(password)) {
                return fail("wrong password");
            }
            store.issueToken(u);
            u.put("isFirstLogin", false);
            store.save();
            return userEnvelope(u);
        }
        // no uid: device-only login — treat imei as the visitor identity
        if (imei != null && !imei.isEmpty()) {
            JSONObject u = store.findOrCreateByKey("device:" + imei, true);
            store.issueToken(u);
            u.put("isFirstLogin", false);
            store.save();
            return userEnvelope(u);
        }
        return fail("missing credentials");
    }

    /** POST /user/api/v1/register — body carries uid + password (+confirm). */
    private static String register(Ctx ctx, StateStore store) {
        JSONObject form = body(ctx);
        String uid = form.optString("uid");
        String password = form.optString("password");
        if (uid == null || uid.isEmpty()) {
            return fail("username required");
        }
        if (password == null || password.isEmpty()) {
            return fail("password required");
        }
        JSONObject u = store.createAccount(uid, password, uid);
        if (u == null) {
            return fail("username already exists");
        }
        store.issueToken(u);
        u.put("isFirstLogin", true);
        store.save();
        L.i("registered new account: " + uid + " -> userId " + u.optLong("userId"));
        return userEnvelope(u);
    }

    /** POST /user/api/v1/user/register — RegisterInfo {nickName, sex, inviteCode}. */
    private static String userRegister(Ctx ctx, StateStore store) {
        JSONObject form = body(ctx);
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        String nick = form.optString("nickName");
        if (nick != null && !nick.isEmpty()) {
            u.put("nickName", nick);
        }
        if (form.has("sex")) {
            u.put("sex", form.optInt("sex"));
        }
        u.put("isFirstLogin", false);
        store.save();
        return userEnvelope(u);
    }

    /** POST /user/api/v1/visitor — returns Visitor {id, accessToken, nickName}. */
    private static String visitor(Ctx ctx, StateStore store) {
        JSONObject form = body(ctx);
        String imei = form.optString("imei");
        if (imei == null || imei.isEmpty()) {
            imei = ctx.header("bmg-device-id");
        }
        if (imei == null || imei.isEmpty()) {
            imei = "unknown-device";
        }
        JSONObject u = store.findOrCreateByKey("visitor:" + imei, true);
        String token = store.issueToken(u);
        JSONObject v = new JSONObject();
        v.put("id", u.optLong("userId"));
        v.put("accessToken", token);
        v.put("nickName", u.optString("nickName"));
        L.i("visitor login: imei=" + imei + " -> userId " + u.optLong("userId"));
        return envelope("obj", v.toString());
    }

    /** POST /user/api/v1/app/user/tourist/login?appType=android — guest per device. */
    private static String tourist(Ctx ctx, StateStore store) {
        String device = ctx.header("bmg-device-id");
        if (device == null || device.isEmpty()) {
            device = ctx.query("appType");
        }
        if (device == null || device.isEmpty()) {
            device = "tourist";
        }
        JSONObject u = store.findOrCreateByKey("tourist:" + device, true);
        store.issueToken(u);
        u.put("isFirstLogin", true);
        store.save();
        L.i("tourist login: device=" + device + " -> userId " + u.optLong("userId"));
        return userEnvelope(u);
    }

    /** GET /user/api/v1/app/auth-token?userId=&... — AuthTokenResponse. */
    private static String authToken(Ctx ctx, StateStore store) {
        long userId = parseLong(ctx.query("userId"), parseLong(ctx.header("userid"), 0L));
        JSONObject u = userId > 0 ? store.findByUserId(userId) : null;
        if (u == null) {
            u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        }
        String token = store.issueToken(u);
        JSONObject a = new JSONObject();
        a.put("accessToken", token);
        a.put("hasBinding", false);
        a.put("hasPassword", u.optBoolean("hasPassword"));
        a.put("userId", u.optLong("userId"));
        return envelope("obj", a.toString());
    }

    /** POST /user/api/v1/app/renew — same shape as auth-token. */
    private static String renew(Ctx ctx, StateStore store) {
        return authToken(ctx, store);
    }

    /** PUT /user/api/v1/user/login-out */
    private static String logout(Ctx ctx, StateStore store) {
        store.dropToken(ctx.header("access-token"));
        return envelope("none", null);
    }

    /** GET /user/api/v1/users/device/token — chat token surrogate (HttpResponse<String>). */
    private static String rongToken(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        return envelope("obj", JSONObject.quote("local-" + u.optLong("userId")));
    }

    // ------------------------------------------------------------- profile

    /** PUT /user/api/v2/user/nickName?nickName= */
    private static String changeNickName(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        String nick = ctx.query("nickName");
        if (nick == null || nick.isEmpty()) {
            nick = body(ctx).optString("nickName");
        }
        if (nick != null && !nick.isEmpty()) {
            u.put("nickName", nick);
            store.save();
        }
        return userEnvelope(u);
    }

    /** PUT /user/api/v1/user/info | POST /user/api/v1/user/details/info */
    private static String changeInfo(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONObject form = body(ctx);
        if (form.has("nickName")) u.put("nickName", form.optString("nickName"));
        if (form.has("sex")) u.put("sex", form.optInt("sex"));
        if (form.has("details")) u.put("details", form.optString("details"));
        if (form.has("birthday")) u.put("birthday", form.optString("birthday"));
        if (form.has("picUrl")) u.put("picUrl", form.optString("picUrl"));
        u.put("isFirstLogin", false);
        store.save();
        return userEnvelope(u);
    }

    // ------------------------------------------------------- boot configs

    /** GET /config/files/blockymods-check-version — LatestVersion (no update). */
    private static String checkVersion(Ctx ctx, StateStore store) {
        JSONObject v = new JSONObject();
        v.put("apkMd5", "");
        v.put("apkUrl", "");
        v.put("content", "");
        v.put("url", "");
        v.put("updateInfo", "");
        v.put("newVersionCode", currentVersionCode());
        v.put("smallerThanVersion", 0);
        v.put("forceUpdateMinVersionCode", 0);
        v.put("forceUpdateMaxVersionCode", 0);
        v.put("status", 0);
        v.put("picUrl", "");
        v.put("needTobeForceUpdateVersions", new org.json.JSONArray());
        v.put("downloadGames", new org.json.JSONArray());
        v.put("langMap", new JSONObject());
        v.put("downInfoMap", new JSONObject());
        return envelope("obj", v.toString());
    }

    private static int currentVersionCode() {
        // keep in sync with the APK versionCode; zero force-update semantics
        return 4003;
    }

    /** GET /config/files/blockmods-config-v1 — AppConfig (all external content off). */
    private static String appConfig(Ctx ctx, StateStore store) {
        JSONObject c = new JSONObject();
        c.put("WhitelistLink", new org.json.JSONArray());
        c.put("activityUrl", "");
        c.put("activityVersionCode", 0);
        c.put("adsConfig", new JSONObject());
        c.put("dailyShareVersionCode", 0);
        c.put("downloadConfig", new JSONObject());
        c.put("downloadGames", new org.json.JSONArray());
        c.put("friendRefreshTimes", 30);
        c.put("gratitudeUrl", "");
        c.put("isClearCache", false);
        c.put("isNeedStopServiceAnnouncement", false);
        c.put("isNeedSystemAnnouncement", false);
        c.put("isOpenMTP", false);
        c.put("isOpenMorePay", false);
        c.put("isOpenUpdateSO", false);
        c.put("isShowActivity", false);
        c.put("isShowAds", false);
        c.put("isShowCampaign", false);
        c.put("isShowChest", false);
        c.put("isShowDressRecommend", false);
        c.put("isShowFriendFollow", false);
        c.put("isShowFriendMatch", false);
        c.put("isShowGameGuide", false);
        c.put("isShowHallowmasChest", false);
        c.put("isShowMainGuide", false);
        c.put("isShowMoreGame", false);
        c.put("isShowPartyInvite", false);
        c.put("isShowShare", false);
        c.put("isShowThirdPart", false);
        c.put("isShowTopActivity", false);
        return envelope("obj", c.toString());
    }

    // ------------------------------------------------- Phase 2: game catalog

    /** GET /game/api/v1/games — category paging: pageNo,pageSize,orderType,typeId,order,isPublish. */
    private static String category(Ctx ctx, StateStore store) {
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        long typeId = parseLong(ctx.query("typeId"), 0);
        String sort = ctx.query("orderType");
        if (sort == null || sort.isEmpty()) sort = ctx.query("order");
        return pageEnvelope(store, sort, typeId, false, pageNo, pageSize, false);
    }

    /** GET /game/api/v1/game/revision/list/by/condition — TypePageData<Game>. */
    private static String gameListByCondition(Ctx ctx, StateStore store) {
        String sort = ctx.query("sortType");
        long typeId = parseLong(ctx.query("filterTypeId"), 0);
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        return pageEnvelope(store, sort, typeId, false, pageNo, pageSize, true);
    }

    /** GET /game/api/v1/game/revision/list/more — PageData<Game>. */
    private static String gameListMore(Ctx ctx, StateStore store) {
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        return pageEnvelope(store, "complex", 0, false, pageNo, pageSize, false);
    }

    /** GET /game/api/v1/game/revision/list/recommend — List<Game>. */
    private static String gameListGuessYouLike(Ctx ctx, StateStore store) {
        return envelope("list", GameCatalog.page(store, "appreciate", 0, false, 1, 10).toString());
    }

    /** GET /game/api/v2/games/recommendation — List<Game>. */
    private static String recommendation(Ctx ctx, StateStore store) {
        return envelope("list", GameCatalog.page(store, "online", 0, false, 1, 12).toString());
    }

    /** GET /game/api/v2/games/recommendation/type — PageData<Game> by category type name. */
    private static String getGameByType(Ctx ctx, StateStore store) {
        String type = ctx.query("type");
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        long typeId = resolveTypeNameToId(store, type);
        return pageEnvelope(store, "online", typeId, false, pageNo, pageSize, false);
    }

    /** GET /game/api/v1/games/ugc — PageData<Game> of UGC titles. */
    private static String getUGCGameList(Ctx ctx, StateStore store) {
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        return pageEnvelope(store, "new", 0, true, pageNo, pageSize, false);
    }

    /** GET /game/api/v1/games/playlist/recently — per-user played history. */
    private static String recentlyPlayList(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray ids = store.recentGames(u, 20);
        JSONArray list = new JSONArray();
        for (int i = 0; i < ids.length(); i++) {
            JSONObject g = GameCatalog.byId(store, ids.optString(i));
            if (g != null) list.put(g);
        }
        return envelope("list", list.toString());
    }

    /** GET /game/api/v1/games/{gameId} — v1 detail. */
    private static String miniGameDetail(Ctx ctx, StateStore store) {
        return gameDetailJson(store, pathTail(store, ctx));
    }

    /** GET /game/api/v2/games/{gameId} — v2 detail. */
    private static String gameDetail(Ctx ctx, StateStore store) {
        return gameDetailJson(store, pathTail(store, ctx));
    }

    private static String gameDetailJson(StateStore store, String gameId) {
        JSONObject g = GameCatalog.byId(store, gameId);
        if (g == null) {
            return fail("game not found");
        }
        return envelope("obj", g.toString());
    }

    /** Extract the {gameId} path segment the router matched (…/games/<id>… patterns). */
    private static String pathTail(StateStore store, Ctx ctx) {
        return ctx.pathParam("gameId");
    }

    /** GET /game/api/v1/games/warmup/{gameId}/languages/{language}. */
    private static String gamePreheat(Ctx ctx, StateStore store) {
        JSONObject g = GameCatalog.byId(store, ctx.pathParam("gameId"));
        if (g == null) {
            return fail("game not found");
        }
        JSONObject w = new JSONObject();
        w.put("gameId", g.optString("gameId"));
        w.put("gameTitle", g.optString("gameTitle"));
        w.put("gameName", g.optString("gameName"));
        w.put("gameCoverPic", g.optString("gameCoverPic"));
        w.put("gameDetail", g.optString("gameDetail"));
        w.put("isPublish", 1);
        return envelope("obj", w.toString());
    }

    /** GET /game/api/v1/category/list/by/language — category tabs. */
    private static String getGameTypeList(Ctx ctx, StateStore store) {
        return envelope("list", GameCatalog.categories(store).toString());
    }

    /** Announcement payload: nothing to announce on a local server. */
    private static String announcement() {
        JSONObject a = new JSONObject();
        a.put("id", 0);
        a.put("isShow", false);
        a.put("isShowInGame", false);
        a.put("title", "");
        a.put("content", "");
        a.put("updateTime", System.currentTimeMillis());
        return envelope("obj", a.toString());
    }

    /** GET /game/api/v1/games/all/open/party. */
    private static String getAllGameIdInfo(Ctx ctx, StateStore store) {
        JSONArray out = new JSONArray();
        JSONArray gs = GameCatalog.list(store, "complex", 0, false);
        for (int i = 0; i < gs.length(); i++) {
            JSONObject g = gs.getJSONObject(i);
            if (g.optInt("isOpenParty") != 1) continue;
            JSONObject a = new JSONObject();
            a.put("gameId", g.optString("gameId"));
            a.put("gameName", g.optString("gameName"));
            a.put("isNewEngine", g.optInt("isNewEngine"));
            a.put("isUgc", g.optInt("isUgcGame"));
            a.put("picUrl", g.optString("gameCoverPic"));
            out.put(a);
        }
        return envelope("list", out.toString());
    }

    /** GET /game/api/v1/games/{gameId}/rank — RankInfo<CampaignRank>. */
    private static String getGameRank(Ctx ctx, StateStore store) {
        JSONArray board = GameCatalog.rankBoard(store, pathTail(store, ctx));
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        JSONArray slice = slice(board, pageNo, pageSize);
        JSONObject page = new JSONObject();
        page.put("data", slice);
        page.put("pageNo", pageNo);
        page.put("pageSize", pageSize);
        page.put("totalPage", totalPages(board.length(), pageSize));
        page.put("totalSize", board.length());
        JSONObject rank = new JSONObject();
        rank.put("pageInfo", page);
        rank.put("remainTime", 0);
        return envelope("obj", rank.toString());
    }

    /** GET /game/api/v1/games/{gameId}/uses/rank — the requesting user's row. */
    private static String getGameMyRank(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray board = GameCatalog.rankBoard(store, pathTail(store, ctx));
        for (int i = 0; i < board.length(); i++) {
            if (board.getJSONObject(i).optLong("userId") == u.optLong("userId")) {
                return envelope("obj", board.getJSONObject(i).toString());
            }
        }
        JSONObject mine = new JSONObject();
        mine.put("userId", u.optLong("userId"));
        mine.put("nickName", u.optString("nickName"));
        mine.put("headPic", "");
        mine.put("vip", u.optInt("vip"));
        mine.put("integral", 0);
        mine.put("isFirst", false);
        mine.put("rank", 0);
        return envelope("obj", mine.toString());
    }

    /** GET /shop/api/v2/shop/game/props/new — per-game prop shop. */
    private static String getGameDetailShop(Ctx ctx, StateStore store) {
        String gameId = ctx.query("gameId");
        if (gameId == null || gameId.isEmpty()) gameId = pathTail(store, ctx);
        return envelope("list", GameCatalog.shopProps(store, gameId).toString());
    }

    /** GET /game/api/v1/games/config/app/{gameId} — party create config. */
    private static String getPartyCreateGameConfig(Ctx ctx, StateStore store) {
        JSONObject c = new JSONObject();
        c.put("gameId", ctx.pathParam("gameId"));
        c.put("gameCategory", "");
        c.put("partyStatus", 1);
        c.put("memberMax", 16);
        c.put("commonMem", 8);
        c.put("teamMem", 4);
        c.put("teamNum", 4);
        c.put("vipMem", 12);
        return envelope("obj", c.toString());
    }

    /** POST /game/api/v1/game/chat/room?roomName= — persistent room ids. */
    private static String getChatRoom(Ctx ctx, StateStore store) {
        String roomName = ctx.query("roomName");
        if (roomName == null || roomName.isEmpty()) roomName = "lobby";
        JSONObject r = new JSONObject();
        r.put("roomId", GameCatalog.chatRoom(store, roomName));
        r.put("roomName", roomName);
        return envelope("obj", r.toString());
    }

    /** PUT /game/api/v1/games/{gameId}/appreciation — increments praise, returns new total. */
    private static String appreciation(Ctx ctx, StateStore store) {
        JSONObject g = GameCatalog.byId(store, pathTail(store, ctx));
        if (g == null) {
            return envelope("num", "0");
        }
        int praises = g.optInt("praiseNumber") + 1;
        g.put("praiseNumber", praises);
        g.put("appreciate", true);
        store.save();
        return envelope("num", String.valueOf(praises));
    }

    /**
     * GET /game/api/v2/game/auth (+ /flow/game/auth, /v1/game-map) — mini-game
     * session token. dispUrl is empty until the GameServer phase ships; the
     * token/timestamp are real dynamic values.
     */
    private static String miniGameToken(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONObject t = new JSONObject();
        t.put("token", "mg-" + u.optLong("userId") + "-"
                + Long.toHexString(System.nanoTime()));
        t.put("timestamp", System.currentTimeMillis());
        t.put("signature", "");
        t.put("dispUrl", "");
        t.put("downloadUrl", "");
        t.put("mapName", ctx.query("mapName") == null ? "" : ctx.query("mapName"));
        t.put("region", 0);
        t.put("country", "");
        return envelope("obj", t.toString());
    }

    // --------------------------------------------- Phase 2: daily + social

    /** GET /user/api/v2/users/{userId}/daily/sign/in — Map<String,DailySignInfo>. */
    private static String dailySignIn(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        boolean claimedToday = store.hasSignedIn(u, today());
        int claimedCount = store.signIns(u) == null ? 0 : store.signIns(u).length();
        int[] rewards = {200, 400, 600, 800, 1000, 1500, 3000};
        String[] keys = {"first", "second", "third", "fourth", "fifth", "sixth", "seventh"};
        JSONObject map = new JSONObject();
        for (int i = 0; i < 7; i++) {
            int slot = i + 1;
            JSONObject d = new JSONObject();
            d.put("id", slot);
            d.put("dailyId", slot);
            d.put("name", "Day " + slot);
            d.put("quantity", rewards[i]);
            d.put("status", (i < claimedCount % 7 || (claimedToday && i == claimedCount % 7)) ? 1 : 0);
            d.put("type", "golds");
            d.put("url", "");
            d.put("adQuantity", 0);
            d.put("adType", "");
            map.put(keys[i], d);
        }
        return envelope("obj", map.toString());
    }

    /** PUT /user/api/v2/users/{userId}/daily/sign/in — claim today's slot, award golds. */
    private static String clickSignIn(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        String date = today();
        if (!store.hasSignedIn(u, date)) {
            int[] rewards = {200, 400, 600, 800, 1000, 1500, 3000};
            int claimed = store.signIns(u) == null ? 0 : store.signIns(u).length();
            long reward = rewards[claimed % 7];
            store.markSignedIn(u, date);
            store.award(u, "golds", reward);
            L.i("sign-in: userId=" + u.optLong("userId") + " +" + reward + " golds");
        }
        return envelope("none", null);
    }

    /** PUT /user/api/v1/users/{userId}/daily/tasks/ads — award 200 golds (cap 5/day). */
    private static String getAdsReward(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        String date = today();
        if (store.adRewardCount(u, date) < 5) {
            store.countAdReward(u, date);
            store.award(u, "golds", 200);
        }
        JSONObject r = new JSONObject();
        r.put("userId", u.optLong("userId"));
        r.put("currency", 1);
        r.put("golds", u.optLong("golds"));
        r.put("diamonds", u.optLong("diamonds"));
        r.put("gDiamonds", u.optLong("gDiamonds"));
        r.put("gDiamondsProfit", 0);
        r.put("money", 0);
        r.put("rewardQuantity", 200);
        return envelope("obj", r.toString());
    }

    /** PUT /user/api/v1/users/daily/sign/ads — AdsSignReward, award 300 golds (cap 3/day). */
    private static String getSignAdsReward(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        String date = today();
        int count = store.adRewardCount(u, date);
        long quantity = count < 3 ? 300 : 0;
        if (count < 3) {
            store.countAdReward(u, date);
            store.award(u, "golds", quantity);
        }
        JSONObject a = new JSONObject();
        a.put("picUrl", "");
        a.put("quantity", quantity);
        return envelope("obj", a.toString());
    }

    /** GET /friend/api/v1/friends/recommendation[/new] — real users + citizens. */
    private static String friendRecommendation(Ctx ctx, StateStore store) {
        JSONObject me = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray out = new JSONArray();
        // other real accounts first (real players)
        JSONObject users = store.root().optJSONObject("users");
        JSONArray names = users.names();
        if (names != null) {
            for (int i = 0; i < names.length() && out.length() < 20; i++) {
                JSONObject u = users.optJSONObject(names.optString(i));
                if (u == null || u.optLong("userId") == me.optLong("userId")) continue;
                out.put(recommendRow(u.optLong("userId"), u.optString("nickName"),
                        u.optInt("sex"), "", u.optInt("vip")));
            }
        }
        // then citizens (the persistent local-world population)
        JSONArray citizens = GameCatalog.citizens(store);
        for (int i = 0; i < citizens.length() && out.length() < 30; i++) {
            JSONObject c = citizens.getJSONObject(i);
            out.put(recommendRow(c.optLong("userId"), c.optString("nickName"),
                    c.optInt("sex"), c.optString("country"), c.optInt("vip")));
        }
        return envelope("list", out.toString());
    }

    private static JSONObject recommendRow(long userId, String nickName, int sex,
                                           String country, int vip) {
        JSONObject r = new JSONObject();
        r.put("userId", userId);
        r.put("nickName", nickName);
        r.put("headPic", "");
        r.put("sex", sex);
        r.put("country", country);
        r.put("language", "en");
        r.put("vip", vip);
        r.put("gameId", new JSONArray());
        r.put("likeGames", new JSONArray());
        r.put("togetherGames", new JSONArray());
        r.put("searchById", false);
        return r;
    }

    /** GET /user/api/v1/user/player/info — BuyVipEntity. */
    private static String getVipInfo(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONObject v = new JSONObject();
        v.put("vip", u.optInt("vip"));
        v.put("expireDate", u.optString("expireDate"));
        v.put("gDiamonds", u.optLong("gDiamonds"));
        return envelope("obj", v.toString());
    }

    /** GET /pay/api/v1/sub/info/get — VipSubInfo (no subscriptions locally). */
    private static String getSubscribeInfo(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONObject p = new JSONObject();
        p.put("vip", u.optInt("vip"));
        p.put("expireDate", u.optString("expireDate"));
        for (String s : new String[]{"1", "2", "3", "4"}) {
            p.put("vip" + s + "ExpiredAt", "");
            p.put("vip" + s + "ExpiredAtStr", "");
        }
        JSONObject sub = new JSONObject();
        sub.put("playerInfo", p);
        sub.put("subInfo", new JSONArray());
        return envelope("obj", sub.toString());
    }

    // ------------------------------------------------- Phase 2 helpers

    /** PageData envelope over the catalog; wrapType selects TypePageData{pageInfo,typeId}. */
    private static String pageEnvelope(StateStore store, String sort, long typeId, boolean ugcOnly,
                                       int pageNo, int pageSize, boolean wrapType) {
        int size = pageSize > 0 ? pageSize : 20;
        JSONArray data = GameCatalog.page(store, sort, typeId, ugcOnly, pageNo, size);
        int total = GameCatalog.count(store, sort, typeId, ugcOnly);
        JSONObject page = new JSONObject();
        page.put("data", data);
        page.put("pageNo", pageNo);
        page.put("pageSize", size);
        page.put("totalPage", totalPages(total, size));
        page.put("totalSize", total);
        if (wrapType) {
            // TypePageData shape: {pageInfo, typeId} — typeId echoed so the
            // client can file games into its local cache correctly.
            JSONObject t = new JSONObject();
            t.put("pageInfo", page);
            t.put("typeId", typeId);
            return envelope("obj", t.toString());
        }
        return envelope("obj", page.toString());
    }

    /** Empty-but-valid PageData for list-first social endpoints. */
    private static String emptyPage(int pageSize) {
        JSONObject page = new JSONObject();
        page.put("data", new JSONArray());
        page.put("pageNo", 1);
        page.put("pageSize", pageSize);
        page.put("totalPage", 0);
        page.put("totalSize", 0);
        return envelope("obj", page.toString());
    }

    private static int totalPages(int total, int size) {
        return size <= 0 ? 0 : (total + size - 1) / size;
    }

    private static JSONArray slice(JSONArray arr, int pageNo, int pageSize) {
        JSONArray out = new JSONArray();
        int size = pageSize > 0 ? pageSize : 20;
        int from = Math.max(0, (pageNo - 1) * size);
        for (int i = from; i < arr.length() && i < from + size; i++) out.put(arr.get(i));
        return out;
    }

    private static long resolveTypeNameToId(StateStore store, String typeName) {
        if (typeName == null || typeName.isEmpty()) return 0;
        JSONArray cats = GameCatalog.categories(store);
        for (int i = 0; i < cats.length(); i++) {
            JSONObject c = cats.getJSONObject(i);
            if (typeName.equals(c.optString("typeName")) || typeName.equals(c.optString("sortType"))) {
                return c.optLong("typeId");
            }
        }
        return 0;
    }

    private static String today() {
        java.text.SimpleDateFormat fmt =
                new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US);
        fmt.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
        return fmt.format(new java.util.Date());
    }

    // -------------------------------------------------------------- utils

    static String envelope(String kind, String dataJson) {
        StringBuilder sb = new StringBuilder(64);
        sb.append("{\"code\":1,\"message\":\"").append(OK).append("\"");
        if (dataJson != null) {
            sb.append(",\"data\":").append(dataJson);
        } else if ("list".equals(kind)) {
            sb.append(",\"data\":[]");
        } else if ("str".equals(kind)) {
            sb.append(",\"data\":\"\"");
        } else if ("num".equals(kind)) {
            sb.append(",\"data\":0");
        } else if ("bool".equals(kind)) {
            sb.append(",\"data\":false");
        } else if ("obj".equals(kind)) {
            sb.append(",\"data\":{}");
        }
        // "none" -> no data field at all
        sb.append("}");
        return sb.toString();
    }

    private static String userEnvelope(JSONObject u) {
        return envelope("obj", storelessUserJson(u));
    }

    private static String storelessUserJson(JSONObject u) {
        // delegate to StateStore serializer without needing the store reference
        return userJsonLocal(u);
    }

    private static String userJsonLocal(JSONObject u) {
        JSONObject out = new JSONObject();
        out.put("userId", u.optLong("userId"));
        out.put("account", u.optString("account"));
        out.put("nickName", u.optString("nickName"));
        out.put("sex", u.optInt("sex"));
        out.put("picUrl", u.optString("picUrl"));
        out.put("accessToken", u.optString("accessToken"));
        out.put("details", u.optString("details"));
        out.put("telephone", u.optString("telephone"));
        out.put("email", u.optString("email"));
        out.put("birthday", u.optString("birthday"));
        out.put("golds", u.optLong("golds"));
        out.put("diamonds", u.optLong("diamonds"));
        out.put("gDiamonds", u.optLong("gDiamonds"));
        out.put("password", u.optString("password"));
        out.put("isFirstLogin", u.optBoolean("isFirstLogin"));
        out.put("expireDate", u.optString("expireDate"));
        out.put("vip", u.optInt("vip"));
        out.put("hasPassword", u.optBoolean("hasPassword"));
        out.put("platform", u.optString("platform"));
        out.put("starCode", u.optString("starCode"));
        return out.toString();
    }

    private static String bool(boolean b) {
        return envelope("bool", b ? "true" : "false");
    }

    private static String fail(String message) {
        return "{\"code\":0,\"message\":\"" + message + "\"}";
    }

    private static JSONObject body(Ctx ctx) {
        String raw = ctx.body();
        if (raw == null) raw = "";
        raw = raw.trim();
        if (raw.isEmpty()) return new JSONObject();
        try {
            return new JSONObject(raw);
        } catch (Throwable t) {
            L.e("body is not JSON (" + abbrev(raw) + "): " + t);
            return new JSONObject();
        }
    }

    private static long parseLong(String s, long def) {
        try {
            return Long.parseLong(s.trim());
        } catch (Throwable t) {
            return def;
        }
    }

    static String abbrev(String s) {
        if (s == null) return "";
        return s.length() <= 120 ? s : s.substring(0, 120) + "...(" + s.length() + "b)";
    }
}
