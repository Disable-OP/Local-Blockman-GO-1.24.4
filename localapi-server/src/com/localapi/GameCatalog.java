package com.localapi;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Game catalog + living-world state for the local API.
 *
 * Nothing is hardcoded per-request: on first boot the catalog is GENERATED
 * (categories, games, shop props, rank boards, citizen players) and persisted
 * into StateStore, after which it is ordinary editable server state that
 * survives restarts. Handlers query it like a real backend would.
 */
final class GameCatalog {

    private GameCatalog() {}

    // ------------------------------------------------------------ bootstrap

    /** Ensure catalog sections exist in the store (generated once, then state). */
    static synchronized void ensure(StateStore store) {
        JSONObject root = store.root();
        boolean dirty = false;
        if (!root.has("categories")) {
            root.put("categories", generateCategories());
            dirty = true;
        }
        if (!root.has("games")) {
            root.put("games", generateGames(root.optJSONArray("categories")));
            dirty = true;
        }
        if (!root.has("citizens")) {
            root.put("citizens", generateCitizens());
            dirty = true;
        }
        if (!root.has("rankBoards")) root.put("rankBoards", new JSONObject());
        if (!root.has("shopProps")) root.put("shopProps", new JSONObject());
        if (!root.has("chatRooms")) root.put("chatRooms", new JSONObject());
        if (!root.has("nextPropId")) root.put("nextPropId", 70001);
        if (!root.has("nextRoomId")) root.put("nextRoomId", 90001);
        if (dirty) {
            L.i("catalog generated: " + root.optJSONArray("games").length()
                    + " games, " + root.optJSONArray("categories").length()
                    + " categories, " + root.optJSONArray("citizens").length() + " citizens");
            store.save();
        }
    }

    // ----------------------------------------------------------- generation

    private static JSONArray generateCategories() {
        String[][] defs = {
                {"101", "Parkour", "online"},
                {"102", "Sandbox", "complex"},
                {"103", "PvP Arena", "online"},
                {"104", "Role Play", "appreciate"},
                {"105", "Shooter", "online"},
                {"106", "Mini Games", "new"},
        };
        JSONArray arr = new JSONArray();
        for (String[] d : defs) {
            JSONObject c = new JSONObject();
            c.put("typeId", Long.parseLong(d[0]));
            c.put("typeName", d[1]);
            c.put("iconUrl", "");
            c.put("iconResId", 0);
            c.put("sortType", d[2]);
            arr.put(c);
        }
        return arr;
    }

