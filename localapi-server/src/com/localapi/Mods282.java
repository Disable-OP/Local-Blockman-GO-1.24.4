package com.localapi;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Blockman GO 2.8.2 (blockymods, engine 10078) client extension domain.
 *
 * The 2.8.2 Retrofit surface is 409 endpoints; 322 are already routed by the
 * 1.24.4-era RoutingTable. This file implements the state-backed handlers for
 * the meaningful subset of the 65 new game-relevant routes; the rest ride the
 * schema-true shape defaults registered beside them in RoutingTable.
 *
 * Shapes are taken from the decompiled 2.8.2 Gson models:
 * - PayUserInfo  = {avatarFrame, colorfulNickName, language, name, picUrl, userId, vip}
 *   (src_classes4/com/sandboxol/googlepay/entity/PayUserInfo.java)
 * - PartyAuthInfo = {country, dispUrl, engineType, partyQuerierService,
 *   partyService, region, signature, timestamp, token}
 *   (src_classes3/com/sandboxol/center/entity/PartyAuthInfo.java)
 * - GoldExchangeRate = {rate: String} (golds per 1 gDiamond)
 * - User (v2 details) = the standard login User model, served from the store.
 *
 * The avatarFrame / colorfulNickName pair is REAL state (the PayUserInfo
 * mirrors it — the 2.8.2 shop/personal pages read it back through
 * /user/api/v1/simple/info). The gdiamond/gold exchange is REAL wallet math.
 */
final class Mods282 {

    /** golds granted per 1 gDiamond on exchange (persisted, editable). */
    static final String DEFAULT_RATE = "10000";

    private Mods282() {}

    // ------------------------------------------------------------------
    // /config/files/blockymods-bannerv2 — the 2.8.2 banner config file.
    // Same file family as blockmods-config-v1 (appConfig): a config-file
    // body, not an envelope-wrapped data object.
    // ------------------------------------------------------------------
    static String bannerConfig(Handlers.Ctx ctx, StateStore store) {
        JSONObject root = store.root();
        JSONObject banner = root.optJSONObject("bannerV2");
        if (banner == null) {
            banner = new JSONObject();
            banner.put("bannerList", new JSONArray());
            banner.put("popupList", new JSONArray());
            banner.put("version", "local-1");
            root.put("bannerV2", banner);
            store.save();
        }
        return Handlers.envelope("obj", banner.toString());
    }

    // ------------------------------------------------------------------
    // GET /user/api/v1/simple/info?userId= — PayUserInfo (IPayApi).
    // ------------------------------------------------------------------
    static String payUserInfo(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        long asked = 0L;
        try { asked = Long.parseLong(ctx.query("userId")); } catch (Exception ignored) {}
        if (u == null && asked == 0) {
            return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        }
        if (u == null) {
            u = store.findByUserId(asked);
        }
        if (u == null) {
            return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        }
        JSONObject d = new JSONObject();
        d.put("userId", u.optLong("userId"));
        d.put("name", u.optString("nickName"));
        d.put("picUrl", u.optString("picUrl"));
        d.put("vip", u.optInt("vip", 0));
        d.put("avatarFrame", u.optString("avatarFrame"));
        d.put("colorfulNickName", u.optString("colorfulNickName"));
        d.put("language", ctx.header("language"));
        return Handlers.envelope("obj", d.toString());
    }

    // ------------------------------------------------------------------
    // GET /user/api/v2/user/details/info — the v2 User details read.
    // ------------------------------------------------------------------
    static String userDetailsV2(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        if (u == null) {
            return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        }
        JSONObject d = new JSONObject(Handlers.userJsonLocal(u));
        // v2 extras the 2.8.2 personal pages read back (kept in real state).
        d.put("avatarFrame", u.optString("avatarFrame"));
        d.put("colorfulNickName", u.optString("colorfulNickName"));
        return Handlers.envelope("obj", d.toString());
    }

    // ------------------------------------------------------------------
    // GET/PUT user/api/{version}/user/avatar/frame
    // ------------------------------------------------------------------
    static String avatarFrameGet(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        if (u == null) return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        return Handlers.envelope("str", "\"" + u.optString("avatarFrame") + "\"");
    }

    static String avatarFramePut(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        if (u == null) return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        String frame = ctx.query("avatarFrame");
        if (frame == null || frame.isEmpty()) {
            frame = Handlers.body(ctx).optString("avatarFrame",
                    Handlers.body(ctx).optString("frameId"));
        }
        u.put("avatarFrame", frame == null ? "" : frame);
        store.save();
        return Handlers.envelope("none", null);
    }

    // ------------------------------------------------------------------
    // GET/PUT user/api/{version}/user/colorful/nickName
    // ------------------------------------------------------------------
    static String colorfulNickNameGet(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        if (u == null) return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        return Handlers.envelope("str", "\"" + u.optString("colorfulNickName") + "\"");
    }

