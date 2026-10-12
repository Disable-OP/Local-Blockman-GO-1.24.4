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
#define __NR_getpid       39L
#define __NR_ptrace      101L
#define __NR_PROCESS_VM_READV 310L
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
#define BPF_NR_PTRICE    101
#define BPF_NR_VMREADV   310
#define BPF_NR_CLONE     56

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
#define __NR_getpid      22L
#define __NR_ptrace      26L
#define __NR_PROCESS_VM_READV 276L
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
#define BPF_NR_PTRICE    26
#define BPF_NR_VMREADV   276
#define BPF_NR_CLONE     120

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
#define SECCOMP_IOCTL_NOTIF_ADDFD 0x40182103u
#define SECCOMP_USER_NOTIF_FLAG_CONTINUE 1u
#define SECCOMP_ADDFD_FLAG_SEND 2u

struct seccomp_notif_addfd {
    u64 id;
    u32 flags;
    u32 srcfd;
    u32 newfd;
    u32 newfd_flags;
};

/* ------------------------------------------------------------------ */
/* THE FILTERS                                                         */
/*                                                                     */
/* bpf15 (primary): USER_NOTIF on open/openat/openat2 + the v14 exit   */
/* block + the v11 prctl fakes. seccomp_data: nr@0, arch@4,            */
/* args[0].lo@16. 21 instructions.                                     */
/*                                                                     */
/*   0  LD  [4]                    arch                                */
/*   1  JEQ <arch> -> 2 else -> 25 (ALLOW for any other arch)          */
/*   2  LD  [0]                    nr                                  */
/*   3  JEQ 322  -> 22 else 4      (openat  -> NOTIFY)                 */
/*   4  JEQ 5    -> 22 else 5      (open    -> NOTIFY)                 */
/*   5  JEQ 437  -> 22 else 6      (openat2 -> NOTIFY)                 */
/*   6  JEQ 172  -> 18 else 7      (prctl   -> option check)           */
/*   7  JEQ 248  -> 14 else 8      (exit_group)                        */
/*   8  JEQ 1    -> 14 else 9      (exit; else fall to io_uring block) */
/*   9  JEQ 425  -> 21 else 10     (io_uring_setup -> ERRNO(ENOSYS))   */
/*  10  JEQ 426  -> 21 else 11     (io_uring_enter)                    */
/*  11  JEQ 427  -> 21 else 23     (io_uring_register)                 */
/*  12  JEQ 26   -> 22 else 13     (ptrace  -> NOTIFY: log + CONTINUE) */
/*  13  JEQ 120  -> 22 else 25     (clone   -> NOTIFY: log + CONTINUE) */
/*  14  LD  [16]                   args[0] low word                    */
/*  15  JEQ 25   -> 23 else 16     (verdict code -> ERRNO(ENOSYS))     */
/*  16  JEQ 30   -> 23 else 17                                         */
/*  17  JA -> 25                   (harmless exit code -> ALLOW)       */
/*  18  LD  [16]                   prctl option                        */
/*  19  JEQ 21   -> 24 else 20     (PR_GET_SECCOMP -> "return 0")      */
/*  20  JEQ 36   -> 24 else 21     (PR_GET_NO_NEW_PRIVS -> 0)          */
/*  21  JA -> 25                                                       */
/*  22  RET 0x7FC00000             (SECCOMP_RET_USER_NOTIF)            */
/*  23  RET 0x00050026             (ERRNO(ENOSYS) - verdict+io_uring)  */
/*  24  RET 0x00050000             (ERRNO(0) - syscall returns 0)      */
/*  25  RET 0x7FFF0000             (ALLOW)                             */
/*                                                                     */
/* v16: io_uring (425/426/427) is ERRNO(ENOSYS): an io_uring OPENAT    */
/* bypasses the whole filter (the open happens kernel-side inside      */
/* io_uring_enter, invisible to the supervisor). Nothing sane in the   */
/* engine uses io_uring; the TSS could, to read the REAL status/maps.  */
/* ------------------------------------------------------------------ */