    private static JSONArray generateGames(JSONArray categories) {
        String[] adj = {"Sky", "Desert", "Frozen", "Neon", "Jungle", "Lost", "Iron", "Cloud",
                "Ruby", "Shadow", "Golden", "Silent", "Wild", "Turbo", "Mystic", "Pixel",
                "Crystal", "Storm", "Nova", "Ancient", "Robo", "Candy", "Volcano", "Arctic"};
        String[] noun = {"Islands", "Raiders", "Runners", "Builders", "Arena", "Legends",
                "Racers", "Craft", "Survival", "Battle", "Worlds", "Rush", "Quest", "Park",
                "Wars", "City", "Zones", "Tower", "Rift", "Kingdom"};
        long now = System.currentTimeMillis();
        JSONArray games = new JSONArray();
        int nCat = categories.length();
        for (int i = 0; i < 42; i++) {
            JSONObject g = new JSONObject();
            long id = 5001 + i;
            String name = adj[i % adj.length] + " " + noun[(i * 7 + i / adj.length) % noun.length];
            JSONObject cat = categories.getJSONObject(i % nCat);
            boolean ugc = (i % 9) == 4;
            g.put("gameId", String.valueOf(id));
            g.put("gameTitle", name);
            g.put("gameName", name);
            g.put("gameCoverPic", "");
            g.put("bannerPic", new JSONArray());
            g.put("gameBannerVideoInfos", new JSONArray());
            g.put("gameDetail", "A locally hosted " + cat.optString("typeName")
                    + " experience. Everything runs on your own server.");
            JSONArray types = new JSONArray();
            types.put(cat.optString("typeName"));
            g.put("gameTypes", types);
            g.put("appreciate", false);
            g.put("gameMode", 1);
            g.put("visitorEnter", 1);
            g.put("version", 1);
            g.put("isRankOnline", 1);
            g.put("isShopOnline", (i % 3 == 0) ? 1 : 0);
            g.put("isOpenParty", (i % 2 == 0) ? 1 : 0);
            g.put("isPay", 0);
            g.put("turntableStatus", 0);
            g.put("turntableRemainCount", 0);
            g.put("isNewEngine", 1);
            g.put("isUgcGame", ugc ? 1 : 0);
            g.put("gameUgcType", ugc ? "ugc" : "");
            g.put("currentPage", 0);
            g.put("currentSize", 0);
            g.put("resVersion", 1);
            g.put("pageType", 0);
            g.put("typeId", cat.optLong("typeId"));
            g.put("createTime", now - (42L - i) * 86_400_000L);
            g.put("complexNum", 40 + (i * 37) % 460);
            g.put("praiseNumber", 120 + (i * 91) % 3800);
            g.put("onlineNumber", 30 + (i * 53) % 2400);
            g.put("index", i);
            JSONObject latest = new JSONObject();
            latest.put("cresVersion", 1);
            latest.put("dresVersion", 1);
            latest.put("gresVersion", 1);
            g.put("latestResVersions", latest);
            games.put(g);
        }
        return games;
    }

    private static JSONArray generateCitizens() {
        String[] names = {"Alex", "Rin", "Marco", "Zoe", "Kai", "Nina", "Theo", "Lua", "Omar",
                "Suki", "Finn", "Ada", "Diego", "Mira", "Jax", "Yuki", "Bram", "Lena", "Cleo",
                "Nico", "Tara", "Ravi", "Esme", "Otto", "Ines", "Hugo", "Nael", "Vera", "Emil",
                "Sana", "Luca", "Priya", "Beni", "Nova", "Ivan", "Tia"};
        String[] countries = {"US", "BR", "ID", "PH", "MX", "EG", "IN", "TR", "VN", "TH", "ES", "AR"};
        JSONArray arr = new JSONArray();
        for (int i = 0; i < names.length; i++) {
            JSONObject c = new JSONObject();
            c.put("userId", 20001 + i);
            c.put("nickName", names[i] + (100 + i));
            c.put("sex", i % 2);
            c.put("country", countries[i % countries.length]);
            c.put("headPic", "");
            c.put("vip", i % 4);
            arr.put(c);
        }
        return arr;
    }

    // -------------------------------------------------------------- queries

    private static JSONArray games(StateStore store) {
        return store.root().optJSONArray("games");
    }

    /** Find one game by its string id ("" -tolerant). */
    static synchronized JSONObject byId(StateStore store, String gameId) {
        if (gameId == null) return null;
        JSONArray gs = games(store);
        for (int i = 0; i < gs.length(); i++) {
            JSONObject g = gs.optJSONObject(i);
            if (g != null && gameId.equals(g.optString("gameId"))) return g;
        }
        return null;
    }

