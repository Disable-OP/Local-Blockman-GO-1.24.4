#!/usr/bin/env python3
"""Wave 29b host-rig precheck (part 2: social chains). Unfriend roundtrip,
group reject + transfer with a second account, chat-room lifecycle,
videostars family."""
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
state = tempfile.mkdtemp(prefix="rig29c-")
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


# --- two sessions ------------------------------------------------------
qa = "rig%05d" % (int(time.time()) % 100000)
r1 = call("POST", "/user/api/v1/register",
          {"uid": qa, "password": "RigPass123", "confirmPassword": "RigPass123",
           "imei": "rig-device", "appType": "android", "os": "12"})
qa_id = (r1.get("data") or {}).get("userId", 0)
hdr = {"Access-Token": (r1.get("data") or {}).get("accessToken", ""),
       "userId": str(qa_id), "language": "en"}
gf = "rigf%05d" % (int(time.time()) % 100000)
gfr = call("POST", "/user/api/v1/register",
           {"uid": gf, "password": "RigPass123", "confirmPassword": "RigPass123",
            "imei": "rigf-device", "appType": "android", "os": "12"})
gf_id = (gfr.get("data") or {}).get("userId", 0)
gf_hdr = {"Access-Token": (gfr.get("data") or {}).get("accessToken", ""),
          "userId": str(gf_id), "language": "en"}
check("two accounts registered", qa_id > 0 and gf_id > 0,
      "%s | %s" % (str(r1)[:80], str(gfr)[:80]))

# friendship
fadd = call("POST", "/friend/api/v1/friends", {"friendId": gf_id, "msg": "rig"},
            headers=hdr)
fagr = call("PUT", "/friend/api/v1/friends/%d/agreement" % qa_id, None,
            headers=gf_hdr)
check("friendship made", fadd.get("code") == 1 and fagr.get("code") == 1,
      "%s | %s" % (str(fadd)[:80], str(fagr)[:80]))

# unfriend roundtrip
fl = call("GET", "/friend/api/v1/friends?pageNo=1&pageSize=20", headers=hdr)
fl_ids = [f.get("userId") for f in ((fl.get("data") or {}).get("data") or [])
          if isinstance(f, dict)]
check("friend list holds friend", fl.get("code") == 1 and gf_id in fl_ids,
      str(fl)[:140])
unf = call("DELETE", "/friend/api/v1/friends?friendId=%d" % gf_id, None,
           headers=hdr)
fl_b = call("GET", "/friend/api/v1/friends?pageNo=1&pageSize=20", headers=hdr)
fl_b_ids = [f.get("userId") for f in ((fl_b.get("data") or {}).get("data") or [])
            if isinstance(f, dict)]
check("unfriend removes both sides", unf.get("code") == 1
      and gf_id not in fl_b_ids, "%s | %s" % (str(unf)[:100], fl_b_ids))
unf_b = call("DELETE", "/friend/api/v1/friends?friendId=%d" % gf_id, None,
             headers=hdr)
check("re-unfriend fails", unf_b.get("code") != 1, str(unf_b)[:110])
readd = call("POST", "/friend/api/v1/friends", {"friendId": gf_id, "msg": "re"},
             headers=hdr)
fagr2 = call("PUT", "/friend/api/v1/friends/%d/agreement" % qa_id, None,
             headers=gf_hdr)
check("friendship restored", readd.get("code") == 1 and fagr2.get("code") == 1,
      "%s | %s" % (str(readd)[:80], str(fagr2)[:80]))

# group reject: invite friend, decline from their feed
g1 = call("POST", "/msg/api/v2/msg/group/chat",
          {"cost": 0, "currency": 1, "memberIds": [], "userId": qa_id,
           "groupName": "RigG%d" % (int(time.time()) % 100000)}, headers=hdr)
gid = (g1.get("data") or {}).get("groupId", 0)
call("POST", "/msg/api/v1/msg/group/chat/add",
     {"groupId": gid, "memberIds": [gf_id]}, headers=hdr)
greq = call("GET", "/msg/api/v1/msg/group/chat/request/list?pageNo=1&pageSize=20",
            headers=gf_hdr)
inv = next((r for r in ((greq.get("data") or {}).get("data") or [])
            if isinstance(r, dict) and r.get("type") == 2
            and r.get("groupId") == gid and r.get("status") == 0), None)
check("invite in friend feed", inv is not None, str(greq)[:140])
if inv:
    grej = call("PUT", "/msg/api/v1/msg/group/chat/reject",
                {"groupId": gid, "requestId": inv["requestId"]}, headers=gf_hdr)
    check("reject declines the invite", grej.get("code") == 1, str(grej)[:120])
    greq_b = call("GET", "/msg/api/v1/msg/group/chat/request/list?pageNo=1&pageSize=20",
                  headers=gf_hdr)
    still = [r for r in ((greq_b.get("data") or {}).get("data") or [])
             if isinstance(r, dict) and r.get("type") == 2
             and r.get("groupId") == gid
             and r.get("requestId") == inv["requestId"]
             and r.get("status") == 0]
    check("rejected invite leaves the feed", greq_b.get("code") == 1
          and still == [], str(greq_b)[:130])

# transfer chain: fresh group, friend joins via invite, ownership moves
g2 = call("POST", "/msg/api/v2/msg/group/chat",
          {"cost": 0, "currency": 1, "memberIds": [], "userId": qa_id,
           "groupName": "RigT%d" % (int(time.time()) % 100000)}, headers=hdr)
