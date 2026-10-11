@ bgscomp.S — the seccomp engine guard, as an armv7 shared object.
@
@ THE PROBLEM: the 2.8.2 client's :BlockmanGo process (32-bit, the engine
@ host) is killed by libBlockMan.so's EMBEDDED Tencent TSS verdict with a
@ clean exit(25) ~5s after BlockManEchoesActivity starts. The wrap282
@ exithook via the Zygote wrap.<pkg> property is unreliable on this image
@ (the boot fleet gets wrapped; later fleets — including every join-time
@ :BlockmanGo — do NOT: runs 38177186129/38178524142/38179978542).
@
@ THE FIX HERE: this library's .init_array constructor installs the SAME
@ seccomp-BPF filter IN-PROCESS when the app's own code loads it (the
@ LocalAPI hook in BaseApplication.onCreate provably runs in :BlockmanGo).
@ exit/exit_group with code 25 or 30 return SECCOMP_RET_ERRNO(ENOSYS)
@ instead of terminating — the verdict becomes a no-op. Everything else
@ passes. The process is 32-bit: exit=1, exit_group=248 (arm64 nrs 93/94
@ kept for the 64-bit edge case).
@
@ Load: System.loadLibrary("bgscomp") — failures are caught Java-side.
@ Raw syscalls only, no libc: prctl(__NR_prctl=172 arm32 EABI).
@ PR_SET_NO_NEW_PRIVS=38, PR_SET_SECCOMP=22, SECCOMP_MODE_FILTER=2.
@ On ANY failure: return silently (never break the host process).

    .arm
    .text
    .balign 4

    .global bgscomp_ctor
bgscomp_ctor:
    push    {r4, r5, lr}
    sub     sp, sp, #16
    @ struct sock_fprog { u16 len; pad; const struct sock_filter *filter; }
    @ arm32 layout: len at [sp], filter at [sp, #4]
    adr     r4, bpf
    mov     r5, #11
    strh    r5, [sp]                @ fprog.len = 11
    str     r4, [sp, #4]            @ fprog.filter = &bpf

    @ prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
    mov     r7, #172                @ __NR_prctl (arm32 EABI)
    mov     r0, #38                 @ PR_SET_NO_NEW_PRIVS
    mov     r1, #1
    mov     r2, #0
    mov     r3, #0
    mov     r4, #0                  @ arg5 (r4 was &bpf — reloaded below)
    svc     #0
    cmp     r0, #0
    bne     done

    @ prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &fprog)
    adr     r4, bpf
    mov     r7, #172
    mov     r0, #22                 @ PR_SET_SECCOMP
    mov     r1, #2                  @ SECCOMP_MODE_FILTER
    mov     r2, sp                  @ &fprog
    svc     #0                      @ 0 = installed, -errno = not (harmless)
done:
    add     sp, sp, #16
    pop     {r4, r5, pc}

@ ---------------------------------------------------------------------------
@ THE BPF FILTER — 11 sock_filter instructions, 8 bytes each:
@ { u16 code; u8 jt; u8 jf; u32 k } -> two .word: (code | jt<<16 | jf<<24), k
@ seccomp_data: nr at 0, args[0] low word at 0x10 (same for compat).
@
@   0: nr = ABS[0]
@   1: JEQ 1   (arm32 exit)       -> 5, else 2
@   2: JEQ 93  (arm64 exit)       -> 5, else 3
@   3: JEQ 94  (arm64 exit_group) -> 5, else 4
@   4: JEQ 248 (arm32 exit_group) -> 5, else 10 OK
@   5: code = ABS[0x10] (args[0] low word)
@   6: JEQ 25 -> 9 ERR, else 7
@   7: JEQ 30 -> 9 ERR, else 8
@   8: JA +1 -> 10 OK
@   9: RET ERRNO(ENOSYS)          (0x00050026)
@  10: RET ALLOW                  (0x7fff0000)
@ ---------------------------------------------------------------------------
    .balign 4
    .global bpf
bpf:
    .word 0x00000020, 0x00000000          @ 0: LD|W|ABS 0        (nr)
    .word 0x00030015, 0x00000001          @ 1: JEQ 1   jt=3 jf=0 (arm32 exit)
    .word 0x00020015, 0x0000005D          @ 2: JEQ 93  jt=2 jf=0 (arm64 exit)
    .word 0x00010015, 0x0000005E          @ 3: JEQ 94  jt=1 jf=0 (arm64 exit_group)
    .word 0x05000015, 0x000000F8          @ 4: JEQ 248 jt=0 jf=5 (arm32 exit_group)
    .word 0x00000020, 0x00000010          @ 5: LD|W|ABS 0x10     (args[0])
    .word 0x00020015, 0x00000019          @ 6: JEQ 25  jt=2 jf=0
    .word 0x00010015, 0x0000001E          @ 7: JEQ 30  jt=1 jf=0
    .word 0x00000005, 0x00000001          @ 8: JA +1
    .word 0x00000006, 0x00050026          @ 9: RET ERRNO(ENOSYS)
    .word 0x00000006, 0x7FFF0000          @10: RET ALLOW

    .section .init_array,"aw",%init_array
    .balign 4
    .word bgscomp_ctor
