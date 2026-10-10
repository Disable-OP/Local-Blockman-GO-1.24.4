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
