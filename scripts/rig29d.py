#!/usr/bin/env python3
"""Wave 29d host-rig precheck: boots the embedded server fresh (same boot as
scripts/test_server_host.py) and drives the EXACT chains Wave 29d asserts on
device (video feedback, throwaway device-account auth lifecycle, user-misc
reads, reward chains, telemetry acks). Run BEFORE dispatching a deep run."""
import json
import random
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = "/home/z/Local-Blockman-GO-1.24.4"
CP = ":".join([
    REPO + "/localapi-server/build/host",
    REPO + "/localapi-server/build/classes",
    REPO + "/.javatools/nanohttpd.jar",
    REPO + "/.javatools/json.jar",
])
PORT = random.randint(21000, 39000)
BASE = "http://127.0.0.1:%d" % PORT
state = tempfile.mkdtemp(prefix="rig29d-")
proc = subprocess.Popen(["java", "-cp", CP, "com.localapi.HostTest",
                         state, str(PORT)], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True)
deadline = time.time() + 60
while time.time() < deadline:
    line = proc.stdout.readline()
    if "HOSTTEST READY" in line:
        break
else:
    print("server never became ready")
    sys.exit(1)
print("rig up on %d" % PORT)

fails = []


def call(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"__error": str(e)}


def check(name, cond, detail=""):
    tag = "ok" if cond else "FAIL"
    if not cond:
        fails.append(name)
    print("  [%s] %s %s" % (tag, name, detail if not cond else ""))


# --- session (Phase C mirror) -----------------------------------------
password = "rig-Pass-%d" % (int(time.time()) % 1000000)
qa_uid = "rig29d%05d" % (int(time.time()) % 100000)
r1 = call("POST", "/user/api/v1/register",
          {"uid": qa_uid, "password": password, "confirmPassword": password,
           "imei": "rig-device", "appType": "android", "os": "12"})
check("register %s" % qa_uid, r1.get("code") == 1 and r1.get("data", {}).get("userId", 0) > 0,
      str(r1)[:120])
qa_uid_num = r1.get("data", {}).get("userId", 0)
r2 = call("POST", "/user/api/v1/login", {"uid": qa_uid, "password": password})
auth_hdr = {"Access-Token": r2.get("data", {}).get("accessToken", ""),
            "userId": str(qa_uid_num), "language": "en"}
check("login", r2.get("code") == 1, str(r2)[:100])
cat = call("GET", "/game/api/v1/game/revision/list/by/condition"
           "?sortType=online&filterTypeId=0&pageNo=1&pageSize=10&os=android&isFilter=1",
           headers={"language": "en"})
first_game = ((cat.get("data", {}).get("pageInfo", {}).get("data") or [{}])[0]
              .get("gameId", "5001"))

# --- dispatch token (Wave 29c mirror for the follow chain) ------------
p1 = call("GET", "/game/api/v2/game/auth?typeId=%s&targetId=%d&gameVersion=1"
          % (first_game, qa_uid_num), headers=auth_hdr)
mg = p1.get("data", {})
check("dispatch token", p1.get("code") == 1 and mg.get("token", "").startswith("mg-"),
      str(p1)[:110])

# ===== Wave 29d chains (mirror of the suite block) =====================
vf = call("POST", "/video/api/v1/app/video/praise/%d" % (int(time.time()) % 900000 + 7),
          None, headers=auth_hdr)
check("video praise zero ack", vf.get("code") == 1 and vf.get("data") == 0, str(vf)[:100])
vd = call("POST", "/video/api/v1/app/video/dislike/%d" % (int(time.time()) % 900000 + 7),
          None, headers=auth_hdr)
check("video dislike zero ack", vd.get("code") == 1 and vd.get("data") == 0, str(vd)[:100])
vpa = call("POST", "/video/api/v1/app/video/report/play/amount",
           {"videoId": 7, "playAmount": 1}, headers=auth_hdr)
check("video play-amount ack", vpa.get("code") == 1 and vpa.get("data") == 0, str(vpa)[:100])

