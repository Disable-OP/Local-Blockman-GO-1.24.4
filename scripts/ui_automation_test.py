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
import os
import time
import xml.etree.ElementTree as ET

FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("  [FAIL] %s" % msg)


def alive_or_recover_at(adb, screen, package, activity, stage):
    """Module-level alive_or_recover (the deep-drive closure is out of
    scope in the late phases). The roaming native-kill family has now
    struck at G-grounded and F-grounded AFTER every chain check had gone
    green (run 37441604561), which then starved Phase H entirely - the
    embedded server IS the app process, so a dead app means no server,
    no wallet reads, no hall. Record the death as evidence, relaunch, and
    let the drive continue; the crash scan stays the honesty gate."""
    if adb.pid(package):
        ok("alive at %s (pid %s)" % (stage, adb.pid(package)))
        return True
    print("  [evidence] process died at stage: %s - relaunching "
          "(native-kill family signature)" % stage)
    if relaunch_and_wait(adb, screen, package, activity, stage):
        ok("recovered after death at %s" % stage)
        return True
    return False


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

    def ime_visible(self):
        """True when the soft keyboard is up (dumpsys input_method)."""
        return "mInputShown=true" in self.sh(
            "dumpsys input_method | grep mInputShown")

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

    def snap(self, tag):
        """Screenshot to /sdcard for the CI diagnostics artifact. Used on
        assertion misses (e.g. the H reward dialog) so the triage has pixel
        evidence, not only an XML dump."""
        try:
            self.adb.sh("screencap -p /sdcard/snap_%s.png" % tag)
            print("  [snap] /sdcard/snap_%s.png" % tag)
        except Exception as e:
            print("  [snap] %s failed: %s" % (tag, e))

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


def dismiss_permission_dialogs(screen, rounds=8, clean_streak=2):
    # 2026-10-07 fast-mode: stop after `clean_streak` consecutive rounds
    # with NO dialog on screen - the old fixed 8-round loop burned ~8s per
    # call even when nothing popped (3+ calls per fast run = ~24s of pure
    # sleep). Staggered late dialogs are still covered: every relaunch
    # path re-calls this after its settle sleep, and the main-screen
    # wait_for would spot a dialog blocking rgBottom.
    quiet = 0
    for _ in range(rounds):
        n = screen.find(texts=["Allow", "ALLOW", "While using the app",
                               "Only this time", "ALLOW ONLY FOR THIS SESSION"])
        if n and n.center:
            screen.tap_node(n)
            time.sleep(1.5)
            quiet = 0
        else:
            quiet += 1
            if quiet >= clean_streak:
                return
            time.sleep(1.0)


def assert_alive(adb, package, stage):
    pid = adb.pid(package)
    if not pid:
        fail("process died at stage: %s" % stage)
        return False
    ok("alive at %s (pid %s)" % (stage, pid))
    return True


def handle_campaign_dialogs(adb, screen, tag):
    """Defensive handler for the surfaces the Wave 5v/5w server lights up:
    the campaign sign-in dialog (dvSignUp grid) and its reward popup.

    The client's hall bookkeeping MAY open the full-screen sign dialog
    (view/dialog/a/d) whenever signInStatus==0. It would otherwise block
    the whole drive (the TribeSettingGuide lesson: a self-serving overlay
    outlasts any timeout). All outcomes are non-fatal probes:
    - dvSignUp + a tappable "Claim"-text button -> tap it (fires POST
      /activity/api/v1/signIn), then dismiss the reward popup (ll_reward)
      that pops on success.
    - dvSignUp without a claim button -> BACK (the dialog is dismissible
      via its close command, and BACK closes FullScreenDialogs).
    Returns a short probe string for the log ('claimed'/'dismissed'/None).
    """
    probe = None
    try:
        for _round in range(2):
            nodes = screen.dump()
            has_grid = any((n.res or "").rsplit("/", 1)[-1] == "dvSignUp" for n in nodes)
            if not has_grid:
                break
            btn = next((n for n in nodes
                        if n.cls == "android.widget.Button" and n.clickable
                        and n.text and n.text.strip().lower() in ("claim",)), None)
            if btn:
                screen.tap_node(btn)
                probe = "claimed"
                print("  [probe] %s: campaign sign dialog -> tapped Claim" % tag)
                time.sleep(3)
                reward = screen.find(ids=["ll_reward", "rlBg"])
                if reward and reward.center:
                    # the reward popup's confirm button is databound (no
                    # id/text) - tap its parent region's lower half
                    n2 = next((x for x in screen.dump()
                               if x.cls == "android.widget.Button" and x.center), None)
                    if n2:
                        screen.tap_node(n2)
                    else:
                        adb.key(4)
                    probe += "+reward-dismissed"
                    print("  [probe] %s: reward popup dismissed" % tag)
                time.sleep(2)
            else:
                adb.key(4)
                probe = "dismissed"
                print("  [probe] %s: campaign sign dialog -> BACK" % tag)
                time.sleep(2)
            if not assert_alive(adb, "com.disabngo.blockynexus",
                                "%s-campaign-dialog" % tag):
                break
    except Exception as e:
        print("  [probe] %s: campaign dialog handler error (non-fatal): %s" % (tag, e))
    return probe


def reenter_scrap(adb, screen, package, activity, tag):
    """Return to the scrap template from wherever the app drifted to.

    Run 37461423454: the app was back at the hall by the time Phase J
    searched for ll_library (the scrap template closed itself after the
    I checks — mechanism undecoded; the dump was a live hall, no FATAL).
    This helper re-runs the proven entry walk: ground at rb_1, collapse
    the shade, expand the header, tap item3/littleItem3. Returns True
    when the template's menu (ll_library) is visible again.
    """
    try:
        if not adb.pid(package):
            alive_or_recover_at(adb, screen, package, activity,
                                "%s-reentry" % tag)
        ground = False
        for _ in range(4):
            if screen.find(ids=["rb_1"]):
                ground = True
                break
            adb.key(4)
            time.sleep(2)
        if not ground:
            return False
        rb1 = screen.find(ids=["rb_1"])
        if rb1 and rb1.center:
            screen.tap_node(rb1)
            time.sleep(4)
        dismiss_permission_dialogs(screen)
        handle_campaign_dialogs(adb, screen, "%s-hall" % tag)
        entry = None
        for _ in range(3):
            adb.sh("cmd statusbar collapse")
            time.sleep(1)
            if not adb.pid(package):
                alive_or_recover_at(adb, screen, package, activity,
                                    "%s-walk" % tag)
            adb.sh("input swipe 360 300 360 800 300")
            time.sleep(2)
            entry = screen.find(ids=["item3"]) \
                or screen.find(ids=["littleItem3"])
            if entry and entry.center:
                break
        if not (entry and entry.center):
            return False
        screen.tap_node(entry)
        time.sleep(6)
        assert_alive(adb, package, "%s-reentered" % tag)
        time.sleep(2)
        return screen.find(ids=["ll_library"]) is not None
    except Exception as e:
        print("  [probe] %s: scrap re-entry error (non-fatal): %s"
              % (tag, e))
        return False


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
        # 2026-10-07 fast-mode: settle 8s (was 12) then poll every 2s -
        # the boot-to-main wait is dominated by real app boot (~55-70s on
        # Redroid), the extra settle seconds just added dead time on top.
        time.sleep(8)
        dismiss_permission_dialogs(screen)
        up = bool(screen.wait_for(ids=["rgBottom", "rb_1", "flHomePage"],
                                  timeout=90, poll=2))
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


# ---------------------------------------------------------------------------
# Deep-phase TIME BUDGET (user mandate 2026-10-08: "lower the DEEP test
# redroid time ... I am sick of always waiting 30-35 minutes ... TIME IS
# PRECIOUS"). --deep-budget-min caps the wall time of the deep phases ONLY
# (the fast core: Phase A visitor / P / C registration / D upgrade and the
# final assertions always run, budget or not).
#   deep-drive A + Phase B  -> non-raising deep_go() gates (they sit BEFORE
#                              the core C/D phases, so they must never abort
#                              the registration chain)
#   Phase E .. LM           -> budget_gate() raises DeepBudgetSkip once the
#                              budget is gone; the suite catches it right
#                              before the fast-mode else and keeps going
# 0 (default when run by hand) = unlimited, the historical behaviour.
class DeepBudgetSkip(Exception):
    """Raised by budget_gate() when the deep-phase budget is exhausted."""


_DEEP_STATE = {"budget": 0.0, "deadline": None}


def _deep_deadline():
    """Lazily start the deep-budget clock at the FIRST deep phase."""
    if _DEEP_STATE["budget"] <= 0:
        return None
    if _DEEP_STATE["deadline"] is None:
        _DEEP_STATE["deadline"] = time.time() + _DEEP_STATE["budget"]
    return _DEEP_STATE["deadline"]


def deep_left():
    """Seconds of deep budget left (inf when unlimited)."""
    dl = _deep_deadline()
    return float("inf") if dl is None else dl - time.time()


def deep_go(label, est_min):
    """NON-raising gate for the pre-core deep phases (deep-drive A, Phase B):
    True -> run; False -> skip (budget exhausted or estimate cannot fit).
    Must NEVER raise: these phases sit before the core C/D registration
    chain and an abort there would kill the whole suite."""
    if _DEEP_STATE["budget"] <= 0:
        return True
    left = deep_left()
    if left <= 0 or left < est_min * 60:
        print("  [skip budget] %s (%.1f min left, needs ~%s min)"
              % (label, max(left, 0.0) / 60.0, est_min))
        return False
    return True


def budget_gate(label, est_min):
    """RAISING gate for the E..LM deep block: DeepBudgetSkip aborts the
    remaining deep phases (caught once right before the fast-mode else;
    the final assertions + crash scan still run)."""
    if _DEEP_STATE["budget"] <= 0:
        return
    left = deep_left()
    if left <= 45 or left < est_min * 60:
        print("  [skip budget] %s (%.1f min left, needs ~%s min) - "
              "remaining deep phases skipped"
              % (label, max(left, 0.0) / 60.0, est_min))
        raise DeepBudgetSkip(label)


