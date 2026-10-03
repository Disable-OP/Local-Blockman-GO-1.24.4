package com.localapi;

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
