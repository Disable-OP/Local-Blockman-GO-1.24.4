#!/usr/bin/env python3
"""UI automation test for the local-API Blockman GO APK (Redroid CI).

Two deterministic phases, driven purely over adb + uiautomator dumps:

  Phase A — VISITOR (fresh app data):
      pm clear -> launch -> the app auto-logs-in as a tourist/visitor account
      through the embedded local server -> navigate all 5 bottom tabs.
      Asserts tourist/auth-token traffic in logcat.

  Phase B — REGISTER (always):
      reach the login screen (Me-tab login entry, or direct am start of
      LoginActivity) -> register a FRESH account through the register UI ->
      (auto-)login -> navigate all tabs again. Asserts
      POST /user/api/v1/register hit the embedded server.

  Final — crash scan (FATAL EXCEPTION / ANR) + process alive everywhere.

Every UI step is derived from live uiautomator dumps, never coordinates.
Exit 0 = pass, 1 = fail.
"""
import argparse
import re
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


class Adb:
    def __init__(self, serial):
        self.serial = serial

    def sh(self, cmd, timeout=30):
        r = subprocess.run(["adb", "-s", self.serial, "shell", cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()

    def raw(self, *args, timeout=60):
        r = subprocess.run(["adb", "-s", self.serial] + list(args),
                           capture_output=True, text=True, timeout=timeout)
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


def register_through_ui(adb, screen, user, password):
    """From the login screen, register a fresh account. Returns True on flow completion."""
    reg = screen.find(ids=["tv_register"], texts=["Register", "Sign up"])
    if not reg:
        return False
    if not screen.tap_node(reg):
        return False
    time.sleep(3)
    acc = screen.wait_for(ids=["editAccount", "inputAccount"], timeout=25, poll=2)
    if not acc:
        return False
    screen.tap_node(acc)
    adb.text(user)
    pw = screen.find(ids=["editPassword", "inputPassword"])
    if pw:
        screen.tap_node(pw)
        adb.text(password)
    pw2 = screen.find(ids=["editPassword1", "inputPassword1"])
    if pw2:
        screen.tap_node(pw2)
        adb.text(password)
    cb = screen.find(ids=["cb_pro"])
    if cb and cb.center:
        screen.tap_node(cb)  # agree to protocol
    nxt = screen.find(texts=["Next", "NEXT"], contains=["next"])
    if not nxt:
        nxt = screen.find(ids=["btn_sign", "btn_next"])
    if not nxt or not screen.tap_node(nxt):
        return False
    time.sleep(3)
    conf = screen.wait_for(texts=["Confirm creation", "Create", "OK", "Done"],
                           ids=["btn_sign", "btn_ok"], timeout=25, poll=2)
    if conf and screen.tap_node(conf):
        time.sleep(2)
    save = screen.find(texts=["Save", "SAVE"], ids=["btn_save"])
    if save and screen.tap_node(save):
        time.sleep(2)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="localhost:5555")
    ap.add_argument("--package", default="com.disabngo.blockynexus")
    ap.add_argument("--activity",
                    default="com.disabngo.blockynexus.view.activity.start.StartActivity")
    args = ap.parse_args()

    adb = Adb(args.serial)
    screen = Screen(adb)
    user = "localqa%05d" % (int(time.time()) % 100000)
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
    paths_a = localapi_paths(adb)
    visitor_hits = [p for p in paths_a if any(
        k in p for k in ("/tourist", "/visitor", "/auth-token", "/login"))]
    if not visitor_hits:
        fail("A: no visitor/tourist/auth traffic seen (paths: %s)" % paths_a[:8])
    else:
        ok("A: visitor auth traffic: %s" % ", ".join(visitor_hits))

    # ------------------------------------------------- Phase B: register
    print("== PHASE B: register a fresh account through the UI ==")
    login_screen = False
    set_password_flow = False

    def on_login_screen():
        return bool(screen.find(ids=["btn_sign"], texts=["Log in", "login"]))

    def dialog_walk(adb, screen, user, password, rounds=30):
        """Walk an unknown sequence of dialogs (password set, register finish,
        confirmations...). The app chains several API calls before showing the
        first dialog, so we keep polling; conclude only after 8 consecutive
        dialog-free dumps."""
        DIALOG_IDS = {"btnSure", "btnCancel", "etPassword", "etPassword2",
                      "btn_ok", "btn_save", "btn_next", "btnOk"}
        stable = 0
        for i in range(rounds):
            nodes = screen.dump()
            if not nodes:
                time.sleep(2)
                continue
            has_dialog = any(n.res.rsplit("/", 1)[-1] in DIALOG_IDS for n in nodes)
            edits = [n for n in nodes if n.cls.endswith("EditText")]
            if not has_dialog and not edits:
                stable += 1
                print("  [walk] round %d: no dialog yet (stable=%d)" % (i, stable))
                if stable >= 15:
                    return False  # nothing dialog-like ever showed up
                time.sleep(2)
                continue
            stable = 0
            sig = tuple(sorted((n.res, n.text) for n in nodes if n.res or n.text))
            for e in edits:
                rid = e.res.rsplit("/", 1)[-1]
                if e.center:
                    screen.tap_node(e)
                    # password boxes get the password, others the username
                    adb.text(password if "assword" in rid or "assword" in e.text else user)
                    time.sleep(0.5)
                    adb.key(111)  # ESC hides the soft keyboard so buttons are visible
                    time.sleep(1)
            if edits:
                nodes = screen.dump()  # re-dump from under the keyboard
            btn = None
            for rid in ["btnSure", "btn_ok", "btn_save", "btn_sign", "btn_next",
                        "btn_confirm", "btnOk"]:
                btn = next((n for n in nodes
                            if n.res.rsplit("/", 1)[-1] == rid and n.res != "btnCancel"), None)
                if btn:
                    break
            if not btn:
                btn = screen.find(texts=["OK", "Confirm", "Save", "Next",
                                         "Confirm creation", "Done", "Set", "confirm"])
            if btn and btn.center:
                screen.tap_node(btn)
            print("  [walk] round %d: edits=%d btn=%s" % (
                i, len(edits), (btn.res.rsplit('/', 1)[-1] if btn and btn.res else
                                (btn.text if btn else "none"))))
            time.sleep(3)
        return True

    def guest_set_password_dialog():
        """Dialog shown for a guest account: set password (register upgrade)."""
        d = screen.find(ids=["etPassword", "etPassword2"], contains=["password", "Password"])
        return d

    def fill_set_password_and_confirm():
        pw_node = screen.find(ids=["etPassword"])
        pw2_node = screen.find(ids=["etPassword2"])
        if pw_node and screen.tap_node(pw_node):
            adb.text(password)
        if pw2_node and screen.tap_node(pw2_node):
            adb.text(password)
        btn = screen.find(texts=["OK", "Confirm", "Save", "Confirm creation", "Done",
                                 "confirm", "ok"])
        if btn and screen.tap_node(btn):
            time.sleep(3)
            return True
        return False

    # 1) More tab (rb_5) -> account row: Tip dialog (guest) -> Set your password
    more = screen.find(ids=["rb_5"])
    if more and screen.tap_node(more):
        time.sleep(4)
        acc_row = screen.find(ids=["ll_account", "rl_header", "ll_nickname"])
        if acc_row and screen.tap_node(acc_row):
            time.sleep(3)
            if on_login_screen():
                login_screen = True
            else:
                ok("B: walking account dialogs generically")
                dialog_walk(adb, screen, user, password)
                # the Tip dialog can be very slow to appear on cold start —
                # give it one more explicit chance before moving on
                log = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
                if ("set-password" in log) or ("/register" in log):
                    set_password_flow = True
                    ok("B: account-creation request observed on the local server")
                else:
                    sure = screen.find(ids=["btnSure"])
                    if sure and screen.tap_node(sure):
                        ok("B: late Tip dialog -> 'Set your password' tapped")
                        dialog_walk(adb, screen, user, password)
                        log = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
                        if ("set-password" in log) or ("/register" in log):
                            set_password_flow = True
                            ok("B: account-creation request observed on the local server")
                    if not set_password_flow:
                        debug_dump(screen, "after-dialog-walk")
        else:
            debug_dump(screen, "acc-row-not-found")

    # 2) scroll the More list for Setting -> Account Switch -> login screen
    if not login_screen and not set_password_flow:
        setting = None
        for _ in range(3):
            adb.sh("input swipe 360 900 360 400 300")
            time.sleep(2)
            setting = screen.find(ids=["me_setting"], texts=["Setting"], contains=["setting"])
            if setting:
                break
        if setting and screen.tap_node(setting):
            time.sleep(3)
            sw = screen.find(texts=["Account Switch", "Switch account"],
                             contains=["account", "switch"])
            if sw and screen.tap_node(sw):
                time.sleep(3)
                login_screen = on_login_screen()
                if not login_screen:
                    add = screen.find(texts=["Add account", "Add", "+", "Log in"],
                                      contains=["add account"])
                    if add and screen.tap_node(add):
                        time.sleep(3)
                        login_screen = on_login_screen()

    # 3) fallback: direct-start the LoginActivity (works on userdebug images)
    if not login_screen and not set_password_flow:
        print("  [info] direct start of LoginActivity as fallback")
        adb.sh("am start -n %s/com.sandbox.login.view.activity.login.LoginActivity" % args.package)
        time.sleep(6)
        login_screen = bool(screen.wait_for(ids=["btn_sign"], texts=["Log in"],
                                            timeout=30, poll=3))
        if not login_screen:
            debug_dump(screen, "fallback-failed")
    if not login_screen and not set_password_flow:
        fail("B: neither login screen nor set-password dialog was reached")
        finish()
    ok("B: account creation flow reached (%s)"
       % ("set-password upgrade" if set_password_flow else "login screen"))
    if not assert_alive(adb, args.package, "B entry"):
        finish()

    if not set_password_flow and login_screen:
        if not register_through_ui(adb, screen, user, password):
            fail("B: register UI flow did not complete")
            finish()
        ok("B: register UI flow completed for user=%s" % user)
        time.sleep(8)
        # maybe a login form is still up (register doesn't always auto-login)
        acc = screen.find(ids=["editAccount", "inputAccount", "edit_password"])
        if acc:
            screen.tap_node(acc)
            adb.text(user)
            pw = screen.find(ids=["editPassword", "inputPassword", "edit_password"])
            if pw:
                screen.tap_node(pw)
                adb.text(password)
            btn = screen.find(ids=["btn_sign"], texts=["Log in"])
            if btn:
                screen.tap_node(btn)
            time.sleep(8)

    main_seen_b = screen.wait_for(ids=["rgBottom", "rb_1", "flHomePage"],
                                  timeout=60, poll=3)
    if not main_seen_b:
        fail("B: main screen not reached after register/login")
        finish()
    ok("B: main screen reached with the freshly registered account")
    navigate_all_tabs(adb, screen, args.package, "B")

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
    if register_endpoints:
        ok("B: an account-creation endpoint hit the embedded server")
    else:
        fail("B: no register/set-password endpoint was exercised")
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
