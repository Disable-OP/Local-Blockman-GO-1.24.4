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

        /** All values of a repeated query parameter (Retrofit String[] expansion). */
        java.util.List<String> queryValues(String name);

        String header(String name);

        String body();

        String pathParam(String name);

        /** Raw request URI (no query string). */
        String path();
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
        // ---- Phase 3: decoration / dress shop / scrap exchange ----
        if ("dressList".equals(name)) return dressList(ctx, store);
        if ("friendUsingList".equals(name)) return friendUsingList(ctx, store);
        if ("dressExpireList".equals(name)) return envelope("list", "[]");
        if ("dressOwnedByType".equals(name)) return dressOwnedByType(ctx, store);
        if ("dressSuitList".equals(name)) return envelope("list", "[]");
        if ("dressRecommend".equals(name)) return dressRecommend(ctx, store);
        if ("isUsingList".equals(name)) return isUsingList(ctx, store);
        if ("dressGuideConfig".equals(name)) return envelope("obj", "{\"dressShopGuideConfigMap\":{}}");
        if ("multiClothe".equals(name)) return multiClothe(ctx, store);
        if ("multiUnclothe".equals(name)) return multiUnclothe(ctx, store);
        if ("removeDecoration".equals(name)) return removeDecoration(ctx, store);
        if ("removeSuitDecoration".equals(name)) return removeSuitDecoration(ctx, store);
        if ("useDecoration".equals(name)) return useDecoration(ctx, store);
        if ("useSuitDecoration".equals(name)) return useSuitDecoration(ctx, store);
        if ("vipDress".equals(name)) return envelope("list", "[]");
        if ("dressResCheck".equals(name)) return envelope("obj", "{\"md5\":\"\",\"update\":false,\"url\":\"\"}");
        if ("dressCheckResource".equals(name)) return envelope("obj", "{\"needUpdate\":false,\"cdns\":[],\"fileCount\":0,\"fileSize\":0,\"hash\":\"\",\"url\":\"\",\"version\":1}");
        if ("dressBuyOne".equals(name)) return dressBuyOne(ctx, store);
        if ("dressBuyMany".equals(name)) return dressBuyMany(ctx, store);
        if ("dressBuyV2".equals(name)) return dressBuyV2(ctx, store);
        if ("dressDetails".equals(name)) return dressDetails(ctx, store);
        if ("dressRecommendList".equals(name)) return dressRecommendList(ctx, store);
        if ("shopList".equals(name)) return shopList(ctx, store);
        if ("shopRecommendV2".equals(name)) return shopRecommendV2(ctx, store);
        if ("giftSuitCanReceive".equals(name)) return envelope("bool", "false");
        if ("scrapBackpack".equals(name)) return scrapBackpack(ctx, store);
        if ("scrapCombineNum".equals(name)) return envelope("num", "3");
        if ("scrapRequestTargets".equals(name)) return scrapRequestTargets(ctx, store);
        if ("scrapRewardValue".equals(name)) return envelope("num", "3000");
        if ("scrapBagValue".equals(name)) return scrapBagValue(ctx, store);
        if ("scrapHistory".equals(name)) return scrapHistory(ctx, store);
        if ("scrapNum".equals(name)) return scrapNum(ctx, store);
        if ("scrapCardDetails".equals(name)) return scrapCardDetails(ctx, store);
        if ("scrapCardList".equals(name)) return scrapCardList(ctx, store);
        if ("scrapRule".equals(name)) return envelope("list", "[\"Collect scraps in the local world.\",\"Combine them into cards.\",\"Exchange cards for golds.\"]");
        if ("scrapTreasureBox".equals(name)) return envelope("obj", "{\"boxList\":[],\"date\":\"\",\"probsNum\":0,\"rewardValue\":0,\"secondsLeft\":0}");
        if ("scrapVipConvert".equals(name)) return envelope("obj", "{\"newVip\":{},\"vip\":{}}");
        if ("scrapCombineCard".equals(name)) return scrapCombineCard(ctx, store);
        if ("scrapAsk".equals(name)) return envelope("none", null);
        if ("scrapReceive".equals(name)) return envelope("none", null);
        if ("scrapSend".equals(name)) return scrapSend(ctx, store);
        // ---- Phase 3.5: rankings from the local world + mailbox + tribe states ----
        if ("rankingPage".equals(name)) return rankingPage(name, ctx, store);
        if ("mailList".equals(name)) return envelope("list", "[]");
        if ("mailOp".equals(name)) return envelope("list", "[]");
        // ---- Phase 4: tribe (clan) real state ----
        if ("tribeId".equals(name)) return tribeId(ctx, store);
        if ("tribeDetail".equals(name)) return tribeDetail(ctx, store);
        if ("tribeBaseInfo".equals(name)) return tribeBaseInfo(ctx, store);
        if ("tribeMemberList".equals(name)) return tribeMemberList(ctx, store);
        if ("clanCreate".equals(name)) return clanCreate(ctx, store);
        if ("clanUpdate".equals(name)) return clanUpdate(ctx, store);
        if ("clanDissolve".equals(name)) return clanDissolve(ctx, store);
        if ("clanExit".equals(name)) return clanExit(ctx, store);
        if ("clanKick".equals(name)) return clanKick(ctx, store);
        if ("clanJoin".equals(name)) return clanJoin(ctx, store);
        if ("clanAgreeJoin".equals(name)) return clanAgreeJoin(ctx, store);
        if ("clanRejectJoin".equals(name)) return clanRejectJoin(ctx, store);
        if ("clanAgreeInvite".equals(name)) return clanAgreeInvite(ctx, store);
        if ("clanRejectInvite".equals(name)) return clanRejectInvite(ctx, store);
        if ("clanInvite".equals(name)) return clanInvite(ctx, store);
        if ("clanSetIdentity".equals(name)) return clanSetIdentity(ctx, store);
        if ("tribeMessageList".equals(name)) return tribeMessageList(ctx, store);
        if ("tribeBulletinGet".equals(name)) return tribeBulletinGet(ctx, store);
        if ("tribeBulletinPost".equals(name)) return tribeBulletinPost(ctx, store);
        if ("tribeDonationInfo".equals(name)) return tribeDonationInfo(ctx, store);
        if ("tribeDonate".equals(name)) return tribeDonate(ctx, store);
        if ("tribeDonationHistory".equals(name)) return tribeDonationHistory(ctx, store);
        if ("tribeCurrency".equals(name)) return tribeCurrency(ctx, store);
        if ("tribeRank".equals(name)) return tribeRank(ctx, store);
        if ("tribeUserRank".equals(name)) return tribeUserRank(ctx, store);
        if ("tribeRecommend".equals(name)) return tribeRecommend(ctx, store);
        if ("tribeSearch".equals(name)) return tribeSearch(ctx, store);
        if ("tribeTasks".equals(name)) return tribeTasks(ctx, store, 1);
        if ("tribePersonalTasks".equals(name)) return tribeTasks(ctx, store, 2);
        if ("tribeTaskAccept".equals(name)) return tribeTaskAction(ctx, store, false);
        if ("tribeTaskReward".equals(name)) return tribeTaskAction(ctx, store, true);
        if ("tribeShopList".equals(name)) return tribeShopList(ctx, store);
        if ("tribeShopDetail".equals(name)) return tribeShopDetail(ctx, store);
        if ("tribeShopBuy".equals(name)) return tribeShopBuy(ctx, store);
        if ("clanFreeVerify".equals(name)) return clanFreeVerify(ctx, store);
        // ---- Phase 3.6: profile/team odds and ends ----
        if ("nickNameFree".equals(name)) return envelope("obj", "{\"currencyType\":1,\"free\":true,\"quantity\":0}");
        if ("frequentlyGames".equals(name)) return frequentlyGames(ctx, store);
        if ("teamMembers".equals(name)) return teamMembers(ctx, store);
        if ("dressAdsInfo".equals(name)) return envelope("obj", "{\"adType\":1,\"currency\":1,\"nextCurrency\":1,\"qty\":0,\"nextQty\":100,\"status\":0}");
        if ("dressAdsReward".equals(name)) return envelope("obj", "{\"picUrl\":\"\",\"quantity\":150}");
        // ---- Phase 3.7: local wallet + pay products (no real money) ----
        if ("wallet".equals(name)) return wallet(ctx, store);
        if ("payHistory".equals(name)) return payHistory(ctx, store);
        if ("products".equals(name)) return products(ctx, store);
        if ("recharge".equals(name)) return recharge(ctx, store);
        if ("rechargeVip".equals(name)) return rechargeVip(ctx, store);
        if ("firstTopReward".equals(name)) return envelope("obj", "{\"status\":1,\"rewardList\":[]}");
        if ("thirdPayFlag".equals(name)) return envelope("bool", "false");
        if ("payssionSignature".equals(name)) return payssionSignature(ctx, store);
        if ("vipProducts".equals(name)) return envelope("obj", "{\"expireDate\":\"\",\"vip\":0,\"products\":{}}");
        if ("thirdPayList".equals(name)) return envelope("obj", "{\"show\":false,\"payChannel\":[],\"currency\":\"\"}");
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
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
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
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
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
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
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

    // ------------------------------- Phase 3: decoration + dress shop

    private static String dressList(Ctx ctx, StateStore store) {
        long typeId = parseLong(ctx.pathParam("typeId"), 0);
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray list = DressShop.ensureType(store, typeId);
        JSONArray out = new JSONArray();
        for (int i = 0; i < list.length(); i++) {
            out.put(DressShop.singleJson(store, u, list.getJSONObject(i)));
        }
        return envelope("list", out.toString());
    }

    private static String friendUsingList(Ctx ctx, StateStore store) {
        long otherId = parseLong(ctx.pathParam("otherId"), 0);
        JSONObject other = store.findByUserId(otherId);
        if (other == null) {
            other = store.findOrCreateByKey("ghost", true);
        }
        return envelope("list", DressShop.usingList(store, other).toString());
    }

    private static String dressOwnedByType(Ctx ctx, StateStore store) {
        long typeId = parseLong(ctx.pathParam("typeId"), 0);
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray list = DressShop.ensureType(store, typeId);
        JSONArray out = new JSONArray();
        for (int i = 0; i < list.length(); i++) {
            JSONObject d = list.getJSONObject(i);
            if (DressShop.owned(store, u, d.optLong("id"))) {
                out.put(DressShop.singleJson(store, u, d));
            }
        }
        return envelope("list", out.toString());
    }

    private static String dressRecommend(Ctx ctx, StateStore store) {
        long typeId = parseLong(ctx.pathParam("typeId"), 0);
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray list = DressShop.ensureType(store, typeId);
        JSONArray out = new JSONArray();
        for (int i = 0; i < list.length() && out.length() < 5; i++) {
            JSONObject d = list.getJSONObject(i);
            if (!DressShop.owned(store, u, d.optLong("id"))) {
                JSONObject row = new JSONObject();
                row.put("id", d.optLong("id"));
                row.put("iconUrl", "");
                row.put("hasPurchase", 0);
                row.put("isNew", d.optInt("isNew"));
                row.put("shopDecorationInfo", DressShop.singleJson(store, u, d));
                out.put(row);
            }
        }
        return envelope("list", out.toString());
    }

    private static String isUsingList(Ctx ctx, StateStore store) {
        long otherId = parseLong(ctx.query("otherId"), 0);
        JSONObject target = otherId > 0
                ? (store.findByUserId(otherId) != null
                   ? store.findByUserId(otherId) : store.findOrCreateByKey("ghost", true))
                : store.resolve(ctx.header("access-token"), ctx.header("userid"));
        return envelope("list", DressShop.usingList(store, target).toString());
    }

    private static JSONArray csvIds(String csv) {
        JSONArray ids = new JSONArray();
        if (csv != null) {
            for (String s : csv.split(",")) {
                long v = parseLong(s.trim(), 0);
                if (v > 0) ids.put(v);
            }
        }
        return ids;
    }

    private static String multiClothe(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray ids = csvIds(ctx.query("ids"));
        DressShop.setUsing(store, u, ids, true);
        JSONArray out = new JSONArray();
        for (int i = 0; i < ids.length(); i++) {
            JSONObject d = DressShop.byId(store, ids.optLong(i));
            if (d != null) out.put(DressShop.singleJson(store, u, d));
        }
        return envelope("list", out.toString());
    }

    private static String multiUnclothe(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray ids = csvIds(ctx.query("ids"));
        DressShop.setUsing(store, u, ids, false);
        return envelope("obj", null);
    }

    private static String removeDecoration(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        long id = parseLong(ctx.pathParam("decorationId"), 0);
        JSONArray one = new JSONArray();
        one.put(id);
        DressShop.setUsing(store, u, one, false);
        JSONObject d = DressShop.byId(store, id);
        return d == null ? fail("decoration not found")
                : envelope("obj", DressShop.singleJson(store, u, d).toString());
    }

    private static String removeSuitDecoration(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray ids = csvIds(ctx.query("ids"));
        DressShop.setUsing(store, u, ids, false);
        JSONArray out = new JSONArray();
        for (int i = 0; i < ids.length(); i++) {
            JSONObject d = DressShop.byId(store, ids.optLong(i));
            if (d != null) out.put(DressShop.singleJson(store, u, d));
        }
        return envelope("list", out.toString());
    }

    private static String useDecoration(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
        long id = parseLong(ctx.pathParam("decorationId"), 0);
        if (!DressShop.owned(store, u, id)) {
            return fail("decoration not owned");
        }
        JSONArray one = new JSONArray();
        one.put(id);
        DressShop.setUsing(store, u, one, true);
        JSONObject d = DressShop.byId(store, id);
        return envelope("obj", DressShop.singleJson(store, u, d).toString());
    }

    private static String useSuitDecoration(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
        JSONArray ids = csvIds(ctx.query("ids"));
        for (int i = 0; i < ids.length(); i++) {
            if (!DressShop.owned(store, u, ids.optLong(i))) {
                return fail("decoration not owned: " + ids.optLong(i));
            }
        }
        DressShop.setUsing(store, u, ids, true);
        JSONArray out = new JSONArray();
        for (int i = 0; i < ids.length(); i++) {
            JSONObject d = DressShop.byId(store, ids.optLong(i));
            if (d != null) out.put(DressShop.singleJson(store, u, d));
        }
        return envelope("list", out.toString());
    }

    private static String dressBuyOne(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
        long id = parseLong(ctx.pathParam("decorationId"), 0);
        if (!DressShop.buy(store, u, id)) {
            return fail("insufficient currency or unknown decoration");
        }
        return envelope("none", null);
    }

    private static String dressBuyMany(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
        JSONArray ids = csvIds(ctx.query("decorationId"));
        JSONArray ok = new JSONArray();
        long golds = 0, diamonds = 0;
        for (int i = 0; i < ids.length(); i++) {
            JSONObject d = DressShop.byId(store, ids.optLong(i));
            if (d == null) continue;
            if (d.optInt("currency") == 2) diamonds += d.optLong("price");
            else golds += d.optLong("price");
        }
        if (u.optLong("golds") >= golds && u.optLong("diamonds") >= diamonds) {
            for (int i = 0; i < ids.length(); i++) {
                if (DressShop.buy(store, u, ids.optLong(i))) ok.put(ids.optLong(i));
            }
        }
        return envelope("obj", DressShop.buyResponse(ids, ok, golds, diamonds).toString());
    }

    private static String dressBuyV2(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
        JSONObject form = body(ctx);
        JSONArray items = form.optJSONArray("buyDecorationList");
        JSONArray ids = new JSONArray();
        if (items != null) {
            for (int i = 0; i < items.length(); i++) {
                ids.put(items.optJSONObject(i).optLong("decorationId"));
            }
        }
        JSONArray ok = new JSONArray();
        long golds = 0, diamonds = 0;
        for (int i = 0; i < ids.length(); i++) {
            JSONObject d = DressShop.byId(store, ids.optLong(i));
            if (d == null) continue;
            if (d.optInt("currency") == 2) diamonds += d.optLong("price");
            else golds += d.optLong("price");
        }
        if (u.optLong("golds") >= golds && u.optLong("diamonds") >= diamonds) {
            for (int i = 0; i < ids.length(); i++) {
                if (DressShop.buy(store, u, ids.optLong(i))) ok.put(ids.optLong(i));
            }
        }
        return envelope("obj", DressShop.buyResponse(ids, ok, golds, diamonds).toString());
    }

    private static String dressDetails(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONObject d = DressShop.byId(store, parseLong(ctx.pathParam("decorationId"), 0));
        return d == null ? fail("decoration not found")
                : envelope("obj", DressShop.singleJson(store, u, d).toString());
    }

    private static String dressRecommendList(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONObject base = DressShop.byId(store, parseLong(ctx.pathParam("decorationId"), 0));
        long typeId = base == null ? 0 : base.optLong("typeId");
        JSONArray list = DressShop.ensureType(store, typeId);
        JSONArray out = new JSONArray();
        for (int i = 0; i < list.length() && out.length() < 6; i++) {
            JSONObject d = list.getJSONObject(i);
            if (d.optLong("id") != (base == null ? -1 : base.optLong("id"))) {
                out.put(DressShop.singleJson(store, u, d));
            }
        }
        return envelope("list", out.toString());
    }

    private static String shopList(Ctx ctx, StateStore store) {
        return dressList(ctx, store);
    }

    private static String shopRecommendV2(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONObject all = store.root().optJSONObject("dresses");
        JSONArray out = new JSONArray();
        if (all != null) {
            JSONArray keys = all.names();
            if (keys != null) {
                for (int k = 0; k < keys.length() && out.length() < 6; k++) {
                    JSONArray list = all.optJSONArray(keys.optString(k));
                    if (list == null || list.length() == 0) continue;
                    JSONObject d = list.getJSONObject(0);
                    JSONObject row = new JSONObject();
                    row.put("id", d.optLong("id"));
                    row.put("iconUrl", "");
                    row.put("hasPurchase", 0);
                    row.put("isNew", d.optInt("isNew"));
                    row.put("shopDecorationInfo", DressShop.singleJson(store, u, d));
                    out.put(row);
                }
            }
        }
        return envelope("list", out.toString());
    }

    // --------------------------------------- Phase 3: scrap exchange

    private static String scrapBackpack(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONObject bag = ScrapBag.backpack(store, u);
        JSONArray out = new JSONArray();
        JSONArray keys = bag.names();
        if (keys != null) {
            for (int i = 0; i < keys.length(); i++) {
                String sid = keys.optString(i);
                int amount = bag.optInt(sid);
                if (amount <= 0) continue;
                JSONObject s = new JSONObject();
                s.put("scrapId", sid);
                s.put("scrapName", "Scrap " + sid.toUpperCase());
                s.put("scrapDesc", "A fragment used for exchange.");
                s.put("scrapPic", "");
                s.put("scrapLevel", 1);
                s.put("scrapType", 1);
                s.put("scrapValue", ScrapBag.valueOf(sid));
                s.put("amount", amount);
                s.put("rewardType", 1);
                out.put(s);
            }
        }
        JSONObject page = new JSONObject();
        page.put("data", out);
        page.put("pageNo", 1);
        page.put("pageSize", 20);
        page.put("totalPage", 1);
        page.put("totalSize", out.length());
        return envelope("obj", page.toString());
    }

    private static String scrapRequestTargets(Ctx ctx, StateStore store) {
        JSONArray citizens = GameCatalog.citizens(store);
        JSONArray out = new JSONArray();
        for (int i = 0; i < citizens.length() && out.length() < 10; i++) {
            JSONObject c = citizens.getJSONObject(i);
            JSONObject t = new JSONObject();
            t.put("friendId", c.optLong("userId"));
            t.put("friendName", c.optString("nickName"));
            t.put("friendPic", "");
            t.put("helpStatus", 0);
            t.put("scrapNum", 1 + (i % 3));
            out.put(t);
        }
        JSONObject page = new JSONObject();
        page.put("data", out);
        page.put("pageNo", 1);
        page.put("pageSize", 10);
        page.put("totalPage", 1);
        page.put("totalSize", out.length());
        return envelope("obj", page.toString());
    }

    private static String scrapBagValue(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        return envelope("num", String.valueOf(ScrapBag.bagValue(store, u)));
    }

    private static String scrapHistory(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray hist = store.userState(u).optJSONArray("combineHistory");
        JSONArray data = hist == null ? new JSONArray() : hist;
        JSONObject page = new JSONObject();
        page.put("data", data);
        page.put("pageNo", 1);
        page.put("pageSize", 20);
        page.put("totalPage", data.length() > 0 ? 1 : 0);
        page.put("totalSize", data.length());
        return envelope("obj", page.toString());
    }

    private static String scrapNum(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        return envelope("num", String.valueOf(
                ScrapBag.scrapNum(store, u, ctx.pathParam("scrapId"))));
    }

    private static String scrapCardDetails(Ctx ctx, StateStore store) {
        JSONObject card = ScrapBag.card(ctx.query("cardId"));
        if (card == null) {
            return fail("card not found");
        }
        JSONObject d = new JSONObject();
        d.put("cardName", card.optString("cardName"));
        d.put("cardDesc", "Collect the listed scraps, then combine.");
        d.put("cardPic", "");
        d.put("cardValue", card.optInt("cardValue"));
        d.put("scrapResponses", card.optJSONArray("needs"));
        return envelope("obj", d.toString());
    }

    private static String scrapCardList(Ctx ctx, StateStore store) {
        JSONArray out = new JSONArray();
        for (int n = 1; n <= 6; n++) {
            JSONObject card = ScrapBag.card("c" + n);
            if (card == null) continue;
            JSONObject row = new JSONObject();
            row.put("cardId", card.optString("cardId"));
            row.put("cardName", card.optString("cardName"));
            row.put("cardPic", "");
            row.put("cardProgress", "0/" + card.optJSONArray("needs").optJSONObject(0).optInt("scrapNum"));
            row.put("cardQuality", card.optInt("cardQuality"));
            row.put("cardRewardType", 1);
            row.put("rewardExpires", 0);
            row.put("status", 0);
            out.put(row);
        }
        JSONObject page = new JSONObject();
        page.put("data", out);
        page.put("pageNo", 1);
        page.put("pageSize", 20);
        page.put("totalPage", 1);
        page.put("totalSize", out.length());
        return envelope("obj", page.toString());
    }

    private static String scrapCombineCard(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
        String cardId = ctx.query("cardId");
        int amount = (int) parseLong(ctx.query("amount"), 1);
        JSONObject out = ScrapBag.combine(store, u, cardId, amount);
        return out == null ? fail("not enough scraps or unknown card")
                : envelope("obj", out.toString());
    }

    private static String scrapSend(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
        String scrapId = ctx.query("scrapId");
        if (ScrapBag.scrapNum(store, u, scrapId) < 1) {
            return fail("no scrap to send");
        }
        ScrapBag.addScrap(store, u, scrapId, -1);
        return envelope("str", JSONObject.quote(
                "send-" + Long.toHexString(System.nanoTime())));
    }

    // ------------------------- Phase 3.5: rankings / mailbox / tribe

    /**
     * All /ranking/api/v1/{board}/rank pages. Rows are DERIVED state:
     * real users ranked by their actual wallets/claims, padded with the
     * persistent citizens pool so every board has a living top-100.
     */
    private static String rankingPage(String handlerName, Ctx ctx, StateStore store) {
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        String p = ctx.path() == null ? "" : ctx.path();
        String board = p.startsWith("/ranking/api/v1/")
                ? p.substring("/ranking/api/v1/".length()) : "active";
        if (board.endsWith("/rank")) {
            board = board.substring(0, board.length() - "/rank".length());
        }
        boolean weekly = board.contains("weekly");
        JSONArray rows = new JSONArray();
        // real accounts first
        JSONObject users = store.root().optJSONObject("users");
        JSONArray keys = users.names();
        if (keys != null) {
            for (int i = 0; i < keys.length(); i++) {
                JSONObject u = users.optJSONObject(keys.optString(i));
                if (u == null) continue;
                long qty = board.contains("gold/diamond")
                        ? u.optLong("diamonds") : u.optLong("golds");
                if (weekly) qty = qty / 7 + 10;
                JSONObject r = new JSONObject();
                r.put("id", u.optLong("userId"));
                r.put("name", u.optString("nickName"));
                r.put("pic", u.optString("picUrl"));
                r.put("quantity", qty);
                rows.put(r);
            }
        }
        // citizens fill the board (deterministic per board name)
        JSONArray citizens = GameCatalog.citizens(store);
        int seed = Math.abs(board.hashCode());
        for (int i = 0; i < citizens.length(); i++) {
            JSONObject c = citizens.getJSONObject(i);
            long base = board.contains("gold/diamond") ? 40_000 : 9_000;
            long qty = base - ((seed + i * 977) % base) + (weekly ? 0 : i);
            if (qty < 1) qty = 1;
            JSONObject r = new JSONObject();
            r.put("id", c.optLong("userId"));
            r.put("name", c.optString("nickName"));
            r.put("pic", c.optString("headPic"));
            r.put("quantity", qty);
            rows.put(r);
        }
        // sort desc by quantity + assign rank
        for (int i = 1; i < rows.length(); i++) {
            JSONObject key = rows.getJSONObject(i);
            int j = i - 1;
            while (j >= 0 && rows.getJSONObject(j).optLong("quantity") < key.optLong("quantity")) {
                rows.put(j + 1, rows.getJSONObject(j));
                j--;
            }
            rows.put(j + 1, key);
        }
        for (int i = 0; i < rows.length(); i++) {
            rows.getJSONObject(i).put("rank", i + 1);
        }
        JSONArray slice = slice(rows, pageNo, pageSize);
        JSONObject page = new JSONObject();
        page.put("data", slice);
        page.put("pageNo", pageNo);
        page.put("pageSize", pageSize);
        page.put("totalPage", totalPages(rows.length(), pageSize));
        page.put("totalSize", rows.length());
        return envelope("obj", page.toString());
    }

    // ------------------------- Phase 3.6: profile/team odds and ends

    /** GET /user/api/v1/data/frequently/game/{userId} — played history, else catalog. */
    private static String frequentlyGames(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray ids = store.recentGames(u, 8);
        JSONArray out = new JSONArray();
        for (int i = 0; i < ids.length(); i++) {
            JSONObject g = GameCatalog.byId(store, ids.optString(i));
            if (g != null) out.put(g);
        }
        if (out.length() == 0) {
            out = GameCatalog.page(store, "online", 0, false, 1, 8);
        }
        return envelope("list", out.toString());
    }

    /** GET /game/api/v1/games/team/member/{teamId} — AuthorInfo rows from citizens. */
    private static String teamMembers(Ctx ctx, StateStore store) {
        long teamId = parseLong(ctx.pathParam("teamId"), 0);
        JSONArray citizens = GameCatalog.citizens(store);
        JSONArray out = new JSONArray();
        for (int i = 0; i < citizens.length() && out.length() < 8; i++) {
            JSONObject c = citizens.getJSONObject(i);
            JSONObject a = new JSONObject();
            a.put("userId", c.optLong("userId"));
            a.put("nickName", c.optString("nickName"));
            a.put("headPic", c.optString("headPic"));
            a.put("teamId", teamId);
            a.put("isTeam", i == 0 ? 1 : 0);
            a.put("isAddFriend", 0);
            a.put("isLast", i == Math.min(8, citizens.length()) - 1);
            out.put(a);
        }
        return envelope("list", out.toString());
    }

    // ------------------- Phase 3.7: local wallet + pay products

    /** GET /pay/api/v1/wealth/user — RechargeEntity of the CURRENT wallet. */
    private static String wallet(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        return envelope("obj", rechargeEntity(u, 0).toString());
    }

    private static JSONObject rechargeEntity(JSONObject u, long rewardQuantity) {
        JSONObject r = new JSONObject();
        r.put("userId", u.optLong("userId"));
        r.put("currency", 1);
        r.put("golds", u.optLong("golds"));
        r.put("diamonds", u.optLong("diamonds"));
        r.put("gDiamonds", u.optLong("gDiamonds"));
        r.put("gDiamondsProfit", 0);
        r.put("money", 0);
        r.put("rewardQuantity", rewardQuantity);
        return r;
    }

    /** GET /pay/api/v1/wealth/record/users/{userId} — persisted pay records. */
    private static String payHistory(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONArray recs = store.userState(u).optJSONArray("payRecords");
        JSONArray data = recs == null ? new JSONArray() : recs;
        JSONObject page = new JSONObject();
        page.put("data", data);
        page.put("pageNo", 1);
        page.put("pageSize", 20);
        page.put("totalPage", data.length() > 0 ? 1 : 0);
        page.put("totalSize", data.length());
        return envelope("obj", page.toString());
    }

    /** Generate (once) the local product catalog: gold/diamond packs + VIP. */
    private static synchronized JSONArray ensureProducts(StateStore store) {
        JSONArray prods = store.root().optJSONArray("products");
        if (prods != null) return prods;
        prods = new JSONArray();
        Object[][] defs = {
                {"local.golds.1", "Pouch of Golds", 1, 1000, 0.99, 0},
                {"local.golds.2", "Bag of Golds", 1, 5500, 4.99, 0},
                {"local.golds.3", "Chest of Golds", 1, 12000, 9.99, 500},
                {"local.diamonds.1", "Handful of Diamonds", 2, 80, 0.99, 0},
                {"local.diamonds.2", "Case of Diamonds", 2, 500, 4.99, 50},
                {"local.diamonds.3", "Vault of Diamonds", 2, 1200, 9.99, 120},
                {"local.vip.1", "VIP Level 1 (30 days)", 0, 0, 2.99, 0},
                {"local.vip.2", "VIP Level 2 (30 days)", 0, 0, 4.99, 0},
        };
        for (int i = 0; i < defs.length; i++) {
            Object[] d = defs[i];
            JSONObject p = new JSONObject();
            p.put("id", 8001 + i);
            p.put("productId", (String) d[0]);
            p.put("name", d[1]);
            p.put("desc", "Local purchase — credits your wallet instantly.");
            p.put("currency", (int) d[2]);
            p.put("price", (double) d[4]);
            p.put("diamonds", (int) d[3]);
            p.put("golds", (int) d[3]);
            p.put("gift", (int) d[5]);
            p.put("month", ((String) d[0]).startsWith("local.vip") ? 1 : 0);
            p.put("level", ((String) d[0]).equals("local.vip.2") ? 2 : 1);
            p.put("isVip", ((String) d[0]).startsWith("local.vip"));
            p.put("isFree", false);
            p.put("status", 1);
            prods.put(p);
        }
        store.root().put("products", prods);
        store.save();
        return prods;
    }

    /** GET /pay/api/v1/pay/products — List<ProductEntity>. */
    private static String products(Ctx ctx, StateStore store) {
        return envelope("list", ensureProducts(store).toString());
    }

    /** Strict auth for economy-mutating endpoints: token must resolve to a real user. */
    private static JSONObject requireUser(Ctx ctx, StateStore store) {
        return store.findByToken(ctx.header("access-token"));
    }

    private static final String NO_AUTH = "authentication required";

    /** POST /pay/api/v2/pay/users/recharge — credit the sku's currency for real. */
    private static String recharge(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
        JSONObject form = body(ctx);
        String sku = form.optString("sku");
        JSONArray prods = ensureProducts(store);
        JSONObject product = null;
        for (int i = 0; i < prods.length(); i++) {
            if (sku.equals(prods.getJSONObject(i).optString("productId"))) {
                product = prods.getJSONObject(i);
                break;
            }
        }
        if (product == null) {
            return fail("unknown product: " + sku);
        }
        long qty = product.optLong("golds") + product.optLong("diamonds");
        store.award(u, product.optInt("currency") == 2 ? "diamonds" : "golds", qty);
        store.award(u, "gDiamonds", product.optLong("gift"));
        recordPay(store, u, product, qty);
        L.i("recharge: userId=" + u.optLong("userId") + " sku=" + sku + " +" + qty);
        return envelope("obj", rechargeEntity(u, qty).toString());
    }

    /** POST /pay/api/v3|v4/pay/users/recharge — VIP purchase sets vip level. */
    private static String rechargeVip(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) {
            return fail(NO_AUTH);
        }
        JSONObject form = body(ctx);
        String sku = form.optString("sku");
        JSONArray prods = ensureProducts(store);
        for (int i = 0; i < prods.length(); i++) {
            JSONObject product = prods.getJSONObject(i);
            if (sku.equals(product.optString("productId"))) {
                int level = product.optInt("level");
                u.put("vip", Math.max(u.optInt("vip"), level));
                String until = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss",
                        java.util.Locale.US).format(
                        new java.util.Date(System.currentTimeMillis() + 30L * 86_400_000L));
                u.put("expireDate", until);
                store.save();
                JSONObject v = new JSONObject();
                v.put("vip", u.optInt("vip"));
                v.put("expireDate", until);
                v.put("gDiamonds", u.optLong("gDiamonds"));
                recordPay(store, u, product, 0);
                return envelope("obj", v.toString());
            }
        }
        return fail("unknown product: " + sku);
    }

    private static void recordPay(StateStore store, JSONObject u, JSONObject product,
                                  long qty) {
        JSONObject st = store.userState(u);
        JSONArray recs = st.optJSONArray("payRecords");
        if (recs == null) {
            recs = new JSONArray();
            st.put("payRecords", recs);
        }
        java.text.SimpleDateFormat fmt =
                new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.US);
        fmt.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
        JSONObject rec = new JSONObject();
        rec.put("orderId", "local-" + Long.toHexString(System.nanoTime()));
        rec.put("userId", u.optLong("userId"));
        rec.put("description", product.optString("name"));
        rec.put("currency", product.optInt("currency"));
        rec.put("qty", qty > 0 ? qty : 1);
        rec.put("status", 2);
        rec.put("inoutType", 1);
        rec.put("transactionType", 1);
        rec.put("created", fmt.format(new java.util.Date()));
        recs.put(rec);
        store.save();
    }

    private static String payssionSignature(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        JSONObject s = new JSONObject();
        s.put("signature", "");
        s.put("userId", u.optLong("userId"));
        return envelope("obj", s.toString());
    }

    // ------------------------------------------------- Phase 4: tribe (clan)

    /**
     * GET /clan/api/v1/clan/tribe/id — the caller's clanId as a STRING,
     * "0" when clan-less. The client's Tribe tab bootstraps from this
     * (TribeCenter.tribeClanId is set from it).
     */
    private static String tribeId(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        long clanId = u == null ? 0 : u.optLong("clanId");
        return envelope("str", "\"" + clanId + "\"");
    }

    /** GET /clan/api/v2/clan/tribe?clanId= — public detail of any clan. */
    private static String tribeDetail(Ctx ctx, StateStore store) {
        long clanId = parseLong(ctx.query("clanId"), 0);
        JSONObject clan = Tribe.find(store, clanId);
        if (clan == null) return fail("clan not found");
        return envelope("obj", tribeDetailJson(clan).toString());
    }

    /** GET /clan/api/v1/clan/tribe/base — the caller's clan detail. */
    private static String tribeBaseInfo(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        JSONObject clan = Tribe.clanOf(store, u);
        if (clan == null) return fail("not in a clan");
        return envelope("obj", tribeDetailJson(clan).toString());
    }

    /** GET /clan/api/v1/clan/tribe/member — List&lt;TribeMember&gt; of the caller's clan. */
    private static String tribeMemberList(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        JSONObject clan = Tribe.clanOf(store, u);
        if (clan == null) return fail("not in a clan");
        return envelope("list", tribeMembersJson(clan).toString());
    }

    /** POST /clan/api/v2/clan/tribe — create (TribeClanRequest body; currency 1=diamonds fee, else golds). */
    private static String clanCreate(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        JSONObject form = body(ctx);
        String err = Tribe.create(store, u, form.optString("name"), form.optString("details"),
                form.optString("headPic"), form.optJSONArray("tags"), form.optInt("currency", 2));
        if (err != null) return fail(err);
        JSONObject clan = Tribe.clanOf(store, u);
        L.i("clanCreate: userId=" + u.optLong("userId") + " clanId=" + clan.optLong("clanId")
                + " name=" + clan.optString("name"));
        return envelope("obj", clanRequestEcho(clan).toString());
    }

    /** PUT /clan/api/v1/clan/tribe — update name/details/headPic/tags (chief). */
    private static String clanUpdate(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        JSONObject clan = Tribe.clanOf(store, u);
        if (clan == null) return fail("not in a clan");
        if (Tribe.roleOf(clan, u.optLong("userId")) != 20) return fail("only the chief can update");
        JSONObject form = body(ctx);
        String name = form.optString("name", clan.optString("name"));
        if (name != null && !name.trim().isEmpty()) {
            clan.put("name", name.trim().replace("\n", " "));
        }
        if (form.has("details")) clan.put("details", form.optString("details"));
        if (form.has("headPic")) clan.put("headPic", form.optString("headPic"));
        if (form.has("tags")) clan.put("tags", form.optJSONArray("tags"));
        store.save();
        return envelope("obj", clanRequestEcho(clan).toString());
    }

    /** DELETE /clan/api/v1/clan/tribe?clanId= — dissolve (chief). */
    private static String clanDissolve(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        String err = Tribe.dissolve(store, u);
        if (err != null) return fail(err);
        L.i("clanDissolve: userId=" + u.optLong("userId"));
        return envelope("none", null);
    }

    /** DELETE /clan/api/v1/clan/tribe/member?clanId= — leave the clan. */
    private static String clanExit(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        String err = Tribe.exit(store, u);
        if (err != null) return fail(err);
        return envelope("none", null);
    }

    /** DELETE /clan/api/v1/clan/tribe/member/remove?otherId= — kick (chief/elder). */
    private static String clanKick(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        String err = Tribe.kick(store, u, parseLong(ctx.query("otherId"), 0));
        if (err != null) return fail(err);
        return envelope("none", null);
    }

    /** POST /clan/api/v1/clan/tribe/member — RequestJoinTribe {clanId, msg}. */
    private static String clanJoin(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        JSONObject form = body(ctx);
        String err = Tribe.requestJoin(store, u, form.optLong("clanId"), form.optString("msg"));
        if (err != null) return fail(err);
        return envelope("none", null);
    }

    /** PUT /clan/api/v1/clan/tribe/member/agreement?otherId= — accept a join request. */
    private static String clanAgreeJoin(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        String err = Tribe.agreeJoin(store, u, parseLong(ctx.query("otherId"), 0));
        if (err != null) return fail(err);
        return envelope("none", null);
    }

    /** PUT /clan/api/v1/clan/tribe/member/rejection?otherId= — reject a join request. */
    private static String clanRejectJoin(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        String err = Tribe.rejectJoin(store, u, parseLong(ctx.query("otherId"), 0));
        if (err != null) return fail(err);
        return envelope("none", null);
    }

    /** PUT /clan/api/v1/clan/tribe/member/agreement/invitation?id= — invitee accepts. */
    private static String clanAgreeInvite(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        String err = Tribe.agreeInvitation(store, u, parseLong(ctx.query("id"), 0));
        if (err != null) return fail(err);
        return envelope("none", null);
    }

    /** PUT /clan/api/v1/clan/tribe/member/rejection/invitation?id= — invitee rejects. */
    private static String clanRejectInvite(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        String err = Tribe.rejectInvitation(store, u, parseLong(ctx.query("id"), 0));
        if (err != null) return fail(err);
        return envelope("none", null);
    }

    /** POST /clan/api/v1/clan/tribe/member/invite?friendIds=1&amp;friendIds=2&amp;msg= — invite. */
    private static String clanInvite(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        java.util.List<String> vals = ctx.queryValues("friendIds");
        JSONArray ids = new JSONArray();
        for (String v : vals) {
            long id = parseLong(v, 0);
            if (id > 0) ids.put(id);
        }
        String err = Tribe.invite(store, u, ids, ctx.query("msg"));
        if (err != null) return fail(err);
        return envelope("none", null);
    }

    /** PUT /clan/api/v1/clan/tribe/member?otherId=&amp;type= — set identity (chief). */
    private static String clanSetIdentity(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        String err = Tribe.setIdentity(store, u, parseLong(ctx.query("otherId"), 0),
                (int) parseLong(ctx.query("type"), 0));
        if (err != null) return fail(err);
        return envelope("none", null);
    }

    /**
     * GET /clan/api/v2/clan/tribe/member/message — the caller's tribe messages:
     * join requests for their clan (chief/elder, type 1) + invitations to them (type 2).
     * Message status: 0 pending, 2 agreed, 3 rejected.
     */
    private static String tribeMessageList(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        JSONArray out = new JSONArray();
        long uid = u.optLong("userId");
        JSONObject clan = Tribe.clanOf(store, u);
        if (clan != null) {
            int role = Tribe.roleOf(clan, uid);
            if (role == 20 || role == 10) {
                JSONArray reqs = clan.optJSONArray("joinRequests");
                for (int i = 0; reqs != null && i < reqs.length(); i++) {
                    JSONObject r = reqs.optJSONObject(i);
                    if (r == null) continue;
                    JSONObject requester = store.findByUserId(r.optLong("userId"));
                    JSONObject m = new JSONObject();
                    m.put("id", 0);
                    m.put("clanId", (int) clan.optLong("clanId"));
                    m.put("headPic", requester == null ? "" : requester.optString("picUrl"));
                    m.put("nickName", r.optLong("userId") == 0 ? "Player"
                            : (requester == null ? "Player" + r.optLong("userId") : requester.optString("nickName")));
                    m.put("msg", r.optString("msg"));
                    m.put("status", r.optInt("status"));
                    m.put("type", 1);
                    m.put("userId", r.optLong("userId"));
                    out.put(m);
                }
            }
        }
        // invitations addressed to me (any clan)
        JSONArray ids = store.root().optJSONObject("tribes") == null
                ? null : store.root().optJSONObject("tribes").names();
        for (int i = 0; ids != null && i < ids.length(); i++) {
            JSONObject c = store.root().optJSONObject("tribes").optJSONObject(ids.optString(i));
            if (c == null) continue;
            JSONArray inv = c.optJSONArray("invitations");
            for (int j = 0; inv != null && j < inv.length(); j++) {
                JSONObject v = inv.optJSONObject(j);
                if (v == null || v.optLong("inviteeId") != uid) continue;
                JSONObject inviter = store.findByUserId(v.optLong("userId"));
                JSONObject m = new JSONObject();
                m.put("id", (int) v.optLong("id"));
                m.put("clanId", (int) c.optLong("clanId"));
                m.put("headPic", inviter == null ? "" : inviter.optString("picUrl"));
                m.put("nickName", inviter == null ? "Player" : inviter.optString("nickName"));
                m.put("msg", v.optString("msg"));
                m.put("status", v.optInt("status"));
                m.put("type", 2);
                m.put("userId", v.optLong("userId"));
                out.put(m);
            }
        }
        return envelope("list", out.toString());
    }

    /** GET /clan/api/v1/clan/tribe/bulletin — TribeNoticeGet {content, updateTime}. */
    private static String tribeBulletinGet(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        JSONObject clan = Tribe.clanOf(store, u);
        if (clan == null) return fail("not in a clan");
        JSONObject b = clan.optJSONObject("bulletin");
        JSONObject out = new JSONObject();
        out.put("content", b == null ? "" : b.optString("content"));
        out.put("updateTime", b == null ? "" : String.valueOf(b.optLong("updateTime")));
        return envelope("obj", out.toString());
    }

    /** POST /clan/api/v1/clan/tribe/bulletin — TribeNoticePost {content} (chief/elder). */
    private static String tribeBulletinPost(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        String err = Tribe.setBulletin(store, u, body(ctx).optString("content"));
        if (err != null) return fail(err);
        return envelope("none", null);
    }

    /** GET /clan/api/v1/clan/tribe/donation — TribeDonationInfo (today's counters). */
    private static String tribeDonationInfo(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        return envelope("obj", Tribe.donationInfo(store, u).toString());
    }

    /** POST /clan/api/v3/clan/tribe/donation?currency=&amp;quantity= — real wallet deduction. */
    private static String tribeDonate(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        int currency = (int) parseLong(ctx.query("currency"), 2);
        int quantity = (int) parseLong(ctx.query("quantity"), 0);
        String err = Tribe.donate(store, u, currency, quantity);
        if (err != null) return err.startsWith("not enough") || err.contains("limit")
                ? failCode(5006, err) : fail(err);
        long exp = currency == 1 ? quantity * 10L : quantity;
        long got = Math.max(1, exp / 10);
        JSONObject out = new JSONObject();
        out.put("experienceGot", (int) exp);
        out.put("totalExperience", (int) Math.min(Tribe.clanOf(store, u).optLong("experience"), Integer.MAX_VALUE));
        out.put("tribeCurrencyGot", (int) got);
        out.put("totalTribeCurrency", (int) Math.min(Tribe.tribeCurrency(u), Integer.MAX_VALUE));
        out.put("userId", u.optLong("userId"));
        L.i("tribeDonate: userId=" + u.optLong("userId") + " currency=" + currency
                + " qty=" + quantity);
        return envelope("obj", out.toString());
    }

    /** GET /clan/api/v2/clan/tribe/donation/history — PageData&lt;TribeDonationHistory&gt;. */
    private static String tribeDonationHistory(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        JSONArray hist = Tribe.donationHistory(store, u);
        JSONArray out = new JSONArray();
        for (int i = 0; i < hist.length(); i++) {
            JSONObject h = hist.optJSONObject(i);
            if (h == null) continue;
            JSONObject o = new JSONObject();
            o.put("date", h.optLong("date"));
            o.put("experienceGot", String.valueOf(h.optInt("experienceGot")));
            o.put("nickName", h.optString("nickName"));
            o.put("quantity", h.optInt("quantity"));
            o.put("tribeCurrencyGot", String.valueOf(h.optInt("tribeCurrencyGot")));
            o.put("type", h.optInt("type"));
            o.put("userId", h.optLong("userId"));
            out.put(o);
        }
        return envelope("obj", pageData(slice(out, pageNo, pageSize), pageNo, pageSize, out.length()).toString());
    }

    /** GET /clan/api/v1/clan/tribe/currency — HttpResponse&lt;Long&gt; personal tribe currency. */
    private static String tribeCurrency(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        return envelope("num", String.valueOf(Tribe.tribeCurrency(u)));
    }

    /** GET /clan/api/v1/clan/rank?type=&amp;pageNo=&amp;pageSize= — RankInfo&lt;TribeRank&gt; over all clans. */
    private static String tribeRank(Ctx ctx, StateStore store) {
        Tribe.ensureNpcTribes(store);
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        JSONArray sorted = clansByExperience(store);
        JSONArray rows = new JSONArray();
        for (int i = 0; i < sorted.length(); i++) {
            rows.put(tribeRankJson(sorted.optJSONObject(i), i + 1));
        }
        JSONObject rankInfo = new JSONObject();
        rankInfo.put("pageInfo", pageData(slice(rows, pageNo, pageSize), pageNo, pageSize, rows.length()));
        rankInfo.put("remainTime", 0L);
        return envelope("obj", rankInfo.toString());
    }

    /** GET /clan/api/v1/clan/user/rank?type= — the caller's clan's TribeRank row. */
    private static String tribeUserRank(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        JSONObject clan = Tribe.clanOf(store, u);
        if (clan == null) return fail("not in a clan");
        JSONArray sorted = clansByExperience(store);
        for (int i = 0; i < sorted.length(); i++) {
            if (sorted.optJSONObject(i) == clan) {
                return envelope("obj", tribeRankJson(clan, i + 1).toString());
            }
        }
        return envelope("obj", tribeRankJson(clan, sorted.length() + 1).toString());
    }

    /** GET /clan/api/v1/clan/tribe/recommendation — List&lt;TribeRecommendation&gt;. */
    private static String tribeRecommend(Ctx ctx, StateStore store) {
        Tribe.ensureNpcTribes(store);
        JSONArray ids = store.root().optJSONObject("tribes").names();
        JSONArray out = new JSONArray();
        for (int i = 0; ids != null && i < ids.length(); i++) {
            JSONObject c = store.root().optJSONObject("tribes").optJSONObject(ids.optString(i));
            if (c != null) out.put(tribeRecommendationJson(store, c));
        }
        return envelope("list", out.toString());
    }

    /** GET /clan/api/v1/clan/tribe/blurry/info?clanName= — PageData&lt;TribeRecommendation&gt;. */
    private static String tribeSearch(Ctx ctx, StateStore store) {
        Tribe.ensureNpcTribes(store);
        String q = ctx.query("clanName");
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        JSONArray ids = store.root().optJSONObject("tribes").names();
        JSONArray hits = new JSONArray();
        for (int i = 0; ids != null && i < ids.length(); i++) {
            JSONObject c = store.root().optJSONObject("tribes").optJSONObject(ids.optString(i));
            if (c == null) continue;
            if (q == null || q.isEmpty() || c.optString("name").toLowerCase(java.util.Locale.US)
                    .contains(q.toLowerCase(java.util.Locale.US))) {
                hits.put(tribeRecommendationJson(store, c));
            }
        }
        return envelope("obj", pageData(slice(hits, pageNo, pageSize), pageNo, pageSize, hits.length()).toString());
    }

    /** GET /clan/api/v2/clan/tasks?type=1|2 and /clan/api/v2/clan/personal/tasks — TribeTask. */
    private static String tribeTasks(Ctx ctx, StateStore store, int type) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        if (Tribe.clanOf(store, u) == null) return fail("not in a clan");
        int t = (int) parseLong(ctx.query("type"), type);
        return envelope("obj", Tribe.tasks(store, u, t).toString());
    }

    /** PUT /clan/api/v1/clan/tasks/accept (claim=false) and PUT /clan/api/v1/clan/tasks (claim=true). */
    private static String tribeTaskAction(Ctx ctx, StateStore store, boolean claim) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        long id = parseLong(ctx.query("id"), 0);
        int type = (int) parseLong(ctx.query("type"), 1);
        String err = Tribe.taskAction(store, u, id, type, claim);
        if (err != null) return fail(err);
        if (claim) {
            L.i("tribeTaskReward: userId=" + u.optLong("userId") + " task=" + id);
        }
        return envelope("none", null);
    }

    /** GET /clan/api/v1/clan/decorations/{typeId} — PageData&lt;TribeShopPageList&gt; (per-caller hasPurchase). */
    private static String tribeShopList(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        int typeId = (int) parseLong(ctx.pathParam("typeId"), 0);
        int pageNo = (int) parseLong(ctx.query("pageNo"), 1);
        int pageSize = (int) parseLong(ctx.query("pageSize"), 20);
        JSONArray all = Tribe.shop(store);
        JSONArray rows = new JSONArray();
        for (int i = 0; i < all.length(); i++) {
            JSONObject s = all.optJSONObject(i);
            if (s == null || (typeId > 0 && s.optInt("typeId") != typeId)) continue;
            JSONObject o = new JSONObject(s.toString());
            o.put("hasPurchase", u != null && Tribe.ownsDecoration(store, u, s.optLong("id")) ? 1 : 0);
            rows.put(o);
        }
        return envelope("obj", pageData(slice(rows, pageNo, pageSize), pageNo, pageSize, rows.length()).toString());
    }

    /** GET /clan/api/v1/clan/decorations/details/{decorationId} — TribeShopDetail. */
    private static String tribeShopDetail(Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        long id = parseLong(ctx.pathParam("decorationId"), 0);
        JSONArray all = Tribe.shop(store);
        for (int i = 0; i < all.length(); i++) {
            JSONObject s = all.optJSONObject(i);
            if (s != null && s.optLong("id") == id) {
                JSONObject o = new JSONObject(s.toString());
                o.put("hasPurchase", u != null && Tribe.ownsDecoration(store, u, id) ? 1 : 0);
                return envelope("obj", o.toString());
            }
        }
        return fail("unknown decoration");
    }

    /** PUT /clan/api/v1/clan/decorations/purchase?decorationId=A&amp;decorationId=B — pay tribe currency. */
    private static String tribeShopBuy(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        java.util.List<String> vals = ctx.queryValues("decorationId");
        long[] ids = new long[vals.size()];
        for (int i = 0; i < vals.size(); i++) ids[i] = parseLong(vals.get(i), 0);
        String err = Tribe.buyDecorations(store, u, ids);
        if (err != null) return fail(err);
        L.i("tribeShopBuy: userId=" + u.optLong("userId") + " items=" + vals.size());
        return envelope("none", null);
    }

    /** PUT /clan/api/v1/clan/free/verification?freeVerify= — chief toggles auto-join; returns ClanResponse. */
    private static String clanFreeVerify(Ctx ctx, StateStore store) {
        JSONObject u = requireUser(ctx, store);
        if (u == null) return fail(NO_AUTH);
        int freeVerify = (int) parseLong(ctx.query("freeVerify"), 0);
        String err = Tribe.setFreeVerify(store, u, freeVerify);
        if (err != null) return fail(err);
        JSONObject clan = Tribe.clanOf(store, u);
        return envelope("obj", clanResponseJson(clan, Tribe.roleOf(clan, u.optLong("userId"))).toString());
    }

    // ------------------------------------------------- Phase 4: tribe serializers

    private static JSONObject tribeDetailJson(JSONObject clan) {
        JSONObject out = new JSONObject();
        out.put("clanId", (int) clan.optLong("clanId"));
        JSONArray members = Tribe.members(clan);
        JSONArray beans = new JSONArray();
        for (int i = 0; i < members.length(); i++) {
            JSONObject m = members.optJSONObject(i);
            if (m == null) continue;
            JSONObject b = new JSONObject();
            b.put("userId", m.optLong("userId"));
            b.put("role", m.optInt("role"));
            b.put("headPic", m.optString("headPic"));
            beans.put(b);
        }
        out.put("clanMembers", beans);
        out.put("currentCount", members.length());
        out.put("maxCount", Tribe.maxMembers(clan));
        out.put("details", clan.optString("details"));
        out.put("experience", clan.optLong("experience"));
        out.put("freeVerify", clan.optInt("freeVerify"));
        out.put("headPic", clan.optString("headPic"));
        out.put("level", Tribe.level(clan));
        out.put("name", clan.optString("name"));
        out.put("tags", clan.optJSONArray("tags") == null ? new JSONArray() : clan.optJSONArray("tags"));
        return out;
    }

    private static JSONArray tribeMembersJson(JSONObject clan) {
        JSONArray members = Tribe.members(clan);
        JSONArray out = new JSONArray();
        for (int i = 0; i < members.length(); i++) {
            JSONObject m = members.optJSONObject(i);
            if (m == null) continue;
            JSONObject o = new JSONObject();
            o.put("ID", i + 1);
            o.put("userId", m.optLong("userId"));
            o.put("localUserId", 0L);
            o.put("experience", m.optInt("experience"));
            o.put("expireDate", m.optString("expireDate"));
            o.put("headPic", m.optString("headPic"));
            o.put("nickName", m.optString("nickName"));
            o.put("role", m.optInt("role"));
            o.put("status", m.optInt("status"));
            o.put("vip", m.optInt("vip"));
            out.put(o);
        }
        return out;
    }

    private static JSONObject clanRequestEcho(JSONObject clan) {
        JSONObject out = new JSONObject();
        out.put("clanId", clan.optLong("clanId"));
        out.put("details", clan.optString("details"));
        out.put("headPic", clan.optString("headPic"));
        out.put("name", clan.optString("name"));
        out.put("tags", clan.optJSONArray("tags") == null ? new JSONArray() : clan.optJSONArray("tags"));
        out.put("currency", 2);
        return out;
    }

    private static JSONObject clanResponseJson(JSONObject clan, int role) {
        JSONObject out = new JSONObject();
        out.put("clanId", clan.optLong("clanId"));
        out.put("details", clan.optString("details"));
        out.put("experience", clan.optLong("experience"));
        out.put("freeVerify", clan.optInt("freeVerify"));
        out.put("headPic", clan.optString("headPic"));
        out.put("level", Tribe.level(clan));
        out.put("name", clan.optString("name"));
        out.put("role", role);
        out.put("tags", clan.optJSONArray("tags") == null ? new JSONArray() : clan.optJSONArray("tags"));
        return out;
    }

    private static JSONObject tribeRecommendationJson(StateStore store, JSONObject clan) {
        JSONObject out = new JSONObject();
        out.put("clanId", (int) clan.optLong("clanId"));
        out.put("name", clan.optString("name"));
        out.put("details", clan.optString("details"));
        out.put("headPic", clan.optString("headPic"));
        out.put("freeVerify", clan.optInt("freeVerify"));
        out.put("level", Tribe.level(clan));
        JSONArray members = Tribe.members(clan);
        out.put("currentCount", members.length());
        out.put("maxCount", Tribe.maxMembers(clan));
        JSONObject chief = members.length() > 0 ? members.optJSONObject(0) : null;
        out.put("chiefId", chief == null ? 0L : chief.optLong("userId"));
        out.put("chiefNickName", chief == null ? "" : chief.optString("nickName"));
        out.put("isFirst", false);
        return out;
    }

    private static JSONObject tribeRankJson(JSONObject clan, int rank) {
        JSONObject out = new JSONObject();
        out.put("clanId", (int) clan.optLong("clanId"));
        out.put("name", clan.optString("name"));
        out.put("headPic", clan.optString("headPic"));
        out.put("experience", String.valueOf(clan.optLong("experience")));
        out.put("rank", String.valueOf(rank));
        return out;
    }

    /** Clans sorted by experience desc (arrays snapshot; caller may compare identity). */
    private static JSONArray clansByExperience(StateStore store) {
        JSONObject clans = store.root().optJSONObject("tribes");
        JSONArray out = new JSONArray();
        if (clans == null) return out;
        JSONArray ids = clans.names();
        for (int i = 0; ids != null && i < ids.length(); i++) {
            JSONObject c = clans.optJSONObject(ids.optString(i));
            if (c != null) out.put(c);
        }
        // insertion sort (small n)
        for (int i = 1; i < out.length(); i++) {
            JSONObject key = out.optJSONObject(i);
            long ke = key.optLong("experience");
            int j = i - 1;
            while (j >= 0 && out.optJSONObject(j).optLong("experience") < ke) {
                out.put(j + 1, out.optJSONObject(j));
                j--;
            }
            out.put(j + 1, key);
        }
        return out;
    }

    private static JSONObject pageData(JSONArray data, int pageNo, int pageSize, int totalSize) {
        int size = pageSize > 0 ? pageSize : 20;
        JSONObject page = new JSONObject();
        page.put("data", data);
        page.put("pageNo", pageNo);
        page.put("pageSize", size);
        page.put("totalPage", totalPages(totalSize, size));
        page.put("totalSize", totalSize);
        return page;
    }

    /** Failure with an explicit numeric code (the client maps code→onError(code)). */
    private static String failCode(int code, String message) {
        return "{\"code\":" + code + ",\"message\":\"" + message + "\"}";
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
