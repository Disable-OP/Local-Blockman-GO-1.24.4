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
 * app_process: exit(93)/exit_group(94) with code 25 or 30 return
 * SECCOMP_RET_ERRNO(ENOSYS) instead of terminating — the verdict
 * becomes a no-op and the engine keeps running. Every other exit code
 * and every other syscall passes through unchanged.
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

    /* --- 2. seccomp(SECCOMP_SET_MODE_FILTER, 0, &fprog); fail=22 --- */
    adr     x2, bpf
    sub     sp, sp, #32
    mov     w3, #14
    str     w3, [sp]                    /* fprog.len = 14           */
    str     x2, [sp, #8]                /* fprog.filter = &bpf      */
    mov     x0, sp
    mov     x8, #SYS_SECCOMP
    mov     x1, #SECCOMP_SET_MODE_FILTER
    mov     x2, #0
    svc     #0
    add     sp, sp, #32
    cbnz    x0, fail22

    /* --- 3. execve(argv[1], argv+1, envp); fail=23 --- */
    ldr     x0, [x29, #8]               /* argv[1] = app_process    */
    add     x1, x29, #8
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
    add     x1, x29, #8
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
    add     x1, x29, #8
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
    lsr     x0, x0, #32
    mov     x1, #96
    add     x0, x1, x0
    b       fail
.balign 4
.balign 4
fail22:
    /* exit(64 + errno) — name the seccomp error in the Zygote log:
       65=EPERM 77=EACCES 86=EINVAL 78=EFAULT 76=ENOMEM 80=EBUSY */
    lsr     x0, x0, #32
    mov     x1, #64
    add     x0, x1, x0
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
   THE BPF FILTER — 14 sock_filter instructions, 8 bytes each:
   { u16 code; u8 jt; u8 jf; u32 k } -> one .xword (LE): (k<<32)|(jf<<16)|(jt<<8)|code
   seccomp_data: nr at 0, args[0] low word at 0x10.
   --------------------------------------------------------------------------- */
    .align  3
    .global bpf
bpf:
    .xword 0x0000000000000020
    .xword 0x0000005D01000015
    .xword 0x0000000100000005
    .xword 0x0000005E09000015
    .xword 0x0000001000000020
    .xword 0x0000001900060015
    .xword 0x0000001E00050015
    .xword 0x7FF0000000000006
    .xword 0x7FF0000000000006
    .xword 0x7FF0000000000006
    .xword 0x7FF0000000000006
    .xword 0x7FF0000000000006
    .xword 0x0005002600000006
    .xword 0x7FF0000000000006