# throwaway device-account lifecycle
im = "rig-29d-%d" % (int(time.time()) % 1000000)
dev = call("POST", "/user/api/v1/app/login", {"imei": im})
dev_d = dev.get("data") or {}
check("imei-only app login device account",
      dev.get("code") == 1 and dev_d.get("userId", 0) > 0 and dev_d.get("accessToken"),
      str(dev)[:130])
vh = {"Access-Token": dev_d.get("accessToken", ""),
      "userId": str(dev_d.get("userId", 0)), "language": "en"}
vis = call("POST", "/user/api/v1/visitor", {"imei": im})
vis_d = vis.get("data") or {}
check("visitor creation", vis.get("code") == 1 and vis_d.get("id", 0) > 0
      and vis_d.get("accessToken"), str(vis)[:110])
vr = call("POST", "/user/api/v1/app/renew?userId=%s" % dev_d.get("userId"), None,
          headers=vh)
vr_d = vr.get("data") or {}
check("renew fresh accessToken", vr.get("code") == 1
      and vr_d.get("userId") == dev_d.get("userId") and vr_d.get("accessToken"),
      str(vr)[:130])
vh["Access-Token"] = vr_d.get("accessToken", "")
lr = call("GET", "/user/api/v1/user/login/change/record", None, headers=vh)
lr_d = lr.get("data") or {}
check("login change record echoes last login", lr.get("code") == 1
      and lr_d.get("appType") == "android" and lr_d.get("loginTime"), str(lr)[:120])
lo = call("PUT", "/user/api/v1/user/login-out", None, headers=vh)
check("login-out drops token", lo.get("code") == 1, str(lo)[:100])
vl2 = call("POST", "/user/api/v1/app/login", {"imei": im})
vl2_d = vl2.get("data") or {}
check("re-login after logout (persistence)", vl2.get("code") == 1
      and vl2_d.get("userId") == dev_d.get("userId") and vl2_d.get("accessToken"),
      str(vl2)[:130])
vh["Access-Token"] = vl2_d.get("accessToken", "")
am = call("POST", "/user/api/v1/user/account/modify",
          {"account": "rig29dacc%d" % (int(time.time()) % 100000)}, headers=vh)
check("account modify re-keys", am.get("code") == 1, str(am)[:110])
rg = call("POST", "/user/api/v1/user/register", {"nickName": "rig29dreg", "sex": 1},
          headers=vh)
rg_d = rg.get("data") or {}
check("user register echoes nickname", rg.get("code") == 1
      and rg_d.get("nickName") == "rig29dreg", str(rg)[:110])
rp = call("POST", "/user/api/v1/report/push", {"report": True}, headers=vh)
rp2 = call("POST", "/user/api/v1/report/status", {"status": 1}, headers=vh)
check("report push/status acks", rp.get("code") == 1 and rp2.get("code") == 1,
      "%s | %s" % (str(rp)[:60], str(rp2)[:60]))
up = call("POST", "/user/api/v1/file", {"b64": "rig"}, headers=vh)
up2 = call("POST", "/user/api/v1/directory/file", {"b64": "rig"}, headers=vh)
check("upload without multipart rejected", up.get("code") != 1 and up2.get("code") != 1,
      "%s | %s" % (str(up)[:80], str(up2)[:80]))
bp = call("POST", "/user/api/v1/user/bind/phone", {"phone": "13800002900", "code": "1234"},
          headers=vh)
check("bind phone", bp.get("code") == 1, str(bp)[:100])
pw = call("POST", "/user/api/v1/user/password",
          {"phone": "13800002900", "password": password, "confirmPassword": password},
          headers=vh)
check("phone password set", pw.get("code") == 1, str(pw)[:100])
bp2 = call("POST", "/user/api/v1/user/unbind/phone", None, headers=vh)
check("unbind phone", bp2.get("code") == 1, str(bp2)[:100])
sm = call("POST", "/user/api/v1/sms/send/13800002900", None, headers=vh)
check("sms/send ack", sm.get("code") == 1, str(sm)[:100])
sm2 = call("POST", "/user/api/v1/sms/send/refound", {"phone": "13800002900"}, headers=vh)
check("sms refound ack", sm2.get("code") == 1, str(sm2)[:100])

