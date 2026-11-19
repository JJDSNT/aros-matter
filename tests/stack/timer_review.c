/*
 * timer_review [round|unique|drift|disable|settime|all] - amiga-m68k timer.device
 * against Kal's review of #2305, one test per point. Each prints its counts
 * and "PASS name" or "FAIL name":
 *
 *  round   (1) A CIA-A handler after the e-clock's in one dispatch round
 *          reads GetUpTime(), GetSysTime() and ReadEClock(): none may be
 *          after what the task reads right after the round. The round is
 *          made: in Disable(), wait for the e-clock interrupt to be pending,
 *          set our bit (the TOD alarm's, 2) with SetICR(), Enable().
 *  unique  (2, 3) GetSysTime() from the task in a loop and from a vertical
 *          blank server at the same time: no two of all the readings equal,
 *          and each side's own in order.
 *  drift   (2) a million GetSysTime() calls: the system time must move as
 *          the uptime does (within 5 ms), and tv_micro stay under a second.
 *  disable (5) GetUpTime(), GetSysTime() and ReadEClock() read once a frame
 *          in a Disable() of 16 frames (320 ms PAL; the e-clock wraps every
 *          92 ms), then after it: none may be before the one before it.
 *  settime (4) TR_SETSYSTIME with a fraction, GetSysTime() at once: the
 *          fraction must read back (within 2 ms).
 */
#include <exec/types.h>
#include <exec/interrupts.h>
#include <devices/timer.h>
#include <hardware/custom.h>
#include <hardware/intbits.h>
#include <aros/asmcall.h>
#include <proto/exec.h>
#include <proto/timer.h>
#include <proto/cia.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct Device *TimerBase;
static struct Library *CiaABase;
static int fails;

#define ECLOCK_BIT 1    /* timer.device's e-clock: CIA-A timer B */
#define OUR_BIT    2    /* the TOD alarm's, free on CIA-A */

static LONG us_diff(const struct timeval *a, const struct timeval *b)
{
    return (LONG)(b->tv_secs - a->tv_secs) * 1000000L + ((LONG)b->tv_micro - (LONG)a->tv_micro);
}

static LONG ec_diff(const struct EClockVal *a, const struct EClockVal *b)
{
    return (LONG)(b->ev_lo - a->ev_lo);
}

static void result(int ok, const char *name)
{
    printf("%s %s\n", ok ? "PASS" : "FAIL", name);
    if (!ok)
        fails++;
}

/* 1: round */
static volatile struct timeval h_up, h_sys;
static volatile struct EClockVal h_ec;
static volatile int h_ran;

AROS_INTH1(round_handler, APTR, data)
{
    AROS_INTFUNC_INIT

    GetUpTime((struct timeval *)&h_up);
    GetSysTime((struct timeval *)&h_sys);
    ReadEClock((struct EClockVal *)&h_ec);
    h_ran++;
    return 0;

    AROS_INTFUNC_EXIT
}

static void test_round(void)
{
    struct Interrupt in;
    struct timeval up, sys;
    struct EClockVal ec;
    int i, n = 40, ahead_up = 0, ahead_sys = 0, ahead_ec = 0;
    LONG worst = 0;

    memset(&in, 0, sizeof(in));
    in.is_Node.ln_Type = NT_INTERRUPT;
    in.is_Node.ln_Name = "timer_review";
    in.is_Code = (APTR)round_handler;
    if (AddICRVector(CiaABase, OUR_BIT, &in)) {
        printf("round: CIA-A bit %d taken\n", OUR_BIT);
        result(0, "round");
        return;
    }
    for (i = 0; i < n; i++) {
        int ran = h_ran;
        Disable();
        while (!(SetICR(CiaABase, 0) & (1 << ECLOCK_BIT)))
            ;
        SetICR(CiaABase, 0x80 | (1 << OUR_BIT));
        Enable();
        GetUpTime(&up);
        GetSysTime(&sys);
        ReadEClock(&ec);
        if (h_ran == ran) {
            printf("round: our handler did not run\n");
            break;
        }
        if (us_diff((struct timeval *)&h_up, &up) < 0) {
            ahead_up++;
            if (-us_diff((struct timeval *)&h_up, &up) > worst) worst = -us_diff((struct timeval *)&h_up, &up);
        }
        if (us_diff((struct timeval *)&h_sys, &sys) < 0) ahead_sys++;
        if (ec_diff((struct EClockVal *)&h_ec, &ec) < 0) ahead_ec++;
    }
    RemICRVector(CiaABase, OUR_BIT, &in);
    printf("round: %d rounds, handler ahead of the task after it: uptime %d (largest %ld us), systime %d, eclock %d\n",
        i, ahead_up, (long)worst, ahead_sys, ahead_ec);
    result(i == n && !ahead_up && !ahead_sys && !ahead_ec, "round");
}

