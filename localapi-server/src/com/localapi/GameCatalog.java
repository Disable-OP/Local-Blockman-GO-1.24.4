package com.localapi;

import java.io.File;
import java.util.Locale;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Game catalog + living-world state for the local API.
 *
 * Nothing is hardcoded per-request: the catalog is SEEDED once (from the
 * client's own ScriptSetting.csv when present — the real Blockman GO game
 * list with real script ids) and persisted into StateStore, after which it
 * is ordinary editable server state that survives restarts. Handlers query
 * it like a real backend would.
 *
 * Engine mandate (user directive): the 1.24.4 client bundles ONLY the
 * engine-1 runtime — every game ships isNewEngine = 0 so game start always
 * boots the old engine that the APK actually carries.
 */
final class GameCatalog {

    /** 3 = real ScriptSetting catalog, engine-1 (isNewEngine=0) everywhere. */
    private static final int CATALOG_VERSION = 3;

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
            JSONArray seeded = seedFromScriptSetting(store);
            root.put("games", seeded != null ? seeded
                    : generateGames(root.optJSONArray("categories")));
            dirty = true;
        }
        // migration: pre-ScriptSetting catalogs (fake ids/names, engine-1
        // flag wrong) regenerate from the seed; fresh boots without a seed
        // keep their generated catalog but still get the engine fix + the
        // version marker.
        if (root.optInt("catalogVersion", 0) < CATALOG_VERSION) {
            JSONArray seeded = seedFromScriptSetting(store);
            if (seeded != null) {
                root.put("games", seeded);
                L.i("catalog migrated to v" + CATALOG_VERSION + " ("
                        + seeded.length() + " real games)");
            }
            root.put("catalogVersion", CATALOG_VERSION);
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
        if (!root.has("gamePurchases")) root.put("gamePurchases", new JSONArray());
        if (ensurePremium(root)) dirty = true;
        if (dirty) {
            L.i("catalog generated: " + root.optJSONArray("games").length()
                    + " games, " + root.optJSONArray("categories").length()
                    + " categories, " + root.optJSONArray("citizens").length() + " citizens");
            store.save();
        }
    }

    /**
     * Migration + fresh-boot guarantee: the catalog always carries ONE
     * premium (paid) game so the client's buy-game surface
     * (GameDetailModel -> PUT /shop/api/v2/pay/game/{gameId}) has a real
     * target. Appended LAST with deliberately low online/praise/complex
     * metrics so it never displaces page-1 entries of any sorted list —
     * the hall drives and host tests keep their stable first games.
     * Runs on every boot; returns true when it appended the game
     * (migration for stores that predate the premium catalog), no-ops
     * once the premium game exists.
     */
    private static boolean ensurePremium(JSONObject root) {
        JSONArray gs = root.optJSONArray("games");
        if (gs == null) return false;
        for (int i = 0; i < gs.length(); i++) {
            JSONObject g = gs.optJSONObject(i);
            if (g != null && g.optInt("isPay") == 1) return false; // already present
        }
        long now = System.currentTimeMillis();
        JSONObject g = new JSONObject();
        g.put("gameId", "5043");
        g.put("gameTitle", "Mystic Vault");
        g.put("gameName", "Mystic Vault");
        g.put("gameCoverPic", "");
        g.put("bannerPic", new JSONArray());
        g.put("gameBannerVideoInfos", new JSONArray());
        g.put("gameDetail", "A premium locally hosted experience. "
                + "Unlock it once with diamonds — everything runs on your own server.");
        JSONArray types = new JSONArray();
        types.put("Mini Games");
        g.put("gameTypes", types);
        g.put("appreciate", false);
        g.put("gameMode", 1);
        g.put("visitorEnter", 0);
        g.put("version", 1);
        g.put("isRankOnline", 1);
        g.put("isShopOnline", 0);
        g.put("isOpenParty", 0);
        g.put("isPay", 1);
        // GamePayInfo (client Game entity, src_classes3 greendao Game.java):
        // qty = price, currency 1 = diamonds / 2 = golds. 800 diamonds —
        // affordable out of the box, real deduction on purchase.
        JSONObject pay = new JSONObject();
        pay.put("qty", 800);
        pay.put("currency", 1);
        pay.put("orderType", 0);
        pay.put("productId", "premium_game_5043");
        pay.put("desc", "Unlock Mystic Vault");
        g.put("gamePayInfo", pay);
        g.put("turntableStatus", 0);
        g.put("turntableRemainCount", 0);
        g.put("isNewEngine", 0);
        g.put("isUgcGame", 0);
        g.put("gameUgcType", "");
        g.put("currentPage", 0);
        g.put("currentSize", 0);
        g.put("resVersion", 1);
        g.put("pageType", 0);
        g.put("typeId", 106);
        g.put("createTime", now);
        // lowest metrics of the whole catalog -> sorts LAST everywhere
        g.put("complexNum", 1);
        g.put("praiseNumber", 1);
        g.put("onlineNumber", 1);
        g.put("index", 9999);
        JSONObject latest = new JSONObject();
        latest.put("cresVersion", 1);
        latest.put("dresVersion", 1);
        latest.put("gresVersion", 1);
        g.put("latestResVersions", latest);
        gs.put(g);
        L.i("catalog: premium game 5043 (Mystic Vault) added");
        return true;
    }

    // ---------------------------------------------------------- ownership

    /** True when userId owns gameId (root.gamePurchases, persisted). */
    static synchronized boolean isOwned(StateStore store, long userId, String gameId) {
        JSONArray ps = store.root().optJSONArray("gamePurchases");
        if (ps == null) return false;
        for (int i = 0; i < ps.length(); i++) {
            JSONObject p = ps.optJSONObject(i);
            if (p != null && p.optLong("userId") == userId
                    && gameId.equals(p.optString("gameId"))) return true;
        }
        return false;
    }

    /** Append a purchase record (caller persists). */
    static synchronized void recordPurchase(StateStore store, long userId, String gameId,
                                            long price, int currency, String orderId) {
        JSONArray ps = store.root().optJSONArray("gamePurchases");
        if (ps == null) {
            ps = new JSONArray();
            store.root().put("gamePurchases", ps);
        }
        JSONObject p = new JSONObject();
        p.put("userId", userId);
        p.put("gameId", gameId);
        p.put("price", price);
        p.put("currency", currency);
        p.put("orderId", orderId);
        p.put("ts", System.currentTimeMillis());
        ps.put(p);
    }

    // ----------------------------------------------------------- generation

    /**
     * Real-catalog seed from the client's OWN ScriptSetting.csv (the APK's
     * assets/resources/Media/Scripts/ScriptSetting.csv, copied by
     * LocalServer.startIfNeeded into <files>/localapi/games_seed.csv).
     * Every enabled row becomes a real catalog game: the real script id
     * (g1008 -> gameId "1008"), the real default map, and the engine-form
     * script id kept in "scriptType" for the dispatch bridge. Rows the
     * client itself disables or that are dev templates are skipped.
     * Returns null when no seed file exists (host rigs without fixtures).
     */
    private static JSONArray seedFromScriptSetting(StateStore store) {
        File seed = new File(store.baseDir(), "games_seed.csv");
        if (!seed.exists() || seed.length() == 0) return null;
        JSONArray categories = store.root().optJSONArray("categories");
        String text;
        try {
            text = slurp(seed);
        } catch (Throwable t) {
            L.e("catalog: games_seed.csv unreadable: " + t);
            return null;
        }
        String[] lines = text.split("\r?\n");
        long now = System.currentTimeMillis();
        JSONArray games = new JSONArray();
        int index = 0;
        for (int li = 0; li < lines.length; li++) {
            String line = lines[li].trim();
            if (line.isEmpty()) continue;
            if (li < 2) continue; // english + chinese header rows
            String[] c = line.split("\t");
            if (c.length < 9) continue;
            String scriptType = c[0].trim();
            if (!scriptType.matches("g[0-9]+")) continue;
            String name = c[2].trim();
            String mapName = c[4].trim();
            String remark = c[8].trim();
            // dev templates are never player-facing games. NOTE: the Enable
            // column is the client-side SCRIPT auto-enable flag, NOT the
            // hall catalog — real BG lists every game in the hall even when
            // the script row ships Enable=0, so no enable filtering here.
            if (name.equals("Sample") || name.equals("Template")
                    || name.equals("GameTool")) {
                continue;
            }
            long gameId = Long.parseLong(scriptType.substring(1));
            JSONObject g = new JSONObject();
            g.put("gameId", String.valueOf(gameId));
            String title = displayName(name);
            g.put("gameTitle", title);
            g.put("gameName", title);
            g.put("remark", remark);            // the original display name
            g.put("scriptType", scriptType);    // engine ScriptSetting key
            g.put("mapName", mapName);          // real default map
            g.put("gameCoverPic", "");
            g.put("bannerPic", new JSONArray());
            g.put("gameBannerVideoInfos", new JSONArray());
            g.put("gameDetail", remark + " — running locally on your own server.");
            long typeId = categoryIdFor(name, categories);
            JSONArray types = new JSONArray();
            types.put(categoryNameFor(categories, typeId));
            g.put("gameTypes", types);
            g.put("appreciate", false);
            g.put("gameMode", 1);
            g.put("visitorEnter", 1);
            g.put("version", 1);
            g.put("isRankOnline", 1);
            g.put("isShopOnline", 1);
            g.put("isOpenParty", 1);
            g.put("isPay", 0);
            g.put("turntableStatus", 0);
            g.put("turntableRemainCount", 0);
            g.put("isNewEngine", 0);   // engine-1 only — the bundled runtime
            g.put("isUgcGame", 0);
            g.put("gameUgcType", "");
            g.put("currentPage", 0);
            g.put("currentSize", 0);
            g.put("resVersion", 1);
            g.put("pageType", 0);
            g.put("typeId", typeId);
            g.put("createTime", now - (200L - index) * 86_400_000L);
            g.put("complexNum", 60 + (index * 41) % 480);
            g.put("praiseNumber", 150 + (index * 97) % 4200);
            g.put("onlineNumber", 40 + (index * 59) % 2600);
            g.put("index", index++);
            JSONObject latest = new JSONObject();
            latest.put("cresVersion", 1);
            latest.put("dresVersion", 1);
            latest.put("gresVersion", 1);
            g.put("latestResVersions", latest);
            games.put(g);
        }
        if (games.length() == 0) return null;
        L.i("catalog: seeded " + games.length() + " real games from ScriptSetting");
        return games;
    }

    /** CamelCase script name -> display name ("BedWar" -> "Bed War"). */
    private static String displayName(String scriptName) {
        return scriptName
                .replaceAll("([a-z0-9])([A-Z])", "$1 $2")
                .replaceAll("([A-Z]+)([A-Z][a-z])", "$1 $2");
    }

    /**
     * Hall category for a real game, from its script name. Keeps the six
     * persisted category tabs; assignment is heuristic (the seed carries no
     * category column) and stays editable state after seeding.
     */
    private static long categoryIdFor(String scriptName, JSONArray categories) {
        String n = scriptName.toLowerCase(Locale.US);
        boolean parkour = n.contains("parkour") || n.equals("tntrun");
        boolean sandbox = n.contains("skyblock") || n.contains("blockcity")
                || n.contains("tycoon") || n.contains("ranchers")
                || n.contains("lifting") || n.contains("bird")
                || n.contains("tinytown") || n.contains("lschampion");
        boolean shooter = n.contains("pixelgun") || n.contains("gunbattle")
                || n.contains("gbstrike") || n.equals("chicken")
                || n.contains("watchcar");
        boolean role = n.contains("murder") || n.contains("hideandseek")
                || n.contains("hashidden") || n.contains("haschase")
                || n.contains("hashall") || n.contains("jailbreak");
        long want = parkour ? 101L : sandbox ? 102L : role ? 104L
                : shooter ? 105L : 103L;
        for (int i = 0; categories != null && i < categories.length(); i++) {
            JSONObject c = categories.optJSONObject(i);
            if (c != null && c.optLong("typeId") == want) return want;
        }
        return categories == null || categories.length() == 0 ? want
                : categories.optJSONObject(0).optLong("typeId");
    }

    private static String categoryNameFor(JSONArray categories, long typeId) {
        for (int i = 0; categories != null && i < categories.length(); i++) {
            JSONObject c = categories.optJSONObject(i);
            if (c != null && c.optLong("typeId") == typeId) {
                return c.optString("typeName");
            }
        }
        return "";
    }

    private static String slurp(File f) throws Exception {
        java.io.FileInputStream in = new java.io.FileInputStream(f);
        try {
            java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
            return new String(bos.toByteArray(), "UTF-8");
        } finally {
            in.close();
        }
    }

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
            g.put("isNewEngine", 0);
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

    /**
     * DELETE /game/api/v1/game/chat/room?roomId= — drop a chat-room binding.
     * The client deletes the room when it leaves a game chat; the local world
     * treats that as truth: the name->id binding is forgotten so a later
     * request for the same room name issues a fresh room id.
     *
     * @return true if a binding existed and was removed.
     */
    static synchronized boolean removeChatRoom(StateStore store, String roomId) {
        if (roomId == null || roomId.isEmpty()) return false;
        JSONObject rooms = store.root().optJSONObject("chatRooms");
        String[] names = JSONObject.getNames(rooms);
        boolean removed = false;
        for (int i = 0; names != null && i < names.length; i++) {
            if (roomId.equals(rooms.optString(names[i]))) {
                rooms.remove(names[i]);
                removed = true;
            }
        }
        if (removed) store.save();
        return removed;
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
            // the premium game keeps its deliberately-low metrics: drift
            // derives counts from the ARRAY INDEX, and the appended-last
            // premium entry would otherwise get the highest online count
            // of the catalog (first in every online-sorted list — the
            // exact displacement ensurePremium exists to prevent).
            if (g.optInt("isPay") == 1) continue;
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