    /**
     * Sorted + filtered + paged view of the catalog.
     * sortType: online | new | appreciate | (default) complex.
     */
    static synchronized JSONArray page(StateStore store, String sortType, long typeId,
                                       boolean ugcOnly, int pageNo, int pageSize) {
        JSONArray gs = games(store);
        JSONArray filtered = new JSONArray();
        for (int i = 0; i < gs.length(); i++) {
            JSONObject g = gs.optJSONObject(i);
            if (g == null) continue;
            if (ugcOnly && g.optInt("isUgcGame") != 1) continue;
            if (typeId > 0 && g.optLong("typeId") != typeId) continue;
            filtered.put(g);
        }
        String sort = sortType == null ? "" : sortType;
        // insertion sort (tiny N) — stable, no boxing; descending by metric
        for (int i = 1; i < filtered.length(); i++) {
            JSONObject key = filtered.getJSONObject(i);
            int j = i - 1;
            while (j >= 0 && compare(filtered.getJSONObject(j), key, sort) > 0) {
                filtered.put(j + 1, filtered.getJSONObject(j));
                j--;
            }
            filtered.put(j + 1, key);
        }
        int size = pageSize > 0 ? pageSize : 20;
        int from = Math.max(0, (pageNo - 1) * size);
        JSONArray out = new JSONArray();
        for (int i = from; i < filtered.length() && i < from + size; i++) out.put(filtered.get(i));
        return out;
    }

    static synchronized int count(StateStore store, String sortType, long typeId, boolean ugcOnly) {
        JSONArray gs = games(store);
        int n = 0;
        for (int i = 0; i < gs.length(); i++) {
            JSONObject g = gs.optJSONObject(i);
            if (g == null) continue;
            if (ugcOnly && g.optInt("isUgcGame") != 1) continue;
            if (typeId > 0 && g.optLong("typeId") != typeId) continue;
            n++;
        }
        return n;
    }

    private static long metric(JSONObject g, String sort) {
        switch (sort) {
            case "online": return g.optLong("onlineNumber");
            case "new": return g.optLong("createTime");
            case "appreciate": return g.optLong("praiseNumber");
            default: return g.optLong("complexNum");
        }
    }

    private static int compare(JSONObject a, JSONObject b, String sort) {
        long ma = metric(a, sort), mb = metric(b, sort);
        if (ma > mb) return -1;      // descending
        if (ma < mb) return 1;
        return 0;
    }

    /** Catalog as List<Game> — thin copies so handlers can tweak fields safely. */
    static synchronized JSONArray list(StateStore store, String sortType, long typeId, boolean ugcOnly) {
        return page(store, sortType, typeId, ugcOnly, 1, Integer.MAX_VALUE / 2);
    }

    static synchronized JSONArray categories(StateStore store) {
        return store.root().optJSONArray("categories");
    }

    static synchronized JSONArray citizens(StateStore store) {
        return store.root().optJSONArray("citizens");
    }

    // ------------------------------------------------------------ shop props

    static synchronized JSONArray shopProps(StateStore store, String gameId) {
        JSONObject all = store.root().optJSONObject("shopProps");
        JSONArray props = all.optJSONArray(gameId);
        if (props != null) return props;
        String[] kinds = {"Skin Pack", "Speed Boost", "Coin Bag", "Wings", "Pet Egg", "Trail FX"};
        props = new JSONArray();
        int base = all.length() == 0 ? 3 : 4;
        int n = 3 + (Math.abs(gameId.hashCode()) % (base - 1));
        for (int i = 0; i < n; i++) {
            JSONObject p = new JSONObject();
            int id = store.root().optInt("nextPropId", 70001);
            store.root().put("nextPropId", id + 1);
            p.put("id", id);
            p.put("name", kinds[(Math.abs(gameId.hashCode()) + i) % kinds.length] + " " + (i + 1));
            p.put("details", "Exclusive item for " + gameName(store, gameId) + ".");
            p.put("iconUrl", "");
            p.put("price", 100 + (Math.abs(gameId.hashCode() * (i + 3)) % 1900));
            p.put("currency", (i % 2 == 0) ? 2 : 1);
            p.put("resourceId", "prop-" + gameId + "-" + (i + 1));
            p.put("status", 1);
            p.put("validate", 1);
            p.put("expireDate", "");
            props.put(p);
        }
        all.put(gameId, props);
        store.save();
        return props;
    }

    private static String gameName(StateStore store, String gameId) {
        JSONObject g = byId(store, gameId);
        return g == null ? "this game" : g.optString("gameTitle");
    }

