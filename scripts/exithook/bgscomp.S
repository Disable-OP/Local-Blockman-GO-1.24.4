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
@ Raw syscalls only, no libc: prctl(__NR_prctl=172), seccomp(__NR_seccomp=383).
@ v14: the install = seccomp(2)+TSYNC (filters are PER-TASK; the delayed-arm
@ thread must propagate the filter to the whole process).
@ PR_SET_NO_NEW_PRIVS=38, PR_SET_SECCOMP=22, SECCOMP_MODE_FILTER=2.
@ On ANY failure: return silently (never break the host process).

    .arm
    .text
    .balign 4

    .global bgscomp_ctor
bgscomp_ctor:
    @ EABI callee-saved: r4-r11 — r7 IS callee-saved even though it is the
    @ syscall register. v10.1: the first build trashed r7 and the linker's
    @ soinfo::call_constructors faulted right after the ctor returned
    @ (SIGSEGV in do_dlopen, a ~3s restart loop — run 38181791036).
    @ v13.2: both prctl results are now REPORTED to
    @ /data/local/tmp/guardlog.txt ("OK", "NNP:<errno-hex>", "SC:<errno-hex>")
    @ — run 38194682340 proved the install can silently fail (ARMED logged,
    @ the verdict still exit(25) 43s later).
    push    {r4, r5, r6, r7, lr}
    sub     sp, sp, #16
    @ struct sock_fprog { u16 len; pad; const struct sock_filter *filter; }
    @ arm32 layout: len at [sp], filter at [sp, #4]
    adr     r4, bpf
    mov     r5, #19
    strh    r5, [sp]                @ fprog.len = 19
    str     r4, [sp, #4]            @ fprog.filter = &bpf

    @ prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
    mov     r7, #172                @ __NR_prctl (arm32 EABI)
    mov     r0, #38                 @ PR_SET_NO_NEW_PRIVS
    mov     r1, #1
    mov     r2, #0
    mov     r3, #0
    mov     r4, #0
    svc     #0
    mov     r5, r0                  @ save the raw return
    cmp     r5, #0
    bne     nnp_fail

    @ v14: SECCOMP FILTERS ARE PER-TASK — a filter installed from this
    @ (background-arm) thread covers ONLY that thread; the TSS verdict runs
    @ on another thread and sails through (runs 38194682340/38192389182:
    @ prctl returned 0 = installed, ARMED logged, verdict still exit(25)
    @ ~1s later). The install now goes through seccomp(2) with
    @ SECCOMP_FILTER_FLAG_TSYNC so the filter lands on EVERY thread in the
    @ process. (prctl(PR_SET_SECCOMP) cannot carry flags.)
    @ seccomp(SECCOMP_SET_MODE_FILTER, SECCOMP_FILTER_FLAG_TSYNC, &fprog)
    adr     r4, bpf
    mov     r7, #383                @ __NR_seccomp (arm32 EABI)
    mov     r0, #1                  @ SECCOMP_SET_MODE_FILTER
    mov     r1, #1                  @ SECCOMP_FILTER_FLAG_TSYNC
    mov     r2, sp                  @ &fprog
    svc     #0
    mov     r5, r0                  @ 0 = synced; +tid = first thread that failed
    cmp     r5, #0
    bne     sc_fail

    @ ok
    adr     r0, msg_ok
    mov     r1, #3
    bl      guard_append
    b       done

nnp_fail:
    adr     r0, msg_nnp
    mov     r1, #4
    bl      guard_append
    bl      append_err2
    b       done

sc_fail:
    adr     r0, msg_sc
    mov     r1, #3
    bl      guard_append
    bl      append_err2

done:
    add     sp, sp, #16
    pop     {r4, r5, r6, r7, pc}

@ ---------------------------------------------------------------------------
@ guard_append: append r1 bytes from [r0] to /data/local/tmp/guardlog.txt
@ (pre-created 0666 by CI — the app uid can write it). Preserves r4-r7.
@ Clobbers r0-r3, r12.
@ ---------------------------------------------------------------------------
guard_append:
    push    {r4, r5, r6, r7, lr}
    mov     r6, r0                  @ buf
    mov     r5, r1                  @ len
    @ fd = openat(AT_FDCWD, path, O_WRONLY|O_APPEND|O_CREAT, 0666)
    mov     r7, #322                @ __NR_openat (arm32 EABI)
    mvn     r0, #99                 @ AT_FDCWD = -100
    adr     r1, guard_path
    mov     r2, #0x441              @ O_WRONLY|O_APPEND|O_CREAT
    mov     r3, #0666
    svc     #0
    cmp     r0, #0
    blt     ga_done                 @ cannot open — silently give up
    mov     r4, r0                  @ fd
    @ write(fd, buf, len)
    mov     r7, #4                  @ __NR_write
    mov     r0, r4
    mov     r1, r6
    mov     r2, r5
    svc     #0
    @ close(fd)
    mov     r7, #6
    mov     r0, r4
    svc     #0
ga_done:
    pop     {r4, r5, r6, r7, pc}

@ append_err2: writes (r5 & 0xff) as two hex digits + "\n" via guard_append.
@ Clobbers r0-r3, r12. Preserves r4-r7.
@ ---------------------------------------------------------------------------
append_err2:
    push    {r4, r5, r6, r7, lr}
    sub     sp, sp, #16             @ the 3-byte buffer on the stack
    mov     r1, sp
    and     r0, r5, #0xff
    mov     r2, r0
    lsr     r0, r0, #4              @ high nibble
    bl      nib2chr
    strb    r0, [r1]
    and     r0, r2, #0xf            @ low nibble
    bl      nib2chr
    strb    r0, [r1, #1]
    mov     r0, #10                 @ '\n'
    strb    r0, [r1, #2]
    mov     r0, sp
    mov     r1, #3
    bl      guard_append
    add     sp, sp, #16
    pop     {r4, r5, r6, r7, pc}

@ nib2chr: r0 in 0..15 -> '0'-'9'/'a'-'f' in r0
nib2chr:
    cmp     r0, #9
    addls   r0, r0, #48             @ '0'
    addhi   r0, r0, #87             @ 'a' - 10
    bx      lr

    .balign 4
guard_path:
    .asciz "/data/local/tmp/guardlog.txt"
msg_ok:
    .asciz "OK\n"
msg_nnp:
    .asciz "NNP:"
msg_sc:
    .asciz "SC:"

@ ---------------------------------------------------------------------------
@ THE BPF FILTER — 19 sock_filter instructions, 8 bytes each:
@ { u16 code; u8 jt; u8 jf; u32 k } -> two .word: (code | jt<<16 | jf<<24), k
@ seccomp_data: nr at 0, args[0] low word at 0x10 (same for compat).
@
@ v11: TSS's INIT detects a foreign seccomp filter via
@ prctl(PR_GET_SECCOMP=21) (returning 2) and aborts with a SIGILL inside
@ its packed libBlockMan.so constructor (run 38183140775 tombstones:
@ '#00 pc 0x169d14 libBlockMan.so / #01 call_constructors'). The filter
@ now FAKES the detection: prctl(PR_GET_SECCOMP=21) and
@ prctl(PR_GET_NO_NEW_PRIVS=36) return SECCOMP_RET_ERRNO(0) — the kernel
@ sets the syscall return value to 0 — i.e. "seccomp disabled / nnp unset".
@
@   0: nr = ABS[0]
@   1: JEQ 1   (arm32 exit)       -> 5, else 2
@   2: JEQ 93  (arm64 exit)       -> 5, else 3
@   3: JEQ 94  (arm64 exit_group) -> 5, else 4
@   4: JEQ 248 (arm32 exit_group) -> 5, else 10
@   5: code = ABS[0x10]
@   6: JEQ 25 -> 9 ERR, else 7
@   7: JEQ 30 -> 9 ERR, else 8
@   8: JA +9 -> 18 OK
@   9: RET ERRNO(ENOSYS)          (the verdict exit becomes a no-op)
@  10: JEQ 167 (arm64 prctl)      -> 12, else 11
@  11: JEQ 172 (arm32 prctl)      -> 12, else 18 OK
@  12: option = ABS[0x10]
@  13: JEQ 21  (PR_GET_SECCOMP)   -> 17 FAKE0, else 14
@  14: JEQ 36  (PR_GET_NO_NEW_PRIVS) -> 17 FAKE0, else 15
@  15: JA +2 -> 18 OK
@  16: JA +1 -> 18 OK             (unreachable filler, keeps bounds honest)
@  17: RET ERRNO(0)               (0x00050000: the syscall "returns 0")
@  18: RET ALLOW
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
    .word 0x00000005, 0x00000009          @ 8: JA +9
    .word 0x00000006, 0x00050026          @ 9: RET ERRNO(ENOSYS)
    .word 0x00010015, 0x000000A7          @10: JEQ 167 jt=1 jf=0 (arm64 prctl)
    .word 0x00000015, 0x000000AC          @11: JEQ 172 jt=0 jf=6 (arm32 prctl)
    .word 0x00000020, 0x00000010          @12: LD|W|ABS 0x10     (option)
    .word 0x00030015, 0x00000015          @13: JEQ 21  jt=3 jf=0 (PR_GET_SECCOMP)
    .word 0x00020015, 0x00000024          @14: JEQ 36  jt=2 jf=0 (PR_GET_NO_NEW_PRIVS)
    .word 0x00000005, 0x00000002          @15: JA +2
    .word 0x00000005, 0x00000001          @16: JA +1 (filler)
    .word 0x00000006, 0x00050000          @17: RET ERRNO(0) — "seccomp disabled"
    .word 0x00000006, 0x7FFF0000          @18: RET ALLOW

    .section .init_array,"aw",%init_array
    .balign 4
    .word bgscomp_ctor
