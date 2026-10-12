/*
 * bgscomp.c — v15: the seccomp USER_NOTIF status-scrub guard (armv7 .so).
 *
 * THE WAR SO FAR (runs 38166105550..38197348885): the 2.8.2 client's
 * :BlockmanGo process (32-bit, hosts libBlockMan.so = engine 10078) is
 * killed by the EMBEDDED Tencent TSS (packed, zero imports):
 *   v10-v13  in-process guard + arm-timing hunt; v13.2 proved the install
 *            "succeeded" yet the verdict still sailed through;
 *   v13/v14  ROOT CAUSE: seccomp filters are PER-TASK — fixed in v14 with
 *            seccomp(2)+SECCOMP_FILTER_FLAG_TSYNC: the clean exit(25)
 *            verdict is GONE;
 *   v14      BUT the TSS ctor now SIGILLs (libBlockMan+0x169d14): the ctor
 *            DETECTS the process-wide filter. v11 proved prctl fakes don't
 *            satisfy it => the check almost certainly reads
 *            /proc/self/status ("Seccomp: 2", "NoNewPrivs: 1").
 *
 * v15 KEEPS the v14 exit-block and ADDS the status scrub: the filter now
 * returns SECCOMP_RET_USER_NOTIF for open/openat/openat2. A supervisor
 * thread (spawned BEFORE the install; same process => same fd table, so
 * NO ADDFD / kernel-5.14 dependency) answers every notification:
 *   - path resolves to /proc/<x>/status: read the REAL status from a
 *     pre-opened fd, rewrite "Seccomp:" and "NoNewPrivs:" values to 0,
 *     write into a fresh memfd, rewind it, reply val=memfd_fd — the
 *     detector reads a clean status and (hopefully) never fires;
 *   - anything else: reply SECCOMP_USER_NOTIF_FLAG_CONTINUE — the syscall
 *     proceeds normally.
 * The supervisor itself never calls open* (all fds are pre-opened) and
 * only uses allowed syscalls (ioctl/read/lseek/write/close/memfd_create),
 * so it cannot deadlock against its own filter.
 *
 * The v14 filter (ERRNO-block on exit/exit_group 25|30 + PR_GET_SECCOMP /
 * PR_GET_NO_NEW_PRIVS faked to 0) is kept VERBATIM as the fallback if the
 * NEW_LISTENER install fails (kernel < 5.9 where TSYNC+LISTENER is EINVAL,
 * or a blocked seccomp(2) — then prctl(PR_SET_SECCOMP) tries the v14
 * behavior one last time).
 *
 * Build (armhf cross, no libc, no libgcc — no 64-bit division anywhere):
 *   arm-linux-gnueabihf-gcc-14 -Os -nostdlib -shared -fPIC \
 *     -fno-stack-protector -fno-builtin -ffreestanding \
 *     -fno-unwind-tables -fno-asynchronous-unwind-tables \
 *     -Wl,--build-id=none -o libbgscomp.so bgscomp.c
 * Load: System.loadLibrary("bgscomp") — Java UNCHANGED (LocalServer).
 *
 * Kernel facts baked in (verified against linux-libc-dev 6.x UAPI):
 *   struct seccomp_notif      = { u64 id; u32 pid; u32 flags; data; } = 80 B
 *   struct seccomp_notif_resp = { u64 id; s64 val; s32 error; u32 flags;} = 24 B
 *   SECCOMP_IOCTL_NOTIF_RECV = _IOWR('!',0,notif) = 0xC0502100 (6.1+;
 *                              5.0-6.0 kernels = 0xC0482100, 72-B struct)
 *   SECCOMP_IOCTL_NOTIF_SEND = _IOWR('!',1,resp)  = 0xC0182101
 *   SECCOMP_RET_USER_NOTIF = 0x7FC00000; FLAG_TSYNC = 1; FLAG_NEW_LISTENER = 8
 *   SECCOMP_USER_NOTIF_FLAG_CONTINUE = 1 (set in resp.flags)
 *   AUDIT_ARCH_ARM = 0x40000028 (EM_ARM=40 | LE)
 * arm32 EABI syscall nrs: open=5 read=3 write=4 close=6 lseek=19 ioctl=54
 *   clone=120 prctl=172 openat=322 seccomp=383 memfd_create=385 openat2=437
 *   exit=1 exit_group=248.
 * CI reality: ubuntu-24.04-arm (kernel 6.8+) + redroid --privileged —
 *   TSYNC+LISTENER (5.9+), CONTINUE (5.5+) and the 6.1+ 80-byte notif are
 *   all supported.
 */

