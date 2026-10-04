package com.localapi;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Decoration-suit ("dress suit") domain for the local API.
 *
 * Suits are generated once on first request and persisted (root.suits).
 * Each suit bundles existing dresses from the DressShop per-typeId catalogs.
 * Ownership lives in the user's state (state.ownedSuits); the gift suit can
 * be claimed once per account (state.giftSuitClaimed).
 */
final class Suits {

    /** typeId values already used by DressShop.ensureType callers (host tests use 101). */
    static final long[] SUIT_TYPES = {101, 102, 103};

    private Suits() {}

    /** Generate (once) and return the persisted suit catalog. */
    static synchronized JSONArray ensureSuits(StateStore store) {
        JSONObject root = store.root();
        JSONArray suits = root.optJSONArray("suits");
        if (suits != null) return suits;
        String[] names = {"Star Captain", "Neon Drifter", "Frost Warden",
                "Blaze Vanguard", "Shadow Courier", "Golden Pioneer"};
        String[] details = {
                "A locally crafted captain outfit for the bold.",
                "Glow with the neon grid in this full set.",
                "Stay cold, stay sharp — the frost set.",
                "Lead the charge in blazing colors.",
                "Move unseen with the courier set.",
                "For those who got here first."};
        suits = new JSONArray();
        long base = System.currentTimeMillis() - 30L * 86_400_000L;
        for (int i = 0; i < names.length; i++) {
            JSONObject s = new JSONObject();
            long suitId = 600001L + i;
            s.put("suitId", suitId);
            s.put("name", names[i] + " Set");
            s.put("details", details[i]);
            s.put("iconUrl", "");
            s.put("currency", (i % 3 == 0) ? 2 : 1);
            s.put("status", 1);
            s.put("itemType", 2);
            s.put("quantity", 1);
            s.put("expire", 0);
            s.put("isNew", (i % 3 == 0) ? 1 : 0);
            s.put("isRecommend", (i % 2 == 0) ? 1 : 0);
            s.put("isActivity", 0);
            s.put("activityFlag", "");
            s.put("blankType", 0);
            s.put("hasLocalRes", false);
            s.put("hasPurchase", 0);
            s.put("buyTime", "");
            s.put("remainingDays", 0);
            s.put("releaseTime", base + i * 86_400_000L);
            s.put("tag", new JSONArray());

            // bundle 4 real dresses: pick ids 300000+typeId*100+{0,3,5,7} and price them
            JSONArray dressIds = new JSONArray();
            long price = 0;
            int currency = (i % 3 == 0) ? 2 : 1;
            for (int t = 0; t < SUIT_TYPES.length; t++) {
                JSONArray typeList = DressShop.ensureType(store, SUIT_TYPES[t]);
                int[] picks = {0, 3, 5};
                for (int p = 0; p < picks.length && dressIds.length() < 8; p++) {
                    JSONObject d = typeList.optJSONObject(picks[p] % typeList.length());
                    if (d == null) continue;
                    dressIds.put(d.optLong("id"));
                    price += d.optLong("price");
                }
            }
            // suit discount ~70% of the summed components; keeps wallet math real
            price = Math.round(price * 0.7d);
            s.put("price", (int) price);
            s.put("dressIds", dressIds);
            suits.put(s);
        }
        root.put("suits", suits);
        store.save();
        return suits;
    }

    /** Find a suit by id in the persisted catalog. */
    static synchronized JSONObject byId(StateStore store, long suitId) {
        JSONArray suits = store.root().optJSONArray("suits");
        for (int i = 0; suits != null && i < suits.length(); i++) {
            JSONObject s = suits.optJSONObject(i);
            if (s != null && s.optLong("suitId") == suitId) return s;
        }
        return null;
    }

    /** The one-time gift suit (the first generated suit). */
    static JSONObject giftSuit(StateStore store) {
        JSONArray suits = ensureSuits(store);
        return suits.optJSONObject(0);
    }

    // ------------------------------------------------------------- ownership

    /** Owned suit ids of a user (lazy array in user state). */
    static synchronized JSONArray ownedSuits(StateStore store, JSONObject user) {
        JSONObject st = store.userState(user);
        JSONArray owned = st.optJSONArray("ownedSuits");
        if (owned == null) {
            owned = new JSONArray();
            st.put("ownedSuits", owned);
        }
        return owned;
    }

    static boolean owned(StateStore store, JSONObject user, long suitId) {
        JSONArray owned = ownedSuits(store, user);
        for (int i = 0; i < owned.length(); i++) {
            if (owned.optLong(i) == suitId) return true;
        }
        return false;
    }

    static synchronized void markOwned(StateStore store, JSONObject user, long suitId) {
        if (owned(store, user, suitId)) return;
        ownedSuits(store, user).put(suitId);
        store.save();
    }

    /** One-time gift claim flag on the user state. */
    static boolean giftClaimed(StateStore store, JSONObject user) {
        return store.userState(user).optBoolean("giftSuitClaimed");
    }

    static synchronized void markGiftClaimed(StateStore store, JSONObject user) {
        store.userState(user).put("giftSuitClaimed", true);
        store.save();
    }

    // ----------------------------------------------------------------- JSON

    /** Full SuitDressInfo JSON (components embedded as SingleDressInfo lists). */
    static JSONObject suitJson(StateStore store, JSONObject user, JSONObject s) {
        JSONObject out = new JSONObject(s.toString());
        JSONArray comps = out.optJSONArray("dressIds");
        JSONArray componentJson = new JSONArray();
        for (int i = 0; comps != null && i < comps.length(); i++) {
            JSONObject d = DressShop.byId(store, comps.optLong(i));
            if (d != null) componentJson.put(DressShop.singleJson(store, user, d));
        }
        out.put("decorationInfoList", componentJson);
        out.put("shopDecorationInfos", componentJson);
        out.put("limitedTimes", new JSONArray());
        out.put("hasPurchase", owned(store, user, out.optLong("suitId")) ? 1 : 0);
        out.put("buyTime", owned(store, user, out.optLong("suitId"))
                ? String.valueOf(System.currentTimeMillis()) : "");
        return out;
    }

    /**
     * Buy a suit for real: deduct the suit price, mark the suit AND all
     * component dresses owned. Returns false when unknown or unaffordable.
     */
    static synchronized boolean buy(StateStore store, JSONObject user, long suitId) {
        JSONObject s = byId(store, suitId);
        if (s == null || owned(store, user, suitId)) return false;
        String kind = s.optInt("currency") == 2 ? "golds" : "diamonds";
        if (user.optLong(kind) < s.optLong("price")) return false;
        store.award(user, kind, -s.optLong("price"));
        markOwned(store, user, suitId);
        JSONArray comps = s.optJSONArray("dressIds");
        for (int i = 0; comps != null && i < comps.length(); i++) {
            DressShop.markOwned(store, user, comps.optLong(i));
        }
        s.put("hasPurchase", 1);
        store.save();
        return true;
    }
}
