package com.localapi;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Phase 4: tribe (clan) domain — real persistent state on top of StateStore.
 *
 * Everything lives in the shared store root:
 *   root.tribes      : { "<clanId>": clan }
 *   root.nextClanId  : long counter
 *   clan = { clanId, name, details, headPic, tags[], experience, currency,
 *            freeVerify, chiefId, members[{userId, role, experience, expireDate,
 *            headPic, nickName, status, vip}], bulletin{content,updateTime},
 *            joinRequests[{userId, msg, at, status}], invitations[{id, userId, msg, at, status}],
 *            donations[{date, userId, nickName, quantity, currency, experienceGot, tribeCurrencyGot}],
 *            purchases[{userId, decorationId, at}], createdAt }
 *
 * Roles match the client (TribeClanMembersBean/getStringRole):
 *   20 = chief, 10 = elder, 0 = member.
 * Donation currency mapping (client event names clan_gold_donate_suc / clan_cube_donate_suc):
 *   1 = diamonds ("cube"), 2 = golds.
 * A user's membership is stored on the user object ("clanId"); the role lives in
 * the clan's members[] entry. Personal tribe currency (shop credit) is user
 * state "tribeCurrency".
 */
final class Tribe {

    private Tribe() {}

    // Client-visible pricing (Phase 7): TribeCreateViewModel gates the golds
    // path at golds >= 8000 (n.java h()), and when golds are short the
    // TribeCreateDialog says "Inadequate coins, cost 60 ... to create a clan?"
    // (tribe_sure_pay_60_diamond). The server must not charge more than the
    // client promises.
    public static final long CREATE_FEE_GOLDS = 8000L;
    public static final long CREATE_FEE_DIAMONDS = 60L;
    public static final int MAX_MEMBERS_BASE = 20;

    // ------------------------------------------------------------ store plumbing

    private static JSONObject clans(StateStore store) {
        JSONObject root = store.root();
        JSONObject t = root.optJSONObject("tribes");
        if (t == null) {
            t = new JSONObject();
            root.put("tribes", t);
        }
        return t;
    }

    private static long nextClanId(StateStore store) {
        JSONObject root = store.root();
        long id = root.optLong("nextClanId", 50001L);
        root.put("nextClanId", id + 1);
        return id;
    }

    public static JSONObject find(StateStore store, long clanId) {
        if (clanId <= 0) return null;
        return clans(store).optJSONObject(String.valueOf(clanId));
    }

    /** The clan the user belongs to, or null. */
    public static JSONObject clanOf(StateStore store, JSONObject user) {
        return find(store, user.optLong("clanId"));
    }

    /** Find a user's membership entry inside a clan (null when absent). */
    public static JSONObject memberOf(JSONObject clan, long userId) {
        JSONArray members = clan.optJSONArray("members");
        if (members == null) return null;
        for (int i = 0; i < members.length(); i++) {
            JSONObject m = members.optJSONObject(i);
            if (m != null && m.optLong("userId") == userId) return m;
        }
        return null;
    }

    /** Caller's role in the given clan: 20 chief / 10 elder / 0 member / -1 none. */
    public static int roleOf(JSONObject clan, long userId) {
        JSONObject m = memberOf(clan, userId);
        return m == null ? -1 : m.optInt("role");
    }

    // ------------------------------------------------------------ lifecycle

