package com.localapi;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * File-backed persistent state for the local API (users, tokens, wallets).
 * Stored as JSON under <filesDir>/localapi/state.json — plain, inspectable,
 * editable. Nothing is hardcoded: every account the game creates lives here
 * and survives restarts. All methods synchronized (NanoHTTPD uses a thread
 * per connection).
 */
public final class StateStore {

    private final File file;
    private JSONObject root;

    public StateStore(File filesDir) {
        File dir = new File(filesDir, "localapi");
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
        this.file = new File(dir, "state.json");
        load();
    }

    private void load() {
        root = new JSONObject();
        try {
            if (file.exists()) {
                byte[] buf = new byte[(int) file.length()];
                FileInputStream in = new FileInputStream(file);
                int read = in.read(buf);
                in.close();
                if (read > 0) {
                    root = new JSONObject(new String(buf, StandardCharsets.UTF_8));
                    return;
                }
            }
        } catch (Throwable t) {
            L.e("state load failed, starting fresh: " + t);
            root = new JSONObject();
        }
        if (!root.has("nextUserId")) root.put("nextUserId", 10001);
        if (!root.has("users")) root.put("users", new JSONObject());
        if (!root.has("tokens")) root.put("tokens", new JSONObject());
        if (!root.has("mailSeq")) root.put("mailSeq", 1);
        save();
    }

    public synchronized void save() {
        try {
            File tmp = new File(file.getParentFile(), "state.json.tmp");
            FileOutputStream out = new FileOutputStream(tmp);
            out.write(root.toString().getBytes(StandardCharsets.UTF_8));
            out.close();
            if (!tmp.renameTo(file)) {
                // rename can fail across fs quirks — fall back to direct write
                FileOutputStream out2 = new FileOutputStream(file);
                out2.write(root.toString().getBytes(StandardCharsets.UTF_8));
                out2.close();
                //noinspection ResultOfMethodCallIgnored
                tmp.delete();
            }
        } catch (Throwable t) {
            L.e("state save failed: " + t);
        }
    }

    /** Direct (synchronized read) access to the store root — used by GameCatalog. */
    public synchronized JSONObject root() {
        return root;
    }

    private JSONObject users() {
        return root.optJSONObject("users");
    }

    private JSONObject tokens() {
        return root.optJSONObject("tokens");
    }

    public synchronized int userCount() {
        return users().length();
    }

    /** Allocate the next numeric user id. */
    private synchronized long nextUserId() {
        long id = root.optLong("nextUserId", 10001L);
        root.put("nextUserId", id + 1);
        return id;
    }

    public synchronized JSONObject findByKey(String key) {
        return users().optJSONObject(key);
    }

    /** Resolve a user by its account name (guests upgraded via
     *  set-password keep their original storage key, so the login account
     *  lives on the record, not in the key). */
    public synchronized JSONObject findByAccount(String account) {
        if (account == null || account.isEmpty()) return null;
        JSONArray keys = users().names();
        if (keys == null) return null;
        for (int i = 0; i < keys.length(); i++) {
            JSONObject u = users().optJSONObject(keys.optString(i));
            if (u != null && account.equalsIgnoreCase(u.optString("account"))) {
                return u;
            }
        }
        return null;
    }

    public synchronized JSONObject findByUserId(long userId) {
        JSONArray keys = users().names();
        if (keys == null) return null;
        for (int i = 0; i < keys.length(); i++) {
            JSONObject u = users().optJSONObject(keys.optString(i));
            if (u != null && u.optLong("userId") == userId) return u;
        }
        return null;
    }

    public synchronized JSONObject findByToken(String token) {
        if (token == null || token.isEmpty()) return null;
        long uid = tokens().optLong(token, 0L);
        return uid > 0 ? findByUserId(uid) : null;
    }

    /** Real presence: does the user hold at least one live (un-dropped) token? */
    public synchronized boolean isOnline(long userId) {
        JSONObject t = tokens();
        JSONArray names = t.names();
        for (int i = 0; names != null && i < names.length(); i++) {
            if (t.optLong(names.optString(i)) == userId) return true;
        }
        return false;
    }

    public synchronized JSONObject findOrCreateByKey(String key, boolean guest) {
        JSONObject u = users().optJSONObject(key);
        if (u != null) return u;
        u = newUser(guest);
        u.put("key", key);
        users().put(key, u);
        save();
        return u;
    }

