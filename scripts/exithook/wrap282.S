/*
 * wrap282.S — the aarch64 exithook wrapper for the 2.8.2 client's engine
 * processes (the wrap.com.sandboxol.blockymods property value).
 *
 * THE PROBLEM: libBlockMan.so (engine 10078) embeds the Tencent TSS
 * native (packed, zero dynamic imports, libtersafe2, tp2_x, g_tprt_y symbols).
 * On a re-signed APK the embedded verdict fires during engine init and
 * the process exits CLEANLY with code 25 (the engine process dies ~5s
 * after BlockManEchoesActivity starts; the main process's JAVA-side
 * TSS was already stubbed by patch_antitp_282 — exit code 30 there).
 *
 * THE FIX: install a seccomp-BPF filter BEFORE exec'ing the real
 * app_process: exit/exit_group with code 25 or 30 return
 * SECCOMP_RET_ERRNO(ENOSYS) instead of terminating — the verdict
 * becomes a no-op and the engine keeps running. Every other exit code
 * and every other syscall passes through unchanged. BOTH syscall-arch
 * nr sets are matched: arm64 (exit=93, exit_group=94 — the wrapper
 * itself) and arm32 (exit=1, exit_group=248 — every app process:
 * the 2.8.2 APK is armeabi-v7a ONLY, so the engine is 32-bit).
 *
 * AMS launches:  <this binary> /system/bin/app_process64 <app args...>
 * (the wrap.<pkg> property value; honored on ro.debuggable builds —
 * redroid is one). Raw syscalls only, no libc: prctl(167),
 * seccomp(277), execve(221), exit_group(94) — aarch64 numbers.
 *
 * Assemble:  aarch64-linux-gnu-as -o wrap282.o wrap282.S
 *            aarch64-linux-gnu-ld -o wrap282 wrap282.o
 */
    .arch armv8-a
    .text
    .global _start

    .equ SYS_EXECVE,     221
    .equ SYS_EXIT_GROUP,  94
    .equ SYS_PRCTL,      167
    .equ SYS_SECCOMP,    277
    .equ PR_SET_NO_NEW_PRIVS, 38
    .equ SECCOMP_SET_MODE_FILTER, 1
    .equ ENOSYS, 38