typedef unsigned int       u32;
typedef unsigned short     u16;
typedef unsigned char      u8;
typedef unsigned long long u64;
typedef long long          s64;
typedef long               lint;

/* ------------------------------------------------------------------ */
/* raw syscalls. TWO ABIs:                                             */
/*   __arm__    — the PRODUCTION build (arm32 EABI, r7=nr, svc #0);    */
/*   __x86_64__ — the HOST functional test build (the exact same C,    */
/*                same BPF logic with the x86_64 audit arch, so the    */
/*                supervisor loop (RECV / path read / scrub / memfd    */
/*                reply / CONTINUE) can be proven on a real kernel     */
/*                before spending a CI run).                           */
/* ------------------------------------------------------------------ */

#if defined(__x86_64__)

#define __NR_read          0L
#define __NR_write         1L
#define __NR_open          2L
#define __NR_close         3L
#define __NR_lseek         8L
#define __NR_ioctl        16L
#define __NR_clone        56L
#define __NR_nanosleep    35L
#define __NR_prctl       157L
#define __NR_openat      257L
#define __NR_exit_group  231L
#define __NR_seccomp     317L
#define __NR_memfd_create 319L
#define __NR_openat2     437L
#define AUDIT_ARCH_THIS  0xC000003EU   /* AUDIT_ARCH_X86_64 */

/* the filter's notified nrs — per-ABI (the BPF arrays below use these) */
#define BPF_NR_OPENAT    257
#define BPF_NR_OPEN      2
#define BPF_NR_OPENAT2   437
#define BPF_NR_EXITGROUP 231
#define BPF_NR_EXIT      60
#define BPF_NR_PRCTL     157

static inline lint sysc(lint n, lint a, lint b, lint c, lint d, lint e)
{
    register lint rdi __asm__("rdi") = a;
    register lint rsi __asm__("rsi") = b;
    register lint rdx __asm__("rdx") = c;
    register lint r10 __asm__("r10") = d;
    register lint r8  __asm__("r8")  = e;
    register lint rax __asm__("rax") = n;
    __asm__ volatile ("syscall"
                      : "=a" (rax)
                      : "a" (rax), "D" (rdi), "S" (rsi), "d" (rdx),
                        "r" (r10), "r" (r8)
                      : "rcx", "r11", "memory");
    return rax;
}

#else /* __arm__ — the production ABI */

#define __NR_exit         1L
#define __NR_read         3L
#define __NR_write        4L
#define __NR_open         5L
#define __NR_close        6L
#define __NR_lseek       19L
#define __NR_ioctl       54L
#define __NR_clone      120L
#define __NR_nanosleep  162L
#define __NR_prctl      172L
#define __NR_openat     322L
#define __NR_exit_group 248L
#define __NR_seccomp    383L
#define __NR_memfd_create 385L
#define __NR_openat2    437L
#define AUDIT_ARCH_THIS  0x40000028U   /* AUDIT_ARCH_ARM (EM_ARM 40|LE) */

/* the filter's notified nrs — per-ABI (the BPF arrays below use these) */
#define BPF_NR_OPENAT    322
#define BPF_NR_OPEN      5
#define BPF_NR_OPENAT2   437
#define BPF_NR_EXITGROUP 248
#define BPF_NR_EXIT      1
#define BPF_NR_PRCTL     172

static inline lint sysc(lint n, lint a, lint b, lint c, lint d, lint e)
{
    register lint r0 __asm__("r0") = a;
    register lint r1 __asm__("r1") = b;
    register lint r2 __asm__("r2") = c;
    register lint r3 __asm__("r3") = d;
    register lint r4 __asm__("r4") = e;
    register lint r7 __asm__("r7") = n;
    __asm__ volatile ("svc #0"
                      : "=r" (r0)
                      : "r" (r0), "r" (r1), "r" (r2), "r" (r3), "r" (r4),
                        "r" (r7)
                      : "memory");
    return r0;
}

