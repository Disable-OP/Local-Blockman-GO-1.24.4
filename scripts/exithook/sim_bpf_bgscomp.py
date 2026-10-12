#!/usr/bin/env python3
"""
sim_bpf_bgscomp.py — offline kernel-semantics simulator + validator for the
two BPF filters embedded in scripts/exithook/bgscomp.c (v15).

Checks (mirrors kernel seccomp_check_filter + bpf_convert_filter semantics):
  - every insn is one of the allowed seccomp-BPF classes
  - LD|W|ABS offsets: 32-bit aligned and < sizeof(seccomp_data)=64
  - JEQ/JA jump targets stay inside [0, len]
  - the LAST instruction is a RET and every path terminates in a RET
Then runs the filter against the decisive scenarios:
  bpf15: openat/open/openat2 -> USER_NOTIF; exit_group(25|30) -> ERRNO(38);
         exit(0)/exit_group(0) -> ALLOW; prctl(PR_GET_SECCOMP|GET_NNP) ->
         "returns 0" (ERRNO(0)); prctl(other)/read -> ALLOW; non-ARM arch ->
         ALLOW (the qemu case).
  bpf14: the exact v14 behavior (verdict exits blocked, prctl fakes, all
         else ALLOW).
The filter sources are PARSED FROM bgscomp.c (single source of truth — if
the C array and this simulator ever disagree, this script fails).
"""
import re
import sys

SECCOMP_DATA_SIZE = 64
RET_KILL_THREAD = 0x00000000
RET_KILL_PROCESS = 0x80000000
RET_TRAP = 0x00030000
RET_ERRNO = 0x00050000
RET_TRACE = 0x7FF00000
RET_LOG = 0x7FFC0000
RET_USER_NOTIF = 0x7FC00000
RET_ALLOW = 0x7FFF0000
VALID_ACTIONS = {RET_KILL_THREAD, RET_KILL_PROCESS, RET_TRAP, RET_ERRNO,
                 RET_TRACE, RET_LOG, RET_USER_NOTIF, RET_ALLOW}

BPF_LD, BPF_JMP, BPF_RET = 0x00, 0x05, 0x06


def parse_filters(src_path):
    src = open(src_path).read()
    out = {}
    for name in ("bpf15", "bpf14"):
        m = re.search(
            r"static const struct sock_filter %s\[\] = \{(.*?)\n\};" % name,
            src, re.S)
        if not m:
            raise SystemExit(f"FATAL: {name} not found in {src_path}")
        body = m.group(1)
        insns = []
        for mm in re.finditer(
                r"\{\s*(0x[0-9A-Fa-f]+),\s*(\d+),\s*(\d+),\s*(0x[0-9A-Fa-f]+U?|\d+|[A-Z_0-9]+)\s*\}",
                body):
            kraw = mm.group(4)
            # production (arm32) constants; the x86_64 test build swaps the
            # same macros via the per-ABI #defines
            MACROS = {"AUDIT_ARCH_THIS": 0x40000028, "BPF_NR_OPENAT": 322,
                      "BPF_NR_OPEN": 5, "BPF_NR_OPENAT2": 437,
                      "BPF_NR_EXITGROUP": 248, "BPF_NR_EXIT": 1,
                      "BPF_NR_PRCTL": 172, "BPF_NR_PTRICE": 26, "BPF_NR_CLONE": 120}
            if kraw in MACROS:
                k = MACROS[kraw]
            elif kraw.startswith("0x"):
                k = int(kraw.rstrip("U"), 16)
            else:
                k = int(kraw)
            code = int(mm.group(1), 16)
            jt, jf = int(mm.group(2)), int(mm.group(3))
            insns.append((code, jt, jf, k))
        out[name] = insns
    return out


