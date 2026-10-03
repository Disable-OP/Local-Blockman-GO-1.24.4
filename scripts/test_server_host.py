#!/usr/bin/env python3
"""Host-JVM integration test for the embedded local API server.

Boots localapi-server HostTest (plain JVM, temp state dir) and drives the
login/register/visitor/tourist flows + config endpoints + a route-table
sweep with real HTTP. Fails (exit 1) on any broken contract.
"""
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
BUILD = os.path.join(REPO, "localapi-server", "build")
HOST_CP = os.pathsep.join([
    os.path.join(BUILD, "host"),
    os.path.join(BUILD, "classes"),
    os.path.join(REPO, ".javatools", "nanohttpd.jar"),
    os.path.join(REPO, ".javatools", "json.jar"),
])
PORT = int(os.environ.get("LOCALAPI_TEST_PORT", str(random.randint(20000, 40000))))
BASE = "http://127.0.0.1:%d" % PORT

passed, failed = [], []


def call(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"__http_error": e.code}


def check(name, cond, detail=""):
    if cond:
        passed.append(name)
        print("  PASS %s" % name)
    else:
        failed.append(name)
        print("  FAIL %s  %s" % (name, detail))


def wait_ready(timeout=30):
    import socket
    end = time.time() + timeout
    while time.time() < end:
        try:
            s = socket.create_connection(("127.0.0.1", PORT), timeout=1)
            s.close()
            return True
        except OSError:
            time.sleep(0.25)
    return False