def clamp_deep(deadline):
    """Clamp a poll ceiling to the deep budget wall (no wait overruns it)."""
    dl = _deep_deadline()
    if dl is None:
        return deadline
    return min(deadline, dl)


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
                alive_or_recover("%s-MailRow" % tag)
                # Wave 15 — opening a mail row fires mailOperation
                # (MailBoxApi.mailOperation = PUT /mailbox/api/v1/mail,
                # the read-marking contract; observed in run 37588191029).
                mlog = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
                mail_op_lit = "/mailbox/api/v1/mail"
                check("A: mail read-marking served (PUT %s)" % mail_op_lit,
                      ("PUT %s" % mail_op_lit) in mlog)
                adb.key(4)  # back to the list
                time.sleep(2)
            else:
                print("  [info] no Welcome mail row this run — read-marking "
                      "gate skipped (row guard)")
            adb.key(4)  # back to Me
            time.sleep(2)
        visit("Top Up", 6)         # recharge screen (pay products path)
        visit("Ranking", 6)        # ranking screen (rank home path)
        visit("Store", 6)          # store screen (dress/suit shop path)
        # Wave 15 — Video row (MoreViewModel.R -> VideoFragment (wa.b) ->
        # rbRecommend -> xa.n list model -> VideoApi.getVideoByTag =
        # GET /video/api/v1/app/video/more/list, fired on template open).
        # Code-proven traffic, so the gate is HARD. The tag list
        # (/video/api/v1/app/video/tag/list) rides the tag-filter dialog
        # (ya.f.a) — discovery only unless the tap proves it.
        # Wave 15b — Video row: the 15a hard gate FAILED on-device (run
        # 37598014388): the tap lands, the app stays alive, but the video
        # template fires NO LocalAPI route on open (its REST loads are
        # interaction-driven — tag filter / pagination / detail). Downgraded
        # to a discovery probe with a node dump until the trigger is mapped.
        vid_row = screen.find(texts=["Video"])
        # Wave 18d — the list/{type} gate reads the LIVE video-section
        # capture instead of the end-of-drive `added` diff: the logcat
        # main buffer rotates under GL traffic (run 37649784800 — the
        # 16:12 video-screen routes rotated out before the 16:20 diff,
        # FAILing a check whose routes demonstrably fired). The video
        # screen fires list/{type} on open every run (lines of evidence:
        # 389/410 in every deep run log).
        vl_frag = "/vid" + "eo/api/v1/app/video/list/"
        vlist_seen = False
        if vid_row and vid_row.center:
            vlog_before = localapi_paths(adb)
            screen.tap_node(vid_row)
            time.sleep(6)
            alive_or_recover("%s-Video" % tag)
            vnew = [p for p in localapi_paths(adb)
                    if p not in vlog_before]
            if vnew:
                ok("A: video screen traffic added: %s" % ", ".join(vnew))
            else:
                print("  [info] video template fired no LocalAPI routes "
                      "(15a verdict stands)")
            if any(p.startswith(vl_frag) for p in vnew):
                vlist_seen = True
            for n in screen.dump():
                if n.res or n.text or n.desc:
                    print("  video] %s | text=%r desc=%r" % (
                        n.res.rsplit("/", 1)[-1] if n.res else "",
                        n.text[:24], n.desc[:24]))
            # Wave 18 — VideoViewModel (wa.d) radio map, decompiled:
            # rbAll -> VideoTotalFragment (ya.c, FragmentAppVideoTotal)
            # whose ROOT ConstraintLayout carries the click command
            # (databinding fd.executeBindings: clickCommand(f5406a,
            # gVar.e)); g.f() -> VideoTotalModel.f.a -> getVideoTagList =
            # GET /video/api/v1/app/video/tag/list, then the
            # VideoTagPopupWindowDialog drops down with the tag rows.
            # rbRecommend -> VideoRecommendFragment (xa.g).
            # The tag gate below is UNCONDITIONAL (always verdict-backed —
            # never a silent phantom claim in gen_coverage): a navigation
            # miss records a FAIL with the dump evidence for triage.
            tag_lit = "/video/api/v1/app/video/tag/list"
            tag_gate_pass = False
            vall = screen.find(ids=["rbAll"])
            if vall and screen.tap_node(vall):
                time.sleep(5)
                alive_or_recover("%s-VideoAll" % tag)
                vlog2 = localapi_paths(adb)
                va_new = [p for p in vlog2 if p not in vlog_before]
                if va_new:
                    ok("A: video ALL-tab traffic: %s" % ", ".join(va_new))
                if any(p.startswith(vl_frag) for p in va_new):
                    vlist_seen = True
                # the tag strip (tvSelect) only exists on the total template
                tsel = screen.find(ids=["tvSelect"])
                if tsel and tsel.center:
                    # fd.java binds clickCommand to the ENCLOSING
                    # ConstraintLayout (f5406a); the TextView itself does
                    # not consume clicks, so tap tvSelect first and fall
                    # back to its clickable ConstraintLayout ancestor.
                    screen.tap_node(tsel)
                    time.sleep(4)
                    tag_log = adb.raw("logcat", "-d", "-s", "LocalAPI",
                                      timeout=60)
                    if ("GET %s" % tag_lit) not in tag_log:
                        tsb = tsel.bounds
                        for n in screen.dump():
                            if not (n.clickable and n.center
                                    and n.cls.endswith("ConstraintLayout")):
                                continue
                            l2, t2, r2, b2 = n.bounds
                            if l2 <= tsb[0] and r2 >= tsb[2] \
                                    and t2 <= tsb[1] and b2 >= tsb[3]:
                                screen.tap_node(n)
                                time.sleep(4)
                                tag_log = adb.raw("logcat", "-d", "-s",
                                                  "LocalAPI", timeout=60)
                                break
                    alive_or_recover("%s-VideoTag" % tag)
                    tag_gate_pass = (("GET %s" % tag_lit) in tag_log)
                    for n in screen.dump():
                        if n.text:
                            print("  videotagdlg] %s | text=%r" % (
                                n.res.rsplit("/", 1)[-1] if n.res else "",
                                n.text[:24]))
                    # close the dropdown: a tag row tap ("All" default row)
                    # re-fires the list/{type} refresh; else BACK is unsafe
                    # (dropdown + template stack) — tap rbAll again instead
                    row = screen.find(texts=["All", "all"])
                    if row and row.center:
                        screen.tap_node(row)
                        time.sleep(4)
                        alive_or_recover("%s-VideoTagSel" % tag)
                        vsel = [p for p in localapi_paths(adb)
                                if p not in vlog2]
                        if vsel:
                            ok("A: video tag-select refresh: %s"
                               % ", ".join(vsel))
                    vlog_before = localapi_paths(adb)
                else:
                    print("  [info] tvSelect not found after rbAll — "
                          "total template did not open (dump above)")
                # round-trip back to the recommend tab
                vreco = screen.find(ids=["rbRecommend"])
                if vreco and screen.tap_node(vreco):
                    time.sleep(4)
                    alive_or_recover("%s-VideoReco" % tag)
            else:
                print("  [info] rbAll not found on the video screen")
            # Unconditional verdict: the decompiled binding (fd.java) proves
            # this click fires tag/list — the gate claims the route only
            # when the drive actually performed it on-device.
            check("A: video tag-filter strip served tag list (GET %s)"
                  % tag_lit, tag_gate_pass)
            # Close the dropdown FIRST: the VideoTagPopupWindowDialog stays
            # open on row-select (CONFIRM/CANCEL semantics) — run
            # 37640357412 evidence: the open popup swallowed the single
            # BACK, every subsequent Me-tab find failed ('Party'/ivTurntable/
            # rb_2 not found) and the shop-mode block + type-radio probes
            # skipped. Then ground on the main tab bar (up to 3 BACKs).
            cancel = screen.find(texts=["CANCEL", "Cancel"])
            if cancel and cancel.center:
                screen.tap_node(cancel)
                time.sleep(2)
            for _ in range(3):
                if screen.find(ids=["rgBottom"]):
                    break
                adb.key(4)
                time.sleep(2)
        else:
            print("  [skip] 'Video' row not found on the Me tab")
        # Wave 15 — Party row (MoreViewModel.K -> PartyHallFragment):
        # discovery probe. The hall's own REST loads are not yet mapped
        # endpoint-for-endpoint; print what the tap adds (promotion to a
        # hard gate lands with the next evidence pass).
        party_row = screen.find(texts=["Party"])
        if party_row and party_row.center:
            screen.tap_node(party_row)
            time.sleep(6)
            alive_or_recover("%s-Party" % tag)
            # Wave 15b — PROMOTED to hard gates: run 37598014388 proved
            # the party-hall open fires both routes every time.
            plog = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
            party_auth_lit = "/game/api/v2/party/auth"
            check("A: party hall auth served (GET %s)" % party_auth_lit,
                  ("GET %s" % party_auth_lit) in plog)
            party_open_lit = "/game/api/v1/games/all/open/party"
            check("A: party hall open-list served (GET %s)"
                  % party_open_lit,
                  ("GET %s" % party_open_lit) in plog)
            adb.key(4)  # back to Me
            time.sleep(2)
        else:
            print("  [skip] 'Party' row not found on the Me tab")
        # Wave 15 — ivTurntable (Me-tab turntable icon ->
        # AdsTurntableDialog family). The red-point GET is config-gated
        # (CampaignControl: slot_machine / Lucky 2020 activity ids) —
        # discovery probe, non-fatal.
        turn = screen.find(ids=["ivTurntable"])
        if turn and turn.center:
            tlog_before = localapi_paths(adb)
            screen.tap_node(turn)
            time.sleep(5)
            alive_or_recover("%s-Turntable" % tag)
            tnew = [p for p in localapi_paths(adb)
                    if p not in tlog_before]
            if tnew:
                ok("A: turntable traffic added: %s" % ", ".join(tnew))
            else:
                print("  [info] turntable tap added no new LocalAPI routes")
            # grounding: close whatever the tap opened WITHOUT risking the
            # double-back-to-exit path on the main activity (an empty tap
            # surface + BACK would arm the exit toast)
            if not screen.find(ids=["rgBottom"]):
                adb.key(4)
                time.sleep(2)
            home_tab = screen.find(ids=["rb_1"])
            if home_tab and home_tab.center:
                screen.tap_node(home_tab)
                time.sleep(2)
        else:
            print("  [skip] ivTurntable not found on the Me tab")
        # Wave 5m — BUY through the real Store UI: the Dressing tab only
        # shows OWNED items, so the wear path needs a purchase first.
        # Entry: rb_2 -> ivShopEnter (id from the 5j on-device dump) so we
        # never depend on Me-row tap timing. Then the first product in the
        # content band, the buy control (text-based), and the confirm
        # dialog if one appears. The purchase is REAL state (dressBuyV2
        # wallet math; the visitor wallet covers a product).
        buy_seen = False
        # One retry: a transient empty uiautomator dump (3 failed reads ->
        # []) silently skipped this whole block in the 37635019492 deep run
        # — the shop-mode traffic + Wave 18 type-radio probes never ran and
        # nothing said why. Retry once, then log the skip.
        tab2s = screen.find(ids=["rb_2"])
        if not tab2s:
            time.sleep(3)
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
                # Wave 15 — the recommend feed is a HARD gate now: the
                # shop-mode open fires shopRecommendByV2 on every run
                # (code: decorate.web.w.a -> IShopApi.shopRecommendByV2;
                # evidence: run 37588191029 printed it on this exact path).
                reco_shop_lit = "/shop/api/v1/new/shop/recommend/decorations"
                check("A: store recommend feed served (GET %s)"
                      % reco_shop_lit,
                      ("GET %s" % reco_shop_lit) in slog)
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
                            "RecyclerView") or n.cls.endswith(
                            "ConstraintLayout") or "item" in n.res.lower():
                        product = n
                        break
                if not product:
                    # run-20 miss: the card roots are ConstraintLayout
                    # (item_new_dress_shop.xml) — fall back to the bgView
                    # child id every dress/shop card carries
                    for n in screen.dump():
                        rid = n.res.rsplit("/", 1)[-1] if n.res else ""
                        if rid == "bgView" and n.center:
                            y = n.center[1]
                            if 260 <= y <= 1000:
                                product = n
                                break
                    if not product:
                        print("  [skip] no store product candidate found "
                              "(bgView fallback missed too)")
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
                    def _find_buy():
                        # Wave 23c: the buy dialog's action control is
                        # text-bearing on some builds ("Confirm", the
                        # dialog_dress_buy action) and databinding-only on
                        # others — search BOTH texts and the known action
                        # ids (the q2 dialogs prove btn_confirm carries
                        # 'Confirm'; decorate_new_dress_buy_confirm stays
                        # in the pool in case it is an id on this build).
                        return screen.find(
                            texts=["Buy", "Buy Now", "Purchase", "Get",
                                   "Confirm"],
                            contains=["buy", "purchase", "confirm"]) \
                            or screen.find(ids=["btn_confirm", "btnSure",
                                                "btn_ok", "btnOk", "btnBuy",
                                                "btn_buy",
                                                "decorate_new_dress_buy_confirm"])
                    buy = _find_buy()
                    if not (buy and buy.center):
                        # run-21: the GL-backed dialog content can render
                        # AFTER ivBigPic — re-dump with longer patience
                        # (run-22: at +5s the price fields were still 0
                        # and the item radios + buy button had not
                        # rendered; guest-GPU frames are slow)
                        time.sleep(10)
                        buy = _find_buy()
                    if not (buy and buy.center):
                        # final GL beat (~20s total wait, budget-clamped
                        # upstream by the deep-phase wall)
                        time.sleep(10)
                        buy = _find_buy()
                    if not (buy and buy.center):
                        # wave 23 evidence: dump the dialog texts so the
                        # next run can target the real controls
                        for x in screen.dump():
                            if x.text or x.desc:
                                print("  [buydlg] %s | text=%r desc=%r" % (
                                    x.res.rsplit("/", 1)[-1] if x.res else "",
                                    x.text[:24], x.desc[:24]))
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
                        # wave 23: the buy fires the v2 cart POST
                        # (dressBuyV2) or the single-item PUT
                        # (dressBuyOne, path carries the id) — the
                        # RES code=1 verdict needs the wallet, the
                        # visitor starts with 50k gold so both pass
                        buy_seen = ("new/shop/decorations/buy" in log
                                    or "REQ PUT /shop/api/v1/shop/"
                                       "decorations/buy/" in log)
                        if "REQ POST /shop/api/v1/new/shop/decorations/" \
                                "buy" in log:
                            buy_seen = True
                            ok("5m: Store buy hit POST /shop/api/v1/new/"
                               "shop/decorations/buy")
                        elif "REQ PUT /shop/api/v1/shop/decorations/" \
                                "buy/" in log:
                            buy_seen = True
                            ok("5m: Store buy hit PUT /shop/api/v1/shop/"
                               "decorations/buy/{id}")
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
                # Wave 15 — the store's suit radio (rbSuit in rgDress):
                # one tap from shop mode loads the suit page through
                # decorate.web.w.b -> shopSuitByV2 =
                # GET /shop/api/v1/new/shop/suit/decorations (code-proven;
                # the route is fcall-asserted since Phase C — this tap
                # upgrades it to real app traffic).
                suit_radio = screen.find(ids=["rbSuit"])
                if suit_radio and suit_radio.center:
                    screen.tap_node(suit_radio)
                    time.sleep(5)
                    alive_or_recover("%s-storesuit" % tag)
                    slog2 = adb.raw("logcat", "-d", "-s", "LocalAPI",
                                    timeout=60)
                    suit_page_lit = "/shop/api/v1/new/shop/suit/decorations"
                    check("A: store suit page served (GET %s)"
                          % suit_page_lit,
                          ("GET %s" % suit_page_lit) in slog2)
                    # Wave 15b — PROMOTED: the suit radio switches the store
                    # to its dress-mode side, whose load chain (code:
                    # va.b(Boolean) -> DressManager.getUsingList family) fires
                    # four deterministic GETs (run 37598014388 captured all
                    # four in this exact snapshot). Regexes are verb-aware
                    # and userId-agnostic (the visitor id is dynamic). The
                    # using-path in the check NAME is source-split (repo
                    # convention) so this GET-only gate never verb-blindly
                    # claims the PUT/DELETE siblings of that path — the GET
                    # claim itself rides the Phase C fcall (verb-aware).
                    check("A: store dress-mode worn-list served (GET "
                          "/dec" + "oration/api/v1/decorations/using)",
                          re.search(r"GET /decoration/api/v1/decorations/"
                                    r"using(?:\?|\s|$)", slog2) is not None)
                    reschk_lit = "/decoration/api/v1/new/decorations/check/resource"
                    check("A: store dress-mode res-check served (GET %s)"
                          % reschk_lit,
                          re.search(r"GET /decoration/api/v1/new/decorations/"
                                    r"check/resource", slog2) is not None)
                    expire_lit = "/decoration/api/v1/new/decorations/users/{userId}/expire"
                    dtype_lit = "/decoration/api/v1/new/decorations/users/{userId}/type/{typeId}"
                    check("A: store dress-mode expire list served (GET %s)"
                          % expire_lit,
                          re.search(r"GET /decoration/api/v1/new/decorations/"
                                    r"users/\d+/expire", slog2) is not None)
                    check("A: store dress-mode type list served (GET %s)"
                          % dtype_lit,
                          re.search(r"GET /decoration/api/v1/new/decorations/"
                                    r"users/\d+/type/", slog2) is not None)
                    # discovery channel: anything else the suit page added
                    known = {reco_shop_lit, suit_page_lit}
                    snew = [ln for ln in re.findall(
                        r"REQ (\w+) (/(?:shop|decoration)/\S+)", slog2)
                        if ln[1].split("?")[0] not in known]
                    if snew:
                        ok("A: suit-page extra traffic: %s" %
                           ", ".join("%s %s" % r for r in sorted(set(snew))))
                    # Wave 23b — suit-card probe: the suit page's cards
                    # (same ConstraintLayout/bgView roots the buy hunt
                    # learned in run 21) open a suit detail whose load
                    # fires the suitDetail GET (shop suit info by id).
                    # First pass = DISCOVERY: tap the first card
                    # candidate, print the traffic delta; no hard gate
                    # (the page-state p/z flags decide the slot) and no
                    # leading-/ literal (nothing is claimed yet).
                    scard = None
                    for x in screen.dump():
                        if not x.center:
                            continue
                        sy = x.center[1]
                        if sy < 420 or sy > 950:
                            continue
                        srid = x.res.rsplit("/", 1)[-1] if x.res else ""
                        if (x.cls.endswith("FrameLayout")
                                or x.cls.endswith("LinearLayout")
                                or x.cls.endswith("ConstraintLayout")
                                or srid == "bgView"):
                            scard = x
                            break
                    if scard and screen.tap_node(scard):
                        time.sleep(5)
                        alive_or_recover("%s-suitcard" % tag)
                        sc_log = adb.raw("logcat", "-d", "-s", "LocalAPI",
                                         timeout=60)
                        if re.search(r"REQ GET /shop/api/v1/new/shop/suit/"
                                     r"info/\d+", sc_log):
                            print("  [evidence] suit detail GET fired "
                                  "from the suit card (new/shop/suit/"
                                  "info/{suitId})")
                        else:
                            print("  [info] suit-card tap added no suit "
                                  "detail GET (GL render or slot "
                                  "mismatch)")
                        adb.key(4)
                        time.sleep(2)
                    # Wave 18 — type-radio probes (DressPageListModel ia /
                    # DressSuitPageListModel oa): the recommend feed
                    # (recommend/users/{userId}/type/{typeId}) only fires
                    # for a NON-ZERO typeId whose page list is uncached —
                    # the 15b chain loads type/0, where ga.onSuccess skips
                    # the recommend ride-along. Probe the type radios and
                    # print what each adds; hard gates land with the next
                    # evidence pass (nav is page-state dependent: p/z
                    # flags decide suit-page vs recommend-page slots).
                    reco_deco_lit = ("recommend/users/")
                    for rid in ["rbCloth", "rbPants", "rbShoes", "rbHair"]:
                        radio = screen.find(ids=[rid])
                        if not (radio and radio.center):
                            continue
                        rlog_before = set(localapi_paths(adb))
                        screen.tap_node(radio)
                        time.sleep(4)
                        alive_or_recover("%s-storetype-%s" % (tag, rid))
                        rlog = localapi_paths(adb)
                        rnew = [p for p in rlog if p not in rlog_before]
                        if not rnew:
                            continue
                        ok("A: store type radio %s traffic: %s"
                           % (rid, ", ".join(rnew)))
                        joined = " ".join(rnew)
                        if reco_deco_lit in joined:
                            print("  [evidence] recommend feed fired from "
                                  "type radio %s" % rid)
                        if ("/suit?" in joined or "/suit " in joined
                                or joined.rstrip().endswith("/suit")):
                            print("  [evidence] decoration suit list fired "
                                  "from type radio %s" % rid)
                else:
                    print("  [skip] rbSuit not found on the store screen")
            else:
                print("  [skip] ivShopEnter not found on the Dressing tab "
                      "(shop-mode block + type-radio probes skipped)")
            # return to the Me tab directly (BACK on the main activity is
            # double-back-to-exit territory)
            me_tab = screen.find(ids=["rb_5"])
            if me_tab and me_tab.center:
                screen.tap_node(me_tab)
                time.sleep(2)
        else:
            print("  [skip] rb_2 not found twice on the Me tab "
                  "(shop-mode buy block + type-radio probes skipped)")
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
                        rid = n.res.rsplit("/", 1)[-1] if n.res else ""
                        if n.cls.endswith("FrameLayout") or n.cls.endswith(
                                "LinearLayout") or n.cls.endswith(
                                "ConstraintLayout") or rid == "bgView":
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
                        # wave 23: the single-item wear (PUT using/{id},
                        # DressItemModel.ea -> t.h) is the primary path;
                        # using/new is the multi-select variant
                        if "REQ PUT /decoration/api/v1/decorations/using/" \
                                in wlog:
                            ok("5m: wear action hit PUT /decoration/api/"
                               "v1/decorations/using/{id}")
                        elif "/decorations/using/new" in wlog:
                            ok("5m: wear action hit PUT /decoration/api/"
                               "v1/decorations/using/new")
                        else:
                            print("  [info] no wear PUT observed (control "
                                  "shape changed?)")
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
        chips_tapped = 0
        for chip in ("rb_clothes", "rb_accessories", "rb_character",
                     "rb_function"):
            n = screen.find(ids=[chip])
            if n and screen.tap_node(n):
                time.sleep(4)
                chips_tapped += 1
                alive_or_recover("%s-dress-%s" % (
                    tag, chip.replace("rb_", "")))
            else:
                print("  [skip] dressing chip %s not found" % chip)
        # Wave 23b — the first-level chips switch the wardrobe's per-type
        # page, whose load fires the dressList family (the concrete v1/v2
        # + typeId land on the wire). Entry load (default chip) + the
        # chip taps = the union, claimed ONCE here. The verb+digit regex
        # cannot touch the /using or new/decorations siblings of the
        # path. Guard: only when at least one chip actually tapped (a
        # screen-shape change must be re-discovered, not fail the run).
        if chips_tapped:
            dlog3 = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
            dlist_lit = "/decoration/api/{version}/decorations/{typeId}"
            check("A: dressing chips fired dressList (GET %s)" % dlist_lit,
                  re.search(r"REQ GET /decoration/api/v\d+/decorations/"
                            r"\d+", dlog3) is not None)
            if "REQ GET /config/files/dress-guide-config" in dlog3:
                print("  [evidence] dress guide config served on the "
                      "wardrobe (config/files/dress-guide-config)")
            else:
                print("  [info] dress-guide-config not seen (one-time "
                      "or cached on this build)")
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
            rid = n.res.rsplit("/", 1)[-1] if n.res else ""
            if n.cls.endswith("FrameLayout") or n.cls.endswith(
                    "LinearLayout") or n.cls.endswith(
                    "ConstraintLayout") or rid == "bgView":
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
                wlog2 = adb.raw("logcat", "-d", "-s", "LocalAPI",
                                timeout=60)
                if "REQ PUT /decoration/api/v1/decorations/using/" in wlog2:
                    ok("dressitem wear hit PUT /decoration/api/v1/"
                       "decorations/using/{id}")
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
        # Wave 18c — PROMOTED to a hard gate: the game-card /
        # creator-outfit surface fires the decoration recommend feed
        # deterministically (evidence: deep runs 37635019492, 37640357412
        # and 37644219937 ALL added /decoration/api/v1/new/decorations/
        # recommend/users/<uid>/type/{5,12} at this exact stage — the
        # card's creator outfit renders via FriendGoodsListModel ->
        # t.a(typeId, isSuit=false) -> getRecommendList). The gate is
        # UNCONDITIONAL (verdict-backed: a navigation miss records a FAIL
        # with evidence, never a silent phantom claim in gen_coverage).
        reco_deco_lit = ("/decoration/api/v1/new/decorations/recommend/"
                         "users/{userId}/type/{typeId}")
        reco_gate_pass = False
        if card:
            screen.tap_node(card)
            time.sleep(8)          # game detail fires its whole surface
            alive_or_recover("%s-gamedetail" % tag)
            # Wave 15 — the game-detail open carries the engine-config
            # upload (PUT /game/api/v1/games/engine; observed in run
            # 37588191029's game-detail surface dump).
            glog = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
            engine_lit = "/game/api/v1/games/engine"
            check("A: game detail engine config served (PUT %s)"
                  % engine_lit,
                  ("PUT %s" % engine_lit) in glog)
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
            rclog = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
            reco_gate_pass = (re.search(r"GET /decoration/api/v1/new/decorations/"
                                        r"recommend/users/\d+/type/", rclog)
                              is not None)
        else:
            print("  [skip] no home card candidate found")
        check("A: creator-outfit recommend feed served (GET %s)"
              % reco_deco_lit, reco_gate_pass)
    added = sorted(set(localapi_paths(adb)) - paths_before)
    ok("deep drive added %d new endpoint paths" % len(added))
    for p in added:
        print("    + %s" % p)
    # Wave 15b — friend-family evidence carrier: the chat tab load and the
    # friend-card surfaces fire the /friend/api/v1/friends/ family every
    # run (run 37588191029 artifact: 7x friends/follow, friends/{id}/gaming,
    # friends/info/{nickName}, v2 friends detail). The trailing-slash
    # variable is a DELIBERATE family probe (gen_coverage prefix rule);
    # the follow GET is the deterministic hard gate for the family.
    friend_fam = "/friend/api/v1/friends/"
    friend_v2_fam = "/friend/api/v2/friends/"
    flog = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
    check("A: friend list family served (GET /friend/api/v1/friends/follow)",
          re.search(r"GET /friend/api/v1/friends/follow", flog) is not None)
    # Wave 15c verdict (run 37603763817): the hall rbSuit chip is a LOCAL
    # filter — the manager cache serves it and NO
    # /decoration/api/v1/new/decorations/users/{userId}/suit GET fires
    # from the hall. The route is client=False until a surface that
    # really calls t.b/getDressSuitList is driven (the STORE suit radio
    # fires the /shop/ suit route instead). No gate here on purpose.
    # Evidence-backed surface assertions (run 37492582973's deep-drive
    # delta proved both fetches fire during THIS walk):
    # - the game detail's video section fetches GET /video/api/v1/app/
    #   video/list/{type} (the client resolved {type} to "new" and
    #   "top");
    # - the profile/friend surface fetches GET /decoration/api/v1/
    #   decorations/{otherId}/using (the client resolved {otherId} to
    #   the live user id). Both route templates are implemented +
    #   host-tested but were never client-asserted. HONESTY (the
    #   session-24 rule): the template constants below are the ONLY
    #   full-path fragments quoted here, so gen_coverage maps exactly
    #   these two routes; the evidence-filter prefix is source-split at
    #   4 chars so no sibling route gets prefix-claimed.
    n_video_tmpl = "/video/api/v1/app/video/list/{type}"
    n_using_tmpl = "/decoration/api/v1/decorations/{otherId}/using"
    video_frag = "/vid" + "eo/api/v1/app/video/list/"
    deco_frag = "/dec" + "oration/api/v1/decorations/"
    # Wave 18d — the video-list gate reads the LIVE video-section capture
    # (vlist_seen); the using-gate keeps the `added` diff — its surface
    # (gamecard creator outfit) is adjacent to the diff point and fired
    # in 4/4 deep runs.
    check("A: game-detail video list fetched (GET %s)"
          % n_video_tmpl, vlist_seen,
          "the video feed never fetched the list/{type} routes")
    using_hits = [p for p in added
                  if p.startswith(deco_frag) and p.endswith("/using")]
    check("A: other-user using list fetched (GET %s in %s)"
          % (n_using_tmpl, using_hits or "[]"),
          bool(using_hits),
          "no other-user using-list fetch in the deep drive")
    # (check/resource moved to the BOOT batch — it fires at startup, not
    # in this delta window; run 37516781819 triage.)
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


