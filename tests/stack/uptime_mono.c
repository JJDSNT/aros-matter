/*
 * uptime_mono [SECS] - whether timer.device's GetUpTime() (and GetSysTime())
 * only goes forward (B73). For SECS seconds (default 20) of uptime it reads
 * each clock over and over and counts the readings that went back from the
 * one before, and those more than half a second ahead of it, printing the
 * first few of each:
 *   "uptime: N reads, B back (largest X us), F jumps (largest Y us)"
 *   "  back 12.999998 -> 12.000003"
 * A clock that is monotonic has B = 0 and F = 0.
 */
#include <exec/types.h>
#include <devices/timer.h>
#include <proto/exec.h>
#include <proto/timer.h>
#include <stdio.h>
#include <stdlib.h>

struct Device *TimerBase;

static LONG us_diff(const struct timeval *a, const struct timeval *b)
{
    return (LONG)(b->tv_secs - a->tv_secs) * 1000000L + ((LONG)b->tv_micro - (LONG)a->tv_micro);
}

static void run(const char *name, int up, ULONG secs)
{
    struct timeval prev, now, start;
    ULONG reads = 0, back = 0, jump = 0, shown = 0;
    LONG worst_back = 0, worst_jump = 0;

    if (up) GetUpTime(&prev); else GetSysTime(&prev);
    start = prev;
    for (;;) {
        LONG d;

        if (up) GetUpTime(&now); else GetSysTime(&now);
        reads++;
        d = us_diff(&prev, &now);
        if (d < 0 || d > 500000) {
            if (d < 0) { back++; if (-d > worst_back) worst_back = -d; }
            else { jump++; if (d > worst_jump) worst_jump = d; }
            if (shown++ < 6)
                printf("  %s %lu.%06lu -> %lu.%06lu\n", d < 0 ? "back" : "jump",
                    (unsigned long)prev.tv_secs, (unsigned long)prev.tv_micro,
                    (unsigned long)now.tv_secs, (unsigned long)now.tv_micro);
        }
        prev = now;
        if (up) {
            if (now.tv_secs - start.tv_secs >= secs) break;
        } else if (reads >= 2000000 || (now.tv_secs - start.tv_secs >= secs && now.tv_secs >= start.tv_secs)) {
            break;
        }
    }
    printf("%s: %lu reads, %lu back (largest %ld us), %lu jumps (largest %ld us)\n",
        name, (unsigned long)reads, (unsigned long)back, (long)worst_back,
        (unsigned long)jump, (long)worst_jump);
}

int main(int argc, char **argv)
{
    struct timerequest tr;
    ULONG secs = argc > 1 ? (ULONG)atol(argv[1]) : 20;

    if (OpenDevice("timer.device", UNIT_MICROHZ, (struct IORequest *)&tr, 0) != 0)
        return 20;
    TimerBase = tr.tr_node.io_Device;
    run("uptime", 1, secs);
    run("systime", 0, secs);
    CloseDevice((struct IORequest *)&tr);
    return 0;
}