    /** Create a brand-new account (register flow). Returns null if key already taken. */
    public synchronized JSONObject createAccount(String key, String passwordHash, String nickName) {
        if (users().optJSONObject(key) != null) return null;
        JSONObject u = newUser(false);
        u.put("key", key);
        u.put("password", passwordHash == null ? "" : passwordHash);
        u.put("hasPassword", passwordHash != null && !passwordHash.isEmpty());
        u.put("nickName", nickName == null || nickName.isEmpty() ? key : nickName);
        users().put(key, u);
        save();
        return u;
    }

    private JSONObject newUser(boolean guest) {
        JSONObject u = new JSONObject();
        long id = nextUserId();
        u.put("userId", id);
        u.put("account", "");
        u.put("nickName", guest ? ("Guest" + id) : ("Player" + id));
        u.put("sex", 0);
        u.put("picUrl", "");
        u.put("details", "");
        u.put("telephone", "");
        u.put("email", "");
        u.put("birthday", "");
        u.put("golds", 50000L);
        u.put("diamonds", 50000L);
        u.put("gDiamonds", 5000L);
        u.put("password", "");
        u.put("isFirstLogin", true);
        u.put("expireDate", "");
        u.put("vip", 0);
        u.put("hasPassword", !guest);
        u.put("platform", "android");
        u.put("starCode", "");
        return u;
    }

    /** Issue (or re-issue) an access token for a user. */
    public synchronized String issueToken(JSONObject user) {
        String token = "local-" + user.optLong("userId") + "-"
                + Long.toHexString(System.nanoTime());
        tokens().put(token, user.optLong("userId"));
        user.put("accessToken", token);
        save();
        return token;
    }

    public synchronized void dropToken(String token) {
        if (token != null) {
            tokens().remove(token);
            save();
        }
    }

    /** Resolve a user the lenient way: token first, then userid header, then ghost. */
    public synchronized JSONObject resolve(String token, String userIdHeader) {
        JSONObject u = findByToken(token);
        if (u != null) return u;
        if (userIdHeader != null) {
            try {
                u = findByUserId(Long.parseLong(userIdHeader.trim()));
                if (u != null) return u;
            } catch (NumberFormatException ignore) {
                // fall through
            }
        }
        return findOrCreateByKey("ghost", true);
    }

    // ------------------------------------------------- per-user economy state

    /** Lazy per-user state object (played games, sign-ins, rewards). */
    public synchronized JSONObject userState(JSONObject user) {
        JSONObject st = user.optJSONObject("state");
        if (st == null) {
            st = new JSONObject();
            st.put("playedGames", new JSONArray());          // [{gameId, at}]
            st.put("signIns", new JSONArray());              // ["2026-10-04", ...]
            st.put("adRewards", new JSONObject());           // {date, count}
            user.put("state", st);
        }
        return st;
    }

    /** Record that the user played a game (most-recent-first, capped). */
    public synchronized void recordPlay(JSONObject user, String gameId) {
        if (gameId == null || gameId.isEmpty()) return;
        JSONObject st = userState(user);
        JSONArray played = st.optJSONArray("playedGames");
        JSONArray next = new JSONArray();
        JSONObject entry = new JSONObject();
        entry.put("gameId", gameId);
        entry.put("at", System.currentTimeMillis());
        next.put(entry);
        if (played != null) {
            for (int i = 0; i < played.length() && next.length() < 30; i++) {
                JSONObject e = played.optJSONObject(i);
                if (e != null && !gameId.equals(e.optString("gameId"))) next.put(e);
            }
        }
        st.put("playedGames", next);
        save();
    }

    /** Most recently played games of a user (list of gameId strings, newest first). */
    public synchronized JSONArray recentGames(JSONObject user, int limit) {
        JSONArray played = userState(user).optJSONArray("playedGames");
        JSONArray out = new JSONArray();
        if (played == null) return out;
        for (int i = 0; i < played.length() && out.length() < limit; i++) {
            JSONObject e = played.optJSONObject(i);
            if (e != null) out.put(e.optString("gameId"));
        }
        return out;
    }

    /** Apply a currency delta to a user's wallet (negative delta = spend). */
    public synchronized void award(JSONObject user, String kind, long delta) {
        if (delta == 0) return;
        user.put(kind, user.optLong(kind) + delta);
        save();
    }

    /** Count of ad rewards claimed by a user on the given calendar date. */
    public synchronized int adRewardCount(JSONObject user, String date) {
        JSONObject ad = userState(user).optJSONObject("adRewards");
        return (ad != null && date.equals(ad.optString("date"))) ? ad.optInt("count") : 0;
    }