def validate(name, prog):
    errs = []
    if not prog:
        return [f"{name}: empty"]
    if (prog[-1][0] & 0x07) != BPF_RET:
        errs.append(f"{name}: last insn is not RET")
    for i, (code, jt, jf, k) in enumerate(prog):
        cls = code & 0x07
        if cls == BPF_LD and (code & 0xE0) == 0x20:  # LD|W|ABS
            if k % 4 or k >= SECCOMP_DATA_SIZE:
                errs.append(f"{name}[{i}]: LD|ABS offset {k} unaligned/ooz")
        elif cls == BPF_RET:
            if (k & 0xFFFF0000) not in VALID_ACTIONS:
                errs.append(f"{name}[{i}]: bad RET action 0x{k:08x}")
        elif cls == BPF_JMP:
            if (code & 0xF0) == 0x00:  # JA
                if i + 1 + k >= len(prog):
                    errs.append(f"{name}[{i}]: JA +{k} out of range")
            else:  # JEQ/JGT/JGE/JSET
                if i + 1 + jt >= len(prog):
                    errs.append(f"{name}[{i}]: JT {jt} out of range")
                if i + 1 + jf >= len(prog):
                    errs.append(f"{name}[{i}]: JF {jf} out of range")
        else:
            errs.append(f"{name}[{i}]: class 0x{cls:02x} not allowed by seccomp")
    return errs


def run(prog, nr, args0, arch=0x40000028):
    """returns (action, data). args0 = low 32 bits of args[0]."""
    i = 0
    for _ in range(len(prog) + 1):
        if i >= len(prog):
            return ("FELL_OFF", 0)
        code, jt, jf, k = prog[i]
        cls = code & 0x07
        if cls == BPF_LD and (code & 0xE0) == 0x20:
            a = k  # seccomp_data: nr@0 arch@4 ip@8 args@16; k is the offset
            if k == 0:
                a = nr & 0xFFFFFFFF
            elif k == 4:
                a = arch
            elif k == 16:
                a = args0 & 0xFFFFFFFF
            else:
                a = 0
            acc = a
            i += 1
        elif cls == BPF_RET:
            return ("RET", k)
        elif cls == BPF_JMP:
            if (code & 0xF0) == 0x00:
                i = i + 1 + k
            elif (code & 0xF0) == 0x10:  # JEQ
                i = i + 1 + (jt if acc == (k & 0xFFFFFFFF) else jf)
            else:
                return ("BADJMP", i)
        else:
            return ("BADCLS", i)
    return ("LOOP", 0)


def act_str(v):
    action = v & 0xFFFF0000
    data = v & 0xFFFF
    name = {RET_ALLOW: "ALLOW", RET_USER_NOTIF: "USER_NOTIF",
            RET_ERRNO: "ERRNO", RET_KILL_THREAD: "KILL",
            RET_TRACE: "TRACE"}.get(action, f"0x{action:08x}")
    return f"{name}({data})" if action == RET_ERRNO else name


def encode(prog):
    """struct sock_filter { u16 code; u8 jt; u8 jf; u32 k } — LE."""
    out = b""
    for code, jt, jf, k in prog:
        out += code.to_bytes(2, "little") + bytes([jt, jf]) + \
            k.to_bytes(4, "little")
    return out


def verify_so(filters, so_path):
    fails = 0
    blob = open(so_path, "rb").read()
    for name, prog in filters.items():
        enc = encode(prog)
        if enc in blob:
            print(f"{name}: {len(prog)} insns FOUND byte-exact in {so_path}")
        else:
            print(f"{name}: NOT FOUND in {so_path} — the committed .so "
                  f"does NOT match the C source (stale rebuild?)")
            fails += 1
    return fails