# qa-session user-misc reads + reward chains
pi = call("GET", "/user/api/v1/user/player/info", None, headers=auth_hdr)
pi_d = pi.get("data") or {}
check("player info vip triple", pi.get("code") == 1 and "vip" in pi_d
      and "expireDate" in pi_d and "gDiamonds" in pi_d, str(pi)[:120])
idc = call("GET", "/user/api/v1/user/id/card/status", None, headers=auth_hdr)
check("id-card status str-0", idc.get("code") == 1 and idc.get("data") == "0", str(idc)[:100])
idc2 = call("POST", "/user/api/v1/user/id/card/status", {"name": "rig", "idCard": "x"},
            headers=auth_hdr)
check("id-card submit stays str-0", idc2.get("code") == 1 and idc2.get("data") == "0",
      str(idc2)[:100])
js = call("GET", "/user/api/v1/user/profile/join/switch", None, headers=auth_hdr)
check("join switch reads true", js.get("code") == 1 and js.get("data") is True, str(js)[:100])
js2 = call("POST", "/user/api/v1/user/profile/join/switch", {"joinSwitch": False},
           headers=auth_hdr)
check("join switch write acked", js2.get("code") == 1, str(js2)[:100])
fq = call("GET", "/user/api/v1/data/frequently/game/%d" % qa_uid_num, None, headers=auth_hdr)
fq_rows = [g for g in (fq.get("data") or []) if isinstance(g, dict) and g.get("gameId")]
check("frequently-played recent-else-catalog", fq.get("code") == 1 and len(fq_rows) >= 3,
      str(fq)[:130])
dai = call("GET", "/user/api/v1/clan/decoration/advertising/%d" % qa_uid_num, None,
           headers=auth_hdr)
dai_d = dai.get("data") or {}
check("clan advertising info obj", dai.get("code") == 1 and dai_d.get("adType") == 1
      and "qty" in dai_d and "nextQty" in dai_d, str(dai)[:120])
wa = call("GET", "/pay/api/v1/wealth/user", headers=auth_hdr).get("data", {})
dar = call("PUT", "/user/api/v1/clan/decoration/advertising/%d" % qa_uid_num, None,
           headers=auth_hdr)
dar_d = dar.get("data") or {}
wb = call("GET", "/pay/api/v1/wealth/user", headers=auth_hdr).get("data", {})
check("advertising reward +150 (wallet untouched)", dar.get("code") == 1
      and dar_d.get("quantity") == 150 and wb.get("golds", 0) == wa.get("golds", 0),
      "%s | w %s -> %s" % (str(dar)[:90], wa, wb))
pc0 = call("POST", "/user/api/v1/users/prefect/info/reward/check/%d" % qa_uid_num,
           None, headers=auth_hdr)
check("prefect check boolean", pc0.get("code") == 1 and isinstance(pc0.get("data"), bool),
      str(pc0)[:100])
if pc0.get("data") is False:
    ci = call("POST", "/user/api/v1/user/details/info", {"details": "rig profile"},
              headers=auth_hdr)
    check("profile details fill", ci.get("code") == 1, str(ci)[:100])
    pc1 = call("POST", "/user/api/v1/users/prefect/info/reward/check/%d" % qa_uid_num,
               None, headers=auth_hdr)
    check("prefect check flips true", pc1.get("code") == 1 and pc1.get("data") is True,
          str(pc1)[:100])
else:
    print("  [info] prefect already done - skipping fill chain")
wc = call("GET", "/pay/api/v1/wealth/user", headers=auth_hdr).get("data", {})
prw = call("POST", "/user/api/v1/users/prefect/info/reward/%d" % qa_uid_num, None,
           headers=auth_hdr)
