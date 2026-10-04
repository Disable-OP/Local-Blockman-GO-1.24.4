package com.localapi;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Phase 4c: group chat management — real persistent state on top of StateStore.
 *
 * (The chat MESSAGE transport is RongCloud IM; these endpoints manage the
 * group entities themselves: create/config/join/invite/kick/ban/transfer.)
 *
 * root.groupChats : { "<groupId>": group }
 * root.nextGroupId: long counter
 * group = { groupId, groupName, groupNotice, groupPic, noticePic[],
 *           inviteStatus (0 = owner approval, 1 = free join),
 *           officialGroup, ownerId (long), muteAll, createdAt,
 *           members: [{userId, identity (2 owner / 1 manager / 0 member),
 *                      banUntil}],
 *           joinRequests: [{requestId, userId, msg, at, status, type}]
 *             type 1 = join request, type 2 = invitation;
 *             status 0 pending / 2 accepted / 3 rejected }
 *
 * Group creation is free for the local world (CreateGroupPrice price=0 —
 * the client treats price==0 as the free tier).
 */
final class GroupChat {

    private GroupChat() {}

    public static final int DAILY_INVITE_LIMIT = 20;

    // ------------------------------------------------------------ store

    private static JSONObject groups(StateStore store) {
        JSONObject root = store.root();
        JSONObject g = root.optJSONObject("groupChats");
        if (g == null) {
            g = new JSONObject();
            root.put("groupChats", g);
        }
        return g;
    }

    private static long nextGroupId(StateStore store) {
        JSONObject root = store.root();
        long id = root.optLong("nextGroupId", 30001L);
        root.put("nextGroupId", id + 1);
        return id;
    }

    private static long nextRequestId(StateStore store) {
        JSONObject root = store.root();
        long id = root.optLong("nextGroupRequestId", 1L);
        root.put("nextGroupRequestId", id + 1);
        return id;
    }

    public static JSONObject find(StateStore store, long groupId) {
        if (groupId <= 0) return null;
        return groups(store).optJSONObject(String.valueOf(groupId));
    }

    public static JSONObject memberOf(JSONObject group, long userId) {
        JSONArray m = group.optJSONArray("members");
        for (int i = 0; m != null && i < m.length(); i++) {
            JSONObject e = m.optJSONObject(i);
            if (e != null && e.optLong("userId") == userId) return e;
        }
        return null;
    }

    public static int identityOf(JSONObject group, long userId) {
        JSONObject m = memberOf(group, userId);
        return m == null ? -1 : m.optInt("identity");
    }

    public static boolean canManage(JSONObject group, long userId) {
        int id = identityOf(group, userId);
        return id == 2 || id == 1;
    }

    // ------------------------------------------------------------ lifecycle

    /** POST /msg/api/v2/msg/group/chat — create with initial members. */
    public static JSONObject create(StateStore store, JSONObject user, JSONArray memberIds,
                                    String name) {
        long uid = user.optLong("userId");
        long gid = nextGroupId(store);
        JSONObject g = new JSONObject();
        g.put("groupId", gid);
        g.put("groupName", name == null || name.isEmpty() ? ("Group" + gid) : name);
        g.put("groupNotice", "");
        g.put("groupPic", "");
        g.put("noticePic", new JSONArray());
        g.put("inviteStatus", 0);
        g.put("officialGroup", 0);
        g.put("ownerId", uid);
        g.put("muteAll", 0);
        g.put("createdAt", System.currentTimeMillis());
        JSONArray members = new JSONArray();
        members.put(memberEntry(user, 2));
        g.put("members", members);
        g.put("joinRequests", new JSONArray());
        groups(store).put(String.valueOf(gid), g);
        user.put("groupId", gid); // most-recent group convenience (harmless)
        addMembers(store, g, memberIds);
        store.save();
        return g;
    }

    private static JSONObject memberEntry(JSONObject user, int identity) {
        JSONObject m = new JSONObject();
        m.put("userId", user.optLong("userId"));
        m.put("userName", user.optString("nickName"));
        m.put("pic", user.optString("picUrl").isEmpty() ? user.optString("headPic")
                : user.optString("picUrl"));
        m.put("vip", user.optInt("vip"));
        m.put("identity", identity);
        m.put("banUntil", 0L);
        return m;
    }

