#!/usr/bin/env python3
"""Host-JVM integration test for the embedded local API server.

Boots localapi-server HostTest (plain JVM, temp state dir) and drives the
login/register/visitor/tourist flows + config endpoints + a route-table
sweep with real HTTP. Fails (exit 1) on any broken contract.
"""
import base64
import json
import os
import random
import re
import socket
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


def call(method, path, body=None, headers=None, base=None):
    req = urllib.request.Request((base or BASE) + path, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"__http_error": e.code}


def call_raw(method, path, data, headers=None):
    """Raw-bytes request (multipart uploads); response parsed as JSON."""
    req = urllib.request.Request(BASE + path, method=method, data=data)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"__http_error": e.code}


def raw_get(url):
    """Fetch raw bytes from the server (file downloads)."""
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()
    except urllib.error.HTTPError:
        return b""


# ---- Wave 11: dependency-free RSA PKCS1v15 (client cipher simulation) ----

def _asn1_len(data, pos):
    ln = data[pos]
    pos += 1
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(data[pos:pos + n], "big")
        pos += n
    return ln, pos


def _asn1_tlv(data, pos):
    """Skip the tag byte, parse the length -> (content_start, content_len)."""
    pos += 1                                  # tag
    return _asn1_len(data, pos)


def _rsa_pub_from_java(path):
    """Parse PUBLIC_KEY_B64 (X509/SPKI) out of RsaCipher.java -> (n, e)."""
    try:
        src = open(path, encoding="utf-8").read()
        import re
        m = re.search(r'PUBLIC_KEY_B64 =\s*\n\s*"([A-Za-z0-9+/=]+)"', src)
        if not m:
            return None
        der = base64.b64decode(m.group(1))
        # SPKI: SEQUENCE { SEQUENCE { OID, NULL }, BIT STRING { SEQ { INT n, INT e } } }
        _, p = _asn1_tlv(der, 0)                      # outer SEQUENCE
        seq2_len, p = _asn1_tlv(der, p)               # algId SEQUENCE
        p += seq2_len                                 # skip algorithm id
        bit_len, p = _asn1_tlv(der, p)                # BIT STRING
        if der[p] != 0:
            return None                               # unused-bits must be 0
        p += 1
        _, p = _asn1_tlv(der, p)                      # inner key SEQUENCE
        n_len, p = _asn1_tlv(der, p)                  # INTEGER n
        if der[p] == 0:                               # leading zero (positive int)
            p += 1
            n_len -= 1
        n = int.from_bytes(der[p:p + n_len], "big")
        p += n_len
        e_len, p = _asn1_tlv(der, p)                  # INTEGER e
        e = int.from_bytes(der[p:p + e_len], "big")
        return (n, e)
    except Exception:
        return None