    static String colorfulNickNamePut(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        if (u == null) return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        String val = ctx.query("colorfulNickName");
        if (val == null || val.isEmpty()) {
            val = Handlers.body(ctx).optString("colorfulNickName");
        }
        u.put("colorfulNickName", val == null ? "" : val);
        store.save();
        return Handlers.envelope("none", null);
    }

    // ------------------------------------------------------------------
    // GET /pay/pay/api/v1/pay/gdiamond/gold/exchange/rate — {rate: "10000"}
    // ------------------------------------------------------------------
    static String goldExchangeRate(Handlers.Ctx ctx, StateStore store) {
        JSONObject root = store.root();
        if (!root.has("goldExchangeRate")) {
            root.put("goldExchangeRate", DEFAULT_RATE);
            store.save();
        }
        JSONObject d = new JSONObject();
        d.put("rate", root.optString("goldExchangeRate", DEFAULT_RATE));
        return Handlers.envelope("obj", d.toString());
    }

    // ------------------------------------------------------------------
    // PUT /pay/pay/api/v1/pay/gdiamond/gold/exchange?gdiamond=N — REAL
    // wallet conversion: N gDiamonds -> N*rate golds, persisted atomically.
    // ------------------------------------------------------------------
    static String goldExchange(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        if (u == null) return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        int gd;
        try { gd = Integer.parseInt(ctx.query("gdiamond")); }
        catch (Exception e) { gd = -1; }
        if (gd <= 0) {
            return Handlers.failCode(0, "gdiamond must be > 0");
        }
        JSONObject root = store.root();
        long rate = Long.parseLong(root.optString("goldExchangeRate", DEFAULT_RATE));
        long have = u.optLong("gDiamonds", 0);
        if (have < gd) {
            return Handlers.failCode(ErrorCodes.GOLD_NOT_ENOUGH, "not enough gDiamonds");
        }
        long golds = gd * rate;
        u.put("gDiamonds", have - gd);
        u.put("golds", u.optLong("golds", 0) + golds);
        store.save();
        JSONObject d = new JSONObject();
        d.put("userId", u.optLong("userId"));
        d.put("gDiamonds", u.optLong("gDiamonds", 0));
        d.put("golds", u.optLong("golds", 0));
        L.i("goldExchange: uid=" + u.optLong("userId") + " -" + gd + "gD +" + golds + "golds");
        return Handlers.envelope("obj", d.toString());
    }

    // ------------------------------------------------------------------
    // GET /game/api/v2/party/auth/test — PartyAuthInfo. The local party
    // flow always passes auth; dispUrl points at this holder.
    // ------------------------------------------------------------------
    static String partyAuthTest(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        if (u == null) return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        JSONObject d = new JSONObject();
        d.put("country", ctx.header("cloudfront-viewer-country"));
        d.put("dispUrl", "http://127.0.0.1:" + LocalServer.PORT);
        d.put("engineType", "1");
        d.put("partyQuerierService", "");
        d.put("partyService", "");
        d.put("region", 0);
        d.put("signature", "local");
        d.put("timestamp", System.currentTimeMillis() / 1000L);
        d.put("token", u.optString("accessToken"));
        return Handlers.envelope("obj", d.toString());
    }

    // ------------------------------------------------------------------
    // GET /game/api/v1/game/info/search + keyword associational word.
    // Search runs over the REAL local catalog (GameCatalog.games).
    // ------------------------------------------------------------------
    static String gameSearch(Handlers.Ctx ctx, StateStore store) {
        String kw = ctx.query("keyword");
        if (kw == null) kw = ctx.query("name");
        JSONArray hits = new JSONArray();
        if (kw != null && !kw.isEmpty()) {
            String needle = kw.toLowerCase();
            JSONArray gs = GameCatalog.games(store);
            for (int i = 0; i < gs.length(); i++) {
                JSONObject g = gs.optJSONObject(i);
                if (g == null) continue;
                String name = g.optString("gameName", g.optString("name"));
                if (name.toLowerCase().contains(needle)) hits.put(g);
            }
        }
        return Handlers.envelope("list", hits.toString());
    }

    static String keywordWords(Handlers.Ctx ctx, StateStore store) {
        String kw = ctx.query("keyword");
        if (kw == null) kw = ctx.query("name");
        JSONArray words = new JSONArray();
        if (kw != null && !kw.isEmpty()) {
            String needle = kw.toLowerCase();
            JSONArray gs = GameCatalog.games(store);
            java.util.LinkedHashSet<String> seen = new java.util.LinkedHashSet<>();
            for (int i = 0; i < gs.length() && seen.size() < 10; i++) {
                JSONObject g = gs.optJSONObject(i);
                if (g == null) continue;
                String name = g.optString("gameName", g.optString("name"));
                if (name.toLowerCase().contains(needle) && seen.add(name)) {
                    words.put(name);
                }
            }
        }
        return Handlers.envelope("list", words.toString());
    }