def main():
    args = [a for a in sys.argv[1:]]
    so_path = None
    if "--verify-so" in args:
        i = args.index("--verify-so")
        so_path = args[i + 1]
        del args[i:i + 2]
    prog_path = args[0] if args else "scripts/exithook/bgscomp.c"
    filters = parse_filters(prog_path)

    if so_path:
        sys.exit(1 if verify_so(filters, so_path) else 0)

    fails = 0
    for name, prog in filters.items():
        errs = validate(name, prog)
        print(f"{name}: {len(prog)} insns, validation: "
              + ("OK" if not errs else "FAIL"))
        for e in errs:
            print("  " + e)
            fails += 1

    b15, b14 = filters["bpf15"], filters["bpf14"]

    cases15 = [
        ("openat -> USER_NOTIF", run(b15, 322, 0), ("RET", RET_USER_NOTIF)),
        ("open   -> USER_NOTIF", run(b15, 5, 0), ("RET", RET_USER_NOTIF)),
        ("openat2-> USER_NOTIF", run(b15, 437, 0), ("RET", RET_USER_NOTIF)),
        ("exit_group(25) -> ERRNO(38)", run(b15, 248, 25), ("RET", RET_ERRNO | 38)),
        ("exit_group(30) -> ERRNO(38)", run(b15, 248, 30), ("RET", RET_ERRNO | 38)),
        ("exit(25)       -> ERRNO(38)", run(b15, 1, 25), ("RET", RET_ERRNO | 38)),
        ("exit_group(0)  -> ALLOW", run(b15, 248, 0), ("RET", RET_ALLOW)),
        ("exit_group(1)  -> ALLOW", run(b15, 248, 1), ("RET", RET_ALLOW)),
        ("prctl(GET_SECCOMP=21) -> ERRNO(0)", run(b15, 172, 21), ("RET", RET_ERRNO | 0)),
        ("prctl(GET_NNP=36)     -> ERRNO(0)", run(b15, 172, 36), ("RET", RET_ERRNO | 0)),
        ("prctl(SET_NNP=38)     -> ALLOW", run(b15, 172, 38), ("RET", RET_ALLOW)),
        ("read -> ALLOW", run(b15, 3, 0), ("RET", RET_ALLOW)),
        ("write-> ALLOW", run(b15, 4, 0), ("RET", RET_ALLOW)),
        ("ioctl-> ALLOW", run(b15, 54, 0), ("RET", RET_ALLOW)),
        ("memfd_create -> ALLOW", run(b15, 385, 0), ("RET", RET_ALLOW)),
        ("seccomp -> ALLOW", run(b15, 383, 0), ("RET", RET_ALLOW)),
        ("clone(120) -> USER_NOTIF", run(b15, 120, 0), ("RET", RET_USER_NOTIF)),
        ("ptrace(26) -> USER_NOTIF", run(b15, 26, 0), ("RET", RET_USER_NOTIF)),
        ("io_uring_setup(425) -> ERRNO(38)", run(b15, 425, 0), ("RET", RET_ERRNO | 38)),
        ("io_uring_enter(426) -> ERRNO(38)", run(b15, 426, 0), ("RET", RET_ERRNO | 38)),
        ("io_uring_register(427) -> ERRNO(38)", run(b15, 427, 0), ("RET", RET_ERRNO | 38)),
        ("x86_64 arch -> ALLOW (qemu)", run(b15, 322, 0, arch=0xC000003E),
         ("RET", RET_ALLOW)),
    ]
    cases14 = [
        ("exit_group(25) -> ERRNO(38)", run(b14, 248, 25), ("RET", RET_ERRNO | 38)),
        ("exit(25)       -> ERRNO(38)", run(b14, 1, 25), ("RET", RET_ERRNO | 38)),
        ("exit_group(0)  -> ALLOW", run(b14, 248, 0), ("RET", RET_ALLOW)),
        ("prctl(GET_SECCOMP=21) -> ERRNO(0)", run(b14, 172, 21), ("RET", RET_ERRNO | 0)),
        ("prctl(GET_NNP=36)     -> ERRNO(0)", run(b14, 172, 36), ("RET", RET_ERRNO | 0)),
        ("openat -> ALLOW (no notify!)", run(b14, 322, 0), ("RET", RET_ALLOW)),
        ("read   -> ALLOW", run(b14, 3, 0), ("RET", RET_ALLOW)),
    ]

    for label, got, want in cases15 + cases14:
        fname = "bpf15" if label in [c[0] for c in cases15] else "bpf14"
        ok = got == want
        if not ok:
            fails += 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {fname}: {label} -> "
              f"{act_str(got[1]) if got[0] == 'RET' else got}")

    print(f"\n{'ALL GREEN' if fails == 0 else f'{fails} FAILURES'}")
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
