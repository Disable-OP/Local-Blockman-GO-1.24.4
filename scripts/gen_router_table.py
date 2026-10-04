#!/usr/bin/env python3
"""Generate localapi-server/src/com/localapi/RoutingTable.java from decompiled Retrofit interfaces.

Parses every Retrofit interface found in work/endpoints.json (jadx .java output),
derives the Gson data shape for each endpoint (list / obj / str / num / bool / none)
and marks overridden endpoints with special handler names (H:<handler>).

Usage: python3 scripts/gen_router_table.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JADX = os.path.join(ROOT, "work", "jadx_out")
OUT = os.path.join(ROOT, "work", "Local-Blockman-GO-1.24.4",
                   "localapi-server", "src", "com", "localapi", "RoutingTable.java")

# Endpoints implemented with real state-backed handlers (Phase 1: auth + boot config).
HANDLERS = {
    "POST /user/api/v1/login": "login",
    "POST /user/api/v1/app/login": "login",
    "POST /user/api/v2/app/login": "login",
    "POST /user/api/v1/register": "register",
    "POST /user/api/v1/user/register": "userRegister",
    "POST /user/api/v1/visitor": "visitor",
    "POST /user/api/v1/app/user/tourist/login": "tourist",
    "POST /user/api/v1/account/invalid/check": "ackPost",
    "GET /user/api/v1/app/auth-token": "authToken",
    "POST /user/api/v1/app/renew": "renew",
    "PUT /user/api/v1/user/login-out": "logout",
    "GET /user/api/v1/users/device/token": "rongToken",
    "GET /config/files/blockymods-check-version": "checkVersion",
    "GET /config/files/blockmods-config-v1": "appConfig",
    "PUT /user/api/v2/user/nickName": "changeNickName",
    "PUT /user/api/v1/user/info": "changeInfo",
    "POST /user/api/v1/user/details/info": "changeInfo",
    "GET /user/api/v1/user/profile/join/switch": "joinSwitch",
    "PUT /user/api/v1/user/device/id": "ackPut",
    "POST /user/api/v1/user/mac/id": "ackPost",
    "POST /user/api/v1/user/language": "ackPost",
    # --- Phase 5: dispatch bridge + suits + upload + misc ---
    "POST /v1/dispatch": "dispatch",
    "POST /v1/follow": "follow",
    "GET /v1/game-res": "gameResInfo",
    "PUT /game/api/v1/game/record/ads": "recordAdsGame",
    "GET /shop/api/v1/new/shop/suit/decorations": "shopSuitList",
    "GET /shop/api/v1/new/shop/suit/list/info": "suitListByIds",
    "GET /shop/api/v1/new/shop/suit/info/{suitId}": "suitDetail",
    "GET /shop/api/v1/new/shop/gift/suit/receive": "suitGiftInfo",
    "POST /shop/api/v1/new/shop/gift/suit/receive": "suitGiftReceive",
    "POST /user/api/v1/file": "uploadFile",
    "POST /user/api/{version}/directory/file": "uploadFile",
    "GET /config/files/name-sensitive-word-config": "sensitiveWords",
    "POST /geoinfo/api/v1/userGeoInfo": "postUserGeoInfo",
    "GET /geoinfo/api/v1/userGeoInfo": "userGeoList",
    "GET /geoinfo/api/v1/user/game/career/data/{userId}": "careerData",
    "GET /ranking/api/v1/ranking/region/home/page/info": "regionRankHome",
    "GET /ranking/api/v1/ranking/user/info": "userRankInfo",
    "GET /game/api/v2/party/auth": "partyAuth",
    "GET /api/v1/parties/exists": "partiesExists",
}

ANN = re.compile(r'@(GET|POST|PUT|DELETE)\("([^"]+)"\)')
RET = re.compile(r'Observable<\s*HttpResponse\s*(?:<\s*(.+?)\s*>\s*)?>\s+(\w+)\s*\(')


def data_kind(generic):
    if generic is None:
        return "none"
    g = generic.strip()
    if g.startswith("List<"):
        return "list"
    if g.startswith("Map<"):
        return "obj"
    if g in ("String",):
        return "str"
    if g in ("Long", "Integer", "Float", "Double"):
        return "num"
    if g in ("Boolean",):
        return "bool"
    return "obj"


def find_java(iface_smali_path):
    rel = iface_smali_path + ".java"  # e.g. com/sandboxol/center/web/IUserApi
    for src in os.listdir(JADX):
        cand = os.path.join(JADX, src, rel)
        if os.path.exists(cand):
            return cand
    return None


def parse_iface(java_path):
    with open(java_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    out = []
    for m in RET.finditer(text):
        kind = data_kind(m.group(1))
        method_name = m.group(2)
        # last verb+path annotation before this return type
        best = None
        for a in ANN.finditer(text, 0, m.start()):
            best = a
        if best is None:
            print("  !! no mapping annotation above %s in %s" % (method_name, java_path), file=sys.stderr)
            continue
        out.append((best.group(1), best.group(2), kind, method_name))
    return out


def discover_interfaces():
    """Find every Retrofit interface in the jadx output that returns
    Observable<HttpResponse<...>> (third-party SDK lookalikes excluded)."""
    found = []
    EXCLUDE = ("/bytedance/", "/firebase/", "/twitter/", "/facebook/",
               "/umeng/", "/pstatp/", "/supersonic/", "/ironsrc/",
               "/applovin/", "/vungle/", "/unity3d/", "/google/")
    for src in os.listdir(JADX):
        base = os.path.join(JADX, src)
        for dirpath, _dirnames, filenames in os.walk(base):
            if dirpath.replace(os.sep, "/").rsplit("/", 1)[-1] != "web":
                continue
            for fn in filenames:
                if not fn.endswith(".java"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, base).replace(os.sep, "/")[:-5]
                if any(e in ("/" + rel) for e in EXCLUDE):
                    continue
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    continue
                if "Observable<HttpResponse" in text and ANN.search(text):
                    found.append(rel)
    return sorted(set(found))


def main():
    ifaces = discover_interfaces()
    rows = {}  # "VERB path" -> kind
    iface_count = 0
    for iface in ifaces:
        jp = None
        for src in os.listdir(JADX):
            cand = os.path.join(JADX, src, iface + ".java")
            if os.path.exists(cand):
                jp = cand
                break
        if jp is None:
            print("!! java source missing for %s" % iface, file=sys.stderr)
            continue
        iface_count += 1
        for verb, path, kind, mname in parse_iface(jp):
            if not path.startswith("/"):
                path = "/" + path  # Retrofit relative paths resolve against base URL
            key = "%s %s" % (verb, path)
            if key in HANDLERS:
                kind = "H:" + HANDLERS[key]
            rows[key] = kind
    # literals first so {version}/{gameId} templates never shadow real paths
    ordered = sorted(rows.items(), key=lambda kv: (1 if "{" in kv[0] else 0, kv[0]))
    buf = []
    buf.append("package com.localapi;")
    buf.append("")
    buf.append("/** GENERATED by scripts/gen_router_table.py — do not edit by hand.")
    buf.append(" *  %d routes from %d Retrofit interfaces. Key format: \"VERB /path|kind\"." % (len(ordered), iface_count))
    buf.append(" *  kinds: obj|list|str|num|bool|none = schema-true default; H:<name> = state-backed handler. */")
    buf.append("public final class RoutingTable {")
    buf.append("    public static final String[] ROUTES = {")
    for key, kind in ordered:
        buf.append('        "%s|%s",' % (key, kind))
    buf.append("    };")
    buf.append("")
    buf.append("    private RoutingTable() {}")
    buf.append("")
    buf.append("    /** Exact verb+template match; literals win because they sort first. Returns kind or null. */")
    buf.append("    public static String lookup(String verb, String path) {")
    buf.append("        for (String entry : ROUTES) {")
    buf.append("            int bar = entry.indexOf('|');")
    buf.append("            String verbPath = entry.substring(0, bar);")
    buf.append("            int sp = verbPath.indexOf(' ');")
    buf.append("            if (!verbPath.substring(0, sp).equals(verb)) continue;")
    buf.append("            if (matches(verbPath.substring(sp + 1), path)) return entry.substring(bar + 1);")
    buf.append("        }")
    buf.append("        return null;")
    buf.append("    }")
    buf.append("")
    buf.append("    private static boolean matches(String tmpl, String path) {")
    buf.append("        String rx = tmpl.replaceAll(\"\\\\{[^}]+\\\\}\", \"([^/]+)\");")
    buf.append("        return path.matches(rx);")
    buf.append("    }")
    buf.append("}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(buf) + "\n")
    handlers = sum(1 for k, v in ordered if v.startswith("H:"))
    kinds = {}
    for _, v in ordered:
        kinds[v] = kinds.get(v, 0) + 1
    print("interfaces parsed: %d" % iface_count)
    print("routes generated:  %d (handlers: %d)" % (len(ordered), handlers))
    print("kind distribution: %s" % json.dumps(kinds, sort_keys=True))


if __name__ == "__main__":
    main()
