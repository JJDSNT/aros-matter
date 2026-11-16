/*
 * waitsel_time - what a WaitSelect() timeout really waits on this AROS
 * (B69: mdnsd's loop sleeps until its next deadline), and how fine
 * DateStamp() (mdnsd's mdnsTicks(), fiftieths of a second) steps.
 *
 * For each timeout (0, 5, 20, 40, 250 ms, 1 s), REPS WaitSelect() calls with
 * no descriptor and no signal: the time each took by timer.device
 * (GetSysTime(), microseconds) - min, mean, max - and how many of them
 * returned before the time asked. Then DateStamp(): the smallest step seen
 * in its ticks over 2 s of reading it, and how many reads one step took.
 */
#define __CONFIG_ROADSHOW__
#include <exec/types.h>
#include <devices/timer.h>
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/timer.h>
#include <proto/socket.h>
#include <sys/time.h>
#include <stdio.h>

struct Library *SocketBase;
struct Device *TimerBase;

#define REPS 20

static LONG ticks_of(void)
{
    struct DateStamp ds;

    DateStamp(&ds);
    return ds.ds_Days * 4320000L + ds.ds_Minute * 3000L + ds.ds_Tick;
}

static ULONG us_between(const struct timeval *a, const struct timeval *b)
{
    return (ULONG)((b->tv_sec - a->tv_sec) * 1000000L + (b->tv_usec - a->tv_usec));
}

int main(void)
{
    static const ULONG asks[] = { 0, 5000, 20000, 40000, 250000, 1000000 };
    struct timerequest tr;
    struct timeval t0, t1, tv;
    ULONG k, i;

    SocketBase = OpenLibrary("bsdsocket.library", 4);
    if (SocketBase == NULL || OpenDevice("timer.device", UNIT_MICROHZ, (struct IORequest *)&tr, 0) != 0)
        return 20;
    TimerBase = tr.tr_node.io_Device;
    for (k = 0; k < sizeof(asks) / sizeof(asks[0]); k++) {
        ULONG min = 0xffffffffUL, max = 0, sum = 0, early = 0;
        LONG dsmin = 0x7fffffff, dsmax = 0;

        for (i = 0; i < (asks[k] >= 250000 ? 5 : REPS); i++) {
            ULONG mask = 0, took;
            LONG d0, d1;

            tv.tv_sec = asks[k] / 1000000;
            tv.tv_usec = asks[k] % 1000000;
            d0 = ticks_of();
            GetSysTime(&t0);
            WaitSelect(0, NULL, NULL, NULL, &tv, &mask);
            GetSysTime(&t1);
            d1 = ticks_of();
            took = us_between(&t0, &t1);
            if (took < min) min = took;
            if (took > max) max = took;
            sum += took;
            if (took < asks[k])
                early++;
            if (d1 - d0 < dsmin) dsmin = d1 - d0;
            if (d1 - d0 > dsmax) dsmax = d1 - d0;
        }
        i = asks[k] >= 250000 ? 5 : REPS;
        printf("ask %7lu us: took min %7lu mean %7lu max %7lu us; early %lu/%lu; DateStamp ticks %ld..%ld\n",
            (unsigned long)asks[k], (unsigned long)min, (unsigned long)(sum / i),
            (unsigned long)max, (unsigned long)early, (unsigned long)i, (long)dsmin, (long)dsmax);
    }
    {
        LONG prev = ticks_of(), now, step = 0x7fffffff;
        ULONG reads = 0, steps = 0;

        GetSysTime(&t0);
        do {
            now = ticks_of();
            reads++;
            if (now != prev) {
                if (now - prev < step)
                    step = now - prev;
                steps++;
                prev = now;
            }
            GetSysTime(&t1);
        } while (us_between(&t0, &t1) < 2000000);
        printf("DateStamp over 2 s: %lu steps, smallest %ld tick(s), %lu reads\n",
            (unsigned long)steps, (long)step, (unsigned long)reads);
    }
    CloseDevice((struct IORequest *)&tr);
    CloseLibrary(SocketBase);
    return 0;
}
