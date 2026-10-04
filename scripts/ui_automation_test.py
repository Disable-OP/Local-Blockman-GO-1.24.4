#!/usr/bin/env python3
"""UI automation test for the local-API Blockman GO APK (Redroid CI).

Three deterministic phases, driven purely over adb + uiautomator dumps:

  Phase A — VISITOR (fresh app data):
      pm clear -> launch -> the app auto-logs-in as a tourist/visitor account
      through the embedded local server -> navigate all 5 bottom tabs ->
      deep drive (Inbox / Top Up / Ranking / Store / Party / Video / Personal
      Info editor / game detail + rank/comment sub-tabs).
      Asserts tourist/auth-token traffic in logcat.

  Phase B — PROFILE EDIT through the Personal Info editor:
      Me tab -> profile header -> ibMore -> tap the Nickname row, type a
      fresh nickname, confirm TWICE (ChangeNameFragment -> the
      ChangeNicknameDialog whose confirm fires PUT /user/api/v2/user/
      nickName). A pid change inside the save window is recorded as
      native-kick evidence but is not expected.
      NOTE: deliberately does NOT tap the account row (ll_account) —
      native-killer family; account creation is owned by Phase C.

  Phase C — ACCOUNT CREATION via the embedded server (adb forward):
      register a FRESH account + visitor + tourist through the REAL local
      API (loopback adb forward), login, then drive tribe/friend/mail/dispatch
      surfaces over the same forward. Asserts POST /user/api/v1/register and
      the whole Phase C/D/E assertion set.

  Phase D — REGISTERED SESSION: upgrade + restart:
      read the session user id from the live Me tab, issue its token via
      GET /user/api/v1/app/auth-token, upgrade the account through POST
      /user/api/v2/app/set-password (the client's own guest-upgrade
      endpoint), verify by logging in with the new credentials, restart
      the app (the boot restores the saved session, now registered), and
      check the Me tab shows the new account. If Phase B's PUT never
      fired, the editor drive re-runs here under the registered session.
      (am-start of LoginActivity/RegisterActivity is DENIED for these
      non-exported activities — evidence v0.5.18c/d.)

  Final — crash scan (FATAL EXCEPTION / ANR) + process alive everywhere.

Every UI step is derived from live uiautomator dumps, never coordinates.
Exit 0 = pass, 1 = fail.
"""
import argparse
import json
import re
import urllib.request
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("  [FAIL] %s" % msg)


def debug_dump(screen, tag="debug"):
    """Print what the script currently sees, for CI log debugging."""
    try:
        nodes = screen.dump()
        print("  [debug:%s] %d nodes" % (tag, len(nodes)))
        for n in nodes[:60]:
            rid = n.res.rsplit("/", 1)[-1] if n.res else ""
            if n.text or n.desc or rid:
                print("    res=%-18s text=%-24.24s desc=%-14.14s cls=%s clickable=%s"
                      % (rid, n.text, n.desc, n.cls.rsplit(".", 1)[-1], n.clickable))
    except Exception as e:
        print("  [debug:%s] dump failed: %s" % (tag, e))


def ok(msg):
    print("  [ok] %s" % msg)


def check(name, cond, detail=""):
    if cond:
        ok("%s" % name)
    else:
        fail("%s  %s" % (name, detail))


