#!/usr/bin/env python3
"""Apply surgical patches to the assembled GameServer sources (idempotent).

Patches (all build-environment driven, none change game behaviour):
1. CoreDef.h            — aarch64 recognized as 64-bit; LORD_FORCE_PLATFORM override
                          so the server compiles its LINUX branches under the NDK.
2. curl_config.h        — drop OpenSSL (loopback http only, no TLS dependency).
3. Core/Std/cpp17/string_view.h — skip the backport shim under libc++.
4. ClientPeer.cpp       — getName() returns LORD::String; passing it through
                          printf-style varargs is UB (gcc hard-errors on it).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
ENGINE = os.path.join(ROOT, 'extract', 'engine-core', 'dev', 'engine')
LIBS = os.path.join(ROOT, 'extract', 'engine-core', 'dev', 'libraries')
SERVER = os.path.join(ROOT, 'extract', 'dev', 'server', 'src')


def patch(path, transforms):
    with open(path, encoding='latin-1') as f:
        s = f.read()
    orig = s
    for old, new in transforms:
        if new in s:
            continue  # already applied
        if old not in s:
            raise SystemExit('patch anchor missing in %s: %r' % (path, old[:60]))
        s = s.replace(old, new, 1)
    if s != orig:
        with open(path, 'w', encoding='latin-1') as f:
            f.write(s)
        print('patched', os.path.relpath(path, ROOT))
    else:
        print('ok (already)', os.path.relpath(path, ROOT))


# 1. CoreDef.h
patch(os.path.join(ENGINE, 'Src/Core/CoreDef.h'), [
    ("defined(__s390x__)",
     "defined(__s390x__) || defined(__aarch64__) || defined(_M_ARM64)"),
    ("#if defined(_WIN32) || defined(__WIN32__) || defined(WIN32)\n#\tdefine LORD_PLATFORM    LORD_PLATFORM_WINDOWS",
     "#if defined(LORD_FORCE_PLATFORM)\n#\tdefine LORD_PLATFORM    LORD_FORCE_PLATFORM\n#elif defined(_WIN32) || defined(__WIN32__) || defined(WIN32)\n#\tdefine LORD_PLATFORM    LORD_PLATFORM_WINDOWS"),
])

# 2. curl_config.h — no TLS needed for loopback
patch(os.path.join(LIBS, 'src/android/curl/curl_config.h'), [
    ("#define USE_OPENSSL 1",
     "/* #undef USE_OPENSSL */ /* loopback-only build: TLS not needed */"),
])

# 3. string_view shim vs libc++
patch(os.path.join(ENGINE, 'Src/Core/Std/cpp17/string_view.h'), [
    ("#if __cplusplus < 201703L",
     "#if !defined(_LIBCPP_VERSION) && __cplusplus < 201703L"),
])

# 3c. gcc 4.9 cannot resolve an overloaded member-function address against
#     explicit template args (reg.addOverrideMember<Ret,Args...>(name, &C::f)).
#     Rewrite every _CLASSREGISTER_*_Override site into an explicit
#     static_cast form. Line-based (robust): each site is one full line.
_OVERRIDE_FILES = [
    os.path.join(SERVER, 'LuaRegister/Server/Blockman_Register.cpp'),
    os.path.join(ROOT, 'extract/dev/logic/Src/LuaRegister/Content/Logic/Item_Register.h'),
    os.path.join(ROOT, 'extract/dev/logic/Src/LuaRegister/Content/Logic/World_Register.h'),
    os.path.join(ROOT, 'extract/dev/logic/Src/LuaRegister/Content/Logic/Util_Register.h'),
    os.path.join(ROOT, 'extract/dev/logic/Src/LuaRegister/Content/Logic/Inventory_Register.h'),
    os.path.join(ROOT, 'extract/dev/logic/Src/LuaRegister/Content/Logic/Block_Register.h'),
    os.path.join(ROOT, 'extract/dev/logic/Src/LuaRegister/Content/Logic/Entity_Register.h'),
]

def _rewrite_line(line, static):
    tag = '_CLASSREGISTER_AddStaticMember_Override' if static \
          else '_CLASSREGISTER_AddMember_Override'
    if not line.lstrip().startswith(tag):
        return None
    inner = line.strip()[len(tag):].strip()
    if not (inner.startswith('(') and inner.endswith(')')):
        return None
    inner = inner[1:-1]
    parts = [x.strip() for x in inner.split(',')]
    if len(parts) < 3:
        return None
    name, ref, ret = parts[0], parts[1], parts[2]
    args = ', '.join(parts[3:])
    if static:
        cast = '%s (*)(%s)' % (ret, args) if args else '%s (*)()' % ret
        tmpl = '<%s, %s>' % (ret, args) if args else '<%s>' % ret
        return 'reg.addOverrideStaticMember%s("%s", static_cast<%s>(&%s));' \
               % (tmpl, name, cast, ref)
    cast = '%s (%s::*)(%s)' % (ret, ref.rpartition('::')[0], args) if args \
           else '%s (%s::*)()' % (ret, ref.rpartition('::')[0])
    tmpl = '<%s, %s>' % (ret, args) if args else '<%s>' % ret
    return 'reg.addOverrideMember%s("%s", static_cast<%s>(&%s));' \
           % (tmpl, name, cast, ref)

_n = 0
for _f in _OVERRIDE_FILES:
    if not os.path.isfile(_f):
        continue
    _out = []
    _changed = False
    for _line in open(_f, encoding='latin-1'):
        _r = _rewrite_line(_line, static='AddStaticMember_Override' in _line)
        if _r is None:
            _out.append(_line)
        else:
            _out.append(_r + '\n')
            _changed = True
            _n += 1
    if _changed:
        open(_f, 'w', encoding='latin-1').write(''.join(_out))
print('override sites rewritten: %d' % _n)

# special case: static override without explicit signature
_blk = os.path.join(ROOT, 'extract/dev/logic/Src/LuaRegister/Content/Logic/Block_Register.h')
if os.path.isfile(_blk):
    _t = open(_blk, encoding='latin-1').read()
    _fixed = _t.replace(
        '_CLASSREGISTER_AddStaticMember_Override(isAssociatedBlockID, Block::isAssociatedBlockID)',
        'reg.addOverrideStaticMember("isAssociatedBlockID", '
        'static_cast<bool (*)(int, int)>(&Block::isAssociatedBlockID));')
    if _fixed != _t:
        open(_blk, 'w', encoding='latin-1').write(_fixed)
        print('patched isAssociatedBlockID special case')

# 3d. stale registration signatures (dev tree snapshot drift): the
#     _Override sites for BlockChangeRecorderServer::record claim (int,int,int)
#     but the real overloads are (int×7) and (const BlockPos&, int×4).
_regcpp = os.path.join(SERVER, 'LuaRegister/Server/Blockman_Register.cpp')
if os.path.isfile(_regcpp):
    _t = open(_regcpp, encoding='latin-1').read()
    _t2 = _t.replace(
        'reg.addOverrideMember<bool, int, int, int>("record", '
        'static_cast<bool (BlockChangeRecorderServer::*)(int, int, int)>'
        '(&BlockChangeRecorderServer::record));',
        'reg.addOverrideMember<bool, int, int, int, int, int, int, int>("record", '
        'static_cast<bool (BlockChangeRecorderServer::*)(int, int, int, int, int, int, int)>'
        '(&BlockChangeRecorderServer::record));')
    _t2 = _t2.replace(
        'reg.addOverrideMember<bool, const BlockPos &>("record1", '
        'static_cast<bool (BlockChangeRecorderServer::*)(const BlockPos &)>'
        '(&BlockChangeRecorderServer::record));',
        'reg.addOverrideMember<bool, const BlockPos &, int, int, int, int>("record1", '
        'static_cast<bool (BlockChangeRecorderServer::*)(const BlockPos &, int, int, int, int)>'
        '(&BlockChangeRecorderServer::record));')
    if _t2 != _t:
        open(_regcpp, 'w', encoding='latin-1').write(_t2)
        print('patched record signatures')

# 3e. const-qualified override targets (dev tree snapshot drift): the line
#     rewriter above emits NON-const member-pointer casts, but these six
#     engine methods are declared const (Entity.h:424/426, StructureBB.h
#     inline bodies). ClassRegister<T> only binds const member pointers
#     through its (Ret(T::*)(Args...) const) overload (Template/
#     ClassRegister.h:42), so the generated casts must carry the trailing
#     const. Listed explicitly — the rewriter cannot see class headers.
_CONST_OVERRIDE_FIXUPS = {
    os.path.join(ROOT, 'extract/dev/logic/Src/LuaRegister/Content/Logic/Entity_Register.h'): [
        ('static_cast<bool (Entity::*)(float)>(&Entity::isInRangeToRenderDist)',
         'static_cast<bool (Entity::*)(float) const>(&Entity::isInRangeToRenderDist)'),
        ('static_cast<bool (Entity::*)(const Vector3 &)>(&Entity::isInRangeToRenderDist)',
         'static_cast<bool (Entity::*)(const Vector3 &) const>(&Entity::isInRangeToRenderDist)'),
    ],
    os.path.join(ROOT, 'extract/dev/logic/Src/LuaRegister/Content/Logic/Util_Register.h'): [
        ('static_cast<bool (StructureBB::*)(const StructureBB &)>(&StructureBB::intersectsWith)',
         'static_cast<bool (StructureBB::*)(const StructureBB &) const>(&StructureBB::intersectsWith)'),
        ('static_cast<bool (StructureBB::*)(int, int, int, int)>(&StructureBB::intersectsWith)',
         'static_cast<bool (StructureBB::*)(int, int, int, int) const>(&StructureBB::intersectsWith)'),
        ('static_cast<bool (StructureBB::*)(int, int, int)>(&StructureBB::isVecInside)',
         'static_cast<bool (StructureBB::*)(int, int, int) const>(&StructureBB::isVecInside)'),
        ('static_cast<bool (StructureBB::*)(const BlockPos &)>(&StructureBB::isVecInside)',
         'static_cast<bool (StructureBB::*)(const BlockPos &) const>(&StructureBB::isVecInside)'),
    ],
}
for _cf in _CONST_OVERRIDE_FIXUPS:
    if not os.path.isfile(_cf):
        continue
    _t = open(_cf, encoding='latin-1').read()
    _o = _t
    for _a, _b in _CONST_OVERRIDE_FIXUPS[_cf]:
        if _b in _t:
            continue  # already applied
        if _a not in _t:
            raise SystemExit('const-override anchor missing in %s: %r'
                             % (os.path.relpath(_cf, ROOT), _a))
        _t = _t.replace(_a, _b)
    if _t != _o:
        open(_cf, 'w', encoding='latin-1').write(_t)
        print('patched const override casts:', os.path.relpath(_cf, ROOT))
    else:
        print('ok (already) const override casts:', os.path.relpath(_cf, ROOT))

# 3f. Listenable<int> through printf varargs is a gcc 4.9 hard error
#     ("cannot pass objects of non-trivially-copyable type"): ItemStack::
#     stackSize is a Listenable<int> (shared_ptr member -> non-trivial
#     copy). Exactly one log site in the tree passes it through '...';
#     route it through the existing int accessor getItemStackSize().
_c2s = os.path.join(SERVER, 'Network/C2SPacketHandles/C2SPlayerActionPacketHandles.cpp')
if os.path.isfile(_c2s):
    _t = open(_c2s, encoding='latin-1').read()
    _o = _t
    _t = _t.replace(
        'stack->itemID, stack->stackSize);',
        'stack->itemID, stack->getItemStackSize());')
    if _t != _o:
        open(_c2s, 'w', encoding='latin-1').write(_t)
        print('patched C2SPacketDropItemPosition dead-player log (Listenable varargs)')
    else:
        print('ok (already) C2SPlayerActionPacketHandles.cpp')

# 3g. `open = {};` on a std::priority_queue member (BedwarPathPlanner::reset)
#     is copy-list-initialization; gnustl's priority_queue(const Compare&,
#     Sequence&&) ctor is explicit, so gcc 4.9 rejects it ("converting to
#     ... from initializer list would use explicit constructor"). Assign a
#     default-constructed value instead — same semantics, era-correct.
_bpp = os.path.join(SERVER, 'Blockman/AI/BedwarPathPlanner.cpp')
if os.path.isfile(_bpp):
    _t = open(_bpp, encoding='latin-1').read()
    _o = _t
    if 'open = decltype(open)();' not in _t:
        if _t.count('open = {};') != 1:
            raise SystemExit('BedwarPathPlanner anchor drifted: %d sites for %r'
                             % (_t.count('open = {};'), 'open = {};'))
        _t = _t.replace('open = {};', 'open = decltype(open)();')
    if _t != _o:
        open(_bpp, 'w', encoding='latin-1').write(_t)
        print('patched BedwarPathPlanner::reset (explicit priority_queue ctor)')
    else:
        print('ok (already) BedwarPathPlanner.cpp')

# 3i. BinnedMalloc untracked-pointer hardening (the first on-device SIGSEGV).
#     Tombstone evidence (test-redroid #212/#213): MallocBinned::FreeInternal
#     -> FindPoolInfo returns NULL (freed pointer never registered) ->
#     `Pool->TableIndex` on a NULL Pool (the two asserts above it are compiled
#     out under APP_OPTIM=release) -> SIGSEGV SEGV_MAPERR fault-addr 0x2 at
#     ~100ms after exec, inside a static initializer (vector realloc during
#     RuntimeClass registration). The allocator internals were audited 1:1
#     against this source (hash insert/lookup constants, vtable slots, struct
#     layout all verified in the shipped .so) -- the miss is a runtime state
#     issue, so the correct era-faithful move is: never dereference a NULL
#     Pool. Log the pointer through logcat (GSALLOC tag) and LEAK it (leaking
#     is always safer than freeing a pointer whose ownership is unknown), so
#     the boot proceeds and the real mismatched-allocation path shows up in
#     the next smoke run's evidence.
_bm = os.path.join(ENGINE, 'Src/Core/Memory/BinnedMalloc.cpp')
patch(_bm, [
    ("#include \"Resource/Threading.h\"\n#include \"Memory/BinnedMalloc.h\"\n#include \"Memory/MemTracker.h\"",
     "#include \"Resource/Threading.h\"\n#include \"Memory/BinnedMalloc.h\"\n#include \"Memory/MemTracker.h\"\n\n/* GS-ONDEVICE (patch 3i): untracked-pointer diagnostics. The gameserver\n * executable links -llog, so __android_log_print resolves at final link. */\n#if defined(__ANDROID__)\n#include <android/log.h>\n#define GSALOG(...) do { __android_log_print(ANDROID_LOG_ERROR, \"GSALLOC\", __VA_ARGS__); } while (0)\n#else\n#define GSALOG(...) ((void)0)\n#endif"),
    ("            size_t BasePtr;\n            SPoolInfo* Pool = FindPoolInfo((size_t)Ptr, BasePtr);\n            assert(Pool);\n            assert(Pool->GetBytes() != 0);",
     "            size_t BasePtr;\n            SPoolInfo* Pool = FindPoolInfo((size_t)Ptr, BasePtr);\n            if (!Pool)\n            {\n                /* GS-ONDEVICE (patch 3i): pointer not tracked by this\n                 * allocator. The era release build fell through to\n                 * Pool->TableIndex on NULL here (SIGSEGV 0x2). Leak instead\n                 * of freeing (ownership unknown) and log for diagnosis. */\n                GSALOG(\"untracked-free ptr=%p (leak instead of crash)\", Ptr);\n                return;\n            }\n            assert(Pool);\n            assert(Pool->GetBytes() != 0);"),
    ("                SPoolInfo* Pool = FindPoolInfo((size_t)Ptr, BasePtr);\n\n                if( Pool->TableIndex < BinnedOSTableIndex )",
     "                SPoolInfo* Pool = FindPoolInfo((size_t)Ptr, BasePtr);\n\n                if (!Pool)\n                {\n                    /* GS-ONDEVICE (patch 3i): untracked pointer through\n                     * Realloc -- grow fresh, leak the old block (its size is\n                     * unknowable without the pool record). */\n                    GSALOG(\"untracked-realloc ptr=%p newSize=%llu\", Ptr, (unsigned long long)NewSize);\n                    return Malloc( NewSize, Alignment );\n                }\n                if( Pool->TableIndex < BinnedOSTableIndex )"),
    ("            size_t BasePtr;\n            SPoolInfo* Pool = FindPoolInfo((size_t)Original, BasePtr);\n            SizeOut = Pool->TableIndex < BinnedSizeLimit ? MemSizeToPoolTable[Pool->TableIndex]->BlockSize : Pool->GetBytes();",
     "            size_t BasePtr;\n            SPoolInfo* Pool = FindPoolInfo((size_t)Original, BasePtr);\n            if (!Pool)\n            {\n                GSALOG(\"untracked-allocsize ptr=%p\", Original);\n                SizeOut = 0;\n                return false;\n            }\n            SizeOut = Pool->TableIndex < BinnedSizeLimit ? MemSizeToPoolTable[Pool->TableIndex]->BlockSize : Pool->GetBytes();"),
])

# 3j. THE root cause of the first on-device SIGSEGV + the 15k untracked-free
#     flood (v0.6.4-gameserver redroid evidence): FindPoolInfoInternal computes
#     the page-hash key as `unsigned int` (32-bit truncation) while GetPoolInfo
#     inserts with `size_t` (64-bit). On the era's 32-bit builds size_t IS
#     32-bit so the two agree; on 64-bit Android every heap address >> 19
#     exceeds 2^32, so EVERY lookup misses (binary proof: the compiled lookup
#     ends with `and x4, x4, #0xffffffff` before the bucket-key compare).
#     Consequence chain: 100% of MallocBinned::Free calls took the NULL-Pool
#     path -> run #212/#213 SIGSEGV (pre-3i) -> now (post-3i) a total
#     leak-every-free regime (15,292 GSALLOC lines in one smoke run, ~250/sec
#     steady-state). Making the lookup key size_t restores the 1:1 insert/
#     lookup pairing. Keep Hash/PoolIndex as unsigned int (both masked < 2^13).
patch(_bm, [
    ("            unsigned int Key=Ptr>>HashKeyShift;\n            unsigned int Hash=Key&(MaxHashBuckets-1);",
     "            size_t Key=Ptr>>HashKeyShift; /* GS-ONDEVICE (patch 3j): was\n            unsigned int -- 32-bit truncation made every lookup miss on\n            64-bit address spaces (GetPoolInfo inserts a size_t key). */\n            unsigned int Hash=Key&(MaxHashBuckets-1);"),
])

# 3h. Windows-style backslash separators inside quoted includes
#     (Log.cpp: #include "Util\UThread.h", FileResourceManager.cpp:
#     #include "Util\ChecksumUtil.h") are fatal on Linux ("No such file
#     or directory" — gcc keeps the backslash as a literal filename char).
#     These LordCore TUs were never reached by CI before (every earlier
#     run died in the gameserver module first). Normalize the separators
#     across the WHOLE assembled tree — forward slashes work everywhere.
import re as _re
_fixed_bs = 0
for _base in (os.path.join(ROOT, 'extract'),):
    for _dirpath, _dirnames, _filenames in os.walk(_base):
        for _fn in _filenames:
            if not _fn.endswith(('.cpp', '.h', '.hpp', '.c', '.cc')):
                continue
            _p = os.path.join(_dirpath, _fn)
            try:
                with open(_p, encoding='latin-1') as f:
                    _t = f.read()
            except OSError:
                continue
            if '\\' not in _t or '#include' not in _t:
                continue
            _t2 = _re.sub(r'(#\s*include\s*")([^"\n]*\\[^"\n]*)(")',
                          lambda m: m.group(1) + m.group(2).replace('\\', '/')
                          + m.group(3), _t)
            if _t2 != _t:
                with open(_p, 'w', encoding='latin-1') as f:
                    f.write(_t2)
                _fixed_bs += 1
                print('patched backslash include:',
                      os.path.relpath(_p, ROOT))
print('backslash-include pass: %d files fixed' % _fixed_bs)

# 4. ClientPeer varargs UB (LORD::String -> const char*)
peer = os.path.join(SERVER, 'Network/ClientPeer.cpp')
with open(peer, encoding='latin-1') as f:
    s = f.read()
fixed = s.replace('getRakssid(), getName(), hasLogon()',
                  'getRakssid(), getName().c_str(), hasLogon()')
if fixed != s:
    with open(peer, 'w', encoding='latin-1') as f:
        f.write(fixed)
    print('patched dev/server/src/Network/ClientPeer.cpp (varargs)')
else:
    print('ok (already) dev/server/src/Network/ClientPeer.cpp')



# ---------------------------------------------------------------------------
# 5. ENGINE-10078 session protocol (the 2.8.2-client GameServer update).
#
#    The 10078 engine_server WebService.lua NO LONGER passes a Lua callback
#    into HttpRequest.asyncGet/asyncPost/asyncPut/asyncDelete; it caches the
#    request under a numeric session (RequestCache) and passes the session
#    id, expecting the engine to dispatch the response to the GLOBAL
#    onHttpResponse(session, result). The 10068 scripts still pass functions.
#    The bound std::function parameter in FunctionalTranslate therefore
#    becomes dual-protocol:
#      LUA_TFUNCTION -> legacy LuaRef callback (10068, byte-identical path);
#      LUA_TNUMBER   -> session protocol (dispatch global onHttpResponse);
#      anything else -> no-op (previously "attempt to call a nil value").
#    One binary then serves BOTH script bundles. Runtime-proven against the
#    REAL decompiled WebService.lua of both versions (session protocol +
#    legacy + error-degradation + stack balance; see the session worklog).
#    Also ships the ConnectorManager compat stub the 10078
#    engine_server/connector/ConnectorCenter.lua resolves when the holder
#    answers the connector-cluster endpoint; inert on the local server
#    (createConnect logs + no-ops, getConnectorClient returns NULL -> Lua nil).
_PT = os.path.join(ROOT, 'extract/dev/logic/Src/LuaRegister/Template/ParamTranslate/ParamTranslate.h')
_PT_OLD = 'namespace FunctionalTranslate\r\n{\r\n\tstruct FuncionalProxy\r\n\t{\r\n\t\tLuaRef _ref;\r\n\t\tlua_State *L;\r\n\r\n\t\tvoid invoke() const\r\n\t\t{\r\n\t\t\t_ref.Push(L);\r\n\t\t}\r\n\t};\r\n\r\n\ttemplate<typename T>\r\n\tstruct innerRead\r\n\t{\r\n\t\tstatic T invoke(lua_State*L, int index)\r\n\t\t{\r\n\r\n\t\t}\r\n\t};\r\n\r\n\r\n\ttemplate<typename RVal, typename ...Args>\r\n\tstruct innerRead<std::function<RVal(Args...)>>\r\n\t{\r\n\t\tstatic std::function<RVal(Args...)> invoke(lua_State *L, int index)\r\n\t\t{\r\n\t\t\tlua_pushvalue(L, index);\r\n\t\t\tFuncionalProxy ref = FuncionalProxy{ { L, luaL_ref(L, LUA_REGISTRYINDEX) }, L };\r\n\r\n\t\t\tauto rt = [ref](Args... args)\r\n\t\t\t{\r\n\t\t\t\tlua_rawgeti(ref.L, LUA_REGISTRYINDEX, -2);\t// debug.traceback\r\n\t\t\t\tint errfunc = lua_gettop(ref.L);\r\n\t\t\t\tref.invoke();\r\n\t\t\t\twrite_n<Args...>(ref.L, std::forward<Args>(args)...);\r\n\t\t\t\tif (lua_pcall(ref.L, sizeof...(Args), 1, errfunc))\r\n\t\t\t\t\tLuaDebug::printError(ref.L, "%s", lua_tostring(ref.L, -1));\r\n\r\n\t\t\t\tlua_remove(ref.L, errfunc);\r\n\r\n\t\t\t\treturn ParamTranslate::pop<RVal>(ref.L);\r\n\t\t\t};\r\n\r\n\t\t\treturn rt;\r\n\t\t}\r\n\t};'.replace('\r\n', '\n')
_PT_NEW = 'namespace FunctionalTranslate\r\n{\r\n\tstruct FuncionalProxy\r\n\t{\r\n\t\tLuaRef _ref;\r\n\t\tlua_State *L;\r\n\r\n\t\tvoid invoke() const\r\n\t\t{\r\n\t\t\t_ref.Push(L);\r\n\t\t}\r\n\t};\r\n\r\n\t// default-construct an RVal without tripping the void-return rule\r\n\ttemplate<typename RVal>\r\n\tstruct DefaultReturn\r\n\t{\r\n\t\tstatic RVal value() { return RVal(); }\r\n\t};\r\n\r\n\ttemplate<>\r\n\tstruct DefaultReturn<void>\r\n\t{\r\n\t\tstatic void value() {}\r\n\t};\r\n\r\n\t// ENGINE-10078 session protocol: write ONLY the first argument\r\n\t// (onHttpResponse(session, result) receives the raw response payload;\r\n\t// any further callback args, e.g. the http status code, are discarded)\r\n\tinline void write_first(lua_State *L)\r\n\t{\r\n\t\t(void)L;\r\n\t}\r\n\r\n\ttemplate<typename T, typename ...Rest>\r\n\tstatic void write_first(lua_State *L, T&& a, Rest&&... rest)\r\n\t{\r\n\t\t(void)sizeof...(rest);\r\n\t\tParamTranslate::write(L, std::forward<T>(a));\r\n\t}\r\n\r\n\ttemplate<typename T>\r\n\tstruct innerRead\r\n\t{\r\n\t\tstatic T invoke(lua_State*L, int index)\r\n\t\t{\r\n\r\n\t\t}\r\n\t};\r\n\r\n\r\n\ttemplate<typename RVal, typename ...Args>\r\n\tstruct innerRead<std::function<RVal(Args...)>>\r\n\t{\r\n\t\tstatic std::function<RVal(Args...)> invoke(lua_State *L, int index)\r\n\t\t{\r\n\t\t\t// ENGINE-10078: the 10078 WebService.lua no longer passes a Lua callback\r\n\t\t\t// function; it caches the request under a numeric session and passes\r\n\t\t\t// HttpRequest.asyncGet(url, params, session). The engine must then dispatch\r\n\t\t\t// the response to the GLOBAL onHttpResponse(session, result). Keep the 10068\r\n\t\t\t// function-callback protocol untouched and add the session protocol here, so\r\n\t\t\t// ONE binary serves both script bundles.\r\n\t\t\tint valueType = lua_type(L, index);\r\n\t\t\tif (valueType == LUA_TNUMBER)\r\n\t\t\t{\r\n\t\t\t\tlua_Number session = lua_tonumber(L, index);\r\n\r\n\t\t\t\tauto rt = [session, L](Args... args)\r\n\t\t\t\t{\r\n\t\t\t\t\tlua_rawgeti(L, LUA_REGISTRYINDEX, -2);\t// debug.traceback\r\n\t\t\t\t\tint errfunc = lua_gettop(L);\r\n\t\t\t\t\tlua_getglobal(L, "onHttpResponse");\r\n\t\t\t\t\tif (lua_isfunction(L, -1))\r\n\t\t\t\t\t{\r\n\t\t\t\t\t\tlua_pushnumber(L, session);\t\t\t\t// arg 1: session id\r\n\t\t\t\t\t\twrite_first(L, std::forward<Args>(args)...);\t// arg 2: raw result\r\n\t\t\t\t\t\tif (lua_pcall(L, (sizeof...(Args) > 0) ? 2 : 1, 1, errfunc))\r\n\t\t\t\t\t\t\tLuaDebug::printError(L, "%s", lua_tostring(L, -1));\r\n\t\t\t\t\t}\r\n\t\t\t\t\telse\r\n\t\t\t\t\t{\r\n\t\t\t\t\t\tLuaDebug::printError(L, "[10078] global onHttpResponse missing, session response dropped (session=%.0f)", session);\r\n\t\t\t\t\t}\r\n\r\n\t\t\t\t\tlua_remove(L, errfunc);\r\n\r\n\t\t\t\t\treturn ParamTranslate::pop<RVal>(L);\r\n\t\t\t\t};\r\n\r\n\t\t\t\treturn rt;\r\n\t\t\t}\r\n\r\n\t\t\tif (valueType != LUA_TFUNCTION)\r\n\t\t\t{\r\n\t\t\t\t// nil/table/... : a no-op handler; the old path would raise\r\n\t\t\t\t// "attempt to call a nil value" on every response instead.\r\n\t\t\t\treturn [](Args... args) -> RVal\r\n\t\t\t\t{\r\n\t\t\t\t\t(void)sizeof...(args);\r\n\t\t\t\t\treturn DefaultReturn<RVal>::value();\r\n\t\t\t\t};\r\n\t\t\t}\r\n\r\n\t\t\tlua_pushvalue(L, index);\r\n\t\t\tFuncionalProxy ref = FuncionalProxy{ { L, luaL_ref(L, LUA_REGISTRYINDEX) }, L };\r\n\r\n\t\t\tauto rt = [ref](Args... args)\r\n\t\t\t{\r\n\t\t\t\tlua_rawgeti(ref.L, LUA_REGISTRYINDEX, -2);\t// debug.traceback\r\n\t\t\t\tint errfunc = lua_gettop(ref.L);\r\n\t\t\t\tref.invoke();\r\n\t\t\t\twrite_n<Args...>(ref.L, std::forward<Args>(args)...);\r\n\t\t\t\tif (lua_pcall(ref.L, sizeof...(Args), 1, errfunc))\r\n\t\t\t\t\tLuaDebug::printError(ref.L, "%s", lua_tostring(ref.L, -1));\r\n\r\n\t\t\t\tlua_remove(ref.L, errfunc);\r\n\r\n\t\t\t\treturn ParamTranslate::pop<RVal>(ref.L);\r\n\t\t\t};\r\n\r\n\t\t\treturn rt;\r\n\t\t}\r\n\t};'.replace('\r\n', '\n')  # patch() reads text-mode: universal newlines
patch(_PT, [(_PT_OLD, _PT_NEW)])

def _write_new(path, content, marker):
    if os.path.isfile(path):
        with open(path, encoding='latin-1') as f:
            cur = f.read()
        if marker in cur:
            print('ok (already)', os.path.relpath(path, ROOT))
        else:
            raise SystemExit('unexpected existing file without marker: %s' % path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='latin-1') as f:
        f.write(content)
    print('wrote', os.path.relpath(path, ROOT))

_CM_H = '#pragma once\n\n#include "Core.h"\n\nusing namespace LORD;\n\nnamespace BLOCKMAN\n{\n        // inert placeholder: never instantiated on the local server; the Lua side\n        // must only ever see nil (ConnectorCenter.lua guards `if not ConnectorClient\n        // then return end` on every call site). Defined complete so the Lua binder\n        // can instantiate its pointer proxy without a forward-declaration hazard.\n        class ConnectorClient { };\n\n        // ENGINE-10078 compat (local single-server deployment).\n        //\n        // The 10078 script tree (engine_server/connector/ConnectorCenter.lua) resolves\n        // the global ConnectorManager when the holder answers the connector-cluster\n        // endpoint (/game/api/v1/inner/region/connector-cluster/{regionCode}/{gameId})\n        // with { addr = "host:port" }. The official region/connector cluster has no\n        // local-server counterpart, so this compat class registers an INERT manager:\n        //\n        //   - createConnect(host, port) logs and drops the link request;\n        //   - getConnectorClient() returns NULL -> the binder pushes nil (CPPDataToLua\n        //     pushes nil for null pointers) and every ConnectorCenter call site guards\n        //     `if not ConnectorClient then return end`, so the whole connector feature\n        //     degrades to a no-op without touching the disp-cluster join flow.\n        //\n        // The manager is lazily self-hosting (function-local static Instance) so Lua\n        // can call ConnectorManager.Instance() at any time after script boot.\n        class ConnectorManager\n        {\n        public:\n                static ConnectorManager* Instance();\n\n                ConnectorManager();\n                ~ConnectorManager();\n\n                void createConnect(const String& host, int port);\n                ConnectorClient* getConnectorClient();\n\n        private:\n                bool m_connected;\n        };\n}\n'
_CM_C = '#include "Network/ConnectorManager.h"\n#include "Log/Log.h"\n#include "LuaRegister/Template/LuaRegister.h"\n\nusing namespace LORD;\nusing namespace BLOCKMAN;\nusing namespace LUA_REGISTER;\n\nnamespace BLOCKMAN\n{\n\tConnectorManager* ConnectorManager::Instance()\n\t{\n\t\tstatic ConnectorManager s_instance;\n\t\treturn &s_instance;\n\t}\n\n\tConnectorManager::ConnectorManager()\n\t\t: m_connected(false)\n\t{\n\t}\n\n\tConnectorManager::~ConnectorManager()\n\t{\n\t}\n\n\tvoid ConnectorManager::createConnect(const String& host, int port)\n\t{\n\t\t// the local deployment has no connector cluster: log and drop the link\n\t\tLordLogInfo("[ConnectorManager-compat] createConnect(%s:%d) ignored - local single-server mode, connector cluster disabled",\n\t\t\thost.c_str(), port);\n\t\tm_connected = false;\n\t}\n\n\tConnectorClient* ConnectorManager::getConnectorClient()\n\t{\n\t\t// NULL -> Lua nil -> ConnectorCenter.lua guards `if not ConnectorClient`\n\t\treturn NULL;\n\t}\n}\n\n// ENGINE-10078: the 10078 engine_server scripts call ConnectorManager.Instance()\n// from ConnectorCenter.lua. Register the class so the global resolves on the\n// 10068 binary as well (the 10078 libgameserver has its own real manager).\n_BEGIN_REGISTER_CLASS(ConnectorManager)\n_CLASSREGISTER_AddStaticMember(Instance, ConnectorManager::Instance)\n_CLASSREGISTER_AddMember(createConnect, ConnectorManager::createConnect)\n_CLASSREGISTER_AddMember(getConnectorClient, ConnectorManager::getConnectorClient)\n_END_REGISTER_CLASS()\n'
_write_new(os.path.join(SERVER, 'Network/ConnectorManager.h'), _CM_H, 'ENGINE-10078')
_write_new(os.path.join(SERVER, 'Network/ConnectorManager.cpp'), _CM_C, 'ENGINE-10078')

# ---------------------------------------------------------------------------
# 6. RUN-25 DECODE (38542201687): the send-buffer coalescing took the login
#    chain DOWN with one bad parse.
#
#    The 2.8.2 client threw "packet decode error: Failed to read Integer:
#    integer overflow" on the FIRST post-accept datagram of the g1048
#    (Skyblock) join. That datagram was a COALESCED BATCH (RaknetSession
#    glues up to MAX_MESSAGE_SIZE bytes per channel between flush ticks):
#    [S2CPacketUserAttr 0x44][S2CPacketSyncWorldTime 0x34][the Lua-common
#    ServerInfo blob 0x50 ...] — byte-perfect per OUR schema, but the
#    client's parse desynced (the same desync that logs the tolerated
#    "unknown packet id: 0" in EVERY boot — run 24 Bedwars/Skyblock +
#    run 25 Bedwars all recovered from it) and the hard variant DROPPED
#    THE WHOLE DATAGRAM — with S2CPacketLoginResult + S2CPacketUserIn
#    glued BEHIND the desync point. The client never logged login
#    succ / userIn / the spawn teleport, kept a null local-player state,
#    and MainTickThread SIGSEGV'd ~3 s in (tombstone_00, fault addr 0x4).
#    Run 24's identical server code survived because the same desync
#    landed on a 0x00 byte and the login packets rode SEPARATE datagrams.
#
#    THE FIX: one application packet per datagram. flush(channel) right
#    after the buffered write — a client parse failure can then cost at
#    most THAT packet, never the login chain queued behind it. The
#    batching is a WAN optimization; this server runs on loopback where
#    per-packet sends are free. RakNet reliability is untouched (same
#    channel/priority/reliability flags; flush() is the existing path).
_RK = os.path.join(ROOT, 'extract/dev/logic/Src/Network/RaknetSession.h')
patch(_RK, [
    ("\t\tbuffer.Write(serializedData);\n"
     "\t\treturn dataSize;",
     "\t\tbuffer.Write(serializedData);\n"
     "\t\t// RUN-25 DECODE: flush per packet - the client's parser drops the\n"
     "\t\t// WHOLE datagram on a decode error, so coalescing let one desync\n"
     "\t\t// take the glued login chain (LoginResult/UserIn) down with it.\n"
     "\t\t// One packet per datagram bounds the damage to that packet only.\n"
     "\t\tflush(channel);\n"
     "\t\treturn dataSize;"),
])

# ---------------------------------------------------------------------------
# 7. RUN-26 DECODE (38551343606): S2CPacketGameInfo's m_coinMapping TAIL is
#    a 10078-client schema drift - the client reads the count byte as the
#    next packet id.
#
#    BYTE-PROVEN TWICE. Our 1.24.4-era S2CPacketGameInfo appends
#    m_coinMapping (vector<CoinMapping>) after m_selectableActions; the
#    2.8.2 (engine 10078) client's GameInfo schema ENDS at
#    m_selectableActions, so its parser reads OUR coinMapping count byte
#    as the next packet's id:
#      - the g1046 hall (CoinManager empty, count 0x00) -> the tolerated
#        "unknown packet id: 0" logged in EVERY boot (runs 24/25/26);
#      - the g1048 Skyblock room (the coin economy room, 16 coins) ->
#        "unknown packet id: 16" (run 26's client.log line 127).
#    The GameInfo fields the client knows all parse fine (the field is
#    LAST), but the framing error means the 10078 client can never read
#    a clean GameInfo datagram - and the SAME drift class on other
#    packets costs real tail content. Strip the tail for 10078 clients:
#    the login packet carries m_engineVersion, so the send site gates the
#    new includeCoinMapping parameter (pre-10078 clients keep the field;
#    their schema still has it).
_SH_H = os.path.join(ROOT, 'extract/dev/server/src/Network/ServerPacketSender.h')
patch(_SH_H, [
    ("\t\tString gameType, int32_t defaultIdle, vector<i32>::type selectableActions, i32 vip);",
     "\t\tString gameType, int32_t defaultIdle, vector<i32>::type selectableActions, i32 vip, bool includeCoinMapping = true);"),
])

_SH_C = os.path.join(ROOT, 'extract/dev/server/src/Network/ServerPacketSender1.cpp')
patch(_SH_C, [
    ("void ServerPacketSender::sendGameInfo(ui64 rakssid, int runtimeID, const Vector3i& spawnPos, \n"
     "\tconst vector<String>::type& recipes, bool isTimeStopped, int32_t sex, String gameType, int32_t defaultIdle, vector<i32>::type selectableActions, i32 vip)\n"
     "{",
     "void ServerPacketSender::sendGameInfo(ui64 rakssid, int runtimeID, const Vector3i& spawnPos, \n"
     "\tconst vector<String>::type& recipes, bool isTimeStopped, int32_t sex, String gameType, int32_t defaultIdle, vector<i32>::type selectableActions, i32 vip, bool includeCoinMapping)\n"
     "{"),
    ("\tLORD::map<int, int>::type coinMapping = CoinManager::Instance()->m_coinMapping;\n"
     "\tfor (LORD::map<int, int>::type::iterator it = coinMapping.begin(); it != coinMapping.end(); ++it)\n"
     "\t{\n"
     "\t\tpacket->m_coinMapping.push_back({ it->first, it->second });\n"
     "\t}",
     "\t// RUN-26 DECODE: the 10078 client's GameInfo schema has NO\n"
     "\t// m_coinMapping - it reads our count byte as the next packet id\n"
     "\t// (\"unknown packet id: 0/16\"). Skip the tail for those clients.\n"
     "\tif (includeCoinMapping)\n"
     "\t{\n"
     "\t\tLORD::map<int, int>::type coinMapping = CoinManager::Instance()->m_coinMapping;\n"
     "\t\tfor (LORD::map<int, int>::type::iterator it = coinMapping.begin(); it != coinMapping.end(); ++it)\n"
     "\t\t{\n"
     "\t\t\tpacket->m_coinMapping.push_back({ it->first, it->second });\n"
     "\t\t}\n"
     "\t}"),
])

_CI = os.path.join(ROOT, 'extract/dev/server/src/Network/C2SPacketHandles/C2SInitPacketHandles.cpp')
patch(_CI, [
    ("\t\tsender->sendGameInfo(clientPeer->getRakssid(), pPlayer->entityId, adjustPos,\n"
     "\t\t\tCraftingManager::Instance()->getRecipeNameList(), pworld->getWorldInfo().isTimeStopped(), pPlayer->m_sex, Server::Instance()->getGameType(), pPlayer->m_defaultIdle, attrInfo.unlockedSelectableActions, pPlayer->m_vip);",
     "\t\tsender->sendGameInfo(clientPeer->getRakssid(), pPlayer->entityId, adjustPos,\n"
     "\t\t\tCraftingManager::Instance()->getRecipeNameList(), pworld->getWorldInfo().isTimeStopped(), pPlayer->m_sex, Server::Instance()->getGameType(), pPlayer->m_defaultIdle, attrInfo.unlockedSelectableActions, pPlayer->m_vip,\n"
     "\t\t\t// RUN-26 DECODE: the 10078 client ends GameInfo at\n"
     "\t\t\t// selectableActions - our coinMapping tail reads as a bogus\n"
     "\t\t\t// packet id (0 for the hall, 16 for Skyblock). Pre-10078\n"
     "\t\t\t// clients keep the field.\n"
     "\t\t\tpacket->m_engineVersion < 10078);"),
])

print('all patches applied')
