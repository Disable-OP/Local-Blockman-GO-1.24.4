#!/usr/bin/env python3
"""Wave 29b host-rig precheck (part 1: decoration using roundtrip).
Boots the embedded server fresh (same boot as scripts/test_server_host.py)
and drives the exact chains Wave 29b asserts on device."""
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
state = tempfile.mkdtemp(prefix="rig29b-")
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
qa = "rig%05d" % (int(time.time()) % 100000)
r1 = call("POST", "/user/api/v1/register",
          {"uid": qa, "password": "RigPass123", "confirmPassword": "RigPass123",
           "imei": "rig-device", "appType": "android", "os": "12"})
qa_id = (r1.get("data") or {}).get("userId", 0)
hdr = {"Access-Token": (r1.get("data") or {}).get("accessToken", ""),
       "userId": str(qa_id), "language": "en"}
check("register", r1.get("code") == 1 and qa_id > 0, str(r1)[:120])

# gift suit -> owned dresses (the Wave-29a chain)
p3 = call("GET", "/shop/api/v1/new/shop/suit/decorations?os=android&engineVersion=1",
          headers={"language": "en"})
sid = (p3.get("data") or [{}])[0].get("suitId", 0)
p5 = call("POST", "/shop/api/v1/new/shop/gift/suit/receive?suitId=%d" % sid,
          {}, headers=hdr)
d29 = [d for d in (p5.get("data") or []) if isinstance(d, dict) and d.get("id")]
check("gift suit claimed", p5.get("code") == 1 and len(d29) >= 2, str(p5)[:140])
a29, b29 = d29[0]["id"], d29[1]["id"]

# 1) multiClothe PUT using/new
mc = call("PUT", "/decoration/api/v1/decorations/using/new?ids=%d,%d" % (a29, b29),
          None, headers=hdr)
mc_ids = [x.get("id") for x in (mc.get("data") or []) if isinstance(x, dict)]
check("multiClothe wears the pair", mc.get("code") == 1
      and a29 in mc_ids and b29 in mc_ids, str(mc)[:160])
worn = call("GET", "/decoration/api/v1/decorations/using", headers=hdr)
worn_ids = [x.get("id") for x in (worn.get("data") or []) if isinstance(x, dict)]
check("worn list holds both", worn.get("code") == 1 and a29 in worn_ids
      and b29 in worn_ids, str(worn)[:160])

# 2) useSuitDecoration PUT using (owned re-wear + unowned rejection)
us = call("PUT", "/decoration/api/v1/decorations/using?ids=%d" % a29,
          None, headers=hdr)
us_ids = [x.get("id") for x in (us.get("data") or []) if isinstance(x, dict)]
check("useSuitDecoration re-wears owned", us.get("code") == 1 and a29 in us_ids,
      str(us)[:150])
us_bad = call("PUT", "/decoration/api/v1/decorations/using?ids=999991",
              None, headers=hdr)
check("useSuitDecoration rejects unowned", us_bad.get("code") != 1,
      str(us_bad)[:120])

# 3) removeSuitDecoration DELETE using (list unwear)
rs = call("DELETE", "/decoration/api/v1/decorations/using?ids=%d" % a29,
          None, headers=hdr)
worn_b = call("GET", "/decoration/api/v1/decorations/using", headers=hdr)
worn_b_ids = [x.get("id") for x in (worn_b.get("data") or [])
              if isinstance(x, dict)]
rs_ids = [x.get("id") for x in (rs.get("data") or []) if isinstance(x, dict)]
check("removeSuitDecoration unwears list (b still worn)",
      rs.get("code") == 1 and a29 in rs_ids and a29 not in worn_b_ids
      and b29 in worn_b_ids, "%s | worn %s" % (str(rs)[:120], worn_b_ids))

# 4) removeDecoration DELETE using/{id} (echo + unknown rejection)
rd = call("DELETE", "/decoration/api/v1/decorations/using/%d" % b29,
          None, headers=hdr)
check("removeDecoration unwears one (data.id echo)", rd.get("code") == 1
      and (rd.get("data") or {}).get("id") == b29, str(rd)[:130])
rd_bad = call("DELETE", "/decoration/api/v1/decorations/using/999992",
              None, headers=hdr)
check("removeDecoration rejects unknown", rd_bad.get("code") != 1,
      str(rd_bad)[:120])

# 5) multiUnclothe DELETE using/new (re-worn first for a real diff)
call("PUT", "/decoration/api/v1/decorations/using/new?ids=%d,%d" % (a29, b29),
     None, headers=hdr)
mu = call("DELETE", "/decoration/api/v1/decorations/using/new?ids=%d,%d" % (a29, b29),
          None, headers=hdr)
worn_c = call("GET", "/decoration/api/v1/decorations/using", headers=hdr)
worn_c_ids = [x.get("id") for x in (worn_c.get("data") or [])
              if isinstance(x, dict)]
check("multiUnclothe unwears pair (empty again)", mu.get("code") == 1
      and a29 not in worn_c_ids and b29 not in worn_c_ids,
      "%s | worn %s" % (str(mu)[:120], worn_c_ids))

proc.terminate()
print("RIG RESULT: %d failed" % len(fails))
if fails:
    print("FAILED:", fails)
sys.exit(1 if fails else 0)
