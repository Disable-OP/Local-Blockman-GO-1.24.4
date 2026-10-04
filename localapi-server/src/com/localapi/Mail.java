package com.localapi;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Mailbox domain: per-user mails with real status transitions
 * (0=unread, 2=read, 3=delete request), attachment claiming into the
 * wallet (currency types match the rest of the local economy:
 * 1=diamonds, 2=golds) and the one-time welcome mail every new
 * account receives.
 *
 * Client semantics verified from jadx (InboxModel / InboxDetailViewModel):
 * - opening a mail without attachments marks it read via mailOperation(2, ids)
 * - claiming an attachment (mail/attachment) also moves the mail to read
 * - "delete read mails" collects status==2 rows and sends mailOperation(3, ids)
 * - the unread badge (mail/new) is driven by hasNewEmail polling
 */
final class Mail {

    /** Attachment type ids follow the local wallet currency ids. */
    static final int TYPE_DIAMONDS = 1;
    static final int TYPE_GOLDS = 2;

    private Mail() {}

    /** Attachment row for a currency grant ({icon,item,name,qty,type,itemId}). */
    static JSONObject currencyAttachment(int currencyType, long qty) {
        JSONObject a = new JSONObject();
        a.put("type", currencyType);
        a.put("itemId", String.valueOf(currencyType));
        a.put("name", currencyType == TYPE_DIAMONDS ? "Diamonds" : "Golds");
        a.put("icon", "");
        a.put("qty", qty);
        return a;
    }

    /**
     * Give every newly created account its one-time welcome mail
     * (500 golds). Guarded by a per-user flag so deleting the mail
     * never re-issues it.
     */
    static synchronized void ensureWelcomeMail(StateStore store, JSONObject user) {
        JSONObject st = store.userState(user);
        if (st.optBoolean("welcomeMail")) return;
        JSONArray att = new JSONArray();
        att.put(currencyAttachment(TYPE_GOLDS, 500));
        store.addMail(user,
                "Welcome to the local world",
                "Your account is ready. Everything here runs on the local API — "
                        + "have fun! Claim the attached golds to get started.",
                0, "", att);
        st.put("welcomeMail", true);
        store.save();
    }

    /** Serialize a stored mail into the exact MailInfo Gson shape. */
    static JSONObject toJson(JSONObject mail) {
        JSONObject m = new JSONObject();
        m.put("id", mail.optLong("id"));
        m.put("title", mail.optString("title"));
        m.put("content", mail.optString("content"));
        m.put("type", mail.optInt("type"));
        m.put("extra", mail.optString("extra"));
        m.put("sendDate", mail.optLong("sendDate"));
        m.put("status", mail.optInt("status"));
        JSONArray att = mail.optJSONArray("attachment");
        JSONArray out = new JSONArray();
        if (att != null) {
            for (int i = 0; i < att.length(); i++) {
                JSONObject a = att.optJSONObject(i);
                if (a == null) continue;
                JSONObject row = new JSONObject();
                row.put("type", a.optInt("type"));
                row.put("itemId", a.optString("itemId"));
                row.put("name", a.optString("name"));
                row.put("icon", a.optString("icon"));
                row.put("qty", a.optInt("qty"));
                out.put(row);
            }
        }
        m.put("attachment", out);
        return m;
    }

    /** Mail list, newest first. */
    static JSONArray list(StateStore store, JSONObject user) {
        JSONArray src = store.mails(user);
        JSONArray out = new JSONArray();
        for (int i = src.length() - 1; i >= 0; i--) {
            JSONObject mail = src.optJSONObject(i);
            if (mail != null) out.put(toJson(mail));
        }
        return out;
    }

    /** True when at least one mail is still unread (status 0). */
    static boolean hasNew(StateStore store, JSONObject user) {
        JSONArray src = store.mails(user);
        for (int i = 0; i < src.length(); i++) {
            JSONObject mail = src.optJSONObject(i);
            if (mail != null && mail.optInt("status") == 0) return true;
        }
        return false;
    }

    /**
     * Apply a client mail operation: status 2 = mark read,
     * status 3 = delete. Returns the updated list (client expects
     * List<MailInfo>) — newest first like mailList.
     */
    static JSONArray operate(StateStore store, JSONObject user, int status, JSONArray ids) {
        for (int i = 0; i < ids.length(); i++) {
            long id = ids.optLong(i, 0L);
            if (id <= 0) continue;
            if (status == 3) {
                store.deleteMail(user, id);
            } else {
                store.markMail(user, id, status);
            }
        }
        return list(store, user);
    }

    /**
     * Claim a mail's attachments into the wallet (once). Returns true on
     * success; false when the mail is gone or was already claimed.
     */
    static synchronized boolean claim(StateStore store, JSONObject user, long mailId) {
        JSONObject mail = store.findMail(user, mailId);
        if (mail == null) return false;
        if (mail.optBoolean("claimed")) return false;
        JSONArray att = mail.optJSONArray("attachment");
        long golds = 0, diamonds = 0;
        if (att != null) {
            for (int i = 0; i < att.length(); i++) {
                JSONObject a = att.optJSONObject(i);
                if (a == null) continue;
                int t = a.optInt("type");
                long qty = a.optLong("qty", 0L);
                if (t == TYPE_DIAMONDS) diamonds += qty;
                else if (t == TYPE_GOLDS) golds += qty;
            }
        }
        if (golds > 0) store.award(user, "golds", golds);
        if (diamonds > 0) store.award(user, "diamonds", diamonds);
        mail.put("claimed", true);
        mail.put("status", 2);
        store.save();
        L.i("mail claim: userId=" + user.optLong("userId") + " mailId=" + mailId
                + " +" + golds + " golds +" + diamonds + " diamonds");
        return true;
    }
}