    /** Create a clan; pays the creation fee from the caller's wallet. Returns error string or null. */
    public static String create(StateStore store, JSONObject user, String name, String details,
                                String headPic, JSONArray tags, int currency) {
        long userId = user.optLong("userId");
        if (user.optLong("clanId") > 0) return "already in a clan";
        if (name == null || name.trim().isEmpty()) return "clan name required";
        name = name.trim().replace("\n", " ");
        // uniqueness across clans
        JSONArray ids = clans(store).names();
        if (ids != null) {
            for (int i = 0; i < ids.length(); i++) {
                JSONObject c = clans(store).optJSONObject(ids.optString(i));
                if (c != null && name.equalsIgnoreCase(c.optString("name"))) return "clan name taken";
            }
        }
        long fee = (currency == 1) ? CREATE_FEE_DIAMONDS : CREATE_FEE_GOLDS;
        String wallet = (currency == 1) ? "diamonds" : "golds";
        if (user.optLong(wallet) < fee) return "not enough " + wallet + " to create a clan";
        store.award(user, wallet, -fee);

        long clanId = nextClanId(store);
        JSONObject clan = new JSONObject();
        clan.put("clanId", clanId);
        clan.put("name", name);
        clan.put("details", details == null ? "" : details);
        clan.put("headPic", headPic == null ? "" : headPic);
        clan.put("tags", tags == null ? new JSONArray() : tags);
        clan.put("experience", 0L);
        clan.put("currency", 0L);
        clan.put("freeVerify", 0);
        clan.put("chiefId", userId);
        clan.put("createdAt", System.currentTimeMillis());
        JSONArray members = new JSONArray();
        members.put(memberEntry(user, 20));
        clan.put("members", members);
        clan.put("bulletin", new JSONObject());
        clan.put("joinRequests", new JSONArray());
        clan.put("invitations", new JSONArray());
        clan.put("donations", new JSONArray());
        clan.put("purchases", new JSONArray());
        clans(store).put(String.valueOf(clanId), clan);
        user.put("clanId", clanId);
        store.save();
        return null;
    }

    private static JSONObject memberEntry(JSONObject user, int role) {
        JSONObject m = new JSONObject();
        m.put("userId", user.optLong("userId"));
        m.put("role", role);
        m.put("experience", 0);
        m.put("expireDate", user.optString("expireDate"));
        m.put("headPic", user.optString("picUrl"));
        m.put("nickName", user.optString("nickName"));
        m.put("status", 0);
        m.put("vip", user.optInt("vip"));
        return m;
    }