.balign 4
_start:
    mov     x29, sp                     /* x29 = original stack */

    /* --- 1. prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0); fail=21 --- */
    mov     x8, #SYS_PRCTL
    mov     x0, #PR_SET_NO_NEW_PRIVS
    mov     x1, #1
    mov     x2, #0
    mov     x3, #0
    mov     x4, #0
    svc     #0
    cbnz    x0, fail21

    /* --- 2. seccomp(SECCOMP_SET_MODE_FILTER, 0, &fprog); fail=22 ---
       aarch64 ABI: args in x0..x5 — x0=op, x1=flags, x2=&fprog, nr in x8.
       v5 fix: the registers were shuffled (x0=&fprog, x1=op, x2=0) so the
       kernel saw op=huge-pointer -> do_seccomp default -> -EINVAL ALWAYS
       (run 38172868682 exit 42), independent of the filter contents. */
    adr     x2, bpf
    sub     sp, sp, #32
    mov     w3, #11
    str     w3, [sp]                    /* fprog.len = 11           */
    str     x2, [sp, #8]                /* fprog.filter = &bpf      */
    mov     x8, #SYS_SECCOMP
    mov     x0, #SECCOMP_SET_MODE_FILTER /* x0 = op                  */
    mov     x1, #0                      /* x1 = flags               */
    mov     x2, sp                      /* x2 = uargs = &fprog      */
    svc     #0
    add     sp, sp, #32
    cbnz    x0, fail22

    /* --- 3. execve(argv[1], &argv[1], envp); fail=23 ---
       Stack at entry: [x29]=argc, [x29+8]=argv[0] (THIS wrapper),
       [x29+16]=argv[1] (the app_process path AMS hands us). v5 fix:
       the old code exec'd argv[0] = itself (infinite self-exec loop;
       the selftest would hang) and passed &argv[0] as argv (app_process
       would mis-parse argv[0]=wrap282). execv convention: argv[0] = path. */
    ldr     x0, [x29, #16]              /* argv[1] = app_process    */
    add     x1, x29, #16                /* argv = &argv[1]          */
    ldr     x3, [x29]
    add     x3, x3, #2
    add     x2, x29, x3, lsl #3
    mov     x8, #SYS_EXECVE
    svc     #0
    cbnz    x0, try64

.balign 4
.balign 4
fail23:
    mov     x0, #23
    b       fail

.balign 4
try64:
    /* --- 4. execve("/system/bin/app_process64", ...) — AMS hands the
       32-bit path on some builds; arm64 redroid has only the 64 ---
       fail=24 */
    adr     x0, app_process64
    add     x1, x29, #16                /* argv = &argv[1]          */
    ldr     x3, [x29]
    add     x3, x3, #2
    add     x2, x29, x3, lsl #3
    mov     x8, #SYS_EXECVE
    svc     #0
    cbnz    x0, try32

.balign 4
.balign 4
fail24:
    mov     x0, #24
    b       fail

.balign 4
try32:
    /* --- 5. execve("/system/bin/app_process", ...); fail=25 --- */
    adr     x0, app_process32
    add     x1, x29, #16                /* argv = &argv[1]          */
    ldr     x3, [x29]
    add     x3, x3, #2
    add     x2, x29, x3, lsl #3
    mov     x8, #SYS_EXECVE
    svc     #0

.balign 4
.balign 4
fail25:
    mov     x0, #25
    b       fail

.balign 4
.balign 4
fail21:
    and     x0, x0, #0xff
    add     x0, x0, #96
    b       fail
.balign 4
.balign 4
fail22:
    /* exit(64 + errno&0xFF) — name the seccomp error in the Zygote log:
       65=EPERM 77=EACCES 86=EINVAL 102=ENOSYS (raw aarch64 syscalls
       return -errno in x0; the low byte IS the errno) */
    and     x0, x0, #0xff
    add     x0, x0, #64
    b       fail

app_process64:
    .asciz "/system/bin/app_process64"

.balign 4
fail:
    mov     x8, #SYS_EXIT_GROUP
    svc     #0

app_process32:
    .asciz "/system/bin/app_process"

/* ---------------------------------------------------------------------------
   THE BPF FILTER — 11 sock_filter instructions, 8 bytes each:
   { u16 code; u8 jt; u8 jf; u32 k } -> one .xword (LE):
   (k<<32)|(jf<<24)|(jt<<16)|code  — byte2=jt, byte3=jf (struct order code,jt,jf,k).
   seccomp_data: nr at 0, args[0] low word at 0x10 (same layout for compat).

   v5 fixes (all three verified by a kernel-semantics simulation):
   1. REGISTERS: seccomp(op,flags,uargs) args were shuffled (x0=&fprog,
      x1=op, x2=0) -> the kernel saw op=garbage -> do_seccomp default ->
      -EINVAL ALWAYS (run 38172868682 exit 42) regardless of the filter.
      Now x0=op, x1=flags, x2=&fprog.
   2. ALLOW VALUE: the default rets were 0x7FF00000 = SECCOMP_RET_TRACE,
      not 0x7FFF0000 = SECCOMP_RET_ALLOW. TRACE with no ptracer fails
      EVERY syscall with -ENOSYS, so the wrapper's own execve would die.
   3. DUAL-ARCH NRs: the 2.8.2 APK is armeabi-v7a ONLY -> every app
      process (incl. the engine) is 32-BIT, where exit=1 and
      exit_group=248 (the wrapper itself is arm64: exit=93, exit_group=94
      — those stay too). The verdict's exit_group(25) in the 32-bit
      engine would have been ALLOWED with the 64-bit-only filter.

   FLOW (11 insns, ERR=RET ERRNO(ENOSYS), OK=RET ALLOW):
     0: nr = ABS[0]
     1: JEQ 1   (arm32 exit)       -> 5, else 2
     2: JEQ 93  (arm64 exit)       -> 5, else 3
     3: JEQ 94  (arm64 exit_group) -> 5, else 4
     4: JEQ 248 (arm32 exit_group) -> 5, else 10 OK
     5: code = ABS[0x10] (args[0] low word)
     6: JEQ 25 -> 9 ERR, else 7
     7: JEQ 30 -> 9 ERR, else 8
     8: JA +1 -> 10 OK
     9: RET ERRNO(ENOSYS)          (the verdict exit becomes a no-op)
    10: RET ALLOW                  (everything else passes)
   --------------------------------------------------------------------------- */
    .align  3
    .global bpf
bpf:
    .xword 0x0000000000000020
    .xword 0x0000000100030015
    .xword 0x0000005D00020015
    .xword 0x0000005E00010015
    .xword 0x000000F805000015
    .xword 0x0000001000000020
    .xword 0x0000001900020015
    .xword 0x0000001E00010015
    .xword 0x0000000100000005
    .xword 0x0005002600000006
    .xword 0x7FFF000000000006