#endif

#define AT_FDCWD   (-100L)
#define SEEK_SET     0L
#define O_RDONLY     0L
#define O_WRONLY     1L
#define O_RDWR       2L
#define O_CREAT    0100L
#define O_APPEND   02000L

/* prctl */
#define PR_SET_SECCOMP       22L
#define PR_GET_SECCOMP       21L
#define PR_SET_NO_NEW_PRIVS  38L
#define PR_GET_NO_NEW_PRIVS  36L
#define SECCOMP_MODE_FILTER   2L

/* seccomp(2) */
#define SECCOMP_SET_MODE_FILTER          1L
#define SECCOMP_FILTER_FLAG_TSYNC        1L
#define SECCOMP_FILTER_FLAG_NEW_LISTENER 8L
/* TSYNC|NEW_LISTENER is -EINVAL without TSYNC_ESRCH on every kernel that
 * has the combination (5.9+ — verified in v5.10 and v6.8 sources): the
 * kernel cannot otherwise tell a listener fd from a dying-tid return.
 * With it: success = fd >= 0, failure = -ESRCH. */
#define SECCOMP_FILTER_FLAG_TSYNC_ESRCH  16L

#ifndef BGSCOMP_LOGPATH
#define BGSCOMP_LOGPATH "/data/local/tmp/guardlog.txt"
#endif

/* ------------------------------------------------------------------ */
/* seccomp UAPI structs (native ABI; identical layout for arm32 — all  */
/* fixed-width fields, naturally aligned)                              */
/* ------------------------------------------------------------------ */

struct sock_filter { u16 code; u8 jt; u8 jf; u32 k; };
struct sock_fprog { unsigned short len; struct sock_filter *filter; };

struct seccomp_data {
    int  nr;
    u32  arch;
    u64  instruction_pointer;
    u64  args[6];
};

/* 6.1+ kernel layout (80 bytes). On 5.x (72 bytes) the tail would be
 * missing — we only decode id/pid/args, all present in both, so the
 * buffer below is safe for either as long as the IOCTL cmd matches the
 * running kernel's struct size (6.8 on CI => 0xC0502100). */
struct seccomp_notif {
    u64 id;
    u32 pid;
    u32 flags;
    struct seccomp_data data;
};

struct seccomp_notif_resp {
    u64 id;
    s64 val;
    int error;
    u32 flags;
};

#define SECCOMP_IOCTL_NOTIF_RECV 0xC0502100u
#define SECCOMP_IOCTL_NOTIF_SEND 0xC0182101u
#define SECCOMP_USER_NOTIF_FLAG_CONTINUE 1u

/* ------------------------------------------------------------------ */
/* THE FILTERS                                                         */
/*                                                                     */
/* bpf15 (primary): USER_NOTIF on open/openat/openat2 + the v14 exit   */
/* block + the v11 prctl fakes. seccomp_data: nr@0, arch@4,            */
/* args[0].lo@16. 21 instructions.                                     */
/*                                                                     */
/*   0  LD  [4]                    arch                                */
/*   1  JEQ 0x40000028 -> 2 else -> 20 (ALLOW for any other arch)      */
/*   2  LD  [0]                    nr                                  */
/*   3  JEQ 322  -> 17 else 4      (openat  -> NOTIFY)                 */
/*   4  JEQ 5    -> 17 else 5      (open    -> NOTIFY)                 */
/*   5  JEQ 437  -> 17 else 6      (openat2 -> NOTIFY)                 */
/*   6  JEQ 172  -> 12 else 7      (prctl   -> option check)           */
/*   7  JEQ 248  -> 9  else 8      (exit_group)                        */
/*   8  JEQ 1    -> 9  else 20     (exit; other nr -> ALLOW)           */
/*   9  LD  [16]                   args[0] low word                    */
/*   10 JEQ 25   -> 18 else 11     (verdict code -> ERRNO(ENOSYS))     */
/*   11 JEQ 30   -> 18 else 12                                         */
/*   12 JA -> 20                   (harmless exit code -> ALLOW)       */
/*   13 LD  [16]                   prctl option                        */
/*   14 JEQ 21   -> 19 else 15     (PR_GET_SECCOMP -> "return 0")      */
/*   15 JEQ 36   -> 19 else 16     (PR_GET_NO_NEW_PRIVS -> 0)          */
/*   16 JA -> 20                                                       */
/*   17 RET 0x7FC00000             (SECCOMP_RET_USER_NOTIF)            */
/*   18 RET 0x00050026             (ERRNO(ENOSYS) — verdict no-op)     */
/*   19 RET 0x00050000             (ERRNO(0) — syscall returns 0)      */
/*   20 RET 0x7FFF0000             (ALLOW)                             */
/* ------------------------------------------------------------------ */