    public synchronized void countAdReward(JSONObject user, String date) {
        JSONObject st = userState(user);
        JSONObject ad = st.optJSONObject("adRewards");
        if (ad == null || !date.equals(ad.optString("date"))) {
            ad = new JSONObject();
            ad.put("date", date);
            ad.put("count", 0);
        }
        ad.put("count", ad.optInt("count") + 1);
        st.put("adRewards", ad);
        save();
    }

    /** Calendar dates on which the user already claimed the daily sign-in. */
    public synchronized JSONArray signIns(JSONObject user) {
        return userState(user).optJSONArray("signIns");
    }

    // ------------------------------------------------ mini-game dispatch tokens

    /**
     * Issue a mini-game dispatch token (the value the client sends back as
     * x-shahe-token when it POSTs /v1/dispatch on the dispUrl host). Kept in
     * root.miniTokens (latest 40) so dispatch can be validated for real.
     */
    public synchronized JSONObject issueMiniToken(long userId, String gameType,
                                                  String mapName, int region) {
        JSONObject mt = root.optJSONObject("miniTokens");
        if (mt == null) {
            mt = new JSONObject();
            root.put("miniTokens", mt);
        }
        JSONObject t = new JSONObject();
        t.put("userId", userId);
        t.put("gameType", gameType == null ? "" : gameType);
        t.put("mapName", mapName == null ? "" : mapName);
        t.put("region", region);
        t.put("requestId", Long.toHexString(System.nanoTime()));
        t.put("signature", Long.toHexString(Double.doubleToLongBits(Math.random())));
        t.put("timestamp", System.currentTimeMillis());
        String key = "mg-" + userId + "-" + Long.toHexString(System.nanoTime());
        mt.put(key, t);
        // prune to the newest 40 tokens
        JSONArray names = mt.names();
        while (names != null && names.length() > 40) {
            long oldest = Long.MAX_VALUE;
            String oldestKey = null;
            for (int i = 0; i < names.length(); i++) {
                String k = names.optString(i);
                if (k.equals(key)) continue; // never prune the token just issued
                long ts = mt.optJSONObject(k) == null ? 0
                        : mt.optJSONObject(k).optLong("timestamp");
                if (ts < oldest) {
                    oldest = ts;
                    oldestKey = k;
                }
            }
            if (oldestKey == null) break;
            mt.remove(oldestKey);
            names = mt.names();
        }
        save();
        t.put("token", key);
        return t;
    }

    /** Look up a previously issued mini-game dispatch token. */
    public synchronized JSONObject findMiniToken(String token) {
        if (token == null || token.isEmpty()) return null;
        JSONObject mt = root.optJSONObject("miniTokens");
        return mt == null ? null : mt.optJSONObject(token);
    }

    // ------------------------------------------------------------ file storage

    /**
     * Store an uploaded file under <filesDir>/localapi/files/<id> with its
     * metadata in root.files. Returns the file id (the URL the handler hands
     * back to the client is http://127.0.0.1:18080/files/<id>).
     */
    public synchronized String storeFile(byte[] data, String fileName, String fileType,
                                         long uploaderId) {
        if (data == null || data.length == 0) return null;
        if (data.length > 4 * 1024 * 1024) return null; // 4 MB cap (avatars/banners)
        JSONObject files = root.optJSONObject("files");
        if (files == null) {
            files = new JSONObject();
            root.put("files", files);
        }
        String id = "f" + Long.toHexString(System.nanoTime())
                + Long.toHexString(Double.doubleToLongBits(Math.random()));
        File dir = new File(file.getParentFile(), "files");
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
        try {
            FileOutputStream out = new FileOutputStream(new File(dir, id));
            out.write(data);
            out.close();
        } catch (Throwable t) {
            L.e("file store failed: " + t);
            return null;
        }
        JSONObject meta = new JSONObject();
        meta.put("fileName", fileName == null ? "" : fileName);
        meta.put("fileType", fileType == null ? "" : fileType);
        meta.put("uploaderId", uploaderId);
        meta.put("size", data.length);
        meta.put("createdAt", System.currentTimeMillis());
        files.put(id, meta);
        save();
        return id;
    }

    public synchronized JSONObject fileMeta(String id) {
        JSONObject files = root.optJSONObject("files");
        return files == null ? null : files.optJSONObject(id);
    }