prw_d = prw.get("data") or {}
wd = call("GET", "/pay/api/v1/wealth/user", headers=auth_hdr).get("data", {})
check("prefect reward +500 golds", prw.get("code") == 1 and prw_d.get("golds") == 500
      and wd.get("golds", 0) == wc.get("golds", 0) + 500,
      "%s | w %s -> %s" % (str(prw)[:110], wc, wd))
prw2 = call("POST", "/user/api/v1/users/prefect/info/reward/%d" % qa_uid_num, None,
            headers=auth_hdr)
check("prefect re-reward rejected", prw2.get("code") != 1, str(prw2)[:100])
we = call("GET", "/pay/api/v1/wealth/user", headers=auth_hdr).get("data", {})
sr = call("POST", "/user/api/v1/users/sharing/reward", None, headers=auth_hdr)
wf = call("GET", "/pay/api/v1/wealth/user", headers=auth_hdr).get("data", {})
check("share reward +200 (first claim)", sr.get("code") == 1
      and wf.get("golds", 0) == we.get("golds", 0) + 200,
      "%s | w %s -> %s" % (str(sr)[:110], we, wf))
sr2 = call("POST", "/user/api/v1/users/sharing/reward", None, headers=auth_hdr)
check("share re-reward rejected", sr2.get("code") != 1, str(sr2)[:100])
wg = call("GET", "/pay/api/v1/wealth/user", headers=auth_hdr).get("data", {})
ra = call("PUT", "/game/api/v1/game/record/ads", None, headers=auth_hdr)
wh = call("GET", "/pay/api/v1/wealth/user", headers=auth_hdr).get("data", {})
check("record-ads +100 golds", ra.get("code") == 1 and ra.get("data") == 100
      and wh.get("golds", 0) == wg.get("golds", 0) + 100,
      "%s | w %s -> %s" % (str(ra)[:110], wg, wh))
# gift-suit: mirror the suite order (suit catalog read -> gift claim ->
# then suitGiftInfo serves the claimed empty state)
gcat = call("GET", "/shop/api/v1/new/shop/suit/decorations?os=android&engineVersion=1",
            headers=auth_hdr)
gift_id = (gcat.get("data") or [{}])[0].get("suitId", 600001)
gp = call("POST", "/shop/api/v1/new/shop/gift/suit/receive?suitId=%s" % gift_id,
          {}, headers=auth_hdr)
check("gift-suit claim", gp.get("code") == 1, str(gp)[:110])
gs = call("GET", "/shop/api/v1/new/shop/gift/suit/receive", None, headers=auth_hdr)
check("gift-suit info claimed-empty", gs.get("code") == 1 and gs.get("data") == {},
      str(gs)[:110])
aic1 = call("POST", "/user/api/v1/account/invalid/check?account=rig-29d-fresh", None,
            headers=auth_hdr)
check("invalid-check fresh available", aic1.get("code") == 1 and aic1.get("data") is True,
      str(aic1)[:110])
aic2 = call("POST", "/user/api/v1/account/invalid/check?account=%s" % qa_uid, None,
            headers=auth_hdr)
check("invalid-check own uid taken", aic2.get("code") == 1 and aic2.get("data") is False,
      str(aic2)[:110])
be = call("POST", "/user/api/v1/users/bind/email", {"email": "rig29d@example.com"},
          headers=auth_hdr)
check("bind email", be.get("code") == 1, str(be)[:100])
ue = call("DELETE", "/user/api/v2/users/%d/emails" % qa_uid_num, None, headers=auth_hdr)
check("unbind email v2", ue.get("code") == 1, str(ue)[:100])
ap = call("PUT", "/game/api/v1/games/%s/appreciation" % first_game, None, headers=auth_hdr)
check("appreciation first like", ap.get("code") == 1, str(ap)[:100])
ap2 = call("PUT", "/game/api/v1/games/%s/appreciation" % first_game, None, headers=auth_hdr)
check("re-appreciation rejected (2005)", ap2.get("code") != 1, str(ap2)[:110])
fs = call("GET", "/friend/api/v1/friend/status/%d" % qa_uid_num, None, headers=auth_hdr)
check("friend status self 2", fs.get("code") == 1 and fs.get("data") == 2, str(fs)[:100])
tm = call("GET", "/game/api/v1/games/team/member/%d" % qa_uid_num, None, headers=auth_hdr)
tm_rows = [t for t in (tm.get("data") or []) if isinstance(t, dict) and t.get("userId")]
check("team member rows", tm.get("code") == 1 and len(tm_rows) >= 1
      and "nickName" in tm_rows[0] and "isTeam" in tm_rows[0], str(tm)[:120])