    /** Dissolve: chief only; clears membership of every member. */
    public static String dissolve(StateStore store, JSONObject user) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        if (roleOf(clan, user.optLong("userId")) != 20) return "only the chief can dissolve";
        JSONArray members = clan.optJSONArray("members");
        if (members != null) {
            for (int i = 0; i < members.length(); i++) {
                JSONObject m = members.optJSONObject(i);
                if (m == null) continue;
                JSONObject u = store.findByUserId(m.optLong("userId"));
                if (u != null) {
                    u.put("clanId", 0);
                    u.put("clanQuitAt", System.currentTimeMillis());
                }
            }
        }
        clans(store).remove(String.valueOf(clan.optLong("clanId")));
        store.save();
        return null;
    }

    /** Leave the clan (chief cannot leave). */
    public static String exit(StateStore store, JSONObject user) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        long uid = user.optLong("userId");
        int role = roleOf(clan, uid);
        if (role == 20) return "the chief cannot leave; dissolve instead";
        JSONArray members = clan.optJSONArray("members");
        JSONArray next = new JSONArray();
        if (members != null) {
            for (int i = 0; i < members.length(); i++) {
                JSONObject m = members.optJSONObject(i);
                if (m != null && m.optLong("userId") != uid) next.put(m);
            }
        }
        clan.put("members", next);
        user.put("clanId", 0);
        user.put("clanQuitAt", System.currentTimeMillis());
        store.save();
        return null;
    }

    /** Kick a member (chief/elder, target must be a plain member). */
    public static String kick(StateStore store, JSONObject user, long otherId) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        int role = roleOf(clan, user.optLong("userId"));
        if (role != 20 && role != 10) return "no permission";
        JSONObject target = memberOf(clan, otherId);
        if (target == null) return "not a member";
        if (target.optInt("role") > 0) return "cannot remove chiefs or elders";
        JSONArray members = clan.optJSONArray("members");
        JSONArray next = new JSONArray();
        if (members != null) {
            for (int i = 0; i < members.length(); i++) {
                JSONObject m = members.optJSONObject(i);
                if (m != null && m.optLong("userId") != otherId) next.put(m);
            }
        }
        clan.put("members", next);
        JSONObject u = store.findByUserId(otherId);
        if (u != null) {
            u.put("clanId", 0);
            u.put("clanQuitAt", System.currentTimeMillis());
        }
        store.save();
        return null;
    }

    /** Chief sets a member's identity: type 10 = elder, 0 = member. */
    public static String setIdentity(StateStore store, JSONObject user, long otherId, int type) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        if (roleOf(clan, user.optLong("userId")) != 20) return "only the chief can set roles";
        JSONObject target = memberOf(clan, otherId);
        if (target == null) return "not a member";
        if (target.optInt("role") == 20) return "cannot change the chief";
        if (type != 0 && type != 10) return "bad role type";
        target.put("role", type);
        store.save();
        return null;
    }

    // ------------------------------------------------------------ joining

    /**
     * Client-verified 24h rejoin cooldown (TribeOnError 7014 -> toast
     * "You can join after 24 hours"). Returns ms still left, or null when
     * the user may join.
     */
    static Long joinCooldownLeft(JSONObject user) {
        long quitAt = user.optLong("clanQuitAt");
        if (quitAt <= 0) return null;
        long left = quitAt + 24L * 60L * 60L * 1000L - System.currentTimeMillis();
        return left > 0 ? Long.valueOf(left) : null;
    }

    /** Request to join a clan (or auto-join when the clan is free-verify). */
    public static String requestJoin(StateStore store, JSONObject user, long clanId, String msg) {
        if (user.optLong("clanId") > 0) return "already in a clan";
        if (joinCooldownLeft(user) != null) return "you can join a clan again after 24 hours";
        JSONObject clan = find(store, clanId);
        if (clan == null) return "clan not found";
        if (members(clan).length() >= maxMembers(clan)) return "clan is full";
        long uid = user.optLong("userId");
        if (clan.optInt("freeVerify") == 1) {
            return join(store, clan, user);
        }
        JSONArray reqs = clan.optJSONArray("joinRequests");
        for (int i = 0; reqs != null && i < reqs.length(); i++) {
            JSONObject r = reqs.optJSONObject(i);
            if (r != null && r.optLong("userId") == uid && r.optInt("status") == 0) {
                return "already requested";
            }
        }
        JSONObject r = new JSONObject();
        r.put("userId", uid);
        r.put("msg", msg == null ? "" : msg);
        r.put("at", System.currentTimeMillis());
        r.put("status", 0);
        reqs.put(r);
        store.save();
        return null;
    }

    /** Chief/elder accepts a join request. */
    public static String agreeJoin(StateStore store, JSONObject user, long otherId) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        int role = roleOf(clan, user.optLong("userId"));
        if (role != 20 && role != 10) return "no permission";
        JSONArray reqs = clan.optJSONArray("joinRequests");
        JSONObject hit = null;
        for (int i = 0; reqs != null && i < reqs.length(); i++) {
            JSONObject r = reqs.optJSONObject(i);
            if (r != null && r.optLong("userId") == otherId && r.optInt("status") == 0) hit = r;
        }
        if (hit == null) return "no pending request";
        JSONObject candidate = store.findByUserId(otherId);
        if (candidate == null) return "user not found";
        if (candidate.optLong("clanId") > 0) {
            hit.put("status", 3);
            store.save();
            return "user already in a clan";
        }
        if (members(clan).length() >= maxMembers(clan)) return "clan is full";
        if (joinCooldownLeft(candidate) != null) {
            hit.put("status", 3);
            store.save();
            return "you can join a clan again after 24 hours";
        }
        hit.put("status", 2);
        String err = join(store, clan, candidate);
        if (err != null) return err;
        return null;
    }

    /** Chief/elder rejects a join request. */
    public static String rejectJoin(StateStore store, JSONObject user, long otherId) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        int role = roleOf(clan, user.optLong("userId"));
        if (role != 20 && role != 10) return "no permission";
        JSONArray reqs = clan.optJSONArray("joinRequests");
        boolean hit = false;
        for (int i = 0; reqs != null && i < reqs.length(); i++) {
            JSONObject r = reqs.optJSONObject(i);
            if (r != null && r.optLong("userId") == otherId && r.optInt("status") == 0) {
                r.put("status", 3);
                hit = true;
            }
        }
        if (!hit) return "no pending request";
        store.save();
        return null;
    }

    /** Chief/elder invites users (friendIds) into their clan. */
    public static String invite(StateStore store, JSONObject user, JSONArray friendIds, String msg) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        int role = roleOf(clan, user.optLong("userId"));
        if (role != 20 && role != 10) return "no permission";
        JSONArray inv = clan.optJSONArray("invitations");
        for (int i = 0; friendIds != null && i < friendIds.length(); i++) {
            long target = friendIds.optLong(i);
            if (target <= 0) continue;
            JSONObject u = store.findByUserId(target);
            if (u == null || u.optLong("clanId") > 0) continue; // unknown or already claned
            JSONObject inv2 = new JSONObject();
            inv2.put("id", nextInviteId(store));
            inv2.put("userId", user.optLong("userId")); // the inviter
            inv2.put("inviteeId", target);
            inv2.put("msg", msg == null ? "" : msg);
            inv2.put("at", System.currentTimeMillis());
            inv2.put("status", 0);
            inv.put(inv2);
        }
        store.save();
        return null;
    }

    private static long nextInviteId(StateStore store) {
        JSONObject root = store.root();
        long id = root.optLong("nextInviteId", 1L);
        root.put("nextInviteId", id + 1);
        return id;
    }

    /** Invitee accepts an invitation by message id. */
    public static String agreeInvitation(StateStore store, JSONObject user, long inviteId) {
        if (user.optLong("clanId") > 0) return "already in a clan";
        if (joinCooldownLeft(user) != null) return "you can join a clan again after 24 hours";
        JSONObject clan = findInvitationClan(store, inviteId, user.optLong("userId"));
        if (clan == null) return "invitation not found";
        if (members(clan).length() >= maxMembers(clan)) return "clan is full";
        markInvitation(clan, inviteId, 2);
        return join(store, clan, user);
    }

    /** Invitee rejects an invitation by message id. */
    public static String rejectInvitation(StateStore store, JSONObject user, long inviteId) {
        JSONObject clan = findInvitationClan(store, inviteId, user.optLong("userId"));
        if (clan == null) return "invitation not found";
        markInvitation(clan, inviteId, 3);
        store.save();
        return null;
    }

    private static JSONObject findInvitationClan(StateStore store, long inviteId, long inviteeId) {
        JSONArray ids = clans(store).names();
        if (ids == null) return null;
        for (int i = 0; i < ids.length(); i++) {
            JSONObject clan = clans(store).optJSONObject(ids.optString(i));
            JSONArray inv = clan == null ? null : clan.optJSONArray("invitations");
            for (int j = 0; inv != null && j < inv.length(); j++) {
                JSONObject v = inv.optJSONObject(j);
                if (v != null && v.optLong("id") == inviteId && v.optLong("inviteeId") == inviteeId) {
                    return clan;
                }
            }
        }
        return null;
    }

    private static void markInvitation(JSONObject clan, long inviteId, int status) {
        JSONArray inv = clan.optJSONArray("invitations");
        for (int j = 0; inv != null && j < inv.length(); j++) {
            JSONObject v = inv.optJSONObject(j);
            if (v != null && v.optLong("id") == inviteId) v.put("status", status);
        }
    }

    private static String join(StateStore store, JSONObject clan, JSONObject user) {
        JSONArray members = clan.optJSONArray("members");
        if (members == null) {
            members = new JSONArray();
            clan.put("members", members);
        }
        members.put(memberEntry(user, 0));
        user.put("clanId", clan.optLong("clanId"));
        store.save();
        return null;
    }

    // ------------------------------------------------------------ read helpers

    public static JSONArray members(JSONObject clan) {
        JSONArray m = clan.optJSONArray("members");
        return m == null ? new JSONArray() : m;
    }

    public static int maxMembers(JSONObject clan) {
        return MAX_MEMBERS_BASE + level(clan) * 2;
    }

    public static int level(JSONObject clan) {
        long exp = clan.optLong("experience");
        int lvl = 1 + (int) (exp / 1000L);
        return Math.min(lvl, 10);
    }

    /** User's personal tribe currency (contribution credit for the clan shop). */
    public static long tribeCurrency(JSONObject user) {
        return user.optLong("tribeCurrency");
    }

    /** Donation counters for the caller (clanId, current/max per currency, count). */
    public static JSONObject donationInfo(StateStore store, JSONObject user) {
        JSONObject clan = clanOf(store, user);
        JSONObject st = store.userState(user);
        JSONObject d = st.optJSONObject("donations");
        String today = utcDate();
        if (d == null || !today.equals(d.optString("date"))) {
            d = new JSONObject();
            d.put("date", today);
            d.put("gold", 0);
            d.put("diamond", 0);
            d.put("count", 0);
        }
        JSONObject out = new JSONObject();
        out.put("clanId", clan == null ? 0 : clan.optLong("clanId"));
        out.put("currentGold", d.optInt("gold"));
        out.put("maxGold", 20000);
        out.put("currentDiamond", d.optInt("diamond"));
        out.put("maxDiamond", 2000);
        out.put("currentTask", d.optInt("count"));
        out.put("maxTask", 10);
        out.put("currentExperience", clan == null ? 0 : (int) Math.min(clan.optLong("experience"), Integer.MAX_VALUE));
        out.put("maxExperience", level(clan == null ? new JSONObject() : clan) * 1000);
        out.put("level", clan == null ? 0 : level(clan));
        return out;
    }

    static String utcDate() {
        java.text.SimpleDateFormat fmt =
                new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US);
        fmt.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
        return fmt.format(new java.util.Date());
    }

    /** Apply a donation: wallet deduction + clan experience + personal tribe currency. */
    public static String donate(StateStore store, JSONObject user, int currency, int quantity) {
        if (quantity <= 0) return "bad quantity";
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        boolean gold = currency == 2;
        String wallet = gold ? "golds" : "diamonds";
        if (user.optLong(wallet) < quantity) return "not enough " + wallet;

        JSONObject st = store.userState(user);
        JSONObject d = st.optJSONObject("donations");
        String today = utcDate();
        if (d == null || !today.equals(d.optString("date"))) {
            d = new JSONObject();
            d.put("date", today);
            d.put("gold", 0);
            d.put("diamond", 0);
            d.put("count", 0);
        }
        int already = gold ? d.optInt("gold") : d.optInt("diamond");
        int cap = gold ? 20000 : 2000;
        if (already + quantity > cap) return "daily donation limit reached";
        if (d.optInt("count") >= 10) return "daily donation count limit reached";

        store.award(user, wallet, -quantity);
        int exp = gold ? quantity : quantity * 10;
        int got = Math.max(1, exp / 10);
        clan.put("experience", clan.optLong("experience") + exp);
        d.put(gold ? "gold" : "diamond", already + quantity);
        d.put("count", d.optInt("count") + 1);
        st.put("donations", d);
        user.put("tribeCurrency", tribeCurrency(user) + got);

        JSONArray hist = clan.optJSONArray("donations");
        if (hist == null) {
            hist = new JSONArray();
            clan.put("donations", hist);
        }
        JSONObject h = new JSONObject();
        h.put("date", System.currentTimeMillis());
        h.put("userId", user.optLong("userId"));
        h.put("nickName", user.optString("nickName"));
        h.put("quantity", quantity);
        h.put("type", currency);
        h.put("experienceGot", exp);
        h.put("tribeCurrencyGot", got);
        hist.put(h);
        store.save();
        return null;
    }

    /** Donations of the caller's clan, newest first (already capped by caller). */
    public static JSONArray donationHistory(StateStore store, JSONObject user) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return new JSONArray();
        JSONArray hist = clan.optJSONArray("donations");
        JSONArray out = new JSONArray();
        if (hist == null) return out;
        for (int i = hist.length() - 1; i >= 0; i--) {
            JSONObject h = hist.optJSONObject(i);
            if (h != null) out.put(h);
        }
        return out;
    }

    /** Set (chief/elder) or read the clan bulletin. */
    public static String setBulletin(StateStore store, JSONObject user, String content) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        int role = roleOf(clan, user.optLong("userId"));
        if (role != 20 && role != 10) return "no permission";
        JSONObject b = new JSONObject();
        b.put("content", content == null ? "" : content);
        b.put("updateTime", System.currentTimeMillis());
        clan.put("bulletin", b);
        store.save();
        return null;
    }

    /** Toggle free verification (chief only). */
    public static String setFreeVerify(StateStore store, JSONObject user, int freeVerify) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        if (roleOf(clan, user.optLong("userId")) != 20) return "only the chief can change verification";
        clan.put("freeVerify", freeVerify == 1 ? 1 : 0);
        store.save();
        return null;
    }

    // ------------------------------------------------------------ tasks

    /** Daily clan tasks derived from real state; progress computed on demand.
     *  type 1 = clan tasks, 2 = personal tasks. */
    public static JSONObject tasks(StateStore store, JSONObject user, int type) {
        JSONObject clan = clanOf(store, user);
        JSONObject st = store.userState(user);
        JSONObject prog = st.optJSONObject("tribeTaskProg");
        String today = utcDate();
        if (prog == null || !today.equals(prog.optString("date"))) {
            prog = new JSONObject();
            prog.put("date", today);
            prog.put("accepted", new JSONArray());
            prog.put("claimed", new JSONArray());
        }
        JSONArray accepted = prog.optJSONArray("accepted");
        JSONArray claimed = prog.optJSONArray("claimed");

        // progress sources (personal): donations today, played games today, sign-in today
        JSONObject d = st.optJSONObject("donations");
        int donated = (d != null && today.equals(d.optString("date"))) ? d.optInt("count") : 0;
        int played = playedToday(st, today);
        boolean signed = st.optJSONArray("signIns") != null && store.hasSignedIn(user, today);

        JSONArray defs = new JSONArray();
        if (type == 1) {
            defs.put(task(1, "Donate to the clan", 1, donated, 50, 100));
            defs.put(task(2, "Play 2 games with clan members", 2, played, 100, 200));
            defs.put(task(3, "Daily sign in", 1, signed ? 1 : 0, 30, 50));
        } else {
            defs.put(task(11, "Donate once", 1, donated, 30, 60));
            defs.put(task(12, "Play 3 games", 3, played, 60, 120));
        }
        JSONArray out = new JSONArray();
        for (int i = 0; i < defs.length(); i++) {
            JSONObject t = defs.optJSONObject(i);
            long tid = t.optLong("taskId");
            boolean acc = contains(accepted, tid);
            boolean clm = contains(claimed, tid);
            t.put("id", (int) tid);
            t.put("finished", t.optLong("need") <= t.optLong("__progress") ? 1 : 0);
            t.put("status", clm ? 3 : (acc ? (t.optInt("finished") == 1 ? 2 : 1) : 0));
            t.remove("__progress");
            out.put(t);
        }
        JSONObject res = new JSONObject();
        res.put("currencyCost", 0);
        res.put("currencyType", 1);
        res.put("nextFreeFlushTime", 0);
        res.put("remainTime", 0L);
        res.put("tasks", out);
        return res;
    }

    private static JSONObject task(int taskId, String name, long need, long progress,
                                   int currencyReward, int experienceReward) {
        JSONObject t = new JSONObject();
        t.put("taskId", taskId);
        t.put("id", taskId);
        t.put("name", name);
        t.put("need", need);
        t.put("__progress", progress);
        t.put("currencyReward", currencyReward);
        t.put("experienceReward", experienceReward);
        t.put("finished", 0);
        t.put("status", 0);
        t.put("type", "day");
        return t;
    }

    private static int playedToday(JSONObject st, String today) {
        JSONArray played = st.optJSONArray("playedGames");
        int n = 0;
        for (int i = 0; played != null && i < played.length(); i++) {
            JSONObject e = played.optJSONObject(i);
            if (e == null) continue;
            String day = utcDateOf(e.optLong("at"));
            if (today.equals(day)) n++;
        }
        return n;
    }

    static String utcDateOf(long ms) {
        java.text.SimpleDateFormat fmt =
                new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US);
        fmt.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
        return fmt.format(new java.util.Date(ms));
    }

    private static boolean contains(JSONArray arr, long id) {
        for (int i = 0; arr != null && i < arr.length(); i++) {
            if (arr.optLong(i) == id) return true;
        }
        return false;
    }

    /** accept → 1; claim → pays rewards (requires accepted+finished). */
    public static String taskAction(StateStore store, JSONObject user, long id, int type, boolean claim) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        JSONObject st = store.userState(user);
        JSONObject prog = st.optJSONObject("tribeTaskProg");
        String today = utcDate();
        if (prog == null || !today.equals(prog.optString("date"))) {
            prog = new JSONObject();
            prog.put("date", today);
            prog.put("accepted", new JSONArray());
            prog.put("claimed", new JSONArray());
        }
        JSONArray accepted = prog.optJSONArray("accepted");
        JSONArray claimed = prog.optJSONArray("claimed");

        if (claim) {
            if (!contains(accepted, id)) return "task not accepted";
            if (contains(claimed, id)) return "reward already claimed";
            JSONObject tasks = tasks(store, user, type);
            JSONArray list = tasks.optJSONArray("tasks");
            JSONObject hit = null;
            for (int i = 0; list != null && i < list.length(); i++) {
                JSONObject t = list.optJSONObject(i);
                if (t != null && t.optLong("taskId") == id) hit = t;
            }
            if (hit == null) return "unknown task";
            if (hit.optInt("finished") != 1) return "task not finished";
            claimed.put(id);
            user.put("tribeCurrency", tribeCurrency(user) + hit.optLong("currencyReward"));
            clan.put("experience", clan.optLong("experience") + hit.optLong("experienceReward"));
        } else {
            if (contains(accepted, id)) return "task already accepted";
            accepted.put(id);
        }
        st.put("tribeTaskProg", prog);
        store.save();
        return null;
    }

    // ------------------------------------------------------------ shop

    /** Clan decoration catalog: generated once, persisted. typeId 1 = frames, 2 = bubbles. */
    public static JSONArray shop(StateStore store) {
        JSONObject root = store.root();
        JSONArray shop = root.optJSONArray("tribeShop");
        if (shop != null && shop.length() > 0) return shop;
        shop = new JSONArray();
        int id = 9001;
        String[][] frames = {
                {"Wooden Frame", "A humble wooden avatar frame."},
                {"Bronze Frame", "Bronze avatar frame for loyal members."},
                {"Silver Frame", "Shiny silver avatar frame."},
                {"Golden Frame", "A golden frame for dedicated chiefs."},
                {"Emerald Frame", "Emerald-trimmed avatar frame."},
                {"Dragon Frame", "Legendary dragon-scale frame."},
        };
        String[][] bubbles = {
                {"Plain Bubble", "A simple chat bubble."},
                {"Sky Bubble", "Chat bubble with a sky pattern."},
                {"Lava Bubble", "Chat bubble with molten lava."},
                {"Frost Bubble", "Chat bubble with frost edges."},
                {"Neon Bubble", "A neon glowing chat bubble."},
                {"Royal Bubble", "The royal purple chat bubble."},
        };
        for (int i = 0; i < frames.length; i++) {
            shop.put(shopItem(id++, 1, frames[i][0], frames[i][1], 20 + i * 30, 1 + (i / 3)));
        }
        for (int i = 0; i < bubbles.length; i++) {
            shop.put(shopItem(id++, 2, bubbles[i][0], bubbles[i][1], 20 + i * 30, 1 + (i / 3)));
        }
        root.put("tribeShop", shop);
        store.save();
        return shop;
    }

    private static JSONObject shopItem(int id, int typeId, String name, String details,
                                       int price, int clanLevel) {
        JSONObject o = new JSONObject();
        o.put("id", id);
        o.put("typeId", typeId);
        o.put("name", name);
        o.put("details", details);
        o.put("iconUrl", "");
        o.put("resourceId", "tribe_deco_" + id);
        o.put("price", price);
        o.put("currency", 3); // tribe contribution credit
        o.put("expire", -1); // permanent
        o.put("quantity", 1);
        o.put("sex", 0);
        o.put("tag", new JSONArray());
        o.put("clanLevel", clanLevel);
        o.put("hasPurchase", 0);
        return o;
    }

    /** Buy decorations with the caller's tribe currency. Returns error or null. */
    public static String buyDecorations(StateStore store, JSONObject user, long[] ids) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return "not in a clan";
        JSONArray shop = shop(store);
        JSONArray purchases = clan.optJSONArray("purchases");
        JSONArray mine = new JSONArray();
        for (int i = 0; purchases != null && i < purchases.length(); i++) {
            JSONObject p = purchases.optJSONObject(i);
            if (p != null && p.optLong("userId") == user.optLong("userId")) {
                mine.put(p.optLong("decorationId"));
            }
        }
        long total = 0;
        for (long id : ids) {
            JSONObject item = null;
            for (int i = 0; i < shop.length(); i++) {
                JSONObject s = shop.optJSONObject(i);
                if (s != null && s.optLong("id") == id) {
                    item = s;
                    break;
                }
            }
            if (item == null) return "unknown decoration " + id;
            if (level(clan) < item.optInt("clanLevel")) return "clan level too low";
            if (contains(mine, id)) continue; // already owned
            total += item.optLong("price");
        }
        if (total > 0) {
            if (tribeCurrency(user) < total) return "not enough tribe currency";
            user.put("tribeCurrency", tribeCurrency(user) - total);
        }
        for (long id : ids) {
            if (contains(mine, id)) continue;
            JSONObject p = new JSONObject();
            p.put("userId", user.optLong("userId"));
            p.put("decorationId", id);
            p.put("at", System.currentTimeMillis());
            purchases.put(p);
        }
        store.save();
        return null;
    }

    public static boolean ownsDecoration(StateStore store, JSONObject user, long decorationId) {
        JSONObject clan = clanOf(store, user);
        if (clan == null) return false;
        JSONArray purchases = clan.optJSONArray("purchases");
        for (int i = 0; purchases != null && i < purchases.length(); i++) {
            JSONObject p = purchases.optJSONObject(i);
            if (p != null && p.optLong("userId") == user.optLong("userId")
                    && p.optLong("decorationId") == decorationId) return true;
        }
        return false;
    }

    // ------------------------------------------------------------ NPC tribes (recommendation content)

    /** Seed a handful of NPC clans once so recommendation/search/rank have content. */
    public static void ensureNpcTribes(StateStore store) {
        JSONObject clans = clans(store);
        if (clans.length() > 0) return;
        String[][] npcs = {
                {"Blocky Pioneers", "The first builders of the local world."},
                {"Night Builders", "We build while you sleep."},
                {"Pixel Wolves", "Fast, friendly, always playing."},
                {"Cloud Crafters", "Sky-high creations only."},
                {"Rookie Republic", "New players welcome!"},
                {"Arena Legends", "Battle-hardened competitors."},
                {"Sandbox Society", "Creative minds unite."},
                {"Diamond Guild", "Collectors and traders."},
        };
        String[] chiefs = {"OldWolf", "Nova", "Pixie", "CloudMaster", "RookieKing",
                "Legend", "Maker", "Glimmer"};
        for (int i = 0; i < npcs.length; i++) {
            long clanId = nextClanId(store);
            JSONObject clan = new JSONObject();
            clan.put("clanId", clanId);
            clan.put("name", npcs[i][0]);
            clan.put("details", npcs[i][1]);
            clan.put("headPic", "");
            clan.put("tags", new JSONArray());
            clan.put("experience", 200L * (npcs.length - i));
            clan.put("currency", 0L);
            clan.put("freeVerify", i % 3 == 0 ? 1 : 0);
            clan.put("chiefId", 0L);
            clan.put("createdAt", System.currentTimeMillis());
            JSONArray members = new JSONArray();
            JSONObject chief = new JSONObject();
            chief.put("userId", 0L);
            chief.put("role", 20);
            chief.put("experience", 0);
            chief.put("expireDate", "");
            chief.put("headPic", "");
            chief.put("nickName", chiefs[i]);
            chief.put("status", 0);
            chief.put("vip", 0);
            members.put(chief);
            for (int j = 0; j < 3 + (i % 4); j++) {
                JSONObject m = new JSONObject();
                m.put("userId", 0L);
                m.put("role", 0);
                m.put("experience", 0);
                m.put("expireDate", "");
                m.put("headPic", "");
                m.put("nickName", chiefs[i] + "fan" + (j + 1));
                m.put("status", 0);
                m.put("vip", 0);
                members.put(m);
            }
            clan.put("members", members);
            clan.put("bulletin", new JSONObject());
            clan.put("joinRequests", new JSONArray());
            clan.put("invitations", new JSONArray());
            clan.put("donations", new JSONArray());
            clan.put("purchases", new JSONArray());
            clans.put(String.valueOf(clanId), clan);
        }
        store.save();
    }

    public static boolean isNpc(JSONObject clan) {
        return clan.optLong("chiefId") == 0L;
    }
}