    public synchronized byte[] readFile(String id) {
        if (id == null || id.isEmpty() || id.contains("/")) return null;
        try {
            File f = new File(new File(file.getParentFile(), "files"), id);
            if (!f.exists()) return null;
            byte[] buf = new byte[(int) f.length()];
            FileInputStream in = new FileInputStream(f);
            int off = 0;
            while (off < buf.length) {
                int r = in.read(buf, off, buf.length - off);
                if (r < 0) break;
                off += r;
            }
            in.close();
            return buf;
        } catch (Throwable t) {
            L.e("file read failed: " + t);
            return null;
        }
    }

    public synchronized boolean hasSignedIn(JSONObject user, String date) {
        JSONArray dates = signIns(user);
        if (dates != null) {
            for (int i = 0; i < dates.length(); i++) {
                if (date.equals(dates.optString(i))) return true;
            }
        }
        return false;
    }

    public synchronized void markSignedIn(JSONObject user, String date) {
        if (hasSignedIn(user, date)) return;
        JSONArray dates = signIns(user);
        if (dates == null) {
            dates = new JSONArray();
            userState(user).put("signIns", dates);
        }
        dates.put(date);
        save();
    }

    // --------------------------------------------------------- mailbox state

    /** All mails of a user (newest first is applied by the caller/domain). */
    public synchronized JSONArray mails(JSONObject user) {
        JSONObject st = userState(user);
        JSONArray m = st.optJSONArray("mails");
        if (m == null) {
            m = new JSONArray();
            st.put("mails", m);
        }
        return m;
    }

    /** Global mail id sequence (unique across all users, never reused). */
    public synchronized long nextMailId() {
        long id = root.optLong("mailSeq", 1L);
        root.put("mailSeq", id + 1);
        return id;
    }

    /** Append a mail: {id,title,content,type,extra,sendDate,status,attachment}. */
    public synchronized JSONObject addMail(JSONObject user, String title, String content,
                                           int type, String extra, JSONArray attachment) {
        JSONObject mail = new JSONObject();
        mail.put("id", nextMailId());
        mail.put("title", title == null ? "" : title);
        mail.put("content", content == null ? "" : content);
        mail.put("type", type);
        mail.put("extra", extra == null ? "" : extra);
        mail.put("sendDate", System.currentTimeMillis());
        mail.put("status", 0); // 0=unread, 2=read, 3=deleted
        mail.put("attachment", attachment == null ? new JSONArray() : attachment);
        mails(user).put(mail);
        save();
        return mail;
    }

    /** Find a mail by id (null when absent or already deleted). */
    public synchronized JSONObject findMail(JSONObject user, long mailId) {
        JSONArray m = mails(user);
        for (int i = 0; i < m.length(); i++) {
            JSONObject mail = m.optJSONObject(i);
            if (mail != null && mail.optLong("id") == mailId) return mail;
        }
        return null;
    }

    /** Set mail status (2=read). Returns false when the mail is gone. */
    public synchronized boolean markMail(JSONObject user, long mailId, int status) {
        JSONObject mail = findMail(user, mailId);
        if (mail == null) return false;
        mail.put("status", status);
        save();
        return true;
    }

    /** Hard-delete a mail (client "delete" operation, status 3). */
    public synchronized boolean deleteMail(JSONObject user, long mailId) {
        JSONArray m = mails(user);
        for (int i = 0; i < m.length(); i++) {
            JSONObject mail = m.optJSONObject(i);
            if (mail != null && mail.optLong("id") == mailId) {
                m.remove(i);
                save();
                return true;
            }
        }
        return false;
    }

    /** Record an engine-version report (telemetry observability, last 20 kept). */
    public synchronized void recordEngineReport(String engineVersion, int newEngineVersion,
                                                String country) {
        JSONArray reports = root.optJSONArray("engineReports");
        if (reports == null) {
            reports = new JSONArray();
            root.put("engineReports", reports);
        }
        JSONObject r = new JSONObject();
        r.put("engineVersion", engineVersion == null ? "" : engineVersion);
        r.put("newEngineVersion", newEngineVersion);
        r.put("country", country == null ? "" : country);
        r.put("at", System.currentTimeMillis());
        JSONArray next = new JSONArray();
        next.put(r);
        for (int i = 0; i < reports.length() && next.length() < 20; i++) next.put(reports.optJSONObject(i));
        root.put("engineReports", next);
        save();
    }

}
