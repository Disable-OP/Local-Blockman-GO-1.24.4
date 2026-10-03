#!/usr/bin/env python3
"""UI automation test for the local-API Blockman GO APK (Redroid CI).

Drives the real app over adb:
  1. launches and grants runtime permission dialogs
  2. registers a FRESH account through the register UI every run
  3. logs in with it, handles role-make (nickname) screen
  4. navigates every bottom tab of the main screen
  5. asserts: process alive, no FATAL EXCEPTION, embedded LocalAPI server
     received traffic (logcat), and at least one auth endpoint was exercised

Everything is derived from the live UI dump (uiautomator), never from fixed
coordinates. Exit 0 = pass, 1 = fail.
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
        # input text cannot contain spaces; use %s
        self.sh('input text "%s"' % s.replace(" ", "%s"))

    def key(self, keycode):
        self.sh("input keyevent %s" % keycode)

    def pid(self, package):
        out = self.sh("pidof %s" % package)
        return out.strip()


class Node:
    def __init__(self, el):
        self.el = el
        self.text = el.get("text", "")
        self.desc = el.get("content-desc", "")
        self.res = el.get("resource-id", "")
        self.cls = el.get("class", "")
        self.clickable = el.get("clickable") == "true"
        b = el.get("bounds", "")
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
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
        for attempt in range(3):
            try:
                self.adb.sh("uiautomator dump /sdcard/localqa_ui.xml", timeout=25)
                xml = self.adb.sh("cat /sdcard/localqa_ui.xml", timeout=25)
                if "<hierarchy" in xml:
                    return [Node(e) for e in ET.fromstring(xml).iter("node")]
            except Exception:
                pass
            time.sleep(2)
        return []

    def find(self, ids=None, texts=None, contains=None, clickable=False):
        nodes = self.dump()
        for n in nodes:
            hay_id = n.res.split("/")[-1] if n.res else ""
            if ids and hay_id in ids:
                if not clickable or n.clickable:
                    return n
            if texts and (n.text in texts):
                if not clickable or n.clickable or n.cls.endswith("TextView"):
                    return n
            if contains and any(c.lower() in n.text.lower() for c in contains):
                return n
        return None

    def wait_for(self, ids=None, texts=None, contains=None, timeout=30, poll=2):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="localhost:5555")
    ap.add_argument("--package", default="com.disabngo.blockynexus")
    ap.add_argument("--activity", default="com.disabngo.blockynexus.view.activity.start.StartActivity")
    args = ap.parse_args()

    adb = Adb(args.serial)
    screen = Screen(adb)
    user = "localqa%05d" % (int(time.time()) % 100000)
    password = "LocalQA%s" % (int(time.time()) % 100000)

    print("== launch ==")
    adb.raw("logcat", "-c")
    adb.sh("am start -n %s/%s" % (args.package, args.activity))
    time.sleep(12)  # cold start incl. embedded server boot
    if not assert_alive(adb, args.package, "launch+12s"):
        finish()

    print("== permission dialogs ==")
    dismiss_permission_dialogs(screen)

    print("== login screen ==")
    login_btn = screen.wait_for(ids=["btn_sign"], texts=["Log in", "login"],
                                timeout=90, poll=3)
    if not login_btn:
        # maybe already logged in from previous state
        if screen.wait_for(ids=["rgBottom", "rb_1", "flHomePage"], timeout=30, poll=3):
            ok("main screen reached directly (already logged in)")
            skip_auth = True
        else:
            fail("neither login screen nor main screen appeared")
            finish()
    else:
        skip_auth = False
    if not assert_alive(adb, args.package, "login-screen"):
        finish()

    if not skip_auth:
        print("== register a fresh account through the UI ==")
        reg = screen.find(ids=["tv_register"], texts=["Register", "register"])
        if reg and screen.tap_node(reg):
            time.sleep(3)
            # step 1: username + password + confirm + protocol checkbox
            acc = screen.wait_for(ids=["editAccount", "inputAccount"], timeout=30, poll=2)
            if not acc:
                fail("register form did not appear")
                finish()
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
            nxt = screen.find(texts=["Next", "next"], contains=["next", "Next"])
            if not nxt:
                nxt = screen.find(ids=["btn_sign", "btn_next"])
            if not nxt or not screen.tap_node(nxt):
                fail("register step1 Next not found")
                finish()
            time.sleep(3)
            # step 2: confirm creation
            conf = screen.wait_for(texts=["Confirm creation", "Create", "OK", "Done",
                                          "confirm"],
                                   ids=["btn_sign", "btn_ok"], timeout=25, poll=2)
            if conf and screen.tap_node(conf):
                time.sleep(2)
            save = screen.find(texts=["Save", "save"], ids=["btn_save"])
            if save and screen.tap_node(save):
                time.sleep(2)
            ok("register flow completed for user=%s" % user)
        else:
            fail("register entry not found on login screen")
            finish()
        if not assert_alive(adb, args.package, "after-register"):
            finish()

        print("== login with the new account ==")
        acc = screen.wait_for(ids=["editAccount", "inputAccount",
                                   "edit_password", "input_password"],
                              timeout=30, poll=2)
        if acc:
            screen.tap_node(acc)
            adb.text(user)
            pw = screen.find(ids=["editPassword", "inputPassword",
                                  "edit_password", "input_password"])
            if pw:
                screen.tap_node(pw)
                adb.text(password)
            btn = screen.find(ids=["btn_sign"], texts=["Log in"])
            if btn:
                screen.tap_node(btn)
            time.sleep(8)
        else:
            ok("no login form visible (maybe auto-logged-in after register)")

    print("== role-make screen (if shown) ==")
    time.sleep(5)
    role = screen.find(contains=["nickname", "Nickname", "role"])
    if role and role.center:
        screen.tap_node(role)
        adb.text("LocalQAPlayer")
        go = screen.find(texts=["Confirm", "OK", "Start", "Enter", "Done"])
        if go and screen.tap_node(go):
            time.sleep(3)

    print("== main screen + navigate every bottom tab ==")
    main_seen = screen.wait_for(ids=["rgBottom", "rb_1", "flHomePage"],
                                timeout=60, poll=3)
    if not main_seen:
        fail("main screen (bottom tabs) not reached")
        finish()
    ok("main screen reached")
    tabs_seen = 0
    for tab in ["rb_1", "rb_2", "rb_3", "rb_4", "rb_5"]:
        n = screen.find(ids=[tab])
        if n and n.center:
            screen.tap_node(n)
            tabs_seen += 1
            time.sleep(5)  # let the tab fire its API calls
            if not assert_alive(adb, args.package, "tab-%s" % tab):
                finish()
        else:
            print("  [skip] tab %s not in current layout" % tab)
    if tabs_seen == 0:
        fail("no bottom tabs were clickable")
    else:
        ok("navigated %d bottom tabs" % tabs_seen)

    print("== deep navigation (best-effort UI walk) ==")
    # open whatever looks like a game card / list entry, then back out
    for _ in range(3):
        n = screen.find(contains=["Start", "start", "Play", "play"])
        if not n:
            break
        screen.tap_node(n)
        time.sleep(6)
        adb.key(4)  # BACK
        time.sleep(2)
        if not assert_alive(adb, args.package, "deep-navigation"):
            finish()

    print("== local API traffic assertions (logcat) ==")
    log = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
    reqs = re.findall(r"REQ (\w+) (\S+)", log)
    unique_paths = sorted(set(p for _, p in reqs))
    print("  LocalAPI requests seen: %d (%d unique)" % (len(reqs), len(unique_paths)))
    for p in unique_paths:
        print("    - %s" % p)
    if not reqs:
        fail("embedded server saw ZERO requests — traffic left the device or server is down")
    auth_hits = [p for p in unique_paths if any(
        k in p for k in ("/login", "/register", "/visitor", "/tourist", "/auth-token"))]
    if not auth_hits:
        fail("no auth endpoint was exercised")
    else:
        ok("auth endpoints exercised: %s" % ", ".join(auth_hits))

    print("== crash scan ==")
    crash = adb.raw("logcat", "-d", "-b", "crash", timeout=60)
    fatal = adb.raw("logcat", "-d", timeout=60)
    has_fatal = ("FATAL EXCEPTION" in fatal) or ("FATAL EXCEPTION" in crash)
    anr = ("ANR in com.disabngo.blockynexus" in fatal)
    if has_fatal:
        fail("FATAL EXCEPTION in logcat")
        for line in fatal.splitlines():
            if "FATAL EXCEPTION" in line:
                print("    " + line)
    else:
        ok("no FATAL EXCEPTION")
    if anr:
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