/* 2, 3: unique */
#define VB_MAX 2048
#define TASK_MAX 30000
static struct timeval vb_t[VB_MAX];
static volatile int vb_n;
static struct timeval *task_t;

AROS_INTH1(vb_server, APTR, data)
{
    AROS_INTFUNC_INIT

    if (vb_n < VB_MAX) {
        GetSysTime(&vb_t[vb_n]);
        vb_n++;
    }
    return 0;

    AROS_INTFUNC_EXIT
}

static int cmp_tv(const void *a, const void *b)
{
    LONG d = us_diff((const struct timeval *)b, (const struct timeval *)a);
    return d < 0 ? -1 : d > 0;
}

static void test_unique(void)
{
    struct Interrupt in;
    struct timeval *all;
    int i, n, nvb, total, dup = 0, back_task = 0, back_vb = 0, same_task = 0;

    task_t = AllocVec(sizeof(struct timeval) * (TASK_MAX + VB_MAX), MEMF_ANY);
    if (!task_t) { result(0, "unique"); return; }
    memset(&in, 0, sizeof(in));
    in.is_Node.ln_Type = NT_INTERRUPT;
    in.is_Node.ln_Pri = 127;
    in.is_Node.ln_Name = "timer_review";
    in.is_Code = (APTR)vb_server;
    vb_n = 0;
    AddIntServer(INTB_VERTB, &in);
    for (n = 0; n < TASK_MAX; n++)
        GetSysTime(&task_t[n]);
    RemIntServer(INTB_VERTB, &in);
    nvb = vb_n;
    for (i = 1; i < n; i++) {
        LONG d = us_diff(&task_t[i - 1], &task_t[i]);
        if (d < 0) back_task++;
        if (d == 0) same_task++;
    }
    for (i = 1; i < nvb; i++)
        if (us_diff(&vb_t[i - 1], &vb_t[i]) <= 0) back_vb++;
    all = task_t;
    memcpy(&all[n], vb_t, sizeof(struct timeval) * nvb);
    total = n + nvb;
    qsort(all, total, sizeof(struct timeval), cmp_tv);
    for (i = 1; i < total; i++)
        if (!us_diff(&all[i - 1], &all[i])) dup++;
    printf("unique: %d task readings, %d from the vertical blank: %d equal pairs in all (%d of them task after task), task back %d, vblank not after the one before %d\n",
        n, nvb, dup, same_task, back_task, back_vb);
    result(nvb > 10 && !dup && !back_task && !back_vb, "unique");
    FreeVec(task_t);
}

/* 2: drift - GetSysTime() against GetUpTime() over many calls */
static void test_drift(void)
{
    struct timeval s0, u0, s1, u1, t;
    ULONG i, n = 1000000, over = 0;
    LONG d;

    GetSysTime(&s0); GetUpTime(&u0);
    for (i = 0; i < n; i++) {
        GetSysTime(&t);
        if (t.tv_micro >= 1000000) over++;
    }
    GetSysTime(&s1); GetUpTime(&u1);
    d = us_diff(&s0, &s1) - us_diff(&u0, &u1);
    printf("drift: %lu GetSysTime() calls: the system time moved %ld us more than the uptime; %lu readings with tv_micro >= 1000000\n",
        (unsigned long)n, (long)d, (unsigned long)over);
    result(d > -5000 && d < 5000 && !over, "drift");
}