    // ------------------------------------------------------------ rank board

    /**
     * Rank board for one game: citizens + real users, ranked by integral.
     * Board is generated on first request per game, then evolves as real state.
     */
    static synchronized JSONArray rankBoard(StateStore store, String gameId) {
        JSONObject boards = store.root().optJSONObject("rankBoards");
        JSONArray board = boards.optJSONArray(gameId);
        if (board != null) return board;
        board = new JSONArray();
        JSONArray citizens = citizens(store);
        int n = Math.min(25, citizens.length());
        for (int i = 0; i < n; i++) {
            JSONObject c = citizens.getJSONObject(i);
            JSONObject row = new JSONObject();
            row.put("userId", c.optLong("userId"));
            row.put("nickName", c.optString("nickName"));
            row.put("headPic", c.optString("headPic"));
            row.put("vip", c.optInt("vip"));
            row.put("integral", 9800 - i * (120 + (Math.abs(gameId.hashCode()) + i) % 260));
            row.put("isFirst", i == 0);
            row.put("rank", i + 1);
            board.put(row);
        }
        boards.put(gameId, board);
        store.save();
        return board;
    }

    /** Record / add integral for a real user on a game board. */
    static synchronized void addIntegral(StateStore store, String gameId, long userId,
                                         String nickName, int vip, long delta) {
        if (delta == 0) return;
        JSONArray board = rankBoard(store, gameId);
        for (int i = 0; i < board.length(); i++) {
            JSONObject row = board.getJSONObject(i);
            if (row.optLong("userId") == userId) {
                row.put("integral", row.optLong("integral") + delta);
                reRank(board);
                store.save();
                return;
            }
        }
        JSONObject row = new JSONObject();
        row.put("userId", userId);
        row.put("nickName", nickName);
        row.put("headPic", "");
        row.put("vip", vip);
        row.put("integral", delta);
        row.put("isFirst", false);
        board.put(row);
        reRank(board);
        store.save();
    }

    private static void reRank(JSONArray board) {
        for (int i = 1; i < board.length(); i++) {
            JSONObject key = board.getJSONObject(i);
            int j = i - 1;
            while (j >= 0 && board.getJSONObject(j).optLong("integral") < key.optLong("integral")) {
                board.put(j + 1, board.getJSONObject(j));
                j--;
            }
            board.put(j + 1, key);
        }
        for (int i = 0; i < board.length(); i++) {
            board.getJSONObject(i).put("rank", i + 1);
            board.getJSONObject(i).put("isFirst", i == 0);
        }
    }

    // ------------------------------------------------------------- chat room

    static synchronized String chatRoom(StateStore store, String roomName) {
        JSONObject rooms = store.root().optJSONObject("chatRooms");
        if (rooms.has(roomName)) return rooms.optString(roomName);
        String roomId = "local-room-" + store.root().optInt("nextRoomId", 90001);
        store.root().put("nextRoomId", store.root().optInt("nextRoomId", 90001) + 1);
        rooms.put(roomName, roomId);
        store.save();
        return roomId;
    }

    // --------------------------------------------------------- catalog drift

    /**
     * Nudge online counts a little on each boot so the hall feels alive.
     * Deterministic per boot (no random flapping within a session).
     */
    static synchronized void drift(StateStore store) {
        JSONArray gs = games(store);
        long boot = (System.currentTimeMillis() / 3_600_000L); // hourly bucket
        boolean changed = false;
        for (int i = 0; i < gs.length(); i++) {
            JSONObject g = gs.getJSONObject(i);
            int base = 30 + (i * 53) % 2400;
            int wobble = (int) ((boot * (7 + i)) % 220);
            int next = base + wobble;
            if (g.optInt("onlineNumber") != next) {
                g.put("onlineNumber", next);
                changed = true;
            }
        }
        if (changed) store.save();
    }
}
