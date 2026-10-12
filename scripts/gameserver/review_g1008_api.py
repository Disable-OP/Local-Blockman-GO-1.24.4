#!/usr/bin/env python3
"""g1008 game-scripts review: sweep every engine-class call in the decompiled
10078 SERVER-RUN Lua trees against the 10068(+10078-compat) C++ registration
table. Same method as docs/10078_GAME_SERVER_UPDATE.md 2.4, restricted to the
trees the g10078 bundle actually loads on the server, and split engine vs game
so NEW game-side gaps surface.
"""
import os, re, sys, json, collections

DEV = "/home/z/work10068/dev"
SRC = "/home/z/src10078"

# ---------- 1. C++ registration table ----------
cls_re   = re.compile(r"_BEGIN_REGISTER_CLASS\(\s*(\w+)\s*\)")
mem_re   = re.compile(r"_CLASSREGISTER_(AddMember_Override|AddStaticMember_Override|AddMember|AddVar|AddStaticMember|AddCtor)\(\s*(\w*)\s*[,)]")
base_re  = re.compile(r"_CLASSREGISTER_AddBaseClass\(\s*(\w+)\s*\)")
end_re   = re.compile(r"_END_REGISTER_CLASS\(\)")

classes = {}          # name -> set(members)
cur = None

WALK_ROOTS = [DEV + "/server/src", DEV + "/logic/Src/LuaRegister", DEV + "/client/Src"]
for walk_root in WALK_ROOTS:
    for root, dirs, files in os.walk(walk_root):
        for fn in sorted(files):
            if not fn.endswith((".cpp", ".h")):
                continue
            path = os.path.join(root, fn)
            try:
                txt = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for line in txt.splitlines():
                m = cls_re.search(line)
                if m:
                    cur = m.group(1)
                    classes.setdefault(cur, set())
                    continue
                if end_re.search(line):
                    cur = None
                    continue
                if cur:
                    m = mem_re.search(line)
                    if m:
                        name = m.group(2)
                        if m.group(1) == "AddCtor" and not name:
                            name = "new"      # _CLASSREGISTER_AddCtor() -> 'new'
                        if name:
                            classes[cur].add(name)
                    m = base_re.search(line)
                    if m:
                        classes.setdefault("__base__:" + cur, set()).add(m.group(1))

# fold base-class members into derived (fixpoint)
for _ in range(4):
    changed = False
    for c in list(classes):
        if c.startswith("__base__"):
            continue
        for b in classes.get("__base__:" + c, set()):
            if b in classes:
                new = classes[b] - classes[c]
                if new:
                    classes[c] |= new
                    changed = True
    if not changed:
        break

real_classes = {c: ms for c, ms in classes.items() if not c.startswith("__base__")}
all_members = set()
for c, ms in real_classes.items():
    all_members |= ms
print(f"[table] classes={len(real_classes)} registered members(unique)={len(all_members)}")
print(f"[table] has World: {'World' in real_classes}, "
      f"World members: {len(real_classes.get('World', set()))}")

# ---------- 2. shims (from the bundle BaseMain.lua) ----------
SHIM_METHODS = {
    ("HostApi", "onSetClipboard"), ("HostApi", "reportError"),
    ("HostApi", "reportErrorFile"), ("HostApi", "reportErrorResource"),
    ("World", "getEntitiesWithinAABBExcludingEntityReturnJson"),
    ("DynamicCastEntity", "dynamicCastFireBall"),
    ("DynamicCastEntity", "dynamicCastFishhook"),
    ("DynamicCastEntity", "dynamicCastItemSkill"),
    ("DynamicCastEntity", "dynamicCastSnowball"),
    ("GunSetting", "getGunSetting"),
}

# ---------- 3. Lua trees the g10078 bundle loads on the server ----------
TREES = [
    ("engine_server",  SRC + "/Engine/lua/engine_server", False),
    ("engine_base",    SRC + "/Engine/lua/engine_base",   False),
    ("engine_plugins", SRC + "/Engine/lua/plugins",       False),
    ("game_server",    SRC + "/Game/g1008/lua/server",    True),
    ("game_base",      SRC + "/Game/g1008/lua/base",      True),
]

# ---------- 4. Lua-side definitions (shadow detection) ----------
def collect_lua_defs(paths):
    defined = collections.defaultdict(set)
    for p in paths:
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in re.finditer(r"([A-Za-z_][\w]*)\s*[.:]([A-Za-z_]\w*)\s*(?:=|\()", txt):
            defined[m.group(1)].add(m.group(2))
    return defined

# ---------- 5. call-site extraction ----------
call_re = re.compile(r"\b([A-Z][A-Za-z0-9_]{1,40})\s*([:.])\s*([a-zA-Z_]\w*)\s*[\(\{\"\']")

def scan():
    paths = []
    for label, path, is_game in TREES:
        for root, dirs, files in os.walk(path):
            for fn in files:
                if fn.endswith(".lua"):
                    paths.append((label, is_game, os.path.join(root, fn)))
    lua_defs = collect_lua_defs([p for _, _, p in paths])

    missing = collections.defaultdict(lambda: collections.defaultdict(set))
    ok_hits = 0
    per_tree_ok = collections.Counter()
    for label, is_game, p in paths:
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        rel = os.path.relpath(p, SRC)
        local_decls = set(re.findall(r"local\s+([A-Za-z_]\w*)", txt))
        for m in call_re.finditer(txt):
            cls, mem = m.group(1), m.group(3)
            if cls not in real_classes:
                continue
            if cls in local_decls:
                continue                  # file-local shadow (e.g. EngineWorld's 'local World')
            if mem in real_classes[cls] or (cls, mem) in SHIM_METHODS:
                ok_hits += 1
                per_tree_ok[label] += 1
                continue
            missing[label][(cls, mem)].add(rel)
    return missing, ok_hits, per_tree_ok, lua_defs

missing, ok_hits, per_tree_ok, lua_defs = scan()
print(f"[scan] resolved engine-class calls: {ok_hits}  per tree: {dict(per_tree_ok)}")
total_missing = sum(len(v) for v in missing.values())
print(f"[scan] UNRESOLVED engine-class member calls: {total_missing}")

for label in [t[0] for t in TREES]:
    items = missing.get(label, {})
    if not items:
        print(f"\n== {label}: clean")
        continue
    print(f"\n== {label}: {len(items)} unresolved")
    for (cls, mem), files in sorted(items.items()):
        fl = ", ".join(sorted(files)[:3])
        more = f" (+{len(files)-3} files)" if len(files) > 3 else ""
        shadow = mem in lua_defs.get(cls, set())
        tag = " [lua-defined-member]" if shadow else ""
        print(f"   {cls}.{mem}{tag}  <- {fl}{more}")

json.dump(
    {label: {f"{c}.{m}": sorted(fs) for (c, m), fs in v.items()} for label, v in missing.items()},
    open("/tmp/g1008_api_review.json", "w"), indent=1)
print("\n[written] /tmp/g1008_api_review.json")