static const struct sock_filter bpf15[] = {
    { 0x20, 0,  0,  4           },   /*  0 LD [4]  arch        */
    { 0x15, 0, 18,  AUDIT_ARCH_THIS },  /*  1 JEQ arch jt=0 jf=18 */
    { 0x20, 0,  0,  0           },   /*  2 LD [0]  nr          */
    { 0x15, 13, 0,  BPF_NR_OPENAT },  /*  3 openat  -> 17       */
    { 0x15, 12, 0,  BPF_NR_OPEN },    /*  4 open    -> 17       */
    { 0x15, 11, 0,  BPF_NR_OPENAT2 }, /*  5 openat2 -> 17       */
    { 0x15, 6,  0,  BPF_NR_PRCTL },   /*  6 prctl   -> 13       */
    { 0x15, 1,  0,  BPF_NR_EXITGROUP }, /*  7 exit_gr -> 9      */
    { 0x15, 0, 11,  BPF_NR_EXIT },    /*  8 exit    -> 9 / 20   */
    { 0x20, 0,  0,  16          },   /*  9 LD [16] args0.lo    */
    { 0x15, 7,  0,  25          },   /* 10 ==25 -> 18          */
    { 0x15, 6,  0,  30          },   /* 11 ==30 -> 18          */
    { 0x05, 0,  0,  7           },   /* 12 JA -> 20            */
    { 0x20, 0,  0,  16          },   /* 13 LD [16] option      */
    { 0x15, 4,  0,  21          },   /* 14 PR_GET_SECCOMP->19  */
    { 0x15, 3,  0,  36          },   /* 15 PR_GET_NNP    ->19  */
    { 0x05, 0,  0,  3           },   /* 16 JA -> 20            */
    { 0x06, 0,  0,  0x7FC00000U },   /* 17 RET USER_NOTIF      */
    { 0x06, 0,  0,  0x00050026U },   /* 18 RET ERRNO(ENOSYS)   */
    { 0x06, 0,  0,  0x00050000U },   /* 19 RET ERRNO(0)        */
    { 0x06, 0,  0,  0x7FFF0000U },   /* 20 RET ALLOW           */
};

/* bpf14 (fallback): the exact v14 filter — ERRNO(ENOSYS) on the verdict
 * exits + the prctl fakes, NO USER_NOTIF (a listener-less process must
 * never return USER_NOTIF from a filter). 19 instructions. The arm64 nr
 * entries (93/94/167) stay literal: they are belt-and-braces for the
 * 64-bit edge case on the arm build and inert elsewhere. */
static const struct sock_filter bpf14[] = {
    { 0x20, 0,  0,  0           },   /*  0 LD [0] nr           */
    { 0x15, 3,  0,  BPF_NR_EXIT },    /*  1 arm32 exit    -> 5  */
    { 0x15, 2,  0,  93          },   /*  2 arm64 exit    -> 5  */
    { 0x15, 1,  0,  94          },   /*  3 arm64 exit_gr -> 5  */
    { 0x15, 0,  5,  BPF_NR_EXITGROUP }, /*  4 arm32 exit_gr -> 5 */
    { 0x20, 0,  0,  16          },   /*  5 LD [16] args0       */
    { 0x15, 2,  0,  25          },   /*  6 ==25 -> 9           */
    { 0x15, 1,  0,  30          },   /*  7 ==30 -> 9           */
    { 0x05, 0,  0,  9           },   /*  8 JA -> 18            */
    { 0x06, 0,  0,  0x00050026U },   /*  9 RET ERRNO(ENOSYS)   */
    { 0x15, 1,  0,  167         },   /* 10 arm64 prctl -> 12   */
    { 0x15, 0,  6,  BPF_NR_PRCTL },   /* 11 arm32 prctl -> 12   */
    { 0x20, 0,  0,  16          },   /* 12 LD [16] option      */
    { 0x15, 3,  0,  21          },   /* 13 GET_SECCOMP -> 17   */
    { 0x15, 2,  0,  36          },   /* 14 GET_NNP     -> 17   */
    { 0x05, 0,  0,  2           },   /* 15 JA -> 18            */
    { 0x05, 0,  0,  1           },   /* 16 JA -> 18 (filler)   */
    { 0x06, 0,  0,  0x00050000U },   /* 17 RET ERRNO(0)        */
    { 0x06, 0,  0,  0x7FFF0000U },   /* 18 RET ALLOW           */
};

