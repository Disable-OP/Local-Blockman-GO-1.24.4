package com.localapi;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Decoration ("dress") + dress-shop domain for the local API.
 *
 * Per-typeId dress catalogs are GENERATED once on first request and persisted
 * (root.dresses[typeId]); ownership/wearing lives in each user's wardrobe
 * state. Buying really deducts currency from the user's wallet.
 */
final class DressShop {

    private DressShop() {}

    // ------------------------------------------------------------- catalog

    /** Generate (once) and return the dress catalog for one typeId. */
    static synchronized JSONArray ensureType(StateStore store, long typeId) {
        JSONObject all = store.root().optJSONObject("dresses");
        if (all == null) {
            all = new JSONObject();
            store.root().put("dresses", all);
        }
        String key = String.valueOf(typeId);
        JSONArray list = all.optJSONArray(key);
        if (list != null) return list;
        String[] words = {"Star", "Retro", "Neon", "Pixel", "Cloud", "Shadow", "Golden",
                "Cyber", "Frost", "Blaze"};
        String[] slots = {"Cap", "Jacket", "Suit", "Cape", "Boots", "Visor", "Pack",
                "Aura", "Gloves", "Mask"};
        list = new JSONArray();
        for (int i = 0; i < 10; i++) {
            JSONObject d = new JSONObject();
            d.put("id", 300000L + typeId * 100 + i);
            d.put("typeId", typeId);
            d.put("name", words[i] + " " + slots[i % slots.length]);
            d.put("details", "Locally crafted " + slots[i % slots.length].toLowerCase()
                    + " for your avatar.");
            d.put("iconUrl", "");
            d.put("currency", (i % 3 == 0) ? 2 : 1);
            d.put("price", 200 + (i * 260) % 2600);
            d.put("sex", 0);
            d.put("expire", 0);
            d.put("status", 1);
            d.put("itemType", 1);
            d.put("quantity", 1);
            d.put("isNew", (i % 4 == 0) ? 1 : 0);
            d.put("hasPurchase", 0);
            d.put("resourceId", "dress-" + typeId + "-" + i);
            d.put("releaseTime", System.currentTimeMillis() - (10L - i) * 86_400_000L);
            list.put(d);
        }
        all.put(key, list);
        store.save();
        return list;
    }

    /** Find a dress anywhere in the persisted catalogs. */
    static synchronized JSONObject byId(StateStore store, long dressId) {
        JSONObject all = store.root().optJSONObject("dresses");
        if (all == null) return null;
        JSONArray keys = all.names();
        if (keys == null) return null;
        for (int i = 0; i < keys.length(); i++) {
            JSONArray list = all.optJSONArray(keys.optString(i));
            if (list == null) continue;
            for (int j = 0; j < list.length(); j++) {
                JSONObject d = list.optJSONObject(j);
                if (d != null && d.optLong("id") == dressId) return d;
            }
        }
        return null;
    }

    /** SingleDressInfo JSON from a stored dress (plus ownership flags). */
    static JSONObject singleJson(StateStore store, JSONObject user, JSONObject d) {
        JSONObject out = new JSONObject(d.toString());
        out.put("decorationInfoList", new JSONArray());
        out.put("limitedTimes", new JSONArray());
        out.put("tag", new JSONArray());
        out.put("occupyPosition", new JSONArray());
        out.put("suitId", 0);
        out.put("suitPrice", 0);
        out.put("remainingDays", 0);
        out.put("orderField", 0);
        out.put("isActivity", 0);
        out.put("isDressRec", false);
        out.put("isRecommend", 0);
        out.put("blankType", 0);
        out.put("clanLevel", 0);
        out.put("buySuccess", false);
        out.put("activityFlag", "");
        out.put("hasPurchase", owned(store, user, d.optLong("id")) ? 1 : 0);
        return out;
    }

    // ------------------------------------------------------------ wardrobe

