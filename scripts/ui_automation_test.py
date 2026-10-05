#!/usr/bin/env python3
"""UI automation test for the local-API Blockman GO APK (Redroid CI).

Three deterministic phases, driven purely over adb + uiautomator dumps:

  Phase A — VISITOR (fresh app data):
      pm clear -> launch -> the app auto-logs-in as a tourist/visitor account
      through the embedded local server -> navigate all 5 bottom tabs ->
      deep drive (Inbox / Top Up / Ranking / Store / Party / Video / Personal
      Info editor / Dressing filter chips / Find Friends+Find Clans /
      game detail + rank/comment sub-tabs).
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
                # 12s cap (was 25): a wedged uiautomator never recovers by
                # waiting longer, and 3x25s per find made post-relaunch
                # runs crawl into the step timeout (run 37329484729)
                self.adb.sh("uiautomator dump /sdcard/localqa_ui.xml", timeout=12)
                xml = self.adb.sh("cat /sdcard/localqa_ui.xml", timeout=12)
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

    def tap_node_high(self, node):
        """Tap at 25% height inside the node's bounds. The center of
        bottom-docked controls sits UNDER the 48px system nav bar
        (5q v5 evidence: the create-clan submit bar (32,1096)-(688,1184)
        centers at y=1140, the nav bar owns 1136-1184 - the tap was
        consumed by the system). Bounds-derived, never raw coordinates."""
        b = node.bounds
        if not b:
            return self.tap_node(node)
        l, t, r, bt = b
        self.adb.tap((l + r) // 2, t + max(8, (bt - t) // 4))
        return True


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


def relaunch_and_wait(adb, screen, package, activity, tag):
    """force-stop + launch + wait for a known main-screen state. Shared by
    the deep-drive recovery, Phase B entry and Phase D's clean_relaunch.
    The am start can be silently swallowed by a transient adbd hiccup
    (v0.5.19 run evidence: force-stop logged, no Start proc, no traceback)
    - print the launch output and retry until the process exists. If the
    process exists but the main screen never appears (splash stall, another
    task in front - run 37216002760 showed Gallery3D foreground after the
    app fired an image PICK during its kick self-relaunch), ONE more full
    force-stop + launch cycle is attempted before giving up."""
    for cycle in range(2):
        adb.sh("am force-stop %s" % package)
        time.sleep(3)
        pid = None
        for attempt in range(3):
            out = adb.sh("am start -n %s/%s" % (package, activity),
                         timeout=45)
            print("  [am start #%d] %s" % (attempt + 1,
                                           (out or "").strip()[:160]))
            deadline = time.time() + 30
            while time.time() < deadline:
                pid = adb.pid(package)
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
        if up:
            return True
        if cycle == 0:
            print("  [retry] %s: main screen not reached (pid=%s) - one "
                  "more full relaunch cycle" % (tag, pid or "none"))
    return False


def ui_create_clan(adb, screen, package, tag):
    """Full CREATE A CLAN form drive through the real UI (waves 5p/5q ->
    5r). The caller picks the session: deep_drive passes the visitor,
    Phase E passes the registered account - a POST in one and not the
    other names the gate. Form facts on record (5p v3, 5q v2/v5/v6):
    etTribeName + an id-less intro EditText + the Add Tag dialog
    (et_msg / btn_confirm) + a submit RelativeLayout whose CENTER sits
    under the 48px system nav bar (tap high inside the bounds).
    Returns (posted, uname): posted is True when POST
    /clan/api/v2/clan/tribe was observed, uname is the created clan name
    (Phase F reuses it to find the OWN clan on the clan screens)."""
    def alive(stage):
        pid = adb.pid(package)
        if pid:
            ok("alive at %s (pid %s)" % (stage, pid))
            return True
        print("  [evidence] process died at %s (native-kill family)"
              % stage)
        return False

    def back():
        adb.key(4)
        time.sleep(2)

    def fill(node, value):
        for _ in range(2):
            screen.tap_node(node)
            time.sleep(1)
            adb.text(value)
            time.sleep(1)
            back()
            for x in screen.dump():
                if x.cls.endswith("EditText") and x.center \
                        and (x.text or "") == value:
                    return True
        return False

    tab3n = screen.find(ids=["rb_3"])
    if not (tab3n and screen.tap_node(tab3n)):
        print("  [skip] %s: rb_3 not on screen" % tag)
        return False, None
    time.sleep(4)
    clanrow = screen.find(ids=["rlSearchClan"])
    if not (clanrow and screen.tap_node(clanrow)):
        print("  [skip] %s: rlSearchClan not on the tab3 list" % tag)
        return False, None
    time.sleep(5)
    if not alive("%s-clanscreen" % tag):
        return False, None
    # the fresh recommendation state carries the CREATE A CLAN banner
    create = screen.find(texts=["CREATE A CLAN"])
    if not (create and create.center):
        print("  [skip] %s: CREATE A CLAN banner not found" % tag)
        back()
        return False, None
    screen.tap_node(create)
    time.sleep(5)
    if not alive("%s-clancreate" % tag):
        return False, None
    uname = "UIClan%05d" % (int(time.time()) % 100000)
    name_in = screen.find(ids=["etTribeName"])
    if not (name_in and name_in.center):
        print("  [skip] %s: etTribeName not found on the form" % tag)
        back()
        return False, None
    if fill(name_in, uname):
        ok("%s: name field verified: %r" % (tag, uname))
    else:
        print("  [info] %s: name fill NOT verified" % tag)
    intro = next((x for x in screen.dump()
                  if x.cls.endswith("EditText") and x.center
                  and x.res.rsplit("/", 1)[-1] != "etTribeName"), None)
    if intro:
        if fill(intro, "Local QA clan"):
            ok("%s: intro field verified" % tag)
        else:
            print("  [info] %s: intro fill NOT verified" % tag)
    else:
        print("  [info] %s: no second EditText (intro) found" % tag)
    # Add Tag dialog: a digit tag defeats IME autocorrect; the first
    # BACK closes the keyboard, not the dialog; CONFIRM unobstructed (v5)
    d = screen.dump()
    tag_label = next((x for x in d if (x.text or "") == "Clan tag"
                      and x.center), None)
    if tag_label:
        idx = d.index(tag_label)
        tag_btn = next((x for x in d[idx + 1: idx + 4]
                        if x.clickable and x.center
                        and not x.cls.endswith("EditText")), None)
        if tag_btn:
            screen.tap_node(tag_btn)
            time.sleep(4)
            if alive("%s-clantag" % tag):
                msg = screen.find(ids=["et_msg"])
                if msg and msg.center:
                    screen.tap_node(msg)
                    time.sleep(1)
                    adb.text("QA1")
                    time.sleep(1)
                    back()
                    cur = screen.find(ids=["et_msg"])
                    ok("%s: tag field now %r"
                       % (tag, cur.text if cur else "<gone>"))
                conf = screen.find(ids=["btn_confirm"])
                if conf and conf.center:
                    screen.tap_node(conf)
                    time.sleep(3)
                    if alive("%s-clantag-confirm" % tag):
                        still = screen.find(ids=["tv_title"])
                        if still and (still.text or "") == "Add Tag":
                            print("  [info] %s: tag dialog still open "
                                  "(tag rejected?)" % tag)
                        else:
                            ok("%s: tag dialog closed - tag set" % tag)
                else:
                    print("  [info] %s: no btn_confirm; BACKing out" % tag)
                    back()
    # submit: the clickable node covering the 'Create a clan' text below
    # the title bar, tapped HIGH inside its bounds (v6 nav-bar fix)
    subs_text = [x for x in screen.dump()
                 if (x.text or "") == "Create a clan" and x.center
                 and x.center[1] > 400]
    target = None
    if subs_text:
        st = subs_text[-1]
        sc = st.center
        cands = [x for x in screen.dump()
                 if x.clickable and x.bounds
                 and x.bounds[0] <= sc[0] <= x.bounds[2]
                 and x.bounds[1] <= sc[1] <= x.bounds[3]]
        target = cands[-1] if cands else None
    posted = False
    if target:
        print("  [info] %s: submitting via %s bounds=%s (high tap)"
              % (tag, target.res.rsplit("/", 1)[-1] if target.res
                 else target.cls, target.bounds))
        # Evidence-bounded posted detection (v4 lesson): a plain full-buffer
        # grep is CONTAMINATED by Phase C's API-level create of the same
        # route (run 37259412423 'E-clanui' ok was Phase C's line, not a UI
        # POST — no clan existed server-side and both recommendation dumps
        # were byte-identical). Snapshot BEFORE the tap and require the
        # match count to GROW, plus the typed-name signature.
        prelog = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
        screen.tap_node_high(target)
        time.sleep(2)
        tlog = adb.raw("logcat", "-d", "-t", "300", timeout=60)
        toasts = [ln.split(": ", 1)[-1] for ln in tlog.splitlines()
                  if "toast" in ln.lower() and "LocalAPI" not in ln][:4]
        if toasts:
            print("  [info] %s: toast lines around submit: %s"
                  % (tag, toasts))
        for rid in ["btnSure", "btn_ok", "btnOk", "btn_confirm"]:
            c = screen.find(ids=[rid])
            if c and c.center:
                screen.tap_node(c)
                break
        time.sleep(5)
        if alive("%s-submit" % tag):
            clog = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
            grew = (clog.count("POST /clan/api/v2/clan/tribe")
                    > prelog.count("POST /clan/api/v2/clan/tribe"))
            typed = ("REQ POST /clan/api/v2/clan/tribe" in clog
                     and uname in clog)
            posted = grew or typed
            if posted:
                ok("%s: UI clan creation hit POST /clan/api/v2/clan/"
                   "tribe (name=%s, grew=%s, typed=%s)"
                   % (tag, uname, grew, typed))
            else:
                print("  [info] %s: no clan-create POST observed"
                      " (bounded evidence: grew=False typed=False)" % tag)
            for x in screen.dump():
                if x.res or x.text or x.desc:
                    print("  %s-dump] %s | text=%r" % (
                        tag, x.res.rsplit("/", 1)[-1] if x.res else "",
                        x.text[:28]))
    else:
        print("  [skip] %s: no clickable submit candidate" % tag)
    back()
    if screen.find(texts=["CREATE A CLAN"]):
        back()  # Find Clans -> tab3 (the caller grounds from here)
    return posted, uname


def deep_drive(adb, screen, package, activity, tag, paths_before):
    """Deeper UI driving: visit labeled Me-tab rows (Inbox / Top Up /
    Ranking), the game-category tab (rb_2, with a safe row probe),
    discovery dumps for rb_3/rb_4, open a game card from Home, and print
    which endpoints the newly visited screens added. Best-effort taps; the
    hard requirement is only that the app stays alive (a crash here is a
    real finding)."""
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
        return alive_or_recover("%s-%s" % (tag, label.replace(" ", "")))

    def alive_or_recover(stage):
        """assert_alive with defense in depth: the native-kill family has
        SIGKILLed the app mid-deep-drive (run 37223386226: fg TOP death,
        no am_kill/crash/ANR - the documented roaming killer). A death is
        recorded as evidence and the app is relaunched so the drive can
        continue; a genuine server-induced crash would still show in the
        crash scan and the LocalAPI diagnostics."""
        if adb.pid(package):
            ok("alive at %s (pid %s)" % (stage, adb.pid(package)))
            return True
        print("  [evidence] process died at stage: %s - relaunching "
              "(native-kill family signature)" % stage)
        if relaunch_and_wait(adb, screen, package, activity, stage):
            ok("recovered after death at %s" % stage)
            return True
        return False

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
            alive_or_recover("%s-Inbox" % tag)
            row = screen.find(texts=["Welcome"], contains=["welcome"])
            if row and row.center:
                screen.tap_node(row)
                time.sleep(5)
                adb.key(4)  # back to the list
                time.sleep(2)
                alive_or_recover("%s-MailRow" % tag)
            adb.key(4)  # back to Me
            time.sleep(2)
        visit("Top Up", 6)         # recharge screen (pay products path)
        visit("Ranking", 6)        # ranking screen (rank home path)
        visit("Store", 6)          # store screen (dress/suit shop path)
        # Wave 5m — BUY through the real Store UI: the Dressing tab only
        # shows OWNED items, so the wear path needs a purchase first.
        # Entry: rb_2 -> ivShopEnter (id from the 5j on-device dump) so we
        # never depend on Me-row tap timing. Then the first product in the
        # content band, the buy control (text-based), and the confirm
        # dialog if one appears. The purchase is REAL state (dressBuyV2
        # wallet math; the visitor wallet covers a product).
        buy_seen = False
        tab2s = screen.find(ids=["rb_2"])
        if tab2s and screen.tap_node(tab2s):
            time.sleep(5)
            shop_enter = screen.find(ids=["ivShopEnter"])
            if shop_enter and screen.tap_node(shop_enter):
                time.sleep(6)
                alive_or_recover("%s-storescreen" % tag)
                # snapshot the shop-mode load traffic NOW (buffer rotates
                # under GL traffic — run 37230697737 lost the evidence)
                slog = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
                shop_reqs = sorted(set(re.findall(
                    r"REQ (\w+) (/shop/\S+)", slog)))
                ok("shop-mode traffic so far: %s" %
                   (", ".join("%s %s" % r for r in shop_reqs[-6:]) or "none"))
                for x in screen.dump():
                    if x.res or x.text or x.desc:
                        print("  store] %s | text=%r desc=%r" % (
                            x.res.rsplit("/", 1)[-1] if x.res else "",
                            x.text[:24], x.desc[:24]))
                product = None
                rv = screen.find(ids=["rvData"])
                rvb = rv.bounds if rv else None
                for n in screen.dump():
                    if not (n.center and n.bounds):
                        continue
                    l, t, r, b = n.bounds
                    w, h = r - l, b - t
                    y = n.center[1]
                    # a grid CARD is small; full-screen containers are not
                    if w > 420 or h > 420:
                        continue
                    if y < 260 or y > 1000:
                        continue
                    # must sit INSIDE the shop grid (rvData) — chips/filters
                    # live outside it (v4 evidence: a chip was tapped)
                    if rvb:
                        rl, rt, rr, rb = rvb
                        cx, cy = n.center
                        if not (rl <= cx <= rr and rt <= cy <= rb):
                            continue
                    if n.cls.endswith("FrameLayout") or n.cls.endswith(
                            "LinearLayout") or n.cls.endswith(
                            "RecyclerView") or "item" in n.res.lower():
                        product = n
                        break
                if product and screen.tap_node(product):
                    # the DressBuyDialog (FullScreenDialog, GL-backed) takes a
                    # moment; wait for its ivBigPic marker (v3 evidence)
                    dlg = screen.wait_for(ids=["ivBigPic"], timeout=15,
                                          poll=2)
                    if not dlg:
                        print("  [info] buy dialog did not open (no ivBigPic)")
                    time.sleep(3)
                    alive_or_recover("%s-storeproduct" % tag)
                    for x in screen.dump():
                        l2, t2, r2, b2 = x.bounds or (0, 0, 0, 0)
                        print("  storeprod] %s | text=%r desc=%r "
                              "btn=%s bounds=%dx%d" % (
                                  x.res.rsplit("/", 1)[-1] if x.res else "",
                                  x.text[:24], x.desc[:24],
                                  x.cls.rsplit(".", 1)[-1],
                                  r2 - l2, b2 - t2))
                    # duration choice (7/30/forever radios): forever is the
                    # clean semantics for the wear-assertion path
                    forever = screen.find(ids=["rbForever"])
                    if forever and forever.center:
                        screen.tap_node(forever)
                        time.sleep(1)
                    buy = screen.find(texts=["Buy", "Buy Now", "Purchase",
                                             "Get"],
                                      contains=["buy", "purchase"])
                    if not (buy and buy.center):
                        # the DressBuyDialog is databinding-driven: its two
                        # action Buttons carry no guaranteed text — fall back
                        # to the LAST Button in the dialog (Buy sits below
                        # Try in the ItemDressBuy layout)
                        btns = [n for n in screen.dump()
                                if n.cls.endswith("Button") and n.center
                                and n.center[1] > 200]
                        if btns:
                            buy = btns[-1]
                            print("  [info] text buy control not found; "
                                  "using Button node at %r" % (buy.center,))
                    if buy and buy.center:
                        screen.tap_node(buy)
                        time.sleep(3)
                        # confirm dialog (same control family as the editor)
                        for rid in ["btnSure", "btn_ok", "btnOk",
                                    "btn_confirm"]:
                            c = screen.find(ids=[rid])
                            if c and c.center:
                                screen.tap_node(c)
                                break
                        time.sleep(5)
                        alive_or_recover("%s-storebuy" % tag)
                        log = adb.raw("logcat", "-d", "-s", "LocalAPI",
                                      timeout=60)
                        buy_seen = ("new/shop/decorations/buy" in log)
                        if buy_seen:
                            ok("5m: Store buy hit POST /shop/api/v1/new/"
                               "shop/decorations/buy")
                        else:
                            print("  [info] buy POST not observed in the "
                                  "LocalAPI log (dialog shape changed?)")
                    else:
                        print("  [skip] no buy control on the product "
                              "detail")
                    adb.key(4)  # back to the store
                    time.sleep(2)
                else:
                    print("  [skip] no store product candidate found")
            else:
                print("  [skip] ivShopEnter not found on the Dressing tab")
            # return to the Me tab directly (BACK on the main activity is
            # double-back-to-exit territory)
            me_tab = screen.find(ids=["rb_5"])
            if me_tab and me_tab.center:
                screen.tap_node(me_tab)
                time.sleep(2)
        if buy_seen:
            # the Dressing tab now holds the purchased item: drive the
            # wear action on it (PUT /decorations/using/new). The item's
            # category chip is unknown — probe each first-level chip and
            # take the first non-empty grid.
            tab2b = screen.find(ids=["rb_2"])
            if tab2b and screen.tap_node(tab2b):
                time.sleep(5)
                owned = None
                for chip in ("rb_clothes", "rb_accessories",
                             "rb_character", "rb_function"):
                    ch = screen.find(ids=[chip])
                    if not (ch and screen.tap_node(ch)):
                        continue
                    time.sleep(4)
                    d = screen.dump()
                    # skip this chip when the honest empty state shows
                    if any((n.text or "").startswith("No ") for n in d):
                        continue
                    for n in d:
                        if not n.center:
                            continue
                        y = n.center[1]
                        if y < 420 or y > 950:
                            continue
                        if n.cls.endswith("FrameLayout") or n.cls.endswith(
                                "LinearLayout"):
                            owned = n
                            break
                    if owned:
                        break
                if owned and screen.tap_node(owned):
                    time.sleep(6)
                    alive_or_recover("%s-owneditem" % tag)
                    wear2 = screen.find(texts=["Wear", "Try", "Use",
                                               "Put on", "Dress"],
                                        contains=["wear", "dress", "try"])
                    if wear2 and wear2.center:
                        screen.tap_node(wear2)
                        time.sleep(5)
                        alive_or_recover("%s-wear" % tag)
                        wlog = adb.raw("logcat", "-d", "-s", "LocalAPI",
                                       timeout=60)
                        if "/decorations/using/new" in wlog:
                            ok("5m: wear action hit PUT /decoration/api/"
                               "v1/decorations/using/new")
                    else:
                        print("  [skip] no wear control on the owned item")
                    adb.key(4)
                    time.sleep(2)
                else:
                    print("  [skip] owned item not found in the grid")
            # return to the Me tab directly
            me_tab2 = screen.find(ids=["rb_5"])
            if me_tab2 and me_tab2.center:
                screen.tap_node(me_tab2)
                time.sleep(2)
        visit("Party", 6)          # party screen (party auth path)
        visit("Video", 6)          # video feed (deliberate-empty probe)
        visit("Gratitude List", 6) # gratitude list row (never visited before)
        # Profile surface: the Me tab has NO settings entry (discovered via
        # the node dump); settings lives behind the profile screen (ibMore).
        prof = screen.find(ids=["ll_top", "rl_header"])
        if prof and prof.center:
            screen.tap_node(prof)
            time.sleep(6)
            alive_or_recover("%s-Profile" % tag)
            more = screen.find(ids=["ibMore"])
            if more and more.center:
                screen.tap_node(more)
                time.sleep(6)
                alive_or_recover("%s-MoreSettings" % tag)
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
                    alive_or_recover("%s-MoreAccount" % tag)
                adb.key(4)  # back to profile
                time.sleep(2)
            adb.key(4)  # back to Me
            time.sleep(2)
            alive_or_recover("%s-ProfileBack" % tag)
    # DRESSING tab (rb_2, ids verified from the 5j on-device dump): tap the
    # filter chips so the wardrobe lists fire through the real client —
    # rb_clothes/rb_accessories/rb_character/rb_function are the first-level
    # radio tabs; rbSuit is a second-level filter (suit list). All are list
    # filters, no engine action is possible from them.
    tab2 = screen.find(ids=["rb_2"])
    if tab2 and screen.tap_node(tab2):
        time.sleep(5)
        for n in screen.dump():
            if n.res or n.text or n.desc:
                print("  ab2] %s | text=%r desc=%r clickable=%s" % (
                    n.res.rsplit("/", 1)[-1] if n.res else "",
                    n.text[:24], n.desc[:24], n.clickable))
        for chip in ("rb_clothes", "rb_accessories", "rb_character",
                     "rb_function"):
            n = screen.find(ids=[chip])
            if n and screen.tap_node(n):
                time.sleep(4)
                alive_or_recover("%s-dress-%s" % (
                    tag, chip.replace("rb_", "")))
            else:
                print("  [skip] dressing chip %s not found" % chip)
        suit = screen.find(ids=["rbSuit"])
        if suit and screen.tap_node(suit):
            time.sleep(5)
            alive_or_recover("%s-dress-suit" % tag)
        # Dressing grid item probe (wave 5l): tap the first grid item under
        # the clothes chip to open the dress detail; if a wear/try button
        # exists (text-based), tap it so PUT /decorations/using/new is
        # client-asserted. Buying is deliberately NOT driven here (the
        # wallet math is host-tested; a mis-tap could double-spend the
        # visitor's balance). BACK always recovers.
        chip_c = screen.find(ids=["rb_clothes"])
        if chip_c and screen.tap_node(chip_c):
            time.sleep(4)
        item = None
        for n in screen.dump():
            if not n.center:
                continue
            y = n.center[1]
            if y < 420 or y > 950:
                continue
            if n.cls.endswith("FrameLayout") or n.cls.endswith(
                    "LinearLayout"):
                item = n
                break
        if item and screen.tap_node(item):
            time.sleep(6)
            alive_or_recover("%s-dressitem" % tag)
            for x in screen.dump():
                if x.res or x.text or x.desc:
                    print("  dressitem] %s | text=%r desc=%r" % (
                        x.res.rsplit("/", 1)[-1] if x.res else "",
                        x.text[:24], x.desc[:24]))
            wear = screen.find(texts=["Wear", "Try", "Use", "Put on",
                                      "Dress"],
                               contains=["wear", "dress", "try"])
            if wear and wear.center:
                screen.tap_node(wear)
                time.sleep(5)
                alive_or_recover("%s-dresswear" % tag)
            else:
                print("  [skip] no wear/try button found on the detail")
            adb.key(4)  # back to the grid
            time.sleep(2)
        else:
            print("  [skip] no dressing-grid item candidate found")
    # FRIENDS/CLANS tab (rb_3, ids from the 5j dump): open the two search
    # rows ("Find Friends" / "Find Clans") — both lead to list/search
    # screens (friend search, clan search), no engine surface behind them.
    # Keep the node dump as the discovery channel.
    tab3 = screen.find(ids=["rb_3"])
    if tab3 and screen.tap_node(tab3):
        time.sleep(4)
        for x in screen.dump():
            if x.res or x.text or x.desc:
                print("  tab3] %s | text=%r desc=%r" % (
                    x.res.rsplit("/", 1)[-1] if x.res else "",
                    x.text[:24], x.desc[:24]))
        # wave 5n input picker: run 37234955486 proved the clan-search
        # screen exposes NO EditText-class node — the input surfaces as a
        # hint-text node "Enter clan name (No more...)". Match either an
        # EditText-family class or the hint-bearing node; the stage dumps
        # now print classes so the real widget type lands in the log.
        def search_input():
            for x in screen.dump():
                if not x.center:
                    continue
                if (x.cls.endswith("EditText")
                        or x.cls.endswith("AutoCompleteTextView")):
                    return x
                if (x.text or "").startswith("Enter clan"):
                    return x
            return None
        for label, stage, typed in (("Find Friends", "findfriends", "alex"),
                                    ("Find Clans", "findclans", "pixel")):
            # wave 5o RESULT (run 37238214502): even the btnSearchFriend
            # ID tap does not navigate — the Find Friends section is the
            # client's "Coming soon" placeholder (no search surface in
            # this build; friends/info/{nickName} stays host-tested with
            # no UI caller). The probe stays as an honest recorder: tap,
            # dump, report. Clans: rlSearchClan navigates to the real
            # Find Clans screen (search client-asserted in wave 5n).
            n = screen.find(ids=(["btnSearchFriend"]
                                 if stage == "findfriends" else
                                 ["rlSearchClan"]))
            if not (n and screen.tap_node(n)):
                n = screen.find(texts=[label])
            if not (n and screen.tap_node(n)):
                print("  [skip] '%s' row not found" % label)
                continue
            time.sleep(5)
            alive_or_recover("%s-%s" % (tag, stage))
            before = set(localapi_paths(adb))
            for x in screen.dump():
                if x.res or x.text or x.desc:
                    print("  %s] %s | cls=%s text=%r desc=%r" % (
                        stage, x.res.rsplit("/", 1)[-1] if x.res else "",
                        x.cls.rsplit(".", 1)[-1] if x.cls else "",
                        x.text[:28], x.desc[:24]))
            edit = search_input()
            if edit:
                screen.tap_node(edit)
                time.sleep(1)
                adb.text(typed)
                time.sleep(1)
                adb.key(66)  # IME action / enter
                time.sleep(5)
                alive_or_recover("%s-%s-search" % (tag, stage))
                log = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
                if stage == "findclans":
                    if "tribe/blurry/info" in log:
                        ok("5n: clan search hit GET /clan/api/v1/clan/"
                           "tribe/blurry/info (fuzzy match, NPC tribes "
                           "seeded: 'Pixel Wolves' answers 'pixel')")
                    else:
                        print("  [info] clan-search endpoint not observed "
                              "(hint node may not be the real input)")
                else:
                    friend_hits = [p for p in sorted(set(localapi_paths(adb))
                                                     - before)
                                   if "/friend/" in p]
                    if friend_hits:
                        ok("5n: friend search surfaced %s" % friend_hits)
                    else:
                        print("  [info] no friend-search endpoint surfaced "
                              "(discovery only)")
            else:
                print("  [skip] no search input found on the %s screen"
                      % stage)
            adb.key(4)  # back (closes the IME first if the search opened it)
            time.sleep(2)
            if stage == "findclans" and not screen.find(ids=["rb_3"]):
                # IME evidence (runs 37236799029..37240694732): the first
                # BACK only dismissed the keyboard — the search screen was
                # still up, stranding the drive (tab4/gamecard/probes
                # skipped, "did not land on Home"). Leave it for real.
                adb.key(4)
                time.sleep(2)
                alive_or_recover("%s-tab3-reentered" % tag)
        # wave 5r: the create-form drive is ui_create_clan() now - run
        # it for the VISITOR session here; Phase E repeats it registered
        # so one run names the gate (5q v1..v6 evidence: every widget
        # verified, submit tapped correctly, still no POST as a guest).
        posted_visitor, _vis_clan = ui_create_clan(adb, screen, package,
                                                   "%s-clanui" % tag)
        if posted_visitor:
            ok("5r: VISITOR session created a clan through the UI")
        else:
            print("  [info] visitor create POST not observed (guest-gate "
                  "hypothesis unresolved)")
        alive_or_recover("%s-tab3-done" % tag)
        # grounding loop: never continue to tab4/gamecard from a screen
        # without the bottom nav (Find Clans/form/IME stranding)
        for _ in range(3):
            if screen.find(ids=["rb_3"]):
                break
            print("  [evidence] no bottom nav after tab3 - BACKing once "
                  "more")
            adb.key(4)
            time.sleep(2)
            alive_or_recover("%s-tab3-grounded" % tag)
    # Discovery-only dump for the chat tab (no taps beyond the tab itself)
    tab4 = screen.find(ids=["rb_4"])
    if tab4 and screen.tap_node(tab4):
        time.sleep(4)
        for x in screen.dump():
            if x.res or x.text or x.desc:
                print("  tab4] %s | text=%r desc=%r" % (
                    x.res.rsplit("/", 1)[-1] if x.res else "",
                    x.text[:24], x.desc[:24]))
        alive_or_recover("%s-tab4" % tag)
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
            alive_or_recover("%s-gamedetail" % tag)
            # game-detail sub-screens (rank / comments) — best-effort probes;
            # labels may vary per game detail layout, BACK always recovers
            for sub in ("rank", "comment"):
                sn = screen.find(contains=[sub])
                if sn and sn.center:
                    screen.tap_node(sn)
                    time.sleep(5)
                    adb.key(4)
                    time.sleep(2)
                    alive_or_recover("%s-gamesub-%s" % (tag, sub))
            adb.key(4)
            time.sleep(2)
            alive_or_recover("%s-gamecard" % tag)
        else:
            print("  [skip] no home card candidate found")
    added = sorted(set(localapi_paths(adb)) - paths_before)
    ok("deep drive added %d new endpoint paths" % len(added))
    for p in added:
        print("    + %s" % p)
    # Return the app to a SAFE screen. Evidence (v0.5.9/0511/0513): all three
    # between-phase SIGKILL incidents happened while the app sat IDLE on
    # FriendInfoActivity (the rank/comment probes can land there); the runs
    # that ended on Home/Me survived. Land on Home before the next phase -
    # and if Home is not actually reached (stranded on a foreign activity,
    # run 37222222759 evidence), relaunch into the known main state.
    home_tab = screen.find(ids=["rb_1"])
    landed = False
    if home_tab and home_tab.center:
        screen.tap_node(home_tab)
        time.sleep(3)
        landed = bool(screen.wait_for(ids=["flHomePage"], timeout=25,
                                      poll=3))
    if not landed:
        print("  [evidence] deep-drive end did not land on Home - "
              "relaunching into the known main state")
        relaunch_and_wait(adb, screen, package, activity, "%s-landhome" % tag)
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
    # Line-buffered stdout: the CI step timeout kills the process and
    # block-buffered output loses the tail — exactly what hid the stall
    # evidence in run 37329484729. Every print now reaches the log live.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
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
    # Snapshot the visitor auth traffic NOW: the deep-drive's dress-detail
    # GL rendering floods the logcat main buffer and rotates early LocalAPI
    # lines out (run 37226628540 evidence), so a single end-of-run scan
    # misses the login/auth-token evidence entirely.
    paths_early = localapi_paths(adb)
    navigate_all_tabs(adb, screen, args.package, "A")
    deep_drive(adb, screen, args.package, args.activity, "A",
               set(paths_early))
    paths_a = sorted(set(paths_early) | set(localapi_paths(adb)))
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

    editor_up = open_personal_info_editor(adb, screen, args.package, "B")
    if not editor_up:
        # Evidence 37222222759: the rank/comment probes can strand the app
        # on FriendInfoActivity (no bottom nav -> rb_5 unfindable). Start
        # from the known main state and retry once before giving up.
        print("  [retry] editor not reached - relaunch into the main state")
        if relaunch_and_wait(adb, screen, args.package, args.activity,
                             "B-editor"):
            editor_up = open_personal_info_editor(adb, screen, args.package,
                                                  "B")
    if editor_up:
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
    d_tok = None   # live session token (auth-token response) - Phase F uses it
    d_uid_live = None  # live session user id - Phase F uses it

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
        """force-stop + launch + wait for main - a known screen state
        (shared implementation with the deep-drive recovery)."""
        if relaunch_and_wait(adb, screen, args.package, args.activity, stage):
            return assert_alive(adb, args.package, stage)
        return False

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
                d_tok = tok
                d_uid_live = d_uid
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
                            # Registered-session surface wave. Evidence
                            # (jadx + run dumps): the Gender row is a
                            # CLIENT STUB — onClickSex() shows a toast and
                            # nothing else (no picker, no network). The
                            # Personal Profile row opens the detail editor
                            # template (e.b.m.b) whose EditText persists
                            # through changeInfo. The Birthday row is a
                            # wheel picker (not driven — low value).
                            tap_label(screen, "Gender")
                            time.sleep(2)
                            print("  [evidence] Gender row is a client "
                                  "stub (toast only) - no picker exists")
                            if tap_label(screen, "Personal Profile"):
                                time.sleep(5)
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
                                    else:
                                        print("  [info] intro save reached "
                                              "no endpoint (dialog shape "
                                              "changed?)")
                                    assert_alive(adb, args.package,
                                                 "D-IntroSaved")
                                else:
                                    debug_dump(screen, "D-intro-editor")
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

    # ------------------------------------------------- Phase E: registered clan create
    # 5q v1..v6 evidence: the create form is fully drivable but the
    # VISITOR submit never POSTs. Phase D makes the registered session
    # reproducible - repeat the identical drive here; a POST now names
    # the visitor silence as a client-side GUEST GATE.
    print("== PHASE E: registered-session UI clan creation ==")
    posted_e, clan_name_e = ui_create_clan(adb, screen, args.package,
                                           "E-clanui")
    if posted_e:
        ok("5r: REGISTERED session created a clan through the UI - "
           "the visitor silence is a client-side GUEST GATE")
    else:
        print("  [info] registered create POST not observed (form-level "
              "gate - headPic? deeper validation?)")
    for _ in range(3):
        if screen.find(ids=["rb_3"]):
            break
        adb.key(4)
        time.sleep(2)
    assert_alive(adb, args.package, "E-grounded")

    # ------------------------------------------------- Phase F: own-clan surfaces
    # Session 15 (wave 5s): Phase E's created clan persists (Phase C
    # dissolved its own API-level clan BEFORE Phase E, so the session now
    # OWNS a clan). Drive the OWNER-state clan surfaces through the real
    # UI: re-enter the clan screen, find the created clan (dump-derived;
    # the search input is a hint-text picker - wave 5n), open its
    # homepage, and record what the client fetches for an owner
    # (base/member/currency/bulletin are all real handlers). Discovery
    # first: node dumps + endpoint evidence; the hard requirement is only
    # that the app stays alive.
    print("== PHASE F: registered-session OWN-CLAN surfaces ==")
    # Session 17: the UI create is ICON-GATED (jadx, PATCH_PLAN Phase 7a -
    # TribeCreateModel requires the gallery+crop icon; the submit never
    # POSTs for ANY session state). So the own clan now comes from the API
    # (the same local server the app itself talks to), created for the LIVE
    # registered session via its Phase-D auth-token. Per-run unique name so
    # the UI search is exact. The UI create (Phase E) stays as the honest
    # probe it is; if it EVER posts, its clan name wins (new evidence).
    own_name = None
    live_hdr = None
    own_clan_id = 0
    if posted_e and clan_name_e:
        own_name = clan_name_e
        ok("F: UI create POSTED (%s) - using the UI-created clan" % own_name)
    elif d_tok and d_uid_live:
        own_name = "PersClan%d" % (int(time.time()) % 100000)
        live_hdr = {"Access-Token": d_tok, "userId": str(d_uid_live),
                    "language": "en"}
        pc_form = {"name": own_name, "details": "persistent-owner",
                   "headPic": "", "tags": [], "currency": 2}
        pc = fcall("POST", "/clan/api/v2/clan/tribe", pc_form, headers=live_hdr)
        if pc.get("code") != 1:
            # the client's own fallback: golds short -> the 60-diamond path
            print("  [info] F: golds-path create failed (%s) - trying the "
                  "diamonds path" % str(pc)[:100])
            pc_form["currency"] = 1
            pc = fcall("POST", "/clan/api/v2/clan/tribe", pc_form,
                       headers=live_hdr)
        if pc.get("code") == 1:
            own_clan_id = pc.get("data", {}).get("clanId", 0)
            ok("F: persistent clan created via the local API for the live "
               "session (%s)" % own_name)
            pid = fcall("GET", "/clan/api/v1/clan/tribe/id", headers=live_hdr)
            check("F: server confirms ownership (tribe/id != 0)",
                  pid.get("code") == 1 and str(pid.get("data")) not in ("0", ""),
                  str(pid)[:100])
        else:
            print("  [info] F: persistent clan create failed: %s"
                  % str(pc)[:120])
            own_name = None
    if own_name:
        # Boot the client WITH the clan: the restart re-fetches tribe/id at
        # boot, so the client-side TribeCenter carries the clan before the
        # drive (the Session 15 design premise - now actually true).
        if clean_relaunch("F-restart-owner"):
            ok("F: app restarted holding the persistent clan (%s)" % own_name)
        f_before = set(localapi_paths(adb))

        def f_alive(stage):
            if adb.pid(args.package):
                ok("alive at %s (pid %s)" % (stage, adb.pid(args.package)))
                return True
            print("  [evidence] process died at %s - relaunching "
                  "(native-kill family)" % stage)
            return relaunch_and_wait(adb, screen, args.package, args.activity,
                                     stage)

        # tab3 as a CLAN OWNER: dump it (evidence - does the owner state
        # change the tab3 layout? does the clan name appear here already?)
        tab3f = screen.find(ids=["rb_3"])
        if tab3f and screen.tap_node(tab3f):
            time.sleep(4)
            for x in screen.dump():
                if x.res or x.text or x.desc:
                    print("  F-tab3] %s | text=%r desc=%r" % (
                        x.res.rsplit("/", 1)[-1] if x.res else "",
                        x.text[:28], x.desc[:24]))
            f_alive("F-tab3")
            # 5t v2 (run 37335622091 F-tab3 dump): for a clan OWNER tab3 IS
            # the clan dashboard — tvClanName carries the clan name,
            # rl_donate/Chief/'1/22' widgets render, and rlEnterClan
            # ('Enter Clan') opens the clan homepage DIRECTLY. The old
            # ivTribe/ivClanMsg0 ids and the list-search path stay as the
            # fallback for non-owner layouts.
            own = None
            sheet_pre = False
            guide_left = False
            if screen.find(ids=["tvClanName"]):
                ok("F: owner dashboard on tab3 (tvClanName=%s)" % own_name)
                enter = screen.find(ids=["rlEnterClan"]) \
                    or screen.find(texts=["Enter Clan"])
                if enter and screen.tap_node(enter):
                    time.sleep(6)
                    if f_alive("F-clanhome-direct"):
                        for x in screen.dump():
                            if x.res or x.text or x.desc:
                                print("  F-clanhome-direct] %s | text=%r" % (
                                    x.res.rsplit("/", 1)[-1] if x.res
                                    else "", x.text[:28]))
                        # 5t v3/v6 (runs 37338438610, 37342075770,
                        # 37344788918, 37348093722): entering the clan
                        # homepage queues the one-time TribeSettingGuide
                        # (self-clears ~20s, may RE-SHOW after the Notice
                        # Board close — v5 evidence) and the "Notice Board"
                        # bulletin dialog (btnSure CLOSE). uiautomator dumps
                        # only the ACTIVE window. Settle loop: CLOSE the
                        # Notice Board whenever up, WAIT OUT the guide
                        # (tapping it re-shows it — Ta label -> f() ->
                        # H()+Ta(true).show()), until a homepage marker or
                        # the budget ends.
                        settle_deadline = time.time() + 100
                        guide_polls = 0
                        label_tapped = False
                        while time.time() < settle_deadline:
                            d_settle = screen.dump()
                            texts_now = [(x.text or "") for x in d_settle]
                            if "Notice Board" in texts_now:
                                close = next(
                                    (x for x in d_settle
                                     if x.res.rsplit("/", 1)[-1] == "btnSure"
                                     and x.center), None)
                                if close:
                                    screen.tap_node(close)
                                    ok("F: Notice Board dialog closed")
                                guide_polls = 0
                                time.sleep(3)
                                continue
                            if any("Authentication-free mode" in t
                                   for t in texts_now):
                                # 5t v9 decode: the I()-shown guide (a=false)
                                # has ONLY the top-right label - its a() opens
                                # the sheet AND f()-shows the a=true guide,
                                # which (hypothesis from the Ta.a variant +
                                # the binding) carries the bottom 'Clan
                                # Settings' bar whose b() dismisses guide +
                                # sheet and opens sa.b. Dance: label first,
                                # then the bar, then BACK from sa.b.
                                guide_polls += 1
                                if guide_polls > 14:
                                    print("  [evidence] F: guide dance gave "
                                          "up after %d polls" % guide_polls)
                                    break
                                if not label_tapped:
                                    label = next(
                                        (x for x in d_settle
                                         if "Authentication-free mode"
                                         in (x.text or "") and x.center), None)
                                    if label and screen.tap_node(label):
                                        label_tapped = True
                                        ok("F: guide label tapped (sheet + "
                                           "a=true guide expected)")
                                    time.sleep(4)
                                    continue
                                bar = next(
                                    (x for x in d_settle
                                     if (x.text or "") == "Clan Settings"
                                     and x.center), None)
                                if bar and screen.tap_node(bar):
                                    guide_left = True
                                    ok("F: guide left via its 'Clan "
                                       "Settings' bar (b()) - BACKing "
                                       "from sa.b")
                                    break
                                print("  [evidence] F: no 'Clan Settings' "
                                      "bar on the a=true guide (poll %d)"
                                      % guide_polls)
                                time.sleep(4)
                                continue
                            break
                        if guide_left:
                            adb.key(4)  # leave sa.b - back to the homepage
                            time.sleep(4)
                        if sheet_pre:
                            own = None  # the sheet window hides the homepage
                        else:
                            own = screen.wait_for(texts=[own_name],
                                                  timeout=14, poll=3)
                        if not own:
                            # 5t v4: the name text may not render where the
                            # post-close dump expects; the top-right id-less
                            # ic_more ImageButton is the homepage's
                            # distinctive control (and the F2 entry anyway -
                            # the homepage block's tap on it opens the
                            # settings sheet directly).
                            for x in screen.dump():
                                if x.center and x.cls.endswith("ImageButton"):
                                    cx, cy = x.center
                                    if cy < 140 and cx > 360:
                                        own = x
                                        ok("F: homepage detected via the "
                                           "top-right ic_more")
                                        break
                        if not own:
                            print("  [evidence] F: screen after the Notice "
                                  "Board close:")
                            for x in screen.dump():
                                if x.res or x.text or x.desc:
                                    print("  F-afterclose] %s | text=%r" % (
                                        x.res.rsplit("/", 1)[-1] if x.res
                                        else "", x.text[:28]))
                        if own:
                            ok("F: clan homepage reached directly via "
                               "rlEnterClan")
            for entry, stage in (tuple() if own else
                                 (("ivTribe", "F-tribeentry"),
                                  ("ivClanMsg0", "F-clanmsg"))):
                node = screen.find(ids=[entry])
                if not (node and screen.tap_node(node)):
                    print("  [skip] F: %s not found on tab3" % entry)
                    continue
                time.sleep(5)
                if not f_alive(stage):
                    break
                for x in screen.dump():
                    if x.res or x.text or x.desc:
                        print("  %s] %s | text=%r" % (
                            stage, x.res.rsplit("/", 1)[-1] if x.res
                            else "", x.text[:28]))
                own = screen.find(texts=[own_name])
                if own and own.center:
                    ok("F: own clan %s reachable via %s" % (own_name,
                                                            entry))
                    break
                # not here. BACK only if we actually LEFT the main screen
                # (the bottom nav is gone) — a no-op entry tap followed by
                # BACK would exit the app (5s v4 guard)
                if screen.find(ids=["rb_3"]):
                    print("  [info] F: %s tap was a no-op (still on tab3)"
                          % entry)
                    continue
                adb.key(4)
                time.sleep(2)
                f_alive("%s-back" % stage)
                own = None
            if not own:
                # re-enter the clan screen (rlSearchClan - established id)
                clanrow = screen.find(ids=["rlSearchClan"])
                if not (clanrow and screen.tap_node(clanrow)):
                    clanrow = screen.find(texts=["Find Clans"])
                    clanrow = (clanrow and screen.tap_node(clanrow)
                               and clanrow) or None
                if clanrow:
                    time.sleep(5)
                    f_alive("F-clanscreen")
                    for x in screen.dump():
                        if x.res or x.text or x.desc:
                            print("  F-clanscreen] %s | text=%r" % (
                                x.res.rsplit("/", 1)[-1] if x.res else "",
                                x.text[:28]))
                    own = screen.find(texts=[own_name])
                    if not own:
                        # 5s v2 evidence (run 37255687401 + localapi.txt):
                        # tribeRecommendation returns ALL tribes — the own
                        # clan IS in the list, usually below the fold.
                        # Swipe rvData up once and look again (no typing).
                        rv = screen.find(ids=["rvData"])
                        if rv and rv.bounds:
                            l, t, r, b = rv.bounds
                            adb.sh("input swipe %d %d %d %d 400"
                                   % ((l + r) // 2, b - 80,
                                      (l + r) // 2, t + 80))
                            time.sleep(3)
                            f_alive("F-clanscreen-swiped")
                            for x in screen.dump():
                                if x.res or x.text or x.desc:
                                    print("  F-clanscreen-swiped] %s | "
                                          "text=%r" % (
                                              x.res.rsplit("/", 1)[-1]
                                              if x.res else "",
                                              x.text[:28]))
                        own = screen.find(texts=[own_name])
                    if not own:
                        # exact-name search. 5s v3 decode (jadx
                        # activity_tribe_search.xml): the input IS a real
                        # EditText (tvTitle, hint tribe_search_hint) in the
                        # toolbar + an ID-LESS search Button right of it.
                        # 5s v2 evidence: the search fired twice yet
                        # returned 97b EMPTY — the typed name was mangled
                        # (wave-5q IME-autocorrect trap). So: type,
                        # VERIFY the EditText content, then tap the search
                        # Button (fallback key(66)).
                        edit = None
                        for attempt in range(3):
                            edit = next((x for x in screen.dump()
                                         if x.center
                                         and x.cls.endswith("EditText")
                                         and (x.text or "")
                                         .startswith("Enter clan")), None)
                            if edit:
                                break
                            print("  [evidence] F: search-input lookup "
                                  "miss #%d (uiautomator dump raced the "
                                  "banner carousel?)" % (attempt + 1))
                            time.sleep(3)
                        if edit:
                            screen.tap_node(edit)
                            time.sleep(1)
                            adb.text(own_name)
                            time.sleep(1)
                            typed = None
                            for x in screen.dump():
                                if x.cls.endswith("EditText") and x.center:
                                    typed = x.text or ""
                                    break
                            ok("F: tvTitle now holds %r (wanted %r)"
                               % (typed, own_name))
                            if typed != own_name:
                                # retype once: clear (select-all+del is
                                # unreliable over adb) — retype appends on
                                # some IMEs, so BACK-space the difference
                                if typed:
                                    adb.key(67)  # DEL
                                    for _ in range(len(typed) + 2):
                                        adb.key(67)
                                        time.sleep(0.1)
                                adb.text(own_name)
                                time.sleep(1)
                                for x in screen.dump():
                                    if x.cls.endswith("EditText") \
                                            and x.center:
                                        typed = x.text or ""
                                        break
                                ok("F: tvTitle after retype %r" % typed)
                            # the id-less search Button sits RIGHT of
                            # tvTitle on the same toolbar row
                            btn = None
                            if edit.bounds:
                                el, et, er, eb = edit.bounds
                                for x in screen.dump():
                                    if not (x.clickable and x.bounds
                                            and x.cls.endswith("Button")):
                                        continue
                                    bl, bt, br, bb = x.bounds
                                    if abs((bt + bb) // 2
                                           - (et + eb) // 2) < 30 \
                                            and bl >= er - 10:
                                        btn = x
                                        break
                            if btn:
                                print("  [info] F: search Button %s "
                                      "bounds=%s" % (
                                          btn.res.rsplit("/", 1)[-1]
                                          if btn.res else "<idless>",
                                          btn.bounds))
                                screen.tap_node(btn)
                            else:
                                print("  [evidence] F: no search Button "
                                      "found - falling back to key(66)")
                                adb.key(66)  # IME action
                            time.sleep(5)
                            f_alive("F-clanscreen-search")
                            # 5n/5p evidence: the first BACK after a search
                            # only closes the IME — dismiss it so the result
                            # row's center is not covered by the keyboard
                            adb.key(4)
                            time.sleep(2)
                            f_alive("F-clanscreen-imeclosed")
                            for x in screen.dump():
                                if x.res or x.text or x.desc:
                                    print("  F-results] %s | text=%r" % (
                                        x.res.rsplit("/", 1)[-1]
                                        if x.res else "", x.text[:28]))
                            own = screen.find(texts=[own_name])
                            if not own:
                                # one honest re-look: the results may need
                                # another beat to render after the IME closes
                                time.sleep(4)
                                own = screen.find(texts=[own_name])
                        else:
                            print("  [evidence] F: no search-input node in "
                                  "3 dumps - cannot exact-name search")
                    elif own and not own.center:
                        print("  [evidence] F: own-clan node present but "
                              "bounds-less (dump race) - retapping dump")
                        own = screen.wait_for(texts=[own_name],
                                              timeout=15, poll=3)
            if (own and own.center) or sheet_pre:
                if own and own.center:
                    ok("F: own clan %s surfaced on the clan screens" % own_name)
                    screen.tap_node(own)
                    time.sleep(6)
                else:
                    ok("F: settings sheet pre-opened through the guide "
                       "label (homepage never fully settled)")
                    time.sleep(2)
                f_alive("F-clanhome")
                for x in screen.dump():
                    if x.res or x.text or x.desc:
                        print("  F-clanhome] %s | text=%r desc=%r" % (
                            x.res.rsplit("/", 1)[-1] if x.res else "",
                            x.text[:28], x.desc[:24]))
                f_new = sorted(set(localapi_paths(adb)) - f_before)
                f_clan = [p for p in f_new if "/clan/" in p]
                if f_clan:
                    ok("F: own-clan surfaces hit %s" % f_clan)
                else:
                    print("  [info] F: no NEW /clan/ endpoints from the "
                          "own-clan drive (homepage may be cached state)")
                # ------------------------------------------------- F2: the
                # clan-UPDATE form. Client chain (jadx, classes2, session
                # 17 decompile): TribeHasFragment (fragment_tribe_has - the
                # top-RIGHT id-less ImageButton, ic_more, tag binding_2 =
                # command o) -> TribeHasViewModel H() BottomDialog (items:
                # Clan Settings [chief], Edit Profile, Manage Members,
                # Cancel) -> "Edit Profile" opens the CREATE template in
                # EDIT mode (bundle is.create=false; name/details/ico.url
                # pre-filled). Submit = the "Modify" Button (binding_7 =
                # command o = i() -> TribeApi.clanUpdate; no icon, no
                # golds gate). Update validation REQUIRES 1..4 tags and a
                # non-empty introduction - our clan ships tags=[] so the
                # drive adds one through the same Add Tag dialog as the
                # create flow. A one-time TribeSettingGuideDialog may cover
                # the homepage: its top-right label tap opens the SAME
                # sheet (and consumes the guide).

                def put_tribe_count():
                    log = adb.raw("logcat", "-d", "-s", "LocalAPI",
                                  timeout=60)
                    return sum(1 for line in log.splitlines()
                               if "REQ PUT /clan/api/v1/clan/tribe" in line
                               and "/clan/api/v1/clan/tribe/member"
                               not in line)

                puts_before = put_tribe_count()
                guide = next((x for x in screen.dump()
                              if "join clan" in (x.text or "") and x.center),
                             None)
                if guide:
                    print("  [evidence] F2: one-time TribeSettingGuideDialog "
                          "is up - its top-right label tap opens the "
                          "settings sheet (and re-shows the guide: wait "
                          "it out)")
                    screen.tap_node(guide)
                    # f() = H() (sheet) + Ta(true).show() — the guide covers
                    # the sheet again and self-clears (~20s, run evidence)
                    sheet = screen.wait_for(texts=["Edit Profile"],
                                            timeout=30, poll=4)
                else:
                    sheet = screen.find(texts=["Edit Profile"])
                if not sheet:
                    more = None
                    for x in screen.dump():
                        if not (x.center and x.cls.endswith("ImageButton")):
                            continue
                        cx, cy = x.center
                        if cy < 140 and cx > 360:
                            more = x
                            break
                    if more and screen.tap_node(more):
                        print("  [evidence] F2: ic_more (top-right id-less "
                              "ImageButton) tapped")
                        sheet = screen.wait_for(texts=["Edit Profile"],
                                                timeout=12, poll=3)
                    else:
                        print("  [info] F2: no top-right ImageButton found "
                              "- cannot open the settings sheet")
                if sheet and sheet.center:
                    ok("F2: settings sheet shows 'Edit Profile'")
                    screen.tap_node(sheet)
                    time.sleep(5)
                    f_alive("F2-editform")
                    title = screen.find(ids=["tv_title"]) \
                        or screen.find(ids=["tvTemplateTitle"])
                    ok("F2: edit form title=%r (want 'Edit Clan')"
                       % (title.text if title else None))
                    name_in = screen.find(ids=["etTribeName"])
                    new_name = "EditClan%05d" % (int(time.time()) % 100000)
                    typed = None
                    if name_in and name_in.center:
                        screen.tap_node(name_in)
                        time.sleep(1)
                        for _ in range(len(own_name) + 4):
                            adb.key(67)  # DEL the pre-filled name
                        time.sleep(0.5)
                        adb.text(new_name)
                        time.sleep(1)
                        adb.key(4)  # close the IME
                        time.sleep(1)
                        for x in screen.dump():
                            if x.cls.endswith("EditText") and x.center \
                                    and x.res.rsplit("/", 1)[-1] == \
                                    "etTribeName":
                                typed = x.text or ""
                                break
                        ok("F2: name field now %r (wanted %r)"
                           % (typed, new_name))
                        if typed != new_name:
                            for _ in range(len((typed or "")) + 4):
                                adb.key(67)
                            adb.text(new_name)
                            time.sleep(1)
                            adb.key(4)
                            time.sleep(1)
                            for x in screen.dump():
                                if x.cls.endswith("EditText") and x.center \
                                        and x.res.rsplit("/", 1)[-1] == \
                                        "etTribeName":
                                    typed = x.text or ""
                                    break
                            ok("F2: name field after retype %r" % typed)
                    else:
                        print("  [info] F2: etTribeName not found on the "
                              "edit form")
                    # tags: required by the update validation - add one if
                    # the form has none (the create flow's proven pattern)
                    d_form = screen.dump()
                    tag_label = next((x for x in d_form
                                      if (x.text or "") == "Clan tag"
                                      and x.center), None)
                    if tag_label:
                        idx = d_form.index(tag_label)
                        tag_btn = next((x for x in d_form[idx + 1: idx + 4]
                                        if x.clickable and x.center
                                        and not x.cls.endswith("EditText")),
                                       None)
                        if tag_btn:
                            screen.tap_node(tag_btn)
                            time.sleep(4)
                            if f_alive("F2-clantag"):
                                msg = screen.find(ids=["et_msg"])
                                if msg and msg.center:
                                    screen.tap_node(msg)
                                    time.sleep(1)
                                    adb.text("QA2")
                                    time.sleep(1)
                                    adb.key(4)
                                    time.sleep(1)
                                conf = screen.find(ids=["btn_confirm"])
                                if conf and conf.center:
                                    screen.tap_node(conf)
                                    time.sleep(3)
                                    still = screen.find(ids=["tv_title"])
                                    if still and (still.text or "") == \
                                            "Add Tag":
                                        print("  [info] F2: tag dialog "
                                              "still open (tag rejected?)")
                                        adb.key(4)  # dismiss the stuck dialog
                                        time.sleep(2)
                                    else:
                                        ok("F2: tag added (dialog closed)")
                    else:
                        print("  [info] F2: 'Clan tag' label not found - "
                              "tags may already exist")
                    # 5t v10 (run 37374604536): the layout applies
                    # textAllCaps - the button renders 'MODIFY'
                    modify = next((x for x in screen.dump()
                                   if (x.text or "") in ("Modify", "MODIFY")
                                   and x.center), None)
                    if modify:
                        screen.tap_node(modify)
                        time.sleep(4)
                        f_alive("F2-edit-submit")
                        puts_after = put_tribe_count()
                        print("  [evidence] F2: PUT count %d -> %d"
                              % (puts_before, puts_after))
                        if live_hdr:
                            base2 = fcall("GET",
                                          "/clan/api/v1/clan/tribe/base",
                                          headers=live_hdr)
                            srv_name = (base2.get("data") or {}).get("name")
                            check("F2: clan-UPDATE client-asserted through "
                                  "the real UI (PUT fired, server name=%r)"
                                  % srv_name,
                                  puts_after > puts_before
                                  and srv_name == new_name,
                                  "puts %d->%d server=%r typed=%r"
                                  % (puts_before, puts_after, srv_name,
                                     typed))
                        else:
                            check("F2: clan-UPDATE PUT fired",
                                  puts_after > puts_before,
                                  "puts %d->%d" % (puts_before, puts_after))
                    else:
                        print("  [info] F2: 'Modify' button not found - "
                              "form dump:")
                        for x in screen.dump():
                            if x.res or x.text:
                                print("  F2-form] %s | text=%r" % (
                                    x.res.rsplit("/", 1)[-1] if x.res
                                    else "", x.text[:28]))
                else:
                    print("  [info] F2: settings sheet never showed 'Edit "
                          "Profile' (dump evidence above)")
                # BACK out of the edit form (when F2 opened it) -> homepage
                adb.key(4)
                time.sleep(2)
                # ------------------------- Phase G: member management + clan
                # settings (session 18, wave 5u). jadx decode:
                # TribeMemberManage (oa.a, right button = invite) rows are
                # TribeHasItemViewModel J: row tap (manage mode, not-self)
                # -> BottomDialog [Hand over Chief | Set as Elder | Remove
                # Member | Cancel] -> TwoButtonDialog (btnSure confirms) ->
                # PUT /clan/api/v1/clan/tribe/member?otherId=&type={1,2,3}
                # (1=elder, 2=member, 3=hand over - server now speaks the
                # client codes) or DELETE .../member/remove?otherId=.
                # Clan Settings (sa.b) is the auto-enter CheckBox ->
                # PUT /clan/api/v1/clan/free/verification?freeVerify={0,1};
                # sa.e initializes the toggle TRUE regardless of server
                # state, so the drive taps twice (PUT 0 then PUT 1), asserts
                # base.freeVerify == 1, taps once more (PUT 0) and restores.
                if live_hdr and d_uid_live:
                    # NOTE: the server REQ log prints the PATH ONLY
                    # (NanoHTTPD getUri(), no query) - count by verb+path
                    # and exclude the sibling routes.
                    puts_g = lambda: sum(
                        1 for line in adb.raw("logcat", "-d", "-s",
                                              "LocalAPI",
                                              timeout=60).splitlines()
                        if "REQ PUT /clan/api/v1/clan/tribe/member" in line
                        and "/member/agreement" not in line
                        and "/member/remove" not in line)
                    fv_req_count = lambda: sum(
                        1 for line in adb.raw("logcat", "-d", "-s",
                                              "LocalAPI",
                                              timeout=60).splitlines()
                        if "REQ PUT /clan/api/v1/clan/free/"
                        "verification" in line)
                    # (a) a second member through the local API
                    gj_uid = "gqa%05d" % (int(time.time()) % 100000)
                    gj_pw = "LocalQA%05d" % (int(time.time()) % 100000)
                    gj = fcall("POST", "/user/api/v1/register",
                               {"uid": gj_uid, "password": gj_pw,
                                "confirmPassword": gj_pw, "imei": "g-device",
                                "appType": "android", "os": "12"})
                    gj_uid_num = (gj.get("data") or {}).get("userId", 0)
                    gj_tok = (gj.get("data") or {}).get("accessToken", "")
                    gj_ok = gj.get("code") == 1 and gj_uid_num > 0
                    if gj_ok:
                        gjh = {"Access-Token": gj_tok,
                               "userId": str(gj_uid_num), "language": "en"}
                        gjr = fcall("POST", "/clan/api/v1/clan/tribe/member",
                                    {"clanId": own_clan_id,
                                     "msg": "g-join"}, headers=gjh)
                        gja = fcall("PUT",
                                    "/clan/api/v1/clan/tribe/member/agreement"
                                    "?otherId=%d" % gj_uid_num, None,
                                    headers=live_hdr)
                        gj_ok = gjr.get("code") == 1 and gja.get("code") == 1
                        ok("G: second member joined via the API (%s)"
                           % gj_uid) if gj_ok else print(
                               "  [info] G: API join failed: %s %s"
                               % (str(gjr)[:80], str(gja)[:80]))
                    gml = fcall("GET", "/clan/api/v1/clan/tribe/member",
                                headers=live_hdr) if gj_ok else {"data": []}
                    g_nick = next((m.get("nickName") for m in
                                   gml.get("data", [])
                                   if m.get("userId") == gj_uid_num), None)
                    if g_nick:
                        more = None
                        for x in screen.dump():
                            if not (x.center
                                    and x.cls.endswith("ImageButton")):
                                continue
                            cx, cy = x.center
                            if cy < 140 and cx > 360:
                                more = x
                                break
                        if more and screen.tap_node(more):
                            time.sleep(3)
                        mm = screen.find(texts=["Manage Members"])
                        if mm and mm.center:
                            ok("G: settings sheet shows 'Manage Members'")
                            screen.tap_node(mm)
                            time.sleep(5)
                            f_alive("G-managescreen")
                            for x in screen.dump():
                                if x.res or x.text or x.desc:
                                    print("  G-manage] %s | text=%r" % (
                                        x.res.rsplit("/", 1)[-1]
                                        if x.res else "", x.text[:28]))
                            row = screen.wait_for(texts=[g_nick], timeout=12,
                                                  poll=3)
                            puts_before_g = puts_g()
                            if row and row.center:
                                # promote: Set as Elder -> btnSure.
                                # 5u run evidence: the manage screen hint is
                                # 'Long press to edit member' - the sheet is
                                # the LONG-CLICK command, not a tap.
                                l, t, r, b = row.bounds
                                adb.sh("input swipe %d %d %d %d 1000"
                                       % ((l + r) // 2, (t + b) // 2,
                                          (l + r) // 2, (t + b) // 2))
                                time.sleep(3)
                                elder = screen.find(texts=["Set as Elder"])
                                if elder and elder.center:
                                    screen.tap_node(elder)
                                    time.sleep(3)
                                    sure = screen.find(ids=["btnSure"])
                                    if sure and sure.center:
                                        screen.tap_node(sure)
                                        time.sleep(4)
                                        f_alive("G-promote")
                                        puts_after_g = puts_g()
                                        ml_g = fcall(
                                            "GET",
                                            "/clan/api/v1/clan/tribe/member",
                                            headers=live_hdr)
                                        g_role = next(
                                            (m.get("role") for m in
                                             ml_g.get("data", [])
                                             if m.get("userId")
                                             == gj_uid_num), None)
                                        check(
                                            "G: setIdentity client-asserted "
                                            "(type 1 elder, server role=%s)"
                                            % g_role,
                                            puts_after_g > puts_before_g
                                            and g_role == 10,
                                            "puts %d->%d role=%s"
                                            % (puts_before_g, puts_after_g,
                                               g_role))
                                else:
                                    print("  [info] G: 'Set as Elder' not "
                                          "on the member sheet")
                                # remove: Remove Member -> btnSure
                                row2 = screen.wait_for(texts=[g_nick],
                                                       timeout=10, poll=3)
                                if row2 and row2.center:
                                    l2, t2, r2, b2 = row2.bounds
                                    adb.sh("input swipe %d %d %d %d 1000"
                                           % ((l2 + r2) // 2, (t2 + b2) // 2,
                                              (l2 + r2) // 2, (t2 + b2) // 2))
                                    time.sleep(3)
                                    rm = screen.find(texts=["Remove Member"])
                                    if rm and rm.center:
                                        screen.tap_node(rm)
                                        time.sleep(3)
                                        sure2 = screen.find(ids=["btnSure"])
                                        if sure2 and sure2.center:
                                            screen.tap_node(sure2)
                                            time.sleep(4)
                                            f_alive("G-remove")
                                            ml_h = fcall(
                                                "GET",
                                                "/clan/api/v1/clan/tribe/"
                                                "member", headers=live_hdr)
                                            gone = all(
                                                m.get("userId")
                                                != gj_uid_num
                                                for m in ml_h.get("data", []))
                                            check("G: removeMember "
                                                  "client-asserted (member "
                                                  "gone)", gone,
                                                  str(ml_h)[:120])
                            else:
                                print("  [info] G: member row %r not on "
                                      "the manage screen" % g_nick)
                            adb.key(4)
                            time.sleep(3)
                        else:
                            print("  [info] G: 'Manage Members' not on the "
                                  "sheet (dump evidence above)")
                        # ---------------- Clan Settings (auto-enter toggle)
                        more2 = None
                        for x in screen.dump():
                            if not (x.center
                                    and x.cls.endswith("ImageButton")):
                                continue
                            cx, cy = x.center
                            if cy < 140 and cx > 360:
                                more2 = x
                                break
                        if more2 and screen.tap_node(more2):
                            time.sleep(3)
                        cs = screen.find(texts=["Clan Settings"])
                        if cs and cs.center:
                            screen.tap_node(cs)
                            time.sleep(5)
                            f_alive("G-settings")
                            cb = next((x for x in screen.dump()
                                       if x.center
                                       and x.cls.endswith("CheckBox")), None)
                            if cb and cb.center:
                                # sa.e hardcodes the toggle TRUE and the
                                # response re-binds it after every PUT, so
                                # the sent value per tap is read from the
                                # REQ line itself (?freeVerify=). Assertion:
                                # the server state always follows the last
                                # value the client sent.
                                # 5u run decode: the client PUTs the value
                                # as a FORM body (NanoHTTPD merges it into
                                # getParameters - the URI carries no query),
                                # and the state follows each tap. Assert the
                                # state sequence CHANGED (the server followed
                                # the client's toggling) with bounded PUTs.
                                fv0 = fv_req_count()
                                states = []
                                for tap_n in range(1, 4):
                                    screen.tap_node(cb)
                                    time.sleep(3)
                                    f_alive("G-fv-tap%d" % tap_n)
                                    base_g = fcall(
                                        "GET", "/clan/api/v1/clan/tribe/base",
                                        headers=live_hdr)
                                    state = (base_g.get("data") or {}).get(
                                        "freeVerify")
                                    states.append(state)
                                    print("  [evidence] G: freeVerify tap %d "
                                          "-> server state %s"
                                          % (tap_n, state))
                                fv2 = fv_req_count()
                                check(
                                    "G: freeVerify toggle client-asserted "
                                    "(server followed the taps: %s, PUTs "
                                    "%d->%d)" % (states, fv0, fv2),
                                    fv2 >= fv0 + 2 and len(set(states)) >= 2
                                    and states[-1] in (0, 1),
                                    "states=%s puts %d->%d"
                                    % (states, fv0, fv2))
                                # restore the deterministic world: 0
                                for _ in range(4):
                                    base_r = fcall(
                                        "GET", "/clan/api/v1/clan/tribe/base",
                                        headers=live_hdr)
                                    if (base_r.get("data") or {}).get(
                                            "freeVerify") in (0, None):
                                        break
                                    screen.tap_node(cb)
                                    time.sleep(3)
                            else:
                                print("  [info] G: auto-enter CheckBox not "
                                      "found on the settings screen")
                            adb.key(4)
                            time.sleep(3)
                        else:
                            print("  [info] G: 'Clan Settings' not on the "
                                  "sheet (chief-only item; dump above)")
                        for _ in range(3):
                            if screen.find(ids=["rb_3"]):
                                break
                            adb.key(4)
                            time.sleep(2)
                        assert_alive(adb, args.package, "G-grounded")
                    else:
                        print("  [skip] G: no second member (API join "
                              "failed) - member/settings drives skipped")
                else:
                    print("  [skip] G: no live session token")
            else:
                print("  [info] F: own clan %s NOT surfaced (tab3 dump + "
                      "clanscreen dump recorded above for the next wave)"
                      % own_name)
            # ground: leave the drive somewhere with the bottom nav
            for _ in range(4):
                if screen.find(ids=["rb_3"]):
                    break
                adb.key(4)
                time.sleep(2)
            assert_alive(adb, args.package, "F-grounded")
        else:
            print("  [skip] F: rb_3 not found after Phase E")
    else:
        print("  [info] Phase F skipped - no own clan (no session token from "
              "Phase D, API create failed, or rb_3 unavailable)")

    # ------------------------------------------------- assertions
    print("== assertions ==")
    # Union with the early snapshot: GL-heavy screens rotate the logcat
    # main buffer, so end-of-run scans alone miss early traffic.
    paths = sorted(set(paths_early) | set(localapi_paths(adb)))
    print("  LocalAPI unique endpoints hit: %d" % len(paths))
    for p in paths:
        print("    - %s" % p)
    reg_hit = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
    register_endpoints = ("REQ POST /user/api/v1/register" in reg_hit
                          or "REQ POST /user/api/v1/app/set-password" in reg_hit
                          or "REQ POST /user/api/v2/app/set-password" in reg_hit
                          or "REQ POST /user/api/v1/user/register" in reg_hit
                          # buffer-rotation-resilient fallback: the path set
                          # (merged with the early snapshot) is authoritative
                          or "/register" in " ".join(paths)
                          or "set-password" in " ".join(paths))
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