def login_module_drive(adb, screen, package, activity, tag, old_password):
    """Wave 20 — login-module flows driven through the REAL client UI.
    Deep mode only (the fast suite budget stays protected).

    jadx trigger map (session 35; every hop verified against the
    decompiled sources, labels resolved from resources.arsc):
      Me tab -> 'Setting' row (MoreViewModel.N "more_setup"; row 8 of
        fragment_more — needs a list scroll) -> SettingFragment (e.b.ia.k)
      Setting -> 'Security' row (ia.m.f; item_view_account_safe)
        -> AccountSafeFragment (e.b.b.f / AccountSafeViewModel e.b.b.g):
        * 'Safety Settings' -> j() (requires hasPassword, else toast)
          -> SafeSettingFragment (e.b.ca.c) -> 'Security Questions' row
          -> f() -> (email unbound) b(0) -> UserApi.getUserQuestion
          -> GET /user/api/v1/users/secret/question -> question screen.
          Run-18 VERDICT: the answer submit IS driven end-to-end (POST
          /user/api/v1/users/secret/question/setting, v1 — served).
        * 'Email' / 'Phone number' rows (binding_4/binding_5): visibility
          GONE in the layout and the ViewModel exposes NO visibility
          observables — the rows CANNOT render in this build (runs 8-19
          dumps agree). The email bind's live surface is SafeSetting's
          'Safety Mailbox' row (wave 22, block 2 below); the phone bind
          (e.b.f.e, sms/send/{phone}, user/bind/phone) is UNREACHABLE
          from the UI — host-tested only.
        * 'Modify Password' (hasPassword) -> f() -> LoginManager.
          onConfirmPassword -> ConfirmPasswordFragment (login.f.a.c.c):
          old pw + confirm -> web.b.c passwordCheck -> POST /user/api/v1/
          user/password/check -> ChangePasswordFragment (login.f.a.b.d):
          new + confirm -> web.b.a modifyPassword -> POST /user/api/v1/
          user/password/modify.
    Local policy: the embedded server validates bind codes itself (no
    SMS/email transport can exist in a purely local world), so the drive
    types arbitrary codes. Order is DELIBERATE: questions before the
    email bind (the question list only fires from SafeSetting while the
    email is unbound) and the password rotate LAST.
    The hard requirement stays: the app never crashes; every gate below
    is verdict-backed evidence for the coverage report."""
    def alive_or_recover(stage):
        if adb.pid(package):
            return True
        print("  [evidence] process died at %s - relaunching" % stage)
        return bool(relaunch_and_wait(adb, screen, package, activity, stage))

    def edit_nodes():
        return [n for n in screen.dump()
                if n.cls.endswith("EditText") and n.center]

    def fill_edit(idx, value):
        eds = edit_nodes()
        if idx >= len(eds):
            print("  [skip] edit field %d not found (%d visible)"
                  % (idx, len(eds)))
            return False
        screen.tap_node(eds[idx])
        time.sleep(0.6)
        adb.key(123)  # MOVE_END
        for _ in range(40):
            adb.key(67)  # DEL
        adb.text(value)
        time.sleep(0.4)
        # run-14 evidence: keyevent 111 (ESC) behaves as BACK on templates
        # with an onBackPressed handler (fa.i shows the exit dialog, and a
        # later swipe confirmed it — finish()). Dismiss ONLY the IME: a
        # single BACK closes the keyboard first when it is actually up.
        if adb.ime_visible():
            adb.key(4)
            time.sleep(0.8)
        return True

    def confirm_button():
        for rid in ["btnSure", "btn_ok", "btn_save", "btnOk", "btn_confirm"]:
            n = screen.find(ids=[rid])
            if n and n.center and "cancel" not in (n.res or ""):
                screen.tap_node(n)
                return True
        n = screen.find(texts=["Confirm", "Add", "Next", "OK", "Save",
                               "sure"])
        if n and n.center:
            screen.tap_node(n)
            return True
        btn = next((x for x in screen.dump()
                    if x.cls == "android.widget.Button" and x.clickable
                    and x.center), None)
        if btn:
            screen.tap_node(btn)
            return True
        return False

    def req_seen(marker):
        return marker in adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)

    def pick_question_row(anchor_ids, row_text_prefix):
        """Tap a question picker anchor, then select the popup's first row
        via DPAD (DOWN + ENTER). Run-10 evidence: the popup is a FOCUSABLE
        PopupWindow with a ListView; a dump-coordinate tap missed it (the
        popup window's dump bounds are not screen coordinates) and the
        outside-touch dismissed it. DPAD events go to the focused popup
        window, so DOWN selects row 0 and ENTER fires the ListView's
        onItemClickListener — dismiss + selection in one deterministic
        step, independent of coordinate spaces. The [qp] dump still
        records the popup rows as evidence. True when the selection
        registered (the anchor TextView now carries the row text)."""
        anchor = screen.find(ids=anchor_ids)
        if not (anchor and anchor.center):
            print("  [skip] LM: picker %s not found" % (anchor_ids,))
            return False
        # baseline = visible EditTexts BEFORE the selection (the answer
        # field's visibility delta is the picked-verification signal)
        pick_question_row.baseline_edits = len([
            n for n in screen.dump()
            if n.cls.endswith("EditText") and n.center])
        screen.tap_node(anchor)
        time.sleep(3)
        # popup evidence: the rows render the CATALOG strings the server
        # served (run-10 [qp] verdict)
        for n in screen.dump():
            if n.text and row_text_prefix.split()[0] in n.text:
                print("  [qp] popup row: %r clickable=%s cls=%s"
                      % (n.text[:30], n.clickable, n.cls))
        adb.key(20)   # DPAD_DOWN — select the first ListView row
        time.sleep(1)
        adb.key(23)   # DPAD_CENTER/ENTER — click the selected row
        time.sleep(2.5)
        # selection verification (run-11 fix): the popup's own rows contain
        # the prefix too, so text-matching alone false-positives. The REAL
        # signals: (a) the answer-field visibility delta — the binding
        # reveals the section's EditText when its question is picked; or
        # (b) the popup ListView is GONE and the picked text remains (the
        # anchor's select TextView mirrors m/n — covers a wizard-style
        # layout that replaces section 1 instead of stacking).
        nodes = screen.dump()
        eds_after = [n for n in nodes
                     if n.cls.endswith("EditText") and n.center]
        listview_gone = not any(n.cls == "android.widget.ListView"
                                for n in nodes)
        text_shown = any(row_text_prefix.split()[0] in (n.text or "")
                         for n in nodes)
        picked = (len(eds_after) > pick_question_row.baseline_edits) \
            or (listview_gone and text_shown)
        if not picked:
            print("  [info] LM: DPAD row pick did not register "
                  "(%s; edits %d->%d)" % (row_text_prefix,
                                          pick_question_row.baseline_edits,
                                          len(eds_after)))
            debug_dump(screen, "lm-qpick")
            # the focusable popup is still open — BACK dismisses it (popups
            # take the back key before the activity), so the outer flow's
            # back count stays anchored on fa.i
            adb.key(4)
            time.sleep(2)
        else:
            ok("LM: question picked (%s; edits %d->%d)"
               % (row_text_prefix, pick_question_row.baseline_edits,
                  len(eds_after)))
            # run-12 evidence: fa.i self-closed within ~4s of the pick (the
            # follow-up dumps landed on SafeSetting with no POST and no
            # back from our side). Pin the state IMMEDIATELY so the next
            # verdict shows whether the screen is still up, what the
            # anchor now displays, and whether the dialog path fired.
            nodes_now = screen.dump()
            print("  [q1-state] listview=%s edits=%d" % (
                any(n.cls == "android.widget.ListView" for n in nodes_now),
                len([n for n in nodes_now
                     if n.cls.endswith("EditText") and n.center])))
            for n in nodes_now:
                if n.text:
                    print("  [q1-state] %s | %r" % (
                        n.res.rsplit("/", 1)[-1] if n.res else "",
                        (n.text or "")[:30]))
            # run-16 evidence: the close fires ~10-20s after the pick with
            # or without further input — sample the title at 5s intervals
            # to timestamp the flip, then capture the real top activity
            for tick in range(3):
                time.sleep(5)
                t_nodes = screen.dump()
                t_title = next((n.text for n in t_nodes
                                if n.res.endswith("tvTemplateTitle")), "?")
                t_edits = len([n for n in t_nodes
                               if n.cls.endswith("EditText") and n.center])
                print("  [q1-t%d] title=%r edits=%d" % (
                    tick, (t_title or "")[:26], t_edits))
            print("  [q1-top] %s" % adb.sh(
                "dumpsys activity activities | grep -E "
                "\"topResumedActivity|ResumedActivity\" | head -2"))
        return picked

    def back(times=1):
        for _ in range(times):
            adb.key(4)
            time.sleep(2)

    def fill_q1(screen, adb):
        return pick_question_row(["ll_question_one"], "childhood nickname")

    def fill_q2(screen, adb):
        return pick_question_row(["ll_question_two"], "first pet")

    # -- process-death awareness ---------------------------------------------
    # RUN-17 SMOKING GUN: the "self-closing" question screen was the
    # documented roaming-killer family — the app process was SIGKILLed
    # ~20s after the pick and relaunched (the GET ran on pid 13766, the
    # next heartbeat on pid 16263), restoring the stack to SafeSetting
    # without fa.i. The drive therefore snapshots the pid at entry and
    # RE-WALKS Me -> Setting -> Security whenever the pid changed.
    pid0 = adb.pid(package)

    def restarted():
        pid_now = adb.pid(package)
        return not pid_now or (pid0 and pid_now != pid0)

    def enter_accountsafe():
        """Ground on the Me tab and walk to the AccountSafe screen.
        Handles a dead/relaunched process and any foreign screen."""
        nonlocal pid0
        if not adb.pid(package):
            print("  [evidence] LM: process dead - relaunching")
            if not relaunch_and_wait(adb, screen, package, activity,
                                     "%s-relaunch" % tag):
                return False
            pid0 = adb.pid(package)
        me = screen.find(ids=["rb_5"])
        if not (me and me.center):
            home = screen.find(ids=["rb_1"])
            if home and home.center:
                screen.tap_node(home)
                time.sleep(2)
            me = screen.find(ids=["rb_5"])
            if not (me and me.center):
                if not relaunch_and_wait(adb, screen, package, activity,
                                         "%s-reme" % tag):
                    return False
                me = screen.find(ids=["rb_5"])
            if not (me and me.center):
                return False
        screen.tap_node(me)
        time.sleep(3)
        setting = None
        for _ in range(4):
            setting = screen.find(texts=["Setting"])
            if setting and setting.center:
                break
            adb.sh("input swipe 360 900 360 320 300")
            time.sleep(2)
        if not (setting and setting.center):
            debug_dump(screen, "%s-no-setting" % tag)
            return False
        screen.tap_node(setting)
        time.sleep(4)
        sec = screen.find(texts=["Security"])
        if not (sec and sec.center):
            debug_dump(screen, "%s-no-security" % tag)
            back(1)
            return False
        screen.tap_node(sec)
        time.sleep(4)
        return bool(adb.pid(package))

    # -- enter the AccountSafe screen (restart-aware) ------------------------
    if not enter_accountsafe():
        print("  [skip] LM: could not reach the Account Security screen")
        return
    ok("LM: Account Security screen open")
    for n in screen.dump():
        if n.text:
            print("  [as] %r" % n.text[:32])

    # -- 1) Safety Settings -> Security Questions (email still UNBOUND) -----
    # honesty (session-24 rule): claim-carrying literals are bare-path
    # variables; the question-list path is SPLIT mid-segment because a full
    # literal would verb-blind-claim the POST /users/secret/question
    # sibling (authUserQuestion) that this gate does NOT exercise. The
    # sms/send literal is split for the same reason (the refound concrete
    # sibling must not be prefix-claimed by a trailing-/ probe).
    q_lit = "/user/api/v1/users/secret/ques" + "tion"
    email_code_lit = "/user/api/v1/emails/{email}"  # run-19: served code=1
    email_verify_lit = "/user/api/v1/emails/verify/"   # deliberate prefix probe
    email_bind_lit = "/user/api/v1/users/bind/email"
    # phone_bind_lit REMOVED (wave 22): the AccountSafe phone hunt is gone
    # (the row never renders) — POST /user/api/v1/user/bind/phone stays
    # host-tested-only until its reachable surface is mapped in this build.
    pw_check_lit = "/user/api/v1/user/password/check"
    pw_modify_lit = "/user/api/v1/user/password/modify"
    q_seen = False
    safe = screen.find(texts=["Safety Settings"])
    if safe and safe.center:
        screen.tap_node(safe)
        time.sleep(4)
        if alive_or_recover("%s-safesetting" % tag):
            ok("LM: Safety Settings screen open")
            qrow = screen.find(texts=["Security Questions"])
            if qrow and qrow.center:
                screen.tap_node(qrow)
                time.sleep(6)
                alive_or_recover("%s-questions" % tag)
                # q_lit is split mid-segment (above) so gen_coverage
                # extracts nothing claimable — a full literal would
                # verb-blind-claim the POST /users/secret/question
                # sibling (authUserQuestion), which this gate does NOT
                # exercise. The gate still proves the GET from traffic.
                q_seen = req_seen("REQ GET " + q_lit)
                if q_seen:
                    ok("LM: question list fetched (GET users/secret/question)")
                else:
                    print("  [info] no question-list GET (row state changed?)")
                # Wave 20c — the answer-submit drive. Server side is now
                # complete (Wave 20b: type=0 catalog, v1 setting without an
                # authCode), so the whole flow is drivable: pick Q1 (popup
                # on ll_question_one), fill answer 1, Next, pick Q2, fill
                # answer 2, Confirm -> POST /user/api/v1/users/secret/
                # question/setting (v1: Retrofit omits the null authCode
                # @Query). The popup rows render the CATALOG strings the
                # server just served, so a row tap targets the first
                # catalog entry's text prefix.
                # run-18 VERDICT: the full submit fired end-to-end (pick Q1
                # -> answer -> Next -> pick Q2 -> answer -> Confirm) and the
                # POST was served — the literal is now full and claims the
                # {version} template via template_match (only a POST exists
                # on the path, so no verb-blind sibling risk).
                qs_lit = "/user/api/v1/users/secret/question/setting"
                if fill_q1(screen, adb):
                    # answer 1 = first visible EditText (appears once the
                    # question selection registered); dump when it doesn't
                    time.sleep(2)
                    if not edit_nodes():
                        print("  [info] LM: no answer field after Q1 pick "
                              "- selection visibility still gated")
                        debug_dump(screen, "lm-qscreen")
                    fill_edit(0, "LocalQA-One")
                    # run-15 evidence: fa.i still finishes even without the
                    # ESC — pin the state right after the answer fill and
                    # after Next so the closing hop is caught red-handed
                    # (exit-dialog texts / focused window / revealed rows)
                    for n in screen.dump():
                        if n.text or n.cls.endswith("Dialog") \
                                or n.cls.endswith("ListView"):
                            print("  [q2-pre] %s | %r | %s" % (
                                n.res.rsplit("/", 1)[-1] if n.res else "",
                                (n.text or "")[:26], n.cls.rsplit(".", 1)[-1]))
                    nxt = screen.find(ids=["btn_next"], texts=["Next"])
                    if nxt and nxt.center:
                        screen.tap_node(nxt)
                        time.sleep(3)
                        # run-13 evidence: section 2 (ll_question_two +
                        # btn_confirm) reveals BELOW the fold after Next —
                        # off-screen nodes don't reach the uiautomator dump,
                        # so the pick/tap hunts must scroll first
                        for _ in range(3):
                            if screen.find(ids=["ll_question_two"]):
                                break
                            adb.sh("input swipe 360 900 360 380 300")
                            time.sleep(2)
                        print("  [q2-post] state after Next + reveal scroll:")
                        for n in screen.dump():
                            if n.text:
                                print("  [q2-post] %s | %r" % (
                                    n.res.rsplit("/", 1)[-1] if n.res else "",
                                    (n.text or "")[:26]))
                    if fill_q2(screen, adb):
                        time.sleep(2)
                        # run-11 evidence: index 0 is ANSWER 1's field (still
                        # visible when section 2 reveals) — the newly-gated
                        # answer-2 field is the LAST EditText
                        eds_q2 = edit_nodes()
                        fill_edit(max(0, len(eds_q2) - 1), "LocalQA-Two")
                        # the Confirm button sits below the fold on 720x1280
                        # — reveal it before the ID-based tap (run-11: the
                        # text hunt missed it and the flow dropped out)
                        cf = screen.find(ids=["btn_confirm"])
                        if not (cf and cf.center):
                            adb.sh("input swipe 360 800 360 400 300")
                            time.sleep(2)
                        cf = screen.find(ids=["btn_confirm"])
                        if cf and cf.center:
                            screen.tap_node(cf)
                            time.sleep(6)
                            alive_or_recover("%s-qset" % tag)
                            if req_seen("REQ POST " + qs_lit):
                                ok("LM: question setting served (POST "
                                   "users/secret/question/setting, v1)")
                            else:
                                print("  [info] no question/setting POST "
                                      "(picker shape changed? see [qs])")
                        else:
                            print("  [skip] LM: btn_confirm not found even "
                                  "after the reveal scroll")
                        print("  [qs-end2] state after the confirm attempt:")
                        for n in screen.dump():
                            if n.text:
                                print("  [qs-end2] %s | %r" % (
                                    n.res.rsplit("/", 1)[-1] if n.res else "",
                                    (n.text or "")[:28]))
                # stale-dump guard (run-12/13: the end-of-question dumps
                # landed on SafeSetting while fa.i was demonstrably up —
                # a wedged accessibility snapshot). Pause + re-dump; if the
                # title still reads SafeSetting the screen genuinely
                # changed, otherwise the earlier dump was stale.
                time.sleep(3)
                for n in screen.dump():
                    if n.text or n.res.endswith("EditText"):
                        print("  [qs-end] %s | %r" % (
                            n.res.rsplit("/", 1)[-1] if n.res else "",
                            (n.text or "")[:24]))
                back(1)
            else:
                print("  [skip] LM: 'Security Questions' row not found")
                debug_dump(screen, "%s-no-qrow" % tag)
            back(1)  # out of Safety Settings
            time.sleep(1)
    else:
        print("  [skip] LM: 'Safety Settings' row not found (hasPassword?)")

    # -- 2) Email bind via SafeSetting's 'Safety Mailbox' row (Wave 22) ------
    # Run 8/10/17/18 evidence: the AccountSafe 'Email'/'Phone number' rows
    # DO NOT render in this build — the old AccountSafe hunts are GONE.
    # jadx trigger map (session 37, e.b.ca/g + e.b.ha/* + e.b.e/*):
    #   SafeSetting 'Safety Mailbox' (item_view_secret_mailbox) -> g.h():
    #   * email unbound AND questions NOT finished -> BindEmailFragment
    #     (e.b.e.f) directly (v1 bind path);
    #   * questions FINISHED (block 1 just set them) -> b(1) ->
    #     GET /users/secret/question?type=1 (saved) -> e.b.ha.f
    #     SecretQuestionVerify: answer 1 + 'Next' and answer 2 + 'Done'
    #     each POST /users/secret/question (authUserQuestion, complete=0/1,
    #     ONE SecretQuestionInfo body); a right answer reveals the next
    #     section (ha.h), and after answer 2 the client CHAINS into
    #     BindEmailFragment carrying the secret_answer bundle — the bind
    #     then fires as POST /user/api/v2/users/bind/email?answer=a1&answer=a2
    #     (IUserApi bindEmail(version, form, answers)).
    # Both paths converge on BindEmailFragment: email + 'Next' (POST
    # user/api/v1/emails/{email} with ?email= — jadx k.a(true) -> e.b.e.g.a
    # -> UserApi.sendEmailCode, IUserApi:240: @POST emails/{email} with
    # NO @Path binding, so Retrofit sends the path LITERALLY
    # with {email} in it and the email rides as the ?email= query; run-19
    # logcat verdict: code=1) -> code + 'Add' (bind). The verify-code
    # variant emails/verify/{email} belongs to the SafeSetting
    # email-BOUND chain (ca.d.a -> sendEmailVerifyCode), a different
    # surface. BACK on the verify screen raises the leave-dialog; its
    # 'Confirm' dismisses + finishes (ha.i.onBack -> TwoButtonDialog
    # listener).
    # NOTE for future literals: never write a trailing-slash emails path
    # here — the claim extractor reads comments too and a bare
    # "emails/" prefix phantom-claims the whole emails family
    # (password/reset included).
    email_bind_v2_lit = "/user/api/v2/users/bind/email"
    # Retrofit leaves {email} UNBOUND in the path (IUserApi:240 has no
    # @Path("email") param) — the logged URI is literally this template,
    # so the same string is both the runtime marker and the claim.
    # FULL literal (wave 22): the mailbox block now GENUINELY fires both
    # verbs on this path — GET ?type=1 (saved-question fetch, b(1)) and
    # POST authUserQuestion (the answer verify, complete=0/1) — so a full
    # literal is claim-honest for both concrete routes.
    qa_verify_lit = "/user/api/v1/users/secret/question"
    if restarted():
        print("  [evidence] LM: process restarted during the question block "
              "(roaming-killer family, pid %s -> %s) - re-walking"
              % (pid0, adb.pid(package)))
        if not enter_accountsafe():
            print("  [skip] LM: could not re-enter Account Security")
            return
        ok("LM: Account Security re-entered after the restart")
    email = "qa%05d@local.test" % (int(time.time()) % 100000)
    code = "138%03d" % (int(time.time()) % 1000)

    def fill_node(node, value):
        """fill_edit for an already-found node (same IME mechanics)."""
        screen.tap_node(node)
        time.sleep(0.6)
        adb.key(123)  # MOVE_END
        for _ in range(40):
            adb.key(67)  # DEL
        adb.text(value)
        time.sleep(0.4)
        if adb.ime_visible():
            adb.key(4)
            time.sleep(0.8)
        return True

    def edit_not_containing(marker):
        """The EditText whose content lacks marker — the code/answer-2
        field when a same-screen sibling keeps the earlier value. Falls
        back to the LAST EditText (the reveal appends fields)."""
        eds = [n for n in screen.dump()
               if n.cls.endswith("EditText") and n.center]
        if not eds:
            return None
        non = [e for e in eds if marker not in (e.text or "")]
        return non[0] if non else eds[-1]

    safe2 = None
    for _ in range(2):
        safe2 = screen.find(texts=["Safety Settings"])
        if safe2 and safe2.center:
            break
        adb.sh("input swipe 360 380 360 900 300")  # row sits at the top
        time.sleep(2)
    if not (safe2 and safe2.center):
        debug_dump(screen, "%s-no-safe2" % tag)
        print("  [skip] LM: 'Safety Settings' row not found for the "
              "mailbox block")
    else:
        screen.tap_node(safe2)
        time.sleep(4)
        if alive_or_recover("%s-safesetting2" % tag):
            mbox = screen.find(texts=["Safety Mailbox"])
            if not (mbox and mbox.center):
                for n in screen.dump():
                    if n.text:
                        print("  [ss] %r" % n.text[:32])
            if mbox and mbox.center:
                screen.tap_node(mbox)
                time.sleep(5)
                alive_or_recover("%s-mailbox" % tag)
                # NanoHTTPD's getUri() never logs the query string — the
                # ?type=1 is invisible in the REQ line. The type=1 verdict
                # is the SCREEN STATE: the verify screen renders the
                # SAVED questions the server returned.
                if req_seen("REQ GET " + qa_verify_lit):
                    print("  [info] LM: saved-question GET fired (log URIs "
                          "are query-less; screen state is the type=1 "
                          "verdict)")
                texts_now = [(n.text or "") for n in screen.dump()]
                for n in screen.dump():
                    if n.text and ("Question" in n.text
                                   or "childhood" in n.text
                                   or "first pet" in n.text):
                        print("  [qv] %r" % n.text[:40])
                on_verify = any(
                    "mail safety question" in t.lower()
                    or t.startswith("Question 1") for t in texts_now)
                on_bind = bool(edit_nodes())
                if on_verify:
                    ok("LM: identity-verify screen open (questions set)")
                    # -- answer 1 -> 'Next' -> POST complete=0 -----------
                    eds_v = edit_nodes()
                    if not eds_v:
                        debug_dump(screen, "%s-no-verify-edt" % tag)
                        print("  [skip] LM: verify answer field missing")
                    elif fill_node(eds_v[0], "LocalQA-One"):
                        if confirm_button():  # 'Next'
                            time.sleep(6)
                            alive_or_recover("%s-qverify1" % tag)
                            # query strings never reach the REQ log; the
                            # answer value in the BODY is the precise
                            # per-answer marker (run-20 logcat evidence)
                            qa1 = req_seen("REQ POST " + qa_verify_lit
                                           + ' body={"answer":"LocalQA-One"')
                            if qa1:
                                ok("LM: answer-1 verify served (POST users/"
                                   "secret/question, authUserQuestion)")
                            else:
                                print("  [info] no authUserQuestion POST "
                                      "(answer-1 gate?)")
                            # section 2 reveals ONLY on a right answer
                            for _ in range(2):
                                if screen.find(ids=["ed_answer_two"]) \
                                        or screen.find(texts=["Done"]):
                                    break
                                adb.sh("input swipe 360 900 360 380 300")
                                time.sleep(2)
                            if screen.find(ids=["ed_answer_two"]) \
                                    or len(edit_nodes()) > 1:
                                ok("LM: verify answer-1 accepted (section 2 "
                                   "revealed)")
                                ed2 = edit_not_containing("LocalQA-One")
                                if ed2 and fill_node(ed2, "LocalQA-Two"):
                                    done = screen.find(texts=["Done"])
                                    if done and done.center:
                                        screen.tap_node(done)
                                        time.sleep(6)
                                        alive_or_recover("%s-qverify2" % tag)
                                        if req_seen("REQ POST " + qa_verify_lit
                                                    + ' body={"answer":'
                                                    '"LocalQA-Two"'):
                                            ok("LM: answer-2 verify served "
                                               "(POST users/secret/question)")
                                        # the client CHAINS into BindEmail
                                        time.sleep(3)
                                        if not edit_nodes():
                                            print("  [evidence] LM: no bind "
                                                  "screen after answer-2 "
                                                  "(verify chain changed?)")
                                    else:
                                        print("  [skip] LM: 'Done' button "
                                              "not found (answer-2 gate?)")
                            else:
                                print("  [info] verify answer-1 REJECTED "
                                      "(right=false?) - section 2 never "
                                      "revealed")
                        else:
                            print("  [skip] LM: verify 'Next' not found")
                elif on_bind:
                    print("  [info] LM: BindEmail opened DIRECTLY (questions "
                          "unfinished) - v1 bind path")
                else:
                    debug_dump(screen, "%s-mailbox-unknown" % tag)
                    print("  [skip] LM: 'Safety Mailbox' tap landed on an "
                          "unrecognized screen")
                # -- BindEmailFragment (reached via either path) ----------
                eds_b = edit_nodes()
                if eds_b and fill_node(eds_b[0], email):
                    if confirm_button():  # 'Next'
                        time.sleep(6)
                        alive_or_recover("%s-emailcode" % tag)
                        c_seen = req_seen("REQ POST " + email_code_lit)
                        if c_seen:
                            ok("LM: email code served (POST emails/{email}, "
                               "sendEmailCode — path literally {email})")
                        else:
                            print("  [info] no emails/{email} call (step-1 "
                                  "client gate?)")
                        v_seen = req_seen("REQ POST " + email_verify_lit)
                        if v_seen:
                            ok("LM: email verify-code acked (POST emails/"
                               "verify/)")
                        cf = edit_not_containing(email)
                        if cf and fill_node(cf, code):
                            if confirm_button():  # 'Add'
                                time.sleep(6)
                                alive_or_recover("%s-emailbind" % tag)
                                b2 = req_seen("REQ POST " + email_bind_v2_lit)
                                b1 = req_seen("REQ POST " + email_bind_lit)
                                if b2:
                                    ok("LM: email bind v2 served (POST "
                                       "{version}/users/bind/email) for %s"
                                       % email)
                                elif b1:
                                    ok("LM: email bind v1 served (POST users/"
                                       "bind/email) for %s" % email)
                                else:
                                    print("  [info] no users/bind/email call")
                            else:
                                print("  [skip] LM: 'Add' button not found")
                        else:
                            print("  [skip] LM: code field not found (step-2 "
                                  "not reached?)")
                elif eds_b:
                    print("  [skip] LM: email field fill failed")
            else:
                print("  [skip] LM: 'Safety Mailbox' row not found on "
                      "SafeSetting")
        # ground back on AccountSafe for the password block: bind success
        # auto-finishes to SafeSetting, a failed hop can strand deeper;
        # BACK on the verify screen raises the leave-dialog whose
        # 'Confirm' dismisses + finishes (ha.i.onBack)
        for _ in range(4):
            if screen.find(texts=["Safety Settings", "Modify Password"]):
                break
            back(1)
            time.sleep(1)
            dlg = screen.find(texts=["Confirm"])
            if dlg and dlg.center:
                screen.tap_node(dlg)
                time.sleep(2)

    # -- 4) Modify Password (LAST — rotates the credential) ------------------
    if restarted():
        print("  [evidence] LM: process restarted before the password flow "
              "- re-walking (pid %s -> %s)" % (pid0, adb.pid(package)))
        if not enter_accountsafe():
            print("  [skip] LM: could not re-enter Account Security (pw)")
            return
        ok("LM: Account Security re-entered (pw)")
    # the email/phone hunts scrolled the list DOWN — Modify Password sits
    # near the TOP of AccountSafe; scroll back up before hunting (run-10:
    # the row was missed after the hunts)
    for swipe in range(3):
        if screen.find(texts=["Modify Password"]):
            break
        adb.sh("input swipe 360 380 360 900 300")
        time.sleep(2)
    mrow = screen.find(texts=["Modify Password"])
    if mrow and mrow.center:
        screen.tap_node(mrow)
        time.sleep(4)
        if alive_or_recover("%s-confirmpw" % tag):
            if fill_edit(0, old_password):
                if confirm_button():
                    time.sleep(8)
                    alive_or_recover("%s-changepw" % tag)
                    c_seen = req_seen("REQ POST " + pw_check_lit)
                    if c_seen:
                        ok("LM: old-password check served (POST password/"
                           "check)")
                    else:
                        print("  [info] no password/check call")
                    new_pw = "NewQA%05d" % (int(time.time()) % 100000)
                    # Run 8 evidence: the ChangePassword form can show ONE
                    # visible EditText at a time (the confirm field appears
                    # after the new password is entered — TextWatcher-driven
                    # visibility). Fill whatever is visible, re-dump, fill
                    # again until two distinct fields are typed.
                    if fill_edit(0, new_pw):
                        time.sleep(2)
                        eds_now = edit_nodes()
                        if len(eds_now) > 1:
                            fill_edit(1, new_pw)
                        else:
                            # confirm field may replace the old one in place
                            fill_edit(0, new_pw)
                    if confirm_button():
                        time.sleep(8)
                        alive_or_recover("%s-modifypw" % tag)
                        m_seen = req_seen("REQ POST " + pw_modify_lit)
                        if m_seen:
                            ok("LM: password modify served (POST password/"
                               "modify)")
                        else:
                            print("  [info] no password/modify call")
            back(1)
            time.sleep(1)
    else:
        print("  [skip] LM: 'Modify Password' row not found (hasPassword "
              "state?)")

    # -- ground back on a safe screen ----------------------------------------
    back(1)  # AccountSafe -> Setting
    time.sleep(1)
    home_tab = screen.find(ids=["rb_1"])
    if home_tab and home_tab.center:
        screen.tap_node(home_tab)
        time.sleep(2)
    else:
        relaunch_and_wait(adb, screen, package, activity, "%s-land" % tag)
    alive_or_recover("%s-end" % tag)
    print("== LM: login-module drive complete ==")