static const struct sock_filter bpf15[] = {
    { 0x20, 0,  0,  4           },   /*  0 LD [4]  arch        */
    { 0x15, 0, 24,  AUDIT_ARCH_THIS },  /*  1 JEQ arch jt=0 jf=24 */
    { 0x20, 0,  0,  0           },   /*  2 LD [0]  nr          */
    { 0x15, 19, 0,  BPF_NR_OPENAT },  /*  3 openat  -> 23       */
    { 0x15, 18, 0,  BPF_NR_OPEN },    /*  4 open    -> 23       */
    { 0x15, 17, 0,  BPF_NR_OPENAT2 }, /*  5 openat2 -> 23       */
    { 0x15, 12, 0,  BPF_NR_PRCTL },   /*  6 prctl   -> 19       */
    { 0x15, 7,  0,  BPF_NR_EXITGROUP }, /*  7 exit_gr -> 15     */
    { 0x15, 6,  0,  BPF_NR_EXIT },    /*  8 exit    -> 15       */
    { 0x15, 14, 0,  425         },   /*  9 io_uring_setup -> 24 */
    { 0x15, 13, 0,  426         },   /* 10 io_uring_enter -> 24 */
    { 0x15, 12, 0,  427         },   /* 11 io_uring_reg   -> 24 */
    { 0x15, 10, 0,  BPF_NR_PTRICE },  /* 12 ptrace  -> 23       */
    { 0x15, 9,  0,  BPF_NR_CLONE },   /* 13 clone   -> 23       */
    { 0x15, 8, 11,  BPF_NR_VMREADV }, /* 14 vm_readv -> 23 / 26  */
    { 0x20, 0,  0,  16          },   /* 15 LD [16] args0.lo    */
    { 0x15, 7,  0,  25          },   /* 16 ==25 -> 24          */
    { 0x15, 6,  0,  30          },   /* 17 ==30 -> 24          */
    { 0x05, 0,  0,  7           },   /* 18 JA -> 26            */
    { 0x20, 0,  0,  16          },   /* 19 LD [16] option      */
    { 0x15, 4,  0,  21          },   /* 20 PR_GET_SECCOMP->25  */
    { 0x15, 3,  0,  36          },   /* 21 PR_GET_NNP    ->25  */
    { 0x05, 0,  0,  3           },   /* 22 JA -> 26            */
    { 0x06, 0,  0,  0x7FC00000U },   /* 23 RET USER_NOTIF      */
    { 0x06, 0,  0,  0x00050026U },   /* 24 RET ERRNO(ENOSYS)   */
    { 0x06, 0,  0,  0x00050000U },   /* 25 RET ERRNO(0)        */
    { 0x06, 0,  0,  0x7FFF0000U },   /* 26 RET ALLOW           */
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
static int g_pfd = -1;   /* pre-opened /proc/self/maps  (O_RDONLY) */
static int g_nfd = -1;   /* pre-opened /proc/self/mountinfo        */
static int g_gfd = -1;   /* guardlog (O_APPEND)                    */
static int g_mypid = 0;  /* our tgid — self vs forked-child notifications */
static u32 g_plog = 0;   /* /proc-path notification log counter    */
/* g_lfd is written by the installing (main) thread and read by the
 * supervisor thread in a tight loop — it MUST be volatile, or the
 * supervisor caches the pre-install -1 and spins on EBADF while the
 * tracee waits forever for its reply (the 18M-line REVE:-9 lesson). */
static volatile int g_lfd = -1;   /* the listener fd                  */

static struct seccomp_notif      g_notif;
static struct seccomp_notif_resp g_resp;
static struct seccomp_notif_addfd g_addfd;
static char g_path[512];   /* the tracee's openat path (from its mem) */
static char g_buf[4096];   /* the real status text                    */
/* maps of the engine process runs tens of KB — one big static buffer */
static char g_big[196608];
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

/* shift-subtract divide by 10 (no libgcc in -nostdlib; gcc emits
 * __aeabi_uidivmod for % and / — an undefined symbol in a bare .so). */
static u32 udiv10(u32 v, u32 *rem)
{
    u32 q = 0, r = 0;
    int i;
    for (i = 31; i >= 0; i--) {
        r = (r << 1) | ((v >> i) & 1u);
        if (r >= 10) { r -= 10; q |= (1u << i); }
    }
    if (rem)
        *rem = r;
    return q;
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
        while (uv) {
            u32 d;
            uv = udiv10(uv, &d);
            tmp[t++] = (char)('0' + d);
        }
    }
    while (t) g_num[p++] = tmp[--t];
    g_num[p++] = '\n';
    sysc(__NR_write, g_gfd, (lint)g_num, p, 0, 0);
}

/* ------------------------------------------------------------------ */
/* the supervisor                                                      */
/* ------------------------------------------------------------------ */

/* path classes for the notified opens (v16) */
#define PC_NONE      0
#define PC_STATUS    1   /* /proc/<x>/status                        */
#define PC_MAPS      2   /* /proc/<x>/maps or /proc/<x>/task/T/smaps */
#define PC_MOUNTINFO 3   /* /proc/<x>/mountinfo|mounts|mountstats   */

