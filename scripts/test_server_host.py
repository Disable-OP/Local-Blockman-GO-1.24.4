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
        check("gameDetail unknown -> code 0", gnf.get("code") == 0, str(gnf)[:100])

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
        check("signin unclaimed status", si["data"]["first"]["status"] == 0
              and si["data"]["first"]["quantity"] > 0, str(si["data"]["first"])[:100])
        cs = call("PUT", "/user/api/v2/users/%d/daily/sign/in" % uid1,
                  headers={"Access-Token": tok1, "userId": str(uid1)})
        check("clickSignIn ok", cs.get("code") == 1, str(cs)[:100])
        after = call("POST", "/user/api/v1/login", {"uid": "qa_user1", "password": "pw1", "imei": "dev1"})
        golds1 = after.get("data", {}).get("golds", 0)
        check("sign-in credited wallet", golds1 == golds0 + 200, "golds %d -> %d" % (golds0, golds1))
        si2 = call("GET", "/user/api/v2/users/%d/daily/sign/in" % uid1,
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("signin claimed status", si2["data"]["first"]["status"] == 1, str(si2["data"]["first"])[:100])
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
        mail = call("GET", "/mailbox/api/v1/mail/new")
        check("mail/new bool", mail.get("code") == 1 and mail.get("data") is False, str(mail)[:80])

        print("== Phase 2: rooms, tokens, misc ==")
        room = call("POST", "/game/api/v1/game/chat/room?roomName=qa-room", {})
        room2 = call("POST", "/game/api/v1/game/chat/room?roomName=qa-room", {})
        check("chatRoom stable id", room.get("code") == 1 and room.get("data", {}).get("roomId")
              and room["data"]["roomId"] == room2.get("data", {}).get("roomId"), str(room)[:100])
        app2 = call("PUT", "/game/api/v1/games/%s/appreciation" % gid)
        check("appreciation int", app2.get("code") == 1
              and isinstance(app2.get("data"), int) and app2["data"] > 0, str(app2)[:100])
        tok = call("GET", "/game/api/v2/game/auth?typeId=1&targetId=%d&gameVersion=1" % uid1,
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("miniGameToken", tok.get("code") == 1 and tok.get("data", {}).get("token")
              and tok["data"].get("timestamp", 0) > 0
              and tok["data"].get("dispUrl") == "", str(tok)[:150])
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
                    (dl["data"][1]["id"], dl["data"][2]["id"]), None,
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
        check("combine insufficient rejected", badc.get("code") == 0, str(badc)[:100])
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
        check("mail list empty", ml.get("code") == 1 and ml.get("data") == [], str(ml)[:80])
        mo = call("PUT", "/mailbox/api/v1/mail?status=1&ids=1", [])
        check("mail op ack", mo.get("code") == 1 and mo.get("data") == [], str(mo)[:80])
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
        check("unauthenticated recharge rejected", noauth.get("code") == 0, str(noauth)[:80])

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
        cond = call("GET", "/game/api/v1/game/revision/list/by/condition"
                    "?sortType=online&filterTypeId=0&pageNo=1&pageSize=10&os=android")
        check("catalog persists across restart", cond.get("code") == 1
              and len(cond.get("data", {}).get("pageInfo", {}).get("data", [])) == 10,
              str(cond)[:120])
        si3 = call("GET", "/user/api/v2/users/%d/daily/sign/in" % uid1,
                   headers={"Access-Token": tok1, "userId": str(uid1)})
        check("sign-in state persists", si3.get("code") == 1
              and si3.get("data", {}).get("first", {}).get("status") == 1, str(si3)[:120])
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
