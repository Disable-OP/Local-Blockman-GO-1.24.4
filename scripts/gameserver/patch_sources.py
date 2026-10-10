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

print('all patches applied')