gh = call("GET", "/game/api/v1/games/warmup/%s/languages/en" % first_game, None,
          headers=auth_hdr)
gh_d = gh.get("data") or {}
check("game preheat echo", gh.get("code") == 1 and gh_d.get("gameId") == first_game
      and gh_d.get("isPublish") == 1, str(gh)[:120])
sl = call("GET", "/shop/api/v1/shop/decorations/1", None, headers=auth_hdr)
sl_rows = [r for r in (sl.get("data") or []) if isinstance(r, dict) and r.get("id")]
check("shop decorations v1 wildcard", sl.get("code") == 1 and len(sl_rows) >= 1, str(sl)[:120])
vp = call("GET", "/decoration/api/v1/vip/decorations/users/1", None, headers=auth_hdr)
check("vip decorations empty list", vp.get("code") == 1 and vp.get("data") == [], str(vp)[:100])
wcr = call("PUT", "/activity/api/v1/activity/task/reward", {"type": 1}, headers=auth_hdr)
check("worldcup task reward inactive", wcr.get("code") != 1, str(wcr)[:110])
fol = call("POST", "/v1/follow",
           {"clz": 0, "name": "rig", "pioneer": True, "targetId": qa_uid_num,
            "resVersion": 1, "ever": 1, "picUrl": "", "packageName": "ci",
            "appVer": "1.24.4", "country": "us", "lang": "en", "rid": 0},
           headers={"x-shahe-uid": str(qa_uid_num), "x-shahe-token": mg.get("token", "")})
check("follow dispatch loopback engine", fol.get("code") == 1
      and (fol.get("data") or {}).get("gaddr") == "127.0.0.1:18080", str(fol)[:150])
dr1 = call("POST", "/datareport/api/v1/app/ping/report/batch", {"events": [{"ping": 30}]},
           headers=auth_hdr)
dr2 = call("POST", "/datareport/api/v1/event/report", [{"eventId": "rig_29d", "count": 1}],
           headers=auth_hdr)
dr3 = call("POST", "/datareport/api/v1/funnel/event/report", [{"funnelId": "rig_29d", "step": 1}],
           headers=auth_hdr)
check("datareport family acks", dr1.get("code") == 1 and dr2.get("code") == 1
      and dr3.get("code") == 1,
      "%s | %s | %s" % (str(dr1)[:60], str(dr2)[:60], str(dr3)[:60]))
gl = call("GET", "/msg/api/v1/msg/group/chat/list", None, headers=auth_hdr)
gl_page = (gl.get("data") or {}) if isinstance(gl.get("data"), dict) else {}
gl_rows = [g for g in (gl_page.get("data") or []) if isinstance(g, dict) and g.get("groupId")]
if gl_rows:
    gm = call("POST", "/msg/api/v1/msg/group/chat/mail/add?groupId=%d" % gl_rows[0]["groupId"],
              None, headers=auth_hdr)
    gm_d = gm.get("data") or {}
    check("group mail add serves group info", gm.get("code") == 1 and gm_d.get("groupId"),
          str(gm)[:130])
else:
    print("  [info] no group on the rig session - mail add skipped")

print("RESULT: %d checks, %d failed" % (len(fails) + 0 if fails else 0, len(fails))
      if False else "RESULT: %s" % ("ALL OK" if not fails else "FAILS: %s" % fails))
proc.terminate()
sys.exit(1 if fails else 0)
