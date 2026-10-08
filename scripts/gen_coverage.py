#!/usr/bin/env python3
"""Generate docs/COVERAGE.json — machine-readable API coverage report.

Sources of truth:
- localapi-server/src/com/localapi/RoutingTable.java  (discovered + implemented)
- scripts/test_server_host.py                          (host-tested paths)
- scripts/ui_automation_test.py                        (client-exercised paths)

Status per endpoint:
- "implemented": H: handler (real state-backed behavior)
- "default":     schema-true static default ({} / [] / "" / 0 / false / none)
- "tested":      endpoint path appears in the host test suite
- "client_seen": endpoint path pattern appears in the UI automation assertions
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = os.path.join(REPO, "localapi-server", "src", "com", "localapi", "RoutingTable.java")
HOST = os.path.join(REPO, "scripts", "test_server_host.py")
UI = os.path.join(REPO, "scripts", "ui_automation_test.py")


def load_routes():
    routes = []
    with open(TABLE) as f:
        for m in re.finditer(r'"([A-Z]+) ([^|]+)\|([^"]+)"', f.read()):
            verb, path, kind = m.group(1), m.group(2), m.group(3)
            routes.append({
                "verb": verb,
                "path": path,
                "kind": kind,
                "implemented": kind.startswith("H:"),
                "handler": kind[2:] if kind.startswith("H:") else None,
            })
    return routes


def concrete_paths(source):
    """Literal path fragments used by the test suites (strip query strings).
    Strings that sit directly behind an fcall("VERB",  cursor are NOT
    included — those are verb-matched by fcall_claims (wave 15 honesty:
    a GET fcall must not claim its PUT/DELETE siblings through the
    verb-blind pool). Bare literals and assertion probes stay here.

    Wave-29a honesty fix: %-formatted literals (e.g.
    "/game/api/v1/game/%s/turntable" inside a probe list) used to be
    captured only up to the % — handing the truncated trailing-slash
    prefix the deliberate-probe privilege and phantom-claiming whole
    families (game chat rooms, team members, turntable PUT...). Now the
    full literal is read: a clean %-format tail normalizes to a {fmt}
    template segment (router-style matching, under-claiming beats
    phantom-claiming); prose tails are dropped entirely."""
    out = set()
    for m in re.finditer(r'"([^"]*)"', source):
        prefix_txt = source[max(0, m.start() - 48):m.start()]
        if re.search(r'fcall\("[A-Za-z]+",\s*$', prefix_txt):
            continue
        lit = m.group(1)
        head = re.match(r'/[A-Za-z0-9\-._{}/]*', lit)
        if not head:
            continue
        p = head.group(0)
        rest = lit[len(p):]
        if rest.startswith("%"):
            m2 = re.match(r'%[\w.]+((?:/[A-Za-z0-9\-._{}/]*)*)(?:\?.*)?$', rest)
            if not m2:
                continue
            segs = [s for s in p.split("/") if s]
            # {fmt+}: the substituted value may span several segments
            # (the host ranking loop passes "active/global/weekly" as
            # ONE %s) — template_match resolves it router-faithfully
            # against the route string, concrete routes excluded.
            segs.append("{fmt+}")
            segs += [s for s in m2.group(1).split("/") if s]
            p = "/" + "/".join(segs)
        else:
            p = p.split("?")[0]
        if len(p) > 4:
            out.add(p)
    return out


def fcall_claims(source):
    """(verb, path) pairs from fcall("VERB", "/path...") probes — verb-aware
    claims (wave 15 honesty fix). The full string literal is captured
    (query stripped) and %-format segments are normalized into {fmt}
    template placeholders BEFORE matching, so a formatted fcall URL
    claims its route TEMPLATE the way the router dispatches a real
    request (wave 24a honesty fix: the old capture stopped at the % and
    handed the truncated prefix the trailing-slash probe privilege —
    which phantom-claimed unrelated siblings like
    GET /user/api/v1/users/security/bind/email). Genuine trailing-slash
    literals (deliberate prefix probes, no % anywhere) keep the prefix
    rule; formatted literals are matched segment-wise only."""
    out = set()
    for m in re.finditer(r'fcall\("(\w+)",\s*"([^"]*)"', source):
        verb = m.group(1).upper()
        p = m.group(2).split("?")[0]
        if "%" in p:
            segs = []
            for s in p.split("/"):
                # a WHOLE-segment %format becomes a placeholder; a
                # mid-segment one (indiegame-new-%s) is kept as-is so
                # _seg_match can apply the router's embedded-wildcard
                # rule (route {gameId} -> ([^/]+) regex).
                segs.append("{fmt}" if s.startswith("%") else s)
            p = "/".join(segs)
        if len(p) > 4:
            out.add((verb, p))
    return out


def template_match(template, literal, concrete=None):
    """Wave 16 honesty+coverage fix: a concrete literal claims a ROUTE-TABLE
    TEMPLATE exactly the way the router dispatches real requests — equal
    segment count, every {placeholder} consumes exactly one literal segment,
    all other segments equal. Never lets a literal claim a longer/shorter
    sibling (the wave-15b rule still holds), and never claims concrete
    routes (they keep the exact/prefix rules).

    Router dispatch semantics: a CONCRETE route wins over a template, so a
    literal that IS a concrete table route (e.g. /user/scrap/value when
    /user/scrap/{scrapId} also exists) must never claim the template —
    pass `concrete` (the set of placeholder-free table paths) to enforce
    that; otherwise the literal /user/scrap/value would phantom-claim the
    {scrapId} sibling just because "value" fits one segment."""
    if concrete is not None and literal in concrete:
        return False
    if "{fmt+}" in literal:
        # multi-segment format probe: match the literal (as a regex with
        # {fmt+} -> .+) against the ROUTE string. NOTE: no concrete-route
        # exclusion here — the probe's runtime values legitimately hit
        # concrete routes (the host ranking loop calls every
        # /ranking/api/v1/<board>/rank board, all concrete entries), and
        # value-tracking is out of scope; shape-matching is the closest
        # honest approximation.
        lit_rx = re.escape(literal).replace(re.escape("{fmt+}"), ".+")
        if re.fullmatch(lit_rx, template) is not None:
            return True
        # Wave 43: placeholder routes with a {placeholder} AFTER the fmt
        # segment (e.g. template .../users/{userId}/type/{typeId} fed by
        # the rig literal .../users/%d/type/101) can NEVER match the
        # literal-as-regex above — the concrete tail (101) is not the
        # template's literal text. Reverse the direction, router-faithful:
        # build the pattern the ROUTER builds from the template
        # ({name} -> [^/]+, static segments escaped) and fullmatch it
        # against the literal, with the fmt value itself confined to ONE
        # segment ([^/]+): a multi-segment runtime value would not
        # dispatch to a single-segment placeholder, so under-claiming
        # stays the honest default (same stance as direction 1).
        tpl_rx = "/".join(
            "[^/]+" if (s.startswith("{") and s.endswith("}")) else re.escape(s)
            for s in template.split("/"))
        return re.fullmatch(tpl_rx, literal) is not None
    ts = template.split("/")
    ls = literal.split("/")
    if len(ts) != len(ls):
        return False
    return all(_seg_match(t, l) for t, l in zip(ts, ls))


def _seg_match(t, l):
    """One template segment vs one literal segment, router-faithful.
    The real router turns every {name} into ([^/]+) REGEX — including
    EMBEDDED ones (the /config/files/indiegame-{gameId} family), so a
    literal with a %-format wildcard inside a segment claims that route
    when the static frames around the wildcard agree (wave 25c)."""
    if t == l:
        return True
    if t.startswith("{") and t.endswith("}"):
        return True
    if "{" in t and "%" in l:
        t_pre, _, t_rest = t.partition("{")
        t_post = t_rest.split("}", 1)[1] if "}" in t_rest else ""
        l_pre, _, l_rest = l.partition("%")
        l_post = l_rest
        while l_post and l_post[0] in "sdf0123456789.":
            l_post = l_post[1:]
        return t_pre == l_pre and t_post == l_post
    return False


def main():
    routes = load_routes()
    host_src = open(HOST).read() if os.path.exists(HOST) else ""
    ui_src = open(UI).read() if os.path.exists(UI) else ""
    host_fcalls = fcall_claims(host_src)
    ui_fcalls = fcall_claims(ui_src)
    host_paths = concrete_paths(host_src)
    ui_paths = concrete_paths(ui_src)

    report = []
    concrete_routes = {r["path"] for r in routes if "{" not in r["path"]}
    for r in routes:
        tested = any(hp == r["path"] or r["path"].startswith(hp.rstrip("*"))
                     or template_match(r["path"], hp, concrete_routes)
                     for hp in host_paths)
        # Honesty (session-28 + wave-15b): a UI literal claims a LONGER
        # route via prefix ONLY when it is itself a deliberate prefix
        # probe — it must END with "/" (e.g. "/game/api/v1/games/"). A
        # complete path literal ("/a/b/using") must never claim its
        # longer siblings ("/a/b/using/new") — that is how the
        # decorations/using family got phantom PUT/DELETE claims.
        client_seen = any(
            up == r["path"]
            or (up.endswith("/")
                and len(up.rstrip("*").split("/")) >= 4
                and r["path"].startswith(up.rstrip("*")))
            or template_match(r["path"], up, concrete_routes)
            for up in ui_paths)
        # Verb-aware fcall claims (wave 15): fcall("GET", "/a/b") asserts
        # exactly the GET route (prefix only from trailing-/ URLs) — never
        # its PUT/DELETE siblings on the same path. Wave 16: template
        # routes unify segment-wise (router dispatch semantics).
        client_seen = client_seen or any(
            fv == r["verb"]
            and (fp == r["path"]
                 or (fp.endswith("/")
                     and len(fp.rstrip("*").split("/")) >= 4
                     and r["path"].startswith(fp.rstrip("*")))
                 or template_match(r["path"], fp, concrete_routes))
            for fv, fp in ui_fcalls)
        status = "implemented" if r["implemented"] else "default"
        report.append({
            "verb": r["verb"],
            "path": r["path"],
            "status": status,
            "handler": r["handler"],
            "host_tested": tested,
            "client_asserted": client_seen,
        })

    summary = {
        "discovered": len(report),
        "implemented": sum(1 for x in report if x["status"] == "implemented"),
        "default": sum(1 for x in report if x["status"] == "default"),
        "host_tested": sum(1 for x in report if x["host_tested"]),
        "client_asserted": sum(1 for x in report if x["client_asserted"]),
    }

    doc = {
        "_comment": ("Generated by scripts/gen_coverage.py — do not edit by hand. "
                     "'implemented' = state-backed handler; 'default' = schema-true "
                     "static response; 'host_tested' = exercised by "
                     "scripts/test_server_host.py; 'client_asserted' = exercised "
                     "in UI automation (app or adb-forward)."),
        "summary": summary,
        "endpoints": report,
    }
    out = os.path.join(REPO, "docs", "COVERAGE.json")
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print("wrote %s: %d discovered, %d implemented, %d default, %d host-tested"
          % (out, summary["discovered"], summary["implemented"],
             summary["default"], summary["host_tested"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
