package com.localapi;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Scrap collect-exchange domain: per-user scrap backpack, exchange cards,
 * combining (consumes scraps, credits the reward, records history).
 */
final class ScrapBag {

    static final String[] SCRAP_IDS = {"s1", "s2", "s3", "s4", "s5", "s6"};

    private ScrapBag() {}

    /** Generate (once, per user) a starting backpack of scraps. */
    static synchronized JSONObject backpack(StateStore store, JSONObject user) {
        JSONObject st = store.userState(user);
        JSONObject bag = st.optJSONObject("scraps");
        if (bag == null) {
            bag = new JSONObject();
            for (int i = 0; i < SCRAP_IDS.length; i++) {
                bag.put(SCRAP_IDS[i], 2 + (i * 3) % 8);
            }
            st.put("scraps", bag);
            store.save();
        }
        return bag;
    }

    static synchronized int scrapNum(StateStore store, JSONObject user, String scrapId) {
        return backpack(store, user).optInt(scrapId);
    }

    static synchronized void addScrap(StateStore store, JSONObject user, String scrapId,
                                      int delta) {
        JSONObject bag = backpack(store, user);
        bag.put(scrapId, Math.max(0, bag.optInt(scrapId) + delta));
        store.save();
    }

    static int valueOf(String scrapId) {
        try {
            return 100 * Integer.parseInt(scrapId.substring(1));
        } catch (Throwable t) {
            return 100;
        }
    }

    static synchronized int bagValue(StateStore store, JSONObject user) {
        JSONObject bag = backpack(store, user);
        int total = 0;
        JSONArray keys = bag.names();
        if (keys != null) {
            for (int i = 0; i < keys.length(); i++) {
                total += bag.optInt(keys.optString(i)) * valueOf(keys.optString(i));
            }
        }
        return total;
    }

    /** ScrapInfo JSON rows for a card's requirement list. */
    static JSONArray scrapInfos(String[] ids, int[] nums) {
        JSONArray arr = new JSONArray();
        for (int i = 0; i < ids.length; i++) {
            JSONObject s = new JSONObject();
            s.put("scrapId", ids[i]);
            s.put("scrapName", "Scrap " + ids[i].toUpperCase());
            s.put("scrapDesc", "A fragment used for exchange.");
            s.put("scrapPic", "");
            s.put("scrapNum", nums[i]);
            s.put("scrapValue", valueOf(ids[i]));
            arr.put(s);
        }
        return arr;
    }

    /** Card catalog: 6 cards, each requiring two scrap kinds. */
    static JSONObject card(String cardId) {
        try {
            int n = Integer.parseInt(cardId.substring(1));
            if (n < 1 || n > 6) return null;
            String[] ids = {SCRAP_IDS[(n - 1) % 6], SCRAP_IDS[n % 6]};
            int[] nums = {n + 1, n};
            JSONObject c = new JSONObject();
            c.put("cardId", cardId);
            c.put("cardName", "Reward " + n);
            c.put("cardPic", "");
            c.put("cardQuality", (n % 3) + 1);
            c.put("cardValue", 300 * n);
            c.put("needs", scrapInfos(ids, nums));
            return c;
        } catch (Throwable t) {
            return null;
        }
    }

    /** Consume scraps + credit the reward; appends a history row. */
    static synchronized JSONObject combine(StateStore store, JSONObject user,
                                           String cardId, int amount) {
        JSONObject card = card(cardId);
        if (card == null || amount < 1) return null;
        JSONArray needs = card.optJSONArray("needs");
        JSONObject bag = backpack(store, user);
        for (int i = 0; i < needs.length(); i++) {
            JSONObject s = needs.getJSONObject(i);
            if (bag.optInt(s.optString("scrapId")) < s.optInt("scrapNum") * amount) {
                return null; // not enough scraps
            }
        }
        for (int i = 0; i < needs.length(); i++) {
            JSONObject s = needs.getJSONObject(i);
            addScrap(store, user, s.optString("scrapId"), -s.optInt("scrapNum") * amount);
        }
        long reward = card.optLong("cardValue") * amount;
        store.award(user, "golds", reward);
        JSONObject st = store.userState(user);
        JSONArray hist = st.optJSONArray("combineHistory");
        if (hist == null) {
            hist = new JSONArray();
            st.put("combineHistory", hist);
        }
        java.text.SimpleDateFormat fmt =
                new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.US);
        fmt.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
        JSONObject row = new JSONObject();
        row.put("rewardName", card.optString("cardName"));
        row.put("rewardPic", "");
        row.put("cardQuality", card.optInt("cardQuality"));
        row.put("amount", amount);
        row.put("combineTime", fmt.format(new java.util.Date()));
        hist.put(row);
        store.save();
        JSONObject out = new JSONObject();
        out.put("amount", amount);
        out.put("cardName", card.optString("cardName"));
        out.put("rewardType", 1);
        out.put("decorationType", 0);
        out.put("expire", 0);
        out.put("gameId", "");
        out.put("goldsCredited", reward);
        return out;
    }
}