def _rsa_pkcs1_encrypt(message, pub):
    """PKCS1 v1.5: 0x00 0x02 || nonzero padding || 0x00 || message, then m^e mod n."""
    n, e = pub
    k = (n.bit_length() + 7) // 8
    pad_len = k - 3 - len(message)
    padding = bytearray()
    while len(padding) < pad_len:
        b = os.urandom(1)
        if b != b"\x00":
            padding += b
    em = b"\x00\x02" + bytes(padding) + b"\x00" + message
    return base64.b64encode(pow(int.from_bytes(em, "big"), e, n)
                            .to_bytes(k, "big")).decode()


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
    # Server logs sink to a FILE, not a pipe: an undrained pipe fills its 64KB
    # buffer after a few hundred requests and L.i() blocks forever, wedging
    # every handler thread (seen as sweep timeouts). Logcat has no such
    # backpressure on-device; this is purely a host-rig concern.
    server_log = open(os.path.join(state_dir, "server.log"), "wb")
    proc = subprocess.Popen(
        ["java", "-cp", HOST_CP, "com.localapi.HostTest", state_dir, str(PORT)],
        stdout=server_log, stderr=subprocess.STDOUT)
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
        check("register dup rejected (101)", r2.get("code") == 101, str(r2)[:100])
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
        check("login unknown account rejected (102)", nog.get("code") == 102, str(nog)[:100])

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

        print("== Phase 2: game catalog ==")
        cond = call("GET", "/game/api/v1/game/revision/list/by/condition"
                    "?sortType=online&filterTypeId=0&pageNo=1&pageSize=10&os=android&isFilter=1",
                    headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("listByCondition code==1 TypePageData",
              cond.get("code") == 1 and "pageInfo" in cond.get("data", {})
              and "typeId" in cond.get("data", {}), str(cond)[:120])
        page1 = cond.get("data", {}).get("pageInfo", {})
        check("listByCondition page has games",
              len(page1.get("data", [])) == 10 and page1.get("totalSize", 0) >= 40
              and page1.get("totalPage", 0) >= 4, str(page1)[:150])
        check("game model fields", all(k in page1["data"][0] for k in
              ("gameId", "gameTitle", "typeId", "onlineNumber", "gameTypes",
               "praiseNumber", "latestResVersions", "isUgcGame")), str(page1["data"][0])[:200])
        cond2 = call("GET", "/game/api/v1/game/revision/list/by/condition"
                     "?sortType=online&filterTypeId=0&pageNo=2&pageSize=10&os=android",
                     headers={"language": "en"})
        p2 = cond2.get("data", {}).get("pageInfo", {}).get("data", [])
        check("paging distinct pages", p2 and p2[0]["gameId"] != page1["data"][0]["gameId"],
              str(cond2)[:120])
        online_vals = [g["onlineNumber"] for g in page1["data"]]
        check("sortType=online desc", online_vals == sorted(online_vals, reverse=True),
              str(online_vals[:6]))
        cf = call("GET", "/game/api/v1/game/revision/list/by/condition"
                  "?sortType=online&filterTypeId=101&pageNo=1&pageSize=10&os=android")
        d_cf = cf.get("data", {})
        check("filterTypeId=101 only that category",
              d_cf.get("typeId") == 101 and all(g["typeId"] == 101 for g in d_cf.get("pageInfo", {}).get("data", []))
              and len(d_cf.get("pageInfo", {}).get("data", [])) > 0, str(cf)[:150])

        more = call("GET", "/game/api/v1/game/revision/list/more?pageNo=1&pageSize=5&isFilter=1&os=android")
        check("listMore PageData", more.get("code") == 1
              and len(more.get("data", {}).get("data", [])) == 5
              and "pageInfo" not in more.get("data", {}), str(more)[:120])
        rec = call("GET", "/game/api/v1/game/revision/list/recommend?isFilter=1&os=android")
        check("guessYouLike list", rec.get("code") == 1
              and isinstance(rec.get("data"), list) and len(rec["data"]) > 0, str(rec)[:100])
        rec2 = call("GET", "/game/api/v2/games/recommendation", headers={"language": "en"})
        check("recommendation v2 list", rec2.get("code") == 1 and len(rec2.get("data", [])) > 0,
              str(rec2)[:100])
        cat = call("GET", "/game/api/v1/games?pageNo=1&pageSize=10&orderType=complex&typeId=0&order=&isPublish=1",
                   headers={"language": "en"})
        check("category PageData", cat.get("code") == 1
              and len(cat.get("data", {}).get("data", [])) == 10, str(cat)[:120])
        ugc = call("GET", "/game/api/v1/games/ugc?language=en&pageSize=20&pageNo=1&os=android")
        check("ugc list all ugc", ugc.get("code") == 1
              and all(g["isUgcGame"] == 1 for g in ugc.get("data", {}).get("data", []))
              and len(ugc.get("data", {}).get("data", [])) > 0, str(ugc)[:120])
        byt = call("GET", "/game/api/v2/games/recommendation/type?type=PvP%20Arena&pageNo=1&pageSize=10&os=android")
        check("getGameByType", byt.get("code") == 1
              and len(byt.get("data", {}).get("data", [])) > 0, str(byt)[:120])
        recent = call("GET", "/game/api/v1/games/playlist/recently?isFilter=1",
                      headers={"Access-Token": tok1, "language": "en"})
        check("recentlyPlayList fresh empty", recent.get("code") == 1 and recent.get("data") == [],
              str(recent)[:100])

        print("== Phase 2: game detail ==")
        gid = page1["data"][0]["gameId"]
        gd = call("GET", "/game/api/v2/games/%s?appVersion=4003" % gid,
                  headers={"language": "en", "engineVersion": "1"})
        check("gameDetail v2", gd.get("code") == 1 and gd.get("data", {}).get("gameId") == gid
              and "gameDetail" in gd["data"], str(gd)[:150])
        gd1 = call("GET", "/game/api/v1/games/%s" % gid, headers={"language": "en"})
        check("miniGameDetail v1", gd1.get("code") == 1 and gd1["data"].get("gameId") == gid,
              str(gd1)[:120])
        pre = call("GET", "/game/api/v1/games/warmup/%s/languages/en" % gid)
        check("gamePreheat shape", pre.get("code") == 1 and pre.get("data", {}).get("gameId") == gid
              and pre["data"].get("isPublish") == 1
              and "gameTitle" in pre["data"], str(pre)[:150])
        gnf = call("GET", "/game/api/v2/games/99999999")
        check("gameDetail unknown -> code 2002", gnf.get("code") == 2002, str(gnf)[:100])

        print("== Phase 2: categories, ranks, shop ==")
        cats = call("GET", "/game/api/v1/category/list/by/language", headers={"language": "en"})
        check("category list", cats.get("code") == 1 and len(cats.get("data", [])) >= 6
              and all("typeId" in c and "typeName" in c for c in cats["data"]), str(cats)[:150])
        rank = call("GET", "/game/api/v1/games/%s/rank?type=complex&pageNo=1&pageSize=20" % gid)
        rd = rank.get("data", {})
        check("gameRank RankInfo", rank.get("code") == 1 and "pageInfo" in rd
              and "remainTime" in rd and len(rd.get("pageInfo", {}).get("data", [])) > 0
              and all("integral" in r and "rank" in r for r in rd["pageInfo"]["data"]), str(rank)[:200])
        myrank = call("GET", "/game/api/v1/games/%s/uses/rank?type=complex" % gid,
                      headers={"Access-Token": tok1, "userId": str(uid1)})
        check("gameMyRank", myrank.get("code") == 1
              and myrank.get("data", {}).get("userId") == uid1, str(myrank)[:120])
        shop = call("GET", "/shop/api/v2/shop/game/props/new?gameId=%s&engineVersion=1" % gid,
                    headers={"userId": str(uid1), "Access-Token": tok1, "language": "en"})
        check("gameDetailShop items", shop.get("code") == 1 and len(shop.get("data", [])) >= 3
              and all("price" in p and "currency" in p for p in shop["data"]), str(shop)[:150])
        # buy the first prop for real (wallet deduction + one-time ownership)
        prop0 = shop["data"][0]
        wp0 = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        tok1 = wp0.get("data", {}).get("accessToken", tok1)
        kind0 = "golds" if prop0["currency"] == 2 else "diamonds"
        pre_buy = wp0.get("data", {})
        pbuy = call("PUT", "/shop/api/v3/shop/game/props/new?gameId=%s&propsId=%d" % (gid, prop0["id"]),
                    None, headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        wp1 = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        post_buy = wp1.get("data", {})
        check("buy game prop deducts wallet", pbuy.get("code") == 1
              and post_buy.get(kind0, 0) == pre_buy.get(kind0, 0) - prop0["price"],
              "%s | %s %s -> %s" % (str(pbuy)[:100], kind0, pre_buy.get(kind0), post_buy.get(kind0)))
        pbuy2 = call("PUT", "/shop/api/v3/shop/game/props/new?gameId=%s&propsId=%d" % (gid, prop0["id"]),
                     None, headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        wp2 = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        check("re-buy prop rejected (no double charge)", pbuy2.get("code") == 0
              and wp2.get("data", {}).get(kind0, 0) == post_buy.get(kind0, 0),
              "%s | %s" % (str(pbuy2)[:80], str(wp2.get("data", {}).get(kind0))))
        pbuyn = call("PUT", "/shop/api/v3/shop/game/props/new?gameId=%s&propsId=999999" % gid,
                     None, headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("buy unknown prop rejected", pbuyn.get("code") == 0, str(pbuyn)[:80])
        ann = call("GET", "/game/api/v1/games/announcement/info", headers={"language": "en"})
        stop = call("GET", "/game/api/v1/games/stop/announcement/info", headers={"language": "en"})
        check("announcements hidden", ann.get("data", {}).get("isShow") is False
              and stop.get("data", {}).get("isShow") is False, str(ann)[:100])
        openp = call("GET", "/game/api/v1/games/all/open/party?appVersion=4003",
                     headers={"language": "en"})
        check("all open party", openp.get("code") == 1 and len(openp.get("data", [])) > 0
              and all("gameId" in a for a in openp["data"]), str(openp)[:100])

        print("== Phase 2: daily economy ==")
        before = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        tok1 = before.get("data", {}).get("accessToken", tok1)  # re-login (old token was logged out)
        golds0 = before.get("data", {}).get("golds", 0)
        si = call("GET", "/user/api/v2/users/%d/daily/sign/in" % uid1,
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("dailySignIn map first..seventh", si.get("code") == 1
              and set(si.get("data", {}).keys()) == {"first", "second", "third", "fourth",
                                                     "fifth", "sixth", "seventh"}, str(si)[:150])
        check("signin fresh day-1 claimable (client: 1 = claimable, "
              "j/h.java)", si["data"]["first"]["status"] == 1
              and si["data"]["first"]["quantity"] > 0, str(si["data"]["first"])[:100])
        cs = call("PUT", "/user/api/v2/users/%d/daily/sign/in" % uid1,
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("clickSignIn ok", cs.get("code") == 1, str(cs)[:100])
        after = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        golds1 = after.get("data", {}).get("golds", 0)
        check("sign-in credited wallet", golds1 == golds0 + 200, "golds %d -> %d" % (golds0, golds1))
        si2 = call("GET", "/user/api/v2/users/%d/daily/sign/in" % uid1,
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("signin claimed status (client: 2 = Received)",
              si2["data"]["first"]["status"] == 2, str(si2["data"]["first"])[:100])
        ad = call("PUT", "/user/api/v1/users/%d/daily/tasks/ads" % uid1,
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("ads task reward RechargeEntity", ad.get("code") == 1
              and ad.get("data", {}).get("rewardQuantity") == 200
              and ad.get("data", {}).get("golds") == golds1 + 200, str(ad)[:150])
        sar = call("PUT", "/user/api/v1/users/daily/sign/ads", None,
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("sign ads reward", sar.get("code") == 1
              and sar.get("data", {}).get("quantity") == 300, str(sar)[:120])
        fri = call("GET", "/friend/api/v1/friends?pageNo=1&pageSize=10",
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("friendList empty PageData", fri.get("code") == 1
              and fri.get("data", {}).get("data") == [] and fri["data"]["totalSize"] == 0,
              str(fri)[:100])
        frec = call("GET", "/friend/api/v1/friends/recommendation", headers={"language": "en"})
        check("friendRecommendation non-empty", frec.get("code") == 1
              and len(frec.get("data", [])) > 0
              and all("userId" in f and "nickName" in f for f in frec["data"]), str(frec)[:150])
        vip = call("GET", "/user/api/v1/user/player/info", headers={"Access-Token": tok1})
        check("vip info", vip.get("code") == 1 and vip.get("data", {}).get("vip") == 0,
              str(vip)[:100])
        sub = call("GET", "/pay/api/v1/sub/info/get?appType=android")
        check("sub info", sub.get("code") == 1 and "playerInfo" in sub.get("data", {})
              and sub["data"].get("subInfo") == [], str(sub)[:120])
        mail = call("GET", "/mailbox/api/v1/mail/new", headers={"Access-Token": tok1, "userId": str(uid1)})
        check("mail/new bool (auth)", mail.get("code") == 1
              and mail.get("data") is True, str(mail)[:80])

        print("== Phase 2: rooms, tokens, misc ==")
        room = call("POST", "/game/api/v1/game/chat/room?roomName=qa-room", {})
        room2 = call("POST", "/game/api/v1/game/chat/room?roomName=qa-room", {})
        check("chatRoom stable id", room.get("code") == 1 and room.get("data", {}).get("roomId")
              and room["data"]["roomId"] == room2.get("data", {}).get("roomId"), str(room)[:100])
        qa_room_id = room.get("data", {}).get("roomId", "")
        del1 = call("DELETE", "/game/api/v1/game/chat/room?roomId=%s" % qa_room_id)
        check("chatRoom delete answers ok", del1.get("code") == 1, str(del1)[:80])
        room3 = call("POST", "/game/api/v1/game/chat/room?roomName=qa-room", {})
        check("chatRoom re-issued after delete", room3.get("code") == 1
              and room3.get("data", {}).get("roomId")
              and room3["data"]["roomId"] != qa_room_id, str(room3)[:100])
        del2 = call("DELETE", "/game/api/v1/game/chat/room?roomId=local-room-99999")
        check("chatRoom delete idempotent (unknown id ok)", del2.get("code") == 1, str(del2)[:80])
        # video feed: the client caches pageData.getData() into greendao — a
        # null list crashed BaseVideoInfoDbHelper on-device (v0.5.6). The page
        # must be a REAL flat PageData with an empty (not absent) data list.
        vp = call("GET", "/video/api/v1/app/video/list/top?pageNo=1&pageSize=20",
                  headers={"language": "en"})
        check("video list returns flat PageData", vp.get("code") == 1
              and isinstance(vp.get("data"), dict)
              and isinstance(vp["data"].get("data"), list)
              and vp["data"].get("totalPage") == 0, str(vp)[:140])
        vn = call("GET", "/video/api/v1/app/video/more/list?pageNo=1&pageSize=20&authorId=1&videoId=1",
                  headers={"language": "en"})
        check("video more/list same PageData shape", vn.get("code") == 1
              and isinstance(vn.get("data", {}).get("data"), list), str(vn)[:100])
        vt = call("GET", "/video/api/v1/app/video/tag/list", headers={"language": "en"})
        check("video tag list map", vt.get("code") == 1 and vt.get("data") == {}, str(vt)[:80])
        app2 = call("PUT", "/game/api/v1/games/%s/appreciation" % gid)
        check("appreciation unauth rejected (7)", app2.get("code") == 7, str(app2)[:100])
        app3 = call("PUT", "/game/api/v1/games/%s/appreciation" % gid,
                    headers={"Access-Token": tok1, "userId": str(uid1)})
        check("appreciation int (first like)", app3.get("code") == 1
              and isinstance(app3.get("data"), int) and app3["data"] > 0, str(app3)[:100])
        app4 = call("PUT", "/game/api/v1/games/%s/appreciation" % gid,
                    headers={"Access-Token": tok1, "userId": str(uid1)})
        check("appreciation repeat rejected (2005)", app4.get("code") == 2005, str(app4)[:100])
        app5 = call("PUT", "/game/api/v1/games/999999/appreciation",
                    headers={"Access-Token": tok1, "userId": str(uid1)})
        check("appreciation unknown game (2002)", app5.get("code") == 2002, str(app5)[:100])
        tok = call("GET", "/game/api/v2/game/auth?typeId=1&targetId=%d&gameVersion=1" % uid1,
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("miniGameToken", tok.get("code") == 1 and tok.get("data", {}).get("token")
              and tok["data"].get("timestamp", 0) > 0
              and tok["data"].get("dispUrl") == "http://127.0.0.1:18080", str(tok)[:150])
        rc = call("GET", "/game/api/v1/games/resource/version?ver=1&platform=android")
        check("resCheck", rc.get("code") == 1 and rc.get("data", {}).get("update") is False,
              str(rc)[:100])
        upd = call("GET", "/game/api/v1/games/app-engine/upgrade?engineVersion=1&resVersion=1&gameType=x")
        check("appEngine no upgrade", upd.get("code") == 1
              and upd.get("data", {}).get("needUpgrade") is False, str(upd)[:100])
        pc = call("GET", "/game/api/v1/games/config/app/%s" % gid)
        check("partyCreateGameConfig", pc.get("code") == 1
              and pc.get("data", {}).get("memberMax", 0) > 0, str(pc)[:100])

        print("== Phase 3: dress catalog + wardrobe + shop ==")
        dl = call("GET", "/decoration/api/v1/decorations/101", headers={"language": "en"})
        check("dressList generated", dl.get("code") == 1 and len(dl.get("data", [])) == 10
              and all("id" in d and "price" in d for d in dl["data"]), str(dl)[:150])
        dress0 = dl["data"][0]
        own = call("GET", "/decoration/api/v1/new/decorations/users/%d/type/101" % uid1,
                   headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("wardrobe empty at start", own.get("code") == 1 and own.get("data") == [],
              str(own)[:100])
        buy1 = call("PUT", "/shop/api/v1/shop/decorations/buy/%d" % dress0["id"], None,
                    headers={"Access-Token": tok1, "userId": str(uid1)})
        check("dress buy one", buy1.get("code") == 1, str(buy1)[:100])
        own2 = call("GET", "/decoration/api/v1/new/decorations/users/%d/type/101" % uid1,
                    headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("wardrobe has bought dress", own2.get("code") == 1
              and len(own2.get("data", [])) == 1
              and own2["data"][0]["id"] == dress0["id"], str(own2)[:120])
        use = call("PUT", "/decoration/api/v1/decorations/using/%d" % dress0["id"], None,
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("use decoration", use.get("code") == 1
              and use.get("data", {}).get("id") == dress0["id"], str(use)[:120])
        wearing = call("GET", "/decoration/api/v1/decorations/using?otherId=%d" % uid1)
        check("isUsingList shows worn", wearing.get("code") == 1
              and len(wearing.get("data", [])) == 1, str(wearing)[:120])
        unw = call("DELETE", "/decoration/api/v1/decorations/using/%d" % dress0["id"],
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("remove decoration", unw.get("code") == 1, str(unw)[:100])
        buy2 = call("PUT", "/shop/api/v1/shop/decorations/buy?decorationId=%d,%d" %
                    (dl["data"][3]["id"], dl["data"][4]["id"]), None,
                    headers={"Access-Token": tok1, "userId": str(uid1)})
        check("dress buy many response", buy2.get("code") == 1
              and "decorationPurchaseStatus" in buy2.get("data", {})
              and buy2["data"].get("goldsNeed", 0) > 0, str(buy2)[:150])
        after2 = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        check("buy deducted wallet", after2.get("data", {}).get("golds", 0) < golds1 + 200,
              str(after2.get("data", {}).get("golds")))
        poor = call("PUT", "/shop/api/v1/shop/decorations/buy/3000009990", None,
                    headers={"Access-Token": tok1, "userId": str(uid1)})
        check("buy unknown dress rejected", poor.get("code") == 0, str(poor)[:100])
        recs = call("GET", "/shop/api/v1/shop/decorations/recommends/%d" % dress0["id"])
        check("dress recommends", recs.get("code") == 1 and len(recs.get("data", [])) > 0,
              str(recs)[:100])
        shopv2 = call("GET", "/shop/api/v1/new/shop/decorations/102?os=android&engineVersion=1")
        check("shop list v2", shopv2.get("code") == 1 and len(shopv2.get("data", [])) == 10,
              str(shopv2)[:100])
        srec = call("GET", "/shop/api/v1/new/shop/recommend/decorations?os=android")
        check("shop recommend v2", srec.get("code") == 1 and len(srec.get("data", [])) > 0,
              str(srec)[:100])

        print("== Phase 3: scrap exchange ==")
        bag = call("GET", "/activity/api/v1/collect/exchange/user/scrap?type=1",
                   headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("scrap backpack", bag.get("code") == 1
              and bag.get("data", {}).get("totalSize", 0) > 0
              and "amount" in bag["data"]["data"][0], str(bag)[:150])
        bv = call("GET", "/activity/api/v1/collect/exchange/user/scrap/value",
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("scrap bag value", bv.get("code") == 1 and isinstance(bv.get("data"), int)
              and bv["data"] > 0, str(bv)[:100])
        cards = call("GET", "/activity/api/v1/collect/exchange/card/list?type=1")
        check("scrap card list", cards.get("code") == 1
              and len(cards.get("data", {}).get("data", [])) == 6, str(cards)[:120])
        cd = call("GET", "/activity/api/v1/collect/exchange/card/details?cardId=c1",
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("scrap card details", cd.get("code") == 1
              and len(cd.get("data", {}).get("scrapResponses", [])) == 2, str(cd)[:120])
        cmb = call("POST", "/activity/api/v1/collect/exchange/user/combine/card?cardId=c1&amount=1",
                   None, headers={"Access-Token": tok1, "userId": str(uid1)})
        check("combine card c1", cmb.get("code") == 1
              and cmb.get("data", {}).get("amount") == 1, str(cmb)[:120])
        hist = call("GET", "/activity/api/v1/collect/exchange/user/combine/record?pageNo=1&pageSize=10",
                    headers={"Access-Token": tok1, "userId": str(uid1)})
        check("combine history recorded", hist.get("code") == 1
              and hist.get("data", {}).get("totalSize", 0) >= 1, str(hist)[:120])
        badc = call("POST", "/activity/api/v1/collect/exchange/user/combine/card?cardId=c6&amount=999",
                    None, headers={"Access-Token": tok1, "userId": str(uid1)})
        check("combine insufficient rejected (10106)", badc.get("code") == 10106, str(badc)[:100])
        badcard = call("POST", "/activity/api/v1/collect/exchange/user/combine/card?cardId=c99&amount=1",
                       None, headers={"Access-Token": tok1, "userId": str(uid1)})
        check("combine unknown card (10107)", badcard.get("code") == 10107, str(badcard)[:100])
        badamt = call("POST", "/activity/api/v1/collect/exchange/user/combine/card?cardId=c1&amount=0",
                      None, headers={"Access-Token": tok1, "userId": str(uid1)})
        check("combine invalid amount (10105)", badamt.get("code") == 10105, str(badamt)[:100])
        targets = call("GET", "/activity/api/v1/collect/exchange/card/details/scrap?scrapId=s1&pageNo=1&pageSize=10")
        check("scrap request targets", targets.get("code") == 1
              and targets.get("data", {}).get("totalSize", 0) > 0, str(targets)[:120])
        rule = call("GET", "/activity/api/v1/collect/exchange/description")
        check("scrap rules list", rule.get("code") == 1 and isinstance(rule.get("data"), list),
              str(rule)[:80])


        print("== Phase 3.5: rankings + mailbox + tribe ==")
        rk = call("GET", "/ranking/api/v1/active/global/overall/rank?pageNo=1&pageSize=10")
        check("ranking page PageData", rk.get("code") == 1
              and len(rk.get("data", {}).get("data", [])) == 10
              and all("rank" in r and "quantity" in r for r in rk["data"]["data"])
              and rk["data"]["data"][0]["rank"] == 1, str(rk)[:150])
        quants = [r["quantity"] for r in rk["data"]["data"]]
        check("ranking desc order", quants == sorted(quants, reverse=True), str(quants[:5]))
        rk2 = call("GET", "/ranking/api/v1/gold/diamond/global/weekly/rank?pageNo=1&pageSize=10")
        check("gdiamond weekly ranking", rk2.get("code") == 1
              and len(rk2.get("data", {}).get("data", [])) == 10, str(rk2)[:100])
        ml = call("GET", "/mailbox/api/v1/mail")
        check("mail list strict (no auth rejected 7)", ml.get("code") == 7, str(ml)[:80])
        mo = call("PUT", "/mailbox/api/v1/mail?status=1&ids=1", [])
        check("mail op strict (no auth rejected 7)", mo.get("code") == 7, str(mo)[:80])
        td = call("GET", "/clan/api/v2/clan/tribe?clanId=0")
        check("tribe detail no-clan rejected", td.get("code") == 0, str(td)[:80])
        tid = call("GET", "/clan/api/v1/clan/tribe/id")
        check("tribe id zero", tid.get("code") == 1 and tid.get("data") == "0", str(tid)[:80])


        print("== Phase 3.6: profile/team extras ==")
        nf = call("GET", "/user/api/v1/user/nickName/free")
        check("nickName free", nf.get("code") == 1 and nf.get("data", {}).get("free") is True,
              str(nf)[:80])
        fq = call("GET", "/user/api/v1/data/frequently/game/%d" % uid1,
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("frequently games", fq.get("code") == 1 and len(fq.get("data", [])) > 0
              and "gameId" in fq["data"][0], str(fq)[:100])
        tm = call("GET", "/game/api/v1/games/team/member/77")
        check("team members", tm.get("code") == 1 and len(tm.get("data", [])) > 0
              and all("userId" in a and "nickName" in a for a in tm["data"]), str(tm)[:100])


        print("== Phase 3.7: local wallet + pay ==")
        w0 = call("GET", "/pay/api/v1/wealth/user", headers={"Access-Token": tok1, "userId": str(uid1)})
        check("wallet endpoint", w0.get("code") == 1
              and w0.get("data", {}).get("golds", 0) > 0
              and w0["data"].get("userId") == uid1, str(w0)[:150])
        prods = call("GET", "/pay/api/v1/pay/products?type=android&appType=android")
        check("product list", prods.get("code") == 1 and len(prods.get("data", [])) >= 6
              and all("productId" in p for p in prods["data"]), str(prods)[:150])
        sku = prods["data"][0]["productId"]
        rc2 = call("POST", "/pay/api/v2/pay/users/recharge?type=android",
                   {"sku": sku, "purchaseData": "local", "signature": "local",
                    "isSub": False}, headers={"Access-Token": tok1, "userId": str(uid1)})
        check("recharge credits wallet", rc2.get("code") == 1
              and rc2.get("data", {}).get("rewardQuantity", 0) > 0, str(rc2)[:150])
        w1 = call("GET", "/pay/api/v1/wealth/user", headers={"Access-Token": tok1, "userId": str(uid1)})
        check("wallet grew", w1.get("data", {}).get("golds", 0)
              == w0["data"]["golds"] + rc2["data"]["rewardQuantity"], str(w1)[:120])
        hist = call("GET", "/pay/api/v1/wealth/record/users/%d?pageNo=1&pageSize=10" % uid1,
                    headers={"Access-Token": tok1, "userId": str(uid1)})
        check("pay history recorded", hist.get("code") == 1
              and hist.get("data", {}).get("totalSize", 0) >= 1, str(hist)[:120])
        vipr = call("POST", "/pay/api/v3/pay/users/recharge?type=android",
                    {"sku": "local.vip.1", "purchaseData": "local", "isSub": False},
                    headers={"Access-Token": tok1, "userId": str(uid1)})
        check("vip purchase", vipr.get("code") == 1
              and vipr.get("data", {}).get("vip") == 1
              and vipr["data"].get("expireDate"), str(vipr)[:150])
        bad = call("POST", "/pay/api/v2/pay/users/recharge?type=android",
                   {"sku": "nope", "purchaseData": "", "isSub": False},
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("unknown sku rejected", bad.get("code") == 0, str(bad)[:80])
        noauth = call("POST", "/pay/api/v2/pay/users/recharge?type=android",
                      {"sku": sku, "purchaseData": "", "isSub": False})
        check("unauthenticated recharge rejected (7)", noauth.get("code") == 7, str(noauth)[:80])

        print("== Phase 4: tribe (clan) discovery ==")
        h1 = {"Access-Token": tok1, "userId": str(uid1), "language": "en"}
        tid0 = call("GET", "/clan/api/v1/clan/tribe/id", headers=h1)
        check("tribeId starts 0", tid0.get("code") == 1 and tid0.get("data") == "0", str(tid0)[:80])
        rec = call("GET", "/clan/api/v1/clan/tribe/recommendation", headers=h1)
        check("recommendation NPC tribes", rec.get("code") == 1 and len(rec.get("data", [])) >= 8
              and all(k in rec["data"][0] for k in
                      ("clanId", "name", "chiefNickName", "currentCount", "maxCount", "level", "freeVerify")),
              str(rec)[:200])
        sr = call("GET", "/clan/api/v1/clan/tribe/blurry/info?clanName=blocky&pageNo=1&pageSize=10",
                  headers=h1)
        check("search by name", sr.get("code") == 1
              and sr.get("data", {}).get("totalSize", 0) >= 1
              and all("blocky" in g["name"].lower() for g in sr["data"]["data"]), str(sr)[:150])
        trank = call("GET", "/clan/api/v1/clan/rank?type=exp&pageNo=1&pageSize=10", headers=h1)
        check("tribe rank RankInfo", trank.get("code") == 1
              and "pageInfo" in trank.get("data", {})
              and len(trank["data"]["pageInfo"]["data"]) >= 8
              and all(k in trank["data"]["pageInfo"]["data"][0] for k in
                      ("clanId", "name", "experience", "rank"))
              and trank["data"]["pageInfo"]["data"][0]["rank"] == "1", str(trank)[:200])
        ur = call("GET", "/clan/api/v1/clan/user/rank?type=exp", headers=h1)
        check("user rank no-clan rejected (7006)", ur.get("code") == 7006, str(ur)[:80])
        mem0 = call("GET", "/clan/api/v1/clan/tribe/member", headers=h1)
        check("member list no-clan rejected (7006)", mem0.get("code") == 7006, str(mem0)[:80])

        print("== Phase 4: create clan (real wallet cost) ==")
        w_before = call("GET", "/pay/api/v1/wealth/user", headers=h1).get("data", {}).get("golds", 0)
        cr = call("POST", "/clan/api/v2/clan/tribe",
                  {"clanId": 0, "name": "QA Clan", "details": "testing clan",
                   "headPic": "", "tags": ["qa"], "currency": 2}, headers=h1)
        check("create clan ok", cr.get("code") == 1 and cr.get("data", {}).get("clanId", 0) > 0
              and cr["data"].get("name") == "QA Clan", str(cr)[:150])
        clan_id = cr.get("data", {}).get("clanId", 0)
        w_after = call("GET", "/pay/api/v1/wealth/user", headers=h1).get("data", {}).get("golds", 0)
        check("create fee deducted (8000 golds, client-visible pricing)", w_before - w_after == 8000,
              "before=%s after=%s" % (w_before, w_after))
        cr2 = call("POST", "/clan/api/v2/clan/tribe",
                   {"name": "QA Clan 2", "currency": 2}, headers=h1)
        check("second create rejected (7001 already in clan)", cr2.get("code") == 7001, str(cr2)[:80])
        tid1 = call("GET", "/clan/api/v1/clan/tribe/id", headers=h1)
        check("tribeId now clanId", tid1.get("code") == 1 and tid1.get("data") == str(clan_id),
              str(tid1)[:80])
        base = call("GET", "/clan/api/v1/clan/tribe/base", headers=h1)
        check("tribeBaseInfo shape", base.get("code") == 1
              and base["data"].get("clanId") == clan_id
              and base["data"].get("currentCount") == 1
              and base["data"].get("maxCount", 0) >= 20
              and base["data"]["clanMembers"][0]["role"] == 20
              and base["data"]["clanMembers"][0]["userId"] == uid1, str(base)[:200])
        dup = call("POST", "/clan/api/v2/clan/tribe",
                   {"name": "QA Clan", "currency": 2},
                   headers={"Access-Token": call("POST", "/user/api/v1/register",
                            {"uid": "qa_tribe_x", "password": "pw", "imei": "devx"}
                            ).get("data", {}).get("accessToken", "")})
        check("duplicate name rejected (7002)", dup.get("code") == 7002, str(dup)[:80])

        print("== Phase 4: clan update (the UI edit-form drive's contract) ==")
        up = call("PUT", "/clan/api/v1/clan/tribe",
                  {"clanId": clan_id, "details": "updated details", "headPic": "",
                   "name": "QA Clan X", "tags": ["qa", "qa2"]}, headers=h1)
        check("chief updates name+details+tags", up.get("code") == 1
              and up.get("data", {}).get("name") == "QA Clan X"
              and up["data"].get("details") == "updated details"
              and up["data"].get("tags") == ["qa", "qa2"], str(up)[:180])
        base_up = call("GET", "/clan/api/v1/clan/tribe/base", headers=h1)
        check("update persisted in base", base_up.get("code") == 1
              and base_up["data"].get("name") == "QA Clan X", str(base_up)[:120])
        ry = call("POST", "/user/api/v1/register",
                  {"uid": "qa_userY", "password": "pwY", "imei": "devY"})
        hy = {"Access-Token": ry["data"]["accessToken"], "userId": str(ry["data"]["userId"]),
              "language": "en"}
        cry = call("POST", "/clan/api/v2/clan/tribe",
                   {"name": "QA Clan Y", "details": "other clan", "headPic": "",
                    "tags": ["y"], "currency": 2}, headers=hy)
        check("second clan exists (for the update-dup test)", cry.get("code") == 1,
              str(cry)[:100])
        up_dup = call("PUT", "/clan/api/v1/clan/tribe",
                      {"clanId": clan_id, "details": "updated details", "headPic": "",
                       "name": "QA Clan Y", "tags": ["qa"]}, headers=h1)
        check("update onto another clan's name rejected (7002)",
              up_dup.get("code") == 7002, str(up_dup)[:80])
        # note: a chief-of-own-clan PUT updates THEIR OWN clan by design
        # (the handler resolves the caller's clan; the elder 7003 case is
        # covered by the guards phase below). Clean the helper clan up so
        # the persistence phase's recommendation count stays exact.
        rn = call("POST", "/user/api/v1/register",
                  {"uid": "qa_userN", "password": "pwN", "imei": "devN"})
        hn = {"Access-Token": rn["data"]["accessToken"], "userId": str(rn["data"]["userId"]),
              "language": "en"}
        up_nonmember = call("PUT", "/clan/api/v1/clan/tribe",
                            {"clanId": 0, "details": "x", "headPic": "",
                             "name": "QA Clan W", "tags": ["qa"]}, headers=hn)
        check("non-member clan update rejected (7006)", up_nonmember.get("code") == 7006,
              str(up_nonmember)[:80])
        up_restore = call("PUT", "/clan/api/v1/clan/tribe",
                          {"clanId": clan_id, "details": "testing clan", "headPic": "",
                           "name": "QA Clan", "tags": ["qa"]}, headers=h1)
        check("rename back to the original name (later phases depend on it)",
              up_restore.get("code") == 1
              and up_restore["data"].get("name") == "QA Clan", str(up_restore)[:120])
        dz = call("DELETE", "/clan/api/v1/clan/tribe?clanId=%d" % cry["data"]["clanId"],
                  headers=hy)
        check("update-dup helper clan dissolved (count hygiene)", dz.get("code") == 1,
              str(dz)[:80])

        print("== Phase 4: bulletin ==")
        r2 = call("POST", "/user/api/v1/register",
                  {"uid": "qa_user2", "password": "pw2", "imei": "dev2"})
        uid2, tok2 = r2["data"]["userId"], r2["data"]["accessToken"]
        h2 = {"Access-Token": tok2, "userId": str(uid2), "language": "en"}
        bn = call("POST", "/clan/api/v1/clan/tribe/bulletin", {"content": "Welcome to QA Clan"},
                  headers=h1)
        check("post bulletin", bn.get("code") == 1, str(bn)[:80])
        bng = call("GET", "/clan/api/v1/clan/tribe/bulletin", headers=h1)
        check("get bulletin", bng.get("code") == 1
              and bng["data"].get("content") == "Welcome to QA Clan"
              and bng["data"].get("updateTime"), str(bng)[:120])

        print("== Phase 4: join request -> agree ==")
        rj = call("POST", "/clan/api/v1/clan/tribe/member", {"clanId": clan_id, "msg": "let me in"},
                  headers=h2)
        check("requestJoin ok", rj.get("code") == 1, str(rj)[:80])
        msgs1 = call("GET", "/clan/api/v2/clan/tribe/member/message", headers=h1)
        join_msgs = [m for m in msgs1.get("data", []) if m.get("type") == 1
                     and m.get("userId") == uid2]
        check("chief sees join request message", msgs1.get("code") == 1 and len(join_msgs) == 1
              and join_msgs[0]["status"] == 0 and join_msgs[0]["msg"] == "let me in"
              and "nickName" in join_msgs[0], str(msgs1)[:200])
        ag = call("PUT", "/clan/api/v1/clan/tribe/member/agreement?otherId=%d" % uid2,
                  headers=h1)
        check("agreeJoin ok", ag.get("code") == 1, str(ag)[:80])
        ml = call("GET", "/clan/api/v1/clan/tribe/member", headers=h1)
        check("member joined (2 members)", ml.get("code") == 1
              and len(ml.get("data", [])) == 2
              and any(m["userId"] == uid2 and m["role"] == 0 for m in ml["data"])
              and all("nickName" in m and "experience" in m and "vip" in m for m in ml["data"]),
              str(ml)[:200])
        tid2 = call("GET", "/clan/api/v1/clan/tribe/id", headers=h2)
        check("member tribeId set", tid2.get("code") == 1 and tid2.get("data") == str(clan_id),
              str(tid2)[:80])

        print("== Phase 4: invite -> agree ==")
        r3 = call("POST", "/user/api/v1/register",
                  {"uid": "qa_user3", "password": "pw3", "imei": "dev3"})
        uid3, tok3 = r3["data"]["userId"], r3["data"]["accessToken"]
        h3 = {"Access-Token": tok3, "userId": str(uid3), "language": "en"}
        inv = call("POST", "/clan/api/v1/clan/tribe/member/invite?friendIds=%d&msg=join%%20us" % uid3,
                   None, headers=h1)
        check("invite ok", inv.get("code") == 1, str(inv)[:80])
        msgs3 = call("GET", "/clan/api/v2/clan/tribe/member/message", headers=h3)
        inv_msgs = [m for m in msgs3.get("data", []) if m.get("type") == 2]
        check("invitee sees invitation", msgs3.get("code") == 1 and len(inv_msgs) == 1
              and inv_msgs[0].get("status") == 0 and inv_msgs[0].get("id", 0) > 0, str(msgs3)[:200])
        agi = call("PUT", "/clan/api/v1/clan/tribe/member/agreement/invitation?id=%d"
                   % inv_msgs[0]["id"], headers=h3)
        check("agree invitation joins", agi.get("code") == 1
              and call("GET", "/clan/api/v1/clan/tribe/id", headers=h3).get("data") == str(clan_id),
              str(agi)[:100])
        ml3 = call("GET", "/clan/api/v1/clan/tribe/member", headers=h1)
        check("3 members now", ml3.get("code") == 1 and len(ml3.get("data", [])) == 3, str(ml3)[:120])

        print("== Phase 4: roles (client type codes: 1=elder, 2=member, 3=hand over) ==")
        si = call("PUT", "/clan/api/v1/clan/tribe/member?otherId=%d&type=1" % uid2, headers=h1)
        check("chief promotes elder (client type 1)", si.get("code") == 1, str(si)[:80])
        ml4 = call("GET", "/clan/api/v1/clan/tribe/member", headers=h2)
        check("elder role 10 visible", ml4.get("code") == 1
              and any(m["userId"] == uid2 and m["role"] == 10 for m in ml4["data"]), str(ml4)[:120])
        si2 = call("PUT", "/clan/api/v1/clan/tribe/member?otherId=%d&type=1" % uid3, headers=h2)
        check("elder cannot set roles (7003)", si2.get("code") == 7003, str(si2)[:80])
        si3 = call("PUT", "/clan/api/v1/clan/tribe/member?otherId=%d&type=2" % uid1, headers=h1)
        check("cannot demote chief", si3.get("code") == 0, str(si3)[:80])
        ho = call("PUT", "/clan/api/v1/clan/tribe/member?otherId=%d&type=3" % uid2, headers=h1)
        check("chief hands over (client type 3)", ho.get("code") == 1, str(ho)[:100])
        ml5 = call("GET", "/clan/api/v1/clan/tribe/member", headers=h2)
        check("new chief role 20 / old chief role 0", ml5.get("code") == 1
              and any(m["userId"] == uid2 and m["role"] == 20 for m in ml5["data"])
              and any(m["userId"] == uid1 and m["role"] == 0 for m in ml5["data"]), str(ml5)[:150])
        old_chief_act = call("PUT", "/clan/api/v1/clan/tribe/member?otherId=%d&type=1" % uid3, headers=h1)
        check("old chief cannot set roles (7003)", old_chief_act.get("code") == 7003,
              str(old_chief_act)[:80])
        ho2 = call("PUT", "/clan/api/v1/clan/tribe/member?otherId=%d&type=3" % uid1, headers=h2)
        check("chief hands back", ho2.get("code") == 1, str(ho2)[:100])
        si4 = call("PUT", "/clan/api/v1/clan/tribe/member?otherId=%d&type=1" % uid2, headers=h1)
        check("re-promote elder for later phases", si4.get("code") == 1, str(si4)[:80])
        si5 = call("PUT", "/clan/api/v1/clan/tribe/member?otherId=%d&type=2" % uid3, headers=h1)
        check("demote via client type 2 (idempotent)", si5.get("code") == 1, str(si5)[:80])

        print("== Phase 4: donation (wallet -> clan experience -> tribe currency) ==")
        w2_before = call("GET", "/pay/api/v1/wealth/user", headers=h2).get("data", {})
        dn = call("POST", "/clan/api/v3/clan/tribe/donation?currency=2&quantity=1000", None, headers=h2)
        check("donate gold", dn.get("code") == 1 and dn["data"].get("experienceGot") == 1000
              and dn["data"].get("tribeCurrencyGot") == 100
              and dn["data"].get("userId") == uid2, str(dn)[:150])
        w2_after = call("GET", "/pay/api/v1/wealth/user", headers=h2).get("data", {})
        check("donation deducted golds", w2_after.get("golds", 0) == w2_before.get("golds", 0) - 1000,
              str(w2_after)[:120])
        di = call("GET", "/clan/api/v1/clan/tribe/donation", headers=h2)
        check("donationInfo counters", di.get("code") == 1 and di["data"].get("currentGold") == 1000
              and di["data"].get("maxGold") == 20000 and di["data"].get("currentTask") == 1
              and "clanId" in di["data"], str(di)[:150])
        dnd = call("POST", "/clan/api/v3/clan/tribe/donation?currency=1&quantity=10", None, headers=h2)
        check("donate diamonds x10 exp", dnd.get("code") == 1
              and dnd["data"].get("experienceGot") == 100, str(dnd)[:120])
        dcap = call("POST", "/clan/api/v3/clan/tribe/donation?currency=2&quantity=30000", None, headers=h2)
        check("donation cap rejected code 7011", dcap.get("code") == 7011, str(dcap)[:100])
        dnoauth = call("POST", "/clan/api/v3/clan/tribe/donation?currency=2&quantity=100")
        check("unauthenticated donation rejected (7)", dnoauth.get("code") == 7, str(dnoauth)[:80])
        dh = call("GET", "/clan/api/v2/clan/tribe/donation/history?pageNo=1&pageSize=10", headers=h1)
        check("donation history rows", dh.get("code") == 1
              and dh["data"].get("totalSize", 0) == 2
              and all(k in dh["data"]["data"][0] for k in
                      ("date", "nickName", "quantity", "type", "experienceGot", "tribeCurrencyGot", "userId")),
              str(dh)[:200])
        tc2 = call("GET", "/clan/api/v1/clan/tribe/currency", headers=h2)
        check("tribe currency accumulated", tc2.get("code") == 1 and tc2.get("data") == 110,
              str(tc2)[:80])

        print("== Phase 4: tasks ==")
        tk = call("GET", "/clan/api/v2/clan/tasks?type=1", headers=h2)
        check("clan tasks list", tk.get("code") == 1 and len(tk["data"].get("tasks", [])) == 3
              and all(k in tk["data"]["tasks"][0] for k in
                      ("id", "taskId", "name", "need", "finished", "status",
                       "currencyReward", "experienceReward")), str(tk)[:200])
        donate_task = [t for t in tk["data"]["tasks"] if t["taskId"] == 1][0]
        check("donate task finished", donate_task.get("finished") == 1, str(donate_task)[:120])
        ta = call("PUT", "/clan/api/v1/clan/tasks/accept?id=1&type=1", headers=h2)
        check("accept task", ta.get("code") == 1, str(ta)[:80])
        tc_before = call("GET", "/clan/api/v1/clan/tribe/currency", headers=h2).get("data", 0)
        trw = call("PUT", "/clan/api/v1/clan/tasks?id=1&type=1", headers=h2)
        tc_after = call("GET", "/clan/api/v1/clan/tribe/currency", headers=h2).get("data", 0)
        check("claim task reward (+50)", trw.get("code") == 1 and tc_after == tc_before + 50,
              "resp=%s before=%s after=%s" % (trw, tc_before, tc_after))
        trw2 = call("PUT", "/clan/api/v1/clan/tasks?id=1&type=1", headers=h2)
        check("double claim rejected (7012)", trw2.get("code") == 7012, str(trw2)[:80])
        pt = call("GET", "/clan/api/v2/clan/personal/tasks?type=2", headers=h2)
        check("personal tasks list", pt.get("code") == 1 and len(pt["data"].get("tasks", [])) == 2,
              str(pt)[:150])

        print("== Phase 4: tribe shop (tribe currency purchases) ==")
        shop = call("GET", "/clan/api/v1/clan/decorations/1?pageNo=1&pageSize=10", headers=h2)
        check("tribe shop page", shop.get("code") == 1 and shop["data"].get("totalSize", 0) == 6
              and all(k in shop["data"]["data"][0] for k in
                      ("id", "name", "price", "currency", "typeId", "clanLevel", "hasPurchase")),
              str(shop)[:200])
        item = shop["data"]["data"][0]
        det = call("GET", "/clan/api/v1/clan/decorations/details/%d" % item["id"], headers=h2)
        check("shop detail", det.get("code") == 1 and det["data"].get("id") == item["id"]
              and det["data"].get("name") == item["name"], str(det)[:150])
        buy = call("PUT", "/clan/api/v1/clan/decorations/purchase?decorationId=%d" % item["id"],
                   None, headers=h2)
        check("buy decoration", buy.get("code") == 1, str(buy)[:80])
        tc_after_buy = call("GET", "/clan/api/v1/clan/tribe/currency", headers=h2).get("data", 0)
        check("purchase charged tribe currency", tc_after_buy == tc_after - item["price"],
              "before=%s price=%s after=%s" % (tc_after, item["price"], tc_after_buy))
        shop2 = call("GET", "/clan/api/v1/clan/decorations/1?pageNo=1&pageSize=10", headers=h2)
        bought = [g for g in shop2["data"]["data"] if g["id"] == item["id"]][0]
        check("hasPurchase flagged", bought.get("hasPurchase") == 1, str(bought)[:120])
        rebuy = call("PUT", "/clan/api/v1/clan/decorations/purchase?decorationId=%d" % item["id"],
                     None, headers=h2)
        check("re-buy free (already owned)", rebuy.get("code") == 1, str(rebuy)[:80])
        poor = call("PUT", "/clan/api/v1/clan/decorations/purchase?decorationId=9006",
                    None, headers=h3)
        check("insufficient tribe currency rejected", poor.get("code") == 0, str(poor)[:80])

        print("== Phase 4: free verification + auto join ==")
        fv = call("PUT", "/clan/api/v1/clan/free/verification?freeVerify=1", headers=h1)
        check("free verify on (ClanResponse)", fv.get("code") == 1
              and fv["data"].get("freeVerify") == 1 and fv["data"].get("role") == 20
              and fv["data"].get("clanId") == clan_id, str(fv)[:150])
        r4 = call("POST", "/user/api/v1/register",
                  {"uid": "qa_user4", "password": "pw4", "imei": "dev4"})
        uid4, tok4 = r4["data"]["userId"], r4["data"]["accessToken"]
        h4 = {"Access-Token": tok4, "userId": str(uid4), "language": "en"}
        aj = call("POST", "/clan/api/v1/clan/tribe/member", {"clanId": clan_id, "msg": ""},
                  headers=h4)
        check("auto-join when free verify", aj.get("code") == 1
              and call("GET", "/clan/api/v1/clan/tribe/id", headers=h4).get("data") == str(clan_id),
              str(aj)[:100])
        # client contract (on-device 5u): the chief's sheet for an ELDER
        # offers 'Remove Member' - the chief may remove elders too. Promote
        # the throwaway to elder first (kicked users carry the 24h rejoin
        # cooldown, so each kick target is used exactly once).
        pe = call("PUT", "/clan/api/v1/clan/tribe/member?otherId=%d&type=1" % uid4, headers=h1)
        check("chief promotes elder (client type 1)", pe.get("code") == 1, str(pe)[:100])
        kj2 = call("DELETE", "/clan/api/v1/clan/tribe/member/remove?otherId=%d" % uid4, headers=h1)
        check("chief kicks elder", kj2.get("code") == 1
              and call("GET", "/clan/api/v1/clan/tribe/id", headers=h4).get("data") == "0",
              str(kj2)[:100])
        rc7 = call("POST", "/user/api/v1/register",
                   {"uid": "qa_user7", "password": "pw7", "imei": "dev7"})
        h7 = {"Access-Token": rc7["data"]["accessToken"], "userId": str(rc7["data"]["userId"]),
              "language": "en"}
        aj7 = call("POST", "/clan/api/v1/clan/tribe/member", {"clanId": clan_id, "msg": ""},
                   headers=h7)
        check("second throwaway auto-joins", aj7.get("code") == 1, str(aj7)[:100])
        kj3 = call("DELETE", "/clan/api/v1/clan/tribe/member/remove?otherId=%d"
                   % rc7["data"]["userId"], headers=h1)
        check("chief kicks plain member", kj3.get("code") == 1
              and call("GET", "/clan/api/v1/clan/tribe/id", headers=h7).get("data") == "0",
              str(kj3)[:100])
        fv0 = call("PUT", "/clan/api/v1/clan/free/verification?freeVerify=0", headers=h1)
        check("free verify off again", fv0.get("code") == 1
              and fv0["data"].get("freeVerify") == 0, str(fv0)[:100])

        print("== Phase 4: update / exit / reject / dissolve guards ==")
        up = call("PUT", "/clan/api/v1/clan/tribe", {"details": "updated details"}, headers=h1)
        check("chief updates clan", up.get("code") == 1 and up["data"].get("details") == "updated details",
              str(up)[:120])
        up2 = call("PUT", "/clan/api/v1/clan/tribe", {"details": "hijack"}, headers=h2)
        check("elder cannot update (7003)", up2.get("code") == 7003, str(up2)[:80])
        rj3 = call("POST", "/user/api/v1/register",
                   {"uid": "qa_user5", "password": "pw5", "imei": "dev5"})
        uid5, tok5 = rj3["data"]["userId"], rj3["data"]["accessToken"]
        h5 = {"Access-Token": tok5, "userId": str(uid5), "language": "en"}
        call("POST", "/clan/api/v1/clan/tribe/member", {"clanId": clan_id, "msg": "hi"}, headers=h5)
        rjct = call("PUT", "/clan/api/v1/clan/tribe/member/rejection?otherId=%d" % uid5, headers=h2)
        check("elder rejects join", rjct.get("code") == 1, str(rjct)[:80])
        check("rejectee not in clan", call("GET", "/clan/api/v1/clan/tribe/id", headers=h5).get("data") == "0",
              "uid5 should have no clan")
        ex = call("DELETE", "/clan/api/v1/clan/tribe/member?clanId=%d" % clan_id, headers=h3)
        check("member exits", ex.get("code") == 1
              and call("GET", "/clan/api/v1/clan/tribe/id", headers=h3).get("data") == "0", str(ex)[:100])
        chief_exit = call("DELETE", "/clan/api/v1/clan/tribe/member?clanId=%d" % clan_id, headers=h1)
        check("chief cannot exit", chief_exit.get("code") == 0, str(chief_exit)[:80])
        # dissolve guard: non-chief try (uid2 creates own clan, then uid3... uid2 is in main clan)
        dc = call("DELETE", "/clan/api/v1/clan/tribe?clanId=%d" % clan_id, headers=h2)
        check("elder cannot dissolve (7003)", dc.get("code") == 7003, str(dc)[:80])
        # throwaway clan dissolve by its chief
        rc2c = call("POST", "/user/api/v1/register",
                    {"uid": "qa_user6", "password": "pw6", "imei": "dev6"})
        tok6 = rc2c["data"]["accessToken"]
        h6 = {"Access-Token": tok6, "userId": str(rc2c["data"]["userId"]), "language": "en"}
        cr6 = call("POST", "/clan/api/v2/clan/tribe", {"name": "Throwaway", "currency": 1},
                   headers=h6)
        check("diamond-fee create ok", cr6.get("code") == 1, str(cr6)[:100])
        dd = call("DELETE", "/clan/api/v1/clan/tribe?clanId=%d" % cr6["data"]["clanId"], headers=h6)
        check("chief dissolves own clan", dd.get("code") == 1
              and call("GET", "/clan/api/v1/clan/tribe/id", headers=h6).get("data") == "0",
              str(dd)[:100])

        print("== Phase 4b: friend discovery ==")
        fs = call("GET", "/friend/api/v1/friends/info/Alex?pageNo=1&pageSize=10", headers=h2)
        check("search citizens by nick", fs.get("code") == 1
              and fs["data"].get("totalSize", 0) >= 1
              and all("alex" in f["nickName"].lower() for f in fs["data"]["data"])
              and all(k in fs["data"]["data"][0] for k in
                      ("userId", "nickName", "sex", "vip", "friend", "status", "alias")),
              str(fs)[:200])
        cid = fs["data"]["data"][0]["userId"]
        fby = call("GET", "/friend/api/v1/friends/info/id/%d" % cid, headers=h2)
        check("friend by id", fby.get("code") == 1 and fby["data"].get("userId") == cid
              and fby["data"].get("friend") is False, str(fby)[:150])
        fdet = call("GET", "/friend/api/v2/friends/%d" % uid3, headers=h2)
        check("friend details real user", fdet.get("code") == 1
              and fdet["data"].get("userId") == uid3, str(fdet)[:120])
        pub0 = call("GET", "/friend/api/v1/friend/status/%d" % uid3, headers=h2)
        check("public status stranger", pub0.get("code") == 1 and pub0.get("data") == 0,
              str(pub0)[:80])

        print("== Phase 4b: friend add -> accept ==")
        selfadd = call("POST", "/friend/api/v1/friends", {"friendId": uid2, "msg": ""},
                       headers=h2)
        check("self-add rejected", selfadd.get("code") == 0, str(selfadd)[:80])
        fa = call("POST", "/friend/api/v1/friends", {"friendId": uid3, "msg": "hi there"},
                  headers=h2)
        check("friend add ok", fa.get("code") == 1, str(fa)[:80])
        fa2 = call("POST", "/friend/api/v1/friends", {"friendId": uid3, "msg": "hi"},
                   headers=h2)
        check("duplicate request rejected", fa2.get("code") == 0, str(fa2)[:80])
        freqs = call("GET", "/friend/api/v1/friends/requests?pageNo=1&pageSize=10", headers=h3)
        check("request visible to target", freqs.get("code") == 1
              and freqs["data"]["totalSize"] == 1
              and freqs["data"]["data"][0]["userId"] == uid2
              and freqs["data"]["data"][0]["msg"] == "hi there"
              and freqs["data"]["data"][0]["status"] == 0, str(freqs)[:200])
        fnoauth = call("POST", "/friend/api/v1/friends", {"friendId": uid3})
        check("unauthenticated add rejected (7)", fnoauth.get("code") == 7, str(fnoauth)[:80])
        fag = call("PUT", "/friend/api/v1/friends/%d/agreement" % uid2, headers=h3)
        check("accept request", fag.get("code") == 1, str(fag)[:80])
        fl2 = call("GET", "/friend/api/v1/friends?pageNo=1&pageSize=10", headers=h2)
        fl3 = call("GET", "/friend/api/v1/friends?pageNo=1&pageSize=10", headers=h3)
        check("both sides list each other", fl2.get("code") == 1 and fl3.get("code") == 1
              and fl2["data"]["totalSize"] == 1 and fl3["data"]["totalSize"] == 1
              and fl2["data"]["data"][0]["userId"] == uid3
              and fl2["data"]["data"][0]["friend"] is True, str(fl2)[:200])
        pub1 = call("GET", "/friend/api/v1/friend/status/%d" % uid3, headers=h2)
        check("public status friend", pub1.get("code") == 1 and pub1.get("data") == 1,
              str(pub1)[:80])
        fst = call("GET", "/friend/api/v2/friends/status", headers=h2)
        check("friendStatus counts+presence", fst.get("code") == 1
              and fst["data"].get("curFriendCount") == 1
              and fst["data"].get("maxFriendCount", 0) > 0
              and fst["data"].get("currentTime", 0) > 0
              and any(b.get("userId") == uid3 and b.get("status") == 1
                      for b in fst["data"].get("status", [])), str(fst)[:200])
        fg = call("GET", "/friend/api/v1/friends/%d/gaming" % uid3, headers=h2)
        check("friend gaming StatusBean", fg.get("code") == 1
              and fg["data"].get("userId") == uid3 and "status" in fg["data"], str(fg)[:120])

        print("== Phase 4b: alias ==")
        al = call("POST", "/friend/api/v1/friends/%d/alias?alias=Buddy" % uid3, None, headers=h2)
        check("set alias", al.get("code") == 1, str(al)[:80])
        fdet2 = call("GET", "/friend/api/v2/friends/%d" % uid3, headers=h2)
        check("alias visible in details", fdet2.get("code") == 1
              and fdet2["data"].get("alias") == "Buddy", str(fdet2)[:120])
        ald = call("DELETE", "/friend/api/v1/friends/%d/alias" % uid3, headers=h2)
        fdet3 = call("GET", "/friend/api/v2/friends/%d" % uid3, headers=h2)
        check("alias removed", ald.get("code") == 1 and fdet3["data"].get("alias") == "",
              str(fdet3)[:120])

        print("== Phase 4b: blacklist / reject / unfriend / citizen add ==")
        bl = call("DELETE", "/friend/api/v1/friends/black?friendId=%d" % uid3, headers=h2)
        check("blacklist unfriends", bl.get("code") == 1
              and call("GET", "/friend/api/v1/friends?pageNo=1&pageSize=10",
                       headers=h2).get("data", {}).get("totalSize") == 0
              and call("GET", "/friend/api/v1/friend/status/%d" % uid3,
                       headers=h2).get("data") == 0, str(bl)[:120])
        blself = call("DELETE", "/friend/api/v1/friends/black?friendId=%d" % uid2, headers=h2)
        check("self-blacklist rejected", blself.get("code") == 0, str(blself)[:80])
        fa3 = call("POST", "/friend/api/v1/friends", {"friendId": uid4, "msg": "again"},
                   headers=h2)
        frj = call("PUT", "/friend/api/v1/friends/%d/rejection" % uid2, headers=h4)
        check("reject request", frj.get("code") == 1
              and call("GET", "/friend/api/v1/friends?pageNo=1&pageSize=10",
                       headers=h2).get("data", {}).get("totalSize") == 0, str(frj)[:120])
        freqs2 = call("GET", "/friend/api/v1/friends/requests?pageNo=1&pageSize=10", headers=h4)
        check("rejected request not pending", freqs2.get("code") == 1
              and freqs2["data"]["totalSize"] == 0, str(freqs2)[:120])
        fcit = call("POST", "/friend/api/v1/friends", {"friendId": cid, "msg": ""},
                    headers=h2)
        check("citizen add auto-accepts", fcit.get("code") == 1
              and call("GET", "/friend/api/v1/friends?pageNo=1&pageSize=10",
                       headers=h2)["data"]["data"][0]["userId"] == cid, str(fcit)[:120])
        fdel = call("DELETE", "/friend/api/v1/friends?friendId=%d" % cid, headers=h2)
        check("unfriend", fdel.get("code") == 1
              and call("GET", "/friend/api/v1/friends?pageNo=1&pageSize=10",
                       headers=h2).get("data", {}).get("totalSize") == 0, str(fdel)[:120])

        print("== Phase 4c: group chat management ==")
        gp = call("GET", "/msg/api/v1/group/chat/price")
        check("group price free tier", gp.get("code") == 1
              and gp["data"].get("price") == 0, str(gp)[:80])
        gc = call("POST", "/msg/api/v2/msg/group/chat",
                  {"cost": 0, "currency": 1, "memberIds": [uid3], "userId": uid2,
                   "groupName": "QA Group"}, headers=h2)
        check("group create", gc.get("code") == 1 and gc["data"].get("groupId", 0) > 0
              and gc["data"].get("ownerId") == str(uid2)
              and gc["data"].get("forbiddenWordsStatus") == 0, str(gc)[:200])
        gid = gc["data"]["groupId"]
        gmembers = gc["data"].get("groupMembers", [])
        check("group members (owner id2 + id3)", len(gmembers) == 2
              and any(m["userId"] == uid2 and m["identity"] == 2 for m in gmembers)
              and any(m["userId"] == uid3 and m["identity"] == 0 for m in gmembers),
              str(gmembers)[:200])
        gl = call("GET", "/msg/api/v1/msg/group/chat/list?pageNo=1&pageSize=10", headers=h3)
        check("group list for member", gl.get("code") == 1 and gl["data"]["totalSize"] == 1
              and gl["data"]["data"][0]["groupId"] == gid, str(gl)[:150])
        gi = call("GET", "/msg/api/v1/msg/group/chat/info?groupId=%d" % gid, headers=h3)
        check("group info", gi.get("code") == 1 and gi["data"]["groupId"] == gid
              and gi["data"]["groupName"] == "QA Group", str(gi)[:150])
        gic = call("GET", "/msg/api/v1/msg/group/chat/invite/count?groupId=%d" % gid, headers=h2)
        check("group invite count", gic.get("code") == 1
              and gic["data"]["inviteCount"] > 0, str(gic)[:100])
        gmd = call("PUT", "/msg/api/v1/msg/group/chat/modify",
                   {"groupId": gid, "groupNotice": "rules here", "inviteStatus": 0},
                   headers=h2)
        check("group modify by owner", gmd.get("code") == 1
              and gmd["data"]["groupNotice"] == "rules here", str(gmd)[:150])
        gmd2 = call("PUT", "/msg/api/v1/msg/group/chat/modify",
                    {"groupId": gid, "groupName": "hijack"}, headers=h3)
        check("member cannot modify", gmd2.get("code") == 0, str(gmd2)[:80])
        # join request flow (inviteStatus 0 -> approval needed)
        ga = call("POST", "/msg/api/v1/msg/group/chat/apply?groupId=%d&msg=hello" % gid,
                  None, headers=h4)
        check("group apply pending", ga.get("code") == 1, str(ga)[:80])
        greq = call("GET", "/msg/api/v1/msg/group/chat/request/list?pageNo=1&pageSize=10",
                    headers=h2)
        greq_rows = [r for r in greq.get("data", {}).get("data", []) if r["type"] == 1]
        check("owner sees join request", greq.get("code") == 1 and len(greq_rows) == 1
              and greq_rows[0]["userId"] == uid4 and greq_rows[0]["requestId"] > 0
              and greq_rows[0]["msg"] == "hello", str(greq)[:200])
        gacc = call("PUT", "/msg/api/v1/msg/group/chat/agreement",
                    {"groupId": gid, "requestId": greq_rows[0]["requestId"],
                     "operateId": uid2, "userId": uid4, "type": 1}, headers=h2)
        check("accept join request", gacc.get("code") == 1
              and any(m["userId"] == uid4 for m in gacc["data"]["groupMembers"]),
              str(gacc)[:200])
        # ban flow
        gban = call("POST", "/msg/api/v1/msg/group/chat/forbidden/member?groupId=%d&memberId=%d&minute=5"
                    % (gid, uid4), None, headers=h2)
        check("ban member", gban.get("code") == 1
              and [m for m in gban["data"]["groupMembers"] if m["userId"] == uid4][0]["banStatus"] == 1,
              str(gban)[:200])
        gunban = call("PUT", "/msg/api/v1/msg/group/chat/remove/forbidden/member?groupId=%d&memberId=%d"
                      % (gid, uid4), None, headers=h2)
        check("unban member", gunban.get("code") == 1
              and [m for m in gunban["data"]["groupMembers"] if m["userId"] == uid4][0]["banStatus"] == 0,
              str(gunban)[:200])
        # manager + kick + transfer
        gsm = call("PUT", "/msg/api/v1/msg/group/chat/set/manager",
                   {"groupId": gid, "inviterId": uid2, "memberIds": [uid3],
                    "operationType": 1}, headers=h2)
        check("set manager", gsm.get("code") == 1
              and [m for m in gsm["data"]["groupMembers"] if m["userId"] == uid3][0]["identity"] == 1,
              str(gsm)[:200])
        gsm2 = call("PUT", "/msg/api/v1/msg/group/chat/set/manager",
                    {"groupId": gid, "inviterId": uid3, "memberIds": [uid4],
                     "operationType": 1}, headers=h3)
        check("manager cannot set managers (8103)", gsm2.get("code") == 8103, str(gsm2)[:80])
        gkick = call("PUT", "/msg/api/v1/msg/group/chat/kickOut",
                     {"groupId": gid, "inviterId": uid2, "memberIds": [uid4],
                      "groupName": "QA Group"}, headers=h2)
        check("kick member", gkick.get("code") == 1
              and not any(m["userId"] == uid4 for m in gkick["data"]["groupMembers"]),
              str(gkick)[:200])
        gmut = call("PUT", "/msg/api/v1/msg/group/chat/forbidden?groupId=%d" % gid, None,
                    headers=h2)
        check("mute all toggled", gmut.get("code") == 1
              and gmut["data"]["forbiddenWordsStatus"] == 1, str(gmut)[:150])
        gtr = call("PUT", "/msg/api/v1/msg/group/chat/transfer",
                   {"groupId": gid, "inviterId": uid2, "userId": uid3}, headers=h2)
        check("transfer ownership", gtr.get("code") == 1 and gtr["data"]["ownerId"] == str(uid3),
              str(gtr)[:150])
        gquit = call("PUT", "/msg/api/v1/msg/group/chat/quit?groupId=%d&groupName=QA%%20Group" % gid,
                     None, headers=h2)
        check("quit group", gquit.get("code") == 1
              and gquit["data"]["totalSize"] == 0, str(gquit)[:150])
        gdel = call("PUT", "/msg/api/v1/msg/group/chat/quit?groupId=%d&groupName=QA%%20Group" % gid,
                    None, headers=h3)
        check("last member quit removes group", gdel.get("code") == 1
              and call("GET", "/msg/api/v1/msg/group/chat/info?groupId=%d" % gid,
                       headers=h3).get("code") == 0, str(gdel)[:150])
        gnoauth = call("POST", "/msg/api/v2/msg/group/chat", {"groupName": "x"})
        check("unauthenticated group create rejected (7)", gnoauth.get("code") == 7, str(gnoauth)[:80])

        print("== Phase 4d: account security + password lifecycle ==")
        sp = call("POST", "/user/api/v1/app/set-password",
                  {"account": "qa_user5", "userId": uid5, "password": "npw5",
                   "confirmPassword": "npw5"},
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        check("set password on fresh account", sp.get("code") == 1, str(sp)[:100])
        spl = call("POST", "/user/api/v1/login", {"uid": "qa_user5", "password": "npw5"})
        check("login with new password", spl.get("code") == 1
              and spl["data"]["userId"] == uid5, str(spl)[:120])
        spbad = call("POST", "/user/api/v1/app/set-password",
                     {"account": "qa_user5", "userId": uid5, "password": "x",
                      "confirmPassword": "y"})
        check("password mismatch rejected", spbad.get("code") == 0, str(spbad)[:80])
        pmw = call("POST", "/user/api/v1/user/password/modify",
                   {"oldPassword": "WRONG", "newPassword": "npw6",
                    "confirmPassword": "npw6"},
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        check("wrong old password rejected", pmw.get("code") == 0, str(pmw)[:80])
        pm = call("POST", "/user/api/v1/user/password/modify",
                  {"oldPassword": "npw5", "newPassword": "npw6",
                   "confirmPassword": "npw6"},
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        check("modify password", pm.get("code") == 1, str(pm)[:80])
        pml = call("POST", "/user/api/v1/login", {"uid": "qa_user5", "password": "npw6"})
        check("login with modified password", pml.get("code") == 1, str(pml)[:100])
        pc = call("POST", "/user/api/v1/user/password/check", {"password": "npw6"},
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        check("password check right", pc.get("code") == 1
              and pc["data"]["right"] is True, str(pc)[:100])
        pc2 = call("POST", "/user/api/v1/user/password/check", {"password": "bad"},
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        check("password check wrong", pc2.get("code") == 1
              and pc2["data"]["right"] is False, str(pc2)[:100])
        ne1 = call("POST", "/user/api/v1/user/nickname/exist?nickName=BrandNewNick", None,
                   headers={"Access-Token": tok5})
        check("nickname free", ne1.get("code") == 1, str(ne1)[:80])
        ne2 = call("POST", "/user/api/v1/user/nickname/exist?nickName=RoleQA", None,
                   headers={"Access-Token": tok5})
        check("nickname taken rejected", ne2.get("code") == 0, str(ne2)[:80])
        am = call("POST", "/user/api/v1/user/account/modify", {"account": "qa_user5_renamed"},
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        aml = call("POST", "/user/api/v1/login", {"uid": "qa_user5_renamed", "password": "npw6"})
        check("account rename + login", am.get("code") == 1
              and aml.get("code") == 1 and aml["data"]["userId"] == uid5, str(aml)[:120])
        lr = call("GET", "/user/api/v1/user/login/change/record",
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        check("login record present", lr.get("code") == 1
              and lr["data"].get("appType") == "android"
              and lr["data"].get("loginTime"), str(lr)[:120])

        print("== Phase 4d: phone/email bind ==")
        bp = call("POST", "/user/api/v1/user/bind/phone",
                  {"phone": "+201234567890", "verifyCode": "1234"},
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        check("bind phone", bp.get("code") == 1, str(bp)[:80])
        bp0 = call("POST", "/user/api/v1/user/bind/phone", {"phone": ""},
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        check("empty phone rejected", bp0.get("code") == 0, str(bp0)[:80])
        be = call("POST", "/user/api/v1/users/bind/email",
                  {"email": "qa@example.com", "verifyCode": "1"}, headers=h5)
        check("bind email", be.get("code") == 1, str(be)[:80])
        be0 = call("POST", "/user/api/v1/users/bind/email", {"email": "nope"},
                   headers=h5)
        check("invalid email rejected", be0.get("code") == 0, str(be0)[:80])
        te = call("GET", "/user/api/v1/users/security/bind/email?userId=%d" % uid5, headers=h5)
        check("masked email tip", te.get("code") == 1 and te["data"] == "q***@example.com",
              str(te)[:100])
        ue = call("DELETE", "/user/api/v1/users/%d/emails" % uid5, headers=h5)
        te2 = call("GET", "/user/api/v1/users/security/bind/email?userId=%d" % uid5, headers=h5)
        check("unbind email", ue.get("code") == 1 and te2["data"] == "", str(te2)[:100])
        sm = call("POST", "/user/api/v1/sms/send/+201234567890", {})
        check("sms send ack", sm.get("code") == 1, str(sm)[:80])
        ev = call("POST", "/user/api/v1/emails/verify/qa@example.com", {})
        check("email verify ack", ev.get("code") == 1, str(ev)[:80])
        up = call("POST", "/user/api/v1/user/unbind/phone", {}, headers=h5)
        check("unbind phone", up.get("code") == 1, str(up)[:80])

        print("== Phase 4d: secret questions ==")
        qs = call("GET", "/user/api/v1/users/secret/question?type=1",
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        check("questions empty at start", qs.get("code") == 1 and qs.get("data") == [],
              str(qs)[:80])
        qa = call("POST", "/user/api/v1/users/secret/question?userId=%d&complete=1" % uid5,
                  [{"question": "Q1", "answer": "A1"}, {"question": "Q2", "answer": "A2"}],
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        check("question auth issues code", qa.get("code") == 1
              and qa["data"].get("right") is True and qa["data"].get("authCode"), str(qa)[:150])
        auth_code = qa["data"]["authCode"]
        qs2 = call("GET", "/user/api/v1/users/secret/question?type=1",
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        check("questions persisted", qs2.get("code") == 1 and len(qs2["data"]) == 2
              and qs2["data"][0]["question"] == "Q1", str(qs2)[:150])
        qrp = call("POST", "/user/api/v1/users/question/reset/password"
                   "?userId=%d&newPwd=resetpw&authCode=%s" % (uid5, auth_code))
        check("reset via authCode", qrp.get("code") == 1, str(qrp)[:100])
        qrpl = call("POST", "/user/api/v1/login", {"uid": "qa_user5_renamed", "password": "resetpw"})
        check("login with reset password", qrpl.get("code") == 1, str(qrpl)[:100])
        qrp2 = call("POST", "/user/api/v1/users/question/reset/password"
                    "?userId=%d&newPwd=x&authCode=bad" % uid5)
        check("bad authCode rejected", qrp2.get("code") == 0, str(qrp2)[:80])
        qus = call("POST", "/user/api/v1/users/unbind/user/security", {},
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        qs3 = call("GET", "/user/api/v1/users/secret/question?type=1",
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        check("unbind security clears questions", qus.get("code") == 1
              and qs3["data"] == [], str(qs3)[:100])

        print("== Phase 4d: daily tasks + rewards ==")
        ndt = call("GET", "/user/api/v1/users/new/daily/tasks",
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        check("new daily tasks strip", ndt.get("code") == 1 and len(ndt["data"]["tasks"]) == 7
              and ndt["data"]["tasks"][0]["count"] == 200
              and "hours" in ndt["data"], str(ndt)[:200])
        wt = call("GET", "/user/api/v1/users/dairy/tasks/1",
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        check("week task map", wt.get("code") == 1 and "taskMap" in wt["data"]
              and wt["data"]["taskMap"]["1"] == 0, str(wt)[:150])
        w0 = call("GET", "/pay/api/v1/wealth/user",
                  headers={"Access-Token": tok5, "userId": str(uid5)}).get("data", {})
        ct = call("PUT", "/user/api/v1/users/tasks/1", None,
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        w1 = call("GET", "/pay/api/v1/wealth/user",
                  headers={"Access-Token": tok5, "userId": str(uid5)}).get("data", {})
        check("claim task rewards wallet", ct.get("code") == 1
              and w1.get("golds", 0) == w0.get("golds", 0) + 200, str(ct)[:150])
        # WeekTaskResponse/RechargeEntity model decode (jadx classes3):
        # the claim response is HttpResponse<RechargeEntity> and the client
        # model carries currency/gDiamondsProfit/money/rewardQuantity too —
        # rewardQuantity carries the granted amount (claim popup).
        check("claim task response is a full RechargeEntity",
              ct.get("code") == 1 and ct["data"].get("currency") == 2
              and ct["data"].get("rewardQuantity") == 200
              and "money" in ct["data"] and "gDiamondsProfit" in ct["data"],
              str(ct)[:200])
        ndt2 = call("GET", "/user/api/v1/users/new/daily/tasks",
                    headers={"Access-Token": tok5, "userId": str(uid5)})
        check("task strip reflects claim", ndt2.get("code") == 1
              and ndt2["data"]["tasks"][0]["status"] == 1, str(ndt2)[:150])
        sr = call("POST", "/user/api/v1/users/sharing/reward?type=1",
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        sr2 = call("POST", "/user/api/v1/users/sharing/reward?type=1",
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        check("share reward once/day", sr.get("code") == 1 and sr2.get("code") == 0,
              "%s %s" % (sr, sr2))
        prc = call("POST", "/user/api/v1/users/prefect/info/reward/check/%d" % uid5,
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        check("prefect check incomplete profile", prc.get("code") == 1
              and prc["data"] is False, str(prc)[:100])
        call("PUT", "/user/api/v1/user/info", {"details": "completing my profile"},
             headers={"Access-Token": tok5, "userId": str(uid5)})
        prc2 = call("POST", "/user/api/v1/users/prefect/info/reward/check/%d" % uid5,
                    headers={"Access-Token": tok5, "userId": str(uid5)})
        pr = call("POST", "/user/api/v1/users/prefect/info/reward/%d" % uid5,
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        pr2 = call("POST", "/user/api/v1/users/prefect/info/reward/%d" % uid5,
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        check("prefect reward lifecycle", prc2.get("code") == 1 and prc2["data"] is True
              and pr.get("code") == 1
              and pr["data"].get("golds") == 500 and pr2.get("code") == 0,
              str(pr)[:150])
        ic = call("GET", "/user/api/v1/user/id/card/status?userId=%d" % uid5,
                  headers={"Access-Token": tok5})
        check("id card status string", ic.get("code") == 1 and isinstance(ic["data"], str),
              str(ic)[:80])
        # error-driven fixes from the v0.4.3 run's client traffic
        ss = call("GET", "/user/api/v2/users/verify/user/security/settings?userId=%d" % uid5,
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        check("security settings shape", ss.get("code") == 1
              and ss["data"].get("bindEmail") is False
              and isinstance(ss["data"].get("secretQuestionList"), list)
              and ss["data"].get("userId") == uid5, str(ss)[:150])
        call("POST", "/user/api/v1/users/bind/email", {"email": "qa@example.com"}, headers=h5)
        ss2 = call("GET", "/user/api/v2/users/verify/user/security/settings?userId=%d" % uid5,
                   headers={"Access-Token": tok5, "userId": str(uid5)})
        check("security settings reflect bind", ss2.get("code") == 1
              and ss2["data"]["bindEmail"] is True
              and ss2["data"]["email"] == "qa@example.com", str(ss2)[:150])
        at = call("GET", "/activity/api/v2/activity/title",
                  headers={"Access-Token": tok5, "userId": str(uid5)})
        # wave 6c: the list is now REAL (weekday + weekend) — the empty-list
        # era is over; the surface is lit by design (see Wave 6c section).
        check("activity title served + serverTime", at.get("code") == 1
              and len(at["data"].get("activityTitleList", [])) == 2
              and at["data"].get("serverTime", 0) > 0, str(at)[:150])

        # ------------------------------------------------ Phase 5: dispatch bridge
        print("== Phase 5: dispatch bridge (token -> dispatch -> game-res) ==")
        mtok = call("GET", "/game/api/v2/game/auth?typeId=%s&targetId=%d&gameVersion=1"
                    % (gid, uid1), headers={"Access-Token": tok1, "userId": str(uid1)})
        mg = mtok.get("data", {})
        check("dispatch token issued", mtok.get("code") == 1
              and mg.get("token", "").startswith("mg-")
              and mg.get("requestId", {}).get(str(uid1)), str(mtok)[:150])
        dp = call("POST", "/v1/dispatch",
                  {"clz": 0, "name": "Player", "pioneer": True, "targetId": uid1,
                   "resVersion": 3, "ever": 1, "picUrl": "", "packageName": "com.test",
                   "appVer": "1.24.4", "country": "us", "lang": "en", "rid": 0},
                  headers={"x-shahe-uid": str(uid1), "x-shahe-token": mg.get("token", "")})
        dd = dp.get("data", {})
        check("dispatch returns engine shape", dp.get("code") == 1
              and dd.get("gaddr") == "127.0.0.1:18080"
              and ":" in (dd.get("gaddr") or "")
              and dd.get("dispUrl") == "http://127.0.0.1:18080"
              and dd.get("croomid"), str(dp)[:250])
        check("dispatch game + requestIds", dd.get("name")
              and dd.get("requestIds", {}).get(str(uid1)) == mg.get("requestId", {}).get(str(uid1))
              and dd.get("resVersion") == 3, str(dd)[:250])
        dp2 = call("POST", "/v1/dispatch", {"resVersion": 1},
                   headers={"x-shahe-uid": str(uid1), "x-shahe-token": "mg-bogus"})
        check("dispatch rejects bad token", dp2.get("code") == 0, str(dp2)[:100])
        fl = call("POST", "/v1/follow",
                  {"targetId": uid1, "resVersion": 1, "ever": 1, "rid": 0},
                  headers={"x-shahe-uid": str(uid1), "x-shahe-token": mg.get("token", "")})
        check("follow returns dispatch too", fl.get("code") == 1
              and fl.get("data", {}).get("gaddr") == "127.0.0.1:18080", str(fl)[:150])
        gr = call("GET", "/v1/game-res?gameType=1&engineVersion=1&resVersion=7")
        gd = gr.get("data", {})
        check("game-res local cdn", gr.get("code") == 1
              and gd.get("resVersion") == 7
              and gd.get("cdns") and gd["cdns"][0]["base"] is True
              and gd["cdns"][0]["url"] == "http://127.0.0.1:18080", str(gr)[:200])

        # ------------------------------------------------ Phase 5: suits
        print("== Phase 5: decoration suits (shop/gift/owned) ==")
        suits = call("GET", "/shop/api/v1/new/shop/suit/decorations?os=android&engineVersion=1",
                     headers={"language": "en"})
        check("suit shop list", suits.get("code") == 1 and len(suits.get("data", [])) == 6
              and suits["data"][0].get("suitId") and "decorationInfoList" in suits["data"][0]
              and "shopDecorationInfos" in suits["data"][0], str(suits)[:200])
        suit0 = suits["data"][0]
        suit1 = suits["data"][1]
        sd = call("GET", "/shop/api/v1/new/shop/suit/info/%d" % suit0["suitId"],
                  headers={"language": "en"})
        check("suit detail components", sd.get("code") == 1
              and len(sd["data"].get("decorationInfoList", [])) >= 3
              and sd["data"]["price"] > 0, str(sd)[:200])
        sby = call("GET", "/shop/api/v1/new/shop/suit/list/info?suitIds=%d&suitIds=%d"
                   % (suit0["suitId"], suit1["suitId"]), headers={"language": "en"})
        check("suit list by ids", sby.get("code") == 1 and len(sby.get("data", [])) == 2,
              str(sby)[:150])
        owned0 = call("GET", "/decoration/api/v1/new/decorations/users/%d/suit" % uid1,
                      headers={"Access-Token": tok1, "userId": str(uid1)})
        check("no owned suits at start", owned0.get("code") == 1 and owned0.get("data") == [],
              str(owned0)[:120])
        gift = call("GET", "/shop/api/v1/new/shop/user/gift/suit/receive",
                    headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("gift suit available", gift.get("code") == 1 and gift.get("data") is True,
              str(gift)[:100])
        gi = call("GET", "/shop/api/v1/new/shop/gift/suit/receive",
                  headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("gift suit info", gi.get("code") == 1
              and gi["data"].get("suitId") == suit0["suitId"], str(gi)[:150])
        w_pre = call("GET", "/pay/api/v1/wealth/user",
                     headers={"Access-Token": tok1, "userId": str(uid1)}).get("data", {})
        claim = call("POST", "/shop/api/v1/new/shop/gift/suit/receive?suitId=%d"
                     % suit0["suitId"], {},
                     headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("gift suit claim -> dresses", claim.get("code") == 1
              and len(claim.get("data", [])) >= 3, str(claim)[:200])
        gift2 = call("GET", "/shop/api/v1/new/shop/user/gift/suit/receive",
                     headers={"Access-Token": tok1, "userId": str(uid1)})
        check("gift suit now unavailable", gift2.get("code") == 1 and gift2.get("data") is False,
              str(gift2)[:100])
        owned1 = call("GET", "/decoration/api/v1/new/decorations/users/%d/suit" % uid1,
                      headers={"Access-Token": tok1, "userId": str(uid1)})
        check("owned suit list has gift suit", owned1.get("code") == 1
              and len(owned1.get("data", [])) == 1
              and owned1["data"][0]["suitId"] == suit0["suitId"], str(owned1)[:200])
        # buy suit1 with real wallet deduction
        w_pre2 = call("GET", "/pay/api/v1/wealth/user",
                      headers={"Access-Token": tok1, "userId": str(uid1)}).get("data", {})
        buysuit = call("POST", "/shop/api/v1/new/shop/decorations/buy",
                       {"buySuitList": [{"suitId": suit1["suitId"], "day": 0}]},
                       headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        w_post = call("GET", "/pay/api/v1/wealth/user",
                      headers={"Access-Token": tok1, "userId": str(uid1)}).get("data", {})
        exp_price = suit1["price"]
        exp_kind = "golds" if suit1["currency"] == 2 else "diamonds"
        check("buy suit deducts wallet", buysuit.get("code") == 1
              and buysuit["data"]["suitPurchaseStatus"].get(str(suit1["suitId"])) is True
              and w_post.get(exp_kind, 0) == w_pre2.get(exp_kind, 0) - exp_price,
              "%s | w %s -> %s" % (str(buysuit)[:200], w_pre2, w_post))
        owned2 = call("GET", "/decoration/api/v1/new/decorations/users/%d/suit" % uid1,
                      headers={"Access-Token": tok1, "userId": str(uid1)})
        check("two owned suits after buy", owned2.get("code") == 1
              and len(owned2.get("data", [])) == 2, str(owned2)[:200])

        # ------------------------------------------------ Phase 5: file upload
        print("== Phase 5: file upload (multipart) + sensitive words ==")
        png = bytes(range(256)) * 4  # 1 KiB binary blob (not valid PNG; bytes survive)
        up = call_raw("POST", "/user/api/v1/file?fileName=avatar.png&fileType=png",
                      b"--XBOUND\r\nContent-Disposition: form-data; name=\"file\";"
                      b" filename=\"avatar.png\"\r\nContent-Type: image/png\r\n\r\n"
                      + png + b"\r\n--XBOUND--\r\n",
                      {"Content-Type": "multipart/form-data; boundary=XBOUND",
                       "Access-Token": tok1, "userId": str(uid1)})
        furl = (up.get("data") or "") if up.get("code") == 1 else ""
        check("upload returns local url", furl.startswith("http://127.0.0.1:18080/files/"),
              str(up)[:150])
        # the stored URL is the device-contract (port 18080); the host rig runs
        # on a random port, so rewrite it for the round-trip fetch
        got = raw_get(furl.replace(":18080/", ":%d/" % PORT)) if furl else b""
        check("uploaded file round-trips", got == png, "got %d bytes" % len(got))
        dup = call_raw("POST", "/user/api/v2/directory/file?fileName=x.bin&directory=mods",
                       b"--XBOUND\r\nContent-Disposition: form-data; name=\"file\";"
                       b" filename=\"x.bin\"\r\n\r\nhello-binary\r\n--XBOUND--\r\n",
                       {"Content-Type": "multipart/form-data; boundary=XBOUND",
                        "Access-Token": tok1, "userId": str(uid1)})
        check("directory file upload", dup.get("code") == 1
              and str(dup.get("data", "")).startswith("http://127.0.0.1:18080/files/"),
              str(dup)[:150])
        sw = call("GET", "/config/files/name-sensitive-word-config")
        check("sensitive words list", sw.get("code") == 1 and "admin" in sw.get("data", []),
              str(sw)[:150])
        nbad = call("POST", "/user/api/v1/user/nickname/exist?nickName=theOFFICIALone", None)
        ngood = call("POST", "/user/api/v1/user/nickname/exist?nickName=qa_free_name_%d"
                     % random.randint(1000, 9999), None)
        check("sensitive nickname rejected", nbad.get("code") == 0
              and ngood.get("code") == 1, "%s %s" % (str(nbad)[:80], str(ngood)[:80]))
        ra = call("PUT", "/game/api/v1/game/record/ads", None,
                  headers={"Access-Token": tok5, "userId": str(uid5), "language": "en"})
        check("record ads game credits", ra.get("code") == 1 and ra.get("data") == 100,
              str(ra)[:100])

        # ------------------------------------------------ Phase 5b: geo/rank/party
        print("== Phase 5b: geoinfo + region ranking + party auth ==")
        pg = call("POST", "/geoinfo/api/v1/userGeoInfo?longitude=31.2&latitude=30.0",
                  None, headers={"Access-Token": tok5, "userId": str(uid5)})
        check("post user geo", pg.get("code") == 1, str(pg)[:100])
        gl = call("GET", "/geoinfo/api/v1/userGeoInfo",
                  headers={"Access-Token": tok5, "userId": str(uid5), "language": "en"})
        glist = gl.get("data", [])
        me_rows = [m for m in glist if m.get("userId") == uid5]
        check("geo list has me + citizens", gl.get("code") == 1
              and len(me_rows) == 1 and len(glist) >= 20
              and me_rows[0]["latitude"] == 30.0 and me_rows[0]["distance"] == 0,
              str(gl)[:200])
        check("geo entries project x/y", all("x" in m and "y" in m and "pic" in m
              for m in glist), str(glist[0])[:120])
        cd = call("GET", "/geoinfo/api/v1/user/game/career/data/%d" % uid5,
                  headers={"language": "en"})
        check("career data shape", cd.get("code") == 1
              and "userGameCareerInfo" in cd.get("data", {})
              and "gameTimeMap" in cd["data"]["userGameCareerInfo"], str(cd)[:150])
        rh = call("GET", "/ranking/api/v1/ranking/region/home/page/info?rankType=overall")
        tops = rh.get("data", {}).get("topRankInfos", [])
        # Session 24 contract (overviewrank/f.java): the podium is ONE row per
        # category — gDiamond/active/clan — so the client's tap mapper can open
        # the matching rank template. Any other type value = silent no-op tap.
        top_types = [t.get("type") for t in tops]
        check("region rank home podium (one row per category)",
              rh.get("code") == 1 and len(tops) == 3
              and set(top_types) == {"gDiamond", "active", "clan"}
              and rh["data"].get("remainingTime", 0) > 0
              and tops[0].get("topName"), str(rh)[:220])
        ri = call("GET", "/ranking/api/v1/ranking/user/info?rankType=overall&type=gDiamond&isRegion=false",
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("user rank info gDiamond", ri.get("code") == 1
              and ri["data"].get("rank", 0) >= 1
              and ri["data"].get("quantity") == ri["data"].get("quantity"), str(ri)[:150])
        ri2 = call("GET", "/ranking/api/v1/ranking/user/info?rankType=week&type=clan&isRegion=true",
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("user rank info clan weekly", ri2.get("code") == 1
              and ri2["data"].get("rankType") == "week", str(ri2)[:120])
        pa = call("GET", "/game/api/v2/party/auth",
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        pad = pa.get("data", {})
        check("party auth loopback services", pa.get("code") == 1
              and pad.get("partyService") == "127.0.0.1:18080"
              and ":" in (pad.get("partyService") or "")
              and pad.get("token", "").startswith("pa-"), str(pa)[:200])
        pe = call("GET", "/api/v1/parties/exists")
        check("parties exists empty", pe.get("code") == 1 and pe.get("data") == "",
              str(pe)[:100])

        # ------------------------------------------------ Phase 5c: real mailbox
        print("== Phase 5c: mailbox (welcome mail / badge / claim / delete) ==")
        mh1 = {"Access-Token": tok1, "userId": str(uid1)}
        ml0 = call("GET", "/mailbox/api/v1/mail", headers=mh1)
        check("welcome mail after register", ml0.get("code") == 1
              and len(ml0.get("data", [])) >= 1, str(ml0)[:200])
        welcome = [m for m in ml0.get("data", []) if "Welcome" in m.get("title", "")]
        check("welcome mail unread w/ 500-gold attachment",
              len(welcome) == 1 and welcome[0]["status"] == 0
              and welcome[0]["attachment"][0]["qty"] == 500
              and welcome[0]["attachment"][0]["type"] == 2, str(welcome)[:200])
        new0 = call("GET", "/mailbox/api/v1/mail/new", headers=mh1)
        check("mail/new true when unread", new0.get("code") == 1
              and new0.get("data") is True, str(new0)[:80])
        wm0 = call("GET", "/pay/api/v1/wealth/user", headers=mh1).get("data", {})
        cl1 = call("PUT", "/mailbox/api/v1/mail/attachment?mailId=%d" % welcome[0]["id"],
                   None, headers=mh1)
        check("claim attachment ok", cl1.get("code") == 1, str(cl1)[:120])
        wm1 = call("GET", "/pay/api/v1/wealth/user", headers=mh1).get("data", {})
        cl2 = call("PUT", "/mailbox/api/v1/mail/attachment?mailId=%d" % welcome[0]["id"],
                   None, headers=mh1)
        wm2 = call("GET", "/pay/api/v1/wealth/user", headers=mh1).get("data", {})
        check("claim credits +500 golds once", cl2.get("code") == 0
              and wm1.get("golds", 0) == wm0.get("golds", 0) + 500
              and wm2.get("golds", 0) == wm1.get("golds", 0),
              "%s | w %s -> %s -> %s" % (str(cl2)[:80], wm0, wm1, wm2))
        new1 = call("GET", "/mailbox/api/v1/mail/new", headers=mh1)
        check("mail/new false after claim", new1.get("code") == 1
              and new1.get("data") is False, str(new1)[:80])
        mrd = call("PUT", "/mailbox/api/v1/mail?status=2&ids=%d" % welcome[0]["id"],
                   None, headers=mh1)
        check("mark read returns updated list", mrd.get("code") == 1 and len(mrd.get("data", [])) >= 1
              and all(m["status"] == 2 for m in mrd["data"] if m["id"] == welcome[0]["id"]),
              str(mrd)[:150])
        # fresh account: delete path + engine telemetry
        r9 = call("POST", "/user/api/v1/register",
                  {"uid": "qa_mailer", "password": "pw9", "imei": "dev9"})
        tok9, uid9 = r9["data"]["accessToken"], r9["data"]["userId"]
        mh9 = {"Access-Token": tok9, "userId": str(uid9)}
        ml9 = call("GET", "/mailbox/api/v1/mail", headers=mh9)
        check("second account own welcome mail", ml9.get("code") == 1
              and len(ml9.get("data", [])) == 1
              and ml9["data"][0]["id"] != welcome[0]["id"], str(ml9)[:150])
        del9 = call("PUT", "/mailbox/api/v1/mail?status=3&ids=%d" % ml9["data"][0]["id"],
                    None, headers=mh9)
        check("delete mail removes it", del9.get("code") == 1 and del9.get("data") == [],
              str(del9)[:120])
        new9 = call("GET", "/mailbox/api/v1/mail/new", headers=mh9)
        check("mail/new false after delete", new9.get("code") == 1
              and new9.get("data") is False, str(new9)[:80])
        eng = call("PUT", "/game/api/v1/games/engine?engineVersion=9.9&newEngineVersion=3",
                   None, headers={"CloudFront-Viewer-Country": "EG"})
        check("engine report ack", eng.get("code") == 1, str(eng)[:80])
        srw = call("GET", "/config/files/blockymods-share-reward")
        check("share reward config matches grant", srw.get("code") == 1
              and len(srw.get("data", [])) == 1 and srw["data"][0]["count"] == 200,
              str(srw)[:120])

        # --------------------------------- Phase 5e: spot checks over previously
        # --------------------------------- implemented-but-untested routes
        print("== Phase 5e: spot checks (game-map, ranking variants, VIP v4, password v2) ==")
        gm = call("GET", "/v1/game-map?typeId=%s&targetId=%d&gameVersion=1" % (gid, uid1),
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("v1/game-map issues token", gm.get("code") == 1
              and str(gm.get("data", {}).get("token", "")).startswith("mg-"), str(gm)[:120])
        rv = [("active", "week", False), ("clan", "overall", False),
              ("gDiamond", "week", True), ("gold", "overall", True)]
        for rt, wk, reg in rv:
            rr = call("GET", "/ranking/api/v1/ranking/user/info?rankType=%s&type=%s&isRegion=%s"
                      % (wk, rt, "true" if reg else "false"),
                      headers={"Access-Token": tok1, "userId": str(uid1)})
            check("rank variant %s/%s/region=%s" % (wk, rt, reg), rr.get("code") == 1
                  and rr.get("data", {}).get("rankType") == wk, str(rr)[:100])
        vip4 = call("POST", "/pay/api/v4/pay/users/recharge?type=android",
                    {"sku": "local.vip.1", "purchaseData": "local", "isSub": True},
                    headers={"Access-Token": tok1, "userId": str(uid1)})
        check("vip recharge v4 sets vip", vip4.get("code") == 1
              and vip4.get("data", {}).get("vip", 0) >= 1
              and vip4["data"].get("expireDate"), str(vip4)[:120])
        spw = call("POST", "/user/api/v2/app/set-password",
                   {"userId": uid9, "password": "newpw9", "confirmPassword": "newpw9"})
        check("v2 set-password", spw.get("code") == 1, str(spw)[:100])
        relg = call("POST", "/user/api/v1/login", {"uid": "qa_mailer", "password": "newpw9"})
        check("login with v2-set password", relg.get("code") == 1
              and relg.get("data", {}).get("userId") == uid9, str(relg)[:120])

        # client-contract regression (Session 12 on-device findings):
        # (a) the rename PUT uses newName=/oldName= (not nickName=) and MUST
        #     persist — the silent no-op the v0.5.18e run exposed;
        # (b) a guest upgraded via set-password gains an account name, and
        #     /user/api/v1/login must resolve it (findByAccount) — the
        #     'account not found' the v0.5.18e run exposed.
        cn2 = call("PUT", "/user/api/v2/user/nickName?newName=NewNameQA&oldName=QAChanged",
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("changeNickName client contract (newName=)", cn2.get("code") == 1
              and cn2.get("data", {}).get("nickName") == "NewNameQA", str(cn2)[:150])
        ne2 = call("POST", "/user/api/v1/user/nickname/exist?nickName=NewNameQA", None)
        check("renamed nickname is taken on the server", ne2.get("code") == 0,
              str(ne2)[:100])
        atg = call("GET", "/user/api/v1/app/auth-token?userId=%d" % uid9)
        gtok = (atg.get("data") or {}).get("accessToken", "")
        gu = call("POST", "/user/api/v2/app/set-password",
                  {"account": "upgraded_guest_qa", "password": "upgpw1",
                   "confirmPassword": "upgpw1"},
                  headers={"Access-Token": gtok, "userId": str(uid9)})
        check("guest upgrade sets account", gu.get("code") == 1, str(gu)[:100])
        glog = call("POST", "/user/api/v1/login",
                    {"uid": "upgraded_guest_qa", "password": "upgpw1"})
        check("login resolves the upgraded account (findByAccount)",
              glog.get("code") == 1 and glog.get("data", {}).get("userId") == uid9,
              str(glog)[:120])

        pwmod = call("POST", "/user/api/v2/user/password/modify",
                     {"oldPassword": "pw1", "newPassword": "pw1b", "confirmPassword": "pw1b"},
                     headers={"Access-Token": tok1, "userId": str(uid1)})
        pwbad = call("POST", "/user/api/v2/user/password/modify",
                     {"oldPassword": "WRONG", "newPassword": "x", "confirmPassword": "x"},
                     headers={"Access-Token": tok1, "userId": str(uid1)})
        check("v2 password modify + wrong-old rejected", pwmod.get("code") == 1
              and pwbad.get("code") == 0, "%s %s" % (str(pwmod)[:80], str(pwbad)[:80]))
        pwback = call("POST", "/user/api/v2/user/password/modify",
                      {"oldPassword": "pw1b", "newPassword": "pw1", "confirmPassword": "pw1"},
                      headers={"Access-Token": tok1, "userId": str(uid1)})
        check("v2 password restored", pwback.get("code") == 1, str(pwback)[:80])

        # ---- Wave 11: the RSA password contract --------------------------
        # The client encrypts v2 login/set-password/password-modify and
        # password/check payloads with RSA/ECB/PKCS1Padding against the
        # public key patched into it by scripts/patch_rsa_key.py. The server
        # decrypts for real (RsaCipher). The test encrypts with the SAME
        # key — parsed straight out of RsaCipher.java (single source of
        # truth) — using a dependency-free PKCS1v15 implementation.
        print("== Wave 11: RSA password contract ==")
        rsa_pub = _rsa_pub_from_java(os.path.join(REPO, "localapi-server", "src",
                                                  "com", "localapi", "RsaCipher.java"))
        check("rsa pubkey parsed from RsaCipher.java", rsa_pub is not None)
        if rsa_pub:
            r11 = call("POST", "/user/api/v1/register",
                       {"uid": "qa_rsa", "password": "plainpw11", "imei": "dev11"})
            uid11 = r11["data"]["userId"]
            enc11 = _rsa_pkcs1_encrypt(b"plainpw11", rsa_pub)
            # (a) v2 client-UI login with an RSA-encrypted password
            lr11 = call("POST", "/user/api/v2/app/login",
                        {"uid": "qa_rsa", "password": enc11, "hasPassword": True,
                         "needReward": 0, "appType": "android", "imei": "dev11",
                         "os": "12"})
            check("v2 login with RSA password", lr11.get("code") == 1
                  and lr11.get("data", {}).get("userId") == uid11, str(lr11)[:120])
            # (b) wrong RSA password rejected
            lw11 = call("POST", "/user/api/v2/app/login",
                        {"uid": "qa_rsa", "password": _rsa_pkcs1_encrypt(b"wrongpw", rsa_pub),
                         "hasPassword": True, "appType": "android", "imei": "dev11"})
            check("v2 login wrong RSA password rejected", lw11.get("code") == 0,
                  str(lw11)[:100])
            # (c) v1 plaintext login still passes (lenient fallback contract)
            lp11 = call("POST", "/user/api/v1/login", {"uid": "qa_rsa", "password": "plainpw11"})
            check("v1 plaintext login still ok", lp11.get("code") == 1, str(lp11)[:100])
            # (d) v2 set-password with RSA password + confirm, then RSA login
            sp11 = call("POST", "/user/api/v2/app/set-password",
                        {"userId": uid11, "password": _rsa_pkcs1_encrypt(b"newrsa11", rsa_pub),
                         "confirmPassword": _rsa_pkcs1_encrypt(b"newrsa11", rsa_pub)})
            check("v2 set-password RSA", sp11.get("code") == 1, str(sp11)[:100])
            sl11 = call("POST", "/user/api/v2/app/login",
                        {"uid": "qa_rsa", "password": _rsa_pkcs1_encrypt(b"newrsa11", rsa_pub),
                         "hasPassword": True, "appType": "android", "imei": "dev11"})
            check("v2 login with RSA-set password", sl11.get("code") == 1, str(sl11)[:100])
            # (e) v2 password modify with RSA old/new
            tok11 = sl11.get("data", {}).get("accessToken", "")
            hm11 = {"Access-Token": tok11, "userId": str(uid11)}
            pm11 = call("POST", "/user/api/v2/user/password/modify",
                        {"oldPassword": _rsa_pkcs1_encrypt(b"newrsa11", rsa_pub),
                         "newPassword": _rsa_pkcs1_encrypt(b"modpw11", rsa_pub),
                         "confirmPassword": _rsa_pkcs1_encrypt(b"modpw11", rsa_pub)},
                        headers=hm11)
            check("v2 password modify RSA", pm11.get("code") == 1, str(pm11)[:100])
            # (f) password/check with an RSA password (right / wrong)
            pc11r = call("POST", "/user/api/v1/user/password/check",
                         {"password": _rsa_pkcs1_encrypt(b"modpw11", rsa_pub)}, headers=hm11)
            pc11w = call("POST", "/user/api/v1/user/password/check",
                         {"password": _rsa_pkcs1_encrypt(b"nope", rsa_pub)}, headers=hm11)
            check("password/check RSA right+wrong", pc11r.get("code") == 1
                  and pc11r.get("data", {}).get("right") is True
                  and pc11w.get("data", {}).get("right") is False,
                  "%s %s" % (str(pc11r)[:80], str(pc11w)[:80]))
            # (g) a Base64 value that is NOT RSA-shaped passes through
            #     unchanged (still fails auth, but as wrong-password code 0
            #     — never a server error)
            nb11 = call("POST", "/user/api/v2/app/login",
                        {"uid": "qa_rsa", "password": "cGxhaW50ZXh0", "hasPassword": True,
                         "appType": "android", "imei": "dev11"})
            check("non-RSA base64 passthrough rejected as wrong-pw",
                  nb11.get("code") == 0, str(nb11)[:100])

        print("== Phase 7: client-verified error codes ==")
        # 7020 (UserOnError has_illegal_character): sensitive rename via a
        # DEFAULT config word ("admin" is seeded into sensitiveWords)
        r7 = call("POST", "/user/api/v1/register",
                  {"uid": "qa_p7_a", "password": "pw7", "imei": "dev7"})
        uid7, tok7 = r7["data"]["userId"], r7["data"]["accessToken"]
        h7 = {"Access-Token": tok7, "userId": str(uid7)}
        s7 = call("PUT", "/user/api/v2/user/nickName?newName=MrAdmin", headers=h7)
        check("rename to sensitive word rejected (7020)", s7.get("code") == 7020, str(s7)[:100])
        ok7 = call("PUT", "/user/api/v2/user/nickName?newName=Harmless", headers=h7)
        check("clean rename still ok", ok7.get("code") == 1, str(ok7)[:80])
        # 3001 / 3003 (FriendOnError)
        r7b = call("POST", "/user/api/v1/register",
                   {"uid": "qa_p7_b", "password": "pw7", "imei": "dev7b"})
        uid7b, tok7b = r7b["data"]["userId"], r7b["data"]["accessToken"]
        h7b = {"Access-Token": tok7b, "userId": str(uid7b)}
        r7c = call("POST", "/user/api/v1/register",
                   {"uid": "qa_p7_c", "password": "pw7", "imei": "dev7c"})
        uid7c, tok7c = r7c["data"]["userId"], r7c["data"]["accessToken"]
        h7c = {"Access-Token": tok7c, "userId": str(uid7c)}
        call("POST", "/friend/api/v1/friends", {"friendId": uid7b, "msg": "hi"}, headers=h7)
        call("PUT", "/friend/api/v1/friends/%d/agreement" % uid7, headers=h7b)
        dupf = call("POST", "/friend/api/v1/friends", {"friendId": uid7b}, headers=h7)
        check("friend dup rejected (3001)", dupf.get("code") == 3001, str(dupf)[:100])
        alias7 = call("POST", "/friend/api/v1/friends/%d/alias?alias=buddy" % uid7b, headers=h7)
        check("alias friend ok", alias7.get("code") == 1, str(alias7)[:80])
        alias7s = call("POST", "/friend/api/v1/friends/%d/alias?alias=x" % uid7c, headers=h7)
        check("alias stranger rejected (3003)", alias7s.get("code") == 3003, str(alias7s)[:100])
        # 7002 / 7014 (TribeOnError): name taken + 24h rejoin cooldown
        c7 = call("POST", "/clan/api/v2/clan/tribe",
                  {"name": "P7 Clan", "details": "d", "tags": ["t"], "currency": 2}, headers=h7)
        check("p7 clan create ok", c7.get("code") == 1, str(c7)[:120])
        c7dup = call("POST", "/clan/api/v2/clan/tribe",
                     {"name": "P7 Clan", "currency": 2}, headers=h7b)
        check("clan name taken (7002)", c7dup.get("code") == 7002, str(c7dup)[:100])
        lv7pre = call("POST", "/clan/api/v1/clan/tribe/member",
                      {"clanId": c7["data"]["clanId"], "msg": "join me"}, headers=h7b)
        check("p7 join requested", lv7pre.get("code") == 1, str(lv7pre)[:80])
        ag7 = call("PUT", "/clan/api/v1/clan/tribe/member/agreement?otherId=%d" % uid7b, headers=h7)
        check("p7 chief accepts", ag7.get("code") == 1, str(ag7)[:80])
        lv7 = call("DELETE", "/clan/api/v1/clan/tribe/member?clanId=%d" % c7["data"]["clanId"],
                   headers=h7b)
        check("member leaves clan", lv7.get("code") == 1, str(lv7)[:80])
        rj7 = call("POST", "/clan/api/v1/clan/tribe/member",
                   {"clanId": c7["data"]["clanId"], "msg": "rejoin"}, headers=h7b)
        check("rejoin within 24h rejected (7014)", rj7.get("code") == 7014, str(rj7)[:100])
        # sensitive clan name (TribeOnError 7020)
        c7bad = call("POST", "/clan/api/v2/clan/tribe",
                     {"name": "Admin Squad", "currency": 2}, headers=h7b)
        check("clan sensitive name rejected (7020)", c7bad.get("code") == 7020, str(c7bad)[:100])

        print("== Wave 5v: campaign sign-in + turntable + datareport ==")
        w5v = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        tok1 = w5v.get("data", {}).get("accessToken", tok1)
        golds_c0 = w5v.get("data", {}).get("golds", 0)
        H5 = {"Access-Token": tok1, "userId": str(uid1)}
        cslist = call("GET", "/activity/api/v1/signIn", None, headers=H5)
        d = cslist.get("data", {})
        days = d.get("userSignInList", [])
        check("campaign signInList 8 cells", cslist.get("code") == 1 and len(days) == 8, str(cslist)[:150])
        check("campaign ids 1..8", [x.get("signInId") for x in days] == list(range(1, 9)), str(days)[:150])
        check("campaign fresh all unclaimed", all(x.get("status") == 0 for x in days), str(days)[:100])
        check("campaign special days 7/8", days and days[6].get("isSpecial") == 1
              and days[7].get("isSpecial") == 1, str(days[-2:])[:120])
        check("campaign day8 carries 4 rewards", days and len(days[7].get("rewards", [])) == 4,
              str(days[-1])[:150])
        check("campaign signInStatus 0 (claimable)", d.get("signInStatus") == 0, str(d)[:100])
        check("campaign remainingTime epoch ms", isinstance(d.get("remainingTime"), int)
              and d.get("remainingTime", 0) > 0, str(d.get("remainingTime"))[:60])
        cclaim = call("POST", "/activity/api/v1/signIn", None, headers=H5)
        check("campaign claim day 1", cclaim.get("code") == 1
              and cclaim.get("data", {}).get("signInId") == 1, str(cclaim)[:120])
        w5v2 = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        golds_c1 = w5v2.get("data", {}).get("golds", 0)
        check("campaign claim credited wallet", golds_c1 == golds_c0 + 200,
              "golds %d -> %d" % (golds_c0, golds_c1))
        cslist2 = call("GET", "/activity/api/v1/signIn", None,
                       headers={"Access-Token": tok1, "userId": str(uid1)})
        d2 = cslist2.get("data", {})
        check("campaign day1 claimed after claim", d2.get("userSignInList", [{}])[0].get("status") == 1
              and d2.get("signInStatus") == 1, str(d2)[:150])
        cclaim2 = call("POST", "/activity/api/v1/signIn", None,
                       headers={"Access-Token": tok1, "userId": str(uid1)})
        check("campaign double-claim 7012", cclaim2.get("code") == 7012, str(cclaim2)[:100])
        csign_nologin = call("POST", "/activity/api/v1/signIn", None)
        check("campaign claim requires auth", csign_nologin.get("code") == 7, str(csign_nologin)[:80])
        # Wave 5v-2 (session 23): the campaign cycle-completion contract.
        # Client (MainModel/Zb.java): signInStatus 2 = cycle complete ->
        # the client chains INTO the week-sign surface (bc.e -> GET
        # /user/api/v2/users/{userId}/daily/sign/in). The cycle is
        # DATE-GATED server-side (one claim per calendar day — faithful
        # to a daily calendar), so completion is not reachable within a
        # single run; what IS testable is the invariant below.
        cs_done_today = call("GET", "/activity/api/v1/signIn", None,
                             headers={"Access-Token": tok1, "userId": str(uid1)})
        check("campaign claimed-today keeps signInStatus 1 (never 2 "
              "mid-cycle)", cs_done_today.get("data", {}).get("signInStatus") == 1,
              str(cs_done_today)[:120])
        cclaim3 = call("POST", "/activity/api/v1/signIn", None,
                       headers={"Access-Token": tok1, "userId": str(uid1)})
        check("campaign claim after completion 7012", cclaim3.get("code") == 7012,
              str(cclaim3)[:100])
        tt = call("GET", "/activity/api/v1/lucky/turntable/gold/status?activityId=Lucky%202020",
                  headers={"language": "en"})
        slot = call("GET", "/activity/api/v1/slot/machine/user/gold/draw/status?activityId=slot_machine",
                    headers={"language": "en"})
        check("turntable isFree", tt.get("code") == 1 and tt.get("data", {}).get("isFree") == 1, str(tt)[:100])
        check("slot draw isFree", slot.get("code") == 1 and slot.get("data", {}).get("isFree") == 1, str(slot)[:100])
        # Wave 5w: the turntable draw chain (info -> draw -> status flips)
        ttinfo = call("GET", "/game/api/v1/game/10001/turntable",
                      headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("turntable info 8 prizes", ttinfo.get("code") == 1 and len(ttinfo.get("data", [])) == 8
              and all("id" in p and "picUrl" in p for p in ttinfo.get("data", [])), str(ttinfo)[:150])
        ttprops = call("GET", "/game/api/v1/game/10001/turntable/props",
                       headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("turntable props free tip", ttprops.get("code") == 1
              and "free draw" in str(ttprops.get("data", "")).lower(), str(ttprops)[:120])
        ttdraw = call("PUT", "/game/api/v1/game/10001/turntable", None,
                      headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        drawn_id = ttdraw.get("data")
        check("turntable draw returns prize id", ttdraw.get("code") == 1
              and isinstance(drawn_id, int) and 1 <= drawn_id <= 8, str(ttdraw)[:120])
        w5v3 = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        golds_c2 = w5v3.get("data", {}).get("golds", 0)
        prize_table = {1: 100, 2: 200, 3: 500, 4: 1000, 5: 50, 6: 300, 7: 800, 8: 2000}
        check("turntable prize credited wallet", golds_c2 == golds_c1 + prize_table[drawn_id],
              "golds %d -> %d (prize %s = +%d)" % (golds_c1, golds_c2, drawn_id, prize_table[drawn_id]))
        ttstatus2 = call("GET", "/activity/api/v1/lucky/turntable/gold/status?activityId=slot_machine",
                         headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("turntable isFree flips after draw", ttstatus2.get("code") == 1
              and ttstatus2.get("data", {}).get("isFree") == 0, str(ttstatus2)[:120])
        ttdraw2 = call("PUT", "/game/api/v1/game/10001/turntable", None,
                       headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("second draw rejected", ttdraw2.get("code") != 1, str(ttdraw2)[:120])
        ttprops2 = call("GET", "/game/api/v1/game/10001/turntable/props",
                        headers={"Access-Token": tok1, "userId": str(uid1), "language": "en"})
        check("turntable props used tip", ttprops2.get("code") == 1
              and "used" in str(ttprops2.get("data", "")).lower(), str(ttprops2)[:120])
        # Wave 5w cont: the per-game ads-CD config files (AdsCdConfig)
        for cfg in ("indiegame-10001", "indiegame-new-10001"):
            cd = call("GET", "/config/files/%s" % cfg)
            check("adsCdConfig %s" % cfg, cd.get("code") == 1
                  and cd.get("data", {}).get("adsCdTimeFirst", 0) > 0
                  and cd.get("data", {}).get("adsCdTimeSecond", 0) > 0, str(cd)[:120])
        ev = call("POST", "/datareport/api/v1/event/report",
                  {"packageName": "com.test.host", "eventRequests": [
                      {"event": "qa_event", "eventType": "behavior", "platform": "android"}]},
                  headers={"deviceId": "qa-dev-1"})
        fu = call("POST", "/datareport/api/v1/funnel/event/report",
                  [{"eventType": "qa_funnel", "platform": "android", "eventList": []}],
                  headers={"deviceId": "qa-dev-1"})
        pg = call("POST", "/datareport/api/v1/app/ping/report/batch", {"pingEvents": []},
                  headers={"deviceId": "qa-dev-1", "CloudFront-Viewer-Country": "US"})
        check("event report ack", ev.get("code") == 1, str(ev)[:100])
        check("funnel report ack", fu.get("code") == 1, str(fu)[:100])
        check("ping report ack", pg.get("code") == 1, str(pg)[:100])
        import glob as _glob
        rep_files = _glob.glob(os.path.join(state_dir, "localapi", "datareport", "*.jsonl"))
        rep_bodies = ""
        for rf in rep_files:
            rep_bodies += open(rf).read()
        check("datareport persisted to disk store", len(rep_files) >= 1
              and "qa_event" in rep_bodies and "qa_funnel" in rep_bodies,
              "files=%d" % len(rep_files))

        print("== Wave 6c: activity task chain (titles light the surface) ==")
        at_h = {"Access-Token": tok1, "userId": str(uid1)}
        at_titles = call("GET", "/activity/api/v2/activity/title", None, headers=at_h)
        at_list = at_titles.get("data", {}).get("activityTitleList", [])
        at_types = sorted(x.get("titleType") for x in at_list)
        check("activity titles weekday+weekend served", at_titles.get("code") == 1
              and at_types == ["weekday", "weekend"], str(at_titles)[:160])
        check("activity titles pass the client's country filter (f.a)",
              all(x.get("countryList") == [] for x in at_list), str(at_list)[:120])
        check("activity titles endTime -1 (no expiry, f.b)",
              all(x.get("endTime") == -1 for x in at_list), str(at_list)[:120])
        check("activity serverTime real", at_titles.get("data", {}).get("serverTime", 0) > 0,
              str(at_titles.get("data", {}))[:100])
        at_wd = call("GET", "/activity/api/v1/activity/action?titleType=weekday",
                     None, headers=at_h)
        check("weekday actions = 3 online_time rows (10/30/60)",
              at_wd.get("code") == 1
              and [x.get("quantity") for x in at_wd.get("data", [])] == [10, 30, 60]
              and all(x.get("actionFlag") == "online_time" for x in at_wd.get("data", [])),
              str(at_wd)[:200])
        check("weekday action carries the client's fields",
              at_wd.get("data") and all(k in at_wd["data"][0] for k in
                  ("actionId", "actionFlag", "actionName", "quantity",
                   "completeQuantity", "status", "actionRewards")),
              str(at_wd.get("data", [{}])[0])[:180])
        check("weekday rewards shaped (golds 200)",
              at_wd.get("data")
              and at_wd["data"][0]["actionRewards"][0].get("rewardType") == "golds"
              and at_wd["data"][0]["actionRewards"][0].get("quantity") == 200,
              str(at_wd.get("data", [{}])[0].get("actionRewards"))[:140])
        at_we = call("GET", "/activity/api/v1/activity/action?titleType=weekend",
                     None, headers=at_h)
        check("weekend actions incl the login rows", at_we.get("code") == 1
              and sorted(x.get("actionFlag") for x in at_we.get("data", []))
              == ["online_time", "saturday_login", "sunday_login"], str(at_we)[:200])
        at_bad = call("GET", "/activity/api/v1/activity/action?titleType=nope",
                      None, headers=at_h)
        check("unknown titleType rejected", at_bad.get("code") != 1, str(at_bad)[:100])
        at_noauth = call("GET", "/activity/api/v1/activity/action?titleType=weekday")
        check("action list requires auth", at_noauth.get("code") == 7, str(at_noauth)[:80])
        # fresh user -> deterministic in-progress state (onlineMinutes < 10)
        call("POST", "/user/api/v1/register",
             {"uid": "atq1", "password": "pwatq1", "confirmPassword": "pwatq1",
              "imei": "atqdev", "appType": "android", "os": "12"})
        atq = call("POST", "/user/api/v1/login",
                   {"uid": "atq1", "password": "pwatq1", "imei": "atqdev"})
        atq_h = {"Access-Token": atq.get("data", {}).get("accessToken", ""),
                 "userId": str(atq.get("data", {}).get("userId", 0))}
        atq_wd = call("GET", "/activity/api/v1/activity/action?titleType=weekday",
                      None, headers=atq_h)
        check("fresh user online_time in progress (status 0, complete < 10)",
              atq_wd.get("code") == 1 and atq_wd["data"][0].get("status") == 0
              and atq_wd["data"][0].get("completeQuantity", 99) < 10, str(atq_wd)[:180])
        atq_claim = call("POST",
                         "/activity/api/v1/receive/reward?titleType=weekday&actionId=1",
                         None, headers=atq_h)
        check("incomplete claim rejected", atq_claim.get("code") != 1, str(atq_claim)[:100])
        atq_bad = call("POST",
                       "/activity/api/v1/receive/reward?titleType=weekday&actionId=999",
                       None, headers=atq_h)
        check("unknown action claim rejected", atq_bad.get("code") != 1, str(atq_bad)[:100])

        print("== route-table sweep (all routes answer the envelope) ==")
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        sweep_miss = []
        count = 0
        with open(os.path.join(REPO, "localapi-server", "src", "com", "localapi", "RoutingTable.java")) as f:
            import re
            for m in re.finditer(r'"([A-Z]+) ([^|]+)\|([a-z]+|H:[a-zA-Z]+)"', f.read()):
                verb, path, kind = m.group(1), m.group(2), m.group(3)
                concrete = re.sub(r"\{[^}]+\}", "123", path)
                try:
                    resp = call(verb if verb in ("GET", "POST", "PUT", "DELETE") else "GET", concrete, {})
                except Exception as e:
                    resp = {"__sweep_error": str(e)}
                count += 1
                ok = resp.get("code") == 1
                if not ok and kind.startswith("H:"):
                    # handlers reject empty/invalid payloads with ANY business
                    # code (Phase 7: 7/101/102/7001-7014/8102-8104/3001-3004...)
                    ok = isinstance(resp.get("code"), int)
                if "__sweep_error" in resp:
                    # one retry on a transient socket hiccup before failing
                    try:
                        resp = call(verb if verb in ("GET", "POST", "PUT", "DELETE") else "GET", concrete, {})
                        ok = resp.get("code") in (0, 1)
                    except Exception as e2:
                        resp = {"__sweep_error": str(e2)}
                        ok = False
                if not ok:
                    sweep_miss.append((verb, concrete, str(resp)[:120]))
        check("sweep %d routes all reachable" % count, not sweep_miss, str(sweep_miss[:5]))

        print("== login-surface contracts (IUserLoginApi decode) ==")
        # GET /user/api/v1/user/set-psd/param/check — client model HttpResponse<Long>.
        # The old {} default crashed Gson on the Long parse; data must be a number.
        # VALUE semantics (GooglePlayPayService recharge onSuccess decode):
        # l > 100 -> startPasswordSettingDialog; the local server prompts
        # (200) for passwordless users, 0 for accounts that have a password.
        psd = call("GET", "/user/api/v1/user/set-psd/param/check?type=set")
        check("set-psd param check returns Long", psd.get("code") == 1
              and isinstance(psd.get("data"), (int, float)), str(psd)[:120])
        # POST /user/api/v1/account/invalid/check — client model HttpResponse<Boolean>.
        # VALUE semantics (SetAccountViewModel h.java decode): true = the
        # name is FREE (confirm dialog then accountModify); false = taken
        # ("Account already exists" helper, flow stops).
        aic = call("POST", "/user/api/v1/account/invalid/check"
                   "?account=qa_invalid_probe&loginTypeId=1&type=login")
        check("account invalid check free name -> true", aic.get("code") == 1
              and aic.get("data") is True, str(aic)[:120])
        # a name that IS taken on this server must answer false
        call("POST", "/user/api/v1/register",
             {"uid": "qa_invalid_taken", "password": "pw11", "imei": "dev11ic"})
        aic2 = call("POST", "/user/api/v1/account/invalid/check"
                    "?account=qa_invalid_taken&loginTypeId=1&type=login")
        check("account invalid check taken name -> false", aic2.get("code") == 1
              and aic2.get("data") is False, str(aic2)[:120])
        vis0 = call("POST", "/user/api/v1/visitor", {"imei": "qa_login_surface_probe"})
        check("probe visitor unaffected", vis0.get("code") == 1
              and bool(vis0.get("data", {}).get("accessToken")), str(vis0)[:120])

        print("== persistence ==")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        time.sleep(1.5)
    # second boot must see persisted users
    # wave 6c: inject 15 online minutes for qa_user1 while the server is
    # stopped — the state file is the documented, inspectable store, so the
    # completion path (status 1 -> claim -> status 2 -> wallet) is testable
    # in milliseconds instead of 10 real minutes of client traffic.
    st_path = os.path.join(state_dir, "localapi", "state.json")
    with open(st_path, "r", encoding="utf-8") as fh:
        st_root = json.load(fh)
    _today = time.strftime("%Y-%m-%d", time.gmtime())
    _hit = False
    for _u in st_root.get("users", {}).values():
        if str(_u.get("userId")) == str(uid1):
            _act = _u.setdefault("state", {}).setdefault("activity", {})
            _act.update({"day": _today, "onlineMinutes": 15, "lastMinute": "",
                         "lastDayLogin": _today, "claimed": {}})
            _hit = True
    with open(st_path, "w", encoding="utf-8") as fh:
        json.dump(st_root, fh)
    check("activity state injected for the completion test", _hit, st_path)
    server_log2 = open(os.path.join(state_dir, "server2.log"), "wb")
    proc2 = subprocess.Popen(
        ["java", "-cp", HOST_CP, "com.localapi.HostTest", state_dir, str(PORT)],
        stdout=server_log2, stderr=subprocess.STDOUT)
    try:
        if not wait_ready():
            print("server restart failed")
            sys.exit(1)
        lg = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1"})
        check("state persists across restart", lg.get("code") == 1
              and lg.get("data", {}).get("userId") == uid1, str(lg)[:150])
        cond = call("GET", "/game/api/v1/game/revision/list/by/condition"
                    "?sortType=online&filterTypeId=0&pageNo=1&pageSize=10&os=android")
        check("catalog persists across restart", cond.get("code") == 1
              and len(cond.get("data", {}).get("pageInfo", {}).get("data", [])) == 10,
              str(cond)[:120])
        si3 = call("GET", "/user/api/v2/users/%d/daily/sign/in" % uid1,
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("sign-in state persists (claimed = 2)", si3.get("code") == 1
              and si3.get("data", {}).get("first", {}).get("status") == 2, str(si3)[:120])
        # Wave 5v: campaign sign-in cycle + datareport files persist across restart
        csp = call("GET", "/activity/api/v1/signIn", None, headers={"Access-Token": tok1, "userId": str(uid1)})
        check("campaign cycle persists", csp.get("code") == 1
              and csp.get("data", {}).get("userSignInList", [{}])[0].get("status") == 1
              and csp.get("data", {}).get("signInStatus") == 1, str(csp)[:150])
        csp2 = call("POST", "/activity/api/v1/signIn", None, headers={"Access-Token": tok1, "userId": str(uid1)})
        check("campaign claim still 7012 after restart", csp2.get("code") == 7012, str(csp2)[:100])
        # Wave 6c cont: the injected 15 online minutes complete the 10-min
        # task; the full lifecycle closes (status 1 -> claim -> status 2 ->
        # wallet credit -> 7012). Day-dependent login tasks branch on the
        # real UTC weekday so the rig stays deterministic any day.
        lg6 = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1"})
        h6 = {"Access-Token": lg6.get("data", {}).get("accessToken", tok1),
              "userId": str(uid1)}
        at_wd2 = call("GET", "/activity/api/v1/activity/action?titleType=weekday",
                      None, headers=h6)
        _a1 = (at_wd2.get("data") or [{}])[0]
        check("injected minutes -> 10min task claimable (status 1, complete 10)",
              at_wd2.get("code") == 1 and _a1.get("status") == 1
              and _a1.get("completeQuantity") == 10, str(at_wd2)[:200])
        at_title2 = call("GET", "/activity/api/v2/activity/title", None, headers=h6)
        check("cumulativeTime reflects tracked minutes (>=15)",
              at_title2.get("code") == 1
              and at_title2.get("data", {}).get("cumulativeTime", 0) >= 15,
              str(at_title2.get("data", {}))[:140])
        g_before6 = lg6.get("data", {}).get("golds", 0)
        at_claim6 = call("POST",
                         "/activity/api/v1/receive/reward?titleType=weekday&actionId=1",
                         None, headers=h6)
        check("claim 10min task (+200, status 2)",
              at_claim6.get("code") == 1 and at_claim6.get("data", {}).get("status") == 2
              and at_claim6.get("data", {}).get("completeQuantity") == 10,
              str(at_claim6)[:180])
        lg6b = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1"})
        g_after6 = lg6b.get("data", {}).get("golds", 0)
        check("activity claim credited wallet (+200)", g_after6 == g_before6 + 200,
              "golds %d -> %d" % (g_before6, g_after6))
        at_claim6b = call("POST",
                          "/activity/api/v1/receive/reward?titleType=weekday&actionId=1",
                          None, headers=h6)
        check("activity double-claim 7012", at_claim6b.get("code") == 7012,
              str(at_claim6b)[:100])
        _wday = time.gmtime().tm_wday  # Monday=0 .. Sunday=6
        for _aid, _flagname, _pywday in ((5, "saturday_login", 5),
                                         (6, "sunday_login", 6)):
            _lc = call("POST",
                       "/activity/api/v1/receive/reward?titleType=weekend&actionId=%d" % _aid,
                       None, headers=h6)
            if _wday == _pywday:
                check("%s claimable on its real day" % _flagname,
                      _lc.get("code") == 1, str(_lc)[:120])
            else:
                check("%s rejected off-day" % _flagname,
                      _lc.get("code") != 1, str(_lc)[:120])
        # Phase 4: tribe state persists (uid1 chief + uid2 elder remain; uid3 exited, uid4 kicked)
        lg4 = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1"})
        tok1b = lg4["data"]["accessToken"]
        h1b = {"Access-Token": tok1b, "userId": str(uid1), "language": "en"}
        tidp = call("GET", "/clan/api/v1/clan/tribe/id", headers=h1b)
        check("tribe membership persists", tidp.get("code") == 1 and tidp.get("data") == str(clan_id),
              str(tidp)[:100])
        basep = call("GET", "/clan/api/v1/clan/tribe/base", headers=h1b)
        check("clan roster persists", basep.get("code") == 1
              and basep["data"].get("currentCount") == 2
              and basep["data"].get("name") == "QA Clan", str(basep)[:150])
        bnp = call("GET", "/clan/api/v1/clan/tribe/bulletin", headers=h1b)
        check("bulletin persists", bnp.get("code") == 1
              and bnp["data"].get("content") == "Welcome to QA Clan", str(bnp)[:100])
        dhp = call("GET", "/clan/api/v2/clan/tribe/donation/history?pageNo=1&pageSize=10", headers=h1b)
        check("donation history persists", dhp.get("code") == 1
              and dhp["data"].get("totalSize", 0) == 2, str(dhp)[:120])
        recp = call("GET", "/clan/api/v1/clan/tribe/recommendation", headers=h1b)
        check("npc tribes persist (not reseeded)", recp.get("code") == 1
              and len(recp.get("data", [])) == 10, str(len(recp.get("data", []))))  # 8 npc + QA Clan + P7 Clan
        # Phase 5c: mailbox persists — welcome mail claimed (no re-credit), wallet intact
        tok1c = tok1b
        mh1c = {"Access-Token": tok1c, "userId": str(uid1)}
        mlp = call("GET", "/mailbox/api/v1/mail", headers=mh1c)
        wp = [m for m in mlp.get("data", []) if "Welcome" in m.get("title", "")]
        check("welcome mail persists across restart", mlp.get("code") == 1 and len(wp) == 1
              and wp[0]["status"] == 2, str(mlp)[:200])
        wmpre = call("GET", "/pay/api/v1/wealth/user", headers=mh1c).get("data", {})
        clp = call("PUT", "/mailbox/api/v1/mail/attachment?mailId=%d" % wp[0]["id"],
                   None, headers=mh1c)
        wmpost = call("GET", "/pay/api/v1/wealth/user", headers=mh1c).get("data", {})
        check("claimed mail not re-credited after restart", clp.get("code") == 0
              and wmpost.get("golds", 0) == wmpre.get("golds", 0),
              "%s | w %s -> %s" % (str(clp)[:80], wmpre, wmpost))
    finally:
        proc2.terminate()
        try:
            proc2.wait(timeout=5)
        except Exception:
            proc2.kill()

    print("== boot resilience: watchdog takeover (v0.5.9 EADDRINUSE fix) ==")
    # v0.5.8 device evidence: a relaunched app process failed 5 binds against
    # the live holder then gave up FOREVER — if the holder died later that
    # instance would have no server. HostBootTest simulates it in-process:
    # a junk holder socket owns the port for 9s, LocalServer.start runs beside
    # it (fast path fails, watchdog starts), holder releases -> watchdog must
    # take the port over and serve state.
    port2 = random.randint(20000, 40000)
    while port2 == PORT:
        port2 = random.randint(20000, 40000)
    state_b = tempfile.mkdtemp(prefix="localapi-boot-")
    boot_log = open(os.path.join(state_b, "boot.log"), "wb")
    boot = subprocess.Popen(
        ["java", "-cp", HOST_CP, "com.localapi.HostBootTest", state_b,
         str(port2), "blocked"],
        stdout=boot_log, stderr=subprocess.STDOUT)
    try:
        base2 = "http://127.0.0.1:%d" % port2
        deadline = time.time() + 45
        up = False
        while time.time() < deadline:
            try:
                v = call("GET", "/config/files/blockymods-check-version", base=base2)
                if v.get("code") == 1:
                    up = True
                    break
            except Exception:
                pass
            time.sleep(0.7)
        check("watchdog takes over after holder release", up)
        if up:
            u = call("POST", "/user/api/v1/visitor", {"imei": "bootqa1"}, base=base2)
            check("post-takeover visitor ok", u.get("code") == 1
                  and bool(u.get("data", {}).get("accessToken")), str(u)[:120])
    finally:
        boot.terminate()
        try:
            boot.wait(timeout=5)
        except Exception:
            boot.kill()

    print("== boot resilience: standby does not disturb the holder ==")
    # A second process starts while a REAL LocalAPI instance is serving: its
    # fast path must fail quietly, its watchdog must detect genuine HTTP and
    # stand by — and the holder must keep serving untouched throughout.
    state_s = tempfile.mkdtemp(prefix="localapi-standby-")
    sb_log = open(os.path.join(state_s, "sb.log"), "wb")
    sb = subprocess.Popen(
        ["java", "-cp", HOST_CP, "com.localapi.HostBootTest", state_s,
         str(PORT), "standby"],
        stdout=sb_log, stderr=subprocess.STDOUT)
    try:
        time.sleep(9)  # fast path (5 x 1s) + at least one watchdog probe cycle
        v1 = call("GET", "/config/files/blockymods-check-version")
        check("holder still serving while standby watches", v1.get("code") == 1,
              str(v1)[:100])
        alive = sb.poll() is None
        time.sleep(3)
        v2 = call("GET", "/config/files/blockymods-check-version")
        check("holder unaffected by standby probes", v2.get("code") == 1,
              str(v2)[:100])
        check("standby process stayed alive (no crash)",
              alive and sb.poll() is None)
    finally:
        sb.terminate()
        try:
            sb.wait(timeout=5)
        except Exception:
            sb.kill()

    print("== boot resilience: bind race stands down fast (run 37569020063) ==")
    # Device evidence (run 37569020063, pid 12672): the loser of a bind
    # race against a sibling LocalAPI holder burned 5 x 1s binds ON THE
    # MAIN THREAD (App.onCreate) before its watchdog detected the holder.
    # HostBootTest "race" reproduces it deterministically: the holder
    # speaks junk on connection 1 (fast-path probe fails) and HTTP from
    # connection 2 (the post-bind-loss probe) — the loser must stand down
    # after the FIRST lost bind, leave the port to the holder, and return
    # from start() in well under a second (the old path took ~5s).
    port4 = random.randint(20000, 40000)
    while port4 in (PORT, port2):
        port4 = random.randint(20000, 40000)
    state_rc = tempfile.mkdtemp(prefix="localapi-race-")
    race_log_path = os.path.join(state_rc, "race.log")
    race_log = open(race_log_path, "wb")
    race = subprocess.Popen(
        ["java", "-cp", HOST_CP, "com.localapi.HostBootTest", state_rc,
         str(port4), "race"],
        stdout=race_log, stderr=subprocess.STDOUT)
    try:
        time.sleep(4)  # start() must have returned well inside this window
        race_log.flush()
        with open(race_log_path) as f:
            logtxt = f.read()
        m = re.search(r"RACE START RETURNED in (\d+)ms", logtxt)
        check("race: start returned after the stand-down", bool(m),
              logtxt[-160:])
        if m:
            check("race: loser stood down fast (<3s; the old path was ~5s)",
                  int(m.group(1)) < 3000, "elapsed=%sms" % m.group(1))
        check("race: loser did NOT bind (holder keeps the port)",
              "RACE BOUND=false" in logtxt, logtxt[-160:])
        ok_holder = False
        try:
            s = socket.create_connection(("127.0.0.1", port4), timeout=2)
            s.sendall(b"GET /health HTTP/1.0\r\n\r\n")
            ok_holder = s.recv(64).startswith(b"HTTP/")
            s.close()
        except Exception:
            pass
        check("race: sibling holder still serving", ok_holder)
        check("race: standby process stayed alive (no crash)",
              race.poll() is None)
    finally:
        race.terminate()
        try:
            race.wait(timeout=5)
        except Exception:
            race.kill()

    print("== boot resilience: in-process server death self-heals ==")
    # The watchdog is PERSISTENT (runs for the process's whole life): if the
    # HTTPD dies while the app process stays alive, it must notice (its state
    # machine goes UP -> NO SERVER) and re-boot. HostBootTest "resurrect"
    # stops the live server 2s after boot; the rig watches up -> down -> up.
    port3 = random.randint(20000, 40000)
    while port3 in (PORT, port2):
        port3 = random.randint(20000, 40000)
    state_r = tempfile.mkdtemp(prefix="localapi-resurrect-")
    res_log = open(os.path.join(state_r, "res.log"), "wb")
    res = subprocess.Popen(
        ["java", "-cp", HOST_CP, "com.localapi.HostBootTest", state_r,
         str(port3), "resurrect"],
        stdout=res_log, stderr=subprocess.STDOUT)
    try:
        base3 = "http://127.0.0.1:%d" % port3
        saw_up = saw_down = up_again = False
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                v = call("GET", "/config/files/blockymods-check-version", base=base3)
                serving = v.get("code") == 1
            except Exception:
                serving = False
            if serving:
                if not saw_up:
                    saw_up = True
                elif saw_down:
                    up_again = True
                    break
            elif saw_up:
                saw_down = True
            time.sleep(0.4)
        check("resurrect: initial boot observed", saw_up)
        check("resurrect: in-process stop observed", saw_down)
        check("watchdog resurrects after in-process death", up_again)
        if up_again:
            u = call("POST", "/user/api/v1/visitor", {"imei": "resqa1"}, base=base3)
            check("post-resurrect visitor ok", u.get("code") == 1
                  and bool(u.get("data", {}).get("accessToken")), str(u)[:120])
    finally:
        res.terminate()
        try:
            res.wait(timeout=5)
        except Exception:
            res.kill()

    print("\nRESULT: %d passed, %d failed" % (len(passed), len(failed)))
    if failed:
        print("failed:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
