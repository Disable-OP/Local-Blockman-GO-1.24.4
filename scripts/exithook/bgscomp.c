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
#define __NR_gettid      186L
#define __NR_mmap          9L
#define __NR_pidfd_open   434L
#define __NR_pidfd_getfd  438L
#define __NR_getppid      110L
#define __NR_fcntl        72L
#define __NR_readlinkat  267L
#define __NR_ptrace      101L
#define __NR_kill         62L
#define __NR_clock_gettime 228L
#define __NR_rt_sigqueueinfo 129L
#define __NR_rt_sigaction   13L
#define __NR_tkill       200L
#define __NR_tgkill      234L
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
#define BPF_NR_KILL       62
#define BPF_NR_TKILL     200
#define BPF_NR_TGKILL    234
#define BPF_NR_SIGQUEUE  129
#define BPF_NR_CLONE     56
#define BPF_NR_SECCOMP   317

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

static inline lint sysc6(lint n, lint a, lint b, lint c, lint d, lint e,
                         lint f)
{
    register lint rdi __asm__("rdi") = a;
    register lint rsi __asm__("rsi") = b;
    register lint rdx __asm__("rdx") = c;
    register lint r10 __asm__("r10") = d;
    register lint r8  __asm__("r8")  = e;
    register lint r9  __asm__("r9")  = f;
    register lint rax __asm__("rax") = n;
    __asm__ volatile ("syscall"
                      : "=a" (rax)
                      : "a" (rax), "D" (rdi), "S" (rsi), "d" (rdx),
                        "r" (r10), "r" (r8), "r" (r9)
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
#define __NR_getpid       20L
#define __NR_gettid      224L
#define __NR_mmap         192L
#define __NR_pidfd_open   434L
#define __NR_pidfd_getfd  438L
#define __NR_getppid       64L
#define __NR_fcntl        55L
#define __NR_readlinkat  332L
#define __NR_ptrace      26L
#define __NR_kill         37L
#define __NR_clock_gettime 263L
#define __NR_rt_sigqueueinfo 265L
#define __NR_rt_sigaction  174L
#define __NR_tkill       238L
#define __NR_tgkill      268L
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
#define BPF_NR_KILL       37
#define BPF_NR_TKILL     238
#define BPF_NR_TGKILL    268
#define BPF_NR_SIGQUEUE  265
#define BPF_NR_CLONE     120
#define BPF_NR_SECCOMP   383

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

/* 6-arg arm32 EABI: args r0-r5, nr in r7. */
static inline lint sysc6(lint n, lint a, lint b, lint c, lint d, lint e,
                         lint f)
{
    register lint r0 __asm__("r0") = a;
    register lint r1 __asm__("r1") = b;
    register lint r2 __asm__("r2") = c;
    register lint r3 __asm__("r3") = d;
    register lint r4 __asm__("r4") = e;
    register lint r5 __asm__("r5") = f;
    register lint r7 __asm__("r7") = n;
    __asm__ volatile ("svc #0"
                      : "=r" (r0)
                      : "r" (r0), "r" (r1), "r" (r2), "r" (r3), "r" (r4),
                        "r" (r5), "r" (r7)
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
#define PR_SET_DUMPABLE       6L
#define PR_SET_PTRACER  0x59616d61L
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
#ifndef BGSCOMP_CHILDLOG
#define BGSCOMP_CHILDLOG "/data/local/tmp/childlog.txt"
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
/* v36: io_uring (425/426/427) moved from ERRNO(ENOSYS) to USER_NOTIF.  */
/* EVIDENCE (runs 38237179615/wip-104 + 38241104113/wip-105): the TSS    */
/* ctor SIGILLs at libBlockMan+0x169d14 inside call_constructors at the   */
/* join-time dlopen, and the supervisor served ZERO /proc opens from it   */
/* (no P:/s: lines in either run) — the ctor's checks do NOT go through   */
/* the open* channel, so the status scrub can never satisfy them. The     */
/* only REMAINING behavioral delta a packed check can observe is a        */
/* syscall this filter denies or changes: io_uring_setup -> ENOSYS is     */
/* the prime suspect (the engine family itself uses io_uring; an          */
/* availability probe returning -ENOSYS in an io_uring-capable kernel is  */
/* exactly a tamper signal). v36 lets io_uring through with a USER_NOTIF  */
/* notification: the supervisor logs it (I:<nr>@<pid>) and CONTINUEs —    */
/* byte-for-byte the clean-system behavior, full visibility, and the      */
/* openat-bypass risk is accepted because this build's TSS demonstrably   */
/* never opens /proc at all.                                              */
/* ------------------------------------------------------------------ */

static const struct sock_filter bpf15[] = {
    { 0x20, 0,  0,  4           },   /*  0 LD [4]  arch        */
    { 0x15, 0, 29,  AUDIT_ARCH_THIS },  /*  1 JEQ arch jt=0 jf=29 (ALLOW=31) */
    { 0x20, 0,  0,  0           },   /*  2 LD [0]  nr          */
    { 0x15, 24, 0,  BPF_NR_OPENAT },  /*  3 openat  -> 28       */
    { 0x15, 23, 0,  BPF_NR_OPEN },    /*  4 open    -> 28       */
    { 0x15, 22, 0,  BPF_NR_OPENAT2 }, /*  5 openat2 -> 28       */
    { 0x15, 17, 0,  BPF_NR_PRCTL },   /*  6 prctl   -> 24       */
    { 0x15, 11, 0,  BPF_NR_EXITGROUP }, /*  7 exit_gr -> 19     */
    { 0x15, 10, 0,  BPF_NR_EXIT },    /*  8 exit    -> 19       */
    { 0x15, 18, 0,  425         },   /*  9 io_uring_setup -> 28 (v36: NOTIFY) */
    { 0x15, 17, 0,  426         },   /* 10 io_uring_enter -> 28 (v36: NOTIFY) */
    { 0x15, 16, 0,  427         },   /* 11 io_uring_reg   -> 28 (v36: NOTIFY) */
    { 0x15, 15, 0,  BPF_NR_PTRICE },  /* 12 ptrace  -> 28       */
    { 0x15, 14, 0,  BPF_NR_CLONE },   /* 13 clone   -> 28       */
    { 0x15, 13, 0,  BPF_NR_VMREADV }, /* 14 vm_readv -> 28       */
    { 0x15, 12, 0,  BPF_NR_KILL },    /* 15 kill    -> 28       */
    { 0x15, 11, 0,  BPF_NR_TGKILL },  /* 16 tgkill  -> 28       */
    { 0x15, 10, 0,  BPF_NR_TKILL },   /* 17 tkill   -> 28       */
    { 0x15, 9,  0,  BPF_NR_SIGQUEUE }, /* 18 sigqueue -> 28 / 19 (seccomp) */
    { 0x15, 8,  0,  BPF_NR_SECCOMP }, /* 19 seccomp  -> 28 (v37: NOTIFY) */
    { 0x20, 0,  0,  16          },   /* 20 LD [16] args0.lo    */
    { 0x15, 7,  0,  25          },   /* 21 ==25 -> 29          */
    { 0x15, 6,  0,  30          },   /* 22 ==30 -> 29          */
    { 0x05, 0,  0,  7           },   /* 23 JA -> 31            */
    { 0x20, 0,  0,  16          },   /* 24 LD [16] option      */
    { 0x15, 4,  0,  21          },   /* 25 PR_GET_SECCOMP->30  */
    { 0x15, 3,  0,  36          },   /* 26 PR_GET_NNP    ->30  */
    { 0x05, 0,  0,  3           },   /* 27 JA -> 31            */
    { 0x06, 0,  0,  0x7FC00000U },   /* 28 RET USER_NOTIF      */
    { 0x06, 0,  0,  0x00050026U },   /* 29 RET ERRNO(ENOSYS)   */
    { 0x06, 0,  0,  0x00050000U },   /* 30 RET ERRNO(0)        */
    { 0x06, 0,  0,  0x7FFF0000U },   /* 31 RET ALLOW           */
};

/* bpf14 (fallback): the v14 filter + the v37 seccomp(GET_MODE) fake —
 * ERRNO(ENOSYS) on the verdict exits, ERRNO(0) on seccomp(GET_MODE) and
 * the prctl GET fakes, NO USER_NOTIF (a listener-less process must never
 * return USER_NOTIF from a filter). 22 instructions. The arm64 nr
 * entries (93/94/167) stay literal: they are belt-and-braces for the
 * 64-bit edge case on the arm build and inert elsewhere. */
static const struct sock_filter bpf14[] = {
    { 0x20, 0,  0,  0           },   /*  0 LD [0] nr           */
    { 0x15, 3,  0,  BPF_NR_EXIT },    /*  1 arm32 exit    -> 5  */
    { 0x15, 2,  0,  93          },   /*  2 arm64 exit    -> 5  */
    { 0x15, 1,  0,  94          },   /*  3 arm64 exit_gr -> 5  */
    { 0x15, 0,  5,  BPF_NR_EXITGROUP }, /*  4 arm32 exit_gr -> 5 / 10 */
    { 0x20, 0,  0,  16          },   /*  5 LD [16] args0       */
    { 0x15, 2,  0,  25          },   /*  6 ==25 -> 9           */
    { 0x15, 1,  0,  30          },   /*  7 ==30 -> 9           */
    { 0x05, 0,  0,  12          },   /*  8 JA -> 21 (harmless exit ALLOW) */
    { 0x06, 0,  0,  0x00050026U },   /*  9 RET ERRNO(ENOSYS)   */
    { 0x15, 0,  2,  BPF_NR_SECCOMP }, /* 10 seccomp -> 11 / 13 (v37) */
    { 0x20, 0,  0,  16          },   /* 11 LD [16] args0       */
    { 0x15, 7,  0,  2           },   /* 12 GET_MODE(2) -> 20 (v37 fake) */
    { 0x15, 1,  0,  167         },   /* 13 arm64 prctl -> 15   */
    { 0x15, 0,  6,  BPF_NR_PRCTL },   /* 14 arm32 prctl -> 15 / 21 */
    { 0x20, 0,  0,  16          },   /* 15 LD [16] option      */
    { 0x15, 3,  0,  21          },   /* 16 GET_SECCOMP -> 20   */
    { 0x15, 2,  0,  36          },   /* 17 GET_NNP     -> 20   */
    { 0x05, 0,  0,  2           },   /* 18 JA -> 21 (ALLOW)    */
    { 0x05, 0,  0,  1           },   /* 19 JA -> 21 (filler)   */
    { 0x06, 0,  0,  0x00050000U },   /* 20 RET ERRNO(0)        */
    { 0x06, 0,  0,  0x7FFF0000U },   /* 21 RET ALLOW           */
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
static int g_suptid = 0; /* the supervisor thread's tid — the watchdog must never stop it */
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

/* millis since boot (CLOCK_MONOTONIC) — stamps every guardlog line so
 * the CI can order the TSS's attach/stop timeline against the watch
 * rounds. clock_gettime is ALLOWed by the filter (never notified). */
static void log_stamp(void)
{
    struct { long long sec; long long nsec; } ts;
    lint q = 0, w = 0;
    u64 ms;
    char tmp2[16];
    lint cr;

    if (g_gfd < 0)
        return;
    ts.sec = 0;
    ts.nsec = 0;
    cr = sysc(__NR_clock_gettime, 1L /* MONOTONIC */, (lint)&ts, 0, 0, 0);
    if (cr != 0)
        return;                 /* no stamp rather than garbage */
    /* u64 ms = sec*1000 + nsec/1e6 — NO 64-bit division anywhere (gcc
     * would emit __aeabi_uldivmod, an undefined symbol in a -nostdlib
     * .so: v21's dlopen failure). sec*1000 via shifts+adds; nsec/1e6
     * via shift-subtract; the digit loop is 64-bit shift-subtract. */
    {
        u64 sec1000 = (u64)ts.sec;
        int i;
        u64 t2 = 0, r2 = 0;
        for (i = 3; i > 0; i--) sec1000 += sec1000 << 2;  /* *5 */
        sec1000 <<= 3;                                    /* *8 => *40 */
        t2 = 0; r2 = 0;
        for (i = 63; i >= 0; i--) {
            r2 = (r2 << 1) | (u64)((u64)ts.nsec >> i & 1u);
            if (r2 >= 1000000u) { r2 -= 1000000u; t2 |= ((u64)1 << i); }
        }
        ms = sec1000 + t2;
    }
    if (ms == 0) {
        tmp2[w++] = '0';
    }
    while (ms) {
        u64 q10 = 0, r10 = 0;
        int i;
        for (i = 63; i >= 0; i--) {
            r10 = (r10 << 1) | (u64)((ms >> i) & 1u);
            if (r10 >= 10) { r10 -= 10; q10 |= ((u64)1 << i); }
        }
        tmp2[w++] = (char)('0' + (u32)r10);
        ms = q10;
    }
    while (w) g_num[q++] = tmp2[--w];
    g_num[q++] = ' ';
    sysc(__NR_write, g_gfd, (lint)g_num, q, 0, 0);
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

static void log_num(const char *tag, lint v);

/* ------------------------------------------------------------------ */
/* v38: the SIGILL trap-skipper.                                       */
/*                                                                     */
/* EVIDENCE CHAIN (wip-104/105/106/107 — runs 38237179615,             */
/* 38241104113, 38244681621, 38247471065): the engine always dies at   */
/* libBlockMan+0x169d14, SIGILL ILL_ILLOPC, in linker                  */
/* call_constructors <- do_dlopen — ~0.8s after the join-time dlopen   */
/* starts. Every syscall-probe hypothesis is EXONERATED (the           */
/* supervisor served zero /proc opens, zero io_uring, zero seccomp     */
/* notifications across all four runs; prctl(21/36) and seccomp-       */
/* GET_MODE were faked consistently by v37). The wip-107 tombstone's   */
/* memory-near-pc shows RUNTIME bytes that are STILL undefined         */
/* opcodes (trap garbage), and lr points INSIDE the linker's           */
/* call_constructors — the faulting "function" IS an init_array ctor   */
/* entry (r10 = 0x969 = 2409 = the ctor index) whose decrypted body    */
/* is a deliberate trap page. Reading: the TSS verdict path runs       */
/* exit(25|30) -> our filter ENOSYSes it -> the verdict code           */
/* continues into a trap page (or the ctor list contains a decoy       */
/* trap entry). Either way the SIGILL is a CALL-site recoverable at    */
/* lr: skipping the faulting ctor lets call_constructors continue      */
/* the list and the dlopen complete.                                   */
/*                                                                     */
/* The handler edits the ucontext: arm_pc := arm_lr (the caller's      */
/* resume point in the linker), logs S:<pc>@<tid> to the guardlog,     */
/* and returns through a hand-rolled rt_sigreturn restorer (bare       */
/* -nostdlib: no libc trampoline). Installed at libbgscomp load        */
/* (+4.2s) — long before the join-time dlopen.                         */
/* ------------------------------------------------------------------ */
#if !defined(__x86_64__)

#define SA_RESTORER_  0x04000000u
#define SA_SIGINFO_   0x00000004u
#define SA_RESTART_   0x10000000u

/* the sigreturn trampoline the kernel jumps to when the handler
 * returns — mov r7,#173 (rt_sigreturn); svc #0 */
__asm__(".text\n.align 2\n.globl sigill_restorer\n.type sigill_restorer,%function\n"
        "sigill_restorer:\n"
        "  mov r7, #173\n"
        "  svc #0\n");
void sigill_restorer(void);

/* arm32 sigcontext offsets inside ucontext_t:
 * uc_flags(0) uc_link(4) uc_stack(8..19) uc_mcontext(20..91)
 *   sigcontext: trap_no(20) error_code(24) oldmask(28)
 *   arm_r0(32) r1(36) r2(40) r3(44) r4(48) r5(52) r6(56) r7(60)
 *   r8(64) r9(68) r10(72) fp(76) ip(80) sp(84) lr(88) pc(92)
 *   cpsr(96) fault_address(100) */
#define UC_ARM_LR  88
#define UC_ARM_PC  92

static volatile unsigned long g_sigill_fires = 0;

static void sigill_skip(int sig, void *si, void *ucv)
{
    unsigned char *uc = (unsigned char *)ucv;
    volatile unsigned long *lr = (volatile unsigned long *)(uc + UC_ARM_LR);
    volatile unsigned long *pc = (volatile unsigned long *)(uc + UC_ARM_PC);
    unsigned long fault = *pc;
    lint q = 0, w = 0;
    char tmp2[12];
    u32 uv;

    (void)sig; (void)si;
    g_sigill_fires++;
    *pc = *lr;      /* resume the CALLER of the faulting ctor */
    if (g_gfd >= 0 && g_plog < 1500) {
        g_plog++;
        g_num[q++] = 'S';
        g_num[q++] = ':';
        uv = (u32)fault;
        if (uv == 0) tmp2[w++] = '0';
        while (uv) { u32 d; uv = udiv10(uv, &d); tmp2[w++] = (char)('0' + d); }
        while (w) g_num[q++] = tmp2[--w];
        g_num[q++] = '\n';
        sysc(__NR_write, g_gfd, (lint)g_num, q, 0, 0);
    }
}

static void install_sigill_skipper(void)
{
    /* kernel_sigaction on arm32: handler, flags, restorer, mask(8B) */
    struct {
        unsigned long handler;
        unsigned long flags;
        void *restorer;
        unsigned long mask[2];
    } act, old;
    lint r;

    act.handler = (unsigned long)sigill_skip;
    act.flags = SA_SIGINFO_ | SA_RESTORER_ | SA_RESTART_;
    act.restorer = (void *)sigill_restorer;
    act.mask[0] = 0; act.mask[1] = 0;
    r = sysc(__NR_rt_sigaction, 4 /* SIGILL */, (lint)&act, (lint)&old,
             8 /* sigsetsize */, 0);
    log_num("SILL:", r);
}

#else  /* x86_64 host selftest: no trap-skipper needed */

static void install_sigill_skipper(void)
{
    log_str("SILL:skip(x86)\n");
}

#endif  /* !__x86_64__ */

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
        if (pclass != PC_NONE && g_gfd >= 0 && g_plog < 1500) {
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
            /* v24: PURE LOGGING. The supervisor now lives in a SEPARATE
             * PROCESS (forked AFTER the install — it inherits the filter
             * and the listener fd, and the notification queue is shared
             * through the refcounted filter object). The watchdog
             * enumerates the ENGINE's threads only — the supervisor
             * process is invisible to it, so every attach can complete
             * and the umbrella finishes (v18/v22/v23: any interference
             * with the attach protocol aborts the TSS init). */
            if (g_gfd >= 0 && g_plog < 1500) {
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
        if (nr == __NR_clone) {
            if (g_gfd >= 0 && g_plog < 1500) {
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
        /* v36: io_uring (425/426/427) — NOTIFY + log + CONTINUE. The
         * engine family probes/uses io_uring; the clean-system behavior
         * is "succeeds". Log it (I:<nr>@<pid>, capped) so the next run
         * PROVES whether the ctor's detection path touches io_uring. */
        if (nr == 425 || nr == 426 || nr == 427) {
            if (g_gfd >= 0 && g_plog < 1500) {
                lint q = 0, w = 0;
                char tmp2[12];
                u32 uv = (u32)nr;
                g_plog++;
                g_num[q++] = 'I';
                g_num[q++] = ':';
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

        /* v37: seccomp(2) — THE filter-detection probe. SECCOMP_GET_MODE
         * (flag 2) on a filtered process returns 2 (filter mode); the
         * prctl(PR_GET_SECCOMP) fake alone left THIS channel answering
         * the real value — and a detector comparing both (they must be
         * consistent on a clean system) or just probing GET_MODE caught
         * the filter in EVERY filter-era run (the ctor SIGILL at
         * libBlockMan+0x169d14, zero /proc opens, zero io_uring calls —
         * the only observable deltas left were exit-block + GET_MODE).
         * Fake: GET_MODE -> returns 0 (= SECCOMP_MODE_DISABLED, the
         * clean-system answer, consistent with the prctl(21) fake).
         * Everything else (SET_MODE_FILTER etc.) CONTINUEs for real. */
        if (nr == BPF_NR_SECCOMP) {
            if (g_gfd >= 0 && g_plog < 1500) {
                lint q = 0, w = 0;
                char tmp2[12];
                u32 uv = (u32)g_notif.data.args[0];
                g_plog++;
                g_num[q++] = 'G';
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
            if ((u32)g_notif.data.args[0] == 2) {
                /* SECCOMP_GET_MODE -> "0" (disabled): val=0, error=0,
                 * flags=0 — the syscall RETURNS 0, no CONTINUE. */
                g_resp.val   = 0;
                g_resp.error = 0;
                g_resp.flags = 0;
                goto reply;
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
                    /* v30: a plain val reply would resolve in the
                     * CALLER's table — for a cross-process notification
                     * that is a bogus fd (the host o2read=-9 case).
                     * Reply a CLEAN failure instead. */
                    sysc(__NR_close, fd, 0, 0, 0, 0);
                    g_resp.val = 0;
                    g_resp.error = -5;      /* -EIO */
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

/* v24: raw fork via clone(SIGCHLD) — per-ABI inline asm (the x86_64
 * host-test build must compile too). */
#if defined(__x86_64__)
static lint fork_process(void)
{
    register lint rdi __asm__("rdi") = 0x11L;   /* SIGCHLD */
    register lint rsi __asm__("rsi") = 0;
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
static lint fork_process(void)
{
    register lint r0 __asm__("r0") = 0x11L;     /* SIGCHLD */
    register lint r1 __asm__("r1") = 0;
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

/* v24b: the supervisor process is forked BEFORE the install (a notified
 * clone could NEVER be served by a supervisor that does not exist yet —
 * the v24 self-deadlock). The child inherits the filter at fork and
 * waits for the listener fd number on a MAP_SHARED page. */
struct bgshm { volatile int lfd; volatile int ready; };
static struct bgshm *g_shm;

static void supervisor_child(void)
{
    struct { long s; long ns; } ts;
    char pbuf[48];
    lint pp, w2 = 0;
    u32 uv = (u32)sysc(__NR_getppid, 0, 0, 0, 0, 0);
    char t3[12];
    lint l = -1;

    /* v28: the child logs to its OWN file (the inherited guardlog fd
     * did not land — root cause irrelevant now, the childlog is proven)
     * and coordinates through the guardlog's LSTFD line. The listener
     * is validated WITHOUT consuming a notification: readlinkat of the
     * parent's /proc/<ppid>/fd/<n> must say "anon_inode:[seccomp..."
     * (the v26/v27 RECV probe ORPHANED the parent's first pending
     * notification and hung it forever). */
    g_gfd = sysc(__NR_openat, AT_FDCWD, (lint)BGSCOMP_CHILDLOG,
                 O_WRONLY | O_APPEND | O_CREAT, 0666L, 0);
    log_str("CH0 spawned\n");

    pp = 0;
    { static const char pre[7] = "/proc/";
      lint i2; for (i2 = 0; i2 < 6; i2++) pbuf[pp++] = pre[i2]; }
    if (uv == 0) t3[w2++] = '0';
    while (uv) { u32 d; uv = udiv10(uv, &d); t3[w2++] = (char)('0' + d); }
    while (w2) pbuf[pp++] = t3[--w2];
    pbuf[pp++] = '/';
    { lint dirbase = pp;   /* "/proc/<ppid>/fd/" prefix len */
      (void)dirbase; }

    for (;;) {
        lint lg = sysc(__NR_openat, AT_FDCWD, (lint)BGSCOMP_LOGPATH,
                       O_RDONLY, 0, 0);
        if (lg >= 0) {
            char buf[4096];
            lint n = sysc(__NR_read, lg, (lint)buf, (lint)sizeof(buf), 0, 0);
            sysc(__NR_close, lg, 0, 0, 0, 0);
            if (n > 0) {
                /* v34: the needle is LSTFD:<MY-PPID>: — the shared log
                 * carries every fleet's line; matching the pid prefix
                 * picks OUR parent's listener only. */
                char nd[24];
                lint nlen = 0, w4 = 0;
                u32 u4 = (u32)sysc(__NR_getppid, 0, 0, 0, 0, 0);
                static const char hdr[7] = "LSTFD:";
                lint i, j;
                for (i = 0; i < 6; i++) nd[nlen++] = hdr[i];
                if (u4 == 0) t3[w4++] = '0';
                while (u4) { u32 d; u4 = udiv10(u4, &d); t3[w4++] = (char)('0' + d); }
                while (w4) nd[nlen++] = t3[--w4];
                nd[nlen++] = ':';
                for (i = n - nlen; i >= 0; i--) {
                    int hit = 1;
                    for (j = 0; j < nlen; j++)
                        if (buf[i + j] != nd[j]) { hit = 0; break; }
                    if (hit) {
                        lint v = 0;
                        int any = 0;
                        for (j = i + nlen; j < n && buf[j] >= '0' &&
                                        buf[j] <= '9'; j++) {
                            v = v * 10 + (buf[j] - '0');
                            any = 1;
                        }
                        if (any && v > 2 && v < 1024)
                            l = v;
                        break;
                    }
                }
            }
        }
        if (l >= 0)
            break;
        ts.s = 0;
        ts.ns = 2000000L;
        sysc(__NR_nanosleep, (lint)&ts, 0, 0, 0, 0);
    }
    log_num("CH1 lstfd:", l);

    { lint tries = 0;
    for (;;) {
        lint pdf = sysc(__NR_pidfd_open,
                        sysc(__NR_getppid, 0, 0, 0, 0, 0), 0, 0, 0, 0);
        if ((++tries & 127) == 0) {     /* power of 2: NO division helper */
            log_num("CH8p:", pdf);
        }
        if (pdf >= 0) {
            lint cand = sysc(__NR_pidfd_getfd, pdf, (lint)l, 0, 0, 0);
            sysc(__NR_close, pdf, 0, 0, 0, 0);
            if (tries == 1)
                log_num("CH8c:", cand);
            if (cand >= 0) {
                /* validate WITHOUT consuming: readlink the parent's
                 * /proc/<ppid>/fd/<l> — a seccomp listener reads back
                 * "anon_inode:[seccomp notify" */
                char lbuf[64];
                char path2[48];
                lint q2 = 0, w3 = 0;
                u32 u3 = (u32)l;
                char t4[12];
                static const char pre2[7] = "/proc/";
                lint i3;
                for (i3 = 0; i3 < 6; i3++) path2[q2++] = pre2[i3];
                u3 = (u32)sysc(__NR_getppid, 0, 0, 0, 0, 0);
                w3 = 0;
                while (u3) { u32 d; u3 = udiv10(u3, &d); t4[w3++] = (char)('0' + d); }
                while (w3) path2[q2++] = t4[--w3];
                path2[q2++] = '/';   /* /proc/<ppid>/fd/<n> */
                path2[q2++] = 'f';
                path2[q2++] = 'd';
                path2[q2++] = '/';
                u3 = (u32)l; w3 = 0;
                while (u3) { u32 d; u3 = udiv10(u3, &d); t4[w3++] = (char)('0' + d); }
                while (w3) path2[q2++] = t4[--w3];
                path2[q2] = 0;
                { lint rl = sysc(__NR_readlinkat, AT_FDCWD, (lint)path2,
                                 (lint)lbuf, (lint)sizeof(lbuf) - 1, 0);
                  if (tries < 4) {
                      lbuf[40] = 0;
                      log_num("CH8r:", rl);
                      log_str("CH8t:");
                      sysc(__NR_write, g_gfd, (lint)path2,
                           slen(path2), 0, 0);
                      log_str("\n");
                  }
                  if (rl >= 18) {
                      static const char want[19] =
                          "anon_inode:seccomp";
                      lint k, hit = 1;
                      for (k = 0; k < 18; k++)
                          if (lbuf[k] != want[k]) { hit = 0; break; }
                      if (hit) {
                          g_lfd = (int)cand;
                          log_num("CH2 serving fd:", g_lfd);
                          supervisor_loop();   /* NEVER returns */
                      }
                  } }
            }
        }
        l = -1;
        ts.s = 0;
        ts.ns = 2000000L;
        sysc(__NR_nanosleep, (lint)&ts, 0, 0, 0, 0);
    }
    } /* tries */
}

/* ------------------------------------------------------------------ */
/* the constructor                                                     */
/* ------------------------------------------------------------------ *//* ------------------------------------------------------------------ */
/* the constructor                                                     */
/* ------------------------------------------------------------------ *//* ------------------------------------------------------------------ */
/* the constructor                                                     */
/* ------------------------------------------------------------------ *//* ------------------------------------------------------------------ */
/* the constructor                                                     */
/* ------------------------------------------------------------------ */

__attribute__((constructor, visibility("default")))
void bgscomp_ctor(void)
{
    struct sock_fprog p15;
    struct sock_fprog p14;
    lint r;

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

    /* v38: the SIGILL trap-skipper — armed BEFORE the TSS ever runs
     * (libbgscomp loads at the delayed-arm time; the join-time dlopen
     * of libBlockMan comes tens of seconds later). */
    install_sigill_skipper();

    /* NNP FIRST: no_new_privs is a PER-TASK flag (inherited at clone from
     * the CURRENT value). The supervisor must ALREADY carry it when TSYNC
     * walks the thread group, or the sync fails (-EINVAL on the whole
     * install). So: NNP -> spawn -> install. */
    /* v26: fork the supervisor BEFORE anything is notified. The child is
     * UNFILTERED (forked pre-install — it cannot even self-notify) and
     * DISCOVERS the listener by probing the parent's /proc/<ppid>/fd
     * entries once the install lands (see supervisor_child). The
     * notification queue lives in the filter object behind that fd, and
     * the kernel delivers every notification — the TSYNC'd engine
     * threads' included — to whichever task holds the fd. */
    {
        lint fk = fork_process();
        if (fk == 0)
            supervisor_child();         /* the child — forever */
        /* v33: LEGALIZE the child's pidfd_getfd. The TSS names its own
         * watchdog with PR_SET_PTRACER (that is why ITS attaches pass
         * while our child's pull returned -EPERM); do the same for the
         * supervisor, and restore dumpable in case the zygote/TSS
         * cleared it (the dumpable gate is the other half of
         * PTRACE_MODE_ATTACH_REALCREDS). */
        sysc(__NR_prctl, PR_SET_PTRACER, fk, 0, 0, 0);
        sysc(__NR_prctl, PR_SET_DUMPABLE, 1, 0, 0, 0);
        log_num("SUPF:", fk);
    }

    r = sysc(__NR_prctl, PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0);
    log_num("NNP:", r);
    if (r != 0)
        goto fallback;          /* no NNP => no filter install at all */

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
        /* the child parses THIS line — the pid prefix makes it
         * unambiguous with MULTIPLE :BlockmanGo processes sharing the
         * log (the v33 fleet bug: a child grabbed ANOTHER fleet's fd
         * number -> EBADF forever). */
        {
            lint q = 0, w = 0;
            char t5[12];
            u32 uv = (u32)g_mypid;
            g_num[q++] = 'L'; g_num[q++] = 'S'; g_num[q++] = 'T';
            g_num[q++] = 'F'; g_num[q++] = 'D'; g_num[q++] = ':';
            if (uv == 0) t5[w++] = '0';
            while (uv) { u32 d; uv = udiv10(uv, &d); t5[w++] = (char)('0' + d); }
            while (w) g_num[q++] = t5[--w];
            g_num[q++] = ':';
            uv = (u32)g_lfd; w = 0;
            while (uv) { u32 d; uv = udiv10(uv, &d); t5[w++] = (char)('0' + d); }
            while (w) g_num[q++] = t5[--w];
            g_num[q++] = '\n';
            sysc(__NR_write, g_gfd, (lint)g_num, q, 0, 0);
        }
        /* v24b: the supervisor is a SEPARATE PROCESS (forked pre-install,
         * woken here) — the watchdog enumerates /proc/<engine>/task which
         * will NEVER contain it: it cannot stop what serves the replies.
         * The child holds the inherited listener fd; the kernel delivers
         * EVERY notification (from any task sharing the filter — TSYNC'd
         * engine threads included) to that one queue. */
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