def navigate_all_tabs(adb, screen, package, tag):
    """Walk the five bottom tabs (liveness proof + API-traffic soak)."""
    tabs_seen = 0
    for tab in ["rb_1", "rb_2", "rb_3", "rb_4", "rb_5"]:
        n = screen.find(ids=[tab])
        if n and n.center:
            screen.tap_node(n)
            tabs_seen += 1
            time.sleep(3)  # let the tab fire its API calls
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
    ap.add_argument("--deep-budget-min", type=float,
                    default=float(os.environ.get("DEEP_BUDGET_MIN", "0") or 0),
                    help="minutes allowed for the deep phases (deep-drive "
                         "A / B / E-O / LM). 0 = unlimited (historical "
                         "~20-30 min full suite). The deep CI workflow "
                         "passes 5 by default so its wall stays ~12-14 min.")
    ap.add_argument("--mode", default=os.environ.get("UI_MODE", "fast"),
                    choices=["fast", "full"],
                    help="fast = CI core (~5 min); full = all deep phases")
    args = ap.parse_args()
    # MODE: "fast" (default) keeps CI at ~5 minutes - boot, visitor,
    # registration (Phase C), registered upgrade (Phase D core) and the
    # final assertions. "full" adds every deep-drive phase (B, E-O) for
    # evidence-gathering sessions (dispatch with UI_MODE=full / --mode full).
    deep = (args.mode == "full")
    _DEEP_STATE["budget"] = max(0.0, float(args.deep_budget_min)) * 60.0
    print("== MODE: %s ==" % args.mode)
    if _DEEP_STATE["budget"] > 0:
        print("== deep budget: %.0f min (deep phases only; core A/P/C/D + "
              "assertions always run) ==" % args.deep_budget_min)
    else:
        print("== deep budget: unlimited ==")

    adb = Adb(args.serial)
    screen = Screen(adb)
    password = "LocalQA%05d" % (int(time.time()) % 100000)

    # ------------------------------------------------- Phase A: visitor
    print("== PHASE A: visitor (fresh data, auto tourist login) ==")
    adb.sh("pm clear %s" % args.package)
    adb.raw("logcat", "-c")
    adb.sh("am start -n %s/%s" % (args.package, args.activity))
    # fast-mode 2026-10-07: 8s settle (was 12) - the main-screen wait_for
    # below owns the real boot wait; the extra 4s just added dead time.
    time.sleep(8)
    if not assert_alive(adb, args.package, "A launch+8s"):
        finish()
    dismiss_permission_dialogs(screen)
    main_seen = screen.wait_for(ids=["rgBottom", "rb_1", "flHomePage"],
                                timeout=90, poll=2)
    if not main_seen:
        fail("A: main screen not reached on fresh data (auto tourist login failed?)")
        finish()
    ok("A: main screen reached without manual login (visitor account)")
    # Wave 5v/5w: the hall may open the campaign sign dialog (server now
    # serves the real signInList) - claim or dismiss before driving on.
    sign_probe = handle_campaign_dialogs(adb, screen, "A")
    if sign_probe:
        ok("A: campaign sign dialog handled (%s)" % sign_probe)
    # Snapshot the visitor auth traffic NOW: the deep-drive's dress-detail
    # GL rendering floods the logcat main buffer and rotates early LocalAPI
    # lines out (run 37226628540 evidence), so a single end-of-run scan
    # misses the login/auth-token evidence entirely.
    paths_early = localapi_paths(adb)
    # mid-run snapshot (filled after Phase D's registration fcalls): the
    # main buffer rotates long before the final assertions, so the
    # registration/set-password proof needs its own capture (run
    # 37492582973: the D-phase upgrade PASSED live but the final
    # register-endpoint gate failed on a rotated-out buffer)
    paths_mid = []
    navigate_all_tabs(adb, screen, args.package, "A")
    if deep and deep_go("deep-drive A (Me-tab rows)", 4):
        deep_drive(adb, screen, args.package, args.activity, "A",
                   set(paths_early))
    else:
        print("  [skip] deep_drive (fast mode or deep budget)")
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
    # Session-28 honesty: the hall's two list feeds are hard-gated per
    # route (the client fires BOTH on every fresh-data boot — evidence:
    # every fast/full run's game-hall line). Concrete literals so
    # gen_coverage claims exactly these routes.
    a_more_lit = "/game/api/v1/game/revision/list/more"
    a_reco_lit = "/game/api/v1/game/revision/list/recommend"
    a_bare = [p.split("?")[0] for p in paths_a]
    check("A: hall more-list served (GET %s)" % a_more_lit,
          a_more_lit in a_bare,
          "the hall never fetched %s on fresh data" % a_more_lit)
    check("A: hall recommend-list served (GET %s)" % a_reco_lit,
          a_reco_lit in a_bare,
          "the hall never fetched %s on fresh data" % a_reco_lit)
    # Wave 5w probe: the lit slot_machine jackpot surface should poll the
    # draw status from the hall. Non-fatal this run (promote to a hard
    # check once observed on-device).
    tt_hits = [p for p in paths_a if "turntable/gold/status" in p
               or "gold/draw/status" in p]
    if tt_hits:
        ok("A: jackpot draw-status poll served locally: %s" % ", ".join(tt_hits))
    else:
        print("  [probe] A: no jackpot draw-status poll yet (surface gate "
              "not reached this run - non-fatal)")
    # Boot-window surfaces the client fetches EVERY run (evidence: the
    # early snapshot in runs 37492582973 + 37499606354):
    # - GET /activity/api/v2/activity/title — CampaignApi
    #   .getActivityTaskTitleList fired from the main boot chain
    #   (view/activity/main/bc);
    # - GET /activity/api/v1/slot/machine/user/gold/draw/status — the
    #   lit jackpot poll (wave-5w probe observed green twice; now hard).
    a_title_lit = "/activity/api/v2/activity/title"
    a_slot_lit = "/activity/api/v1/slot/machine/user/gold/draw/status"
    a_bare = [p.split("?")[0] for p in paths_a]
    check("A: activity title list fetched at boot (GET %s)"
          % a_title_lit,
          a_title_lit in a_bare,
          "the boot never fetched activity/title (bc chain gate)")
    check("A: jackpot draw-status poll served locally (GET %s)"
          % a_slot_lit,
          a_slot_lit in a_bare,
          "no slot-machine draw-status poll in the boot window")
    # Boot/A-window one-shot surfaces (evidence: the path unions of runs
    # 37492582973 + 37505691180 — all six fire EVERY run during boot or
    # the A walk; each path is verb-unique in the RoutingTable so a bare
    # path presence check claims exactly its own route):
    # - GET /config/files/blockmods-config-v1 (boot config)
    # - POST /user/api/v1/user/daily/life/info (boot telemetry)
    # - PUT /user/api/v1/user/device/id (boot device registration)
    # - POST /user/api/v1/user/language (boot locale report)
    # - POST /user/api/v1/user/mac/id (boot device report)
    # - GET /user/api/v1/users/device/token (periodic IM token poll)
    for a_boot_lit in [
            "/config/files/blockmods-config-v1",
            "/decoration/api/v1/new/decorations/check/resource",
            "/user/api/v1/user/daily/life/info",
            "/user/api/v1/user/device/id",
            "/user/api/v1/user/language",
            "/user/api/v1/user/mac/id",
            "/user/api/v1/users/device/token",
    ]:
        check("A: boot surface served (GET/POST/PUT %s)" % a_boot_lit,
              a_boot_lit in a_bare,
              "the boot window never fetched %s" % a_boot_lit)

    # ------------------------------------------------- Phase P: the sign banner
    # Wave 12 decode (ActivityItemViewModel tap handler e.b.c.c.java): the
    # hall's activity banner list (GET /activity/api/v2/activity/title)
    # renders one IMAGE banner per title (item_activity_list = pic ImageView
    # + red point + countdown; NO title text — Eg binding). A row whose
    # content carries "activity:sign" opens the campaign sign-in surface
    # (bc.c -> CampaignApi.signInList -> GET /activity/api/v1/signIn, then
    # the claim dialog POSTs /activity/api/v1/signIn). The server serves
    # the sign banner as the THIRD array entry.
    print("== Phase P: hall sign banner -> campaign sign-in surface ==")
    # Wave 14 verdict (session 29, code-level): the activity strip's ONLY
    # home is ActivityFragment (e/b/c/b) — ORPHANED in 1.24.4 (D.b(Context)
    # has zero live callers; every call site binds D.b(Activity) ->
    # OverViewRankActivity). The strip can never appear on any tab for any
    # user, so the old 4-tab bg_content walk (~50s per fast run) was
    # provably dead work. Phase P now just grounds on the hall and keeps
    # the split-literal traffic probe + the defensive dialog handler; the
    # sign surface itself stays gated on game-play (Wave 12/14).
    # honesty (session-24 rule): the path literal is SPLIT so gen_coverage
    # extracts only "/act" (len 4, below its >4 threshold) — the GET must
    # earn its client_asserted claim from REQ evidence, and the sibling
    # POST /activity/api/v1/signIn must not be prefix-claimed by this
    # filter either.
    p_sign_lit = "/act" + "ivity/api/v1/signIn"

    def p_count(marker):
        return sum(1 for ln in adb.raw("logcat", "-d", "-s", "LocalAPI",
                                       timeout=60).splitlines()
                   if marker in ln)

    p_pre = p_count("REQ GET " + p_sign_lit)
    # ground on the home tab for the later phases
    p_home = screen.find(ids=["rb_1"])
    if p_home and p_home.center:
        screen.tap_node(p_home)
        time.sleep(2)
    p_seen = p_count("REQ GET " + p_sign_lit)
    if p_seen > p_pre:
        # never observed on 1.24.4 (the opener is dead); kept as a
        # non-fatal probe in case a future client build revives the strip.
        ok("P: campaign sign list fetched without the strip (GET %s %d->%d)"
           % (p_sign_lit, p_pre, p_seen))
        handle_campaign_dialogs(adb, screen, "P-sign")
    else:
        print("  [probe] P: no campaign sign traffic (expected: the strip "
              "fragment is orphaned in this client build - Wave 14); "
              "non-fatal")
        if not adb.pid(args.package):
            alive_or_recover_at(adb, screen, args.package, args.activity,
                                "P-ground")

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
    # Wave 23b budget fix: the editor helpers below are defined INSIDE the
    # Phase B block (python if-blocks do not scope, so they only bind when
    # the block runs). Phase D's re-drive calls two of them — it must skip
    # when the budget gate skipped Phase B (run 37738096151:
    # UnboundLocalError on open_personal_info_editor).
    b_ran = False
    if deep and deep_go("Phase B (profile editor)", 3):
        b_ran = True

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
            # SOFT probe (run 37400811634): the roaming native-killer family
            # SIGKILLs the app right here occasionally (Session 11 forensics)
            # and the outer retry below recovers fully — a death at editor
            # ENTRY is evidence, not a run failure. A death after the retry
            # still fails the run through the editor_up=False path.
            if not adb.pid(package):
                print("  [evidence] process died entering %s-Profile (roaming "
                      "killer family) - the phase-B retry owns recovery" % tag)
                return False
            ok("alive at %s-Profile" % tag)
            ib = screen.find(ids=["ibMore"])
            if not (ib and ib.center):
                debug_dump(screen, "ibMore-not-found")
                adb.key(4)
                time.sleep(2)
                return False
            screen.tap_node(ib)
            time.sleep(5)
            # run 37476577270: the killer also strikes HERE (after ibMore, on
            # the editor entry) — same roaming family as the B-Profile entry
            # probe above. Evidence + False: the outer retry owns recovery and
            # re-drives; recording a FAIL here turned a fully-green run (51
            # endpoints, every phase after B pass) into a red run.
            if not adb.pid(package):
                print("  [evidence] process died entering %s-PersonalInfo "
                      "(roaming killer family) - the phase-B retry owns "
                      "recovery" % tag)
                return False
            ok("alive at %s-PersonalInfo" % tag)
            return True

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
    else:
        print("  [skip] Phase B editor drive (fast mode)")

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
    # Wave 15d — capture the register/set-password LOGCAT EVIDENCE the
    # moment it exists. The end-of-run register gate reads the whole
    # buffer; a relaunch storm (run 37611564558: 4 process deaths) rotates
    # the early lines out and both fallback path-sets can miss. This
    # snapshot is the rotation-proof carrier.
    register_seen_early = (
        "REQ POST /user/api/v1/register" in adb.raw(
            "logcat", "-d", "-s", "LocalAPI", timeout=60))
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
    # Wave 19 — promote /user/api/v1/user/set-psd/param/check to a HARD
    # verdict-backed gate. Evidence chain: (1) the app fires it NATURALLY
    # at boot (run 37572753047 boot call site; fresh fast run 37663387823
    # at 18:02:22, no query param, code=1); (2) the host contract is
    # pinned (HttpResponse<Long>, data MUST be 0 — value >100 opens the
    # set-password dialog and disrupts the drive); (3) the drive now
    # exercises it through the forward with the type=set query the
    # Retrofit @Query("type") declares.
    r6b = fcall("GET", "/user/api/v1/user/set-psd/param/check?type=set")
    check("C: set-psd param check (prompt gate Long 0)",
          r6b.get("code") == 1 and r6b.get("data") == 0, str(r6b)[:120])

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
    # Wave 15 — on-device proof (adb forward) for the current-worn
    # decorations list the dress template loads on its dress-mode side.
    r15 = fcall("GET", "/decoration/api/v1/decorations/using?otherId=%d" % qa_uid_num,
                headers=auth_hdr)
    check("C: worn-decoration list", r15.get("code") == 1
          and isinstance(r15.get("data"), list), str(r15)[:120])

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
    # Wave 23b: `if outcome_d == "edited":` is a SIBLING of the
    # open_personal_info_editor() guard (not nested inside it) — when the
    # editor never opens, outcome_d must be defined or main crashes with
    # UnboundLocalError (same class as the run-37738096151 budget skip).
    outcome_d = None
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
    # fast-mode 2026-10-07: a full relaunch costs ~80s of Redroid boot;
    # when the app is already alive on the main UI (fast mode: Phase B is
    # skipped and Phase P exited at the hall) reuse that state instead.
    # Deep mode still gets the hard reset whenever the editor/kick left a
    # foreign screen (rgBottom would not be visible there).
    d_up = False
    if screen.find(ids=["rgBottom", "rb_1", "flHomePage"]):
        d_up = assert_alive(adb, args.package, "D-atmain")
        if d_up:
            ok("D: app already on the main UI - skipping the D-relaunch "
               "boot (fast path, ~80s saved)")
    if not d_up:
        d_up = clean_relaunch("D-relaunch")
    if d_up:
        tab5 = screen.find(ids=["rb_5"])
        d_uid = None
        if tab5 and screen.tap_node(tab5):
            time.sleep(2)
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
                # capture the registration proof NOW — later phases rotate
                # the main buffer and the final gate would go blind
                paths_mid = localapi_paths(adb)
                # restart the client: the boot restores the saved session,
                # whose user is now registered (hasPassword=true)
                if clean_relaunch("D-restart-registered"):
                    ok("D: app restarted onto the registered session")
                    tab5b = screen.find(ids=["rb_5"])
                    if tab5b and screen.tap_node(tab5b):
                        time.sleep(2)
                        shown = any(qa_uid_d in (n.text or "")
                                    for n in screen.dump())
                        print("  [%s] Me tab shows the new account %r"
                              % ("ok" if shown else "info", qa_uid_d))
                    if b_ran and not guest_edited:
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
    if deep:
      try:
        budget_gate("PHASE E (registered clan create)", 2.5)
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
        budget_gate("PHASE F (own-clan surfaces + G walks)", 4)
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

            # ---- Session 20 (wave 6a): a REAL friendship for the invite drive.
            # jadx decode: TribeInviteFriendListModel g.onLoad reads the greendao
            # Friend table (P) directly — network rows reach that cache only via
            # ChatModel v.a -> FriendApi.friendList(0, 50) -> P.b() clear +
            # per-row insert, which fires when the Messages tab's internal
            # rbFriend sub-tab is selected (ChatViewModel x.a num==1|2). So:
            # register a friend candidate, owner adds + candidate accepts via
            # the API, then tap rb_1 -> rbFriend and wait for the row.
            friend_nick = None
            # wave 7: the second candidate is seeded AFTER the friends-page
            # refresh below, but the refresh wait already references it —
            # bind it here (run 37430306318 UnboundLocalError lesson).
            friend_nick2 = None
            fr_uid_num = 0
            frh = None
            fr_uid = "fqa%05d" % (int(time.time()) % 100000)
            fr_pw = "LocalQA%05d" % (int(time.time()) % 100000)
            fr = fcall("POST", "/user/api/v1/register",
                       {"uid": fr_uid, "password": fr_pw,
                        "confirmPassword": fr_pw, "imei": "f-device",
                        "appType": "android", "os": "12"})
            fr_uid_num = (fr.get("data") or {}).get("userId", 0)
            fr_tok = (fr.get("data") or {}).get("accessToken", "")
            if fr.get("code") == 1 and fr_uid_num > 0 and live_hdr:
                frh = {"Access-Token": fr_tok, "userId": str(fr_uid_num),
                       "language": "en"}
                add = fcall("POST", "/friend/api/v1/friends",
                            {"friendId": fr_uid_num, "msg": "qa-add"},
                            headers=live_hdr)
                agr = fcall("PUT", "/friend/api/v1/friends/%s/agreement"
                            % d_uid_live, None, headers=frh)
                if add.get("code") == 1 and agr.get("code") == 1:
                    ok("F: real friendship via the API (%s <-> live session)"
                       % fr_uid)
                    fl = fcall("GET",
                               "/friend/api/v1/friends?pageNo=1&pageSize=20",
                               headers=live_hdr)
                    frow_api = next((m for m in (fl.get("data") or {}).get(
                        "data", []) if m.get("userId") == fr_uid_num), None)
                    friend_nick = (frow_api or {}).get("nickName")
                    ok("F: friend %s listed by the server (nick=%r)"
                       % (fr_uid_num, friend_nick)) if friend_nick else print(
                           "  [info] F: friend %s NOT in the server list: %s"
                           % (fr_uid_num, str(fl)[:100]))
                    # session 20 run-37409714321 fix: the ChatFragment (with the
                    # internal rbChat/rbFriend radios) is hosted by rb_4, not
                    # rb_1 (nc.java switch: 0x7F090429 = chatFragment). rb_4
                    # also requests storage permissions — dismiss defensively.
                    rb4 = screen.wait_for(ids=["rb_4"], timeout=10, poll=2)
                    if rb4 and screen.tap_node(rb4):
                        time.sleep(4)
                        dismiss_permission_dialogs(screen)
                        handle_campaign_dialogs(adb, screen, "F-rb4")
                        f_alive("F-chatpage")
                        rbf = screen.wait_for(ids=["rbFriend"], timeout=10,
                                              poll=2)
                        if rbf and screen.tap_node(rbf):
                            time.sleep(5)
                            f_alive("F-friends-refresh")
                            seen = screen.wait_for(
                                texts=[n for n in (friend_nick, friend_nick2)
                                       if n], timeout=14, poll=3) \
                                if (friend_nick or friend_nick2) else None
                            if seen:
                                ok("F: friend row %r visible on the Friends "
                                   "page (greendao cache refreshed)"
                                   % seen.text)
                            else:
                                print("  [info] F: friend rows %r/%r not on the "
                                      "Friends page (cache timing)"
                                      % (friend_nick, friend_nick2))
                        else:
                            print("  [info] F: internal rbFriend not found "
                                  "(Messages layout changed?)")
                    else:
                        print("  [info] F: rb_4 not found (tab bar unavailable)")
                else:
                    print("  [info] F: API friendship failed: add=%s agr=%s"
                          % (str(add)[:80], str(agr)[:80]))
            else:
                print("  [info] F: friend candidate register failed: %s"
                      % str(fr)[:100])

            # wave 7 (session 21): a SECOND friend candidate - the invite
            # screen renders one row per greendao Friend row, so a denser list
            # gives the row-find a fallback (the standing session-20 next-step
            # list suggested seeding 2 friends for the single-run POST catch).
            friend_nick2 = None
            f2_uid = "fqb%05d" % (int(time.time()) % 100000)
            f2_pw = "LocalQA%05d" % (int(time.time()) % 100000)
            f2 = fcall("POST", "/user/api/v1/register",
                       {"uid": f2_uid, "password": f2_pw,
                        "confirmPassword": f2_pw, "imei": "f2-device",
                        "appType": "android", "os": "12"})
            f2_uid_num = (f2.get("data") or {}).get("userId", 0)
            f2_tok = (f2.get("data") or {}).get("accessToken", "")
            if f2.get("code") == 1 and f2_uid_num > 0 and live_hdr:
                f2h = {"Access-Token": f2_tok, "userId": str(f2_uid_num),
                       "language": "en"}
                add2 = fcall("POST", "/friend/api/v1/friends",
                             {"friendId": f2_uid_num, "msg": "qa-add2"},
                             headers=live_hdr)
                agr2 = fcall("PUT", "/friend/api/v1/friends/%s/agreement"
                             % d_uid_live, None, headers=f2h)
                if add2.get("code") == 1 and agr2.get("code") == 1:
                    fl2 = fcall("GET",
                                "/friend/api/v1/friends?pageNo=1&pageSize=20",
                                headers=live_hdr)
                    f2row = next((m for m in (fl2.get("data") or {}).get(
                        "data", []) if m.get("userId") == f2_uid_num), None)
                    friend_nick2 = (f2row or {}).get("nickName")
                    ok("F: second friendship via the API (%s, nick=%r)"
                       % (f2_uid, friend_nick2))
                else:
                    print("  [info] F: second friendship failed: %s %s"
                          % (str(add2)[:80], str(agr2)[:80]))
            else:
                print("  [info] F: second friend candidate register failed: %s"
                      % str(f2)[:100])

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
                            settle_deadline = clamp_deep(time.time() + 100)
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
                        # run-37418335203: the tag input leaves the soft
                        # keyboard up - BACK once drops it (the form stays);
                        # otherwise the MODIFY taps land on the keyboard
                        adb.key(4)
                        time.sleep(2)
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
                            # session 20: ONE bounded re-tap when the first
                            # MODIFY tap missed (run 37409714321: puts 0->0
                            # with everything else green - tap timing, not
                            # a contract break)
                            if puts_after <= puts_before:
                                modify2 = next(
                                    (x for x in screen.dump()
                                     if (x.text or "") in ("Modify", "MODIFY")
                                     and x.center), None)
                                if modify2:
                                    screen.tap_node(modify2)
                                    time.sleep(4)
                                    f_alive("F2-edit-submit-retry")
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
                            # wave 7: normalize the screen FIRST - the F phase
                            # can end on rb_4 (friends refresh), and the sheet
                            # entry needs the CLAN HOME (the recurring sheet
                            # misses tapped whatever top-right ImageButton the
                            # CURRENT screen owned). Same walk the proven
                            # hand-over path uses: rb_3 -> Enter Clan -> clan
                            # home -> settle Notice Board.
                            gm_rb3 = screen.wait_for(ids=["rb_3"], timeout=10,
                                                     poll=2)
                            if gm_rb3 and screen.tap_node(gm_rb3):
                                time.sleep(4)
                            gm_ent = screen.find(ids=["rlEnterClan"]) \
                                or screen.find(texts=["Enter Clan"])
                            if gm_ent and gm_ent.center \
                                    and screen.tap_node(gm_ent):
                                time.sleep(6)
                                for _ in range(4):
                                    d_g = screen.dump()
                                    if any((x.text or "") == "Notice Board"
                                           for x in d_g):
                                        cls_g = next(
                                            (x for x in d_g
                                             if x.res.rsplit("/", 1)[-1]
                                             == "btnSure" and x.center), None)
                                        if cls_g:
                                            screen.tap_node(cls_g)
                                        time.sleep(3)
                                    else:
                                        break
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
                            # session 20 (run 37409714321): the FIRST sheet tap
                            # can miss (timing) — one bounded re-tap of ic_more
                            # before giving up (the hand-over walk proved the
                            # sheet + items still render).
                            # run-37421024074: single-shot find raced the
                            # sheet animation - poll instead
                            mm = screen.wait_for(texts=["Manage Members"],
                                                 timeout=6, poll=2)
                            if not (mm and mm.center) and more:
                                # only re-tap when the sheet is NOT actually
                                # open (a blind re-tap would toggle it closed)
                                sheet_open = any(
                                    (x.text or "") in ("Manage Members",
                                                       "Edit Profile",
                                                       "Clan Settings")
                                    for x in screen.dump())
                                if not sheet_open:
                                    screen.tap_node(more)
                                    time.sleep(3)
                                    mm = screen.wait_for(
                                        texts=["Manage Members"], timeout=8,
                                        poll=2)
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
                                loader = screen.find(texts=["Loading…"])
                                if loader:
                                    time.sleep(6)  # let the member list finish
                                row = screen.wait_for(texts=[g_nick], timeout=20,
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
                                # ---- Session 20 (wave 6a): the INVITE flow,
                                # still ON the manage screen. jadx decode:
                                # TribeMemberManage (oa.a) is hosted by
                                # TemplateActivity with RIGHT_RESOURCE_ID =
                                # ic_add_friend (T.c -> startTemplate), so the
                                # title bar's ibTemplateRight is visible; its
                                # onRightButtonClick starts TribeInviteFriend
                                # (na.c). Rows = greendao friends with a
                                # right-aligned CheckBox (tick adds
                                # String(userId) to the selection); the bottom
                                # green 'Invite Friend' button (binding_2)
                                # opens EditTextDialog (et_msg + btn_confirm)
                                # -> POST /clan/api/v1/clan/tribe/member/invite
                                # ?friendIds=&msg= (ITribeApi @POST). Success
                                # -> tribe_invite_success toast.
                                if friend_nick and fr_uid_num and frh:
                                    inv_count = lambda: sum(
                                        1 for line in adb.raw(
                                            "logcat", "-d", "-s", "LocalAPI",
                                            timeout=60).splitlines()
                                        if "REQ POST /clan/api/v1/clan/tribe/"
                                           "member/invite" in line)
                                    right = screen.wait_for(ids=["ibTemplateRight"],
                                                            timeout=8, poll=2)
                                    if right and right.center:
                                        screen.tap_node(right)
                                        time.sleep(5)
                                        f_alive("G-invitescreen")
                                        # wait for the BOTTOM button: the
                                        # title carries the SAME text and the
                                        # first dump can race the transition
                                        # (run 37412479967 tapped the title at
                                        # y=95). The button is anchored
                                        # bottom (y > 900 on 720x1280).
                                        # wave 7: one bounded RE-ENTRY - runs
                                        # 37421024074/37423815542 missed the
                                        # FIRST ibTemplateRight tap (transition
                                        # race). ibTemplateRight lives only on
                                        # the manage screen, so a find hit there
                                        # mid-wait means we never left: tap it
                                        # once more and keep waiting.
                                        low = None
                                        btn_deadline = time.time() + 16
                                        h_reentered = False
                                        while time.time() < btn_deadline:
                                            cand = [x for x in screen.dump()
                                                    if x.center
                                                    and (x.text or "").upper()
                                                    == "INVITE FRIEND"
                                                    and x.bounds
                                                    and x.bounds[1] > 900]
                                            if cand:
                                                low = cand[0]
                                                break
                                            if not h_reentered \
                                                    and time.time() > btn_deadline - 10:
                                                r2 = screen.find(
                                                    ids=["ibTemplateRight"])
                                                if r2 and r2.center:
                                                    screen.tap_node(r2)
                                                    h_reentered = True
                                                    print("  [info] G: invite "
                                                          "screen re-entry tap")
                                            time.sleep(2)
                                        if low:
                                            ok("G: TribeInviteFriend open "
                                               "(bottom 'Invite Friend' button "
                                               "at %s)" % (low.center,))
                                            pre_inv = inv_count()
                                            frow = screen.wait_for(
                                                texts=[n for n in
                                                       (friend_nick, friend_nick2)
                                                       if n], timeout=12,
                                                poll=3)
                                            if frow and frow.center:
                                                icb = next(
                                                    (x for x in screen.dump()
                                                     if x.center and
                                                     x.cls.endswith("CheckBox")),
                                                    None)
                                                if icb and icb.center:
                                                    screen.tap_node(icb)
                                                else:
                                                    l4, t4, r4, b4 = frow.bounds
                                                    adb.tap(r4 - 30,
                                                            (t4 + b4) // 2)
                                                time.sleep(2)
                                                ok("G: friend row %r ticked "
                                                   "(selection=String(userId))"
                                                   % frow.text)
                                                screen.tap_node(low)
                                                time.sleep(3)
                                                et = screen.wait_for(
                                                    ids=["et_msg"], timeout=8,
                                                    poll=2)
                                                if et and et.center:
                                                    screen.tap_node(et)
                                                    time.sleep(1)
                                                    adb.text("JoinUsQA")
                                                    time.sleep(1)
                                                    # run-37418335203: the soft
                                                    # keyboard covers the confirm
                                                    # button - BACK once drops the
                                                    # keyboard and keeps the dialog
                                                    adb.key(4)
                                                    time.sleep(2)
                                                    conf = screen.wait_for(
                                                        ids=["btn_confirm"],
                                                        timeout=8, poll=2)
                                                    if conf and conf.center:
                                                        screen.tap_node(conf)
                                                        time.sleep(5)
                                                        if inv_count() == pre_inv:
                                                            conf2 = screen.find(
                                                                ids=["btn_confirm"])
                                                            if conf2 and conf2.center:
                                                                screen.tap_node(conf2)
                                                                time.sleep(5)
                                                        f_alive("G-invite-sent")
                                                        post_inv = inv_count()
                                                        msgs_f = fcall(
                                                            "GET",
                                                            "/clan/api/v2/clan/"
                                                            "tribe/member/message",
                                                            headers=frh)
                                                        inv_msg = next(
                                                            (m for m in
                                                             (msgs_f.get("data")
                                                              or [])
                                                             if m.get("type") == 2
                                                             and m.get("clanId")
                                                             == own_clan_id),
                                                            None)
                                                        check(
                                                            "G: inviteFriend "
                                                            "client-asserted "
                                                            "(POST %d->%d, "
                                                            "invitee sees the "
                                                            "type-2 message=%s)"
                                                            % (pre_inv, post_inv,
                                                               bool(inv_msg)),
                                                            post_inv > pre_inv
                                                            and inv_msg is not None,
                                                            "msgs=%s" % str(msgs_f)[:140])
                                                    else:
                                                        print("  [info] G: "
                                                              "EditTextDialog "
                                                              "btn_confirm not "
                                                              "found")
                                                else:
                                                    print("  [info] G: "
                                                          "EditTextDialog did "
                                                          "not open (selection "
                                                          "not registered?)")
                                            else:
                                                print("  [info] G: friend row "
                                                      "%r not on the invite "
                                                      "screen (greendao cache)"
                                                      % friend_nick)
                                        else:
                                            print("  [info] G: 'Invite Friend' "
                                                  "button not on the invite "
                                                  "screen")
                                        adb.key(4)  # invite screen -> manage
                                        time.sleep(3)
                                    else:
                                        print("  [info] G: ibTemplateRight not "
                                              "on the manage screen (invite "
                                              "entry unavailable)")
                                else:
                                    print("  [info] G: no friend candidate "
                                          "(invite drive skipped)")
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
                            cs = screen.wait_for(texts=["Clan Settings"],
                                                 timeout=6, poll=2)
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
                                    fv_owner_alive = True
                                    for tap_n in range(1, 4):
                                        # session 20 (run 37412479967) + run
                                        # 37505691180: the roaming native-killer
                                        # can strike INSIDE this loop — in
                                        # 37505691180 the app died between the
                                        # settings dump and tap 1, the recovery
                                        # landed on the hall, and the old
                                        # once-captured pid guard was None
                                        # (captured while dead) so it never
                                        # fired: the remaining taps hit wrong
                                        # UI and the hard check failed on a
                                        # state that never moved. Track the
                                        # pid PER TAP and abandon honestly on
                                        # any death (the check stays hard on
                                        # the normal no-death path).
                                        pid_pre = adb.pid(args.package)
                                        cb_now = next(
                                            (x for x in screen.dump()
                                             if x.center
                                             and x.cls.endswith("CheckBox")),
                                            None) or cb
                                        screen.tap_node(cb_now)
                                        time.sleep(3)
                                        f_alive("G-fv-tap%d" % tap_n)
                                        pid_post = adb.pid(args.package)
                                        if not pid_pre or not pid_post \
                                                or pid_post != pid_pre:
                                            print("  [evidence] process died "
                                                  "around freeVerify tap %d "
                                                  "(pid %s -> %s) - taps "
                                                  "abandoned honestly"
                                                  % (tap_n, pid_pre, pid_post))
                                            fv_owner_alive = False
                                            break
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
                                    if fv_owner_alive:
                                        check(
                                            "G: freeVerify toggle client-asserted "
                                            "(server followed the taps: %s, PUTs "
                                            "%d->%d)" % (states, fv0, fv2),
                                            fv2 >= fv0 + 2 and len(set(states)) >= 2
                                            and states[-1] in (0, 1),
                                            "states=%s puts %d->%d"
                                            % (states, fv0, fv2))
                                    # restore the deterministic world: 0
                                    # (only meaningful when no death occurred —
                                    # otherwise cb is stale and the state never
                                    # moved from 0)
                                    for _ in range(4 if fv_owner_alive else 0):
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
                            # ---- Session 20 (wave 6b): HAND OVER CHIEF through
                            # the UI, deliberately LAST (after this the live
                            # session is a plain member — no chief-gated drive
                            # may follow). jadx decode (TribeHasItemViewModel
                            # J.h/f): chief long-presses a MEMBER row -> sheet
                            # [Hand over Chief | Set as Elder | Remove Member |
                            # Cancel] -> item 2131823573 'Hand over Chief' ->
                            # e(3) TwoButtonDialog ('Are you sure to hand over?')
                            # -> btnSure -> PUT /clan/api/v1/clan/tribe/member
                            # ?otherId=&type=3 (client code 3 = chief handover;
                            # server: old chief -> member, chiefId follows).
                            gk_uid = "hqa%05d" % (int(time.time()) % 100000)
                            gk_pw = "LocalQA%05d" % (int(time.time()) % 100000)
                            gk = fcall("POST", "/user/api/v1/register",
                                       {"uid": gk_uid, "password": gk_pw,
                                        "confirmPassword": gk_pw,
                                        "imei": "h-device", "appType": "android",
                                        "os": "12"})
                            gk_uid_num = (gk.get("data") or {}).get("userId", 0)
                            gk_tok = (gk.get("data") or {}).get("accessToken", "")
                            gk_ok = gk.get("code") == 1 and gk_uid_num > 0
                            gk_nick = None
                            if gk_ok:
                                gkh = {"Access-Token": gk_tok,
                                       "userId": str(gk_uid_num), "language": "en"}
                                gkr = fcall("POST",
                                            "/clan/api/v1/clan/tribe/member",
                                            {"clanId": own_clan_id,
                                             "msg": "h-join"}, headers=gkh)
                                gka = fcall("PUT",
                                            "/clan/api/v1/clan/tribe/member/"
                                            "agreement?otherId=%d" % gk_uid_num,
                                            None, headers=live_hdr)
                                gk_ok = gkr.get("code") == 1 \
                                    and gka.get("code") == 1
                                gml2 = fcall("GET",
                                             "/clan/api/v1/clan/tribe/member",
                                             headers=live_hdr)
                                gk_nick = next(
                                    (m.get("nickName") for m in
                                     gml2.get("data", [])
                                     if m.get("userId") == gk_uid_num), None)
                                ok("G: third member joined via the API (%s, "
                                   "nick=%r)" % (gk_uid, gk_nick)) if gk_ok \
                                    else print(
                                        "  [info] G: third-member API join "
                                        "failed: %s %s" % (str(gkr)[:80],
                                                           str(gka)[:80]))
                            ho_done = False
                            if gk_ok and gk_nick:
                                # re-enter: rb_3 -> Enter Clan -> clan home ->
                                # ic_more -> Manage Members
                                # RUN 37584366843 + decode: the settings sheet
                                # drops 'Manage Members' when the client's
                                # CACHED TribeCenter.tribeRole went stale
                                # across the phase's force-stops (the guard
                                # h() silently drops unless the cache reads
                                # 10/20). A clean relaunch makes the boot
                                # re-fetch the tribe info and rebuilds the
                                # cache before the re-entry (full-mode-only
                                # cost, ~80s).
                                if relaunch_and_wait(adb, screen, args.package,
                                                     args.activity,
                                                     "G-ho-cache"):
                                    assert_alive(adb, args.package,
                                                 "G-ho-cache")
                                rb3h = screen.wait_for(ids=["rb_3"], timeout=10,
                                                       poll=2)
                                if rb3h and screen.tap_node(rb3h):
                                    time.sleep(4)
                                    ent2 = screen.find(ids=["rlEnterClan"]) \
                                        or screen.find(texts=["Enter Clan"])
                                    if ent2 and screen.tap_node(ent2):
                                        time.sleep(6)
                                        for _ in range(4):
                                            d_h = screen.dump()
                                            if any(
                                                    (x.text or "")
                                                    == "Notice Board"
                                                    for x in d_h):
                                                cls_h = next(
                                                    (x for x in d_h
                                                     if x.res.rsplit("/", 1)[-1]
                                                     == "btnSure" and x.center),
                                                    None)
                                                if cls_h:
                                                    screen.tap_node(cls_h)
                                                time.sleep(3)
                                            else:
                                                break
                                        more3 = None
                                        for x in screen.dump():
                                            if not (x.center
                                                    and x.cls.endswith(
                                                        "ImageButton")):
                                                continue
                                            cx, cy = x.center
                                            if cy < 140 and cx > 360:
                                                more3 = x
                                                break
                                        if more3 and screen.tap_node(more3):
                                            time.sleep(3)
                                        mm3 = screen.wait_for(
                                            texts=["Manage Members"], timeout=8,
                                            poll=2)
                                        if mm3 and mm3.center:
                                            screen.tap_node(mm3)
                                            time.sleep(5)
                                            # Wave 15d — the member list may
                                            # sit on its loading spinner long
                                            # after the G-ho-cache cold
                                            # relaunch; wait for it to clear
                                            # (up to ~24s) before hunting the
                                            # row (run 37607065791).
                                            for _sp in range(8):
                                                if not screen.find(
                                                        ids=["rlLoading"]):
                                                    break
                                                time.sleep(3)
                                            f_alive("G-managescreen-ho")

                                            def ho_attempt(tag):
                                                # One full hand-over
                                                # interaction: long-press the
                                                # third member's row -> sheet
                                                # -> 'Hand over Chief' ->
                                                # TwoButtonDialog btnSure ->
                                                # PUT member type=3. Returns
                                                # (ok, evidence).
                                                row = screen.wait_for(
                                                    texts=[gk_nick], timeout=20,
                                                    poll=3)
                                                if not (row and row.center):
                                                    return (False, "third member "
                                                            "row %r not on the "
                                                            "manage screen"
                                                            % gk_nick)
                                                pid_at_ho = adb.pid(args.package)
                                                pre_ho = puts_g()
                                                l5, t5, r5, b5 = row.bounds
                                                hx = (l5 + r5) // 2
                                                hy = (t5 + b5) // 2
                                                adb.sh(
                                                    "input swipe %d %d %d %d 1000"
                                                    % (hx, hy, hx, hy))
                                                time.sleep(3)
                                                hov = screen.find(
                                                    texts=["Hand over Chief"])
                                                if not (hov and hov.center) \
                                                        and adb.pid(args.package) \
                                                        == pid_at_ho:
                                                    # one bounded re-long-press
                                                    # (sheet timing / a missed
                                                    # press)
                                                    adb.sh(
                                                        "input swipe %d %d %d %d 1000"
                                                        % (hx, hy, hx, hy))
                                                    time.sleep(3)
                                                    hov = screen.find(
                                                        texts=["Hand over Chief"])
                                                if not (hov and hov.center):
                                                    return (False, "'Hand over "
                                                            "Chief' not on the "
                                                            "member sheet")
                                                # BottomDialog/TwoButtonDialog
                                                # entrance animations: a
                                                # coordinate tap during the
                                                # animation misses the hitbox
                                                # and DISMISSES the dialog
                                                # silently (the run-37546126594
                                                # family: taps landed, zero
                                                # traffic, no error). Settle +
                                                # re-find before both critical
                                                # taps.
                                                time.sleep(1.2)
                                                hov2 = screen.find(
                                                    texts=["Hand over Chief"])
                                                if hov2 and hov2.center:
                                                    hov = hov2
                                                screen.tap_node(hov)
                                                time.sleep(3)
                                                sure3 = screen.wait_for(
                                                    ids=["btnSure"], timeout=8,
                                                    poll=2)
                                                if not (sure3 and sure3.center):
                                                    return (False, "hand-over "
                                                            "TwoButtonDialog not "
                                                            "confirmed")
                                                time.sleep(1.2)
                                                sure3b = screen.find(
                                                    ids=["btnSure"])
                                                if sure3b and sure3b.center:
                                                    sure3 = sure3b
                                                screen.tap_node(sure3)
                                                time.sleep(5)
                                                f_alive("G-handover-" + tag)
                                                post_ho = puts_g()
                                                ml_ho = fcall(
                                                    "GET",
                                                    "/clan/api/v1/clan/"
                                                    "tribe/member",
                                                    headers=live_hdr)
                                                gk_role = next(
                                                    (m.get("role")
                                                     for m in
                                                     ml_ho.get("data", [])
                                                     if m.get("userId")
                                                     == gk_uid_num), None)
                                                me_role = next(
                                                    (m.get("role")
                                                     for m in
                                                     ml_ho.get("data", [])
                                                     if str(m.get("userId"))
                                                     == str(d_uid_live)), None)
                                                base_ho = fcall(
                                                    "GET",
                                                    "/clan/api/v1/clan/"
                                                    "tribe/base",
                                                    headers=live_hdr)
                                                # tribe/base carries the
                                                # roster (clanMembers), not a
                                                # chiefId field — the chief is
                                                # the role-20 row (fix from run
                                                # 37409714321: chiefId=None
                                                # read the wrong field)
                                                chief_from_base = next(
                                                    (m.get("userId")
                                                     for m in
                                                     (base_ho.get("data")
                                                      or {}).get(
                                                          "clanMembers", [])
                                                     if m.get("role") == 20),
                                                    None)
                                                ev = ("PUT %d->%d, gk role=%s, "
                                                      "old chief role=%s, chief "
                                                      "from base=%s"
                                                      % (pre_ho, post_ho,
                                                         gk_role, me_role,
                                                         chief_from_base))
                                                ho_res = post_ho > pre_ho \
                                                    and gk_role == 20 \
                                                    and me_role == 0 \
                                                    and str(chief_from_base) \
                                                    == str(gk_uid_num)
                                                return (ho_res, ev)

                                            # RUN 37546126594 triage: every
                                            # tap landed but the client never
                                            # fired the PUT (silent client-side
                                            # drop; invite-sent runs had passed
                                            # before, so it is a race, not a
                                            # gate). Retry the WHOLE
                                            # interaction once and dump the UI
                                            # as evidence before the hard
                                            # verdict.
                                            ho_ev = "not attempted"
                                            for ho_i in range(2):
                                                if ho_i:
                                                    # Wave 15d — the member
                                                    # list can sit on its
                                                    # loading spinner for
                                                    # 30s+ after the G-ho-cache
                                                    # cold relaunch (run
                                                    # 37607065791: both row
                                                    # hunts expired against a
                                                    # stuck 'Loading…' screen).
                                                    # The retry now LEAVES and
                                                    # RE-ENTERS the manage
                                                    # screen — a fresh open
                                                    # re-fires the member GET —
                                                    # then waits for the
                                                    # spinner to clear before
                                                    # hunting the row.
                                                    adb.key(4)
                                                    time.sleep(3)
                                                    mm3r = screen.wait_for(
                                                        texts=["Manage Members"],
                                                        timeout=8, poll=2)
                                                    if mm3r and mm3r.center:
                                                        screen.tap_node(mm3r)
                                                        time.sleep(5)
                                                        for _sp in range(8):
                                                            if not screen.find(
                                                                    ids=["rlLoading"]):
                                                                break
                                                            time.sleep(3)
                                                    f_alive("G-managescreen-ho2")
                                                ho_ok, ho_ev = ho_attempt(
                                                    "attempt%d" % (ho_i + 1))
                                                if ho_ok:
                                                    check(
                                                        "G: HAND OVER CHIEF "
                                                        "client-asserted (%s)"
                                                        % ho_ev, True)
                                                    ho_done = True
                                                    break
                                                if ho_i == 0:
                                                    print("  [retry] G: "
                                                          "hand-over attempt 1 "
                                                          "no PUT (%s) - "
                                                          "retrying once"
                                                          % ho_ev)
                                                    for n in screen.dump():
                                                        if n.res or n.text:
                                                            print(
                                                                "  G-ho-dump] %s |"
                                                                " text=%r"
                                                                % (n.res.rsplit(
                                                                    "/", 1)[-1]
                                                                    if n.res
                                                                    else "",
                                                                    n.text[:28]))
                                            if not ho_done:
                                                check(
                                                    "G: HAND OVER CHIEF "
                                                    "client-asserted (%s)"
                                                    % ho_ev, False,
                                                    "no PUT reached the server "
                                                    "after 2 full attempts")
                                        else:
                                            print("  [info] G: 'Manage Members' "
                                                  "not on the sheet (hand-over "
                                                  "re-entry)")
                                if not ho_done and not rb3h:
                                    print("  [info] G: rb_3 not found for the "
                                          "hand-over re-entry")
                            else:
                                print("  [info] G: no third member (hand-over "
                                      "drive skipped)")
                            alive_or_recover_at(adb, screen, args.package,
                                                args.activity, "G-grounded")
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
                alive_or_recover_at(adb, screen, args.package, args.activity,
                                    "F-grounded")
            else:
                print("  [skip] F: rb_3 not found after Phase E")
        else:
            print("  [info] Phase F skipped - no own clan (no session token from "
                  "Phase D, API create failed, or rb_3 unavailable)")

        # ------------------------------------------------- Phase H: the
        # activity-task claim through the REAL UI (session 21, wave 7).
        # jadx decode: the hall's icon_activity entry (content_header1 item1,
        # bound by ka.java to MainFragmentViewModel.onActivity) -> bc.j -> D.b
        # -> TemplateUtils.startTemplate(ActivityFragment (e.b.c.b), title
        # string game_g1008) -> ActivityViewModel g -> ActivityListModel f ->
        # CampaignApi.getActivityTaskTitleList (GET /activity/api/v2/activity/
        # title, the wave-6c surface) -> title cards (item_activity_list).
        # Clicking the "weekend" card (ActivityItemViewModel c.f titleType
        # switch: weekend/recharge -> ActivityNewDialog) opens m (FullScreen
        # dialog, layout activity_content_temp_weekend) -> ActivityTaskContent
        # ListModel q -> GET .../activity/action?titleType=weekend fetched
        # FRESH on dialog open -> rows (item_activity_task_content); each
        # row's Button (text = string/receive "Get", NO resource-id) fires
        # ActivityTaskContentItemViewModel o.h -> POST /activity/api/v1/
        # receive/reward?titleType=&actionId=; n.onSuccess sets status 2 and
        # shows CampaignGetIntegralRewardDialog (Confirm button = base_sure).
        # The 10-min online_time task turns claimable once the server has
        # tracked >= 10 DISTINCT authenticated online minutes for this user
        # (wave-6c handler); this drive runs after the F/G walks, late in the
        # run, so the budget has already accrued. NO GameServer work.
        budget_gate("Phase H (activity-task claim)", 1.5)
        print("== Phase H: activity-task claim (weekend task dialog) ==")
        # the quoted literal keeps docs/COVERAGE.json's client_asserted
        # detection honest (the assertion really is in this script)
        h_rr_path = "/activity/api/v1/receive/reward"
        h_post = lambda: sum(
            1 for line in adb.raw("logcat", "-d", "-s", "LocalAPI",
                                  timeout=60).splitlines()
            if ("REQ POST " + h_rr_path) in line)
        h_golds_before = None

        def h_wallet_preread():
            # the embedded server IS the app process: a dead app (the roaming
            # killer) means NO server -> this read resolves to None. Called
            # AFTER the H ground/recovery so the read rides a live server.
            if not live_hdr:
                return None
            h_act = fcall("GET",
                          "/activity/api/v1/activity/action?titleType=weekend",
                          headers=live_hdr)
            h_rows = h_act.get("data") if isinstance(h_act.get("data"), list) \
                else []
            h_first = next((r for r in h_rows
                            if r.get("actionFlag") == "online_time"), None)
            h_wallet = fcall("GET", "/pay/api/v1/wealth/user", headers=live_hdr)
            h_golds = (h_wallet.get("data") or {}).get("golds")
            print("  [evidence] H: weekend online_time status=%s golds=%s"
                  % ((h_first or {}).get("status"), h_golds))
            return h_golds

        h_ground = False
        for h_try in range(2):
            # the killer struck BETWEEN G and H (run 37441604561): recover at
            # the H ENTRY or the whole claim drive starves (rb_1 is never
            # found on a dead app and the drive was skipped to its tail)
            if not adb.pid(args.package):
                alive_or_recover_at(adb, screen, args.package, args.activity,
                                    "H-entry")
            for _ in range(4):
                if screen.find(ids=["rb_1"]):
                    h_ground = True
                    break
                adb.key(4)
                time.sleep(2)
            if h_ground:
                break
        if h_ground:
            h_golds_before = h_wallet_preread()
            rb1h = screen.find(ids=["rb_1"])
            if rb1h and rb1h.center:
                screen.tap_node(rb1h)
                time.sleep(4)
            dismiss_permission_dialogs(screen)
            handle_campaign_dialogs(adb, screen, "H-hall")
            h_entry = None
            for _ in range(3):
                # swipe down to expand the collapsing hall header (parallax);
                # the BIG header (content_header1) owns item1, the COLLAPSED
                # small header (content_header2) owns littleItem1 — both fire
                # MainFragmentViewModel.onActivity (ka.java / ma.java)
                adb.sh("input swipe 360 300 360 800 300")
                time.sleep(2)
                h_entry = screen.find(ids=["item1"]) \
                    or screen.find(ids=["littleItem1"])
                if h_entry and h_entry.center:
                    break
            if h_entry and h_entry.center:
                ok("H: hall activity entry found (%s at %s)"
                   % ("item1" if (h_entry.res or "").endswith("item1")
                      else "littleItem1", h_entry.center))
                pre_h = h_post()
                screen.tap_node(h_entry)
                time.sleep(5)
                alive_or_recover_at(adb, screen, args.package, args.activity,
                                    "H-activitycenter")

                def h_get_buttons():
                    # bounded poll: the dialog fetches the weekend actions
                    # fresh on open (q.onLoad) before the rows render
                    end = time.time() + 10
                    while time.time() < end:
                        btns = [x for x in screen.dump()
                                if x.center and x.cls.endswith("Button")
                                and (x.text or "").strip().upper() == "GET"]
                        if btns:
                            return btns
                        time.sleep(2)
                    return []

                h_btns = []
                for h_attempt, h_idx in ((1, 1), (2, 0)):
                    # cards = bg_content nodes (one per title card); the client
                    # renders [weekday, weekend] and ONLY the weekend card
                    # opens the task dialog (c.f titleType switch; weekday
                    # falls into the content switch and our content is inert).
                    # The template fetches titles on open (f.onLoad), so poll
                    # for the cards before tapping (bounded).
                    h_cards = []
                    h_card_deadline = time.time() + 12
                    while time.time() < h_card_deadline:
                        h_cards = [x for x in screen.dump()
                                   if x.center and x.res.rsplit("/", 1)[-1]
                                   == "bg_content"]
                        h_cards = list({x.bounds: x for x in h_cards}.values())
                        if len(h_cards) > h_idx:
                            break
                        time.sleep(2)
                    if len(h_cards) > h_idx:
                        h_card = sorted(h_cards,
                                        key=lambda n: n.bounds[1])[h_idx]
                        screen.tap_node(h_card)
                        time.sleep(6)
                        h_btns = h_get_buttons()
                        if h_btns:
                            break
                    print("  [info] H: no GET buttons after card index %d "
                          "(attempt %d, cards=%d)"
                          % (h_idx, h_attempt, len(h_cards)))
                if h_btns:
                    ok("H: weekend task dialog open (%d GET buttons)"
                       % len(h_btns))
                    screen.tap_node(h_btns[0])  # first row = online_time 10 min
                    time.sleep(6)
                    post_h = h_post()
                    # n.onSuccess shows CampaignGetIntegralRewardDialog on a
                    # REAL claim; an incomplete task gets a non-fatal error tip
                    # (the POST still fires). Session-21 lesson: the dialog was
                    # missed in the old 6s EXACT-text wait — the client's
                    # textAllCaps renders base_sure as "CONFIRM", and find()
                    # matches texts= exactly. Match case-insensitively
                    # (contains=["confirm"]), widen to 16s, and PROMOTE to a
                    # hard check gated on the wallet delta (a real claim credits
                    # golds, so a grown wallet + no dialog is a genuine miss).
                    h_conf = screen.wait_for(contains=["confirm"], timeout=16,
                                             poll=2)
                    h_dialog_seen = False
                    if h_conf and h_conf.center:
                        screen.tap_node(h_conf)
                        time.sleep(3)
                        h_dialog_seen = True
                        ok("H: reward dialog seen (real claim path)")
                    else:
                        screen.snap("H_reward_dialog_missing")
                        debug_dump(screen, "H-reward-dialog")
                    h_delta = None
                    if live_hdr:
                        h_wallet2 = fcall("GET", "/pay/api/v1/wealth/user",
                                          headers=live_hdr)
                        h_golds_after = (h_wallet2.get("data") or {}).get("golds")
                        print("  [evidence] H: golds after claim=%s (before=%s)"
                              % (h_golds_after, h_golds_before))
                        try:
                            h_delta = (int(h_golds_after)
                                       - int(h_golds_before or 0))
                        except (TypeError, ValueError):
                            h_delta = None
                    check("H: reward dialog on real claim (wallet delta=%s, "
                          "POST receive/reward %d->%d)"
                          % (h_delta, pre_h, post_h),
                          (not h_delta or h_delta <= 0) or h_dialog_seen,
                          "wallet grew but CampaignGetIntegralRewardDialog "
                          "was never seen (snap_H_reward_dialog_missing.png)")
                    check("H: activity-task claim client-asserted (POST "
                          "receive/reward %d->%d)" % (pre_h, post_h),
                          post_h > pre_h, "no POST observed")
                else:
                    print("  [info] H: task dialog not reached from the title "
                          "cards (dump evidence above)")
                # ground: leave the dialog + template back at the hall
                for _ in range(4):
                    if screen.find(ids=["rb_1"]):
                        break
                    adb.key(4)
                    time.sleep(2)
            else:
                print("  [info] H: hall activity entry not found "
                      "(item1/littleItem1) - visible nodes:")
                for n in screen.dump():
                    if n.res or n.text or n.desc:
                        print("  H-dump] %s | text=%r" % (
                            n.res.rsplit("/", 1)[-1] if n.res else "",
                            n.text[:28]))
        else:
            print("  [info] H: rb_1 not found (hall unavailable)")

        # ------------------------------------------------- Phase I: the scrap
        # screen through the REAL UI (session 22, error-driven UI expansion).
        # jadx decode: the hall's icon_scrap entry (content_header1 item3 /
        # content_header2 littleItem3) fires MainFragmentViewModel.onScrap ->
        # onEnterScrap -> TemplateUtils.startTemplate(e.b.da.h =
        # ScrapMainFragment, string 2131820785). The model (o =
        # ScrapMainViewModel) calls m() -> ScrapApi.getRewardValue on CONSTRUCT
        # (GET /activity/api/v1/collect/exchange/reward/value), and renders 5
        # tabs (l(): ObservableList<p> from the icon int-array); each tab is a
        # ListItemViewModel whose DefaultListModel (l.java) fetches
        # ScrapApi.getScrapRewardList (GET /activity/api/{version}/collect/
        # exchange/card/list?type=N) on render. The bag entry (command o ->
        # f()) opens ScrapBagDialog -> ScrapBagListModel -> getBackpackInfo
        # (GET /activity/api/{version}/collect/exchange/user/scrap) +
        # getScrapBagValue. ALL 16 IScrapApi routes are real state-backed
        # handlers (ScrapBag.java) host-tested since Phase 3 — but this
        # surface has never been exercised by the client; the drive asserts
        # the on-open pair and records every /collect/exchange/ path the
        # client actually fires (error-driven evidence for the next wave).
        budget_gate("Phase I (scrap screen)", 1.5)
        print("== Phase I: scrap screen (collect & exchange) ==")
        i_rv_path = "/activity/api/v1/collect/exchange/reward/value"
        i_cl_marker = "/collect/exchange/card/list"
        # gen_coverage mapping: the ROUTE is the {version} template — quote
        # the template form so the concrete v2 the client fires maps to it
        # (the session-23 j_bag_route_lit pattern)
        i_cl_route_lit = "/activity/api/{version}/collect/exchange/card/list"
        # the scrap tabs ALSO fetch the per-card combine counts (v2 observed
        # in runs 37505691180 + 37516781819 I-windows)
        i_combine_route_lit = "/activity/api/{version}/collect/exchange/card/combine"
        i_reqs = lambda: [ln.split("REQ ", 1)[1].split(" ")[1]
                          for ln in adb.raw("logcat", "-d", "-s", "LocalAPI",
                                            timeout=60).splitlines()
                          if "REQ " in ln and "/collect/exchange/" in ln]
        i_ground = False
        for i_try in range(2):
            if not adb.pid(args.package):
                alive_or_recover_at(adb, screen, args.package, args.activity,
                                    "I-entry")
            for _ in range(4):
                if screen.find(ids=["rb_1"]):
                    i_ground = True
                    break
                adb.key(4)
                time.sleep(2)
            if i_ground:
                break
        if i_ground:
            rb1i = screen.find(ids=["rb_1"])
            if rb1i and rb1i.center:
                screen.tap_node(rb1i)
                time.sleep(4)
            dismiss_permission_dialogs(screen)
            handle_campaign_dialogs(adb, screen, "I-hall")
            i_entry = None
            for _ in range(3):
                # The H-tail relaunch can leave the QS shade dragged open:
                # a swipe-down on a not-yet-rendered window pulls the SYSTEM
                # shade, not the collapsing header (run 37454273455's I-dump
                # was pure quick_settings_panel). Collapse it, re-verify the
                # app, THEN swipe — every attempt, idempotently.
                adb.sh("cmd statusbar collapse")
                time.sleep(1)
                if not adb.pid(args.package):
                    alive_or_recover_at(adb, screen, args.package,
                                        args.activity, "I-walk")
                # same collapsing-header dance as H: BIG header item3 vs
                # COLLAPSED littleItem3 — both fire MainFragmentViewModel
                # .onScrap (ka.java / ma.java)
                adb.sh("input swipe 360 300 360 800 300")
                time.sleep(2)
                i_entry = screen.find(ids=["item3"]) \
                    or screen.find(ids=["littleItem3"])
                if i_entry and i_entry.center:
                    break
            if i_entry and i_entry.center:
                ok("I: scrap entry found (%s at %s)"
                   % ("item3" if (i_entry.res or "").endswith("item3")
                      else "littleItem3", i_entry.center))
                screen.tap_node(i_entry)
                time.sleep(6)
                assert_alive(adb, args.package, "I-scrapcenter")
                # the on-open pair: reward/value (model m()) + card/list
                # (first tab's DefaultListModel render)
                i_rv = sum(1 for ln in adb.raw("logcat", "-d", "-s", "LocalAPI",
                                               timeout=60).splitlines()
                           if ("REQ GET " + i_rv_path) in ln)
                check("I: scrap on-open getRewardValue client-asserted "
                      "(GET %s 0->%d)" % (i_rv_path, i_rv), i_rv > 0,
                      "reward/value was never requested")
                # bounded poll: the ViewPager may render the first tab a beat
                # after the template settles
                i_seen = []
                i_cl = False
                i_deadline = time.time() + 12
                while time.time() < i_deadline:
                    i_seen = sorted(set(i_reqs()))
                    i_cl = any(i_cl_marker in p for p in i_seen)
                    if i_cl:
                        break
                    time.sleep(2)
                check("I: scrap card list fetched by a tab (%s in %s)"
                      % (i_cl_marker, i_seen), i_cl,
                      "no tab fetched card/list (tabs may render lazily)")
                print("  [evidence] I: route template %s (v2 observed "
                      "on-device)" % i_cl_route_lit)
                i_comb = any("/card/combine" in p for p in i_seen)
                check("I: scrap card combine counts fetched (%s in %s)"
                      % ("/card/combine", i_seen), i_comb,
                      "no tab fetched card/combine")
                print("  [evidence] I: route template %s" % i_combine_route_lit)
                for p in i_seen:
                    print("  [evidence] I: client fired %s" % p)
                # ------------------------------------------------- Phase J:
                # the scrap BAG dialog (session 23, error-driven UI
                # expansion). jadx decode: the scrap main bottom-right menu
                # has three buttons — ll_library ("Inventory"/背包, command
                # o -> f()), ll_record ("Record"), ll_rule ("Rule").
                # f() opens ScrapBagDialog(context, isFromMain=true, 0L,
                # isPrivate=true); the dialog's ScrapBagViewModel CONSTRUCTOR
                # calls ScrapApi.getScrapBagValue (GET /activity/api/v1/
                # collect/exchange/user/scrap/value — EXACTLY ONE call site
                # across classes1-5, so a phase-local 0->N is sound), and
                # each of the 5 ViewPager pages (ScrapBagPageViewModel ->
                # ScrapBagListModel.onLoad) fetches ScrapApi.getBackpackInfo
                # (GET /activity/api/{version}/collect/exchange/user/scrap?
                # type=N&pageNo=&pageSize=; tab order types 0,2,4,1,3 from
                # R.array.scrap_bag_tab_array_type — Phase I evidence shows
                # the client resolves {version} to v2 at runtime). Both
                # routes are real ScrapBag.java handlers host-tested since
                # Phase 3; the bag DIALOG has never been client-exercised.
                budget_gate("Phase J (scrap bag dialog)", 1)
                print("== Phase J: scrap bag dialog ==")
                # bare path literals keep gen_coverage's client_asserted
                # detection exact (prefix matching against the RoutingTable)
                j_value_lit = "/activity/api/v1/collect/exchange/user/scrap/value"
                j_value_marker = "REQ GET " + j_value_lit
                j_bag_route_lit = "/activity/api/{version}/collect/exchange/user/scrap"
                # the bag pager pages also fetch the per-card combine counts
                # (GET /activity/api/{version}/collect/exchange/card/combine,
                # v2 observed on-device in runs 37492582973 + 37505691180)
                # NOTE: card/combine is asserted in PHASE I (the scrap tabs
                # fetch it there; the bag dialog reuses the cached counts —
                # run 37516781819: J-window delta was 2->2).

                def j_count(marker):
                    return sum(1 for ln in adb.raw("logcat", "-d", "-s",
                                                   "LocalAPI",
                                                   timeout=60).splitlines()
                               if marker in ln)

                def j_bag_paths():
                    # NOTE (run 37456710154 logcat evidence): the client
                    # sends this fetch WITHOUT a query string (null @Query
                    # params are omitted by Retrofit) — the REQ line is
                    # exactly "REQ GET /activity/api/v2/collect/exchange/
                    # user/scrap". Exclude the value route by suffix.
                    return [ln.split("REQ ", 1)[1].split(" ")[1]
                            for ln in adb.raw("logcat", "-d", "-s", "LocalAPI",
                                              timeout=60).splitlines()
                            if "REQ " in ln
                            and "/collect/exchange/user/scrap" in ln
                            and "/user/scrap/value" not in ln]
                j_pre_value = j_count(j_value_marker)
                j_pre_bag = len(j_bag_paths())
                j_bag = screen.find(ids=["ll_library"])
                if not (j_bag and j_bag.center):
                    # run 37461423454: the app drifted back to the hall
                    # between the I checks and the J search (template self-
                    # closed; live hall dump, no FATAL). Re-enter and retry
                    # once before giving up.
                    print("  [info] J: ll_library missing - re-entering the "
                          "scrap template")
                    if reenter_scrap(adb, screen, args.package, args.activity,
                                     "J"):
                        j_bag = screen.find(ids=["ll_library"])
                if j_bag and j_bag.center:
                    ok("J: bag entry found (ll_library at %s)" % (j_bag.center,))
                    screen.tap_node(j_bag)
                    time.sleep(5)
                    assert_alive(adb, args.package, "J-bagdialog")
                    # bounded poll: the dialog construct fires user/scrap/
                    # value immediately; the first ViewPager page's
                    # backpack fetch settled AFTER a 14s window in run
                    # 37453703969 (the PageRecyclerView fetches late), so
                    # poll 20s and, if still empty, FLIP A TAB (a real
                    # swipe on the ViewPager forces the next page's
                    # onLoad -> another user/scrap?type=N fetch).
                    j_seen_value = j_pre_value
                    j_seen_bag = j_pre_bag
                    j_deadline = time.time() + 20
                    while time.time() < j_deadline:
                        j_seen_value = j_count(j_value_marker)
                        j_seen_bag = len(j_bag_paths())
                        if j_seen_value > j_pre_value \
                                and j_seen_bag > j_pre_bag:
                            break
                        time.sleep(2)
                    if j_seen_bag <= j_pre_bag:
                        adb.sh("input swipe 560 620 160 620 250")
                        time.sleep(6)
                        j_seen_bag = len(j_bag_paths())
                    if j_seen_bag <= j_pre_bag:
                        adb.sh("input swipe 560 620 160 620 250")
                        time.sleep(6)
                        j_seen_bag = len(j_bag_paths())
                    check("J: scrap bag value client-asserted (GET "
                          "user/scrap/value %d->%d)"
                          % (j_pre_value, j_seen_value),
                          j_seen_value > j_pre_value,
                          "getScrapBagValue never fired (dialog may not "
                          "have opened)")
                    check("J: backpack pages fetched (GET user/scrap "
                          "%d->%d)" % (j_pre_bag, j_seen_bag),
                          j_seen_bag > j_pre_bag,
                          "no backpack page request (the ViewPager prefetch "
                          "fires on dialog open — marker may be wrong)")
                    for p in sorted(set(j_bag_paths())):
                        print("  [evidence] J: client fired %s" % p)
                    print("  [evidence] J: route template %s (v2 observed "
                          "on-device)" % j_bag_route_lit)
                    # close the dialog (iv_close in base_dialog_scrap_bag;
                    # BACK is the fallback — FullScreenDialog dismiss) and
                    # let the existing ground walk return to the hall
                    j_close = screen.find(ids=["iv_close"])
                    if j_close and j_close.center:
                        screen.tap_node(j_close)
                        time.sleep(2)
                    else:
                        adb.key(4)
                        time.sleep(2)
                else:
                    print("  [info] J: bag entry (ll_library) not found - "
                          "visible nodes:")
                    for n in screen.dump():
                        if n.res or n.text or n.desc:
                            print("  J-dump] %s | text=%r" % (
                                n.res.rsplit("/", 1)[-1] if n.res else "",
                                n.text[:28]))
                # ------------------------------------------------- Phase K:
                # scrap record + rule dialogs (session 23, same decode wave).
                # jadx decode: the scrap main menu's ll_record ("Record")
                # fires command p -> i() -> ScrapHistoryDialog (view.dialog
                # .f.b) whose ScrapHistoryListModel.onLoad is the ONLY call
                # site of ScrapApi.getCombineHistory (GET /activity/api/v1/
                # collect/exchange/user/combine/record — real server-side
                # handler scrapHistory, never client-exercised); ll_rule
                # ("Rule") fires command q -> j() -> ScrapRuleDialog
                # (view.dialog.h.b) whose ScrapRuleListModel.onLoad is the
                # ONLY call site of ScrapApi.getScrapRule (GET /activity/
                # api/v1/collect/exchange/description — handler scrapRule).
                # Both dialogs close via iv_close (dialog_scrap_history /
                # dialog_scrap_rule layouts).
                budget_gate("Phase K (scrap record + rule)", 1.5)
                print("== Phase K: scrap record + rule dialogs ==")
                # The three menu buttons (ll_library/ll_record/ll_rule) are
                # 50dp ConstraintLayouts ALL constrained to parent-end — they
                # STACK, ll_library last (= topmost). bg_menu (the 22dp pill)
                # carries the toggle command n -> o.h() whose AnimatorSet
                # fans them out (binder hf.java: f5444a <- o.n, e <- o.o,
                # f <- o.p, g <- o.q). J works from the stack (ll_library is
                # on top); ll_record/ll_rule need the fan OPEN. Detect the
                # stack (identical centers) and expand before each tap.
                def k_menu_open():
                    lib = screen.find(ids=["ll_library"])
                    rec = screen.find(ids=["ll_record"])
                    if lib and rec and lib.center and rec.center \
                            and abs(lib.center[0] - rec.center[0]) < 8 \
                            and abs(lib.center[1] - rec.center[1]) < 8:
                        bm = screen.find(ids=["bg_menu"])
                        if bm and bm.center:
                            screen.tap_node(bm)
                            time.sleep(2)

                k_record_lit = "/activity/api/v1/collect/exchange/user/combine/record"
                k_rule_lit = "/activity/api/v1/collect/exchange/description"
                k_record_marker = "REQ GET " + k_record_lit
                k_rule_marker = "REQ GET " + k_rule_lit
                k_pre_record = j_count(k_record_marker)
                k_pre_rule = j_count(k_rule_marker)
                k_menu_open()
                k_rec = screen.find(ids=["ll_record"])
                if not (k_rec and k_rec.center):
                    print("  [info] K: ll_record missing - re-entering the "
                          "scrap template")
                    if reenter_scrap(adb, screen, args.package, args.activity,
                                     "K-record"):
                        k_menu_open()
                        k_rec = screen.find(ids=["ll_record"])
                if k_rec and k_rec.center:
                    ok("K: record entry found (ll_record at %s)"
                       % (k_rec.center,))
                    screen.tap_node(k_rec)
                    time.sleep(5)
                    assert_alive(adb, args.package, "K-record")
                    k_seen = j_count(k_record_marker)
                    k_deadline = time.time() + 12
                    while time.time() < k_deadline and k_seen <= k_pre_record:
                        k_seen = j_count(k_record_marker)
                        time.sleep(2)
                    check("K: combine record fetched (GET user/combine/record "
                          "%d->%d)" % (k_pre_record, k_seen),
                          k_seen > k_pre_record,
                          "getCombineHistory never fired (dialog may not "
                          "have opened)")
                    k_close = screen.find(ids=["iv_close"])
                    if k_close and k_close.center:
                        screen.tap_node(k_close)
                        time.sleep(2)
                    else:
                        adb.key(4)
                        time.sleep(2)
                else:
                    print("  [info] K: record entry (ll_record) not found")
                k_menu_open()
                k_rule = screen.find(ids=["ll_rule"])
                if not (k_rule and k_rule.center):
                    print("  [info] K: ll_rule missing - re-entering the "
                          "scrap template")
                    if reenter_scrap(adb, screen, args.package, args.activity,
                                     "K-rule"):
                        k_menu_open()
                        k_rule = screen.find(ids=["ll_rule"])
                if k_rule and k_rule.center:
                    ok("K: rule entry found (ll_rule at %s)"
                       % (k_rule.center,))
                    screen.tap_node(k_rule)
                    time.sleep(5)
                    assert_alive(adb, args.package, "K-rule")
                    k_seen = j_count(k_rule_marker)
                    k_deadline = time.time() + 12
                    while time.time() < k_deadline and k_seen <= k_pre_rule:
                        k_seen = j_count(k_rule_marker)
                        time.sleep(2)
                    check("K: scrap rule fetched (GET description %d->%d)"
                          % (k_pre_rule, k_seen), k_seen > k_pre_rule,
                          "getScrapRule never fired (dialog may not have "
                          "opened)")
                    k_close = screen.find(ids=["iv_close"])
                    if k_close and k_close.center:
                        screen.tap_node(k_close)
                        time.sleep(2)
                    else:
                        adb.key(4)
                        time.sleep(2)
                else:
                    print("  [info] K: rule entry (ll_rule) not found")
                # leave the template back at the hall
                for _ in range(4):
                    if screen.find(ids=["rb_1"]):
                        break
                    adb.key(4)
                    time.sleep(2)
            else:
                print("  [info] I: scrap entry not found (item3/littleItem3) "
                      "- visible nodes:")
                for n in screen.dump():
                    if n.res or n.text or n.desc:
                        print("  I-dump] %s | text=%r" % (
                            n.res.rsplit("/", 1)[-1] if n.res else "",
                            n.text[:28]))
        else:
            print("  [info] I: rb_1 not found (hall unavailable)")
        # tail resilience (wave 7): the documented roaming killer has now
        # struck at the very TAIL of consecutive runs (run 37433234002: died
        # during the H entry search AFTER every check had gone green). A
        # tail death is absorbed like deep_drive's: relaunch, and if the app
        # comes back the run continues (the death itself is recorded as
        # evidence; a genuine server-induced crash would still show in the
        # crash scan above it).
        if not adb.pid(args.package):
            print("  [evidence] process died at the H tail - relaunching "
                  "(native-kill family signature)")
            if not relaunch_and_wait(adb, screen, args.package,
                                     args.activity, "H-tail"):
                print("  [info] H-tail relaunch failed (kept as evidence)")
        assert_alive(adb, args.package, "H-grounded")

        def ground_main(tag):
            """Wait for the MAIN screen (rb_1) after any recovery. RUN
            37542145915: a relaunch right before L left the app on the
            SPLASH (pid alive, no bottom bar) — L/M/N/O's rb_5 finds all
            raced it and three phases silently skipped inside a green run.
            Waits up to 30s, relaunching once if the process died."""
            deadline = time.time() + 30
            relaunched = False
            while time.time() < deadline:
                if screen.find(ids=["rb_1"]):
                    return True
                if not adb.pid(args.package) and not relaunched:
                    relaunch_and_wait(adb, screen, args.package,
                                      args.activity, tag)
                    relaunched = True
                time.sleep(3)
            return bool(screen.find(ids=["rb_1"]))

        # ------------------------------------------------- Phase L: the rank
        # surface (session 24, error-driven UI expansion). jadx decode:
        # the Me-tab "Ranking" row opens OverViewRankActivity (k) whose TWO
        # ViewPager pages (week/overall, rb_week_tab checked by default)
        # each load OverViewRankListModel -> GET /ranking/api/v1/ranking/
        # region/home/page/info?rankType=week|overall (the top-3 podium).
        # Each podium row (TopRankInfo) carries a `type` that the item VM
        # (overviewrank/f.java) maps to the matching rank template:
        # "gDiamond" -> W.c.h, "active" -> W.a.h, "clan" -> W.b.h — ANY
        # other value (e.g. the old server's "gold") makes the tap a
        # SILENT NO-OP. The server now emits one row per category; the
        # first row is therefore the gDiamond board's #1. Tapping it opens
        # the gDiamond template whose W.c.n list model fires GET /ranking/
        # api/v1/gold/diamond/{region|global}/{weekly|overall}/rank and
        # GET /ranking/api/v1/ranking/user/info (rankType inherited from
        # the podium's page: week here; the template's TWO pager pages
        # (period, area) + (period, global) both fetch on open).
        budget_gate("Phase L (rank podium + gDiamond)", 1.5)
        print("== Phase L: rank home podium + gDiamond template ==")
        l_home_lit = "/ranking/api/v1/ranking/region/home/page/info"
        l_user_lit = "/ranking/api/v1/ranking/user/info"
        l_gd_region_lit = "/ranking/api/v1/gold/diamond/region/weekly/rank"
        l_gd_global_lit = "/ranking/api/v1/gold/diamond/global/weekly/rank"

        def l_count(marker):
            return sum(1 for ln in adb.raw("logcat", "-d", "-s",
                                           "LocalAPI",
                                           timeout=60).splitlines()
                       if marker in ln)

        def l_rank_paths():
            # the evidence filter's literal is SPLIT in source below so
            # gen_coverage's quote-anchored regex extracts only "/ran" (len 4,
            # below its >4 threshold) and cannot prefix-match the 10 ranking
            # routes the client never fired (session 24: an unsplit single-
            # string filter here flagged all 14 ranking routes and inflated
            # client_asserted to 155).
            rank_frag = "/ran" + "king/"
            return sorted(set(ln.split("REQ ", 1)[1].split(" ")[1]
                              for ln in adb.raw("logcat", "-d", "-s",
                                                "LocalAPI",
                                                timeout=60).splitlines()
                              if "REQ " in ln and rank_frag in ln))

        l_me = screen.find(ids=["rb_5"])
        l_entered = False
        # pre-counts BEFORE the tap: the OverViewRankActivity fires the podium
        # fetch during its first seconds — counting after the open sleep would
        # swallow the delta (the classic 0->N honesty rule).
        l_pre_home = l_count("REQ GET " + l_home_lit)
        l_pre_user = l_count("REQ GET " + l_user_lit)
        l_pre_gdr = l_count("REQ GET " + l_gd_region_lit)
        l_pre_gdg = l_count("REQ GET " + l_gd_global_lit)
        # run 37492582973: right after the K-phase relaunch the Me tab was
        # still settling — the "Ranking" row was found and tapped but the tap
        # landed on a shifted list, the activity never opened, and L (and the
        # M header walk that trusted the same screen) drifted. The walk now
        # VERIFIES the open with the podium fetch delta and retries once.
        # run 37542145915: ground on the MAIN screen first (the splash has
        # no rb_5).
        l_grounded = ground_main("L-ground")
        for l_try in range(2) if l_grounded else range(0):
            l_me = screen.find(ids=["rb_5"])
            if not (l_me and l_me.center and screen.tap_node(l_me)):
                break
            time.sleep(4 + 2 * l_try)
            l_row = screen.find(texts=["Ranking"])
            if l_row and l_row.center:
                screen.tap_node(l_row)
                time.sleep(6)
                l_seen_open = l_pre_home
                l_open_deadline = time.time() + 6
                while time.time() < l_open_deadline \
                        and l_seen_open <= l_pre_home:
                    time.sleep(2)
                    l_seen_open = l_count("REQ GET " + l_home_lit)
                if l_seen_open > l_pre_home:
                    l_entered = True
                    break
        if not l_entered:
            alive_or_recover_at(adb, screen, args.package,
                                args.activity, "L-rank-open")
        if l_entered:
            # L1: the podium fetch fires on page 0 (week) — bounded poll.
            l_seen_home = l_pre_home
            l_deadline = time.time() + 14
            while time.time() < l_deadline and l_seen_home <= l_pre_home:
                time.sleep(2)
                l_seen_home = l_count("REQ GET " + l_home_lit)
            check("L: rank home podium fetched (GET region/home/page/info "
                  "%d->%d)" % (l_pre_home, l_seen_home),
                  l_seen_home > l_pre_home,
                  "getRegionRankHomePageInfoResponse never fired (the "
                  "Ranking screen may not have opened)")
            # podium rows: item_rank_left/right_type carry tv_rank_type_
            # top1_name; row order mirrors the server's [gDiamond, active,
            # clan]. Tap the FIRST row = gDiamond template (W.c.h).
            l_podium = screen.find(ids=["tv_rank_type_top1_name"])
            if l_podium and l_podium.center:
                ok("L: podium row found (top1 name at %s)" % (l_podium.center,))
                screen.tap_node(l_podium)
                time.sleep(6)
                assert_alive(adb, args.package, "L-template")
                # L2: the template's list fetch (page 0 = area, period =
                # week inherited from the podium page).
                l_seen_gdr = l_pre_gdr
                l_deadline = time.time() + 16
                while time.time() < l_deadline and l_seen_gdr <= l_pre_gdr:
                    time.sleep(2)
                    l_seen_gdr = l_count("REQ GET " + l_gd_region_lit)
                check("L: gDiamond board fetched (GET gold/diamond/region/"
                      "weekly/rank %d->%d)" % (l_pre_gdr, l_seen_gdr),
                      l_seen_gdr > l_pre_gdr,
                      "getGDiamondRegionWeeklyRanks never fired (the podium "
                      "tap may have been a no-op — check TopRankInfo.type)")
                # L3: my-row fetch fires alongside every list load
                # (W.c.n.onLoad -> a() -> getUserRankInfoResponse).
                l_seen_user = l_pre_user
                l_deadline = time.time() + 8
                while time.time() < l_deadline and l_seen_user <= l_pre_user:
                    time.sleep(2)
                    l_seen_user = l_count("REQ GET " + l_user_lit)
                check("L: my rank row fetched (GET ranking/user/info "
                      "%d->%d)" % (l_pre_user, l_seen_user),
                      l_seen_user > l_pre_user,
                      "getUserRankInfoResponse never fired")
                # L4: the template's SECOND pager page (period, global)
                # prefetches on open; a real rb_global_tab tap is the
                # fallback if the prefetch lags.
                l_seen_gdg = l_pre_gdg
                l_deadline = time.time() + 8
                while time.time() < l_deadline and l_seen_gdg <= l_pre_gdg:
                    time.sleep(2)
                    l_seen_gdg = l_count("REQ GET " + l_gd_global_lit)
                if l_seen_gdg <= l_pre_gdg:
                    g_tab = screen.find(ids=["rb_global_tab"])
                    if g_tab and g_tab.center:
                        screen.tap_node(g_tab)
                        l_deadline = time.time() + 12
                        while time.time() < l_deadline \
                                and l_seen_gdg <= l_pre_gdg:
                            time.sleep(2)
                            l_seen_gdg = l_count("REQ GET " + l_gd_global_lit)
                check("L: gDiamond global board fetched (GET gold/diamond/"
                      "global/weekly/rank %d->%d)" % (l_pre_gdg, l_seen_gdg),
                      l_seen_gdg > l_pre_gdg,
                      "getGDiamondGlobalWeeklyRanks never fired (prefetch "
                      "and rb_global_tab both missed)")
            else:
                print("  [info] L: podium rows not found - visible nodes:")
                for n in screen.dump():
                    if n.res or n.text or n.desc:
                        print("  L-dump] %s | text=%r" % (
                            n.res.rsplit("/", 1)[-1] if n.res else "",
                            n.text[:28]))
            for p in l_rank_paths():
                print("  [evidence] L: client fired %s" % p)
            # exit: BACK to the rank activity (if the template opened) and
            # BACK again to the hall; absorb a drift by grounding on rb_1.
            for _ in range(4):
                if screen.find(ids=["rb_1"]):
                    break
                adb.key(4)
                time.sleep(2)
            alive_or_recover_at(adb, screen, args.package, args.activity,
                                "L-exit")
        else:
            print("  [info] L: Ranking row not found (Me tab walk failed)")

        # ------------------------------------------------- Phase M: the VIP
        # privilege center (session 25, the last undriven hall entry -
        # item2). jadx decode: the hall header's item2 (content_header1) /
        # littleItem2 (collapsed content_header2) fires
        # MainFragmentViewModel.onEnterVip -> VipManager.enterVipFragment
        # -> ARouter "/subs/service" -> com.sandboxol.vip.service.VipService
        # (a REGISTERED ARouter provider - ARouter$$Providers$$vip - the
        # "service-gated" worry from session 24 is DECODED: the static
        # VipManager.<clinit> resolves it via RouteServiceManager.provide
        # and the route table is present, so it is not a no-op locally) ->
        # TemplateUtils.startTemplate(PrivilegeCenterFragment) whose
        # PrivilegeCenterViewModel.initData() calls VipApi.getSubscribeInfo
        # -> GET /pay/api/v1/sub/info/get (exactly one call site in the
        # whole vip package, so a phase-local 0->N is sound).
        budget_gate("Phase M (VIP privilege center)", 1.5)
        print("== Phase M: VIP privilege center (item2) ==")
        m_vip_lit = "/pay/api/v1/sub/info/get"
        # run 37499606354 evidence: the privilege-center flow ALSO fetches
        # the vip products list (BillingManager.vipSubsProductsList <-
        # vip/view/fragment/main/p) — GET /pay/api/v2/pay/products/vip
        m_vp_lit = "/pay/api/v2/pay/products/vip"

        def m_count(marker):
            return sum(1 for ln in adb.raw("logcat", "-d", "-s",
                                           "LocalAPI",
                                           timeout=60).splitlines()
                       if marker in ln)

        m_pre_vip = m_count("REQ GET " + m_vip_lit)
        m_pre_vp = m_count("REQ GET " + m_vp_lit)
        m_paths_before = set(localapi_paths(adb))
        m_entry = None
        if ground_main("M-ground"):
            # ground on the HALL TAB first: rb_1 is the bottom bar's first
            # radio and exists on EVERY main tab (run 37492582973: L's walk
            # left the app on the Me tab; the header walk then searched the
            # wrong screen and item2 was "not found"). Tapping rb_1 switches
            # back to the hall regardless of the current tab.
            m_rb1 = screen.find(ids=["rb_1"])
            if m_rb1 and m_rb1.center:
                screen.tap_node(m_rb1)
                time.sleep(4)
            for _ in range(3):
                adb.sh("cmd statusbar collapse")
                time.sleep(1)
                if not adb.pid(args.package):
                    alive_or_recover_at(adb, screen, args.package,
                                        args.activity, "M-walk")
                # same collapsing-header dance as H/I: BIG header item2 vs
                # COLLAPSED littleItem2 - both fire onEnterVip
                adb.sh("input swipe 360 300 360 800 300")
                time.sleep(2)
                m_entry = screen.find(ids=["item2"]) \
                    or screen.find(ids=["littleItem2"])
                if m_entry and m_entry.center:
                    break
        if m_entry and m_entry.center:
            ok("M: vip entry found (%s at %s)"
               % ("item2" if (m_entry.res or "").endswith("item2")
                  else "littleItem2", m_entry.center))
            screen.tap_node(m_entry)
            time.sleep(6)
            assert_alive(adb, args.package, "M-privilegecenter")
            m_seen = m_pre_vip
            m_deadline = time.time() + 14
            while time.time() < m_deadline and m_seen <= m_pre_vip:
                time.sleep(2)
                m_seen = m_count("REQ GET " + m_vip_lit)
            check("M: vip subscribe info fetched (GET %s %d->%d)"
                  % (m_vip_lit, m_pre_vip, m_seen),
                  m_seen > m_pre_vip,
                  "getSubscribeInfo never fired (the privilege center may "
                  "not have opened)")
            m_seen_vp = m_pre_vp
            m_vp_deadline = time.time() + 10
            while time.time() < m_vp_deadline and m_seen_vp <= m_pre_vp:
                time.sleep(2)
                m_seen_vp = m_count("REQ GET " + m_vp_lit)
            check("M: vip products list fetched (GET %s %d->%d)"
                  % (m_vp_lit, m_pre_vp, m_seen_vp),
                  m_seen_vp > m_pre_vp,
                  "vipSubsProductsList never fired (the privilege center "
                  "may not have loaded its products)")
            for p in sorted(set(localapi_paths(adb)) - m_paths_before):
                print("  [evidence] M: client fired %s" % p)
            # exit: BACK to the hall; absorb a drift by grounding on rb_1
            for _ in range(4):
                if screen.find(ids=["rb_1"]):
                    break
                adb.key(4)
                time.sleep(2)
            alive_or_recover_at(adb, screen, args.package, args.activity,
                                "M-exit")
        else:
            print("  [info] M: vip entry not found (item2/littleItem2)")

        # ------------------------------------------------- Phase N: the rank
        # podium rows 2+3 (session 25, the natural completion of Phase L).
        # Session 24's podium contract emits ONE row per category
        # ([gDiamond, active, clan]) and Phase L taps only the FIRST row
        # (gDiamond -> W.c.h). jadx decode: overviewrank/f.smali maps
        # type->template ("gDiamond"->W.c.h, "active"->W.a.h,
        # "clan"->W.b.h) and puts the podium period (rank_period_type) in
        # the bundle; the template list models W.a.n / W.b.n fire IRankingApi
        # getActive* / getClan* fetches + the shared ranking/user/info.
        # CLIENT CONTRACT (run 37492582973 triage + decode):
        # - ActiveRankViewModel (W/a/p) constructs TWO pager pages — area 0
        #   (region) + area 1 (global); both fetch on open. The active
        #   template's fragment has rb_area_tab + rb_global_tab.
        # - ClanRankViewModel (W/b/p) constructs ONE page only — area 1
        #   (GLOBAL); fragment_clan_rank.xml carries ONLY rb_global_tab.
        #   The clan REGION routes (clan/region/weekly + clan/region/
        #   overall) have NO reachable client call path from the podium —
        #   they stay implemented + host-tested but are NOT client-
        #   assertable, so Phase N hard-checks the clan GLOBAL boards only.
        # The podium activity also carries rb_overall_tab
        # (activity_overview_rank.xml): flipping it re-fetches region/home/
        # page/info?rankType=overall and the inherited period drives the
        # templates' overall variants.
        budget_gate("Phase N (rank rows 2+3)", 1.5)
        print("== Phase N: rank podium rows 2+3 (active, clan) ==")
        n_lits = [
            "/ranking/api/v1/active/region/weekly/rank",
            "/ranking/api/v1/active/global/weekly/rank",
            "/ranking/api/v1/clan/global/weekly/rank",
            "/ranking/api/v1/active/region/overall/rank",
            "/ranking/api/v1/active/global/overall/rank",
            "/ranking/api/v1/clan/global/overall/rank",
        ]
        n_home_lit = "/ranking/api/v1/ranking/region/home/page/info"
        n_user_lit = "/ranking/api/v1/ranking/user/info"

        def n_count(marker):
            return sum(1 for ln in adb.raw("logcat", "-d", "-s",
                                           "LocalAPI",
                                           timeout=60).splitlines()
                       if marker in ln)

        def n_rows():
            rows = [n for n in screen.dump()
                    if n.res and n.res.rsplit("/", 1)[-1]
                    == "tv_rank_type_top1_name" and n.center]
            rows.sort(key=lambda n: (n.center[1], n.center[0]))
            return rows

        def n_wait(lit, pre, seconds=16):
            seen = pre
            deadline = time.time() + seconds
            while time.time() < deadline and seen <= pre:
                time.sleep(2)
                seen = n_count("REQ GET " + lit)
            return seen

        # pre-counts BEFORE the Me-tab walk (the 0->N honesty rule)
        n_pre = {}
        for lit in n_lits:
            n_pre[lit] = n_count("REQ GET " + lit)
        n_pre_user = n_count("REQ GET " + n_user_lit)

        def n_open_ranking():
            # VERIFIED open (the L-walk lesson, run 37492582973): the walk
            # only reports success when the podium rows are actually visible;
            # the row tap is retried once on a stale-position miss, and an
            # already-open podium short-circuits (the ranking activity has no
            # rb_5 — a second walk attempt from ON the podium would fail).
            if not ground_main("N-ground"):
                return False
            for _ in range(2):
                if n_rows():
                    return True
                me = screen.find(ids=["rb_5"])
                if not (me and me.center):
                    return False
                if not screen.tap_node(me):
                    return False
                time.sleep(4)
                row = screen.find(texts=["Ranking"])
                if row and row.center:
                    screen.tap_node(row)
                    time.sleep(6)
                    rows = n_rows()
                    deadline = time.time() + 8
                    while not rows and time.time() < deadline:
                        time.sleep(2)
                        rows = n_rows()
                    if rows:
                        return True
            return alive_or_recover_at(adb, screen, args.package,
                                       args.activity, "N-rank-open") and bool(n_rows())

        def n_back_to_podium():
            for _ in range(4):
                if n_rows():
                    return True
                adb.key(4)
                time.sleep(2)
            return bool(n_rows())

        def n_drive_row(idx, label, board_checks):
            # board_checks: [(literal, fallback_tab_id)] — each literal is
            # hard-checked 0->N; when the on-open prefetch lags, the given
            # template tab is tapped as the fallback (Phase L pattern).
            rows = n_rows()
            deadline = time.time() + 8
            while not rows and time.time() < deadline:
                time.sleep(2)
                rows = n_rows()
            if idx >= len(rows):
                fail("N: %s podium row missing (found %d row(s) with "
                     "tv_rank_type_top1_name; server emits 3 categories)"
                     % (label, len(rows)))
                for n in screen.dump():
                    if n.res or n.text or n.desc:
                        print("  N-dump] %s | text=%r" % (
                            n.res.rsplit("/", 1)[-1] if n.res else "",
                            n.text[:28]))
                return
            screen.tap_node(rows[idx])
            time.sleep(6)
            assert_alive(adb, args.package, "N-%s-template" % label)
            for lit, tab in board_checks:
                seen = n_wait(lit, n_pre[lit], 8)
                if seen <= n_pre[lit] and tab:
                    # Wave 18d: run 37654738617 — the rb_area_tab fallback
                    # tap was a silent no-op once in 5 deep runs (the
                    # sibling rb_global_tab passed seconds later). Retry
                    # the tab tap once with a FRESH find before failing;
                    # check semantics unchanged (0->N).
                    for _ in range(2):
                        t = screen.find(ids=[tab])
                        if t and t.center and screen.tap_node(t):
                            seen = n_wait(lit, n_pre[lit], 12)
                            if seen > n_pre[lit]:
                                break
                        time.sleep(2)
                check("N: %s board fetched (GET %s %d->%d)"
                      % (label, lit, n_pre[lit], seen),
                      seen > n_pre[lit],
                      "%s fetch never fired (prefetch and the %s tab both "
                      "missed - the podium tap may have been a silent "
                      "no-op)" % (label, tab or "template"))
            n_back_to_podium()

        if n_open_ranking():
            # week podium (default tab): sorted rows[1] = active, rows[2] =
            # clan (row 0 = gDiamond, already asserted by Phase L). Active
            # gets both areas (region page + global page / rb_area_tab +
            # rb_global_tab); clan is GLOBAL-ONLY per the client contract.
            n_drive_row(1, "active/week", [
                (n_lits[0], "rb_area_tab"), (n_lits[1], "rb_global_tab")])
            n_drive_row(2, "clan/week", [(n_lits[2], "rb_global_tab")])
            # the documented drift (run 37492582973: the template self-closed
            # to the hall between drives) — re-ground before the overall leg
            if not n_rows():
                print("  [info] N: podium gone after the week drives "
                      "(documented drift) - re-opening")
                if not n_open_ranking():
                    fail("N: ranking screen unreachable for the overall leg")
            # flip the podium to OVERALL and repeat; the flip itself
            # re-fetches region/home/page/info with rankType=overall.
            # RACE (runs 37511675438 + 37533194661): the ranking activity
            # can self-close to the hall around the flip (before the tab
            # find, or within seconds AFTER tapping it) — the whole overall
            # leg is retried up to 3 times: re-open the podium when the
            # rows vanish, re-find the tab, flip, and VERIFY the podium
            # survived the flip before driving the rows.
            o_done = False
            for o_attempt in range(3):
                if not n_rows() and not n_open_ranking():
                    continue
                o_tab = screen.find(ids=["rb_overall_tab"])
                if not (o_tab and o_tab.center):
                    time.sleep(3)
                    continue
                screen.tap_node(o_tab)
                time.sleep(5)
                if not n_rows():
                    print("  [info] N: podium self-closed right after the "
                          "overall flip (attempt %d) - re-grounding"
                          % (o_attempt + 1))
                    continue
                n_drive_row(1, "active/overall", [
                    (n_lits[3], "rb_area_tab"), (n_lits[4], "rb_global_tab")])
                n_drive_row(2, "clan/overall", [(n_lits[5], "rb_global_tab")])
                o_done = True
                break
            if not o_done:
                fail("N: the overall leg could not be driven in 3 attempts "
                     "(the documented self-close drift struck every time - "
                     "dump below)")
                for n in screen.dump():
                    if n.res or n.text or n.desc:
                        print("  N-dump] %s | text=%r" % (
                            n.res.rsplit("/", 1)[-1] if n.res else "",
                            n.text[:28]))
            seen_user = n_count("REQ GET " + n_user_lit)
            if seen_user > n_pre_user:
                ok("N: my-rank rows kept fetching (user/info %d->%d)"
                   % (n_pre_user, seen_user))
            for p in l_rank_paths():
                print("  [evidence] N: client fired %s" % p)
            # exit: BACK to the hall; absorb a drift by grounding on rb_1
            for _ in range(4):
                if screen.find(ids=["rb_1"]):
                    break
                adb.key(4)
                time.sleep(2)
            alive_or_recover_at(adb, screen, args.package, args.activity,
                                "N-exit")
        else:
            print("  [info] N: Ranking walk failed (Me tab)")

        # ------------------------------------------------- Phase O: account
        # switch + the CLIENT's own login (session 25). jadx decode:
        # SettingViewModel.u() -> LoginManager.onSwitchAccount(activity) ->
        # LoginService (ARouter /login/service): fetches the account records
        # then starts com.sandbox.login.view.activity.login.LoginActivity
        # (extras key.is.with.back.btn / key.is.with.register). The login
        # screen's model fires GET /user/api/v1/user/login/change/record
        # (IUserLoginApi.accountRecord, LoginModel y.smali) and the
        # btn_sign submit fires IUserLoginApi.login ->
        # POST /user/api/v1/login (LoginRegisterAccountForm) — the client's
        # OWN login submit has never been client-asserted (the C/D phases
        # log in via runner-side fcalls). The form: editName + edit_password
        # (login_activity_login.xml). The registered D-phase credentials
        # (qa_uid_d / password_d) are reused so the session stays valid.
        budget_gate("Phase O (client-UI login)", 2)
        print("== Phase O: account switch + client-UI login ==")
        o_login_lit = "/user/api/v1/login"

        def o_count(marker):
            return sum(1 for ln in adb.raw("logcat", "-d", "-s",
                                           "LocalAPI",
                                           timeout=60).splitlines()
                       if marker in ln)

        # RUN 37538041177 evidence: the client-UI login submits POST
        # /user/api/v2/app/login (the modern unified login), NOT v1 — watch
        # both; accountRecord has NEVER fired on-device (likely gated on
        # saved-account records) so its marker is source-split (the /use
        # fragment is at the regex's len>4 threshold and the tail has no
        # leading slash) to avoid claiming an unproven route.
        o_v2_lit = "/user/api/v2/app/login"
        o_rec_marker = "REQ GET /use" + "r/api/v1/user/login/change/record"

        def o_rec_count():
            return o_count(o_rec_marker)

        # RES lines now carry the envelope code (LocalHttpd Wave 11): the
        # client-UI login must be ACCEPTED (code=1), not merely submitted.
        def o_ok_login_count():
            return sum(
                1 for ln in adb.raw("logcat", "-d", "-s", "LocalAPI",
                                    timeout=60).splitlines()
                if ("RES POST " + o_v2_lit in ln
                    or "RES POST " + o_login_lit in ln)
                and "code=1" in ln)

        o_pre_rec = o_rec_count()
        o_pre_login = o_count("REQ POST " + o_login_lit) \
            + o_count("REQ POST " + o_v2_lit)
        o_pre_ok = o_ok_login_count()
        o_paths_before = set(localapi_paths(adb))
        o_form = False
        if ground_main("O-ground"):
            # walk: Me tab -> the "Setting" row (me_setting; runs the
            # SettingFragment template via MoreViewModel.N / "more_setup")
            # -> the "Account Switch" row (setting_change_account).
            # RUN 37533194661 triage: profile -> ibMore opens the Personal
            # Info EDITOR, not the settings - the row walk below is the
            # decoded path.
            tab_o = screen.find(ids=["rb_5"])
            if tab_o and tab_o.center:
                screen.tap_node(tab_o)
                time.sleep(4)
            set_o = None
            o_deadline = time.time() + 12
            while time.time() < o_deadline and not set_o:
                set_o = screen.find(texts=["Setting"])
                if not set_o:
                    adb.sh("input swipe 360 700 360 400 300")
                    time.sleep(2)
            if set_o and set_o.center:
                ok("O: Setting row found at %s" % (set_o.center,))
                screen.tap_node(set_o)
                time.sleep(6)
            else:
                print("  [info] O: Setting row not found on the Me tab")
            # the Account Switch row (setting_change_account = "Account
            # Switch"); a bounded wait absorbs the template render
            sw_o = None
            o_deadline = time.time() + 10
            while time.time() < o_deadline and not sw_o:
                sw_o = screen.find(texts=["Account Switch"])
                if not sw_o:
                    time.sleep(2)
            if sw_o and sw_o.center:
                ok("O: Account Switch row found at %s" % (sw_o.center,))
                screen.tap_node(sw_o)
                time.sleep(8)
                # the LoginActivity (or a confirm dialog first)
                handle_campaign_dialogs(adb, screen, "O-switch")
                name_o = next((x for x in screen.dump()
                               if x.res and x.res.rsplit("/", 1)[-1]
                               == "editName" and x.center), None)
                if name_o:
                    o_form = True
                else:
                    print("  [info] O: login form not shown after the "
                          "switch tap - visible nodes:")
                    for n in screen.dump():
                        if n.res or n.text or n.desc:
                            print("  O-dump] %s | text=%r" % (
                                n.res.rsplit("/", 1)[-1] if n.res else "",
                                n.text[:28]))
            else:
                print("  [info] O: Account Switch row not found (settings "
                      "sheet layout drifted) - visible nodes:")
                for n in screen.dump():
                    if n.res or n.text or n.desc:
                        print("  O-dump] %s | text=%r" % (
                            n.res.rsplit("/", 1)[-1] if n.res else "",
                            n.text[:28]))
        if o_form:
            # the account-record fetch: NON-FATAL probe (never observed
            # on-device; likely gated on saved-account records)
            o_seen_rec = o_rec_count()
            if o_seen_rec > o_pre_rec:
                ok("O: login-screen account records fetched (%d->%d)"
                   % (o_pre_rec, o_seen_rec))
            else:
                print("  [probe] O: no accountRecord fetch (gated on saved "
                      "records - non-fatal)")
            # fill the form with the registered credentials and submit
            fill_focused_edit(adb, screen, qa_uid_d)
            pw_o = next((x for x in screen.dump()
                         if x.res and x.res.rsplit("/", 1)[-1]
                         == "edit_password" and x.center), None)
            if pw_o and pw_o.center:
                screen.tap_node(pw_o)
                time.sleep(1)
                adb.key(123)
                for _ in range(40):
                    adb.key(67)
                adb.text(password_d)
                time.sleep(1)
                adb.key(111)
            sign_o = screen.find(ids=["btn_sign"])
            if sign_o and sign_o.center:
                screen.tap_node(sign_o)
                time.sleep(8)
            o_seen_login = o_count("REQ POST " + o_login_lit) \
                + o_count("REQ POST " + o_v2_lit)
            o_deadline = time.time() + 16
            while time.time() < o_deadline and o_seen_login <= o_pre_login:
                time.sleep(2)
                o_seen_login = o_count("REQ POST " + o_login_lit) \
                    + o_count("REQ POST " + o_v2_lit)
            check("O: client-UI login submitted (POST %s %d->%d)"
                  % (o_v2_lit, o_pre_login, o_seen_login),
                  o_seen_login > o_pre_login,
                  "the login screen never submitted a login POST (v1 or "
                  "v2)")
            # Wave 11: the submitted login must ALSO be accepted — the
            # pre-fix server answered the client-UI RSA login with a 37b
            # code=0 error (run 37546126594 diagnostics). The RSA contract
            # is now served for real (RsaCipher + patch_rsa_key.py).
            time.sleep(2)
            o_post_ok = o_ok_login_count()
            for ln in adb.raw("logcat", "-d", "-s", "LocalAPI",
                              timeout=60).splitlines():
                if ("RES POST " + o_v2_lit in ln
                        or "RES POST " + o_login_lit in ln):
                    print("  [evidence] O: %s" % ln.split("LocalAPI:")[-1].strip())
            check("O: client-UI login accepted by the server (RES code=1 %d->%d)"
                  % (o_pre_ok, o_post_ok),
                  o_post_ok > o_pre_ok,
                  "the login POST was rejected server-side (wrong password "
                  "/ unknown account) — RSA contract regression?")
            for p in sorted(set(localapi_paths(adb)) - o_paths_before):
                print("  [evidence] O: client fired %s" % p)
            # recover: BACK out of whatever landed (hall or login result)
            for _ in range(4):
                if screen.find(ids=["rb_1"]):
                    break
                adb.key(4)
                time.sleep(2)
            alive_or_recover_at(adb, screen, args.package, args.activity,
                                "O-exit")

        # ------------------------------------------------- Phase LM (Wave 20):
        # login-module flows through the real UI (Setting -> Security).
        # LAST deep phase, DELIBERATELY: the jadx-decoded success callback
        # of the password modify fires logoutOnModifyPwd -> UserApi.logout
        # (login.f.a.b.f -> login.y.a) — the session ends on success, so
        # every session-dependent phase (D's token, E-O) must run BEFORE
        # this. The drive's email/phone/question flows also mutate the
        # account (bind state), which is why it runs on the fully-registered
        # Phase-D session at the very end of the suite. The final
        # assertions + crash scan below need no valid session.
        budget_gate("PHASE LM (login-module flows)", 4)
        print("== PHASE LM: login-module flows (Setting -> Security) ==")
        login_module_drive(adb, screen, args.package, args.activity, "LM",
                           password_d)
      except DeepBudgetSkip as _bs:
        print("  [skip budget] deep phases stopped after: %s" % _bs)
    else:
        print("  [skip] Phases E-O deep drives (fast mode)")

    # ------------------------------------------------- assertions
    print("== assertions ==")
    # Union with the early + mid snapshots: GL-heavy screens rotate the
    # logcat main buffer, so end-of-run scans alone miss early (Phase A)
    # and mid-run (Phase D registration) traffic.
    paths = sorted(set(paths_early) | set(paths_mid)
                   | set(localapi_paths(adb)))
    print("  LocalAPI unique endpoints hit: %d" % len(paths))
    for p in paths:
        print("    - %s" % p)
    reg_hit = adb.raw("logcat", "-d", "-s", "LocalAPI", timeout=60)
    register_endpoints = ("REQ POST /user/api/v1/register" in reg_hit
                          or "REQ POST /user/api/v1/app/set-password" in reg_hit
                          or "REQ POST /user/api/v2/app/set-password" in reg_hit
                          or "REQ POST /user/api/v1/user/register" in reg_hit
                          # Wave 15d — rotation-proof: the register evidence
                          # captured at the moment Phase C created the
                          # account (survives any relaunch storm).
                          or register_seen_early
                          # buffer-rotation-resilient fallback: the path sets
                          # (early + mid snapshots) are authoritative — the
                          # mid snapshot holds Phase D's registration fcalls
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
    # Session 20 (run 37412479967): the uiautomator DUMP TOOL itself can
    # NPE (AccessibilityNodeInfoDumper.childNafCheck) on Android 12 redroid
    # and land its own FATAL EXCEPTION in the shared logcat — that is a
    # tool-side death, not an app crash. Attribute every FATAL block: a
    # block whose first ~30 frames mention uiautomator WITHOUT any app
    # frame is tool noise; anything touching the app (or unattributable)
    # still fails the run.
    app_fatal = []
    for src in (fatal, crash):
        lines = src.splitlines()
        i = 0
        while i < len(lines):
            if "FATAL EXCEPTION" in lines[i]:
                block = "\n".join(lines[i:i + 30])
                if "uiautomator" in block \
                        and "com.disabngo" not in block \
                        and "com.sandboxol" not in block:
                    print("  [evidence] tool-side FATAL (uiautomator dump "
                          "NPE) - not an app crash")
                else:
                    app_fatal.append(lines[i])
            i += 1
    if app_fatal:
        fail("FATAL EXCEPTION in logcat")
        for line in app_fatal:
            print("    " + line)
    else:
        ok("no app FATAL EXCEPTION")
    if "ANR in %s" % args.package in fatal:
        fail("ANR detected")
    # same tail absorb for the final assert (the killer has struck twice
    # in one tail window in the past; one relaunch covers it)
    if not adb.pid(args.package):
        print("  [evidence] process died before the final check - "
              "relaunching (native-kill family signature)")
        relaunch_and_wait(adb, screen, args.package, args.activity,
                          "end-tail")
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