def main():
    state_dir = tempfile.mkdtemp(prefix="localapi-test-")
    proc = subprocess.Popen(
        ["java", "-cp", HOST_CP, "com.localapi.HostTest", state_dir, str(PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        if not wait_ready():
            print("server failed to boot (port %d)" % PORT)
            try:
                proc.terminate()
                out, _ = proc.communicate(timeout=5)
                print(out.decode(errors="replace"))
            except Exception as e:
                print("diag failed:", e)
            sys.exit(1)

        print("== boot configs ==")
        v = call("GET", "/config/files/blockymods-check-version")
        check("checkVersion code==1", v.get("code") == 1, str(v)[:100])
        check("checkVersion newVersionCode==4003",
              v.get("data", {}).get("newVersionCode") == 4003, str(v)[:100])
        c = call("GET", "/config/files/blockmods-config-v1")
        check("appConfig code==1 no-ads", c.get("code") == 1
              and c.get("data", {}).get("isShowAds") is False, str(c)[:100])
        b = call("GET", "/config/files/blockymods-banner")
        check("banner list==[]", b.get("code") == 1 and b.get("data") == [], str(b)[:100])
        s = call("GET", "/config/files/name-sensitive-word-config")
        check("sensitiveWords list", isinstance(s.get("data"), list), str(s)[:100])

        print("== register / login ==")
        r = call("POST", "/user/api/v1/register",
                 {"uid": "qa_user1", "password": "pw1", "confirmPassword": "pw1",
                  "imei": "dev1", "appType": "android", "os": "12"})
        check("register ok", r.get("code") == 1 and r.get("data", {}).get("userId", 0) > 0, str(r)[:150])
        uid1 = r.get("data", {}).get("userId")
        tok1 = r.get("data", {}).get("accessToken", "")
        check("register has accessToken+wallet", bool(tok1)
              and r["data"].get("golds", 0) > 0, str(r)[:150])
        r2 = call("POST", "/user/api/v1/register", {"uid": "qa_user1", "password": "x"})
        check("register dup rejected", r2.get("code") == 0, str(r2)[:100])
        lg = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        check("login ok same userId", lg.get("code") == 1
              and lg.get("data", {}).get("userId") == uid1, str(lg)[:150])
        bad = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "WRONG", "imei": "dev1"})
        check("login wrong pw rejected", bad.get("code") == 0, str(bad)[:100])
        lg2 = call("POST", "/user/api/v1/app/login", {"uid": "qa_user1", "password": "pw1"},
                   {"bmg-device-id": "Android:redroid", "bmg-sign": "abc"})
        check("app/login ok", lg2.get("code") == 1, str(lg2)[:100])
        lg3 = call("POST", "/user/api/v2/app/login", {"uid": "qa_user1", "password": "pw1"})
        check("v2/app/login ok", lg3.get("code") == 1, str(lg3)[:100])
        nog = call("POST", "/user/api/v1/login", {"uid": "ghost_user", "password": "pw"})
        check("login unknown account rejected", nog.get("code") == 0, str(nog)[:100])

        print("== visitor / tourist ==")
        vis = call("POST", "/user/api/v1/visitor", {"imei": "qaimei1"})
        check("visitor ok", vis.get("code") == 1 and vis.get("data", {}).get("id", 0) > 0
              and vis.get("data", {}).get("accessToken"), str(vis)[:150])
        vis2 = call("POST", "/user/api/v1/visitor", {"imei": "qaimei1"})
        check("visitor stable per imei", vis2.get("data", {}).get("id")
              == vis.get("data", {}).get("id"), str(vis2)[:100])
        tou = call("POST", "/user/api/v1/app/user/tourist/login?appType=android", None,
                   {"bmg-device-id": "Android:redroid"})
        check("tourist ok", tou.get("code") == 1 and tou.get("data", {}).get("userId", 0) > 0, str(tou)[:150])
        tou2 = call("POST", "/user/api/v1/app/user/tourist/login?appType=android", None,
                    {"bmg-device-id": "Android:redroid"})
        check("tourist stable per device", tou2.get("data", {}).get("userId")
              == tou.get("data", {}).get("userId"), str(tou2)[:100])

        print("== token lifecycle ==")
        at = call("GET", "/user/api/v1/app/auth-token?userId=%d&androidId=x&signature=y" % uid1)
        check("auth-token ok", at.get("code") == 1 and at.get("data", {}).get("userId") == uid1
              and at.get("data", {}).get("accessToken"), str(at)[:150])
        rn = call("POST", "/user/api/v1/app/renew?androidId=x&signature=y")
        check("renew ok", rn.get("code") == 1 and rn.get("data", {}).get("accessToken"), str(rn)[:150])
        rt = call("GET", "/user/api/v1/users/device/token",
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("rongToken string", rt.get("code") == 1 and isinstance(rt.get("data"), str), str(rt)[:100])
        lo = call("PUT", "/user/api/v1/user/login-out", headers={"Access-Token": tok1})
        check("logout ok", lo.get("code") == 1, str(lo)[:100])

        print("== profile ==")
        cn = call("PUT", "/user/api/v2/user/nickName?nickName=QAChanged",
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("changeNickName", cn.get("code") == 1
              and cn.get("data", {}).get("nickName") == "QAChanged", str(cn)[:150])
        ur = call("POST", "/user/api/v1/user/register",
                  {"nickName": "RoleQA", "sex": 1, "inviteCode": ""},
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("userRegister role-make", ur.get("code") == 1
              and ur.get("data", {}).get("nickName") == "RoleQA", str(ur)[:150])
        ci = call("PUT", "/user/api/v1/user/info", {"details": "local player"},
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("changeInfo", ci.get("code") == 1
              and ci.get("data", {}).get("details") == "local player", str(ci)[:150])
        js = call("GET", "/user/api/v1/user/profile/join/switch")
        check("join/switch bool", js.get("code") == 1
              and isinstance(js.get("data"), bool), str(js)[:100])

        print("== route-table sweep (all routes answer the envelope) ==")
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        sweep_miss = []
        count = 0
        with open(os.path.join(REPO, "localapi-server", "src", "com", "localapi", "RoutingTable.java")) as f:
            import re
            for m in re.finditer(r'"([A-Z]+) ([^|]+)\|([a-z]+|H:[a-zA-Z]+)"', f.read()):
                verb, path, kind = m.group(1), m.group(2), m.group(3)
                concrete = re.sub(r"\{[^}]+\}", "123", path)
                resp = call(verb if verb in ("GET", "POST", "PUT", "DELETE") else "GET", concrete, {})
                count += 1
                ok = resp.get("code") == 1
                if not ok and kind.startswith("H:"):
                    # handlers correctly reject empty/invalid payloads (code 0)
                    ok = resp.get("code") == 0
                if not ok:
                    sweep_miss.append((verb, concrete, resp))
        check("sweep %d routes all reachable" % count, not sweep_miss, str(sweep_miss[:5]))

        print("== persistence ==")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        time.sleep(1.5)
    # second boot must see persisted users
    proc2 = subprocess.Popen(
        ["java", "-cp", HOST_CP, "com.localapi.HostTest", state_dir, str(PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        if not wait_ready():
            print("server restart failed")
            sys.exit(1)
        lg = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1"})
        check("state persists across restart", lg.get("code") == 1
              and lg.get("data", {}).get("userId") == uid1, str(lg)[:150])
    finally:
        proc2.terminate()
        try:
            proc2.wait(timeout=5)
        except Exception:
            proc2.kill()

    print("\nRESULT: %d passed, %d failed" % (len(passed), len(failed)))
    if failed:
        print("failed:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