g2id = (g2.get("data") or {}).get("groupId", 0)
call("POST", "/msg/api/v1/msg/group/chat/add",
     {"groupId": g2id, "memberIds": [gf_id]}, headers=hdr)
greq_c = call("GET", "/msg/api/v1/msg/group/chat/request/list?pageNo=1&pageSize=20",
              headers=gf_hdr)
inv2 = next((r for r in ((greq_c.get("data") or {}).get("data") or [])
             if isinstance(r, dict) and r.get("type") == 2
             and r.get("groupId") == g2id and r.get("status") == 0), None)
joined = False
if inv2:
    gacc = call("PUT", "/msg/api/v1/msg/group/chat/agreement",
                {"groupId": g2id, "requestId": inv2["requestId"],
                 "userId": qa_id}, headers=gf_hdr)
    acc_ids = [m.get("userId") for m in
               ((gacc.get("data") or {}).get("groupMembers") or [])]
    joined = gacc.get("code") == 1 and gf_id in acc_ids
    check("invitee joins transfer group", joined, str(gacc)[:130])
if joined:
    gtr = call("PUT", "/msg/api/v1/msg/group/chat/transfer",
               {"groupId": g2id, "userId": gf_id}, headers=hdr)
    g2d = gtr.get("data") or {}
    g2m = {m.get("userId"): m.get("identity")
           for m in g2d.get("groupMembers") or []}
    check("transfer hands ownership over", gtr.get("code") == 1
          and str(g2d.get("ownerId")) == str(gf_id) and g2m.get(gf_id) == 2
          and g2m.get(qa_id) == 0, str(gtr)[:160])
    gtr_bad = call("PUT", "/msg/api/v1/msg/group/chat/transfer",
                   {"groupId": g2id, "userId": qa_id}, headers=hdr)
    check("deposed owner cannot transfer again", gtr_bad.get("code") != 1,
          str(gtr_bad)[:110])
    fq = call("PUT", "/msg/api/v1/msg/group/chat/quit?groupId=%d" % g2id,
              None, headers=gf_hdr)
    check("owner quit deletes emptied group", fq.get("code") == 1,
          str(fq)[:100])

# chat room lifecycle
cr = call("POST", "/game/api/v1/game/chat/room?roomName=rig29room", None,
          headers=hdr)
cr_id = (cr.get("data") or {}).get("roomId", "")
check("chat room served", cr.get("code") == 1 and cr_id
      and (cr.get("data") or {}).get("roomName") == "rig29room",
      str(cr)[:130])
crd = call("DELETE", "/game/api/v1/game/chat/room?roomId=%s" % cr_id, None,
           headers=hdr)
crd_b = call("DELETE", "/game/api/v1/game/chat/room?roomId=%s" % cr_id, None,
             headers=hdr)
check("chat room delete + idempotent re-delete", crd.get("code") == 1
      and crd_b.get("code") == 1,
      "%s | %s" % (str(crd)[:80], str(crd_b)[:80]))

# videostars family
sc = call("GET", "/user/api/v1/videostars/config/get", headers=hdr)
sc_d = sc.get("data") or {}
check("videostars config served", sc.get("code") == 1
      and isinstance(sc_d.get("answering"), list)
      and isinstance(sc_d.get("introduce"), list), str(sc)[:130])
sg = call("GET", "/user/api/v1/videostars/getbycode?starCode=BG%d" % qa_id,
          headers=hdr)
sg_d = sg.get("data") or {}
check("getbycode resolves seeded code", sg.get("code") == 1
      and sg_d.get("userId") == qa_id
      and sg_d.get("starCode") == "BG%d" % qa_id, str(sg)[:140])
sg_bad = call("GET", "/user/api/v1/videostars/getbycode?starCode=BG0",
              headers=hdr)
check("getbycode rejects unknown", sg_bad.get("code") != 1, str(sg_bad)[:100])
sb = call("GET", "/user/api/v1/videostars/billing/list/get?pageNo=1&pageSize=20",
          headers=hdr)
sb_d = sb.get("data") or {}
check("billing page served", sb.get("code") == 1 and "todayProfit" in sb_d
      and isinstance((sb_d.get("data") or {}).get("data"), list), str(sb)[:130])
sca = call("PUT", "/user/api/v1/videostars/cashapply", {"money": 10},
           headers=hdr)
sca_d = sca.get("data") or {}
check("cashapply echoes money", sca.get("code") == 1
      and sca_d.get("money") == 10 and sca_d.get("userId") == qa_id,
      str(sca)[:140])
sca_bad = call("PUT", "/user/api/v1/videostars/cashapply", {"money": 0},
               headers=hdr)
check("cashapply rejects zero", sca_bad.get("code") != 1, str(sca_bad)[:100])
wpre = call("GET", "/pay/api/v1/wealth/user", headers=hdr)
sex = call("PUT", "/user/api/v1/videostars/exchange", {}, headers=hdr)
wpost = call("GET", "/pay/api/v1/wealth/user", headers=hdr)
check("exchange zero profit (wallet unchanged)", sex.get("code") == 1
      and (wpost.get("data") or {}).get("diamonds")
      == (wpre.get("data") or {}).get("diamonds"),
      "%s | %s -> %s" % (str(sex)[:80], wpre.get("data"), wpost.get("data")))

proc.terminate()
print("RIG RESULT: %d failed" % len(fails))
if fails:
    print("FAILED:", fails)
sys.exit(1 if fails else 0)