/* 5: disable */
static int frame_wait(void)
{
    volatile struct Custom *c = (struct Custom *)0xdff000;
    UWORD v, prev = ((c->vposr & 1) << 8) | (c->vhposr >> 8);
    for (;;) {
        v = ((c->vposr & 1) << 8) | (c->vhposr >> 8);
        if (v < prev && prev - v > 100)
            return 1;
        prev = v;
    }
}

#define FRAMES 16
static void test_disable(void)
{
    struct timeval up[FRAMES + 2], sys[FRAMES + 2];
    struct EClockVal ec[FRAMES + 2];
    int r, i, back_up = 0, back_sys = 0, back_ec = 0;
    LONG worst = 0;

    for (r = 0; r < 5; r++) {
        Disable();
        for (i = 0; i <= FRAMES; i++) {
            GetUpTime(&up[i]);
            GetSysTime(&sys[i]);
            ReadEClock(&ec[i]);
            if (i < FRAMES)
                frame_wait();
        }
        Enable();
        GetUpTime(&up[i]);
        GetSysTime(&sys[i]);
        ReadEClock(&ec[i]);
        for (i = 1; i <= FRAMES + 1; i++) {
            LONG d = us_diff(&up[i - 1], &up[i]);
            if (d < 0) { back_up++; if (-d > worst) worst = -d; }
            if (us_diff(&sys[i - 1], &sys[i]) < 0) back_sys++;
            if (ec_diff(&ec[i - 1], &ec[i]) < 0) back_ec++;
        }
    }
    printf("disable: 5 x %d frames, readings before the one before: uptime %d (largest %ld us), systime %d, eclock %d\n",
        FRAMES, back_up, (long)worst, back_sys, back_ec);
    result(!back_up && !back_sys && !back_ec, "disable");
}

/* 4: settime */
static void test_settime(struct timerequest *tr)
{
    static const ULONG fr[] = { 0, 250000, 500000, 750000, 999000 };
    struct timeval now, keep;
    int i, bad = 0;

    GetSysTime(&keep);
    for (i = 0; i < 5; i++) {
        LONG d;
        tr->tr_node.io_Command = TR_SETSYSTIME;
        tr->tr_time.tv_secs = keep.tv_secs + 100 + i;
        tr->tr_time.tv_micro = fr[i];
        DoIO((struct IORequest *)tr);
        GetSysTime(&now);
        d = (LONG)(now.tv_secs - (keep.tv_secs + 100 + i)) * 1000000L + (LONG)now.tv_micro - (LONG)fr[i];
        printf("settime: set %lu.%06lu, read %lu.%06lu (%ld us)\n",
            (unsigned long)(keep.tv_secs + 100 + i), (unsigned long)fr[i],
            (unsigned long)now.tv_secs, (unsigned long)now.tv_micro, (long)d);
        if (d < 0 || d > 2000) bad++;
    }
    tr->tr_node.io_Command = TR_SETSYSTIME;
    tr->tr_time = keep;
    DoIO((struct IORequest *)tr);
    result(!bad, "settime");
}

int main(int argc, char **argv)
{
    struct timerequest tr;
    const char *what = argc > 1 ? argv[1] : "all";
    int all = !strcmp(what, "all");

    if (OpenDevice("timer.device", UNIT_MICROHZ, (struct IORequest *)&tr, 0) != 0)
        return 20;
    TimerBase = tr.tr_node.io_Device;
    CiaABase = OpenResource("ciaa.resource");
    if (all || !strcmp(what, "round")) test_round();
    if (all || !strcmp(what, "unique")) test_unique();
    if (all || !strcmp(what, "drift")) test_drift();
    if (all || !strcmp(what, "disable")) test_disable();
    if (all || !strcmp(what, "settime")) test_settime(&tr);
    printf("timer_review: %d failed\n", fails);
    CloseDevice((struct IORequest *)&tr);
    return fails ? 5 : 0;
}