    /** Per-user wardrobe: {owned: [id...], using: [id...]}. */
    static synchronized JSONObject wardrobe(StateStore store, JSONObject user) {
        JSONObject st = store.userState(user);
        JSONObject w = st.optJSONObject("wardrobe");
        if (w == null) {
            w = new JSONObject();
            w.put("owned", new JSONArray());
            w.put("using", new JSONArray());
            st.put("wardrobe", w);
        }
        return w;
    }

    static boolean owned(StateStore store, JSONObject user, long dressId) {
        JSONArray owned = wardrobe(store, user).optJSONArray("owned");
        if (owned != null) {
            for (int i = 0; i < owned.length(); i++) {
                if (owned.optLong(i) == dressId) return true;
            }
        }
        return false;
    }

    static synchronized void markOwned(StateStore store, JSONObject user, long dressId) {
        JSONObject w = wardrobe(store, user);
        JSONArray owned = w.optJSONArray("owned");
        if (owned == null) {
            owned = new JSONArray();
            w.put("owned", owned);
        }
        for (int i = 0; i < owned.length(); i++) {
            if (owned.optLong(i) == dressId) return;
        }
        owned.put(dressId);
        store.save();
    }

    static synchronized void setUsing(StateStore store, JSONObject user, JSONArray ids,
                                      boolean wear) {
        JSONObject w = wardrobe(store, user);
        JSONArray using = w.optJSONArray("using");
        if (using == null) {
            using = new JSONArray();
            w.put("using", using);
        }
        for (int i = 0; i < ids.length(); i++) {
            long id = ids.optLong(i);
            boolean found = false;
            for (int j = 0; j < using.length(); j++) {
                if (using.optLong(j) == id) {
                    found = true;
                    if (!wear) using.remove(j);
                    break;
                }
            }
            if (wear && !found) using.put(id);
        }
        store.save();
    }

    static synchronized JSONArray usingList(StateStore store, JSONObject user) {
        JSONArray using = wardrobe(store, user).optJSONArray("using");
        JSONArray out = new JSONArray();
        if (using == null) return out;
        for (int i = 0; i < using.length(); i++) {
            JSONObject d = byId(store, using.optLong(i));
            if (d != null) out.put(singleJson(store, user, d));
        }
        return out;
    }

    // ----------------------------------------------------------------- buy

    /**
     * Deduct the price from the user's wallet and mark ownership.
     * currency: 1 = diamonds, 2 = golds (verified from client usage: the
     * recharge dialog shows ic_diamond for currency 1; the dress checkout
     * checks the currency!=2 total against the diamonds balance).
     * Returns false when the user cannot afford it or the dress is unknown.
     */
    static synchronized boolean buy(StateStore store, JSONObject user, long dressId) {
        JSONObject d = byId(store, dressId);
        if (d == null) return false;
        long price = d.optLong("price");
        String kind = d.optInt("currency") == 2 ? "golds" : "diamonds";
        if (user.optLong(kind) < price) return false;
        store.award(user, kind, -price);
        markOwned(store, user, dressId);
        d.put("hasPurchase", 1);
        store.save();
        return true;
    }

    /** BuyDressResponse JSON: per-id status + totals that WOULD be needed. */
    static JSONObject buyResponse(JSONArray ids, JSONArray okIds, long goldsNeed,
                                  long diamondsNeed) {
        JSONObject r = new JSONObject();
        JSONObject status = new JSONObject();
        for (int i = 0; i < ids.length(); i++) {
            String k = String.valueOf(ids.optLong(i));
            boolean ok = false;
            for (int j = 0; j < okIds.length(); j++) {
                if (String.valueOf(okIds.optLong(j)).equals(k)) {
                    ok = true;
                    break;
                }
            }
            status.put(k, ok);
        }
        r.put("decorationPurchaseStatus", status);
        r.put("suitPurchaseStatus", new JSONObject());
        r.put("goldsNeed", goldsNeed);
        r.put("diamondsNeed", diamondsNeed);
        r.put("needShowAds", false);
        return r;
    }
}