/* ------------------------------------------------------------------ */
/* state                                                               */
/* ------------------------------------------------------------------ */

static int g_sfd = -1;   /* pre-opened /proc/self/status (O_RDONLY)*/
static int g_mfd = -1;   /* pre-opened /proc/self/mem    (O_RDWR)  */
static int g_gfd = -1;   /* guardlog (O_APPEND)                    */
/* g_lfd is written by the installing (main) thread and read by the
 * supervisor thread in a tight loop — it MUST be volatile, or the
 * supervisor caches the pre-install -1 and spins on EBADF while the
 * tracee waits forever for its reply (the 18M-line REVE:-9 lesson). */
static volatile int g_lfd = -1;   /* the listener fd                  */

static struct seccomp_notif      g_notif;
static struct seccomp_notif_resp g_resp;
static char g_path[512];   /* the tracee's openat path (from its mem) */
static char g_buf[4096];   /* the real status text                    */
static char g_num[24];     /* log scratch                             */

/* ------------------------------------------------------------------ */
/* tiny logging (write to the pre-opened O_APPEND fd)                  */
/* ------------------------------------------------------------------ */

static lint slen(const char *s)
{
    lint n = 0;
    while (s[n]) n++;
    return n;
}

static void log_str(const char *s)
{
    if (g_gfd >= 0 && s)
        sysc(__NR_write, g_gfd, (lint)s, slen(s), 0, 0);
}

static void log_num(const char *tag, lint v)
{
    lint p = 0;
    char tmp[12];
    lint t = 0;
    u32 uv;

    if (g_gfd < 0)
        return;
    while (tag && tag[p]) { g_num[p] = tag[p]; p++; }
    if (v < 0) { g_num[p++] = '-'; uv = (u32)(-v); }
    else       { uv = (u32)v; }
    if (uv == 0) {
        tmp[t++] = '0';
    } else {
        /* no libgcc: shift-subtract divide-by-10 (32 rounds), the
         * remainder of the LAST round is the decimal digit. */
        while (uv) {
            u32 q = 0, r = 0;
            int i;
            for (i = 31; i >= 0; i--) {
                r = (r << 1) | ((uv >> i) & 1u);
                if (r >= 10) { r -= 10; q |= (1u << i); }
            }
            tmp[t++] = (char)('0' + r);
            uv = q;
        }
    }
    while (t) g_num[p++] = tmp[--t];
    g_num[p++] = '\n';
    sysc(__NR_write, g_gfd, (lint)g_num, p, 0, 0);
}

/* ------------------------------------------------------------------ */
/* the supervisor                                                      */
/* ------------------------------------------------------------------ */

/* does g_path[0..n) hold a NUL-terminated /proc/<x>/status path? */
static int path_is_status(lint n)
{
    static const char sfx[7] = { '/', 's', 't', 'a', 't', 'u', 's' };
    lint len = 0;
    lint i;

    if (n <= 0 || n > (lint)sizeof(g_path))
        return 0;
    while (len < n && g_path[len]) len++;
    if (len >= n)          return 0;   /* not NUL-terminated: give up  */
    if (len < 14)          return 0;   /* min: /proc/1/status          */
    if (g_path[0] != '/' || g_path[1] != 'p' || g_path[2] != 'r' ||
        g_path[3] != 'o'  || g_path[4] != 'c' || g_path[5] != '/')
        return 0;
    for (i = 0; i < 7; i++)
        if (g_path[len - 7 + i] != sfx[i])
            return 0;
    return 1;
}