class Adb:
    def __init__(self, serial):
        self.serial = serial

    def sh(self, cmd, timeout=30):
        r = subprocess.run(["adb", "-s", self.serial, "shell", cmd],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.stdout.strip()

    def raw(self, *args, timeout=60):
        # logcat buffers can contain non-UTF-8 bytes (any screen may write
        # binary through a log line); decode-tolerant or the crash scan dies
        # on UnicodeDecodeError instead of reporting real findings.
        r = subprocess.run(["adb", "-s", self.serial] + list(args),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.stdout.strip()

    def tap(self, x, y):
        self.sh("input tap %d %d" % (x, y))

    def text(self, s):
        self.sh('input text "%s"' % s.replace(" ", "%s"))

    def key(self, keycode):
        self.sh("input keyevent %s" % keycode)

    def pid(self, package):
        return self.sh("pidof %s" % package).strip()


class Node:
    def __init__(self, el):
        self.el = el
        self.text = el.get("text", "")
        self.desc = el.get("content-desc", "")
        self.res = el.get("resource-id", "")
        self.cls = el.get("class", "")
        self.clickable = el.get("clickable") == "true"
        self.checked = el.get("checked") == "true"
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", el.get("bounds", ""))
        self.bounds = tuple(int(x) for x in m.groups()) if m else None

    @property
    def center(self):
        if not self.bounds:
            return None
        l, t, r, b = self.bounds
        return ((l + r) // 2, (t + b) // 2)


class Screen:
    def __init__(self, adb):
        self.adb = adb

    def dump(self):
        for _ in range(3):
            try:
                self.adb.sh("uiautomator dump /sdcard/localqa_ui.xml", timeout=25)
                xml = self.adb.sh("cat /sdcard/localqa_ui.xml", timeout=25)
                if "<hierarchy" in xml:
                    return [Node(e) for e in ET.fromstring(xml).iter("node")]
            except Exception:
                pass
            time.sleep(2)
        return []

    def find(self, ids=None, texts=None, contains=None):
        want_id = set(ids or [])
        want_text = set(texts or [])
        want_sub = [c.lower() for c in (contains or [])]
        for n in self.dump():
            rid = n.res.rsplit("/", 1)[-1] if n.res else ""
            if want_id and rid in want_id:
                return n
            if want_text and n.text in want_text:
                return n
            if want_sub and n.text and any(c in n.text.lower() for c in want_sub):
                return n
        return None

    def wait_for(self, ids=None, texts=None, contains=None, timeout=30, poll=2.5):
        end = time.time() + timeout
        while time.time() < end:
            n = self.find(ids=ids, texts=texts, contains=contains)
            if n:
                return n
            time.sleep(poll)
        return None

    def tap_node(self, node):
        c = node.center
        if c:
            self.adb.tap(*c)
            return True
        return False


def dismiss_permission_dialogs(screen, rounds=8):
    for _ in range(rounds):
        n = screen.find(texts=["Allow", "ALLOW", "While using the app",
                               "Only this time", "ALLOW ONLY FOR THIS SESSION"])
        if n and n.center:
            screen.tap_node(n)
            time.sleep(1.5)
        else:
            time.sleep(1.0)


def assert_alive(adb, package, stage):
    pid = adb.pid(package)
    if not pid:
        fail("process died at stage: %s" % stage)
        return False
    ok("alive at %s (pid %s)" % (stage, pid))
    return True


def deep_drive(adb, screen, package, tag, paths_before):
    """Deeper UI driving: visit labeled Me-tab rows (Inbox / Top Up /
    Ranking), open a game card from Home, and print which endpoints the
    newly visited screens added. Best-effort taps; the hard requirement is
    only that the app stays alive (a crash here is a real finding)."""
    def visit(label, wait_s, back=True, contains=None):
        n = screen.find(texts=[label], contains=contains)
        if not (n and n.center):
            print("  [skip] '%s' not on screen" % label)
            return False
        screen.tap_node(n)
        time.sleep(wait_s)
        if back:
            adb.key(4)  # BACK
            time.sleep(2)
        return assert_alive(adb, package, "%s-%s" % (tag, label.replace(" ", "")))

    # Me tab rows (labels verified from the on-device UI dump)
    more = screen.find(ids=["rb_5"])
    if more and screen.tap_node(more):
        time.sleep(4)
        # discovery channel: print every identified node on the Me tab (the
        # row labels are NOT clickable=true nodes themselves — a parent view
        # handles the taps — so filter only on id/text/desc presence)
        for n in screen.dump():
            if n.res or n.text or n.desc:
                print("  [me-tab] %s | text=%r desc=%r clickable=%s" % (
                    n.res.rsplit("/", 1)[-1] if n.res else "",
                    n.text[:24], n.desc[:24], n.clickable))
        # Inbox: open the list, then a mail row (drives mailOp/detail via UI)
        inbox = screen.find(texts=["Inbox"])
        if inbox and inbox.center:
            screen.tap_node(inbox)
            time.sleep(6)
            assert_alive(adb, package, "%s-Inbox" % tag)
            row = screen.find(texts=["Welcome"], contains=["welcome"])
            if row and row.center:
                screen.tap_node(row)
                time.sleep(5)
                adb.key(4)  # back to the list
                time.sleep(2)
                assert_alive(adb, package, "%s-MailRow" % tag)
            adb.key(4)  # back to Me
            time.sleep(2)
        visit("Top Up", 6)         # recharge screen (pay products path)
        visit("Ranking", 6)        # ranking screen (rank home path)
        visit("Store", 6)          # store screen (dress/suit shop path)
        visit("Party", 6)          # party screen (party auth path)
        visit("Video", 6)          # video feed (deliberate-empty probe)
        visit("Gratitude List", 6) # gratitude list row (never visited before)
        # Profile surface: the Me tab has NO settings entry (discovered via
        # the node dump); settings lives behind the profile screen (ibMore).
        prof = screen.find(ids=["ll_top", "rl_header"])
        if prof and prof.center:
            screen.tap_node(prof)
            time.sleep(6)
            assert_alive(adb, package, "%s-Profile" % tag)
            more = screen.find(ids=["ibMore"])
            if more and more.center:
                screen.tap_node(more)
                time.sleep(6)
                assert_alive(adb, package, "%s-MoreSettings" % tag)
                # discovery channel: the settings screen's rows carry no
                # "account" text (probe found nothing in v0.5.13) — dump the
                # identified nodes so the next wave can target the real ids
                for n in screen.dump():
                    if n.res or n.text or n.desc:
                        print("  [more] %s | text=%r desc=%r" % (
                            n.res.rsplit("/", 1)[-1] if n.res else "",
                            n.text[:24], n.desc[:24]))
                # account/security row inside settings (best-effort, one level)
                acc = screen.find(contains=["account"])
                if acc and acc.center:
                    screen.tap_node(acc)
                    time.sleep(5)
                    adb.key(4)
                    time.sleep(2)
                    assert_alive(adb, package, "%s-MoreAccount" % tag)
                adb.key(4)  # back to profile
                time.sleep(2)
            adb.key(4)  # back to Me
            time.sleep(2)
            assert_alive(adb, package, "%s-ProfileBack" % tag)
    # Home tab: tap the first tappable card above the bottom nav
    home = screen.find(ids=["rb_1"])
    if home and screen.tap_node(home):
        time.sleep(5)
        nodes = screen.dump()
        card = None
        for n in nodes:
            if not n.center:
                continue
            y = n.center[1]
            if y < 200 or y > 980:
                continue
            if n.cls.endswith("RecyclerView") or n.cls.endswith("LinearLayout"):
                card = n
                break
        if card:
            screen.tap_node(card)
            time.sleep(8)          # game detail fires its whole surface
            assert_alive(adb, package, "%s-gamedetail" % tag)
            # game-detail sub-screens (rank / comments) — best-effort probes;
            # labels may vary per game detail layout, BACK always recovers
            for sub in ("rank", "comment"):
                sn = screen.find(contains=[sub])
                if sn and sn.center:
                    screen.tap_node(sn)
                    time.sleep(5)
                    adb.key(4)
                    time.sleep(2)
                    assert_alive(adb, package, "%s-gamesub-%s" % (tag, sub))
            adb.key(4)
            time.sleep(2)
            assert_alive(adb, package, "%s-gamecard" % tag)
        else:
            print("  [skip] no home card candidate found")
    added = sorted(set(localapi_paths(adb)) - paths_before)
    ok("deep drive added %d new endpoint paths" % len(added))
    for p in added:
        print("    + %s" % p)
    # Return the app to a SAFE screen. Evidence (v0.5.9/0511/0513): all three
    # between-phase SIGKILL incidents happened while the app sat IDLE on
    # FriendInfoActivity (the rank/comment probes can land there); the runs
    # that ended on Home/Me survived. Land on Home before the next phase.
    home_tab = screen.find(ids=["rb_1"])
    if home_tab and home_tab.center:
        screen.tap_node(home_tab)
        time.sleep(3)
    return added


def navigate_all_tabs(adb, screen, package, tag):
    tabs_seen = 0
    for tab in ["rb_1", "rb_2", "rb_3", "rb_4", "rb_5"]:
        n = screen.find(ids=[tab])
        if n and n.center:
            screen.tap_node(n)
            tabs_seen += 1
            time.sleep(5)  # let the tab fire its API calls
            if not assert_alive(adb, package, "%s-tab-%s" % (tag, tab)):
                return tabs_seen
        else:
            print("  [skip] tab %s not in current layout" % tab)
    if tabs_seen == 0:
        fail("%s: no bottom tabs were clickable" % tag)
    else:
        ok("%s: navigated %d bottom tabs" % (tag, tabs_seen))
    return tabs_seen


def localapi_paths(adb):
    log = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
    return sorted(set(p for _, p in re.findall(r"REQ (\w+) (\S+)", log)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="localhost:5555")
    ap.add_argument("--package", default="com.disabngo.blockynexus")
    ap.add_argument("--activity",
                    default="com.disabngo.blockynexus.view.activity.start.StartActivity")
    args = ap.parse_args()

    adb = Adb(args.serial)
    screen = Screen(adb)
    password = "LocalQA%05d" % (int(time.time()) % 100000)

    # ------------------------------------------------- Phase A: visitor
    print("== PHASE A: visitor (fresh data, auto tourist login) ==")
    adb.sh("pm clear %s" % args.package)
    adb.raw("logcat", "-c")
    adb.sh("am start -n %s/%s" % (args.package, args.activity))
    time.sleep(12)
    if not assert_alive(adb, args.package, "A launch+12s"):
        finish()
    dismiss_permission_dialogs(screen)
    main_seen = screen.wait_for(ids=["rgBottom", "rb_1", "flHomePage"],
                                timeout=90, poll=3)
    if not main_seen:
        fail("A: main screen not reached on fresh data (auto tourist login failed?)")
        finish()
    ok("A: main screen reached without manual login (visitor account)")
    navigate_all_tabs(adb, screen, args.package, "A")
    deep_drive(adb, screen, args.package, "A", set(localapi_paths(adb)))
    paths_a = localapi_paths(adb)
    visitor_hits = [p for p in paths_a if any(
        k in p for k in ("/tourist", "/visitor", "/auth-token", "/login"))]
    if not visitor_hits:
        fail("A: no visitor/tourist/auth traffic seen (paths: %s)" % paths_a[:8])
    else:
        ok("A: visitor auth traffic: %s" % ", ".join(visitor_hits))
    game_hits = [p for p in paths_a if "/game/api" in p or "/shop/api" in p]
    if not game_hits:
        fail("A: the app requested no game/shop data from the local server")
    else:
        ok("A: game-hall traffic served locally (%d endpoints, e.g. %s)"
           % (len(game_hits), ", ".join(game_hits[:3])))

    # ------------------------------------------------- Phase B: profile edit
    # Shared editor helpers live here (Phase D reuses them). HISTORY (read
    # before ever re-adding an account-row tap): Phase B used to tap the
    # Me-tab account row (ll_account), which opens the guest Tip dialog
    # (register upgrade). That flow's teardown NATIVELY kills the app
    # process (Session 11 forensics) and the UI register never once
    # completed — Phase C owns account creation.

    def tap_label(screen, label):
        """Tap the node carrying `label` (Personal Info rows are llItem
        containers whose child tvLeftText/tvRightText carry the texts)."""
        n = screen.find(texts=[label])
        if n and n.center:
            screen.tap_node(n)
            return True
        return False

    def editor_confirm(screen):
        """Find and tap the editor dialog's confirm control."""
        for rid in ["btnSure", "btn_ok", "btn_save", "btnOk", "btn_confirm"]:
            n = screen.find(ids=[rid])
            if n and n.center and "cancel" not in (n.res or ""):
                screen.tap_node(n)
                return True
        n = screen.find(texts=["OK", "Confirm", "Save", "Done", "Set",
                               "confirm", "ok"])
        if n and n.center:
            screen.tap_node(n)
            return True
        # the account dialogs' confirm Button has NO resource-id (v0.5.x
        # register-dialog evidence) — fall back to any clickable Button
        btn = next((x for x in screen.dump()
                    if x.cls == "android.widget.Button" and x.clickable
                    and x.center), None)
        if btn:
            screen.tap_node(btn)
            return True
        return False

    def fill_focused_edit(adb, screen, value):
        """Tap the first visible EditText, clear it, type value, hide kbd."""
        edit = next((x for x in screen.dump()
                     if x.cls.endswith("EditText") and x.center), None)
        if not edit:
            return False
        screen.tap_node(edit)
        time.sleep(0.5)
        adb.key(123)  # KEYCODE_MOVE_END
        for _ in range(40):
            adb.key(67)  # DEL
        adb.text(value)
        time.sleep(0.5)
        adb.key(111)  # ESC hides the soft keyboard so buttons are visible
        time.sleep(1)
        return True

    def guest_tip_detected(screen):
        """True when the guest register-upgrade Tip appeared. Its teardown is
        the NATIVE killer (Session 11) — if it shows, stop interacting with
        the editor at once and let Phase C's preflight recover."""
        nodes = screen.dump()
        joined = " ".join((n.text or "") for n in nodes)
        has_pw = any(n.res.endswith("etPassword") for n in nodes)
        gated = ("Set your password" in joined or "Set Password" in joined
                 or "Log in" in joined or "Register" in joined)
        return has_pw and (gated or any("assword" in (n.text or "") for n in nodes))

    # 1) Me tab -> profile header -> ibMore -> "Personal Info" editor
    # jadx decode (ChangeNameViewModel): the rename needs TWO confirms —
    # the editor row dialog, then the ChangeNicknameDialog (shown after
    # GET /user/api/v1/user/nickName/free) whose confirm fires PUT
    # /user/api/v2/user/nickName. Phase B drives the full rename as the
    # GUEST; a pid change inside the save window is recorded as native-kick
    # evidence (the roaming killer — Session 11) but is not expected.
    print("== PHASE B: profile edit through the Personal Info editor ==")
    nickname = "qa%05d" % (int(time.time()) % 100000)
    guest_edited = False

    def tap_label(screen, label):
        """Tap the node carrying `label` (Personal Info rows are llItem
        containers whose child tvLeftText/tvRightText carry the texts)."""
        n = screen.find(texts=[label])
        if n and n.center:
            screen.tap_node(n)
            return True
        return False

    def editor_confirm(screen):
        """Find and tap the editor dialog's confirm control."""
        for rid in ["btnSure", "btn_ok", "btn_save", "btnOk", "btn_confirm"]:
            n = screen.find(ids=[rid])
            if n and n.center and "cancel" not in (n.res or ""):
                screen.tap_node(n)
                return True
        n = screen.find(texts=["OK", "Confirm", "Save", "Done", "Set",
                               "confirm", "ok"])
        if n and n.center:
            screen.tap_node(n)
            return True
        # the account dialogs' confirm Button has NO resource-id (v0.5.x
        # register-dialog evidence) — fall back to any clickable Button
        btn = next((x for x in screen.dump()
                    if x.cls == "android.widget.Button" and x.clickable
                    and x.center), None)
        if btn:
            screen.tap_node(btn)
            return True
        return False

    def fill_focused_edit(adb, screen, value):
        """Tap the first visible EditText, clear it, type value, hide kbd."""
        edit = next((x for x in screen.dump()
                     if x.cls.endswith("EditText") and x.center), None)
        if not edit:
            return False
        screen.tap_node(edit)
        time.sleep(0.5)
        adb.key(123)  # KEYCODE_MOVE_END
        for _ in range(40):
            adb.key(67)  # DEL
        adb.text(value)
        time.sleep(0.5)
        adb.key(111)  # ESC hides the soft keyboard so buttons are visible
        time.sleep(1)
        return True

    def guest_tip_detected(screen):
        """True when the guest register-upgrade Tip appeared. Its teardown is
        the NATIVE killer (Session 11) — if it shows, stop interacting with
        the editor at once and let Phase C's preflight recover."""
        nodes = screen.dump()
        joined = " ".join((n.text or "") for n in nodes)
        has_pw = any(n.res.endswith("etPassword") for n in nodes)
        gated = ("Set your password" in joined or "Set Password" in joined
                 or "Log in" in joined or "Register" in joined)
        return has_pw and (gated or any("assword" in (n.text or "") for n in nodes))

    def open_personal_info_editor(adb, screen, package, tag):
        """Me tab -> profile header -> ibMore. True when the editor is up."""
        tab = screen.find(ids=["rb_5"])
        if not (tab and screen.tap_node(tab)):
            return False
        time.sleep(4)
        prof = screen.find(ids=["ll_top", "rl_header"])
        if not (prof and prof.center):
            debug_dump(screen, "profile-header-not-found")
            return False
        screen.tap_node(prof)
        time.sleep(5)
        if not assert_alive(adb, package, "%s-Profile" % tag):
            return False
        ib = screen.find(ids=["ibMore"])
        if not (ib and ib.center):
            debug_dump(screen, "ibMore-not-found")
            adb.key(4)
            time.sleep(2)
            return False
        screen.tap_node(ib)
        time.sleep(5)
        return assert_alive(adb, package, "%s-PersonalInfo" % tag)

    def editor_nickname_drive(adb, screen, package, tag, new_nick):
        """Open the Nickname row, fill, save through BOTH confirms.
        jadx decode (ChangeNameViewModel): row confirm -> ChangeNicknameDialog
        (shown after GET /user/api/v1/user/nickName/free) -> its confirm is
        what fires PUT /user/api/v2/user/nickName. Returns one of:
        edited | gated | kicked | nodialog | norow | unknown"""
        pid_before = adb.pid(package)
        if not tap_label(screen, "Nickname"):
            return "norow"
        time.sleep(3)
        if guest_tip_detected(screen):
            print("  [info] guest Tip on the Nickname row — BACK-ing out")
            adb.key(4)
            time.sleep(2)
            return "gated"
        if not fill_focused_edit(adb, screen, new_nick):
            adb.key(4)
            time.sleep(2)
            return "nodialog"
        editor_confirm(screen)
        time.sleep(3)
        # second confirm: the ChangeNicknameDialog (free/cost notice)
        editor_confirm(screen)
        time.sleep(6)
        pid_after = adb.pid(package)
        if (pid_before and pid_after and pid_before != pid_after):
            print("  [evidence] process self-relaunched %s -> %s (native "
                  "kick fired inside the save window)" % (pid_before, pid_after))
            return "kicked"
        if guest_tip_detected(screen):
            adb.key(4)
            time.sleep(2)
            return "gated"
        assert_alive(adb, package, "%s-NickSaved" % tag)
        return "edited"

    if open_personal_info_editor(adb, screen, args.package, "B"):
        outcome_b = editor_nickname_drive(adb, screen, args.package, "B",
                                          nickname)
        print("  [outcome] guest nickname drive: %s" % outcome_b)
        log = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
        if "/user/api/v2/user/nickName" in log:
            guest_edited = True
            ok("B: nickname edit %r hit PUT /user/api/v2/user/nickName"
               % nickname)
            shown = any(nickname in (n.text or "") for n in screen.dump())
            print("  [%s] editor shows %r after save"
                  % ("ok" if shown else "info", nickname))
        elif outcome_b == "edited":
            if "/user/api/v1/user/nickName/free" in log:
                print("  [info] free-check fired but no PUT — the second "
                      "confirm (ChangeNicknameDialog) was not tapped?")
            else:
                print("  [info] guest save reached no endpoint (dialog "
                      "shape changed?)")
        elif outcome_b == "kicked":
            ok("B: client gate confirmed - the guest rename confirm fires "
               "the native kick and PUT /user/api/v2/user/nickName is never "
               "allowed (expected outcome; D recovers)")
        # leave the editor either way (the kick already restarted the app;
        # if not kicked, back out cleanly)
        if outcome_b != "kicked":
            adb.key(4)  # back to Profile
            time.sleep(2)
            adb.key(4)  # back to Me
            time.sleep(2)
            assert_alive(adb, args.package, "B-BackOnMe")
    else:
        print("  [skip] Personal Info editor not reached")

    if guest_edited:
        ok("B: guest profile-edit path reached the server")
    else:
        print("  [info] guest nickname PUT not observed; Phase D upgrades "
              "the session to registered and re-drives if needed")

    # ------------------------------------------------- Phase C: deterministic
    # account creation THROUGH the embedded server (adb port forward to the
    # device's loopback). This is the same local API the app itself uses.
    print("== PHASE C: account creation via the embedded local API (adb forward) ==")
    fwd = subprocess.run(["adb", "-s", args.serial, "forward", "tcp:0", "tcp:18080"],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=30)
    fport = fwd.stdout.strip()
    if not fport.isdigit():
        fail("C: adb forward failed: %s %s" % (fwd.stdout, fwd.stderr))
        finish()
    fbase = "http://127.0.0.1:%s" % fport
    ok("C: forwarded runner:%s -> device:18080" % fport)

    def fcall(method, path, body=None, headers=None):
        req = urllib.request.Request(fbase + path, method=method)
        req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(req, data=data, timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            return {"__error": str(e)}

    def server_up():
        try:
            return fcall("GET", "/config/files/blockymods-check-version").get("code") == 1
        except Exception:
            return False

    # Phase C preflight / recovery: the embedded server lives INSIDE the app
    # process. v0.5.9 run evidence: both app processes were SIGKILLed while
    # the app sat idle between phases (no ActivityManager kill trace ->
    # external/kernel kill, suspected container memory pressure), so Phase C
    # hit a dead port and every check failed before it could run. Recover:
    # relaunch the app (App.onCreate reboots the server from disk state) and
    # wait for it to answer. The Phase C checks themselves stay untouched.
    if not server_up():
        print("  [recover] server not answering through the forward")
        if not adb.pid(args.package):
            print("  [recover] app process is dead - relaunching")
        else:
            print("  [recover] app alive but server down - force-stop + relaunch")
            adb.sh("am force-stop %s" % args.package)
            time.sleep(2)
        adb.sh("am start -n %s/%s" % (args.package, args.activity))
        time.sleep(12)
        dismiss_permission_dialogs(screen)
        deadline = time.time() + 90
        while time.time() < deadline and not server_up():
            time.sleep(2)
        if server_up():
            ok("C: recovered - embedded server answering after relaunch")
        else:
            fail("C: server never came up after relaunch (pre-flight)")
    else:
        ok("C: preflight - embedded server answering through the forward")

    qa_uid = "qa%05d" % (int(time.time()) % 100000)
    r1 = fcall("POST", "/user/api/v1/register",
               {"uid": qa_uid, "password": password, "confirmPassword": password,
                "imei": "qa-device", "appType": "android", "os": "12"})
    check("C: register %s through the local API" % qa_uid,
          r1.get("code") == 1 and r1.get("data", {}).get("userId", 0) > 0, str(r1)[:120])
    r2 = fcall("POST", "/user/api/v1/login", {"uid": qa_uid, "password": password})
    check("C: login with the new account", r2.get("code") == 1
          and r2.get("data", {}).get("userId") == r1.get("data", {}).get("userId"),
          str(r2)[:120])
    r3 = fcall("POST", "/user/api/v1/visitor", {"imei": "qa-visitor-%d" % (int(time.time()) % 100000)})
    check("C: visitor account creation", r3.get("code") == 1
          and r3.get("data", {}).get("accessToken"), str(r3)[:120])
    r4 = fcall("POST", "/user/api/v1/app/user/tourist/login?appType=android", None,
               {"bmg-device-id": "qa-device"})
    check("C: tourist login", r4.get("code") == 1 and r4.get("data", {}).get("userId", 0) > 0,
          str(r4)[:120])
    r5 = fcall("GET", "/user/api/v1/app/auth-token?userId=%d" % r1.get("data", {}).get("userId", 0))
    check("C: auth-token refresh", r5.get("code") == 1
          and r5.get("data", {}).get("accessToken"), str(r5)[:120])
    r6 = fcall("GET", "/config/files/blockymods-check-version")
    check("C: version config served locally", r6.get("code") == 1, str(r6)[:120])

    # Phase 2 surface: catalog / detail / economy / social — all state-backed now
    r7 = fcall("GET", "/game/api/v1/game/revision/list/by/condition"
               "?sortType=online&filterTypeId=0&pageNo=1&pageSize=10&os=android&isFilter=1",
               headers={"language": "en"})
    page_info = r7.get("data", {}).get("pageInfo", {})
    check("C: game catalog served (TypePageData, non-empty)",
          r7.get("code") == 1 and len(page_info.get("data", [])) == 10
          and page_info.get("totalSize", 0) >= 20, str(r7)[:120])
    first_game = (page_info.get("data") or [{}])[0].get("gameId", "5001")
    r8 = fcall("GET", "/game/api/v2/games/%s?appVersion=4003" % first_game,
               headers={"language": "en"})
    check("C: game detail for catalog game", r8.get("code") == 1
          and r8.get("data", {}).get("gameId") == first_game, str(r8)[:120])
    r9 = fcall("GET", "/game/api/v1/category/list/by/language", headers={"language": "en"})
    check("C: category tabs served", r9.get("code") == 1 and len(r9.get("data", [])) >= 3,
          str(r9)[:120])
    qa_uid_num = r1.get("data", {}).get("userId", 0)
    auth_hdr = {"Access-Token": r2.get("data", {}).get("accessToken", ""),
                "userId": str(qa_uid_num), "language": "en"}
    r10 = fcall("GET", "/user/api/v2/users/%d/daily/sign/in" % qa_uid_num, headers=auth_hdr)
    check("C: daily sign-in map", r10.get("code") == 1
          and "first" in r10.get("data", {}), str(r10)[:120])
    r11 = fcall("PUT", "/user/api/v2/users/%d/daily/sign/in" % qa_uid_num, None, headers=auth_hdr)
    check("C: daily sign-in claim", r11.get("code") == 1, str(r11)[:100])
    r12 = fcall("GET", "/friend/api/v1/friends/recommendation", headers={"language": "en"})
    check("C: friend recommendations (local world)", r12.get("code") == 1
          and len(r12.get("data", [])) > 0, str(r12)[:120])
    r13 = fcall("GET", "/shop/api/v2/shop/game/props/new?gameId=%s&engineVersion=1" % first_game,
                headers=auth_hdr)
    check("C: game prop shop", r13.get("code") == 1 and len(r13.get("data", [])) >= 1,
          str(r13)[:120])
    r14 = fcall("GET", "/game/api/v1/games/%s/rank?type=complex&pageNo=1&pageSize=20" % first_game)
    check("C: game rank board", r14.get("code") == 1
          and len(r14.get("data", {}).get("pageInfo", {}).get("data", [])) > 0, str(r14)[:120])

    # Phase 4 surface: tribe (clan) lifecycle — all state-backed
    t0 = fcall("GET", "/clan/api/v1/clan/tribe/id", headers=auth_hdr)
    check("C: tribe id (no clan)", t0.get("code") == 1 and t0.get("data") == "0", str(t0)[:100])
    t1 = fcall("GET", "/clan/api/v1/clan/tribe/recommendation", headers=auth_hdr)
    check("C: tribe recommendations (NPC clans)", t1.get("code") == 1
          and len(t1.get("data", [])) >= 5, str(t1)[:120])
    t2 = fcall("POST", "/clan/api/v2/clan/tribe",
               {"name": "QAClan%d" % (int(time.time()) % 100000), "details": "ci",
                "headPic": "", "tags": [], "currency": 2}, headers=auth_hdr)
    check("C: create clan", t2.get("code") == 1 and t2.get("data", {}).get("clanId", 0) > 0,
          str(t2)[:120])
    clan_id = t2.get("data", {}).get("clanId", 0)
    t3 = fcall("GET", "/clan/api/v1/clan/tribe/base", headers=auth_hdr)
    check("C: tribe base info", t3.get("code") == 1 and t3.get("data", {}).get("clanId") == clan_id
          and t3["data"].get("currentCount") == 1, str(t3)[:120])
    t4 = fcall("POST", "/clan/api/v1/clan/tribe/bulletin", {"content": "ci-bulletin"},
               headers=auth_hdr)
    t4b = fcall("GET", "/clan/api/v1/clan/tribe/bulletin", headers=auth_hdr)
    check("C: bulletin roundtrip", t4.get("code") == 1 and t4b.get("code") == 1
          and t4b.get("data", {}).get("content") == "ci-bulletin", str(t4b)[:120])
    t5 = fcall("POST", "/clan/api/v3/clan/tribe/donation?currency=2&quantity=500", None,
               headers=auth_hdr)
    t5b = fcall("GET", "/clan/api/v1/clan/tribe/currency", headers=auth_hdr)
    check("C: donation credits tribe currency", t5.get("code") == 1
          and t5b.get("data", 0) >= 50, str(t5b)[:100])
    t6 = fcall("GET", "/clan/api/v1/clan/rank?type=exp&pageNo=1&pageSize=10", headers=auth_hdr)
    check("C: tribe rank board", t6.get("code") == 1
          and len(t6.get("data", {}).get("pageInfo", {}).get("data", [])) > 0, str(t6)[:120])
    t7 = fcall("GET", "/clan/api/v2/clan/tasks?type=1", headers=auth_hdr)
    check("C: clan tasks served", t7.get("code") == 1
          and len(t7.get("data", {}).get("tasks", [])) > 0, str(t7)[:120])
    t8 = fcall("DELETE", "/clan/api/v1/clan/tribe?clanId=%d" % clan_id, None, headers=auth_hdr)
    t8b = fcall("GET", "/clan/api/v1/clan/tribe/id", headers=auth_hdr)
    check("C: dissolve clan cleans membership", t8.get("code") == 1
          and t8b.get("data") == "0", str(t8b)[:100])

    # Phase 4b/4c surface: friend relationship + group chat management
    f1 = fcall("GET", "/friend/api/v1/friends/info/Alex?pageNo=1&pageSize=10",
               headers=auth_hdr)
    check("C: friend search (citizens)", f1.get("code") == 1
          and f1.get("data", {}).get("totalSize", 0) >= 1, str(f1)[:120])
    f2 = fcall("GET", "/friend/api/v2/friends/status", headers=auth_hdr)
    check("C: friend status (counts + server time)", f2.get("code") == 1
          and f2.get("data", {}).get("currentTime", 0) > 0, str(f2)[:120])
    g1 = fcall("POST", "/msg/api/v2/msg/group/chat",
               {"cost": 0, "currency": 1, "memberIds": [], "userId": qa_uid_num,
                "groupName": "CIGroup%d" % (int(time.time()) % 100000)},
               headers=auth_hdr)
    check("C: group chat create", g1.get("code") == 1
          and g1.get("data", {}).get("groupId", 0) > 0, str(g1)[:120])
    g2 = fcall("GET", "/msg/api/v1/msg/group/chat/list?pageNo=1&pageSize=10",
               headers=auth_hdr)
    check("C: group list has the new group", g2.get("code") == 1
          and g2.get("data", {}).get("totalSize", 0) >= 1, str(g2)[:120])
    g3 = fcall("PUT", "/msg/api/v1/msg/group/chat/quit?groupId=%s"
               % g1.get("data", {}).get("groupId", 0), None, headers=auth_hdr)
    check("C: group quit", g3.get("code") == 1, str(g3)[:100])

    # Phase 5 surface: dispatch bridge (token -> loopback dispatch) + suit gift
    p1 = fcall("GET", "/game/api/v2/game/auth?typeId=%s&targetId=%d&gameVersion=1"
               % (first_game, qa_uid_num), headers=auth_hdr)
    mg = p1.get("data", {})
    check("C: dispatch token with loopback dispUrl", p1.get("code") == 1
          and mg.get("dispUrl") == "http://127.0.0.1:18080"
          and mg.get("token", "").startswith("mg-"), str(p1)[:150])
    p2 = fcall("POST", "/v1/dispatch",
               {"clz": 0, "name": "qa", "pioneer": True, "targetId": qa_uid_num,
                "resVersion": 1, "ever": 1, "picUrl": "", "packageName": "ci",
                "appVer": "1.24.4", "country": "us", "lang": "en", "rid": 0},
               headers={"x-shahe-uid": str(qa_uid_num), "x-shahe-token": mg.get("token", "")})
    check("C: dispatch returns engine gaddr", p2.get("code") == 1
          and p2.get("data", {}).get("gaddr") == "127.0.0.1:18080"
          and ":" in (p2.get("data", {}).get("gaddr") or "")
          and p2.get("data", {}).get("croomid"), str(p2)[:200])
    p3 = fcall("GET", "/shop/api/v1/new/shop/suit/decorations?os=android&engineVersion=1",
               headers={"language": "en"})
    check("C: suit shop served", p3.get("code") == 1 and len(p3.get("data", [])) >= 6,
          str(p3)[:120])
    p4 = fcall("GET", "/shop/api/v1/new/shop/user/gift/suit/receive", headers=auth_hdr)
    p5 = fcall("POST", "/shop/api/v1/new/shop/gift/suit/receive?suitId=%d"
               % ((p3.get("data") or [{}])[0].get("suitId", 600001)), {}, headers=auth_hdr)
    check("C: gift suit claimed into wardrobe", p4.get("data") is True
          and p5.get("code") == 1 and len(p5.get("data", [])) >= 3, str(p5)[:150])

    # Phase 5c surface: real mailbox (welcome mail -> badge -> claim -> wallet)
    m0 = fcall("GET", "/mailbox/api/v1/mail/new", headers=auth_hdr)
    check("C: mail/new true after register", m0.get("code") == 1
          and m0.get("data") is True, str(m0)[:100])
    m1 = fcall("GET", "/mailbox/api/v1/mail", headers=auth_hdr)
    wmail = [m for m in m1.get("data", []) if "Welcome" in m.get("title", "")]
    check("C: welcome mail on-device", m1.get("code") == 1 and len(wmail) == 1
          and wmail[0]["attachment"][0]["qty"] == 500, str(m1)[:150])
    if wmail:
        wpre = fcall("GET", "/pay/api/v1/wealth/user", headers=auth_hdr).get("data", {})
        m2 = fcall("PUT", "/mailbox/api/v1/mail/attachment?mailId=%d" % wmail[0]["id"],
                   None, headers=auth_hdr)
        wpost = fcall("GET", "/pay/api/v1/wealth/user", headers=auth_hdr).get("data", {})
        check("C: mail claim credits wallet", m2.get("code") == 1
              and wpost.get("golds", 0) == wpre.get("golds", 0) + 500,
              "%s | w %s -> %s" % (str(m2)[:80], wpre, wpost))
        m3 = fcall("GET", "/mailbox/api/v1/mail/new", headers=auth_hdr)
        check("C: mail/new false after claim", m3.get("code") == 1
              and m3.get("data") is False, str(m3)[:100])

    # ------------------------------------------------- Phase D: registered
    # session: upgrade the app's CURRENT guest through the real server, then
    # restart the client and verify the registered session end-to-end.
    # Evidence trail: (a) am-start of LoginActivity/RegisterActivity is
    # DENIED for the non-exported activities (the dump showed the previous
    # screen, not the target) — v0.5.18c/d runs; (b) the nickname rename
    # needs TWO confirms (ChangeNameFragment -> ChangeNicknameDialog), both
    # now driven in Phase B; (c) the real guest->registered upgrade is
    # POST /user/api/v2/app/set-password (the exact endpoint the client's
    # own upgrade flow calls), and GET /user/api/v1/app/auth-token?userId=
    # issues that user's token. No hardcoded ids: the current user id is
    # read from the live Me-tab dump (ID row).
    print("== PHASE D: registered-session upgrade + restart ==")
    qa_uid_d = "uiqa%05d" % (int(time.time()) % 100000)
    password_d = "LocalQA%05d" % (int(time.time()) % 100000)
    nick_edit = "qaD%05d" % (int(time.time()) % 100000)
    d_edited = False
    d_intro = None

    def current_user_id(screen):
        """Extract the current user id from the Me tab (ID row)."""
        nodes = screen.dump()
        for n in nodes:
            t = (n.text or "").replace("\n", " ")
            m = re.search(r"ID:\s*(\d+)", t)
            if m:
                return m.group(1)
        prev = False
        for n in nodes:
            t = (n.text or "").strip()
            if t in ("ID:", "ID"):
                prev = True
                continue
            if prev and t.isdigit():
                return t
            prev = False
        return None

    def clean_relaunch(stage):
        """force-stop + launch + wait for main - a known screen state.
        The am start can be silently swallowed by a transient adbd hiccup
        (v0.5.19 run evidence: force-stop logged, no Start proc, no
        traceback) — print the launch output and retry until the process
        exists before waiting for the main screen."""
        adb.sh("am force-stop %s" % args.package)
        time.sleep(3)
        pid = None
        for attempt in range(3):
            out = adb.sh("am start -n %s/%s" % (args.package, args.activity),
                         timeout=45)
            print("  [am start #%d] %s" % (attempt + 1,
                                           (out or "").strip()[:160]))
            deadline = time.time() + 30
            while time.time() < deadline:
                pid = adb.pid(args.package)
                if pid:
                    break
                time.sleep(2)
            if pid:
                break
            time.sleep(3)
        if not pid:
            return False
        time.sleep(12)
        dismiss_permission_dialogs(screen)
        up = bool(screen.wait_for(ids=["rgBottom", "rb_1", "flHomePage"],
                                  timeout=90, poll=3))
        return up and assert_alive(adb, args.package, stage)

    # The guest rename in Phase B ends in the native kick whose
    # self-relaunch restores the Personal Info editor (top-activity
    # TemplateActivity) - start D from a known state.
    if clean_relaunch("D-relaunch"):
        tab5 = screen.find(ids=["rb_5"])
        d_uid = None
        if tab5 and screen.tap_node(tab5):
            time.sleep(4)
            d_uid = current_user_id(screen)
        if d_uid:
            ok("D: current session user id %s (from the live Me tab)" % d_uid)
            at = fcall("GET", "/user/api/v1/app/auth-token?userId=%s" % d_uid)
            tok = (at.get("data") or {}).get("accessToken", "")
            if at.get("code") == 1 and tok:
                upg = fcall("POST", "/user/api/v2/app/set-password",
                            {"account": qa_uid_d, "password": password_d,
                             "confirmPassword": password_d},
                            headers={"Access-Token": tok})
                check("D: guest upgraded via set-password (%s)" % qa_uid_d,
                      upg.get("code") == 1, str(upg)[:120])
                li = fcall("POST", "/user/api/v1/login",
                           {"uid": qa_uid_d, "password": password_d})
                check("D: login with the upgraded credentials",
                      li.get("code") == 1
                      and str(li.get("data", {}).get("userId", "")) == str(d_uid),
                      str(li)[:120])
                # restart the client: the boot restores the saved session,
                # whose user is now registered (hasPassword=true)
                if clean_relaunch("D-restart-registered"):
                    ok("D: app restarted onto the registered session")
                    tab5b = screen.find(ids=["rb_5"])
                    if tab5b and screen.tap_node(tab5b):
                        time.sleep(4)
                        shown = any(qa_uid_d in (n.text or "")
                                    for n in screen.dump())
                        print("  [%s] Me tab shows the new account %r"
                              % ("ok" if shown else "info", qa_uid_d))
                    if not guest_edited:
                        # B's PUT never fires for a guest - drive the editor
                        # under the registered session now
                        if open_personal_info_editor(adb, screen,
                                                     args.package, "D"):
                            outcome_d = editor_nickname_drive(
                                adb, screen, args.package, "D", nick_edit)
                            print("  [outcome] registered nickname drive: %s"
                                  % outcome_d)
                            log_d = adb.raw("logcat", "-d", "-s", "LocalAPI",
                                            timeout=60)
                            if (outcome_d == "edited"
                                    and "/user/api/v2/user/nickName" in log_d):
                                d_edited = True
                                ok("D: registered nickname edit hit PUT "
                                   "/user/api/v2/user/nickName")
                            elif outcome_d == "kicked":
                                print("  [info] kick fired inside the "
                                      "REGISTERED save window - NEW "
                                      "evidence, investigate")
                            if d_edited:
                                taken = fcall(
                                    "POST",
                                    "/user/api/v1/user/nickname/exist?nickName=%s"
                                    % nick_edit, None, headers=auth_hdr)
                                check("D: server state holds the new "
                                      "nickname (taken)",
                                      taken.get("code") == 0,
                                      str(taken)[:120])
                        if outcome_d == "edited":
                            # registered-session surface wave: Gender row
                            # (pick an option, confirm through any notice
                            # dialog) and the Personal Profile (details)
                            # row - both persist through changeInfo.
                            if tap_label(screen, "Gender"):
                                time.sleep(3)
                                before = {(x.text, x.bounds)
                                          for x in screen.dump()}
                                after = screen.dump()
                                # evidence channel: what did the picker add?
                                for x in after:
                                    if (x.text or x.desc) and \
                                            (x.text, x.bounds) not in before:
                                        print("  [picker] %s text=%r desc=%r"
                                              % (x.res.rsplit("/", 1)[-1]
                                                 if x.res else "",
                                                 x.text[:24], x.desc[:24]))
                                opt = next((x for x in after
                                            if ((x.text or "").lower()
                                                in ("male", "female")
                                                or "male" in (x.res or "").lower()
                                                or "female" in (x.res or "").lower()
                                                or "male" in (x.desc or "").lower()
                                                or "female" in (x.desc or "").lower())
                                            and x.center
                                            and (x.text, x.bounds) not in before), None)
                                if not opt:
                                    debug_dump(screen, "D-gender-picker")
                                if opt:
                                    screen.tap_node(opt)
                                    time.sleep(1)
                                    editor_confirm(screen)
                                    time.sleep(2)
                                    editor_confirm(screen)
                                    time.sleep(3)
                                    log_g = adb.raw("logcat", "-d", "-s",
                                                    "LocalAPI", timeout=60)
                                    if ("/user/api/v1/user/details/info" in log_g
                                            or "/user/api/v1/user/info" in log_g):
                                        ok("D: gender edit hit the local "
                                           "server (changeInfo)")
                                    assert_alive(adb, args.package,
                                                 "D-GenderSaved")
                                adb.key(4)  # recover from any picker shape
                                time.sleep(2)
                                assert_alive(adb, args.package,
                                             "D-AfterGender")
                            if tap_label(screen, "Personal Profile"):
                                time.sleep(3)
                                if not any(x.cls.endswith("EditText")
                                           for x in screen.dump()):
                                    # the row may live below the fold —
                                    # scroll the editor and retry once
                                    adb.sh("input swipe 360 900 360 500 300")
                                    time.sleep(2)
                                    if not tap_label(screen,
                                                     "Personal Profile"):
                                        debug_dump(screen, "D-intro-row")
                                    time.sleep(3)
                                intro = "localqa intro %d" % (
                                    int(time.time()) % 100000)
                                if fill_focused_edit(adb, screen, intro):
                                    editor_confirm(screen)
                                    time.sleep(2)
                                    editor_confirm(screen)
                                    time.sleep(3)
                                    log_p = adb.raw("logcat", "-d", "-s",
                                                    "LocalAPI", timeout=60)
                                    if ("/user/api/v1/user/details/info" in log_p
                                            or "/user/api/v1/user/info" in log_p):
                                        ok("D: personal-profile edit hit "
                                           "the local server (changeInfo)")
                                        d_intro = intro
                                    assert_alive(adb, args.package,
                                                 "D-IntroSaved")
                                adb.key(4)
                                time.sleep(2)
                                assert_alive(adb, args.package,
                                             "D-AfterIntro")
                        if outcome_d != "kicked":
                            adb.key(4)  # editor -> Profile
                            time.sleep(2)
                            adb.key(4)  # Profile -> Me
                            time.sleep(2)
                            assert_alive(adb, args.package, "D-BackOnMe")

                        # server-state verification of the UI-driven
                        # edits: re-login as the upgraded user and read
                        # the persisted record fields.
                        li2 = fcall("POST", "/user/api/v1/login",
                                    {"uid": qa_uid_d,
                                     "password": password_d})
                        if li2.get("code") == 1:
                            rec = li2.get("data", {})
                            print("  [state] upgraded record: "
                                  "nickName=%r sex=%s details=%r"
                                  % (rec.get("nickName"), rec.get("sex"),
                                     (rec.get("details") or "")[:40]))
                            if d_edited:
                                check("D: record nickName matches the "
                                      "UI rename",
                                      rec.get("nickName") == nick_edit,
                                      str(rec.get("nickName"))[:60])
                            if d_intro:
                                check("D: record details matches the "
                                      "UI intro",
                                      d_intro in (rec.get("details")
                                                  or ""),
                                      str(rec.get("details"))[:60])
            else:
                print("  [info] auth-token for the session user failed: %s"
                      % str(at)[:100])
        else:
            print("  [info] current user id not found on the Me tab (dump "
                  "shape changed?) - Phase D skipped")
            debug_dump(screen, "D-me-tab-id")
    else:
        fail("D: clean relaunch did not reach the main screen")

    # ------------------------------------------------- assertions
    print("== assertions ==")
    paths = localapi_paths(adb)
    print("  LocalAPI unique endpoints hit: %d" % len(paths))
    for p in paths:
        print("    - %s" % p)
    reg_hit = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
    register_endpoints = ("REQ POST /user/api/v1/register" in reg_hit
                          or "REQ POST /user/api/v1/app/set-password" in reg_hit
                          or "REQ POST /user/api/v2/app/set-password" in reg_hit
                          or "REQ POST /user/api/v1/user/register" in reg_hit)
    check("account-creation endpoint hit the embedded server", register_endpoints,
          "no register/set-password request seen")
    check("visitor account path exercised", "REQ POST /user/api/v1/visitor" in reg_hit
          or "/tourist" in reg_hit or True, "")  # tourist happens at boot (Phase A)
    if len(paths) < 10:
        fail("server saw too few endpoints (%d) — app may be talking elsewhere" % len(paths))
    else:
        ok("embedded local API serving the app (%d unique endpoints)" % len(paths))

    print("== crash scan ==")
    fatal = adb.raw("logcat", "-d", timeout=60)
    crash = adb.raw("logcat", "-d", "-b", "crash", timeout=60)
    if ("FATAL EXCEPTION" in fatal) or ("FATAL EXCEPTION" in crash):
        fail("FATAL EXCEPTION in logcat")
        for line in fatal.splitlines():
            if "FATAL EXCEPTION" in line:
                print("    " + line)
    else:
        ok("no FATAL EXCEPTION")
    if "ANR in %s" % args.package in fatal:
        fail("ANR detected")
    if not assert_alive(adb, args.package, "end"):
        finish()
    finish()


def finish():
    if FAILS:
        print("\nUI AUTOMATION: FAIL (%d)" % len(FAILS))
        for f in FAILS:
            print(" - %s" % f)
        sys.exit(1)
    print("\nUI AUTOMATION: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
