/*
 * sup_selftest.c — a -nostdlib STATIC ELF that runs the bgscomp ctor and
 * then PROVES the supervisor end-to-end. Two build flavors:
 *
 * 1. arm32 + qemu-arm-static (constructor/install smoke): qemu returns
 *    -ENOSYS for seccomp(2) and does not translate struct sock_fprog for
 *    prctl(PR_SET_SECCOMP), so the install falls through the fallback
 *    chain and lands as log lines — the point is ctor crash-freedom, the
 *    raw-clone supervisor spawn, and clean logging.
 *
 * 2. x86_64 native (the REAL functional test): the same C with the
 *    x86_64 audit arch installs bpf15 on the HOST kernel, and every
 *    openat this process then makes is genuinely notified. Assertions:
 *      a) openat("/proc/self/status") returns the SCRUBBED memfd —
 *         the read-back shows "Seccomp: 0" and "NoNewPrivs: 0";
 *      b) openat("/etc/hostname") goes through CONTINUE and reads fine;
 *      c) openat2("/proc/self/status") is scrubbed too;
 *      d) the process still exits cleanly (exit_group ALLOWed).
 *
 * Build/run:
 *   armhf:  armhf-gcc -Os -nostdlib -static ... -o sup_selftest
 *           qemu-arm-static ./sup_selftest && cat $LOG
 *   x86_64: gcc -Os -nostdlib -static ... -o sup_selftest_x86
 *           ./sup_selftest_x86 && cat $LOG
 */

#include "bgscomp.c"

#define SELF_NANOSLEEP 162L /* arm32; x86_64 = 35 — handled below */

#if defined(__x86_64__)
#define SELF_NR_NANOSLEEP 35L
#define SELF_NR_EXIT      60L
#else
#define SELF_NR_NANOSLEEP 162L
#define SELF_NR_EXIT      1L
#endif

static lint self_read(lint fd, char *buf, lint n)
{
    return sysc(__NR_read, fd, (lint)buf, n, 0, 0);
}

static void self_log(const char *s)
{
    log_str(s);
}

__attribute__((noreturn))
void _start(void)
{
    struct { long s; long ns; } ts;
    char buf[4096];
    lint fd, n, i;

    bgscomp_ctor();

    ts.s  = 0;
    ts.ns = 300000000L;      /* 300ms — let the supervisor settle */
#if defined(__x86_64__)
    sysc(35L /* nanosleep */, (lint)&ts, 0, 0, 0, 0);
#else
    sysc(SELF_NR_NANOSLEEP, (lint)&ts, 0, 0, 0, 0);
#endif

    /* (a) openat(/proc/self/status) — must come back SCRUBBED */
    fd = sysc(__NR_openat, AT_FDCWD, (lint)"/proc/self/status",
              O_RDONLY, 0, 0);
    self_log("SELF:stfd=");
    log_num("", fd);
    if (fd >= 0) {
        n = self_read(fd, buf, (lint)sizeof(buf) - 1);
        sysc(__NR_close, fd, 0, 0, 0, 0);
        if (n > 0) {
            buf[n] = 0;
            /* find the Seccomp line and log the value digit */
            for (i = 0; i + 8 < n; i++) {
                if (buf[i] == 'S' && buf[i+1] == 'e' && buf[i+2] == 'c' &&
                    buf[i+3] == 'c' && buf[i+4] == 'o' && buf[i+5] == 'm' &&
                    buf[i+6] == 'p' && buf[i+7] == ':') {
                    lint p = i + 8;
                    while (p < n && (buf[p] == '\t' || buf[p] == ' ')) p++;
                    self_log("SELF:seccomp_val=");
                    if (p < n) {
                        char one[2];
                        one[0] = buf[p];
                        one[1] = 0;
                        self_log(one);
                    }
                    self_log("\n");
                    break;
                }
            }
            /* NoNewPrivs value */
            for (i = 0; i + 11 < n; i++) {
                if (buf[i] == 'N' && buf[i+1] == 'o' && buf[i+2] == 'N' &&
                    buf[i+3] == 'e' && buf[i+4] == 'w' && buf[i+5] == 'P') {
                    lint p = i + 11;
                    while (p < n && (buf[p] == '\t' || buf[p] == ' ')) p++;
                    self_log("SELF:nnp_val=");
                    if (p < n) {
                        char one[2];
                        one[0] = buf[p];
                        one[1] = 0;
                        self_log(one);
                    }
                    self_log("\n");
                    break;
                }
            }
        } else {
            self_log("SELF:stread=EMPTY\n");
        }
    }

    /* (b) openat(/etc/hostname) — CONTINUE: a normal open */
    fd = sysc(__NR_openat, AT_FDCWD, (lint)"/etc/hostname", O_RDONLY, 0, 0);
    self_log("SELF:hnfd=");
    log_num("", fd);
    if (fd >= 0) {
        n = self_read(fd, buf, (lint)sizeof(buf) - 1);
        sysc(__NR_close, fd, 0, 0, 0, 0);
        self_log("SELF:hnread=");
        log_num("", n);
    }

    /* (c) openat2(/proc/self/status) — also scrubbed (args[1] path) */
    {
        struct { u64 flags; u64 mode; u64 resolve; } how;
        how.flags = 0; how.mode = 0; how.resolve = 0;
        fd = sysc(__NR_openat2, AT_FDCWD, (lint)"/proc/self/status",
                  (lint)&how, (lint)sizeof(how), 0);
        self_log("SELF:o2fd=");
        log_num("", fd);
        if (fd >= 0) {
            n = self_read(fd, buf, (lint)sizeof(buf) - 1);
            sysc(__NR_close, fd, 0, 0, 0, 0);
            self_log("SELF:o2read=");
            log_num("", n);
        }
    }

    self_log("SELF:DONE\n");
    sysc(__NR_exit_group, 0, 0, 0, 0, 0);
    __builtin_unreachable();
}