/* rewrite the VALUE digit of "Seccomp:" / "NoNewPrivs:" lines to '0'.
 * returns a bitmask: 1 = Seccomp seen, 2 = NoNewPrivs seen. */
static int scrub_status(lint n)
{
    static const char n1[8] = { 'S','e','c','c','o','m','p',':' };
    static const char n2[11] = { 'N','o','N','e','w','P','r','i','v','s',':' };
    lint i, j;
    int mask = 0;

    for (i = 0; i < n; i++) {
        if (g_buf[i] == 'S' || g_buf[i] == 'N') {
            const char *nd;
            lint ndlen, off;

            if (g_buf[i] == 'S') { nd = n1; ndlen = 8; off = 0; }
            else                 { nd = n2; ndlen = 11; off = 1; }
            if (i + ndlen <= n) {
                int hit = 1;
                for (j = 0; j < ndlen; j++)
                    if (g_buf[i + j] != nd[j]) { hit = 0; break; }
                if (hit) {
                    lint p = i + ndlen;          /* past the colon */
                    if (p < n && g_buf[p] == '\t') p++;
                    while (p < n && g_buf[p] >= '0' && g_buf[p] <= '9')
                        g_buf[p++] = '0';
                    mask |= (1 << off);
                    i = p;
                }
            }
        }
    }
    return mask;
}

__attribute__((noreturn))
static void supervisor_loop(void)
{
    u32 fail_streak = 0;

    /* wait for the installer to publish the listener fd — the spawn
     * races the seccomp(2) install, and spinning on ioctl(-1) burns CPU
     * AND floods the guardlog (the 18M-line REVE:-9 lesson). */
    while (g_lfd < 0) {
        struct { long s; long ns; } ts;
        ts.s = 0;
        ts.ns = 1000000L;       /* 1ms */
        sysc(__NR_nanosleep, (lint)&ts, 0, 0, 0, 0);
    }

    for (;;) {
        lint r;
        u32 nr;
        u32 pp;
        lint n;
        int is_status = 0;

        /* the kernel REQUIRES a fully-zeroed RECV buffer:
         * seccomp_notify_recv() runs check_zeroed_user(buf, sizeof(unotif))
         * as its extensibility contract — a dirty (reused) buffer returns
         * -EINVAL and every later notification stalls forever. */
        {
            u32 *zp = (u32 *)&g_notif;
            u32 zi;
            for (zi = 0; zi < (u32)sizeof(g_notif) / 4; zi++)
                zp[zi] = 0;
        }

        r = sysc(__NR_ioctl, g_lfd,
                 (lint)SECCOMP_IOCTL_NOTIF_RECV, (lint)&g_notif, 0, 0);

        if (r != 0) {
            log_num("REVE:", r);   /* ENOENT/ESRCH/EINTR — retry */
            if (++fail_streak > 64) {
                /* persistent RECV failure (e.g. a cmd-encoding mismatch
                 * on an older kernel): park softly instead of burning
                 * CPU — the v14 filter is still installed as the
                 * backstop for the exit verdict. */
                struct { long s; long ns; } ts;
                ts.s = 1;
                ts.ns = 0;
                sysc(__NR_nanosleep, (lint)&ts, 0, 0, 0, 0);
            }
            continue;
        }
        fail_streak = 0;

        nr = (u32)g_notif.data.nr;
        /* open(path,flags): path = args[0]; openat/openat2: args[1] */
        pp = (u32)((nr == __NR_open) ? g_notif.data.args[0]
                                     : g_notif.data.args[1]);

        if (pp) {
            sysc(__NR_lseek, g_mfd, (lint)pp, SEEK_SET, 0, 0);
            n = sysc(__NR_read, g_mfd, (lint)g_path,
                     (lint)sizeof(g_path) - 1, 0, 0);
            if (n > 0)
                is_status = path_is_status(n);
        }

        g_resp.id    = g_notif.id;
        g_resp.val   = 0;
        g_resp.error = 0;
        g_resp.flags = 0;

        if (is_status) {
            lint m, fd;
            int mask = 0;

            /* rewind: seq_file reads continue from f_pos — a second
             * read without the seek would return EOF. */
            sysc(__NR_lseek, g_sfd, 0, SEEK_SET, 0, 0);
            m = sysc(__NR_read, g_sfd, (lint)g_buf,
                     (lint)sizeof(g_buf), 0, 0);
            if (m > 0)
                mask = scrub_status(m);

            fd = sysc(__NR_memfd_create, (lint)".bgst", 0, 0, 0, 0);
            if (fd >= 0 && m > 0) {
                sysc(__NR_write, fd, (lint)g_buf, m, 0, 0);
                sysc(__NR_lseek, fd, 0, SEEK_SET, 0, 0);
                g_resp.val = fd;
            } else {
                if (fd >= 0)
                    sysc(__NR_close, fd, 0, 0, 0, 0);
                g_resp.error = -5;      /* -EIO: the open fails cleanly */
            }
            /* file evidence: s<mask>:<tracee pid> */
            g_num[0] = 's';
            g_num[1] = (char)('0' + (mask & 3));
            g_num[2] = ':';
            sysc(__NR_write, g_gfd, (lint)g_num, 3, 0, 0);
            log_num("", (lint)g_notif.pid);
        } else {
            g_resp.flags = SECCOMP_USER_NOTIF_FLAG_CONTINUE;
#ifdef BGSCOMP_DEBUG_REPLY
            log_str("CNT\n");
#endif
        }

        r = sysc(__NR_ioctl, g_lfd,
                 (lint)SECCOMP_IOCTL_NOTIF_SEND, (lint)&g_resp, 0, 0);
        if (r != 0)
            log_num("SNDE:", r);
    }
}

/* CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|CLONE_THREAD|CLONE_SYSVSEM
 * = 0x50F00 — no TLS needed (pure syscall code, no bionic/glibc). */
#define SUP_STACK_SIZE 65536
static char g_supstack[SUP_STACK_SIZE] __attribute__((aligned(8)));

#if defined(__x86_64__)
/* generic layout: flags, newsp, parent_tid, child_tid, tls */
static lint clone_supervisor(void)
{
    register lint rdi __asm__("rdi") = 0x50F00L;
    register lint rsi __asm__("rsi") = (lint)(g_supstack + SUP_STACK_SIZE - 8);
    register lint rdx __asm__("rdx") = 0;
    register lint r10 __asm__("r10") = 0;
    register lint r8  __asm__("r8")  = 0;
    register lint rax __asm__("rax") = __NR_clone;
    __asm__ volatile ("syscall"
                      : "=a" (rax)
                      : "a" (rax), "D" (rdi), "S" (rsi), "d" (rdx),
                        "r" (r10), "r" (r8)
                      : "rcx", "r11", "memory");
    return rax;
}
#else
/* arm32 clone (CONFIG_CLONE_BACKWARDS): r0=flags r1=newsp r2=parent_tid
 * r3=tls r4=child_tid */
static lint clone_supervisor(void)
{
    register lint r0 __asm__("r0") = 0x50F00L;
    register lint r1 __asm__("r1") = (lint)(g_supstack + SUP_STACK_SIZE - 8);
    register lint r2 __asm__("r2") = 0;
    register lint r3 __asm__("r3") = 0;
    register lint r4 __asm__("r4") = 0;
    register lint r7 __asm__("r7") = __NR_clone;

    __asm__ volatile ("svc #0"
                      : "=r" (r0)
                      : "r" (r0), "r" (r1), "r" (r2), "r" (r3), "r" (r4),
                        "r" (r7)
                      : "memory");
    return r0;
}
#endif

/* ------------------------------------------------------------------ */
/* the constructor                                                     */
/* ------------------------------------------------------------------ */