static int path_ends(lint len, const char *sfx, lint slen)
{
    lint i;
    if (len < slen)
        return 0;
    for (i = 0; i < slen; i++)
        if (g_path[len - slen + i] != sfx[i])
            return 0;
    return 1;
}

/* does g_path[0..n) hold a NUL-terminated /proc/<x>/<sensitive> path? */
static int path_class(lint n)
{
    lint len = 0;

    if (n <= 0 || n > (lint)sizeof(g_path))
        return PC_NONE;
    while (len < n && g_path[len]) len++;
    if (len >= n)          return PC_NONE;  /* not NUL-terminated */
    if (len < 12)          return PC_NONE;
    if (g_path[0] != '/' || g_path[1] != 'p' || g_path[2] != 'r' ||
        g_path[3] != 'o'  || g_path[4] != 'c' || g_path[5] != '/')
        return PC_NONE;
    if (path_ends(len, "/status", 7))
        return PC_STATUS;
    if (path_ends(len, "/maps", 5) || path_ends(len, "/smaps", 6))
        return PC_MAPS;
    if (path_ends(len, "/mountinfo", 10) || path_ends(len, "/mounts", 7) ||
        path_ends(len, "/mountstats", 11))
        return PC_MOUNTINFO;
    return PC_NONE;
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

/* drop every line containing the needle, in place. returns the new
 * length. used for /proc/.../maps (hide libbgscomp) and /proc/.../
 * mountinfo|mounts (hide the layer-2 fake-status binds). */
static lint filter_lines(char *buf, lint n, const char *nd, lint ndlen)
{
    lint r = 0, w = 0, ls, i, hit;

    while (r < n) {
        ls = r;
        while (r < n && buf[r] != '\n')
            r++;
        if (r < n)
            r++;                    /* include the newline */
        hit = 0;
        for (i = ls; i + ndlen <= r; i++) {
            lint j;
            for (j = 0; j < ndlen; j++)
                if (buf[i + j] != nd[j])
                    break;
            if (j == ndlen) { hit = 1; break; }
        }
        if (!hit) {
            lint k;
            for (k = ls; k < r; k++)
                buf[w++] = buf[k];
        }
    }
    return w;
}

#ifndef BGSCOMP_MAPSNEEDLE
#define BGSCOMP_MAPSNEEDLE "bgscomp"
#endif
#ifndef BGSCOMP_MNTNEEDLE
#define BGSCOMP_MNTNEEDLE "/data/local/tmp/fs_"
#endif

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
        int pclass = PC_NONE;

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
                pclass = path_class(n);
        }

        /* v16 diagnostics: EVERY /proc/* open the TSS (or the engine)
         * makes is logged — the run's dead drops told us the TSS never
         * opened status; this tells us what it DOES read. Capped. */
        if (pclass != PC_NONE && g_gfd >= 0 && g_plog < 300) {
            lint i2, st = 0, q = 0;
            u32 uv = nr;
            g_plog++;
            /* assemble ONE line — concurrent writers garble multi-write
             * lines even through O_APPEND (each write is atomic, the
             * line is not). */
            g_num[q++] = 'P';
            g_num[q++] = ':';
            if (uv == 0) g_num[q++] = '0';
            {
                char tmp2[12];
                lint w = 0;
                while (uv) { u32 d; uv = udiv10(uv, &d); tmp2[w++] = (char)('0' + d); }
                while (w) g_num[q++] = tmp2[--w];
            }
            g_num[q++] = ':';
            for (i2 = 0; i2 < n && g_path[i2]; i2++)
                if (g_path[i2] == '/') st = i2 + 1;
            while (q < (lint)sizeof(g_num) - 2 && st < n)
                g_num[q++] = g_path[st++];
            g_num[q++] = '\n';
            sysc(__NR_write, g_gfd, (lint)g_num, q, 0, 0);
        }

        g_resp.id    = g_notif.id;
        g_resp.val   = 0;
        g_resp.error = 0;
        g_resp.flags = 0;

        /* v17: the TSS watchdog's ptrace/fork behavior is THE missing
         * picture (v15/v16: zero proc-file reads, the engine frozen in
         * ptrace_stop). Notify these two, log, CONTINUE — zero behavior
         * change, full visibility of WHO attaches WHEN with WHAT. */
        if (nr == __NR_ptrace) {
            /* v19: ATTACH denial REVERTED — v18 proved the TSS ABORTS
             * engine init when its watchdog cannot attach (echoes never
             * came up; the umbrella is MANDATORY). Log everything, pass
             * everything: the freeze comes from the watchdog's LATER
             * tamper response, not from the attach itself. */
            if (g_gfd >= 0 && g_plog < 400) {
                lint q = 0, w = 0;
                char tmp2[12];
                u32 uv = (u32)g_notif.data.args[0];
                g_plog++;
                g_num[q++] = 'T';
                g_num[q++] = ':';
                if (uv == 0) tmp2[w++] = '0';
                while (uv) { u32 d; uv = udiv10(uv, &d); tmp2[w++] = (char)('0' + d); }
                while (w) g_num[q++] = tmp2[--w];
                g_num[q++] = '@';
                uv = (u32)g_notif.pid;
                w = 0;
                while (uv) { u32 d; uv = udiv10(uv, &d); tmp2[w++] = (char)('0' + d); }
                while (w) g_num[q++] = tmp2[--w];
                g_num[q++] = '\n';
                sysc(__NR_write, g_gfd, (lint)g_num, q, 0, 0);
            }
            g_resp.flags = SECCOMP_USER_NOTIF_FLAG_CONTINUE;
            goto reply;
        }
        if (nr == __NR_PROCESS_VM_READV) {
            /* v19: the watchdog's memory scan channel. In v17 the
             * ATTACHes succeeded, ZERO further ptrace requests appeared,
             * yet the scan still detected the tampering — it reads
             * memory via process_vm_readv, which never showed in the
             * ptrace log. DENY it: the scan cannot run. If the TSS
             * fails-open, the engine finally plays; if it fails-closed
             * the death pattern will say so. args: (pid, lvec, liovcnt,
             * rvec, riovcnt, flags) — args[0] = the TARGET pid. */
            if (g_gfd >= 0 && g_plog < 400) {
                lint q = 0, w = 0;
                char tmp2[12];
                u32 uv = (u32)g_notif.data.args[0];
                g_plog++;
                g_num[q++] = 'V';
                g_num[q++] = ':';
                if (uv == 0) tmp2[w++] = '0';
                while (uv) { u32 d; uv = udiv10(uv, &d); tmp2[w++] = (char)('0' + d); }
                while (w) g_num[q++] = tmp2[--w];
                g_num[q++] = '@';
                uv = (u32)g_notif.pid;
                w = 0;
                while (uv) { u32 d; uv = udiv10(uv, &d); tmp2[w++] = (char)('0' + d); }
                while (w) g_num[q++] = tmp2[--w];
                g_num[q++] = '\n';
                sysc(__NR_write, g_gfd, (lint)g_num, q, 0, 0);
            }
            g_resp.error = -1;              /* -EPERM: the scan is blind */
            g_resp.val   = 0;
            g_resp.flags = 0;
            goto reply;
        }
        if (nr == __NR_clone) {
            if (g_gfd >= 0 && g_plog < 400) {
                lint q = 0, w = 0;
                char tmp2[12];
                u32 uv = (u32)g_notif.data.args[0];
                g_plog++;
                g_num[q++] = 'C';
                g_num[q++] = ':';
                if (uv == 0) tmp2[w++] = '0';
                while (uv) { u32 d; uv = udiv10(uv, &d); tmp2[w++] = (char)('0' + d); }
                while (w) g_num[q++] = tmp2[--w];
                g_num[q++] = '@';
                uv = (u32)g_notif.pid;
                w = 0;
                while (uv) { u32 d; uv = udiv10(uv, &d); tmp2[w++] = (char)('0' + d); }
                while (w) g_num[q++] = tmp2[--w];
                g_num[q++] = '\n';
                sysc(__NR_write, g_gfd, (lint)g_num, q, 0, 0);
            }
            g_resp.flags = SECCOMP_USER_NOTIF_FLAG_CONTINUE;
            goto reply;
        }

        if (pclass == PC_STATUS) {
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
            /* file evidence: s<mask>:<tracee pid> — ONE write */
            {
                lint q = 0;
                u32 uv = (u32)g_notif.pid;
                char tmp2[12];
                lint w = 0;
                g_num[q++] = 's';
                g_num[q++] = (char)('0' + (mask & 3));
                g_num[q++] = ':';
                if (uv == 0) g_num[q++] = '0';
                while (uv && w < 11) {
                    u32 d;
                    uv = udiv10(uv, &d);
                    tmp2[w++] = (char)('0' + d);
                }
                while (w) g_num[q++] = tmp2[--w];
                g_num[q++] = '\n';
                sysc(__NR_write, g_gfd, (lint)g_num, q, 0, 0);
            }
        } else if (pclass == PC_MAPS || pclass == PC_MOUNTINFO) {
            /* serve the PRE-OPENED SELF file: /proc/self/maps IS the
             * engine's maps (the TSS's watchdog child asks for OUR pid's
             * maps). Scrub the incriminating lines, hand back a memfd.
             * Cross-process (forked watchdog) replies need ADDFD: the
             * memfd exists only in OUR fd table, the child resolves the
             * returned number in ITS OWN (pre-fork) table. */
            lint src = (pclass == PC_MAPS) ? g_pfd : g_nfd;
            lint m, fd, out;
            sysc(__NR_lseek, src, 0, SEEK_SET, 0, 0);
            m = sysc(__NR_read, src, (lint)g_big,
                     (lint)sizeof(g_big), 0, 0);
            out = 0;
            if (m > 0) {
                if (pclass == PC_MAPS)
                    out = filter_lines(g_big, m, BGSCOMP_MAPSNEEDLE,
                                       (lint)sizeof(BGSCOMP_MAPSNEEDLE) - 1);
                else
                    out = filter_lines(g_big, m, BGSCOMP_MNTNEEDLE,
                                       (lint)sizeof(BGSCOMP_MNTNEEDLE) - 1);
            }
            fd = sysc(__NR_memfd_create, (lint)".bgmp", 0, 0, 0, 0);
            if (fd >= 0 && out > 0) {
                sysc(__NR_write, fd, (lint)g_big, out, 0, 0);
                sysc(__NR_lseek, fd, 0, SEEK_SET, 0, 0);
                if ((u32)g_notif.pid != (u32)g_mypid) {
                    /* forked watchdog: inject the fd into ITS table and
                     * complete the notification atomically. */
                    g_addfd.id = g_notif.id;
                    g_addfd.flags = SECCOMP_ADDFD_FLAG_SEND;
                    g_addfd.srcfd = (u32)fd;
                    g_addfd.newfd = 0;
                    g_addfd.newfd_flags = 0;
                    r = sysc(__NR_ioctl, g_lfd,
                             (lint)SECCOMP_IOCTL_NOTIF_ADDFD,
                             (lint)&g_addfd, 0, 0);
                    if (r >= 0) {
                        sysc(__NR_close, fd, 0, 0, 0, 0);
                        continue;   /* ADDFD+SEND already replied */
                    }
                    log_num("ADDE:", r);
                    /* fall through: reply the (dead-in-child) number
                     * anyway rather than stalling — the child treats a
                     * bad fd like a failed open. */
                    g_resp.val = fd;
                } else {
                    g_resp.val = fd;    /* same fd table (self) */
                }
            } else {
                if (fd >= 0)
                    sysc(__NR_close, fd, 0, 0, 0, 0);
                g_resp.error = -5;      /* -EIO */
            }
            {
                lint q = 0;
                u32 uv = (u32)g_notif.pid;
                char tmp2[12];
                lint w = 0;
                g_num[q++] = (pclass == PC_MAPS) ? 'M' : 'N';
                g_num[q++] = ':';
                while (uv && w < 11) {
                    u32 d;
                    uv = udiv10(uv, &d);
                    tmp2[w++] = (char)('0' + d);
                }
                while (w) g_num[q++] = tmp2[--w];
                g_num[q++] = '\n';
                sysc(__NR_write, g_gfd, (lint)g_num, q, 0, 0);
            }
        } else {
            g_resp.flags = SECCOMP_USER_NOTIF_FLAG_CONTINUE;
#ifdef BGSCOMP_DEBUG_REPLY
            log_str("CNT\n");
#endif
        }

reply:
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
    /* v16: the pre-opened SELF maps/mountinfo serve every /proc/<ourpid>/
     * maps|mountinfo notification (the TSS watchdog child asks for OUR
     * pid's files — same inode, pre-opened before the filter existed). */
    g_pfd = sysc(__NR_openat, AT_FDCWD, (lint)"/proc/self/maps",
                 O_RDONLY, 0, 0);
    g_nfd = sysc(__NR_openat, AT_FDCWD, (lint)"/proc/self/mountinfo",
                 O_RDONLY, 0, 0);
    g_mypid = (int)sysc(__NR_getpid, 0, 0, 0, 0, 0);

    log_str("v16 ctor\n");
    log_num("SFD:", g_sfd);
    log_num("MFD:", g_mfd);
    log_num("PFD:", g_pfd);
    log_num("NFD:", g_nfd);
    log_num("PID:", g_mypid);

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