    // ------------------------------------------------------------------
    // POST /game/api/v1/games/like — REAL counter on the catalog entry
    // (persisted under root.gameLikes).
    // ------------------------------------------------------------------
    static String gamesLike(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        if (u == null) return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        JSONObject form = Handlers.body(ctx);
        String gameId = form.optString("gameId",
                ctx.query("gameId") == null ? "" : ctx.query("gameId"));
        JSONObject root = store.root();
        JSONObject likes = root.optJSONObject("gameLikes");
        if (likes == null) { likes = new JSONObject(); root.put("gameLikes", likes); }
        long n = likes.optLong(gameId, 0) + 1;
        likes.put(gameId, n);
        store.save();
        JSONObject d = new JSONObject();
        d.put("gameId", gameId);
        d.put("likes", n);
        return Handlers.envelope("obj", d.toString());
    }

    // ------------------------------------------------------------------
    // POST /msg/api/v1/game/chat/room — REAL chat-room create (the 2.8.2
    // in-game chat room); state lives under root.chatRooms282.
    // ------------------------------------------------------------------
    static String chatRoomCreate(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        if (u == null) return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        JSONObject form = Handlers.body(ctx);
        JSONObject root = store.root();
        JSONArray rooms = root.optJSONArray("chatRooms282");
        if (rooms == null) { rooms = new JSONArray(); root.put("chatRooms282", rooms); }
        String roomId = "room-" + System.currentTimeMillis();
        JSONObject room = new JSONObject();
        room.put("roomId", roomId);
        room.put("name", form.optString("name", form.optString("roomName", roomId)));
        room.put("ownerId", u.optLong("userId"));
        room.put("gameId", form.optString("gameId", "g1008"));
        room.put("members", new JSONArray().put(u.optLong("userId")));
        room.put("createTime", System.currentTimeMillis());
        rooms.put(room);
        store.save();
        return Handlers.envelope("obj", room.toString());
    }

    static String chatRoomDelete(Handlers.Ctx ctx, StateStore store) {
        JSONObject u = store.resolve(ctx.header("access-token"), ctx.header("userid"));
        if (u == null) return Handlers.failCode(ErrorCodes.NOT_LOGIN, "authentication required");
        JSONObject form = Handlers.body(ctx);
        String roomId = form.optString("roomId",
                ctx.query("roomId") == null ? "" : ctx.query("roomId"));
        JSONObject root = store.root();
        JSONArray rooms = root.optJSONArray("chatRooms282");
        if (rooms != null) {
            JSONArray kept = new JSONArray();
            for (int i = 0; i < rooms.length(); i++) {
                JSONObject r = rooms.optJSONObject(i);
                if (r != null && !roomId.equals(r.optString("roomId"))) kept.put(r);
            }
            root.put("chatRooms282", kept);
            store.save();
        }
        return Handlers.envelope("none", null);
    }

    /**
     * GET /game/api/v1/game/revision/all/list/by/condition — the 2.8.2 HOME
     * FEED: List<HomeColumn> (src_classes5 .../homedata/HomeColumn.java).
     * The previous |list template served data:[] — Gson produced no
     * columns and the home rendered EMPTY (run 38156920974: 41 dump
     * nodes, zero tv_game_name cards, the UI join had no Bedwars card to
     * press). Shape per column: {areaName, code, insideShow/Sort,
     * outsideShow/Sort, response:{typeId, pageInfo:{data:[Game], pageNo,
     * pageSize, totalPage, totalSize}}}. The client switch is on code:
     * "latest" -> single list adapter (app_item_game), "recommend" ->
     * DoubleGame grid (two stacked app_item_game_basic), "banner" ->
     * the banner widget, ANY other code -> a generic list adapter keyed
     * by that code (HomeViewModel.b/c, src_classes3 blockymods pages/
     * home/t.java). Two columns carry the SAME pinned-first catalog
     * pages so both card styles render and the Bedwars hall card is
     * first either way.
     */
    static String homeData(Handlers.Ctx ctx, StateStore store) {
        JSONArray games = GameCatalog.page(store, "complex", 0, false, 1, 40);
        JSONArray cols = new JSONArray();
        int total = games.length();
        String[] codes = {"recommend", "latest"};
        for (int c = 0; c < codes.length; c++) {
            JSONObject col = new JSONObject();
            col.put("code", codes[c]);
            col.put("areaName", "recommend".equals(codes[c])
                    ? "Recommend" : "Latest");
            col.put("type", codes[c]);
            col.put("insideShow", 1);
            col.put("outsideShow", 1);
            col.put("insideSort", c + 1);
            col.put("outsideSort", c + 1);
            JSONObject resp = new JSONObject();
            resp.put("typeId", 0);
            JSONObject page = new JSONObject();
            page.put("data", games);
            page.put("pageNo", 1);
            page.put("pageSize", total);
            page.put("totalPage", 1);
            page.put("totalSize", total);
            resp.put("pageInfo", page);
            col.put("response", resp);
            cols.put(col);
        }
        return Handlers.envelope("list", cols.toString());
    }
}