__attribute__((constructor, visibility("default")))
void bgscomp_ctor(void)
{
    struct sock_fprog p15;
    struct sock_fprog p14;
    lint tid, r;

    g_lfd = -1; g_sfd = -1; g_mfd = -1;

    g_gfd = sysc(__NR_openat, AT_FDCWD, (lint)BGSCOMP_LOGPATH,
                 O_WRONLY | O_APPEND | O_CREAT, 0666L, 0);

    /* pre-open EVERYTHING the supervisor will ever need — it must never
     * call open* (it would notify itself). */
    g_sfd = sysc(__NR_openat, AT_FDCWD, (lint)"/proc/self/status",
                 O_RDONLY, 0, 0);
    g_mfd = sysc(__NR_openat, AT_FDCWD, (lint)"/proc/self/mem",
                 O_RDWR, 0, 0);
    if (g_mfd < 0)
        g_mfd = sysc(__NR_openat, AT_FDCWD, (lint)"/proc/self/mem",
                     O_RDONLY, 0, 0);

    log_str("v15 ctor\n");
    log_num("SFD:", g_sfd);
    log_num("MFD:", g_mfd);

    /* NNP FIRST: no_new_privs is a PER-TASK flag (inherited at clone from
     * the CURRENT value). The supervisor must ALREADY carry it when TSYNC
     * walks the thread group, or the sync fails (-EINVAL on the whole
     * install). So: NNP -> spawn -> install. */
    r = sysc(__NR_prctl, PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0);
    log_num("NNP:", r);
    if (r != 0)
        goto fallback;          /* no NNP => no filter install at all */

    /* the supervisor spawns BEFORE the filter so TSYNC covers it too —
     * by design it only issues ALLOWed syscalls. */
    tid = clone_supervisor();
    if (tid == 0)
        supervisor_loop();      /* the child — never returns */
    log_num("SUP:", tid);

    p15.len    = (unsigned short)(sizeof(bpf15) / sizeof(bpf15[0]));
    p15.filter = (struct sock_filter *)bpf15;

    /* seccomp(SET_MODE_FILTER, TSYNC|NEW_LISTENER|TSYNC_ESRCH, &prog)
     * — returns the LISTENER fd (>=0) on success, a negative errno on
     * failure (TSYNC_ESRCH makes the return unambiguous). */
    r = sysc(__NR_seccomp, SECCOMP_SET_MODE_FILTER,
             SECCOMP_FILTER_FLAG_TSYNC | SECCOMP_FILTER_FLAG_NEW_LISTENER |
             SECCOMP_FILTER_FLAG_TSYNC_ESRCH,
             (lint)&p15, 0, 0);
    if (r >= 0) {
        g_lfd = (int)r;
        log_num("LST:", g_lfd);
        log_str("DONE\n");
        return;
    }
    log_num("LE:", r);

#ifdef BGSCOMP_HOSTTEST
    /* TEST-ONLY stage (never compiled into the APK): kernels < 5.11-ish
     * reject TSYNC|NEW_LISTENER (-EPERM) but accept a listener WITHOUT
     * TSYNC — the filter then covers ONLY this thread, which is exactly
     * the thread running the selftest assertions. */
    r = sysc(__NR_seccomp, SECCOMP_SET_MODE_FILTER,
             SECCOMP_FILTER_FLAG_NEW_LISTENER, (lint)&p15, 0, 0);
    if (r >= 0) {
        g_lfd = (int)r;
        log_num("LST1:", g_lfd);
        log_str("DONE\n");
        return;
    }
    log_num("L1E:", r);
#endif

fallback:
    /* FALLBACK 1: the exact v14 filter via seccomp+TSYNC (no listener —
     * the verdict exit(25|30) still no-ops; only the status scrub is
     * lost, which is what the ctor detection feeds on). */
    p14.len    = (unsigned short)(sizeof(bpf14) / sizeof(bpf14[0]));
    p14.filter = (struct sock_filter *)bpf14;
    r = sysc(__NR_seccomp, SECCOMP_SET_MODE_FILTER,
             SECCOMP_FILTER_FLAG_TSYNC, (lint)&p14, 0, 0);
    if (r == 0) {
        log_str("F14\nDONE\n");
        return;
    }
    log_num("F14E:", r);

    /* FALLBACK 2: prctl(PR_SET_SECCOMP) — works even where seccomp(2)
     * is blocked by policy (proven on-device in v10-v13). */
    r = sysc(__NR_prctl, PR_SET_SECCOMP, SECCOMP_MODE_FILTER,
             (lint)&p14, 0, 0);
    if (r == 0) {
        log_str("F14P\nDONE\n");
        return;
    }
    log_num("F14PE:", r);
    log_str("DONE\n");
}

/* the smoke-test harness (sup_selftest.c) calls this directly; keep the
 * symbol so a static link can find it. */