    /** Add users to a group (silently skips unknown ids and existing members). */
    private static void addMembers(StateStore store, JSONObject group, JSONArray memberIds) {
        JSONArray members = group.optJSONArray("members");
        if (members == null) {
            members = new JSONArray();
            group.put("members", members);
        }
        for (int i = 0; memberIds != null && i < memberIds.length(); i++) {
            long uid = memberIds.optLong(i);
            if (uid <= 0 || memberOf(group, uid) != null) continue;
            JSONObject p = Friend.person(store, uid);
            if (p == null) continue;
            JSONObject u = store.findByUserId(uid);
            members.put(memberEntry(u != null ? u : p, 0));
        }
    }

    /** PUT quit — owner transfer to the first remaining member or dissolve. */
    public static String quit(StateStore store, JSONObject user, long groupId) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        long uid = user.optLong("userId");
        JSONObject me = memberOf(g, uid);
        if (me == null) return "not a member";
        JSONArray members = g.optJSONArray("members");
        JSONArray next = new JSONArray();
        for (int i = 0; members != null && i < members.length(); i++) {
            JSONObject m = members.optJSONObject(i);
            if (m != null && m.optLong("userId") != uid) next.put(m);
        }
        if (identityOf(g, uid) == 2) {
            if (next.length() == 0) {
                groups(store).remove(String.valueOf(groupId));
                store.save();
                return null;
            }
            JSONObject heir = next.optJSONObject(0);
            heir.put("identity", 2);
            g.put("ownerId", heir.optLong("userId"));
        }
        g.put("members", next);
        store.save();
        return null;
    }

    // ------------------------------------------------------------ membership changes

    public static String kick(StateStore store, JSONObject user, long groupId, JSONArray memberIds) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        if (!canManage(g, user.optLong("userId"))) return "no permission";
        JSONArray members = g.optJSONArray("members");
        JSONArray next = new JSONArray();
        for (int i = 0; members != null && i < members.length(); i++) {
            JSONObject m = members.optJSONObject(i);
            if (m == null) continue;
            boolean kick = false;
            for (int j = 0; memberIds != null && j < memberIds.length(); j++) {
                if (memberIds.optLong(j) == m.optLong("userId")) kick = true;
            }
            if (!kick || m.optInt("identity") == 2) next.put(m);
        }
        g.put("members", next);
        store.save();
        return null;
    }

    public static String setManagers(StateStore store, JSONObject user, long groupId,
                                     JSONArray memberIds, int operationType) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        if (identityOf(g, user.optLong("userId")) != 2) return "only the owner can set managers";
        JSONArray members = g.optJSONArray("members");
        for (int i = 0; members != null && i < members.length(); i++) {
            JSONObject m = members.optJSONObject(i);
            if (m == null || m.optInt("identity") == 2) continue;
            for (int j = 0; memberIds != null && j < memberIds.length(); j++) {
                if (memberIds.optLong(j) == m.optLong("userId")) {
                    m.put("identity", operationType != 0 ? 1 : 0);
                }
            }
        }
        store.save();
        return null;
    }

    public static String transfer(StateStore store, JSONObject user, long groupId, long newOwner) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        if (identityOf(g, user.optLong("userId")) != 2) return "only the owner can transfer";
        JSONObject target = memberOf(g, newOwner);
        if (target == null) return "target is not a member";
        JSONObject me = memberOf(g, user.optLong("userId"));
        me.put("identity", 0);
        target.put("identity", 2);
        g.put("ownerId", newOwner);
        store.save();
        return null;
    }

    // ------------------------------------------------------------ bans

    public static String banMember(StateStore store, JSONObject user, long groupId,
                                   long memberId, int minutes) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        if (!canManage(g, user.optLong("userId"))) return "no permission";
        JSONObject m = memberOf(g, memberId);
        if (m == null) return "not a member";
        if (m.optInt("identity") == 2) return "cannot ban the owner";
        m.put("banUntil", System.currentTimeMillis() + Math.max(1, minutes) * 60_000L);
        store.save();
        return null;
    }

    public static String unbanMember(StateStore store, JSONObject user, long groupId, long memberId) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        if (!canManage(g, user.optLong("userId"))) return "no permission";
        JSONObject m = memberOf(g, memberId);
        if (m == null) return "not a member";
        m.put("banUntil", 0L);
        store.save();
        return null;
    }

    public static String toggleMuteAll(StateStore store, JSONObject user, long groupId) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        if (!canManage(g, user.optLong("userId"))) return "no permission";
        g.put("muteAll", g.optInt("muteAll") == 0 ? 1 : 0);
        store.save();
        return null;
    }

    // ------------------------------------------------------------ joining / invites

    public static String apply(StateStore store, JSONObject user, long groupId, String msg) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        long uid = user.optLong("userId");
        if (memberOf(g, uid) != null) return "already a member";
        if (g.optInt("inviteStatus") == 1) {
            JSONArray members = g.optJSONArray("members");
            members.put(memberEntry(user, 0));
            store.save();
            return null;
        }
        JSONArray reqs = g.optJSONArray("joinRequests");
        for (int i = 0; reqs != null && i < reqs.length(); i++) {
            JSONObject r = reqs.optJSONObject(i);
            if (r != null && r.optLong("userId") == uid && r.optInt("status") == 0) {
                return "request already pending";
            }
        }
        JSONObject r = new JSONObject();
        r.put("requestId", nextRequestId(store));
        r.put("userId", uid);
        r.put("msg", msg == null ? "" : msg);
        r.put("at", System.currentTimeMillis());
        r.put("status", 0);
        r.put("type", 1);
        reqs.put(r);
        store.save();
        return null;
    }

    /** Owner/manager invites users (direct add for citizens, invitation for real users). */
    public static String invite(StateStore store, JSONObject user, long groupId, JSONArray memberIds) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        if (!canManage(g, user.optLong("userId"))) return "no permission";
        JSONArray reqs = g.optJSONArray("joinRequests");
        for (int i = 0; memberIds != null && i < memberIds.length(); i++) {
            long target = memberIds.optLong(i);
            if (target <= 0 || memberOf(g, target) != null) continue;
            JSONObject u = store.findByUserId(target);
            if (u == null) {
                // citizen: direct add (nobody to notify)
                addMembers(store, g, new JSONArray().put(target));
                continue;
            }
            JSONObject r = new JSONObject();
            r.put("requestId", nextRequestId(store));
            r.put("userId", user.optLong("userId")); // the inviter
            r.put("inviteeId", target);
            r.put("msg", "");
            r.put("at", System.currentTimeMillis());
            r.put("status", 0);
            r.put("type", 2);
            reqs.put(r);
        }
        store.save();
        return null;
    }

    /** Accept (operate) a request: type 1 join request / type 2 invitation. */
    public static String acceptRequest(StateStore store, JSONObject operator, long groupId,
                                       long requestId, long userId) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        JSONArray reqs = g.optJSONArray("joinRequests");
        JSONObject hit = null;
        for (int i = 0; reqs != null && i < reqs.length(); i++) {
            JSONObject r = reqs.optJSONObject(i);
            if (r != null && r.optLong("requestId") == requestId && r.optInt("status") == 0) hit = r;
        }
        if (hit == null) return "no pending request";
        if (hit.optInt("type") == 2) {
            // the invitee accepts their own invitation
            if (hit.optLong("inviteeId") != operator.optLong("userId")) return "not your invitation";
        } else {
            if (!canManage(g, operator.optLong("userId"))) return "no permission";
        }
        if (hit.optInt("type") == 2 && memberOf(g, operator.optLong("userId")) != null) {
            return "already a member";
        }
        JSONObject joiner = store.findByUserId(
                hit.optInt("type") == 2 ? operator.optLong("userId") : userId);
        if (joiner == null) return "user not found";
        hit.put("status", 2);
        JSONArray members = g.optJSONArray("members");
        members.put(memberEntry(joiner, 0));
        store.save();
        return null;
    }

    public static String rejectRequest(StateStore store, JSONObject operator, long groupId,
                                       long requestId) {
        JSONObject g = find(store, groupId);
        if (g == null) return "group not found";
        JSONArray reqs = g.optJSONArray("joinRequests");
        boolean hit = false;
        for (int i = 0; reqs != null && i < reqs.length(); i++) {
            JSONObject r = reqs.optJSONObject(i);
            if (r != null && r.optLong("requestId") == requestId && r.optInt("status") == 0) {
                r.put("status", 3);
                hit = true;
            }
        }
        if (!hit) return "no pending request";
        store.save();
        return null;
    }

    // ------------------------------------------------------------ reads

    /** Groups the user belongs to. */
    public static JSONArray mine(StateStore store, long userId) {
        JSONObject all = groups(store);
        JSONArray ids = all.names();
        JSONArray out = new JSONArray();
        for (int i = 0; ids != null && i < ids.length(); i++) {
            JSONObject g = all.optJSONObject(ids.optString(i));
            if (g != null && memberOf(g, userId) != null) out.put(g);
        }
        return out;
    }

    /** Requests for the caller: join requests to groups they manage (type 1)
     *  + invitations addressed to them (type 2). */
    public static JSONArray requestFeed(StateStore store, long userId) {
        JSONObject all = groups(store);
        JSONArray ids = all.names();
        JSONArray out = new JSONArray();
        for (int i = 0; ids != null && i < ids.length(); i++) {
            JSONObject g = all.optJSONObject(ids.optString(i));
            if (g == null) continue;
            boolean manager = canManage(g, userId);
            JSONArray reqs = g.optJSONArray("joinRequests");
            for (int j = 0; reqs != null && j < reqs.length(); j++) {
                JSONObject r = reqs.optJSONObject(j);
                if (r == null) continue;
                boolean forMe = r.optInt("type") == 2 && r.optLong("inviteeId") == userId;
                if (!manager && !forMe) continue;
                if (r.optInt("type") == 1 && !manager) continue;
                JSONObject o = new JSONObject();
                o.put("requestId", r.optLong("requestId"));
                o.put("groupId", g.optLong("groupId"));
                o.put("groupName", g.optString("groupName"));
                o.put("userId", r.optLong("userId"));
                o.put("msg", r.optString("msg"));
                o.put("status", r.optInt("status"));
                o.put("type", r.optInt("type"));
                JSONObject p = Friend.person(store, r.optLong("userId"));
                o.put("nickName", p == null ? "Player" : p.optString("nickName"));
                o.put("picUrl", p == null ? "" : (p.optString("headPic").isEmpty()
                        ? p.optString("picUrl") : p.optString("headPic")));
                o.put("vip", p == null ? 0 : p.optInt("vip"));
                out.put(o);
            }
        }
        return out;
    }

    /** GroupInfo JSON in the exact shape of the client model. */
    public static JSONObject groupJson(JSONObject g) {
        JSONObject out = new JSONObject();
        out.put("groupId", g.optLong("groupId"));
        out.put("groupName", g.optString("groupName"));
        out.put("groupNotice", g.optString("groupNotice"));
        out.put("groupPic", g.optString("groupPic"));
        out.put("noticePic", g.optJSONArray("noticePic") == null ? new JSONArray()
                : g.optJSONArray("noticePic"));
        out.put("inviteStatus", g.optInt("inviteStatus"));
        out.put("officialGroup", g.optInt("officialGroup"));
        out.put("ownerId", String.valueOf(g.optLong("ownerId")));
        out.put("releaseTime", "");
        out.put("muteAll", g.optInt("muteAll"));
        JSONArray members = g.optJSONArray("members");
        JSONArray mj = new JSONArray();
        long now = System.currentTimeMillis();
        for (int i = 0; members != null && i < members.length(); i++) {
            JSONObject m = members.optJSONObject(i);
            if (m == null) continue;
            JSONObject o = new JSONObject();
            o.put("userId", m.optLong("userId"));
            o.put("userName", m.optString("userName"));
            o.put("pic", m.optString("pic"));
            o.put("vip", m.optInt("vip"));
            o.put("identity", m.optInt("identity"));
            o.put("banStatus", m.optLong("banUntil") > now ? 1 : 0);
            mj.put(o);
        }
        out.put("groupMembers", mj);
        out.put("forbiddenWordsStatus", g.optInt("muteAll"));
        return out;
    }
}
